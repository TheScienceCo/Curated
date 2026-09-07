"""H. Overall score, recommended action, and the full scoring run.

The overall score is a *weighted* combination, not an average (§6H), and the
weights are configurable per candidate. Risk is reported separately and only
subtracts if the user opts in.

A hard gate caps the overall score, because "great job you are not eligible
for" should never sit at the top of the dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.enums import RecommendedAction
from app.core.logging import get_logger
from app.services.scoring.base import DimensionScore, Gap
from app.services.scoring.career_capital import score_career_capital
from app.services.scoring.compensation import score_compensation
from app.services.scoring.config import ScoringConfig
from app.services.scoring.fit import score_fit
from app.services.scoring.lifestyle import score_lifestyle
from app.services.scoring.proofability import build_prove_it_analysis, score_proofability
from app.services.scoring.risk import score_risk
from app.services.scoring.upside import score_upside

logger = get_logger(__name__)


@dataclass
class ScoringResult:
    fit: DimensionScore
    career_capital: DimensionScore
    proofability: DimensionScore
    compensation: DimensionScore
    lifestyle: DimensionScore
    upside: DimensionScore
    risk: DimensionScore
    overall: float
    recommended_action: RecommendedAction
    matched_strengths: list[str]
    missing_requirements: list[str]
    hard_gates: list[Gap]
    proofable_gaps: list[Gap]
    prove_it: dict[str, Any]
    weights_used: dict[str, float]
    headline_reasons: list[str] = field(default_factory=list)
    overall_capped: bool = False

    def dimensions(self) -> dict[str, DimensionScore]:
        return {
            "fit": self.fit,
            "career_capital": self.career_capital,
            "proofability": self.proofability,
            "compensation": self.compensation,
            "lifestyle": self.lifestyle,
            "upside": self.upside,
            "risk": self.risk,
        }

    def explanation(self) -> dict[str, Any]:
        """The transparent "why" payload stored on OpportunityScore."""
        return {
            "headline": self.headline_reasons,
            "dimensions": {name: dim.to_dict() for name, dim in self.dimensions().items()},
            "weights": self.weights_used,
            "overall_capped_by_hard_gate": self.overall_capped,
            "prove_it": self.prove_it,
        }


def recommend_action(
    overall: float, hard_gates: list[Gap], config: ScoringConfig
) -> RecommendedAction:
    """Map an overall score onto the six-level action ladder (§7)."""
    thresholds = config.thresholds
    if hard_gates:
        # An unwaivable gate means the honest answer is "not without a change
        # on their side", however attractive the rest of the job is.
        return (
            RecommendedAction.LOW_PRIORITY
            if overall >= thresholds.low_priority
            else RecommendedAction.REJECT
        )
    if overall >= thresholds.strongly_pursue:
        return RecommendedAction.STRONGLY_PURSUE
    if overall >= thresholds.pursue:
        return RecommendedAction.PURSUE
    if overall >= thresholds.worth_a_call:
        return RecommendedAction.WORTH_A_CALL
    if overall >= thresholds.maybe:
        return RecommendedAction.MAYBE
    if overall >= thresholds.low_priority:
        return RecommendedAction.LOW_PRIORITY
    return RecommendedAction.REJECT


def score_opportunity(job, candidate, config: ScoringConfig | None = None) -> ScoringResult:
    """Run every dimension and combine them. Pure function - no I/O."""
    config = config or ScoringConfig()

    fit, gaps = score_fit(job, candidate, config)
    proofability, hard_gates, proofable_gaps = score_proofability(gaps, job, candidate, config)
    career_capital = score_career_capital(job, candidate, config)
    compensation = score_compensation(job, candidate, config)
    lifestyle = score_lifestyle(job, candidate, config)
    upside = score_upside(job, candidate, config)
    risk = score_risk(job, candidate, gaps, config)

    weights = config.weights.normalized()
    overall = (
        weights["fit"] * fit.score
        + weights["career_capital"] * career_capital.score
        + weights["proofability"] * proofability.score
        + weights["compensation"] * compensation.score
        + weights["lifestyle"] * lifestyle.score
        + weights["upside"] * upside.score
    )

    if config.risk_penalty_weight:
        overall -= config.risk_penalty_weight * risk.score

    capped = False
    if hard_gates and overall > config.hard_gate_overall_cap:
        logger.debug(
            "Capping overall score %.1f -> %.1f due to %d hard gate(s)",
            overall,
            config.hard_gate_overall_cap,
            len(hard_gates),
        )
        overall = config.hard_gate_overall_cap
        capped = True

    overall = max(0.0, min(100.0, overall))
    action = recommend_action(overall, hard_gates, config)

    matched_strengths = _collect_strengths(fit, career_capital, compensation, upside)
    missing_requirements = [g.requirement for g in gaps]
    prove_it = build_prove_it_analysis(job, candidate, gaps)

    return ScoringResult(
        fit=fit,
        career_capital=career_capital,
        proofability=proofability,
        compensation=compensation,
        lifestyle=lifestyle,
        upside=upside,
        risk=risk,
        overall=round(overall, 1),
        recommended_action=action,
        matched_strengths=matched_strengths,
        missing_requirements=missing_requirements,
        hard_gates=hard_gates,
        proofable_gaps=proofable_gaps,
        prove_it=prove_it,
        weights_used=weights,
        headline_reasons=_headline(
            fit,
            career_capital,
            proofability,
            compensation,
            upside,
            risk,
            hard_gates,
            proofable_gaps,
        ),
        overall_capped=capped,
    )


def _collect_strengths(*dimensions: DimensionScore) -> list[str]:
    """The positive reasons, strongest first, de-duplicated."""
    positives = [
        reason for dim in dimensions for reason in dim.reasons if reason.kind == "positive"
    ]
    positives.sort(key=lambda r: -r.impact)
    seen: set[str] = set()
    out: list[str] = []
    for reason in positives:
        if reason.text not in seen:
            seen.add(reason.text)
            out.append(reason.text)
    return out[:8]


def _headline(
    fit: DimensionScore,
    career_capital: DimensionScore,
    proofability: DimensionScore,
    compensation: DimensionScore,
    upside: DimensionScore,
    risk: DimensionScore,
    hard_gates: list[Gap],
    proofable_gaps: list[Gap],
) -> list[str]:
    """The 4-6 bullets shown next to the recommended action."""
    bullets: list[str] = []

    if compensation.details.get("specified"):
        low = compensation.details.get("salary_min")
        high = compensation.details.get("salary_max")
        if low and high:
            bullets.append(f"${low:,}-${high:,} compensation")
        elif high or low:
            bullets.append(f"${(high or low):,} compensation")
    else:
        bullets.append("Compensation not disclosed - ask before investing time")

    if career_capital.score >= 75:
        bullets.append(f"Strong career capital ({career_capital.score:.0f}/100)")
    elif career_capital.score <= 40:
        bullets.append(f"Weak career capital ({career_capital.score:.0f}/100)")

    top_positive = next(
        (
            r
            for r in sorted(career_capital.reasons, key=lambda r: -r.impact)
            if r.kind == "positive"
        ),
        None,
    )
    if top_positive:
        bullets.append(top_positive.text)

    if hard_gates:
        bullets.append(
            "Hard gate: " + "; ".join(g.requirement for g in hard_gates[:2]) + " - low proofability"
        )
    elif proofable_gaps:
        names = ", ".join(g.requirement for g in proofable_gaps[:3])
        bullets.append(f"Gaps in {names}, but high proofability ({proofability.score:.0f}/100)")
    else:
        bullets.append("No unmet requirements identified")

    if upside.score >= 70:
        bullets.append(f"Strong long-term upside ({upside.score:.0f}/100)")
    if risk.score >= 60:
        bullets.append(f"Elevated risk ({risk.score:.0f}/100) - see the risk breakdown")

    return bullets[:6]


__all__ = ["score_opportunity", "ScoringResult", "recommend_action"]
