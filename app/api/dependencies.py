from typing import Annotated

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import UserRole
from app.core.exceptions import AuthenticationError
from app.database.session import get_session
from app.llm.factory import build_llm_client
from app.service.auth_service import AuthService, AuthenticatedActor

SessionDependency = Annotated[AsyncSession, Depends(get_session)]

bearer_scheme = HTTPBearer(auto_error=False)


def get_llm_client():
    return build_llm_client(get_settings())


async def get_current_actor(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    x_actor_id: Annotated[str | None, Header()] = None,
    x_actor_role: Annotated[str | None, Header()] = None,
) -> AuthenticatedActor:
    if credentials is not None:
        return AuthService().decode_bearer_token(credentials.credentials)

    settings = get_settings()
    if settings.app_env != "production" and x_actor_id and x_actor_role:
        return AuthenticatedActor(actor_id=x_actor_id, role=UserRole(x_actor_role))

    raise AuthenticationError("Authentication is required")
