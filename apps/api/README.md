# PlanProof API

The FastAPI service owns authoritative state, validation, persistence, and job creation.

It deliberately does **not** execute verification workflows inside request handlers. Workers will be
introduced in the next milestone after the project/snapshot/run persistence contracts are stable.

## Local setup

1. Fill `MONGODB_URI` in the repository-root `.env`. Do not commit that file.
2. From this directory, run `uv sync --all-groups`.
3. Run `uv run uvicorn app.main:app --reload --port 8000`.
4. Open `/docs`, `/health/live`, and `/health/ready`.

`/health/live` proves the process is running. `/health/ready` checks MongoDB and returns `503` when
the database is not configured or cannot be reached; this is intentional safe behavior.
