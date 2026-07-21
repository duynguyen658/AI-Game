from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.campaign import CampaignCreate


class N8NCampaignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign: CampaignCreate
    run_async: bool = True


class N8NWebhookResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: bool
    duplicate: bool = False
    resource_type: str
    resource_id: str
    job_id: str | None = None


class N8NFileTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    content_base64: str
    content_type: str = "application/octet-stream"


class N8NOutboundEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_type: str
    aggregate_id: str
    payload: dict[str, Any]
    timestamp: str
    signature: str
