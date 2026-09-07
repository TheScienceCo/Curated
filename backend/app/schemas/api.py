"""Request and response models for the REST API.

Separate from the ORM on purpose: the wire format is a contract, and it should
not change just because a column moved.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.enums import (
    ClearanceLevel,
    DecisionType,
    DraftIntent,
    DraftTone,
    EmploymentType,
    MessageChannel,
    MessageStatus,
    PolygraphType,
    RecommendedAction,
    RemotePreference,
    RemoteStatus,
    SourceType,
)

ORM = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------
# Candidate profile
# --------------------------------------------------------------------------


class CandidateProfileBase(BaseModel):
    name: str
    summary: str | None = None
    current_location: str | None = None
    citizenship: str | None = None
    work_authorization: str | None = None
    clearance_level: ClearanceLevel = ClearanceLevel.NONE
    polygraph_type: PolygraphType = PolygraphType.NONE
    languages: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    technical_skills: list[str] = Field(default_factory=list)
    domain_skills: list[str] = Field(default_factory=list)
    years_experience_by_skill: dict[str, float] = Field(default_factory=dict)
    target_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    remote_preference: RemotePreference = RemotePreference.NO_PREFERENCE
    willingness_to_travel: int = Field(default=25, ge=0, le=100)
    minimum_salary: int | None = None
    target_salary: int | None = None
    desired_equity: str | None = None
    preferred_weekly_hours: int | None = Field(default=None, ge=1, le=120)
    lifestyle_preferences: dict[str, Any] = Field(default_factory=dict)
    industries_of_interest: list[str] = Field(default_factory=list)
    industries_to_avoid: list[str] = Field(default_factory=list)
    career_goals: list[str] = Field(default_factory=list)
    risk_tolerance: str = "medium"
    notes: str | None = None
    scoring_config: dict[str, Any] = Field(default_factory=dict)
    proofable_skills: list[str] = Field(default_factory=list)


class CandidateProfileCreate(CandidateProfileBase):
    pass


class CandidateProfileUpdate(BaseModel):
    """Every field optional - PATCH semantics."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    summary: str | None = None
    current_location: str | None = None
    citizenship: str | None = None
    work_authorization: str | None = None
    clearance_level: ClearanceLevel | None = None
    polygraph_type: PolygraphType | None = None
    languages: list[str] | None = None
    education: list[str] | None = None
    certifications: list[str] | None = None
    technical_skills: list[str] | None = None
    domain_skills: list[str] | None = None
    years_experience_by_skill: dict[str, float] | None = None
    target_roles: list[str] | None = None
    preferred_locations: list[str] | None = None
    remote_preference: RemotePreference | None = None
    willingness_to_travel: int | None = Field(default=None, ge=0, le=100)
    minimum_salary: int | None = None
    target_salary: int | None = None
    desired_equity: str | None = None
    preferred_weekly_hours: int | None = Field(default=None, ge=1, le=120)
    lifestyle_preferences: dict[str, Any] | None = None
    industries_of_interest: list[str] | None = None
    industries_to_avoid: list[str] | None = None
    career_goals: list[str] | None = None
    risk_tolerance: str | None = None
    notes: str | None = None
    scoring_config: dict[str, Any] | None = None
    proofable_skills: list[str] | None = None


class CandidateProfileRead(CandidateProfileBase):
    model_config = ORM
    id: str
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------
# Résumés
# --------------------------------------------------------------------------


class ResumeCreate(BaseModel):
    candidate_id: str | None = None
    title: str
    raw_text: str
    parsed_sections: dict[str, Any] = Field(default_factory=dict)
    target_families: list[str] = Field(default_factory=list)
    active: bool = True


class ResumeRead(BaseModel):
    model_config = ORM
    id: str
    candidate_id: str
    title: str
    raw_text: str
    parsed_sections: dict[str, Any]
    skills: list[str]
    target_families: list[str]
    active: bool
    created_at: datetime
    has_embedding: bool = False


# --------------------------------------------------------------------------
# Opportunities
# --------------------------------------------------------------------------


