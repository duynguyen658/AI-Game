from enum import StrEnum


class UserRole(StrEnum):
    MARKETING = "marketing"
    REVIEWER = "reviewer"
    MANAGER = "manager"
    ADMIN = "admin"
    SYSTEM = "system"


class CampaignStatus(StrEnum):
    RECEIVED = "RECEIVED"
    VALIDATING = "VALIDATING"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    ANALYZING = "ANALYZING"
    GENERATING = "GENERATING"
    REVIEWING = "REVIEWING"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    REVISION_REQUIRED = "REVISION_REQUIRED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class ApprovalDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_REVISION = "REQUEST_REVISION"


class Platform(StrEnum):
    FACEBOOK = "Facebook"
    TIKTOK = "TikTok"
    DISCORD = "Discord"

MAX_CAMPAIGN_ID_LENGTH = 100