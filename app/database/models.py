from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import (
    ACTIVE_WORKFLOW_STATUS_VALUES,
    ActionExecutionStatus,
    ActionRequestStatus,
    AgentRunStatus,
    CampaignStatus,
    MemoryRecordStatus,
    MemoryType,
    WorkflowStep,
)
from app.database.base import Base, utc_now


class CampaignModel(Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        CheckConstraint("retry_count >= 0", name="ck_campaign_retry_count_nonnegative"),
        CheckConstraint("version >= 1", name="ck_campaign_version_positive"),
        CheckConstraint(
            "quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 100)",
            name="ck_campaign_quality_score_range",
        ),
        Index("ix_campaigns_status_created_at", "status", "created_at"),
    )

    campaign_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    game_name: Mapped[str] = mapped_column(String(200), nullable=False)
    genre: Mapped[str] = mapped_column(String(100), nullable=False)
    target_audience: Mapped[str] = mapped_column(String(300), nullable=False)
    market: Mapped[str] = mapped_column(String(100), nullable=False)
    platforms: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    campaign_objective: Mapped[str] = mapped_column(Text, nullable=False)
    tone: Mapped[str] = mapped_column(String(500), nullable=False)
    launch_date: Mapped[date] = mapped_column(Date, nullable=False)
    promotion: Mapped[str] = mapped_column(Text, nullable=False)
    raw_brief: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=CampaignStatus.RECEIVED.value,
        index=True,
    )
    brief_analysis: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    generated_content: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    quality_review: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    quality_score: Mapped[int | None] = mapped_column(Integer, index=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    workflow_runs: Mapped[list[WorkflowRunModel]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
    )
    approvals: Mapped[list[ApprovalRecordModel]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
    )
    agent_runs: Mapped[list[AgentRunModel]] = relationship(back_populates="campaign")
    action_requests: Mapped[list[AgentActionRequestModel]] = relationship(
        back_populates="campaign"
    )
    memory_entries: Mapped[list[AgentMemoryEntryModel]] = relationship(
        back_populates="campaign"
    )


class WorkflowRunModel(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        CheckConstraint(
            "llm_call_count >= 0", name="ck_workflow_llm_call_count_nonnegative"
        ),
        CheckConstraint("retry_count >= 0", name="ck_workflow_retry_count_nonnegative"),
        CheckConstraint(
            "revision_number >= 0",
            name="ck_workflow_runs_revision_number_non_negative",
        ),
        CheckConstraint(
            "quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 100)",
            name="ck_workflow_quality_score_range",
        ),
        Index("ix_workflow_runs_campaign_status", "campaign_id", "status"),
        Index("ix_workflow_runs_parent_workflow_id", "parent_workflow_id"),
        Index(
            "uq_workflow_runs_one_active_per_campaign",
            "campaign_id",
            unique=True,
            postgresql_where=text(
                "completed_at IS NULL AND status IN ("
                + ", ".join(f"'{status}'" for status in ACTIVE_WORKFLOW_STATUS_VALUES)
                + ")"
            ),
        ),
    )

    workflow_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.campaign_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_workflow_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("workflow_runs.workflow_id", ondelete="SET NULL"),
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=CampaignStatus.RECEIVED.value,
        index=True,
    )
    current_step: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=WorkflowStep.RECEIVE_CAMPAIGN.value,
    )
    llm_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quality_score: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(String(2000))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    campaign: Mapped[CampaignModel] = relationship(back_populates="workflow_runs")
    parent_workflow: Mapped[WorkflowRunModel | None] = relationship(
        remote_side="WorkflowRunModel.workflow_id",
    )
    approvals: Mapped[list[ApprovalRecordModel]] = relationship(
        back_populates="workflow_run",
        cascade="all, delete-orphan",
    )
    agent_runs: Mapped[list[AgentRunModel]] = relationship(
        back_populates="workflow_run"
    )
    action_requests: Mapped[list[AgentActionRequestModel]] = relationship(
        back_populates="workflow_run"
    )
    memory_entries: Mapped[list[AgentMemoryEntryModel]] = relationship(
        back_populates="workflow_run"
    )


