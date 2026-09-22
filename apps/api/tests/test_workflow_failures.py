from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.domain.runs import VerificationRun, VerificationRunStatus
from app.domain.verification import (
    Criticality,
    ObligationCategory,
    ObligationStatus,
    ProofObligation,
)
from app.workflow.engine import VerificationWorkflow


class FakeRuns:
    def __init__(self, run):
        self.run = run
        self.update_run = AsyncMock()
        self.append_event = AsyncMock()
        self.get_snapshot = AsyncMock(return_value=None)
        self.get_plan_version = AsyncMock(
            return_value=SimpleNamespace(change_request="c", candidate_plan="p")
        )

    async def get_run(self, _id):
        return self.run


class FakeVerification:
    def __init__(self, obligations):
        self.obligations = obligations
        self.create_tool_run = AsyncMock()
        self.update_obligation = AsyncMock()
        self.database = SimpleNamespace(
            events=SimpleNamespace(find_one=AsyncMock(return_value=None)),
            evidence=SimpleNamespace(find=lambda *args, **kwargs: AsyncIteratorMock([])),
            repository_files=SimpleNamespace(find_one=AsyncMock(return_value=None)),
            tool_runs=SimpleNamespace(find_one=AsyncMock(return_value=None)),
        )

    async def list_run_obligations(self, _id):
        return self.obligations


class AsyncIteratorMock:
    def __init__(self, items):
        self.items = items

    def __aiter__(self):
        self._iter = iter(self.items)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


@pytest.mark.asyncio
async def test_provider_or_schema_failure_marks_run_failed_without_verification(
    monkeypatch,
) -> None:
    run = VerificationRun(project_id="p", snapshot_id="s", plan_version_id="plan")
    runs, verification = FakeRuns(run), FakeVerification([])

    async def fail_extract(*args, **kwargs):
        raise ValueError("malformed structured output")

    monkeypatch.setattr("app.workflow.engine.ObligationExtractionService.extract", fail_extract)
    await VerificationWorkflow(runs, verification, Settings()).run(run.id)
    assert run.status == VerificationRunStatus.FAILED
    assert verification.update_obligation.await_count == 0


@pytest.mark.asyncio
async def test_tool_failure_records_failed_run_and_never_verifies(monkeypatch) -> None:
    run = VerificationRun(project_id="p", snapshot_id="s", plan_version_id="plan")
    obligation = ProofObligation(
        project_id="p",
        snapshot_id="s",
        plan_version_id="plan",
        run_id=run.id,
        statement="Provider accepts refund amount",
        normalized_statement="provider accepts refund amount",
        category=ObligationCategory.BEHAVIOR,
        criticality=Criticality.HIGH,
    )
    runs, verification = FakeRuns(run), FakeVerification([obligation])

    async def fail_search(*args, **kwargs):
        raise TimeoutError("tool timeout")

    monkeypatch.setattr("app.workflow.engine.RepositoryTools.search_code_lexical", fail_search)
    await VerificationWorkflow(runs, verification, Settings()).run(run.id)
    assert obligation.status == ObligationStatus.INCONCLUSIVE
    assert verification.create_tool_run.await_count >= 1
    assert not obligation.evidence_ids and not obligation.counter_evidence_ids
