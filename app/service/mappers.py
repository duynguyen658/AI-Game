from app.core.constants import (
    ActionExecutionStatus,
    ActionRequestStatus,
    AgentName,
    AgentRunStatus,
    ApprovalDecision,
    CampaignStatus,
    MemoryEventType,
    MemoryRecordStatus,
    MemoryType,
    Platform,
    PolicyDecision,
    SecurityEventType,
    SecuritySeverity,
    ToolCallStatus,
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
from app.schemas.agent_run import AgentRunRead
from app.schemas.action_execution import ActionExecutionRead
from app.schemas.action_request import ActionRequestRead
from app.schemas.approval import ApprovalRecord
from app.schemas.campaign import (
    BriefAnalysis,
    CampaignCreate,
    CampaignRecord,
    GeneratedContent,
    QualityReview,
)
from app.schemas.security_event import SecurityEvent
from app.schemas.memory_entry import MemoryEntryRead
from app.schemas.tool_call import ToolCallRead
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
        prompt_template_id=model.prompt_template_id,
        prompt_version_id=model.prompt_version_id,
        prompt_version_number=model.prompt_version_number,
        prompt_content_hash=model.prompt_content_hash,
        provider=model.provider,
        model_configuration_hash=model.model_configuration_hash,
        tool_registry_version=model.tool_registry_version,
        policy_version=model.policy_version,
        application_version=model.application_version,
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
        last_policy_decision=(
            PolicyDecision(model.last_policy_decision)
            if model.last_policy_decision
            else None
        ),
        last_policy_reason_code=model.last_policy_reason_code,
        last_policy_reason=model.last_policy_reason,
        last_required_role=(
            UserRole(model.last_required_role) if model.last_required_role else None
        ),
        last_policy_campaign_status=(
            CampaignStatus(model.last_policy_campaign_status)
            if model.last_policy_campaign_status
            else None
        ),
        last_policy_workflow_status=(
            CampaignStatus(model.last_policy_workflow_status)
            if model.last_policy_workflow_status
            else None
        ),
        last_policy_revision_number=model.last_policy_revision_number,
        last_policy_evaluated_at=model.last_policy_evaluated_at,
        status=ActionRequestStatus(model.status),
        requested_at=model.requested_at,
        expires_at=model.expires_at,
        approved_by=model.approved_by,
        approved_role=UserRole(model.approved_role) if model.approved_role else None,
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
        reserved_campaign_status=(
            CampaignStatus(model.reserved_campaign_status)
            if model.reserved_campaign_status
            else None
        ),
        reserved_campaign_version=model.reserved_campaign_version,
        reserved_workflow_status=(
            CampaignStatus(model.reserved_workflow_status)
            if model.reserved_workflow_status
            else None
        ),
        reserved_revision_number=model.reserved_revision_number,
        memory_record_status=MemoryRecordStatus(model.memory_record_status),
        memory_record_attempts=model.memory_record_attempts,
        memory_record_error_code=model.memory_record_error_code,
        memory_record_error_message=model.memory_record_error_message,
        memory_recorded_at=model.memory_recorded_at,
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
        action_execution_id=model.action_execution_id,
        memory_type=MemoryType(model.memory_type),
        event_type=MemoryEventType(model.event_type),
        summary=model.summary,
        metadata=model.metadata_,
        importance=model.importance,
        created_at=model.created_at,
        expires_at=model.expires_at,
    )
