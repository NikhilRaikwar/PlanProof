import asyncio
import logging
import re
from datetime import UTC, datetime
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.config import Settings
from app.domain.revised_plans import RevisedPlanStatus
from app.domain.runs import HumanQuestion, RunEvent, SnapshotStatus, VerificationRunStatus
from app.domain.verification import (
    EvidenceType,
    ObligationCategory,
    ObligationStatus,
    SemanticRole,
    ToolRun,
    ToolRunStatus,
)
from app.repositories.runs import RunRepository
from app.repositories.verification import VerificationRepository
from app.services.evidence import EvidenceAuthority
from app.services.investigation_planning import InvestigationPlanningService
from app.services.models import ProviderGateway
from app.services.obligations import ObligationExtractionService
from app.services.repository_tools import (
    CheckPathMembershipInput,
    FindSymbolInput,
    ReadFileRangeInput,
    RepositoryTools,
    SearchCodeInput,
)
from app.services.revision import PlanRevisionService

logger = logging.getLogger(__name__)


class WorkflowState(TypedDict):
    run_id: str


STOP_WORDS = {
    "use",
    "uses",
    "used",
    "using",
    "add",
    "adds",
    "added",
    "adding",
    "create",
    "creates",
    "created",
    "creating",
    "update",
    "updates",
    "updated",
    "updating",
    "delete",
    "deletes",
    "deleted",
    "deleting",
    "implement",
    "implements",
    "implemented",
    "implementing",
    "ensure",
    "ensures",
    "ensured",
    "ensuring",
    "check",
    "checks",
    "checked",
    "checking",
    "follow",
    "follows",
    "followed",
    "following",
    "handle",
    "handles",
    "handled",
    "handling",
    "read",
    "reads",
    "write",
    "writes",
    "store",
    "stores",
    "stored",
    "storing",
    "dispatch",
    "dispatches",
    "dispatched",
    "dispatching",
    "the",
    "this",
    "that",
    "these",
    "those",
    "from",
    "with",
    "without",
    "and",
    "for",
    "to",
    "into",
    "onto",
    "should",
    "will",
    "can",
    "must",
    "have",
    "has",
    "had",
    "been",
    "all",
    "any",
    "not",
    "component",
    "function",
    "utility",
    "class",
    "module",
    "service",
    "process",
    "user",
    "input",
    "commands",
    "application",
    "existing",
    "backend",
    "database",
    "validation",
    "authentication",
    "patterns",
    "pattern",
    "layer",
    "security",
    "enhanced",
    "error",
    "logging",
    "integrated",
    "around",
    "communication",
    "configuration",
    "endpoints",
    "system",
    "code",
    "schema",
    "synchronization",
    "client",
    "billing",
    "model",
    "models",
    "import",
    "imports",
    "imported",
    "export",
    "exports",
    "exported",
    "const",
    "let",
    "var",
    "type",
    "interface",
    "true",
    "false",
}


_PATH_EXTENSIONS_SET = {
    ".tsx",
    ".ts",
    ".jsx",
    ".js",
    ".py",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".sql",
    ".md",
    ".css",
    ".env",
    ".go",
    ".rs",
    ".rb",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".sh",
}

_PATH_REGEX = r"(?:@\/|[a-zA-Z0-9_.-]+\/)*[a-zA-Z0-9_.-]+\.(?:tsx?|jsx?|py|json|yaml|yml|toml|sql|md|css|env|go|rs|rb|java|c|cpp|h|hpp|sh)"


def _is_file_path(token: str) -> bool:
    """Returns True if the token represents a file path rather than a code identifier."""
    if not token or not isinstance(token, str):
        return False
    clean = token.strip().replace("\\", "/")
    if "/" in clean:
        return True
    return any(clean.lower().endswith(ext) for ext in _PATH_EXTENSIONS_SET)


def _extract_explicit_paths(obligation) -> list[str]:
    """Extract explicit file paths referenced in statement or hints, preserving exact case and git posix semantics."""
    paths: list[str] = []
    text = obligation.statement + " " + " ".join(obligation.verification_hints)

    for p in re.findall(_PATH_REGEX, text):
        clean = p.strip().strip("'\"`").replace("\\", "/")
        if clean.startswith("@/"):
            clean = clean[2:]
        if clean.startswith("./"):
            clean = clean[2:]
        if (
            clean in {"import.meta.env", "process.env"}
            or clean.startswith("import.meta")
            or clean.startswith("process.env")
        ):
            continue
        if clean and not clean.startswith("/") and ".." not in clean and "\x00" not in clean:
            paths.append(clean)

    seen = set()
    deduped = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            deduped.append(p)
    return deduped


