# PlanProof Production Readiness & Audit Report

**Audit Date**: September 2026  
**Infrastructure Project**: `planproof-ai` (GCP Region: `asia-south1`)  
**Repository**: `NikhilRaikwar/PlanProof`  

---

## 1. Production Health & Service Checklist

| Component | Target Resource | Status | Verification Evidence |
| :--- | :--- | :--- | :--- |
| **Web Service** | Cloud Run: `planproof-web` | **READY** | `https://planproof-web-lfrrer4z6q-el.a.run.app` |
| **API Service** | Cloud Run: `planproof-api` | **READY** | `https://planproof-api-lfrrer4z6q-el.a.run.app` (Revision `planproof-api-00060-d2l`) |
| **Worker Service** | Cloud Run: `planproof-verification-worker` | **READY** | `https://planproof-verification-worker-lfrrer4z6q-el.a.run.app` (Scale-to-zero, min=0, max=1) |
| **Health Probe** | `/health/ready` | **HEALTHY** | Returns `{"status":"ok","mongo":"ok","queue":"cloud_tasks"}` |
| **Database** | MongoDB Atlas (`planproofapp`) | **HEALTHY** | Collections with unique & compound indexes verified across snapshots, runs, outbox, and evaluations |
| **Queue / Dispatch** | Google Cloud Tasks (`planproof-verification-queue`) | **HEALTHY** | Serverless task delivery, OIDC IAM authentication, 1800s dispatch deadline, and monotonic execution generation |
| **Scheduler** | Cloud Scheduler (`planproof-outbox-recovery`) | **HEALTHY** | Periodic `/internal/tasks/recover-dispatches` invocation (OIDC authenticated) |
| **GitHub App** | `PlanProof Verification` | **AUTHENTICATED**| Live verified via GitHub App installation |
| **Model Gateway** | OpenRouter (Primary) / AIMLAPI (Fallback) | **ACTIVE** | Server-side credentials, structured output validation |

---

## 2. Real Authenticated Production Verification Proof

A full end-to-end verification run was executed through the live authenticated Web UI:

- **Run ID**: `375a0873-1fd5-4172-a025-19510cc03d6a`
- **Repository**: `NikhilRaikwar/Aelix` (Snapshot `71f6d0b`, branch `main`, commit `57ef352`)
- **Execution Generation**: `0`
- **Deterministic Task Name**: `run-375a0873-1fd5-4172-a025-19510cc03d6a-g0`
- **Cloud Task Dispatch**: Initiated by `planproof-api` via MongoDB outbox pattern into `planproof-verification-queue`
- **OIDC Target Audience**: `https://planproof-verification-worker-lfrrer4z6q-el.a.run.app`
- **Worker Execution**: Confirmed processed by `planproof-verification-worker-00010-zpr` at `2026-09-24T19:08:17Z`
- **Execution Claim**: Atomic MongoDB lease acquired (`claimed_at`, `claim_expires_at`, `execution_claim_id`)
- **Workflow Execution**: LangGraph pre-flight engine executed, recorded tool traces (`search_code_lexical`), and completed model extraction
- **Final Domain State**: `INCONCLUSIVE` (persisted durably in MongoDB `verification_runs`)
  - *Note: `INCONCLUSIVE` is a valid verification-domain outcome reflecting literal lexical search finding no matching code evidence for generic query strings in the searched snapshot, not an infrastructure failure.*
- **SSE & UI Updates**: Real-time event projection delivered to user browser session
- **Infrastructure Status**: 100% successful execution without unhandled errors

---

## 3. Redis Decommission & Cost Position

### Redis Decommission Audit
- **API Secret Mapping**: `REDIS_URL` / `planproof-redis-url` mapping completely removed from `planproof-api`.
- **Active API Revision**: `planproof-api-00060-d2l` deployed and serving 100% traffic with zero Redis configuration.
- **Health Verification**:
  - `/health/live` returns `200 OK` (`{"status":"ok","mongo":null,"queue":null}`)
  - `/health/ready` returns `200 OK` (`{"status":"ok","mongo":"ok","queue":"cloud_tasks"}`)
