from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.domain.common import new_id, now_utc


class InvestigationActionType(StrEnum):
    INSPECT_EXACT_FILE = "INSPECT_EXACT_FILE"
    FIND_SYMBOL = "FIND_SYMBOL"
    SEARCH_LEXICAL = "SEARCH_LEXICAL"
    READ_SOURCE_RANGE = "READ_SOURCE_RANGE"


class InvestigationAction(BaseModel):
    action_type: InvestigationActionType
    path: str | None = None
    symbol: str | None = None
    query: str | None = None
    identifiers: list[str] = Field(default_factory=list)
    context_lines: int = Field(default=2, ge=0, le=5)


class InvestigationIntent(BaseModel):
    obligation_id: str
    facts_needed: list[str] = Field(default_factory=list)
    proposed_actions: list[InvestigationAction] = Field(default_factory=list)
    safe_rationale: str = ""


class InvestigationPlan(BaseModel):
    id: str = Field(default_factory=new_id)
    run_id: str
    snapshot_id: str
    model_call_id: str | None = None
    intents: list[InvestigationIntent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now_utc)
