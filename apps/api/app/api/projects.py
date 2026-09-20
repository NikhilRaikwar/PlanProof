from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_mongo
from app.db.mongo import MongoManager
from app.domain.projects import CreateProjectRequest, Project, RepositorySourceType
from app.ingestion.sources import InvalidRepositorySource, PublicGitHubSource
from app.repositories.projects import ProjectsRepository

router = APIRouter(prefix="/v1/projects", tags=["projects"])


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(
    request: CreateProjectRequest,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
) -> Project:
    if request.repository_source_type == RepositorySourceType.PUBLIC_GITHUB:
        try:
            PublicGitHubSource.from_url(str(request.repository_url), request.requested_ref)
        except (InvalidRepositorySource, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="invalid repository source",
            ) from exc
    project = Project.from_create_request(request)
    return await ProjectsRepository(mongo).create(project)


@router.get("/{project_id}", response_model=Project)
async def get_project(
    project_id: str,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
) -> Project:
    project = await ProjectsRepository(mongo).get(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    return project
