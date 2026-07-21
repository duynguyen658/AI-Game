from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.actions.definitions import ActionDefinition, ActionExecutionGuard
from app.agentic.actions.registry import ActionRegistry
from app.agentic.policies.engine import PolicyEngine
from app.core.config import Settings, get_settings
from app.core.constants import (
    ActionExecutionStatus,
    ActionRequestStatus,
    AgentName,
    CampaignStatus,
    MemoryEventType,
    MemoryRecordStatus,
    OutboxEventType,
    PolicyDecision,
    UserRole,
)
from app.core.exceptions import (
    ActionApprovalRequiredError,
    ActionExecutionConflictError,
    ActionExpiredError,
    ActionNotFoundError,
    ActionPolicyApprovalRequiredError,
    ActionPolicyReevaluationDeniedError,
    ActionRequestNotFoundError,
    ActionScopeConflictError,
    ActionVersionConflictError,
    ApplicationError,
    ControlledActionExecutionError,
    PersistenceError,
    PolicyDeniedError,
)
from app.core.sanitization import sanitize_json, sanitize_text
from app.database.models import AgentActionExecutionModel, AgentActionRequestModel
from app.database.m5_integrity import is_action_execution_duplicate
from app.outbox.service import OutboxService
from app.observability.metrics import (
    ACTION_EXECUTION_FAILURES,
    ACTION_EXECUTIONS,
)
from app.observability.tracing import traced_operation
from app.repositories.action_execution_repository import ActionExecutionRepository
from app.repositories.action_request_repository import ActionRequestRepository
from app.repositories.campaign_repository import CampaignRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.schemas.action_execution import ActionExecutionRead
from app.schemas.policy_decision import PolicyEvaluationContext
from app.service.auth_service import role_satisfies_requirement
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
        self.campaigns = CampaignRepository(session)
        self.workflows = WorkflowRepository(session)
        self.policy = PolicyEngine()
        self.memories = memory_service or MemoryService(session, settings=self.settings)
        self.outbox = OutboxService(session, settings=self.settings)

    async def execute(
        self, action_request_id: UUID, *, expected_version: int | None = None
    ) -> ActionExecutionRead:
        with traced_operation(
            "action.execute", action_request_id=str(action_request_id)
        ):
            return await self._execute(
                action_request_id, expected_version=expected_version
            )

    async def _execute(
        self, action_request_id: UUID, *, expected_version: int | None = None
    ) -> ActionExecutionRead:
        request, execution, definition, guard = await self._reserve(
            action_request_id, expected_version=expected_version
        )
        request_id = request.action_request_id
        execution_id = execution.action_execution_id
        try:
            validated_input = definition.input_model.model_validate(request.arguments)
        except ValidationError as exc:
            await self._finalize_failure(request_id, execution_id, exc)
            raise ControlledActionExecutionError(
                "Action input validation failed"
            ) from exc

        started = time.monotonic()
        try:
            async with asyncio.timeout(self.settings.action_execution_timeout_seconds):
                raw_output = await definition.handler(validated_input, guard)
            output = definition.output_model.model_validate(raw_output)
            safe_result = sanitize_json(output.model_dump(mode="json"))
            summary = sanitize_text(
                json.dumps(safe_result, ensure_ascii=True, separators=(",", ":")),
                max_characters=12_000,
            )
            return await self._finalize_success(
                request_id,
                execution_id,
                result_summary=summary,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except asyncio.CancelledError:
            await asyncio.shield(
                self._finalize_cancelled(
                    request_id,
                    execution_id,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
            )
            raise
        except TimeoutError as exc:
            timeout_error = ControlledActionExecutionError("Action execution timed out")
            await self._finalize_failure(
                request_id,
                execution_id,
                timeout_error,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            raise timeout_error from exc
        except Exception as exc:
            wrapped: ApplicationError = (
                exc
                if isinstance(exc, ApplicationError)
                else ControlledActionExecutionError(
                    "Controlled action execution failed"
                )
            )
            await self._finalize_failure(
                request_id,
                execution_id,
                wrapped,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            if wrapped is exc:
                raise
            raise wrapped from exc

    async def _reserve(
        self, action_request_id: UUID, *, expected_version: int | None
    ) -> tuple[
        AgentActionRequestModel,
        AgentActionExecutionModel,
        ActionDefinition,
        ActionExecutionGuard,
    ]:
        await self.session.rollback()
        request_hint = await self.requests.get_by_id(action_request_id)
        if request_hint is None:
            await self.session.rollback()
            raise ActionRequestNotFoundError("Action request not found")
        campaign = await self.campaigns.get_by_id_for_update(request_hint.campaign_id)
        if campaign is None:
            await self.session.rollback()
            raise ActionScopeConflictError("Action campaign scope is unavailable")
        workflow = await self.workflows.get_by_id_for_update(request_hint.workflow_id)
        if workflow is None or workflow.campaign_id != campaign.campaign_id:
            await self.session.rollback()
            raise ActionScopeConflictError("Action workflow scope is invalid")
        request = await self.requests.get_by_id_for_update(action_request_id)
        if (
            request is None
            or request.campaign_id != campaign.campaign_id
            or request.workflow_id != workflow.workflow_id
        ):
            await self.session.rollback()
            raise ActionScopeConflictError("Action request scope changed")
        status = ActionRequestStatus(request.status)
        if status == ActionRequestStatus.EXPIRED:
            await self.session.rollback()
            raise ActionExpiredError("Action request has expired")
        if status in {
            ActionRequestStatus.EXECUTING,
            ActionRequestStatus.COMPLETED,
            ActionRequestStatus.FAILED,
            ActionRequestStatus.REJECTED,
        }:
            await self.session.rollback()
            raise ActionExecutionConflictError("Action has already been executed")
        if expected_version is not None and request.version != expected_version:
            await self.session.rollback()
            raise ActionVersionConflictError("Action request version is stale")

        definition = self._definition(request.action_name)
        prior_actions = await self.requests.list(
            workflow_id=workflow.workflow_id, limit=100, offset=0
        )
        context = PolicyEvaluationContext(
            agent_run_id=request.agent_run_id,
            workflow_id=workflow.workflow_id,
            campaign_id=campaign.campaign_id,
            agent_name=AgentName(request.agent_name),
            action_name=request.action_name,
            arguments=request.arguments,
            campaign_status=CampaignStatus(campaign.status),
            workflow_status=CampaignStatus(workflow.status),
            actor_id=request.approved_by,
            actor_role=(
                UserRole(request.approved_role) if request.approved_role else None
            ),
            revision_number=workflow.revision_number,
            previous_action_count=len(prior_actions),
        )
        current_policy = self.policy.evaluate(context, definition)
        await self.requests.save_latest_policy_result(request, current_policy, context)

        if current_policy.decision == PolicyDecision.FORBIDDEN:
            reason = f"Fresh policy denied execution: {current_policy.reason}"
            await self.requests.save_latest_policy_result(
                request,
                current_policy,
                context,
                reason_code="POLICY_REEVALUATION_DENIED",
                reason=reason,
            )
            await self.requests.reject_after_policy_reevaluation(request, reason=reason)
            await self.session.commit()
            raise ActionPolicyReevaluationDeniedError(
                "Action is no longer allowed by current policy"
            )

        if request.expires_at is not None and request.expires_at <= datetime.now(UTC):
            await self.requests.expire(
                action_request_id, expected_version=request.version
            )
            await self.session.commit()
            raise ActionExpiredError("Action request has expired")

        original_policy = PolicyDecision(request.policy_decision)
        if current_policy.decision == PolicyDecision.APPROVAL_REQUIRED:
            if status == ActionRequestStatus.PROPOSED:
                await self.requests.save_latest_policy_result(
                    request,
                    current_policy,
                    context,
                    reason_code="POLICY_REEVALUATION_APPROVAL_REQUIRED",
                    reason="Fresh policy now requires human approval",
                )
                await self.requests.mark_pending_approval(
                    request,
                    datetime.now(UTC)
                    + timedelta(
                        seconds=current_policy.expires_in_seconds
                        or self.settings.action_approval_ttl_seconds
                    ),
                )
                await self.session.commit()
                raise ActionPolicyApprovalRequiredError(
                    "Fresh policy requires human approval"
                )
            if status != ActionRequestStatus.APPROVED:
                await self.session.commit()
                raise ActionApprovalRequiredError("Action requires human approval")
            if not role_satisfies_requirement(
                request.approved_role, current_policy.required_role
            ):
                reason = "Existing approval does not satisfy the current required role"
                await self.requests.save_latest_policy_result(
                    request,
                    current_policy,
                    context,
                    reason_code="POLICY_REEVALUATION_APPROVAL_REQUIRED",
                    reason=reason,
                )
                await self.requests.reject_after_policy_reevaluation(
                    request, reason=reason
                )
                await self.session.commit()
                raise ActionPolicyApprovalRequiredError(reason)
        elif (
            original_policy == PolicyDecision.APPROVAL_REQUIRED
            and status != ActionRequestStatus.APPROVED
        ):
            await self.session.commit()
            raise ActionPolicyApprovalRequiredError(
                "Original request lifecycle still requires human approval"
            )
        elif status not in {
            ActionRequestStatus.PROPOSED,
            ActionRequestStatus.APPROVED,
        }:
            await self.session.rollback()
            raise ActionExecutionConflictError("Action is no longer executable")

        existing = await self.executions.find_by_idempotency_key(
            request.idempotency_key
        )
        if existing is not None:
            await self.session.rollback()
            raise ActionExecutionConflictError("Action has already been executed")
        if definition is None:
            await self.session.rollback()
            raise PolicyDeniedError("Unregistered action cannot execute")
        guard = ActionExecutionGuard(
            campaign_id=campaign.campaign_id,
            workflow_id=workflow.workflow_id,
            expected_campaign_status=CampaignStatus(campaign.status),
            expected_campaign_version=campaign.version,
            expected_workflow_status=CampaignStatus(workflow.status),
            expected_revision_number=workflow.revision_number,
        )
        try:
            execution = await self.executions.create(
                action_request_id=request.action_request_id,
                idempotency_key=request.idempotency_key,
                guard=guard,
            )
            await self.executions.mark_running(execution)
            await self.requests.mark_executing(request)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if is_action_execution_duplicate(exc):
                raise ActionExecutionConflictError(
                    "Action execution already exists"
                ) from exc
            raise PersistenceError("Unable to reserve action execution") from exc
        return request, execution, definition, guard

    async def _finalize_success(
        self,
        request_id: UUID,
        execution_id: UUID,
        *,
        result_summary: str,
        duration_ms: int,
    ) -> ActionExecutionRead:
        await self.session.rollback()
        current_request = await self._required_request(request_id)
        current_execution = await self._required_execution(execution_id)
        await self.executions.mark_completed(
            current_execution,
            result_summary=result_summary,
            duration_ms=duration_ms,
        )
        await self.requests.mark_completed(current_request)
        await self.outbox.add_event(
            event_type=OutboxEventType.ACTION_COMPLETED,
            aggregate_type="action_execution",
            aggregate_id=str(current_execution.action_execution_id),
            payload={
                "action_execution_id": str(current_execution.action_execution_id),
                "action_request_id": str(current_request.action_request_id),
                "action_name": current_request.action_name,
            },
            idempotency_key=(
                f"action-execution:{current_execution.action_execution_id}:completed"
            ),
        )
        await self.session.commit()
        ACTION_EXECUTIONS.labels(
            current_request.action_name, ActionExecutionStatus.COMPLETED.value
        ).inc()
        await self._record_terminal_memory(
            request_id,
            execution_id,
            event_type=MemoryEventType.ACTION_COMPLETED,
            summary=result_summary,
            metadata={"action_name": current_request.action_name},
            importance=4,
        )
        refreshed = await self.executions.get_by_id(execution_id)
        if refreshed is None:
            raise ActionExecutionConflictError("Action execution audit is missing")
        return action_execution_to_schema(refreshed)

    async def _finalize_failure(
        self,
        request_id: UUID,
        execution_id: UUID,
        error: Exception,
        *,
        duration_ms: int = 0,
    ) -> None:
        await self.session.rollback()
        current_request = await self._required_request(request_id)
        current_execution = await self._required_execution(execution_id)
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
        await self.outbox.add_event(
            event_type=OutboxEventType.ACTION_FAILED,
            aggregate_type="action_execution",
            aggregate_id=str(current_execution.action_execution_id),
            payload={
                "action_execution_id": str(current_execution.action_execution_id),
                "action_request_id": str(current_request.action_request_id),
                "action_name": current_request.action_name,
                "error_code": code,
            },
            idempotency_key=(
                f"action-execution:{current_execution.action_execution_id}:failed"
            ),
        )
        await self.session.commit()
        ACTION_EXECUTIONS.labels(
            current_request.action_name, ActionExecutionStatus.FAILED.value
        ).inc()
        ACTION_EXECUTION_FAILURES.labels(current_request.action_name).inc()
        await self._record_terminal_memory(
            request_id,
            execution_id,
            event_type=MemoryEventType.ACTION_FAILED,
            summary=message,
            metadata={"action_name": current_request.action_name, "error_code": code},
            importance=5,
        )

    async def _finalize_cancelled(
        self,
        request_id: UUID,
        execution_id: UUID,
        *,
        duration_ms: int,
    ) -> None:
        await self.session.rollback()
        current_request = await self._required_request(request_id)
        current_execution = await self._required_execution(execution_id)
        message = "Action execution was cancelled"
        await self.executions.mark_cancelled(
            current_execution,
            error_message=message,
            duration_ms=duration_ms,
        )
        await self.requests.mark_failed(current_request)
        await self.session.commit()
        await self._record_terminal_memory(
            request_id,
            execution_id,
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
        model = await self.executions.get_by_id_for_update(execution_id)
        if model is None:
            raise ActionExecutionConflictError("Action execution audit is missing")
        if ActionExecutionStatus(model.status) != ActionExecutionStatus.RUNNING:
            raise ActionExecutionConflictError("Action execution is already terminal")
        return model

    def _definition(self, action_name: str) -> ActionDefinition | None:
        try:
            return self.registry.get(action_name)
        except ActionNotFoundError:
            return None

    async def _record_terminal_memory(
        self,
        request_id: UUID,
        execution_id: UUID,
        *,
        event_type: MemoryEventType,
        summary: str,
        metadata: dict[str, object],
        importance: int,
    ) -> None:
        await self.session.rollback()
        current = await self.executions.get_by_id_for_update(execution_id)
        if current is None:
            raise ActionExecutionConflictError("Action execution audit is missing")
        request = await self.requests.get_by_id(request_id)
        if request is None or current.action_request_id != request.action_request_id:
            await self.session.rollback()
            raise ActionScopeConflictError("Action memory scope is invalid")
        if current.memory_record_status == MemoryRecordStatus.RECORDED.value:
            await self.session.commit()
            return
        campaign_id = request.campaign_id
        workflow_id = request.workflow_id
        agent_run_id = request.agent_run_id
        action_request_id = request.action_request_id
        await self.executions.start_memory_record_attempt(current)
        await self.session.commit()
        try:
            await self.memories.record_event(
                campaign_id=campaign_id,
                workflow_id=workflow_id,
                agent_run_id=agent_run_id,
                action_request_id=action_request_id,
                action_execution_id=execution_id,
                event_type=event_type,
                summary=summary,
                metadata=metadata,
                importance=importance,
            )
            recorded = await self.executions.get_by_id_for_update(execution_id)
            if recorded is None:
                raise ActionExecutionConflictError("Action execution audit is missing")
            await self.executions.mark_memory_recorded(recorded)
            await self.session.commit()
        except Exception as exc:
            await self.session.rollback()
            failed = await self.executions.get_by_id_for_update(execution_id)
            if failed is None:
                return
            code = (
                exc.error_code
                if isinstance(exc, ApplicationError)
                else "MEMORY_RECORDING_ERROR"
            )
            message = (
                sanitize_text(exc.message, max_characters=2000)
                if isinstance(exc, ApplicationError)
                else "Action memory recording failed"
            )
            await self.executions.mark_memory_record_failed(
                failed,
                error_code=code,
                error_message=message,
            )
            await self.outbox.add_event(
                event_type=OutboxEventType.MEMORY_RECONCILIATION_REQUIRED,
                aggregate_type="action_execution",
                aggregate_id=str(execution_id),
                payload={
                    "action_execution_id": str(execution_id),
                    "action_request_id": str(request_id),
                    "error_code": code,
                },
                idempotency_key=f"action-execution:{execution_id}:memory-reconciliation",
            )
            await self.session.commit()

    async def reconcile_pending_action_memories(
        self, *, limit: int = 100
    ) -> list[ActionExecutionRead]:
        models = await self.executions.list_reconcilable_memories(
            limit=min(max(limit, 1), 100)
        )
        execution_ids = [model.action_execution_id for model in models]
        await self.session.commit()
        results: list[ActionExecutionRead] = []
        for execution_id in execution_ids:
            execution = await self.executions.get_by_id(execution_id)
            if execution is None:
                continue
            request = await self.requests.get_by_id(execution.action_request_id)
            if request is None:
                continue
            status = ActionExecutionStatus(execution.status)
            completed = status == ActionExecutionStatus.COMPLETED
            await self._record_terminal_memory(
                request.action_request_id,
                execution.action_execution_id,
                event_type=(
                    MemoryEventType.ACTION_COMPLETED
                    if completed
                    else MemoryEventType.ACTION_FAILED
                ),
                summary=(
                    execution.result_summary if completed else execution.error_message
                )
                or "Controlled action reached a terminal state",
                metadata={
                    "action_name": request.action_name,
                    "reconciled": True,
                },
                importance=4 if completed else 5,
            )
            refreshed = await self.executions.get_by_id(execution_id)
            if refreshed is not None:
                results.append(action_execution_to_schema(refreshed))
        await self.session.commit()
        return results
