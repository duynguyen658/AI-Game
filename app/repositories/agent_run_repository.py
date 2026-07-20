from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import AgentName, AgentRunStatus
from app.database.models import AgentRunModel
from app.schemas.agent_run import AgentRunCreate


class AgentRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, payload: AgentRunCreate) -> AgentRunModel:
        model = AgentRunModel(
            **payload.model_dump(mode="python"), status=AgentRunStatus.CREATED.value
        )
        self.session.add(model)
        await self.session.flush()
        return model

    async def get_by_id(self, agent_run_id: UUID) -> AgentRunModel | None:
        return await self.session.get(AgentRunModel, agent_run_id)

    async def find_active(
        self, workflow_id: UUID, agent_name: AgentName
    ) -> AgentRunModel | None:
        result = await self.session.execute(
            select(AgentRunModel)
            .where(AgentRunModel.workflow_id == workflow_id)
            .where(AgentRunModel.agent_name == agent_name.value)
            .where(
                AgentRunModel.status.in_(
                    [AgentRunStatus.CREATED.value, AgentRunStatus.RUNNING.value]
                )
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        workflow_id: UUID | None = None,
        campaign_id: str | None = None,
    ) -> Sequence[AgentRunModel]:
        query: Select[tuple[AgentRunModel]] = select(AgentRunModel)
        if workflow_id is not None:
            query = query.where(AgentRunModel.workflow_id == workflow_id)
        if campaign_id is not None:
            query = query.where(AgentRunModel.campaign_id == campaign_id)
        result = await self.session.execute(
            query.order_by(
                AgentRunModel.started_at.desc(), AgentRunModel.agent_run_id.desc()
            )
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def update_status(
        self, run: AgentRunModel, status: AgentRunStatus
    ) -> AgentRunModel:
        run.status = status.value
        await self.session.flush()
        return run

    async def increment_iteration_count(self, run: AgentRunModel) -> AgentRunModel:
        run.iteration_count += 1
        await self.session.flush()
        return run

    async def increment_llm_call_count(self, run: AgentRunModel) -> AgentRunModel:
        run.llm_call_count += 1
        await self.session.flush()
        return run

    async def increment_tool_call_count(self, run: AgentRunModel) -> AgentRunModel:
        run.tool_call_count += 1
        await self.session.flush()
        return run

    async def finish(
        self,
        run: AgentRunModel,
        status: AgentRunStatus,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> AgentRunModel:
        run.status = status.value
        run.error_code = error_code
        run.error_message = error_message
        run.completed_at = datetime.now(UTC)
        await self.session.flush()
        return run
