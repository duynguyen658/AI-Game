from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.agentic.state.campaign_context import CampaignContext
from app.agentic.tools.registry import ToolRegistry
from app.core.constants import AgentName, ToolCallStatus
from app.core.exceptions import (
    ApplicationError,
    ToolExecutionError,
    ToolCancelledError,
    ToolInputValidationError,
    ToolNotAllowedError,
    ToolNotFoundError,
    ToolTimeoutError,
)
from app.core.sanitization import sanitize_json
from app.llm.agent_turn import AgentToolRequest
from app.observability.tracing import traced_operation
from app.schemas.tool_call import ToolCallRequest, ToolCallResult
from app.service.agent_run_service import AgentRunService


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        run_service: AgentRunService,
        *,
        max_result_characters: int,
        timeout_seconds: int = 10,
    ) -> None:
        self.registry = registry
        self.run_service = run_service
        self.max_result_characters = max_result_characters
        self.timeout_seconds = timeout_seconds

    async def execute(
        self,
        *,
        agent_run_id: UUID,
        agent_name: AgentName,
        request: AgentToolRequest,
        context: CampaignContext,
    ) -> ToolCallResult:
        with traced_operation(
            "tool.execute",
            agent_name=agent_name.value,
            tool_name=request.tool_name,
        ):
            return await self._execute(
                agent_run_id=agent_run_id,
                agent_name=agent_name,
                request=request,
                context=context,
            )

    async def _execute(
        self,
        *,
        agent_run_id: UUID,
        agent_name: AgentName,
        request: AgentToolRequest,
        context: CampaignContext,
    ) -> ToolCallResult:
        audit = await self.run_service.create_tool_call(
            ToolCallRequest(
                agent_run_id=agent_run_id,
                tool_name=request.tool_name,
                arguments=request.arguments,
            )
        )
        started = time.monotonic()
        try:
            definition = self.registry.get_for_agent(agent_name, request.tool_name)
            self._validate_scope(request.arguments, context)
            try:
                validated_input = definition.input_model.model_validate(
                    request.arguments
                )
            except ValidationError as exc:
                raise ToolInputValidationError("Tool arguments are invalid") from exc
            await self.run_service.start_tool_call(audit.tool_call_id)
            try:
                async with asyncio.timeout(self.timeout_seconds):
                    raw_result = await definition.handler(context, validated_input)
            except TimeoutError as exc:
                raise ToolTimeoutError("Tool execution timed out") from exc
            content, summary = self._bounded_result(raw_result)
            duration = int((time.monotonic() - started) * 1000)
            await self.run_service.finish_tool_call(
                audit.tool_call_id,
                status=ToolCallStatus.COMPLETED,
                result_summary=summary,
                duration_ms=duration,
            )
            return ToolCallResult(
                tool_call_id=audit.tool_call_id,
                tool_name=request.tool_name,
                status=ToolCallStatus.COMPLETED,
                content=content,
            )
        except asyncio.CancelledError:
            cancelled = ToolCancelledError("Tool execution was cancelled")
            await asyncio.shield(
                self.run_service.finish_tool_call(
                    audit.tool_call_id,
                    status=ToolCallStatus.FAILED,
                    error=cancelled,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
            )
            raise
        except (
            ToolNotFoundError,
            ToolNotAllowedError,
            ToolInputValidationError,
        ) as exc:
            await self.run_service.finish_tool_call(
                audit.tool_call_id,
                status=ToolCallStatus.REJECTED,
                error=exc,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            raise
        except Exception as exc:
            wrapped = (
                exc
                if isinstance(exc, ApplicationError)
                else ToolExecutionError("Tool execution failed")
            )
            await self.run_service.finish_tool_call(
                audit.tool_call_id,
                status=ToolCallStatus.FAILED,
                error=wrapped,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            if wrapped is exc:
                raise
            raise wrapped from exc

    def _validate_scope(
        self, arguments: dict[str, Any], context: CampaignContext
    ) -> None:
        if arguments.get("campaign_id") != context.campaign_id:
            raise ToolNotAllowedError("Tool campaign is outside the Agent run scope")
        workflow_id = arguments.get("workflow_id")
        if workflow_id is not None and str(workflow_id) != str(context.workflow_id):
            raise ToolNotAllowedError("Tool workflow is outside the Agent run scope")

    def _bounded_result(self, value: object) -> tuple[Any, str]:
        safe = sanitize_json(value)
        serialized = json.dumps(safe, ensure_ascii=True, separators=(",", ":"))
        if len(serialized) <= self.max_result_characters:
            return safe, serialized
        summary = serialized[: self.max_result_characters] + "...[TRUNCATED]"
        return summary, summary
