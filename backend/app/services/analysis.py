"""The vertical slice: text in, saved-and-scored opportunity out.

This is the only module that knows the whole flow, and it is deliberately
thin - extraction, scoring, missing-info detection and drafting are all
independently testable, and this just sequences them and persists the result.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.enums import MessageStatus
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.db.models import (
    CandidateProfile,
    JobOpportunity,
    OpportunityScore,
    RecruiterMessage,
    ResumeDocument,
)
from app.llm.base import LlmProvider
from app.schemas.extraction import ExtractionResult
from app.services import embeddings as embeddings_service
from app.services.extraction import extract
from app.services.missing_info import detect_missing_information
from app.services.response_draft import ResponseDraft, generate_response_draft
from app.services.resume_match import rank_resumes
from app.services.scoring import ScoringConfig, ScoringResult, score_opportunity

logger = get_logger(__name__)


def apply_extraction_to_job(job: JobOpportunity, result: ExtractionResult) -> JobOpportunity:
    """Copy an ExtractionResult onto an ORM row.

    Written out longhand rather than via setattr loops so that adding a field
    to the schema without wiring it here is a visible omission.
    """
    job.company = result.company
    job.title = result.title
    job.employment_type = result.employment_type.value
    job.recruiter_name = result.recruiter_name
    job.recruiter_contact = result.recruiter_contact
    job.source_type = result.source_type.value
    job.source_url = result.source_url
    job.job_description = result.job_description

    comp = result.compensation
    job.salary_min = comp.salary_min
    job.salary_max = comp.salary_max
    job.salary_currency = comp.salary_currency
    job.bonus = comp.bonus
    job.commission_ote = comp.commission_ote
    job.equity = comp.equity
    job.equity_percent_min = comp.equity_percent_min
    job.equity_percent_max = comp.equity_percent_max
    job.equity_notes = comp.equity_notes

    life = result.lifestyle
    job.remote_status = life.remote_status.value
    job.location = life.location
    job.relocation_required = life.relocation_required
    job.travel = life.travel_percent
    job.hours = life.weekly_hours
    job.on_call = life.on_call
    job.nights_weekends = life.nights_weekends
    job.shift_work = life.shift_work

    req = result.requirements
    job.required_skills = list(req.required_skills)
    job.preferred_skills = list(req.preferred_skills)
    job.required_years_experience = req.required_years_experience
    job.preferred_years_experience = req.preferred_years_experience
    job.education_requirements = list(req.education_requirements)
    job.certifications = list(req.certifications)
    job.citizenship_requirement = req.citizenship_requirement
    job.security_clearance = req.security_clearance.value
    job.polygraph_requirement = req.polygraph_requirement.value
    job.management_responsibility = req.management_responsibility

    ch = result.characteristics
    job.company_stage = ch.company_stage.value if ch.company_stage else None
    job.estimated_company_size = ch.estimated_company_size
    job.industry = ch.industry
    job.customer_type = ch.customer_type
    job.government_or_commercial = ch.government_or_commercial
    job.revenue_responsibility = ch.revenue_responsibility
    job.customer_facing_intensity = ch.customer_facing_intensity
    job.technical_depth = ch.technical_depth
    job.research_intensity = ch.research_intensity
    job.ownership_level = ch.ownership_level
    job.job_family = ch.job_family.value

    job.confidence = {k: v.value for k, v in result.confidence.items()}
    job.extraction_method = result.extraction_method
    return job


def get_active_candidate(db: Session, candidate_id: str | None = None) -> CandidateProfile:
    """Fetch the requested profile, or the only one, or fail loudly.

    Single-user by design in v1; multi-user auth is on the roadmap, and this
    is the single place that assumption lives.
    """
    if candidate_id:
        candidate = db.get(CandidateProfile, candidate_id)
        if candidate is None:
            raise NotFoundError(f"Candidate profile {candidate_id} not found")
        return candidate
    candidate = db.query(CandidateProfile).order_by(CandidateProfile.created_at).first()
    if candidate is None:
        raise NotFoundError(
            "No candidate profile exists yet. Create one with POST /api/profile "
            "before analyzing jobs."
        )
    return candidate


def config_for(candidate: CandidateProfile) -> ScoringConfig:
    """Build the scoring config from the profile, warning on invalid overrides.

    A malformed override falls back to defaults rather than failing the
    request, but it says so - scoring against weights the user did not choose
    should never be silent.
    """
    if not candidate.scoring_config:
        return ScoringConfig()
    try:
        return ScoringConfig.model_validate(candidate.scoring_config)
    except Exception as exc:  # noqa: BLE001 - defaults are always safe
        logger.warning(
            "Candidate %s has an invalid scoring_config (%s); using defaults.", candidate.id, exc
        )
        return ScoringConfig()


def persist_score(
    db: Session, job: JobOpportunity, candidate: CandidateProfile, result: ScoringResult
) -> OpportunityScore:
    score = OpportunityScore(
        opportunity_id=job.id,
        candidate_id=candidate.id,
        fit_score=result.fit.score,
        career_capital_score=result.career_capital.score,
        proofability_score=result.proofability.score,
        compensation_score=result.compensation.score,
        lifestyle_score=result.lifestyle.score,
        upside_score=result.upside.score,
        risk_score=result.risk.score,
        overall_score=result.overall,
        recommended_action=result.recommended_action.value,
        explanation=result.explanation(),
        missing_requirements=[g.to_dict() for g in [*result.hard_gates, *result.proofable_gaps]],
        matched_strengths=result.matched_strengths,
        hard_gates=[g.to_dict() for g in result.hard_gates],
        proofable_gaps=[g.to_dict() for g in result.proofable_gaps],
        weights_used=result.weights_used,
    )
    db.add(score)
    return score


def build_resume_match(
    db: Session, job: JobOpportunity, candidate: CandidateProfile
) -> dict[str, Any] | None:
    """Rank the candidate's résumé variants for this job."""
    resumes = (
        db.query(ResumeDocument)
        .filter(ResumeDocument.candidate_id == candidate.id)
        .order_by(ResumeDocument.created_at)
        .all()
    )
    if not resumes:
        return None

    job_embedding = None
    if embeddings_service.embeddings_available():
        job_embedding = embeddings_service.embed_text(job.job_description or job.title or "")

    ranked = rank_resumes(resumes, job, job_embedding)
    return {
        "best": ranked[0].to_dict() if ranked else None,
        "ranked": [m.to_dict() for m in ranked],
        "semantic_enabled": job_embedding is not None,
    }


