from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import (
    get_mongo,
    get_quota_service,
    require_session,
    verify_tenant_project_access,
)
from app.db.mongo import MongoManager
from app.domain.projects import CreateProjectRequest, Project, RepositorySourceType
from app.ingestion.sources import InvalidRepositorySource, PublicGitHubSource
from app.repositories.projects import ProjectsRepository
from app.services.quotas import QuotaService

router = APIRouter(prefix="/v1/projects", tags=["projects"])


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(
    request: CreateProjectRequest,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    session: Annotated[dict, Depends(require_session)],
    quota_service: Annotated[QuotaService, Depends(get_quota_service)],
) -> Project:
    # Atomically reserve project quota for this account
    await quota_service.reserve_project_quota(session["account_login"])

    if request.repository_source_type == RepositorySourceType.PUBLIC_GITHUB:
        try:
            PublicGitHubSource.from_url(str(request.repository_url), request.requested_ref)
        except (InvalidRepositorySource, ValueError) as exc:
            await quota_service.rollback_project_quota(session["account_login"])
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="invalid repository source",
            ) from exc

    # Server-derived authority: ignore client owner_id and bind to session
    project = Project.from_create_request(request)
    project.owner_id = session["account_login"]
    project.github_installation_id = session.get("installation_id")
    project.data_scope = "USER"
    try:
        return await ProjectsRepository(mongo).create(project)
    except Exception:
        await quota_service.rollback_project_quota(session["account_login"])
        raise


@router.get("", response_model=list[Project])
async def list_projects(
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    session: Annotated[dict, Depends(require_session)],
    include_demo: bool = False,
) -> list[Project]:
    query: dict[str, Any] = {"owner_id": session["account_login"]}
    if include_demo:
        query["data_scope"] = {"$in": ["USER", "DEMO"]}
    else:
        query["data_scope"] = "USER"
    cursor = mongo.database().projects.find(query).sort("created_at", -1)
    return [Project.model_validate(item) async for item in cursor]


@router.get("/{project_id}", response_model=Project)
async def get_project(
    project_id: str,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    session: Annotated[dict, Depends(require_session)],
) -> Project:
    project = await ProjectsRepository(mongo).get(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    verify_tenant_project_access(project, session)
    return project
