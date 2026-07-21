from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ImageGenerationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt: str = Field(min_length=1, max_length=10_000)
    negative_prompt: str | None = Field(default=None, max_length=3000)
    width: int = Field(default=1024, ge=256, le=2048)
    height: int = Field(default=1024, ge=256, le=2048)
    model: str = Field(min_length=1, max_length=200)


class GeneratedImage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    content: bytes
    mime_type: str
    width: int
    height: int
    provider_job_id: str | None = None
    estimated_cost: float = Field(default=0, ge=0)
    safety_flags: list[str] = Field(default_factory=list)
