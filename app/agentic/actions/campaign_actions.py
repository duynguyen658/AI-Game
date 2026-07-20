from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.actions.definitions import ActionDefinition
from app.agentic.actions.registry import ActionRegistry
from app.core.config import Settings, get_settings
from app.core.constants import (
    AgentName,
    CampaignStatus,
    PolicyDecision,
    UserRole,
    WorkflowStep,
)
from app.core.exceptions import AgentContextError
from app.schemas.campaign import CampaignMetadataUpdate
from app.service.campaign_service import CampaignService
from app.service.workflow_service import WorkflowService


class ScopedActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    campaign_id: str = Field(min_length=3, max_length=100)
    workflow_id: UUID
    revision_number: int = Field(ge=0)


class InternalRecommendationInput(ScopedActionInput):
    recommendation: str = Field(min_length=1, max_length=2000)


class CampaignSummaryInput(ScopedActionInput):
    focus: str = Field(default="current campaign", min_length=1, max_length=500)


class RevisionDraftInput(ScopedActionInput):
    feedback: str = Field(min_length=1, max_length=3000)
    draft_instructions: str = Field(min_length=1, max_length=3000)


class UpdateCampaignMetadataInput(ScopedActionInput):
    tone: str | None = Field(default=None, min_length=1, max_length=500)
    target_audience: str | None = Field(default=None, min_length=1, max_length=300)
    promotion: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def require_change(self) -> "UpdateCampaignMetadataInput":
        CampaignMetadataUpdate.model_validate(
            self.model_dump(include={"tone", "target_audience", "promotion"})
        )
        return self


class RegenerationInput(ScopedActionInput):
    reason: str = Field(min_length=1, max_length=2000)


class ManualReviewNoteInput(ScopedActionInput):
    note: str = Field(min_length=1, max_length=3000)


class MarkManualReviewInput(ScopedActionInput):
    reason: str = Field(min_length=1, max_length=2000)


class InternalActionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: str = Field(min_length=1, max_length=5000)
    changed: bool


class CampaignActionHandlers:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.campaigns = CampaignService(session)
        self.workflows = WorkflowService(session)

    async def create_recommendation(
        self, payload: InternalRecommendationInput
    ) -> InternalActionResult:
        await self._validate_scope(payload)
        return InternalActionResult(
            summary=f"Internal recommendation prepared: {payload.recommendation}",
            changed=False,
        )

    async def generate_summary(
        self, payload: CampaignSummaryInput
    ) -> InternalActionResult:
        campaign = await self._validate_scope(payload)
        return InternalActionResult(
            summary=(
                f"{campaign.campaign.game_name}: {campaign.campaign.campaign_objective}; "
                f"focus={payload.focus}"
            ),
            changed=False,
        )

    async def prepare_revision(
        self, payload: RevisionDraftInput
    ) -> InternalActionResult:
        await self._validate_scope(payload)
        return InternalActionResult(
            summary=(
                f"Revision draft prepared from feedback: {payload.feedback}. "
                f"Instructions: {payload.draft_instructions}"
            ),
            changed=False,
        )

    async def update_metadata(
        self, payload: UpdateCampaignMetadataInput
    ) -> InternalActionResult:
        await self._validate_scope(payload)
        await self.campaigns.update_metadata(
            payload.campaign_id,
            CampaignMetadataUpdate(
                tone=payload.tone,
                target_audience=payload.target_audience,
                promotion=payload.promotion,
            ),
        )
        return InternalActionResult(summary="Campaign metadata updated", changed=True)

    async def request_regeneration(
        self, payload: RegenerationInput
    ) -> InternalActionResult:
        await self._validate_scope(payload)
        await self.workflows.transition(
            payload.workflow_id,
            CampaignStatus.GENERATING,
            step=WorkflowStep.GENERATE_CONTENT,
        )
        return InternalActionResult(
            summary=f"Campaign regeneration requested: {payload.reason}", changed=True
        )

    async def add_manual_review_note(
        self, payload: ManualReviewNoteInput
    ) -> InternalActionResult:
        await self._validate_scope(payload)
        return InternalActionResult(
            summary=f"Manual review note recorded: {payload.note}", changed=True
        )

    async def mark_for_manual_review(
        self, payload: MarkManualReviewInput
    ) -> InternalActionResult:
        await self._validate_scope(payload)
        await self.workflows.transition(
            payload.workflow_id,
            CampaignStatus.MANUAL_REVIEW_REQUIRED,
            step=WorkflowStep.HUMAN_REVIEW,
        )
        return InternalActionResult(
            summary=f"Campaign marked for manual review: {payload.reason}",
            changed=True,
        )

    async def _validate_scope(self, payload: ScopedActionInput):
        campaign = await self.campaigns.get_campaign(payload.campaign_id)
        workflow = await self.workflows.get_workflow(payload.workflow_id)
        if (
            workflow.campaign_id != payload.campaign_id
            or workflow.revision_number != payload.revision_number
        ):
            await self.session.rollback()
            raise AgentContextError("Action scope does not match workflow revision")
        await self.session.commit()
        return campaign


