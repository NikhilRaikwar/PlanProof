import hashlib

from app.domain.verification import Evidence, EvidenceType, ToolRunStatus, ValidatorResult
from app.repositories.verification import VerificationRepository


async def _inspect_path_manifest_state(
    database, snapshot_id: str, path: str
) -> tuple[str, dict | None]:
    """
    Recompute authoritative state for path membership against the snapshot manifest:
    Returns (PRESENT | ABSENT | INCONCLUSIVE, snapshot_doc)
    """
    snapshots_col = getattr(database, "repository_snapshots", None)
    snapshot = await snapshots_col.find_one({"id": snapshot_id}) if snapshots_col else None
    if not snapshot or snapshot.get("status") != "READY":
        return "INCONCLUSIVE", snapshot

    manifest_col = getattr(database, "snapshot_manifest", None)
    if manifest_col is not None:
        entry = await manifest_col.find_one({"snapshot_id": snapshot_id, "path": path})
        if entry is not None:
            return "PRESENT", snapshot

        # Inspect submodule ancestor
        parts = path.strip("/").split("/")
        candidate_prefixes = ["/".join(parts[:i]) for i in range(1, len(parts))]
        if candidate_prefixes:
            submodule_ancestor = await manifest_col.find_one(
                {
                    "snapshot_id": snapshot_id,
                    "path": {"$in": candidate_prefixes},
                    "path_kind": "submodule_gitlink",
                }
            )
            if submodule_ancestor is not None:
                return "INCONCLUSIVE", snapshot

    # If repository_files contains it (fallback)
    repo_files_col = getattr(database, "repository_files", None)
    if repo_files_col is not None:
        file_doc = await repo_files_col.find_one({"snapshot_id": snapshot_id, "path": path})
        if file_doc is not None:
            return "PRESENT", snapshot

    if snapshot.get("manifest_complete"):
        return "ABSENT", snapshot

    return "INCONCLUSIVE", snapshot


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
            or tool_run.tool_name not in {"read_file_range", "search_code_lexical", "find_symbol"}
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

    async def issue_path_membership(
        self,
        *,
        snapshot_id: str,
        tool_run_id: str,
        path: str,
        present: bool,
        summary: str,
        run_id: str | None = None,
        obligation_id: str | None = None,
        relationship: str | None = None,
    ) -> Evidence:
        tool_run = await self.repository.get_tool_run(tool_run_id)
        if (
            not tool_run
            or tool_run.status != ToolRunStatus.SUCCEEDED
            or tool_run.snapshot_id != snapshot_id
            or tool_run.tool_name != "check_path_membership"
        ):
            raise ValueError(
                "tool run is not authorized to issue path membership evidence for this snapshot"
            )

        state, snapshot = await _inspect_path_manifest_state(
            self.repository.database, snapshot_id, path
        )
        if not snapshot or snapshot.get("status") != "READY":
            raise ValueError("snapshot is not ready for path membership evidence")

        if state == "PRESENT":
            if not present or relationship == "CONTRADICTS":
                raise ValueError("cannot issue negative membership evidence for present path")
            target_relationship = relationship or "SUPPORTS"
        elif state == "ABSENT":
            if present or relationship == "SUPPORTS":
                raise ValueError("cannot issue positive membership evidence for absent path")
            target_relationship = relationship or "CONTRADICTS"
        else:
            raise ValueError(
                "cannot issue conclusive membership evidence for inconclusive or submodule child path"
            )

        manifest_hash = snapshot.get("manifest_hash") or snapshot.get("root_content_hash")

        return await self.repository.create_evidence(
            Evidence(
                snapshot_id=snapshot_id,
                run_id=run_id,
                obligation_id=obligation_id,
                source_tool_run_id=tool_run_id,
                evidence_type=EvidenceType.SNAPSHOT_PATH_MEMBERSHIP,
                path=path,
                content_hash=manifest_hash,
                matched_query=path,
                relationship=target_relationship,
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

        if evidence.run_id and tool_run.run_id and evidence.run_id != tool_run.run_id:
            raise ValueError("evidence run_id does not match tool run run_id")

        if evidence.evidence_type == EvidenceType.SNAPSHOT_PATH_MEMBERSHIP:
            if tool_run.tool_name != "check_path_membership":
                raise ValueError("tool cannot issue snapshot path membership evidence")
            state, snapshot = await _inspect_path_manifest_state(
                self.repository.database, evidence.snapshot_id, evidence.path
            )
            if not snapshot or snapshot.get("status") != "READY":
                raise ValueError("snapshot is not ready for path membership validation")

            if tool_run.input_summary and tool_run.input_summary.get("path") != evidence.path:
                raise ValueError("canonical path does not match tool input")

            expected_hash = snapshot.get("manifest_hash") or snapshot.get("root_content_hash")
            if evidence.content_hash != expected_hash:
                raise ValueError(
                    "snapshot manifest hash does not match persisted manifest authority"
                )

            if state == "PRESENT" and evidence.relationship != "SUPPORTS":
                raise ValueError("path is present but evidence relationship is not SUPPORTS")
            elif state == "ABSENT" and evidence.relationship != "CONTRADICTS":
                raise ValueError("path is absent but evidence relationship is not CONTRADICTS")
            elif state == "INCONCLUSIVE":
                raise ValueError(
                    "cannot validate conclusive path membership evidence for inconclusive state"
                )

            return evidence

        if evidence.evidence_type != EvidenceType.SOURCE_RANGE or tool_run.tool_name not in {
            "read_file_range",
            "search_code_lexical",
            "find_symbol",
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
    state, snapshot = await _inspect_path_manifest_state(repository.database, snapshot_id, path)
    if state == "PRESENT":
        return ValidatorResult.SATISFIED
    elif state == "ABSENT":
        return ValidatorResult.CONTRADICTED
    return ValidatorResult.INSUFFICIENT


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