class AgentRunModel(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "iteration_count >= 0", name="ck_agent_runs_iteration_count_nonnegative"
        ),
        CheckConstraint(
            "llm_call_count >= 0", name="ck_agent_runs_llm_call_count_nonnegative"
        ),
        CheckConstraint(
            "tool_call_count >= 0", name="ck_agent_runs_tool_call_count_nonnegative"
        ),
        CheckConstraint(
            "(status IN ('COMPLETED', 'FAILED', 'LIMIT_EXCEEDED') AND completed_at IS NOT NULL) "
            "OR (status IN ('CREATED', 'RUNNING') AND completed_at IS NULL)",
            name="ck_agent_runs_completed_at_consistency",
        ),
        Index("ix_agent_runs_workflow_started_at", "workflow_id", "started_at"),
        Index(
            "uq_agent_runs_one_active_specialist",
            "workflow_id",
            "agent_name",
            unique=True,
            postgresql_where=text("status IN ('CREATED', 'RUNNING')"),
        ),
    )

    agent_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workflow_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_runs.workflow_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.campaign_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    agent_name: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=AgentRunStatus.CREATED.value, index=True
    )
    model: Mapped[str | None] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    iteration_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)

    workflow_run: Mapped[WorkflowRunModel] = relationship(back_populates="agent_runs")
    campaign: Mapped[CampaignModel] = relationship(back_populates="agent_runs")
    tool_calls: Mapped[list[AgentToolCallModel]] = relationship(
        back_populates="agent_run"
    )
    action_requests: Mapped[list[AgentActionRequestModel]] = relationship(
        back_populates="agent_run"
    )
    memory_entries: Mapped[list[AgentMemoryEntryModel]] = relationship(
        back_populates="agent_run"
    )


class AgentToolCallModel(Base):
    __tablename__ = "agent_tool_calls"
    __table_args__ = (
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_agent_tool_calls_duration_nonnegative",
        ),
        CheckConstraint(
            "(status IN ('COMPLETED', 'FAILED', 'REJECTED') AND completed_at IS NOT NULL) "
            "OR (status IN ('REQUESTED', 'RUNNING') AND completed_at IS NULL)",
            name="ck_agent_tool_calls_completed_at_consistency",
        ),
        Index("ix_agent_tool_calls_run_started_at", "agent_run_id", "started_at"),
    )

    tool_call_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    agent_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.agent_run_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    arguments: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    result_summary: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    agent_run: Mapped[AgentRunModel] = relationship(back_populates="tool_calls")


