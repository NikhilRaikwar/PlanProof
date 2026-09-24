# Security Architecture and Beta Hardening

## 1. Threat Model & Trust Boundaries

All external inputs are treated as untrusted:
- Repository URLs, branch refs, directory structures, filenames, source code, commit metadata, and documentation.
- LLM provider outputs (which may only propose typed actions; deterministic server-side code authorizes tool execution, path normalization, evidence generation, and Plan Gate evaluation).
- Browser input, cookies, headers, and request bodies.

PlanProof does not claim to be "fully secure" or "DDoS-proof." Security hardening provides multi-layered defenses to prevent unauthorized resource access, tenant data leakage, unbounded compute/model spend, and code execution.

---

## 2. Authentication & Identity Binding

- **Fail-Closed Session Requirement**: All product endpoints (`/v1/projects`, `/v1/snapshots`, `/v1/verification-runs`, `/v1/proof-obligations`, `/v1/evidence`, `/v1/human-questions`) require an authenticated server-issued session cookie (`planproof_session`). Anonymous requests return `401 Unauthorized`.
- **GitHub App User OAuth Verification**: In production (`PLANPROOF_ENV=production`), authentication requires GitHub user OAuth code exchange. The server verifies the user's identity via GitHub API (`/user`) and confirms that the authenticated user possesses access to the selected installation (`/user/installations/{installation_id}/repositories`). Missing OAuth credentials or unverified users fail closed with `400/401/403`.
- **Atomic Nonce Defense**: Auth connection state nonces are inserted atomically into `used_auth_nonces` guarded by a unique index (`{ nonce: 1 }, unique=True`) and a BSON datetime TTL index (`{ expires_at: 1 }, expireAfterSeconds=0`). Replay attempts trigger `DuplicateKeyError` and are rejected with `400 Bad Request`.
- **Server-Derived Authority**: Resource ownership (`owner_id`, `actor_id`) is derived strictly from the verified server session, ignoring client-supplied ownership fields.

---

## 3. Strict Tenant Isolation

- **Zero Metadata Leakage**: Accessing another tenant's project, snapshot, run, obligation, or question returns `404 Not Found` (never 200 or 403) to prevent resource enumeration.
- **Tenant-Scoped Idempotency**: Verification run idempotency keys are compound-indexed with `project_id` (`[("project_id", 1), ("idempotency_key", 1)], unique=True, sparse=True`). Cross-tenant idempotency collisions are impossible.

---

## 4. Public Beta Quotas & Cost Controls

- **Canonical Quota Buckets**: Multi-period quotas are stored in `account_quotas` with a compound unique index `[("scope_type", 1), ("scope_id", 1), ("quota_type", 1), ("period_start", 1)]`.
  - Account Daily Runs: `ACCOUNT / <id> / RUN_DAILY / <YYYY-MM-DD>` (Max 3/day)
  - Account Monthly Runs: `ACCOUNT / <id> / RUN_MONTHLY / <YYYY-MM-01>` (Max 10/month)
  - Global Daily Runs: `GLOBAL / global / GLOBAL_RUN_DAILY / <YYYY-MM-DD>` (Max 30/day)
  - Daily Snapshots: `ACCOUNT / <id> / SNAPSHOT_DAILY / <YYYY-MM-DD>` (Max 5/day)
  - Projects Per Account: `ACCOUNT / <id> / PROJECT_CREATIONS_TOTAL / permanent` (Max 3 lifetime beta creations)
- **Concurrency-Safe Atomic Increments**: Quotas are incremented atomically via MongoDB transactions or conditional updates (`count < limit`). Exceeding requests receive `429 Too Many Requests` with a `Retry-After` header.
- **Idempotency-First Evaluation**: Idempotent duplicate requests return the existing run without consuming quota.
- **Quota Rollback**: If a run fails pre-enqueue persistence due to infrastructure errors, reserved quota buckets are automatically rolled back.

---

## 5. Active Concurrency Leases & Crash Recovery

- **Active Worker Reservation**: Concurrent active runs are capped at 1 per account and 1 per project via `active_reservations` (`RUN_ACCOUNT:<login>`, `RUN_PROJECT:<id>`).
- **HUMAN_WAIT Slot Release**: When a verification run pauses waiting for human input (`HUMAN_WAIT`), the active worker compute slot is released. When human authority answers the question, the compute slot is reacquired before re-queueing.
- **Worker Crash Recovery**: Active reservations carry a TTL (`expires_at`), are protected by lease-owner fencing, and are automatically reconciled on terminal states (`COMPLETE`, `BLOCKED`, `INCONCLUSIVE`, `FAILED`, `HUMAN_WAIT`).
- **Active Heartbeat**: Long-running executions periodically renew the lease using their unique `lease_owner` identity.

---

## 6. Model Budget & Gateway Boundary

- **Centralized Provider Gateway**: All model invocations route through `ProviderGateway.complete`, which authoritatively tracks `model_call_count`, `provider_attempts`, `prompt_tokens`, and `completion_tokens`.
- **Hard Run Budget**: A hard ceiling of 3 logical model operations (`verification_max_model_calls=3`) and a hard cost bound of 6 outbound HTTP attempts (`planproof_max_provider_attempts_per_run=6`) prevents runaway spend.
- **Output Token Cap**: All completions specify `max_tokens` (default 3000) to prevent model token runaway.

---

## 7. Ingestion Resource Boundaries & Git Credential Protection

- **Streaming Limits**: Ingestion aborts early during processing if repository limits are exceeded:
  - Max Workspace Size: 200 MB disk limit during clone.
  - Max Manifest Entries: 10,000 files.
  - Max Indexable Files: 2,000 files.
  - Max Indexed Bytes: 15 MB in MongoDB.
- **Process-Local Credential Protection**: Temporary GitHub installation tokens are never passed on the command line (`http.extraHeader` in `argv`). A temporary `GIT_ASKPASS` helper script reads credentials from process environment variables and is cleaned up in a `finally:` block.

---

## 8. Network & HTTP Boundaries

- **CSRF Defense**: Mutating requests (`POST`, `PUT`, `PATCH`, `DELETE`) require a trusted `Origin` in `PLANPROOF_WEB_ORIGINS`. Cookie-authenticated mutations with missing or untrusted `Origin`/`Referer` return `403 Forbidden`.
- **Bounded Request Bodies**: Payloads exceeding `max_request_bytes` (1 MB) return `413 Payload Too Large`.
- **Security Headers**: All responses include `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`, and HSTS in production.
- **Debug Routes Disabled**: `/v1/tools/execute` and `/v1/plan-versions/{id}/extract-obligations` return 404 in production.

---

## 9. Remaining Known Risks & Follow-Up Items

1. **Subprocess Sandboxing**: Git and AST parsing operate in containerized runtime. High-assurance multi-tenancy should adopt gVisor sandbox container boundaries.
2. **Cloud Tasks OIDC Identity Verification**: Internal task execution requires Google-signed OIDC bearer tokens strictly validating the audience `PLANPROOF_WORKER_SERVICE_URL` and authorized service account email.
3. **Third-Party Cookie Policies**: SameSite=None requires custom domain alignment (`api.planproof...` and `app.planproof...`) to ensure reliable Safari ITP compatibility.
