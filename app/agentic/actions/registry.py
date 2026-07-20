from __future__ import annotations

from collections.abc import Iterable

from app.agentic.actions.definitions import ActionDefinition
from app.core.constants import AgentName
from app.core.exceptions import ActionNotAllowedError, ActionNotFoundError


class ActionRegistry:
    def __init__(self, definitions: Iterable[ActionDefinition]) -> None:
        registered: dict[str, ActionDefinition] = {}
        for definition in definitions:
            if definition.name in registered:
                raise ValueError(f"Duplicate action definition: {definition.name}")
            registered[definition.name] = definition
        self._definitions = registered

    def get(self, name: str) -> ActionDefinition:
        definition = self._definitions.get(name)
        if definition is None:
            raise ActionNotFoundError("Action is not registered")
        return definition

    def get_for_agent(self, agent_name: AgentName, name: str) -> ActionDefinition:
        definition = self.get(name)
        if agent_name not in definition.allowed_agents:
            raise ActionNotAllowedError("Action is not allowed for this Agent")
        return definition

    def list_for_agent(self, agent_name: AgentName) -> tuple[ActionDefinition, ...]:
        return tuple(
            definition
            for definition in self._definitions.values()
            if agent_name in definition.allowed_agents
        )
