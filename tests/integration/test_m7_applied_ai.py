from __future__ import annotations

import base64
import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.business_impact.service import BusinessImpactService
from app.agentic.runtime.orchestrator import AgenticOrchestrator
from app.core.config import get_settings
from app.core.constants import (
    MediaAssetStatus,
    PromptVersionStatus,
    UserRole,
)
from app.database.models import AgentRunModel, EvaluationDatasetModel
from app.database.session import AsyncSessionLocal
from app.integrations.n8n.service import N8NService
from app.integrations.n8n.signatures import sign_webhook
from app.jobs.handlers import build_job_handlers
from app.jobs.worker import JobWorker
from app.llm.mock_client import MockLLMClient
from app.media.service import MediaService
from app.prompt_management.service import PromptService
from app.schemas.business_impact import (
    TaskBaselineCreate,
    TaskImpactCreate,
    UserFeedbackCreate,
)
from app.schemas.media import ImageGenerationRequest, MediaReviewRequest
from app.schemas.campaign import CampaignCreate
from app.schemas.prompt import (
    PromptExperimentCreate,
    PromptExperimentRun,
    PromptTemplateCreate,
    PromptVersionCreate,
)
from app.service.auth_service import AuthenticatedActor
from app.service.campaign_service import CampaignService
from app.service.data_analysis_service import DataAnalysisService
from app.service.workflow_service import WorkflowService

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_TESTS") != "1",
        reason="set RUN_POSTGRES_TESTS=1 to run PostgreSQL integration tests",
    ),
]


@pytest_asyncio.fixture(autouse=True)
async def clean_m7_database():
    statement = text(
        "TRUNCATE media_reviews, media_generation_attempts, media_assets, "
        "prompt_experiment_results, prompt_experiments, ai_task_impacts, user_feedback, "
        "task_baselines, applied_workflow_tasks, n8n_webhook_receipts, prompt_versions, "
        "prompt_templates, evaluation_results, evaluation_runs, evaluation_cases, "
        "evaluation_datasets, outbox_events, job_attempts, background_jobs, "
        "agent_tool_calls, agent_runs, approval_records, workflow_runs, campaigns, security_events "
        "RESTART IDENTITY CASCADE"
    )
    async with AsyncSessionLocal() as session:
        await session.execute(statement)
        await session.commit()
    yield
    async with AsyncSessionLocal() as session:
        await session.execute(statement)
        await session.commit()


def manager() -> AuthenticatedActor:
    return AuthenticatedActor(actor_id="m7-manager", role=UserRole.MANAGER)


