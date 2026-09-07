"""The demo dataset must load and produce a meaningful spread of outcomes.

The sample data doubles as documentation, so it is worth asserting that it
still demonstrates what the README claims it demonstrates.
"""

from __future__ import annotations

import json

import pytest

from app.db.models import CandidateProfile, JobOpportunity, OpportunityScore
from app.db.seed import DATA_DIR, seed_all


@pytest.fixture
def seeded(db):
    seed_all(db)
    db.commit()
    return db


def test_sample_files_exist():
    for name in ("candidate_profile.json", "resumes.json", "recruiter_messages.json"):
        assert (DATA_DIR / name).exists(), f"missing sample file {name}"


def test_samples_contain_no_real_contact_details():
    """§21 - the public demo dataset is fictional by construction."""
    messages = json.loads((DATA_DIR / "recruiter_messages.json").read_text())
    for message in messages:
        for line in message["raw_text"].splitlines():
            if "@" in line:
                assert ".example" in line, f"non-example email address in sample: {line}"


def test_seeding_creates_the_full_demo(seeded):
    assert seeded.query(CandidateProfile).count() == 1
    assert seeded.query(JobOpportunity).count() >= 6
    assert seeded.query(OpportunityScore).count() == seeded.query(JobOpportunity).count()


def test_seeded_candidate_holds_ci_not_full_scope(seeded):
    candidate = seeded.query(CandidateProfile).one()
    assert candidate.clearance_level == "ts_sci"
    assert candidate.polygraph_type == "ci"


def test_demo_covers_the_full_action_ladder(seeded):
    actions = {score.recommended_action for score in seeded.query(OpportunityScore).all()}
    assert "STRONGLY_PURSUE" in actions
    assert "REJECT" in actions or "LOW_PRIORITY" in actions
    assert len(actions) >= 4, "the demo should show a spread, not one verdict"


def test_the_fsp_sample_is_gated_despite_strong_pay(seeded):
    job = (
        seeded.query(JobOpportunity)
        .filter(JobOpportunity.polygraph_requirement == "full_scope")
        .one()
    )
    score = seeded.query(OpportunityScore).filter(OpportunityScore.opportunity_id == job.id).one()
    assert job.salary_max and job.salary_max > 250_000
    assert score.hard_gates, "a full scope requirement must register as a hard gate"
    assert score.recommended_action in ("LOW_PRIORITY", "REJECT")


def test_the_vague_sample_produces_a_question_asking_draft(seeded):
    from app.db.models import RecruiterMessage

    vague = (
        seeded.query(JobOpportunity)
        .filter(JobOpportunity.salary_min.is_(None), JobOpportunity.title.is_(None))
        .first()
    )
    assert vague is not None
    message = (
        seeded.query(RecruiterMessage).filter(RecruiterMessage.opportunity_id == vague.id).one()
    )
    assert message.response_draft
    assert "salary range" in message.response_draft.lower()
    assert len(message.extracted_missing_information) >= 5


def test_seeding_is_idempotent_via_seed_if_empty(db):
    from app.db.seed import seed_if_empty

    assert seed_if_empty() is True
    assert seed_if_empty() is False
    assert db.query(CandidateProfile).count() == 1
