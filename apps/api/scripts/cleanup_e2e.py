"""Remove exactly one named E2E project and its dependent test records.

This is a local operator utility, never an HTTP endpoint. It intentionally
requires an exact project name beginning with ``e2e-`` and follows persisted
foreign IDs before deleting anything. It cannot broad-delete shared Atlas data.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Executing a file from ``scripts/`` makes that directory Python's import root.
# Add the API project root explicitly so this operator utility works with
# ``uv run python scripts/cleanup_e2e.py`` without changing user environment.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings
from app.db.mongo import MongoManager


async def cleanup(project_name: str) -> int:
    if not project_name.startswith("e2e-"):
        raise ValueError("refusing cleanup: project name must begin with 'e2e-'")
    mongo = MongoManager(Settings())
    await mongo.connect()
    try:
        database = mongo.database()
        projects = [item async for item in database.projects.find({"name": project_name})]
        if len(projects) != 1:
            raise ValueError("refusing cleanup: expected exactly one matching E2E project")
        project_id = projects[0]["id"]
        snapshots = [
            item["id"]
            async for item in database.repository_snapshots.find({"project_id": project_id})
        ]
        plans = [
            item["id"] async for item in database.plan_versions.find({"project_id": project_id})
        ]
        runs = [
            item["id"] async for item in database.verification_runs.find({"project_id": project_id})
        ]

        if runs:
            await database.events.delete_many({"run_id": {"$in": runs}})
            await database.human_questions.delete_many({"run_id": {"$in": runs}})
            await database.proof_obligations.delete_many({"run_id": {"$in": runs}})
            await database.verification_runs.delete_many({"id": {"$in": runs}})
        if plans:
            await database.proof_obligations.delete_many({"plan_version_id": {"$in": plans}})
            await database.plan_versions.delete_many({"id": {"$in": plans}})
        if snapshots:
            await database.evidence.delete_many({"snapshot_id": {"$in": snapshots}})
            await database.tool_runs.delete_many({"snapshot_id": {"$in": snapshots}})
            await database.code_symbols.delete_many({"snapshot_id": {"$in": snapshots}})
            await database.code_chunks.delete_many({"snapshot_id": {"$in": snapshots}})
            await database.repository_files.delete_many({"snapshot_id": {"$in": snapshots}})
            await database.repository_snapshots.delete_many({"id": {"$in": snapshots}})
        await database.projects.delete_one({"id": project_id})
        return 0
    finally:
        await mongo.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely clean one PlanProof E2E project.")
    parser.add_argument("--project-name", required=True)
    args = parser.parse_args()
    return asyncio.run(cleanup(args.project_name))


if __name__ == "__main__":
    raise SystemExit(main())
