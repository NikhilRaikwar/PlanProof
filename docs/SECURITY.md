# Security boundaries

## Trust model

Repository URLs, filenames, source text, READMEs, model output, and human browser input are untrusted. PlanProof connects via an official GitHub App with least-privilege read-only permissions (or canonical public GitHub HTTPS URLs) and materializes repositories in controlled temporary workspaces.

The ingestion and tool layers enforce normalized snapshot-relative paths, reject traversal and absolute paths, exclude symlink escape/binary/oversized/generated content, and never allow model-proposed shell execution.

## Evidence authority

Evidence is issued only by server code after a successful tool run. It must bind snapshot, tool run, relative path/range, content hash, evidence type, and timestamp. Invented IDs, stale hashes, failed tool runs, invalid ranges, and cross-snapshot provenance are rejected.

## Operational controls

- Request payload size and Redis-backed rate-limit boundaries are configurable.
- CORS uses an explicit `PLANPROOF_WEB_ORIGINS` allowlist; credentials are not enabled.
- API/model/Mongo/Redis credentials remain server-side Secret Manager values in production. `NEXT_PUBLIC_*` may contain only the public API URL.
- Readiness checks MongoDB indexes and Redis; liveness never depends on external services.
- Logs and events contain safe summaries and correlation IDs, never full prompts, repository files, or secrets.

## Atlas and GCP

Atlas remains the canonical database. Deployment must use restricted application credentials and a narrow network policy; do not add `0.0.0.0/0` just to make Cloud Run work. Secret Manager references are injected into Cloud Run/worker runtime, never baked into images or committed.
