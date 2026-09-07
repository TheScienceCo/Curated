"""Configurable scoring knobs.

Everything a user might reasonably disagree with lives here, and every value
can be overridden per-candidate via `CandidateProfile.scoring_config`. The
scoring functions themselves contain no magic numbers that the user cannot
change.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class CompensationBands(BaseModel):
    """Candidate-defined salary thresholds (§6D).

    Defaults follow the spec's example ladder: <120k poor, 150k acceptable,
    200k strong, 250k+ excellent.
    """

    poor: int = 120_000
    acceptable: int = 150_000
    strong: int = 200_000
    excellent: int = 250_000

    @model_validator(mode="after")
    def _check_monotonic(self) -> CompensationBands:
        values = [self.poor, self.acceptable, self.strong, self.excellent]
        if values != sorted(values):
            raise ValueError(
                "Compensation bands must increase: poor < acceptable < strong < excellent"
            )
        return self


class ScoreWeights(BaseModel):
    """Weights for the overall score (§6H). Must sum to 1.0 after normalisation."""

    fit: float = 0.20
    career_capital: float = 0.25
    proofability: float = 0.15
    compensation: float = 0.20
    lifestyle: float = 0.10
    upside: float = 0.10

    def normalized(self) -> dict[str, float]:
        raw = self.model_dump()
        total = sum(raw.values())
        if total <= 0:
            raise ValueError("Score weights must sum to a positive number")
        return {k: v / total for k, v in raw.items()}


class ActionThresholds(BaseModel):
    """Overall-score cutoffs for the recommended action (§7)."""

    strongly_pursue: float = 82.0
    pursue: float = 72.0
    worth_a_call: float = 62.0
    maybe: float = 50.0
    low_priority: float = 38.0


class ScoringConfig(BaseModel):
    compensation_bands: CompensationBands = Field(default_factory=CompensationBands)
    weights: ScoreWeights = Field(default_factory=ScoreWeights)
    thresholds: ActionThresholds = Field(default_factory=ActionThresholds)

    #: How much of the risk score is subtracted from the overall score.
    #: 0.0 keeps risk purely informational (the spec's default posture:
    #: "risk should be shown separately and optionally subtract").
    risk_penalty_weight: float = Field(default=0.0, ge=0.0, le=0.5)

    #: A hard gate (clearance/poly/licence the candidate cannot obtain) caps
    #: the overall score at this value regardless of how good the job is.
    hard_gate_overall_cap: float = 45.0

    #: Missing formal years of experience is discounted this heavily when the
    #: underlying skills are demonstrable (§6A: "do not over-penalize").
    yoe_shortfall_discount: float = Field(default=0.35, ge=0.0, le=1.0)

    #: Below this fraction of the candidate's minimum salary, a stated salary
    #: is treated as disqualifying rather than merely weak.
    salary_dealbreaker_ratio: float = Field(default=0.8, ge=0.0, le=1.0)

    @classmethod
    def from_profile(cls, raw: dict[str, Any] | None) -> ScoringConfig:
        """Build a config from a profile's stored overrides, ignoring junk.

        A malformed override should never take the whole app down, so we fall
        back to defaults and let the caller log it.
        """
        if not raw:
            return cls()
        try:
            return cls.model_validate(raw)
        except Exception:  # noqa: BLE001 - defaults are always safe
            return cls()


DEFAULT_CONFIG = ScoringConfig()

__all__ = [
    "ScoringConfig",
    "ScoreWeights",
    "CompensationBands",
    "ActionThresholds",
    "DEFAULT_CONFIG",
]
