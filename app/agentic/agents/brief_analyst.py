from app.agentic.agents.base import BaseSpecialistAgent
from app.core.constants import AgentName
from app.schemas.campaign import BriefAnalysis


class BriefAnalystAgent(BaseSpecialistAgent[BriefAnalysis]):
    name = AgentName.BRIEF_ANALYST
    output_schema = BriefAnalysis
    allowed_tool_names = frozenset({"get_previous_workflow_summary"})
    prompt_file = "brief_analyst.md"
