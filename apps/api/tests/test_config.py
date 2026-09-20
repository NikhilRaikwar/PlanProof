from app.core.config import Settings


def test_production_requires_mongodb_uri() -> None:
    try:
        Settings(planproof_env="production", mongodb_uri=None)
    except ValueError as exc:
        assert "MONGODB_URI is required" in str(exc)
    else:
        raise AssertionError("production settings accepted a missing MongoDB URI")


def test_mongo_is_not_configured_for_blank_uri() -> None:
    settings = Settings(mongodb_uri="")
    assert settings.mongo_is_configured is False
