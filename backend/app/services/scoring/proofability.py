"""C. Proofability Score - "are the gaps barriers, or just unproven?"

This is the dimension that makes the product opinionated. A missing "5 years
of TypeScript" and a missing Full Scope Polygraph are not the same kind of
problem, and collapsing them into one "you're 80% qualified" number destroys
the only information that matters.

Scoring rule:
* No gaps at all -> 100 (nothing to prove).
* All gaps proofable -> high, scaled by how fast they can be proved.
* Any hard gate -> capped hard, because no amount of demonstration fixes it.
"""

from __future__ import annotations

from app.core.enums import ProofabilityTier
from app.services.scoring.base import DimensionScore, Gap, Reason, clamp
from app.services.scoring.config import ScoringConfig

#: A single hard gate caps the score here. Two or more caps it lower still.
HARD_GATE_CAP = 25.0
MULTI_HARD_GATE_CAP = 10.0


def score_proofability(
    gaps: list[Gap], job, candidate, config: ScoringConfig
) -> tuple[DimensionScore, list[Gap], list[Gap]]:
    """Return (score, hard_gates, proofable_gaps)."""
    reasons: list[Reason] = []
    hard_gates = [g for g in gaps if g.tier is ProofabilityTier.HARD_GATE]
    proofable = [g for g in gaps if g.tier is ProofabilityTier.PROOFABLE]

    if not gaps:
        reasons.append(
            Reason(
                "No unmet requirements found - nothing to prove beyond the normal interview.",
                impact=100,
                kind="positive",
            )
        )
        return (
            DimensionScore(name="Proofability", score=100.0, reasons=reasons, details={"gaps": 0}),
            [],
            [],
        )

    if hard_gates:
        score = MULTI_HARD_GATE_CAP if len(hard_gates) > 1 else HARD_GATE_CAP
        for gate in hard_gates:
            reasons.append(
                Reason(
                    f"Hard gate - {gate.requirement}. {gate.detail} Low proofability: this cannot "
                    "be offset by projects or interview performance.",
                    impact=-40,
                    kind="negative",
                )
            )
        if proofable:
            # Proofable gaps alongside a hard gate still deserve a small lift:
            # if the employer waives or sponsors the gate, the rest is fixable.
            lift = min(10.0, 2.0 * len(proofable))
            score += lift
            reasons.append(
                Reason(
                    f"The remaining {len(proofable)} gap(s) are demonstrable, so the "
                    "hard gate is the only real blocker - worth asking whether the "
                    "employer can sponsor or waive it.",
                    impact=lift,
                    kind="neutral",
                )
            )
        return (
            DimensionScore(
                name="Proofability",
                score=clamp(score),
                reasons=reasons,
                details={
                    "hard_gates": len(hard_gates),
                    "proofable_gaps": len(proofable),
                },
            ),
            hard_gates,
            proofable,
        )

    # All gaps are demonstrable. Score on how quickly, and how many.
    average_proofability = sum(g.proofability for g in proofable) / len(proofable)
    volume_penalty = min(20.0, max(0, len(proofable) - 2) * 4.0)
    score = clamp(55 + average_proofability * 45 - volume_penalty)

    fast = [g for g in proofable if g.proofability >= 0.85]
    slow = [g for g in proofable if g.proofability < 0.6]

    if fast:
        reasons.append(
            Reason(
                "High proofability - "
                + ", ".join(g.requirement for g in fast[:5])
                + " can be demonstrated with a technical interview or public projects.",
                impact=25,
                kind="positive",
            )
        )
    middling = [g for g in proofable if 0.6 <= g.proofability < 0.85]
    if middling:
        reasons.append(
            Reason(
                "Demonstrable with focused effort: "
                + ", ".join(f"{g.requirement} ({g.interview_readiness})" for g in middling[:4]),
                impact=10,
                kind="neutral",
            )
        )
    if slow:
        reasons.append(
            Reason(
                "Slower to prove: "
                + ", ".join(f"{g.requirement} ({g.interview_readiness})" for g in slow[:4]),
                impact=-10,
                kind="negative",
            )
        )
    if volume_penalty:
        reasons.append(
            Reason(
                f"{len(proofable)} simultaneous gaps - individually provable, but that is a lot "
                "to demonstrate in one loop.",
                impact=-volume_penalty,
                kind="negative",
            )
        )

    return (
        DimensionScore(
            name="Proofability",
            score=score,
            reasons=reasons,
            details={
                "hard_gates": 0,
                "proofable_gaps": len(proofable),
                "average_proofability": round(average_proofability, 2),
            },
        ),
        [],
        proofable,
    )


