from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import AppliedTaskStatus, AppliedWorkflowType
from app.core.exceptions import M7ResourceNotFoundError
from app.database.models import AppliedWorkflowTaskModel
from app.repositories.applied_workflow_repository import AppliedWorkflowRepository
from app.schemas.applied_workflow import AppliedTaskRead


class AppliedWorkflowService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = AppliedWorkflowRepository(session)

    async def get(self, task_run_id: UUID) -> AppliedTaskRead:
        return task_to_schema(await self.required(task_run_id))

    async def required(self, task_run_id: UUID) -> AppliedWorkflowTaskModel:
        model = await self.repository.get(task_run_id)
        if model is None:
            raise M7ResourceNotFoundError("Applied workflow task not found")
        return model

    async def list(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        owner_id: str | None = None,
        workflow_type: AppliedWorkflowType | None = None,
        status: AppliedTaskStatus | None = None,
    ) -> list[AppliedTaskRead]:
        models = await self.repository.list(
            limit=min(max(limit, 1), 100),
            offset=max(offset, 0),
            owner_id=owner_id,
            workflow_type=workflow_type.value if workflow_type else None,
            status=status.value if status else None,
        )
        return [task_to_schema(model) for model in models]

    async def complete(
        self,
        task_run_id: UUID,
        result: dict[str, Any],
        *,
        status: AppliedTaskStatus = AppliedTaskStatus.COMPLETED,
        commit: bool = True,
    ) -> AppliedTaskRead:
        model = await self.required(task_run_id)
        model.status = status.value
        model.result = result
        model.completed_at = datetime.now(UTC)
        model.duration_ms = _duration_ms(model.started_at, model.completed_at)
        if commit:
            await self.session.commit()
        return task_to_schema(model)

    async def mark_processing(
        self, task_run_id: UUID, *, commit: bool = True
    ) -> AppliedWorkflowTaskModel:
        model = await self.required(task_run_id)
        model.status = AppliedTaskStatus.PROCESSING.value
        model.started_at = model.started_at or datetime.now(UTC)
        model.error_code = None
        model.error_message = None
        if commit:
            await self.session.commit()
        return model


def task_to_schema(model: AppliedWorkflowTaskModel) -> AppliedTaskRead:
    return AppliedTaskRead.model_validate(model, from_attributes=True)


def _duration_ms(started_at: datetime | None, completed_at: datetime) -> int:
    if started_at is None:
        return 0
    return max(int((completed_at - started_at).total_seconds() * 1000), 0)
