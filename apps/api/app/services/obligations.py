from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.domain.verification import Criticality, ObligationCategory, ProofObligation
from app.repositories.verification import VerificationRepository
from app.services.models import ModelGateway, ModelRequest, parse_json_object


class ObligationProposal(BaseModel):
    statement: str = Field(min_length=5, max_length=2000)
    category: ObligationCategory = ObligationCategory.UNKNOWN
    criticality: Criticality = Criticality.MEDIUM
    verification_hints: list[str] = Field(default_factory=list, max_length=5)


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
        run_id: str | None = None,
    ) -> list[ProofObligation]:
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
                "Category must be one of SYMBOL, DEPENDENCY, SCHEMA, API_CONTRACT, IDEMPOTENCY, BEHAVIOR, "
                "CROSS_SERVICE, BUSINESS_RULE, UNKNOWN. Use BUSINESS_RULE ONLY for propositions requiring external human "
                "policy/authority (e.g. data retention, legal compliance, pricing). Technical claims (symbols, modules, "
                "imports, calls, configs) must NEVER use BUSINESS_RULE. "
                "Criticality must be LOW, MEDIUM, HIGH, or CRITICAL. "
                "verification_hints must be an array of strings (max 5 exact identifiers/paths). "
                'Return only JSON: {"obligations":[{"statement":"...","category":"...","criticality":"...","verification_hints":["..."]}]}.'
            ),
            user=f"Change request:\n{change_request}\nCandidate plan:\n{plan}",
        )
        try:
            result = await self.gateway.complete(req, run_id=run_id)
        except TypeError:
            result = await self.gateway.complete(req)
        proposals = ObligationProposals.model_validate(parse_json_object(result.content))
        output = []
        for proposal in proposals.obligations:
            normalized = re.sub(r"\s+", " ", proposal.statement.strip().casefold())
            output.append(
                await self.repository.create_obligation(
                    ProofObligation(
                        project_id=project_id,
                        snapshot_id=snapshot_id,
                        plan_version_id=plan_version_id,
                        run_id=run_id,
                        statement=proposal.statement,
                        normalized_statement=normalized,
                        category=proposal.category,
                        criticality=proposal.criticality,
                        verification_hints=proposal.verification_hints,
                        proposal_metadata={
                            "provider": result.provider,
                            "model": result.model,
                            "prompt_tokens": str(result.prompt_tokens or 0),
                            "completion_tokens": str(result.completion_tokens or 0),
                        },
                    )
                )
            )
        return output
