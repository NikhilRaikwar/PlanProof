from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.domain.facts import AuthorizedFact, FactRelationship
from app.domain.revised_plans import (
    ConfidenceBasis,
    PlanChange,
    PlanChangeType,
    RevisedPlan,
    RevisedPlanStatus,
    RevisedPlanStep,
)
from app.domain.runs import PlanVersion
from app.domain.verification import ObligationStatus, ProofObligation
from app.repositories.revised_plans import RevisedPlansRepository

if TYPE_CHECKING:
    from app.repositories.verification import VerificationRepository
    from app.services.models import ProviderGateway

logger = logging.getLogger(__name__)


class ModelPlanChange(BaseModel):
    change_type: str
    source_plan_step_ids: list[str] = Field(default_factory=list)
    original_text: str | None = None
    updated_text: str | None = None
    rationale: str = ""
    basis_fact_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    human_decision_ids: list[str] = Field(default_factory=list)


class ModelRevisedPlanStep(BaseModel):
    order: int
    action: str
    rationale: str
    status: str = "MODIFY"
    source_plan_step_ids: list[str] = Field(default_factory=list)
    basis_fact_ids: list[str] = Field(default_factory=list)
    supporting_obligation_ids: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    supporting_human_decision_ids: list[str] = Field(default_factory=list)
    unresolved_dependency_ids: list[str] = Field(default_factory=list)
    existing_target_files: list[str] = Field(default_factory=list)
    proposed_new_files: list[str] = Field(default_factory=list)
    existing_target_symbols: list[str] = Field(default_factory=list)
    proposed_new_symbols: list[str] = Field(default_factory=list)
    target_symbols: list[str] = Field(default_factory=list)
    confidence_basis: str = "UNRESOLVED"


class ModelRevisedPlanResponse(BaseModel):
    executive_summary: str
    plan_changes: list[ModelPlanChange] = Field(default_factory=list)
    implementation_plan: list[ModelRevisedPlanStep] = Field(default_factory=list)


