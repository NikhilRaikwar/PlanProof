from pathlib import Path
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.db.mongo import MongoManager
from app.domain.projects import CreateProjectRequest, Project, RepositorySourceType
from app.domain.runs import RepositorySnapshot
from app.ingestion.service import INDEX_VERSION, PARSER_VERSION, SnapshotIngestionService
from app.ingestion.sources import PublicGitHubSource, seeded_fixture_source
from app.repositories.projects import ProjectsRepository
from app.repositories.runs import RunRepository


@pytest.mark.integration
async def test_seeded_fixture_uses_generic_pipeline_and_persists_index() -> None:
    settings = Settings()
    if not settings.mongo_is_configured:
        pytest.skip("MONGODB_URI is not configured")
    mongo = MongoManager(settings)
    await mongo.connect()
    project = None
    snapshot = None
    try:
        project = Project.from_create_request(
            CreateProjectRequest(
                name="fixture",
                owner_id=f"itest-{uuid4().hex}",
                repository_source_type=RepositorySourceType.SEEDED,
                fixture_id="partial-refunds-v1",
            )
        )
        await ProjectsRepository(mongo).create(project)
        source = seeded_fixture_source(
            "partial-refunds-v1", Path(__file__).resolve().parents[3] / "demo-repos"
        )
        snapshot = RepositorySnapshot(
            project_id=project.id,
            repository_identity=source.identity,
            requested_ref=source.requested_ref,
            parser_version=PARSER_VERSION,
            index_version=INDEX_VERSION,
        )
        records = RunRepository(mongo)
        await records.create_snapshot(snapshot)
        snapshot = await SnapshotIngestionService(records).ingest(snapshot.id, source)
        reloaded = await records.get_snapshot(snapshot.id)
        assert (
            reloaded.status == "READY"
            and reloaded.files_indexed > 0
            and reloaded.symbols_indexed > 0
        )
        assert (
            await mongo.database().repository_files.count_documents({"snapshot_id": snapshot.id})
            == reloaded.files_indexed
        )
        assert (
            await mongo.database().code_symbols.count_documents({"snapshot_id": snapshot.id})
            == reloaded.symbols_indexed
        )
        print(
            "FIXTURE_SMOKE",
            {
                "discovered": reloaded.files_discovered,
                "indexed": reloaded.files_indexed,
                "ignored": reloaded.ignored_files,
                "symbols": reloaded.symbols_indexed,
                "root": reloaded.root_content_hash,
            },
        )
    finally:
        if snapshot and project and snapshot.project_id == project.id:
            await mongo.database().repository_files.delete_many({"snapshot_id": snapshot.id})
            await mongo.database().code_symbols.delete_many({"snapshot_id": snapshot.id})
            await mongo.database().repository_snapshots.delete_one({"id": snapshot.id})
        if project:
            await mongo.database().projects.delete_one({"id": project.id})
        await mongo.close()


def test_public_source_requires_no_token() -> None:
    source = PublicGitHubSource.from_url("https://github.com/pallets/flask", "main")
    assert source.clone_url == "https://github.com/pallets/flask.git"


