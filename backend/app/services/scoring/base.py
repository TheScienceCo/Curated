"""Shared types for the scoring engine.

Every dimension returns a `DimensionScore`: a number *and* the reasons for it.
The reasons are not decoration - the product's whole premise is that the user
should be able to see why a job scored what it did and disagree with it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.enums import ProofabilityTier


@dataclass
class Reason:
    """One line of a score's justification."""

    text: str
    #: Signed contribution in score points, for the "show your work" view.
    impact: float = 0.0
    kind: str = "neutral"  # positive | negative | neutral | missing

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "impact": round(self.impact, 1), "kind": self.kind}


@dataclass
class DimensionScore:
    name: str
    score: float
    reasons: list[Reason] = field(default_factory=list)
    #: Extra structured detail specific to the dimension.
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": round(self.score, 1),
            "reasons": [r.to_dict() for r in self.reasons],
            "details": self.details,
        }


@dataclass
class Gap:
    """A requirement the candidate does not currently meet."""

    requirement: str
    tier: ProofabilityTier
    detail: str
    #: 0..1; how demonstrable this is without formal calendar time.
    proofability: float = 0.0
    suggested_project: str | None = None
    interview_readiness: str | None = None
    learning_difficulty: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement": self.requirement,
            "tier": self.tier.value,
            "detail": self.detail,
            "proofability": round(self.proofability, 2),
            "suggested_project": self.suggested_project,
            "interview_readiness": self.interview_readiness,
            "learning_difficulty": self.learning_difficulty,
        }


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def scale(
    value: float, low: float, high: float, *, out_low: float = 0.0, out_high: float = 100.0
) -> float:
    """Linearly map `value` from [low, high] onto [out_low, out_high], clamped."""
    if high <= low:
        return out_low
    ratio = (value - low) / (high - low)
    return clamp(
        out_low + ratio * (out_high - out_low), min(out_low, out_high), max(out_low, out_high)
    )


__all__ = ["DimensionScore", "Reason", "Gap", "clamp", "scale"]
