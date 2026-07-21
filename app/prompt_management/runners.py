from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.constants import (
    OutboxEventType,
    PromptExperimentStatus,
    ProviderComparisonStatus,
    ProviderName,
)
from app.core.exceptions import ApplicationError, M7ResourceNotFoundError
from app.core.sanitization import sanitize_text
from app.database.models import (
    PromptExperimentCaseResultModel,
    PromptExperimentResultModel,
    ProviderComparisonCaseResultModel,
)
from app.llm.base import LLMClient
from app.outbox.service import OutboxService
from app.prompt_management.execution import (
    aggregate_case_metrics,
    choose_winner,
    execute_prompt_case,
)
from app.repositories.evaluation_repository import EvaluationRepository
from app.repositories.prompt_experiment_repository import PromptExperimentRepository
from app.repositories.prompt_repository import PromptRepository
from app.repositories.provider_comparison_repository import (
    ProviderComparisonRepository,
)

Checkpoint = Callable[[], Any]
ProviderClientFactory = Callable[[ProviderName], LLMClient]


class PromptExperimentRunner:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        provider_client_factory: ProviderClientFactory,
    ) -> None:
        self.session_factory = session_factory
        self.provider_client_factory = provider_client_factory

    async def run(self, experiment_id: UUID, *, checkpoint: Checkpoint) -> None:
        async with self.session_factory() as session:
            experiments = PromptExperimentRepository(session)
            experiment = await experiments.get_for_update(experiment_id)
            if experiment is None:
                raise M7ResourceNotFoundError("Prompt experiment not found")
            if experiment.status == PromptExperimentStatus.COMPLETED.value:
                return
            if experiment.status == PromptExperimentStatus.CANCELLED.value:
                return
            experiment.status = PromptExperimentStatus.RUNNING.value
            experiment.started_at = experiment.started_at or datetime.now(UTC)
            control = await PromptRepository(session).get_version(
                experiment.control_version_id
            )
            candidate = await PromptRepository(session).get_version(
                experiment.candidate_version_id
            )
            cases = list(
                (await EvaluationRepository(session).list_cases(experiment.dataset_id))[
                    : experiment.sample_size
                ]
            )
            if control is None or candidate is None or not cases:
                raise M7ResourceNotFoundError("Experiment inputs are unavailable")
            provider = ProviderName(experiment.provider)
            model_name = experiment.model
            settings = dict(experiment.execution_settings)
            await session.commit()

        client = self.provider_client_factory(provider)
        for case in cases:
            for variant, version in (("control", control), ("candidate", candidate)):
                await checkpoint()
                if await self._is_completed(
                    experiment_id, case.evaluation_case_id, variant
                ):
                    continue
                try:
                    executed = await execute_prompt_case(
                        client,
                        version,
                        case,
                        model=model_name,
                        execution_settings=settings,
                    )
                except Exception as exc:
                    await self._record_experiment_case(
                        experiment_id,
                        case.evaluation_case_id,
                        version.prompt_version_id,
                        variant,
                        status="FAILED",
                        error=exc,
                    )
                    raise
                await self._record_experiment_case(
                    experiment_id,
                    case.evaluation_case_id,
                    version.prompt_version_id,
                    variant,
                    status="COMPLETED",
                    output=executed.output,
                    metrics=executed.metrics,
                )
        await self._complete_experiment(experiment_id)

    async def _is_completed(
        self, experiment_id: UUID, case_id: UUID, variant: str
    ) -> bool:
        async with self.session_factory() as session:
            status = await session.scalar(
                select(PromptExperimentCaseResultModel.status).where(
                    PromptExperimentCaseResultModel.experiment_id == experiment_id,
                    PromptExperimentCaseResultModel.evaluation_case_id == case_id,
                    PromptExperimentCaseResultModel.variant == variant,
                )
            )
            return status == "COMPLETED"

    async def _record_experiment_case(
        self,
        experiment_id: UUID,
        case_id: UUID,
        version_id: UUID,
        variant: str,
        *,
        status: str,
        output: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        async with self.session_factory() as session:
            row = await session.scalar(
                select(PromptExperimentCaseResultModel).where(
                    PromptExperimentCaseResultModel.experiment_id == experiment_id,
                    PromptExperimentCaseResultModel.evaluation_case_id == case_id,
                    PromptExperimentCaseResultModel.variant == variant,
                )
            )
            if row is None:
                row = PromptExperimentCaseResultModel(
                    experiment_id=experiment_id,
                    evaluation_case_id=case_id,
                    prompt_version_id=version_id,
                    variant=variant,
                    status=status,
                )
                session.add(row)
            row.status = status
            row.output = output
            row.metrics = metrics or {"success": 0.0, "failure": 1.0}
            row.error_code, row.error_message = _error_fields(error)
            await session.commit()

    async def _complete_experiment(self, experiment_id: UUID) -> None:
        async with self.session_factory() as session:
            repository = PromptExperimentRepository(session)
            experiment = await repository.get_for_update(experiment_id)
            if experiment is None:
                raise M7ResourceNotFoundError("Prompt experiment not found")
            if experiment.status == PromptExperimentStatus.CANCELLED.value:
                return
            rows = await repository.case_results(experiment_id)
            control_metrics = aggregate_case_metrics(
                [row.metrics for row in rows if row.variant == "control"]
            )
            candidate_metrics = aggregate_case_metrics(
                [row.metrics for row in rows if row.variant == "candidate"]
            )
            winner, reason = choose_winner(control_metrics, candidate_metrics)
            result = await repository.result(experiment_id)
            if result is None:
                result = PromptExperimentResultModel(
                    experiment_id=experiment_id,
                    control_metrics=control_metrics,
                    candidate_metrics=candidate_metrics,
                    winner=winner,
                    decision_reason=reason,
                )
                session.add(result)
            experiment.status = PromptExperimentStatus.COMPLETED.value
            experiment.completed_at = datetime.now(UTC)
            experiment.error_code = None
            experiment.error_message = None
            await OutboxService(session).add_event(
                event_type=OutboxEventType.PROMPT_EXPERIMENT_COMPLETED,
                aggregate_type="prompt_experiment",
                aggregate_id=str(experiment_id),
                payload={"experiment_id": str(experiment_id), "winner": winner},
                idempotency_key=f"prompt-experiment-completed:{experiment_id}",
            )
            await session.commit()


class ProviderComparisonRunner:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        provider_client_factory: ProviderClientFactory,
    ) -> None:
        self.session_factory = session_factory
        self.provider_client_factory = provider_client_factory

    async def run(self, comparison_id: UUID, *, checkpoint: Checkpoint) -> None:
        async with self.session_factory() as session:
            repository = ProviderComparisonRepository(session)
            comparison = await repository.get_for_update(comparison_id)
            if comparison is None:
                raise M7ResourceNotFoundError("Provider comparison not found")
            if comparison.status == ProviderComparisonStatus.COMPLETED.value:
                return
            if comparison.status == ProviderComparisonStatus.CANCELLED.value:
                return
            comparison.status = ProviderComparisonStatus.RUNNING.value
            comparison.started_at = comparison.started_at or datetime.now(UTC)
            version = await PromptRepository(session).get_version(
                comparison.prompt_version_id
            )
            cases = list(
                (await EvaluationRepository(session).list_cases(comparison.dataset_id))[
                    : comparison.sample_size
                ]
            )
            providers = [ProviderName(value) for value in comparison.providers]
            models = dict(comparison.models)
            settings = dict(comparison.execution_settings)
            if version is None or not cases:
                raise M7ResourceNotFoundError("Comparison inputs are unavailable")
            await session.commit()

        for provider in providers:
            try:
                client = self.provider_client_factory(provider)
            except Exception as exc:
                for case in cases:
                    await self._record_provider_case(
                        comparison_id,
                        case.evaluation_case_id,
                        provider,
                        models[provider.value],
                        status="FAILED",
                        error=exc,
                    )
                continue
            for case in cases:
                await checkpoint()
                if await self._provider_case_completed(
                    comparison_id, case.evaluation_case_id, provider
                ):
                    continue
                try:
                    executed = await execute_prompt_case(
                        client,
                        version,
                        case,
                        model=models[provider.value],
                        execution_settings=settings,
                    )
                except Exception as exc:
                    await self._record_provider_case(
                        comparison_id,
                        case.evaluation_case_id,
                        provider,
                        models[provider.value],
                        status="FAILED",
                        error=exc,
                    )
                    continue
                await self._record_provider_case(
                    comparison_id,
                    case.evaluation_case_id,
                    provider,
                    models[provider.value],
                    status="COMPLETED",
                    output=executed.output,
                    metrics=executed.metrics,
                )
        await self._complete_comparison(comparison_id)

    async def _provider_case_completed(
        self, comparison_id: UUID, case_id: UUID, provider: ProviderName
    ) -> bool:
        async with self.session_factory() as session:
            status = await session.scalar(
                select(ProviderComparisonCaseResultModel.status).where(
                    ProviderComparisonCaseResultModel.comparison_id == comparison_id,
                    ProviderComparisonCaseResultModel.evaluation_case_id == case_id,
                    ProviderComparisonCaseResultModel.provider == provider.value,
                )
            )
            return status == "COMPLETED"

    async def _record_provider_case(
        self,
        comparison_id: UUID,
        case_id: UUID,
        provider: ProviderName,
        model_name: str,
        *,
        status: str,
        output: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        async with self.session_factory() as session:
            row = await session.scalar(
                select(ProviderComparisonCaseResultModel).where(
                    ProviderComparisonCaseResultModel.comparison_id == comparison_id,
                    ProviderComparisonCaseResultModel.evaluation_case_id == case_id,
                    ProviderComparisonCaseResultModel.provider == provider.value,
                )
            )
            if row is None:
                row = ProviderComparisonCaseResultModel(
                    comparison_id=comparison_id,
                    evaluation_case_id=case_id,
                    provider=provider.value,
                    model=model_name,
                    status=status,
                )
                session.add(row)
            row.status = status
            row.output = output
            row.metrics = metrics or {"success": 0.0, "failure": 1.0}
            row.error_code, row.error_message = _error_fields(error)
            await session.commit()

    async def _complete_comparison(self, comparison_id: UUID) -> None:
        async with self.session_factory() as session:
            repository = ProviderComparisonRepository(session)
            comparison = await repository.get_for_update(comparison_id)
            if comparison is None:
                raise M7ResourceNotFoundError("Provider comparison not found")
            if comparison.status == ProviderComparisonStatus.CANCELLED.value:
                return
            rows = await repository.case_results(comparison_id)
            comparisons: list[dict[str, Any]] = []
            for provider in comparison.providers:
                provider_rows = [
                    row.metrics
                    for row in rows
                    if row.provider == provider and row.status == "COMPLETED"
                ]
                metrics = aggregate_case_metrics(provider_rows)
                failed_count = sum(
                    row.provider == provider and row.status == "FAILED" for row in rows
                )
                attempted_count = int(metrics["case_count"]) + failed_count
                metrics.update(
                    {
                        "attempted_case_count": attempted_count,
                        "failed_case_count": failed_count,
                        "failure_rate": (
                            failed_count / attempted_count if attempted_count else 0.0
                        ),
                    }
                )
                comparisons.append(
                    {
                        "provider": provider,
                        "model": comparison.models[provider],
                        "metrics": metrics,
                        "score": _provider_score(metrics),
                    }
                )
            successful = [
                row for row in comparisons if int(row["metrics"]["case_count"])
            ]
            if not successful:
                raise RuntimeError("All provider comparison executions failed")
            recommendation = max(successful, key=lambda row: float(row["score"]))[
                "provider"
            ]
            comparison.report = {
                "comparisons": comparisons,
                "recommended_provider": recommendation,
                "human_decision_required": True,
            }
            comparison.status = ProviderComparisonStatus.COMPLETED.value
            comparison.completed_at = datetime.now(UTC)
            comparison.error_code = None
            comparison.error_message = None
            await session.commit()


def _provider_score(metrics: dict[str, float | int]) -> float:
    return (
        float(metrics["quality_score"])
        + float(metrics["schema_validity_rate"])
        + float(metrics["success_rate"])
        - float(metrics["failure_rate"])
        - float(metrics["estimated_cost"])
        - float(metrics["latency_ms"]) * 0.0001
    )


def _error_fields(error: Exception | None) -> tuple[str | None, str | None]:
    if error is None:
        return None, None
    code = (
        error.error_code if isinstance(error, ApplicationError) else "EXECUTION_ERROR"
    )
    message = (
        error.message
        if isinstance(error, ApplicationError)
        else "Provider execution failed"
    )
    return code, sanitize_text(message, max_characters=2000)
