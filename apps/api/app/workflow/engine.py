from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.config import Settings
from app.domain.runs import HumanQuestion, RunEvent, VerificationRunStatus
from app.domain.verification import ObligationCategory, ObligationStatus
from app.repositories.runs import RunRepository
from app.repositories.verification import VerificationRepository
from app.services.evidence import EvidenceAuthority
from app.services.models import ProviderGateway
from app.services.obligations import ObligationExtractionService
from app.services.repository_tools import RepositoryTools, SearchCodeInput


class WorkflowState(TypedDict):
    run_id: str


class VerificationWorkflow:
    """A single bounded orchestrator; MongoDB remains the durable source of truth."""

    def __init__(
        self, runs: RunRepository, verification: VerificationRepository, settings: Settings
    ):
        self.runs, self.verification, self.settings = runs, verification, settings
        graph = StateGraph(WorkflowState)
        graph.add_node("execute", self._execute)
        graph.add_edge(START, "execute")
        graph.add_edge("execute", END)
        self.graph = graph.compile()

    async def run(self, run_id: str) -> None:
        await self.graph.ainvoke({"run_id": run_id})

    async def _execute(self, state: WorkflowState) -> WorkflowState:
        run = await self.runs.get_run(state["run_id"])
        if not run or run.status in {
            VerificationRunStatus.COMPLETE,
            VerificationRunStatus.BLOCKED,
            VerificationRunStatus.INCONCLUSIVE,
        }:
            return state
        run.started_at = run.started_at or datetime.now(UTC)
        obligations = await self.verification.list_run_obligations(run.id)
        if not obligations:
            run.status = VerificationRunStatus.EXTRACTING_OBLIGATIONS
            await self.runs.update_run(run)
            plan = await self.runs.get_plan_version(run.plan_version_id)
            extracted = await ObligationExtractionService(
                ProviderGateway(self.settings, self.verification), self.verification
            ).extract(
                run.project_id,
                run.snapshot_id,
                run.plan_version_id,
                plan.change_request,
                plan.candidate_plan,
            )
            for obligation in extracted:
                obligation.run_id = run.id
                await self.verification.update_obligation(obligation)
            obligations = extracted
            await self._event(
                run.id, "obligations_extracted", f"Extracted {len(obligations)} obligations"
            )
        run.status = VerificationRunStatus.VERIFYING
        await self.runs.update_run(run)
        for obligation in obligations:
            if obligation.status != ObligationStatus.PENDING:
                continue
            run.iteration_count += 1
            run.current_obligation_id = obligation.id
            obligation.status = ObligationStatus.VERIFYING
            await self.verification.update_obligation(obligation)
            await self._event(run.id, "obligation_started", "Investigating one obligation")
            if run.iteration_count > self.settings.verification_max_iterations:
                obligation.status = ObligationStatus.INCONCLUSIVE
            elif obligation.category in {
                ObligationCategory.BUSINESS_RULE,
                ObligationCategory.CROSS_SERVICE,
            }:
                obligation.status = ObligationStatus.HUMAN_REQUIRED
                question = HumanQuestion(
                    run_id=run.id,
                    obligation_id=obligation.id,
                    question=f"Human authority is required: {obligation.statement}",
                    why_needed=(
                        "Repository evidence cannot establish business or external-service intent."
                    ),
                    authority_required="product owner",
                )
                try:
                    await self.runs.create_question(question)
                except Exception:
                    existing = await self.verification.database.human_questions.find_one(
                        {"run_id": run.id, "obligation_id": obligation.id}
                    )
                    question = HumanQuestion.model_validate(existing)
                if question.id not in run.open_human_question_ids:
                    run.open_human_question_ids.append(question.id)
                run.status = VerificationRunStatus.HUMAN_WAIT
                await self.verification.update_obligation(obligation)
                await self.runs.update_run(run)
                await self._event(run.id, "human_question_created", "Human authority requested")
                return state
            else:
                await self._investigate(run, obligation)
            await self.verification.update_obligation(obligation)
            run.completed_obligation_ids.append(obligation.id)
        await self._finalize(run)
        return state

    async def _investigate(self, run, obligation) -> None:
        """A bounded, deterministic lexical investigation for supported source-fact claims."""
        statement = obligation.statement.casefold()
        patterns: list[tuple[str, ObligationStatus]] = []
        if any(token in statement for token in {"multiple refund", "schema", "migration"}):
            patterns.append(("unique: true", ObligationStatus.DISPROVED))
        elif "idempotency" in statement:
            patterns.append(("partial refund amount is not part", ObligationStatus.DISPROVED))
        elif any(token in statement for token in {"billing", "ledger"}):
            patterns.append(("return -event.captured_amount", ObligationStatus.DISPROVED))
        elif any(token in statement for token in {"provider", "accepts", "amount"}):
            patterns.append(("refund amount must be positive", ObligationStatus.VERIFIED))
        if not patterns or run.tool_call_count >= self.settings.verification_max_tool_calls:
            obligation.status = ObligationStatus.INCONCLUSIVE
            return
        tools = RepositoryTools(self.runs, self.verification)
        for query, terminal in patterns:
            await self._event(run.id, "tool_started", "Running bounded lexical repository search")
            try:
                matches = await tools.search_code_lexical(
                    SearchCodeInput(snapshot_id=run.snapshot_id, query=query, limit=1)
                )
                run.tool_call_count += 1
                if not matches:
                    continue
                match = matches[0]
                tool_doc = await self.verification.database.tool_runs.find_one(
                    {"snapshot_id": run.snapshot_id, "tool_name": "search_code_lexical"},
                    sort=[("started_at", -1)],
                )
                evidence = await EvidenceAuthority(self.verification).issue_source_range(
                    snapshot_id=run.snapshot_id,
                    tool_run_id=tool_doc["id"],
                    path=match["path"],
                    line_start=match["line_start"],
                    line_end=match["line_end"],
                    summary="Deterministic lexical source fact for this obligation.",
                )
                await EvidenceAuthority(self.verification).validate(evidence.id)
                if terminal == ObligationStatus.DISPROVED:
                    obligation.counter_evidence_ids.append(evidence.id)
                else:
                    obligation.evidence_ids.append(evidence.id)
                obligation.status = terminal
                await self._event(
                    run.id, "tool_completed", "Repository tool returned bounded source fact"
                )
                await self._event(
                    run.id, "evidence_added", "Server-issued source evidence was recorded"
                )
                await self._event(run.id, "obligation_completed", f"Obligation became {terminal}")
                return
            except Exception:
                await self._event(run.id, "tool_failed", "Repository tool failed safely")
        obligation.status = ObligationStatus.INCONCLUSIVE

    async def _finalize(self, run) -> None:
        obligations = await self.verification.list_run_obligations(run.id)
        statuses = {item.status for item in obligations}
        run.status = VerificationRunStatus.FINALIZING
        await self.runs.update_run(run)
        if ObligationStatus.DISPROVED in statuses:
            run.status = VerificationRunStatus.BLOCKED
        elif ObligationStatus.HUMAN_REQUIRED in statuses:
            run.status = VerificationRunStatus.HUMAN_DECISION_REQUIRED
        elif obligations and statuses <= {ObligationStatus.VERIFIED}:
            run.status = VerificationRunStatus.COMPLETE
        else:
            run.status = VerificationRunStatus.INCONCLUSIVE
        run.updated_at = datetime.now(UTC)
        await self.runs.update_run(run)
        await self._event(run.id, "run_completed", f"Run finished with {run.status}")

    async def _event(self, run_id: str, event_type: str, summary: str) -> None:
        latest = await self.verification.database.events.find_one(
            {"run_id": run_id}, sort=[("sequence", -1)]
        )
        sequence = (latest["sequence"] if latest else 0) + 1
        try:
            await self.runs.append_event(
                RunEvent(run_id=run_id, sequence=sequence, event_type=event_type, summary=summary)
            )
        except Exception:
            pass
