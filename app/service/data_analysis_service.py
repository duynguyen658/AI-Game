from __future__ import annotations

import hashlib

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.constants import AppliedTaskStatus, AppliedWorkflowType, JobType
from app.database.models import AppliedWorkflowTaskModel
from app.jobs.definitions import DataAnalysisJobPayload
from app.jobs.queue import JobQueue
from app.prompt_management.execution import model_configuration_hash
from app.prompt_management.service import PromptService
from app.repositories.applied_workflow_repository import AppliedWorkflowRepository
from app.schemas.applied_workflow import AppliedTaskRead
from app.service.applied_workflow_service import task_to_schema


class DataAnalysisService:
    def __init__(
        self, session: AsyncSession, *, settings: Settings | None = None
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repository = AppliedWorkflowRepository(session)

    async def request(
        self, content: bytes, filename: str, *, actor_id: str, commit: bool = True
    ) -> AppliedTaskRead:
        managed = await PromptService(self.session).resolve(
            values={"metrics": "pending deterministic analysis"},
            task_type="data_analysis",
        )
        model_name = self.settings.llm_model or "mock-applied-ai"
        model = AppliedWorkflowTaskModel(
            workflow_type=AppliedWorkflowType.DATA_ANALYSIS.value,
            status=AppliedTaskStatus.PENDING.value,
            input_metadata={
                "filename": filename,
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "mime_type": "text/csv",
            },
            input_content=content,
            provider=self.settings.llm_provider,
            model=model_name,
            prompt_template_id=managed.prompt_template_id,
            prompt_version_id=managed.prompt_version_id,
            prompt_version_number=managed.prompt_version_number,
            prompt_content_hash=managed.content_hash,
            model_configuration_hash=model_configuration_hash(
                self.settings.llm_provider, model_name, {"temperature": 0}
            ),
            application_version=self.settings.application_version,
            created_by=actor_id,
        )
        await self.repository.create(model)
        job = await JobQueue(self.session, settings=self.settings).enqueue(
            JobType.DATA_ANALYSIS,
            DataAnalysisJobPayload(task_run_id=model.task_run_id),
            created_by=actor_id,
            idempotency_key=f"data-analysis:{model.task_run_id}",
            commit=False,
        )
        model.job_id = job.job_id
        if commit:
            await self.session.commit()
        return task_to_schema(model)