class AgentActionRequestModel(Base):
    __tablename__ = "agent_action_requests"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_action_requests_version_positive"),
        CheckConstraint(
            "policy_decision <> 'FORBIDDEN' OR status = 'REJECTED'",
            name="ck_action_requests_forbidden_rejected",
        ),
        CheckConstraint(
            "status <> 'PENDING_APPROVAL' OR ((policy_decision = 'APPROVAL_REQUIRED' OR last_policy_decision = 'APPROVAL_REQUIRED') AND expires_at IS NOT NULL)",
            name="ck_action_requests_pending_consistency",
        ),
        CheckConstraint(
            "status <> 'APPROVED' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_action_requests_approved_consistency",
        ),
        CheckConstraint(
            "status <> 'REJECTED' OR rejected_at IS NOT NULL",
            name="ck_action_requests_rejected_consistency",
        ),
        UniqueConstraint("idempotency_key", name="uq_action_requests_idempotency_key"),
        Index(
            "ix_action_requests_campaign_requested",
            "campaign_id",
            "requested_at",
        ),
        Index(
            "ix_action_requests_workflow_requested",
            "workflow_id",
            "requested_at",
        ),
        Index(
            "ix_action_requests_pending",
            "status",
            "expires_at",
            postgresql_where=text("status = 'PENDING_APPROVAL'"),
        ),
    )

    action_request_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    agent_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.agent_run_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    workflow_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_runs.workflow_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.campaign_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    agent_name: Mapped[str] = mapped_column(String(50), nullable=False)
    action_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    rationale_summary: Mapped[str] = mapped_column(Text, nullable=False)
    policy_decision: Mapped[str] = mapped_column(String(50), nullable=False)
    policy_reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    policy_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    required_role: Mapped[str | None] = mapped_column(String(50))
    last_policy_decision: Mapped[str | None] = mapped_column(String(50))
    last_policy_reason_code: Mapped[str | None] = mapped_column(String(100))
    last_policy_reason: Mapped[str | None] = mapped_column(String(500))
    last_required_role: Mapped[str | None] = mapped_column(String(50))
    last_policy_campaign_status: Mapped[str | None] = mapped_column(String(50))
    last_policy_workflow_status: Mapped[str | None] = mapped_column(String(50))
    last_policy_revision_number: Mapped[int | None] = mapped_column(Integer)
    last_policy_evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=ActionRequestStatus.PROPOSED.value,
        index=True,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str | None] = mapped_column(String(200))
    approved_role: Mapped[str | None] = mapped_column(String(50))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_by: Mapped[str | None] = mapped_column(String(200))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    agent_run: Mapped[AgentRunModel] = relationship(back_populates="action_requests")
    workflow_run: Mapped[WorkflowRunModel] = relationship(
        back_populates="action_requests"
    )
    campaign: Mapped[CampaignModel] = relationship(back_populates="action_requests")
    executions: Mapped[list[AgentActionExecutionModel]] = relationship(
        back_populates="action_request"
    )
    memory_entries: Mapped[list[AgentMemoryEntryModel]] = relationship(
        back_populates="action_request"
    )


class AgentActionExecutionModel(Base):
    __tablename__ = "agent_action_executions"
    __table_args__ = (
        CheckConstraint(
            "attempt_number >= 1", name="ck_action_executions_attempt_positive"
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_action_executions_duration_nonnegative",
        ),
        CheckConstraint(
            "memory_record_attempts >= 0",
            name="ck_action_executions_memory_attempts_nonnegative",
        ),
        CheckConstraint(
            "memory_record_status <> 'RECORDED' OR memory_recorded_at IS NOT NULL",
            name="ck_action_executions_memory_recorded_at",
        ),
        CheckConstraint(
            "(status = 'CREATED' AND started_at IS NULL AND completed_at IS NULL) OR "
            "(status = 'RUNNING' AND started_at IS NOT NULL AND completed_at IS NULL) OR "
            "(status IN ('COMPLETED', 'FAILED', 'CANCELLED') AND started_at IS NOT NULL AND completed_at IS NOT NULL)",
            name="ck_action_executions_status_timestamps",
        ),
        UniqueConstraint(
            "action_request_id", name="uq_action_executions_one_per_request"
        ),
        UniqueConstraint(
            "idempotency_key", name="uq_action_executions_idempotency_key"
        ),
        Index(
            "ix_action_executions_request_created",
            "action_request_id",
            "created_at",
        ),
    )

    action_execution_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    action_request_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_action_requests.action_request_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=ActionExecutionStatus.CREATED.value,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    result_summary: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    reserved_campaign_status: Mapped[str | None] = mapped_column(String(50))
    reserved_campaign_version: Mapped[int | None] = mapped_column(Integer)
    reserved_workflow_status: Mapped[str | None] = mapped_column(String(50))
    reserved_revision_number: Mapped[int | None] = mapped_column(Integer)
    memory_record_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=MemoryRecordStatus.NOT_REQUIRED.value
    )
    memory_record_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    memory_record_error_code: Mapped[str | None] = mapped_column(String(100))
    memory_record_error_message: Mapped[str | None] = mapped_column(Text)
    memory_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    action_request: Mapped[AgentActionRequestModel] = relationship(
        back_populates="executions"
    )
    memory_entries: Mapped[list[AgentMemoryEntryModel]] = relationship(
        back_populates="action_execution"
    )


