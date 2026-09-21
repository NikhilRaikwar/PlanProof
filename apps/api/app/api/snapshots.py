import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_mongo
from app.db.mongo import MongoManager
from app.domain.projects import RepositorySourceType
from app.domain.runs import RepositorySnapshot
from app.ingestion.service import INDEX_VERSION, PARSER_VERSION, SnapshotIngestionService
from app.ingestion.sources import InvalidRepositorySource, PublicGitHubSource, seeded_fixture_source
from app.repositories.projects import ProjectsRepository
from app.repositories.runs import RunRepository

router = APIRouter(tags=["snapshots"])
_configured_fixtures_root = os.environ.get("PLANPROOF_FIXTURES_ROOT")
_FIXTURES_ROOT = (
    Path(_configured_fixtures_root)
    if _configured_fixtures_root
    else Path(__file__).resolve().parents[4] / "demo-repos"
)


@router.post(
    "/v1/projects/{project_id}/snapshots",
    response_model=RepositorySnapshot,
    status_code=status.HTTP_201_CREATED,
)
async def create_snapshot(
    project_id: str, mongo: Annotated[MongoManager, Depends(get_mongo)]
) -> RepositorySnapshot:
    project = await ProjectsRepository(mongo).get(project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    try:
        if project.repository_source_type == RepositorySourceType.PUBLIC_GITHUB:
            source = PublicGitHubSource.from_url(project.repository_url, project.requested_ref)
        else:
            source = seeded_fixture_source(project.fixture_id, _FIXTURES_ROOT)
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
    result = await SnapshotIngestionService(records).ingest(snapshot.id, source)
    return result


@router.get("/v1/projects/{project_id}/snapshots", response_model=list[RepositorySnapshot])
async def list_project_snapshots(
    project_id: str, mongo: Annotated[MongoManager, Depends(get_mongo)]
) -> list[RepositorySnapshot]:
    if not await ProjectsRepository(mongo).get(project_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    cursor = mongo.database().repository_snapshots.find({"project_id": project_id}).sort(
        "created_at", -1
    )
    return [RepositorySnapshot.model_validate(item) async for item in cursor]


@router.get("/v1/snapshots/{snapshot_id}", response_model=RepositorySnapshot)
async def get_snapshot(
    snapshot_id: str, mongo: Annotated[MongoManager, Depends(get_mongo)]
) -> RepositorySnapshot:
    snapshot = await RunRepository(mongo).get_snapshot(snapshot_id)
    if snapshot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "snapshot not found")
    return snapshot
