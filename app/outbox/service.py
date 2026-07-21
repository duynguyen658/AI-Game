from __future__ import annotations

import hashlib
import json
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.constants import OutboxEventType
from app.core.exceptions import PersistenceError
from app.core.sanitization import sanitize_json
from app.database.integrity import get_constraint_name
from app.database.models import OutboxEventModel
from app.observability.context import get_context_value
from app.repositories.outbox_repository import OutboxRepository


class OutboxService:
    def __init__(
        self, session: AsyncSession, *, settings: Settings | None = None
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repository = OutboxRepository(session)

    async def add_event(
        self,
        *,
        event_type: OutboxEventType,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, object],
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        trace_id: str | None = None,
    ) -> OutboxEventModel:
        safe_payload = sanitize_json(payload)
        if not isinstance(safe_payload, dict):
            raise PersistenceError("Unable to prepare outbox payload")
        key = idempotency_key or self.build_idempotency_key(
            event_type, aggregate_type, aggregate_id, safe_payload
        )
        if len(key) > 64:
            key = hashlib.sha256(key.encode("utf-8")).hexdigest()
        try:
            async with self.session.begin_nested():
                return await self.repository.create(
                    event_type=event_type,
                    aggregate_type=aggregate_type,
                    aggregate_id=aggregate_id,
                    payload=safe_payload,
                    idempotency_key=key,
                    correlation_id=correlation_id
                    or get_context_value("correlation_id")
                    or str(uuid4()),
                    trace_id=trace_id or get_context_value("trace_id"),
                    max_attempts=self.settings.job_max_attempts,
                )
        except IntegrityError as exc:
            if get_constraint_name(exc) != "uq_outbox_events_idempotency":
                raise PersistenceError("Unable to persist outbox event") from exc
            existing = await self.repository.find_by_key(key)
            if existing is None:
                raise PersistenceError(
                    "Unable to load idempotent outbox event"
                ) from exc
            return existing

    @staticmethod
    def build_idempotency_key(
        event_type: OutboxEventType,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, object],
    ) -> str:
        normalized = json.dumps(
            payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        )
        value = f"{event_type.value}|{aggregate_type}|{aggregate_id}|{normalized}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
