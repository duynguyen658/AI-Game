from __future__ import annotations

import hashlib
import json
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.constants import (
    EvaluationExecutionMode,
    EvaluationResultStatus,
    EvaluationRunStatus,
    OutboxEventType,
)
from app.core.exceptions import EvaluationConflictError, EvaluationNotFoundError
from app.core.sanitization import sanitize_text
from app.database.models import EvaluationDatasetModel, EvaluationRunModel
from app.observability.context import get_context_value
from app.outbox.service import OutboxService
from app.repositories.evaluation_repository import EvaluationRepository
from app.schemas.evaluation import (
    EvaluationDatasetCreate,
    EvaluationDatasetRead,
    EvaluationResultRead,
    EvaluationRunRead,
)


class EvaluationService:
    def __init__(
        self, session: AsyncSession, *, settings: Settings | None = None
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repository = EvaluationRepository(session)
        self.outbox = OutboxService(session, settings=self.settings)

    async def create_dataset(
        self, data: EvaluationDatasetCreate, *, actor_id: str
    ) -> EvaluationDatasetRead:
        try:
            model = await self.repository.create_dataset(
                data, created_by=sanitize_text(actor_id, max_characters=200)
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise EvaluationConflictError(
                "Evaluation dataset version already exists"
            ) from exc
        return dataset_to_schema(model, case_count=len(data.cases))

    async def request_run(
        self,
        dataset_id: UUID,
        *,
        execution_mode: EvaluationExecutionMode = EvaluationExecutionMode.SYSTEM,
        actor_id: str,
    ) -> EvaluationRunRead:
        dataset = await self.repository.get_dataset(dataset_id)
        if dataset is None:
            raise EvaluationNotFoundError("Evaluation dataset not found")
        total_cases = await self.repository.count_enabled_cases(dataset_id)
        if total_cases == 0:
            raise EvaluationConflictError("Evaluation dataset has no enabled cases")
        if (
            execution_mode == EvaluationExecutionMode.SYSTEM
            and await self.repository.count_cases_with_actual_output(dataset_id) > 0
        ):
            raise EvaluationConflictError(
                "SYSTEM evaluation cases cannot contain client-supplied actual output"
            )
        provider = (
            "mock"
            if execution_mode == EvaluationExecutionMode.SYSTEM
            else self.settings.llm_provider
        )
        material = json.dumps(
            {
                "provider": provider,
                "model": self.settings.llm_model or provider,
                "timeout": self.settings.llm_timeout_seconds,
                "execution_mode": execution_mode.value,
            },
            sort_keys=True,
        )
        correlation_id = get_context_value("correlation_id") or str(uuid4())
        run = await self.repository.create_run(
            dataset_id=dataset_id,
            status=EvaluationRunStatus.PENDING.value,
            execution_mode=execution_mode.value,
            dataset_version=dataset.version,
            model_name=(
                "mock"
                if execution_mode == EvaluationExecutionMode.SYSTEM
                else self.settings.llm_model or "mock"
            ),
            model_configuration_hash=hashlib.sha256(material.encode()).hexdigest(),
            prompt_version=self.settings.prompt_version,
            tool_registry_version=self.settings.tool_registry_version,
            policy_version=self.settings.policy_version,
            application_version=self.settings.application_version,
            total_cases=total_cases,
            completed_cases=0,
            created_by=sanitize_text(actor_id, max_characters=200),
            correlation_id=correlation_id,
        )
        await self.outbox.add_event(
            event_type=OutboxEventType.EVALUATION_REQUESTED,
            aggregate_type="evaluation_run",
            aggregate_id=str(run.evaluation_run_id),
            payload={"evaluation_run_id": str(run.evaluation_run_id)},
            idempotency_key=f"evaluation-run:{run.evaluation_run_id}:requested",
            correlation_id=correlation_id,
        )
        await self.session.commit()
        return evaluation_run_to_schema(run)

    async def get(self, run_id: UUID) -> EvaluationRunRead:
        model = await self.repository.get_run(run_id, with_results=True)
        if model is None:
            raise EvaluationNotFoundError("Evaluation run not found")
        await self.session.commit()
        return evaluation_run_to_schema(model, include_results=True)

    async def list(
        self, *, limit: int = 20, offset: int = 0
    ) -> list[EvaluationRunRead]:
        models = await self.repository.list_runs(
            limit=min(max(limit, 1), 100), offset=max(offset, 0)
        )
        await self.session.commit()
        return [evaluation_run_to_schema(model) for model in models]


def dataset_to_schema(
    model: EvaluationDatasetModel, *, case_count: int
) -> EvaluationDatasetRead:
    return EvaluationDatasetRead(
        dataset_id=model.dataset_id,
        name=model.name,
        version=model.version,
        description=model.description,
        case_count=case_count,
        created_by=model.created_by,
        created_at=model.created_at,
    )


def evaluation_run_to_schema(
    model: EvaluationRunModel, *, include_results: bool = False
) -> EvaluationRunRead:
    results = []
    if include_results:
        results = [
            EvaluationResultRead(
                evaluation_result_id=result.evaluation_result_id,
                evaluation_case_id=result.evaluation_case_id,
                case_name=result.case.name,
                status=EvaluationResultStatus(result.status),
                assertions=result.assertions,
                metrics=result.metrics,
                output_summary=result.output_summary,
                duration_ms=result.duration_ms,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                estimated_cost=result.estimated_cost,
                error_code=result.error_code,
                error_message=result.error_message,
            )
            for result in sorted(model.results, key=lambda item: item.case.case_order)
        ]
    return EvaluationRunRead(
        evaluation_run_id=model.evaluation_run_id,
        dataset_id=model.dataset_id,
        status=EvaluationRunStatus(model.status),
        execution_mode=EvaluationExecutionMode(model.execution_mode),
        dataset_version=model.dataset_version,
        model_name=model.model_name,
        model_configuration_hash=model.model_configuration_hash,
        prompt_version=model.prompt_version,
        tool_registry_version=model.tool_registry_version,
        policy_version=model.policy_version,
        application_version=model.application_version,
        total_cases=model.total_cases,
        completed_cases=model.completed_cases,
        metrics=model.metrics,
        regression_passed=model.regression_passed,
        correlation_id=model.correlation_id,
        created_by=model.created_by,
        created_at=model.created_at,
        started_at=model.started_at,
        completed_at=model.completed_at,
        error_code=model.error_code,
        error_message=model.error_message,
        results=results,
    )
