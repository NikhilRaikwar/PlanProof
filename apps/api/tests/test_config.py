from app.core.config import Settings


def test_production_requires_mongodb_uri() -> None:
    try:
        Settings(planproof_env="production", mongodb_uri=None)
    except ValueError as exc:
        assert "MONGODB_URI is required" in str(exc)
    else:
        raise AssertionError("production settings accepted a missing MongoDB URI")


def test_production_does_not_require_redis_url() -> None:
    # Production boots without REDIS_URL when required Cloud Tasks settings are supplied
    settings = Settings(
        planproof_env="production",
        mongodb_uri="mongodb://example",
        redis_url=None,
        session_secret="dummy-session-secret-32-chars-long!",
        github_app_id="123",
        github_app_slug="app",
        github_app_private_key="key",
        github_client_id="cid",
        github_client_secret="csecret",
        planproof_gcp_project_id="planproof-ai",
        planproof_worker_service_url="https://worker.planproof.internal",
        planproof_tasks_invoker_service_account="tasks@planproof-ai.iam.gserviceaccount.com",
    )
    assert settings.redis_url is None
    assert settings.redis_is_configured is False


def test_web_origins_are_normalized_and_restrictive() -> None:
    settings = Settings(planproof_web_origins=" https://ui.example ,http://localhost:3000/ ")
    assert settings.web_origins == ["https://ui.example", "http://localhost:3000"]


def test_mongo_is_not_configured_for_blank_uri() -> None:
    settings = Settings(mongodb_uri="")
    assert settings.mongo_is_configured is False
