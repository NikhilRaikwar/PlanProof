# PlanProof API

The FastAPI service owns request validation, project/snapshot/run APIs, authoritative persistence boundaries, health/readiness, GitHub integration, and verification job creation.

Verification workflows do not execute inside HTTP request handlers.

POSTed verification work is queued through Redis/Dramatiq and processed by the PlanProof Cloud Run Worker Pool / local Dramatiq worker.

MongoDB remains the canonical application state store.

## Local Setup

1. Fill `MONGODB_URI` and `REDIS_URL` in the repository-root `.env`. Do not commit that file.
2. From this directory, run `uv sync --all-groups`.
3. Run the API: `uv run uvicorn app.main:app --reload --port 8000`.
4. Run the worker (in a separate terminal): `uv run python -m app.workflow.worker`.
5. Open `/docs`, `/health/live`, and `/health/ready`.

`/health/live` proves the process is running. `/health/ready` checks MongoDB and Redis readiness and returns `503` when dependencies are not configured or cannot be reached; this is intentional safe behavior.