def analyze_text(
    db: Session,
    *,
    raw_text: str,
    candidate: CandidateProfile,
    provider: LlmProvider | None = None,
    source_url: str | None = None,
    company: str | None = None,
    title: str | None = None,
    recruiter_name: str | None = None,
    channel: str = "other",
    save: bool = True,
    generate_draft: bool = True,
    tone=None,
    use_llm: bool = True,
    existing_job: JobOpportunity | None = None,
) -> dict[str, Any]:
    """Run the full pipeline. Returns the pieces the API assembles into a response.

    When `save` is False everything still runs, nothing is committed, and the
    caller gets a preview - useful for "what would this score?" without
    cluttering the dashboard.
    """
    extraction = extract(
        raw_text,
        provider=provider if use_llm else None,
        source_url=source_url,
        known_company=company,
        known_title=title,
        use_llm=use_llm,
    )
    if recruiter_name and not extraction.recruiter_name:
        extraction.recruiter_name = recruiter_name

    job = existing_job or JobOpportunity()
    apply_extraction_to_job(job, extraction)
    if recruiter_name:
        job.recruiter_name = recruiter_name

    config = config_for(candidate)
    scoring = score_opportunity(job, candidate, config)
    missing = detect_missing_information(job)

    draft: ResponseDraft | None = None
    if generate_draft:
        from app.core.enums import DraftTone

        draft = generate_response_draft(
            job,
            scoring,
            missing,
            tone=tone or DraftTone.PROFESSIONAL,
            candidate_name=candidate.name,
            provider=provider if use_llm else None,
            polish=use_llm,
        )

    message: RecruiterMessage | None = None
    score_row: OpportunityScore | None = None

    if save:
        db.add(job)
        db.flush()  # assign job.id before dependent rows reference it
        score_row = persist_score(db, job, candidate, scoring)
        message = RecruiterMessage(
            opportunity_id=job.id,
            raw_text=raw_text,
            channel=channel,
            sender=job.recruiter_name,
            extracted_missing_information=[m.to_dict() for m in missing],
            response_draft=draft.body if draft else None,
            status=MessageStatus.DRAFT_GENERATED.value if draft else MessageStatus.ANALYZED.value,
        )
        db.add(message)
        db.commit()
        db.refresh(job)
        db.refresh(score_row)
    else:
        # Give the preview a stable identity without touching the database.
        from app.db.base import new_id

        job.id = job.id or new_id()
        score_row = OpportunityScore(
            opportunity_id=job.id,
            candidate_id=candidate.id,
            fit_score=scoring.fit.score,
            career_capital_score=scoring.career_capital.score,
            proofability_score=scoring.proofability.score,
            compensation_score=scoring.compensation.score,
            lifestyle_score=scoring.lifestyle.score,
            upside_score=scoring.upside.score,
            risk_score=scoring.risk.score,
            overall_score=scoring.overall,
            recommended_action=scoring.recommended_action.value,
            explanation=scoring.explanation(),
            missing_requirements=[
                g.to_dict() for g in [*scoring.hard_gates, *scoring.proofable_gaps]
            ],
            matched_strengths=scoring.matched_strengths,
            hard_gates=[g.to_dict() for g in scoring.hard_gates],
            proofable_gaps=[g.to_dict() for g in scoring.proofable_gaps],
            weights_used=scoring.weights_used,
        )
        _fill_preview_defaults(job, score_row)

    resume_match = build_resume_match(db, job, candidate) if save else None

    return {
        "job": job,
        "score": score_row,
        "scoring": scoring,
        "missing": missing,
        "draft": draft,
        "message": message,
        "resume_match": resume_match,
        "extraction": extraction,
    }


def _fill_preview_defaults(job: JobOpportunity, score: OpportunityScore) -> None:
    """Populate server-side defaults that a flush would normally supply.

    An unsaved row has None where the database would have written a default,
    and the response schemas require real values.
    """
    from app.db.base import new_id, utcnow

    now = utcnow()
    score.id = score.id or new_id()
    score.generated_at = score.generated_at or now
    job.created_at = job.created_at or now
    job.updated_at = job.updated_at or now
    job.extracted_at = job.extracted_at or now
    for attr in (
        "required_skills",
        "preferred_skills",
        "education_requirements",
        "certifications",
    ):
        if getattr(job, attr) is None:
            setattr(job, attr, [])
    if job.confidence is None:
        job.confidence = {}


__all__ = [
    "analyze_text",
    "apply_extraction_to_job",
    "get_active_candidate",
    "config_for",
    "persist_score",
    "build_resume_match",
]
