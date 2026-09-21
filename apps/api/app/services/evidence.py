import hashlib

from app.domain.verification import Evidence, EvidenceType, ToolRunStatus, ValidatorResult
from app.repositories.verification import VerificationRepository


class EvidenceAuthority:
    """Only deterministic tool runs may issue evidence with source provenance."""

    def __init__(self, repository: VerificationRepository) -> None:
        self.repository = repository

    async def issue_source_range(
        self,
        *,
        snapshot_id: str,
        tool_run_id: str,
        path: str,
        line_start: int,
        line_end: int,
        summary: str,
        run_id: str | None = None,
        obligation_id: str | None = None,
        matched_query: str | None = None,
        relationship: str | None = None,
    ) -> Evidence:
        tool_run = await self.repository.get_tool_run(tool_run_id)
        if (
            not tool_run
            or tool_run.status != ToolRunStatus.SUCCEEDED
            or tool_run.snapshot_id != snapshot_id
            or tool_run.tool_name not in {"read_file_range", "search_code_lexical"}
        ):
            raise ValueError("tool run is not authorized to issue evidence for this snapshot")
        file = await self.repository.database.repository_files.find_one(
            {"snapshot_id": snapshot_id, "path": path}
        )
        if not file or line_start < 1 or line_end < line_start:
            raise ValueError("invalid evidence source range")
        lines = file.get("text", "").splitlines()
        if line_end > len(lines):
            raise ValueError("invalid evidence source range")
        return await self.repository.create_evidence(
            Evidence(
                snapshot_id=snapshot_id,
                run_id=run_id,
                obligation_id=obligation_id,
                source_tool_run_id=tool_run_id,
                evidence_type=EvidenceType.SOURCE_RANGE,
                path=path,
                line_start=line_start,
                line_end=line_end,
                content_hash=file["content_hash"],
                matched_query=matched_query,
                relationship=relationship,
                summary=summary,
            )
        )

    async def validate(self, evidence_id: str) -> Evidence:
        evidence = await self.repository.get_evidence(evidence_id)
        if not evidence:
            raise ValueError("evidence does not exist")
        tool_run = await self.repository.get_tool_run(evidence.source_tool_run_id)
        if (
            not tool_run
            or tool_run.status != ToolRunStatus.SUCCEEDED
            or tool_run.snapshot_id != evidence.snapshot_id
        ):
            raise ValueError("evidence provenance is invalid")
        if evidence.evidence_type != EvidenceType.SOURCE_RANGE or tool_run.tool_name not in {
            "read_file_range",
            "search_code_lexical",
        }:
            raise ValueError("tool cannot issue this evidence type")
        file = await self.repository.database.repository_files.find_one(
            {"snapshot_id": evidence.snapshot_id, "path": evidence.path}
        )
        if not file or hashlib.sha256(file.get("text", "").encode()).hexdigest() != file.get(
            "content_hash"
        ):
            raise ValueError("source content hash is stale")
        if file["content_hash"] != evidence.content_hash:
            raise ValueError("evidence content hash is stale")
        lines = file.get("text", "").splitlines()
        if not evidence.line_start or not evidence.line_end or evidence.line_end > len(lines):
            raise ValueError("evidence source range is invalid")
        return evidence


async def validate_symbol_exists(
    repository: VerificationRepository, snapshot_id: str, symbol: str
) -> ValidatorResult:
    item = await repository.database.code_symbols.find_one(
        {"snapshot_id": snapshot_id, "qualified_name": symbol}
    )
    return ValidatorResult.SATISFIED if item else ValidatorResult.INSUFFICIENT


async def validate_file_exists(
    repository: VerificationRepository, snapshot_id: str, path: str
) -> ValidatorResult:
    item = await repository.database.repository_files.find_one(
        {"snapshot_id": snapshot_id, "path": path}
    )
    return ValidatorResult.SATISFIED if item else ValidatorResult.CONTRADICTED


async def validate_source_contains(
    repository: VerificationRepository,
    snapshot_id: str,
    path: str,
    token: str,
) -> ValidatorResult:
    item = await repository.database.repository_files.find_one(
        {"snapshot_id": snapshot_id, "path": path}
    )
    if not item or "text" not in item:
        return ValidatorResult.INSUFFICIENT
    return ValidatorResult.SATISFIED if token in item["text"] else ValidatorResult.CONTRADICTED
