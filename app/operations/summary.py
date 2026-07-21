from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import WorkerStatus
from app.database.models import (
    AgentActionExecutionModel,
    BackgroundJobModel,
    EvaluationRunModel,
    OperationalAlertModel,
    OutboxEventModel,
    WorkerHeartbeatModel,
    WorkflowRunModel,
)
from app.schemas.operations import OperationsSummary


async def operations_summary(session: AsyncSession) -> OperationsSummary:
    settings = get_settings()
    fresh_after = datetime.now(UTC) - timedelta(
        seconds=settings.worker_stale_after_seconds
    )
    fresh_workers = int(
        await session.scalar(
            select(func.count(WorkerHeartbeatModel.worker_id)).where(
                WorkerHeartbeatModel.status.in_(
                    [WorkerStatus.STARTING.value, WorkerStatus.RUNNING.value]
                ),
                WorkerHeartbeatModel.last_seen_at >= fresh_after,
            )
        )
        or 0
    )
    summary = OperationsSummary(
        application_version=settings.application_version,
        jobs=await _status_counts(session, BackgroundJobModel.status),
        alerts=await _status_counts(session, OperationalAlertModel.status),
        workflows=await _status_counts(session, WorkflowRunModel.status),
        actions=await _status_counts(session, AgentActionExecutionModel.status),
        evaluations=await _status_counts(session, EvaluationRunModel.status),
        outbox=await _status_counts(session, OutboxEventModel.status),
        fresh_workers=fresh_workers,
        generated_at=datetime.now(UTC),
    )
    await session.commit()
    return summary


async def _status_counts(session: AsyncSession, column) -> dict[str, int]:
    rows = (await session.execute(select(column, func.count()).group_by(column))).all()
    return {str(status): int(count) for status, count in rows}
