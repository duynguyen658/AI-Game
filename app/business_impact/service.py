from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.business_impact.calculator import ImpactCalculator
from app.core.constants import AppliedTaskStatus, OutboxEventType, UserRole
from app.core.exceptions import (
    AuthorizationError,
    M7ConflictError,
    M7ResourceNotFoundError,
)
from app.core.sanitization import sanitize_text
from app.database.models import (
    AITaskImpactModel,
    AppliedWorkflowTaskModel,
    TaskBaselineModel,
    UserFeedbackModel,
)
from app.outbox.service import OutboxService
from app.repositories.business_impact_repository import BusinessImpactRepository
from app.repositories.feedback_repository import FeedbackRepository
from app.repositories.applied_workflow_repository import AppliedWorkflowRepository
from app.schemas.business_impact import (
    BusinessImpactAnalytics,
    TaskBaselineCreate,
    TaskBaselineRead,
    TaskImpactCreate,
    TaskImpactRead,
    UserFeedbackCreate,
    UserFeedbackRead,
)
from app.service.auth_service import AuthenticatedActor


class BusinessImpactService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.impacts = BusinessImpactRepository(session)
        self.feedback = FeedbackRepository(session)

    async def create_baseline(
        self, data: TaskBaselineCreate, *, actor_id: str
    ) -> TaskBaselineRead:
        model = TaskBaselineModel(**data.model_dump(), created_by=actor_id)
        await self.impacts.create_baseline(model)
        await self.session.commit()
        return TaskBaselineRead.model_validate(model, from_attributes=True)

    async def list_baselines(
        self, *, limit: int, offset: int
    ) -> list[TaskBaselineRead]:
        models = await self.impacts.list_baselines(
            limit=min(limit, 100), offset=max(offset, 0)
        )
        return [
            TaskBaselineRead.model_validate(model, from_attributes=True)
            for model in models
        ]

    async def record_impact(
        self,
        task_run_id: UUID,
        data: TaskImpactCreate,
        *,
        actor: AuthenticatedActor,
    ) -> TaskImpactRead:
        task = await self._eligible_task(task_run_id, actor=actor)
        if actor.role not in {UserRole.MANAGER, UserRole.ADMIN}:
            raise AuthorizationError("Operator role is required to record impact")
        baseline = await self.impacts.latest_baseline(
            task.workflow_type.lower(), data.department
        )
        manual_duration = data.manual_duration_baseline_override
        if manual_duration is None:
            if baseline is None:
                raise M7ConflictError("No task baseline is available")
            manual_duration = baseline.manual_duration_minutes
        ai_duration = Decimal(task.duration_ms or 0) / Decimal(60_000)
        workflow_id = _metadata_uuid(task.input_metadata, "workflow_id")
        agent_run_id = _metadata_uuid(task.input_metadata, "agent_run_id")
        if task.provider is None or task.model is None:
            raise M7ConflictError("Task execution provenance is incomplete")
        model = AITaskImpactModel(
            task_run_id=task_run_id,
            task_type=task.workflow_type.lower(),
            department=data.department,
            workflow_id=workflow_id,
            job_id=task.job_id,
            agent_run_id=agent_run_id,
            prompt_version_id=task.prompt_version_id,
            provider=task.provider,
            model=task.model,
            manual_duration_baseline=manual_duration,
            ai_duration_minutes=ai_duration,
            steps_before=data.steps_before,
            steps_after=max(data.steps_before - data.automated_steps, 0),
            automated_steps=data.automated_steps,
            output_accepted=True,
            accepted_without_editing=data.accepted_without_editing,
            editing_minutes=data.editing_minutes,
            rework_count=data.rework_count,
            error_count=data.error_count,
            estimated_cost=task.estimated_cost,
            minutes_saved=ImpactCalculator.minutes_saved(manual_duration, ai_duration),
            automation_rate=ImpactCalculator.automation_rate(
                data.automated_steps, data.steps_before
            ),
        )
        await self.impacts.create_impact(model)
        await OutboxService(self.session).add_event(
            event_type=OutboxEventType.TASK_IMPACT_RECORDED,
            aggregate_type="applied_task",
            aggregate_id=str(task_run_id),
            payload={
                "task_run_id": str(task_run_id),
                "minutes_saved": str(model.minutes_saved),
                "automation_rate": str(model.automation_rate),
            },
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise M7ConflictError("Impact already exists for this task run") from exc
        return TaskImpactRead.model_validate(model)

    async def record_feedback(
        self,
        task_run_id: UUID,
        data: UserFeedbackCreate,
        *,
        actor: AuthenticatedActor,
    ) -> UserFeedbackRead:
        task = await self._eligible_task(task_run_id, actor=actor, reviewable=True)
        actor_id = actor.actor_id
        existing = await self.feedback.get_for_actor(task_run_id, actor_id)
        values = data.model_dump(exclude={"expected_version"})
        values.update(
            {
                "task_type": task.workflow_type.lower(),
                "workflow_id": _metadata_uuid(task.input_metadata, "workflow_id"),
                "agent_run_id": _metadata_uuid(task.input_metadata, "agent_run_id"),
                "prompt_version_id": task.prompt_version_id,
                "provider": task.provider or "unknown",
                "model": task.model or "unknown",
            }
        )
        values["comment"] = (
            sanitize_text(data.comment, max_characters=2000) if data.comment else None
        )
        if existing is None:
            if data.expected_version is not None:
                raise M7ConflictError("Feedback does not exist at the expected version")
            model = UserFeedbackModel(
                task_run_id=task_run_id, actor_id=actor_id, **values
            )
            await self.feedback.create(model)
        else:
            if data.expected_version != existing.version:
                raise M7ConflictError("Feedback changed; refresh and retry")
            for field, value in values.items():
                setattr(existing, field, value)
            existing.version += 1
            model = existing
        await OutboxService(self.session).add_event(
            event_type=OutboxEventType.USER_FEEDBACK_RECEIVED,
            aggregate_type="applied_task",
            aggregate_id=str(task_run_id),
            payload={
                "task_run_id": str(task_run_id),
                "actor_id": actor_id,
                "rating": data.rating,
            },
            idempotency_key=f"feedback:{model.user_feedback_id}:v{model.version}",
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise M7ConflictError(
                "Feedback changed or already exists; refresh and retry"
            ) from exc
        return UserFeedbackRead.model_validate(model, from_attributes=True)

    async def _eligible_task(
        self,
        task_run_id: UUID,
        *,
        actor: AuthenticatedActor,
        reviewable: bool = False,
    ) -> AppliedWorkflowTaskModel:
        task = await AppliedWorkflowRepository(self.session).get(task_run_id)
        if task is None:
            raise M7ResourceNotFoundError("Applied workflow task not found")
        if actor.actor_id != task.created_by and actor.role not in {
            UserRole.MANAGER,
            UserRole.ADMIN,
        }:
            raise AuthorizationError("Actor cannot access this applied workflow task")
        eligible = {AppliedTaskStatus.COMPLETED.value}
        if reviewable:
            eligible.add(AppliedTaskStatus.READY_FOR_REVIEW.value)
        if task.status not in eligible:
            raise M7ConflictError("Applied workflow task is not eligible")
        return task

    async def analytics(
        self,
        *,
        task_type: str | None = None,
        department: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        prompt_version_id: UUID | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> BusinessImpactAnalytics:
        impacts = list(
            await self.impacts.list_impacts(
                task_type=task_type,
                department=department,
                provider=provider,
                model=model,
                prompt_version_id=prompt_version_id,
                created_from=created_from,
                created_to=created_to,
            )
        )
        feedback = list(
            await self.feedback.list_feedback(
                task_type=task_type,
                provider=provider,
                model=model,
                prompt_version_id=prompt_version_id,
                created_from=created_from,
                created_to=created_to,
            )
        )
        completed = len(impacts)
        total_minutes = sum((item.minutes_saved for item in impacts), Decimal(0))
        total_cost = sum((item.estimated_cost for item in impacts), Decimal(0))
        average_automation = (
            sum((item.automation_rate for item in impacts), Decimal(0))
            / Decimal(completed)
            if completed
            else Decimal(0)
        )
        return BusinessImpactAnalytics(
            completed_tasks=completed,
            total_minutes_saved=total_minutes,
            average_automation_rate=average_automation,
            first_pass_acceptance_rate=ImpactCalculator.first_pass_acceptance_rate(
                sum(item.accepted_without_editing for item in impacts), completed
            ),
            revision_rate=ImpactCalculator.revision_rate(
                sum(item.rework_count > 0 for item in impacts), completed
            ),
            error_rate=ImpactCalculator.error_rate(
                sum(item.error_count > 0 for item in impacts), completed
            ),
            user_satisfaction=ImpactCalculator.user_satisfaction(
                item.rating for item in feedback
            ),
            would_use_again_rate=ImpactCalculator.would_use_again_rate(
                sum(item.would_use_again for item in feedback), len(feedback)
            ),
            total_estimated_cost=total_cost,
            series=[
                {
                    "task_run_id": str(item.task_run_id),
                    "task_type": item.task_type,
                    "provider": item.provider,
                    "model": item.model,
                    "minutes_saved": str(item.minutes_saved),
                    "automation_rate": str(item.automation_rate),
                    "created_at": item.created_at.isoformat(),
                }
                for item in impacts
            ],
        )


def _metadata_uuid(metadata: dict[str, object], field: str) -> UUID | None:
    value = metadata.get(field)
    if value is None:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None
