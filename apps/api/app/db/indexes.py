from __future__ import annotations

from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.asynchronous.database import AsyncDatabase

INDEXES: dict[str, list[IndexModel]] = {
    "projects": [IndexModel([("owner_id", ASCENDING), ("created_at", DESCENDING)])],
    "repository_snapshots": [
        IndexModel(
            [("project_id", ASCENDING), ("resolved_commit_sha", ASCENDING)],
            unique=True,
            partialFilterExpression={"resolved_commit_sha": {"$type": "string"}},
        ),
        IndexModel(
            [
                ("repository_identity", ASCENDING),
                ("resolved_commit_sha", ASCENDING),
                ("parser_version", ASCENDING),
                ("index_version", ASCENDING),
            ],
            unique=True,
            partialFilterExpression={"resolved_commit_sha": {"$type": "string"}},
        ),
    ],
    "repository_files": [
        IndexModel([("snapshot_id", ASCENDING), ("path", ASCENDING)], unique=True),
    ],
    "code_symbols": [IndexModel([("snapshot_id", ASCENDING), ("qualified_name", ASCENDING)])],
    "code_chunks": [
        IndexModel([("snapshot_id", ASCENDING), ("path", ASCENDING), ("symbol", ASCENDING)]),
    ],
    "plan_versions": [IndexModel([("project_id", ASCENDING), ("version", ASCENDING)], unique=True)],
    "verification_runs": [
        IndexModel([("project_id", ASCENDING), ("created_at", DESCENDING)]),
        IndexModel([("status", ASCENDING), ("updated_at", ASCENDING)]),
        IndexModel(
            [("idempotency_key", ASCENDING)],
            unique=True,
            partialFilterExpression={"idempotency_key": {"$type": "string"}},
        ),
    ],
    "proof_obligations": [
        IndexModel([("run_id", ASCENDING), ("status", ASCENDING), ("criticality", ASCENDING)]),
        IndexModel(
            [("plan_version_id", ASCENDING), ("normalized_statement", ASCENDING)], unique=True
        ),
    ],
    "evidence": [IndexModel([("snapshot_id", ASCENDING), ("source_tool_run_id", ASCENDING)])],
    "tool_runs": [
        IndexModel([("run_id", ASCENDING), ("started_at", ASCENDING)]),
        IndexModel([("snapshot_id", ASCENDING), ("tool_name", ASCENDING)]),
    ],
    "model_calls": [
        IndexModel([("provider", ASCENDING), ("model", ASCENDING), ("created_at", DESCENDING)])
    ],
    "events": [IndexModel([("run_id", ASCENDING), ("sequence", ASCENDING)], unique=True)],
    "human_questions": [
        IndexModel([("status", ASCENDING), ("created_at", ASCENDING)]),
        IndexModel([("run_id", ASCENDING), ("obligation_id", ASCENDING)], unique=True),
    ],
    "eval_runs": [
        IndexModel([("timestamp", DESCENDING)]),
        IndexModel([("case_set_version", ASCENDING), ("timestamp", DESCENDING)]),
    ],
}


async def ensure_indexes(database: AsyncDatabase) -> None:
    """Create operational indexes safely and idempotently at service startup/deploy time."""

    for collection, indexes in INDEXES.items():
        await database.get_collection(collection).create_indexes(indexes)