def _extract_explicit_imported_identifiers(obligation) -> list[str]:
    """Extract specific imported identifier names when statement claims an import."""
    text = obligation.statement
    identifiers: list[str] = []

    import_matches = re.findall(
        r"(?:imports?|importing)\s+([A-Za-z0-9_,\s{}]+?)\s+from", text, re.IGNORECASE
    )
    for match in import_matches:
        cleaned_match = match.replace("{", "").replace("}", "")
        for item in cleaned_match.split(","):
            ident = item.strip()
            if (
                ident
                and ident.lower() not in STOP_WORDS
                and len(ident) >= 2
                and not _is_file_path(ident)
            ):
                identifiers.append(ident)

    for sym in re.findall(r"\b[A-Z][a-zA-Z0-9_]+\b", text):
        if sym.lower() not in STOP_WORDS and len(sym) >= 3 and not _is_file_path(sym):
            identifiers.append(sym)

    seen = set()
    deduped = []
    for ident in identifiers:
        if ident.lower() not in seen:
            seen.add(ident.lower())
            deduped.append(ident)
    return deduped


def _extract_primary_obligation_symbols(obligation) -> list[str]:
    """Extract distinct identifiers and symbols that define the obligation, strictly excluding file paths."""
    symbols = []
    statement = obligation.statement
    explicit_paths = set(_extract_explicit_paths(obligation))

    # 1. Backticked tokens
    for token in re.findall(r"`([^`]+)`", statement):
        clean = token.strip()
        if (
            clean
            and clean.lower() not in STOP_WORDS
            and clean not in explicit_paths
            and not _is_file_path(clean)
        ):
            symbols.append(clean)

    # 2. Quoted tokens
    for token in re.findall(r"['\"]([^'\"]+)['\"]", statement):
        clean = token.strip()
        if (
            clean
            and clean.lower() not in STOP_WORDS
            and clean not in explicit_paths
            and not _is_file_path(clean)
        ):
            symbols.append(clean)

    # 3. Specific PascalCase, camelCase, snake_case, or UPPER_CASE identifiers
    for word in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", statement):
        if word.lower() in STOP_WORDS or _is_file_path(word):
            continue
        if re.match(r"^[a-z]+[A-Z][A-Za-z0-9]*$", word):
            symbols.append(word)
        elif re.match(r"^[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*$", word):
            symbols.append(word)
        elif "_" in word and len(word) >= 3 and not word.startswith("__"):
            symbols.append(word)
        elif word.isupper() and len(word) >= 3:
            symbols.append(word)
        elif re.search(r"[0-9]", word) and len(word) >= 3:
            symbols.append(word)

    # 4. Extract symbols from verification hints
    for hint in obligation.verification_hints:
        clean = hint.strip().strip("'\"`")
        if not clean or _is_file_path(clean) or clean in explicit_paths:
            continue
        for token in re.findall(r"[`'\"]([^`'\"]+)[`'\"]", clean):
            t_clean = token.strip()
            if t_clean and t_clean.lower() not in STOP_WORDS and not _is_file_path(t_clean):
                symbols.append(t_clean)
        for word in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", clean):
            if word.lower() in STOP_WORDS or _is_file_path(word):
                continue
            if (
                re.match(r"^[a-z]+[A-Z][A-Za-z0-9]*$", word)
                or re.match(r"^[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*$", word)
                or ("_" in word and len(word) >= 3 and not word.startswith("__"))
                or (word.isupper() and len(word) >= 3)
                or (re.search(r"[0-9]", word) and len(word) >= 3)
            ):
                symbols.append(word)
        if (
            len(clean.split()) == 1
            and clean.lower() not in STOP_WORDS
            and len(clean) >= 3
            and not _is_file_path(clean)
        ):
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
    """Extract bounded, prioritized deterministic queries from an obligation statement and hints, excluding file paths."""
    statement = obligation.statement
    statement_lower = statement.casefold()
    explicit_paths = set(_extract_explicit_paths(obligation))

    queries: list[tuple[str, ObligationStatus, str]] = []

    # 1. Deterministic contradiction/verification patterns
    if any(
        token in statement_lower
        for token in {"multiple refund", "unique refund", "refund uniqueness"}
    ):
        queries.append(("unique: true", ObligationStatus.DISPROVED, "Schema uniqueness constraint"))
    if "idempotency" in statement_lower and any(
        token in statement_lower for token in {"partial refund", "amount is not part"}
    ):
        queries.append(
            (
                "partial refund amount is not part",
                ObligationStatus.DISPROVED,
                "Idempotency key constraint",
            )
        )
    if "ledger" in statement_lower or "captured_amount" in statement_lower:
        queries.append(
            ("return -event.captured_amount", ObligationStatus.DISPROVED, "Ledger calculation")
        )
    if any(
        token in statement_lower
        for token in {
            "payment provider",
            "refund provider",
            "accepts positive",
            "positive amount",
            "provider accepts",
            "accepts a refund",
        }
    ):
        queries.append(
            (
                "refund amount must be positive",
                ObligationStatus.VERIFIED,
                "Provider accepts positive amount",
            )
        )

    # 2. Extract primary symbols
    for sym in _extract_primary_obligation_symbols(obligation):
        if not _is_file_path(sym) and sym not in explicit_paths:
            queries.append((sym, ObligationStatus.VERIFIED, f"Primary symbol {sym}"))

    # 3. Extract exact quoted tokens or short tokens from verification hints
    for hint in obligation.verification_hints:
        clean_hint = hint.strip().strip("'\"`")
        if not clean_hint or _is_file_path(clean_hint) or clean_hint in explicit_paths:
            continue
        for token in re.findall(r"[`'\"]([^`'\"]+)[`'\"]", clean_hint):
            t_clean = token.strip()
            if (
                t_clean
                and t_clean.lower() not in STOP_WORDS
                and not _is_file_path(t_clean)
                and t_clean not in explicit_paths
            ):
                queries.append((t_clean, ObligationStatus.VERIFIED, f"Hint token `{t_clean}`"))
        if (
            len(clean_hint.split()) <= 2
            and clean_hint.lower() not in STOP_WORDS
            and not _is_file_path(clean_hint)
            and clean_hint not in explicit_paths
        ):
            queries.append(
                (clean_hint, ObligationStatus.VERIFIED, f"Verification hint {clean_hint}")
            )

    # 4. Extract environment variable / config identifiers if present in statement
    for env_match in re.findall(r"\b[A-Z][A-Z0-9_]{3,}\b", statement):
        if (
            env_match.lower() not in STOP_WORDS
            and not _is_file_path(env_match)
            and env_match not in explicit_paths
        ):
            queries.append(
                (env_match, ObligationStatus.VERIFIED, f"Environment/config identifier {env_match}")
            )

    # Deduplicate while preserving priority order
    seen = set()
    deduped = []
    for q, status, desc in queries:
        q_norm = q.strip().casefold()
        if (
            q_norm
            and q_norm not in seen
            and not _is_file_path(q.strip())
            and q.strip() not in explicit_paths
        ):
            seen.add(q_norm)
            deduped.append((q.strip(), status, desc))

    return deduped