@pytest.mark.asyncio
async def test_prompt_lifecycle_rollback_and_experiment_are_persisted() -> None:
    async with AsyncSessionLocal() as session:
        service = PromptService(session)
        template = await service.create_template(
            PromptTemplateCreate(
                name="Brief analysis",
                slug="brief-analysis",
                agent_name="BRIEF_ANALYST",
                task_type="campaign_brief",
                description="Analyze campaign briefs.",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            ),
            actor=manager(),
        )
        first = await service.create_version(
            template.prompt_template_id,
            PromptVersionCreate(
                system_prompt="Analyze the campaign brief safely.",
                user_prompt_template="Untrusted campaign context: {context}",
                variables={"context": {"type": "string"}},
                change_summary="Initial managed prompt",
                model_requirements={"structured_output": True},
            ),
            actor=manager(),
        )
        first = await service.transition(
            first.prompt_version_id,
            PromptVersionStatus.TESTING,
            expected_status=PromptVersionStatus.DRAFT,
            actor=manager(),
        )
        first = await service.transition(
            first.prompt_version_id,
            PromptVersionStatus.APPROVED,
            expected_status=PromptVersionStatus.TESTING,
            actor=manager(),
        )
        first = await service.activate(
            first.prompt_version_id,
            expected_status=PromptVersionStatus.APPROVED,
            actor=manager(),
        )
        rendered = await service.resolve(
            agent_name="BRIEF_ANALYST", values={"context": "safe"}
        )
        assert rendered.prompt_version_id == first.prompt_version_id
        second = await service.create_version(
            template.prompt_template_id,
            PromptVersionCreate(
                system_prompt="Analyze the campaign brief using version two.",
                user_prompt_template="Context: {context}",
                variables={"context": {}},
                change_summary="Candidate prompt",
            ),
            actor=manager(),
        )
        await service.transition(
            second.prompt_version_id,
            PromptVersionStatus.TESTING,
            expected_status=PromptVersionStatus.DRAFT,
            actor=manager(),
        )
        await service.transition(
            second.prompt_version_id,
            PromptVersionStatus.APPROVED,
            expected_status=PromptVersionStatus.TESTING,
            actor=manager(),
        )
        await service.activate(
            second.prompt_version_id,
            expected_status=PromptVersionStatus.APPROVED,
            actor=manager(),
        )
        rolled_back = await service.rollback(
            template.prompt_template_id, first.prompt_version_id, actor=manager()
        )
        assert rolled_back.status == PromptVersionStatus.ACTIVE
        assert (
            await service.get_version(second.prompt_version_id)
        ).status == PromptVersionStatus.RETIRED
        dataset = EvaluationDatasetModel(
            name="m7-prompt-fixture",
            version="1",
            description="Deterministic fixture",
            created_by="m7-manager",
        )
        session.add(dataset)
        await session.flush()
        experiment = await service.create_experiment(
            PromptExperimentCreate(
                prompt_template_id=template.prompt_template_id,
                control_version_id=first.prompt_version_id,
                candidate_version_id=second.prompt_version_id,
                dataset_id=dataset.dataset_id,
                sample_size=10,
            ),
            actor=manager(),
        )
        completed = await service.run_experiment(
            experiment.experiment_id,
            PromptExperimentRun(
                control_metrics={
                    "quality": 0.8,
                    "schema_validity": 1,
                    "success_rate": 0.9,
                    "latency": 100,
                    "estimated_cost": 0.1,
                },
                candidate_metrics={
                    "quality": 0.9,
                    "schema_validity": 1,
                    "success_rate": 0.95,
                    "latency": 90,
                    "estimated_cost": 0.1,
                },
            ),
            actor=manager(),
        )
        assert completed.result["winner"] == "candidate"
        assert (
            await service.get_version(first.prompt_version_id)
        ).status == PromptVersionStatus.ACTIVE

        await CampaignService(session).create_campaign(
            CampaignCreate(
                campaign_id="M7-PROMPT-TRACE",
                game_name="Cyber Legends",
                genre="Action RPG",
                target_audience="Core players",
                market="Vietnam",
                platforms=["Facebook"],
                campaign_objective="Pre-registration",
                tone="Energetic",
                launch_date="2026-08-15",
                promotion="Launch reward",
            )
        )
        workflow = await WorkflowService(session).create_workflow("M7-PROMPT-TRACE")
        await AgenticOrchestrator(session, MockLLMClient()).run_brief_analysis(
            campaign_id="M7-PROMPT-TRACE", workflow_id=workflow.workflow_id
        )
        agent_run = (await session.execute(select(AgentRunModel))).scalar_one()
        assert agent_run.prompt_template_id == template.prompt_template_id
        assert agent_run.prompt_version_id == first.prompt_version_id
        assert agent_run.prompt_content_hash == first.content_hash


@pytest.mark.asyncio
async def test_business_impact_feedback_and_analytics() -> None:
    task_run_id = uuid4()
    async with AsyncSessionLocal() as session:
        service = BusinessImpactService(session)
        await service.create_baseline(
            TaskBaselineCreate(
                task_type="data_analysis",
                department="marketing",
                manual_duration_minutes=Decimal("90"),
                manual_steps=12,
                historical_error_rate=Decimal("0.10"),
                baseline_cost=Decimal("30"),
                sample_size=10,
                source="internal time study",
            ),
            actor_id="m7-manager",
        )
        impact = await service.record_impact(
            task_run_id,
            TaskImpactCreate(
                task_type="data_analysis",
                department="marketing",
                provider="mock",
                model="mock-applied-ai",
                manual_duration_baseline=Decimal("90"),
                ai_duration_minutes=Decimal("15"),
                steps_before=12,
                steps_after=4,
                automated_steps=8,
                output_accepted=True,
                accepted_without_editing=True,
                editing_minutes=Decimal("0"),
                rework_count=0,
                error_count=0,
                estimated_cost=Decimal("0"),
            ),
        )
        assert impact.minutes_saved == Decimal("75.00")
        await service.record_feedback(
            task_run_id,
            UserFeedbackCreate(
                task_type="data_analysis",
                provider="mock",
                model="mock-applied-ai",
                rating=5,
                helpfulness=5,
                accuracy=4,
                ease_of_use=5,
                accepted_without_editing=True,
                editing_minutes=Decimal("0"),
                rework_count=0,
                would_use_again=True,
                comment="Useful report",
            ),
            actor_id="internal-user",
        )
        analytics = await service.analytics(task_type="data_analysis")
        assert analytics.total_minutes_saved == Decimal("75.00")
        assert analytics.first_pass_acceptance_rate == Decimal("1.000000")
        assert analytics.user_satisfaction == Decimal("5.00")
        unrelated_task = uuid4()
        await service.record_feedback(
            unrelated_task,
            UserFeedbackCreate(
                task_type="document_processing",
                provider="mock",
                model="mock-applied-ai",
                rating=1,
                helpfulness=1,
                accuracy=1,
                ease_of_use=1,
                accepted_without_editing=False,
                editing_minutes=Decimal("15"),
                rework_count=1,
                would_use_again=False,
            ),
            actor_id="another-user",
        )
        filtered = await service.analytics(task_type="data_analysis")
        assert filtered.user_satisfaction == Decimal("5.00")
        assert filtered.would_use_again_rate == Decimal("1.000000")


