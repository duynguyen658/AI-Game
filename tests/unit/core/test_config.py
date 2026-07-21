import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_mock_llm_does_not_require_api_key() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user:pass@localhost:5432/app",
        llm_provider="mock",
        llm_api_key=None,
        llm_model="",
    )

    assert settings.llm_provider == "mock"


def test_openai_provider_requires_api_key_and_model() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://user:pass@localhost:5432/app",
            llm_provider="openai",
            llm_api_key=None,
            llm_model="",
        )


def test_production_rejects_unsafe_default_secrets() -> None:
    with pytest.raises(ValidationError, match="must be set safely"):
        Settings(
            _env_file=None,
            app_env="production",
            database_url="postgresql+asyncpg://user:pass@localhost:5432/app",
            llm_provider="mock",
            postgres_password="change-me",
            jwt_secret_key="change-me",
            n8n_webhook_secret="change-me",
            approval_token_secret="change-me",
        )


def test_production_rejects_default_metrics_token() -> None:
    with pytest.raises(ValidationError, match="METRICS_TOKEN"):
        Settings(
            _env_file=None,
            app_env="production",
            database_url="postgresql+asyncpg://user:pass@localhost:5432/app",
            llm_provider="mock",
            postgres_password="safe-postgres-password",
            jwt_secret_key="safe-jwt-secret",
            n8n_webhook_secret="safe-webhook-secret",
            approval_token_secret="safe-approval-secret",
            metrics_token="change-me",
        )


def test_database_url_must_use_async_postgres() -> None:
    with pytest.raises(ValidationError, match="postgresql\\+asyncpg"):
        Settings(
            _env_file=None,
            database_url="sqlite+aiosqlite:///app.db",
            llm_provider="mock",
        )


def test_production_rejects_demo_provider_aliases() -> None:
    with pytest.raises(ValidationError, match="DEMO_PROVIDER_ALIASES"):
        Settings(
            _env_file=None,
            app_env="production",
            database_url="postgresql+asyncpg://user:pass@localhost:5432/app",
            llm_provider="mock",
            postgres_password="safe-postgres-password",
            jwt_secret_key="safe-jwt-secret",
            n8n_webhook_secret="safe-webhook-secret",
            approval_token_secret="safe-approval-secret",
            metrics_token="safe-metrics-token",
            jwt_algorithm="RS256",
            jwt_jwks_url="https://identity.example.test/.well-known/jwks.json",
            jwt_issuer="https://identity.example.test",
            jwt_audience="cyber-legends",
            demo_provider_aliases=True,
        )


def test_outbox_heartbeat_and_retry_ranges_must_be_safe() -> None:
    with pytest.raises(ValidationError, match="OUTBOX_HEARTBEAT_SECONDS"):
        Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://user:pass@localhost:5432/app",
            outbox_lease_seconds=10,
            outbox_heartbeat_seconds=10,
        )
    with pytest.raises(ValidationError, match="OUTBOX_RETRY_BASE_SECONDS"):
        Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://user:pass@localhost:5432/app",
            outbox_retry_base_seconds=20,
            outbox_retry_max_seconds=10,
        )
