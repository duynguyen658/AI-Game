from __future__ import annotations

import asyncio
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.agents.base import BaseSpecialistAgent
from app.agentic.agents.brief_analyst import BriefAnalystAgent
from app.agentic.agents.content_generator import ContentGeneratorAgent
from app.agentic.agents.content_reviewer import ContentReviewerAgent
from app.agentic.runtime.agent_loop import AgentLoop
from app.agentic.runtime.context_builder import AgentContextBuilder
from app.agentic.runtime.execution_budget import AgentExecutionBudget
from app.agentic.state.agent_state import AgentState
from app.agentic.state.campaign_context import CampaignContext
from app.agentic.tools.executor import ToolExecutor
from app.agentic.tools.registry import build_default_tool_registry
from app.core.config import Settings, get_settings
from app.core.constants import AgentRunStatus
from app.core.exceptions import (
    AgentExecutionError,
    AgentExecutionCancelledError,
    AgentIterationLimitError,
    AgentLLMCallLimitError,
    AgentTimeoutError,
    AgentToolCallLimitError,
    ApplicationError,
)
from app.llm.base import LLMClient
from app.schemas.agent_run import AgentRunCreate
from app.schemas.campaign import BriefAnalysis, GeneratedContent, QualityReview
from app.service.agent_run_service import AgentRunService
from app.service.agent_query_service import AgentReadQueryService
from app.service.workflow_service import WorkflowService

OutputT = TypeVar("OutputT", bound=BaseModel)
LIMIT_ERRORS = (
    AgentIterationLimitError,
    AgentLLMCallLimitError,
    AgentToolCallLimitError,
    AgentTimeoutError,
)


class AgenticOrchestrator:
    def __init__(
        self,
        session: AsyncSession,
        llm_client: LLMClient,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.llm_client = llm_client
        self.settings = settings or get_settings()
        self.context_builder = AgentContextBuilder(session)
        self.run_service = AgentRunService(session)
        self.workflow_service = WorkflowService(session)
        self.registry = build_default_tool_registry(AgentReadQueryService(session))
        self.budget = AgentExecutionBudget(
            max_iterations=self.settings.agent_max_iterations,
            max_llm_calls=self.settings.agent_max_llm_calls,
            max_tool_calls=self.settings.agent_max_tool_calls,
            timeout_seconds=self.settings.agent_timeout_seconds,
        )

    async def run_brief_analysis(
        self, *, campaign_id: str, workflow_id: UUID
    ) -> BriefAnalysis:
        context = await self.context_builder.build_brief_analysis_context(
            campaign_id=campaign_id, workflow_id=workflow_id
        )
        return await self._run(BriefAnalystAgent(), context)

    async def run_content_generation(
        self, *, campaign_id: str, workflow_id: UUID
    ) -> GeneratedContent:
        context = await self.context_builder.build_content_generation_context(
            campaign_id=campaign_id, workflow_id=workflow_id
        )
        return await self._run(ContentGeneratorAgent(), context)

    async def run_content_review(
        self, *, campaign_id: str, workflow_id: UUID
    ) -> QualityReview:
        context = await self.context_builder.build_content_review_context(
            campaign_id=campaign_id, workflow_id=workflow_id
        )
        return await self._run(ContentReviewerAgent(), context)

    async def _run(
        self,
        agent: BaseSpecialistAgent[OutputT],
        context: CampaignContext,
    ) -> OutputT:
        run = await self.run_service.create_run(
            AgentRunCreate(
                workflow_id=context.workflow_id,
                campaign_id=context.campaign_id,
                agent_name=agent.name,
                model=self.settings.llm_model or self.settings.llm_provider,
                prompt_version=agent.prompt_version,
            )
        )
        await self.run_service.start_run(run.agent_run_id)
        state = AgentState(
            agent_run_id=run.agent_run_id,
            workflow_id=context.workflow_id,
            campaign_id=context.campaign_id,
            agent_name=agent.name,
            status=AgentRunStatus.RUNNING,
        )
        executor = ToolExecutor(
            self.registry,
            self.run_service,
            max_result_characters=self.settings.agent_max_tool_result_characters,
        )
        loop = AgentLoop(
            llm_client=self.llm_client,
            registry=self.registry,
            executor=executor,
            run_service=self.run_service,
            reserve_workflow_llm_call=lambda: self.workflow_service.record_llm_call(
                context.workflow_id
            ),
        )
        try:
            output = await loop.run(
                agent=agent, state=state, context=context, budget=self.budget
            )
            await self.run_service.complete_run(run.agent_run_id)
            return output
        except asyncio.CancelledError:
            cancelled = AgentExecutionCancelledError("Agent execution was cancelled")
            await asyncio.shield(self.run_service.fail_run(run.agent_run_id, cancelled))
            raise
        except LIMIT_ERRORS as exc:
            await self.run_service.fail_run(run.agent_run_id, exc, limit=True)
            raise
        except Exception as exc:
            wrapped = (
                exc
                if isinstance(exc, ApplicationError)
                else AgentExecutionError("Agent specialist execution failed")
            )
            await self.run_service.fail_run(run.agent_run_id, wrapped)
            if wrapped is exc:
                raise
            raise wrapped from exc