class AgentMemoryEntryModel(Base):
    __tablename__ = "agent_memory_entries"
    __table_args__ = (
        CheckConstraint(
            "importance >= 1 AND importance <= 5",
            name="ck_memory_entries_importance_range",
        ),
        CheckConstraint(
            "expires_at IS NULL OR expires_at > created_at",
            name="ck_memory_entries_expiration_order",
        ),
        UniqueConstraint(
            "action_execution_id",
            "event_type",
            name="uq_memory_entries_execution_event",
        ),
        Index("ix_memory_entries_campaign_created", "campaign_id", "created_at"),
        Index("ix_memory_entries_workflow_created", "workflow_id", "created_at"),
        Index("ix_memory_entries_event_created", "event_type", "created_at"),
        Index("ix_memory_entries_importance_created", "importance", "created_at"),
    )

    memory_entry_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.campaign_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    workflow_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("workflow_runs.workflow_id", ondelete="RESTRICT"), index=True
    )
    agent_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_runs.agent_run_id", ondelete="RESTRICT"), index=True
    )
    action_request_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_action_requests.action_request_id", ondelete="RESTRICT"),
        index=True,
    )
    action_execution_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_action_executions.action_execution_id", ondelete="RESTRICT"),
        index=True,
    )
    memory_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default=MemoryType.EPISODIC.value
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    importance: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    campaign: Mapped[CampaignModel] = relationship(back_populates="memory_entries")
    workflow_run: Mapped[WorkflowRunModel | None] = relationship(
        back_populates="memory_entries"
    )
    agent_run: Mapped[AgentRunModel | None] = relationship(
        back_populates="memory_entries"
    )
    action_request: Mapped[AgentActionRequestModel | None] = relationship(
        back_populates="memory_entries"
    )
    action_execution: Mapped[AgentActionExecutionModel | None] = relationship(
        back_populates="memory_entries"
    )


class ApprovalRecordModel(Base):
    __tablename__ = "approval_records"
    __table_args__ = (
        CheckConstraint(
            "previous_version >= 1", name="ck_approval_previous_version_positive"
        ),
        CheckConstraint(
            "resulting_version >= previous_version", name="ck_approval_version_order"
        ),
        UniqueConstraint("workflow_id", name="uq_approval_records_workflow_id"),
        Index("ix_approval_records_campaign_decided_at", "campaign_id", "decided_at"),
    )

    approval_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.campaign_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workflow_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_runs.workflow_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    decision: Mapped[str] = mapped_column(String(50), nullable=False)
    feedback: Mapped[str | None] = mapped_column(String(5000))
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(50), nullable=False)
    previous_version: Mapped[int] = mapped_column(Integer, nullable=False)
    resulting_version: Mapped[int] = mapped_column(Integer, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    campaign: Mapped[CampaignModel] = relationship(back_populates="approvals")
    workflow_run: Mapped[WorkflowRunModel] = relationship(back_populates="approvals")


class SecurityEventModel(Base):
    __tablename__ = "security_events"
    __table_args__ = (
        Index("ix_security_events_type_created_at", "event_type", "created_at"),
        Index("ix_security_events_actor_created_at", "actor_id", "created_at"),
    )

    event_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    actor_id: Mapped[str | None] = mapped_column(String(200), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(100))
    resource_type: Mapped[str | None] = mapped_column(String(100))
    resource_id: Mapped[str | None] = mapped_column(String(200))
    campaign_id: Mapped[str | None] = mapped_column(String(100))
    workflow_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
