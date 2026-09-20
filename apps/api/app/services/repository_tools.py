from __future__ import annotations

import hashlib
import json
import time
from fnmatch import fnmatch
from pathlib import PurePosixPath

from pydantic import BaseModel, Field

from app.domain.runs import SnapshotStatus
from app.domain.verification import ToolRun, ToolRunStatus
from app.repositories.runs import RunRepository
from app.repositories.verification import VerificationRepository


class ToolInput(BaseModel):
    snapshot_id: str = Field(min_length=1)
    limit: int = Field(default=25, ge=1, le=100)


class ListFilesInput(ToolInput):
    prefix: str | None = Field(default=None, max_length=300)
    glob: str | None = Field(default=None, max_length=100)
    language: str | None = Field(default=None, max_length=20)


class SearchCodeInput(ToolInput):
    query: str = Field(min_length=1, max_length=200)
    path: str | None = None
    language: str | None = None
    context_lines: int = Field(default=2, ge=0, le=5)


class ReadFileRangeInput(ToolInput):
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class FindSymbolInput(ToolInput):
    query: str = Field(min_length=1, max_length=200)
    kind: str | None = None
    path: str | None = None


class RepositoryTools:
    def __init__(self, runs: RunRepository, audit: VerificationRepository) -> None:
        self.runs = runs
        self.audit = audit
        self.database = audit.database

    async def list_files(self, data: ListFilesInput) -> list[dict]:
        query: dict = {"snapshot_id": data.snapshot_id}
        if data.language:
            query["language"] = data.language
        files = await self._files(data.snapshot_id, query)
        result = [
            {key: item[key] for key in ("path", "language", "size_bytes", "content_hash")}
            for item in files
            if (not data.prefix or item["path"].startswith(data.prefix))
            and (not data.glob or fnmatch(item["path"], data.glob))
        ][: data.limit]
        await self._audit("list_files", data, len(result))
        return result

    async def search_code_lexical(self, data: SearchCodeInput) -> list[dict]:
        files = await self._files(data.snapshot_id, {"snapshot_id": data.snapshot_id})
        matches: list[dict] = []
        needle = data.query.casefold()
        for item in files:
            if data.path and item["path"] != self._safe_path(data.path):
                continue
            if data.language and item["language"] != data.language:
                continue
            lines = item.get("text", "").splitlines()
            for line_no, line in enumerate(lines, 1):
                if needle in line.casefold():
                    start = max(1, line_no - data.context_lines)
                    end = min(len(lines), line_no + data.context_lines)
                    matches.append(
                        {
                            "path": item["path"],
                            "line_start": start,
                            "line_end": end,
                            "content_hash": item["content_hash"],
                            "content": "\n".join(lines[start - 1 : end]),
                        }
                    )
                    if len(matches) >= data.limit:
                        await self._audit("search_code_lexical", data, len(matches))
                        return matches
        await self._audit("search_code_lexical", data, len(matches))
        return matches

    async def read_file_range(self, data: ReadFileRangeInput) -> dict:
        if data.end_line < data.start_line or data.end_line - data.start_line >= 200:
            raise ValueError("invalid or oversized line range")
        path = self._safe_path(data.path)
        item = await self.database.repository_files.find_one(
            {"snapshot_id": data.snapshot_id, "path": path}
        )
        if not item or "text" not in item:
            raise ValueError("source file not available in snapshot")
        lines = item["text"].splitlines()
        if data.start_line > len(lines):
            raise ValueError("line range is outside file")
        content = "\n".join(lines[data.start_line - 1 : min(data.end_line, len(lines))])
        if len(content.encode()) > 32_000:
            raise ValueError("requested content is too large")
        result = {
            "path": path,
            "line_start": data.start_line,
            "line_end": min(data.end_line, len(lines)),
            "content": content,
            "content_hash": item["content_hash"],
        }
        await self._audit("read_file_range", data, 1)
        return result

    async def find_symbol(self, data: FindSymbolInput) -> list[dict]:
        await self._ready(data.snapshot_id)
        query: dict = {
            "snapshot_id": data.snapshot_id,
            "qualified_name": {"$regex": data.query, "$options": "i"},
        }
        if data.kind:
            query["kind"] = data.kind
        if data.path:
            query["path"] = self._safe_path(data.path)
        result = [
            {
                key: item[key]
                for key in (
                    "qualified_name",
                    "kind",
                    "path",
                    "line_start",
                    "line_end",
                    "is_exported",
                )
            }
            async for item in self.database.code_symbols.find(query)
            .sort("path", 1)
            .limit(data.limit)
        ]
        await self._audit("find_symbol", data, len(result))
        return result

    async def find_references(self, data: FindSymbolInput) -> dict:
        symbols = await self.find_symbol(data)
        return {"completeness": "PARTIAL_LEXICAL", "symbols": symbols}

    async def _files(self, snapshot_id: str, query: dict) -> list[dict]:
        await self._ready(snapshot_id)
        return [item async for item in self.database.repository_files.find(query).sort("path", 1)]

    async def _ready(self, snapshot_id: str) -> None:
        snapshot = await self.runs.get_snapshot(snapshot_id)
        if not snapshot or snapshot.status != SnapshotStatus.READY:
            raise ValueError("snapshot is not READY")

    @staticmethod
    def _safe_path(value: str) -> str:
        path = PurePosixPath(value)
        if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
            raise ValueError("path must be normalized and snapshot-relative")
        return path.as_posix()

    async def _audit(self, tool_name: str, data: BaseModel, count: int) -> ToolRun:
        started = time.monotonic()
        normalized = data.model_dump(mode="json")
        item = ToolRun(
            snapshot_id=data.snapshot_id,
            tool_name=tool_name,
            input_hash=hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest(),
            status=ToolRunStatus.SUCCEEDED,
            result_count=count,
            duration_ms=max(0, int((time.monotonic() - started) * 1000)),
        )
        return await self.audit.create_tool_run(item)
