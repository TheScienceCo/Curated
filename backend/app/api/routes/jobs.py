"""Opportunity endpoints: analyze, list, read, update, score, draft, résumé match."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import db_session, llm_provider
from app.core.enums import MessageStatus
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.db.models import JobOpportunity, OpportunityScore, RecruiterMessage
from app.llm.base import LlmProvider
from app.schemas.api import (
    AnalyzeRequest,
    AnalyzeResponse,
    DraftRequest,
    DraftResponse,
    JobCreate,
    JobOpportunityRead,
    JobOpportunityUpdate,
    OpportunityScoreRead,
    RecruiterMessageRead,
    ResumeMatchResponse,
)
from app.services.analysis import (
    analyze_text,
    build_resume_match,
    config_for,
    get_active_candidate,
    persist_score,
)
from app.services.missing_info import detect_missing_information
from app.services.response_draft import generate_response_draft
from app.services.scoring import score_opportunity

logger = get_logger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

#: Statuses that represent a human sign-off, which regeneration must not undo.
_SIGNED_OFF = frozenset({MessageStatus.APPROVED.value, MessageStatus.EDITED.value})


def _get_job(db: Session, job_id: str) -> JobOpportunity:
    job = db.get(JobOpportunity, job_id)
    if job is None:
        raise NotFoundError(f"Opportunity {job_id} not found")
    return job


def _latest_score(db: Session, job_id: str) -> OpportunityScore | None:
    return (
        db.query(OpportunityScore)
        .filter(OpportunityScore.opportunity_id == job_id)
        .order_by(desc(OpportunityScore.generated_at))
        .first()
    )


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(
    payload: AnalyzeRequest,
    db: Session = Depends(db_session),
    provider: LlmProvider = Depends(llm_provider),
) -> AnalyzeResponse:
    """The core workflow: paste text, get structured data, scores and a draft.

    Nothing is sent anywhere. The draft is stored for human approval.
    """
    candidate = get_active_candidate(db, payload.candidate_id)
    outcome = analyze_text(
        db,
        raw_text=payload.raw_text,
        candidate=candidate,
        provider=provider,
        source_url=payload.source_url,
        company=payload.company,
        title=payload.title,
        recruiter_name=payload.recruiter_name,
        channel=payload.channel.value,
        save=payload.save,
        generate_draft=payload.generate_draft,
        tone=payload.tone,
        use_llm=payload.use_llm,
    )
    logger.info(
        "Analyzed opportunity '%s' -> %s (%.1f)",
        outcome["job"].title,
        outcome["scoring"].recommended_action.value,
        outcome["scoring"].overall,
    )

    draft = outcome["draft"]
    draft_response = None
    if draft is not None:
        draft_response = DraftResponse(
            **draft.to_dict(),
            message_id=outcome["message"].id if outcome["message"] else None,
            missing_information=[m.to_dict() for m in outcome["missing"]],
        )

    return AnalyzeResponse(
        opportunity=JobOpportunityRead.model_validate(outcome["job"]),
        score=OpportunityScoreRead.model_validate(outcome["score"]),
        missing_information=[m.to_dict() for m in outcome["missing"]],
        draft=draft_response,
        resume_match=outcome["resume_match"],
        prove_it=outcome["scoring"].prove_it,
        saved=payload.save,
    )


@router.post("", response_model=JobOpportunityRead, status_code=201)
def create_job(
    payload: JobCreate,
    db: Session = Depends(db_session),
    provider: LlmProvider = Depends(llm_provider),
) -> JobOpportunity:
    """Save an opportunity from raw text without scoring it."""
    from app.services.analysis import apply_extraction_to_job
    from app.services.extraction import extract

    extraction = extract(
        payload.raw_text,
        provider=provider if payload.use_llm else None,
        source_url=payload.source_url,
        known_company=payload.company,
        known_title=payload.title,
        use_llm=payload.use_llm,
    )
    job = apply_extraction_to_job(JobOpportunity(), extraction)
    if payload.recruiter_name:
        job.recruiter_name = payload.recruiter_name
    db.add(job)
    db.flush()
    db.add(
        RecruiterMessage(
            opportunity_id=job.id,
            raw_text=payload.raw_text,
            channel=payload.channel.value,
            sender=job.recruiter_name,
            extracted_missing_information=[m.to_dict() for m in detect_missing_information(job)],
            status=MessageStatus.NEW.value,
        )
    )
    db.commit()
    db.refresh(job)
    return job


@router.get("", response_model=list[JobOpportunityRead])
def list_jobs(
    db: Session = Depends(db_session),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    job_family: str | None = Query(default=None),
    company: str | None = Query(default=None),
) -> list[JobOpportunity]:
    query = db.query(JobOpportunity)
    if job_family:
        query = query.filter(JobOpportunity.job_family == job_family)
    if company:
        query = query.filter(JobOpportunity.company.ilike(f"%{company}%"))
    return query.order_by(desc(JobOpportunity.created_at)).offset(offset).limit(limit).all()


@router.get("/{job_id}")
def read_job(job_id: str, db: Session = Depends(db_session)) -> dict[str, Any]:
    """Full detail view: the job, its latest score, messages and decisions."""
    from app.db.models import UserDecision

    job = _get_job(db, job_id)
    score = _latest_score(db, job_id)
    messages = (
        db.query(RecruiterMessage)
        .filter(RecruiterMessage.opportunity_id == job_id)
        .order_by(RecruiterMessage.timestamp)
        .all()
    )
    decisions = (
        db.query(UserDecision)
        .filter(UserDecision.opportunity_id == job_id)
        .order_by(desc(UserDecision.timestamp))
        .all()
    )
    return {
        "opportunity": JobOpportunityRead.model_validate(job).model_dump(),
        "score": OpportunityScoreRead.model_validate(score).model_dump() if score else None,
        "messages": [RecruiterMessageRead.model_validate(m).model_dump() for m in messages],
        "decisions": [
            {
                "id": d.id,
                "decision": d.decision,
                "reason": d.reason,
                "edited_response": d.edited_response,
                "outcome_metadata": d.outcome_metadata,
                "timestamp": d.timestamp,
            }
            for d in decisions
        ],
        "missing_information": [m.to_dict() for m in detect_missing_information(job)],
    }


@router.patch("/{job_id}", response_model=JobOpportunityRead)
def update_job(
    job_id: str, payload: JobOpportunityUpdate, db: Session = Depends(db_session)
) -> JobOpportunity:
    """Correct extracted fields by hand.

    Manual corrections are marked HIGH confidence: a human typed them.
    """
    job = _get_job(db, job_id)
    updates = payload.model_dump(exclude_unset=True)
    confidence = dict(job.confidence or {})
    for key, value in updates.items():
        setattr(job, key, value.value if hasattr(value, "value") else value)
        confidence[key] = "high"
    job.confidence = confidence
    job.extraction_method = (
        "manual" if job.extraction_method == "manual" else f"{job.extraction_method}+manual"
    )
    db.commit()
    db.refresh(job)
    return job


@router.delete("/{job_id}", status_code=204, response_class=Response)
def delete_job(job_id: str, db: Session = Depends(db_session)) -> Response:
    job = _get_job(db, job_id)
    db.delete(job)
    db.commit()
    return Response(status_code=204)


@router.post("/{job_id}/score", response_model=OpportunityScoreRead)
def rescore_job(
    job_id: str,
    candidate_id: str | None = Query(default=None),
    db: Session = Depends(db_session),
) -> OpportunityScore:
    """Re-run scoring, e.g. after editing the profile weights or the job fields.

    Each run is stored as a new row, so score history is preserved.
    """
    job = _get_job(db, job_id)
    candidate = get_active_candidate(db, candidate_id)
    result = score_opportunity(job, candidate, config_for(candidate))
    score = persist_score(db, job, candidate, result)
    db.commit()
    db.refresh(score)
    return score


@router.post("/{job_id}/draft-response", response_model=DraftResponse)
def draft_response(
    job_id: str,
    payload: DraftRequest,
    candidate_id: str | None = Query(default=None),
    db: Session = Depends(db_session),
    provider: LlmProvider = Depends(llm_provider),
) -> DraftResponse:
    """Generate (or regenerate) a recruiter reply for human approval."""
    job = _get_job(db, job_id)
    candidate = get_active_candidate(db, candidate_id)
    result = score_opportunity(job, candidate, config_for(candidate))
    missing = detect_missing_information(job)

    draft = generate_response_draft(
        job,
        result,
        missing,
        tone=payload.tone,
        candidate_name=candidate.name,
        intent=payload.intent,
        provider=provider,
        polish=payload.polish,
    )

    message = (
        db.query(RecruiterMessage)
        .filter(RecruiterMessage.opportunity_id == job_id)
        .order_by(desc(RecruiterMessage.timestamp))
        .first()
    )
    if message is None:
        message = RecruiterMessage(
            opportunity_id=job.id,
            raw_text=job.job_description or "",
            channel="other",
            sender=job.recruiter_name,
        )
        db.add(message)
    message.response_draft = draft.body
    message.extracted_missing_information = [m.to_dict() for m in missing]
    # Regenerating supersedes an earlier draft but must not silently discard a
    # sign-off the user already gave. An edited approval counts as an approval:
    # the user rewrote the text and kept it.
    if message.status not in _SIGNED_OFF:
        message.status = MessageStatus.DRAFT_GENERATED.value
    db.commit()
    db.refresh(message)

    return DraftResponse(
        **draft.to_dict(),
        message_id=message.id,
        missing_information=[m.to_dict() for m in missing],
    )


@router.post("/{job_id}/resume-match", response_model=ResumeMatchResponse)
def resume_match(
    job_id: str,
    candidate_id: str | None = Query(default=None),
    db: Session = Depends(db_session),
) -> ResumeMatchResponse:
    """Recommend which résumé variant to send, and how to tailor it truthfully."""
    job = _get_job(db, job_id)
    candidate = get_active_candidate(db, candidate_id)
    match = build_resume_match(db, job, candidate)
    if match is None:
        return ResumeMatchResponse(best=None, ranked=[], semantic_enabled=False)
    return ResumeMatchResponse(**match)


@router.get("/{job_id}/scores", response_model=list[OpportunityScoreRead])
def score_history(job_id: str, db: Session = Depends(db_session)) -> list[OpportunityScore]:
    """Every score ever generated for this opportunity, newest first."""
    _get_job(db, job_id)
    return (
        db.query(OpportunityScore)
        .filter(OpportunityScore.opportunity_id == job_id)
        .order_by(desc(OpportunityScore.generated_at))
        .all()
    )
