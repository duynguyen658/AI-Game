from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.core.constants import AppliedWorkflowType, JobType, UserRole


class AppliedWorkflowDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workflow_type: AppliedWorkflowType
    display_name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    required_capabilities: list[str]
    allowed_roles: list[UserRole]
    job_type: JobType | None
    business_impact_task_type: str
    prompt_template_slug: str | None
    enabled: bool
