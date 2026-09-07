"""A. Current Fit Score - "can I do this job on paper today?"

Deliberately *not* the headline number. A low fit score with a high
proofability score is the product's core thesis: an imperfect paper match on
a high-value job is an opportunity, not a rejection.
"""

from __future__ import annotations

from app.core.enums import ClearanceLevel, PolygraphType, ProofabilityTier, RemoteStatus
from app.services.clearance import clearance_label, evaluate_eligibility, polygraph_label
from app.services.scoring.base import DimensionScore, Gap, Reason, clamp, scale
from app.services.scoring.config import ScoringConfig
from app.services.skills import classify_gap, label_for

# Sub-weights within the fit score. They sum to 1.0.
W_SKILLS = 0.40
W_CLEARANCE = 0.20
W_EXPERIENCE = 0.15
W_DOMAIN = 0.10
W_LOCATION = 0.08
W_EDUCATION = 0.04
W_AUTHORIZATION = 0.03


def _as_list(value) -> list:
    return list(value) if value else []


def candidate_skill_set(candidate) -> set[str]:
    """Everything the candidate can claim today, normalised to slugs.

    Includes anything with recorded years of experience (if the profile says
    "customer_facing: 8 years", that is a held skill whether or not it was
    also typed into the skills list) and anything implied by a held skill.
    """
    from app.services.skills import expand_skills, normalize_skills

    experience_keys = [str(k) for k in (candidate.years_experience_by_skill or {})]
    stated = normalize_skills(
        [
            *_as_list(candidate.technical_skills),
            *_as_list(candidate.domain_skills),
            *_as_list(candidate.certifications),
            *experience_keys,
        ]
    )
    # Implied skills count: someone shipping RAG systems has machine learning.
    return expand_skills(stated)


