"""Shared fixtures.

Every test runs against an in-memory SQLite database with the real schema, so
the ORM, the services and the API are all exercised for real without needing
Postgres in CI.
"""

from __future__ import annotations

import os

# Configure the environment before anything imports app.core.config, whose
# settings object is built once at import time.
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SEED_ON_STARTUP", "false")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("EMBEDDINGS_ENABLED", "false")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.models import CandidateProfile, JobOpportunity, ResumeDocument  # noqa: E402
from app.db.session import create_all, get_session_factory, init_engine  # noqa: E402


@pytest.fixture(scope="function")
def db() -> Session:
    init_engine("sqlite://")
    create_all()
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def candidate(db: Session) -> CandidateProfile:
    """The reference candidate: TS/SCI with a CI poly, NOT a full scope."""
    profile = CandidateProfile(
        name="Test Candidate",
        summary="AI/ML and intelligence generalist.",
        current_location="Washington, DC",
        citizenship="US citizen",
        work_authorization="US citizen",
        clearance_level="ts_sci",
        polygraph_type="ci",
        languages=["English", "Mandarin"],
        education=["BS, Biochemistry"],
        certifications=["Security+"],
        technical_skills=[
            "Python",
            "SQL",
            "FastAPI",
            "APIs",
            "Docker",
            "Git",
            "LLMs",
            "RAG",
            "embeddings",
            "agents",
            "tool calling",
        ],
        domain_skills=["HUMINT", "OSINT", "all-source intelligence", "customer-facing"],
        years_experience_by_skill={
            "python": 6,
            "llms": 3,
            "rag": 2,
            "customer_facing": 8,
            "humint": 8,
        },
        proofable_skills=["react", "typescript", "nextjs", "cpp"],
        target_roles=["forward_deployed_engineer", "ai_engineer", "ml_engineer"],
        preferred_locations=["Washington, DC", "Remote"],
        remote_preference="hybrid_ok",
        willingness_to_travel=30,
        minimum_salary=170_000,
        target_salary=220_000,
        preferred_weekly_hours=45,
        lifestyle_preferences={},
        industries_of_interest=["national security", "ai"],
        industries_to_avoid=["gambling"],
        career_goals=["forward deployed engineer", "agentic AI"],
        risk_tolerance="high",
        scoring_config={},
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@pytest.fixture
def resumes(db: Session, candidate: CandidateProfile) -> list[ResumeDocument]:
    from app.services.skills import extract_skills_from_text

    definitions = [
        (
            "Forward Deployed AI Resume",
            ["forward_deployed_engineer", "ai_engineer"],
            "TS/SCI with CI poly. Built agentic AI with RAG, FastAPI, Python and "
            "embeddings. Customer-facing delivery with government customers. HUMINT.",
        ),
        (
            "Intelligence / Science Resume",
            ["technical_intelligence_analyst"],
            "All-source intelligence, HUMINT, OSINT, targeting. Biochemistry, stem "
            "cells, LC-MS wet lab. Mandarin.",
        ),
    ]
    created = []
    for title, families, text in definitions:
        resume = ResumeDocument(
            candidate_id=candidate.id,
            title=title,
            raw_text=text,
            parsed_sections={},
            target_families=families,
            skills=extract_skills_from_text(text),
            active=True,
        )
        db.add(resume)
        created.append(resume)
    db.commit()
    return created


@pytest.fixture
def client(db: Session) -> TestClient:
    """API client bound to the same in-memory database as `db`.

    The dependency override is what keeps the session shared - without it the
    app would open a second connection to a different in-memory database.
    """
    from app.api.deps import db_session
    from app.main import app

    def override():
        yield db

    app.dependency_overrides[db_session] = override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def fde_text() -> str:
    """The MVP acceptance-test input from the product spec (§19)."""
    return (
        "Hi Eric, I'm recruiting for a Forward Deployed Engineer supporting national "
        "security customers. The role requires TS/SCI and experience with Python, "
        "React, TypeScript, LLMs, and customer-facing technical delivery. Salary is "
        "$190k-$240k plus equity. Position is onsite in San Francisco with "
        "approximately 20% travel. We're looking for 3-5 years full-stack "
        "engineering experience."
    )


def make_job(**overrides) -> JobOpportunity:
    """Build an in-memory JobOpportunity with sane defaults.

    ORM column defaults only apply on flush, so the defaults are spelled out
    here to keep pure-function scoring tests independent of the database.
    """
    defaults = {
        "company": "Test Co",
        "title": "Forward Deployed Engineer",
        "location": "San Francisco",
        "remote_status": "onsite",
        "employment_type": "full_time",
        "salary_min": 190_000,
        "salary_max": 240_000,
        "salary_currency": "USD",
        "equity": True,
        "security_clearance": "ts_sci",
        "polygraph_requirement": "unknown",
        "required_skills": ["python", "react", "typescript", "llms", "customer_facing"],
        "preferred_skills": [],
        "required_years_experience": 3.0,
        "education_requirements": [],
        "certifications": [],
        "travel": 20,
        "job_family": "forward_deployed_engineer",
        "customer_facing_intensity": "high",
        "technical_depth": "high",
        "confidence": {},
    }
    defaults.update(overrides)
    return JobOpportunity(**defaults)
