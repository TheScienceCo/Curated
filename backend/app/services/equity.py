"""§14 - equity scenario calculator.

Pure arithmetic with no market assumptions baked in. Every output is labelled
hypothetical because that is what it is: a grant's value depends on an exit
that has not happened, at a valuation nobody knows, after dilution nobody can
predict.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Exit valuations the table shows by default, in dollars.
DEFAULT_EXIT_VALUATIONS: tuple[int, ...] = (
    100_000_000,
    500_000_000,
    1_000_000_000,
    5_000_000_000,
)

DISCLAIMER = (
    "All values are hypothetical illustrations, not predictions or offers. They ignore taxes, "
    "liquidation preferences, participation rights, option strike costs beyond those entered, "
    "vesting cliffs, and the possibility of a zero outcome - which is the single most common "
    "outcome for early-stage equity."
)


@dataclass
class EquityScenario:
    exit_valuation: int
    gross_value: float
    net_value: float
    label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "exit_valuation": self.exit_valuation,
            "gross_value": round(self.gross_value, 2),
            "net_value": round(self.net_value, 2),
            "label": self.label,
        }


@dataclass
class EquityAnalysis:
    equity_percent: float
    dilution_percent: float
    post_dilution_percent: float
    strike_price: float | None
    shares: int | None
    current_valuation: int | None
    current_paper_value: float | None
    scenarios: list[EquityScenario]
    disclaimer: str = DISCLAIMER

    def to_dict(self) -> dict[str, Any]:
        return {
            "equity_percent": round(self.equity_percent, 4),
            "dilution_percent": round(self.dilution_percent, 2),
            "post_dilution_percent": round(self.post_dilution_percent, 4),
            "strike_price": self.strike_price,
            "shares": self.shares,
            "current_valuation": self.current_valuation,
            "current_paper_value": (
                round(self.current_paper_value, 2) if self.current_paper_value is not None else None
            ),
            "scenarios": [s.to_dict() for s in self.scenarios],
            "disclaimer": self.disclaimer,
        }


def _label(value: int) -> str:
    if value >= 1_000_000_000:
        billions = value / 1_000_000_000
        return f"${billions:.0f}B" if billions.is_integer() else f"${billions:.1f}B"
    millions = value / 1_000_000
    return f"${millions:.0f}M" if millions.is_integer() else f"${millions:.1f}M"


def calculate_equity(
    *,
    equity_percent: float,
    dilution_percent: float = 40.0,
    current_valuation: int | None = None,
    strike_price: float | None = None,
    shares: int | None = None,
    exit_valuations: tuple[int, ...] | list[int] | None = None,
) -> EquityAnalysis:
    """Build the dilution-adjusted scenario table.

    `equity_percent` is the grant as a percentage (0.25 means 0.25%).
    `dilution_percent` is total expected future dilution (40 means the stake
    ends up at 60% of its starting size).
    """
    if equity_percent < 0:
        raise ValueError("equity_percent cannot be negative")
    if not 0 <= dilution_percent < 100:
        raise ValueError("dilution_percent must be between 0 and 100")

    retained = 1 - (dilution_percent / 100)
    post = equity_percent * retained

    exits = tuple(exit_valuations) if exit_valuations else DEFAULT_EXIT_VALUATIONS
    strike_cost = 0.0
    if strike_price is not None and shares:
        strike_cost = strike_price * shares

    scenarios = [
        EquityScenario(
            exit_valuation=int(value),
            gross_value=value * (post / 100),
            net_value=max(0.0, value * (post / 100) - strike_cost),
            label=_label(int(value)),
        )
        for value in sorted(exits)
    ]

    current_paper = current_valuation * (equity_percent / 100) if current_valuation else None

    return EquityAnalysis(
        equity_percent=equity_percent,
        dilution_percent=dilution_percent,
        post_dilution_percent=post,
        strike_price=strike_price,
        shares=shares,
        current_valuation=current_valuation,
        current_paper_value=current_paper,
        scenarios=scenarios,
    )


__all__ = [
    "calculate_equity",
    "EquityAnalysis",
    "EquityScenario",
    "DEFAULT_EXIT_VALUATIONS",
    "DISCLAIMER",
]
