from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.domain.common import new_id, now_utc


class PlanChangeType(StrEnum):
    KEEP = "KEEP"
    MODIFY = "MODIFY"
    REMOVE = "REMOVE"
    ADD = "ADD"
    UNRESOLVED = "UNRESOLVED"


class ConfidenceBasis(StrEnum):
    EVIDENCE_BACKED = "EVIDENCE_BACKED"
    PARTIALLY_EVIDENCED = "PARTIALLY_EVIDENCED"
    HUMAN_CONFIRMED = "HUMAN_CONFIRMED"
    UNRESOLVED = "UNRESOLVED"


class RevisedPlanStatus(StrEnum):
    EVIDENCE_GROUNDED = "EVIDENCE_GROUNDED"
    PROVISIONAL = "PROVISIONAL"
    AWAITING_HUMAN_DECISION = "AWAITING_HUMAN_DECISION"
    UNAVAILABLE = "UNAVAILABLE"


class PlanChange(BaseModel):
    id: str = Field(default_factory=new_id)
    change_type: PlanChangeType
    source_plan_step_ids: list[str] = Field(default_factory=list)
    original_text: str | None = None
    updated_text: str | None = None
    rationale: str
    basis_fact_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    human_decision_ids: list[str] = Field(default_factory=list)


class RevisedPlanStep(BaseModel):
    id: str = Field(default_factory=new_id)
    order: int
    action: str
    rationale: str
    status: PlanChangeType

    source_plan_step_ids: list[str] = Field(default_factory=list)
    basis_fact_ids: list[str] = Field(default_factory=list)
    supporting_obligation_ids: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    supporting_human_decision_ids: list[str] = Field(default_factory=list)
    unresolved_dependency_ids: list[str] = Field(default_factory=list)

    existing_target_files: list[str] = Field(default_factory=list)
    proposed_new_files: list[str] = Field(default_factory=list)
    target_symbols: list[str] = Field(default_factory=list)

    confidence_basis: ConfidenceBasis


class RevisedPlan(BaseModel):
    id: str = Field(default_factory=new_id)
    run_id: str
    project_id: str
    snapshot_id: str
    original_plan_version_id: str
    revision_version: int = 1
    status: RevisedPlanStatus
    executive_summary: str

    plan_changes: list[PlanChange] = Field(default_factory=list)
    implementation_plan: list[RevisedPlanStep] = Field(default_factory=list)

    model_call_id: str | None = None
    created_at: datetime = Field(default_factory=now_utc)
