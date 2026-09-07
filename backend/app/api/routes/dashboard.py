"""Dashboard and reference-data endpoints (§15)."""

from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import db_session
from app.core.enums import RecommendedAction
from app.db.models import (
    CandidateProfile,
    JobOpportunity,
    OpportunityScore,
    RecruiterMessage,
    UserDecision,
)
from app.schemas.api import (
    CandidateProfileRead,
    DashboardResponse,
    DashboardRow,
    EquityRequest,
)
from app.services.equity import calculate_equity
from app.services.job_families import FAMILY_GROUPS, FAMILY_LABELS
from app.services.skills import SKILLS

router = APIRouter(prefix="/api", tags=["dashboard"])

SORTABLE = {
    "overall": "overall_score",
    "fit": "fit_score",
    "career_capital": "career_capital_score",
    "proofability": "proofability_score",
    "compensation": "compensation_score",
    "lifestyle": "lifestyle_score",
    "upside": "upside_score",
    "risk": "risk_score",
}


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(
    db: Session = Depends(db_session),
    sort: str = Query(
        default="overall", description=f"One of: {', '.join(SORTABLE)}, salary, created"
    ),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=100, ge=1, le=500),
    action: RecommendedAction | None = Query(default=None),
    include_rejected: bool = Query(default=True),
) -> DashboardResponse:
    """Top opportunities with every score dimension, sortable.

    One row per opportunity, using its most recent score.
    """
    candidate = db.query(CandidateProfile).order_by(CandidateProfile.created_at).first()

    jobs = db.query(JobOpportunity).order_by(desc(JobOpportunity.created_at)).all()
    latest_scores = _latest_scores(db)
    latest_decisions = _latest_decisions(db)
    latest_messages = _latest_messages(db)

    rows: list[DashboardRow] = []
    for job in jobs:
        score = latest_scores.get(job.id)
        decision = latest_decisions.get(job.id)
        message = latest_messages.get(job.id)

        if action and (score is None or score.recommended_action != action.value):
            continue
        if not include_rejected and decision and decision.decision in ("reject", "ignore"):
            continue

        rows.append(
            DashboardRow(
                opportunity_id=job.id,
                company=job.company,
                title=job.title,
                location=job.location,
                remote_status=job.remote_status,
                salary_min=job.salary_min,
                salary_max=job.salary_max,
                salary_currency=job.salary_currency,
                job_family=job.job_family,
                overall_score=score.overall_score if score else 0.0,
                fit_score=score.fit_score if score else 0.0,
                career_capital_score=score.career_capital_score if score else 0.0,
                proofability_score=score.proofability_score if score else 0.0,
                compensation_score=score.compensation_score if score else 0.0,
                lifestyle_score=score.lifestyle_score if score else 0.0,
                upside_score=score.upside_score if score else 0.0,
                risk_score=score.risk_score if score else 0.0,
                recommended_action=(
                    score.recommended_action if score else RecommendedAction.MAYBE.value
                ),
                hard_gate_count=len(score.hard_gates or []) if score else 0,
                decision=decision.decision if decision else None,
                message_status=message.status if message else None,
                scored_at=score.generated_at if score else None,
                created_at=job.created_at,
            )
        )

    rows = _sort_rows(rows, sort, order)[:limit]

    return DashboardResponse(
        rows=rows,
        total=len(rows),
        candidate=CandidateProfileRead.model_validate(candidate) if candidate else None,
        stats=_stats(rows),
    )


def _latest_scores(db: Session) -> dict[str, OpportunityScore]:
    """Most recent score per opportunity.

    Done in Python rather than a window function so the same code runs on
    SQLite in tests and Postgres in production. The dataset is one person's
    inbox, not a warehouse.
    """
    out: dict[str, OpportunityScore] = {}
    for score in db.query(OpportunityScore).order_by(OpportunityScore.generated_at).all():
        out[score.opportunity_id] = score
    return out


def _latest_decisions(db: Session) -> dict[str, UserDecision]:
    out: dict[str, UserDecision] = {}
    for decision in db.query(UserDecision).order_by(UserDecision.timestamp).all():
        out[decision.opportunity_id] = decision
    return out


def _latest_messages(db: Session) -> dict[str, RecruiterMessage]:
    out: dict[str, RecruiterMessage] = {}
    for message in db.query(RecruiterMessage).order_by(RecruiterMessage.timestamp).all():
        out[message.opportunity_id] = message
    return out


def _sort_rows(rows: list[DashboardRow], sort: str, order: str) -> list[DashboardRow]:
    reverse = order == "desc"
    if sort == "salary":
        return sorted(rows, key=lambda r: (r.salary_max or r.salary_min or 0), reverse=reverse)
    if sort == "created":
        return sorted(rows, key=lambda r: r.created_at, reverse=reverse)
    attribute = SORTABLE.get(sort, "overall_score")
    return sorted(rows, key=lambda r: getattr(r, attribute), reverse=reverse)


def _stats(rows: list[DashboardRow]) -> dict[str, Any]:
    if not rows:
        return {
            "count": 0,
            "by_action": {},
            "average_overall": 0.0,
            "hard_gated": 0,
            "median_salary_max": None,
        }
    salaries = sorted(r.salary_max for r in rows if r.salary_max)
    median = salaries[len(salaries) // 2] if salaries else None
    return {
        "count": len(rows),
        "by_action": dict(Counter(r.recommended_action for r in rows)),
        "average_overall": round(sum(r.overall_score for r in rows) / len(rows), 1),
        "hard_gated": sum(1 for r in rows if r.hard_gate_count),
        "median_salary_max": median,
    }


@router.post("/equity/calculate")
def equity_calculator(payload: EquityRequest) -> dict[str, Any]:
    """§14 - dilution-adjusted equity scenarios. All values hypothetical."""
    analysis = calculate_equity(
        equity_percent=payload.equity_percent,
        dilution_percent=payload.dilution_percent,
        current_valuation=payload.current_valuation,
        strike_price=payload.strike_price,
        shares=payload.shares,
        exit_valuations=payload.exit_valuations,
    )
    return analysis.to_dict()


@router.get("/reference/job-families")
def job_families() -> dict[str, Any]:
    """The job-family taxonomy, grouped as the UI displays it."""
    return {
        "groups": {
            group: [{"value": f.value, "label": FAMILY_LABELS[f]} for f in families]
            for group, families in FAMILY_GROUPS.items()
        }
    }


@router.get("/reference/skills")
def skill_ontology() -> dict[str, Any]:
    """The normalised skill taxonomy with proofability metadata."""
    by_category: dict[str, list[dict[str, Any]]] = {}
    for skill in SKILLS:
        by_category.setdefault(skill.category, []).append(
            {
                "slug": skill.slug,
                "label": skill.label,
                "proofability": skill.proofability,
                "career_capital": skill.career_capital,
                "learning_difficulty": skill.learning_difficulty,
                "aliases": list(skill.aliases),
                "suggested_project": skill.proof_project,
            }
        )
    return {"categories": by_category, "total": len(SKILLS)}
