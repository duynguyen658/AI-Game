def test_public_schema_exports_are_importable() -> None:
    from app.schemas import (
        ApprovalRecord,
        ApprovalRequest,
        BriefAnalysis,
        CampaignCreate,
        CampaignRecord,
        DiscordContent,
        FacebookContent,
        GeneratedContent,
        QualityReview,
        SecurityEvent,
        TikTokContent,
        TikTokScene,
        WorkflowRun,
    )

    exported_types = [
        ApprovalRecord,
        ApprovalRequest,
        BriefAnalysis,
        CampaignCreate,
        CampaignRecord,
        DiscordContent,
        FacebookContent,
        GeneratedContent,
        QualityReview,
        SecurityEvent,
        TikTokContent,
        TikTokScene,
        WorkflowRun,
    ]

    assert all(item is not None for item in exported_types)