def score_fit(job, candidate, config: ScoringConfig) -> tuple[DimensionScore, list[Gap]]:
    """Return the fit score plus every gap it found, classified by tier."""
    reasons: list[Reason] = []
    gaps: list[Gap] = []

    held = candidate_skill_set(candidate)
    proofable_claims = set(_as_list(candidate.proofable_skills))
    required = _as_list(job.required_skills)
    preferred = _as_list(job.preferred_skills)

    # --- skills -----------------------------------------------------------
    if required:
        matched = [s for s in required if s in held]
        missing = [s for s in required if s not in held]
        skill_ratio = len(matched) / len(required)
        skill_component = skill_ratio * 100
        if matched:
            reasons.append(
                Reason(
                    f"Matches {len(matched)}/{len(required)} required skills: "
                    + ", ".join(label_for(s) for s in matched[:6]),
                    impact=W_SKILLS * skill_component,
                    kind="positive",
                )
            )
        for slug in missing:
            gap = classify_gap(slug)
            # A skill the candidate has explicitly flagged as proofable is
            # reported as such even if the ontology is more pessimistic.
            tier = (
                ProofabilityTier.PROOFABLE
                if slug in proofable_claims and gap.tier is ProofabilityTier.HARD_GATE
                else gap.tier
            )
            gaps.append(
                Gap(
                    requirement=gap.label,
                    tier=tier,
                    detail=f"Required skill not in profile: {gap.label}.",
                    proofability=gap.proofability,
                    suggested_project=gap.suggested_project,
                    interview_readiness=gap.interview_readiness,
                    learning_difficulty=gap.learning_difficulty,
                )
            )
        if missing:
            reasons.append(
                Reason(
                    f"Missing {len(missing)} required skill(s): "
                    + ", ".join(label_for(s) for s in missing[:6]),
                    impact=-W_SKILLS * (100 - skill_component),
                    kind="negative",
                )
            )
    else:
        # No parsed requirements is an information problem, not a fit problem.
        skill_component = 55.0
        reasons.append(
            Reason("No required skills stated - fit assessed on other signals.", kind="missing")
        )

    # Preferred skills are a small bonus, never a penalty.
    preferred_bonus = 0.0
    if preferred:
        matched_pref = [s for s in preferred if s in held]
        if matched_pref:
            preferred_bonus = min(8.0, 3.0 * len(matched_pref))
            reasons.append(
                Reason(
                    "Also holds preferred skills: "
                    + ", ".join(label_for(s) for s in matched_pref[:5]),
                    impact=preferred_bonus,
                    kind="positive",
                )
            )

    # --- clearance / polygraph -------------------------------------------
    verdict = evaluate_eligibility(
        candidate_clearance=candidate.clearance_level or ClearanceLevel.NONE.value,
        candidate_polygraph=candidate.polygraph_type or PolygraphType.NONE.value,
        required_clearance=job.security_clearance or ClearanceLevel.UNSPECIFIED.value,
        required_polygraph=job.polygraph_requirement or PolygraphType.UNKNOWN.value,
    )
    if verdict.eligible:
        clearance_component = 100.0
        if (job.security_clearance or "") not in (
            ClearanceLevel.UNSPECIFIED.value,
            ClearanceLevel.NONE.value,
        ):
            reasons.append(
                Reason(
                    f"Clearance requirement met: holds {clearance_label(candidate.clearance_level)}"
                    + (
                        f" with {polygraph_label(candidate.polygraph_type)}"
                        if candidate.polygraph_type not in (PolygraphType.NONE.value, None)
                        else ""
                    )
                    + ".",
                    impact=W_CLEARANCE * 100,
                    kind="positive",
                )
            )
    else:
        clearance_component = 0.0
        for gap_text in (verdict.clearance_gap, verdict.polygraph_gap):
            if not gap_text:
                continue
            reasons.append(Reason(gap_text, impact=-W_CLEARANCE * 100, kind="negative"))
            gaps.append(
                Gap(
                    requirement=(
                        "Security clearance" if gap_text is verdict.clearance_gap else "Polygraph"
                    ),
                    tier=ProofabilityTier.HARD_GATE,
                    detail=gap_text,
                    proofability=0.0,
                    interview_readiness="not achievable by demonstration",
                    learning_difficulty="gated",
                )
            )
    for note in verdict.notes:
        reasons.append(Reason(note, kind="missing"))

    # --- years of experience ---------------------------------------------
    required_yoe = job.required_years_experience
    candidate_yoe = _relevant_years(candidate, required)
    if required_yoe:
        if candidate_yoe >= required_yoe:
            experience_component = 100.0
            reasons.append(
                Reason(
                    f"Meets the stated {_fmt(required_yoe)} years of experience "
                    f"(~{_fmt(candidate_yoe)} relevant).",
                    impact=W_EXPERIENCE * 100,
                    kind="positive",
                )
            )
        else:
            shortfall = required_yoe - candidate_yoe
            raw = scale(candidate_yoe, 0, required_yoe, out_low=30, out_high=100)
            # §6A: do not over-penalise missing formal years when the skills
            # themselves are demonstrable.
            demonstrable = _demonstrable_fraction(required, held, proofable_claims)
            experience_component = clamp(
                raw + (100 - raw) * config.yoe_shortfall_discount * demonstrable
            )
            reasons.append(
                Reason(
                    f"{_fmt(shortfall)} years short of the stated {_fmt(required_yoe)}-year bar "
                    f"(~{_fmt(candidate_yoe)} relevant). Discounted because "
                    f"{int(demonstrable * 100)}% of the required skills are demonstrable.",
                    impact=-(W_EXPERIENCE * (100 - experience_component)),
                    kind="negative",
                )
            )
            gaps.append(
                Gap(
                    requirement=f"{_fmt(required_yoe)} years of experience",
                    tier=ProofabilityTier.PROOFABLE
                    if demonstrable >= 0.5
                    else ProofabilityTier.HARD_GATE,
                    detail=(
                        f"Conventional {_fmt(required_yoe)}-year bar; candidate has ~"
                        f"{_fmt(candidate_yoe)} directly relevant years. Years cannot be "
                        "manufactured, but the underlying skills can be demonstrated."
                        if demonstrable >= 0.5
                        else (
                            f"Requires {_fmt(required_yoe)} years in skills the "
                            "candidate has not demonstrated."
                        )
                    ),
                    proofability=0.6 if demonstrable >= 0.5 else 0.2,
                    suggested_project=(
                        "Portfolio projects and a technical interview in place of tenure."
                    ),
                    interview_readiness="immediate with a portfolio",
                    learning_difficulty="moderate",
                )
            )
    else:
        experience_component = 70.0
        reasons.append(Reason("No years-of-experience requirement stated.", kind="missing"))

    # --- domain / industry ------------------------------------------------
    domain_component, domain_reason = _domain_alignment(job, candidate)
    if domain_reason:
        reasons.append(domain_reason)

    # --- location ---------------------------------------------------------
    location_component, location_reason = _location_alignment(job, candidate)
    if location_reason:
        reasons.append(location_reason)

    # --- education --------------------------------------------------------
    education_component, education_gap = _education_alignment(job, candidate)
    if education_gap:
        gaps.append(education_gap)
        reasons.append(Reason(education_gap.detail, impact=-W_EDUCATION * 100, kind="negative"))

    # --- work authorization ------------------------------------------------
    auth_component, auth_gap = _authorization_alignment(job, candidate)
    if auth_gap:
        gaps.append(auth_gap)
        reasons.append(Reason(auth_gap.detail, impact=-W_AUTHORIZATION * 100, kind="negative"))

    total = (
        W_SKILLS * skill_component
        + W_CLEARANCE * clearance_component
        + W_EXPERIENCE * experience_component
        + W_DOMAIN * domain_component
        + W_LOCATION * location_component
        + W_EDUCATION * education_component
        + W_AUTHORIZATION * auth_component
        + preferred_bonus
    )

    return (
        DimensionScore(
            name="Current Fit",
            score=clamp(total),
            reasons=reasons,
            details={
                "skills": round(skill_component, 1),
                "clearance": round(clearance_component, 1),
                "experience": round(experience_component, 1),
                "domain": round(domain_component, 1),
                "location": round(location_component, 1),
                "education": round(education_component, 1),
                "work_authorization": round(auth_component, 1),
                "matched_skills": [s for s in required if s in held],
                "missing_skills": [s for s in required if s not in held],
            },
        ),
        gaps,
    )


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}"


