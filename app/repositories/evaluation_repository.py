from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import EvaluationResultStatus, EvaluationRunStatus
from app.database.models import (
    EvaluationCaseModel,
    EvaluationDatasetModel,
    EvaluationResultModel,
    EvaluationRunModel,
)
from app.schemas.evaluation import EvaluationDatasetCreate


class EvaluationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_dataset(
        self, data: EvaluationDatasetCreate, *, created_by: str
    ) -> EvaluationDatasetModel:
        dataset = EvaluationDatasetModel(
            name=data.name,
            version=data.version,
            description=data.description,
            created_by=created_by,
        )
        self.session.add(dataset)
        await self.session.flush()
        for order, case in enumerate(data.cases):
            self.session.add(
                EvaluationCaseModel(
                    dataset_id=dataset.dataset_id,
                    name=case.name,
                    case_order=order,
                    campaign_input=case.campaign_input,
                    actual_output=case.actual_output,
                    system_config=case.system_config,
                    expected=case.expected,
                    thresholds=case.thresholds,
                    enabled=case.enabled,
                )
            )
        await self.session.flush()
        return dataset

    async def get_dataset(self, dataset_id: UUID) -> EvaluationDatasetModel | None:
        return await self.session.get(EvaluationDatasetModel, dataset_id)

    async def count_enabled_cases(self, dataset_id: UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count(EvaluationCaseModel.evaluation_case_id)).where(
                    EvaluationCaseModel.dataset_id == dataset_id,
                    EvaluationCaseModel.enabled.is_(True),
                )
            )
            or 0
        )

    async def count_cases_with_actual_output(self, dataset_id: UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count(EvaluationCaseModel.evaluation_case_id)).where(
                    EvaluationCaseModel.dataset_id == dataset_id,
                    EvaluationCaseModel.enabled.is_(True),
                    EvaluationCaseModel.actual_output.is_not(None),
                )
            )
            or 0
        )

    async def list_cases(self, dataset_id: UUID) -> Sequence[EvaluationCaseModel]:
        result = await self.session.execute(
            select(EvaluationCaseModel)
            .where(
                EvaluationCaseModel.dataset_id == dataset_id,
                EvaluationCaseModel.enabled.is_(True),
            )
            .order_by(
                EvaluationCaseModel.case_order, EvaluationCaseModel.evaluation_case_id
            )
        )
        return result.scalars().all()

    async def create_run(self, **values: object) -> EvaluationRunModel:
        model = EvaluationRunModel(**values)
        self.session.add(model)
        await self.session.flush()
        return model

    async def get_run(
        self, run_id: UUID, *, with_results: bool = False, for_update: bool = False
    ) -> EvaluationRunModel | None:
        statement = select(EvaluationRunModel).where(
            EvaluationRunModel.evaluation_run_id == run_id
        )
        if with_results:
            statement = statement.options(
                selectinload(EvaluationRunModel.results).selectinload(
                    EvaluationResultModel.case
                )
            )
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_runs(
        self, *, limit: int, offset: int
    ) -> Sequence[EvaluationRunModel]:
        result = await self.session.execute(
            select(EvaluationRunModel)
            .order_by(
                EvaluationRunModel.created_at.desc(),
                EvaluationRunModel.evaluation_run_id,
            )
            .offset(offset)
            .limit(limit)
        )
        return result.scalars().all()

    async def mark_running(self, run: EvaluationRunModel) -> None:
        run.status = EvaluationRunStatus.RUNNING.value
        run.started_at = datetime.now(UTC)
        run.error_code = None
        run.error_message = None
        await self.session.flush()

    async def upsert_result(
        self,
        *,
        run_id: UUID,
        case_id: UUID,
        status: EvaluationResultStatus,
        assertions: Mapping[str, object],
        metrics: Mapping[str, object],
        output_summary: str,
        duration_ms: int,
        input_tokens: int,
        output_tokens: int,
        estimated_cost: float,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        values = {
            "evaluation_run_id": run_id,
            "evaluation_case_id": case_id,
            "status": status.value,
            "assertions": dict(assertions),
            "metrics": dict(metrics),
            "output_summary": output_summary,
            "duration_ms": duration_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost": estimated_cost,
            "error_code": error_code,
            "error_message": error_message,
        }
        statement = insert(EvaluationResultModel).values(**values)
        await self.session.execute(
            statement.on_conflict_do_update(
                constraint="uq_evaluation_results_run_case", set_=values
            )
        )

    async def result_payloads(self, run_id: UUID) -> list[dict[str, object]]:
        result = await self.session.execute(
            select(EvaluationResultModel)
            .where(EvaluationResultModel.evaluation_run_id == run_id)
            .order_by(EvaluationResultModel.evaluation_case_id)
        )
        return [
            {
                "assertions": model.assertions,
                "metrics": model.metrics,
                "duration_ms": model.duration_ms,
                "input_tokens": model.input_tokens,
                "output_tokens": model.output_tokens,
                "estimated_cost": model.estimated_cost,
            }
            for model in result.scalars().all()
        ]
