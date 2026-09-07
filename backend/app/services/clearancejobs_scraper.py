"""ClearanceJobs.com scraper integration via Apify actor."""

from __future__ import annotations

import time

import httpx
from sqlalchemy.orm import Session

from app.core.errors import ExternalServiceError
from app.core.logging import get_logger
from app.db.base import new_id
from app.db.models import CandidateProfile, JobOpportunity, OpportunityScore
from app.services.analysis import apply_extraction_to_job
from app.services.extraction import extract

logger = get_logger(__name__)


def generate_keywords(candidate: CandidateProfile) -> str:
    """Generate search keywords from target roles and technical skills.

    Returns keyword string ready to pass to Apify actor.
    """
    keywords = []
    # Add top 3 target roles
    if candidate.target_roles:
        keywords.extend(candidate.target_roles[:3])
    # Add top 2 technical skills
    if candidate.technical_skills:
        keywords.extend(candidate.technical_skills[:2])

    return " OR ".join(keywords) if keywords else ""


class ApifyClient:
    """Client for Apify actor API."""

    def __init__(self, api_token: str):
        self.api_token = api_token
        self.base_url = "https://api.apify.com/v2"

    def run_actor(
        self, actor_id: str, input_data: dict, timeout: int = 3600
    ) -> dict:
        """Run an Apify actor and wait for completion.

        Args:
            actor_id: Apify actor ID (e.g., "parseforge/clearancejobs-scraper")
            input_data: Input configuration for the actor
            timeout: Maximum time to wait for completion (seconds)

        Returns:
            Actor run data from the API response
        """
        # Start the actor run
        headers = {"Authorization": f"Bearer {self.api_token}"}
        start_url = f"{self.base_url}/acts/{actor_id}/runs"
        start_payload = {"input": input_data}

        with httpx.Client(timeout=60.0) as client:
            response = client.post(start_url, json=start_payload, headers=headers)
            response.raise_for_status()
            run_data = response.json()["data"]
            run_id = run_data["id"]
            logger.info(f"Started Apify actor run {run_id}")

        # Poll for completion
        status_url = f"{self.base_url}/acts/{actor_id}/runs/{run_id}"
        start_time = time.time()

        while time.time() - start_time < timeout:
            with httpx.Client(timeout=60.0) as client:
                response = client.get(status_url, headers=headers)
                response.raise_for_status()
                run_data = response.json()["data"]

            status = run_data.get("status")
            logger.info(f"Apify run {run_id} status: {status}")

            if status == "SUCCEEDED":
                logger.info(f"Apify actor run {run_id} completed successfully")
                return run_data
            elif status in ("FAILED", "ABORTED"):
                raise ExternalServiceError(
                    f"Apify actor run {run_id} failed with status {status}"
                )

            time.sleep(10)  # Poll every 10 seconds

        raise ExternalServiceError(
            f"Apify actor run {run_id} timed out after {timeout} seconds"
        )

    def get_results(self, actor_id: str, run_id: str) -> list[dict]:
        """Fetch results from a completed actor run.

        Args:
            actor_id: Apify actor ID
            run_id: Run ID from run_actor

        Returns:
            List of result items from the actor
        """
        headers = {"Authorization": f"Bearer {self.api_token}"}
        results_url = f"{self.base_url}/acts/{actor_id}/runs/{run_id}/dataset/items"

        with httpx.Client(timeout=60.0) as client:
            response = client.get(results_url, headers=headers)
            response.raise_for_status()
            return response.json()


def scrape_clearancejobs(
    db: Session, candidate_id: str, keywords: str, api_token: str
) -> tuple[list[JobOpportunity], list[dict]]:
    """Scrape ClearanceJobs.com and save matched opportunities.

    Args:
        db: SQLAlchemy session
        candidate_id: Candidate profile ID
        keywords: Search keywords (e.g., "Security Engineer OR Python")
        api_token: Apify API token

    Returns:
        Tuple of (saved_jobs, stats) where stats contains import metadata
    """
    candidate = db.get(CandidateProfile, candidate_id)
    if not candidate:
        raise ValueError(f"Candidate {candidate_id} not found")

    # Configure Apify actor input
    actor_input = {
        "searchTerm": keywords,
        "maxResults": 50,
        "clearanceType": "TS/SCI",  # Filter for TS/SCI clearance
    }

    # Run scraper
    client = ApifyClient(api_token)
    run_data = client.run_actor(
        "parseforge/clearancejobs-scraper", actor_input, timeout=120
    )
    run_id = run_data["id"]

    # Get results
    raw_results = client.get_results("parseforge/clearancejobs-scraper", run_id)
    logger.info(f"Retrieved {len(raw_results)} results from ClearanceJobs")

    # Transform to JobOpportunity records
    saved_jobs = []
    duplicates_skipped = 0
    below_threshold_count = 0

    for raw_job in raw_results:
        try:
            # Map Apify result to job description text
            job_text = _format_job_for_extraction(raw_job)

            # Extract structured data
            extraction = extract(job_text)

            # Create and populate ORM object
            job = JobOpportunity()
            apply_extraction_to_job(job, extraction)
            job.source_type = "clearancejobs_scraper"
            job.source_url = raw_job.get("url", "")

            # Check for duplicates (company + title + location)
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
            from app.services.scoring import score_opportunity

            scoring_config = {
                key: value
                for key, value in candidate.scoring_config.items()
                if isinstance(value, int | float)
            }
            score_result = score_opportunity(job, candidate, scoring_config)

            # Only save if above threshold (>40)
            if score_result.overall >= 40:
                # Ensure job has an ID before saving
                if not job.id:
                    job.id = new_id()

                db.add(job)
                db.flush()  # Flush to ensure ID is assigned

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
                msg = f"Saved job: {job.company} - {job.title} (score: {score_result.overall:.1f})"
                logger.info(msg)
            else:
                below_threshold_count += 1
                logger.info(
                    f"Skipped below threshold: {job.company} - {job.title} "
                    f"(score: {score_result.overall:.1f})"
                )

        except Exception as e:
            logger.warning(f"Failed to process job from ClearanceJobs: {e}")
            continue

    db.commit()

    stats = {
        "total_results": len(raw_results),
        "saved": len(saved_jobs),
        "below_threshold": below_threshold_count,
        "duplicates_skipped": duplicates_skipped,
    }

    return saved_jobs, stats


def _format_job_for_extraction(raw_job: dict) -> str:
    """Format Apify job result as text for extraction pipeline."""
    parts = []

    if title := raw_job.get("title"):
        parts.append(f"Title: {title}")

    if company := raw_job.get("company"):
        parts.append(f"Company: {company}")

    if location := raw_job.get("location"):
        parts.append(f"Location: {location}")

    if description := raw_job.get("description"):
        parts.append(f"\n{description}")

    if salary := raw_job.get("salary"):
        parts.append(f"\nSalary: {salary}")

    if remote := raw_job.get("remote"):
        parts.append(f"Remote: {remote}")

    if clearance := raw_job.get("clearance"):
        parts.append(f"Clearance: {clearance}")

    return "\n".join(parts)


__all__ = ["generate_keywords", "scrape_clearancejobs", "ApifyClient"]
