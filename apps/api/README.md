# PlanProof API

The FastAPI service owns request validation, project/snapshot/run APIs, authoritative persistence boundaries, health/readiness, GitHub integration, and verification job creation.

Verification workflows do not execute inside HTTP request handlers.

POSTed verification work is queued through Google Cloud Tasks and processed asynchronously by the scale-to-zero Cloud Run worker service.

MongoDB Atlas is the canonical application state store and handles rate limits and concurrency reservations atomically with zero idle compute.

## Local Setup

1. Fill `MONGODB_URI` and API keys in the repository-root `.env`. Do not commit that file.
2. From this directory, run `uv sync --all-groups`.
3. Run the API: `PLANPROOF_RUNTIME_ROLE=api uv run uvicorn app.main:app --reload --port 8000`.
4. Open `/docs`, `/health/live`, and `/health/ready`.

`/health/live` proves the process is running. `/health/ready` checks MongoDB readiness and returns `503` when dependencies are not configured or cannot be reached; this is intentional safe behavior.
