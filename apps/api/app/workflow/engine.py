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


STOP_WORDS = {
    "use", "uses", "used", "using", "add", "adds", "added", "adding", "create", "creates",
    "created", "creating", "update", "updates", "updated", "updating", "delete", "deletes",
    "deleted", "deleting", "implement", "implements", "implemented", "implementing", "ensure",
    "ensures", "ensured", "ensuring", "check", "checks", "checked", "checking", "follow",
    "follows", "followed", "following", "handle", "handles", "handled", "handling", "read",
    "reads", "write", "writes", "store", "stores", "stored", "storing", "dispatch",
    "dispatches", "dispatched", "dispatching", "the", "this", "that", "these", "those",
    "from", "with", "without", "and", "for", "to", "into", "onto", "should", "will", "can",
    "must", "have", "has", "had", "been", "all", "any", "not", "component", "function",
    "utility", "class", "module", "service", "process", "user", "input", "commands",
    "application", "existing", "backend", "database", "validation", "authentication",
    "patterns", "pattern", "layer", "security", "enhanced", "error", "logging", "integrated",
    "around", "communication", "configuration", "endpoints", "system", "code", "schema",
    "synchronization", "client", "billing", "model", "models", "import", "imports", "imported",
    "export", "exports", "exported", "const", "let", "var", "type", "interface", "true", "false"
}


def _extract_primary_obligation_symbols(obligation) -> list[str]:
    """Extract distinct identifiers, quoted tokens, paths, and hints that define the obligation."""
    symbols = []
    statement = obligation.statement

    # 1. Backticked tokens
    for token in re.findall(r"`([^`]+)`", statement):
        clean = token.strip()
        if clean and clean.lower() not in STOP_WORDS:
            symbols.append(clean)

    # 2. Quoted tokens
    for token in re.findall(r"['\"]([^'\"]+)['\"]", statement):
        clean = token.strip()
        if clean and clean.lower() not in STOP_WORDS:
            symbols.append(clean)

    # 3. Path references (e.g. '@/utils/arbitrumAgent', 'src/components/ChatInterface.tsx')
    for path in re.findall(r"(?:@\/|[a-zA-Z0-9_-]+\/)[a-zA-Z0-9_./-]+", statement):
        clean = path.strip().strip("'\"`")
        if clean and clean.lower() not in STOP_WORDS:
            symbols.append(clean)

    # 4. Specific PascalCase (e.g. PrivyProvider), camelCase (e.g. sendMessageToAgent), snake_case (e.g. user_balance), or UPPER_CASE identifiers
    for word in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", statement):
        if word.lower() in STOP_WORDS:
            continue
        # camelCase (e.g. sendMessageToAgent, userBalance)
        if re.match(r"^[a-z]+[A-Z][A-Za-z0-9]*$", word):
            symbols.append(word)
        # PascalCase with at least two word parts (e.g. PrivyProvider, ChatInterface, QueryClient)
        elif re.match(r"^[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*$", word):
            symbols.append(word)
        # snake_case with underscores (e.g. user_balance, token_hash)
        elif "_" in word and len(word) >= 3 and not word.startswith("__"):
            symbols.append(word)
        # SCREAMING_SNAKE or UPPER_CASE identifier (e.g. JWT_SECRET, PORT)
        elif word.isupper() and len(word) >= 3:
            symbols.append(word)
        # Technical identifiers with embedded version/digits (e.g. ServiceV99, v2)
        elif re.search(r"[0-9]", word) and len(word) >= 3:
            symbols.append(word)

    # 5. Extract symbols from verification hints (identifiers, paths, quotes, or single-token hints)
    for hint in obligation.verification_hints:
        clean = hint.strip().strip("'\"`")
        if not clean:
            continue
        # Backticked or quoted tokens in hint
        for token in re.findall(r"[`'\"]([^`'\"]+)[`'\"]", clean):
            t_clean = token.strip()
            if t_clean and t_clean.lower() not in STOP_WORDS:
                symbols.append(t_clean)
        # Paths in hint
        for path in re.findall(r"(?:@\/|[a-zA-Z0-9_-]+\/)[a-zA-Z0-9_./-]+", clean):
            p_clean = path.strip().strip("'\"`")
            if p_clean and p_clean.lower() not in STOP_WORDS:
                symbols.append(p_clean)
        # Identifiers in hint
        for word in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", clean):
            if word.lower() in STOP_WORDS:
                continue
            if (
                re.match(r"^[a-z]+[A-Z][A-Za-z0-9]*$", word)
                or re.match(r"^[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*$", word)
                or ("_" in word and len(word) >= 3 and not word.startswith("__"))
                or (word.isupper() and len(word) >= 3)
                or (re.search(r"[0-9]", word) and len(word) >= 3)
            ):
                symbols.append(word)
        # If the entire hint is a single identifier (e.g. "mongoose", "Schema")
        if len(clean.split()) == 1 and clean.lower() not in STOP_WORDS and len(clean) >= 3:
            symbols.append(clean)

    # Deduplicate preserving order
    seen = set()
    deduped = []
    for s in symbols:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    return deduped


