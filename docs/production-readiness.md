# PlanProof Production Readiness & Audit Report

**Audit Date**: September 2026  
**Infrastructure Project**: `planproof-ai` (GCP Region: `asia-south1`)  
**Repository**: `NikhilRaikwar/PlanProof`  

---

## 1. Production Health & Service Checklist

| Component | Target Resource | Status | Verification Evidence |
| :--- | :--- | :--- | :--- |
| **Web Service** | Cloud Run: `planproof-web` | **READY** | `https://planproof-web-530622821497.asia-south1.run.app` |
| **API Service** | Cloud Run: `planproof-api` | **READY** | `https://planproof-api-530622821497.asia-south1.run.app` |
| **Health Probe** | `/health/ready` | **HEALTHY** | Returns `{"status":"ok","mongo":"ok","redis":"ok"}` |
| **Database** | MongoDB Atlas (`planproofapp`) | **HEALTHY** | 14 collections with unique & compound indexes verified |
| **Queue / Cache** | Memorystore / Redis | **HEALTHY** | Task delivery, rate limiting, and deduplication verified |
| **GitHub App** | `PlanProof Verification` (`5023064`) | **AUTHENTICATED**| Live verified for `@NikhilRaikwar` (Installation ID: `163541413`) |
| **Model Gateway** | OpenRouter (Primary) / AIMLAPI (Fallback) | **ACTIVE** | Server-side credentials, structured output validation |

---

## 2. Security & Credentials Audit

- **GCP Secret Manager**: All database connection strings, model API keys, and GitHub App RSA private keys are managed server-side.
- **Frontend Hygiene**: `NEXT_PUBLIC_*` contains zero sensitive credentials or API keys.
- **Automated Scanning**: `npm run secret:scan` executed against all tracked git files with 0 detected credentials.
- **Least Privilege Permissions**: GitHub App requires strictly `Repository Contents: Read-only` and `Metadata: Read-only`. No write permissions requested.

---

## 3. Test & Evaluation Verification Results

### Backend Test Suite (`apps/api`)
- **Unit & Deterministic Suite**: **48 / 48 Passed** (`pytest -q`)
- **Live Integration Suite**: **11 / 11 Passed** (`pytest -m integration -q`)
- **Total Backend Coverage**: **59 / 59 Tests Passing**

### Frontend Test Suite (`Next.js 16 App Router`)
- **Typecheck**: **0 TypeScript Errors** (`npm run typecheck`)
- **Production Build**: **13 / 13 Routes Compiled & Optimized** (`npm run build`)
- **Playwright UI & Boundary Suite**: **6 / 6 Passed** (`npm run test:ui`)

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

## 4. Operational Runbook & Diagnosis

| Symptom | Diagnostic Step | Resolution |
| :--- | :--- | :--- |
| **API returns 503 on connect** | Check `GITHUB_APP_ID` and `GITHUB_APP_PRIVATE_KEY` in environment | Ensure `.pem` private key is loaded in Secret Manager / `.env` |
| **Worker tasks stay QUEUED** | Check Redis connectivity & Dramatiq worker logs | Ensure Dramatiq worker process is active and subscribed to Redis broker |
| **Human Question Pending** | Check `/workspace` dashboard or `/workspace/runs/{id}` | Submit answer via UI; workflow automatically resumes to final gate |
| **Rate Limit Exceeded (429)** | Check client request frequency | Boundaries are bounded at 300 requests/minute per client |
