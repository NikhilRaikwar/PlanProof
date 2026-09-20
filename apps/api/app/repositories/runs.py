from __future__ import annotations

from pymongo.errors import DuplicateKeyError

from app.core.errors import DuplicateResourceError
from app.db.mongo import MongoManager
from app.domain.runs import PlanVersion, RepositorySnapshot, RunEvent, VerificationRun


class RunRepository:
    """Persistence adapter for immutable plans, snapshots, runs, and append-only run events."""

    def __init__(self, mongo: MongoManager) -> None:
        self._database = mongo.database()

    async def create_snapshot(self, snapshot: RepositorySnapshot) -> RepositorySnapshot:
        try:
            await self._database.repository_snapshots.insert_one(snapshot.model_dump(mode="python"))
        except DuplicateKeyError as exc:
            raise DuplicateResourceError("snapshot identity already exists") from exc
        return snapshot

    async def get_snapshot(self, snapshot_id: str) -> RepositorySnapshot | None:
        document = await self._database.repository_snapshots.find_one({"id": snapshot_id})
        return RepositorySnapshot.model_validate(document) if document else None

    async def get_ready_snapshot(
        self, identity: str, sha: str, parser: str, index: str
    ) -> RepositorySnapshot | None:
        document = await self._database.repository_snapshots.find_one(
            {
                "repository_identity": identity,
                "resolved_commit_sha": sha,
                "parser_version": parser,
                "index_version": index,
                "status": "READY",
            }
        )
        return RepositorySnapshot.model_validate(document) if document else None

    async def update_snapshot(self, snapshot: RepositorySnapshot) -> None:
        await self._database.repository_snapshots.update_one(
            {"id": snapshot.id}, {"$set": snapshot.model_dump(mode="python")}
        )

    async def delete_snapshot(self, snapshot_id: str) -> None:
        await self._database.repository_snapshots.delete_one({"id": snapshot_id})

    async def replace_index(self, snapshot_id: str, files: list[dict], symbols: list[dict]) -> None:
        await self._database.repository_files.delete_many({"snapshot_id": snapshot_id})
        await self._database.code_symbols.delete_many({"snapshot_id": snapshot_id})
        if files:
            await self._database.repository_files.insert_many(
                [
                    {("path" if k == "relative_path" else k): v for k, v in file.items()}
                    | {"snapshot_id": snapshot_id}
                    for file in files
                ]
            )
        if symbols:
            await self._database.code_symbols.insert_many(
                [
                    {
                        ("path" if key == "relative_path" else key): value
                        for key, value in symbol.items()
                    }
                    | {"snapshot_id": snapshot_id}
                    for symbol in symbols
                ]
            )

    async def create_plan_version(self, plan_version: PlanVersion) -> PlanVersion:
        try:
            await self._database.plan_versions.insert_one(plan_version.model_dump(mode="python"))
        except DuplicateKeyError as exc:
            raise DuplicateResourceError("plan version already exists") from exc
        return plan_version

    async def get_plan_version(self, plan_version_id: str) -> PlanVersion | None:
        document = await self._database.plan_versions.find_one({"id": plan_version_id})
        return PlanVersion.model_validate(document) if document else None

    async def create_run(self, run: VerificationRun) -> VerificationRun:
        await self._database.verification_runs.insert_one(run.model_dump(mode="python"))
        return run

    async def get_run(self, run_id: str) -> VerificationRun | None:
        document = await self._database.verification_runs.find_one({"id": run_id})
        return VerificationRun.model_validate(document) if document else None

    async def append_event(self, event: RunEvent) -> RunEvent:
        try:
            await self._database.events.insert_one(event.model_dump(mode="python"))
        except DuplicateKeyError as exc:
            raise DuplicateResourceError("run event sequence already exists") from exc
        return event

    async def get_event(self, run_id: str, sequence: int) -> RunEvent | None:
        document = await self._database.events.find_one({"run_id": run_id, "sequence": sequence})
        return RunEvent.model_validate(document) if document else None
