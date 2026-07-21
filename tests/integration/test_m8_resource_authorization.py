from __future__ import annotations

import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.constants import (
    AppliedTaskStatus,
    AppliedWorkflowType,
    MediaAssetStatus,
    MediaAssetType,
)
from app.database.models import AppliedWorkflowTaskModel, MediaAssetModel
from app.database.session import AsyncSessionLocal

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_TESTS") != "1",
        reason="set RUN_POSTGRES_TESTS=1 to run PostgreSQL integration tests",
    ),
]

USER_A = {"x-actor-id": "m8-user-a", "x-actor-role": "marketing"}
USER_B = {"x-actor-id": "m8-user-b", "x-actor-role": "marketing"}
MANAGER = {"x-actor-id": "m8-manager", "x-actor-role": "manager"}


@pytest_asyncio.fixture(autouse=True)
async def clean_database() -> AsyncIterator[None]:
    statement = text(
        "TRUNCATE media_reviews, media_generation_attempts, media_assets, "
        "ai_task_impacts, user_feedback, applied_workflow_tasks, n8n_webhook_receipts, "
        "outbox_events, job_attempts, background_jobs, agent_tool_calls, agent_runs, "
        "approval_records, workflow_runs, campaigns RESTART IDENTITY CASCADE"
    )
    async with AsyncSessionLocal() as session:
        await session.execute(statement)
        await session.commit()
    yield
    async with AsyncSessionLocal() as session:
        await session.execute(statement)
        await session.commit()


@pytest_asyncio.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


def campaign_payload(campaign_id: str) -> dict[str, object]:
    return {
        "campaign_id": campaign_id,
        "game_name": "Cyber Legends",
        "genre": "Action RPG",
        "target_audience": "18-30",
        "market": "Vietnam",
        "platforms": ["Facebook"],
        "campaign_objective": "Drive registrations",
        "tone": "Confident",
        "launch_date": "2026-08-15",
        "promotion": "Launch reward",
    }


@pytest.mark.asyncio
async def test_campaign_workflow_job_and_timeline_block_cross_user_idor(
    api_client: AsyncClient,
) -> None:
    campaign_id = "CL-M8-IDOR"
    created = await api_client.post(
        "/campaigns", json=campaign_payload(campaign_id), headers=USER_A
    )
    assert created.status_code == 201
    workflow = await api_client.post(
        f"/workflows/campaigns/{campaign_id}", headers=USER_A
    )
    assert workflow.status_code == 201
    workflow_id = workflow.json()["workflow_id"]
    queued = await api_client.post(f"/workflows/{workflow_id}/run", headers=USER_A)
    assert queued.status_code == 202
    job_id = queued.json()["job_id"]

    protected_urls = [
        f"/campaigns/{campaign_id}",
        f"/workflows/{workflow_id}",
        f"/jobs/{job_id}",
        f"/jobs/{job_id}/status",
        f"/operations/campaigns/{campaign_id}/timeline",
        f"/operations/workflows/{workflow_id}/timeline",
    ]
    for url in protected_urls:
        assert (await api_client.get(url, headers=USER_B)).status_code == 403
        assert (await api_client.get(url, headers=MANAGER)).status_code == 200

    assert (await api_client.get("/campaigns", headers=USER_B)).json() == []
    assert (await api_client.get("/workflows", headers=USER_B)).json() == []
    assert len((await api_client.get("/campaigns", headers=MANAGER)).json()) == 1


@pytest.mark.asyncio
async def test_task_and_media_collections_filter_owners(
    api_client: AsyncClient,
) -> None:
    task_a = uuid4()
    task_b = uuid4()
    asset_a = uuid4()
    asset_b = uuid4()
    async with AsyncSessionLocal() as session:
        session.add_all(
            [
                AppliedWorkflowTaskModel(
                    task_run_id=task_a,
                    workflow_type=AppliedWorkflowType.DATA_ANALYSIS.value,
                    status=AppliedTaskStatus.COMPLETED.value,
                    input_metadata={"filename": "a.csv"},
                    result={"rows": 1},
                    created_by=USER_A["x-actor-id"],
                ),
                AppliedWorkflowTaskModel(
                    task_run_id=task_b,
                    workflow_type=AppliedWorkflowType.DOCUMENT_PROCESSING.value,
                    status=AppliedTaskStatus.COMPLETED.value,
                    input_metadata={"filename": "b.txt"},
                    result={"summary": "safe"},
                    created_by=USER_B["x-actor-id"],
                ),
                MediaAssetModel(
                    media_asset_id=asset_a,
                    task_type="campaign_image",
                    asset_type=MediaAssetType.IMAGE.value,
                    status=MediaAssetStatus.READY_FOR_REVIEW.value,
                    provider="mock",
                    model="mock-image",
                    generation_prompt="owner A image",
                    safety_status="READY_FOR_HUMAN_REVIEW",
                    created_by=USER_A["x-actor-id"],
                ),
                MediaAssetModel(
                    media_asset_id=asset_b,
                    task_type="video_storyboard",
                    asset_type=MediaAssetType.VIDEO_STORYBOARD.value,
                    status=MediaAssetStatus.REQUESTED.value,
                    provider="mock",
                    model="mock-storyboard",
                    generation_prompt="owner B storyboard",
                    safety_status="PENDING",
                    created_by=USER_B["x-actor-id"],
                ),
            ]
        )
        await session.commit()

    assert (
        await api_client.get(f"/data-analysis/tasks/{task_a}", headers=USER_B)
    ).status_code == 403
    assert (
        await api_client.get(f"/media/assets/{asset_a}", headers=USER_B)
    ).status_code == 403
    tasks_a = await api_client.get("/applied-workflow-tasks", headers=USER_A)
    assets_a = await api_client.get("/media/assets", headers=USER_A)
    storyboards_b = await api_client.get("/media/storyboards", headers=USER_B)
    assert [row["task_run_id"] for row in tasks_a.json()] == [str(task_a)]
    assert [row["media_asset_id"] for row in assets_a.json()] == [str(asset_a)]
    assert [row["media_asset_id"] for row in storyboards_b.json()] == [str(asset_b)]

    assert (
        len((await api_client.get("/applied-workflow-tasks", headers=MANAGER)).json())
        == 2
    )
    assert len((await api_client.get("/media/assets", headers=MANAGER)).json()) == 2
