from __future__ import annotations

from functools import lru_cache

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
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
    planproof_web_origins: str = "http://localhost:3000"

    mongodb_uri: SecretStr | None = None
    mongodb_database: str = Field(default="planproof", min_length=1, max_length=64)
    mongo_server_selection_timeout_ms: int = Field(default=3_000, ge=50, le=30_000)

    redis_url: SecretStr | None = None

    verification_max_iterations: int = Field(default=4, ge=1, le=20)
    verification_max_tool_calls: int = Field(default=6, ge=1, le=30)
    verification_max_model_calls: int = Field(default=3, ge=0, le=20)
    verification_max_context_bytes: int = Field(default=64_000, ge=1_000, le=1_000_000)
    max_request_bytes: int = Field(default=1_000_000, ge=1_024, le=10_000_000)
    rate_limit_requests: int = Field(default=60, ge=1, le=10_000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3_600)

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
        if self.planproof_env == "production" and self.redis_url is None:
            raise ValueError("REDIS_URL is required in production")
        return self

    @field_validator("planproof_web_origins")
    @classmethod
    def validate_web_origins(cls, value: str) -> str:
        origins = [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        if not origins or any(not origin.startswith(("http://", "https://")) for origin in origins):
            raise ValueError("PLANPROOF_WEB_ORIGINS must be a comma-separated list of HTTP origins")
        return ",".join(origins)

    @property
    def mongo_is_configured(self) -> bool:
        return self.mongodb_uri is not None and bool(self.mongodb_uri.get_secret_value().strip())

    @property
    def redis_is_configured(self) -> bool:
        return self.redis_url is not None and bool(self.redis_url.get_secret_value().strip())

    @property
    def web_origins(self) -> list[str]:
        return self.planproof_web_origins.split(",")


@lru_cache
def get_settings() -> Settings:
    return Settings()
