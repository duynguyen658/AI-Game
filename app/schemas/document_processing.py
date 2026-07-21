from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DocumentType(StrEnum):
    MARKETING_BRIEF = "MARKETING_BRIEF"
    CAMPAIGN_REPORT = "CAMPAIGN_REPORT"
    GAME_DESIGN_DOCUMENT = "GAME_DESIGN_DOCUMENT"
    PRODUCT_REQUIREMENT_DOCUMENT = "PRODUCT_REQUIREMENT_DOCUMENT"
    MEETING_NOTES = "MEETING_NOTES"
    UNKNOWN = "UNKNOWN"


class DocumentProcessingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: DocumentType
    executive_summary: str
    key_points: list[str]
    missing_sections: list[str]
    inconsistencies: list[str]
    risks: list[str]
    action_items: list[str]
    open_questions: list[str]
    confidence: float = Field(ge=0, le=1)
    limitations: list[str]
    prompt_injection_warning: bool
    page_count: int
    character_count: int
    generated_at: datetime
