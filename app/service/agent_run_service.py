from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import AgentRunStatus, ToolCallStatus
from app.core.exceptions import (
    AgentRunAlreadyActiveError,
    AgentRunNotFoundError,
    ApplicationError,
    CampaignNotFoundError,
    InvalidAgentRunTransitionError,
    InvalidToolCallTransitionError,
    PersistenceError,
    WorkflowNotFoundError,
)
from app.core.sanitization import sanitize_json, sanitize_text
from app.database.integrity import get_constraint_name
from app.database.models import AgentRunModel, AgentToolCallModel
from app.observability.metrics import (
    AGENT_FAILURES,
    AGENT_LLM_CALLS,
    AGENT_LIMIT_EXCEEDED,
    AGENT_RUN_DURATION,
    AGENT_RUNS,
    AGENT_TOOL_CALLS,
)
from app.repositories.agent_run_repository import AgentRunRepository
from app.repositories.agent_tool_call_repository import AgentToolCallRepository
from app.repositories.campaign_repository import CampaignRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.schemas.agent_run import AgentRunCreate, AgentRunRead
from app.schemas.tool_call import ToolCallRead, ToolCallRequest
from app.service.mappers import agent_run_to_schema, tool_call_to_schema


class AgentRunService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.runs = AgentRunRepository(session)
        self.tool_calls = AgentToolCallRepository(session)
        self.campaigns = CampaignRepository(session)
        self.workflows = WorkflowRepository(session)

    async def create_run(self, payload: AgentRunCreate) -> AgentRunRead:
        if await self.runs.find_active(payload.workflow_id, payload.agent_name):
            await self.session.rollback()
            raise AgentRunAlreadyActiveError("Specialist already has an active run")
        try:
            model = await self.runs.create(payload)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if get_constraint_name(exc) == "uq_agent_runs_one_active_specialist":
                raise AgentRunAlreadyActiveError(
                    "Specialist already has an active run"
                ) from exc
            raise PersistenceError("Unable to create agent run") from exc
        return agent_run_to_schema(model)

    async def get_run(self, agent_run_id: UUID) -> AgentRunRead:
        model = await self.runs.get_by_id(agent_run_id)
        if model is None:
            raise AgentRunNotFoundError("Agent run not found")
        return agent_run_to_schema(model)

    async def list_runs(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        workflow_id: UUID | None = None,
        campaign_id: str | None = None,
    ) -> list[AgentRunRead]:
        models = await self.runs.list(
            limit=min(max(limit, 1), 100),
            offset=max(offset, 0),
            workflow_id=workflow_id,
            campaign_id=campaign_id,
        )
        return [agent_run_to_schema(model) for model in models]

    async def start_run(self, agent_run_id: UUID) -> None:
        model = await self._required_run(agent_run_id)
        self._require_run_status(
            model, {AgentRunStatus.CREATED}, AgentRunStatus.RUNNING
        )
        await self.runs.update_status(model, AgentRunStatus.RUNNING)
        await self.session.commit()

    async def record_iteration(self, agent_run_id: UUID) -> None:
        model = await self._required_run(agent_run_id)
        self._require_run_status(model, {AgentRunStatus.RUNNING})
        await self.runs.increment_iteration_count(model)
        await self.session.commit()

    async def record_llm_call(self, agent_run_id: UUID) -> None:
        model = await self._required_run(agent_run_id)
        self._require_run_status(model, {AgentRunStatus.RUNNING})
        await self.runs.increment_llm_call_count(model)
        await self.session.commit()
        AGENT_LLM_CALLS.labels(model.agent_name).inc()

    async def complete_run(self, agent_run_id: UUID) -> None:
        model = await self._required_run(agent_run_id)
        self._require_run_status(
            model, {AgentRunStatus.RUNNING}, AgentRunStatus.COMPLETED
        )
        await self.runs.finish(model, AgentRunStatus.COMPLETED)
        await self.session.commit()
        AGENT_RUNS.labels(model.agent_name, AgentRunStatus.COMPLETED.value).inc()
        if model.completed_at is not None:
            AGENT_RUN_DURATION.labels(
                model.agent_name, AgentRunStatus.COMPLETED.value
            ).observe(max((model.completed_at - model.started_at).total_seconds(), 0))

    async def fail_run(
        self, agent_run_id: UUID, exc: Exception, *, limit: bool = False
    ) -> None:
        await self.session.rollback()
        model = await self._required_run(agent_run_id)
        status = AgentRunStatus.LIMIT_EXCEEDED if limit else AgentRunStatus.FAILED
        self._require_run_status(
            model,
            {AgentRunStatus.CREATED, AgentRunStatus.RUNNING},
            status,
        )
        code = (
            exc.error_code
            if isinstance(exc, ApplicationError)
            else "AGENT_EXECUTION_ERROR"
        )
        await self.runs.finish(
            model,
            status,
            error_code=code,
            error_message=sanitize_text(exc, max_characters=2000),
        )
        await self.session.commit()
        AGENT_RUNS.labels(model.agent_name, status.value).inc()
        AGENT_FAILURES.labels(model.agent_name).inc()
        if limit:
            AGENT_LIMIT_EXCEEDED.labels(code).inc()
        if model.completed_at is not None:
            AGENT_RUN_DURATION.labels(model.agent_name, status.value).observe(
                max((model.completed_at - model.started_at).total_seconds(), 0)
            )

    async def create_tool_call(self, payload: ToolCallRequest) -> ToolCallRead:
        run = await self._required_run(payload.agent_run_id)
        self._require_run_status(run, {AgentRunStatus.RUNNING})
        safe_payload = payload.model_copy(
            update={"arguments": sanitize_json(payload.arguments)}
        )
        call = await self.tool_calls.create(safe_payload)
        await self.runs.increment_tool_call_count(run)
        await self.session.commit()
        AGENT_TOOL_CALLS.labels(run.agent_name, payload.tool_name).inc()
        return tool_call_to_schema(call)

    async def start_tool_call(self, tool_call_id: UUID) -> None:
        call = await self._required_tool_call(tool_call_id)
        self._require_tool_status(
            call,
            {ToolCallStatus.REQUESTED},
            ToolCallStatus.RUNNING,
        )
        await self.tool_calls.update_status(call, ToolCallStatus.RUNNING)
        await self.session.commit()

    async def finish_tool_call(
        self,
        tool_call_id: UUID,
        *,
        status: ToolCallStatus,
        result_summary: str | None = None,
        error: Exception | None = None,
        duration_ms: int | None = None,
    ) -> None:
        await self.session.rollback()
        call = await self._required_tool_call(tool_call_id)
        allowed_from = {
            ToolCallStatus.REQUESTED,
            ToolCallStatus.RUNNING,
        }
        if status == ToolCallStatus.COMPLETED:
            allowed_from = {ToolCallStatus.RUNNING}
        elif status == ToolCallStatus.REJECTED:
            allowed_from = {ToolCallStatus.REQUESTED}
        elif status != ToolCallStatus.FAILED:
            raise InvalidToolCallTransitionError(
                f"Tool call cannot finish as {status.value}"
            )
        self._require_tool_status(call, allowed_from, status)
        code = None
        message = None
        if error is not None:
            code = (
                error.error_code
                if isinstance(error, ApplicationError)
                else "TOOL_EXECUTION_ERROR"
            )
            message = sanitize_text(error, max_characters=2000)
        await self.tool_calls.finish(
            call,
            status,
            result_summary=(
                sanitize_text(result_summary, max_characters=12_000)
                if result_summary
                else None
            ),
            error_code=code,
            error_message=message,
            duration_ms=duration_ms,
        )
        await self.session.commit()

    async def list_tool_calls(self, agent_run_id: UUID) -> list[ToolCallRead]:
        await self._required_run(agent_run_id)
        models = await self.tool_calls.list_by_agent_run(agent_run_id)
        return [tool_call_to_schema(model) for model in models]

    async def list_workflow_runs(
        self, workflow_id: UUID, *, limit: int = 20, offset: int = 0
    ) -> list[AgentRunRead]:
        if await self.workflows.get_by_id(workflow_id) is None:
            raise WorkflowNotFoundError("Workflow not found")
        return await self.list_runs(workflow_id=workflow_id, limit=limit, offset=offset)

    async def list_campaign_runs(
        self, campaign_id: str, *, limit: int = 20, offset: int = 0
    ) -> list[AgentRunRead]:
        if await self.campaigns.get_by_id(campaign_id) is None:
            raise CampaignNotFoundError("Campaign not found")
        return await self.list_runs(campaign_id=campaign_id, limit=limit, offset=offset)

    async def _required_run(self, agent_run_id: UUID) -> AgentRunModel:
        model = await self.runs.get_by_id(agent_run_id)
        if model is None:
            raise AgentRunNotFoundError("Agent run not found")
        return model

    async def _required_tool_call(self, tool_call_id: UUID) -> AgentToolCallModel:
        model = await self.tool_calls.get_by_id(tool_call_id)
        if model is None:
            raise PersistenceError("Agent tool call not found")
        return model

    def _require_run_status(
        self,
        run: AgentRunModel,
        allowed: set[AgentRunStatus],
        target: AgentRunStatus | None = None,
    ) -> None:
        current = AgentRunStatus(run.status)
        if current not in allowed:
            suffix = f" to {target.value}" if target else ""
            raise InvalidAgentRunTransitionError(
                f"Agent run cannot transition from {current.value}{suffix}"
            )

    def _require_tool_status(
        self,
        call: AgentToolCallModel,
        allowed: set[ToolCallStatus],
        target: ToolCallStatus,
    ) -> None:
        current = ToolCallStatus(call.status)
        if current not in allowed:
            raise InvalidToolCallTransitionError(
                f"Tool call cannot transition from {current.value} to {target.value}"
            )