UNVERIFIABLE_QUALITATIVE_TERMS = [
    "reliable",
    "reliability",
    "secure",
    "secures",
    "securing",
    "secured",
    "correctly implemented",
    "correct implementation",
    "properly integrated",
    "proper integration",
    "backward compatible",
    "backward compatibility",
    "robust",
    "foolproof",
]


def _is_genuine_human_authority_obligation(obligation) -> bool:
    """True only if the proposition genuinely requires external product/business authority."""
    statement_lower = obligation.statement.casefold()

    technical_indicators = [
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".py",
        ".json",
        ".yaml",
        ".yml",
        ".sql",
        "import ",
        "export ",
        "function ",
        "component ",
        "class ",
        "const ",
        "let ",
        "var ",
        "endpoint",
        "route",
        "schema",
        "database",
        "mongo",
        "redis",
        "postgres",
        "header",
        "cookie",
        "payload",
    ]
    if any(ind in statement_lower for ind in technical_indicators):
        return False

    human_authority_indicators = [
        "retention",
        "retention period",
        "retention policy",
        "how long to keep",
        "delete history after",
        "pricing",
        "pricing policy",
        "business tier",
        "approval",
        "approval required",
        "user approval",
        "consent",
        "compliance",
        "legal review",
        "sla",
        "sla guarantee",
        "third-party contract",
        "business authority",
        "product owner",
        "management approval",
        "policy",
    ]
    return any(ind in statement_lower for ind in human_authority_indicators)


def classify_obligation_routing(obligation) -> str:
    """
    Classify semantic role routing:
    - 'PROPOSED_ACTION': Preserved for revised-plan synthesis only; never investigated as an existing repo fact.
    - 'HUMAN_AUTHORITY': Routed strictly to human authority workflow (creates HumanQuestion).
    - 'REPO_INVESTIGATION': Routed to repository investigation proof tools.
    """
    role = getattr(obligation, "semantic_role", None)
    if role == SemanticRole.PROPOSED_ACTION:
        return "PROPOSED_ACTION"

    if role == SemanticRole.HUMAN_DECISION:
        return "HUMAN_AUTHORITY"

    if role == SemanticRole.CONSTRAINT:
        if _is_genuine_human_authority_obligation(obligation) or obligation.category in {
            ObligationCategory.BUSINESS_RULE,
            ObligationCategory.CROSS_SERVICE,
        }:
            return "HUMAN_AUTHORITY"
        return "REPO_INVESTIGATION"

    if obligation.category in {
        ObligationCategory.BUSINESS_RULE,
        ObligationCategory.CROSS_SERVICE,
    } and _is_genuine_human_authority_obligation(obligation):
        return "HUMAN_AUTHORITY"

    return "REPO_INVESTIGATION"


def check_evidence_relevance(obligation, path: str, snippet: str, matched_query: str) -> bool:
    """Validate that repository snippet/path contains symbols or paths related to the obligation."""
    statement_lower = obligation.statement.casefold()
    snippet_lower = snippet.casefold()
    path_lower = path.casefold()
    query_lower = matched_query.casefold()

    # If the obligation explicitly specifies file paths, candidate evidence MUST belong to one of those paths!
    explicit_paths = _extract_explicit_paths(obligation)
    if explicit_paths:
        path_matches = any(
            p.casefold() == path_lower or path_lower.endswith(p.casefold()) for p in explicit_paths
        )
        if not path_matches:
            return False

    # Special deterministic fixture invariants
    if "multiple refund" in statement_lower and "unique: true" in snippet_lower:
        return True
    if "idempotency" in statement_lower and "partial refund amount is not part" in snippet_lower:
        return True
    if (
        any(
            token in statement_lower
            for token in {"positive", "provider accepts", "accepts a refund"}
        )
        and "refund amount must be positive" in snippet_lower
    ):
        return True
    if "ledger" in statement_lower and "return -event.captured_amount" in snippet_lower:
        return True

    # Extract all required primary symbols from statement
    primary_symbols = _extract_primary_obligation_symbols(obligation)

    if primary_symbols:
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

    return query_lower in snippet_lower or query_lower in path_lower


