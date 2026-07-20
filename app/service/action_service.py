from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.actions.campaign_actions import build_default_action_registry
from app.agentic.actions.executor import ControlledActionExecutor
from app.agentic.actions.registry import ActionRegistry
from app.core.config import Settings, get_settings
from app.core.constants import (
    ActionRequestStatus,
    AgentName,
    MemoryEventType,
    PolicyDecision,
)
from app.core.exceptions import (
    ActionAlreadyDecidedError,
    ActionExpiredError,
    ActionRequestNotFoundError,
    ActionVersionConflictError,
    PersistenceError,
)
from app.core.sanitization import sanitize_json, sanitize_text
from app.database.m5_integrity import is_action_request_duplicate
from app.repositories.action_execution_repository import ActionExecutionRepository
from app.repositories.action_request_repository import ActionRequestRepository
from app.schemas.action_execution import ActionExecutionRead
from app.schemas.action_request import (
    ActionProposalResult,
    ActionRequestCreate,
    ActionRequestRead,
    AgentActionProposal,
)
from app.service.auth_service import AuthService, AuthenticatedActor
from app.service.mappers import action_execution_to_schema, action_request_to_schema
from app.service.memory_service import MemoryService
from app.service.policy_service import PolicyService


class ActionService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        registry: ActionRegistry | None = None,
        settings: Settings | None = None,
        memory_service: MemoryService | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.registry = registry or build_default_action_registry(
            session, settings=self.settings
        )
        self.requests = ActionRequestRepository(session)
        self.executions = ActionExecutionRepository(session)
        self.memories = memory_service or MemoryService(session, settings=self.settings)
        self.policy = PolicyService(session, self.registry)
        self.executor = ControlledActionExecutor(
            session,
            self.registry,
            memory_service=self.memories,
            settings=self.settings,
        )
        self.auth = AuthService()

    async def propose(
        self,
        *,
        agent_run_id: UUID,
        agent_name: AgentName,
        proposal: AgentActionProposal,
    ) -> ActionProposalResult:
        safe_proposal = proposal.model_copy(
            update={
                "arguments": sanitize_json(proposal.arguments),
                "rationale_summary": sanitize_text(
                    proposal.rationale_summary, max_characters=1000
                ),
            }
        )
        policy, _, context = await self.policy.evaluate(
            agent_run_id=agent_run_id,
            agent_name=agent_name,
            proposal=safe_proposal,
        )
        idempotency_key = self.build_idempotency_key(
            campaign_id=context.campaign_id,
            workflow_id=context.workflow_id,
            revision_number=context.revision_number,
            action_name=safe_proposal.action_name,
            arguments=safe_proposal.arguments,
        )
        existing = await self.requests.find_by_idempotency_key(idempotency_key)
        if existing is not None:
            await self.session.commit()
            return await self._proposal_result(existing.action_request_id)

        now = datetime.now(UTC)
        status = ActionRequestStatus.PROPOSED
        expires_at = None
        rejected_at = None
        rejection_reason = None
        if policy.decision == PolicyDecision.APPROVAL_REQUIRED:
            status = ActionRequestStatus.PENDING_APPROVAL
            expires_at = now + timedelta(
                seconds=policy.expires_in_seconds
                or self.settings.action_approval_ttl_seconds
            )
        elif policy.decision == PolicyDecision.FORBIDDEN:
            status = ActionRequestStatus.REJECTED
            rejected_at = now
            rejection_reason = policy.reason

        try:
            model = await self.requests.create_proposal(
                ActionRequestCreate(
                    agent_run_id=agent_run_id,
                    workflow_id=context.workflow_id,
                    campaign_id=context.campaign_id,
                    agent_name=agent_name,
                    action_name=safe_proposal.action_name,
                    arguments=safe_proposal.arguments,
                    rationale_summary=safe_proposal.rationale_summary,
                    idempotency_key=idempotency_key,
                ),
                policy,
                context,
                status=status,
                expires_at=expires_at,
                rejected_at=rejected_at,
                rejection_reason=rejection_reason,
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if not is_action_request_duplicate(exc):
                raise PersistenceError("Unable to persist action request") from exc
            duplicate = await self.requests.find_by_idempotency_key(idempotency_key)
            if duplicate is None:
                raise PersistenceError(
                    "Unable to load duplicate action request"
                ) from exc
            await self.session.commit()
            return await self._proposal_result(duplicate.action_request_id)

        await self.memories.record_event(
            campaign_id=model.campaign_id,
            workflow_id=model.workflow_id,
            agent_run_id=model.agent_run_id,
            action_request_id=model.action_request_id,
            event_type=MemoryEventType.ACTION_PROPOSED,
            summary=f"Action proposed: {model.action_name}",
            metadata={"policy_decision": model.policy_decision},
        )
        await self.memories.record_event(
            campaign_id=model.campaign_id,
            workflow_id=model.workflow_id,
            agent_run_id=model.agent_run_id,
            action_request_id=model.action_request_id,
            event_type=MemoryEventType.POLICY_DECIDED,
            summary=model.policy_reason,
            metadata={"reason_code": model.policy_reason_code},
        )
        if policy.decision == PolicyDecision.SAFE:
            execution = await self.executor.execute(model.action_request_id)
            return ActionProposalResult(
                action_request=await self.get(model.action_request_id),
                execution_status=execution.status.value,
                result_summary=execution.result_summary,
            )
        if policy.decision == PolicyDecision.FORBIDDEN:
            await self.memories.record_event(
                campaign_id=model.campaign_id,
                workflow_id=model.workflow_id,
                agent_run_id=model.agent_run_id,
                action_request_id=model.action_request_id,
                event_type=MemoryEventType.ACTION_REJECTED,
                summary=model.policy_reason,
                metadata={"forbidden": True},
                importance=4,
            )
        return ActionProposalResult(action_request=action_request_to_schema(model))

    async def approve(
        self,
        action_request_id: UUID,
        *,
        actor: AuthenticatedActor,
        expected_version: int,
    ) -> ActionRequestRead:
        request = await self._required(action_request_id)
        self.auth.require_action_approval(
            actor, request.required_role, request.agent_name
        )
        if request.version != expected_version:
            raise ActionVersionConflictError("Action request version is stale")
        self._ensure_pending(request)
        if request.expires_at is not None and request.expires_at <= datetime.now(UTC):
            await self.requests.expire(
                action_request_id, expected_version=expected_version
            )
            await self.session.commit()
            raise ActionExpiredError("Action request has expired")
        if not await self.requests.approve(
            action_request_id,
            actor_id=actor.actor_id,
            actor_role=actor.role.value,
            expected_version=expected_version,
        ):
            await self.session.rollback()
            raise ActionVersionConflictError("Action request version is stale")
        await self.session.commit()
        result = await self.get(action_request_id)
        await self.memories.record_event(
            campaign_id=result.campaign_id,
            workflow_id=result.workflow_id,
            agent_run_id=result.agent_run_id,
            action_request_id=result.action_request_id,
            event_type=MemoryEventType.ACTION_APPROVED,
            summary="Action approved by an authorized human",
            metadata={"actor_role": actor.role.value},
            importance=4,
        )
        return result

    async def reject(
        self,
        action_request_id: UUID,
        *,
        actor: AuthenticatedActor,
        expected_version: int,
        reason: str,
    ) -> ActionRequestRead:
        request = await self._required(action_request_id)
        self.auth.require_action_approval(
            actor, request.required_role, request.agent_name
        )
        if request.version != expected_version:
            raise ActionVersionConflictError("Action request version is stale")
        self._ensure_pending(request)
        if not await self.requests.reject(
            action_request_id,
            actor_id=actor.actor_id,
            reason=sanitize_text(reason, max_characters=1000),
            expected_version=expected_version,
        ):
            await self.session.rollback()
            raise ActionVersionConflictError("Action request version is stale")
        await self.session.commit()
        result = await self.get(action_request_id)
        await self.memories.record_event(
            campaign_id=result.campaign_id,
            workflow_id=result.workflow_id,
            agent_run_id=result.agent_run_id,
            action_request_id=result.action_request_id,
            event_type=MemoryEventType.ACTION_REJECTED,
            summary=result.rejection_reason or "Action rejected",
            metadata={"actor_role": actor.role.value},
            importance=4,
        )
        return result

    async def execute(
        self,
        action_request_id: UUID,
        *,
        actor: AuthenticatedActor,
        expected_version: int,
    ) -> ActionExecutionRead:
        request = await self._required(action_request_id)
        self.auth.require_action_execution(actor, request.required_role)
        return await self.executor.execute(
            action_request_id, expected_version=expected_version
        )

    async def get(self, action_request_id: UUID) -> ActionRequestRead:
        return action_request_to_schema(await self._required(action_request_id))

    async def list_requests(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        status: ActionRequestStatus | None = None,
    ) -> list[ActionRequestRead]:
        models = await self.requests.list(
            limit=min(max(limit, 1), 100),
            offset=max(offset, 0),
            status=status,
        )
        return [action_request_to_schema(model) for model in models]

    async def list_executions(
        self, action_request_id: UUID
    ) -> list[ActionExecutionRead]:
        await self._required(action_request_id)
        models = await self.executions.list_by_request(action_request_id)
        return [action_execution_to_schema(model) for model in models]

    async def reconcile_pending_action_memories(
        self, *, limit: int = 100
    ) -> list[ActionExecutionRead]:
        return await self.executor.reconcile_pending_action_memories(limit=limit)

    async def _proposal_result(self, action_request_id: UUID) -> ActionProposalResult:
        request = await self.get(action_request_id)
        executions = await self.list_executions(action_request_id)
        execution = executions[-1] if executions else None
        return ActionProposalResult(
            action_request=request,
            execution_status=execution.status.value if execution else None,
            result_summary=(
                execution.result_summary
                if execution and request.status == ActionRequestStatus.COMPLETED
                else None
            ),
        )

    async def _required(self, action_request_id: UUID):
        model = await self.requests.get_by_id(action_request_id)
        if model is None:
            raise ActionRequestNotFoundError("Action request not found")
        return model

    def _ensure_pending(self, request) -> None:
        if ActionRequestStatus(request.status) != ActionRequestStatus.PENDING_APPROVAL:
            raise ActionAlreadyDecidedError("Action request is not pending approval")

    @staticmethod
    def build_idempotency_key(
        *,
        campaign_id: str,
        workflow_id: UUID,
        revision_number: int,
        action_name: str,
        arguments: dict,
    ) -> str:
        normalized = json.dumps(
            sanitize_json(arguments),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        material = "|".join(
            [
                campaign_id,
                str(workflow_id),
                str(revision_number),
                action_name,
                hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            ]
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()
