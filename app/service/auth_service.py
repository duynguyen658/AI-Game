from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError

from app.core.config import get_settings
from app.core.constants import UserRole
from app.core.exceptions import AuthenticationError, AuthorizationError

AGENT_RUN_VIEWER_ROLES = {
    UserRole.REVIEWER,
    UserRole.MANAGER,
    UserRole.ADMIN,
    UserRole.SYSTEM,
}
ACTION_ROLE_LEVELS = {
    UserRole.REVIEWER: 1,
    UserRole.MANAGER: 2,
    UserRole.ADMIN: 3,
}


@lru_cache(maxsize=4)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True, lifespan=300)


def role_satisfies_requirement(
    actual_role: str | UserRole | None,
    required_role: UserRole | None,
) -> bool:
    if actual_role is None or required_role is None:
        return required_role is None
    try:
        actual = UserRole(actual_role)
    except ValueError:
        return False
    return ACTION_ROLE_LEVELS.get(actual, 0) >= ACTION_ROLE_LEVELS.get(
        required_role, 99
    )


@dataclass(frozen=True)
class AuthenticatedActor:
    actor_id: str
    role: UserRole


class AuthService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def decode_bearer_token(self, token: str) -> AuthenticatedActor:
        try:
            key: Any = self.settings.jwt_secret_key.get_secret_value()
            if self.settings.jwt_jwks_url:
                key = (
                    _jwks_client(self.settings.jwt_jwks_url)
                    .get_signing_key_from_jwt(token)
                    .key
                )
            payload = jwt.decode(
                token,
                key,
                algorithms=[self.settings.jwt_algorithm],
                issuer=self.settings.jwt_issuer,
                audience=self.settings.jwt_audience,
                options={
                    "verify_iss": self.settings.jwt_issuer is not None,
                    "verify_aud": self.settings.jwt_audience is not None,
                },
            )
        except (InvalidTokenError, PyJWKClientError) as exc:
            raise AuthenticationError("Invalid authentication token") from exc
        subject = payload.get("sub")
        role = payload.get(self.settings.jwt_role_claim)
        if not subject or not role:
            raise AuthenticationError("Authentication token is missing required claims")
        try:
            actor_role = UserRole(role)
        except ValueError as exc:
            raise AuthenticationError("Authentication token role is invalid") from exc
        return AuthenticatedActor(actor_id=str(subject), role=actor_role)

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
        minimum = UserRole(required_role) if required_role else UserRole.ADMIN
        if not role_satisfies_requirement(actor.role, minimum):
            raise AuthorizationError("Actor role cannot approve this action")

    def require_action_execution(
        self, actor: AuthenticatedActor, required_role: str | None
    ) -> None:
        if actor.role == UserRole.SYSTEM:
            raise AuthorizationError("SYSTEM cannot execute approved human actions")
        minimum = UserRole(required_role) if required_role else UserRole.ADMIN
        if not role_satisfies_requirement(actor.role, minimum):
            raise AuthorizationError("Actor role cannot execute this action")

    def require_operator(self, actor: AuthenticatedActor) -> None:
        if actor.role not in {UserRole.MANAGER, UserRole.ADMIN}:
            raise AuthorizationError("Operator role is required")
