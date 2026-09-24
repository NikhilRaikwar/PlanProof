from __future__ import annotations

import asyncio
import hashlib
import shutil
import subprocess
import sys
import tempfile
from os import environ
from pathlib import Path

from pymongo.errors import DuplicateKeyError

from app.core.config import Settings, get_settings
from app.domain.runs import PathKind, SnapshotManifestEntry, SnapshotStatus
from app.ingestion.parsers import ExtractedSymbol, extract_jsts_symbols, extract_python_symbols
from app.ingestion.sources import (
    GitHubAppSource,
    PublicGitHubSource,
    RepositorySource,
    SeededFixtureSource,
)
from app.repositories.runs import RunRepository

PARSER_VERSION = "ast-regex-v1"
INDEX_VERSION = "files-symbols-v1"
_IGNORE_DIRS = {
    ".git",
    "node_modules",
    ".next",
    "dist",
    "build",
    "coverage",
    ".venv",
    "venv",
    "__pycache__",
    "vendor",
    "generated",
}
_LANGUAGES = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
}


class SnapshotIngestionService:
    def __init__(self, records: RunRepository, settings: Settings | None = None) -> None:
        self.records = records
        self.settings = settings or get_settings()

    async def ingest(self, snapshot_id: str, source: RepositorySource):
        snapshot = await self.records.get_snapshot(snapshot_id)
        if snapshot is None:
            raise ValueError("snapshot not found")
        workspace: Path | None = None
        try:
            snapshot.status = SnapshotStatus.RESOLVING
            await self.records.update_snapshot(snapshot)
            snapshot.status = SnapshotStatus.MATERIALIZING
            await self.records.update_snapshot(snapshot)
            workspace, repository_root, sha = self._materialize(source)
            existing = await self.records.get_ready_snapshot(
                snapshot.project_id,
                source.identity,
                sha,
                snapshot.parser_version,
                snapshot.index_version,
            )
            if existing is not None and existing.id != snapshot.id:
                await self.records.delete_snapshot(snapshot.id)
                return existing
            snapshot.resolved_commit_sha = sha
            snapshot.status = SnapshotStatus.HASHING
            try:
                await self.records.update_snapshot(snapshot)
            except DuplicateKeyError as error:
                legacy_doc = await self.records._database.repository_snapshots.find_one(
                    {
                        "project_id": snapshot.project_id,
                        "repository_identity": source.identity,
                        "resolved_commit_sha": sha,
                        "parser_version": snapshot.parser_version,
                        "index_version": snapshot.index_version,
                    }
                )
                if legacy_doc and not legacy_doc.get("manifest_complete"):
                    await self.records.delete_snapshot(legacy_doc["id"])
                    await self.records.update_snapshot(snapshot)
                else:
                    for _ in range(20):
                        existing = await self.records.get_ready_snapshot(
                            snapshot.project_id,
                            source.identity,
                            sha,
                            snapshot.parser_version,
                            snapshot.index_version,
                        )
                        if existing is not None:
                            await self.records.delete_snapshot(snapshot.id)
                            return existing
                        await asyncio.sleep(0.05)
                    snapshot.resolved_commit_sha = None
                    snapshot.status = SnapshotStatus.FAILED
                    snapshot.failure_category = "INGESTION_CONFLICT"
                    await self.records.update_snapshot(snapshot)
                    raise RuntimeError("immutable snapshot conflict") from error
            files, root_hash, ignored_files = self._inventory(repository_root)
            manifest_entries, manifest_hash = self._inventory_manifest(
                repository_root, snapshot.id, is_git=not isinstance(source, SeededFixtureSource)
            )
            snapshot.root_content_hash = root_hash
            snapshot.manifest_complete = True
            snapshot.manifest_entry_count = len(manifest_entries)
            snapshot.manifest_hash = manifest_hash
            snapshot.files_discovered = len(files)
            snapshot.files_indexed = len(files)
            snapshot.ignored_files = ignored_files
            snapshot.supported_languages = sorted({file["language"] for file in files})
            snapshot.status = SnapshotStatus.PARSING
            await self.records.update_snapshot(snapshot)
            symbols = self._symbols(files)
            snapshot.status = SnapshotStatus.INDEXING
            await self.records.update_snapshot(snapshot)
            await self.records.replace_index(snapshot.id, files, symbols)
            await self.records.replace_manifest(snapshot.id, manifest_entries)
            snapshot.files_indexed = len(files)
            snapshot.symbols_indexed = len(symbols)
            snapshot.status = SnapshotStatus.READY
            await self.records.update_snapshot(snapshot)
            return snapshot
        except Exception:
            snapshot.status = SnapshotStatus.FAILED
            snapshot.failure_category = "INGESTION_FAILED"
            await self.records.update_snapshot(snapshot)
            raise
        finally:
            if workspace is not None:
                shutil.rmtree(workspace, ignore_errors=True)

    def _materialize(self, source: RepositorySource) -> tuple[Path, Path, str]:
        root = Path(tempfile.mkdtemp(prefix="planproof-ingest-"))
        destination = root / "repository"
        try:
            if isinstance(source, SeededFixtureSource):
                shutil.copytree(source.fixture_path, destination, symlinks=False)
                self._check_workspace_size(destination)
                return root, destination, hashlib.sha256(self._tree_bytes(destination)).hexdigest()

            assert isinstance(source, (PublicGitHubSource, GitHubAppSource))
            command = [
                "git",
                "-c",
                "credential.helper=",
                "clone",
                "--depth",
                "1",
                "--single-branch",
                "--no-tags",
            ]
            git_environment = {
                **environ,
                "GIT_TERMINAL_PROMPT": "0",
                "GCM_INTERACTIVE": "Never",
                "GIT_LFS_SKIP_SMUDGE": "1",
            }

            clone_target = source.clone_url
            if isinstance(source, GitHubAppSource):
                # Token security: Pass credential via GIT_ASKPASS script to prevent token in process argv
                askpass_script = root / "askpass.py"
                askpass_script.write_text(
                    "import os, sys\nsys.stdout.write(os.environ.get('PLANPROOF_GIT_TOKEN', ''))\n",
                    encoding="utf-8",
                )
                git_environment["GIT_ASKPASS"] = f"{sys.executable} {askpass_script.as_posix()}"
                git_environment["PLANPROOF_GIT_TOKEN"] = source.installation_token
                clone_target = f"https://x-access-token@github.com/{source.owner}/{source.repository}.git"

            if source.requested_ref:
                command.extend(["--branch", source.requested_ref])
            command.extend([clone_target, str(destination)])

            subprocess.run(
                command,
                check=True,
                capture_output=True,
                timeout=60,
                env=git_environment,
            )

            self._check_workspace_size(destination)

            sha = subprocess.run(
                ["git", "-C", str(destination), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.strip()
            return root, destination, sha
        except Exception:
            shutil.rmtree(root, ignore_errors=True)
            raise

    def _check_workspace_size(self, root: Path) -> None:
        total_size = 0
        for p in root.rglob("*"):
            if p.is_file() and not p.is_symlink():
                total_size += p.stat().st_size
                if total_size > self.settings.planproof_max_repo_workspace_bytes:
                    raise ValueError(
                        f"repository workspace size ({total_size} bytes) exceeds maximum limit of {self.settings.planproof_max_repo_workspace_bytes} bytes"
                    )

    def _inventory(self, root: Path) -> tuple[list[dict], str, int]:
        entries: list[dict] = []
        ignored = 0
        total_indexed_bytes = 0

        for path in sorted(root.rglob("*")):
            relative_path = path.relative_to(root)
            if any(part in _IGNORE_DIRS for part in relative_path.parts):
                if path.is_file() or path.is_symlink():
                    ignored += 1
                continue
            if not path.is_file() or path.is_symlink():
                continue
            relative = relative_path.as_posix()
            if path.stat().st_size > 1_000_000:
                ignored += 1
                continue
            raw = path.read_bytes()
            if b"\0" in raw or path.suffix.lower() not in _LANGUAGES:
                ignored += 1
                continue

            total_indexed_bytes += len(raw)
            if total_indexed_bytes > self.settings.planproof_max_indexed_bytes:
                raise ValueError(
                    f"indexed repository bytes ({total_indexed_bytes}) exceed maximum limit of {self.settings.planproof_max_indexed_bytes} bytes"
                )

            entries.append(
                {
                    "relative_path": relative,
                    "content_hash": hashlib.sha256(raw).hexdigest(),
                    "size_bytes": len(raw),
                    "language": _LANGUAGES[path.suffix.lower()],
                    "index_state": "INDEXED",
                    "text": raw.decode("utf-8", errors="strict"),
                }
            )

            if len(entries) > self.settings.planproof_max_repo_files:
                raise ValueError(
                    f"repository file count ({len(entries)}) exceeds maximum limit of {self.settings.planproof_max_repo_files} files"
                )

        root_hash = hashlib.sha256(
            "".join(f"{x['relative_path']}:{x['content_hash']}\n" for x in entries).encode()
        ).hexdigest()
        return entries, root_hash, ignored

    def _symbols(self, files: list[dict]) -> list[dict]:
        result: list[dict] = []
        for file in files:
            extracted: list[ExtractedSymbol] = (
                extract_python_symbols(Path(file["relative_path"]), file["text"])
                if file["language"] == "python"
                else extract_jsts_symbols(file["text"])
            )
            result.extend(
                {"relative_path": file["relative_path"], **symbol.__dict__} for symbol in extracted
            )
        return result

    @staticmethod
    def _tree_bytes(root: Path) -> bytes:
        return b"".join(path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file())

    def _inventory_manifest(
        self, root: Path, snapshot_id: str, is_git: bool
    ) -> tuple[list[SnapshotManifestEntry], str]:
        entries: list[SnapshotManifestEntry] = []
        if is_git:
            res = subprocess.run(
                ["git", "-C", str(root), "ls-tree", "-r", "-z", "HEAD"],
                check=True,
                capture_output=True,
                timeout=30,
            )
            raw_output = res.stdout
            records = raw_output.split(b"\0")
            for record in records:
                if not record:
                    continue
                tab_index = record.find(b"\t")
                if tab_index == -1:
                    continue
                meta = record[:tab_index].decode("utf-8", errors="replace")
                path_str = record[tab_index + 1 :].decode("utf-8", errors="replace")
                meta_parts = meta.split()
                if len(meta_parts) != 3:
                    continue
                git_mode, object_type, object_sha = meta_parts
                if git_mode == "160000" or object_type == "commit":
                    kind = PathKind.SUBMODULE_GITLINK
                elif git_mode.startswith("12"):
                    kind = PathKind.SYMLINK
                else:
                    kind = PathKind.REGULAR_BLOB
                entries.append(
                    SnapshotManifestEntry(
                        snapshot_id=snapshot_id,
                        path=path_str,
                        git_mode=git_mode,
                        object_type=object_type,
                        object_sha=object_sha,
                        path_kind=kind,
                    )
                )
                if len(entries) > self.settings.planproof_max_manifest_entries:
                    raise ValueError(
                        f"manifest entry count exceeds maximum limit of {self.settings.planproof_max_manifest_entries}"
                    )
        else:
            for path in sorted(root.rglob("*")):
                if path.is_symlink():
                    rel = path.relative_to(root).as_posix()
                    entries.append(
                        SnapshotManifestEntry(
                            snapshot_id=snapshot_id,
                            path=rel,
                            git_mode="120000",
                            object_type="blob",
                            object_sha=hashlib.sha256(str(path.readlink()).encode()).hexdigest(),
                            path_kind=PathKind.SYMLINK,
                        )
                    )
                elif path.is_file():
                    rel = path.relative_to(root).as_posix()
                    raw = path.read_bytes()
                    entries.append(
                        SnapshotManifestEntry(
                            snapshot_id=snapshot_id,
                            path=rel,
                            git_mode="100644",
                            object_type="blob",
                            object_sha=hashlib.sha256(raw).hexdigest(),
                            path_kind=PathKind.REGULAR_BLOB,
                        )
                    )
                if len(entries) > self.settings.planproof_max_manifest_entries:
                    raise ValueError(
                        f"manifest entry count exceeds maximum limit of {self.settings.planproof_max_manifest_entries}"
                    )

        entries.sort(key=lambda e: e.path)
        manifest_hash = hashlib.sha256(
            "".join(
                f"{e.git_mode} {e.object_type} {e.object_sha}\t{e.path}\n" for e in entries
            ).encode("utf-8")
        ).hexdigest()
        return entries, manifest_hash
