from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    OutboxEventType,
    PromptExperimentStatus,
    PromptTemplateStatus,
    PromptVersionStatus,
    SecurityEventType,
    SecuritySeverity,
    UserRole,
)
from app.core.exceptions import (
    M7ConflictError,
    M7ResourceNotFoundError,
    M7ValidationError,
)
from app.core.sanitization import sanitize_json, sanitize_text
from app.database.models import (
    PromptExperimentModel,
    PromptExperimentResultModel,
    PromptTemplateModel,
    PromptVersionModel,
    SecurityEventModel,
)
from app.outbox.service import OutboxService
from app.prompt_management.definitions import RenderedPrompt
from app.prompt_management.renderer import PromptRenderer
from app.repositories.prompt_experiment_repository import PromptExperimentRepository
from app.repositories.prompt_repository import PromptRepository
from app.schemas.prompt import (
    PromptExperimentCreate,
    PromptExperimentRead,
    PromptExperimentRun,
    PromptTemplateCreate,
    PromptTemplateRead,
    PromptVersionCreate,
    PromptVersionRead,
)
from app.service.auth_service import AuthenticatedActor


class PromptService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.prompts = PromptRepository(session)
        self.experiments = PromptExperimentRepository(session)
        self.renderer = PromptRenderer()

    async def create_template(
        self, data: PromptTemplateCreate, *, actor: AuthenticatedActor
    ) -> PromptTemplateRead:
        self._require_manager(actor)
        safe_input = sanitize_json(data.input_schema)
        safe_output = sanitize_json(data.output_schema)
        if not isinstance(safe_input, dict) or not isinstance(safe_output, dict):
            raise M7ValidationError("Prompt schemas must be JSON objects")
        model = PromptTemplateModel(
            **data.model_dump(exclude={"input_schema", "output_schema"}),
            input_schema=safe_input,
            output_schema=safe_output,
            status=PromptTemplateStatus.ACTIVE.value,
            created_by=actor.actor_id,
        )
        self.prompts.session.add(model)
        self._audit(actor, "prompt_template_created", model.prompt_template_id)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise M7ConflictError("Prompt template slug already exists") from exc
        return template_to_schema(model)

    async def list_templates(
        self, *, limit: int, offset: int
    ) -> list[PromptTemplateRead]:
        models = await self.prompts.list_templates(
            limit=min(limit, 100), offset=max(offset, 0)
        )
        return [template_to_schema(model) for model in models]

    async def get_template(self, template_id: UUID) -> PromptTemplateRead:
        return template_to_schema(await self._template(template_id))

    async def create_version(
        self,
        template_id: UUID,
        data: PromptVersionCreate,
        *,
        actor: AuthenticatedActor,
    ) -> PromptVersionRead:
        self._require_manager(actor)
        await self._template(template_id)
        self.renderer.validate_content(data.system_prompt, data.user_prompt_template)
        declared = set(data.variables)
        referenced = self.renderer.variables(data.user_prompt_template)
        if referenced - declared:
            raise M7ValidationError("Every prompt variable must be declared")
        version = await self.prompts.next_version(template_id)
        model = PromptVersionModel(
            prompt_template_id=template_id,
            version=version,
            status=PromptVersionStatus.DRAFT.value,
            system_prompt=data.system_prompt,
            user_prompt_template=data.user_prompt_template,
            variables=sanitize_json(data.variables),
            change_summary=sanitize_text(data.change_summary, max_characters=1000),
            model_requirements=sanitize_json(data.model_requirements),
            content_hash=prompt_content_hash(data),
            created_by=actor.actor_id,
        )
        self.prompts.session.add(model)
        self._audit(actor, "prompt_version_created", model.prompt_version_id)
        await self.session.commit()
        return version_to_schema(model)

    async def get_version(self, version_id: UUID) -> PromptVersionRead:
        return version_to_schema(await self._version(version_id))

    async def transition(
        self,
        version_id: UUID,
        target: PromptVersionStatus,
        *,
        expected_status: PromptVersionStatus,
        actor: AuthenticatedActor,
    ) -> PromptVersionRead:
        self._require_manager(actor)
        model = await self._version(version_id)
        if await self.prompts.get_template_for_update(model.prompt_template_id) is None:
            raise M7ResourceNotFoundError("Prompt template not found")
        current = PromptVersionStatus(model.status)
        if current != expected_status:
            raise M7ConflictError("Prompt version changed; refresh and retry")
        allowed = {
            PromptVersionStatus.TESTING: {PromptVersionStatus.DRAFT},
            PromptVersionStatus.APPROVED: {PromptVersionStatus.TESTING},
            PromptVersionStatus.RETIRED: {PromptVersionStatus.ACTIVE},
        }
        if current not in allowed.get(target, set()):
            raise M7ConflictError(
                f"Cannot transition prompt from {current} to {target}"
            )
        now = datetime.now(UTC)
        if target == PromptVersionStatus.APPROVED:
            if actor.role == UserRole.SYSTEM:
                raise M7ConflictError("SYSTEM cannot approve prompt versions")
            model.approved_by = actor.actor_id
            model.approved_at = now
        if target == PromptVersionStatus.RETIRED:
            model.retired_at = now
        model.status = target.value
        self._audit(actor, f"prompt_version_{target.value.lower()}", version_id)
        await self.session.commit()
        return version_to_schema(model)

    async def activate(
        self,
        version_id: UUID,
        *,
        expected_status: PromptVersionStatus,
        actor: AuthenticatedActor,
    ) -> PromptVersionRead:
        self._require_manager(actor)
        model = await self._version(version_id)
        if await self.prompts.get_template_for_update(model.prompt_template_id) is None:
            raise M7ResourceNotFoundError("Prompt template not found")
        current = PromptVersionStatus(model.status)
        if current != expected_status or current not in {
            PromptVersionStatus.APPROVED,
            PromptVersionStatus.RETIRED,
        }:
            raise M7ConflictError(
                "Only approved or retired prompt versions can activate"
            )
        previous = await self.prompts.get_active_version(model.prompt_template_id)
        now = datetime.now(UTC)
        if previous is not None and previous.prompt_version_id != version_id:
            previous.status = PromptVersionStatus.RETIRED.value
            previous.retired_at = now
            await self.session.flush()
        model.status = PromptVersionStatus.ACTIVE.value
        model.activated_at = now
        model.retired_at = None
        await OutboxService(self.session).add_event(
            event_type=OutboxEventType.PROMPT_VERSION_ACTIVATED,
            aggregate_type="prompt_version",
            aggregate_id=str(version_id),
            payload={
                "prompt_template_id": str(model.prompt_template_id),
                "prompt_version_id": str(version_id),
                "version": model.version,
            },
        )
        self._audit(actor, "prompt_version_activated", version_id)
        await self.session.commit()
        return version_to_schema(model)

    async def rollback(
        self, template_id: UUID, version_id: UUID, *, actor: AuthenticatedActor
    ) -> PromptVersionRead:
        model = await self._version(version_id)
        if model.prompt_template_id != template_id:
            raise M7ValidationError("Prompt version does not belong to the template")
        return await self.activate(
            version_id,
            expected_status=PromptVersionStatus(model.status),
            actor=actor,
        )

    async def resolve(
        self,
        *,
        values: dict[str, Any],
        agent_name: str | None = None,
        task_type: str | None = None,
    ) -> RenderedPrompt:
        template = await self.prompts.find_template(
            agent_name=agent_name, task_type=task_type
        )
        if template is None:
            raise M7ResourceNotFoundError("Managed prompt template not found")
        version = await self.prompts.get_active_version(template.prompt_template_id)
        if version is None:
            raise M7ResourceNotFoundError("Active managed prompt version not found")
        allow_unknown = bool(version.variables.get("__allow_unknown__", False))
        allowed = {key for key in version.variables if not key.startswith("__")}
        user_prompt = self.renderer.render(
            version.user_prompt_template,
            values,
            allowed_variables=allowed,
            allow_unknown=allow_unknown,
        )
        return RenderedPrompt(
            prompt_template_id=template.prompt_template_id,
            prompt_version_id=version.prompt_version_id,
            prompt_version_number=version.version,
            content_hash=version.content_hash,
            system_prompt=version.system_prompt,
            user_prompt=user_prompt,
            output_schema=template.output_schema,
            model_requirements=version.model_requirements,
        )

    async def create_experiment(
        self, data: PromptExperimentCreate, *, actor: AuthenticatedActor
    ) -> PromptExperimentRead:
        self._require_manager(actor)
        control = await self._version(data.control_version_id)
        candidate = await self._version(data.candidate_version_id)
        if data.control_version_id == data.candidate_version_id:
            raise M7ValidationError("Control and candidate versions must differ")
        if {control.prompt_template_id, candidate.prompt_template_id} != {
            data.prompt_template_id
        }:
            raise M7ValidationError("Experiment versions must belong to one template")
        model = PromptExperimentModel(
            **data.model_dump(),
            status=PromptExperimentStatus.DRAFT.value,
            created_by=actor.actor_id,
        )
        await self.experiments.create(model)
        self._audit(actor, "prompt_experiment_created", model.experiment_id)
        await self.session.commit()
        return experiment_to_schema(model, None)

    async def list_experiments(
        self, *, limit: int, offset: int
    ) -> list[PromptExperimentRead]:
        models = await self.experiments.list(
            limit=min(limit, 100), offset=max(offset, 0)
        )
        return [
            experiment_to_schema(
                model, await self.experiments.result(model.experiment_id)
            )
            for model in models
        ]

    async def get_experiment(self, experiment_id: UUID) -> PromptExperimentRead:
        model = await self._experiment(experiment_id)
        return experiment_to_schema(model, await self.experiments.result(experiment_id))

    async def run_experiment(
        self,
        experiment_id: UUID,
        data: PromptExperimentRun,
        *,
        actor: AuthenticatedActor,
    ) -> PromptExperimentRead:
        self._require_manager(actor)
        model = await self._experiment(experiment_id)
        if model.status != PromptExperimentStatus.DRAFT.value:
            raise M7ConflictError("Only draft experiments can run")
        model.status = PromptExperimentStatus.RUNNING.value
        model.started_at = datetime.now(UTC)
        winner, reason = compare_metrics(data.control_metrics, data.candidate_metrics)
        result = PromptExperimentResultModel(
            experiment_id=experiment_id,
            evaluation_run_id=data.evaluation_run_id,
            control_metrics=sanitize_json(data.control_metrics),
            candidate_metrics=sanitize_json(data.candidate_metrics),
            winner=winner,
            decision_reason=reason,
        )
        self.session.add(result)
        model.status = PromptExperimentStatus.COMPLETED.value
        model.completed_at = datetime.now(UTC)
        await OutboxService(self.session).add_event(
            event_type=OutboxEventType.PROMPT_EXPERIMENT_COMPLETED,
            aggregate_type="prompt_experiment",
            aggregate_id=str(experiment_id),
            payload={"experiment_id": str(experiment_id), "winner": winner},
        )
        self._audit(actor, "prompt_experiment_completed", experiment_id)
        await self.session.commit()
        return experiment_to_schema(model, result)

    async def cancel_experiment(
        self, experiment_id: UUID, *, actor: AuthenticatedActor
    ) -> PromptExperimentRead:
        self._require_manager(actor)
        model = await self._experiment(experiment_id)
        if model.status not in {
            PromptExperimentStatus.DRAFT.value,
            PromptExperimentStatus.RUNNING.value,
        }:
            raise M7ConflictError("Experiment cannot be cancelled")
        model.status = PromptExperimentStatus.CANCELLED.value
        model.completed_at = datetime.now(UTC)
        self._audit(actor, "prompt_experiment_cancelled", experiment_id)
        await self.session.commit()
        return experiment_to_schema(model, await self.experiments.result(experiment_id))

    async def _template(self, template_id: UUID) -> PromptTemplateModel:
        model = await self.prompts.get_template(template_id)
        if model is None:
            raise M7ResourceNotFoundError("Prompt template not found")
        return model

    async def _version(self, version_id: UUID) -> PromptVersionModel:
        model = await self.prompts.get_version(version_id)
        if model is None:
            raise M7ResourceNotFoundError("Prompt version not found")
        return model

    async def _experiment(self, experiment_id: UUID) -> PromptExperimentModel:
        model = await self.experiments.get(experiment_id)
        if model is None:
            raise M7ResourceNotFoundError("Prompt experiment not found")
        return model

    @staticmethod
    def _require_manager(actor: AuthenticatedActor) -> None:
        if actor.role not in {UserRole.MANAGER, UserRole.ADMIN}:
            raise M7ConflictError("Manager or admin role is required")

    def _audit(self, actor: AuthenticatedActor, action: str, resource_id: UUID) -> None:
        self.session.add(
            SecurityEventModel(
                event_type=SecurityEventType.OPERATOR_ACTION.value,
                severity=SecuritySeverity.LOW.value,
                actor_id=actor.actor_id,
                resource_type="managed_prompt",
                resource_id=str(resource_id),
                source="prompt_management",
                message=action,
                metadata_={"action": action},
            )
        )


