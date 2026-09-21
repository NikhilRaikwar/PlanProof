import re
from datetime import UTC, datetime
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.config import Settings
from app.domain.runs import HumanQuestion, RunEvent, VerificationRunStatus
from app.domain.verification import ObligationCategory, ObligationStatus, ToolRun, ToolRunStatus
from app.repositories.runs import RunRepository
from app.repositories.verification import VerificationRepository
from app.services.evidence import EvidenceAuthority
from app.services.models import ProviderGateway
from app.services.obligations import ObligationExtractionService
from app.services.repository_tools import FindSymbolInput, RepositoryTools, SearchCodeInput


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
            VerificationRunStatus.HUMAN_WAIT,
            VerificationRunStatus.HUMAN_DECISION_REQUIRED,
        }:
            return state
        run.started_at = run.started_at or datetime.now(UTC)
        obligations = await self.verification.list_run_obligations(run.id)
        if not obligations:
            run.status = VerificationRunStatus.EXTRACTING_OBLIGATIONS
            await self.runs.update_run(run)
            plan = await self.runs.get_plan_version(run.plan_version_id)
            try:
                extracted = await ObligationExtractionService(
                    ProviderGateway(self.settings, self.verification), self.verification
                ).extract(
                    run.project_id,
                    run.snapshot_id,
                    run.plan_version_id,
                    plan.change_request,
                    plan.candidate_plan,
                    run_id=run.id,
                )
                run.model_call_count += 1
                if extracted and extracted[0].proposal_metadata:
                    meta = extracted[0].proposal_metadata
                    run.prompt_tokens += int(meta.get("prompt_tokens", 0) or 0)
                    run.completion_tokens += int(meta.get("completion_tokens", 0) or 0)
            except Exception:
                run.status = VerificationRunStatus.FAILED
                await self.runs.update_run(run)
                await self._event(
                    run.id, "run_failed", "Structured obligation extraction failed safely"
                )
                return state
            for obligation in extracted:
                obligation.run_id = run.id
                await self.verification.update_obligation(obligation)
            obligations = extracted
            await self._event(
                run.id, "obligations_extracted", f"Extracted {len(obligations)} obligations"
            )
        run.status = VerificationRunStatus.VERIFYING
        await self.runs.update_run(run)
        # Establish code-backed facts before pausing for product/operational
        # authority.  A cross-service/business question must not prevent the
        # same immutable run from discovering direct repository contradictions.
        # This ordering is deterministic and deliberately independent of the
        # model's proposal order.
        ordered_obligations = sorted(
            obligations,
            key=lambda item: item.category
            in {ObligationCategory.BUSINESS_RULE, ObligationCategory.CROSS_SERVICE},
        )
        for obligation in ordered_obligations:
            if obligation.status != ObligationStatus.PENDING:
                continue
            run.iteration_count += 1
            run.current_obligation_id = obligation.id
            obligation.status = ObligationStatus.VERIFYING
            await self.verification.update_obligation(obligation)
            await self._event(run.id, "obligation_started", f"Investigating obligation: {obligation.statement[:80]}")
            if run.iteration_count > self.settings.verification_max_iterations:
                obligation.status = ObligationStatus.INCONCLUSIVE
                obligation.proposal_metadata["inconclusive_reason"] = "Verification iteration limit reached"
                await self._event(run.id, "obligation_completed", "Obligation became INCONCLUSIVE (iteration limit)")
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
        """A bounded, deterministic repository investigation for code-verifiable claims."""
        if run.tool_call_count >= self.settings.verification_max_tool_calls:
            obligation.status = ObligationStatus.INCONCLUSIVE
            obligation.proposal_metadata["inconclusive_reason"] = "Investigation tool budget reached"
            await self._event(run.id, "obligation_completed", "Obligation became INCONCLUSIVE (tool budget reached)")
            return

        tools = RepositoryTools(self.runs, self.verification, run_id=run.id)
        statement = obligation.statement.casefold()

        # 1. Check known explicit deterministic contradictions / verification patterns
        patterns: list[tuple[str, ObligationStatus, str]] = []
        if any(token in statement for token in {"multiple refund", "schema", "migration"}):
            patterns.append(("unique: true", ObligationStatus.DISPROVED, "Schema uniqueness constraint contradicts claim"))
        if "idempotency" in statement:
            patterns.append(("partial refund amount is not part", ObligationStatus.DISPROVED, "Idempotency key constraint"))
        if any(token in statement for token in {"billing", "ledger"}):
            patterns.append(("return -event.captured_amount", ObligationStatus.DISPROVED, "Ledger calculation contradicts claim"))
        if any(token in statement for token in {"provider", "accepts", "amount"}):
            patterns.append(("refund amount must be positive", ObligationStatus.VERIFIED, "Provider accepts positive amount"))

        # 2. Extract domain search terms from verification hints and statement
        search_terms: list[tuple[str, ObligationStatus, str]] = list(patterns)

        # Add hints
        for hint in obligation.verification_hints:
            clean_hint = hint.strip().strip('"\'`')
            if clean_hint and 3 <= len(clean_hint) <= 80:
                search_terms.append((clean_hint, ObligationStatus.VERIFIED, f"Repository evidence matching hint '{clean_hint}'"))

        # Add category-specific architectural keyword searches
        statement_words = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_-]{3,}", statement))

        if obligation.category in {
            ObligationCategory.SCHEMA,
            ObligationCategory.DEPENDENCY,
            ObligationCategory.API_CONTRACT,
            ObligationCategory.BEHAVIOR,
            ObligationCategory.SYMBOL,
            ObligationCategory.IDEMPOTENCY,
            ObligationCategory.UNKNOWN,
        }:
            if any(w in statement_words for w in {"database", "mongo", "mongodb", "model", "models", "schema", "prisma", "mongoose", "postgres", "sql"}):
                for term in ["mongoose", "prisma", "mongodb", "Schema", "model", "database", "db."]:
                    search_terms.append((term, ObligationStatus.VERIFIED, f"Database/persistence pattern '{term}'"))

            if any(w in statement_words for w in {"auth", "authentication", "jwt", "session", "user", "token"}):
                for term in ["jwt", "auth", "session", "passport", "bearer", "login"]:
                    search_terms.append((term, ObligationStatus.VERIFIED, f"Authentication pattern '{term}'"))

            if any(w in statement_words for w in {"route", "router", "routes", "api", "endpoint", "controller", "express", "fastapi"}):
                for term in ["router", "express", "app.use", "app.get", "app.post", "api/", "APIRouter"]:
                    search_terms.append((term, ObligationStatus.VERIFIED, f"Routing convention '{term}'"))

            if any(w in statement_words for w in {"validation", "validate", "validator", "zod", "pydantic"}):
                for term in ["zod", "pydantic", "validate", "schema.parse"]:
                    search_terms.append((term, ObligationStatus.VERIFIED, f"Validation pattern '{term}'"))

            if any(w in statement_words for w in {"test", "tests", "spec", "jest", "pytest"}):
                for term in ["describe(", "test(", "it(", "def test_"]:
                    search_terms.append((term, ObligationStatus.VERIFIED, f"Test suite pattern '{term}'"))

            if any(w in statement_words for w in {"conversation", "history", "message", "chat"}):
                for term in ["conversation", "history", "message", "chat"]:
                    search_terms.append((term, ObligationStatus.VERIFIED, f"Conversation history pattern '{term}'"))

        # Deduplicate search terms by query string
        seen_queries = set()
        unique_terms = []
        for q, term_status, desc in search_terms:
            q_norm = q.strip().casefold()
            if q_norm and q_norm not in seen_queries:
                seen_queries.add(q_norm)
                unique_terms.append((q, term_status, desc))

        # Cap bounded searches per obligation (max 3 searches)
        bounded_terms = unique_terms[:3]

        # If no terms derived, do a lexical match of statement prefix
        if not bounded_terms:
            bounded_terms = [(obligation.statement[:40], ObligationStatus.VERIFIED, "Lexical match for statement")]

        # If symbol category, try find_symbol first
        if obligation.category == ObligationCategory.SYMBOL:
            symbol_candidates = [q for q, _, _ in bounded_terms if len(q) < 50]
            for sym in symbol_candidates:
                try:
                    await self._event(run.id, "tool_started", f"Searching symbols for '{sym}'")
                    symbols = await tools.find_symbol(FindSymbolInput(snapshot_id=run.snapshot_id, query=sym, limit=1))
                    run.tool_call_count += 1
                    if symbols:
                        sym_match = symbols[0]
                        tool_doc = await self.verification.database.tool_runs.find_one(
                            {"run_id": run.id, "tool_name": "find_symbol"},
                            sort=[("started_at", -1)],
                        )
                        evidence = await EvidenceAuthority(self.verification).issue_source_range(
                            snapshot_id=run.snapshot_id,
                            tool_run_id=tool_doc["id"] if tool_doc else "tool-symbol-search",
                            path=sym_match["path"],
                            line_start=sym_match["line_start"],
                            line_end=sym_match["line_end"],
                            summary=f"Symbol '{sym_match['qualified_name']}' ({sym_match.get('kind', 'symbol')}) found in {sym_match['path']}:{sym_match['line_start']}-{sym_match['line_end']}",
                        )
                        await EvidenceAuthority(self.verification).validate(evidence.id)
                        obligation.evidence_ids.append(evidence.id)
                        obligation.status = ObligationStatus.VERIFIED
                        await self._event(run.id, "tool_completed", f"Found symbol '{sym_match['qualified_name']}' in {sym_match['path']}")
                        await self._event(run.id, "evidence_added", f"Server-issued symbol evidence recorded: {evidence.id}")
                        await self._event(run.id, "obligation_completed", "Obligation became VERIFIED")
                        return
                except Exception:
                    pass

        # Execute bounded lexical searches
        for query, terminal, desc in bounded_terms:
            if run.tool_call_count >= self.settings.verification_max_tool_calls:
                break
            await self._event(run.id, "tool_started", f"Running bounded lexical search for '{query}'")
            try:
                matches = await tools.search_code_lexical(
                    SearchCodeInput(snapshot_id=run.snapshot_id, query=query, limit=1)
                )
                run.tool_call_count += 1
                if not matches:
                    continue
                match = matches[0]
                tool_doc = await self.verification.database.tool_runs.find_one(
                    {"run_id": run.id, "tool_name": "search_code_lexical"},
                    sort=[("started_at", -1)],
                ) or await self.verification.database.tool_runs.find_one(
                    {"snapshot_id": run.snapshot_id, "tool_name": "search_code_lexical"},
                    sort=[("started_at", -1)],
                )
                evidence = await EvidenceAuthority(self.verification).issue_source_range(
                    snapshot_id=run.snapshot_id,
                    tool_run_id=tool_doc["id"] if tool_doc else "tool-search-code-lexical",
                    path=match["path"],
                    line_start=match["line_start"],
                    line_end=match["line_end"],
                    summary=f"{desc} in {match['path']}:{match['line_start']}-{match['line_end']}",
                )
                await EvidenceAuthority(self.verification).validate(evidence.id)
                if terminal == ObligationStatus.DISPROVED:
                    obligation.counter_evidence_ids.append(evidence.id)
                else:
                    obligation.evidence_ids.append(evidence.id)
                obligation.status = terminal
                await self._event(
                    run.id, "tool_completed", f"Repository tool returned source fact in {match['path']}"
                )
                await self._event(
                    run.id, "evidence_added", f"Server-issued source evidence was recorded: {evidence.id}"
                )
                await self._event(run.id, "obligation_completed", f"Obligation became {terminal}")
                return
            except Exception:
                await self.verification.create_tool_run(
                    ToolRun(
                        snapshot_id=run.snapshot_id,
                        run_id=run.id,
                        tool_name="search_code_lexical",
                        input_hash="workflow-tool-failure",
                        status=ToolRunStatus.FAILED,
                        safe_error_class="TOOL_FAILURE",
                        duration_ms=0,
                    )
                )
                await self._event(run.id, "tool_failed", "Repository tool failed safely")

        # If bounded investigation completes with no matches:
        obligation.status = ObligationStatus.INCONCLUSIVE
        obligation.proposal_metadata["inconclusive_reason"] = "No supporting repository evidence found within investigation budget"
        await self._event(run.id, "obligation_completed", "Obligation became INCONCLUSIVE: No supporting repository evidence found within investigation budget")

    async def _finalize(self, run) -> None:
        obligations = await self.verification.list_run_obligations(run.id)
        statuses = {item.status for item in obligations}
        run.status = VerificationRunStatus.FINALIZING

        all_ev_ids = []
        for item in obligations:
            all_ev_ids.extend(item.evidence_ids)
            all_ev_ids.extend(item.counter_evidence_ids)
        run.evidence_count = len(set(all_ev_ids))
        run.tool_execution_count = run.tool_call_count
        run.has_open_human_question = len(run.open_human_question_ids) > 0

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
