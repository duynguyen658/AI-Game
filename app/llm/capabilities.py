from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import ProviderName


class ModelCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    structured_output: bool
    tool_calling: bool
    image_input: bool
    image_generation: bool
    max_context_tokens: int = Field(ge=1)
    supports_system_prompt: bool


class CompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    system_prompt: str = Field(default="", max_length=30_000)
    user_prompt: str = Field(min_length=1, max_length=60_000)
    model: str = Field(min_length=1, max_length=200)
    tools: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    temperature: float = Field(default=0, ge=0, le=2)
    max_output_tokens: int = Field(default=2048, ge=1, le=32_000)


class NormalizedUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    estimated_cost: float = Field(default=0, ge=0)


class NormalizedToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    call_id: str
    name: str
    arguments: dict[str, Any]


class NormalizedCompletion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: ProviderName
    model: str
    content: str | None = None
    structured: dict[str, Any] | None = None
    tool_calls: list[NormalizedToolCall] = Field(default_factory=list)
    usage: NormalizedUsage = Field(default_factory=NormalizedUsage)
    finish_reason: str | None = None
    fallback_from: ProviderName | None = None
