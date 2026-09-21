"""Offline, test-only evaluator for observed PlanProof case outputs.

This module intentionally lives outside ``app``. It never participates in a
production verification run and never supplies expected answers to runtime
code. A caller must provide observed case results produced by an isolated test
execution before metrics or regression decisions can be emitted.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from evaluation.harness import build_run, load_cases, regression_gate
from evaluation.schemas import CaseResult


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a versioned PlanProof evaluation report.")
    parser.add_argument(
        "--results", type=Path, required=True, help="Observed CaseResult JSON array"
    )
    parser.add_argument(
        "--case-directory",
        type=Path,
        default=Path("../../evals/cases/v1"),
        help="Versioned case metadata directory",
    )
    parser.add_argument("--provider", default="deterministic-test")
    parser.add_argument("--model", default="not-used")
    parser.add_argument("--parser-version", default="v1")
    parser.add_argument("--index-version", default="v1")
    parser.add_argument("--git-sha", default=_git_sha())
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--thresholds", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cases = load_cases(args.case_directory)
    raw_results = _read_json(args.results)
    if not isinstance(raw_results, list):
        raise ValueError("--results must contain a JSON array of observed CaseResult objects")
    results = [CaseResult.model_validate(item) for item in raw_results]
    run = build_run(
        cases=cases,
        results=results,
        git_sha=args.git_sha,
        provider=args.provider,
        model=args.model,
        parser_version=args.parser_version,
        index_version=args.index_version,
        budget_configuration={},
    )
    report = run.model_dump(mode="json")
    if args.baseline and args.thresholds:
        baseline = _read_json(args.baseline)
        thresholds = _read_json(args.thresholds)
        report["regression_status"] = regression_gate(
            baseline["metrics"] if "metrics" in baseline else baseline,
            run.metrics,
            thresholds,
        ).value
    output = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
