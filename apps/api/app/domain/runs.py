from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.domain.common import new_id, now_utc


class SnapshotStatus(StrEnum):
    CREATED = "CREATED"
    RESOLVING = "RESOLVING"
    CLONING = "CLONING"
    HASHING = "HASHING"
    PARSING = "PARSING"
    INDEXING = "INDEXING"
    READY = "READY"
    FAILED = "FAILED"
    UNSUPPORTED = "UNSUPPORTED"


class VerificationRunStatus(StrEnum):
    CREATED = "CREATED"
    INDEX_REQUIRED = "INDEX_REQUIRED"
    READY = "READY"
    FAILED = "FAILED"


class RepositorySnapshot(BaseModel):
    id: str = Field(default_factory=new_id)
    project_id: str
    repository_identity: str
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
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class RunEvent(BaseModel):
    id: str = Field(default_factory=new_id)
    run_id: str
    sequence: int = Field(ge=1)
    event_type: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=500)
    created_at: datetime = Field(default_factory=now_utc)
