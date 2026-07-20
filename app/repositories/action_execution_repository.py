from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ActionExecutionStatus
from app.database.models import AgentActionExecutionModel


class ActionExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self, *, action_request_id: UUID, idempotency_key: str
    ) -> AgentActionExecutionModel:
        model = AgentActionExecutionModel(
            action_request_id=action_request_id,
            idempotency_key=idempotency_key,
            status=ActionExecutionStatus.CREATED.value,
        )
        self.session.add(model)
        await self.session.flush()
        return model

    async def get_by_id(
        self, action_execution_id: UUID
    ) -> AgentActionExecutionModel | None:
        return await self.session.get(AgentActionExecutionModel, action_execution_id)

    async def list_by_request(
        self, action_request_id: UUID
    ) -> Sequence[AgentActionExecutionModel]:
        result = await self.session.execute(
            select(AgentActionExecutionModel)
            .where(AgentActionExecutionModel.action_request_id == action_request_id)
            .order_by(
                AgentActionExecutionModel.created_at,
                AgentActionExecutionModel.action_execution_id,
            )
        )
        return result.scalars().all()

    async def find_by_idempotency_key(
        self, idempotency_key: str
    ) -> AgentActionExecutionModel | None:
        result = await self.session.execute(
            select(AgentActionExecutionModel).where(
                AgentActionExecutionModel.idempotency_key == idempotency_key
            )
        )
        return result.scalar_one_or_none()

    async def mark_running(
        self, execution: AgentActionExecutionModel
    ) -> AgentActionExecutionModel:
        execution.status = ActionExecutionStatus.RUNNING.value
        execution.started_at = datetime.now(UTC)
        await self.session.flush()
        return execution

    async def mark_completed(
        self,
        execution: AgentActionExecutionModel,
        *,
        result_summary: str,
        duration_ms: int,
    ) -> AgentActionExecutionModel:
        execution.status = ActionExecutionStatus.COMPLETED.value
        execution.result_summary = result_summary
        execution.duration_ms = duration_ms
        execution.completed_at = datetime.now(UTC)
        await self.session.flush()
        return execution

    async def mark_failed(
        self,
        execution: AgentActionExecutionModel,
        *,
        error_code: str,
        error_message: str,
        duration_ms: int,
    ) -> AgentActionExecutionModel:
        execution.status = ActionExecutionStatus.FAILED.value
        execution.error_code = error_code
        execution.error_message = error_message
        execution.duration_ms = duration_ms
        execution.completed_at = datetime.now(UTC)
        await self.session.flush()
        return execution

    async def mark_cancelled(
        self,
        execution: AgentActionExecutionModel,
        *,
        error_message: str,
        duration_ms: int,
    ) -> AgentActionExecutionModel:
        execution.status = ActionExecutionStatus.CANCELLED.value
        execution.error_code = "ACTION_CANCELLED"
        execution.error_message = error_message
        execution.duration_ms = duration_ms
        execution.completed_at = datetime.now(UTC)
        await self.session.flush()
        return execution
