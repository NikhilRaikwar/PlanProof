# PlanProof

> **Engineering plans are hypotheses. PlanProof tests them before agents build them.**

PlanProof is pre-flight verification infrastructure for AI-generated engineering plans. It binds a candidate plan to an immutable repository snapshot, extracts testable proof obligations, gathers bounded repository evidence, and applies deterministic policy before allowing execution.

The core rule is simple: **the model proposes; deterministic code authorizes.**

## What is implemented

- Public GitHub repository ingestion without GitHub tokens for P0, plus an explicitly labelled seeded demo fixture.
- Immutable repository snapshots, deterministic file hashes, source symbol indexing, and bounded snapshot-scoped tools.
- Evidence that is server-issued and provenance-bound to a successful deterministic tool run.
- Provider-neutral structured model gateway: OpenRouter primary, AIMLAPI availability fallback, bounded retries, and safe model-call metadata.
- LangGraph-based bounded verification workflow with Redis/Dramatiq execution, MongoDB persistence, deterministic final gates, and human pause/resume.
- API-backed Next.js workspace, live safe event display, evidence/tool trace inspection, human decision submission, and immutable plan amendments.
- Versioned evaluation fixtures, explicit regression-policy helpers, security tests, container definitions, and CI checks.

## Deliberate engineering choices

PlanProof is not a coding agent, generic repository chatbot, or multi-agent swarm. A single explicit state machine is more auditable here: known facts are checked by deterministic validators before any model call, and adding agents would increase cost, coordination failures, and observability complexity without justified capability.

It also intentionally does not use vector RAG, arbitrary code execution, unbounded reflection loops, model confidence as authority, private GitHub support, or a complete semantic call graph in the current release. These are tradeoffs, not hidden gaps: a bounded lexical/symbol index is safer and more explainable for the supported P0 workflow.

## Architecture

```text
Next.js workspace
  -> FastAPI /v1
  -> MongoDB Atlas (projects, snapshots, plans, runs, evidence, audit)
  -> Redis + Dramatiq (durable verification jobs)
  -> LangGraph bounded orchestrator
  -> deterministic repository tools + validators
  -> OpenRouter primary / AIMLAPI fallback for structured proposals only
```

Repository facts never come from an LLM. Models can extract ambiguous candidate-plan claims or propose one allowlisted next action; they cannot create evidence IDs, read the host filesystem, execute shell commands, mutate MongoDB, or set final verification status.

See [architecture](docs/ARCHITECTURE.md), [security](docs/SECURITY.md), and [evaluation design](docs/EVALUATIONS.md).

## Product flow

1. Add a public GitHub HTTPS repository or select the labelled demo fixture.
2. Index an immutable READY snapshot.
3. Submit a change request and candidate engineering plan.
4. Create an immutable plan version and queue a verification run.
5. Resolve proof obligations with bounded tools, authoritative evidence, policy, and human authority where code cannot decide.
6. Receive a deterministic gate: `VERIFIED_FOR_EXECUTION`, `BLOCKED`, `HUMAN_DECISION_REQUIRED`, `INCONCLUSIVE`, or `FAILED`.

## Local development

Prerequisites: Node 22+, Python 3.11–3.13, Docker (for local Redis), and a local ignored `.env` populated from `.env.example`. Never commit `.env`.

```bash
docker compose up redis
cd apps/api
uv sync --all-groups
uv run uvicorn app.main:app --reload --port 8000
```

In another terminal, run `cd apps/api && uv run dramatiq app.workflow.worker`. For the UI, run `npm ci` then `npm run dev`.

Local quality checks:

```bash
npm run typecheck
npm run build
npm run test:ui
cd apps/api && uv run ruff check app tests && uv run pytest -q
```

Network/paid provider and Atlas checks are deliberately marked separately from deterministic tests.

## Evaluation harness

The `evals/cases/v1` set contains versioned test-only metadata spanning schema, idempotency, API, dependency, human-authority, provider-failure, prompt-injection, evidence-provenance, worker-retry, and budget-safety scenarios. Evaluation expectations never enter production workflow code.

Metrics are produced only from observed evaluator outputs; when a metric cannot be substantiated, it is omitted rather than invented. A regression comparison accepts explicit caller-provided thresholds and can return `PASS`, `REGRESSION`, or `INSUFFICIENT_DATA`.

## Deployment

The production target is Google Cloud Run (Next.js UI and FastAPI), Cloud Run Worker Pools (Dramatiq), Artifact Registry, Secret Manager, Memorystore Redis, and MongoDB Atlas in `asia-south1` under `planproof-ai`.

Deployment definitions and a runbook are in [docs/DEPLOYMENT_GCP.md](docs/DEPLOYMENT_GCP.md). The runbook keeps mutable deployment URLs out of source control; a production deployment is usable only after its live and dependency readiness checks succeed.

## Honest limitations

- Public GitHub HTTPS repositories only; no OAuth, GitHub App, or private repository access.
- Python parsing is AST-backed for the supported subset. TypeScript/JavaScript extraction is lightweight and does not provide complete type resolution, call graphs, or semantic references.
- Deterministic reference/dependency results are explicitly partial where the index is partial.
- The project has deployment templates and production safeguards, but deployment status must be verified against the target cloud account.

## Review path

- [API and workflow implementation](apps/api/app)
- [Versioned evaluation cases](evals/cases/v1)
- [Security controls and threat boundaries](docs/SECURITY.md)
- [GCP deployment runbook](docs/DEPLOYMENT_GCP.md)
- [Five-minute product demonstration](docs/DEMO.md)

MIT. Copyright © 2026 Nikhil Raikwar.
