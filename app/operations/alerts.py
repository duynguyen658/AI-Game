from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import AlertStatus, AlertType, SecuritySeverity
from app.core.exceptions import AlertNotFoundError, JobConflictError, PersistenceError
from app.core.sanitization import sanitize_json, sanitize_text
from app.database.models import OperationalAlertModel
from app.observability.context import get_context_value
from app.repositories.alert_repository import AlertRepository
from app.schemas.alert import AlertRead

logger = structlog.get_logger()


class AlertService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = AlertRepository(session)

    async def open(
        self,
        *,
        alert_type: AlertType,
        severity: SecuritySeverity,
        resource_type: str,
        resource_id: str,
        summary: str,
        details: dict[str, object] | None = None,
        occurred_at: datetime | None = None,
    ) -> AlertRead:
        bucket = (occurred_at or datetime.now(UTC)).strftime("%Y%m%d%H")
        material = f"{alert_type.value}|{resource_type}|{resource_id}|{bucket}"
        key = hashlib.sha256(material.encode()).hexdigest()
        safe_details = sanitize_json(details or {})
        if not isinstance(safe_details, dict):
            raise PersistenceError("Unable to prepare alert details")
        model = await self.repository.open_or_increment(
            alert_type=alert_type,
            severity=severity,
            resource_type=sanitize_text(resource_type, max_characters=100),
            resource_id=sanitize_text(resource_id, max_characters=200),
            deduplication_key=key,
            summary=sanitize_text(summary, max_characters=1000),
            details=safe_details,
            correlation_id=get_context_value("correlation_id") or str(uuid4()),
        )
        await self.session.commit()
        logger.warning(
            "alert_opened",
            alert_id=str(model.alert_id),
            alert_type=model.alert_type,
            severity=model.severity,
        )
        return alert_to_schema(model)

    async def get(self, alert_id: UUID) -> AlertRead:
        model = await self.repository.get(alert_id)
        if model is None:
            raise AlertNotFoundError("Operational alert not found")
        await self.session.commit()
        return alert_to_schema(model)

    async def list(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        status: AlertStatus | None = None,
        alert_type: AlertType | None = None,
    ) -> list[AlertRead]:
        models = await self.repository.list(
            limit=min(max(limit, 1), 100),
            offset=max(offset, 0),
            status=status,
            alert_type=alert_type,
        )
        await self.session.commit()
        return [alert_to_schema(model) for model in models]

    async def acknowledge(self, alert_id: UUID, *, actor_id: str) -> AlertRead:
        model = await self._required_for_update(alert_id)
        if model.status == AlertStatus.RESOLVED.value:
            raise JobConflictError("Resolved alert cannot be acknowledged")
        model.status = AlertStatus.ACKNOWLEDGED.value
        model.acknowledged_by = sanitize_text(actor_id, max_characters=200)
        model.acknowledged_at = datetime.now(UTC)
        await self.session.commit()
        return alert_to_schema(model)

    async def resolve(self, alert_id: UUID, *, actor_id: str) -> AlertRead:
        model = await self._required_for_update(alert_id)
        if model.status == AlertStatus.RESOLVED.value:
            return alert_to_schema(model)
        model.status = AlertStatus.RESOLVED.value
        model.resolved_by = sanitize_text(actor_id, max_characters=200)
        model.resolved_at = datetime.now(UTC)
        await self.session.commit()
        logger.info("alert_resolved", alert_id=str(alert_id))
        return alert_to_schema(model)

    async def _required_for_update(self, alert_id: UUID) -> OperationalAlertModel:
        model = await self.repository.get(alert_id, for_update=True)
        if model is None:
            raise AlertNotFoundError("Operational alert not found")
        return model

    async def resolve_cleared(
        self,
        *,
        managed_types: set[AlertType],
        active_resources: set[tuple[AlertType, str, str]],
        actor_id: str = "alert-reconciler",
    ) -> int:
        models = await self.repository.list_active_for_types(managed_types)
        resolved = 0
        now = datetime.now(UTC)
        for model in models:
            identity = (
                AlertType(model.alert_type),
                model.resource_type,
                model.resource_id,
            )
            if identity not in active_resources:
                model.status = AlertStatus.RESOLVED.value
                model.resolved_by = actor_id
                model.resolved_at = now
                resolved += 1
        await self.session.commit()
        return resolved


def alert_to_schema(model: OperationalAlertModel) -> AlertRead:
    return AlertRead(
        alert_id=model.alert_id,
        alert_type=AlertType(model.alert_type),
        status=AlertStatus(model.status),
        severity=SecuritySeverity(model.severity),
        resource_type=model.resource_type,
        resource_id=model.resource_id,
        summary=model.summary,
        details=model.details,
        first_seen_at=model.first_seen_at,
        last_seen_at=model.last_seen_at,
        acknowledged_by=model.acknowledged_by,
        acknowledged_at=model.acknowledged_at,
        resolved_by=model.resolved_by,
        resolved_at=model.resolved_at,
        occurrence_count=model.occurrence_count,
        correlation_id=model.correlation_id,
    )
