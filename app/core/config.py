from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Cyber Legends AI Workflow"
    app_env: Literal["development", "testing", "production"] = "development"
    app_debug: bool = False
    # Configurable API bind host for local/container runtime.
    app_host: str = "0.0.0.0"  # nosec B104
    app_port: int = 8000

    postgres_db: str = "cyber_legends"
    postgres_user: str = "cyber_legends"
    postgres_password: SecretStr = SecretStr("change-me")
    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5432, ge=1, le=65535)

    database_url: str = (
        "postgresql+asyncpg://cyber_legends:change-me@localhost:5432/cyber_legends"
    )
    database_echo: bool = False
    database_pool_size: int = Field(default=10, ge=1)
    database_max_overflow: int = Field(default=20, ge=0)
    database_pool_timeout_seconds: int = Field(default=30, ge=1)

    llm_provider: Literal["openai", "mock", "gemini", "anthropic"] = "mock"
    llm_api_key: SecretStr | None = None
    llm_model: str = ""
    openai_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    llm_fallback_providers: str = ""
    llm_max_estimated_cost: float = Field(default=5.0, ge=0)
    llm_timeout_seconds: int = Field(default=60, ge=1, le=300)
    llm_max_retries: int = Field(default=2, ge=0, le=5)

    jwt_secret_key: SecretStr = SecretStr("change-me")
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    n8n_webhook_secret: SecretStr = SecretStr("change-me")
    n8n_timestamp_tolerance_seconds: int = Field(default=300, ge=30, le=3600)
    n8n_max_body_bytes: int = Field(default=1_048_576, ge=1024, le=10_485_760)
    image_provider: Literal["mock", "openai"] = "mock"
    image_model: str = "gpt-image-1"
    media_storage_root: str = "var/media"
    media_max_cost: float = Field(default=5.0, ge=0)
    max_upload_bytes: int = Field(default=5_242_880, ge=1024, le=52_428_800)
    max_csv_rows: int = Field(default=50_000, ge=1, le=1_000_000)
    max_csv_columns: int = Field(default=100, ge=1, le=1000)
    max_document_pages: int = Field(default=200, ge=1, le=2000)
    enable_real_video_generation: bool = False
    approval_token_secret: SecretStr = SecretStr("change-me")
    metrics_token: SecretStr = SecretStr("change-me")

    rate_limit_requests: int = Field(default=20, ge=1)
    rate_limit_window_seconds: int = Field(default=60, ge=1)

    max_llm_calls_per_workflow: int = Field(default=6, ge=1)
    max_content_retries: int = Field(default=2, ge=0, le=5)
    max_input_characters: int = Field(default=20_000, ge=100)

    agent_max_iterations: int = Field(default=5, ge=1, le=20)
    agent_max_llm_calls: int = Field(default=5, ge=1, le=20)
    agent_max_tool_calls: int = Field(default=8, ge=0, le=50)
    agent_timeout_seconds: int = Field(default=90, ge=1, le=300)
    agent_max_tool_result_characters: int = Field(default=12_000, ge=100, le=50_000)
    agent_max_action_proposals: int = Field(default=3, ge=0, le=10)
    action_approval_ttl_seconds: int = Field(default=3600, ge=60, le=86_400)
    action_execution_timeout_seconds: int = Field(default=60, ge=1, le=300)
    memory_max_results: int = Field(default=20, ge=1, le=100)
    memory_default_ttl_days: int = Field(default=90, ge=1, le=3650)

    job_poll_interval_seconds: float = Field(default=1.0, ge=0.05, le=60)
    job_lease_seconds: int = Field(default=60, ge=5, le=3600)
    job_heartbeat_seconds: int = Field(default=15, ge=1, le=600)
    job_max_attempts: int = Field(default=5, ge=1, le=20)
    job_retry_base_seconds: int = Field(default=5, ge=1, le=3600)
    job_retry_max_seconds: int = Field(default=300, ge=1, le=86_400)
    job_batch_size: int = Field(default=10, ge=1, le=100)
    worker_stale_after_seconds: int = Field(default=120, ge=10, le=3600)

    outbox_lease_seconds: int = Field(default=60, ge=5, le=3600)
    outbox_heartbeat_seconds: int = Field(default=15, ge=1, le=600)
    outbox_batch_size: int = Field(default=10, ge=1, le=100)
    outbox_max_attempts: int = Field(default=5, ge=1, le=20)
    outbox_retry_base_seconds: int = Field(default=5, ge=1, le=3600)
    outbox_retry_max_seconds: int = Field(default=300, ge=1, le=86_400)

    max_request_body_bytes: int = Field(default=1_048_576, ge=1024, le=10_485_760)
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:5173"
    otel_enabled: bool = False
    otel_service_name: str = "cyber-legends-api"
    outbox_ready_backlog_limit: int = Field(default=1000, ge=1)
    audit_retention_days: int = Field(default=365, ge=30, le=3650)
    application_version: str = "1.0.0-rc.1"
    prompt_version: str = "m6"
    tool_registry_version: str = "m5"
    policy_version: str = "m5"
    jwt_issuer: str | None = None
    jwt_audience: str | None = None

    log_level: str = "INFO"

    @property
    def allowed_origins(self) -> list[str]:
        return [
            value.strip()
            for value in self.cors_allowed_origins.split(",")
            if value.strip()
        ]

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use postgresql+asyncpg")
        return value

    @model_validator(mode="after")
    def validate_provider_and_secrets(self) -> "Settings":
        if self.outbox_heartbeat_seconds >= self.outbox_lease_seconds:
            raise ValueError(
                "OUTBOX_HEARTBEAT_SECONDS must be lower than OUTBOX_LEASE_SECONDS"
            )
        if self.outbox_retry_base_seconds > self.outbox_retry_max_seconds:
            raise ValueError(
                "OUTBOX_RETRY_BASE_SECONDS must not exceed OUTBOX_RETRY_MAX_SECONDS"
            )
        if self.llm_provider == "openai":
            key = self.openai_api_key or self.llm_api_key
            if not key or not key.get_secret_value():
                raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
            if not self.llm_model:
                raise ValueError("LLM_MODEL is required when LLM_PROVIDER=openai")
        if self.llm_provider == "gemini" and not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini")
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic"
            )

        if self.app_env == "production":
            unsafe_values = {
                "change-me",
                "",
            }
            secret_fields = {
                "POSTGRES_PASSWORD": self.postgres_password,
                "JWT_SECRET_KEY": self.jwt_secret_key,
                "N8N_WEBHOOK_SECRET": self.n8n_webhook_secret,
                "APPROVAL_TOKEN_SECRET": self.approval_token_secret,
                "METRICS_TOKEN": self.metrics_token,
            }
            for field_name, secret in secret_fields.items():
                if secret.get_secret_value() in unsafe_values:
                    raise ValueError(f"{field_name} must be set safely in production")

        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
