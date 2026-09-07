"""F. Upside Score - credible paths to $300k / $500k / $1M+.

Distinct from Compensation: a $150k seed-stage founding-engineer role with
1.5% equity has a weak compensation score and a strong upside score, and the
product should say both rather than averaging them into mush.
"""

from __future__ import annotations

from app.core.enums import CompanyStage, JobFamily
from app.services.scoring.base import DimensionScore, Reason, clamp
from app.services.scoring.config import ScoringConfig

#: Equity upside is dominated by stage: 0.5% of a seed company and 0.5% of a
#: late-stage company are wildly different bets.
STAGE_EQUITY_MULTIPLIER: dict[str, float] = {
    CompanyStage.PRE_SEED.value: 30.0,
    CompanyStage.SEED.value: 26.0,
    CompanyStage.SERIES_A.value: 20.0,
    CompanyStage.SERIES_B.value: 14.0,
    CompanyStage.SERIES_C.value: 10.0,
    CompanyStage.GROWTH.value: 8.0,
    CompanyStage.LATE_STAGE.value: 6.0,
    CompanyStage.PUBLIC.value: 4.0,
    CompanyStage.ESTABLISHED_PRIVATE.value: 3.0,
    CompanyStage.GOVERNMENT.value: 0.0,
    CompanyStage.NONPROFIT.value: 0.0,
}

#: Families with a short path into executive, founder or top-of-market IC pay.
FAMILY_UPSIDE: dict[str, float] = {
    JobFamily.FOUNDERS_OFFICE.value: 18,
    JobFamily.ENTREPRENEUR_IN_RESIDENCE.value: 18,
    JobFamily.CHIEF_OF_STAFF.value: 15,
    JobFamily.FORWARD_DEPLOYED_ENGINEER.value: 14,
    JobFamily.MEMBER_OF_TECHNICAL_STAFF.value: 14,
    JobFamily.AI_ENGINEER.value: 13,
    JobFamily.ML_ENGINEER.value: 13,
    JobFamily.RESEARCH_ENGINEER.value: 12,
    JobFamily.TECHNICAL_ACCOUNT_EXECUTIVE.value: 14,
    JobFamily.SOLUTIONS_ENGINEER.value: 11,
    JobFamily.TECHNICAL_BUSINESS_DEVELOPMENT.value: 12,
    JobFamily.GTM_ENGINEER.value: 11,
    JobFamily.VULNERABILITY_RESEARCHER.value: 11,
    JobFamily.AI_SECURITY_ENGINEER.value: 11,
    JobFamily.SPECIAL_PROJECTS.value: 10,
    JobFamily.SOLUTIONS_ARCHITECT.value: 9,
    JobFamily.AI_MISSION_ENGINEER.value: 9,
    JobFamily.SCIENTIFIC_ML_ENGINEER.value: 9,
    JobFamily.COMPUTATIONAL_BIOLOGY_ML.value: 8,
    JobFamily.MALWARE_REVERSE_ENGINEER.value: 7,
    JobFamily.CLEARED_SOFTWARE_ENGINEER.value: 5,
    JobFamily.STRATEGY_AND_OPERATIONS.value: 5,
    JobFamily.BIOSECURITY_SCIENTIST.value: 5,
    JobFamily.CYBER_THREAT_INTELLIGENCE.value: 4,
    JobFamily.TECHNICAL_INTELLIGENCE_ANALYST.value: 1,
    JobFamily.TECHNICAL_PROGRAM_SETA.value: 0,
}

BASE_SCORE = 35.0


