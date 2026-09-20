from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_liveness_is_available_without_database_configuration() -> None:
    app = create_app(Settings(mongodb_uri=None))
    with TestClient(app) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mongo": None}


def test_readiness_fails_closed_without_database_configuration() -> None:
    app = create_app(Settings(mongodb_uri=None))
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == "database is not configured"
