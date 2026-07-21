from __future__ import annotations

import re
from string import Formatter
from typing import Any

from app.core.exceptions import M7ValidationError

MAX_RENDERED_PROMPT_CHARACTERS = 60_000
_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|authorization|password|secret|token)\s*[:=]\s*\S+"
)
_HIDDEN_REASONING_PATTERN = re.compile(
    r"(?i)(chain[-_ ]of[-_ ]thought|hidden reasoning|show your reasoning step by step)"
)


class PromptRenderer:
    @staticmethod
    def validate_content(system_prompt: str, user_prompt_template: str) -> None:
        content = f"{system_prompt}\n{user_prompt_template}"
        if _SECRET_PATTERN.search(content):
            raise M7ValidationError("Managed prompts cannot contain secrets")
        if _HIDDEN_REASONING_PATTERN.search(content):
            raise M7ValidationError("Managed prompts cannot request hidden reasoning")
        if len(content) > MAX_RENDERED_PROMPT_CHARACTERS:
            raise M7ValidationError("Managed prompt exceeds the size limit")

    @staticmethod
    def variables(template: str) -> set[str]:
        names: set[str] = set()
        try:
            for _, field_name, _, _ in Formatter().parse(template):
                if field_name:
                    names.add(field_name)
        except ValueError as exc:
            raise M7ValidationError("Prompt template syntax is invalid") from exc
        return names

    def render(
        self,
        template: str,
        values: dict[str, Any],
        *,
        allowed_variables: set[str],
        allow_unknown: bool = False,
    ) -> str:
        referenced = self.variables(template)
        missing = referenced - values.keys()
        unknown = values.keys() - allowed_variables
        if missing:
            raise M7ValidationError(
                f"Missing prompt variables: {', '.join(sorted(missing))}"
            )
        if unknown and not allow_unknown:
            raise M7ValidationError(
                f"Unknown prompt variables: {', '.join(sorted(unknown))}"
            )
        safe_values = {name: str(value) for name, value in values.items()}
        try:
            rendered = template.format_map(safe_values)
        except (KeyError, ValueError) as exc:
            raise M7ValidationError("Prompt rendering failed") from exc
        if len(rendered) > MAX_RENDERED_PROMPT_CHARACTERS:
            raise M7ValidationError("Rendered prompt exceeds the size limit")
        return rendered
