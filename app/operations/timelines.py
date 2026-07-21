from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CampaignNotFoundError, WorkflowNotFoundError
from app.database.models import (
    AgentActionExecutionModel,
    AgentActionRequestModel,
    AgentMemoryEntryModel,
    AgentRunModel,
    AgentToolCallModel,
    BackgroundJobModel,
    CampaignModel,
    OutboxEventModel,
    WorkflowRunModel,
)
from app.schemas.operations import TimelineEvent


class TimelineService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def workflow(
        self, workflow_id: UUID, *, limit: int = 100
    ) -> list[TimelineEvent]:
        workflow = await self.session.get(WorkflowRunModel, workflow_id)
        if workflow is None:
            raise WorkflowNotFoundError("Workflow not found")
        events = [
            TimelineEvent(
                occurred_at=workflow.started_at,
                event_type="WORKFLOW_CREATED",
                resource_type="workflow",
                resource_id=str(workflow.workflow_id),
                status=workflow.status,
                summary=f"Workflow entered {workflow.status}",
                metadata={
                    "step": workflow.current_step,
                    "revision": workflow.revision_number,
                },
            )
        ]
        events.extend(await self._workflow_related(workflow_id))
        await self.session.commit()
        return _ordered(events, limit)

    async def campaign(
        self, campaign_id: str, *, limit: int = 100
    ) -> list[TimelineEvent]:
        campaign = await self.session.get(CampaignModel, campaign_id)
        if campaign is None:
            raise CampaignNotFoundError("Campaign not found")
        events = [
            TimelineEvent(
                occurred_at=campaign.created_at,
                event_type="CAMPAIGN_CREATED",
                resource_type="campaign",
                resource_id=campaign.campaign_id,
                status=campaign.status,
                summary=f"Campaign entered {campaign.status}",
            )
        ]
        workflows = (
            (
                await self.session.execute(
                    select(WorkflowRunModel)
                    .where(WorkflowRunModel.campaign_id == campaign_id)
                    .order_by(WorkflowRunModel.started_at, WorkflowRunModel.workflow_id)
                )
            )
            .scalars()
            .all()
        )
        for workflow in workflows:
            events.append(
                TimelineEvent(
                    occurred_at=workflow.started_at,
                    event_type="WORKFLOW_CREATED",
                    resource_type="workflow",
                    resource_id=str(workflow.workflow_id),
                    status=workflow.status,
                    summary=f"Workflow revision {workflow.revision_number} entered {workflow.status}",
                )
            )
            events.extend(await self._workflow_related(workflow.workflow_id))
        await self.session.commit()
        return _ordered(events, limit)

    async def _workflow_related(self, workflow_id: UUID) -> list[TimelineEvent]:
        events: list[TimelineEvent] = []
        runs = (
            (
                await self.session.execute(
                    select(AgentRunModel).where(
                        AgentRunModel.workflow_id == workflow_id
                    )
                )
            )
            .scalars()
            .all()
        )
        run_ids = [run.agent_run_id for run in runs]
        for run in runs:
            events.append(
                TimelineEvent(
                    occurred_at=run.started_at,
                    event_type="AGENT_RUN",
                    resource_type="agent_run",
                    resource_id=str(run.agent_run_id),
                    status=run.status,
                    summary=f"{run.agent_name} run {run.status.lower()}",
                    metadata={
                        "iterations": run.iteration_count,
                        "llm_calls": run.llm_call_count,
                        "tool_calls": run.tool_call_count,
                    },
                )
            )
        if run_ids:
            tools = (
                (
                    await self.session.execute(
                        select(AgentToolCallModel).where(
                            AgentToolCallModel.agent_run_id.in_(run_ids)
                        )
                    )
                )
                .scalars()
                .all()
            )
            for tool in tools:
                events.append(
                    TimelineEvent(
                        occurred_at=tool.started_at,
                        event_type="TOOL_CALL",
                        resource_type="tool_call",
                        resource_id=str(tool.tool_call_id),
                        status=tool.status,
                        summary=f"Tool {tool.tool_name} {tool.status.lower()}",
                    )
                )
        requests = (
            (
                await self.session.execute(
                    select(AgentActionRequestModel).where(
                        AgentActionRequestModel.workflow_id == workflow_id
                    )
                )
            )
            .scalars()
            .all()
        )
        request_ids = [request.action_request_id for request in requests]
        for request in requests:
            events.append(
                TimelineEvent(
                    occurred_at=request.requested_at,
                    event_type="ACTION_REQUEST",
                    resource_type="action_request",
                    resource_id=str(request.action_request_id),
                    status=request.status,
                    summary=f"Action {request.action_name} {request.status.lower()}",
                    metadata={"policy_decision": request.policy_decision},
                )
            )
        if request_ids:
            executions = (
                (
                    await self.session.execute(
                        select(AgentActionExecutionModel).where(
                            AgentActionExecutionModel.action_request_id.in_(request_ids)
                        )
                    )
                )
                .scalars()
                .all()
            )
            for execution in executions:
                events.append(
                    TimelineEvent(
                        occurred_at=execution.started_at or execution.created_at,
                        event_type="ACTION_EXECUTION",
                        resource_type="action_execution",
                        resource_id=str(execution.action_execution_id),
                        status=execution.status,
                        summary=execution.result_summary
                        or execution.error_message
                        or f"Action execution {execution.status.lower()}",
                    )
                )
        memories = (
            (
                await self.session.execute(
                    select(AgentMemoryEntryModel).where(
                        AgentMemoryEntryModel.workflow_id == workflow_id
                    )
                )
            )
            .scalars()
            .all()
        )
        for memory in memories:
            events.append(
                TimelineEvent(
                    occurred_at=memory.created_at,
                    event_type="MEMORY_RECORDED",
                    resource_type="memory",
                    resource_id=str(memory.memory_entry_id),
                    status=memory.event_type,
                    summary=memory.summary,
                )
            )
        jobs = (
            (
                await self.session.execute(
                    select(BackgroundJobModel).where(
                        BackgroundJobModel.payload["workflow_id"].astext
                        == str(workflow_id)
                    )
                )
            )
            .scalars()
            .all()
        )
        for job in jobs:
            events.append(
                TimelineEvent(
                    occurred_at=job.created_at,
                    event_type="BACKGROUND_JOB",
                    resource_type="job",
                    resource_id=str(job.job_id),
                    status=job.status,
                    summary=f"{job.job_type} job {job.status.lower()}",
                    correlation_id=job.correlation_id,
                )
            )
        outbox = (
            (
                await self.session.execute(
                    select(OutboxEventModel).where(
                        OutboxEventModel.aggregate_type == "workflow",
                        OutboxEventModel.aggregate_id == str(workflow_id),
                    )
                )
            )
            .scalars()
            .all()
        )
        for event in outbox:
            events.append(
                TimelineEvent(
                    occurred_at=event.created_at,
                    event_type=event.event_type,
                    resource_type="outbox_event",
                    resource_id=str(event.outbox_event_id),
                    status=event.status,
                    summary=f"Outbox event {event.event_type.lower()}",
                    correlation_id=event.correlation_id,
                )
            )
        return events


def _ordered(events: list[TimelineEvent], limit: int) -> list[TimelineEvent]:
    return sorted(
        events,
        key=lambda event: (event.occurred_at, event.event_type, event.resource_id),
    )[-min(max(limit, 1), 500) :]
