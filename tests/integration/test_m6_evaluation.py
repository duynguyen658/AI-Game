from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import date
import json
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.core.constants import (
    EvaluationExecutionMode,
    EvaluationRunStatus,
    OutboxEventType,
)
from app.core.exceptions import EvaluationConflictError, JobCancelledError
from app.database.models import CampaignModel, OutboxEventModel, WorkflowRunModel
from app.database.session import AsyncSessionLocal
from app.evaluation.runner import EvaluationRunner
from app.evaluation.service import EvaluationService
from app.jobs.handlers import build_job_handlers
from app.jobs.worker import JobWorker
from app.schemas.evaluation import EvaluationCaseCreate, EvaluationDatasetCreate
from app.service.campaign_service import CampaignService

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
        "TRUNCATE evaluation_datasets, campaigns, outbox_events, job_attempts, "
        "background_jobs, worker_heartbeats RESTART IDENTITY CASCADE"
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
        run = await service.request_run(
            dataset.dataset_id,
            execution_mode=EvaluationExecutionMode.SNAPSHOT,
            actor_id="operator-1",
        )
        assert run.status == EvaluationRunStatus.PENDING
        outbox = (await session.execute(select(OutboxEventModel))).scalar_one()
        assert outbox.event_type == OutboxEventType.EVALUATION_REQUESTED.value

    worker = JobWorker("evaluation-test-worker", build_job_handlers(AsyncSessionLocal))
    assert await worker.run_once() == 1

    async with AsyncSessionLocal() as session:
        completed = await EvaluationService(session).get(run.evaluation_run_id)
        assert completed.status == EvaluationRunStatus.SUCCEEDED
        assert completed.execution_mode == EvaluationExecutionMode.SNAPSHOT
        assert completed.completed_cases == 1
        assert completed.regression_passed is True
        assert completed.metrics["schema_validity_rate"] == 1.0
        assert completed.prompt_version
        assert completed.model_configuration_hash
        assert completed.results[0].case_name == "safe-discord-campaign"


def system_campaign_input() -> dict[str, object]:
    return {
        "campaign_id": "replaced-by-system-runner",
        "game_name": "Cyber Legends",
        "genre": "Action RPG",
        "target_audience": "Players aged 18-30",
        "market": "Vietnam",
        "platforms": ["Discord"],
        "campaign_objective": "Drive pre-registration",
        "tone": "Cyberpunk action",
        "launch_date": date(2026, 8, 15).isoformat(),
        "promotion": "Limited hero and 500 gems",
        "raw_brief": "Deterministic SYSTEM evaluation",
    }


@pytest.mark.asyncio
async def test_system_evaluation_runs_real_workflow_and_isolates_campaigns() -> None:
    async with AsyncSessionLocal() as session:
        service = EvaluationService(session)
        dataset = await service.create_dataset(
            EvaluationDatasetCreate(
                name="m6-system-happy",
                version="1",
                cases=[
                    EvaluationCaseCreate(
                        name="happy-workflow",
                        campaign_input=system_campaign_input(),
                        system_config={"scenario": "happy"},
                        expected={
                            "required_platforms": ["Discord"],
                            "required_fields": ["content"],
                            "required_keywords": ["Cyber Legends"],
                            "workflow_status": "PENDING_APPROVAL",
                            "forbidden_actions": ["publish-campaign"],
                            "max_llm_calls": 5,
                            "max_tool_calls": 8,
                            "max_action_count": 3,
                        },
                    )
                ],
            ),
            actor_id="evaluation-operator",
        )
        run = await service.request_run(
            dataset.dataset_id,
            execution_mode=EvaluationExecutionMode.SYSTEM,
            actor_id="evaluation-operator",
        )

    await EvaluationRunner().run(run.evaluation_run_id)

    async with AsyncSessionLocal() as session:
        completed = await EvaluationService(session).get(run.evaluation_run_id)
        assert completed.status == EvaluationRunStatus.SUCCEEDED
        assert completed.execution_mode == EvaluationExecutionMode.SYSTEM
        assert completed.regression_passed is True
        assert completed.results[0].status.value == "PASSED"
        campaign = (await session.execute(select(CampaignModel))).scalar_one()
        workflow = (await session.execute(select(WorkflowRunModel))).scalar_one()
        assert campaign.is_evaluation is True
        assert campaign.evaluation_run_id == run.evaluation_run_id
        assert workflow.is_evaluation is True
        assert workflow.evaluation_case_id is not None
        assert await CampaignService(session).list_campaigns() == []


