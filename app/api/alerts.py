from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import SessionDependency, get_current_actor
from app.core.constants import AlertStatus, AlertType
from app.operations.alerts import AlertService
from app.schemas.alert import AlertRead
from app.service.auth_service import AuthService, AuthenticatedActor

router = APIRouter(prefix="/alerts", tags=["Operations - Alerts"])


@router.get("", response_model=list[AlertRead])
async def list_alerts(
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: AlertStatus | None = None,
    alert_type: AlertType | None = None,
) -> list[AlertRead]:
    AuthService().require_operator(actor)
    return await AlertService(session).list(
        limit=limit, offset=offset, status=status, alert_type=alert_type
    )


@router.get("/{alert_id}", response_model=AlertRead)
async def get_alert(
    alert_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> AlertRead:
    AuthService().require_operator(actor)
    return await AlertService(session).get(alert_id)


@router.post("/{alert_id}/acknowledge", response_model=AlertRead)
async def acknowledge_alert(
    alert_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> AlertRead:
    AuthService().require_operator(actor)
    return await AlertService(session).acknowledge(alert_id, actor_id=actor.actor_id)


@router.post("/{alert_id}/resolve", response_model=AlertRead)
async def resolve_alert(
    alert_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> AlertRead:
    AuthService().require_operator(actor)
    return await AlertService(session).resolve(alert_id, actor_id=actor.actor_id)
