from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from app.domain.verification import (
    Criticality,
    ObligationCategory,
    ProofObligation,
    SemanticRole,
    TargetIntent,
)
from app.repositories.verification import VerificationRepository
from app.services.models import ModelGateway, ModelRequest, parse_json_object

_PATH_EXT_RE = r"(?:@\/|[a-zA-Z0-9_.-]+\/)*[a-zA-Z0-9_.-]+\.(?:tsx?|jsx?|py|json|yaml|yml|toml|sql|md|css|env|go|rs|rb|java|c|cpp|h|hpp|sh)"


def _extract_canonical_paths_from_text(text: str) -> list[str]:
    """Extract explicit file paths preserving exact case and canonical git posix semantics."""
    paths: list[str] = []
    for match in re.finditer(_PATH_EXT_RE, text):
        raw = match.group(0).strip().strip("'\"`").replace("\\", "/")
        if raw.startswith("@/"):
            raw = raw[2:]
        if raw.startswith("./"):
            raw = raw[2:]
        if (
            raw in {"import.meta.env", "process.env"}
            or raw.startswith("import.meta")
            or raw.startswith("process.env")
        ):
            continue
        if raw and not raw.startswith("/") and ".." not in raw and "\x00" not in raw:
            paths.append(raw)

    seen = set()
    deduped = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            deduped.append(p)
    return deduped


def classify_target_intent(statement: str) -> TargetIntent:
    """
    Classify the target intent of a proposed action:
    - MUST_EXIST: Verbs like update, modify, replace in, delete, remove from, refactor, rename, patch, edit
    - CREATE_NEW: Verbs like create, add, introduce, scaffold, generate, implement
    - CREATE_OR_UPDATE: Both creation and update mentioned
    - UNKNOWN: Ambiguous phrasing
    """
    s = statement.strip().lower()
    if (
        "create or update" in s
        or "create and update" in s
        or "create and then update" in s
        or "add or update" in s
        or "add and update" in s
    ):
        return TargetIntent.CREATE_OR_UPDATE
    if ("introduce" in s or "create" in s or "add" in s) and (
        "modify" in s or "update" in s or "replace" in s or "delete" in s or "remove" in s
    ):
        return TargetIntent.CREATE_OR_UPDATE
    if s.startswith("do not ") or "don't " in s:
        return TargetIntent.UNKNOWN

    is_create = any(
        re.search(rf"\b{verb}\b", s)
        for verb in ["create", "add", "introduce", "scaffold", "generate", "implement"]
    )
    is_modify = any(
        re.search(rf"\b{verb}\b", s)
        for verb in [
            "update",
            "modify",
            "replace",
            "remove",
            "delete",
            "rename",
            "refactor",
            "edit",
            "patch",
            "migrate away from",
            "deprecate in",
        ]
    )

    if is_create and is_modify:
        return TargetIntent.CREATE_OR_UPDATE
    if is_modify:
        return TargetIntent.MUST_EXIST
    if is_create:
        return TargetIntent.CREATE_NEW
    return TargetIntent.UNKNOWN


class ObligationProposal(BaseModel):
    statement: str = Field(min_length=5, max_length=2000)
    semantic_role: SemanticRole = SemanticRole.CURRENT_STATE_ASSUMPTION
    category: ObligationCategory = ObligationCategory.UNKNOWN
    criticality: Criticality = Criticality.MEDIUM
    verification_hints: list[str] = Field(default_factory=list, max_length=5)
    source_plan_step_ids: list[str] = Field(default_factory=list)


class ObligationProposals(BaseModel):
    obligations: list[ObligationProposal] = Field(max_length=20)


