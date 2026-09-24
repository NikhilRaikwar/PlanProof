import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import (
    get_authorized_project,
    get_mongo,
    get_quota_service,
    get_settings_dep,
    require_session,
)
from app.core.config import Settings
from app.db.mongo import MongoManager
from app.domain.runs import RepositorySnapshot
from app.ingestion.service import INDEX_VERSION, PARSER_VERSION, SnapshotIngestionService
from app.ingestion.sources import InvalidRepositorySource, PublicGitHubSource, seeded_fixture_source
from app.repositories.projects import ProjectsRepository
from app.repositories.runs import RunRepository
from app.services.quotas import QuotaService

router = APIRouter(tags=["snapshots"])


def _resolve_fixtures_root() -> Path:
    env_root = os.environ.get("PLANPROOF_FIXTURES_ROOT")
    if env_root and Path(env_root).exists():
        return Path(env_root)
    curr = Path(__file__).resolve()
    for parent in curr.parents:
        candidate = parent / "demo-repos"
        if candidate.exists() and candidate.is_dir():
            return candidate
    return Path("/demo-repos")


_FIXTURES_ROOT = _resolve_fixtures_root()


@router.post(
    "/v1/projects/{project_id}/snapshots",
    response_model=RepositorySnapshot,
    status_code=status.HTTP_201_CREATED,
)
async def create_snapshot(
    project_id: str,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    session: Annotated[dict, Depends(require_session)],
    quota_service: Annotated[QuotaService, Depends(get_quota_service)],
) -> RepositorySnapshot:
    if not settings.planproof_ingestion_enabled:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "repository ingestion is currently paused for maintenance",
        )

    _ = await get_authorized_project(project_id, mongo, session)
    account_key = str(session.get("installation_id") or session["account_login"])
    await quota_service.reserve_snapshot_quota(account_key, session["account_login"])

    project = await ProjectsRepository(mongo).get(project_id)
    if project is None:
        raise HTTPException(404, "project not found")

    try:
        if project.repository_url:
            source = PublicGitHubSource.from_url(str(project.repository_url), project.requested_ref)
        elif project.fixture_id:
            source = seeded_fixture_source(project.fixture_id, _FIXTURES_ROOT)
        else:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "project lacks repository source"
            )
    except (InvalidRepositorySource, ValueError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid repository source"
        ) from exc

    records = RunRepository(mongo)
    snapshot = RepositorySnapshot(
        project_id=project.id,
        repository_identity=source.identity,
        source_type=source.source_type,
        requested_ref=source.requested_ref,
        parser_version=PARSER_VERSION,
        index_version=INDEX_VERSION,
    )
    await records.create_snapshot(snapshot)
    await quota_service.acquire_active_ingestion_reservation(session["account_login"], snapshot.id)
    try:
        result = await SnapshotIngestionService(records, settings=settings).ingest(snapshot.id, source)
        return result
    finally:
        await quota_service.release_active_reservation(snapshot.id)


@router.get("/v1/projects/{project_id}/snapshots", response_model=list[RepositorySnapshot])
async def list_project_snapshots(
    project_id: str,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    session: Annotated[dict, Depends(require_session)],
) -> list[RepositorySnapshot]:
    await get_authorized_project(project_id, mongo, session)

    cursor = (
        mongo.database()
        .repository_snapshots.find({"project_id": project_id})
        .sort("created_at", -1)
    )
    return [RepositorySnapshot.model_validate(item) async for item in cursor]


@router.get("/v1/snapshots/{snapshot_id}", response_model=RepositorySnapshot)
async def get_snapshot(
    snapshot_id: str,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    session: Annotated[dict, Depends(require_session)],
) -> RepositorySnapshot:
    snapshot = await RunRepository(mongo).get_snapshot(snapshot_id)
    if snapshot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "snapshot not found")
    await get_authorized_project(snapshot.project_id, mongo, session)
    return snapshot
