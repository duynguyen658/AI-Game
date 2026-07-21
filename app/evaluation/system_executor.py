from __future__ import annotations

import json
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ApprovalDecision, PolicyDecision, UserRole
from app.core.exceptions import (
    ApplicationError,
    EvaluationConflictError,
    EvaluationExecutionError,
    EvaluationIsolationError,
)
from app.database.models import (
    AgentActionRequestModel,
    AgentRunModel,
    CampaignModel,
    WorkflowRunModel,
)
from app.llm.agent_turn import AgentToolRequest, AgentTurn
from app.llm.base import LLMClient
from app.llm.mock_client import MockLLMClient
from app.schemas.approval import ApprovalRequest
from app.schemas.action_request import AgentActionProposal
from app.schemas.campaign import (
    BriefAnalysis,
    CampaignCreate,
    DiscordContent,
    FacebookContent,
    GeneratedContent,
    QualityReview,
    TikTokContent,
    TikTokScene,
)
from app.service.approval_service import ApprovalService
from app.service.campaign_service import CampaignService
from app.service.workflow_service import WorkflowService
from app.workflows.campaign_workflow import CampaignWorkflow


class SystemEvaluationExecutor:
    async def execute(
        self,
        session: AsyncSession,
        *,
        run_id: UUID,
        case_id: UUID,
        campaign_input: dict[str, Any],
        system_config: dict[str, Any],
    ) -> dict[str, Any]:
        campaign_id = f"eval-{run_id.hex[:10]}-{case_id.hex[:10]}"
        raw_input = dict(campaign_input)
        raw_input["campaign_id"] = campaign_id
        try:
            payload = CampaignCreate.model_validate(raw_input)
        except ValueError as exc:
            raise EvaluationConflictError(
                "SYSTEM evaluation campaign input is invalid"
            ) from exc

        await CampaignService(session).create_campaign(
            payload,
            evaluation_run_id=run_id,
            evaluation_case_id=case_id,
        )
        workflow = await WorkflowService(session).create_workflow(campaign_id)
        scenario = str(system_config.get("scenario", "happy"))
        client = self._client_for(
            scenario,
            campaign_id=campaign_id,
            workflow_id=workflow.workflow_id,
        )
        try:
            await CampaignWorkflow(
                session, cast(LLMClient, client)
            ).run_to_pending_approval(workflow.workflow_id)
        except ApplicationError:
            await session.rollback()

        final_workflow_id = workflow.workflow_id
        if scenario == "revision":
            final_workflow_id = await self._run_revision(
                session,
                campaign_id=campaign_id,
                workflow_id=workflow.workflow_id,
            )
        return await self._collect(session, campaign_id, final_workflow_id)

    async def _run_revision(
        self, session: AsyncSession, *, campaign_id: str, workflow_id: UUID
    ) -> UUID:
        campaign = await session.get(CampaignModel, campaign_id)
        if campaign is None:
            raise EvaluationIsolationError("Evaluation campaign disappeared")
        await ApprovalService(session).decide(
            ApprovalRequest(
                campaign_id=campaign_id,
                workflow_id=workflow_id,
                decision=ApprovalDecision.REQUEST_REVISION,
                feedback="Deterministic evaluation revision",
                expected_version=campaign.version,
            ),
            actor_id="evaluation-system",
            actor_role=UserRole.REVIEWER,
        )
        revision = await WorkflowService(session).create_workflow(campaign_id)
        await CampaignWorkflow(
            session, cast(LLMClient, MockLLMClient())
        ).run_to_pending_approval(revision.workflow_id)
        return revision.workflow_id

    @staticmethod
    def _client_for(
        scenario: str, *, campaign_id: str, workflow_id: UUID
    ) -> MockLLMClient:
        analysis = _analysis()
        content = _content()
        if scenario == "retry":
            return MockLLMClient(
                scripted_turns=[
                    AgentTurn(final_output=analysis.model_dump(mode="json")),
                    AgentTurn(final_output=content.model_dump(mode="json")),
                    AgentTurn(final_output=_review("FAIL", 45).model_dump(mode="json")),
                    AgentTurn(final_output=content.model_dump(mode="json")),
                    AgentTurn(final_output=_review("PASS", 90).model_dump(mode="json")),
                ]
            )
        if scenario == "manual_review":
            return MockLLMClient(
                scripted_turns=[
                    AgentTurn(final_output=analysis.model_dump(mode="json")),
                    AgentTurn(final_output=content.model_dump(mode="json")),
                    AgentTurn(
                        final_output=_review("MANUAL_REVIEW_REQUIRED", 60).model_dump(
                            mode="json"
                        )
                    ),
                ]
            )
        if scenario == "provider_failure":
            from app.core.exceptions import LLMProviderError

            return MockLLMClient(
                scripted_turns=[LLMProviderError("deterministic provider unavailable")]
            )
        if scenario == "agent_limit":
            turns: list[AgentTurn | Exception] = [
                AgentTurn(final_output=analysis.model_dump(mode="json"))
            ]
            turns.extend(
                AgentTurn(
                    tool_calls=[
                        AgentToolRequest(
                            tool_call_id=f"evaluation-limit-{index}",
                            tool_name="get_previous_quality_review",
                            arguments={
                                "campaign_id": campaign_id,
                                "workflow_id": workflow_id,
                            },
                        )
                    ]
                )
                for index in range(5)
            )
            return MockLLMClient(scripted_turns=turns)
        if scenario == "forbidden_action":
            return MockLLMClient(
                scripted_turns=[
                    AgentTurn(
                        final_output=analysis.model_dump(mode="json"),
                        action_proposals=[
                            AgentActionProposal(
                                action_name="publish-campaign",
                                arguments={"campaign_id": campaign_id},
                                rationale_summary="Deterministic forbidden proposal",
                            )
                        ],
                    )
                ]
            )
        if scenario == "approval_required":
            scoped = {
                "campaign_id": campaign_id,
                "workflow_id": workflow_id,
                "revision_number": 0,
                "note": "Deterministic evaluation note",
            }
            return MockLLMClient(
                scripted_turns=[
                    AgentTurn(final_output=analysis.model_dump(mode="json")),
                    AgentTurn(final_output=content.model_dump(mode="json")),
                    AgentTurn(
                        final_output=_review("PASS", 90).model_dump(mode="json"),
                        action_proposals=[
                            AgentActionProposal(
                                action_name="add_manual_review_note",
                                arguments=scoped,
                                rationale_summary="Require deterministic human approval",
                            )
                        ],
                    ),
                ]
            )
        if scenario in {"happy", "revision"}:
            return MockLLMClient()
        raise EvaluationExecutionError("Unknown SYSTEM evaluation scenario")

    @staticmethod
    async def _collect(
        session: AsyncSession, campaign_id: str, workflow_id: UUID
    ) -> dict[str, Any]:
        campaign = await session.get(CampaignModel, campaign_id)
        workflow = await session.get(WorkflowRunModel, workflow_id)
        if campaign is None or workflow is None:
            raise EvaluationIsolationError("Evaluation-owned workflow state is missing")
        agent_runs = (
            (
                await session.execute(
                    select(AgentRunModel).where(
                        AgentRunModel.workflow_id == workflow_id
                    )
                )
            )
            .scalars()
            .all()
        )
        actions = (
            (
                await session.execute(
                    select(AgentActionRequestModel).where(
                        AgentActionRequestModel.workflow_id == workflow_id
                    )
                )
            )
            .scalars()
            .all()
        )
        decisions = {item.policy_decision for item in actions}
        policy_decision = next(
            (
                decision.value
                for decision in (
                    PolicyDecision.FORBIDDEN,
                    PolicyDecision.APPROVAL_REQUIRED,
                    PolicyDecision.SAFE,
                )
                if decision.value in decisions
            ),
            None,
        )
        executable_actions = [
            item.action_name for item in actions if item.status != "REJECTED"
        ]
        blocked_actions = [
            item.action_name for item in actions if item.status == "REJECTED"
        ]
        content = json.dumps(
            campaign.generated_content or {}, ensure_ascii=True, sort_keys=True
        )
        return {
            "campaign_id": campaign_id,
            "workflow_id": str(workflow_id),
            "workflow_status": workflow.status,
            "revision_number": workflow.revision_number,
            "platforms": campaign.platforms,
            "content": content,
            "generated_content": campaign.generated_content or {},
            "quality_review": campaign.quality_review or {},
            "policy_decision": policy_decision,
            "proposed_actions": executable_actions,
            "blocked_actions": blocked_actions,
            "action_count": len(actions),
            "agent_statuses": sorted({run.status for run in agent_runs}),
            "agent_error_codes": sorted(
                {run.error_code for run in agent_runs if run.error_code}
            ),
            "iterations": sum(run.iteration_count for run in agent_runs),
            "llm_calls": sum(run.llm_call_count for run in agent_runs),
            "tool_calls": sum(run.tool_call_count for run in agent_runs),
            "retry_count": workflow.retry_count,
            "limit_exceeded": any(run.status == "LIMIT_EXCEEDED" for run in agent_runs),
            "error_code": workflow.error_code,
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost": 0.0,
            "summary": f"{workflow.status} workflow for {campaign.game_name}",
        }


