from __future__ import annotations

from uuid import uuid4

import pytest

from app.core.config import Settings
from app.db.indexes import ensure_indexes
from app.db.mongo import MongoManager
from app.domain.projects import CreateProjectRequest, Project, RepositorySourceType
from app.domain.runs import (
    PlanVersion,
    RepositorySnapshot,
    RunEvent,
    SnapshotStatus,
    VerificationRun,
)
from app.repositories.projects import ProjectsRepository
from app.repositories.runs import RunRepository


@pytest.mark.integration
async def test_atlas_persists_and_reloads_phase_one_records() -> None:
    settings = Settings()
    if not settings.mongo_is_configured:
        pytest.skip("MONGODB_URI is not configured")

    suffix = uuid4().hex
    owner_id = f"itest-{suffix}"
    mongo = MongoManager(settings)
    restarted_mongo: MongoManager | None = None
    project: Project | None = None
    snapshot: RepositorySnapshot | None = None
    plan: PlanVersion | None = None
    run: VerificationRun | None = None
    await mongo.connect()
    database = mongo.database()

    try:
        await mongo.ping()
        await ensure_indexes(database)

        projects = ProjectsRepository(mongo)
        project = Project.from_create_request(
            CreateProjectRequest(
                name="Atlas persistence integration",
                owner_id=owner_id,
                repository_source_type=RepositorySourceType.SEEDED,
                fixture_id="partial-refunds-v1",
            )
        )
        await projects.create(project)

        records = RunRepository(mongo)
        snapshot = RepositorySnapshot(
            project_id=project.id,
            repository_identity="seeded:atlas-integration",
            requested_ref="fixture",
            resolved_commit_sha="a" * 40,
            root_content_hash="b" * 64,
            parser_version="integration-test",
            index_version="integration-test",
            status=SnapshotStatus.READY,
        )
        plan = PlanVersion(
            project_id=project.id,
            version=1,
            change_request="Verify Atlas persistence.",
            candidate_plan="Create a test record.",
        )
        run = VerificationRun(
            project_id=project.id, snapshot_id=snapshot.id, plan_version_id=plan.id
        )
        event = RunEvent(
            run_id=run.id, sequence=1, event_type="INTEGRATION", summary="Persisted safely."
        )

        await records.create_snapshot(snapshot)
        await records.create_plan_version(plan)
        await records.create_run(run)
        await records.append_event(event)

        await mongo.close()
        restarted_mongo = MongoManager(settings)
        await restarted_mongo.connect()
        restarted_records = RunRepository(restarted_mongo)

        assert (await ProjectsRepository(restarted_mongo).get(project.id)).id == project.id
        assert (
            await restarted_records.get_snapshot(snapshot.id)
        ).root_content_hash == snapshot.root_content_hash
        assert (
            await restarted_records.get_plan_version(plan.id)
        ).candidate_plan == plan.candidate_plan
        assert (await restarted_records.get_run(run.id)).snapshot_id == snapshot.id
        assert (await restarted_records.get_event(run.id, 1)).summary == event.summary

        index_cursor = await restarted_mongo.database().repository_snapshots.list_indexes()
        indexes = [index async for index in index_cursor]
        assert any(
            "resolved_commit_sha" in index.get("key", {})
            or "resolved_commit_sha" in index.get("name", "")
            for index in indexes
        )
    finally:
        cleanup_database = restarted_mongo.database() if restarted_mongo is not None else database
        if run is not None:
            await cleanup_database.events.delete_many({"run_id": run.id})
            await cleanup_database.verification_runs.delete_one({"id": run.id})
        if plan is not None:
            await cleanup_database.plan_versions.delete_one({"id": plan.id})
        if snapshot is not None:
            await cleanup_database.repository_snapshots.delete_one({"id": snapshot.id})
        if project is not None:
            await cleanup_database.projects.delete_one({"id": project.id})
        if restarted_mongo is not None:
            await restarted_mongo.close()
        await mongo.close()
