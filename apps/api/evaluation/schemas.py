from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ExpectedStatus(StrEnum):
    VERIFIED = "VERIFIED"
    DISPROVED = "DISPROVED"
    INCONCLUSIVE = "INCONCLUSIVE"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"


class EvalExpectation(BaseModel):
    statement_hint: str = Field(min_length=1, max_length=500)
    accepted_statuses: set[ExpectedStatus] = Field(min_length=1)
    required_evidence_paths: list[str] = Field(default_factory=list)


class EvaluationCase(BaseModel):
    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,80}$")
    case_version: str = Field(pattern=r"^v[0-9]+$")
    fixture_repo: str = Field(min_length=1, max_length=300)
    fixture_revision: str = Field(min_length=1, max_length=128)
    change_request: str = Field(min_length=1, max_length=20_000)
    candidate_plan: str = Field(min_length=1, max_length=50_000)
    critical_expected_assumptions: list[EvalExpectation] = Field(default_factory=list)
    forbidden_unsupported_claims: list[str] = Field(default_factory=list)
    expected_human_escalation: bool
    provider_configuration: dict[str, Any] = Field(default_factory=dict)
    tool_index_configuration: dict[str, Any] = Field(default_factory=dict)
    budget_configuration: dict[str, int | float] = Field(default_factory=dict)
    tags: set[str] = Field(min_length=1)


class CaseResult(BaseModel):
    case_id: str
    statuses: dict[str, str]
    evidence_paths: set[str] = Field(default_factory=set)
    human_escalated: bool = False
    tool_successes: int = 0
    tool_attempts: int = 0
    elapsed_ms: int | None = Field(default=None, ge=0)
    model_calls: int | None = Field(default=None, ge=0)
    tool_calls: int | None = Field(default=None, ge=0)
    token_usage: int | None = Field(default=None, ge=0)
    estimated_model_cost_usd: float | None = Field(default=None, ge=0)


class RegressionStatus(StrEnum):
    PASS = "PASS"
    REGRESSION = "REGRESSION"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class EvaluationRun(BaseModel):
    eval_run_id: str
    timestamp: datetime
    git_sha: str
    case_set_version: str
    sample_count: int
    provider: str
    model: str
    parser_version: str
    index_version: str
    budget_configuration: dict[str, int | float]
    results: list[CaseResult]
    metrics: dict[str, float | int]
    limitations: list[str] = Field(default_factory=list)
