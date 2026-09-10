"""Bulk import of raw job text (recruiting ads, email, etc.)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.base import new_id
from app.db.models import CandidateProfile, JobOpportunity, OpportunityScore
from app.services.analysis import apply_extraction_to_job
from app.services.extraction import extract
from app.services.scoring import score_opportunity

logger = get_logger(__name__)


def import_raw_jobs(
    db: Session, candidate_id: str, raw_texts: list[str]
) -> dict:
    """Import raw job text(s) and score them.

    Each item in raw_texts is processed as a separate job opportunity.

    Args:
        db: SQLAlchemy session
        candidate_id: Candidate profile ID
        raw_texts: List of raw job descriptions (email, job posting, etc.)

    Returns:
        Stats dict with saved, below_threshold, duplicates_skipped counts
    """
    candidate = db.get(CandidateProfile, candidate_id)
    if not candidate:
        raise ValueError(f"Candidate {candidate_id} not found")

    saved_jobs = []
    duplicates_skipped = 0
    below_threshold_count = 0
    failed_count = 0

    for i, raw_text in enumerate(raw_texts):
        if not raw_text or not raw_text.strip():
            continue

        try:
            # Extract structured data
            extraction = extract(raw_text)

            # Create ORM object
            job = JobOpportunity()
            apply_extraction_to_job(job, extraction)
            job.source_type = "manual_paste"
            job.job_description = raw_text[:5000]  # Store first 5k chars

            # Check for duplicates
            existing = (
                db.query(JobOpportunity)
                .filter(
                    JobOpportunity.company == job.company,
                    JobOpportunity.title == job.title,
                    JobOpportunity.location == job.location,
                )
                .first()
            )
            if existing:
                logger.info(f"Skipping duplicate: {job.company} - {job.title}")
                duplicates_skipped += 1
                continue

            # Score the job
            scoring_config = {
                key: value
                for key, value in candidate.scoring_config.items()
                if isinstance(value, int | float)
            }
            score_result = score_opportunity(job, candidate, scoring_config)

            # Save if above threshold
            if score_result.overall >= 40:
                if not job.id:
                    job.id = new_id()

                db.add(job)
                db.flush()

                score_record = OpportunityScore(
                    opportunity_id=job.id,
                    candidate_id=candidate_id,
                    fit_score=score_result.fit,
                    career_capital_score=score_result.career_capital,
                    proofability_score=score_result.proofability,
                    compensation_score=score_result.compensation,
                    lifestyle_score=score_result.lifestyle,
                    upside_score=score_result.upside,
                    risk_score=score_result.risk,
                    overall_score=score_result.overall,
                    recommended_action=score_result.recommended_action.value,
                    explanation=score_result.explanation,
                    missing_requirements=score_result.missing_requirements,
                    matched_strengths=score_result.matched_strengths,
                    hard_gates=score_result.hard_gates,
                    proofable_gaps=score_result.proofable_gaps,
                    weights_used=score_result.weights_used,
                )
                db.add(score_record)
                saved_jobs.append(job)
                logger.info(f"Saved: {job.company} - {job.title} ({score_result.overall:.1f})")
            else:
                below_threshold_count += 1
                logger.info(
                    f"Below threshold: {job.company} - {job.title} "
                    f"({score_result.overall:.1f})"
                )

        except Exception as e:
            logger.warning(f"Failed to process job {i + 1}: {e}")
            failed_count += 1
            continue

    db.commit()

    return {
        "total_processed": len(raw_texts),
        "saved": len(saved_jobs),
        "below_threshold": below_threshold_count,
        "duplicates_skipped": duplicates_skipped,
        "failed": failed_count,
    }


__all__ = ["import_raw_jobs"]
