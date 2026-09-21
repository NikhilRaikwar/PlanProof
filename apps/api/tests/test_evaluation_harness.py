import json
from pathlib import Path

from evaluation.harness import calculate_metrics, load_cases, regression_gate
from evaluation.runner import main
from evaluation.schemas import CaseResult, RegressionStatus

CASE_DIRECTORY = Path(__file__).parents[3] / "evals" / "cases" / "v1"


def test_versioned_case_set_has_meaningful_breadth() -> None:
    cases = load_cases(CASE_DIRECTORY)

    assert len(cases) >= 20
    assert len({case.case_id for case in cases}) == len(cases)
    tags = {tag for case in cases for tag in case.tags}
    assert {"schema", "security", "provider", "human", "budgets"} <= tags


def test_metrics_are_calculated_only_from_observed_case_results() -> None:
    cases = load_cases(CASE_DIRECTORY)
    case = next(item for item in cases if item.case_id == "schema-uniqueness")
    result = CaseResult(
        case_id=case.case_id,
        statuses={"refund schema supports multiple partial refunds": "DISPROVED"},
        evidence_paths={"db/models/refund.ts"},
        tool_successes=1,
        tool_attempts=1,
    )

    metrics = calculate_metrics([case], [result])

    assert metrics["critical_assumption_recall"] == 1
    assert metrics["status_accuracy"] == 1
    assert metrics["evidence_provenance_validity"] == 1
    assert "p50_latency_ms" not in metrics
    assert "estimated_model_cost_per_run" not in metrics


def test_regression_thresholds_are_explicit_and_insufficient_data_is_honest() -> None:
    assert regression_gate({}, {}, {"status_accuracy": 0.01}) is RegressionStatus.INSUFFICIENT_DATA
    assert regression_gate(
        {"status_accuracy": 0.9}, {"status_accuracy": 0.7}, {"status_accuracy": 0.1}
    ) is RegressionStatus.REGRESSION
    assert regression_gate(
        {"status_accuracy": 0.9}, {"status_accuracy": 0.85}, {"status_accuracy": 0.1}
    ) is RegressionStatus.PASS


def test_offline_runner_requires_observed_results_and_emits_explicit_regression(
    tmp_path: Path,
) -> None:
    results = tmp_path / "observed.json"
    baseline = tmp_path / "baseline.json"
    thresholds = tmp_path / "thresholds.json"
    output = tmp_path / "report.json"
    results.write_text(
        json.dumps(
            [
                {
                    "case_id": "schema-uniqueness",
                    "statuses": {"refund schema supports multiple partial refunds": "DISPROVED"},
                    "evidence_paths": ["db/models/refund.ts"],
                    "human_escalated": False,
                    "tool_successes": 1,
                    "tool_attempts": 1,
                }
            ]
        ),
        encoding="utf-8",
    )
    baseline.write_text(json.dumps({"metrics": {"status_accuracy": 1.0}}), encoding="utf-8")
    thresholds.write_text(json.dumps({"status_accuracy": 0.01}), encoding="utf-8")

    assert main(
        [
            "--results",
            str(results),
            "--case-directory",
            str(CASE_DIRECTORY),
            "--baseline",
            str(baseline),
            "--thresholds",
            str(thresholds),
            "--output",
            str(output),
        ]
    ) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["sample_count"] == 1
    assert report["regression_status"] == "PASS"
