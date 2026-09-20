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
