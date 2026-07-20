from dataclasses import dataclass

from jose import JWTError, jwt  # type: ignore[import-untyped]

from app.core.config import get_settings
from app.core.constants import UserRole
from app.core.exceptions import AuthenticationError, AuthorizationError

AGENT_RUN_VIEWER_ROLES = {
    UserRole.REVIEWER,
    UserRole.MANAGER,
    UserRole.ADMIN,
    UserRole.SYSTEM,
}


@dataclass(frozen=True)
class AuthenticatedActor:
    actor_id: str
    role: UserRole


class AuthService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def decode_bearer_token(self, token: str) -> AuthenticatedActor:
        try:
            payload = jwt.decode(
                token,
                self.settings.jwt_secret_key.get_secret_value(),
                algorithms=[self.settings.jwt_algorithm],
            )
        except JWTError as exc:
            raise AuthenticationError("Invalid authentication token") from exc
        subject = payload.get("sub")
        role = payload.get("role")
        if not subject or not role:
            raise AuthenticationError("Authentication token is missing required claims")
        return AuthenticatedActor(actor_id=str(subject), role=UserRole(role))

    def require_agent_run_read(self, actor: AuthenticatedActor) -> None:
        if actor.role not in AGENT_RUN_VIEWER_ROLES:
            raise AuthorizationError("Actor is not allowed to view Agent run audits")

    def require_action_read(self, actor: AuthenticatedActor) -> None:
        if actor.role not in AGENT_RUN_VIEWER_ROLES:
            raise AuthorizationError("Actor is not allowed to view action audits")

    def require_action_approval(
        self, actor: AuthenticatedActor, required_role: str | None, agent_name: str
    ) -> None:
        if actor.role == UserRole.SYSTEM or actor.actor_id == f"agent:{agent_name}":
            raise AuthorizationError("Agents and SYSTEM cannot approve actions")
        hierarchy = {
            UserRole.REVIEWER: 1,
            UserRole.MANAGER: 2,
            UserRole.ADMIN: 3,
        }
        minimum = UserRole(required_role) if required_role else UserRole.ADMIN
        if hierarchy.get(actor.role, 0) < hierarchy.get(minimum, 99):
            raise AuthorizationError("Actor role cannot approve this action")

    def require_action_execution(
        self, actor: AuthenticatedActor, required_role: str | None
    ) -> None:
        if actor.role == UserRole.SYSTEM:
            raise AuthorizationError("SYSTEM cannot execute approved human actions")
        hierarchy = {
            UserRole.REVIEWER: 1,
            UserRole.MANAGER: 2,
            UserRole.ADMIN: 3,
        }
        minimum = UserRole(required_role) if required_role else UserRole.ADMIN
        if hierarchy.get(actor.role, 0) < hierarchy.get(minimum, 99):
            raise AuthorizationError("Actor role cannot execute this action")
