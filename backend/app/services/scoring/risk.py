"""G. Risk Score. Higher = riskier.

Shown separately from the overall score by default (§6H). It is a warning
label, not a penalty, unless the user opts into `risk_penalty_weight`.
"""

from __future__ import annotations

from app.core.enums import CompanyStage, ProofabilityTier, RemoteStatus
from app.services.scoring.base import DimensionScore, Gap, Reason, clamp
from app.services.scoring.config import ScoringConfig

BASE_RISK = 20.0

STAGE_RISK: dict[str, float] = {
    CompanyStage.PRE_SEED.value: 35.0,
    CompanyStage.SEED.value: 28.0,
    CompanyStage.SERIES_A.value: 20.0,
    CompanyStage.SERIES_B.value: 12.0,
    CompanyStage.SERIES_C.value: 8.0,
    CompanyStage.GROWTH.value: 6.0,
    CompanyStage.LATE_STAGE.value: 5.0,
    CompanyStage.PUBLIC.value: 2.0,
    CompanyStage.ESTABLISHED_PRIVATE.value: 4.0,
    CompanyStage.GOVERNMENT.value: 3.0,
    CompanyStage.NONPROFIT.value: 6.0,
}

_RISK_TOLERANCE_ADJUST = {"low": 8.0, "medium": 0.0, "high": -8.0}


def score_risk(job, candidate, gaps: list[Gap], config: ScoringConfig) -> DimensionScore:
    reasons: list[Reason] = []
    risk = BASE_RISK

    stage = job.company_stage or ""
    stage_risk = STAGE_RISK.get(stage, 10.0)
    risk += stage_risk
    if stage_risk >= 20:
        reasons.append(
            Reason(
                f"Early stage ({stage.replace('_', ' ')}) - meaningful probability the company "
                "does not survive 24 months.",
                impact=stage_risk,
                kind="negative",
            )
        )
    elif stage:
        reasons.append(
            Reason(
                f"Company stage ({stage.replace('_', ' ')}) implies moderate stability.",
                impact=stage_risk,
                kind="neutral",
            )
        )
    else:
        reasons.append(
            Reason(
                "Company stage unknown - stability cannot be assessed.",
                impact=stage_risk,
                kind="missing",
            )
        )

    # --- compensation uncertainty -----------------------------------------
    if job.salary_min is None and job.salary_max is None:
        risk += 15
        reasons.append(
            Reason(
                "No compensation disclosed - you cannot evaluate the offer until they share it.",
                impact=15,
                kind="negative",
            )
        )
    if job.equity and not job.equity_percent_min:
        risk += 6
        reasons.append(
            Reason(
                "Equity is unquantified, so its value is unknowable today.",
                impact=6,
                kind="negative",
            )
        )
    if job.commission_ote and not job.salary_min:
        risk += 8
        reasons.append(
            Reason(
                "OTE quoted without a base - the guaranteed portion is unclear.",
                impact=8,
                kind="negative",
            )
        )

    # --- clearance dependence ---------------------------------------------
    from app.core.enums import ClearanceLevel, PolygraphType

    if job.security_clearance not in (
        None,
        ClearanceLevel.NONE.value,
        ClearanceLevel.UNSPECIFIED.value,
    ):
        risk += 8
        reasons.append(
            Reason(
                "Clearance-dependent role: the job disappears if the clearance lapses, and it "
                "narrows your options to cleared employers.",
                impact=8,
                kind="negative",
            )
        )
    if job.polygraph_requirement == PolygraphType.UNSPECIFIED_POLYGRAPH.value:
        risk += 10
        reasons.append(
            Reason(
                "Polygraph required but the scope is unstated - a CI and a Full Scope are very "
                "different commitments and timelines.",
                impact=10,
                kind="negative",
            )
        )

    # --- relocation and location -------------------------------------------
    if job.relocation_required:
        risk += 12
        reasons.append(
            Reason(
                "Relocation required - high personal switching cost if it goes badly.",
                impact=12,
                kind="negative",
            )
        )
    elif job.remote_status == RemoteStatus.ONSITE.value and job.location:
        preferred = {str(p).lower() for p in (candidate.preferred_locations or [])}
        if not any(p in job.location.lower() for p in preferred):
            risk += 8
            reasons.append(
                Reason(
                    f"Onsite in {job.location}, away from your preferred locations.",
                    impact=8,
                    kind="negative",
                )
            )

    # --- role clarity -------------------------------------------------------
    if not job.required_skills:
        risk += 8
        reasons.append(
            Reason(
                "No concrete requirements stated - the role may not be well defined.",
                impact=8,
                kind="negative",
            )
        )
    if job.ownership_level == "high" and not job.title:
        risk += 4
        reasons.append(
            Reason(
                "High ambiguity with an unclear title - scope creep is likely.",
                impact=4,
                kind="neutral",
            )
        )

    # --- eligibility risk ---------------------------------------------------
    hard_gates = [g for g in gaps if g.tier is ProofabilityTier.HARD_GATE]
    if hard_gates:
        risk += 10
        reasons.append(
            Reason(
                f"{len(hard_gates)} hard gate(s) - real chance of investing interview time and "
                "being disqualified on eligibility.",
                impact=10,
                kind="negative",
            )
        )

    # --- candidate tolerance -------------------------------------------------
    adjust = _RISK_TOLERANCE_ADJUST.get((candidate.risk_tolerance or "medium").lower(), 0.0)
    if adjust:
        risk += adjust
        reasons.append(
            Reason(
                f"Adjusted for your stated {candidate.risk_tolerance} risk tolerance.",
                impact=adjust,
                kind="neutral",
            )
        )

    return DimensionScore(
        name="Risk",
        score=clamp(risk),
        reasons=reasons,
        details={"stage_risk": stage_risk, "hard_gates": len(hard_gates)},
    )


__all__ = ["score_risk", "STAGE_RISK"]
