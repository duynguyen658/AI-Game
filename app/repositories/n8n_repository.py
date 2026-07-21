from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import N8NWebhookReceiptModel


class N8NRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_idempotency(self, key: str) -> N8NWebhookReceiptModel | None:
        return await self.session.scalar(
            select(N8NWebhookReceiptModel).where(
                N8NWebhookReceiptModel.idempotency_key == key
            )
        )

    async def get_by_signature(
        self, signature_hash: str
    ) -> N8NWebhookReceiptModel | None:
        return await self.session.scalar(
            select(N8NWebhookReceiptModel).where(
                N8NWebhookReceiptModel.signature_hash == signature_hash
            )
        )

    async def create(self, model: N8NWebhookReceiptModel) -> N8NWebhookReceiptModel:
        self.session.add(model)
        await self.session.flush()
        return model
