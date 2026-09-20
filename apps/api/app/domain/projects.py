from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl

from app.domain.common import new_id, now_utc


class RepositorySourceType(StrEnum):
    SEEDED = "SEEDED"
    PUBLIC_GITHUB = "PUBLIC_GITHUB"


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    owner_id: str = Field(min_length=1, max_length=120)
    repository_source_type: RepositorySourceType
    repository_url: HttpUrl | None = None


class Project(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    owner_id: str
    repository_source_type: RepositorySourceType
    repository_url: str | None = None
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)

    @classmethod
    def from_create_request(cls, request: CreateProjectRequest) -> Project:
        if (
            request.repository_source_type == RepositorySourceType.PUBLIC_GITHUB
            and request.repository_url is None
        ):
            raise ValueError("repository_url is required for public GitHub repositories")
        return cls(
            name=request.name.strip(),
            owner_id=request.owner_id,
            repository_source_type=request.repository_source_type,
            repository_url=str(request.repository_url) if request.repository_url else None,
        )
