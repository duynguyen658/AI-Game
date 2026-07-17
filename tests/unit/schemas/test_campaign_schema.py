from typing import Any

import pytest
from pydantic import ValidationError

from app.core.constants import CampaignStatus, Platform
from app.schemas.campaign import (
    CampaignCreate,
    CampaignRecord,
    DiscordContent,
    FacebookContent,
    GeneratedContent,
    QualityReview,
    TikTokContent,
    TikTokScene,
)


def test_campaign_accepts_valid_payload(
    valid_campaign_payload: dict[str, Any],
) -> None:
    campaign = CampaignCreate.model_validate(valid_campaign_payload)

    assert campaign.campaign_id == "CL-PREREG-001"
    assert campaign.game_name == "Cyber Legends"
    assert campaign.launch_date.isoformat() == "2026-08-15"


def test_campaign_normalizes_and_deduplicates_platforms(
    valid_campaign_payload: dict[str, Any],
) -> None:
    campaign = CampaignCreate.model_validate(valid_campaign_payload)

    assert campaign.platforms == [
        Platform.FACEBOOK,
        Platform.TIKTOK,
    ]


def test_campaign_strips_whitespace(
    valid_campaign_payload: dict[str, Any],
) -> None:
    campaign = CampaignCreate.model_validate(valid_campaign_payload)

    assert campaign.raw_brief == "Chiến dịch đăng ký trước"


def test_empty_raw_brief_becomes_none(
    valid_campaign_payload: dict[str, Any],
) -> None:
    valid_campaign_payload["raw_brief"] = "   "

    campaign = CampaignCreate.model_validate(valid_campaign_payload)

    assert campaign.raw_brief is None


@pytest.mark.parametrize(
    "campaign_id",
    [
        "ab",
        "campaign id",
        "-invalid",
        "_invalid",
        "game@2026",
    ],
)
def test_campaign_rejects_invalid_campaign_id(
    valid_campaign_payload: dict[str, Any],
    campaign_id: str,
) -> None:
    valid_campaign_payload["campaign_id"] = campaign_id

    with pytest.raises(ValidationError):
        CampaignCreate.model_validate(valid_campaign_payload)


def test_campaign_rejects_unsupported_platform(
    valid_campaign_payload: dict[str, Any],
) -> None:
    valid_campaign_payload["platforms"] = ["Facebook", "Instagram"]

    with pytest.raises(ValidationError):
        CampaignCreate.model_validate(valid_campaign_payload)


def test_campaign_rejects_non_list_platforms(
    valid_campaign_payload: dict[str, Any],
) -> None:
    valid_campaign_payload["platforms"] = "Facebook"

    with pytest.raises(ValidationError, match="platforms must be a list"):
        CampaignCreate.model_validate(valid_campaign_payload)


def test_campaign_rejects_empty_platform_list(
    valid_campaign_payload: dict[str, Any],
) -> None:
    valid_campaign_payload["platforms"] = []

    with pytest.raises(ValidationError):
        CampaignCreate.model_validate(valid_campaign_payload)


def test_campaign_rejects_unknown_field(
    valid_campaign_payload: dict[str, Any],
) -> None:
    valid_campaign_payload["api_key"] = "must-not-be-accepted"

    with pytest.raises(
        ValidationError,
        match="Extra inputs are not permitted",
    ):
        CampaignCreate.model_validate(valid_campaign_payload)


def test_generated_content_supports_each_platform_schema() -> None:
    content = GeneratedContent(
        facebook=FacebookContent(
            headline="Cyber Legends mở đăng ký trước",
            content="Tham gia thế giới cyberpunk ngay hôm nay.",
            cta="Đăng ký ngay",
            hashtags=["#CyberLegends"],
        ),
        tiktok=TikTokContent(
            hook="Bạn đã sẵn sàng bước vào tương lai?",
            scenes=[
                TikTokScene(
                    order=1,
                    duration_seconds=3,
                    visual="Thành phố cyberpunk về đêm",
                    text_overlay="Cyber Legends",
                )
            ],
            voiceover="Đăng ký trước để nhận quà giới hạn.",
            cta="Đăng ký ngay",
        ),
        discord=DiscordContent(
            title="Pre-registration is open",
            message="Cyber Legends đã mở đăng ký trước.",
            cta="Đăng ký ngay",
        ),
    )

    assert content.facebook is not None
    assert content.tiktok is not None
    assert content.discord is not None


@pytest.mark.parametrize("score", [-1, 101])
def test_quality_review_rejects_score_outside_range(score: int) -> None:
    with pytest.raises(ValidationError):
        QualityReview(
            status="PASS",
            quality_score=score,
            factual_accuracy_score=90,
            tone_score=90,
            platform_fit_score=90,
        )


def test_quality_review_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        QualityReview(
            status="UNKNOWN",
            quality_score=90,
            factual_accuracy_score=90,
            tone_score=90,
            platform_fit_score=90,
        )


def test_campaign_record_uses_safe_defaults(
    valid_campaign_payload: dict[str, Any],
) -> None:
    campaign = CampaignCreate.model_validate(valid_campaign_payload)
    record = CampaignRecord(campaign=campaign)

    assert record.status == CampaignStatus.RECEIVED
    assert record.retry_count == 0
    assert record.version == 1
    assert record.created_at.tzinfo is not None
    assert record.updated_at.tzinfo is not None


def test_campaign_record_validates_assignment(
    valid_campaign_payload: dict[str, Any],
) -> None:
    campaign = CampaignCreate.model_validate(valid_campaign_payload)
    record = CampaignRecord(campaign=campaign)

    with pytest.raises(ValidationError):
        record.retry_count = -1