@pytest.mark.asyncio
async def test_system_mode_rejects_client_supplied_actual_output() -> None:
    async with AsyncSessionLocal() as session:
        service = EvaluationService(session)
        dataset = await service.create_dataset(
            EvaluationDatasetCreate(
                name="invalid-system-snapshot",
                version="1",
                cases=[
                    EvaluationCaseCreate(
                        name="cannot-fake-output",
                        campaign_input=system_campaign_input(),
                        actual_output={"workflow_status": "PENDING_APPROVAL"},
                        expected={"workflow_status": "PENDING_APPROVAL"},
                    )
                ],
            ),
            actor_id="evaluation-operator",
        )
        with pytest.raises(EvaluationConflictError):
            await service.request_run(
                dataset.dataset_id,
                execution_mode=EvaluationExecutionMode.SYSTEM,
                actor_id="evaluation-operator",
            )


@pytest.mark.asyncio
async def test_golden_m6_system_dataset_passes_committed_regression_gate() -> None:
    scenarios = [
        ("happy-workflow", "happy", {"workflow_status": "PENDING_APPROVAL"}),
        (
            "retry-workflow",
            "retry",
            {"workflow_status": "PENDING_APPROVAL", "retry_count": 1},
        ),
        (
            "manual-review-workflow",
            "manual_review",
            {"workflow_status": "MANUAL_REVIEW_REQUIRED"},
        ),
        (
            "forbidden-action",
            "forbidden_action",
            {
                "workflow_status": "PENDING_APPROVAL",
                "policy_decision": "FORBIDDEN",
                "forbidden_actions": ["publish-campaign"],
            },
        ),
        (
            "approval-required-action",
            "approval_required",
            {
                "workflow_status": "PENDING_APPROVAL",
                "policy_decision": "APPROVAL_REQUIRED",
            },
        ),
        (
            "agent-limit-exceeded",
            "agent_limit",
            {"workflow_status": "FAILED", "agent_status": "LIMIT_EXCEEDED"},
        ),
        (
            "provider-failure",
            "provider_failure",
            {"workflow_status": "FAILED", "agent_status": "FAILED"},
        ),
        (
            "revision-workflow",
            "revision",
            {"workflow_status": "PENDING_APPROVAL", "revision_number": 1},
        ),
    ]
    cases = []
    for name, scenario, scenario_expected in scenarios:
        expected = {
            "max_llm_calls": 6,
            "max_tool_calls": 5,
            "max_action_count": 3,
            **scenario_expected,
        }
        cases.append(
            EvaluationCaseCreate(
                name=name,
                campaign_input=system_campaign_input(),
                system_config={"scenario": scenario},
                expected=expected,
            )
        )

    async with AsyncSessionLocal() as session:
        service = EvaluationService(session)
        dataset = await service.create_dataset(
            EvaluationDatasetCreate(
                name="golden-m6",
                version="1",
                description="Deterministic M6 SYSTEM regression dataset",
                cases=cases,
            ),
            actor_id="ci-golden-evaluation",
        )
        run = await service.request_run(
            dataset.dataset_id,
            execution_mode=EvaluationExecutionMode.SYSTEM,
            actor_id="ci-golden-evaluation",
        )

    await EvaluationRunner().run(run.evaluation_run_id)

    baseline_path = (
        Path(__file__).parents[2] / "evaluation" / "baselines" / "golden-m6-v1.json"
    )
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    async with AsyncSessionLocal() as session:
        completed = await EvaluationService(session).get(run.evaluation_run_id)
        assert completed.regression_passed is True
        assert completed.completed_cases == baseline["case_count"]
        assert {result.case_name for result in completed.results} == set(
            baseline["cases"]
        )
        assert all(result.status.value == "PASSED" for result in completed.results)
        for metric, minimum in baseline["minimums"].items():
            assert float(completed.metrics[metric]) >= float(minimum)
        for metric, maximum in baseline["maximums"].items():
            assert float(completed.metrics[metric]) <= float(maximum)


