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
    CampaignStatus,
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
