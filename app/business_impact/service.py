from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.business_impact.calculator import ImpactCalculator
from app.core.constants import OutboxEventType
from app.core.exceptions import M7ConflictError
from app.core.sanitization import sanitize_text
from app.database.models import AITaskImpactModel, TaskBaselineModel, UserFeedbackModel
from app.outbox.service import OutboxService
from app.repositories.business_impact_repository import BusinessImpactRepository
from app.repositories.feedback_repository import FeedbackRepository
from app.schemas.business_impact import (
    BusinessImpactAnalytics,
    TaskBaselineCreate,
    TaskBaselineRead,
    TaskImpactCreate,
    TaskImpactRead,
    UserFeedbackCreate,
    UserFeedbackRead,
)


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
        self, task_run_id: UUID, data: TaskImpactCreate
    ) -> TaskImpactRead:
        model = AITaskImpactModel(
            task_run_id=task_run_id,
            **data.model_dump(),
            minutes_saved=ImpactCalculator.minutes_saved(
                data.manual_duration_baseline, data.ai_duration_minutes
            ),
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
        return TaskImpactRead.model_validate(model, from_attributes=True)

    async def record_feedback(
        self, task_run_id: UUID, data: UserFeedbackCreate, *, actor_id: str
    ) -> UserFeedbackRead:
        existing = await self.feedback.get_for_actor(task_run_id, actor_id)
        values = data.model_dump(exclude={"expected_version"})
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
        await self.session.commit()
        return UserFeedbackRead.model_validate(model, from_attributes=True)

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
