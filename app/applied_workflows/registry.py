from __future__ import annotations

from app.applied_workflows.definitions import AppliedWorkflowDefinition
from app.core.constants import AppliedWorkflowType, JobType, UserRole


class AppliedWorkflowRegistry:
    def __init__(self) -> None:
        common_roles = [
            UserRole.MARKETING,
            UserRole.REVIEWER,
            UserRole.MANAGER,
            UserRole.ADMIN,
        ]
        self._definitions = {
            AppliedWorkflowType.CAMPAIGN_CONTENT: AppliedWorkflowDefinition(
                workflow_type=AppliedWorkflowType.CAMPAIGN_CONTENT,
                display_name="Campaign Content",
                description="Create and review multi-channel campaign content.",
                input_schema={"$ref": "#/components/schemas/CampaignCreate"},
                output_schema={"$ref": "#/components/schemas/GeneratedContent"},
                required_capabilities=["structured_output", "tool_calling"],
                allowed_roles=common_roles,
                job_type=JobType.WORKFLOW_RUN,
                business_impact_task_type="campaign_content",
                prompt_template_slug="campaign-content",
                enabled=True,
            ),
            AppliedWorkflowType.DATA_ANALYSIS: AppliedWorkflowDefinition(
                workflow_type=AppliedWorkflowType.DATA_ANALYSIS,
                display_name="CSV Data Analysis",
                description="Compute deterministic campaign and game analytics.",
                input_schema={
                    "type": "string",
                    "format": "binary",
                    "contentMediaType": "text/csv",
                },
                output_schema={"$ref": "#/components/schemas/DataAnalysisReport"},
                required_capabilities=["structured_output"],
                allowed_roles=common_roles,
                job_type=JobType.DATA_ANALYSIS,
                business_impact_task_type="data_analysis",
                prompt_template_slug="data-analysis-explanation",
                enabled=True,
            ),
            AppliedWorkflowType.DOCUMENT_PROCESSING: AppliedWorkflowDefinition(
                workflow_type=AppliedWorkflowType.DOCUMENT_PROCESSING,
                display_name="Document Processing",
                description="Extract and structure business documents safely.",
                input_schema={"type": "string", "format": "binary"},
                output_schema={"$ref": "#/components/schemas/DocumentProcessingResult"},
                required_capabilities=["structured_output"],
                allowed_roles=common_roles,
                job_type=JobType.DOCUMENT_PROCESSING,
                business_impact_task_type="document_processing",
                prompt_template_slug="document-processing",
                enabled=True,
            ),
            AppliedWorkflowType.IMAGE_GENERATION: AppliedWorkflowDefinition(
                workflow_type=AppliedWorkflowType.IMAGE_GENERATION,
                display_name="Image Generation",
                description="Generate review-gated campaign imagery.",
                input_schema={"$ref": "#/components/schemas/ImageGenerationRequest"},
                output_schema={"$ref": "#/components/schemas/MediaAssetRead"},
                required_capabilities=["image_generation"],
                allowed_roles=common_roles,
                job_type=JobType.IMAGE_GENERATION,
                business_impact_task_type="image_generation",
                prompt_template_slug="campaign-image-generation",
                enabled=True,
            ),
            AppliedWorkflowType.VIDEO_STORYBOARD: AppliedWorkflowDefinition(
                workflow_type=AppliedWorkflowType.VIDEO_STORYBOARD,
                display_name="Video Storyboard",
                description="Create a structured storyboard for human review.",
                input_schema={"$ref": "#/components/schemas/VideoStoryboardRequest"},
                output_schema={"$ref": "#/components/schemas/VideoStoryboard"},
                required_capabilities=["structured_output"],
                allowed_roles=common_roles,
                job_type=JobType.VIDEO_STORYBOARD,
                business_impact_task_type="video_storyboard",
                prompt_template_slug="video-storyboard",
                enabled=True,
            ),
        }

    def list(self) -> list[AppliedWorkflowDefinition]:
        return list(self._definitions.values())

    def get(self, workflow_type: AppliedWorkflowType) -> AppliedWorkflowDefinition:
        return self._definitions[workflow_type]
