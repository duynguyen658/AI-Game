import pytest

from app.core.exceptions import LLMResponseError, LLMTimeoutError
from app.llm.mock_client import MockLLMClient, mock_timeout
from app.llm.structured_output import validate_structured_output
from app.schemas.campaign import BriefAnalysis, GeneratedContent, QualityReview


@pytest.mark.asyncio
async def test_mock_llm_returns_deterministic_outputs() -> None:
    client = MockLLMClient()

    analysis = await client.generate_structured(
        system_prompt="analyze",
        user_prompt="brief",
        output_schema=BriefAnalysis,
    )
    content = await client.generate_structured(
        system_prompt="generate",
        user_prompt="analysis",
        output_schema=GeneratedContent,
    )
    review = await client.generate_structured(
        system_prompt="review",
        user_prompt="content",
        output_schema=QualityReview,
    )

    assert analysis.summary.startswith("Cyber Legends")
    assert content.facebook is not None
    assert review.quality_score == 88


@pytest.mark.asyncio
async def test_mock_llm_supports_scripted_failures() -> None:
    client = MockLLMClient(scripted_failures=[mock_timeout()])

    with pytest.raises(LLMTimeoutError):
        await client.generate_structured(
            system_prompt="analyze",
            user_prompt="brief",
            output_schema=BriefAnalysis,
        )


def test_structured_output_rejects_malformed_json() -> None:
    with pytest.raises(LLMResponseError, match="not valid JSON"):
        validate_structured_output("{", BriefAnalysis)


def test_structured_output_rejects_schema_mismatch() -> None:
    with pytest.raises(LLMResponseError, match="expected schema"):
        validate_structured_output({"summary": ""}, BriefAnalysis)
