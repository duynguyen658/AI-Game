from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.action_request import AgentActionProposal


class AgentToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_call_id: str = Field(min_length=1, max_length=200)
    tool_name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)


class AgentMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant", "tool"]
    content: str = Field(max_length=20_000)
    tool_call_id: str | None = Field(default=None, max_length=200)
    tool_name: str | None = Field(default=None, max_length=100)
    tool_calls: list[AgentToolRequest] = Field(default_factory=list, max_length=10)


class LLMUsage(BaseModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)


class AgentTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assistant_text: str | None = Field(default=None, max_length=20_000)
    tool_calls: list[AgentToolRequest] = Field(default_factory=list, max_length=10)
    final_output: dict[str, Any] | None = None
    action_proposals: list[AgentActionProposal] = Field(
        default_factory=list, max_length=10
    )
    usage: LLMUsage | None = None

    @model_validator(mode="after")
    def require_action(self) -> "AgentTurn":
        if not self.tool_calls and self.final_output is None:
            raise ValueError("Agent turn must contain tool calls or final output")
        if self.tool_calls and self.final_output is not None:
            raise ValueError("Agent turn cannot mix tool calls and final output")
        return self
