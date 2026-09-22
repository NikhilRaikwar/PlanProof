from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.domain.investigation import (
    InvestigationAction,
    InvestigationActionType,
    InvestigationIntent,
    InvestigationPlan,
)
from app.domain.verification import ProofObligation

if TYPE_CHECKING:
    from app.repositories.verification import VerificationRepository
    from app.services.models import ProviderGateway


class ModelInvestigationAction(BaseModel):
    action_type: str
    path: str | None = None
    symbol: str | None = None
    query: str | None = None
    identifiers: list[str] = Field(default_factory=list)


class ModelInvestigationIntent(BaseModel):
    obligation_id: str
    facts_needed: list[str] = Field(default_factory=list)
    proposed_actions: list[ModelInvestigationAction] = Field(default_factory=list)
    safe_rationale: str = ""


class ModelInvestigationPlanResponse(BaseModel):
    intents: list[ModelInvestigationIntent] = Field(default_factory=list)


class InvestigationPlanningService:
    def __init__(
        self,
        gateway: ProviderGateway | None,
        verification: VerificationRepository,
    ) -> None:
        self.gateway = gateway
        self.verification = verification
        self.database = verification.database

    def validate_action(
        self,
        action: InvestigationAction,
        snapshot_files: set[str],
    ) -> InvestigationAction | None:
        """Deterministic server-side authorization filter for model-proposed actions."""
        # 1. Action type authorization
        if action.action_type not in InvestigationActionType:
            return None

        # 2. Path normalization & traversal protection
        if action.path:
            raw_path = action.path.strip().replace("\\", "/")
            if raw_path.startswith("/") or ".." in raw_path or "\x00" in raw_path:
                return None
            norm_path = str(PurePosixPath(raw_path))
            if norm_path.startswith("..") or norm_path.startswith("/"):
                return None
            action.path = norm_path

            # If action requires exact file existence, verify snapshot containment
            if action.action_type in {
                InvestigationActionType.INSPECT_EXACT_FILE,
                InvestigationActionType.READ_SOURCE_RANGE,
            }:
                if snapshot_files and action.path not in snapshot_files:
                    # File does not exist in immutable snapshot
                    return None

        # 3. Symbol / Query length boundaries
        if action.symbol:
            action.symbol = action.symbol.strip()[:200]
            if not action.symbol:
                action.symbol = None

        if action.query:
            action.query = action.query.strip()[:200]
            if not action.query:
                action.query = None

        action.identifiers = [
            ident.strip()[:100] for ident in action.identifiers if ident.strip()
        ][:10]

        return action

    def generate_deterministic_intents(
        self,
        obligations: list[ProofObligation],
        snapshot_files: set[str],
    ) -> list[InvestigationIntent]:
        """Deterministic query and locator planning without model dependency."""
        from app.workflow.engine import _extract_explicit_paths, _extract_primary_obligation_symbols

        intents: list[InvestigationIntent] = []
        for ob in obligations:
            actions: list[InvestigationAction] = []
            explicit_paths = _extract_explicit_paths(ob)
            primary_symbols = _extract_primary_obligation_symbols(ob)

            # Priority 1: Explicit path in snapshot
            for p in explicit_paths:
                if p in snapshot_files:
                    actions.append(
                        InvestigationAction(
                            action_type=InvestigationActionType.INSPECT_EXACT_FILE,
                            path=p,
                            identifiers=primary_symbols[:5],
                        )
                    )

            # Priority 2: Primary symbols
            for sym in primary_symbols[:3]:
                actions.append(
                    InvestigationAction(
                        action_type=InvestigationActionType.FIND_SYMBOL,
                        symbol=sym,
                        query=sym,
                        identifiers=[sym],
                    )
                )

            # Priority 3: Fallback lexical search query
            if not actions:
                actions.append(
                    InvestigationAction(
                        action_type=InvestigationActionType.SEARCH_LEXICAL,
                        query=ob.statement[:60],
                    )
                )

            intents.append(
                InvestigationIntent(
                    obligation_id=ob.id,
                    facts_needed=[f"Verify proposition: {ob.statement}"],
                    proposed_actions=actions,
                    safe_rationale="Deterministic locator strategy derived from explicit paths and symbols",
                )
            )

        return intents

    async def plan(
        self,
        run_id: str,
        snapshot_id: str,
        obligations: list[ProofObligation],
    ) -> InvestigationPlan:
        """Create an InvestigationPlan via structured model gateway or deterministic fallback."""
        # Fetch available files in snapshot
        cursor = self.database.repository_files.find(
            {"snapshot_id": snapshot_id}, {"path": 1}
        )
        snapshot_files = {doc["path"] async for doc in cursor}

        model_call_id: str | None = None
        intents: list[InvestigationIntent] = []

        if self.gateway and obligations:
            prompt_payload = {
                "snapshot_file_count": len(snapshot_files),
                "sample_files": sorted(list(snapshot_files))[:40],
                "obligations": [
                    {
                        "obligation_id": ob.id,
                        "statement": ob.statement,
                        "category": str(ob.category),
                        "verification_hints": ob.verification_hints,
                    }
                    for ob in obligations
                ],
            }

            system_instruction = (
                "You are an investigation planning assistant. Given a list of proof obligations for an immutable "
                "codebase snapshot, propose focused investigation actions (INSPECT_EXACT_FILE, FIND_SYMBOL, SEARCH_LEXICAL). "
                "Prioritize exact file paths when an obligation mentions a specific file."
            )

            try:
                response = await self.gateway.complete_structured(
                    prompt=str(prompt_payload),
                    schema=ModelInvestigationPlanResponse,
                    system=system_instruction,
                    run_id=run_id,
                    purpose="INVESTIGATION_PLANNING",
                )
                if response:
                    for raw_intent in response.intents:
                        valid_actions: list[InvestigationAction] = []
                        for raw_action in raw_intent.proposed_actions:
                            try:
                                atype = InvestigationActionType(raw_action.action_type)
                            except ValueError:
                                continue
                            action_obj = InvestigationAction(
                                action_type=atype,
                                path=raw_action.path,
                                symbol=raw_action.symbol,
                                query=raw_action.query,
                                identifiers=raw_action.identifiers,
                            )
                            validated = self.validate_action(action_obj, snapshot_files)
                            if validated:
                                valid_actions.append(validated)

                        if valid_actions:
                            intents.append(
                                InvestigationIntent(
                                    obligation_id=raw_intent.obligation_id,
                                    facts_needed=raw_intent.facts_needed,
                                    proposed_actions=valid_actions,
                                    safe_rationale=raw_intent.safe_rationale[:200],
                                )
                            )
            except Exception:
                # Fall back safely
                intents = []

        # If model proposal failed or returned empty intents, use deterministic planner
        if not intents:
            intents = self.generate_deterministic_intents(obligations, snapshot_files)

        plan = InvestigationPlan(
            run_id=run_id,
            snapshot_id=snapshot_id,
            model_call_id=model_call_id,
            intents=intents,
        )

        try:
            await self.database.investigation_plans.insert_one(plan.model_dump(mode="python"))
        except Exception:
            pass

        return plan
