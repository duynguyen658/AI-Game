from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status

from app.api.dependencies import SessionDependency
from app.integrations.n8n.schemas import N8NWebhookResponse
from app.integrations.n8n.service import N8NService
from app.operations.rate_limit import enforce_sensitive_rate_limit

router = APIRouter(
    prefix="/integrations/n8n",
    tags=["Integrations - n8n"],
    dependencies=[Depends(enforce_sensitive_rate_limit)],
)


@router.post(
    "/campaigns",
    response_model=N8NWebhookResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def n8n_campaign_webhook(
    request: Request,
    session: SessionDependency,
    timestamp: Annotated[str, Header(alias="X-N8N-Timestamp")],
    signature: Annotated[str, Header(alias="X-N8N-Signature")],
    idempotency_key: Annotated[str, Header(alias="X-Idempotency-Key")],
    correlation_id: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> N8NWebhookResponse:
    raw_body = await request.body()
    return await N8NService(session).accept_campaign(
        raw_body=raw_body,
        timestamp=timestamp,
        signature=signature,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )


async def _file_webhook(
    endpoint: str,
    request: Request,
    session: SessionDependency,
    timestamp: str,
    signature: str,
    idempotency_key: str,
    correlation_id: str | None,
) -> N8NWebhookResponse:
    return await N8NService(session).accept_file_task(
        endpoint=endpoint,
        raw_body=await request.body(),
        timestamp=timestamp,
        signature=signature,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )


@router.post("/data-analysis", response_model=N8NWebhookResponse, status_code=202)
async def n8n_data_analysis_webhook(
    request: Request,
    session: SessionDependency,
    timestamp: Annotated[str, Header(alias="X-N8N-Timestamp")],
    signature: Annotated[str, Header(alias="X-N8N-Signature")],
    idempotency_key: Annotated[str, Header(alias="X-Idempotency-Key")],
    correlation_id: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> N8NWebhookResponse:
    return await _file_webhook(
        "data-analysis",
        request,
        session,
        timestamp,
        signature,
        idempotency_key,
        correlation_id,
    )


@router.post("/document-processing", response_model=N8NWebhookResponse, status_code=202)
async def n8n_document_processing_webhook(
    request: Request,
    session: SessionDependency,
    timestamp: Annotated[str, Header(alias="X-N8N-Timestamp")],
    signature: Annotated[str, Header(alias="X-N8N-Signature")],
    idempotency_key: Annotated[str, Header(alias="X-Idempotency-Key")],
    correlation_id: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> N8NWebhookResponse:
    return await _file_webhook(
        "document-processing",
        request,
        session,
        timestamp,
        signature,
        idempotency_key,
        correlation_id,
    )