class JobOpportunityRead(BaseModel):
    model_config = ORM

    id: str
    company: str | None
    title: str | None
    location: str | None
    remote_status: RemoteStatus
    employment_type: EmploymentType
    salary_min: int | None
    salary_max: int | None
    salary_currency: str
    bonus: str | None
    commission_ote: int | None
    equity: bool | None
    equity_percent_min: float | None
    equity_percent_max: float | None
    equity_notes: str | None
    hours: int | None
    travel: int | None
    relocation_required: bool | None
    on_call: bool | None
    nights_weekends: bool | None
    shift_work: bool | None
    security_clearance: ClearanceLevel
    polygraph_requirement: PolygraphType
    citizenship_requirement: str | None
    required_skills: list[str]
    preferred_skills: list[str]
    required_years_experience: float | None
    preferred_years_experience: float | None
    education_requirements: list[str]
    certifications: list[str]
    management_responsibility: bool | None
    company_stage: str | None
    estimated_company_size: str | None
    industry: str | None
    customer_type: str | None
    government_or_commercial: str | None
    revenue_responsibility: bool | None
    customer_facing_intensity: str | None
    technical_depth: str | None
    research_intensity: str | None
    ownership_level: str | None
    job_family: str | None
    job_description: str | None
    source_url: str | None
    recruiter_name: str | None
    recruiter_contact: str | None
    source_type: SourceType
    extracted_at: datetime
    confidence: dict[str, Any]
    extraction_method: str
    notes: str | None
    created_at: datetime
    updated_at: datetime

    #: slug -> display label, so the UI never has to guess that "cicd" is
    #: "CI/CD". Derived from the ontology rather than stored.
    skill_labels: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _attach_skill_labels(self) -> JobOpportunityRead:
        from app.services.skills import label_for

        self.skill_labels = {
            slug: label_for(slug) for slug in (*self.required_skills, *self.preferred_skills)
        }
        return self


class JobOpportunityUpdate(BaseModel):
    """Manual correction of extracted fields (§17 PATCH /api/jobs/{id})."""

    model_config = ConfigDict(extra="forbid")

    company: str | None = None
    title: str | None = None
    location: str | None = None
    remote_status: RemoteStatus | None = None
    employment_type: EmploymentType | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    bonus: str | None = None
    commission_ote: int | None = None
    equity: bool | None = None
    equity_percent_min: float | None = None
    equity_percent_max: float | None = None
    hours: int | None = Field(default=None, ge=1, le=120)
    travel: int | None = Field(default=None, ge=0, le=100)
    relocation_required: bool | None = None
    on_call: bool | None = None
    nights_weekends: bool | None = None
    shift_work: bool | None = None
    security_clearance: ClearanceLevel | None = None
    polygraph_requirement: PolygraphType | None = None
    citizenship_requirement: str | None = None
    required_skills: list[str] | None = None
    preferred_skills: list[str] | None = None
    required_years_experience: float | None = None
    education_requirements: list[str] | None = None
    certifications: list[str] | None = None
    company_stage: str | None = None
    estimated_company_size: str | None = None
    industry: str | None = None
    job_family: str | None = None
    source_url: str | None = None
    recruiter_name: str | None = None
    recruiter_contact: str | None = None
    notes: str | None = None


class JobCreate(BaseModel):
    """Save an opportunity without running the analyzer."""

    raw_text: str = Field(min_length=1)
    source_url: str | None = None
    company: str | None = None
    title: str | None = None
    recruiter_name: str | None = None
    channel: MessageChannel = MessageChannel.OTHER
    use_llm: bool = True


# --------------------------------------------------------------------------
# Scores
# --------------------------------------------------------------------------


class OpportunityScoreRead(BaseModel):
    model_config = ORM

    id: str
    opportunity_id: str
    candidate_id: str
    fit_score: float
    career_capital_score: float
    proofability_score: float
    compensation_score: float
    lifestyle_score: float
    upside_score: float
    risk_score: float
    overall_score: float
    recommended_action: RecommendedAction
    explanation: dict[str, Any]
    missing_requirements: list[Any]
    matched_strengths: list[Any]
    hard_gates: list[Any]
    proofable_gaps: list[Any]
    weights_used: dict[str, float]
    generated_at: datetime


