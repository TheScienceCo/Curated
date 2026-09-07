"""Canonical enumerations shared by the ORM, the API schemas and the services.

These are plain `str` enums so they serialise cleanly to JSON and can be stored
in portable string columns (Postgres in production, SQLite in tests).
"""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - trivial
        return str(self.value)


class ClearanceLevel(StrEnum):
    """US personnel security clearance levels, ordered least -> most access."""

    NONE = "none"
    PUBLIC_TRUST = "public_trust"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"
    TOP_SECRET = "top_secret"
    TS_SCI = "ts_sci"
    UNSPECIFIED = "unspecified"


#: Ordering used for "does the candidate meet the bar?" comparisons.
CLEARANCE_RANK: dict[str, int] = {
    ClearanceLevel.NONE: 0,
    ClearanceLevel.PUBLIC_TRUST: 1,
    ClearanceLevel.CONFIDENTIAL: 2,
    ClearanceLevel.SECRET: 3,
    ClearanceLevel.TOP_SECRET: 4,
    ClearanceLevel.TS_SCI: 5,
}


class PolygraphType(StrEnum):
    """Polygraph requirements.

    The distinction between a counterintelligence (CI) polygraph and a
    full-scope / expanded-scope polygraph (FSP / ESP) is deliberately explicit.
    They are NOT interchangeable: a CI poly does not satisfy an FSP
    requirement, and treating them as equivalent produces dangerously wrong
    eligibility answers.
    """

    NONE = "none"
    CI = "ci"
    FULL_SCOPE = "full_scope"
    UNSPECIFIED_POLYGRAPH = "unspecified_polygraph"
    UNKNOWN = "unknown"


#: Which candidate polygraphs satisfy which job requirement.
#: FSP/ESP subsumes CI. CI never subsumes FSP/ESP.
POLYGRAPH_SATISFIES: dict[str, set[str]] = {
    PolygraphType.NONE: {PolygraphType.NONE},
    PolygraphType.CI: {PolygraphType.NONE, PolygraphType.CI},
    PolygraphType.FULL_SCOPE: {
        PolygraphType.NONE,
        PolygraphType.CI,
        PolygraphType.FULL_SCOPE,
        PolygraphType.UNSPECIFIED_POLYGRAPH,
    },
}


class RemoteStatus(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNSPECIFIED = "unspecified"


class RemotePreference(StrEnum):
    REMOTE_ONLY = "remote_only"
    REMOTE_PREFERRED = "remote_preferred"
    HYBRID_OK = "hybrid_ok"
    ONSITE_OK = "onsite_ok"
    NO_PREFERENCE = "no_preference"


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    FRACTIONAL = "fractional"
    UNSPECIFIED = "unspecified"


class SourceType(StrEnum):
    RECRUITER_EMAIL = "recruiter_email"
    LINKEDIN_MESSAGE = "linkedin_message"
    JOB_POSTING = "job_posting"
    REFERRAL = "referral"
    MANUAL = "manual"
    OTHER = "other"


class MessageChannel(StrEnum):
    EMAIL = "email"
    LINKEDIN = "linkedin"
    SMS = "sms"
    PHONE = "phone"
    JOB_BOARD = "job_board"
    OTHER = "other"


class MessageStatus(StrEnum):
    NEW = "new"
    ANALYZED = "analyzed"
    DRAFT_GENERATED = "draft_generated"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"
    IGNORED = "ignored"


class DecisionType(StrEnum):
    PURSUE = "pursue"
    MAYBE = "maybe"
    REJECT = "reject"
    IGNORE = "ignore"
    RESPONDED = "responded"
    INTERVIEWED = "interviewed"
    OFFER = "offer"
    DECLINED_OFFER = "declined_offer"
    ACCEPTED_OFFER = "accepted_offer"


class RecommendedAction(StrEnum):
    STRONGLY_PURSUE = "STRONGLY_PURSUE"
    PURSUE = "PURSUE"
    WORTH_A_CALL = "WORTH_A_CALL"
    MAYBE = "MAYBE"
    LOW_PRIORITY = "LOW_PRIORITY"
    REJECT = "REJECT"


class CompanyStage(StrEnum):
    PRE_SEED = "pre_seed"
    SEED = "seed"
    SERIES_A = "series_a"
    SERIES_B = "series_b"
    SERIES_C = "series_c"
    GROWTH = "growth"
    LATE_STAGE = "late_stage"
    PUBLIC = "public"
    GOVERNMENT = "government"
    NONPROFIT = "nonprofit"
    ESTABLISHED_PRIVATE = "established_private"
    UNSPECIFIED = "unspecified"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    ABSENT = "absent"


class ProofabilityTier(StrEnum):
    """How a missing requirement can (or cannot) be closed."""

    ALREADY_DEMONSTRATED = "already_demonstrated"
    PROOFABLE = "proofable"
    HARD_GATE = "hard_gate"


class JobFamily(StrEnum):
    # AI / Engineering
    FORWARD_DEPLOYED_ENGINEER = "forward_deployed_engineer"
    AI_ENGINEER = "ai_engineer"
    ML_ENGINEER = "ml_engineer"
    RESEARCH_ENGINEER = "research_engineer"
    MEMBER_OF_TECHNICAL_STAFF = "member_of_technical_staff"
    SOLUTIONS_ARCHITECT = "solutions_architect"
    # National security / defense
    CLEARED_SOFTWARE_ENGINEER = "cleared_software_engineer"
    AI_MISSION_ENGINEER = "ai_mission_engineer"
    TECHNICAL_INTELLIGENCE_ANALYST = "technical_intelligence_analyst"
    TECHNICAL_PROGRAM_SETA = "technical_program_seta"
    # Cyber
    MALWARE_REVERSE_ENGINEER = "malware_reverse_engineer"
    VULNERABILITY_RESEARCHER = "vulnerability_researcher"
    CYBER_THREAT_INTELLIGENCE = "cyber_threat_intelligence"
    AI_SECURITY_ENGINEER = "ai_security_engineer"
    # Bio / scientific AI
    SCIENTIFIC_ML_ENGINEER = "scientific_ml_engineer"
    COMPUTATIONAL_BIOLOGY_ML = "computational_biology_ml"
    BIOSECURITY_SCIENTIST = "biosecurity_scientist"
    # Customer / revenue
    SOLUTIONS_ENGINEER = "solutions_engineer"
    TECHNICAL_ACCOUNT_EXECUTIVE = "technical_account_executive"
    TECHNICAL_BUSINESS_DEVELOPMENT = "technical_business_development"
    GTM_ENGINEER = "gtm_engineer"
    # Generalist / multidisciplinary
    CHIEF_OF_STAFF = "chief_of_staff"
    FOUNDERS_OFFICE = "founders_office"
    SPECIAL_PROJECTS = "special_projects"
    STRATEGY_AND_OPERATIONS = "strategy_and_operations"
    ENTREPRENEUR_IN_RESIDENCE = "entrepreneur_in_residence"
    # Fallback
    OTHER = "other"


class DraftTone(StrEnum):
    PROFESSIONAL = "professional"
    WARM = "warm"
    DIRECT = "direct"
    HUMOROUS = "humorous"


class DraftIntent(StrEnum):
    REQUEST_MISSING_INFO = "request_missing_info"
    ENTHUSIASTIC_SCHEDULE = "enthusiastic_schedule"
    POLITE_DECLINE = "polite_decline"
    CLEARANCE_CLARIFICATION = "clearance_clarification"
