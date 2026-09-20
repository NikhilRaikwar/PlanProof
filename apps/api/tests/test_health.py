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


def test_liveness_survives_unreachable_database_while_readiness_fails_closed() -> None:
    app = create_app(
        Settings(
            mongodb_uri="mongodb://127.0.0.1:1",
            mongo_server_selection_timeout_ms=50,
        )
    )
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == "database is unavailable"
