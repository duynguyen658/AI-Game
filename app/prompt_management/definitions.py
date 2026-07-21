from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RenderedPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt_template_id: UUID
    prompt_version_id: UUID
    prompt_version_number: int
    content_hash: str
    system_prompt: str
    user_prompt: str
    output_schema: dict[str, Any]
    model_requirements: dict[str, Any]
