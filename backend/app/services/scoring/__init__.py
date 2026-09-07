"""Transparent, multi-dimensional opportunity scoring.

Each dimension lives in its own module and returns both a number and the
reasons behind it. Nothing here calls an LLM: scoring is arithmetic over
extracted facts, which is what makes it reproducible and arguable.
"""

from app.services.scoring.base import DimensionScore, Gap, Reason
from app.services.scoring.config import (
    ActionThresholds,
    CompensationBands,
    ScoreWeights,
    ScoringConfig,
)
from app.services.scoring.engine import ScoringResult, recommend_action, score_opportunity

__all__ = [
    "score_opportunity",
    "ScoringResult",
    "recommend_action",
    "ScoringConfig",
    "ScoreWeights",
    "CompensationBands",
    "ActionThresholds",
    "DimensionScore",
    "Reason",
    "Gap",
]
