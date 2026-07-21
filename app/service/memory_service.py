from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.memory.summarizer import DeterministicMemorySummarizer
from app.core.config import Settings, get_settings
from app.core.constants import MemoryEventType, MemoryType
from app.core.exceptions import (
    AgentContextError,
    CampaignNotFoundError,
    MemoryEntryNotFoundError,
    PersistenceError,
    WorkflowNotFoundError,
)
from app.core.sanitization import sanitize_json, sanitize_text
from app.database.m5_integrity import is_memory_execution_event_duplicate
from app.repositories.action_execution_repository import ActionExecutionRepository
from app.repositories.action_request_repository import ActionRequestRepository
from app.repositories.agent_run_repository import AgentRunRepository
from app.repositories.campaign_repository import CampaignRepository
from app.repositories.memory_repository import MemoryRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.schemas.memory_entry import MemoryEntryCreate, MemoryEntryRead
from app.observability.tracing import traced_operation
from app.service.mappers import memory_entry_to_schema


class MemoryService:
    def __init__(
        self, session: AsyncSession, *, settings: Settings | None = None
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.memories = MemoryRepository(session)
        self.campaigns = CampaignRepository(session)
        self.workflows = WorkflowRepository(session)
        self.agent_runs = AgentRunRepository(session)
        self.action_requests = ActionRequestRepository(session)
        self.action_executions = ActionExecutionRepository(session)
        self.summarizer = DeterministicMemorySummarizer()

    async def record_event(
        self,
        *,
        campaign_id: str,
        event_type: MemoryEventType,
        summary: object,
        metadata: dict[str, Any] | None = None,
        workflow_id: UUID | None = None,
        agent_run_id: UUID | None = None,
        action_request_id: UUID | None = None,
        action_execution_id: UUID | None = None,
        memory_type: MemoryType = MemoryType.EPISODIC,
        importance: int = 3,
        expires_at: datetime | None = None,
    ) -> MemoryEntryRead:
        with traced_operation(
            "memory.record",
            event_type=event_type.value,
            campaign_id=campaign_id,
        ):
            return await self._record_event(
                campaign_id=campaign_id,
                event_type=event_type,
                summary=summary,
                metadata=metadata,
                workflow_id=workflow_id,
                agent_run_id=agent_run_id,
                action_request_id=action_request_id,
                action_execution_id=action_execution_id,
                memory_type=memory_type,
                importance=importance,
                expires_at=expires_at,
            )

    async def _record_event(
        self,
        *,
        campaign_id: str,
        event_type: MemoryEventType,
        summary: object,
        metadata: dict[str, Any] | None = None,
        workflow_id: UUID | None = None,
        agent_run_id: UUID | None = None,
        action_request_id: UUID | None = None,
        action_execution_id: UUID | None = None,
        memory_type: MemoryType = MemoryType.EPISODIC,
        importance: int = 3,
        expires_at: datetime | None = None,
    ) -> MemoryEntryRead:
        await self._validate_scope(
            campaign_id=campaign_id,
            workflow_id=workflow_id,
            agent_run_id=agent_run_id,
            action_request_id=action_request_id,
            action_execution_id=action_execution_id,
        )
        safe_metadata = self._bounded_metadata(metadata or {})
        expiration = expires_at or (
            datetime.now(UTC) + timedelta(days=self.settings.memory_default_ttl_days)
        )
        try:
            model = await self.memories.create(
                MemoryEntryCreate(
                    campaign_id=campaign_id,
                    workflow_id=workflow_id,
                    agent_run_id=agent_run_id,
                    action_request_id=action_request_id,
                    action_execution_id=action_execution_id,
                    memory_type=memory_type,
                    event_type=event_type,
                    summary=self.summarizer.summarize(event_type, summary),
                    metadata=safe_metadata,
                    importance=importance,
                    expires_at=expiration,
                )
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if action_execution_id is not None and is_memory_execution_event_duplicate(
                exc
            ):
                existing = await self.memories.find_by_execution_event(
                    action_execution_id, event_type
                )
                if existing is not None:
                    await self.session.commit()
                    return memory_entry_to_schema(existing)
            raise PersistenceError("Unable to persist memory entry") from exc
        except Exception:
            await self.session.rollback()
            raise
        return memory_entry_to_schema(model)

    async def get(self, memory_entry_id: UUID) -> MemoryEntryRead:
        model = await self.memories.get_by_id(memory_entry_id)
        if model is None:
            raise MemoryEntryNotFoundError("Memory entry not found")
        return memory_entry_to_schema(model)

    async def list_campaign(
        self,
        campaign_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
        event_type: MemoryEventType | None = None,
    ) -> list[MemoryEntryRead]:
        if await self.campaigns.get_by_id(campaign_id) is None:
            await self.session.rollback()
            raise CampaignNotFoundError("Campaign not found")
        models = await self.memories.list(
            campaign_id=campaign_id,
            event_type=event_type,
            limit=self._limit(limit),
            offset=max(offset, 0),
        )
        await self.session.commit()
        return [memory_entry_to_schema(model) for model in models]

    async def list_workflow(
        self,
        workflow_id: UUID,
        *,
        limit: int = 20,
        offset: int = 0,
        event_type: MemoryEventType | None = None,
    ) -> list[MemoryEntryRead]:
        if await self.workflows.get_by_id(workflow_id) is None:
            await self.session.rollback()
            raise WorkflowNotFoundError("Workflow not found")
        models = await self.memories.list(
            workflow_id=workflow_id,
            event_type=event_type,
            limit=self._limit(limit),
            offset=max(offset, 0),
        )
        await self.session.commit()
        return [memory_entry_to_schema(model) for model in models]

    async def recent_campaign(
        self, campaign_id: str, *, limit: int = 10
    ) -> list[MemoryEntryRead]:
        return await self.list_campaign(campaign_id, limit=limit)

    async def previous_failures(
        self, campaign_id: str, *, limit: int = 10
    ) -> list[MemoryEntryRead]:
        return await self.list_campaign(
            campaign_id,
            limit=limit,
            event_type=MemoryEventType.ACTION_FAILED,
        )

    async def previous_review_feedback(
        self, campaign_id: str, *, limit: int = 10
    ) -> list[MemoryEntryRead]:
        return await self.list_campaign(
            campaign_id,
            limit=limit,
            event_type=MemoryEventType.REVIEW_FEEDBACK,
        )

    async def previous_action_results(
        self, campaign_id: str, *, limit: int = 10
    ) -> list[MemoryEntryRead]:
        return await self.list_campaign(
            campaign_id,
            limit=limit,
            event_type=MemoryEventType.ACTION_COMPLETED,
        )

    async def _validate_scope(
        self,
        *,
        campaign_id: str,
        workflow_id: UUID | None,
        agent_run_id: UUID | None,
        action_request_id: UUID | None,
        action_execution_id: UUID | None,
    ) -> None:
        if await self.campaigns.get_by_id(campaign_id) is None:
            await self.session.rollback()
            raise CampaignNotFoundError("Campaign not found")
        if workflow_id is not None:
            workflow = await self.workflows.get_by_id(workflow_id)
            if workflow is None:
                await self.session.rollback()
                raise WorkflowNotFoundError("Workflow not found")
            if workflow.campaign_id != campaign_id:
                await self.session.rollback()
                raise AgentContextError("Memory workflow scope does not match campaign")
        if agent_run_id is not None:
            run = await self.agent_runs.get_by_id(agent_run_id)
            if (
                run is None
                or run.campaign_id != campaign_id
                or (workflow_id is not None and run.workflow_id != workflow_id)
            ):
                await self.session.rollback()
                raise AgentContextError("Memory Agent run scope is invalid")
        request = None
        if action_request_id is not None:
            request = await self.action_requests.get_by_id(action_request_id)
            if (
                request is None
                or request.campaign_id != campaign_id
                or (workflow_id is not None and request.workflow_id != workflow_id)
                or (agent_run_id is not None and request.agent_run_id != agent_run_id)
            ):
                await self.session.rollback()
                raise AgentContextError("Memory action request scope is invalid")
        if action_execution_id is not None:
            execution = await self.action_executions.get_by_id(action_execution_id)
            if (
                execution is None
                or request is None
                or execution.action_request_id != request.action_request_id
            ):
                await self.session.rollback()
                raise AgentContextError("Memory action execution scope is invalid")

    def _bounded_metadata(self, value: dict[str, Any]) -> dict[str, Any]:
        safe = sanitize_json(value, max_string_characters=2000)
        serialized = json.dumps(safe, ensure_ascii=True, separators=(",", ":"))
        if len(serialized) <= 12_000:
            return safe
        return {"summary": sanitize_text(serialized, max_characters=11_900)}

    def _limit(self, value: int) -> int:
        return min(max(value, 1), self.settings.memory_max_results)
