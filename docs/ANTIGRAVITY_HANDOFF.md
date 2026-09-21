# PlanProof engineering handoff

## Product

PlanProof is pre-flight verification infrastructure for AI-generated engineering plans: it binds a candidate plan to an immutable repository snapshot, extracts testable obligations, gathers bounded code evidence, and applies a server-authoritative gate before execution.

**The model proposes; deterministic code authorizes.** Models produce structured proposals only. Repository facts, evidence IDs, source locations, tool policy, budgets, and final statuses belong to deterministic services.

Phases 0–7 are complete. The Phase 8/9 production foundation is deployed: evaluation harness, security boundaries, Cloud Run deployment, API-backed UI, Redis/Dramatiq worker, LangGraph workflow, evidence and HITL. The only remaining final gate is one clean deployed Playwright lifecycle after resolving the browser snapshot-post regression described below.

## Deployed topology

- GCP project `planproof-ai`, region `asia-south1`.
- Web: Cloud Run service `planproof-web`, canonical URL `https://planproof-web-lfrrer4z6q-el.a.run.app` (latest known `planproof-web-00005-lw4`).
- API: Cloud Run service `planproof-api`, canonical URL `https://planproof-api-lfrrer4z6q-el.a.run.app` (current ready revision `planproof-api-00012-wwk`).
- Worker: Cloud Run Worker Pool `planproof-worker`, Dramatiq consuming Memorystore Redis (latest known `planproof-worker-00009-tlv`).
- State: MongoDB Atlas; queue: Memorystore for Redis; images: Artifact Registry repository `planproof`; secrets: Secret Manager.
- Networking: VPC/private Redis and Cloud NAT static egress `34.93.153.36/32`, allowlisted in Atlas.
- Providers: OpenRouter primary and AIMLAPI availability fallback.
- Logging/metrics: Cloud Logging/Monitoring plus safe structured application instrumentation.

No secret values are in this document.

## Important commits

- `9f4ef45 feat(tools): add deterministic evidence foundations` — scoped tools, provenance and validation foundations.
- `ef263b8 feat(workflow): add durable verification orchestration` — durable LangGraph workflow.
- `f7242f7 test(workflow): prove restart safety and bounded verification` — restart/budget coverage.
- `f613a68 feat(workflow): execute evidence-backed obligation verification` — tool/evidence loop.
- `ee7bfee feat(policy): expose deterministic verification run projection` — final projection API.
- `e53dda2 feat(frontend): connect verification workspace to API` — real API-backed UI.
- `0458be2 fix(ui): remove static repository context` — removes fake production context.
- `e6bc3dc feat(evals): add versioned verification evaluation harness` — versioned evaluator.
- `4370ec8 fix(security): harden runtime dependencies and request boundaries` — production boundary middleware.
- `b6bb3dd chore(gcp): prepare Cloud Run production deployment` — containers, Cloud Build, deployment docs.
- `46975aa fix(production): harden browser workflow isolation` — CORS/error behavior, project-scoped snapshots, UI polling and E2E cleanup.
- `97e4426 fix(test): make E2E cleanup utility executable` — safe cleanup operator utility.
- `001bf4a fix(ui): recover persisted live verification state` — persisted projection recovery after SSE disruption.

## Proven working

The repository already demonstrates immutable snapshots, deterministic repository tools, server-issued provenance-bound evidence, structured obligation extraction, provider routing/fallback, Mongo persistence/reconnect, LangGraph workflow, Redis/Dramatiq execution, duplicate-delivery protection, HUMAN_WAIT and restart/resume, deterministic final gates, immutable amendments, API-backed UI, SSE/projection recovery, deployed GCP web/API/worker, Atlas and Memorystore readiness, and safe evaluation/security/CI/deployment work.

Previously observed validations: deterministic backend suite `43 passed` (with integration tests separately selected) and targeted Atlas ingestion `4 passed`. A real seeded backend workflow reached `HUMAN_WAIT`, persisted tool/evidence records, accepted a persisted human answer, resumed, and ended `BLOCKED` while unrelated disproved obligations remained disproved.

