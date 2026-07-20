from app.agentic.agents.base import BaseSpecialistAgent
from app.core.constants import AgentName
from app.schemas.campaign import GeneratedContent


class ContentGeneratorAgent(BaseSpecialistAgent[GeneratedContent]):
    name = AgentName.CONTENT_GENERATOR
    output_schema = GeneratedContent
    allowed_tool_names = frozenset(
        {
            "get_campaign",
            "get_workflow",
            "get_brief_analysis",
            "get_previous_quality_review",
            "get_previous_revision",
        }
    )
    prompt_file = "content_generator.md"
