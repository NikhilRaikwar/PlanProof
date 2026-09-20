# Payments Platform — PlanProof Seeded Fixture

This repository is intentionally small and contains known engineering constraints. It exists so
PlanProof can demonstrate real, reproducible verification without access to a third-party GitHub
repository.

## Scenario

Change request: **Add partial refunds while preserving current full-refund behavior and API
compatibility.**

The candidate plan may incorrectly assume that no migration is required, existing idempotency is
safe, and billing is unaffected. Those assumptions are deliberately false in this fixture.

## Ground truth

| Claim | Expected result | Evidence |
| --- | --- | --- |
| Provider accepts a refund amount | `VERIFIED` | `services/provider.py` |
| Multiple refunds fit the current schema | `DISPROVED` | `db/models/refund.ts` |
| Existing idempotency works for partial refunds | `DISPROVED` | `api/idempotency.ts` |
| Billing is unaffected | `DISPROVED` | `billing/ledger.py` |
| API can remain compatible | `VERIFIED` | `openapi/payments.yaml` |
| Mobile-client impact is known | `HUMAN_REQUIRED` | no mobile repository is connected |

This fixture must remain deterministic. Any behavior change requires updating the corresponding
versioned evaluation case before it is used in the public demo.
