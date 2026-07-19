from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.security_event_repository import SecurityEventRepository
from app.schemas.security_event import SecurityEvent
from app.service.mappers import security_event_to_schema

SECRET_KEYS = {"api_key", "authorization", "token", "password", "secret"}


class SecurityEventService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = SecurityEventRepository(session)

    async def record_event(self, event: SecurityEvent) -> SecurityEvent:
        event.metadata = {
            key: value
            for key, value in event.metadata.items()
            if key.lower() not in SECRET_KEYS
        }
        model = await self.repository.create(event)
        await self.session.commit()
        return security_event_to_schema(model)
