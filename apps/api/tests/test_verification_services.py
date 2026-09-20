import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.domain.verification import ToolRun, ToolRunStatus, ValidatorResult
from app.services.evidence import (
    EvidenceAuthority,
    validate_file_exists,
    validate_source_contains,
    validate_symbol_exists,
)
from app.services.obligations import ObligationExtractionService, ObligationProposals
from app.services.repository_tools import ReadFileRangeInput, RepositoryTools, ToolInput


class OneCollection:
    def __init__(self, item=None):
        self.item = item

    async def find_one(self, query):
        if self.item and all(self.item.get(k) == v for k, v in query.items()):
            return self.item
        return None


def test_tool_inputs_enforce_result_and_path_bounds() -> None:
    assert ToolInput(snapshot_id="s", limit=100).limit == 100
    with pytest.raises(ValidationError):
        ToolInput(snapshot_id="s", limit=101)
    for unsafe in ("../secret", "/etc/passwd", "C:\\Users\\secret"):
        with pytest.raises(ValueError):
            RepositoryTools._safe_path(unsafe)
    assert RepositoryTools._safe_path("services/payment.py") == "services/payment.py"
    with pytest.raises(ValidationError):
        ReadFileRangeInput(snapshot_id="s", path="x.py", start_line=0, end_line=1)


@pytest.mark.asyncio
async def test_evidence_authority_accepts_only_valid_server_provenance() -> None:
    text = "first\nsecond"
    file = {
        "snapshot_id": "s1",
        "path": "a.py",
        "text": text,
        "content_hash": hashlib.sha256(text.encode()).hexdigest(),
    }
    tool = ToolRun(
        snapshot_id="s1",
        tool_name="read_file_range",
        input_hash="a" * 64,
        status=ToolRunStatus.SUCCEEDED,
        result_count=1,
        duration_ms=1,
    )
    saved = {}
    repo = SimpleNamespace(database=SimpleNamespace(repository_files=OneCollection(file)))
    repo.get_tool_run = AsyncMock(return_value=tool)

    async def create(item):
        saved[item.id] = item
        return item

    repo.create_evidence = create
    repo.get_evidence = AsyncMock(side_effect=lambda item_id: saved.get(item_id))
    authority = EvidenceAuthority(repo)
    evidence = await authority.issue_source_range(
        snapshot_id="s1",
        tool_run_id=tool.id,
        path="a.py",
        line_start=1,
        line_end=1,
        summary="real fact",
    )
    assert await authority.validate(evidence.id) == evidence
    with pytest.raises(ValueError):
        await authority.validate("invented")
    repo.get_tool_run.return_value = tool.model_copy(update={"snapshot_id": "s2"})
    with pytest.raises(ValueError):
        await authority.validate(evidence.id)
    repo.get_tool_run.return_value = tool.model_copy(update={"status": ToolRunStatus.FAILED})
    with pytest.raises(ValueError):
        await authority.issue_source_range(
            snapshot_id="s1",
            tool_run_id=tool.id,
            path="a.py",
            line_start=1,
            line_end=1,
            summary="no",
        )
    repo.get_tool_run.return_value = tool
    file["text"] = "altered"
    with pytest.raises(ValueError):
        await authority.validate(evidence.id)


@pytest.mark.asyncio
async def test_deterministic_validators_are_typed() -> None:
    repo = SimpleNamespace(
        database=SimpleNamespace(
            repository_files=OneCollection({"snapshot_id": "s", "path": "a.py"}),
            code_symbols=OneCollection({"snapshot_id": "s", "qualified_name": "A.method"}),
        )
    )
    assert await validate_file_exists(repo, "s", "a.py") == ValidatorResult.SATISFIED
    assert await validate_file_exists(repo, "s", "missing.py") == ValidatorResult.CONTRADICTED
    assert await validate_symbol_exists(repo, "s", "A.method") == ValidatorResult.SATISFIED
    assert await validate_symbol_exists(repo, "s", "missing") == ValidatorResult.INSUFFICIENT
    repo.database.repository_files.item["text"] = "unique: true"
    assert (
        await validate_source_contains(repo, "s", "a.py", "unique: true")
        == ValidatorResult.SATISFIED
    )
    assert (
        await validate_source_contains(repo, "s", "a.py", "nullable: true")
        == ValidatorResult.CONTRADICTED
    )


class FakeGateway:
    def __init__(self, content):
        self.content = content

    async def complete(self, request):
        return SimpleNamespace(provider="mock", model="mock-model", content=self.content)


class ObligationRepo:
    def __init__(self):
        self.items = {}

    async def create_obligation(self, item):
        return self.items.setdefault((item.plan_version_id, item.normalized_statement), item)


@pytest.mark.asyncio
async def test_obligations_are_server_owned_pending_and_deduplicated() -> None:
    content = (
        '{"obligations":['
        '{"statement":"Symbol exists","category":"SYMBOL","criticality":"HIGH",'
        '"verification_hints":[]},'
        '{"statement":"  symbol   exists ","category":"SYMBOL","criticality":"LOW",'
        '"verification_hints":[]}]}'
    )
    repo = ObligationRepo()
    result = await ObligationExtractionService(FakeGateway(content), repo).extract(
        "p", "s", "pv", "change", "plan"
    )
    assert result[0].id == result[1].id
    assert result[0].status == "PENDING" and result[0].evidence_ids == []
    with pytest.raises(ValidationError):
        ObligationProposals.model_validate(
            {
                "obligations": [
                    {"statement": "valid claim", "category": "BAD", "criticality": "HIGH"}
                ]
            }
        )
