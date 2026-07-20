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

    llm_provider: Literal["openai", "mock"] = "mock"
    llm_api_key: SecretStr | None = None
    llm_model: str = ""
    llm_timeout_seconds: int = Field(default=60, ge=1, le=300)
    llm_max_retries: int = Field(default=2, ge=0, le=5)

    jwt_secret_key: SecretStr = SecretStr("change-me")
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    n8n_webhook_secret: SecretStr = SecretStr("change-me")
    approval_token_secret: SecretStr = SecretStr("change-me")

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

    log_level: str = "INFO"

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use postgresql+asyncpg")
        return value

    @model_validator(mode="after")
    def validate_provider_and_secrets(self) -> "Settings":
        if self.llm_provider == "openai":
            if not self.llm_api_key or not self.llm_api_key.get_secret_value():
                raise ValueError("LLM_API_KEY is required when LLM_PROVIDER=openai")
            if not self.llm_model:
                raise ValueError("LLM_MODEL is required when LLM_PROVIDER=openai")

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
