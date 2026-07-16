from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Cyber Legends AI Workflow"
    app_env: Literal["development", "testing", "production"] = "development"
    app_debug: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    database_url: str = "sqlite+aiosqlite:///./cyber_legends.db"

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

    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()