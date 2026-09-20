from __future__ import annotations

from functools import lru_cache

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded only from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=("../../.env", "../../../.env", ".env"),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    planproof_env: str = Field(default="development", pattern="^(development|test|production)$")
    planproof_api_url: AnyHttpUrl = "http://localhost:8000"
    planproof_web_origin: AnyHttpUrl = "http://localhost:3000"

    mongodb_uri: SecretStr | None = None
    mongodb_database: str = Field(default="planproof", min_length=1, max_length=64)
    mongo_server_selection_timeout_ms: int = Field(default=3_000, ge=50, le=30_000)

    redis_url: SecretStr | None = SecretStr("redis://127.0.0.1:6379/0")

    verification_max_iterations: int = Field(default=4, ge=1, le=20)
    verification_max_tool_calls: int = Field(default=6, ge=1, le=30)
    verification_max_model_calls: int = Field(default=3, ge=0, le=20)
    verification_max_context_bytes: int = Field(default=64_000, ge=1_000, le=1_000_000)

    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: AnyHttpUrl = "https://openrouter.ai/api/v1"
    openrouter_primary_model: str | None = None
    aimlapi_api_key: SecretStr | None = None
    aimlapi_base_url: AnyHttpUrl = "https://api.aimlapi.com/v1"
    aimlapi_fallback_model: str | None = None

    otel_exporter_otlp_endpoint: AnyHttpUrl | None = None
    otel_service_name: str = "planproof-api"

    @model_validator(mode="after")
    def require_production_database(self) -> Settings:
        if self.planproof_env == "production" and self.mongodb_uri is None:
            raise ValueError("MONGODB_URI is required in production")
        return self

    @property
    def mongo_is_configured(self) -> bool:
        return self.mongodb_uri is not None and bool(self.mongodb_uri.get_secret_value().strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
