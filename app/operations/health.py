from __future__ import annotations

from datetime import UTC, datetime, timedelta

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.constants import JobStatus, OutboxStatus, WorkerStatus
from app.database.models import (
    BackgroundJobModel,
    OutboxEventModel,
    WorkerHeartbeatModel,
)


async def readiness_report(
    session: AsyncSession, *, settings: Settings | None = None
) -> tuple[bool, dict[str, object]]:
    config = settings or get_settings()
    checks: dict[str, object] = {}
    try:
        await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
        database_revision = await session.scalar(
            text("SELECT version_num FROM alembic_version")
        )
        code_revision = ScriptDirectory.from_config(
            Config("alembic.ini")
        ).get_current_head()
        checks["migration"] = {
            "status": "ok" if database_revision == code_revision else "mismatch",
            "database_revision": database_revision,
            "code_revision": code_revision,
        }
        pending_jobs = int(
            await session.scalar(
                select(func.count(BackgroundJobModel.job_id)).where(
                    BackgroundJobModel.status.in_(
                        [JobStatus.PENDING.value, JobStatus.RUNNING.value]
                    )
                )
            )
            or 0
        )
        checks["queue"] = {"status": "ok", "pending_or_running": pending_jobs}
        fresh_after = datetime.now(UTC) - timedelta(
            seconds=config.worker_stale_after_seconds
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
        worker_ok = pending_jobs == 0 or fresh_workers > 0
        checks["worker"] = {
            "status": "ok" if worker_ok else "stale",
            "fresh_workers": fresh_workers,
        }
        outbox_backlog = int(
            await session.scalar(
                select(func.count(OutboxEventModel.outbox_event_id)).where(
                    OutboxEventModel.status.in_(
                        [
                            OutboxStatus.PENDING.value,
                            OutboxStatus.FAILED.value,
                            OutboxStatus.PROCESSING.value,
                        ]
                    )
                )
            )
            or 0
        )
        outbox_ok = outbox_backlog <= config.outbox_ready_backlog_limit
        checks["outbox"] = {
            "status": "ok" if outbox_ok else "backlog",
            "pending": outbox_backlog,
        }
        checks["configuration"] = "ok"
        checks["llm"] = {
            "status": "configured",
            "provider": config.llm_provider,
            "model": config.llm_model or "mock",
        }
        migration_ok = database_revision == code_revision
        ready = migration_ok and worker_ok and outbox_ok
        await session.commit()
        return ready, checks
    except Exception:
        await session.rollback()
        return False, {"postgres": "unavailable"}
