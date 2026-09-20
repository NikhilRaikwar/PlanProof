from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.domain.common import new_id, now_utc


class SnapshotStatus(StrEnum):
    CREATED = "CREATED"
    RESOLVING = "RESOLVING"
    MATERIALIZING = "MATERIALIZING"
    HASHING = "HASHING"
    PARSING = "PARSING"
    INDEXING = "INDEXING"
    READY = "READY"
    FAILED = "FAILED"
    UNSUPPORTED = "UNSUPPORTED"


class VerificationRunStatus(StrEnum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    EXTRACTING_OBLIGATIONS = "EXTRACTING_OBLIGATIONS"
    VERIFYING = "VERIFYING"
    HUMAN_WAIT = "HUMAN_WAIT"
    FINALIZING = "FINALIZING"
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"
    HUMAN_DECISION_REQUIRED = "HUMAN_DECISION_REQUIRED"
    INCONCLUSIVE = "INCONCLUSIVE"
    FAILED = "FAILED"


class RepositorySnapshot(BaseModel):
    id: str = Field(default_factory=new_id)
    project_id: str
    repository_identity: str
    source_type: str | None = None
    requested_ref: str | None = None
    resolved_commit_sha: str | None = None
    root_content_hash: str | None = None
    parser_version: str
    index_version: str
    status: SnapshotStatus = SnapshotStatus.CREATED
    files_discovered: int = 0
    files_indexed: int = 0
    symbols_indexed: int = 0
    unsupported_files: int = 0
    ignored_files: int = 0
    supported_languages: list[str] = Field(default_factory=list)
    failure_category: str | None = None
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class PlanVersion(BaseModel):
    id: str = Field(default_factory=new_id)
    project_id: str
    version: int = Field(ge=1)
    change_request: str = Field(min_length=1, max_length=20_000)
    candidate_plan: str = Field(min_length=1, max_length=50_000)
    parent_plan_version_id: str | None = None
    created_at: datetime = Field(default_factory=now_utc)


class VerificationRun(BaseModel):
    id: str = Field(default_factory=new_id)
    project_id: str
    snapshot_id: str
    plan_version_id: str
    status: VerificationRunStatus = VerificationRunStatus.CREATED
    idempotency_key: str | None = None
    current_obligation_id: str | None = None
    completed_obligation_ids: list[str] = Field(default_factory=list)
    open_human_question_ids: list[str] = Field(default_factory=list)
    iteration_count: int = 0
    tool_call_count: int = 0
    model_call_count: int = 0
    retrieved_context_bytes: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: float = 0
    started_at: datetime | None = None
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class RunEvent(BaseModel):
    id: str = Field(default_factory=new_id)
    run_id: str
    sequence: int = Field(ge=1)
    event_type: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=500)
    created_at: datetime = Field(default_factory=now_utc)


class HumanQuestionStatus(StrEnum):
    OPEN = "OPEN"
    ANSWERED = "ANSWERED"


class HumanQuestion(BaseModel):
    id: str = Field(default_factory=new_id)
    run_id: str
    obligation_id: str
    question: str = Field(min_length=1, max_length=1000)
    why_needed: str = Field(min_length=1, max_length=1000)
    authority_required: str = Field(min_length=1, max_length=200)
    status: HumanQuestionStatus = HumanQuestionStatus.OPEN
    answer: str | None = Field(default=None, max_length=5000)
    actor_id: str | None = None
    created_at: datetime = Field(default_factory=now_utc)
    answered_at: datetime | None = None
