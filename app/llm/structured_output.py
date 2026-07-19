import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.core.exceptions import LLMResponseError

OutputT = TypeVar("OutputT", bound=BaseModel)


def validate_structured_output(
    raw_response: str | dict[str, object],
    output_schema: type[OutputT],
) -> OutputT:
    try:
        payload = (
            json.loads(raw_response) if isinstance(raw_response, str) else raw_response
        )
    except json.JSONDecodeError as exc:
        raise LLMResponseError("LLM response was not valid JSON") from exc
    try:
        return output_schema.model_validate(payload)
    except ValidationError as exc:
        raise LLMResponseError("LLM response did not match expected schema") from exc
