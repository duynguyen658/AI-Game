from __future__ import annotations

from app.agentic.tools.campaign_tools import campaign_tool_definitions
from app.agentic.tools.definitions import ToolDefinition
from app.agentic.tools.memory_tools import memory_tool_definitions
from app.core.constants import AgentName
from app.core.exceptions import ToolNotAllowedError, ToolNotFoundError
from app.service.agent_query_service import AgentReadQueryService
from app.service.memory_service import MemoryService

DEFAULT_PERMISSIONS: dict[AgentName, frozenset[str]] = {
    AgentName.BRIEF_ANALYST: frozenset(
        {"get_previous_workflow_summary", "get_recent_campaign_memories"}
    ),
    AgentName.CONTENT_GENERATOR: frozenset(
        {
            "get_previous_quality_review",
            "get_previous_revision",
            "get_previous_review_feedback",
            "get_previous_action_results",
        }
    ),
    AgentName.CONTENT_REVIEWER: frozenset(
        {
            "get_previous_quality_review",
            "get_previous_review_feedback",
            "get_previous_failures",
        }
    ),
}


class ToolRegistry:
    def __init__(
        self,
        definitions: list[ToolDefinition],
        permissions: dict[AgentName, frozenset[str]],
    ) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        for definition in definitions:
            if definition.name in self._tools:
                raise ValueError(f"Duplicate tool name: {definition.name}")
            if not definition.read_only:
                raise ValueError("M4 registry accepts read-only tools only")
            self._tools[definition.name] = definition
        self._permissions = {
            name: frozenset(values) for name, values in permissions.items()
        }

    def get(self, name: str) -> ToolDefinition:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolNotFoundError("Unknown tool requested") from exc

    def get_for_agent(self, agent_name: AgentName, name: str) -> ToolDefinition:
        definition = self.get(name)
        if name not in self._permissions.get(agent_name, frozenset()):
            raise ToolNotAllowedError("Tool is not allowed for this specialist")
        return definition

    def list_for_agent(self, agent_name: AgentName) -> list[ToolDefinition]:
        allowed = self._permissions.get(agent_name, frozenset())
        return [self._tools[name] for name in sorted(allowed) if name in self._tools]

    def provider_schemas(self, agent_name: AgentName) -> list[dict[str, object]]:
        return [
            definition.provider_schema()
            for definition in self.list_for_agent(agent_name)
        ]


def build_default_tool_registry(
    query_service: AgentReadQueryService,
    memory_service: MemoryService | None = None,
) -> ToolRegistry:
    definitions = campaign_tool_definitions(query_service)
    permissions = DEFAULT_PERMISSIONS
    if memory_service is not None:
        definitions = [*definitions, *memory_tool_definitions(memory_service)]
    else:
        permissions = {
            agent: frozenset(
                name
                for name in allowed
                if not name.startswith("get_recent_")
                and name
                not in {
                    "get_previous_failures",
                    "get_previous_review_feedback",
                    "get_previous_action_results",
                }
            )
            for agent, allowed in DEFAULT_PERMISSIONS.items()
        }
    return ToolRegistry(definitions, permissions)
