"""Domain enums for TalentScreen AI.
Defines all authoritative enum types according to 00-scope-decisions and 03-data-api-state-machines.
"""
from enum import Enum


class EnvironmentMode(str, Enum):
    SANDBOX = "sandbox"
    PILOT = "pilot"


class PilotStage(str, Enum):
    SHADOW = "shadow"
    ASSISTED = "assisted"


class UserStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class AccountRole(str, Enum):
    ADMIN = "admin"
    RECRUITER = "recruiter"
    REVIEWER = "reviewer"


class MembershipRole(str, Enum):
    OWNER = "owner"
    REVIEWER = "reviewer"


class RequisitionStatus(str, Enum):
    DRAFT = "draft"
    OPEN = "open"
    PAUSED = "paused"
    CLOSED = "closed"


class RubricStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class CriterionId(str, Enum):
    PYTHON_BACKEND = "python_backend"
    API_DESIGN = "api_design"
    SQL_DATA = "sql_data"
    TESTING_DEBUGGING = "testing_debugging"
    SECURITY_PRIVACY = "security_privacy"
    DELIVERY_OPS = "delivery_ops"


class CriterionOutcome(str, Enum):
    ASSESSED = "assessed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"


class Recommendation(str, Enum):
    CONSIDER_NEXT_ROUND = "consider_next_round"
    NEEDS_CLARIFICATION = "needs_clarification"
    REVIEW_REQUIRED = "review_required"


class DecisionOutcome(str, Enum):
    ADVANCE = "advance"
    REQUEST_INFORMATION = "request_information"
    NOT_ADVANCE = "not_advance"


class DecisionBasis(str, Enum):
    ASSESSMENT_REVIEW = "assessment_review"
    MANUAL_DOCUMENT_REVIEW = "manual_document_review"
    TECHNICAL_INFORMATION_REQUEST = "technical_information_request"


class DocumentSafetyStatus(str, Enum):
    PENDING = "pending"
    PASSED = "passed"
    REJECTED = "rejected"


class SanitizedVersionStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    SUPERSEDED = "superseded"
    REVOKED = "revoked"


class JobType(str, Enum):
    INGEST_DOCUMENT = "ingest_document"
    EMBED_SANITIZED = "embed_sanitized"
    DRAFT_RUBRIC = "draft_rubric"
    ASSESS_APPLICATION = "assess_application"
    DRAFT_INTERVIEW = "draft_interview"
    PURGE_DATA = "purge_data"
    COPILOT_SELECT = "copilot_select"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STALE = "stale"


class LLMInvocationStatus(str, Enum):
    RESERVED = "reserved"
    ADMITTED = "admitted"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    OUTCOME_UNKNOWN = "outcome_unknown"


class BudgetScope(str, Enum):
    DEVELOPMENT = "development"
    PILOT = "pilot"


class DeletionScope(str, Enum):
    APPLICATION = "application"
    CANDIDATE = "candidate"


class DeletionStatus(str, Enum):
    REQUESTED = "requested"
    PURGING = "purging"
    AWAITING_EXTERNAL = "awaiting_external"
    COMPLETED = "completed"
    FAILED = "failed"