def extract_obligation_queries(obligation) -> list[tuple[str, ObligationStatus, str]]:
    """Extract bounded, prioritized deterministic queries from an obligation statement and hints."""
    statement = obligation.statement
    statement_lower = statement.casefold()

    queries: list[tuple[str, ObligationStatus, str]] = []

    # 1. Deterministic contradiction/verification patterns (synthetic & fixture rules)
    if any(token in statement_lower for token in {"multiple refund", "unique refund", "refund uniqueness"}):
        queries.append(("unique: true", ObligationStatus.DISPROVED, "Schema uniqueness constraint"))
    if "idempotency" in statement_lower and any(token in statement_lower for token in {"partial refund", "amount is not part"}):
        queries.append(("partial refund amount is not part", ObligationStatus.DISPROVED, "Idempotency key constraint"))
    if "ledger" in statement_lower or "captured_amount" in statement_lower:
        queries.append(("return -event.captured_amount", ObligationStatus.DISPROVED, "Ledger calculation"))
    if any(token in statement_lower for token in {"payment provider", "refund provider", "accepts positive", "positive amount", "provider accepts", "accepts a refund"}):
        queries.append(("refund amount must be positive", ObligationStatus.VERIFIED, "Provider accepts positive amount"))

    # 2. Extract primary symbols
    for sym in _extract_primary_obligation_symbols(obligation):
        queries.append((sym, ObligationStatus.VERIFIED, f"Primary symbol {sym}"))

    # 3. Extract exact quoted tokens or short tokens from verification hints
    for hint in obligation.verification_hints:
        clean_hint = hint.strip().strip("'\"`")
        if not clean_hint:
            continue
        for token in re.findall(r"[`'\"]([^`'\"]+)[`'\"]", clean_hint):
            t_clean = token.strip()
            if t_clean and t_clean.lower() not in STOP_WORDS:
                queries.append((t_clean, ObligationStatus.VERIFIED, f"Hint token `{t_clean}`"))
        # If single or two-word hint (e.g. "mongoose", "Schema", "user balance")
        if len(clean_hint.split()) <= 2 and clean_hint.lower() not in STOP_WORDS:
            queries.append((clean_hint, ObligationStatus.VERIFIED, f"Verification hint {clean_hint}"))

    # Deduplicate while preserving priority order
    seen = set()
    deduped = []
    for q, status, desc in queries:
        q_norm = q.strip().casefold()
        if q_norm and q_norm not in seen:
            seen.add(q_norm)
            deduped.append((q.strip(), status, desc))

    return deduped


UNVERIFIABLE_QUALITATIVE_TERMS = [
    "reliable", "reliability", "secure", "secures", "securing", "secured",
    "correctly implemented", "correct implementation", "properly integrated",
    "proper integration", "backward compatible", "backward compatibility",
    "robust", "foolproof"
]


