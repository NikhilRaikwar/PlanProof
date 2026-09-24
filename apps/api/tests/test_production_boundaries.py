from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


class MockDenyingLimiter:
    def is_allowed(self, *_args) -> bool:
        return False


class MockAllowingLimiter:
    def is_allowed(self, *_args) -> bool:
        return True


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
    app.state.rate_limiter = MockDenyingLimiter()
    with TestClient(app) as client:
        response = client.get("/probe")

    assert response.status_code == 429
    assert response.json() == {"detail": "rate limit exceeded"}


def test_boundary_errors_keep_cors_and_use_forwarded_client_bucket() -> None:
    app = _app(Settings(mongodb_uri=None, planproof_web_origins="https://web.example"))
    app.state.rate_limiter = MockDenyingLimiter()
    with TestClient(app) as client:
        response = client.get(
            "/probe",
            headers={"Origin": "https://web.example", "X-Forwarded-For": "203.0.113.8, 10.0.0.1"},
        )

    assert response.status_code == 429
    assert response.headers["access-control-allow-origin"] == "https://web.example"


def test_payload_limit_and_request_id_are_enforced() -> None:
    app = _app(Settings(mongodb_uri=None, max_request_bytes=1024))
    app.state.rate_limiter = MockAllowingLimiter()
    with TestClient(app) as client:
        oversized = client.post("/payload", content="x" * 2048)
        healthy = client.get("/probe", headers={"X-Request-ID": "test-request"})

    assert oversized.status_code == 413
    assert healthy.status_code == 200
    assert healthy.headers["X-Request-ID"] == "test-request"


def test_in_memory_rate_limiter_allows_and_throttles() -> None:
    from app.main import InMemoryRateLimiter

    limiter = InMemoryRateLimiter()
    # 3 requests allowed with limit 3
    assert limiter.is_allowed("user-1", max_requests=3, window_seconds=60) is True
    assert limiter.is_allowed("user-1", max_requests=3, window_seconds=60) is True
    assert limiter.is_allowed("user-1", max_requests=3, window_seconds=60) is True
    # 4th request throttled
    assert limiter.is_allowed("user-1", max_requests=3, window_seconds=60) is False
    # Different user allowed
    assert limiter.is_allowed("user-2", max_requests=3, window_seconds=60) is True
