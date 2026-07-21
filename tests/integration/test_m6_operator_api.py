from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.config import get_settings
from app.core.constants import AlertType, SecuritySeverity
from app.database.session import AsyncSessionLocal
from app.operations.alerts import AlertService

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_TESTS") != "1",
        reason="set RUN_POSTGRES_TESTS=1 to run PostgreSQL integration tests",
    ),
]

MANAGER_HEADERS = {"x-actor-id": "manager-1", "x-actor-role": "manager"}


@pytest_asyncio.fixture(autouse=True)
async def clean_database() -> AsyncIterator[None]:
    statement = text(
        "TRUNCATE evaluation_results, evaluation_runs, evaluation_cases, "
        "evaluation_datasets, operational_alerts, outbox_events, job_attempts, "
        "background_jobs, worker_heartbeats, approval_records, workflow_runs, "
        "campaigns, security_events RESTART IDENTITY CASCADE"
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


@pytest.mark.asyncio
async def test_health_metrics_operator_authorization_and_lifecycles(
    api_client: AsyncClient,
) -> None:
    correlation_id = "6a6e1b0d-596f-49e8-8381-72fb1e036adb"
    live = await api_client.get("/live", headers={"x-correlation-id": correlation_id})
    assert live.status_code == 200
    assert live.json()["version"] == "1.0.0-rc.1"
    assert live.headers["x-correlation-id"] == correlation_id
    assert live.headers["x-content-type-options"] == "nosniff"
    assert (await api_client.get("/health")).status_code == 200
    assert (await api_client.get("/ready")).status_code == 200
    metrics = await api_client.get("/metrics")
    assert metrics.status_code == 401
    metrics = await api_client.get(
        "/metrics",
        headers={
            "Authorization": (
                f"Bearer {get_settings().metrics_token.get_secret_value()}"
            )
        },
    )
    assert metrics.status_code == 200
    assert "http_requests_total" in metrics.text

    assert (await api_client.get("/jobs")).status_code == 401
    assert (
        await api_client.get(
            "/jobs", headers={"x-actor-id": "reviewer-1", "x-actor-role": "reviewer"}
        )
    ).status_code == 403

    campaign = await api_client.post(
        "/campaigns",
        json={
            "campaign_id": "CL-M6-OPS",
            "game_name": "Cyber Legends",
            "genre": "Action RPG",
            "target_audience": "18-30",
            "market": "Vietnam",
            "platforms": ["Facebook", "TikTok"],
            "campaign_objective": "Drive pre-registration",
            "tone": "Cyberpunk action",
            "launch_date": "2026-08-15",
            "promotion": "Launch rewards",
            "raw_brief": "Pre-registration campaign",
        },
    )
    assert campaign.status_code == 201
    workflow = await api_client.post("/workflows/campaigns/CL-M6-OPS")
    workflow_id = workflow.json()["workflow_id"]
    queued = await api_client.post(f"/workflows/{workflow_id}/run")
    assert queued.status_code == 202
    job_id = queued.json()["job_id"]
    assert queued.json()["status_url"] == f"/jobs/{job_id}/status"
    assert (await api_client.get(f"/jobs/{job_id}/status")).status_code == 401
    safe_status = await api_client.get(
        f"/jobs/{job_id}/status",
        headers={"x-actor-id": "marketing-1", "x-actor-role": "marketing"},
    )
    assert safe_status.status_code == 200
    assert safe_status.json()["job_id"] == job_id
    assert "payload" not in safe_status.json()
    assert "locked_by" not in safe_status.json()
    job = await api_client.get(f"/jobs/{job_id}", headers=MANAGER_HEADERS)
    assert job.status_code == 200
    cancelled = await api_client.post(f"/jobs/{job_id}/cancel", headers=MANAGER_HEADERS)
    assert cancelled.json()["status"] == "CANCELLED"

    async with AsyncSessionLocal() as session:
        alert = await AlertService(session).open(
            alert_type=AlertType.JOB_DEAD_LETTER,
            severity=SecuritySeverity.HIGH,
            resource_type="job",
            resource_id=job_id,
            summary="Injected operator test alert",
        )
    acknowledged = await api_client.post(
        f"/alerts/{alert.alert_id}/acknowledge", headers=MANAGER_HEADERS
    )
    assert acknowledged.json()["status"] == "ACKNOWLEDGED"
    resolved = await api_client.post(
        f"/alerts/{alert.alert_id}/resolve", headers=MANAGER_HEADERS
    )
    assert resolved.json()["status"] == "RESOLVED"

    summary = await api_client.get("/operations/summary", headers=MANAGER_HEADERS)
    assert summary.status_code == 200
    assert summary.json()["application_version"] == "1.0.0-rc.1"
    assert summary.json()["jobs"]["CANCELLED"] == 1
    timeline = await api_client.get(
        f"/operations/workflows/{workflow_id}/timeline", headers=MANAGER_HEADERS
    )
    assert timeline.status_code == 200
    assert [event["occurred_at"] for event in timeline.json()] == sorted(
        event["occurred_at"] for event in timeline.json()
    )
    user_timeline = await api_client.get(
        f"/operations/workflows/{workflow_id}/timeline",
        headers={"x-actor-id": "marketing-1", "x-actor-role": "marketing"},
    )
    assert user_timeline.status_code == 200
    assert (
        await api_client.get(f"/operations/workflows/{workflow_id}/timeline")
    ).status_code == 401

    dataset = await api_client.post(
        "/evaluations/datasets",
        headers=MANAGER_HEADERS,
        json={
            "name": "api-golden",
            "version": "1",
            "cases": [
                {
                    "name": "safe-case",
                    "campaign_input": {"objective": "launch"},
                    "actual_output": {
                        "content": "Cyber Legends launch",
                        "platforms": ["discord"],
                        "policy_decision": "FORBIDDEN",
                        "proposed_actions": [],
                    },
                    "expected": {
                        "required_fields": ["content"],
                        "required_platforms": ["discord"],
                        "policy_decision": "FORBIDDEN",
                        "forbidden_actions": ["publish_campaign"],
                    },
                }
            ],
        },
    )
    assert dataset.status_code == 201
    evaluation = await api_client.post(
        "/evaluations",
        headers=MANAGER_HEADERS,
        json={
            "dataset_id": dataset.json()["dataset_id"],
            "execution_mode": "SNAPSHOT",
        },
    )
    assert evaluation.status_code == 202
    assert evaluation.json()["status"] == "PENDING"