def build_prove_it_analysis(job, candidate, gaps: list[Gap]) -> dict:
    """§8 - the three-bucket view the detail page renders.

    Already demonstrated / learnable / hard gate, with a concrete plan for
    each item in the middle bucket.
    """
    from app.services.scoring.fit import candidate_skill_set
    from app.services.skills import get_skill, label_for

    held = candidate_skill_set(candidate)
    required = list(job.required_skills or [])
    preferred = list(job.preferred_skills or [])

    already: list[dict] = []
    for slug in [*required, *preferred]:
        if slug in held and not any(a["skill"] == label_for(slug) for a in already):
            skill = get_skill(slug)
            already.append(
                {
                    "skill": label_for(slug),
                    "category": skill.category if skill else "other",
                    "required": slug in required,
                }
            )

    # Clearance and polygraph the candidate holds are "already demonstrated"
    # credentials worth showing explicitly - they are often the strongest card.
    from app.core.enums import ClearanceLevel, PolygraphType
    from app.services.clearance import (
        clearance_label,
        clearance_satisfies,
        polygraph_label,
        polygraph_satisfies,
    )

    if job.security_clearance not in (
        None,
        ClearanceLevel.UNSPECIFIED.value,
        ClearanceLevel.NONE.value,
    ):
        if clearance_satisfies(candidate.clearance_level or "", job.security_clearance):
            already.append(
                {
                    "skill": clearance_label(candidate.clearance_level),
                    "category": "credential",
                    "required": True,
                }
            )
    if job.polygraph_requirement not in (
        None,
        PolygraphType.UNKNOWN.value,
        PolygraphType.NONE.value,
    ):
        if polygraph_satisfies(candidate.polygraph_type or "", job.polygraph_requirement):
            already.append(
                {
                    "skill": polygraph_label(candidate.polygraph_type),
                    "category": "credential",
                    "required": True,
                }
            )

    learnable = [
        {
            "requirement": g.requirement,
            "learning_difficulty": g.learning_difficulty,
            "suggested_project": g.suggested_project,
            "interview_readiness": g.interview_readiness,
            "how_to_demonstrate": g.suggested_project
            or "Build and publish a small project exercising this directly.",
            "proofability": round(g.proofability, 2),
        }
        for g in gaps
        if g.tier is ProofabilityTier.PROOFABLE
    ]

    hard = [
        {
            "requirement": g.requirement,
            "detail": g.detail,
            "why_hard": "Granted by an external process (adjudication, accreditation or law), "
            "not by demonstrated skill.",
        }
        for g in gaps
        if g.tier is ProofabilityTier.HARD_GATE
    ]

    return {
        "already_demonstrated": already,
        "learnable": learnable,
        "hard_gates": hard,
        "summary": _prove_it_summary(already, learnable, hard),
    }


def _prove_it_summary(already: list, learnable: list, hard: list) -> str:
    if hard:
        names = ", ".join(h["requirement"] for h in hard[:3])
        return (
            f"{len(hard)} hard gate(s) - {names} - would need to be waived or sponsored. "
            f"{len(learnable)} remaining gap(s) are demonstrable."
        )
    if learnable:
        return (
            f"No hard gates. {len(already)} requirement(s) already demonstrated and "
            f"{len(learnable)} demonstrable with focused work - this is a paper-fit gap, "
            "not an eligibility gap."
        )
    return f"All {len(already)} stated requirement(s) already demonstrated."


__all__ = ["score_proofability", "build_prove_it_analysis"]