## Single remaining regression

The final production Playwright flow can create its isolated seeded project in the browser. In some fresh runs its immediately following browser snapshot POST does not result in a persisted snapshot, so it cannot reach READY → run → HUMAN_WAIT → resume → BLOCKED.

This is currently a browser/API integration regression, not evidence that the verification engine is broken. Do not assume root cause: the direct control below proves the deployed endpoint itself works for the affected project.

## Exact reproduction and control

Browser route: `https://planproof-web-lfrrer4z6q-el.a.run.app/workspace/repositories`.

UI operation: choose `seeded_fixture`, fixture `partial-refunds-v1`, provide an `e2e-*` display name, then click **Create and index snapshot**. The frontend sends `POST /v1/projects/{project_id}/snapshots` with no body. Expected is HTTP 201 and a persisted READY seeded snapshot. The frontend's project creation request is `POST /v1/projects` with a repository source shaped like `{ "type": "seeded_fixture", "fixture_id": "partial-refunds-v1" }` (no secrets).

The failed final run left project `801b29ca-e60a-4476-a27a-97d52fdfaa0b` (`e2e-seeded-prod-final-e2e-clean`) without a snapshot immediately after the browser action. The project ID is valid and the seeded discriminator is valid. The prior browser failure context showed `rate limit exceeded` on the report page; this led to a local, uncommitted default rate-limit adjustment from 60 to 300 requests/minute. That change has been built/deployed as API revision `planproof-api-00012-wwk`, but must be committed only after final verification.

Direct deployed control for that exact project succeeded:

`POST https://planproof-api-lfrrer4z6q-el.a.run.app/v1/projects/801b29ca-e60a-4476-a27a-97d52fdfaa0b/snapshots`

returned **201** with snapshot `35696300-99db-4d55-ae48-88d70e2c5b8e`, status `READY`, 7 indexed files, 27 symbols. This confirms FastAPI, Mongo persistence, fixture resolution, and snapshot idempotency are functional for the project. The next agent should focus on browser request construction/error handling/rate middleware interaction and test synchronization, not rebuild ingestion.

Use Cloud Run request logs for the exact POST to determine whether the browser request reaches FastAPI and which safe status it returns. Check CORS/rate/body validation before changing ingestion. Never include credentials in logs or notes.

## Code map

- `app/workspace/repositories/page.tsx` — browser form, project creation, snapshot POST, persisted project/snapshot polling.
- `lib/api.ts` — typed frontend HTTP client and normalized API errors.
- `app/workspace/new-verification/page.tsx` — READY snapshot selection and immutable plan/run creation.
- `app/workspace/runs/[runId]/page.tsx` — SSE plus persisted run projection recovery and HITL UI.
- `apps/api/app/api/snapshots.py` — `POST /v1/projects/{project_id}/snapshots` and snapshot reads.
- `apps/api/app/ingestion/service.py` — safe materialization, hashing, parsing, indexing, READY transition.
- `apps/api/app/ingestion/sources.py` — public GitHub and seeded fixture source validation.
- `apps/api/app/repositories/runs.py` — snapshots, plan versions, runs and events persistence.
- `apps/api/app/db/indexes.py` — project-scoped immutable snapshot unique index and index migration.
- `apps/api/app/main.py` — request-size/rate limiting and CORS middleware ordering.
- `apps/api/app/core/config.py` — runtime configuration, including the currently uncommitted 300/min default.
- `tests/seeded-real.e2e.spec.ts` — production browser lifecycle test; currently has uncommitted, state-based reload/strict-locator hardening.
- `apps/api/scripts/cleanup_e2e.py` — exact-name, `e2e-*`-only cleanup utility.

## Highest-priority debugging seams

1. `app/workspace/repositories/page.tsx`: inspect the actual browser response from `api.createSnapshot` and ensure `load()` failure cannot hide a successful/failed snapshot POST.
2. `lib/api.ts` and `apps/api/app/main.py`: compare browser request headers/origin with direct control; rate-limit/CORS responses must remain readable.
3. `tests/seeded-real.e2e.spec.ts`: ensure it reloads/awaits persisted snapshot state after the POST and does not assume one same-render refresh completed.