- **Logs Inspection**: Verified clean startup with zero Redis connection attempts or missing-variable errors.
- **Memorystore Decommission**: Memorystore instance `planproof-redis` in `asia-south1` deleted (`Listed 0 items`).
- **Old Worker Pool**: Confirmed no persistent worker pool remains.
- **Legacy Secret**: Secret Manager secret object `planproof-redis-url` remains as an unused legacy object pending optional later cleanup.

### Final Cost Position
- **Near-zero idle verification execution cost**:
  - Fixed Redis ($35+/mo) and persistent verification-worker compute costs have been completely eliminated.
  - Verification compute now scales to zero (`min-instances=0`) and is 100% usage-driven.
- **Static Egress Preservation**:
  - Cloud NAT (`planproof-nat`), Cloud Router (`planproof-router`), and static external IP (`34.93.153.36`) remain intentionally provisioned for secure MongoDB Atlas allowlisting.
  - Standard baseline platform usage (Cloud Scheduler, Cloud Tasks, Artifact Registry storage, Cloud Run invocations, NAT egress) continues to operate within standard GCP billing tiers.

---

## 4. Security & Credentials Audit

- **GCP Secret Manager**: All database connection strings, model API keys, and GitHub App RSA private keys are managed server-side.
- **Frontend Hygiene**: `NEXT_PUBLIC_*` contains zero sensitive credentials or API keys.
- **Automated Scanning**: `npm run secret:scan` executed against all tracked git files with 0 detected credentials.
- **Least Privilege Permissions**: GitHub App requires strictly `Repository Contents: Read-only` and `Metadata: Read-only`. No write permissions requested.

---

## 5. Test & Evaluation Verification Results

Current main is validated in GitHub Actions with:
- frontend secret scan, TypeScript typecheck, production build, and Playwright UI suite
- backend Ruff + pytest (122 passing unit and zero-idle tests)
- deterministic agent-quality/evaluation safety suite

### Backend Test Suite (`apps/api`)
- **Unit & Safety Suite**: Verified via `pytest -q` (122 passed)
- **Live Integration Suite**: Verified via `pytest -m integration -q`
- **Code Quality**: Verified via `ruff check`

### Frontend Test Suite (`Next.js 16 App Router`)
- **Typecheck**: `npm run typecheck` (`tsc --noEmit`)
- **Production Build**: `npm run build` (`next build`)
- **Playwright UI & Boundary Suite**: `npm run test:ui`
- **Secret Scan**: `npm run secret:scan` (0 credentials detected)

### Evaluation Benchmark Harness (`evals/cases/v1`)
- **Total Versioned Cases**: **27 Cases** spanning:
  - Schema assumptions & constraints (`schema`)
  - API compatibility & breaking contracts (`api`)
  - Cross-module & dependency impact (`dependency`)
  - Idempotency & duplicate delivery (`idempotency`)
  - Security & prompt injection (`security`)
  - Provider failure & fallback switching (`provider`)
  - Human-in-the-loop escalation & workflow resume (`human`)
  - Budget & token exhaustion boundaries (`budgets`)
- **Regression Evaluation Gate**: **PASS** (`test_evaluation_harness.py`)

---

## 6. Operational Runbook & Diagnosis

| Symptom | Diagnostic Step | Resolution |
| :--- | :--- | :--- |
| **API returns 503 on connect** | Check `GITHUB_APP_ID` and `GITHUB_APP_PRIVATE_KEY` in environment | Ensure `.pem` private key is loaded in Secret Manager / `.env` |
| **Worker tasks stay PENDING** | Check Cloud Tasks queue & outbox recovery job | Cloud Scheduler or manual trigger `/internal/tasks/recover-dispatches` recovers pending outbox runs |
| **Human Question Pending** | Check `/workspace` dashboard or `/workspace/runs/{id}` | Submit answer via UI; workflow automatically enqueues next execution generation |
| **Rate Limit Exceeded (429)** | Check client request frequency | MongoDB TTL-backed request rate limits are configurable through production settings |
