# PlanProof

> **Engineering plans are hypotheses. PlanProof tests them before agents build them.**

PlanProof is pre-flight verification infrastructure for AI-generated engineering plans. It binds a candidate plan to an immutable repository snapshot, extracts testable proof obligations, gathers bounded repository evidence, and applies deterministic policy before allowing execution.

The core rule is simple: **the model proposes; deterministic code authorizes.**

---

## Key Capabilities

- **GitHub App & Private/Public Repository Ingestion**:
  - Secure GitHub App connection (`PlanProof Verification`, App ID: `5023064`) with least-privilege permissions (**Repository Contents: Read-only**, **Metadata: Read-only**).
  - Queries granted repositories, branch refs, and resolves branch HEAD to exact immutable commit SHAs.
  - Fallback support for public HTTPS GitHub repositories and explicitly labelled deterministic demo fixtures.
- **Immutable Codebase Snapshots & AST Symbol Indexing**:
  - SHA-bound snapshots, cryptographic content hashes, symbol extraction (classes, functions, types, imports), and bounded snapshot-scoped tools.
- **Server-Issued Evidence Authority**:
  - Evidence is issued exclusively by backend code from successful deterministic tool runs, binding snapshot identity, tool run ID, relative path/range, and content hash provenance.
  - Rejects model-invented evidence, cross-snapshot pollution, stale hashes, or invalid ranges.
- **Server-Managed Model Gateway**:
  - Provider-neutral gateway with OpenRouter primary and AIMLAPI fallback managed entirely on the server.
  - User model keys are never requested or exposed client-side.
- **Durable Asynchronous Verification Engine**:
  - Single-orchestrator LangGraph state machine executed via Redis/Dramatiq workers and persisted to MongoDB Atlas.
  - Enforces strict budgets (max iterations, tool calls, model calls, context byte limits).
  - Deterministic final gates: `VERIFIED_FOR_EXECUTION`, `BLOCKED`, `HUMAN_DECISION_REQUIRED`, `INCONCLUSIVE`, or `FAILED`.
- **Human-in-the-Loop (HITL) Authority Boundary**:
  - Emits `HUMAN_REQUIRED` when repository code lacks authority (e.g. cross-service client contracts, operational business policies).
  - Persists questions, accepts human decisions, and resumes the workflow without erasing unrelated counter-evidence.
- **Live Next.js 16 Workspace Dashboard**:
  - Real GitHub user session display (`@username`), snapshot readiness cards, granted repository listings, branch selector, recent runs, and interactive decision banners.
- **Versioned Evaluation Suite**:
  - 27 versioned evaluation cases in `evals/cases/v1` with explicit regression gating (`PASS`, `REGRESSION`, `INSUFFICIENT_DATA`).

---

## Deliberate Engineering Decisions

### Why a Single Orchestrator (Not a Multi-Agent Swarm)?
PlanProof uses a single durable LangGraph state machine rather than an unconstrained multi-agent swarm:
1. **Causal Traceability**: Every obligation transition, tool run, and evidence item is sequentially traceable to a single execution graph.
2. **Coordination Overhead**: Multi-agent swarms introduce compounding token costs, nondeterministic consensus loops, and unexplainable failure modes.
3. **Deterministic Authority**: In verification, known facts are resolved by deterministic AST tools and validators before any model is invoked.

### Why AST / Symbol Indexing (Not Premature Vector RAG)?
1. **Exact Codebase Truth**: Code verification requires exact symbol definitions, type signatures, and file line ranges. Vector similarity search frequently retrieves false-positive matches that lack structural authority.
2. **Deterministic Provenance**: Evidence hashes must be cryptographically verifiable against exact lines in immutable commit snapshots.
3. *Note*: Semantic embeddings remain an optional future extension if controlled evaluations demonstrate retrieval recall gaps.

---

## Architecture

