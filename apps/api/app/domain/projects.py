from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl, model_validator

from app.domain.common import new_id, now_utc


class RepositorySourceType(StrEnum):
    SEEDED = "seeded_fixture"
    PUBLIC_GITHUB = "public_github"


class RepositorySourceInput(BaseModel):
    type: RepositorySourceType
    repository_url: HttpUrl | None = None
    requested_ref: str | None = Field(default=None, max_length=128)
    fixture_id: str | None = Field(default=None, max_length=80)


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    owner_id: str = Field(default="local-user", min_length=1, max_length=120)
    repository_source: RepositorySourceInput | None = None
    # Flat fields remain for the Phase 1 Python API; HTTP clients use repository_source.
    repository_source_type: RepositorySourceType | None = None
    repository_url: HttpUrl | None = None
    requested_ref: str | None = Field(default=None, max_length=128)
    fixture_id: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def normalize_repository_source(self) -> CreateProjectRequest:
        if self.repository_source is not None:
            if self.repository_source_type is not None:
                raise ValueError("provide repository_source instead of flat source fields")
            self.repository_source_type = self.repository_source.type
            self.repository_url = self.repository_source.repository_url
            self.requested_ref = self.repository_source.requested_ref
            self.fixture_id = self.repository_source.fixture_id
        if self.repository_source_type is None:
            raise ValueError("repository_source is required")
        return self


class Project(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    owner_id: str
    repository_source_type: RepositorySourceType
    repository_url: str | None = None
    requested_ref: str | None = None
    fixture_id: str | None = None
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)

    @classmethod
    def from_create_request(cls, request: CreateProjectRequest) -> Project:
        if (
            request.repository_source_type == RepositorySourceType.PUBLIC_GITHUB
            and request.repository_url is None
        ):
            raise ValueError("repository_url is required for public GitHub repositories")
        if request.repository_source_type == RepositorySourceType.SEEDED and not request.fixture_id:
            raise ValueError("fixture_id is required for seeded fixtures")
        return cls(
            name=request.name.strip(),
            owner_id=request.owner_id,
            repository_source_type=request.repository_source_type,
            repository_url=str(request.repository_url) if request.repository_url else None,
            requested_ref=request.requested_ref,
            fixture_id=request.fixture_id,
        )
