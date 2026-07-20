from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ToolCallStatus
from app.database.models import AgentToolCallModel
from app.schemas.tool_call import ToolCallRequest


class AgentToolCallRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, payload: ToolCallRequest) -> AgentToolCallModel:
        model = AgentToolCallModel(
            **payload.model_dump(mode="python"), status=ToolCallStatus.REQUESTED.value
        )
        self.session.add(model)
        await self.session.flush()
        return model

    async def get_by_id(self, tool_call_id: UUID) -> AgentToolCallModel | None:
        return await self.session.get(AgentToolCallModel, tool_call_id)

    async def list_by_agent_run(
        self, agent_run_id: UUID
    ) -> Sequence[AgentToolCallModel]:
        result = await self.session.execute(
            select(AgentToolCallModel)
            .where(AgentToolCallModel.agent_run_id == agent_run_id)
            .order_by(AgentToolCallModel.started_at, AgentToolCallModel.tool_call_id)
        )
        return result.scalars().all()

    async def update_status(
        self, call: AgentToolCallModel, status: ToolCallStatus
    ) -> AgentToolCallModel:
        call.status = status.value
        await self.session.flush()
        return call

    async def finish(
        self,
        call: AgentToolCallModel,
        status: ToolCallStatus,
        *,
        result_summary: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        duration_ms: int | None = None,
    ) -> AgentToolCallModel:
        call.status = status.value
        call.result_summary = result_summary
        call.error_code = error_code
        call.error_message = error_message
        call.duration_ms = duration_ms
        call.completed_at = datetime.now(UTC)
        await self.session.flush()
        return call
