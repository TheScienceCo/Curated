"""ORM models for the Job Intelligence Agent.

Design notes
------------
* IDs are string UUIDs so the same DDL works on Postgres and SQLite.
* List/dict-shaped fields use a portable JSON column (JSONB on Postgres).
* Enum-valued columns are stored as strings; validation lives in the Pydantic
  layer so the database stays easy to migrate and inspect.
* `embedding` is stored as a JSON float array. pgvector is on the roadmap; the
  cosine similarity used today is computed in Python, which is more than fast
  enough for the handful of résumé variants a single candidate maintains.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    ClearanceLevel,
    Confidence,
    EmploymentType,
    MessageStatus,
    PolygraphType,
    RemotePreference,
    RemoteStatus,
    SourceType,
)
from app.db.base import Base, IdType, JsonType, UtcDateTime, new_id, utcnow


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    id: Mapped[str] = mapped_column(IdType, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text, default=None)

    # Location / eligibility ------------------------------------------------
    current_location: Mapped[str | None] = mapped_column(String(200), default=None)
    citizenship: Mapped[str | None] = mapped_column(String(100), default=None)
    work_authorization: Mapped[str | None] = mapped_column(String(200), default=None)
    clearance_level: Mapped[str] = mapped_column(String(40), default=ClearanceLevel.NONE.value)
    polygraph_type: Mapped[str] = mapped_column(String(40), default=PolygraphType.NONE.value)

    # Background ------------------------------------------------------------
    languages: Mapped[list] = mapped_column(JsonType, default=list)
    education: Mapped[list] = mapped_column(JsonType, default=list)
    certifications: Mapped[list] = mapped_column(JsonType, default=list)
    technical_skills: Mapped[list] = mapped_column(JsonType, default=list)
    domain_skills: Mapped[list] = mapped_column(JsonType, default=list)
    years_experience_by_skill: Mapped[dict] = mapped_column(JsonType, default=dict)

    # Targets ---------------------------------------------------------------
    target_roles: Mapped[list] = mapped_column(JsonType, default=list)
    preferred_locations: Mapped[list] = mapped_column(JsonType, default=list)
    remote_preference: Mapped[str] = mapped_column(
        String(40), default=RemotePreference.NO_PREFERENCE.value
    )
    willingness_to_travel: Mapped[int] = mapped_column(Integer, default=25)  # percent
    minimum_salary: Mapped[int | None] = mapped_column(Integer, default=None)
    target_salary: Mapped[int | None] = mapped_column(Integer, default=None)
    desired_equity: Mapped[str | None] = mapped_column(String(200), default=None)
    preferred_weekly_hours: Mapped[int | None] = mapped_column(Integer, default=None)

    # Preferences -----------------------------------------------------------
    lifestyle_preferences: Mapped[dict] = mapped_column(JsonType, default=dict)
    industries_of_interest: Mapped[list] = mapped_column(JsonType, default=list)
    industries_to_avoid: Mapped[list] = mapped_column(JsonType, default=list)
    career_goals: Mapped[list] = mapped_column(JsonType, default=list)
    risk_tolerance: Mapped[str] = mapped_column(String(20), default="medium")
    notes: Mapped[str | None] = mapped_column(Text, default=None)

    #: Candidate-configurable knobs: compensation bands and score weights.
    scoring_config: Mapped[dict] = mapped_column(JsonType, default=dict)
    #: Skills the candidate can demonstrate quickly despite no formal experience.
    proofable_skills: Mapped[list] = mapped_column(JsonType, default=list)

    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, onupdate=utcnow)

    resumes: Mapped[list[ResumeDocument]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )


class ResumeDocument(Base):
    __tablename__ = "resume_documents"

    id: Mapped[str] = mapped_column(IdType, primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(
        IdType, ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    raw_text: Mapped[str] = mapped_column(Text)
    parsed_sections: Mapped[dict] = mapped_column(JsonType, default=dict)
    #: Optional dense vector; null when embeddings are disabled.
    embedding: Mapped[list | None] = mapped_column(JsonType, default=None)
    #: Normalised skill slugs mined from the résumé text (deterministic).
    skills: Mapped[list] = mapped_column(JsonType, default=list)
    #: Job families this variant is aimed at, used to break ties in matching.
    target_families: Mapped[list] = mapped_column(JsonType, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    candidate: Mapped[CandidateProfile] = relationship(back_populates="resumes")


class JobOpportunity(Base):
    __tablename__ = "job_opportunities"

    id: Mapped[str] = mapped_column(IdType, primary_key=True, default=new_id)
    company: Mapped[str | None] = mapped_column(String(200), default=None, index=True)
    title: Mapped[str | None] = mapped_column(String(300), default=None)
    location: Mapped[str | None] = mapped_column(String(200), default=None)
    remote_status: Mapped[str] = mapped_column(String(30), default=RemoteStatus.UNSPECIFIED.value)
    employment_type: Mapped[str] = mapped_column(
        String(30), default=EmploymentType.UNSPECIFIED.value
    )

    # Compensation ----------------------------------------------------------
    salary_min: Mapped[int | None] = mapped_column(Integer, default=None)
    salary_max: Mapped[int | None] = mapped_column(Integer, default=None)
    salary_currency: Mapped[str] = mapped_column(String(8), default="USD")
    bonus: Mapped[str | None] = mapped_column(String(200), default=None)
    commission_ote: Mapped[int | None] = mapped_column(Integer, default=None)
    equity: Mapped[bool | None] = mapped_column(Boolean, default=None)
    equity_percent_min: Mapped[float | None] = mapped_column(Float, default=None)
    equity_percent_max: Mapped[float | None] = mapped_column(Float, default=None)
    equity_notes: Mapped[str | None] = mapped_column(String(300), default=None)

    # Lifestyle -------------------------------------------------------------
    hours: Mapped[int | None] = mapped_column(Integer, default=None)
    travel: Mapped[int | None] = mapped_column(Integer, default=None)  # percent
    relocation_required: Mapped[bool | None] = mapped_column(Boolean, default=None)
    on_call: Mapped[bool | None] = mapped_column(Boolean, default=None)
    nights_weekends: Mapped[bool | None] = mapped_column(Boolean, default=None)
    shift_work: Mapped[bool | None] = mapped_column(Boolean, default=None)

    # Eligibility -----------------------------------------------------------
    security_clearance: Mapped[str] = mapped_column(
        String(40), default=ClearanceLevel.UNSPECIFIED.value
    )
    polygraph_requirement: Mapped[str] = mapped_column(
        String(40), default=PolygraphType.UNKNOWN.value
    )
    citizenship_requirement: Mapped[str | None] = mapped_column(String(200), default=None)

    # Requirements ----------------------------------------------------------
    required_skills: Mapped[list] = mapped_column(JsonType, default=list)
    preferred_skills: Mapped[list] = mapped_column(JsonType, default=list)
    required_years_experience: Mapped[float | None] = mapped_column(Float, default=None)
    preferred_years_experience: Mapped[float | None] = mapped_column(Float, default=None)
    education_requirements: Mapped[list] = mapped_column(JsonType, default=list)
    certifications: Mapped[list] = mapped_column(JsonType, default=list)
    management_responsibility: Mapped[bool | None] = mapped_column(Boolean, default=None)

    # Opportunity characteristics ------------------------------------------
    company_stage: Mapped[str | None] = mapped_column(String(40), default=None)
    estimated_company_size: Mapped[str | None] = mapped_column(String(60), default=None)
    industry: Mapped[str | None] = mapped_column(String(120), default=None)
    customer_type: Mapped[str | None] = mapped_column(String(60), default=None)
    government_or_commercial: Mapped[str | None] = mapped_column(String(40), default=None)
    revenue_responsibility: Mapped[bool | None] = mapped_column(Boolean, default=None)
    customer_facing_intensity: Mapped[str | None] = mapped_column(String(20), default=None)
    technical_depth: Mapped[str | None] = mapped_column(String(20), default=None)
    research_intensity: Mapped[str | None] = mapped_column(String(20), default=None)
    ownership_level: Mapped[str | None] = mapped_column(String(20), default=None)
    job_family: Mapped[str | None] = mapped_column(String(60), default=None, index=True)

    # Provenance ------------------------------------------------------------
    job_description: Mapped[str | None] = mapped_column(Text, default=None)
    source_url: Mapped[str | None] = mapped_column(String(1000), default=None)
    recruiter_name: Mapped[str | None] = mapped_column(String(200), default=None)
    recruiter_contact: Mapped[str | None] = mapped_column(String(200), default=None)
    source_type: Mapped[str] = mapped_column(String(40), default=SourceType.MANUAL.value)
    extracted_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    #: Per-field confidence map, e.g. {"salary_min": "high", "travel": "low"}.
    confidence: Mapped[dict] = mapped_column(JsonType, default=dict)
    #: Which pipeline produced this record: "rules", "llm", or "llm+rules".
    extraction_method: Mapped[str] = mapped_column(String(30), default="rules")

    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, onupdate=utcnow)

    messages: Mapped[list[RecruiterMessage]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )
    scores: Mapped[list[OpportunityScore]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )
    decisions: Mapped[list[UserDecision]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )


class RecruiterMessage(Base):
    __tablename__ = "recruiter_messages"

    id: Mapped[str] = mapped_column(IdType, primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(
        IdType, ForeignKey("job_opportunities.id", ondelete="CASCADE"), index=True
    )
    raw_text: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(30), default="other")
    sender: Mapped[str | None] = mapped_column(String(200), default=None)
    timestamp: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    #: Ordered list of missing-field records (field, priority, question).
    extracted_missing_information: Mapped[list] = mapped_column(JsonType, default=list)
    response_draft: Mapped[str | None] = mapped_column(Text, default=None)
    #: The human-edited version, kept separately so the draft stays auditable.
    approved_response: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(String(30), default=MessageStatus.NEW.value, index=True)

    opportunity: Mapped[JobOpportunity] = relationship(back_populates="messages")


class OpportunityScore(Base):
    __tablename__ = "opportunity_scores"

    id: Mapped[str] = mapped_column(IdType, primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(
        IdType, ForeignKey("job_opportunities.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[str] = mapped_column(
        IdType, ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )

    fit_score: Mapped[float] = mapped_column(Float, default=0.0)
    career_capital_score: Mapped[float] = mapped_column(Float, default=0.0)
    proofability_score: Mapped[float] = mapped_column(Float, default=0.0)
    compensation_score: Mapped[float] = mapped_column(Float, default=0.0)
    lifestyle_score: Mapped[float] = mapped_column(Float, default=0.0)
    upside_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)

    recommended_action: Mapped[str] = mapped_column(String(30), default="MAYBE")
    #: Human-readable narrative plus per-dimension reason bullets.
    explanation: Mapped[dict] = mapped_column(JsonType, default=dict)
    missing_requirements: Mapped[list] = mapped_column(JsonType, default=list)
    matched_strengths: Mapped[list] = mapped_column(JsonType, default=list)
    hard_gates: Mapped[list] = mapped_column(JsonType, default=list)
    proofable_gaps: Mapped[list] = mapped_column(JsonType, default=list)
    weights_used: Mapped[dict] = mapped_column(JsonType, default=dict)
    generated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    opportunity: Mapped[JobOpportunity] = relationship(back_populates="scores")


Index(
    "ix_scores_opportunity_generated",
    OpportunityScore.opportunity_id,
    OpportunityScore.generated_at,
)


class UserDecision(Base):
    __tablename__ = "user_decisions"

    id: Mapped[str] = mapped_column(IdType, primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(
        IdType, ForeignKey("job_opportunities.id", ondelete="CASCADE"), index=True
    )
    decision: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    edited_response: Mapped[str | None] = mapped_column(Text, default=None)
    #: Outcome feedback used later for ranking improvements (§16).
    outcome_metadata: Mapped[dict] = mapped_column(JsonType, default=dict)
    timestamp: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    opportunity: Mapped[JobOpportunity] = relationship(back_populates="decisions")


__all__ = [
    "CandidateProfile",
    "ResumeDocument",
    "JobOpportunity",
    "RecruiterMessage",
    "OpportunityScore",
    "UserDecision",
    "Confidence",
]