## Current git state

At handoff creation, HEAD is `001bf4a`. Uncommitted files are:

- `apps/api/app/core/config.py`: raises default unauthenticated request limit 60 → 300 because real report polling can exceed 60/minute.
- `tests/seeded-real.e2e.spec.ts`: state-based browser reload after creation, explicit human-authority wording, and non-brittle exact DISPROVED locator.
- this handoff file.

These are coherent finalization changes, not speculative architecture. Commit them locally only after reviewing/validating the final E2E; do not push. `next-env.d.ts` is clean at this point.

## Environment contract

Names only: `MONGODB_URI`, `MONGODB_DATABASE`, `REDIS_URL`, `OPENROUTER_API_KEY`, `OPENROUTER_PRIMARY_MODEL`, `AIMLAPI_API_KEY`, `AIMLAPI_FALLBACK_MODEL`, `NEXT_PUBLIC_PLANPROOF_API_URL`, `PLANPROOF_WEB_ORIGINS`, `PLANPROOF_ENV`, `PLANPROOF_FIXTURES_ROOT`, `OTEL_EXPORTER_OTLP_ENDPOINT`, and `OTEL_SERVICE_NAME`.

Mongo, Redis, and provider values are supplied to Cloud Run from Secret Manager (except ordinary non-secret deployment configuration such as origins, fixture root and OTEL service name). Frontend exposes only `NEXT_PUBLIC_PLANPROOF_API_URL`.

## Commands

From repository root:

```powershell
# frontend
npm run typecheck
npm run test:ui
npm run build
$env:PLAYWRIGHT_EXTERNAL_SERVER='1'; $env:PLAYWRIGHT_BASE_URL='https://planproof-web-lfrrer4z6q-el.a.run.app'; $env:PLANPROOF_E2E_TAG='prod-final-unique'; npx playwright test tests/seeded-real.e2e.spec.ts --reporter=line

# backend
Set-Location apps/api
C:\Users\raikw\.local\bin\uv.exe run ruff check app evaluation tests
C:\Users\raikw\.local\bin\uv.exe run pytest -q
C:\Users\raikw\.local\bin\uv.exe run python scripts/cleanup_e2e.py --project-name e2e-seeded-prod-final-unique

# deployed health/log/resource inspection
curl.exe -sS https://planproof-api-lfrrer4z6q-el.a.run.app/health/ready
& 'C:\Users\raikw\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd' run services describe planproof-api --project planproof-ai --region asia-south1
& 'C:\Users\raikw\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd' run worker-pools describe planproof-worker --project planproof-ai --region asia-south1
& 'C:\Users\raikw\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd' beta run worker-pools logs tail planproof-worker --project planproof-ai --region asia-south1

# affected service deploys only
& 'C:\Users\raikw\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd' builds submit --config cloudbuild.api.yaml --substitutions=_IMAGE=asia-south1-docker.pkg.dev/planproof-ai/planproof/api:TAG .
& 'C:\Users\raikw\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd' run deploy planproof-api --project planproof-ai --region asia-south1 --image asia-south1-docker.pkg.dev/planproof-ai/planproof/api:TAG --quiet
& 'C:\Users\raikw\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd' run worker-pools deploy planproof-worker --project planproof-ai --region asia-south1 --image asia-south1-docker.pkg.dev/planproof-ai/planproof/api:TAG --quiet
```

For a frontend-only change, use `cloudbuild.web.yaml` and deploy `planproof-web` with its Artifact Registry image. Do not recreate healthy infrastructure.

## Definition of done

Fix only the snapshot browser integration issue, deploy only affected components, and run one clean production Playwright E2E proving browser project → persisted READY snapshot → queued run → worker → tools/evidence → HUMAN_REQUIRED → browser answer → resume → authoritative BLOCKED, with a disproved obligation still present, evidence and tool trace pages working. Run exact cleanup and targeted regressions. No new product features are needed.