```text
Next.js 16 Workspace UI (App Router)
  └──> FastAPI Backend (/v1)
        ├──> GitHub App Auth (RS256 JWT, installation tokens, branch SHA resolution)
        ├──> MongoDB Atlas (14 collections: projects, snapshots, runs, evidence, symbols, etc.)
        ├──> Redis + Dramatiq Worker Pool (Asynchronous verification jobs)
        └──> LangGraph Verification Engine
              ├──> Deterministic AST Validators & Symbol Tools
              ├──> Server-Issued Evidence Authority
              ├──> Server-Side Model Gateway (OpenRouter -> AIMLAPI fallback)
              └──> Deterministic Gate Policy + Human-in-the-Loop Resumption
```

---

## Repository Structure

```text
├── app/                  # Next.js 16 App Router (Landing, /workspace, /runs, /evidence)
├── apps/api/             # FastAPI Backend Service
│   ├── app/api/          # API Routers (github, projects, snapshots, verification, workflow, evals)
│   ├── app/core/         # Settings & Runtime Configuration
│   ├── app/db/           # MongoDB Atlas & Redis Managers, Collection Indexes
│   ├── app/domain/       # Pydantic Domain Entities (Runs, Obligations, Evidence, Projects)
│   ├── app/ingestion/    # Codebase Ingestion, AST Parsers, Symbol Extractors
│   ├── app/workflow/     # LangGraph Verification Graph, Dramatiq Worker Tasks
│   └── tests/            # 59 Comprehensive Backend Tests (Unit + Integration)
├── components/           # Polished Cream/Light Design System Components
├── evals/                # 27 Versioned Evaluation Cases (evals/cases/v1)
├── docs/                 # Architecture, Security, Evaluations, GCP Deployment, Demo Script
└── tests/                # Playwright End-to-End & UI Verification Suites
```

---

## Local Development & Testing

### Prerequisites
- Node.js 22+, Python 3.11–3.13, Docker (for local Redis), Git.
- Local `.env` configured from `.env.example`.

### Running Locally

```bash
# 1. Start Redis
docker compose up -d redis

# 2. Run Backend API
cd apps/api
uv sync --all-groups
uv run uvicorn app.main:app --reload --port 8000

# 3. Run Worker (in separate terminal)
cd apps/api
uv run dramatiq app.workflow.worker

# 4. Run Frontend (in separate terminal)
npm ci
npm run dev
```

### Running Test Suites

```bash
# Frontend quality checks
npm run secret:scan      # Scan tracked files for leaked credentials
npm run typecheck        # TypeScript strict verification
npm run build            # Next.js 16 production build verification
npm run test:ui          # Playwright UI & state isolation tests

# Backend test suite (48 unit + 11 Atlas/Redis integration)
cd apps/api
uv run ruff check app tests
uv run pytest -q

# Evaluation harness & regression checks
uv run pytest tests/test_evaluation_harness.py -q
```

---

## Production Deployment

PlanProof is deployed on **Google Cloud Platform (GCP)** in `asia-south1` under project `planproof-ai`:
- **Web UI**: Cloud Run service `planproof-web`
- **Authoritative API**: Cloud Run service `planproof-api`
- **Database**: MongoDB Atlas (`planproofapp`)
- **Queue/Cache**: Cloud Redis / Memorystore
- **Secrets**: GCP Secret Manager (Zero secrets in client bundles or git repository)

See [docs/DEPLOYMENT_GCP.md](docs/DEPLOYMENT_GCP.md) and [docs/production-readiness.md](docs/production-readiness.md) for runbooks and validation results.

---

## Security & Compliance

- **No Secret Transmission**: All LLM provider keys and GitHub private keys are stored securely server-side.
- **Least Privilege**: GitHub App requests strictly read-only repository contents.
- **Strict Boundary Isolation**: Test/E2E records are scoped and isolated from normal user workspaces.
- **Automated Secret Scanning**: Pre-commit / CI script (`scripts/secret-scan.mjs`) ensures no credentials enter version control.