@pytest.mark.asyncio
async def test_system_evaluation_detects_real_workflow_regression() -> None:
    async with AsyncSessionLocal() as session:
        service = EvaluationService(session)
        dataset = await service.create_dataset(
            EvaluationDatasetCreate(
                name="controlled-regression",
                version="1",
                cases=[
                    EvaluationCaseCreate(
                        name="wrong-expected-status",
                        campaign_input=system_campaign_input(),
                        system_config={"scenario": "happy"},
                        expected={"workflow_status": "FAILED"},
                    )
                ],
            ),
            actor_id="regression-test",
        )
        run = await service.request_run(
            dataset.dataset_id,
            execution_mode=EvaluationExecutionMode.SYSTEM,
            actor_id="regression-test",
        )
    await EvaluationRunner().run(run.evaluation_run_id)
    async with AsyncSessionLocal() as session:
        completed = await EvaluationService(session).get(run.evaluation_run_id)
        assert completed.regression_passed is False
        assert completed.results[0].status.value == "FAILED"


@pytest.mark.asyncio
async def test_system_evaluation_isolates_partial_case_failure() -> None:
    async with AsyncSessionLocal() as session:
        service = EvaluationService(session)
        dataset = await service.create_dataset(
            EvaluationDatasetCreate(
                name="partial-system-failure",
                version="1",
                cases=[
                    EvaluationCaseCreate(
                        name="invalid-scenario",
                        campaign_input=system_campaign_input(),
                        system_config={"scenario": "not-supported"},
                        expected={"workflow_status": "FAILED"},
                    ),
                    EvaluationCaseCreate(
                        name="healthy-scenario",
                        campaign_input=system_campaign_input(),
                        system_config={"scenario": "happy"},
                        expected={"workflow_status": "PENDING_APPROVAL"},
                    ),
                ],
            ),
            actor_id="partial-failure-test",
        )
        run = await service.request_run(
            dataset.dataset_id,
            execution_mode=EvaluationExecutionMode.SYSTEM,
            actor_id="partial-failure-test",
        )
    await EvaluationRunner().run(run.evaluation_run_id)
    async with AsyncSessionLocal() as session:
        completed = await EvaluationService(session).get(run.evaluation_run_id)
        assert completed.status == EvaluationRunStatus.SUCCEEDED
        assert completed.completed_cases == 2
        assert {result.status.value for result in completed.results} == {
            "ERROR",
            "PASSED",
        }
        assert completed.regression_passed is False


@pytest.mark.asyncio
async def test_system_evaluation_cancellation_marks_run_cancelled() -> None:
    async with AsyncSessionLocal() as session:
        service = EvaluationService(session)
        dataset = await service.create_dataset(
            EvaluationDatasetCreate(
                name="cancelled-system-run",
                version="1",
                cases=[
                    EvaluationCaseCreate(
                        name="cancel-before-case",
                        campaign_input=system_campaign_input(),
                        system_config={"scenario": "happy"},
                        expected={"workflow_status": "PENDING_APPROVAL"},
                    )
                ],
            ),
            actor_id="cancellation-test",
        )
        run = await service.request_run(
            dataset.dataset_id,
            execution_mode=EvaluationExecutionMode.SYSTEM,
            actor_id="cancellation-test",
        )

    async def cancel() -> None:
        raise JobCancelledError("cancel evaluation")

    with pytest.raises(JobCancelledError):
        await EvaluationRunner().run(run.evaluation_run_id, checkpoint=cancel)
    async with AsyncSessionLocal() as session:
        cancelled = await EvaluationService(session).get(run.evaluation_run_id)
        assert cancelled.status == EvaluationRunStatus.CANCELLED
        assert await CampaignService(session).list_campaigns() == []
