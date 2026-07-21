from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import AlertStatus, AlertType, SecuritySeverity
from app.database.models import OperationalAlertModel


class AlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def open_or_increment(
        self,
        *,
        alert_type: AlertType,
        severity: SecuritySeverity,
        resource_type: str,
        resource_id: str,
        deduplication_key: str,
        summary: str,
        details: dict[str, object],
        correlation_id: str,
    ) -> OperationalAlertModel:
        now = datetime.now(UTC)
        statement = (
            insert(OperationalAlertModel)
            .values(
                alert_type=alert_type.value,
                status=AlertStatus.OPEN.value,
                severity=severity.value,
                resource_type=resource_type,
                resource_id=resource_id,
                deduplication_key=deduplication_key,
                summary=summary,
                details=details,
                first_seen_at=now,
                last_seen_at=now,
                occurrence_count=1,
                correlation_id=correlation_id,
            )
            .on_conflict_do_update(
                constraint="uq_operational_alerts_dedup",
                set_={
                    "status": AlertStatus.OPEN.value,
                    "severity": severity.value,
                    "summary": summary,
                    "details": details,
                    "last_seen_at": now,
                    "occurrence_count": OperationalAlertModel.occurrence_count + 1,
                    "acknowledged_by": None,
                    "acknowledged_at": None,
                    "resolved_by": None,
                    "resolved_at": None,
                    "correlation_id": correlation_id,
                },
            )
            .returning(OperationalAlertModel)
        )
        return (await self.session.execute(statement)).scalar_one()

    async def get(
        self, alert_id: UUID, *, for_update: bool = False
    ) -> OperationalAlertModel | None:
        statement = select(OperationalAlertModel).where(
            OperationalAlertModel.alert_id == alert_id
        )
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        status: AlertStatus | None,
        alert_type: AlertType | None,
    ) -> Sequence[OperationalAlertModel]:
        statement = select(OperationalAlertModel)
        if status is not None:
            statement = statement.where(OperationalAlertModel.status == status.value)
        if alert_type is not None:
            statement = statement.where(
                OperationalAlertModel.alert_type == alert_type.value
            )
        result = await self.session.execute(
            statement.order_by(
                OperationalAlertModel.last_seen_at.desc(),
                OperationalAlertModel.alert_id,
            )
            .offset(offset)
            .limit(limit)
        )
        return result.scalars().all()

    async def list_active_for_types(
        self, alert_types: set[AlertType]
    ) -> Sequence[OperationalAlertModel]:
        result = await self.session.execute(
            select(OperationalAlertModel)
            .where(
                OperationalAlertModel.alert_type.in_(
                    [alert_type.value for alert_type in alert_types]
                ),
                OperationalAlertModel.status.in_(
                    [AlertStatus.OPEN.value, AlertStatus.ACKNOWLEDGED.value]
                ),
            )
            .order_by(OperationalAlertModel.alert_id)
            .with_for_update(skip_locked=True)
        )
        return result.scalars().all()
