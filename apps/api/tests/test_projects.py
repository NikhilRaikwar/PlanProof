import pytest

from app.domain.projects import CreateProjectRequest, Project, RepositorySourceType


def test_seeded_project_does_not_require_url() -> None:
    project = Project.from_create_request(
        CreateProjectRequest(
            name="Partial refunds demo",
            owner_id="test-owner",
            repository_source_type=RepositorySourceType.SEEDED,
        )
    )
    assert project.repository_url is None


def test_public_github_project_requires_url() -> None:
    request = CreateProjectRequest(
        name="Public repository",
        owner_id="test-owner",
        repository_source_type=RepositorySourceType.PUBLIC_GITHUB,
    )
    with pytest.raises(ValueError, match="repository_url is required"):
        Project.from_create_request(request)