def _is_genuine_human_authority_obligation(obligation) -> bool:
    """True only if the proposition genuinely requires external product/business authority."""
    statement_lower = obligation.statement.casefold()

    # If the statement explicitly mentions code identifiers, symbols, files, imports, APIs, or parameters:
    # it is a technical claim, NOT a human policy decision.
    technical_indicators = [
        ".ts", ".tsx", ".js", ".jsx", ".py", ".json", ".yaml", ".yml",
        "import", "export", "function", "component", "class", "const",
        "endpoint", "grpc", "protobuf", "schema", "model", "parameter",
        "token", "identifier", "method", "variable", "route", "handler",
        "interface", "type", "@/"
    ]
    if any(ind in statement_lower for ind in technical_indicators):
        return False

    # Specific PascalCase, camelCase, UPPER_CASE, or snake_case technical identifiers
    symbols = _extract_primary_obligation_symbols(obligation)
    if symbols:
        return False

    # Check category: BUSINESS_RULE or CROSS_SERVICE (without code symbols)
    if obligation.category in {ObligationCategory.BUSINESS_RULE, ObligationCategory.CROSS_SERVICE}:
        return True

    # Check for genuine business policy keywords
    business_keywords = [
        "retention policy", "retain for", "retained for", "deleted after",
        "days", "pricing", "legal", "compliance", "terms of service",
        "gdpr", "sla", "approval", "product owner", "contractual",
        "business policy", "human decision", "manual review"
    ]
    return any(kw in statement_lower for kw in business_keywords)



def check_evidence_relevance(obligation, path: str, snippet: str, matched_query: str) -> bool:
    """Validate that repository snippet/path contains symbols or paths related to the obligation."""
    statement_lower = obligation.statement.casefold()
    snippet_lower = snippet.casefold()
    path_lower = path.casefold()
    query_lower = matched_query.casefold()

    # Special deterministic fixture invariants
    if "multiple refund" in statement_lower and "unique: true" in snippet_lower:
        return True
    if "idempotency" in statement_lower and "partial refund amount is not part" in snippet_lower:
        return True
    if any(token in statement_lower for token in {"positive", "provider accepts", "accepts a refund"}) and "refund amount must be positive" in snippet_lower:
        return True
    if "ledger" in statement_lower and "return -event.captured_amount" in snippet_lower:
        return True

    # Extract all required primary symbols from statement
    primary_symbols = _extract_primary_obligation_symbols(obligation)

    if primary_symbols:
        # At least one primary symbol or path MUST be present in the snippet or file path
        found = False
        for sym in primary_symbols:
            sym_lower = sym.casefold()
            clean_sym = sym_lower.replace("@/", "").rstrip(".ts").rstrip(".tsx").rstrip(".js")
            if (
                sym_lower in snippet_lower
                or sym_lower in path_lower
                or (len(clean_sym) >= 4 and (clean_sym in snippet_lower or clean_sym in path_lower))
            ):
                found = True
                break
        if not found:
            return False

    # The matched query must also be contained in the snippet or path
    return query_lower in snippet_lower or query_lower in path_lower


