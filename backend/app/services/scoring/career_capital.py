"""B. Career Capital Score.

The question this answers, verbatim from the spec: *if the candidate takes
this role and performs well for 24 months, how much more valuable will they
become?*

This is the highest-weighted dimension by default, because it is the one most
people under-weight when a salary number is on the table.
"""

from __future__ import annotations

from app.core.enums import CompanyStage, JobFamily
from app.services.job_families import family_label
from app.services.scoring.base import DimensionScore, Reason, clamp
from app.services.scoring.config import ScoringConfig
from app.services.skills import get_skill, label_for

#: Job families that compound in value fastest right now. Score is a bonus in
#: points, applied once.
FAMILY_CAPITAL: dict[str, float] = {
    JobFamily.FORWARD_DEPLOYED_ENGINEER.value: 18,
    JobFamily.AI_ENGINEER.value: 16,
    JobFamily.AI_MISSION_ENGINEER.value: 16,
    JobFamily.ML_ENGINEER.value: 15,
    JobFamily.RESEARCH_ENGINEER.value: 15,
    JobFamily.MEMBER_OF_TECHNICAL_STAFF.value: 15,
    JobFamily.AI_SECURITY_ENGINEER.value: 15,
    JobFamily.VULNERABILITY_RESEARCHER.value: 14,
    JobFamily.FOUNDERS_OFFICE.value: 14,
    JobFamily.SCIENTIFIC_ML_ENGINEER.value: 13,
    JobFamily.COMPUTATIONAL_BIOLOGY_ML.value: 13,
    JobFamily.MALWARE_REVERSE_ENGINEER.value: 12,
    JobFamily.SOLUTIONS_ARCHITECT.value: 11,
    JobFamily.CHIEF_OF_STAFF.value: 11,
    JobFamily.ENTREPRENEUR_IN_RESIDENCE.value: 11,
    JobFamily.SOLUTIONS_ENGINEER.value: 10,
    JobFamily.GTM_ENGINEER.value: 10,
    JobFamily.SPECIAL_PROJECTS.value: 10,
    JobFamily.CLEARED_SOFTWARE_ENGINEER.value: 9,
    JobFamily.BIOSECURITY_SCIENTIST.value: 9,
    JobFamily.TECHNICAL_BUSINESS_DEVELOPMENT.value: 8,
    JobFamily.TECHNICAL_ACCOUNT_EXECUTIVE.value: 8,
    JobFamily.CYBER_THREAT_INTELLIGENCE.value: 7,
    JobFamily.STRATEGY_AND_OPERATIONS.value: 6,
    JobFamily.TECHNICAL_INTELLIGENCE_ANALYST.value: 2,
    JobFamily.TECHNICAL_PROGRAM_SETA.value: 0,
    JobFamily.OTHER.value: 4,
}

#: Stage affects network quality, brand and optionality.
STAGE_CAPITAL: dict[str, float] = {
    CompanyStage.SEED.value: 8,
    CompanyStage.SERIES_A.value: 10,
    CompanyStage.SERIES_B.value: 10,
    CompanyStage.SERIES_C.value: 8,
    CompanyStage.GROWTH.value: 7,
    CompanyStage.LATE_STAGE.value: 6,
    CompanyStage.PUBLIC.value: 5,
    CompanyStage.PRE_SEED.value: 5,
    CompanyStage.ESTABLISHED_PRIVATE.value: 3,
    CompanyStage.GOVERNMENT.value: 0,
    CompanyStage.NONPROFIT.value: 1,
}

#: Explicit negative signals from §6B.
_STAGNATION_MARKERS = (
    (
        "seta",
        -10,
        "SETA / staff-augmentation work tends to build process credibility, not technical capital.",
    ),
    (
        "staff augmentation",
        -10,
        "Staff-augmentation contracting rarely compounds into higher-comp roles.",
    ),
    ("butts in seats", -12, "Body-shop contracting signals low ownership."),
    ("level of effort", -6, "Level-of-effort contract work usually means low ownership."),
    ("maintain existing", -5, "Maintenance-only scope limits skill growth."),
    ("ticket", -4, "Ticket-driven work limits ownership and technical growth."),
    (
        "shift work",
        -5,
        "Shift-based watch-floor work rarely builds transferable technical capital.",
    ),
    ("watch floor", -6, "Watch-floor operations rarely build transferable technical capital."),
)

BASE_SCORE = 40.0