# --------------------------------------------------------------------------
# Messages, drafts, decisions
# --------------------------------------------------------------------------


class RecruiterMessageRead(BaseModel):
    model_config = ORM

    id: str
    opportunity_id: str
    raw_text: str
    channel: MessageChannel
    sender: str | None
    timestamp: datetime
    extracted_missing_information: list[Any]
    response_draft: str | None
    approved_response: str | None
    status: MessageStatus


class DraftRequest(BaseModel):
    tone: DraftTone = DraftTone.PROFESSIONAL
    intent: DraftIntent | None = None
    #: Set false to skip LLM polishing even when a provider is configured.
    polish: bool = True


class DraftResponse(BaseModel):
    intent: DraftIntent
    tone: DraftTone
    subject: str
    body: str
    questions_asked: list[str]
    generated_by: str
    message_id: str | None = None
    missing_information: list[dict[str, Any]] = Field(default_factory=list)


class MessageStatusUpdate(BaseModel):
    status: MessageStatus
    approved_response: str | None = None


class DecisionCreate(BaseModel):
    opportunity_id: str
    decision: DecisionType
    reason: str | None = None
    edited_response: str | None = None
    outcome_metadata: dict[str, Any] = Field(default_factory=dict)


class DecisionRead(BaseModel):
    model_config = ORM
    id: str
    opportunity_id: str
    decision: DecisionType
    reason: str | None
    edited_response: str | None
    outcome_metadata: dict[str, Any]
    timestamp: datetime


# --------------------------------------------------------------------------
# Analyze / dashboard / résumé match / equity
# --------------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    raw_text: str = Field(min_length=1, description="Recruiter message, email or job description")
    source_url: str | None = None
    company: str | None = None
    title: str | None = None
    recruiter_name: str | None = None
    channel: MessageChannel = MessageChannel.OTHER
    candidate_id: str | None = None
    #: Persist the opportunity. False gives a preview without saving.
    save: bool = True
    #: Generate a recruiter reply draft as part of the analysis.
    generate_draft: bool = True
    tone: DraftTone = DraftTone.PROFESSIONAL
    use_llm: bool = True


class AnalyzeResponse(BaseModel):
    opportunity: JobOpportunityRead
    score: OpportunityScoreRead
    missing_information: list[dict[str, Any]]
    draft: DraftResponse | None = None
    resume_match: dict[str, Any] | None = None
    prove_it: dict[str, Any]
    saved: bool


class DashboardRow(BaseModel):
    opportunity_id: str
    company: str | None
    title: str | None
    location: str | None
    remote_status: RemoteStatus
    salary_min: int | None
    salary_max: int | None
    salary_currency: str
    job_family: str | None
    overall_score: float
    fit_score: float
    career_capital_score: float
    proofability_score: float
    compensation_score: float
    lifestyle_score: float
    upside_score: float
    risk_score: float
    recommended_action: RecommendedAction
    hard_gate_count: int
    decision: DecisionType | None
    message_status: MessageStatus | None
    scored_at: datetime | None
    created_at: datetime


class DashboardResponse(BaseModel):
    rows: list[DashboardRow]
    total: int
    candidate: CandidateProfileRead | None
    stats: dict[str, Any]


class ResumeMatchResponse(BaseModel):
    best: dict[str, Any] | None
    ranked: list[dict[str, Any]]
    semantic_enabled: bool


class EquityRequest(BaseModel):
    equity_percent: float = Field(ge=0, le=100)
    dilution_percent: float = Field(default=40.0, ge=0, lt=100)
    current_valuation: int | None = Field(default=None, ge=0)
    strike_price: float | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    exit_valuations: list[int] | None = None


class ErrorResponse(BaseModel):
    error: dict[str, Any]


class ClearanceJobsKeywordsResponse(BaseModel):
    """Auto-generated search keywords for ClearanceJobs import."""
    keywords: str
    source: str = "target_roles and technical_skills"


class ClearanceJobsImportResponse(BaseModel):
    """Results from ClearanceJobs scraper import."""
    saved: int
    below_threshold: int
    duplicates_skipped: int
    total_results: int


__all__ = [name for name in dir() if name[0].isupper()]
