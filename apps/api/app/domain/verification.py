from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.domain.common import new_id, now_utc


class ToolRunStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class EvidenceType(StrEnum):
    SOURCE_RANGE = "SOURCE_RANGE"
    SYMBOL = "SYMBOL"
    SCHEMA = "SCHEMA"


class ValidatorResult(StrEnum):
    SATISFIED = "SATISFIED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT = "INSUFFICIENT"
    UNSUPPORTED = "UNSUPPORTED"


class ObligationCategory(StrEnum):
    SYMBOL = "SYMBOL"
    DEPENDENCY = "DEPENDENCY"
    SCHEMA = "SCHEMA"
    API_CONTRACT = "API_CONTRACT"
    IDEMPOTENCY = "IDEMPOTENCY"
    BEHAVIOR = "BEHAVIOR"
    CROSS_SERVICE = "CROSS_SERVICE"
    BUSINESS_RULE = "BUSINESS_RULE"
    UNKNOWN = "UNKNOWN"


class Criticality(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ObligationStatus(StrEnum):
    PENDING = "PENDING"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    DISPROVED = "DISPROVED"
    INCONCLUSIVE = "INCONCLUSIVE"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"


class ToolRun(BaseModel):
    id: str = Field(default_factory=new_id)
    snapshot_id: str
    run_id: str | None = None
    tool_name: str
    input_hash: str
    input_summary: dict[str, Any] | None = None
    trace_id: str = Field(default_factory=new_id)
    status: ToolRunStatus
    result_count: int = 0
    safe_error_class: str | None = None
    duration_ms: int = Field(ge=0)
    started_at: datetime = Field(default_factory=now_utc)
    finished_at: datetime = Field(default_factory=now_utc)


class Evidence(BaseModel):
    id: str = Field(default_factory=new_id)
    snapshot_id: str
    run_id: str | None = None
    obligation_id: str | None = None
    source_tool_run_id: str
    evidence_type: EvidenceType
    path: str | None = None
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    content_hash: str | None = None
    matched_query: str | None = None
    relationship: str | None = None
    summary: str = Field(min_length=1, max_length=1000)
    created_at: datetime = Field(default_factory=now_utc)


class ProofObligation(BaseModel):
    id: str = Field(default_factory=new_id)
    project_id: str
    snapshot_id: str
    plan_version_id: str
    run_id: str | None = None
    source_plan_step_ids: list[str] = Field(default_factory=list)
    statement: str = Field(min_length=1, max_length=2000)
    normalized_statement: str
    category: ObligationCategory
    criticality: Criticality
    status: ObligationStatus = ObligationStatus.PENDING
    verification_hints: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    counter_evidence_ids: list[str] = Field(default_factory=list)
    proposal_metadata: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now_utc)


class ModelCall(BaseModel):
    id: str = Field(default_factory=new_id)
    run_id: str | None = None
    purpose: str | None = None
    provider: str
    model: str
    request_schema_version: str
    response_schema_version: str
    latency_ms: int = Field(ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    retry_count: int = Field(ge=0)
    used_fallback: bool = False
    safe_error_class: str | None = None
    created_at: datetime = Field(default_factory=now_utc)
