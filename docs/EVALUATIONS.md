# Evaluation harness

Evaluation definitions live in `evals/cases/v1`, outside the runtime package. Each case is versioned and contains fixture identity, change request, candidate plan, expected assumptions/outcomes, unsupported claims, human-escalation expectation, provider/tool/index configuration, budgets, and tags.

The evaluator loader validates case structure and uniqueness. It persists executed outputs to `eval_runs`, separate from verification data. No production service imports expectations.

## Metrics

The evaluator calculates only metrics backed by supplied results: critical-assumption recall, status accuracy, evidence provenance validity, appropriate escalation rate, tool success rate, and optional latency/model/tool/token/cost summaries. It deliberately omits unsupported metrics such as retrieval recall when no labelled retrieval set exists.

Regression policy is explicit at the caller/CI layer. The comparator returns `PASS`, `REGRESSION`, or `INSUFFICIENT_DATA`; it never hides thresholds in the harness.

## Run an observed evaluation

The harness accepts only observed `CaseResult` JSON. It does not use expected case
answers to manufacture a product result. Run it from `apps/api` after an isolated
test/evaluator has produced results:

```bash
uv run python -m evaluation.runner \
  --results path/to/observed-results.json \
  --case-directory ../../evals/cases/v1 \
  --output eval-report.json
```

Optionally provide a prior report and an explicit JSON threshold map to produce a
typed regression decision. With no comparable measurements, the result is
`INSUFFICIENT_DATA`, not a claimed quality score.