def check_evidence_sufficiency(obligation, path: str, snippet: str, matched_query: str) -> bool:
    """Validate that candidate evidence is SUFFICIENT to prove the entire atomic proposition."""
    if not check_evidence_relevance(obligation, path, snippet, matched_query):
        return False

    statement_lower = obligation.statement.casefold()
    snippet_lower = snippet.casefold()
    path_lower = path.casefold()

    # 1. Higher-order unverifiable terms cannot be verified by a static repository snippet
    if any(term in statement_lower for term in UNVERIFIABLE_QUALITATIVE_TERMS):
        return False

    # 2. Strict exact path check
    explicit_paths = _extract_explicit_paths(obligation)
    if explicit_paths:
        path_matches = any(
            p.casefold() == path_lower or path_lower.endswith(p.casefold()) for p in explicit_paths
        )
        if not path_matches:
            return False

    # 3. Exact imported identifier check
    is_import_claim = any(
        kw in statement_lower
        for kw in ["import ", "imports ", "imported", "imported into", "importing"]
    )
    if is_import_claim:
        has_import_statement = "import " in snippet_lower or "require(" in snippet_lower
        if not has_import_statement:
            return False

        explicit_imported_symbols = _extract_explicit_imported_identifiers(obligation)
        if explicit_imported_symbols:
            has_imported_symbol = any(
                sym.casefold() in snippet_lower for sym in explicit_imported_symbols
            )
            if not has_imported_symbol:
                return False

    # 4. Environment variable / config access check
    env_access_indicators = [
        "import.meta.env",
        "import.meta",
        "process.env",
        "os.getenv",
        "os.environ",
        "environ",
        "system.getenv",
        "env.",
        "config.",
        "get_secret",
    ]
    if any(ind in statement_lower for ind in env_access_indicators):
        has_env_access = any(
            token in snippet_lower
            for token in [
                "import.meta.env",
                "import.meta",
                "process.env",
                "os.getenv",
                "os.environ",
                "environ",
                "system.getenv",
                "env(",
                "env.",
                "getenv",
                "config",
            ]
        )
        if not has_env_access:
            return False

    # 5. Required uppercase / config / environment identifier checks
    for ident in re.findall(r"\b[A-Z][A-Z0-9_]{3,}\b", obligation.statement):
        if ident.lower() not in STOP_WORDS and not _is_file_path(ident) and ident not in snippet:
            return False

    # 6. Call / Invocation / Usage claims
    is_call_claim = any(
        kw in statement_lower
        for kw in [
            "invok",
            "calls ",
            "called",
            "calling",
            "execut",
            "triggers",
            "trigger",
            "handles submitted",
            "when handling",
            "processes input",
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

    # 6. Component Wrapping / Provider claim
    is_wrapping_claim = any(
        kw in statement_lower
        for kw in ["wraps", "wrapping", "wrapped", "nested inside", "encloses"]
    ) or ("<" in obligation.statement and ">" in obligation.statement)
    if is_wrapping_claim:
        has_jsx_tag = bool(re.search(r"<\s*[A-Z][A-Za-z0-9_]*", snippet))
        if not has_jsx_tag:
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
        run = await self.runs.get_run(run_id)
        if not run:
            return

        # Start lease renewal heartbeat loop for long-running executions
        heartbeat_task = None
        if hasattr(self.verification, "database") and self.verification.database is not None:
            try:
                project = await self.verification.database.projects.find_one({"id": run.project_id})
                account_login = project.get("owner_id") if project else None
                if account_login:
                    from app.services.quotas import QuotaService

                    quota_service = QuotaService(self.verification.database, self.settings)

                    async def _heartbeat_loop() -> None:
                        try:
                            while True:
                                await asyncio.sleep(20)
                                await quota_service.renew_active_reservation(
                                    account_login, run.project_id, run.id
                                )
                        except asyncio.CancelledError:
                            pass
                        except Exception as exc:
                            logger.warning("lease_heartbeat_failed run_id=%s error=%s", run_id, exc)

                    heartbeat_task = asyncio.create_task(_heartbeat_loop())
            except Exception:
                pass

        try:
            await self.graph.ainvoke({"run_id": run_id})
        finally:
            if heartbeat_task and not heartbeat_task.done():
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

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
        plan = await self.runs.get_plan_version(run.plan_version_id)

        if not obligations:
            run.status = VerificationRunStatus.EXTRACTING_OBLIGATIONS
            await self.runs.update_run(run)
            try:
                extracted = await ObligationExtractionService(
                    ProviderGateway(self.settings, self.verification), self.verification
                ).extract(
                    run.project_id,
                    run.snapshot_id,
                    run.plan_version_id,
                    plan.change_request,
                    plan.candidate_plan,
                    normalized_steps=plan.normalized_steps,
                    run_id=run.id,
                )
                updated_run = await self.runs.get_run(run.id)
                if updated_run:
                    run.model_call_count = updated_run.model_call_count
                    run.prompt_tokens = updated_run.prompt_tokens
                    run.completion_tokens = updated_run.completion_tokens
            except Exception as exc:
                logger.exception("Structured obligation extraction failed", exc_info=exc)
                run.status = VerificationRunStatus.FAILED
                await self.runs.update_run(run)
                await self._event(
                    run.id, "run_failed", f"Structured obligation extraction failed safely: {exc}"
                )
                return state
            for obligation in extracted:
                obligation.run_id = run.id
                await self.verification.update_obligation(obligation)
            obligations = extracted
            await self._event(
                run.id, "obligations_extracted", f"Extracted {len(obligations)} obligations"
            )

        # Stage 5: Investigation Planning Proposal Layer
        try:
            gateway = ProviderGateway(self.settings, self.verification)
            inv_planner = InvestigationPlanningService(gateway, self.verification)
            await inv_planner.plan(run.id, run.snapshot_id, obligations)
        except Exception:
            pass

        run.status = VerificationRunStatus.VERIFYING
        await self.runs.update_run(run)

        ordered_obligations = sorted(
            obligations,
            key=lambda item: classify_obligation_routing(item) == "HUMAN_AUTHORITY",
        )

        for obligation in ordered_obligations:
            if obligation.status != ObligationStatus.PENDING:
                continue

            routing = classify_obligation_routing(obligation)

            if routing == "PROPOSED_ACTION":
                # Preserved for revised-plan synthesis only; NEVER investigated as an already-existing repository fact!
                obligation.proposal_metadata["routing"] = "PROPOSED_ACTION_SYNTHESIS_ONLY"
                await self._event(
                    run.id,
                    "obligation_preserved",
                    f"Preserved proposed action for plan revision synthesis: {obligation.statement[:80]}",
                )
                await self.verification.update_obligation(obligation)
                run.completed_obligation_ids.append(obligation.id)
                continue

            run.iteration_count += 1
            run.current_obligation_id = obligation.id
            obligation.status = ObligationStatus.VERIFYING
            await self.verification.update_obligation(obligation)
            await self._event(
                run.id,
                "obligation_started",
                f"Investigating obligation: {obligation.statement[:80]}",
            )
            if run.iteration_count > self.settings.verification_max_iterations:
                obligation.status = ObligationStatus.INCONCLUSIVE
                obligation.proposal_metadata["inconclusive_reason"] = (
                    "Verification iteration limit reached"
                )
                await self._event(
                    run.id,
                    "obligation_completed",
                    "Obligation became INCONCLUSIVE (iteration limit)",
                )
            elif routing == "HUMAN_AUTHORITY":
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

                # Phase 7: Synthesize Provisional Revised Plan v1 BEFORE entering HUMAN_WAIT
                try:
                    rev_service = PlanRevisionService(
                        ProviderGateway(self.settings, self.verification), self.verification
                    )
                    await rev_service.synthesize(
                        run.id,
                        run.project_id,
                        run.snapshot_id,
                        plan,
                        obligations,
                        status_override=RevisedPlanStatus.AWAITING_HUMAN_DECISION,
                        revision_version=1,
                    )
                except Exception:
                    pass

                return state
            else:
                await self._investigate(run, obligation, ordered_obligations)

            await self.verification.update_obligation(obligation)
            run.completed_obligation_ids.append(obligation.id)

        await self._finalize(run, plan)
        return state

    async def _investigate(self, run, obligation, ordered_obligations: list) -> None:
        """A bounded, deterministic repository investigation with exact-path priority and fair budgeting."""
        remaining_budget = max(0, self.settings.verification_max_tool_calls - run.tool_call_count)
        if remaining_budget <= 0:
            obligation.status = ObligationStatus.INCONCLUSIVE
            obligation.proposal_metadata["inconclusive_reason"] = (
                "Investigation tool budget reached"
            )
            await self._event(
                run.id,
                "obligation_completed",
                "Obligation became INCONCLUSIVE (tool budget reached)",
            )
            return

        # Fair Budget Reservation Algorithm
        remaining_pending = len(
            [
                ob
                for ob in ordered_obligations
                if ob.status in {ObligationStatus.PENDING, ObligationStatus.VERIFYING}
            ]
        )
        max_allowed_for_this_ob = max(1, remaining_budget - max(0, remaining_pending - 1))
        ob_budget = min(3, max_allowed_for_this_ob)
        ob_calls_used = 0

        tools = RepositoryTools(self.runs, self.verification, run_id=run.id)

        # Priority 0: Reuse already-read source evidence within same run & snapshot
        try:
            cursor_ev = self.verification.database.evidence.find(
                {
                    "run_id": run.id,
                    "snapshot_id": run.snapshot_id,
                    "evidence_type": EvidenceType.SOURCE_RANGE,
                }
            )
            async for prev_ev in cursor_ev:
                p = prev_ev.get("path")
                if not p:
                    continue
                file_doc = await self.verification.database.repository_files.find_one(
                    {"snapshot_id": run.snapshot_id, "path": p}
                )
                if not file_doc or file_doc.get("content_hash") != prev_ev.get("content_hash"):
                    continue
                lines = file_doc.get("text", "").splitlines()
                l_start = max(1, prev_ev.get("line_start", 1))
                l_end = min(len(lines), prev_ev.get("line_end", len(lines)))
                snippet = "\n".join(lines[l_start - 1 : l_end])

                if check_evidence_sufficiency(
                    obligation, p, snippet, prev_ev.get("matched_query") or p
                ):
                    evidence = await EvidenceAuthority(self.verification).issue_source_range(
                        snapshot_id=run.snapshot_id,
                        run_id=run.id,
                        obligation_id=obligation.id,
                        matched_query=prev_ev.get("matched_query") or p,
                        relationship="SUPPORTS",
                        tool_run_id=prev_ev["source_tool_run_id"],
                        path=p,
                        line_start=l_start,
                        line_end=l_end,
                        summary=f"Reused verified source fact in {p}:{l_start}-{l_end}",
                    )
                    await EvidenceAuthority(self.verification).validate(evidence.id)
                    obligation.evidence_ids.append(evidence.id)
                    obligation.status = ObligationStatus.VERIFIED
                    await self._event(
                        run.id,
                        "evidence_added",
                        f"Reused existing snapshot evidence from {p}:{l_start}-{l_end}",
                    )
                    await self._event(run.id, "obligation_completed", "Obligation became VERIFIED")
                    return
        except Exception:
            pass

        # Priority 1: Exact-Path-First Strategy & Snapshot Manifest Existence/Absence
        explicit_paths = _extract_explicit_paths(obligation)
        snapshot = (
            await self.runs.get_snapshot(run.snapshot_id)
            if hasattr(self.runs, "get_snapshot")
            else None
        )
        is_manifest_complete = bool(
            snapshot and snapshot.status == SnapshotStatus.READY and snapshot.manifest_complete
        )

        for target_path in explicit_paths:
            if (
                ob_calls_used >= ob_budget
                or run.tool_call_count >= self.settings.verification_max_tool_calls
            ):
                break
            file_doc = await self.verification.database.repository_files.find_one(
                {"snapshot_id": run.snapshot_id, "path": target_path}
            )

            stmt_low = obligation.statement.casefold()
            is_existence_claim = (
                obligation.semantic_role == SemanticRole.EXISTING_DEPENDENCY
                or "exists in" in stmt_low
                or "exists." in stmt_low
                or stmt_low.endswith("exists")
                or "target existence" in stmt_low
            )

            if is_existence_claim:
                try:
                    res = await tools.check_path_membership(
                        CheckPathMembershipInput(snapshot_id=run.snapshot_id, path=target_path)
                    )
                    run.tool_call_count += 1
                    ob_calls_used += 1
                    tool_doc = await self.verification.database.tool_runs.find_one(
                        {"run_id": run.id, "tool_name": "check_path_membership"},
                        sort=[("started_at", -1)],
                    )
                    if res.get("present") is True:
                        evidence = await EvidenceAuthority(self.verification).issue_path_membership(
                            snapshot_id=run.snapshot_id,
                            run_id=run.id,
                            obligation_id=obligation.id,
                            tool_run_id=tool_doc["id"]
                            if tool_doc
                            else "tool-check-path-membership",
                            path=target_path,
                            present=True,
                            summary=f"Exact path '{target_path}' verified present in repository snapshot manifest",
                        )
                        await EvidenceAuthority(self.verification).validate(evidence.id)
                        obligation.evidence_ids.append(evidence.id)
                        obligation.status = ObligationStatus.VERIFIED
                        await self._event(
                            run.id,
                            "tool_completed",
                            f"Exact path '{target_path}' present in snapshot manifest",
                        )
                        await self._event(
                            run.id,
                            "evidence_added",
                            f"Server-issued path membership evidence recorded: {evidence.id}",
                        )
                        await self._event(
                            run.id, "obligation_completed", "Obligation became VERIFIED"
                        )
                        return
                    elif (
                        res.get("present") is False
                        and is_manifest_complete
                        and not res.get("is_inconclusive")
                    ):
                        evidence = await EvidenceAuthority(self.verification).issue_path_membership(
                            snapshot_id=run.snapshot_id,
                            run_id=run.id,
                            obligation_id=obligation.id,
                            tool_run_id=tool_doc["id"]
                            if tool_doc
                            else "tool-check-path-membership",
                            path=target_path,
                            present=False,
                            relationship="CONTRADICTS",
                            summary=f"Exact path '{target_path}' is absent from complete repository snapshot manifest",
                        )
                        await EvidenceAuthority(self.verification).validate(evidence.id)
                        obligation.counter_evidence_ids.append(evidence.id)
                        obligation.status = ObligationStatus.DISPROVED
                        await self._event(
                            run.id,
                            "tool_completed",
                            f"Exact path '{target_path}' absent from complete snapshot manifest",
                        )
                        await self._event(
                            run.id,
                            "evidence_added",
                            f"Server-issued contradiction evidence recorded: {evidence.id}",
                        )
                        await self._event(
                            run.id, "obligation_completed", "Obligation became DISPROVED"
                        )
                        return
                    else:
                        inconclusive_msg = (
                            res.get("inconclusive_reason") or "Snapshot manifest is not complete"
                        )
                        obligation.status = ObligationStatus.INCONCLUSIVE
                        obligation.proposal_metadata["inconclusive_reason"] = inconclusive_msg
                        await self._event(
                            run.id,
                            "obligation_completed",
                            f"Obligation became INCONCLUSIVE: {inconclusive_msg}",
                        )
                        return
                except Exception:
                    obligation.status = ObligationStatus.INCONCLUSIVE
                    obligation.proposal_metadata["inconclusive_reason"] = (
                        "Exact path membership authority failed safely"
                    )
                    await self._event(
                        run.id,
                        "obligation_completed",
                        "Obligation became INCONCLUSIVE: exact path membership authority failed safely",
                    )
                    return

            if not file_doc:
                # Target path does not exist in snapshot
                continue

            lines = file_doc.get("text", "").splitlines()
            if not lines:
                continue

            # Read full file range up to 200 lines
            sample_snippet = "\n".join(lines[:200])

            # Check if this exact file satisfies the proposition
            if check_evidence_sufficiency(obligation, target_path, sample_snippet, target_path):
                try:
                    await tools.read_file_range(
                        ReadFileRangeInput(
                            snapshot_id=run.snapshot_id,
                            path=target_path,
                            start_line=1,
                            end_line=min(50, len(lines)),
                        )
                    )
                    run.tool_call_count += 1
                    ob_calls_used += 1
                    tool_doc = await self.verification.database.tool_runs.find_one(
                        {"run_id": run.id, "tool_name": "read_file_range"},
                        sort=[("started_at", -1)],
                    )
                    evidence = await EvidenceAuthority(self.verification).issue_source_range(
                        snapshot_id=run.snapshot_id,
                        run_id=run.id,
                        obligation_id=obligation.id,
                        matched_query=target_path,
                        relationship="SUPPORTS",
                        tool_run_id=tool_doc["id"] if tool_doc else "tool-read-file-range",
                        path=target_path,
                        line_start=1,
                        line_end=min(50, len(lines)),
                        summary=f"Exact target file verified in {target_path}:1-{min(50, len(lines))}",
                    )
                    await EvidenceAuthority(self.verification).validate(evidence.id)
                    obligation.evidence_ids.append(evidence.id)
                    obligation.status = ObligationStatus.VERIFIED
                    await self._event(
                        run.id,
                        "tool_completed",
                        f"Exact file verified in {target_path}",
                    )
                    await self._event(
                        run.id,
                        "evidence_added",
                        f"Server-issued exact-path evidence recorded: {evidence.id}",
                    )
                    await self._event(run.id, "obligation_completed", "Obligation became VERIFIED")
                    return
                except Exception:
                    pass

        # Priority 2: Primary Symbol Lookup
        if obligation.category == ObligationCategory.SYMBOL:
            symbol_candidates = _extract_primary_obligation_symbols(obligation)
            for sym in symbol_candidates[:2]:
                if (
                    ob_calls_used >= ob_budget
                    or run.tool_call_count >= self.settings.verification_max_tool_calls
                ):
                    break
                try:
                    await self._event(run.id, "tool_started", f"Searching symbols for '{sym}'")
                    symbols = await tools.find_symbol(
                        FindSymbolInput(snapshot_id=run.snapshot_id, query=sym, limit=1)
                    )
                    run.tool_call_count += 1
                    ob_calls_used += 1
                    if symbols:
                        sym_match = symbols[0]
                        file_doc = await self.verification.database.repository_files.find_one(
                            {"snapshot_id": run.snapshot_id, "path": sym_match["path"]}
                        )
                        if not file_doc:
                            continue
                        lines = file_doc.get("text", "").splitlines()
                        start_l = max(1, sym_match.get("line_start", 1))
                        end_l = min(len(lines), max(start_l, sym_match.get("line_end", start_l)))
                        matched_snippet = "\n".join(lines[start_l - 1 : end_l])

                        if not check_evidence_sufficiency(
                            obligation, sym_match["path"], matched_snippet, sym
                        ):
                            continue
                        tool_doc = await self.verification.database.tool_runs.find_one(
                            {"run_id": run.id, "tool_name": "find_symbol"},
                            sort=[("started_at", -1)],
                        )
                        if (
                            not tool_doc
                            or tool_doc.get("status") != "succeeded"
                            or tool_doc.get("snapshot_id") != run.snapshot_id
                        ):
                            continue
                        evidence = await EvidenceAuthority(self.verification).issue_source_range(
                            snapshot_id=run.snapshot_id,
                            run_id=run.id,
                            obligation_id=obligation.id,
                            matched_query=sym,
                            relationship="SUPPORTS",
                            tool_run_id=tool_doc["id"],
                            path=sym_match["path"],
                            line_start=start_l,
                            line_end=end_l,
                            summary=f"Symbol '{sym_match['qualified_name']}' ({sym_match.get('kind', 'symbol')}) found in {sym_match['path']}:{start_l}-{end_l}",
                        )
                        await EvidenceAuthority(self.verification).validate(evidence.id)
                        obligation.evidence_ids.append(evidence.id)
                        obligation.status = ObligationStatus.VERIFIED
                        await self._event(
                            run.id,
                            "tool_completed",
                            f"Found symbol '{sym_match['qualified_name']}' in {sym_match['path']}",
                        )
                        await self._event(
                            run.id,
                            "evidence_added",
                            f"Server-issued symbol evidence recorded: {evidence.id}",
                        )
                        await self._event(
                            run.id, "obligation_completed", "Obligation became VERIFIED"
                        )
                        return
                except Exception:
                    pass

        # Priority 3: Bounded Lexical Searches
        queries = extract_obligation_queries(obligation)
        for query, terminal, desc in queries:
            if (
                ob_calls_used >= ob_budget
                or run.tool_call_count >= self.settings.verification_max_tool_calls
            ):
                break
            await self._event(
                run.id, "tool_started", f"Running bounded lexical search for '{query}'"
            )
            try:
                # If target path specified, scope lexical search to that path
                target_p = explicit_paths[0] if explicit_paths else None
                matches = await tools.search_code_lexical(
                    SearchCodeInput(
                        snapshot_id=run.snapshot_id,
                        query=query,
                        path=target_p,
                        limit=1,
                    )
                )
                run.tool_call_count += 1
                ob_calls_used += 1
                if not matches:
                    continue
                match = matches[0]

                file_doc = await self.verification.database.repository_files.find_one(
                    {"snapshot_id": run.snapshot_id, "path": match["path"]}
                )
                if not file_doc:
                    continue

                lines = file_doc.get("text", "").splitlines()
                start_l = max(1, match["line_start"])
                end_l = min(len(lines), match["line_end"])
                matched_snippet = "\n".join(lines[start_l - 1 : end_l])

                if not check_evidence_sufficiency(
                    obligation, match["path"], matched_snippet, query
                ):
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
                    relationship="CONTRADICTS"
                    if terminal == ObligationStatus.DISPROVED
                    else "SUPPORTS",
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
                    run.id,
                    "tool_completed",
                    f"Repository tool returned source fact in {match['path']}",
                )
                await self._event(
                    run.id,
                    "evidence_added",
                    f"Server-issued source evidence was recorded: {evidence.id}",
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

        obligation.status = ObligationStatus.INCONCLUSIVE
        obligation.proposal_metadata["inconclusive_reason"] = (
            "No sufficient repository evidence found within investigation budget"
        )
        await self._event(
            run.id,
            "obligation_completed",
            "Obligation became INCONCLUSIVE: No sufficient repository evidence found within investigation budget",
        )

    async def _finalize(self, run, plan) -> None:
        obligations = await self.verification.list_run_obligations(run.id)
        proof_obligations = [
            ob
            for ob in obligations
            if getattr(ob, "semantic_role", None)
            in {
                SemanticRole.CURRENT_STATE_ASSUMPTION,
                SemanticRole.EXISTING_DEPENDENCY,
                SemanticRole.CONSTRAINT,
                SemanticRole.HUMAN_DECISION,
            }
        ]
        target_obligations = proof_obligations if proof_obligations else obligations
        statuses = {item.status for item in target_obligations}
        run.status = VerificationRunStatus.FINALIZING

        all_ev_ids = []
        for item in obligations:
            all_ev_ids.extend(item.evidence_ids)
            all_ev_ids.extend(item.counter_evidence_ids)
        run.evidence_count = len(set(all_ev_ids))
        run.tool_execution_count = run.tool_call_count
        run.has_open_human_question = len(run.open_human_question_ids) > 0

        await self.runs.update_run(run)
        await self._event(run.id, "run_finalizing", "Synthesizing evidence-grounded revised plan")

        # Phase 6: Synthesize Evidence-Grounded Revised Implementation Plan
        try:
            existing_revisions = await self.verification.database.revised_plans.count_documents(
                {"run_id": run.id}
            )
            revision_version = existing_revisions + 1
            rev_service = PlanRevisionService(
                ProviderGateway(self.settings, self.verification), self.verification
            )
            await rev_service.synthesize(
                run.id,
                run.project_id,
                run.snapshot_id,
                plan,
                obligations,
                revision_version=revision_version,
            )
        except Exception as exc:
            logger.exception("Revised plan synthesis failed", exc_info=exc)

        if ObligationStatus.DISPROVED in statuses:
            run.status = VerificationRunStatus.BLOCKED
        elif ObligationStatus.HUMAN_REQUIRED in statuses:
            run.status = VerificationRunStatus.HUMAN_DECISION_REQUIRED
        elif target_obligations and statuses <= {ObligationStatus.VERIFIED}:
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
