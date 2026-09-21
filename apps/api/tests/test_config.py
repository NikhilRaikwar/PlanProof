from app.core.config import Settings


def test_production_requires_mongodb_uri() -> None:
    try:
        Settings(planproof_env="production", mongodb_uri=None)
    except ValueError as exc:
        assert "MONGODB_URI is required" in str(exc)
    else:
        raise AssertionError("production settings accepted a missing MongoDB URI")


def test_production_requires_redis_url() -> None:
    try:
        Settings(planproof_env="production", mongodb_uri="mongodb://example", redis_url=None)
    except ValueError as exc:
        assert "REDIS_URL is required" in str(exc)
    else:
        raise AssertionError("production settings accepted a missing Redis URL")


def test_web_origins_are_normalized_and_restrictive() -> None:
    settings = Settings(planproof_web_origins=" https://ui.example ,http://localhost:3000/ ")
    assert settings.web_origins == ["https://ui.example", "http://localhost:3000"]


def test_mongo_is_not_configured_for_blank_uri() -> None:
    settings = Settings(mongodb_uri="")
    assert settings.mongo_is_configured is False