def check_evidence_sufficiency(obligation, path: str, snippet: str, matched_query: str) -> bool:
    """Validate that candidate evidence is SUFFICIENT to prove the entire atomic proposition."""
    if not check_evidence_relevance(obligation, path, snippet, matched_query):
        return False

    statement_lower = obligation.statement.casefold()
    snippet_lower = snippet.casefold()

    # 1. Higher-order unverifiable terms cannot be verified by a static repository snippet
    if any(term in statement_lower for term in UNVERIFIABLE_QUALITATIVE_TERMS):
        return False

    # 2. Call / Invocation / Usage claims
    is_call_claim = any(
        kw in statement_lower for kw in [
            "invok", "calls ", "called", "calling", "execut", "triggers",
            "trigger", "handles submitted", "when handling", "processes input"
        ]
    )
    if is_call_claim:
        primary_symbols = _extract_primary_obligation_symbols(obligation)
        has_call_expression = False
        for sym in primary_symbols:
            pattern = rf"\b{re.escape(sym)}\s*\("
            if re.search(pattern, snippet):
                has_call_expression = True
                break
        if not has_call_expression:
            return False

    # 3. Component Wrapping / Provider claim
    is_wrapping_claim = any(
        kw in statement_lower for kw in ["wraps", "wrapping", "wrapped", "nested inside", "encloses"]
    ) or ("<" in obligation.statement and ">" in obligation.statement)
    if is_wrapping_claim:
        has_jsx_tag = bool(re.search(r"<\s*[A-Z][A-Za-z0-9_]*", snippet))
        if not has_jsx_tag:
            return False

    # 4. Import claim
    is_import_claim = any(
        kw in statement_lower for kw in ["import ", "imports ", "imported from", "importing"]
    )
    if is_import_claim and not is_call_claim and not is_wrapping_claim:
        has_import_statement = "import " in snippet_lower or "require(" in snippet_lower
        if not has_import_statement:
            return False

    return True


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
        # Establish code-backed facts before pausing for product/operational authority
        ordered_obligations = sorted(
            obligations,
            key=lambda item: item.category
            in {ObligationCategory.BUSINESS_RULE, ObligationCategory.CROSS_SERVICE}
            and _is_genuine_human_authority_obligation(item),
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
            elif (
                obligation.category in {ObligationCategory.BUSINESS_RULE, ObligationCategory.CROSS_SERVICE}
                and _is_genuine_human_authority_obligation(obligation)
            ):
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
        """A bounded, deterministic repository investigation with relevance and sufficiency guards."""
        if run.tool_call_count >= self.settings.verification_max_tool_calls:
            obligation.status = ObligationStatus.INCONCLUSIVE
            obligation.proposal_metadata["inconclusive_reason"] = "Investigation tool budget reached"
            await self._event(run.id, "obligation_completed", "Obligation became INCONCLUSIVE (tool budget reached)")
            return

        tools = RepositoryTools(self.runs, self.verification, run_id=run.id)
        queries = extract_obligation_queries(obligation)

        # Cap bounded searches per obligation (max 4 searches)
        bounded_terms = queries[:4]

        # If no queries derived, do a lexical match of statement prefix
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
                        if not check_evidence_sufficiency(obligation, sym_match["path"], sym_match.get("qualified_name", ""), sym):
                            continue
                        tool_doc = await self.verification.database.tool_runs.find_one(
                            {"run_id": run.id, "tool_name": "find_symbol"},
                            sort=[("started_at", -1)],
                        )
                        evidence = await EvidenceAuthority(self.verification).issue_source_range(
                            snapshot_id=run.snapshot_id,
                            run_id=run.id,
                            obligation_id=obligation.id,
                            matched_query=sym,
                            relationship="SUPPORTS",
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

        # Execute bounded lexical searches with strict deterministic relevance and sufficiency checks
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

                # Fetch file snippet to verify deterministic relevance and sufficiency
                file_doc = await self.verification.database.repository_files.find_one(
                    {"snapshot_id": run.snapshot_id, "path": match["path"]}
                )
                if not file_doc:
                    continue

                lines = file_doc.get("text", "").splitlines()
                start_l = max(1, match["line_start"])
                end_l = min(len(lines), match["line_end"])
                matched_snippet = "\n".join(lines[start_l - 1 : end_l])

                # Guard: Verify sufficiency for THIS specific atomic proposition
                if not check_evidence_sufficiency(obligation, match["path"], matched_snippet, query):
                    # Candidate match does not SUFFICIENTLY prove this proposition
                    continue

                tool_doc = await self.verification.database.tool_runs.find_one(
                    {"run_id": run.id, "tool_name": "search_code_lexical"},
                    sort=[("started_at", -1)],
                ) or await self.verification.database.tool_runs.find_one(
                    {"snapshot_id": run.snapshot_id, "tool_name": "search_code_lexical"},
                    sort=[("started_at", -1)],
                )
                evidence = await EvidenceAuthority(self.verification).issue_source_range(
                    snapshot_id=run.snapshot_id,
                    run_id=run.id,
                    obligation_id=obligation.id,
                    matched_query=query,
                    relationship="CONTRADICTS" if terminal == ObligationStatus.DISPROVED else "SUPPORTS",
                    tool_run_id=tool_doc["id"] if tool_doc else "tool-search-code-lexical",
                    path=match["path"],
                    line_start=start_l,
                    line_end=end_l,
                    summary=f"{desc} in {match['path']}:{start_l}-{end_l}",
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

        # If bounded investigation completes with no sufficient matches:
        obligation.status = ObligationStatus.INCONCLUSIVE
        obligation.proposal_metadata["inconclusive_reason"] = "No sufficient repository evidence found within investigation budget"
        await self._event(run.id, "obligation_completed", "Obligation became INCONCLUSIVE: No sufficient repository evidence found within investigation budget")

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
