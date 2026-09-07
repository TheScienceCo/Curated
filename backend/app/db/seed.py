"""Load the demo dataset.

The sample data is fictional. Real recruiter messages and personal contact
details are deliberately kept out of the repository (§21).
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import CandidateProfile, JobOpportunity, ResumeDocument
from app.db.session import session_scope
from app.llm.factory import get_provider
from app.services.analysis import analyze_text
from app.services.skills import extract_skills_from_text

logger = get_logger(__name__)

#: data/samples lives at the repo root, two levels above `backend/`.
DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "samples"


def _load(name: str) -> object:
    path = DATA_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Sample data not found at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def seed_candidate(db: Session) -> CandidateProfile:
    payload = _load("candidate_profile.json")
    assert isinstance(payload, dict)
    profile = CandidateProfile(**payload)
    db.add(profile)
    db.flush()
    logger.info("Seeded candidate profile: %s", profile.name)
    return profile


def seed_resumes(db: Session, candidate: CandidateProfile) -> list[ResumeDocument]:
    payload = _load("resumes.json")
    assert isinstance(payload, list)
    resumes = []
    for item in payload:
        resume = ResumeDocument(
            candidate_id=candidate.id,
            title=item["title"],
            raw_text=item["raw_text"],
            parsed_sections={},
            target_families=item.get("target_families", []),
            active=item.get("active", True),
            skills=extract_skills_from_text(item["raw_text"]),
        )
        db.add(resume)
        resumes.append(resume)
    db.flush()
    logger.info("Seeded %d résumé variants", len(resumes))
    return resumes


def seed_opportunities(db: Session, candidate: CandidateProfile) -> int:
    """Run each sample message through the real analysis pipeline.

    Seeding via the same code path the API uses means the demo data can never
    drift from what the application actually produces.
    """
    payload = _load("recruiter_messages.json")
    assert isinstance(payload, list)
    provider = get_provider()
    count = 0
    for item in payload:
        try:
            analyze_text(
                db,
                raw_text=item["raw_text"],
                candidate=candidate,
                provider=provider,
                channel=item.get("channel", "other"),
                save=True,
                generate_draft=True,
                # Seeding stays deterministic so the demo dataset is identical
                # for every user, with or without an API key.
                use_llm=False,
            )
            count += 1
        except Exception as exc:  # noqa: BLE001 - one bad sample must not stop the rest
            logger.warning("Failed to seed sample %s: %s", item.get("id"), exc)
    logger.info("Seeded %d sample opportunities", count)
    return count


def seed_all(db: Session) -> None:
    candidate = seed_candidate(db)
    seed_resumes(db, candidate)
    db.commit()
    seed_opportunities(db, candidate)


def seed_if_empty() -> bool:
    """Seed only when the database has no profile yet. Returns True if seeded."""
    with session_scope() as db:
        if db.query(CandidateProfile).first() is not None:
            logger.debug("Database already has a candidate profile; skipping seed.")
            return False
        seed_all(db)
        return True


def reset_and_seed() -> None:
    """Drop every row and reseed. Destructive - used by `make seed`."""
    from app.db.models import OpportunityScore, RecruiterMessage, UserDecision

    with session_scope() as db:
        for model in (
            UserDecision,
            OpportunityScore,
            RecruiterMessage,
            JobOpportunity,
            ResumeDocument,
            CandidateProfile,
        ):
            db.query(model).delete()
        db.commit()
    with session_scope() as db:
        seed_all(db)
    logger.info("Database reset and reseeded.")


if __name__ == "__main__":  # pragma: no cover - operational entrypoint
    from app.core.config import settings
    from app.core.logging import configure_logging
    from app.db.session import create_all, init_engine

    configure_logging(settings.log_level)
    init_engine()
    create_all()
    reset_and_seed()
