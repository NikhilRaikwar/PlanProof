import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, status

from app.api.dependencies import get_mongo, get_settings_dep
from app.api.github import get_optional_session
from app.core.config import Settings
from app.db.mongo import MongoManager
from app.domain.projects import RepositorySourceType
from app.domain.runs import RepositorySnapshot
from app.ingestion.service import INDEX_VERSION, PARSER_VERSION, SnapshotIngestionService
from app.ingestion.sources import InvalidRepositorySource, PublicGitHubSource, seeded_fixture_source
from app.repositories.projects import ProjectsRepository
from app.repositories.runs import RunRepository

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


def _verify_tenant_project_access(project: dict, session: dict | None) -> None:
    if not session:
        return
    proj_inst_id = project.get("github_installation_id")
    if proj_inst_id is not None:
        if proj_inst_id != session.get("installation_id"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
        return
    if project.get("owner_id") != session.get("account_login"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")


@router.post(
    "/v1/projects/{project_id}/snapshots",
    response_model=RepositorySnapshot,
    status_code=status.HTTP_201_CREATED,
)
async def create_snapshot(
    project_id: str,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    planproof_session: Annotated[str | None, Cookie()] = None,
) -> RepositorySnapshot:
    session = await get_optional_session(mongo, settings, planproof_session)
    project = await ProjectsRepository(mongo).get(project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    _verify_tenant_project_access(project.model_dump(), session)

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
    project_id: str,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    planproof_session: Annotated[str | None, Cookie()] = None,
) -> list[RepositorySnapshot]:
    session = await get_optional_session(mongo, settings, planproof_session)
    project = await ProjectsRepository(mongo).get(project_id)
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    _verify_tenant_project_access(project.model_dump(), session)

    cursor = mongo.database().repository_snapshots.find({"project_id": project_id}).sort(
        "created_at", -1
    )
    return [RepositorySnapshot.model_validate(item) async for item in cursor]


@router.get("/v1/snapshots/{snapshot_id}", response_model=RepositorySnapshot)
async def get_snapshot(
    snapshot_id: str,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    planproof_session: Annotated[str | None, Cookie()] = None,
) -> RepositorySnapshot:
    session = await get_optional_session(mongo, settings, planproof_session)
    snapshot = await RunRepository(mongo).get_snapshot(snapshot_id)
    if snapshot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "snapshot not found")
    project = await mongo.database().projects.find_one({"id": snapshot.project_id})
    if project:
        _verify_tenant_project_access(project, session)
    return snapshot