class ObligationExtractionService:
    def __init__(self, gateway: ModelGateway, repository: VerificationRepository) -> None:
        self.gateway, self.repository = gateway, repository

    async def extract(
        self,
        project_id: str,
        snapshot_id: str,
        plan_version_id: str,
        change_request: str,
        plan: str,
        normalized_steps: list[Any] | None = None,
        run_id: str | None = None,
    ) -> list[ProofObligation]:
        from app.domain.runs import normalize_candidate_plan_steps

        # 1. Deterministic MUST_EXIST derivation from original candidate plan steps
        if normalized_steps is None:
            steps_to_analyze = normalize_candidate_plan_steps(plan)
        else:
            steps_to_analyze = normalized_steps

        derived_prerequisites: dict[str, ObligationProposal] = {}
        for step in steps_to_analyze:
            intent = classify_target_intent(step.text)
            if intent == TargetIntent.MUST_EXIST:
                paths = _extract_canonical_paths_from_text(step.text)
                for path in paths:
                    prereq_stmt = f"{path} exists in the current snapshot."
                    key = prereq_stmt.strip().casefold()
                    if key in derived_prerequisites:
                        if step.id not in derived_prerequisites[key].source_plan_step_ids:
                            derived_prerequisites[key].source_plan_step_ids.append(step.id)
                    else:
                        derived_prerequisites[key] = ObligationProposal(
                            statement=prereq_stmt,
                            semantic_role=SemanticRole.EXISTING_DEPENDENCY,
                            category=ObligationCategory.DEPENDENCY,
                            criticality=Criticality.HIGH,
                            verification_hints=[path],
                            source_plan_step_ids=[step.id],
                        )

        # 2. Extract semantic obligations via model gateway
        req = ModelRequest(
            system=(
                "You are PlanProof's formal obligation extractor. Decompose candidate plans into "
                "ATOMIC, INDEPENDENTLY VERIFIABLE propositions. Each proposition must represent ONE "
                "concrete code fact (e.g. 'Component X imports Y from Z', 'Component X calls Y', "
                "'Provider X wraps routes in App.tsx', 'Schema X contains field Y', 'Module Z reads env var W') "
                "or ONE genuine business policy proposition (e.g. 'Conversation history must be retained for 30 days'). "
                "NEVER combine multiple claims into one statement. "
                "NEVER use subjective or compound buzzwords like 'correctly implemented', 'reliable', "
                "'secures the application', 'properly integrated', 'backward compatible'. "
                "Classify each proposition with a strict `semantic_role`: \n"
                "- `CURRENT_STATE_ASSUMPTION`: Factual claim asserting the repository's present state before changes.\n"
                "- `EXISTING_DEPENDENCY`: Claim asserting that a pre-existing dependency/symbol/module exists in the repo.\n"
                "- `PROPOSED_ACTION`: Future planned mutation or replacement action (e.g. 'Replace X with Y', 'Create Z'). "
                "Must NEVER be classified as CURRENT_STATE_ASSUMPTION.\n"
                "- `CONSTRAINT`: Invariant or boundary condition (technical schema/code constraints, or business constraints).\n"
                "- `HUMAN_DECISION`: External policy, business authorization, product decision, or external credential.\n"
                "Category must be one of SYMBOL, DEPENDENCY, SCHEMA, API_CONTRACT, IDEMPOTENCY, BEHAVIOR, "
                "CROSS_SERVICE, BUSINESS_RULE, UNKNOWN. Use BUSINESS_RULE ONLY for propositions requiring external human "
                "policy/authority. Technical claims must NEVER use BUSINESS_RULE. "
                "Criticality must be LOW, MEDIUM, HIGH, or CRITICAL. "
                "verification_hints must be an array of strings (max 5 exact identifiers/paths). "
                'Return only JSON: {"obligations":[{"statement":"...","semantic_role":"...","category":"...","criticality":"...","verification_hints":["..."]}]}.'
            ),
            user=f"Change request:\n{change_request}\nCandidate plan:\n{plan}",
        )
        try:
            result = await self.gateway.complete(req, run_id=run_id)
        except TypeError:
            result = await self.gateway.complete(req)
        proposals = ObligationProposals.model_validate(parse_json_object(result.content))

        # Check model proposals for additional implied MUST_EXIST prerequisites
        for proposal in proposals.obligations:
            if proposal.semantic_role == SemanticRole.PROPOSED_ACTION:
                intent = classify_target_intent(proposal.statement)
                if intent == TargetIntent.MUST_EXIST:
                    paths = _extract_canonical_paths_from_text(
                        proposal.statement + " " + " ".join(proposal.verification_hints)
                    )
                    for path in paths:
                        prereq_stmt = f"{path} exists in the current snapshot."
                        key = prereq_stmt.strip().casefold()
                        if key not in derived_prerequisites:
                            derived_prerequisites[key] = ObligationProposal(
                                statement=prereq_stmt,
                                semantic_role=SemanticRole.EXISTING_DEPENDENCY,
                                category=ObligationCategory.DEPENDENCY,
                                criticality=Criticality.HIGH,
                                verification_hints=[path],
                                source_plan_step_ids=list(proposal.source_plan_step_ids),
                            )

        # Merge model proposals and server-derived prerequisites, deduplicating
        final_proposals: list[ObligationProposal] = []
        emitted_keys = set()

        for proposal in proposals.obligations:
            key = proposal.statement.strip().casefold()
            if key in derived_prerequisites:
                prereq = derived_prerequisites[key]
                combined_step_ids = list(
                    dict.fromkeys(prereq.source_plan_step_ids + proposal.source_plan_step_ids)
                )
                prereq.source_plan_step_ids = combined_step_ids
                if key not in emitted_keys:
                    emitted_keys.add(key)
                    final_proposals.append(prereq)
            else:
                emitted_keys.add(key)
                final_proposals.append(proposal)

        for key, prereq in derived_prerequisites.items():
            if key not in emitted_keys:
                emitted_keys.add(key)
                final_proposals.append(prereq)

        output = []
        for proposal in final_proposals:
            normalized = re.sub(r"\s+", " ", proposal.statement.strip().casefold())
            metadata = {
                "provider": result.provider,
                "model": result.model,
                "prompt_tokens": str(result.prompt_tokens or 0),
                "completion_tokens": str(result.completion_tokens or 0),
            }
            if proposal.semantic_role == SemanticRole.PROPOSED_ACTION:
                metadata["target_intent"] = str(classify_target_intent(proposal.statement))

            output.append(
                await self.repository.create_obligation(
                    ProofObligation(
                        project_id=project_id,
                        snapshot_id=snapshot_id,
                        plan_version_id=plan_version_id,
                        run_id=run_id,
                        source_plan_step_ids=proposal.source_plan_step_ids,
                        statement=proposal.statement,
                        normalized_statement=normalized,
                        semantic_role=proposal.semantic_role,
                        category=proposal.category,
                        criticality=proposal.criticality,
                        verification_hints=proposal.verification_hints,
                        proposal_metadata=metadata,
                    )
                )
            )
        return output