@pytest.mark.integration
async def test_ready_snapshot_is_reused_after_new_mongo_client() -> None:
    settings = Settings()
    if not settings.mongo_is_configured:
        pytest.skip("MONGODB_URI is not configured")
    source = seeded_fixture_source(
        "partial-refunds-v1", Path(__file__).resolve().parents[3] / "demo-repos"
    )
    mongo = MongoManager(settings)
    await mongo.connect()
    project = first = second = None
    try:
        project = Project.from_create_request(
            CreateProjectRequest(
                name="idempotency", owner_id=f"itest-{uuid4().hex}",
                repository_source_type=RepositorySourceType.SEEDED, fixture_id="partial-refunds-v1"
            )
        )
        await ProjectsRepository(mongo).create(project)
        records = RunRepository(mongo)
        first = RepositorySnapshot(
            project_id=project.id,
            repository_identity=source.identity,
            requested_ref=source.requested_ref,
            parser_version=PARSER_VERSION,
            index_version=INDEX_VERSION,
        )
        await records.create_snapshot(first)
        first_result = await SnapshotIngestionService(records).ingest(first.id, source)
        file_count = await mongo.database().repository_files.count_documents(
            {"snapshot_id": first_result.id}
        )
        symbol_count = await mongo.database().code_symbols.count_documents(
            {"snapshot_id": first_result.id}
        )
        await mongo.close()
        mongo = MongoManager(settings)
        await mongo.connect()
        records = RunRepository(mongo)
        second = RepositorySnapshot(
            project_id=project.id,
            repository_identity=source.identity,
            requested_ref=source.requested_ref,
            parser_version=PARSER_VERSION,
            index_version=INDEX_VERSION,
        )
        await records.create_snapshot(second)
        reused = await SnapshotIngestionService(records).ingest(second.id, source)
        assert reused.id == first_result.id
        assert await records.get_snapshot(second.id) is None
        assert (
            await mongo.database().repository_files.count_documents({"snapshot_id": reused.id})
            == file_count
        )
        assert (
            await mongo.database().code_symbols.count_documents({"snapshot_id": reused.id})
            == symbol_count
        )
    finally:
        if first:
            await mongo.database().repository_files.delete_many({"snapshot_id": first.id})
            await mongo.database().code_symbols.delete_many({"snapshot_id": first.id})
            await mongo.database().repository_snapshots.delete_many(
                {"project_id": first.project_id}
            )
        if project:
            await mongo.database().projects.delete_one({"id": project.id})
        await mongo.close()


@pytest.mark.integration
async def test_public_github_repository_uses_generic_pipeline_without_credentials() -> None:
    settings = Settings()
    if not settings.mongo_is_configured:
        pytest.skip("MONGODB_URI is not configured")
    mongo = MongoManager(settings)
    await mongo.connect()
    project = snapshot = None
    try:
        source = PublicGitHubSource.from_url("https://github.com/pallets/itsdangerous", "main")
        project = Project.from_create_request(
            CreateProjectRequest(
                name="public smoke",
                owner_id=f"itest-{uuid4().hex}",
                repository_source_type=RepositorySourceType.PUBLIC_GITHUB,
                repository_url="https://github.com/pallets/itsdangerous",
                requested_ref="main",
            )
        )
        await ProjectsRepository(mongo).create(project)
        records = RunRepository(mongo)
        snapshot = RepositorySnapshot(
            project_id=project.id,
            repository_identity=source.identity,
            requested_ref=source.requested_ref,
            parser_version=PARSER_VERSION,
            index_version=INDEX_VERSION,
        )
        await records.create_snapshot(snapshot)
        snapshot = await SnapshotIngestionService(records).ingest(snapshot.id, source)
        reloaded = await records.get_snapshot(snapshot.id)
        assert reloaded.status == "READY" and len(reloaded.resolved_commit_sha) == 40
        print(
            "PUBLIC_SMOKE",
            {
                "repo": "https://github.com/pallets/itsdangerous",
                "ref": "main",
                "sha": reloaded.resolved_commit_sha,
                "discovered": reloaded.files_discovered,
                "indexed": reloaded.files_indexed,
                "symbols": reloaded.symbols_indexed,
                "root": reloaded.root_content_hash,
            },
        )
    finally:
        if snapshot and project and snapshot.project_id == project.id:
            for collection in (
                mongo.database().repository_files,
                mongo.database().code_symbols,
                mongo.database().repository_snapshots,
            ):
                await collection.delete_many(
                    {"snapshot_id": snapshot.id}
                ) if collection.name != "repository_snapshots" else await collection.delete_one(
                    {"id": snapshot.id}
                )
        if project:
            await mongo.database().projects.delete_one({"id": project.id})
        await mongo.close()
