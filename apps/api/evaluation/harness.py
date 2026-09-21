from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from uuid import uuid4

from pymongo.asynchronous.database import AsyncDatabase

from evaluation.schemas import CaseResult, EvaluationCase, EvaluationRun, RegressionStatus


def load_cases(case_directory: Path) -> list[EvaluationCase]:
    """Load versioned test-only data; never import this from runtime application code."""
    cases = [
        EvaluationCase.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(case_directory.glob("*.json"))
    ]
    ids = [case.case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("evaluation case IDs must be unique")
    return cases


def calculate_metrics(
    cases: list[EvaluationCase], results: list[CaseResult]
) -> dict[str, float | int]:
    """Compute only metrics that the supplied evaluator output can substantiate."""
    by_id = {result.case_id: result for result in results}
    expected_pairs: list[tuple[set[str], str]] = []
    critical_hits = 0
    critical_total = 0
    evidence_checks = 0
    evidence_valid = 0
    escalation_checks = 0
    escalation_matches = 0
    tool_successes = 0
    tool_attempts = 0
    latencies: list[int] = []
    model_calls: list[int] = []
    tool_calls: list[int] = []
    token_usage: list[int] = []
    costs: list[float] = []
    for case in cases:
        result = by_id.get(case.case_id)
        if result is None:
            continue
        escalation_checks += 1
        escalation_matches += result.human_escalated == case.expected_human_escalation
        for expectation in case.critical_expected_assumptions:
            actual = result.statuses.get(expectation.statement_hint)
            if actual is not None:
                expected_pairs.append((set(expectation.accepted_statuses), actual))
            critical_total += 1
            if actual in expectation.accepted_statuses:
                critical_hits += 1
            if expectation.required_evidence_paths:
                evidence_checks += len(expectation.required_evidence_paths)
                evidence_valid += sum(
                    path in result.evidence_paths for path in expectation.required_evidence_paths
                )
        tool_successes += result.tool_successes
        tool_attempts += result.tool_attempts
        if result.elapsed_ms is not None:
            latencies.append(result.elapsed_ms)
        if result.model_calls is not None:
            model_calls.append(result.model_calls)
        if result.tool_calls is not None:
            tool_calls.append(result.tool_calls)
        if result.token_usage is not None:
            token_usage.append(result.token_usage)
        if result.estimated_model_cost_usd is not None:
            costs.append(result.estimated_model_cost_usd)
    metrics: dict[str, float | int] = {"sample_count": len(results)}
    if critical_total:
        metrics["critical_assumption_recall"] = critical_hits / critical_total
    if expected_pairs:
        status_matches = sum(actual in expected for expected, actual in expected_pairs)
        metrics["status_accuracy"] = status_matches / len(expected_pairs)
    if evidence_checks:
        metrics["evidence_provenance_validity"] = evidence_valid / evidence_checks
    if escalation_checks:
        metrics["appropriate_escalation_rate"] = escalation_matches / escalation_checks
    if tool_attempts:
        metrics["tool_success_rate"] = tool_successes / tool_attempts
    if latencies:
        ordered = sorted(latencies)
        metrics["p50_latency_ms"] = median(ordered)
        metrics["p95_latency_ms"] = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    if model_calls:
        metrics["model_calls_per_run"] = sum(model_calls) / len(model_calls)
    if tool_calls:
        metrics["tool_calls_per_run"] = sum(tool_calls) / len(tool_calls)
    if token_usage:
        metrics["token_usage_per_run"] = sum(token_usage) / len(token_usage)
    if costs:
        metrics["estimated_model_cost_per_run"] = sum(costs) / len(costs)
    return metrics


def build_run(
    *,
    cases: list[EvaluationCase],
    results: list[CaseResult],
    git_sha: str,
    provider: str,
    model: str,
    parser_version: str,
    index_version: str,
    budget_configuration: dict[str, int | float],
) -> EvaluationRun:
    return EvaluationRun(
        eval_run_id=f"eval-{uuid4()}",
        timestamp=datetime.now(UTC),
        git_sha=git_sha,
        case_set_version="v1",
        sample_count=len(results),
        provider=provider,
        model=model,
        parser_version=parser_version,
        index_version=index_version,
        budget_configuration=budget_configuration,
        results=results,
        metrics=calculate_metrics(cases, results),
        limitations=[
            "Metrics describe only the executed fixture set and do not establish general "
            "production accuracy."
        ],
    )


def regression_gate(
    baseline: dict[str, float | int],
    candidate: dict[str, float | int],
    thresholds: dict[str, float],
) -> RegressionStatus:
    """Thresholds are caller-provided policy, never hidden evaluator constants."""
    comparable = [name for name in thresholds if name in baseline and name in candidate]
    if not comparable:
        return RegressionStatus.INSUFFICIENT_DATA
    for name in comparable:
        if float(candidate[name]) < float(baseline[name]) - thresholds[name]:
            return RegressionStatus.REGRESSION
    return RegressionStatus.PASS


def dump_run(run: EvaluationRun) -> str:
    return json.dumps(run.model_dump(mode="json"), indent=2, sort_keys=True)


async def persist_run(database: AsyncDatabase, run: EvaluationRun) -> None:
    """Store evaluation output separately from product verification state."""
    await database.eval_runs.insert_one(run.model_dump(mode="python"))