def build_default_action_registry(
    session: AsyncSession, *, settings: Settings | None = None
) -> ActionRegistry:
    handlers = CampaignActionHandlers(session)
    config = settings or get_settings()
    all_agents = frozenset(AgentName)
    active_states = frozenset(
        {
            CampaignStatus.ANALYZING,
            CampaignStatus.GENERATING,
            CampaignStatus.REVIEWING,
            CampaignStatus.MANUAL_REVIEW_REQUIRED,
            CampaignStatus.PENDING_APPROVAL,
            CampaignStatus.REVISION_REQUIRED,
        }
    )
    return ActionRegistry(
        [
            ActionDefinition(
                name="create_internal_recommendation",
                description="Create a bounded internal recommendation.",
                input_model=InternalRecommendationInput,
                output_model=InternalActionResult,
                default_policy=PolicyDecision.SAFE,
                reversible=True,
                allowed_agents=all_agents,
                handler=handlers.create_recommendation,
                allowed_campaign_statuses=active_states,
                allowed_workflow_statuses=active_states,
            ),
            ActionDefinition(
                name="generate_internal_campaign_summary",
                description="Generate a deterministic internal campaign summary.",
                input_model=CampaignSummaryInput,
                output_model=InternalActionResult,
                default_policy=PolicyDecision.SAFE,
                reversible=True,
                allowed_agents=all_agents,
                handler=handlers.generate_summary,
                allowed_campaign_statuses=active_states,
                allowed_workflow_statuses=active_states,
            ),
            ActionDefinition(
                name="prepare_revision_draft",
                description="Prepare internal revision guidance without persisting content.",
                input_model=RevisionDraftInput,
                output_model=InternalActionResult,
                default_policy=PolicyDecision.SAFE,
                reversible=True,
                allowed_agents=frozenset({AgentName.CONTENT_GENERATOR}),
                handler=handlers.prepare_revision,
                allowed_campaign_statuses=frozenset(
                    {CampaignStatus.REVISION_REQUIRED, CampaignStatus.GENERATING}
                ),
                allowed_workflow_statuses=frozenset(
                    {CampaignStatus.REVISION_REQUIRED, CampaignStatus.GENERATING}
                ),
            ),
            ActionDefinition(
                name="update_campaign_metadata",
                description="Update selected internal campaign metadata.",
                input_model=UpdateCampaignMetadataInput,
                output_model=InternalActionResult,
                default_policy=PolicyDecision.APPROVAL_REQUIRED,
                reversible=True,
                allowed_agents=all_agents,
                handler=handlers.update_metadata,
                required_role=UserRole.MANAGER,
                allowed_campaign_statuses=frozenset(
                    {
                        CampaignStatus.RECEIVED,
                        CampaignStatus.NEEDS_CLARIFICATION,
                        CampaignStatus.REVISION_REQUIRED,
                    }
                ),
                allowed_workflow_statuses=frozenset(
                    {
                        CampaignStatus.RECEIVED,
                        CampaignStatus.NEEDS_CLARIFICATION,
                        CampaignStatus.REVISION_REQUIRED,
                    }
                ),
                approval_ttl_seconds=config.action_approval_ttl_seconds,
            ),
            ActionDefinition(
                name="request_campaign_regeneration",
                description="Request regeneration through the workflow state machine.",
                input_model=RegenerationInput,
                output_model=InternalActionResult,
                default_policy=PolicyDecision.APPROVAL_REQUIRED,
                reversible=True,
                allowed_agents=frozenset({AgentName.CONTENT_REVIEWER}),
                handler=handlers.request_regeneration,
                required_role=UserRole.MANAGER,
                allowed_campaign_statuses=frozenset({CampaignStatus.REVIEWING}),
                allowed_workflow_statuses=frozenset({CampaignStatus.REVIEWING}),
                approval_ttl_seconds=config.action_approval_ttl_seconds,
            ),
            ActionDefinition(
                name="add_manual_review_note",
                description="Record an internal manual review note.",
                input_model=ManualReviewNoteInput,
                output_model=InternalActionResult,
                default_policy=PolicyDecision.APPROVAL_REQUIRED,
                reversible=True,
                allowed_agents=frozenset({AgentName.CONTENT_REVIEWER}),
                handler=handlers.add_manual_review_note,
                required_role=UserRole.REVIEWER,
                allowed_campaign_statuses=frozenset(
                    {CampaignStatus.REVIEWING, CampaignStatus.MANUAL_REVIEW_REQUIRED}
                ),
                allowed_workflow_statuses=frozenset(
                    {CampaignStatus.REVIEWING, CampaignStatus.MANUAL_REVIEW_REQUIRED}
                ),
                approval_ttl_seconds=config.action_approval_ttl_seconds,
            ),
            ActionDefinition(
                name="mark_for_manual_review",
                description="Move a reviewing workflow to manual review.",
                input_model=MarkManualReviewInput,
                output_model=InternalActionResult,
                default_policy=PolicyDecision.APPROVAL_REQUIRED,
                reversible=True,
                allowed_agents=frozenset({AgentName.CONTENT_REVIEWER}),
                handler=handlers.mark_for_manual_review,
                required_role=UserRole.REVIEWER,
                allowed_campaign_statuses=frozenset({CampaignStatus.REVIEWING}),
                allowed_workflow_statuses=frozenset({CampaignStatus.REVIEWING}),
                approval_ttl_seconds=config.action_approval_ttl_seconds,
            ),
        ]
    )
