# PlanProof

> **Verify the plan before agents build it.**  
> PlanProof checks candidate engineering plans against your codebase, identifies high-risk assumptions, and returns code-grounded proof obligations before implementation begins.

---

## Overview

PlanProof is an internal engineering platform designed to gate autonomous coding agents and engineers before code execution. By combining deterministic AST parsing, semantic symbol indexing, dependency call-graphs, and OpenAPI/schema validators, PlanProof ensures plans are safe, feasible, and contradiction-free.

```
Candidate Plan Submitted
        ↓
Proof Claims Extracted
        ↓
Repository Snapshot Pinned
        ↓
Code & Schema Evidence Gathered
        ↓
Obligations Verified / Disproved
        ↓
High-Risk Decisions Escalated to Human
        ↓
Plan Gated Before Implementation
```

---

## Core Features

- **Marketing Experience**: Responsive landing page with interactive verification flow and confidence breakdowns.
- **Verification Intake**: Supports pasting plans directly or uploading plan documents (`.md`, `.txt`, `.json`, `.yaml`).
- **Plan Gate Reports**: Detailed verification status (`VERIFIED FOR EXECUTION` / `BLOCKED BEFORE EXECUTION`), proof obligations inspector, codebase counter-evidence, and one-click `Copy Agent Prompt`.
- **Repository Indexing**: Connected GitHub repositories with pinned commit snapshots and AST readiness telemetry.
- **Evidence Explorer**: Code-backed evidence viewer with line ranges, AST facts, and contract diffs.
- **Tool Traces**: 6-step deterministic AST execution timeline (`claim_extraction`, `symbol_search`, `schema_probe`, `dependency_graph`, `openapi_scan`, `contradiction_check`).
- **Internal Quality Benchmarks (`/internal/quality`)**: Offline reliability metrics, Catmull-Rom accuracy trend curves, evaluation suites, and latency/cost telemetry.

---

## Architecture & Navigation

### Normal User Navigation (`/workspace/*`)
- **`BUILD`**:
  - `New verification` (`/workspace/new-verification`)
  - `Runs` (`/workspace/runs`)
  - `Repositories` (`/workspace/repositories`)
- **`VERIFY`**:
  - `Evidence` (`/workspace/evidence`)
  - `Tool traces` (`/workspace/tool-traces`)

### Internal Engineering Only (`/internal/*`)
- `Quality Benchmarks` (`/internal/quality`)

---

## Tech Stack

- **Framework**: Next.js 16 (App Router)
- **Language**: TypeScript
- **Styling**: Vanilla CSS Design System with light cream palette & coral accents
- **Icons**: Lucide React
- **Animations**: Framer Motion

---

## Getting Started

### 1. Install Dependencies
```bash
npm install
# or
pnpm install
```

### 2. Run Development Server
```bash
npm run dev
# or
pnpm dev
```
Open [http://localhost:3000](http://localhost:3000) to view the landing page, or [http://localhost:3000/workspace/new-verification](http://localhost:3000/workspace/new-verification) for the workspace.

### 3. Production Build
```bash
npm run build
npm run start
```

---

## License

This project is licensed under the MIT License.  
See [LICENSE](./LICENSE) for details.

Copyright © 2026 Nikhil Raikwar.
