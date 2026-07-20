from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.actions.registry import ActionRegistry
from app.core.config import Settings, get_settings
from app.core.constants import (
    ActionExecutionStatus,
    ActionRequestStatus,
    AgentName,
    MemoryEventType,
    PolicyDecision,
)
from app.core.exceptions import (
    ActionApprovalRequiredError,
    ActionExecutionConflictError,
    ActionExpiredError,
    ActionRequestNotFoundError,
    ActionVersionConflictError,
    ApplicationError,
    ControlledActionExecutionError,
    PolicyDeniedError,
)
from app.core.sanitization import sanitize_json, sanitize_text
from app.database.models import AgentActionExecutionModel, AgentActionRequestModel
from app.repositories.action_execution_repository import ActionExecutionRepository
from app.repositories.action_request_repository import ActionRequestRepository
from app.schemas.action_execution import ActionExecutionRead
from app.service.mappers import action_execution_to_schema
from app.service.memory_service import MemoryService


class ControlledActionExecutor:
    def __init__(
        self,
        session: AsyncSession,
        registry: ActionRegistry,
        *,
        memory_service: MemoryService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.registry = registry
        self.settings = settings or get_settings()
        self.requests = ActionRequestRepository(session)
        self.executions = ActionExecutionRepository(session)
        self.memories = memory_service or MemoryService(session, settings=self.settings)

    async def execute(
        self, action_request_id: UUID, *, expected_version: int | None = None
    ) -> ActionExecutionRead:
        request, execution = await self._reserve(
            action_request_id, expected_version=expected_version
        )
        definition = self.registry.get_for_agent(
            AgentName(request.agent_name), request.action_name
        )
        try:
            validated_input = definition.input_model.model_validate(request.arguments)
        except ValidationError as exc:
            await self._finalize_failure(request, execution, exc)
            raise ControlledActionExecutionError(
                "Action input validation failed"
            ) from exc

        started = time.monotonic()
        try:
            async with asyncio.timeout(self.settings.action_execution_timeout_seconds):
                raw_output = await definition.handler(validated_input)
            output = definition.output_model.model_validate(raw_output)
            safe_result = sanitize_json(output.model_dump(mode="json"))
            summary = sanitize_text(
                json.dumps(safe_result, ensure_ascii=True, separators=(",", ":")),
                max_characters=12_000,
            )
            return await self._finalize_success(
                request,
                execution,
                result_summary=summary,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except asyncio.CancelledError:
            await asyncio.shield(
                self._finalize_cancelled(
                    request,
                    execution,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
            )
            raise
        except TimeoutError as exc:
            wrapped = ControlledActionExecutionError("Action execution timed out")
            await self._finalize_failure(
                request,
                execution,
                wrapped,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            raise wrapped from exc
        except Exception as exc:
            wrapped = (
                exc
                if isinstance(exc, ControlledActionExecutionError)
                else ControlledActionExecutionError(
                    "Controlled action execution failed"
                )
            )
            await self._finalize_failure(
                request,
                execution,
                wrapped,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            if wrapped is exc:
                raise
            raise wrapped from exc

    async def _reserve(
        self, action_request_id: UUID, *, expected_version: int | None
    ) -> tuple[AgentActionRequestModel, AgentActionExecutionModel]:
        await self.session.rollback()
        request = await self.requests.get_by_id_for_update(action_request_id)
        if request is None:
            await self.session.rollback()
            raise ActionRequestNotFoundError("Action request not found")
        policy = PolicyDecision(request.policy_decision)
        status = ActionRequestStatus(request.status)
        if status in {
            ActionRequestStatus.EXECUTING,
            ActionRequestStatus.COMPLETED,
            ActionRequestStatus.FAILED,
        }:
            await self.session.rollback()
            raise ActionExecutionConflictError("Action has already been executed")
        if expected_version is not None and request.version != expected_version:
            await self.session.rollback()
            raise ActionVersionConflictError("Action request version is stale")
        if policy == PolicyDecision.FORBIDDEN:
            await self.session.rollback()
            raise PolicyDeniedError("Forbidden action cannot execute")
        if request.expires_at is not None and request.expires_at <= datetime.now(UTC):
            if status == ActionRequestStatus.PENDING_APPROVAL:
                await self.requests.expire(
                    action_request_id, expected_version=request.version
                )
                await self.session.commit()
            else:
                await self.session.rollback()
            raise ActionExpiredError("Action request has expired")
        if (
            policy == PolicyDecision.APPROVAL_REQUIRED
            and status != ActionRequestStatus.APPROVED
        ):
            await self.session.rollback()
            raise ActionApprovalRequiredError("Action requires human approval")
        if policy == PolicyDecision.SAFE and status != ActionRequestStatus.PROPOSED:
            await self.session.rollback()
            raise ActionExecutionConflictError("Safe action is no longer executable")
        existing = await self.executions.find_by_idempotency_key(
            request.idempotency_key
        )
        if existing is not None:
            await self.session.rollback()
            raise ActionExecutionConflictError("Action has already been executed")
        try:
            execution = await self.executions.create(
                action_request_id=request.action_request_id,
                idempotency_key=request.idempotency_key,
            )
            await self.executions.mark_running(execution)
            await self.requests.mark_executing(request)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ActionExecutionConflictError(
                "Action execution already exists"
            ) from exc
        return request, execution

    async def _finalize_success(
        self,
        request: AgentActionRequestModel,
        execution: AgentActionExecutionModel,
        *,
        result_summary: str,
        duration_ms: int,
    ) -> ActionExecutionRead:
        await self.session.rollback()
        current_request = await self._required_request(request.action_request_id)
        current_execution = await self._required_execution(
            execution.action_execution_id
        )
        await self.executions.mark_completed(
            current_execution,
            result_summary=result_summary,
            duration_ms=duration_ms,
        )
        await self.requests.mark_completed(current_request)
        await self.session.commit()
        result = action_execution_to_schema(current_execution)
        await self.memories.record_event(
            campaign_id=current_request.campaign_id,
            workflow_id=current_request.workflow_id,
            agent_run_id=current_request.agent_run_id,
            action_request_id=current_request.action_request_id,
            event_type=MemoryEventType.ACTION_COMPLETED,
            summary=result_summary,
            metadata={"action_name": current_request.action_name},
            importance=4,
        )
        return result

    async def _finalize_failure(
        self,
        request: AgentActionRequestModel,
        execution: AgentActionExecutionModel,
        error: Exception,
        *,
        duration_ms: int = 0,
    ) -> None:
        await self.session.rollback()
        current_request = await self._required_request(request.action_request_id)
        current_execution = await self._required_execution(
            execution.action_execution_id
        )
        code = (
            error.error_code
            if isinstance(error, ApplicationError)
            else "ACTION_EXECUTION_ERROR"
        )
        message = sanitize_text(error, max_characters=2000)
        await self.executions.mark_failed(
            current_execution,
            error_code=code,
            error_message=message,
            duration_ms=duration_ms,
        )
        await self.requests.mark_failed(current_request)
        await self.session.commit()
        await self.memories.record_event(
            campaign_id=current_request.campaign_id,
            workflow_id=current_request.workflow_id,
            agent_run_id=current_request.agent_run_id,
            action_request_id=current_request.action_request_id,
            event_type=MemoryEventType.ACTION_FAILED,
            summary=message,
            metadata={"action_name": current_request.action_name, "error_code": code},
            importance=5,
        )

    async def _finalize_cancelled(
        self,
        request: AgentActionRequestModel,
        execution: AgentActionExecutionModel,
        *,
        duration_ms: int,
    ) -> None:
        await self.session.rollback()
        current_request = await self._required_request(request.action_request_id)
        current_execution = await self._required_execution(
            execution.action_execution_id
        )
        message = "Action execution was cancelled"
        await self.executions.mark_cancelled(
            current_execution,
            error_message=message,
            duration_ms=duration_ms,
        )
        await self.requests.mark_failed(current_request)
        await self.session.commit()
        await self.memories.record_event(
            campaign_id=current_request.campaign_id,
            workflow_id=current_request.workflow_id,
            agent_run_id=current_request.agent_run_id,
            action_request_id=current_request.action_request_id,
            event_type=MemoryEventType.ACTION_FAILED,
            summary=message,
            metadata={"action_name": current_request.action_name, "cancelled": True},
            importance=5,
        )

    async def _required_request(self, request_id: UUID) -> AgentActionRequestModel:
        model = await self.requests.get_by_id_for_update(request_id)
        if model is None:
            raise ActionRequestNotFoundError("Action request not found")
        return model

    async def _required_execution(
        self, execution_id: UUID
    ) -> AgentActionExecutionModel:
        model = await self.executions.get_by_id(execution_id)
        if model is None:
            raise ActionExecutionConflictError("Action execution audit is missing")
        if ActionExecutionStatus(model.status) != ActionExecutionStatus.RUNNING:
            raise ActionExecutionConflictError("Action execution is already terminal")
        return model