def _relevant_years(candidate, required_skills: list[str]) -> float:
    """Years of experience weighted toward the skills this job actually asks for."""
    by_skill: dict = dict(candidate.years_experience_by_skill or {})
    if not by_skill:
        return 0.0
    from app.services.skills import normalize_skill

    normalized = {}
    for raw, years in by_skill.items():
        slug = normalize_skill(str(raw)) or str(raw)
        try:
            normalized[slug] = max(float(years), normalized.get(slug, 0.0))
        except (TypeError, ValueError):
            continue
    if required_skills:
        relevant = [normalized[s] for s in required_skills if s in normalized]
        if relevant:
            # The strongest relevant skill anchors, the rest add a little
            # breadth credit - closer to how an interviewer reads a résumé
            # than a raw average would be.
            return max(relevant) + 0.25 * (sum(relevant) - max(relevant)) / max(
                len(relevant) - 1, 1
            )
    return max(normalized.values()) if normalized else 0.0


def _demonstrable_fraction(required: list[str], held: set[str], proofable: set[str]) -> float:
    """What share of the required skills the candidate can hold or prove."""
    if not required:
        return 1.0
    count = 0
    for slug in required:
        if slug in held or slug in proofable:
            count += 1
        else:
            gap = classify_gap(slug)
            if gap.tier is ProofabilityTier.PROOFABLE:
                count += 1
    return count / len(required)


