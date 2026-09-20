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
    ) -> Evidence:
        tool_run = await self.repository.get_tool_run(tool_run_id)
        if (
            not tool_run
            or tool_run.status != ToolRunStatus.SUCCEEDED
            or tool_run.snapshot_id != snapshot_id
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
                source_tool_run_id=tool_run_id,
                evidence_type=EvidenceType.SOURCE_RANGE,
                path=path,
                line_start=line_start,
                line_end=line_end,
                content_hash=file["content_hash"],
                summary=summary,
            )
        )


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