def score_upside(job, candidate, config: ScoringConfig) -> DimensionScore:
    reasons: list[Reason] = []
    score = BASE_SCORE

    # --- equity ------------------------------------------------------------
    stage = job.company_stage or ""
    if job.equity and job.equity_percent_min:
        multiplier = STAGE_EQUITY_MULTIPLIER.get(stage, 12.0)
        percent = job.equity_percent_max or job.equity_percent_min
        bonus = min(30.0, percent * multiplier)
        score += bonus
        reasons.append(
            Reason(
                f"{percent}% equity at {stage.replace('_', ' ') or 'an unstated stage'} - "
                "meaningful ownership if the company works.",
                impact=bonus,
                kind="positive",
            )
        )
    elif job.equity:
        score += 8
        reasons.append(
            Reason(
                "Equity offered but not quantified. Ask for percentage, strike price and "
                "current valuation before treating it as upside.",
                impact=8,
                kind="missing",
            )
        )
    elif job.equity is False:
        score -= 10
        reasons.append(
            Reason("No equity - upside is capped at salary growth.", impact=-10, kind="negative")
        )
    else:
        reasons.append(Reason("Equity not mentioned.", kind="missing"))

    # --- stage optionality --------------------------------------------------
    if stage in (CompanyStage.SEED.value, CompanyStage.SERIES_A.value, CompanyStage.PRE_SEED.value):
        score += 8
        reasons.append(
            Reason(
                "Early stage: high variance, but the scenarios that pay $1M+ live here.",
                impact=8,
                kind="positive",
            )
        )
    elif stage in (CompanyStage.GOVERNMENT.value, CompanyStage.NONPROFIT.value):
        score -= 12
        reasons.append(
            Reason(
                "Government / non-profit: compensation is banded and there is no equity "
                "outcome. Upside is career capital, not money.",
                impact=-12,
                kind="negative",
            )
        )

    # --- family path --------------------------------------------------------
    family = job.job_family or JobFamily.OTHER.value
    family_bonus = FAMILY_UPSIDE.get(family, 6)
    score += family_bonus
    if family_bonus >= 12:
        reasons.append(
            Reason(
                "This family has a short path into executive, founder or top-of-market IC "
                "compensation.",
                impact=family_bonus,
                kind="positive",
            )
        )
    elif family_bonus <= 2:
        reasons.append(
            Reason(
                "Limited structural path to substantially higher compensation.",
                impact=-6,
                kind="negative",
            )
        )
        score -= 6

    # --- variable comp ------------------------------------------------------
    if job.revenue_responsibility or job.commission_ote:
        score += 10
        reasons.append(
            Reason(
                "Carries revenue / commission - uncapped or accelerator-based earnings are a "
                "real path past $300k.",
                impact=10,
                kind="positive",
            )
        )

    # --- current comp as a floor -------------------------------------------
    top = job.salary_max or job.salary_min
    if top:
        if top >= 300_000:
            score += 14
            reasons.append(Reason("Base alone already clears $300k.", impact=14, kind="positive"))
        elif top >= 250_000:
            score += 9
            reasons.append(
                Reason(
                    "Base approaches $250k, a strong starting point for growth.",
                    impact=9,
                    kind="positive",
                )
            )
        elif top >= 200_000:
            score += 5
            reasons.append(
                Reason("Base at $200k+ compounds well with promotions.", impact=5, kind="positive")
            )
        elif top < 130_000:
            score -= 8
            reasons.append(
                Reason(
                    "Low base means the upside case rests entirely on equity or promotion.",
                    impact=-8,
                    kind="negative",
                )
            )

    # --- ownership and specialization ---------------------------------------
    if job.ownership_level == "high":
        score += 6
        reasons.append(
            Reason(
                "High ownership accelerates promotion and founder optionality.",
                impact=6,
                kind="positive",
            )
        )
    if job.technical_depth == "high" and job.research_intensity == "high":
        score += 6
        reasons.append(
            Reason(
                "Deep technical specialisation in a scarce area commands premium pay.",
                impact=6,
                kind="positive",
            )
        )

    return DimensionScore(
        name="Upside",
        score=clamp(score),
        reasons=reasons,
        details={
            "stage": stage or None,
            "equity_percent": job.equity_percent_max or job.equity_percent_min,
        },
    )


__all__ = ["score_upside", "STAGE_EQUITY_MULTIPLIER", "FAMILY_UPSIDE"]
