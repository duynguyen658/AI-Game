from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import SecurityEventType, SecuritySeverity
from app.schemas.security_event import SecurityEvent
from app.service.auth_service import AuthenticatedActor
from app.service.security_event_service import SecurityEventService


async def record_operator_action(
    session: AsyncSession,
    *,
    actor: AuthenticatedActor,
    action: str,
    resource_type: str,
    resource_id: str,
    workflow_id: UUID | None = None,
    campaign_id: str | None = None,
) -> None:
    await SecurityEventService(session).record_event(
        SecurityEvent(
            event_type=SecurityEventType.OPERATOR_ACTION,
            severity=SecuritySeverity.LOW,
            actor_id=actor.actor_id,
            workflow_id=workflow_id,
            campaign_id=campaign_id,
            source="operator-api",
            message=f"Operator performed {action}",
            metadata={
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
            },
        )
    )