def _analysis() -> BriefAnalysis:
    return BriefAnalysis(
        summary="Cyber Legends deterministic evaluation campaign",
        campaign_objective="Drive pre-registration",
        target_audience="Action RPG players aged 18-30",
        main_message="Pre-register for Cyber Legends",
    )


def _content() -> GeneratedContent:
    return GeneratedContent(
        facebook=FacebookContent(
            headline="Cyber Legends pre-registration",
            content="Join Cyber Legends and reserve launch rewards.",
            cta="Pre-register now",
        ),
        tiktok=TikTokContent(
            hook="Cyber Legends is calling",
            scenes=[
                TikTokScene(
                    order=1,
                    duration_seconds=3,
                    visual="Cyber Legends neon city",
                )
            ],
            voiceover="Pre-register for Cyber Legends",
            cta="Join now",
        ),
        discord=DiscordContent(
            title="Cyber Legends pre-registration",
            message="Reserve Cyber Legends launch rewards.",
            cta="Pre-register now",
        ),
    )


def _review(
    status: Literal["PASS", "FAIL", "MANUAL_REVIEW_REQUIRED"], score: int
) -> QualityReview:
    return QualityReview(
        status=status,
        quality_score=score,
        factual_accuracy_score=score,
        tone_score=score,
        platform_fit_score=score,
    )
