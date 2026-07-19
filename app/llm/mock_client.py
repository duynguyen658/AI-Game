from __future__ import annotations

import asyncio
from collections import deque
from typing import Deque

from pydantic import BaseModel

from app.core.exceptions import LLMProviderError, LLMResponseError, LLMTimeoutError
from app.schemas.campaign import (
    BriefAnalysis,
    DiscordContent,
    FacebookContent,
    GeneratedContent,
    QualityReview,
    TikTokContent,
    TikTokScene,
)


class MockLLMClient:
    def __init__(self, scripted_failures: list[Exception] | None = None) -> None:
        self.scripted_failures: Deque[Exception] = deque(scripted_failures or [])

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[BaseModel],
    ) -> BaseModel:
        del system_prompt, user_prompt
        await asyncio.sleep(0)
        if self.scripted_failures:
            raise self.scripted_failures.popleft()
        if output_schema is BriefAnalysis:
            return BriefAnalysis(
                summary="Cyber Legends pre-registration campaign for core action RPG players.",
                campaign_objective="Drive pre-registration before launch.",
                target_audience="Action RPG players aged 18-30.",
                main_message="Register early to claim limited launch rewards.",
                key_benefits=["Limited character", "500 Gem launch reward"],
                content_requirements=["Platform-specific CTA", "Cyberpunk tone"],
                missing_information=[],
                risk_flags=[],
            )
        if output_schema is GeneratedContent:
            return GeneratedContent(
                facebook=FacebookContent(
                    headline="Cyber Legends pre-registration is open",
                    content="Enter a neon action RPG world and reserve your launch rewards.",
                    cta="Pre-register now",
                    hashtags=["#CyberLegends", "#ActionRPG"],
                ),
                tiktok=TikTokContent(
                    hook="Your cyberpunk squad is calling.",
                    scenes=[
                        TikTokScene(
                            order=1,
                            duration_seconds=3,
                            visual="Neon city reveal with hero team silhouettes.",
                            text_overlay="Cyber Legends",
                        )
                    ],
                    voiceover="Pre-register for Cyber Legends and claim limited rewards.",
                    cta="Join before launch",
                ),
                discord=DiscordContent(
                    title="Cyber Legends pre-registration is live",
                    message="Reserve your place before launch and unlock limited rewards.",
                    cta="Pre-register now",
                ),
            )
        if output_schema is QualityReview:
            return QualityReview(
                status="PASS",
                quality_score=88,
                factual_accuracy_score=90,
                tone_score=86,
                platform_fit_score=88,
                issues=[],
                suggestions=["Localize CTA for each target market."],
                requires_human_review=True,
            )
        raise LLMResponseError("Mock client has no response for requested schema")


def mock_timeout() -> LLMTimeoutError:
    return LLMTimeoutError("Mock LLM timeout")


def mock_provider_error() -> LLMProviderError:
    return LLMProviderError("Mock provider error")
