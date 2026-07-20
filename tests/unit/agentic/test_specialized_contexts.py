from datetime import date
from uuid import uuid4

from app.agentic.state.campaign_context import (
    BriefAnalysisContext,
    ContentGenerationContext,
    ContentReviewContext,
)
from app.core.constants import CampaignStatus
from app.schemas.campaign import BriefAnalysis, FacebookContent, GeneratedContent


def common() -> dict[str, object]:
    return {
        "campaign_id": "CL-CONTEXT",
        "workflow_id": uuid4(),
        "revision_number": 1,
        "current_workflow_status": CampaignStatus.GENERATING,
        "retry_count": 1,
        "parent_workflow_id": uuid4(),
    }


def analysis() -> BriefAnalysis:
    return BriefAnalysis(
        summary="Summary",
        campaign_objective="Register",
        target_audience="18-30",
        main_message="Join now",
    )


def content() -> GeneratedContent:
    return GeneratedContent(
        facebook=FacebookContent(
            headline="Launch",
            content="Register now",
            cta="Join",
        )
    )


def test_brief_context_excludes_generated_artifacts() -> None:
    context = BriefAnalysisContext.model_validate(
        {
            **common(),
            "game_name": "Cyber Legends",
            "genre": "RPG",
            "target_audience": "18-30",
            "market": "Vietnam",
            "platforms": ["Facebook"],
            "campaign_objective": "Register",
            "tone": "Action",
            "launch_date": date(2026, 8, 15),
            "promotion": "500 gems",
            "raw_brief": "Brief",
        }
    )
    fields = context.model_dump().keys()
    assert "generated_content" not in fields
    assert "prior_quality_review" not in fields
    assert "brief_analysis" not in fields


def test_generator_and_reviewer_contexts_have_minimum_distinct_fields() -> None:
    generator = ContentGenerationContext.model_validate(
        {
            **common(),
            "game_name": "Cyber Legends",
            "target_audience": "18-30",
            "market": "Vietnam",
            "platforms": ["Facebook"],
            "campaign_objective": "Register",
            "tone": "Action",
            "launch_date": date(2026, 8, 15),
            "promotion": "500 gems",
            "raw_brief": "Brief",
            "brief_analysis": analysis(),
            "prior_generated_content": content(),
        }
    )
    reviewer = ContentReviewContext.model_validate(
        {
            **common(),
            "current_workflow_status": CampaignStatus.REVIEWING,
            "campaign_objective": "Register",
            "platforms": ["Facebook"],
            "tone": "Action",
            "brief_analysis": analysis(),
            "generated_content": content(),
        }
    )
    assert "prior_generated_content" in generator.model_fields_set
    assert "generated_content" not in generator.model_dump()
    assert "generated_content" in reviewer.model_dump()
    assert "raw_brief" not in reviewer.model_dump()
    assert "target_audience" not in reviewer.model_dump()
