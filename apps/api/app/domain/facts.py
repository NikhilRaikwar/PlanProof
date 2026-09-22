from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.domain.common import new_id, now_utc
from app.domain.verification import ObligationStatus


class FactRelationship(StrEnum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    HUMAN_CONFIRMED = "HUMAN_CONFIRMED"


class AuthorizedFact(BaseModel):
    id: str = Field(default_factory=new_id)
    run_id: str
    snapshot_id: str
    obligation_id: str
    obligation_status: ObligationStatus
    canonical_fact: str
    semantic_role: str = "CURRENT_STATE_ASSUMPTION"
    relationship: FactRelationship
    evidence_ids: list[str] = Field(default_factory=list)
    file_paths: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    human_decision_id: str | None = None
    created_at: datetime = Field(default_factory=now_utc)
