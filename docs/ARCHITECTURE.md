# PlanProof architecture

PlanProof uses one bounded, auditable verification orchestrator rather than a multi-agent swarm. A run is immutable with respect to project, snapshot, and plan version. MongoDB Atlas is the system of record; Redis carries work only.

```mermaid
flowchart TD
  Plan[Immutable plan version] --> Run[Durable verification run]
  Snapshot[READY immutable snapshot] --> Run
  Run --> Extract[Structured obligation proposals]
  Extract --> Policy[Server-owned obligations / PENDING]
  Policy --> Tool[Allowlisted snapshot-scoped tool]
  Tool --> ToolRun[Audited tool_run]
  ToolRun --> Evidence[Server-issued evidence]
  Evidence --> Validator[Deterministic validator + policy]
  Validator --> Gate[Authoritative final gate]
  Validator --> Human[HUMAN_REQUIRED]
  Human --> Resume[Persisted answer + queue resume]
  Resume --> Policy
```

## Authority boundaries

| Concern | Authority |
| --- | --- |
| Repository facts | Snapshot-scoped deterministic tools and validators |
| Evidence IDs and provenance | Server-side evidence authority |
| Obligation and final run status | Deterministic policy code |
| Ambiguous claim extraction / next-action proposal | Structured model gateway |
| Business or external-system intent | Persisted human question and answer |

The model cannot execute shell commands, choose arbitrary paths, access the host filesystem, write MongoDB, create evidence, or override budgets and policy. Repository text is untrusted data even when it appears in model context.

## Durable flow

```text
POST verification run -> Mongo run + event -> Redis/Dramatiq
worker -> LangGraph bounded state -> tools -> tool runs -> evidence -> policy
                       \-> HUMAN_WAIT -> persisted answer -> requeued worker
```

Every useful artefact is bound to an immutable snapshot. Retries use persisted identifiers and unique indexes so duplicate delivery cannot create duplicate authoritative evidence or terminal transitions.

## Storage

MongoDB collections include `projects`, `repository_snapshots`, `repository_files`, `code_symbols`, `plan_versions`, `verification_runs`, `proof_obligations`, `tool_runs`, `evidence`, `model_calls`, `human_questions`, `events`, and `eval_runs`. Indexes match identity, lifecycle, snapshot scope, event sequencing, and evaluator query patterns.

Redis is intentionally not authoritative: it transports Dramatiq messages and provides bounded rate-limit counters. If it is mandatory but unavailable, readiness fails closed.