@pytest.mark.asyncio
async def test_n8n_campaign_webhook_is_idempotent_and_replay_safe() -> None:
    payload = {
        "campaign": {
            "campaign_id": "M7-N8N-001",
            "game_name": "Cyber Legends",
            "genre": "Action RPG",
            "target_audience": "Core players",
            "market": "Vietnam",
            "platforms": ["Facebook"],
            "campaign_objective": "Pre-registration",
            "tone": "Energetic",
            "launch_date": "2026-08-15",
            "promotion": "Launch reward",
        },
        "run_async": True,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    timestamp = str(int(datetime.now(UTC).timestamp()))
    settings = get_settings()
    signature = sign_webhook(
        settings.n8n_webhook_secret.get_secret_value(), timestamp, raw
    )
    async with AsyncSessionLocal() as session:
        service = N8NService(session)
        first = await service.accept_campaign(
            raw_body=raw,
            timestamp=timestamp,
            signature=signature,
            idempotency_key="n8n-campaign-001",
            correlation_id="m7-correlation",
        )
        duplicate = await service.accept_campaign(
            raw_body=raw,
            timestamp=timestamp,
            signature=signature,
            idempotency_key="n8n-campaign-001",
            correlation_id="m7-correlation",
        )
        assert first.accepted is True
        assert first.job_id is not None
        assert duplicate.duplicate is True


@pytest.mark.asyncio
async def test_n8n_file_webhook_creates_one_task_and_job() -> None:
    payload = {
        "filename": "campaign.csv",
        "content_type": "text/csv",
        "content_base64": base64.b64encode(
            b"platform,impressions,clicks\nFacebook,100,10\n"
        ).decode(),
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    timestamp = str(int(datetime.now(UTC).timestamp()))
    settings = get_settings()
    signature = sign_webhook(
        settings.n8n_webhook_secret.get_secret_value(), timestamp, raw
    )
    async with AsyncSessionLocal() as session:
        service = N8NService(session)
        first = await service.accept_file_task(
            endpoint="data-analysis",
            raw_body=raw,
            timestamp=timestamp,
            signature=signature,
            idempotency_key="n8n-data-001",
            correlation_id="m7-data-correlation",
        )
        duplicate = await service.accept_file_task(
            endpoint="data-analysis",
            raw_body=raw,
            timestamp=timestamp,
            signature=signature,
            idempotency_key="n8n-data-001",
            correlation_id="m7-data-correlation",
        )
        assert first.accepted is True
        assert first.job_id is not None
        assert duplicate.resource_id == first.resource_id
        assert duplicate.job_id == first.job_id
        assert duplicate.duplicate is True


@pytest.mark.asyncio
async def test_data_and_image_jobs_complete_with_mock_providers(tmp_path) -> None:
    settings = get_settings().model_copy(update={"media_storage_root": str(tmp_path)})
    async with AsyncSessionLocal() as session:
        data_task = await DataAnalysisService(session, settings=settings).request(
            b"platform,impressions,clicks\nFacebook,100,10\nTikTok,200,30\n",
            "fixture.csv",
            actor_id="m7-user",
        )
    worker = JobWorker(
        "m7-data-worker",
        build_job_handlers(
            AsyncSessionLocal,
            settings=settings,
            llm_client_factory=MockLLMClient,
        ),
        settings=settings,
    )
    assert await worker.run_once() == 1
    async with AsyncSessionLocal() as session:
        completed = await DataAnalysisService(
            session, settings=settings
        ).repository.get(data_task.task_run_id)
        assert completed is not None
        assert completed.status == "COMPLETED"
        assert completed.result["summary_metrics"]["ctr"] == "0.133333"
        image = await MediaService(session, settings=settings).request_image(
            ImageGenerationRequest(prompt="Safe cyberpunk game launch artwork"),
            actor=manager(),
        )
    media_worker = JobWorker(
        "m7-media-worker",
        build_job_handlers(
            AsyncSessionLocal,
            settings=settings,
            llm_client_factory=MockLLMClient,
        ),
        settings=settings,
    )
    assert await media_worker.run_once() == 1
    async with AsyncSessionLocal() as session:
        service = MediaService(session, settings=settings)
        ready = await service.get(image.media_asset_id)
        assert ready.status == MediaAssetStatus.READY_FOR_REVIEW
        approved = await service.review(
            image.media_asset_id,
            MediaReviewRequest(decision="APPROVE", rating=5, comment="Approved"),
            actor=manager(),
        )
        assert approved.status == MediaAssetStatus.APPROVED
        run_rows = (await session.execute(select(AgentRunModel))).scalars().all()
        assert run_rows == []
