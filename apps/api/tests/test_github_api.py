import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.domain.projects import RepositorySourceType
from app.ingestion.sources import GitHubAppSource, InvalidRepositorySource
from app.main import create_app


def test_github_connect_fails_if_app_not_configured() -> None:
    app = create_app(Settings(mongodb_uri=None, github_app_id=None))
    with TestClient(app) as client:
        response = client.get("/v1/auth/github/connect", follow_redirects=False)

    assert response.status_code == 503
    assert "GitHub connection is not configured" in response.json()["detail"]


def test_github_connect_redirects_when_app_configured() -> None:
    app = create_app(
        Settings(
            mongodb_uri=None,
            github_app_id="123456",
            github_app_slug="planproof-app",
            github_app_private_key=SecretStr("dummy-private-key"),
            session_secret=SecretStr("super-secret-key-1234567890"),
        )
    )
    with TestClient(app) as client:
        response = client.get("/v1/auth/github/connect", follow_redirects=False)

    assert response.status_code == 307
    assert (
        "https://github.com/apps/planproof-app/installations/new?state="
        in response.headers["location"]
    )
    assert "planproof_github_state" in response.cookies


def test_session_status_unauthorized_without_cookie() -> None:
    app = create_app(Settings(mongodb_uri=None))
    with TestClient(app) as client:
        response = client.get("/v1/auth/session")

    assert response.status_code == 401


def test_logout_clears_cookie() -> None:
    app = create_app(Settings(mongodb_uri=None))
    with TestClient(app) as client:
        response = client.post("/v1/auth/logout")

    assert response.status_code == 200
    assert response.json() == {"connected": False}


def test_github_app_source_validation() -> None:
    source = GitHubAppSource.from_repository("owner", "repo", "main", "token123")
    assert source.source_type == RepositorySourceType.GITHUB_APP
    assert source.identity == "github:owner/repo"
    assert source.clone_url == "https://github.com/owner/repo.git"

    with pytest.raises(InvalidRepositorySource):
        GitHubAppSource.from_repository("invalid owner!", "repo", "main", "token123")
