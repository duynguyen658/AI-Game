from app.core.constants import (
    ApprovalDecision,
    CampaignStatus,
    Platform,
    SecurityEventType,
    SecuritySeverity,
    UserRole,
    WorkflowStep,
)
from app.database.models import (
    AgentActionExecutionModel,
    AgentActionRequestModel,
    AgentMemoryEntryModel,
    AgentRunModel,
    AgentToolCallModel,
    ApprovalRecordModel,
    CampaignModel,
    SecurityEventModel,
    WorkflowRunModel,
)
from app.schemas.action_execution import ActionExecutionRead
from app.schemas.action_request import ActionRequestRead
from app.schemas.memory_entry import MemoryEntryRead
from app.core.constants import (
    ActionExecutionStatus,
    ActionRequestStatus,
    MemoryEventType,
    MemoryType,
    PolicyDecision,
)
from app.core.constants import AgentName, AgentRunStatus, ToolCallStatus
from app.schemas.agent_run import AgentRunRead
from app.schemas.tool_call import ToolCallRead
from app.schemas.approval import ApprovalRecord
from app.schemas.campaign import (
    BriefAnalysis,
    CampaignCreate,
    CampaignRecord,
    GeneratedContent,
    QualityReview,
)
from app.schemas.security_event import SecurityEvent
from app.schemas.workflow_run import WorkflowRun


def campaign_to_record(model: CampaignModel) -> CampaignRecord:
    campaign = CampaignCreate(
        campaign_id=model.campaign_id,
        game_name=model.game_name,
        genre=model.genre,
        target_audience=model.target_audience,
        market=model.market,
        platforms=[Platform(platform) for platform in model.platforms],
        campaign_objective=model.campaign_objective,
        tone=model.tone,
        launch_date=model.launch_date,
        promotion=model.promotion,
        raw_brief=model.raw_brief,
    )
    return CampaignRecord(
        campaign=campaign,
        status=CampaignStatus(model.status),
        analysis=(
            BriefAnalysis.model_validate(model.brief_analysis)
            if model.brief_analysis
            else None
        ),
        generated_content=(
            GeneratedContent.model_validate(model.generated_content)
            if model.generated_content
            else None
        ),
        quality_review=(
            QualityReview.model_validate(model.quality_review)
            if model.quality_review
            else None
        ),
        retry_count=model.retry_count,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def workflow_to_schema(model: WorkflowRunModel) -> WorkflowRun:
    return WorkflowRun(
        workflow_id=model.workflow_id,
        campaign_id=model.campaign_id,
        parent_workflow_id=model.parent_workflow_id,
        revision_number=model.revision_number,
        status=CampaignStatus(model.status),
        current_step=WorkflowStep(model.current_step),
        llm_call_count=model.llm_call_count,
        retry_count=model.retry_count,
        quality_score=model.quality_score,
        error_code=model.error_code,
        error_message=model.error_message,
        started_at=model.started_at,
        completed_at=model.completed_at,
    )


def approval_to_schema(model: ApprovalRecordModel) -> ApprovalRecord:
    return ApprovalRecord(
        campaign_id=model.campaign_id,
        workflow_id=model.workflow_id,
        decision=ApprovalDecision(model.decision),
        feedback=model.feedback,
        actor_id=model.actor_id,
        actor_role=UserRole(model.actor_role),
        previous_version=model.previous_version,
        resulting_version=model.resulting_version,
        decided_at=model.decided_at,
    )


def security_event_to_schema(model: SecurityEventModel) -> SecurityEvent:
    return SecurityEvent(
        event_id=model.event_id,
        event_type=SecurityEventType(model.event_type),
        severity=SecuritySeverity(model.severity),
        campaign_id=model.campaign_id,
        workflow_id=model.workflow_id,
        actor_id=model.actor_id,
        source=model.source,
        message=model.message,
        metadata=model.metadata_,
        occurred_at=model.created_at,
    )


def agent_run_to_schema(model: AgentRunModel) -> AgentRunRead:
    return AgentRunRead(
        agent_run_id=model.agent_run_id,
        workflow_id=model.workflow_id,
        campaign_id=model.campaign_id,
        agent_name=AgentName(model.agent_name),
        status=AgentRunStatus(model.status),
        model=model.model,
        prompt_version=model.prompt_version,
        iteration_count=model.iteration_count,
        llm_call_count=model.llm_call_count,
        tool_call_count=model.tool_call_count,
        started_at=model.started_at,
        updated_at=model.updated_at,
        completed_at=model.completed_at,
        error_code=model.error_code,
        error_message=model.error_message,
    )


def tool_call_to_schema(model: AgentToolCallModel) -> ToolCallRead:
    return ToolCallRead(
        tool_call_id=model.tool_call_id,
        agent_run_id=model.agent_run_id,
        tool_name=model.tool_name,
        arguments=model.arguments,
        status=ToolCallStatus(model.status),
        result_summary=model.result_summary,
        error_code=model.error_code,
        error_message=model.error_message,
        started_at=model.started_at,
        completed_at=model.completed_at,
        duration_ms=model.duration_ms,
    )


def action_request_to_schema(model: AgentActionRequestModel) -> ActionRequestRead:
    return ActionRequestRead(
        action_request_id=model.action_request_id,
        agent_run_id=model.agent_run_id,
        workflow_id=model.workflow_id,
        campaign_id=model.campaign_id,
        agent_name=AgentName(model.agent_name),
        action_name=model.action_name,
        arguments=model.arguments,
        rationale_summary=model.rationale_summary,
        policy_decision=PolicyDecision(model.policy_decision),
        policy_reason_code=model.policy_reason_code,
        policy_reason=model.policy_reason,
        required_role=UserRole(model.required_role) if model.required_role else None,
        status=ActionRequestStatus(model.status),
        requested_at=model.requested_at,
        expires_at=model.expires_at,
        approved_by=model.approved_by,
        approved_at=model.approved_at,
        rejected_by=model.rejected_by,
        rejected_at=model.rejected_at,
        rejection_reason=model.rejection_reason,
        version=model.version,
        idempotency_key=model.idempotency_key,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def action_execution_to_schema(
    model: AgentActionExecutionModel,
) -> ActionExecutionRead:
    return ActionExecutionRead(
        action_execution_id=model.action_execution_id,
        action_request_id=model.action_request_id,
        status=ActionExecutionStatus(model.status),
        attempt_number=model.attempt_number,
        idempotency_key=model.idempotency_key,
        started_at=model.started_at,
        completed_at=model.completed_at,
        duration_ms=model.duration_ms,
        result_summary=model.result_summary,
        error_code=model.error_code,
        error_message=model.error_message,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def memory_entry_to_schema(model: AgentMemoryEntryModel) -> MemoryEntryRead:
    return MemoryEntryRead(
        memory_entry_id=model.memory_entry_id,
        campaign_id=model.campaign_id,
        workflow_id=model.workflow_id,
        agent_run_id=model.agent_run_id,
        action_request_id=model.action_request_id,
        memory_type=MemoryType(model.memory_type),
        event_type=MemoryEventType(model.event_type),
        summary=model.summary,
        metadata=model.metadata_,
        importance=model.importance,
        created_at=model.created_at,
        expires_at=model.expires_at,
    )