def _domain_alignment(job, candidate) -> tuple[float, Reason | None]:
    industries_of_interest = {str(i).lower() for i in _as_list(candidate.industries_of_interest)}
    industries_to_avoid = {str(i).lower() for i in _as_list(candidate.industries_to_avoid)}
    industry = (job.industry or "").lower()
    family = (job.job_family or "").lower()
    target_roles = {str(r).lower() for r in _as_list(candidate.target_roles)}

    if industry and any(avoid and avoid in industry for avoid in industries_to_avoid):
        return 10.0, Reason(
            f"Industry '{job.industry}' is on the avoid list.",
            impact=-W_DOMAIN * 90,
            kind="negative",
        )
    if family and any(
        family in role.replace(" ", "_") or role.replace(" ", "_") in family
        for role in target_roles
    ):
        return 100.0, Reason(
            "Role is in a target job family.", impact=W_DOMAIN * 100, kind="positive"
        )
    if industry and any(interest and interest in industry for interest in industries_of_interest):
        return 90.0, Reason(
            f"Industry '{job.industry}' is on the interest list.",
            impact=W_DOMAIN * 90,
            kind="positive",
        )
    return 55.0, None


def _location_alignment(job, candidate) -> tuple[float, Reason | None]:
    remote = job.remote_status or RemoteStatus.UNSPECIFIED.value
    preferred = {str(p).lower() for p in _as_list(candidate.preferred_locations)}
    location = (job.location or "").lower()

    if remote == RemoteStatus.REMOTE.value:
        return 100.0, Reason(
            "Fully remote - no location constraint.", impact=W_LOCATION * 100, kind="positive"
        )
    if not location:
        return 60.0, Reason("Location not stated.", kind="missing")
    if any(p and (p in location or location in p) for p in preferred):
        return 100.0, Reason(
            f"{job.location} is a preferred location.", impact=W_LOCATION * 100, kind="positive"
        )
    if remote == RemoteStatus.HYBRID.value:
        return 45.0, Reason(
            f"Hybrid in {job.location}, outside the preferred locations.",
            impact=-W_LOCATION * 55,
            kind="negative",
        )
    return 30.0, Reason(
        f"Onsite in {job.location}, outside the preferred locations - "
        "relocation or commute required.",
        impact=-W_LOCATION * 70,
        kind="negative",
    )


_DEGREE_RANK = {"associate": 1, "bachelor": 2, "master": 3, "phd": 4}


def _education_alignment(job, candidate) -> tuple[float, Gap | None]:
    requirements = [str(r).lower() for r in _as_list(job.education_requirements)]
    if not requirements:
        return 80.0, None
    held_text = " ".join(str(e).lower() for e in _as_list(candidate.education))
    held_rank = max((rank for name, rank in _DEGREE_RANK.items() if name in held_text), default=0)
    required_rank = max(
        (rank for name, rank in _DEGREE_RANK.items() if any(name in r for r in requirements)),
        default=0,
    )
    if required_rank == 0 or held_rank >= required_rank:
        return 100.0, None

    hard = required_rank >= 4  # a PhD requirement is a genuine hard gate
    return (
        20.0,
        Gap(
            requirement="Education requirement",
            tier=ProofabilityTier.HARD_GATE if hard else ProofabilityTier.PROOFABLE,
            detail=(
                f"Requires {requirements[0][:80]}; profile does not show it."
                + (
                    " A doctorate cannot be demonstrated in lieu."
                    if hard
                    else " Many employers waive degree bars for demonstrated skill."
                )
            ),
            proofability=0.0 if hard else 0.4,
            interview_readiness="not achievable by demonstration" if hard else "negotiable",
            learning_difficulty="gated" if hard else "high",
        ),
    )


def _authorization_alignment(job, candidate) -> tuple[float, Gap | None]:
    requirement = (job.citizenship_requirement or "").lower()
    if not requirement:
        return 90.0, None
    citizenship = (candidate.citizenship or "").lower()
    if "citizen" in requirement and "u.s" in requirement.replace("us", "u.s"):
        if "us" in citizenship or "u.s" in citizenship or "american" in citizenship:
            return 100.0, None
        return 0.0, Gap(
            requirement="US citizenship",
            tier=ProofabilityTier.HARD_GATE,
            detail="Role requires US citizenship; profile does not confirm it.",
            proofability=0.0,
            interview_readiness="not achievable by demonstration",
            learning_difficulty="gated",
        )
    if "no sponsorship" in requirement and not candidate.work_authorization:
        return 50.0, None
    return 90.0, None


__all__ = ["score_fit", "candidate_skill_set"]
