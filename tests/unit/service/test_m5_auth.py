import pytest

from app.core.constants import UserRole
from app.core.exceptions import AuthorizationError
from app.service.auth_service import AuthService, AuthenticatedActor


def test_system_and_agent_cannot_self_approve_actions() -> None:
    service = AuthService()
    with pytest.raises(AuthorizationError):
        service.require_action_approval(
            AuthenticatedActor(actor_id="system", role=UserRole.SYSTEM),
            UserRole.REVIEWER.value,
            "CONTENT_REVIEWER",
        )
    with pytest.raises(AuthorizationError):
        service.require_action_approval(
            AuthenticatedActor(actor_id="agent:CONTENT_REVIEWER", role=UserRole.ADMIN),
            UserRole.REVIEWER.value,
            "CONTENT_REVIEWER",
        )


def test_action_approval_role_hierarchy() -> None:
    service = AuthService()
    service.require_action_approval(
        AuthenticatedActor(actor_id="manager", role=UserRole.MANAGER),
        UserRole.REVIEWER.value,
        "CONTENT_REVIEWER",
    )
    with pytest.raises(AuthorizationError):
        service.require_action_approval(
            AuthenticatedActor(actor_id="reviewer", role=UserRole.REVIEWER),
            UserRole.MANAGER.value,
            "CONTENT_REVIEWER",
        )