def prompt_content_hash(data: PromptVersionCreate) -> str:
    material = json.dumps(
        data.model_dump(mode="json"),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode()).hexdigest()


def compare_metrics(
    control: dict[str, float], candidate: dict[str, float]
) -> tuple[str | None, str]:
    required = {
        "quality",
        "schema_validity",
        "success_rate",
        "latency",
        "estimated_cost",
    }
    if required - control.keys() or required - candidate.keys():
        raise M7ValidationError("Experiment metrics are incomplete")
    control_score = (
        control["quality"] + control["schema_validity"] + control["success_rate"]
    )
    candidate_score = (
        candidate["quality"] + candidate["schema_validity"] + candidate["success_rate"]
    )
    candidate_score -= max(candidate["latency"] - control["latency"], 0) * 0.01
    candidate_score -= max(candidate["estimated_cost"] - control["estimated_cost"], 0)
    if abs(candidate_score - control_score) < 0.001:
        return None, "No statistically meaningful deterministic winner"
    winner = "candidate" if candidate_score > control_score else "control"
    return (
        winner,
        f"{winner} has the higher quality-adjusted score; human promotion is required",
    )


def template_to_schema(model: PromptTemplateModel) -> PromptTemplateRead:
    return PromptTemplateRead.model_validate(model, from_attributes=True)


def version_to_schema(model: PromptVersionModel) -> PromptVersionRead:
    return PromptVersionRead.model_validate(model, from_attributes=True)


def experiment_to_schema(
    model: PromptExperimentModel, result: PromptExperimentResultModel | None
) -> PromptExperimentRead:
    payload = PromptExperimentRead.model_validate(model, from_attributes=True)
    if result is None:
        return payload
    return payload.model_copy(
        update={
            "result": {
                "experiment_result_id": str(result.experiment_result_id),
                "evaluation_run_id": str(result.evaluation_run_id)
                if result.evaluation_run_id
                else None,
                "control_metrics": result.control_metrics,
                "candidate_metrics": result.candidate_metrics,
                "winner": result.winner,
                "decision_reason": result.decision_reason,
            }
        }
    )
