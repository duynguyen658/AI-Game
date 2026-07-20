from app.agentic.agents.base import BaseSpecialistAgent
from app.core.constants import AgentName
from app.schemas.campaign import QualityReview


class ContentReviewerAgent(BaseSpecialistAgent[QualityReview]):
    name = AgentName.CONTENT_REVIEWER
    output_schema = QualityReview
    allowed_tool_names = frozenset(
        {
            "get_previous_quality_review",
        }
    )
    prompt_file = "content_reviewer.md"
