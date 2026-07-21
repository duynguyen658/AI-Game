from __future__ import annotations

import hashlib

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.constants import AppliedTaskStatus, AppliedWorkflowType, JobType
from app.database.models import AppliedWorkflowTaskModel
from app.jobs.definitions import DocumentProcessingJobPayload
from app.jobs.queue import JobQueue
from app.repositories.applied_workflow_repository import AppliedWorkflowRepository
from app.schemas.applied_workflow import AppliedTaskRead
from app.service.applied_workflow_service import task_to_schema


class DocumentProcessingService:
    def __init__(
        self, session: AsyncSession, *, settings: Settings | None = None
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repository = AppliedWorkflowRepository(session)

    async def request(
        self,
        content: bytes,
        filename: str,
        content_type: str,
        *,
        actor_id: str,
        commit: bool = True,
    ) -> AppliedTaskRead:
        model = AppliedWorkflowTaskModel(
            workflow_type=AppliedWorkflowType.DOCUMENT_PROCESSING.value,
            status=AppliedTaskStatus.PENDING.value,
            input_metadata={
                "filename": filename,
                "content_type": content_type,
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            },
            input_content=content,
            provider=self.settings.llm_provider,
            model=self.settings.llm_model or "mock-applied-ai",
            created_by=actor_id,
        )
        await self.repository.create(model)
        job = await JobQueue(self.session, settings=self.settings).enqueue(
            JobType.DOCUMENT_PROCESSING,
            DocumentProcessingJobPayload(task_run_id=model.task_run_id),
            created_by=actor_id,
            idempotency_key=f"document-processing:{model.task_run_id}",
            commit=False,
        )
        model.job_id = job.job_id
        if commit:
            await self.session.commit()
        return task_to_schema(model)
