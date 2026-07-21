from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.constants import (
    ActionExecutionStatus,
    AlertType,
    JobStatus,
    MemoryRecordStatus,
    OutboxStatus,
    SecuritySeverity,
)
from app.database.models import (
    AgentActionExecutionModel,
    BackgroundJobModel,
    OutboxEventModel,
)
from app.operations.alerts import AlertService


@dataclass(frozen=True)
class AlertCondition:
    alert_type: AlertType
    severity: SecuritySeverity
    resource_type: str
    resource_id: str
    summary: str
    details: dict[str, object]


class AlertReconciler:
    MANAGED_TYPES = {
        AlertType.JOB_QUEUE_BACKLOG,
        AlertType.JOB_DEAD_LETTER,
        AlertType.ACTION_EXECUTION_FAILURE,
        AlertType.MEMORY_RECONCILIATION_BACKLOG,
        AlertType.OUTBOX_BACKLOG,
    }

    def __init__(
        self, session: AsyncSession, *, settings: Settings | None = None
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.alerts = AlertService(session)

    async def reconcile(self, *, limit: int = 100) -> dict[str, int]:
        conditions = await self._conditions(limit=min(max(limit, 1), 500))
        active: set[tuple[AlertType, str, str]] = set()
        for condition in conditions:
            active.add(
                (
                    condition.alert_type,
                    condition.resource_type,
                    condition.resource_id,
                )
            )
            await self.alerts.open(
                alert_type=condition.alert_type,
                severity=condition.severity,
                resource_type=condition.resource_type,
                resource_id=condition.resource_id,
                summary=condition.summary,
                details=condition.details,
            )
        resolved = await self.alerts.resolve_cleared(
            managed_types=self.MANAGED_TYPES, active_resources=active
        )
        return {"opened_or_incremented": len(conditions), "resolved": resolved}

    async def _conditions(self, *, limit: int) -> list[AlertCondition]:
        conditions: list[AlertCondition] = []
        dead_jobs = (
            (
                await self.session.execute(
                    select(BackgroundJobModel)
                    .where(BackgroundJobModel.status == JobStatus.DEAD_LETTER.value)
                    .order_by(
                        BackgroundJobModel.completed_at.desc(),
                        BackgroundJobModel.job_id,
                    )
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        conditions.extend(
            AlertCondition(
                AlertType.JOB_DEAD_LETTER,
                SecuritySeverity.HIGH,
                "job",
                str(job.job_id),
                "Background job reached dead letter",
                {"job_type": job.job_type, "error_code": job.error_code},
            )
            for job in dead_jobs
        )

        failed_actions = (
            (
                await self.session.execute(
                    select(AgentActionExecutionModel)
                    .where(
                        AgentActionExecutionModel.status
                        == ActionExecutionStatus.FAILED.value
                    )
                    .order_by(
                        AgentActionExecutionModel.completed_at.desc(),
                        AgentActionExecutionModel.action_execution_id,
                    )
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        conditions.extend(
            AlertCondition(
                AlertType.ACTION_EXECUTION_FAILURE,
                SecuritySeverity.HIGH,
                "action_execution",
                str(execution.action_execution_id),
                "Controlled action execution failed",
                {"error_code": execution.error_code},
            )
            for execution in failed_actions
        )

        memory_backlog = int(
            await self.session.scalar(
                select(func.count(AgentActionExecutionModel.action_execution_id)).where(
                    AgentActionExecutionModel.memory_record_status
                    == MemoryRecordStatus.FAILED.value
                )
            )
            or 0
        )
        if memory_backlog:
            conditions.append(
                AlertCondition(
                    AlertType.MEMORY_RECONCILIATION_BACKLOG,
                    SecuritySeverity.MEDIUM,
                    "system",
                    "memory",
                    "Action memory reconciliation is pending",
                    {"count": memory_backlog},
                )
            )

        queue_backlog = int(
            await self.session.scalar(
                select(func.count(BackgroundJobModel.job_id)).where(
                    BackgroundJobModel.status == JobStatus.PENDING.value
                )
            )
            or 0
        )
        if queue_backlog > self.settings.job_batch_size * 10:
            conditions.append(
                AlertCondition(
                    AlertType.JOB_QUEUE_BACKLOG,
                    SecuritySeverity.MEDIUM,
                    "system",
                    "job-queue",
                    "Background job queue exceeds its operational threshold",
                    {"count": queue_backlog},
                )
            )

        outbox_backlog = int(
            await self.session.scalar(
                select(func.count(OutboxEventModel.outbox_event_id)).where(
                    OutboxEventModel.status.in_(
                        [
                            OutboxStatus.PENDING.value,
                            OutboxStatus.FAILED.value,
                            OutboxStatus.DEAD_LETTER.value,
                        ]
                    )
                )
            )
            or 0
        )
        if outbox_backlog > self.settings.outbox_ready_backlog_limit:
            conditions.append(
                AlertCondition(
                    AlertType.OUTBOX_BACKLOG,
                    SecuritySeverity.HIGH,
                    "system",
                    "outbox",
                    "Transactional outbox exceeds its operational threshold",
                    {"count": outbox_backlog},
                )
            )
        await self.session.commit()
        return conditions
