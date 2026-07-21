from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import AppliedTaskStatus
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
        if commit:
            await self.session.commit()
        return task_to_schema(model)


def task_to_schema(model: AppliedWorkflowTaskModel) -> AppliedTaskRead:
    return AppliedTaskRead.model_validate(model, from_attributes=True)
