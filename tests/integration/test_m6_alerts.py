from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import AlertStatus, AlertType, SecuritySeverity
from app.database.session import AsyncSessionLocal
from app.operations.alerts import AlertService

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_TESTS") != "1",
        reason="set RUN_POSTGRES_TESTS=1 to run PostgreSQL integration tests",
    ),
]


@pytest_asyncio.fixture(autouse=True)
async def clean_alerts() -> AsyncIterator[None]:
    async with AsyncSessionLocal() as session:
        await session.execute(text("TRUNCATE operational_alerts RESTART IDENTITY"))
        await session.commit()
    yield
    async with AsyncSessionLocal() as session:
        await session.execute(text("TRUNCATE operational_alerts RESTART IDENTITY"))
        await session.commit()


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


@pytest.mark.asyncio
async def test_alert_dedup_acknowledge_resolve_and_reopen(
    db_session: AsyncSession,
) -> None:
    alerts = AlertService(db_session)
    occurred_at = datetime(2026, 7, 21, 1, tzinfo=UTC)
    first = await alerts.open(
        alert_type=AlertType.JOB_DEAD_LETTER,
        severity=SecuritySeverity.HIGH,
        resource_type="job",
        resource_id="job-1",
        summary="Job failed",
        occurred_at=occurred_at,
    )
    duplicate = await alerts.open(
        alert_type=AlertType.JOB_DEAD_LETTER,
        severity=SecuritySeverity.HIGH,
        resource_type="job",
        resource_id="job-1",
        summary="Job failed again",
        occurred_at=occurred_at,
    )
    assert duplicate.alert_id == first.alert_id
    assert duplicate.occurrence_count == 2

    acknowledged = await alerts.acknowledge(first.alert_id, actor_id="operator-1")
    assert acknowledged.status == AlertStatus.ACKNOWLEDGED
    resolved = await alerts.resolve(first.alert_id, actor_id="operator-1")
    assert resolved.status == AlertStatus.RESOLVED
    reopened = await alerts.open(
        alert_type=AlertType.JOB_DEAD_LETTER,
        severity=SecuritySeverity.CRITICAL,
        resource_type="job",
        resource_id="job-1",
        summary="Job failed again",
        occurred_at=occurred_at,
    )
    assert reopened.status == AlertStatus.OPEN
    assert reopened.occurrence_count == 3
