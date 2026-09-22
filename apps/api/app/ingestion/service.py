from __future__ import annotations

import asyncio
import hashlib
import shutil
import subprocess
import tempfile
from os import environ
from pathlib import Path

from pymongo.errors import DuplicateKeyError

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
    def __init__(self, records: RunRepository) -> None:
        self.records = records

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
                # A concurrent ingest may have resolved the same immutable source
                # between our preflight lookup and this unique-indexed transition.
                # Reuse only its completed immutable snapshot; never continue with
                # two competing index writers for the same identity.
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
                return root, destination, hashlib.sha256(self._tree_bytes(destination)).hexdigest()
            assert isinstance(source, (PublicGitHubSource, GitHubAppSource))
            command = ["git", "-c", "credential.helper=", "clone", "--depth", "1"]
            if isinstance(source, GitHubAppSource):
                # Avoid embedding credentials in the clone URL or persistent
                # repository state. git receives a short-lived header only.
                import base64

                basic = base64.b64encode(
                    f"x-access-token:{source.installation_token}".encode()
                ).decode()
                command[1:1] = ["-c", f"http.extraHeader=AUTHORIZATION: basic {basic}"]
            if source.requested_ref:
                command.extend(["--branch", source.requested_ref])
            command.extend([source.clone_url, str(destination)])
            git_environment = {**environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never"}
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                timeout=60,
                env=git_environment,
            )
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

    def _inventory(self, root: Path) -> tuple[list[dict], str, int]:
        entries: list[dict] = []
        ignored = 0
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

        entries.sort(key=lambda e: e.path)
        manifest_hash = hashlib.sha256(
            "".join(
                f"{e.git_mode} {e.object_type} {e.object_sha}\t{e.path}\n" for e in entries
            ).encode("utf-8")
        ).hexdigest()
        return entries, manifest_hash
