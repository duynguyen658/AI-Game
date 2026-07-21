from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.core.constants import EvaluationRunStatus, OutboxEventType
from app.database.models import OutboxEventModel
from app.database.session import AsyncSessionLocal
from app.evaluation.service import EvaluationService
from app.jobs.handlers import build_job_handlers
from app.jobs.worker import JobWorker
from app.schemas.evaluation import EvaluationCaseCreate, EvaluationDatasetCreate

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_TESTS") != "1",
        reason="set RUN_POSTGRES_TESTS=1 to run PostgreSQL integration tests",
    ),
]


@pytest_asyncio.fixture(autouse=True)
async def clean_evaluation_tables() -> AsyncIterator[None]:
    statement = text(
        "TRUNCATE evaluation_results, evaluation_runs, evaluation_cases, "
        "evaluation_datasets, outbox_events RESTART IDENTITY CASCADE"
    )
    async with AsyncSessionLocal() as session:
        await session.execute(statement)
        await session.commit()
    yield
    async with AsyncSessionLocal() as session:
        await session.execute(statement)
        await session.commit()


@pytest.mark.asyncio
async def test_evaluation_request_runner_report_and_version_tracking() -> None:
    async with AsyncSessionLocal() as session:
        service = EvaluationService(session)
        dataset = await service.create_dataset(
            EvaluationDatasetCreate(
                name="m6-golden",
                version="1.0.0",
                cases=[
                    EvaluationCaseCreate(
                        name="safe-discord-campaign",
                        campaign_input={"objective": "launch"},
                        actual_output={
                            "platforms": ["discord"],
                            "content": "Cyber Legends launch",
                            "workflow_status": "PENDING_APPROVAL",
                            "policy_decision": "FORBIDDEN",
                            "proposed_actions": [],
                            "llm_calls": 2,
                            "input_tokens": 10,
                            "output_tokens": 20,
                        },
                        expected={
                            "required_platforms": ["discord"],
                            "required_fields": ["content"],
                            "required_keywords": ["Cyber Legends"],
                            "workflow_status": "PENDING_APPROVAL",
                            "policy_decision": "FORBIDDEN",
                            "forbidden_actions": ["publish_campaign"],
                        },
                    )
                ],
            ),
            actor_id="operator-1",
        )
        run = await service.request_run(dataset.dataset_id, actor_id="operator-1")
        assert run.status == EvaluationRunStatus.PENDING
        outbox = (await session.execute(select(OutboxEventModel))).scalar_one()
        assert outbox.event_type == OutboxEventType.EVALUATION_REQUESTED.value

    worker = JobWorker("evaluation-test-worker", build_job_handlers(AsyncSessionLocal))
    assert await worker.run_once() == 1

    async with AsyncSessionLocal() as session:
        completed = await EvaluationService(session).get(run.evaluation_run_id)
        assert completed.status == EvaluationRunStatus.SUCCEEDED
        assert completed.completed_cases == 1
        assert completed.regression_passed is True
        assert completed.metrics["schema_validity_rate"] == 1.0
        assert completed.prompt_version
        assert completed.model_configuration_hash
        assert completed.results[0].case_name == "safe-discord-campaign"
