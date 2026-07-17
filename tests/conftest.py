from typing import Any

import pytest


@pytest.fixture
def valid_campaign_payload() -> dict[str, Any]:
    return {
        "campaign_id": "CL-PREREG-001",
        "game_name": "Cyber Legends",
        "genre": "Action RPG",
        "target_audience": "18-30 tuổi",
        "market": "Việt Nam",
        "platforms": ["facebook", "TikTok", "FACEBOOK"],
        "campaign_objective": "Thu hút người chơi đăng ký trước",
        "tone": "Cyberpunk, mạnh mẽ, hành động",
        "launch_date": "2026-08-15",
        "promotion": "Nhân vật giới hạn và 500 Gem",
        "raw_brief": "  Chiến dịch đăng ký trước  ",
    }
