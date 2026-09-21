from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


class DenyingRedis:
    async def consume_rate_limit(self, *_args) -> bool:
        return False

    async def close(self) -> None:
        return None


class AllowingRedis:
    async def consume_rate_limit(self, *_args) -> bool:
        return True

    async def close(self) -> None:
        return None


class FailingRedis:
    async def consume_rate_limit(self, *_args) -> bool:
        raise TimeoutError("Redis unavailable")

    async def close(self) -> None:
        return None


def _app(settings: Settings):
    app = create_app(settings)

    @app.get("/probe")
    async def probe():
        return {"ok": True}

    @app.post("/payload")
    async def payload():
        return {"ok": True}

    return app


def test_rate_limit_fails_closed_without_exposing_client_data() -> None:
    app = _app(Settings(mongodb_uri=None))
    app.state.redis = DenyingRedis()
    with TestClient(app) as client:
        response = client.get("/probe")

    assert response.status_code == 429
    assert response.json() == {"detail": "rate limit exceeded"}


def test_payload_limit_and_request_id_are_enforced() -> None:
    app = _app(Settings(mongodb_uri=None, max_request_bytes=1024))
    app.state.redis = AllowingRedis()
    with TestClient(app) as client:
        oversized = client.post("/payload", content="x" * 2048)
        healthy = client.get("/probe", headers={"X-Request-ID": "test-request"})

    assert oversized.status_code == 413
    assert healthy.status_code == 200
    assert healthy.headers["X-Request-ID"] == "test-request"


def test_rate_limit_dependency_failure_is_safe_and_fail_closed() -> None:
    app = _app(Settings(mongodb_uri=None))
    app.state.redis = FailingRedis()
    with TestClient(app) as client:
        response = client.get("/probe")

    assert response.status_code == 503
    assert response.json() == {"detail": "required dependency is unavailable"}
