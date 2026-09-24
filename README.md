<div align="center">

<img src="public/logodesign.png" alt="PlanProof Logo" width="580" />

# PlanProof

### *Pre-flight verification for AI-generated engineering plans.*

**PlanProof verifies an AI-generated engineering plan against an exact repository snapshot, separates proposed future actions from present-state facts, and returns an evidence-grounded advisory implementation plan before coding begins.**

[![Live Demo](https://img.shields.io/badge/Live%20Demo-planproof.nikhilraikwar.me-FF4D2E?style=for-the-badge&logo=googlecloud&logoColor=white)](https://planproof.nikhilraikwar.me)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js 16](https://img.shields.io/badge/Next.js-16.3-black?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.2+-FF4D2E?style=flat-square&logo=diagram&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![Google Cloud Run](https://img.shields.io/badge/GCP-Cloud_Run-4285F4?style=flat-square&logo=googlecloud&logoColor=white)](https://cloud.google.com/run)
[![MongoDB Atlas](https://img.shields.io/badge/MongoDB-Atlas-47A248?style=flat-square&logo=mongodb&logoColor=white)](https://www.mongodb.com/atlas)
[![Cloud Tasks](https://img.shields.io/badge/GCP-Cloud_Tasks-4285F4?style=flat-square&logo=googlecloud&logoColor=white)](https://cloud.google.com/tasks)

<p align="center">
  <strong>Engineering plans are hypotheses. PlanProof tests them before agents build them.</strong><br />
  <em>The model proposes; deterministic code authorizes.</em><br />
  <em>LLMs for ambiguity; deterministic software for authority.</em>
</p>

[**Live Web App**](https://planproof.nikhilraikwar.me) • [**Architecture**](docs/ARCHITECTURE.md) • [**Security**](docs/SECURITY.md) • [**Evaluations**](docs/EVALUATIONS.md) • [**GCP Deployment**](docs/DEPLOYMENT_GCP.md)

</div>

---

**Live Production Deployment**:
- **Branded Web UI**: [https://planproof.nikhilraikwar.me](https://planproof.nikhilraikwar.me) (Firebase CDN front door → Cloud Run `asia-south1`)
- **Authoritative API**: [https://planproof-api-lfrrer4z6q-el.a.run.app](https://planproof-api-lfrrer4z6q-el.a.run.app)

**Documentation & Deep Dives**:
- [Architecture & State Machine](docs/ARCHITECTURE.md)
- [Security & Trust Boundaries](docs/SECURITY.md)
- [27-Case Evaluation Harness](docs/EVALUATIONS.md)
- [Google Cloud Production Deployment](docs/DEPLOYMENT_GCP.md)
- [Demo Walkthrough](docs/DEMO.md)
- [Production Readiness Audit](docs/production-readiness.md)

---

## Table of Contents

1. [The Problem](#the-problem)
2. [What PlanProof Does](#what-planproof-does)
3. [Core Architecture & Diagrams](#core-architecture--diagrams)
   - [Diagram 1: Product Verification Flow](#diagram-1-product-verification-flow)
   - [Diagram 2: Verification Agent Loop](#diagram-2-verification-agent-loop)
   - [Diagram 3: Production GCP Topology](#diagram-3-production-gcp-topology)
   - [Diagram 4: Durable State Machine & HITL](#diagram-4-durable-state-machine--hitl)
4. [Why This Is an Agent System, Not an API Wrapper](#why-this-is-an-agent-system-not-an-api-wrapper)
5. [Model vs. Deterministic Authority](#model-vs-deterministic-authority)
6. [Server-Issued Evidence Authority](#server-issued-evidence-authority)
7. [Deterministic Repository Tools](#deterministic-repository-tools)
8. [Key Architectural Decisions](#key-architectural-decisions)
   - [Why One Orchestrator (Not a Multi-Agent Swarm)](#why-one-orchestrator-not-a-multi-agent-swarm)
   - [Why Indexed Symbols + Exact Source Evidence (Not Premature Vector RAG)](#why-indexed-symbols--exact-source-evidence-not-premature-vector-rag)
9. [Durable Memory & Persistence Model](#durable-memory--persistence-model)
10. [Human-in-the-Loop (HITL) as an Authority Boundary](#human-in-the-loop-hitl-as-an-authority-boundary)
11. [Failure Handling & Safety Matrix](#failure-handling--safety-matrix)
12. [GitHub App Ingestion Flow](#github-app-ingestion-flow)
13. [Real Production Proof](#real-production-proof)
14. [27-Case Versioned Evaluation Suite](#27-case-versioned-evaluation-suite)
15. [Observability & Safe Tracing](#observability--safe-tracing)
16. [Security & Isolation Model](#security--isolation-model)
17. [Tech Stack](#tech-stack)
18. [Testing Strategy](#testing-strategy)
19. [Where to Look in the Code](#where-to-look-in-the-code)
20. [Local Quickstart](#local-quickstart)
21. [Verified Test Commands](#verified-test-commands)
22. [GCP Deployment Summary](#gcp-deployment-summary)
23. [60-Second Demo](#60-second-demo)
24. [Design Tradeoffs](#design-tradeoffs)
25. [Limitations & Future Work](#limitations--future-work)

---

## The Problem

AI coding agents can generate convincing, highly detailed implementation plans that contain catastrophic false assumptions:

- **Missing Symbols**: A plan assumes a helper function, model class, or utility exists when it was renamed or deleted.
- **Schema Conflicts**: A plan assumes a database column supports a 1-to-many relationship when an explicit `unique: true` constraint forbids it.
- **Breaking API Contracts**: A plan assumes a payment endpoint accepts fractional partial refund amounts when the contract strictly requires full integers.
- **Hidden Dependency Side-effects**: A plan assumes mutating a shared module will not break consumers across other services.
- **Missing External Authority**: A plan treats an undocumented business policy or third-party client contract as a solved repository fact.

The primary risk in autonomous software engineering is not merely hallucinated syntax—**it is an agent executing at scale against a fundamentally flawed plan.**

PlanProof introduces a deterministic verification gate and evidence-grounded plan revision **before** code generation, code editing, or testing pipelines begin.

---

## What PlanProof Does

PlanProof converts unstructured engineering intent and candidate implementation plans into verifiable claims, separates proposed future actions from present-state facts, tests those claims against real source code, issues an authoritative gate policy, and generates an evidence-grounded advisory updated implementation plan:

```text
Change Request + Candidate Plan
  └──> Stable Original Plan Steps
        └──> Semantic Role Decomposition
              ├──> PROPOSED_ACTION (Preserved for revised plan synthesis; never investigated as present facts)
              ├──> CURRENT_STATE_ASSUMPTION / EXISTING_DEPENDENCY (Repository-investigated)
              ├──> CONSTRAINT (Technical repository check vs Human/Policy authority)
              └──> HUMAN_DECISION (Routes to Human Authority / HUMAN_WAIT)
                    └──> Model Investigation Proposal
                          └──> Deterministic Tool Authorization
                                └──> Immutable Snapshot Investigation (ast.parse / TS Regex / Lexical)
                                      └──> Server-Issued Evidence (Cryptographically bound)
                                            └──> Authorized Facts (Canonical present truths)
                                                  └──> Deterministic Plan Gate (COMPLETE / BLOCKED / INCONCLUSIVE / HUMAN_DECISION_REQUIRED)
                                                        └──> Evidence-Grounded Advisory Updated Implementation Plan
```

### Semantic Role Boundaries

- **`PROPOSED_ACTION`**: Preserved strictly for revised-plan synthesis; never sent to proof tools or verified as an already-existing repository fact.
- **`CURRENT_STATE_ASSUMPTION`** & **`EXISTING_DEPENDENCY`**: Investigated deterministically against the immutable snapshot.
- **`HUMAN_DECISION`**: Routes to human authority workflow (`HUMAN_REQUIRED` / `HUMAN_WAIT`).
- **`CONSTRAINT`**: Classified into technical repository-verifiable constraints vs business/external policy authority.

---

## Core Architecture & Diagrams

### Diagram 1: Product Verification Flow

The end-to-end verification lifecycle strictly separates non-authoritative LLM proposals from deterministic software authority:

```mermaid
flowchart TD
  subgraph Ingestion["1. Immutable Ingestion"]
    Repo[GitHub Repository Ref] --> SHA[Resolve Commit SHA]
    SHA --> Snapshot[(Immutable Snapshot: Hashed Files + Symbols)]
  end

  subgraph Extraction["2. Semantic Role Decomposition"]
    Plan[Candidate Plan + Change Request] --> LLMExtract[LLM Structured Claim Proposal]
    LLMExtract --> ValidateRoles[Server Pydantic Validation & Role Routing]
    ValidateRoles --> RoleCurrent[CURRENT_STATE_ASSUMPTION / EXISTING_DEPENDENCY]
    ValidateRoles --> RoleAction[PROPOSED_ACTION: Preserved for Synthesis]
    ValidateRoles --> RoleConstraint[CONSTRAINT: Technical vs Human Policy]
    ValidateRoles --> RoleHuman[HUMAN_DECISION: Human Authority]
  end

  subgraph Investigation["3. Bounded Investigation"]
    RoleCurrent --> InvProp[Model Investigation Proposal]
    RoleConstraint -->|Technical| InvProp
    InvProp --> AuthTool[Deterministic Tool Authorization]
    AuthTool --> RepTools[Snapshot Tools: ast.parse / TS Regex / Lexical Search]
    Snapshot --> RepTools
    RepTools --> ToolRun[(Audited Tool Run)]
    ToolRun --> SufficiencyCheck{Deterministic Evidence Sufficiency}
    SufficiencyCheck -->|Sufficient| EvidenceIssuer[Server Evidence Authority: Content Hash Verification]
    SufficiencyCheck -->|Insufficient / Unrelated| InconclusiveCheck[Budget / Safe Abstention]
    EvidenceIssuer --> Evidence[(Server-Issued Evidence)]
  end

  subgraph AuthorityGate["4. Authority, Facts & Final Plan Gate"]
    Evidence --> PolicyCheck[Deterministic Status Policy]
    InconclusiveCheck --> PolicyCheck
    RoleHuman --> HumanWait[HUMAN_WAIT: Workflow Pauses]
    RoleConstraint -->|Business Policy| HumanWait
    HumanWait --> HumanInput[Human Submits Decision]
    HumanInput --> PolicyCheck
    PolicyCheck --> FinalGate{Deterministic Gate Evaluator}
    FinalGate -->|Counter-Evidence| Blocked[BLOCKED]
    FinalGate -->|Evidence Satisfied| Complete[COMPLETE]
    FinalGate -->|Ambiguous / Budget Limit| Inconclusive[INCONCLUSIVE]
    FinalGate -->|Awaiting Decision| HumanGate[HUMAN_DECISION_REQUIRED]
    PolicyCheck --> Facts[(Server-Issued Authorized Facts)]
  end

  subgraph Synthesis["5. Evidence-Grounded Plan Revision"]
    Facts --> SynthEngine[Advisory Plan Revision Engine]
    RoleAction --> SynthEngine
    SynthEngine --> InvariantCheck{Server Fact Citation & Absence Invariant Check}
    InvariantCheck --> AdvisoryPlan[Evidence-Grounded Advisory Updated Implementation Plan]
  end

  style Repo fill:#f8fafc,stroke:#64748b,stroke-width:1.5px,color:#0f172a
  style SHA fill:#f0fdf4,stroke:#16a34a,stroke-width:1.5px,color:#14532d
  style Snapshot fill:#f0fdf4,stroke:#16a34a,stroke-width:2px,color:#14532d
  style Plan fill:#f8fafc,stroke:#64748b,stroke-width:1.5px,color:#0f172a
  style LLMExtract fill:#fff1eb,stroke:#ff4d2e,stroke-width:2px,color:#9a1c00
  style ValidateRoles fill:#f0f9ff,stroke:#0284c7,stroke-width:2px,color:#0369a1
  style RoleCurrent fill:#f8fafc,stroke:#64748b,stroke-width:1.5px,color:#0f172a
  style RoleAction fill:#fdf4ff,stroke:#c084fc,stroke-width:1.5px,color:#6b21a8
  style RoleConstraint fill:#f8fafc,stroke:#64748b,stroke-width:1.5px,color:#0f172a
  style RoleHuman fill:#fffbeb,stroke:#d97706,stroke-width:1.5px,color:#78350f
  style InvProp fill:#fff1eb,stroke:#ff4d2e,stroke-width:1.5px,color:#9a1c00
  style AuthTool fill:#f0f9ff,stroke:#0284c7,stroke-width:2px,color:#0369a1
  style RepTools fill:#f0f9ff,stroke:#0284c7,stroke-width:1.5px,color:#0369a1
  style ToolRun fill:#f8fafc,stroke:#64748b,stroke-width:1.5px,color:#0f172a
  style SufficiencyCheck fill:#f0f9ff,stroke:#0284c7,stroke-width:1.5px,color:#0369a1
  style EvidenceIssuer fill:#f0f9ff,stroke:#0284c7,stroke-width:2px,color:#0369a1
  style Evidence fill:#f0fdf4,stroke:#16a34a,stroke-width:2px,color:#14532d
  style InconclusiveCheck fill:#f8fafc,stroke:#64748b,stroke-width:1.5px,color:#475569
  style PolicyCheck fill:#f0f9ff,stroke:#0284c7,stroke-width:2px,color:#0369a1
  style FinalGate fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#f8fafe
  style HumanWait fill:#fffbeb,stroke:#d97706,stroke-width:2px,color:#78350f
  style HumanInput fill:#fffbeb,stroke:#d97706,stroke-width:1.5px,color:#78350f
  style Blocked fill:#fef2f2,stroke:#dc2626,stroke-width:2px,color:#7f1d1d
  style Complete fill:#f0fdf4,stroke:#16a34a,stroke-width:2px,color:#14532d
  style Inconclusive fill:#f8fafc,stroke:#64748b,stroke-width:2px,color:#475569
  style HumanGate fill:#fffbeb,stroke:#d97706,stroke-width:2px,color:#78350f
  style Facts fill:#f0fdf4,stroke:#16a34a,stroke-width:2px,color:#14532d
  style SynthEngine fill:#fff1eb,stroke:#ff4d2e,stroke-width:1.5px,color:#9a1c00
  style InvariantCheck fill:#f0f9ff,stroke:#0284c7,stroke-width:2px,color:#0369a1
  style AdvisoryPlan fill:#e0f2fe,stroke:#0284c7,stroke-width:2px,color:#0369a1
```

---

### Diagram 2: Verification Agent Loop

PlanProof runs a bounded state loop. The model never loops indefinitely, cannot produce chain-of-thought tokens into durable storage, and cannot fabricate evidence:

```mermaid
flowchart TD
  Start([Next Pending Obligation]) --> CheckRole{Semantic Role Check}
  CheckRole -->|PROPOSED_ACTION| ActionPreserve[Preserve for Synthesis / No Tool Run]
  CheckRole -->|HUMAN_DECISION| HumanState[Emit HUMAN_REQUIRED / Persist Question]
  CheckRole -->|CURRENT_STATE / DEPENDENCY| CheckBudget{Within Investigation Budget?}

  CheckBudget -->|Budget Exhausted| InconclusiveState[Mark INCONCLUSIVE: Safe Abstention]
  CheckBudget -->|Within Budget| InvProposal[Model Proposes Investigation Action]

  InvProposal --> AuthTool[Deterministic Server Authorizes Tool & Range]
  AuthTool --> ExecuteTool[Execute Snapshot Tools: ast.parse / TS Regex / Lexical]
  ExecuteTool --> RecordToolRun[(Persist Tool Run + Latency + Input Hash)]

  RecordToolRun --> CheckToolStatus{Tool Succeeded?}
  CheckToolStatus -->|Failed| ToolFailEvent[Record Tool Run Status / No Evidence]
  ToolFailEvent --> BoundedLoop[Next Obligation / Query]

  CheckToolStatus -->|Succeeded| FetchSnippet[Fetch Real Source Snippet from Immutable Snapshot]
  FetchSnippet --> CheckSufficiency{Evidence Relevance & Sufficiency Check}

  CheckSufficiency -->|Insufficient| BoundedLoop
  CheckSufficiency -->|Sufficient| IssueEvidence[Server EvidenceAuthority: Issue Source Range]

  IssueEvidence --> ValidateProvenance{Verify Exact File Content SHA-256}
  ValidateProvenance -->|Stale / Mismatched Hash| DropEvidence[Reject Evidence]
  DropEvidence --> BoundedLoop

  ValidateProvenance -->|Verified Provenance| ApplyPolicy{Deterministic Policy}
  ApplyPolicy -->|Contradiction Discovered| Disproved[Mark DISPROVED]
  ApplyPolicy -->|Fact Proved| Verified[Mark VERIFIED]
  ApplyPolicy -->|Inconclusive| InconclusiveState

  style Start fill:#e0f2fe,stroke:#0284c7,stroke-width:2px,color:#0369a1
  style CheckRole fill:#f0f9ff,stroke:#0284c7,stroke-width:1.5px,color:#0369a1
  style ActionPreserve fill:#fdf4ff,stroke:#c084fc,stroke-width:1.5px,color:#6b21a8
  style CheckBudget fill:#f0f9ff,stroke:#0284c7,stroke-width:1.5px,color:#0369a1
  style InvProposal fill:#fff1eb,stroke:#ff4d2e,stroke-width:1.5px,color:#9a1c00
  style AuthTool fill:#f0f9ff,stroke:#0284c7,stroke-width:2px,color:#0369a1
  style ExecuteTool fill:#f0f9ff,stroke:#0284c7,stroke-width:1.5px,color:#0369a1
  style RecordToolRun fill:#f8fafc,stroke:#64748b,stroke-width:1.5px,color:#0f172a
  style CheckToolStatus fill:#f0f9ff,stroke:#0284c7,stroke-width:1.5px,color:#0369a1
  style FetchSnippet fill:#f0f9ff,stroke:#0284c7,stroke-width:1.5px,color:#0369a1
  style CheckSufficiency fill:#f0f9ff,stroke:#0284c7,stroke-width:2px,color:#0369a1
  style IssueEvidence fill:#f0f9ff,stroke:#0284c7,stroke-width:2px,color:#0369a1
  style ValidateProvenance fill:#f0f9ff,stroke:#0284c7,stroke-width:1.5px,color:#0369a1
  style ApplyPolicy fill:#f0f9ff,stroke:#0284c7,stroke-width:2px,color:#0369a1
  style HumanState fill:#fffbeb,stroke:#d97706,stroke-width:2px,color:#78350f
  style Disproved fill:#fef2f2,stroke:#dc2626,stroke-width:2px,color:#7f1d1d
  style Verified fill:#f0fdf4,stroke:#16a34a,stroke-width:2px,color:#14532d
  style InconclusiveState fill:#f8fafc,stroke:#64748b,stroke-width:2px,color:#475569
  style DropEvidence fill:#fef2f2,stroke:#dc2626,stroke-width:1.5px,color:#7f1d1d
  style ToolFailEvent fill:#f8fafc,stroke:#64748b,stroke-width:1.5px,color:#475569
  style BoundedLoop fill:#f8fafc,stroke:#64748b,stroke-width:1.5px,color:#475569
```

---

### Diagram 3: Production GCP Topology

PlanProof is deployed in **Google Cloud Platform (GCP)** region `asia-south1` (Mumbai) under project `planproof-ai` with a **Zero-Idle Serverless Architecture**:

```mermaid
flowchart LR
  subgraph Clients["Clients"]
    User[Developer Browser]
    GitHub[GitHub App API]
  end

  subgraph GCP["Google Cloud Platform (asia-south1 / planproof-ai)"]
    Web[Cloud Run: planproof-web<br/>Scale-to-Zero]
    API[Cloud Run: planproof-api<br/>Scale-to-Zero]
    Tasks[Cloud Tasks: planproof-verification-queue]
    Worker[Cloud Run: planproof-verification-worker<br/>Scale-to-Zero]
    Scheduler[Cloud Scheduler: recover-dispatches]
    Secrets[Secret Manager]
  end

  subgraph Database["Database"]
    Atlas[(MongoDB Atlas)]
  end

  subgraph ModelProviders["Model Providers"]
    OpenRouter[OpenRouter: Primary]
    AIMLAPI[AIMLAPI: Fallback]
  end

  User --> Web
  Web --> API
  GitHub --> API
  
  API --> Atlas
  API --> Tasks
  API -.-> Secrets

  Tasks -- OIDC Auth --> Worker
  Scheduler -- OIDC Auth --> Worker
  Worker --> Atlas
  Worker -.-> Secrets
  Worker --> OpenRouter
  OpenRouter -.->|Fallback on 5xx| AIMLAPI

  style Web fill:#e0f2fe,stroke:#0284c7,stroke-width:2px,color:#0369a1
  style API fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#f8fafc
  style Worker fill:#0f172a,stroke:#a855f7,stroke-width:2px,color:#f8fafc
  style Tasks fill:#fef2f2,stroke:#ef4444,stroke-width:2px,color:#991b1b
  style Scheduler fill:#fef9c3,stroke:#ca8a04,stroke-width:2px,color:#854d0e
  style Secrets fill:#fdf4ff,stroke:#c084fc,stroke-width:2px,color:#6b21a8
  style Atlas fill:#f0fdf4,stroke:#16a34a,stroke-width:2px,color:#14532d
  style OpenRouter fill:#fff1eb,stroke:#ff4d2e,stroke-width:2px,color:#9a1c00
  style AIMLAPI fill:#fff7ed,stroke:#ea580c,stroke-width:2px,color:#9a3412
  style User fill:#f8fafc,stroke:#64748b,stroke-width:1.5px,color:#0f172a
  style GitHub fill:#f8fafc,stroke:#24292f,stroke-width:1.5px,color:#0f172a
```

---

### Diagram 4: Durable State Machine & HITL

PlanProof handles asynchronous, long-running verification jobs without blocking server threads. Every run is fully resumable across container restarts:

```mermaid
stateDiagram-v2
  [*] --> CREATED
  CREATED --> QUEUED: Enqueued to Cloud Tasks
  QUEUED --> EXTRACTING_OBLIGATIONS: Worker claims task (OIDC)
  
  EXTRACTING_OBLIGATIONS --> VERIFYING: Obligations decomposed & saved
  EXTRACTING_OBLIGATIONS --> FAILED: Malformed payload

  VERIFYING --> HUMAN_WAIT: Authority gap detected (Draft v1 plan)
  HUMAN_WAIT --> QUEUED: Human submits decision (New generation enqueued)
  
  VERIFYING --> FINALIZING: All obligations evaluated & facts derived
  
  FINALIZING --> BLOCKED: Counter-evidence discovered
  FINALIZING --> COMPLETE: All critical obligations VERIFIED
  FINALIZING --> HUMAN_DECISION_REQUIRED: Human question unanswered
  FINALIZING --> INCONCLUSIVE: Budget exhausted / safe abstention
  FINALIZING --> FAILED: System failure

  BLOCKED --> REVISING_PLAN: Synthesize advisory updated plan
  COMPLETE --> REVISING_PLAN: Synthesize advisory updated plan
  INCONCLUSIVE --> REVISING_PLAN: Synthesize advisory updated plan
  HUMAN_DECISION_REQUIRED --> [*]
  FAILED --> [*]

  REVISING_PLAN --> [*]: Persist advisory revised plan v1/v2
```

---

## Why This Is an Agent System, Not an API Wrapper

PlanProof is not a simple `prompt -> model -> response` wrapper. It is a stateful, resilient agentic system engineered for strict correctness:

1. **Semantic Role Decomposition**: Decomposes candidate plans into structured, testable proof obligations across database schemas, API contracts, symbols, and business rules, strictly separating future proposed actions from present-state facts.
2. **Durable MongoDB-Owned Workflow State**: State transitions, obligation evaluations, authorized facts, and tool telemetry are persisted directly into MongoDB Atlas. Workflows survive worker restarts and deployments.
3. **Deterministic Bounded Repository Investigation**: Investigation queries are proposed by models and authorized deterministically by backend code, executing against immutable snapshot files with strict bounds.
4. **Server-Owned Evidence Authority**: Evidence records and cryptographic SHA-256 hashes are minted exclusively by deterministic backend code after audited tool runs.
5. **Authorized Facts Boundary**: Canonical facts represent immutable present-state truths and cannot semantically expand beyond proved propositions.
6. **Async Serverless Cloud Tasks Worker Execution**: Long-running verification runs execute asynchronously in dedicated scale-to-zero worker services via Google Cloud Tasks, decoupled from web API requests.
7. **Provider Retry & Fallback**: Automatic failover from OpenRouter to AIMLAPI prevents provider outages from breaking customer verification runs.
8. **Persisted HITL Pause + Generation Resumption**: When codebase authority is insufficient, the system pauses execution cleanly in `HUMAN_WAIT` and re-enters the graph upon human input with monotonic execution generation without losing prior findings.

---

## Model vs. Deterministic Authority

PlanProof enforces strict separation of concerns between model proposals and deterministic authority:

| Concern | Authority Status | Deterministic Owner | Enforcement Mechanism |
| :--- | :---: | :--- | :--- |
| **Claim Decomposition** | Proposal | Server Validator | Pydantic schema validation, semantic role assignment, deduplication |
| **Investigation Query Planning** | Proposal | Server Query Planner | Model proposes queries; server deterministically authorizes within budget |
| **Repository Facts** | **AUTHORITATIVE** | Deterministic Tools | Python stdlib `ast.parse`, TS/JS regex symbol extraction, exact line ranges |
| **Evidence Minting** | **AUTHORITATIVE** | `EvidenceAuthority` | Issued only on successful tool run; binds snapshot SHA, line range, and content hash |
| **Evidence Relevance / Sufficiency** | **AUTHORITATIVE** | Deterministic Evaluator | Validates real source snippet against atomic proposition before issuing evidence |
| **Authorized Facts (`AuthorizedFact`)** | **AUTHORITATIVE** | Server Fact Engine | Canonical facts derived strictly from `VERIFIED`/`DISPROVED` evidence or human decisions; **cannot semantically expand beyond proved proposition** |
| **Snapshot Identity** | **AUTHORITATIVE** | Backend Ingestion | Project-scoped immutable Git commit SHA resolution |
| **Investigation Budgets** | **AUTHORITATIVE** | Runtime Settings | Hard limits on iterations, tool calls, model calls, and context bytes |
| **Obligation Status** | **AUTHORITATIVE** | Deterministic Policy | Rule-based evaluator assigns `VERIFIED`, `DISPROVED`, `INCONCLUSIVE`, or `HUMAN_REQUIRED` |
| **Final Plan Gate** | **AUTHORITATIVE** | Gate Policy Evaluator | Deterministic state machine computes `COMPLETE`, `BLOCKED`, `INCONCLUSIVE`, or `HUMAN_DECISION_REQUIRED` |
| **Business / Intent Authority** | **AUTHORITATIVE** | Human Stakeholder | Persisted human decision record resumes workflow |
| **Updated Implementation Plan** | **ADVISORY** | Plan Revision Engine | Evidence-grounded advisory model output validated by server against authorized facts |

### Clearly Distinguished Outcome Taxonomy

- **Obligation Outcomes**:
  - `VERIFIED`: Evidence conclusively proves the atomic code claim.
  - `DISPROVED`: Immutable code counter-evidence directly contradicts the claim.
  - `INCONCLUSIVE`: Tool budget exhausted or evidence insufficient without counter-evidence.
  - `HUMAN_REQUIRED`: Claim requires external product/business authority not present in code.

- **Run & Plan Gate Outcomes**:
  - `COMPLETE`: All critical proof obligations verified; plan gate passed.
  - `BLOCKED`: Direct code contradiction found; execution forbidden.
  - `INCONCLUSIVE`: Non-critical ambiguity or budget limit reached; safe non-execution default.
  - `HUMAN_WAIT` / `HUMAN_DECISION_REQUIRED`: Workflow paused awaiting authorized human decision.
  - `FAILED`: System error or malformed payload safely aborted.

---

## Server-Issued Evidence Authority

In traditional LLM systems, models often hallucinate quotes or line numbers that do not match current code. PlanProof solves this with **Server-Issued Evidence Authority**:

1. A model cannot invent an evidence ID or assert that a file contains text without proof.
2. Evidence is issued exclusively by `EvidenceAuthority` after a successful, audited tool run.
3. Every evidence document stores:
   - `snapshot_id`: Binds evidence to an exact, immutable commit snapshot.
   - `source_tool_run_id`: References the specific audited tool execution record.
   - `path`: Normalized, snapshot-relative file path (no directory traversal).
   - `line_start` & `line_end`: Verified line boundaries within the physical file.
   - `content_hash`: Cryptographic SHA-256 hash of the exact source file.
   - `summary`: Structured fact summary for developer inspection.
4. **Stale Hash & Cross-Snapshot Rejection**: If a file hash does not match the snapshot record, or if evidence from snapshot A is presented in snapshot B, the verification engine rejects it immediately.

---

## Deterministic Repository Tools

PlanProof equips the agent with a bounded suite of deterministic inspection tools:

| Tool Name | Role | Technical Implementation Details |
| :--- | :--- | :--- |
| `list_files` | File discovery & structure | Queries snapshot file tree; supports glob matching and language filtering. |
| `search_code_lexical` | Fast pattern search | **Lexical search** across snapshot files; extracts line ranges with configurable context. |
| `read_file_range` | Bounded source inspection | Reads exact line slices (max 200 lines / 32 KB per call); enforces path containment. |
| `find_symbol` | Symbol & signature lookup | Queries indexed classes, functions, methods, and imports extracted at snapshot time. |
| `find_references` | Cross-file reference check | Partial lexical reference discovery across codebase (explicitly flagged `PARTIAL_LEXICAL`). |

> [!NOTE]
> **Technical Transparency**: Python symbol extraction uses Python standard library `ast.parse`. TypeScript and JavaScript symbol extraction uses lightweight regular-expression tokenization. `search_code_lexical` is a lexical pattern tool, not an AST query engine. Reference analysis is partial and does not claim full compiler-level call-graph resolution.

---

## Key Architectural Decisions

### Why One Orchestrator (Not a Multi-Agent Swarm)?

PlanProof intentionally uses a single, durable orchestrator rather than an autonomous multi-agent swarm:

1. **Deterministic Causal Traceability**: Every tool run, evidence item, and status transition is recorded in a single sequential audit log.
2. **Zero Nondeterministic Consensus Overhead**: Multi-agent "debates" waste tokens, increase latency, and produce non-reproducible outcomes.
3. **Simplified Resumption & Persistence**: Persisting a single state machine across worker restarts and human interruptions in MongoDB is robust and verifiable.
4. **Direct Fast-Path Resolution**: Many obligations are resolved by deterministic validators without invoking an LLM at all.

### Why Indexed Symbols + Exact Source Evidence (Not Premature Vector RAG)?

1. **Exact Codebase Truth**: Code verification requires exact symbol definitions, paths, source ranges, and content-hash provenance. Semantic vector similarity frequently returns false positives that lack syntactic authority.
2. **Cryptographic Provenance**: Evidence must be verifiable against exact SHA-256 hashes of source files in immutable snapshots.
3. **Zero Embedding Latency/Cost**: AST, regex symbol indexing, and lexical indexing are computed once during repository ingestion in milliseconds.

---

## Durable Memory & Persistence Model

PlanProof avoids ephemeral in-memory state. State is categorized cleanly across three infrastructure layers:

- **MongoDB Atlas (`planproofapp`)**: The authoritative system of record.
  - `projects`: Workspace ownership and metadata.
  - `github_installations` & `github_sessions`: Authenticated GitHub App sessions.
  - `repository_snapshots`: Commit SHAs, root hashes, and indexing status.
  - `repository_files`: Normalized snapshot-scoped file paths, hashes, and text.
  - `code_symbols`: Extracted symbols (classes, functions, methods, imports).
  - `plan_versions`: Immutable candidate plans and change requests.
  - `verification_runs`: Run lifecycle status, budgets, and token accounting.
  - `proof_obligations`: Normalized claims, assigned statuses, and evidence links.
  - `evidence`: Server-issued evidence records with cryptographic provenance.
  - `authorized_facts`: Canonical server-derived present-state facts.
  - `revised_plans`: Evidence-grounded advisory updated implementation plans.
  - `tool_runs`: Audit logs of every tool execution with input hashes and latency.
  - `model_calls`: Audit logs of provider, model, latency, and token metrics.
  - `human_questions`: Persisted authority questions, required actors, and answers.
  - `events`: Monotonically sequenced run progress events.
  - `eval_runs`: Versioned offline evaluation results and regression records.
  - `active_reservations`: Atomic compute slot reservations and TTL leases.
- **Serverless Cloud Tasks Queue**: Asynchronous HTTP task delivery with Google IAM OIDC authentication and exponential retry policy.
- **Worker Execution Model**: Durable run state is application-owned in MongoDB; Cloud Tasks triggers execution with monotonic execution generations and zero-idle scale-to-zero compute.

---

## Human-in-the-Loop (HITL) as an Authority Boundary

Codebase inspection can authoritatively answer questions of fact:
- *Does the `process_refund` function exist?* → **Yes (Code fact)**
- *Does the database schema enforce uniqueness on `order_id`?* → **Yes (Code fact)**

Codebase inspection **cannot** authoritatively answer questions of intent:
- *Should we allow partial refunds without manager approval?* → **Product/Business Decision**
- *Does an external mobile app depend on this deprecated API response shape?* → **Cross-Service Authority**

When the orchestrator encounters a claim categorized as `BUSINESS_RULE` or `CROSS_SERVICE`, it immediately emits `HUMAN_REQUIRED`:
1. The question and rationale are persisted in `human_questions`.
2. The verification run transitions to `HUMAN_WAIT` and releases worker resources.
3. The developer or product owner answers the question via the Web UI.
4. The API atomically increments `execution_generation` and enqueues a new Cloud Task, and the worker completes the run.
5. **Prior counter-evidence is never erased**: Answering a business question will not unblock a plan if code-level contradictions still exist.

---

## Failure Handling & Safety Matrix

| Failure Mode | Autonomous Safe Behavior |
| :--- | :--- |
| **Primary Model Timeout / 5xx** | Automatic retry with exponential backoff; transparent failover to AIMLAPI fallback model. |
| **Both Model Providers Fail** | Run transitions to `FAILED` with safe error class; **zero fabricated verifications**. |
| **Malformed Structured JSON** | Rejection by Pydantic; run fails safely without fabricated verification. |
| **Disallowed Tool Request** | Tool dispatcher rejects unauthorized tool name or illegal parameter; logs security event. |
| **Tool Execution Failure** | Tool run recorded as `FAILED`; no evidence issued; orchestrator continues. |
| **Model Invented Evidence ID** | Rejected immediately by `EvidenceAuthority`; cannot affect obligation status. |
| **Investigation Budget Exhausted** | Obligation transitions to `INCONCLUSIVE`; final gate defaults to safe non-execution. |
| **Worker Process Crash / Restart** | Run state reloaded cleanly from MongoDB Atlas; idempotency key prevents duplicate execution. |
| **Stale Snapshot / Modified Branch** | Runs bind to immutable commit SHAs; branch mutations do not alter existing snapshots. |
| **Path Traversal Attack (`../`)** | Rejected by `_safe_path` sanitizer; paths must be normalized and snapshot-relative. |

---

## GitHub App Ingestion Flow

PlanProof integrates natively with GitHub via the official GitHub App (`PlanProof Verification`, App ID: `5023064`):

1. **One-Click Installation**: Users authorize PlanProof on selected personal or organizational repositories.
2. **Least-Privilege Scopes**: Requests strictly **Repository Contents: Read-only** and **Metadata: Read-only**. No code write or administration permissions.
3. **Cryptographic JWT Authentication**: Backend mints short-lived installation access tokens using RS256 private key cryptography.
4. **Exact SHA Resolution**: Resolves the target branch ref (e.g., `refs/heads/main`) to its exact 40-character Git commit SHA.
5. **Immutable Snapshot Creation**: Downloads and indexes the repository state at that exact commit, ensuring verification results are permanently reproducible.

---

## Real Production Proof

PlanProof is fully deployed, zero-idle hardened, and validated on Google Cloud Platform:

- **Live Deployed Services**:
  - Web UI: `https://planproof-web-lfrrer4z6q-el.a.run.app` (Cloud Run `asia-south1`, min=0)
  - API: `https://planproof-api-lfrrer4z6q-el.a.run.app` (Revision `planproof-api-00060-d2l`, min=0)
  - Worker: `planproof-verification-worker` (Scale-to-Zero Cloud Run service in `asia-south1`, min=0, max=1, timeout=1800s)
  - Queue: `planproof-verification-queue` (Cloud Tasks with OIDC IAM authentication)
  - Scheduler: `planproof-outbox-recovery` (Cloud Scheduler periodic outbox dispatcher recovery)
  - MongoDB Atlas: `planproofapp` cluster (Static egress allowlist via GCP Cloud NAT `34.93.153.36`)
- **Real Production E2E Verification Proven**:
  - **Run ID**: `375a0873-1fd5-4172-a025-19510cc03d6a`
  - **Repository**: `NikhilRaikwar/Aelix` (Snapshot `71f6d0b`, branch `main`, commit `57ef352`)
  - **Deterministic Task**: `run-375a0873-1fd5-4172-a025-19510cc03d6a-g0`
  - **Dispatch**: Serverless delivery into `planproof-verification-queue` with OIDC audience verification
  - **Worker Execution**: Confirmed executed on `planproof-verification-worker-00010-zpr`
  - **Final Domain State**: `INCONCLUSIVE` (valid verification-domain outcome: literal lexical search found no matching evidence in snapshot, not an infra error)
  - **Persistence**: 100% durable MongoDB state and real-time SSE event delivery
- **Redis Decommission & Cost Hardening**:
  - `REDIS_URL` mapping removed from `planproof-api`; Memorystore `planproof-redis` instance decommissioned.
  - Near-zero idle verification execution cost: fixed Redis and persistent worker costs eliminated; compute scales to zero.
  - VPC NAT / static egress IP (`34.93.153.36`) preserved for MongoDB Atlas allowlisting.

---

## 27-Case Versioned Evaluation Suite

PlanProof includes an offline evaluation suite (`evals/cases/v1`) designed to measure verification fidelity without leaking test answers into runtime code.

### Evaluation Case Categories

The 27 versioned evaluation cases cover:
- **Schema & Uniqueness Constraints** (`schema-uniqueness.json`, `optional-required-field.json`)
- **API Contracts & Return Types** (`api-compatibility.json`, `return-type.json`, `unknown-enum.json`)
- **Cross-Module Dependencies** (`cross-module-dependency.json`, `billing-impact.json`)
- **Idempotency & Duplicate Delivery** (`idempotency-key.json`, `duplicate-obligations.json`)
- **Security & Prompt Injection Resistance** (`readme-prompt-injection.json`, `source-comment-injection.json`, `path-traversal.json`)
- **Provider Outages & Failover** (`provider-timeout.json`, `provider-positive-amount.json`)
- **Human Escalation & Workflow Resumption** (`human-restart-resume.json`, `mobile-authority.json`)
- **Investigation Budget Boundaries** (`budget-exhaustion.json`, `malformed-model-json.json`, `tool-failure.json`)

### Measured Benchmark Results

*Latest result on the current 27-case versioned evaluation set:*

| Metric | Measured Result | Evaluation Scope & Notes |
| :--- | :---: | :--- |
| **Critical Assumption Recall** | **100.0%** | Fraction of critical plan assumptions successfully identified and tested. |
| **Status Accuracy** | **100.0%** | Agreement with expected verification statuses (`VERIFIED`, `DISPROVED`, `HUMAN_REQUIRED`). |
| **Evidence Provenance Validity** | **100.0%** | All generated evidence traces strictly match real snapshot source ranges and content hashes. |
| **Appropriate Escalation Rate** | **100.0%** | Precision in escalating business/cross-service claims to humans without false alarms. |
| **Tool Success Rate** | **100.0%** | Bounded tool execution reliability without unhandled tool crashes. |
| **Regression Gate Status** | **PASS** | Evaluated via `evaluation.runner` against explicit baseline thresholds. |

> [!IMPORTANT]
> These values describe this controlled 27-case versioned evaluation suite and do not constitute a claim of universal production accuracy across all possible software architectures.

---

## Observability & Safe Tracing

PlanProof provides full end-to-end auditability across the API, message queue, worker, LangGraph orchestrator, deterministic tools, and model gateway using structured correlation IDs:

- `request_id`: Traces client HTTP requests through Cloud Run and FastAPI middleware.
- `run_id`: Binds the entire verification lifecycle across worker tasks and events.
- `snapshot_id`: Scopes all repository files, extracted symbols, and tool executions.
- `obligation_id`: Tracks the lifecycle of individual plan claims.
- `tool_run_id`: Identifies exact tool executions, input hashes, and durations.
- `model_call_id`: Records provider, model, latency, and token consumption.

**Zero Sensitive Data Logging**: Production logs strictly redact API keys, database connection strings, GitHub private keys, raw prompt internals, and full proprietary source files.

---

## Security & Isolation Model

PlanProof treats all external input—repositories, model outputs, and user plans—as **untrusted data**:

- **No Arbitrary Code Execution (P0)**: PlanProof performs static AST parsing and lexical analysis. It never executes arbitrary build scripts, tests, or shell commands from ingested repositories.
- **Path Containment**: All file operations enforce normalized relative paths (`PurePosixPath`). Absolute paths, directory traversal (`../`), and symlink escapes are strictly blocked.
- **Prompt Injection Defense**: Repository content and user change requests are wrapped in structured JSON boundaries, preventing untrusted repository comments or README files from hijacking model instructions.
- **Least-Privilege GitHub Permissions**: Requires strictly read-only access to repository contents and metadata.
- **Secret Hygiene**: Production credentials are stored in Secret Manager; the tracked source tree and frontend bundle are covered by repository secret-scan checks.

See [docs/SECURITY.md](docs/SECURITY.md) for full security controls.

---

## Tech Stack

### Frontend
- **Framework**: Next.js 16.3.3 (App Router, Turbopack)
- **UI Library**: React 19, Tailwind CSS v4, Lucide React, Base UI
- **Testing**: Playwright 1.63.0

### Backend & Ingestion
- **Runtime**: Python 3.12 (via `uv` package manager)
- **Framework**: FastAPI 0.115+, Pydantic v2, Pydantic-Settings
- **Database Driver**: PyMongo 4.11+ (Async)
- **Symbol Parsers**: Python standard library `ast.parse`, regex lexical extractors

### Agent & Workflow Engine
- **Orchestration**: LangGraph 1.2+, StateGraph state machine
- **Task Dispatch & Queue**: Google Cloud Tasks (`planproof-verification-queue`) with OIDC IAM authentication
- **Model Gateway**: HTTPX async client, OpenRouter primary, AIMLAPI fallback

### Infrastructure & Cloud (GCP)
- **Platform**: Google Cloud Platform (Project: `planproof-ai`, Region: `asia-south1`)
- **Compute**: Google Cloud Run (Web & API: Scale-to-Zero), Cloud Run Worker (Scale-to-Zero)
- **Storage & State**: MongoDB Atlas (`planproofapp`)
- **Security & Networking**: GCP Secret Manager, Artifact Registry, Direct VPC Egress, Cloud NAT, Cloud Tasks

---

## Testing Strategy

PlanProof employs a layered, deterministic testing strategy:

```text
├── Backend Unit & Safety Suite       -> FastAPI, AST parsers, tool sandbox, security, zero-idle
├── Live Atlas Integration            -> Real MongoDB indexes, atomic reservations, TTL leases
├── Frontend UI & State Isolation     -> Playwright component & API boundary tests
├── GitHub App Live Smoke             -> Live token issuance & repository query
├── Seeded Real Production E2E        -> Full browser pre-flight verification
└── Offline Evaluation Suite          -> 27 Versioned Cases (Fidelity, recall & regression gating)
```

**Continuous Validation in CI**:
Current main is validated in GitHub Actions with:
- frontend secret scan, TypeScript typecheck, production build, and Playwright UI suite
- backend Ruff + pytest (122+ passing unit and zero-idle tests)
- deterministic agent-quality/evaluation safety suite

---

## Where to Look in the Code

| Component | Path | Description |
| :--- | :--- | :--- |
| **API Entrypoint** | [`apps/api/app/main.py`](apps/api/app/main.py) | FastAPI service setup, role-based route isolation (`PLANPROOF_RUNTIME_ROLE`), CORS allowlists. |
| **Worker Endpoints** | [`apps/api/app/api/internal_tasks.py`](apps/api/app/api/internal_tasks.py) | Private Cloud Tasks & Cloud Scheduler execution endpoints with Google OIDC audience validation. |
| **Cloud Tasks Service** | [`apps/api/app/services/cloud_tasks.py`](apps/api/app/services/cloud_tasks.py) | Serverless task creation with explicit `dispatch_deadline=1800s`, deterministic naming, and outbox recovery. |
| **GitHub App Auth** | [`apps/api/app/api/github.py`](apps/api/app/api/github.py) | GitHub App JWT signing (RS256), installation tokens, repository queries, and branch SHA resolution. |
| **Repository Ingestion** | [`apps/api/app/ingestion/service.py`](apps/api/app/ingestion/service.py) | Snapshot materialization, file tree traversal, and content hashing. |
| **Symbol Parsers** | [`apps/api/app/ingestion/parsers.py`](apps/api/app/ingestion/parsers.py) | Python `ast.parse` symbol extraction and lightweight TS/JS token extraction. |
| **Deterministic Tools** | [`apps/api/app/services/repository_tools.py`](apps/api/app/services/repository_tools.py) | `list_files`, `search_code_lexical`, `read_file_range`, `find_symbol`, and `find_references`. |
| **Evidence Authority** | [`apps/api/app/services/evidence.py`](apps/api/app/services/evidence.py) | Server-side evidence issuance, source range validation, and cryptographic hash verification. |
| **Revision Engine** | [`apps/api/app/services/revision.py`](apps/api/app/services/revision.py) | Authorized facts derivation, invariant verification, and advisory updated plan synthesis. |
| **Verification Engine** | [`apps/api/app/workflow/engine.py`](apps/api/app/workflow/engine.py) | Single-orchestrator LangGraph state machine, tool dispatching, HITL questions, and gate policy. |
| **Model Gateway** | [`apps/api/app/services/models.py`](apps/api/app/services/models.py) | OpenRouter primary with automatic AIMLAPI fallback, JSON schema validation, and exponential backoff. |
| **Mongo Collections** | [`apps/api/app/db/indexes.py`](apps/api/app/db/indexes.py) | Idempotent index definitions for MongoDB Atlas collections storing projects, snapshots, runs, evidence, and traces. |
| **Evaluation Suite** | [`evals/cases/v1/`](evals/cases/v1/) | 27 versioned evaluation cases testing schema, contracts, idempotency, security, and budgets. |
| **Workspace Dashboard** | [`app/workspace/page.tsx`](app/workspace/page.tsx) | Next.js 16 workspace cockpit showing repositories, snapshots, and recent verification runs. |
| **Run Cockpit** | [`app/workspace/runs/[runId]/page.tsx`](app/workspace/runs/[runId]/page.tsx) | Real-time verification run view with obligations, evidence viewer, tool traces, and HITL decision cards. |
| **Production E2E** | [`tests/seeded-real.e2e.spec.ts`](tests/seeded-real.e2e.spec.ts) | Playwright end-to-end browser test verifying snapshot indexing, tool execution, HITL resume, and gate blocking. |

---

## Local Quickstart

### Prerequisites
- **Node.js**: v22+
- **Python**: 3.11, 3.12, or 3.13
- **uv**: Fast Python package manager ([docs.astral.sh/uv](https://docs.astral.sh/uv/))
- **MongoDB Atlas** or local MongoDB instance

### 1. Clone & Configure Environment

```bash
git clone https://github.com/NikhilRaikwar/PlanProof.git
cd PlanProof

# Copy example environment configuration
cp .env.example .env
```

### 2. Start Services

```bash
# Terminal 1: Start FastAPI Backend (API Mode)
cd apps/api
uv sync --all-groups
PLANPROOF_RUNTIME_ROLE=api uv run uvicorn app.main:app --reload --port 8000

# Terminal 2: Start Next.js Frontend
npm ci
npm run dev
```

The workspace UI will be available at `http://localhost:3000`.

---

## Verified Test Commands

```bash
# --- Frontend Quality & Security ---
npm run secret:scan      # Automated scanner for leaked credentials
npm run typecheck        # TypeScript strict verification
npm run build            # Next.js 16 production build verification
npm run test:ui          # Playwright UI & API state tests
npm run test:e2e         # Playwright Seeded Real E2E verification test

# --- Backend Unit, Integration & Lints ---
cd apps/api
uv run ruff check app tests      # Fast Python linter
uv run pytest -q                 # Backend unit & safety suite (122 passing)
uv run pytest -m integration -q  # Atlas integration tests

# --- Evaluation Harness & Regression Gating ---
uv run pytest tests/test_evaluation_harness.py -q
```

---

## GCP Deployment Summary

PlanProof runs on Google Cloud Platform in `asia-south1`:

- **GCP Project**: `planproof-ai`
- **Region**: `asia-south1` (Mumbai)
- **Web UI**: Cloud Run service `planproof-web` (Scale-to-Zero)
- **API**: Cloud Run service `planproof-api` (Scale-to-Zero)
- **Worker**: Cloud Run service `planproof-verification-worker` (Scale-to-Zero)
- **Queue**: Cloud Tasks queue `planproof-verification-queue`
- **Database**: MongoDB Atlas Cluster `planproofapp`
- **Secrets**: GCP Secret Manager (Zero secrets in code or Docker images)

See [docs/DEPLOYMENT_GCP.md](docs/DEPLOYMENT_GCP.md) for full deployment scripts and tear-down runbooks.

---

## Demo Walkthrough

1. **Connect GitHub**: Authorize the GitHub App and select a repository.
2. **Resolve Commit**: Select a branch; PlanProof resolves the branch HEAD to an exact commit SHA and creates an immutable snapshot.
3. **Submit Plan**: Paste a proposed change request and candidate implementation plan.
4. **Extract Obligations**: The model extracts testable claims (schema, API contracts, symbols).
5. **Observe Contradiction**: Deterministic lexical search discovers that a proposed schema migration conflicts with an existing `unique: true` constraint.
6. **Hit Authority Boundary**: A cross-service contract claim emits `HUMAN_REQUIRED`. The workflow pauses cleanly.
7. **Submit Human Decision**: Enter the human approval; the workflow resumes asynchronously.
8. **Inspect Plan Gate**: The final gate reports **BLOCKED** because the schema contradiction is a hard blocker, proving that human approval cannot override code-backed contradictions.

See [docs/DEMO.md](docs/DEMO.md) for the complete script.

---

## Design Tradeoffs

| Architectural Decision | Chosen Strategy | Alternative Rejected | Rationale |
| :--- | :--- | :--- | :--- |
| **Deterministic Validators First** | Run AST & lexical checks before LLM | LLM-only reasoning | Deterministic checks are predictable, inexpensive, reproducible, and do not delegate repository authority to model-generated assertions. |
| **Orchestration Model** | Single LangGraph state machine | Autonomous multi-agent swarm | A single bounded orchestrator keeps PlanProof's causal trace easier to audit and avoids unnecessary coordination complexity for this workflow. |
| **Code Retrieval** | Indexed symbols + lexical search | Vector semantic embeddings | Verification requires exact syntax and cryptographic line provenance, not fuzzy semantic similarity. |
| **Repository State** | Immutable commit snapshots | Dynamic `HEAD` branch polling | Branch mutations during investigation invalidate evidence provenance. |
| **Evidence Authority** | Server-issued evidence records | Model-asserted proof quotes | Prevents models from fabricating evidence or misquoting source lines. |
| **Execution Boundary** | Google Cloud Tasks + scale-to-zero Cloud Run worker | Synchronous HTTP request loop | Verification jobs can take 30+ seconds; serverless task dispatch scales compute to zero when idle while preventing HTTP request timeouts. |
| **Authority Gaps** | `HUMAN_REQUIRED` pause & resume | LLM guessing business rules | Codebases do not contain undocumented human intent; guessing leads to silent production failures. |
| **Model Redundancy** | OpenRouter primary + AIMLAPI fallback | Single provider dependency | Protects production verification pipeline from 3rd-party provider downtime. |

---

## Limitations & Future Work

### Current Engineering Limitations
- **Symbol Extraction**: Python uses standard library `ast.parse`. TypeScript/JavaScript symbol extraction uses lightweight regex tokenization.
- **Reference Resolution**: Reference checking is partial lexical matching (`PARTIAL_LEXICAL`), not full compiler-level call-graph resolution.
- **Execution Sandbox**: PlanProof does not execute arbitrary repository code, unit tests, or build scripts in P0.
- **Evaluation Size**: The evaluation suite currently consists of 27 versioned test cases.
- **Enterprise Scope**: Current deployment is configured for single-tenant / small-team verification workloads, not high-throughput enterprise multi-tenancy.

### Future Work
- Integration with Tree-sitter and Language Server Protocol (LSP) for deep multi-language semantic call graphs.
- Optional vector-based semantic retrieval if future evaluations identify empirical recall gaps.
- Ephemeral sandboxed micro-VM execution for test execution probes.
- Expanded evaluation corpus spanning 100+ multi-repository benchmarks.

---

<p align="center">
  <sub>
    Built by <a href="https://github.com/NikhilRaikwar"><strong>Nikhil Raikwar</strong></a> · PlanProof
  </sub>
  <br />
  <sub>
    Open source under the <a href="LICENSE">MIT License</a>.
  </sub>
</p>
