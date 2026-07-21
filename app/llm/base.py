from typing import Any, Protocol, TypeVar

from pydantic import BaseModel
from app.llm.agent_turn import AgentMessage, AgentTurn
from app.llm.capabilities import CompletionRequest, NormalizedCompletion

OutputT = TypeVar("OutputT", bound=BaseModel)


class LLMClient(Protocol):
    async def complete(self, request: CompletionRequest) -> NormalizedCompletion: ...

    async def complete_structured(
        self, request: CompletionRequest, output_schema: type[OutputT]
    ) -> NormalizedCompletion: ...

    async def complete_with_tools(
        self, request: CompletionRequest
    ) -> NormalizedCompletion: ...

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[OutputT],
    ) -> OutputT: ...

    async def run_agent_turn(
        self,
        *,
        system_prompt: str,
        messages: list[AgentMessage],
        tools: list[dict[str, Any]],
        output_schema: type[OutputT],
    ) -> AgentTurn: ...
