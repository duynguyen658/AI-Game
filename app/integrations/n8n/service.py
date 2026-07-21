from __future__ import annotations

import base64
import binascii
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.constants import JobType
from app.core.exceptions import M7ConflictError, M7ValidationError
from app.database.models import N8NWebhookReceiptModel
from app.integrations.n8n.schemas import (
    N8NCampaignRequest,
    N8NFileTaskRequest,
    N8NOutboundEnvelope,
    N8NWebhookResponse,
)
from app.integrations.n8n.signatures import sign_webhook, verify_webhook
from app.jobs.definitions import WorkflowRunJobPayload
from app.jobs.queue import JobQueue
from app.repositories.campaign_repository import CampaignRepository
from app.repositories.n8n_repository import N8NRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.service.mappers import campaign_to_record
from app.service.data_analysis_service import DataAnalysisService
from app.service.document_processing_service import DocumentProcessingService


class N8NService:
    def __init__(
        self, session: AsyncSession, *, settings: Settings | None = None
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repository = N8NRepository(session)

    async def accept_campaign(
        self,
        *,
        raw_body: bytes,
        timestamp: str,
        signature: str,
        idempotency_key: str,
        correlation_id: str | None,
    ) -> N8NWebhookResponse:
        if len(raw_body) > self.settings.n8n_max_body_bytes:
            raise M7ValidationError("Webhook body exceeds the size limit")
        if not idempotency_key or len(idempotency_key) > 200:
            raise M7ValidationError("Webhook idempotency key is invalid")
        signature_hash = verify_webhook(
            self.settings.n8n_webhook_secret.get_secret_value(),
            timestamp,
            raw_body,
            signature,
            tolerance_seconds=self.settings.n8n_timestamp_tolerance_seconds,
        )
        existing = await self.repository.get_by_idempotency(idempotency_key)
        if existing is not None:
            return N8NWebhookResponse.model_validate(
                {**existing.response_body, "duplicate": True}
            )
        replay = await self.repository.get_by_signature(signature_hash)
        if replay is not None:
            raise M7ConflictError("Webhook replay was rejected")
        try:
            payload = N8NCampaignRequest.model_validate_json(raw_body)
        except ValueError as exc:
            raise M7ValidationError("Webhook payload is invalid") from exc
        campaigns = CampaignRepository(self.session)
        if await campaigns.exists(payload.campaign.campaign_id):
            raise M7ConflictError("Campaign already exists")
        campaign = await campaigns.create(payload.campaign)
        workflow = await WorkflowRepository(self.session).create(
            campaign_id=payload.campaign.campaign_id,
            parent_workflow_id=None,
            revision_number=0,
        )
        job_id = None
        if payload.run_async:
            job = await JobQueue(self.session, settings=self.settings).enqueue(
                JobType.WORKFLOW_RUN,
                WorkflowRunJobPayload(workflow_id=workflow.workflow_id),
                created_by="n8n-webhook",
                idempotency_key=f"n8n:{idempotency_key}:workflow",
                correlation_id=correlation_id,
                commit=False,
            )
            job_id = str(job.job_id)
        response = N8NWebhookResponse(
            accepted=True,
            resource_type="campaign",
            resource_id=campaign_to_record(campaign).campaign.campaign_id,
            job_id=job_id,
        )
        receipt = N8NWebhookReceiptModel(
            idempotency_key=idempotency_key,
            signature_hash=signature_hash,
            endpoint="campaigns",
            correlation_id=correlation_id or str(uuid4()),
            response_status=202,
            response_body=response.model_dump(mode="json"),
        )
        await self.repository.create(receipt)
        await self.session.commit()
        return response

    async def accept_file_task(
        self,
        *,
        endpoint: str,
        raw_body: bytes,
        timestamp: str,
        signature: str,
        idempotency_key: str,
        correlation_id: str | None,
    ) -> N8NWebhookResponse:
        signature_hash, duplicate = await self._verify_file_request(
            endpoint=endpoint,
            raw_body=raw_body,
            timestamp=timestamp,
            signature=signature,
            idempotency_key=idempotency_key,
        )
        if duplicate is not None:
            return duplicate
        try:
            payload = N8NFileTaskRequest.model_validate_json(raw_body)
            content = base64.b64decode(payload.content_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise M7ValidationError("Webhook file payload is invalid") from exc
        if endpoint == "data-analysis":
            task = await DataAnalysisService(
                self.session, settings=self.settings
            ).request(
                content,
                payload.filename,
                actor_id="n8n-webhook",
                commit=False,
            )
        elif endpoint == "document-processing":
            task = await DocumentProcessingService(
                self.session, settings=self.settings
            ).request(
                content,
                payload.filename,
                payload.content_type,
                actor_id="n8n-webhook",
                commit=False,
            )
        else:
            raise M7ValidationError("Webhook endpoint is unsupported")
        response = N8NWebhookResponse(
            accepted=True,
            resource_type="applied_task",
            resource_id=str(task.task_run_id),
            job_id=str(task.job_id) if task.job_id else None,
        )
        await self.repository.create(
            N8NWebhookReceiptModel(
                idempotency_key=idempotency_key,
                signature_hash=signature_hash,
                endpoint=endpoint,
                correlation_id=correlation_id or str(uuid4()),
                response_status=202,
                response_body=response.model_dump(mode="json"),
            )
        )
        await self.session.commit()
        return response

    async def _verify_file_request(
        self,
        *,
        endpoint: str,
        raw_body: bytes,
        timestamp: str,
        signature: str,
        idempotency_key: str,
    ) -> tuple[str, N8NWebhookResponse | None]:
        if len(raw_body) > self.settings.n8n_max_body_bytes:
            raise M7ValidationError("Webhook body exceeds the size limit")
        if not idempotency_key or len(idempotency_key) > 200:
            raise M7ValidationError("Webhook idempotency key is invalid")
        signature_hash = verify_webhook(
            self.settings.n8n_webhook_secret.get_secret_value(),
            timestamp,
            raw_body,
            signature,
            tolerance_seconds=self.settings.n8n_timestamp_tolerance_seconds,
        )
        existing = await self.repository.get_by_idempotency(idempotency_key)
        if existing is not None:
            if existing.endpoint != endpoint:
                raise M7ConflictError(
                    "Webhook idempotency key belongs to another endpoint"
                )
            return signature_hash, N8NWebhookResponse.model_validate(
                {**existing.response_body, "duplicate": True}
            )
        if await self.repository.get_by_signature(signature_hash) is not None:
            raise M7ConflictError("Webhook replay was rejected")
        return signature_hash, None

    def outbound_envelope(
        self, event_type: str, aggregate_id: str, payload: dict[str, object]
    ) -> N8NOutboundEnvelope:
        timestamp = str(int(datetime.now(UTC).timestamp()))
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return N8NOutboundEnvelope(
            event_type=event_type,
            aggregate_id=aggregate_id,
            payload=payload,
            timestamp=timestamp,
            signature=sign_webhook(
                self.settings.n8n_webhook_secret.get_secret_value(), timestamp, body
            ),
        )
