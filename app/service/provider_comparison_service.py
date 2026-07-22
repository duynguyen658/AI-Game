from __future__ import annotations

import builtins
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.constants import JobType, ProviderComparisonStatus, ProviderName
from app.core.exceptions import (
    M7ConflictError,
    M7ResourceNotFoundError,
    M7ValidationError,
)
from app.core.sanitization import sanitize_json
from app.database.models import ProviderComparisonModel
from app.jobs.definitions import ProviderComparisonRunJobPayload
from app.jobs.queue import JobQueue
from app.llm.registry import ProviderRegistry, build_provider_registry
from app.repositories.evaluation_repository import EvaluationRepository
from app.repositories.prompt_repository import PromptRepository
from app.repositories.provider_comparison_repository import (
    ProviderComparisonRepository,
)
from app.schemas.provider import (
    ProviderComparisonCaseRead,
    ProviderComparisonCreate,
    ProviderComparisonRead,
    ProviderComparisonRun,
)
from app.service.auth_service import AuthenticatedActor


class ProviderComparisonService:
    def __init__(
        self,
        session: AsyncSession | None = None,
        *,
        settings: Settings | None = None,
        registry: ProviderRegistry | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.registry = registry or build_provider_registry(self.settings)

    def catalog(self) -> list[dict[str, object]]:
        return self.registry.catalog()

    async def create(
        self, data: ProviderComparisonCreate, *, actor: AuthenticatedActor
    ) -> ProviderComparisonRead:
        session = self._session()
        providers = list(dict.fromkeys(data.providers))
        if len(providers) != len(data.providers):
            raise M7ValidationError("Comparison providers must be unique")
        if set(data.model_by_provider) != set(providers):
            raise M7ValidationError("Every provider requires exactly one model")
        _validate_execution_settings(data.execution_settings)
        for provider in providers:
            self.registry.validate(provider, structured_output=True)
        version = await PromptRepository(session).get_version(data.prompt_version_id)
        if version is None:
            raise M7ResourceNotFoundError("Prompt version not found")
        evaluations = EvaluationRepository(session)
        dataset = await evaluations.get_dataset(data.dataset_id)
        if dataset is None:
            raise M7ResourceNotFoundError("Evaluation dataset not found")
        if data.sample_size > await evaluations.count_enabled_cases(data.dataset_id):
            raise M7ValidationError("Sample size exceeds enabled evaluation cases")
        model = ProviderComparisonModel(
            prompt_version_id=data.prompt_version_id,
            dataset_id=data.dataset_id,
            dataset_version=dataset.version,
            providers=[provider.value for provider in providers],
            models={
                provider.value: data.model_by_provider[provider]
                for provider in providers
            },
            sample_size=data.sample_size,
            execution_settings=sanitize_json(data.execution_settings),
            status=ProviderComparisonStatus.DRAFT.value,
            created_by=actor.actor_id,
        )
        await ProviderComparisonRepository(session).create(model)
        await session.commit()
        return comparison_to_schema(model)

    async def get(self, comparison_id: UUID) -> ProviderComparisonRead:
        return comparison_to_schema(await self._required(comparison_id))

    async def list(self, *, limit: int, offset: int) -> list[ProviderComparisonRead]:
        models = await ProviderComparisonRepository(self._session()).list(
            limit=min(limit, 100), offset=max(offset, 0)
        )
        return [comparison_to_schema(model) for model in models]

    async def run(
        self,
        comparison_id: UUID,
        data: ProviderComparisonRun,
        *,
        actor: AuthenticatedActor,
    ) -> ProviderComparisonRead:
        del data
        session = self._session()
        repository = ProviderComparisonRepository(session)
        model = await repository.get_for_update(comparison_id)
        if model is None:
            raise M7ResourceNotFoundError("Provider comparison not found")
        if model.status != ProviderComparisonStatus.DRAFT.value:
            raise M7ConflictError("Only draft provider comparisons can run")
        model.status = ProviderComparisonStatus.RUNNING.value
        model.started_at = datetime.now(UTC)
        job = await JobQueue(session, settings=self.settings).enqueue(
            JobType.PROVIDER_COMPARISON_RUN,
            ProviderComparisonRunJobPayload(comparison_id=comparison_id),
            created_by=actor.actor_id,
            idempotency_key=f"provider-comparison:{comparison_id}",
            commit=False,
        )
        model.job_id = job.job_id
        await session.commit()
        return comparison_to_schema(model)

    async def cancel(self, comparison_id: UUID) -> ProviderComparisonRead:
        session = self._session()
        repository = ProviderComparisonRepository(session)
        model = await repository.get_for_update(comparison_id)
        if model is None:
            raise M7ResourceNotFoundError("Provider comparison not found")
        if model.status not in {
            ProviderComparisonStatus.DRAFT.value,
            ProviderComparisonStatus.RUNNING.value,
        }:
            raise M7ConflictError("Provider comparison cannot be cancelled")
        model.status = ProviderComparisonStatus.CANCELLED.value
        model.completed_at = datetime.now(UTC)
        if model.job_id is not None:
            await JobQueue(session, settings=self.settings).repository.cancel(
                model.job_id
            )
        await session.commit()
        return comparison_to_schema(model)

    async def results(
        self, comparison_id: UUID
    ) -> builtins.list[ProviderComparisonCaseRead]:
        await self._required(comparison_id)
        return [
            ProviderComparisonCaseRead.model_validate(row)
            for row in await ProviderComparisonRepository(self._session()).case_results(
                comparison_id
            )
        ]

    async def _required(self, comparison_id: UUID) -> ProviderComparisonModel:
        model = await ProviderComparisonRepository(self._session()).get(comparison_id)
        if model is None:
            raise M7ResourceNotFoundError("Provider comparison not found")
        return model

    def _session(self) -> AsyncSession:
        if self.session is None:
            raise RuntimeError("A database session is required")
        return self.session


def comparison_to_schema(model: ProviderComparisonModel) -> ProviderComparisonRead:
    return ProviderComparisonRead(
        prompt_version_id=model.prompt_version_id,
        dataset_id=model.dataset_id,
        providers=[ProviderName(provider) for provider in model.providers],
        model_by_provider={
            ProviderName(provider): model_name
            for provider, model_name in model.models.items()
        },
        sample_size=model.sample_size,
        execution_settings=model.execution_settings,
        comparison_id=model.comparison_id,
        status=model.status,
        report=model.report,
        job_id=model.job_id,
        dataset_version=model.dataset_version,
        created_by=model.created_by,
        created_at=model.created_at,
        started_at=model.started_at,
        completed_at=model.completed_at,
        error_code=model.error_code,
        error_message=model.error_message,
    )


def _validate_execution_settings(settings: dict[str, object]) -> None:
    allowed = {"temperature", "seed", "max_tokens"}
    if set(settings) - allowed:
        raise M7ValidationError("Unsupported provider comparison execution setting")
    temperature = settings.get("temperature", 0)
    if not isinstance(temperature, (int, float)) or temperature != 0:
        raise M7ValidationError("Provider comparisons require temperature 0")
