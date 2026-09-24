from __future__ import annotations

from functools import lru_cache
from pathlib import Path

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
    planproof_runtime_role: str = Field(default="api", pattern="^(api|worker)$")
    planproof_api_url: AnyHttpUrl = "http://localhost:8000"
    planproof_web_origins: str = "http://localhost:3000"

    mongodb_uri: SecretStr | None = None
    mongodb_database: str = Field(default="planproof", min_length=1, max_length=64)
    mongo_server_selection_timeout_ms: int = Field(default=3_000, ge=50, le=30_000)
    mongo_tls_insecure: bool = Field(default=False)

    redis_url: SecretStr | None = None

    # GitHub App credentials remain backend-only.  They are optional during
    # local development so the rest of PlanProof can still run without an App.
    github_app_id: str | None = None
    github_app_slug: str | None = None
    github_app_private_key: SecretStr | None = None
    github_callback_url: AnyHttpUrl | None = None
    session_secret: SecretStr | None = None
    session_cookie_secure: bool = False

    verification_max_iterations: int = Field(default=20, ge=1, le=20)
    verification_max_tool_calls: int = Field(default=20, ge=1, le=30)
    verification_max_model_calls: int = Field(default=3, ge=0, le=20)
    verification_max_context_bytes: int = Field(default=64_000, ge=1_000, le=1_000_000)
    max_request_bytes: int = Field(default=1_000_000, ge=1_024, le=10_000_000)
    # A live run report makes bounded persisted-projection reads while SSE
    # reconnects.  Sixty requests/minute denies one normal browser session;
    # 300 still provides a finite unauthenticated abuse boundary.
    rate_limit_requests: int = Field(default=1200, ge=1, le=10_000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3_600)

    # Public Beta feature switches and quotas
    planproof_verification_enabled: bool = True
    planproof_ingestion_enabled: bool = True
    planproof_free_runs_per_day: int = Field(default=3, ge=1, le=100)
    planproof_free_runs_per_month: int = Field(default=10, ge=1, le=1000)
    planproof_global_runs_per_day: int = Field(default=30, ge=1, le=10000)
    planproof_max_active_runs_per_account: int = Field(default=1, ge=1, le=10)
    planproof_max_active_runs_per_project: int = Field(default=1, ge=1, le=10)
    planproof_max_projects_per_account: int = Field(default=3, ge=1, le=50)
    planproof_max_project_creations_per_account: int = Field(default=3, ge=1, le=50)
    planproof_snapshots_per_day: int = Field(default=5, ge=1, le=50)
    planproof_max_active_ingestions_per_account: int = Field(default=1, ge=1, le=10)
    planproof_max_repo_files: int = Field(default=2000, ge=10, le=50000)
    planproof_max_manifest_entries: int = Field(default=10000, ge=10, le=100000)
    planproof_max_indexed_bytes: int = Field(default=15_000_000, ge=1000, le=100_000_000)
    planproof_max_repo_workspace_bytes: int = Field(default=200_000_000, ge=10000, le=1_000_000_000)
    planproof_max_model_output_tokens: int = Field(default=3000, ge=100, le=8192)
    planproof_max_provider_attempts_per_run: int = Field(default=6, ge=1, le=20)

    # GitHub OAuth / User authorization credentials (canonical names)
    github_client_id: str | None = None
    github_client_secret: SecretStr | None = None

    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: AnyHttpUrl = "https://openrouter.ai/api/v1"
    openrouter_primary_model: str = Field(default="openai/gpt-4.1-mini")
    aimlapi_api_key: SecretStr | None = None
    aimlapi_base_url: AnyHttpUrl = "https://api.aimlapi.com/v1"
    aimlapi_fallback_model: str = Field(default="gpt-4.1-mini")

    otel_exporter_otlp_endpoint: AnyHttpUrl | None = None
    otel_service_name: str = "planproof-api"

    # Cloud Tasks & Scale-to-Zero Worker Service configuration
    planproof_gcp_project_id: str | None = None
    planproof_cloud_tasks_location: str = "asia-south1"
    planproof_cloud_tasks_queue: str = "planproof-verification"
    planproof_worker_service_url: AnyHttpUrl | None = None
    planproof_tasks_invoker_service_account: str | None = None
    planproof_scheduler_invoker_service_account: str | None = None

    @model_validator(mode="after")
    def require_production_database(self) -> Settings:
        if self.planproof_env == "production":
            self.session_cookie_secure = True
            if self.mongodb_uri is None:
                raise ValueError("MONGODB_URI is required in production")
            if self.mongo_tls_insecure:
                raise ValueError("mongo_tls_insecure cannot be True in production environment")
            if self.planproof_runtime_role == "api":
                if self.session_secret is None:
                    raise ValueError("SESSION_SECRET is required in production")
                if not self.github_app_id or not self.github_app_private_key:
                    raise ValueError("GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY are required in production")
            if self.planproof_verification_enabled:
                if not self.planproof_gcp_project_id:
                    raise ValueError("PLANPROOF_GCP_PROJECT_ID is required in production for Cloud Tasks")
                if not self.planproof_worker_service_url:
                    raise ValueError("PLANPROOF_WORKER_SERVICE_URL is required in production for Cloud Tasks")
                if not self.planproof_tasks_invoker_service_account:
                    raise ValueError("PLANPROOF_TASKS_INVOKER_SERVICE_ACCOUNT is required in production for OIDC")
        return self

    @field_validator("github_app_id", "github_app_slug", mode="before")
    @classmethod
    def strip_github_app_fields(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            return value.strip()
        return value

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
    def github_app_is_configured(self) -> bool:
        return bool(
            self.github_app_id
            and self.github_app_slug
            and self.github_app_private_key
            and self.session_secret
        )

    @property
    def github_private_key_pem(self) -> str | None:
        if not self.github_app_private_key:
            return None
        val = self.github_app_private_key.get_secret_value().strip()
        try:
            p = Path(val)
            if p.exists() and p.is_file():
                return p.read_text(encoding="utf-8").strip()
        except Exception:
            pass
        if "\\n" in val and "\n" not in val:
            val = val.replace("\\n", "\n")
        return val

    @property
    def web_origins(self) -> list[str]:
        return self.planproof_web_origins.split(",")


@lru_cache
def get_settings() -> Settings:
    return Settings()