def score_career_capital(job, candidate, config: ScoringConfig) -> DimensionScore:
    reasons: list[Reason] = []
    score = BASE_SCORE
    text = " ".join(
        filter(None, [job.job_description or "", job.title or "", job.industry or ""])
    ).lower()

    # --- job family -------------------------------------------------------
    family = job.job_family or JobFamily.OTHER.value
    family_bonus = FAMILY_CAPITAL.get(family, 4)
    score += family_bonus
    if family_bonus >= 10:
        reasons.append(
            Reason(
                f"{family_label(family)} is a high-demand family that compounds quickly.",
                impact=family_bonus,
                kind="positive",
            )
        )
    elif family_bonus <= 2:
        reasons.append(
            Reason(
                f"{family_label(family)} builds slowly in market value relative to "
                "engineering-heavy alternatives.",
                impact=family_bonus - 8,
                kind="negative",
            )
        )
        score -= 8

    # --- skill market value ------------------------------------------------
    skills = [*(job.required_skills or []), *(job.preferred_skills or [])]
    if skills:
        valuable = sorted(
            ((s, get_skill(s).career_capital) for s in skills if get_skill(s)),
            key=lambda pair: -pair[1],
        )
        top = [pair for pair in valuable if pair[1] >= 0.75][:6]
        if top:
            bonus = min(18.0, sum(pair[1] for pair in top) * 3.0)
            score += bonus
            reasons.append(
                Reason(
                    "Builds high-demand skills: " + ", ".join(label_for(s) for s, _ in top),
                    impact=bonus,
                    kind="positive",
                )
            )
        elif valuable:
            avg = sum(p[1] for p in valuable) / len(valuable)
            if avg < 0.5:
                score -= 8
                reasons.append(
                    Reason(
                        "The skills exercised here are not in especially high market demand.",
                        impact=-8,
                        kind="negative",
                    )
                )

    # --- ownership, customer exposure, revenue ----------------------------
    if job.ownership_level == "high":
        score += 10
        reasons.append(
            Reason(
                "High ownership / ambiguity - the kind of scope that produces "
                "quantifiable achievements.",
                impact=10,
                kind="positive",
            )
        )
    elif job.ownership_level == "medium":
        score += 5
        reasons.append(Reason("Moderate ownership of outcomes.", impact=5, kind="positive"))
    elif job.ownership_level == "low":
        score -= 8
        reasons.append(
            Reason(
                "Low ownership - execution against someone else's plan.", impact=-8, kind="negative"
            )
        )

    if job.customer_facing_intensity == "high":
        score += 8
        reasons.append(
            Reason(
                "Customer-facing technical ownership - rare, and it transfers to FDE, "
                "solutions and founding roles.",
                impact=8,
                kind="positive",
            )
        )
    elif job.customer_facing_intensity == "medium":
        score += 4
        reasons.append(Reason("Some direct customer exposure.", impact=4, kind="positive"))

    if job.revenue_responsibility:
        score += 7
        reasons.append(
            Reason(
                "Revenue exposure - a credible path into executive and founder tracks.",
                impact=7,
                kind="positive",
            )
        )

    if job.management_responsibility:
        score += 6
        reasons.append(Reason("Leadership / people-management scope.", impact=6, kind="positive"))

    if job.research_intensity == "high":
        score += 6
        reasons.append(
            Reason(
                "Research credibility (publications / novel methods).", impact=6, kind="positive"
            )
        )

    if job.technical_depth == "high":
        score += 6
        reasons.append(
            Reason("Deep technical work rather than coordination.", impact=6, kind="positive")
        )
    elif job.technical_depth == "low":
        score -= 6
        reasons.append(
            Reason("Shallow technical depth - limited skill growth.", impact=-6, kind="negative")
        )

    # --- company brand and stage ------------------------------------------
    stage_bonus = STAGE_CAPITAL.get(job.company_stage or "", 0)
    if stage_bonus:
        score += stage_bonus
        reasons.append(
            Reason(
                f"Company stage ({(job.company_stage or '').replace('_', ' ')}) supports network "
                "and brand growth.",
                impact=stage_bonus,
                kind="positive",
            )
        )
    if job.equity:
        score += 4
        reasons.append(
            Reason(
                "Equity participation aligns upside with contribution.", impact=4, kind="positive"
            )
        )

    # --- explicit negative markers ----------------------------------------
    for marker, penalty, explanation in _STAGNATION_MARKERS:
        if marker in text:
            score += penalty
            reasons.append(Reason(explanation, impact=penalty, kind="negative"))
            break  # one stagnation penalty is enough; they overlap heavily

    # --- alignment with the candidate's stated goals ----------------------
    goals = [str(g).lower() for g in (candidate.career_goals or [])]
    if goals:
        goal_text = " ".join(goals)
        hits = [
            label_for(s) for s in skills if get_skill(s) and get_skill(s).label.lower() in goal_text
        ]
        family_in_goals = family.replace("_", " ") in goal_text
        if hits or family_in_goals:
            score += 5
            reasons.append(
                Reason("Directly advances a stated career goal.", impact=5, kind="positive")
            )

    if not reasons:
        reasons.append(
            Reason(
                "Too little information about scope, ownership or company to judge career "
                "capital confidently.",
                kind="missing",
            )
        )

    return DimensionScore(
        name="Career Capital",
        score=clamp(score),
        reasons=reasons,
        details={"job_family": family, "family_bonus": family_bonus},
    )


__all__ = ["score_career_capital", "FAMILY_CAPITAL", "STAGE_CAPITAL"]