class PlanRevisionService:
    def __init__(
        self,
        gateway: ProviderGateway | None,
        verification: VerificationRepository,
    ) -> None:
        self.gateway = gateway
        self.verification = verification
        self.database = verification.database
        self.repository = RevisedPlansRepository(verification.database)

    async def derive_authorized_facts(
        self,
        run_id: str,
        snapshot_id: str,
        obligations: list[ProofObligation],
    ) -> list[AuthorizedFact]:
        """Derive canonical server-owned facts strictly from VERIFIED, DISPROVED, or answered human obligations."""
        facts: list[AuthorizedFact] = []

        for ob in obligations:
            if ob.status == ObligationStatus.VERIFIED and ob.evidence_ids:
                # Fetch actual evidence records
                cursor = self.database.evidence.find({"id": {"$in": ob.evidence_ids}})
                ev_docs = [doc async for doc in cursor]
                paths = list({doc["path"] for doc in ev_docs if doc.get("path")})
                symbols = list(
                    {doc["matched_query"] for doc in ev_docs if doc.get("matched_query")}
                )
                facts.append(
                    AuthorizedFact(
                        run_id=run_id,
                        snapshot_id=snapshot_id,
                        obligation_id=ob.id,
                        obligation_status=ob.status,
                        semantic_role=getattr(ob, "semantic_role", None),
                        canonical_fact=f"Present-state repository fact: {ob.statement}",
                        relationship=FactRelationship.SUPPORTS,
                        evidence_ids=ob.evidence_ids,
                        file_paths=paths,
                        symbols=symbols,
                    )
                )
            elif ob.status == ObligationStatus.DISPROVED and ob.counter_evidence_ids:
                cursor = self.database.evidence.find({"id": {"$in": ob.counter_evidence_ids}})
                ev_docs = [doc async for doc in cursor]
                paths = list({doc["path"] for doc in ev_docs if doc.get("path")})
                symbols = list(
                    {doc["matched_query"] for doc in ev_docs if doc.get("matched_query")}
                )
                facts.append(
                    AuthorizedFact(
                        run_id=run_id,
                        snapshot_id=snapshot_id,
                        obligation_id=ob.id,
                        obligation_status=ob.status,
                        semantic_role=getattr(ob, "semantic_role", None),
                        canonical_fact=f"Contradicted candidate assumption: {ob.statement}",
                        relationship=FactRelationship.CONTRADICTS,
                        evidence_ids=ob.counter_evidence_ids,
                        file_paths=paths,
                        symbols=symbols,
                    )
                )

        # Check for answered human decisions
        cursor = self.database.human_questions.find(
            {"run_id": run_id, "answer": {"$exists": True, "$ne": None}}
        )
        async for q_doc in cursor:
            facts.append(
                AuthorizedFact(
                    run_id=run_id,
                    snapshot_id=snapshot_id,
                    obligation_id=q_doc["obligation_id"],
                    obligation_status=ObligationStatus.VERIFIED,
                    canonical_fact=f"Human authority decision: {q_doc.get('answer')}",
                    relationship=FactRelationship.HUMAN_CONFIRMED,
                    human_decision_id=q_doc["id"],
                )
            )

        # Persist facts for auditability
        for f in facts:
            try:
                await self.database.authorized_facts.insert_one(f.model_dump(mode="python"))
            except Exception:
                pass

        return facts

    async def synthesize(
        self,
        run_id: str,
        project_id: str,
        snapshot_id: str,
        plan_version: PlanVersion,
        obligations: list[ProofObligation],
        status_override: RevisedPlanStatus | None = None,
        revision_version: int = 1,
    ) -> RevisedPlan:
        """Synthesize an evidence-grounded updated implementation plan with strict server-side validation."""
        # 1. Derive authoritative facts
        facts = await self.derive_authorized_facts(run_id, snapshot_id, obligations)
        fact_map = {f.id: f for f in facts}
        valid_fact_evidence_ids = {ev_id for f in facts for ev_id in f.evidence_ids}

        # 2. Fetch snapshot file list for target file validation
        cursor = self.database.repository_files.find(
            {"snapshot_id": snapshot_id}, {"path": 1}
        )
        snapshot_files = {doc["path"] async for doc in cursor}

        # 3. Determine plan status
        statuses = {ob.status for ob in obligations}
        if status_override:
            final_status = status_override
        elif ObligationStatus.HUMAN_REQUIRED in statuses:
            final_status = RevisedPlanStatus.AWAITING_HUMAN_DECISION
        elif ObligationStatus.DISPROVED in statuses or ObligationStatus.INCONCLUSIVE in statuses:
            final_status = RevisedPlanStatus.PROVISIONAL
        elif statuses <= {ObligationStatus.VERIFIED}:
            final_status = RevisedPlanStatus.EVIDENCE_GROUNDED
        else:
            final_status = RevisedPlanStatus.PROVISIONAL

        # 4. Invoke model synthesis if gateway is available
        model_call_id: str | None = None
        plan_changes: list[PlanChange] = []
        implementation_plan: list[RevisedPlanStep] = []
        executive_summary = ""

        if self.gateway:
            prompt_payload = {
                "change_request": plan_version.change_request,
                "original_plan_steps": [
                    {"id": s.id, "order": s.order, "text": s.text}
                    for s in plan_version.normalized_steps
                ],
                "authorized_facts": [
                    {
                        "fact_id": f.id,
                        "obligation_id": f.obligation_id,
                        "canonical_fact": f.canonical_fact,
                        "relationship": str(f.relationship),
                        "file_paths": f.file_paths,
                        "symbols": f.symbols,
                        "evidence_ids": f.evidence_ids,
                    }
                    for f in facts
                ],
                "unresolved_items": [
                    {
                        "obligation_id": ob.id,
                        "statement": ob.statement,
                        "status": str(ob.status),
                        "reason": ob.proposal_metadata.get("inconclusive_reason", ""),
                    }
                    for ob in obligations
                    if ob.status in {ObligationStatus.INCONCLUSIVE, ObligationStatus.HUMAN_REQUIRED}
                ],
            }

            system_instruction = (
                "You are an expert engineering reviewer. Synthesize an evidence-grounded updated implementation plan.\n"
                "CRITICAL SEMANTIC RULES:\n"
                "1. Distinguish present repository state from planned future actions. NEVER state that a proposed replacement "
                "or new component already exists in the repository unless verified in authorized_facts.\n"
                "2. `existing_target_files`: MUST list only verified snapshot files that exist now in the repository.\n"
                "3. `proposed_new_files`: MUST list any new files that need to be created.\n"
                "4. `existing_target_symbols`: MUST list only symbols that currently exist in the repository snapshot.\n"
                "5. `proposed_new_symbols`: MUST list any new symbols to be created/introduced.\n"
                "6. `unresolved_dependency_ids`: MUST list any unresolved dependencies or obligations lacking repository evidence.\n"
                "7. Every factual statement or modification must cite a valid `basis_fact_id` from the provided authorized_facts.\n"
                "8. If a candidate plan step contradicts repository facts or is redundant, mark it MODIFY or REMOVE with evidence rationale.\n"
                "9. If a step relies on unverified dependencies or requires human authority, mark confidence_basis as UNRESOLVED."
            )

            response: ModelRevisedPlanResponse | None = None
            validation_error: str | None = None
            max_attempts = 2

            try:
                for attempt in range(1, max_attempts + 1):
                    current_payload = dict(prompt_payload)
                    if validation_error:
                        current_payload["semantic_validation_error"] = (
                            f"Your previous revision proposal violated semantic facts: {validation_error}. "
                            f"Fix all structured fields and prose to strictly adhere to authorized facts and snapshot files."
                        )

                    try:
                        candidate_response = await self.gateway.complete_structured(
                            prompt=json.dumps(current_payload, indent=2),
                            schema=ModelRevisedPlanResponse,
                            system=system_instruction,
                            run_id=run_id,
                            purpose="PLAN_REVISION",
                        )
                    except Exception as exc:
                        logger.warning(f"Plan revision model synthesis attempt {attempt} failed safely: {exc}")
                        break

                    if not candidate_response:
                        break

                    # Validate candidate response structured fields against snapshot
                    validation_issues = []
                    for step in candidate_response.implementation_plan:
                        for fpath in step.existing_target_files:
                            clean_p = fpath.strip().replace("\\", "/")
                            if clean_p and clean_p not in snapshot_files:
                                validation_issues.append(
                                    f"File '{clean_p}' in step {step.order} was listed in existing_target_files, but does not exist in the snapshot"
                                )

                    if validation_issues and attempt < max_attempts:
                        validation_error = "; ".join(validation_issues)
                        logger.info(f"Plan revision attempt {attempt} semantic validation failed: {validation_error}. Retrying bounded...")
                        continue

                    response = candidate_response
                    break

                if response:
                    executive_summary = response.executive_summary[:1000]

                    # Validate Plan Changes
                    for raw_change in response.plan_changes:
                        try:
                            ctype = PlanChangeType(raw_change.change_type)
                        except ValueError:
                            ctype = PlanChangeType.MODIFY

                        # Validate basis facts
                        valid_fact_ids = [fid for fid in raw_change.basis_fact_ids if fid in fact_map]
                        valid_ev_ids = [eid for eid in raw_change.evidence_ids if eid in valid_fact_evidence_ids]

                        plan_changes.append(
                            PlanChange(
                                change_type=ctype,
                                source_plan_step_ids=raw_change.source_plan_step_ids,
                                original_text=raw_change.original_text,
                                updated_text=raw_change.updated_text,
                                rationale=raw_change.rationale,
                                basis_fact_ids=valid_fact_ids,
                                evidence_ids=valid_ev_ids,
                                human_decision_ids=raw_change.human_decision_ids,
                            )
                        )

                    # Validate Implementation Plan Steps
                    for raw_step in response.implementation_plan:
                        try:
                            stype = PlanChangeType(raw_step.status)
                        except ValueError:
                            stype = PlanChangeType.MODIFY

                        valid_fact_ids = [fid for fid in raw_step.basis_fact_ids if fid in fact_map]
                        valid_ev_ids = [eid for eid in raw_step.supporting_evidence_ids if eid in valid_fact_evidence_ids]

                        # Verify existing target files strictly exist in snapshot
                        existing_files: list[str] = []
                        suggested_files: list[str] = list(raw_step.proposed_new_files)

                        step_has_invalid_existing_file = False
                        for fpath in raw_step.existing_target_files:
                            clean_fpath = fpath.strip().replace("\\", "/")
                            if clean_fpath in snapshot_files:
                                existing_files.append(clean_fpath)
                            else:
                                step_has_invalid_existing_file = True
                                suggested_files.append(clean_fpath)

                        if step_has_invalid_existing_file:
                            stype = PlanChangeType.UNRESOLVED

                        # Determine strict confidence basis
                        if step_has_invalid_existing_file:
                            confidence = ConfidenceBasis.UNRESOLVED
                        elif valid_fact_ids and any(fact_map[fid].relationship in {FactRelationship.SUPPORTS, FactRelationship.CONTRADICTS} for fid in valid_fact_ids):
                            confidence = ConfidenceBasis.EVIDENCE_BACKED
                        elif raw_step.supporting_human_decision_ids:
                            confidence = ConfidenceBasis.HUMAN_CONFIRMED
                        elif valid_fact_ids:
                            confidence = ConfidenceBasis.PARTIALLY_EVIDENCED
                        else:
                            confidence = ConfidenceBasis.UNRESOLVED

                        implementation_plan.append(
                            RevisedPlanStep(
                                order=raw_step.order,
                                action=raw_step.action,
                                rationale=raw_step.rationale,
                                status=stype,
                                source_plan_step_ids=raw_step.source_plan_step_ids,
                                basis_fact_ids=valid_fact_ids,
                                supporting_obligation_ids=raw_step.supporting_obligation_ids,
                                supporting_evidence_ids=valid_ev_ids,
                                supporting_human_decision_ids=raw_step.supporting_human_decision_ids,
                                unresolved_dependency_ids=raw_step.unresolved_dependency_ids,
                                existing_target_files=existing_files,
                                proposed_new_files=suggested_files,
                                existing_target_symbols=raw_step.existing_target_symbols,
                                proposed_new_symbols=raw_step.proposed_new_symbols,
                                target_symbols=raw_step.target_symbols or (raw_step.existing_target_symbols + raw_step.proposed_new_symbols),
                                confidence_basis=confidence,
                            )
                        )
            except Exception as exc:
                logger.warning(f"Plan revision model synthesis failed safely: {exc}")
                # Failure mode: Do NOT fabricate a false plan.
                final_status = RevisedPlanStatus.UNAVAILABLE
                executive_summary = "Verification completed, but updated-plan synthesis was unavailable."

        # If model failed or no plan produced, create safe fallback entry
        if not implementation_plan and final_status != RevisedPlanStatus.UNAVAILABLE:
            final_status = RevisedPlanStatus.UNAVAILABLE
            executive_summary = "Verification completed, but updated-plan synthesis was unavailable."

        revised_plan = RevisedPlan(
            run_id=run_id,
            project_id=project_id,
            snapshot_id=snapshot_id,
            original_plan_version_id=plan_version.id,
            revision_version=revision_version,
            status=final_status,
            executive_summary=executive_summary,
            plan_changes=plan_changes,
            implementation_plan=implementation_plan,
            model_call_id=model_call_id,
        )

        saved = await self.repository.create(revised_plan)
        logger.info("Saved revised plan id=%s run_id=%s version=%s status=%s steps=%d", saved.id, run_id, saved.revision_version, saved.status, len(saved.implementation_plan))
        return saved
