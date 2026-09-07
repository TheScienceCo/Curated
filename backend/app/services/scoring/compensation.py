"""D. Compensation Score.

Uses the candidate's own bands (§6D), never a market average. The bands are
fully configurable; the defaults follow the spec's ladder.

Unstated compensation is scored as a neutral unknown, not a zero. A recruiter
who has not shared a range has given you no information - and the correct
response is to ask, which is exactly what the missing-information detector
does with this signal.
"""

from __future__ import annotations

from app.services.scoring.base import DimensionScore, Reason, clamp, scale
from app.services.scoring.config import ScoringConfig

#: Score awarded when no compensation is stated at all.
UNKNOWN_SCORE = 50.0


def _band_score(value: int, config: ScoringConfig) -> float:
    """Map a dollar figure onto 0-100 using the candidate's bands.

    Piecewise-linear through the four anchors so the curve is monotone and
    easy to explain: poor=30, acceptable=55, strong=80, excellent=95.
    """
    bands = config.compensation_bands
    if value <= bands.poor:
        return scale(value, bands.poor * 0.5, bands.poor, out_low=0, out_high=30)
    if value <= bands.acceptable:
        return scale(value, bands.poor, bands.acceptable, out_low=30, out_high=55)
    if value <= bands.strong:
        return scale(value, bands.acceptable, bands.strong, out_low=55, out_high=80)
    if value <= bands.excellent:
        return scale(value, bands.strong, bands.excellent, out_low=80, out_high=95)
    # Above "excellent" the curve flattens: 400k is better than 250k, but not
    # proportionally so, and the extra usually shows up in Upside instead.
    return scale(value, bands.excellent, bands.excellent * 2, out_low=95, out_high=100)


def _fmt_money(value: int | None, currency: str = "USD") -> str:
    if value is None:
        return "unspecified"
    symbol = {"USD": "$", "GBP": "£", "EUR": "€"}.get(currency, "")
    return f"{symbol}{value:,.0f}"


#: Bonuses beyond base salary (equity, bonus, OTE, transparency) are capped
#: in total, so a pile of small positives cannot turn a mediocre base into a
#: 100. Base salary should dominate this dimension.
MAX_NON_BASE_BONUS = 10.0


def score_compensation(job, candidate, config: ScoringConfig) -> DimensionScore:
    reasons: list[Reason] = []
    bands = config.compensation_bands
    currency = job.salary_currency or "USD"
    #: Accumulates equity / bonus / OTE / transparency adjustments, capped below.
    bonus_pool = 0.0

    salary_min = job.salary_min
    salary_max = job.salary_max

    if salary_min is None and salary_max is None:
        reasons.append(
            Reason(
                "No compensation stated. Scored as a neutral unknown - this is the single "
                "highest-priority question to ask before investing time.",
                kind="missing",
            )
        )
        base = UNKNOWN_SCORE
        transparency_penalty = 0.0
    else:
        # Score the midpoint but lean toward the bottom of the range: the top
        # of a posted band is aspirational far more often than it is real.
        if salary_min is not None and salary_max is not None:
            reference = salary_min + (salary_max - salary_min) * 0.4
            label = f"{_fmt_money(salary_min, currency)}-{_fmt_money(salary_max, currency)}"
        else:
            reference = salary_max or salary_min or 0
            label = _fmt_money(reference, currency)
        base = _band_score(int(reference), config)
        transparency_penalty = 0.0

        if base >= 80:
            kind, verdict = "positive", "strong to excellent against your bands"
        elif base >= 55:
            kind, verdict = "positive", "acceptable against your bands"
        elif base >= 30:
            kind, verdict = "negative", "below your acceptable band"
        else:
            kind, verdict = "negative", "well below your poor-band floor"
        reasons.append(
            Reason(
                f"Base salary {label} is {verdict} "
                f"(poor <{_fmt_money(bands.poor)}, acceptable {_fmt_money(bands.acceptable)}, "
                f"strong {_fmt_money(bands.strong)}, excellent {_fmt_money(bands.excellent)}+).",
                impact=base - 50,
                kind=kind,
            )
        )

        minimum = candidate.minimum_salary
        if minimum and (salary_max or salary_min or 0) < minimum * config.salary_dealbreaker_ratio:
            reasons.append(
                Reason(
                    f"Top of range is below {int(config.salary_dealbreaker_ratio * 100)}% of your "
                    f"{_fmt_money(minimum)} minimum - effectively a dealbreaker unless equity "
                    "or the role itself is exceptional.",
                    impact=-25,
                    kind="negative",
                )
            )
            base = min(base, 20.0)
        elif minimum and (salary_max or salary_min or 0) < minimum:
            reasons.append(
                Reason(
                    f"Range tops out below your stated {_fmt_money(minimum)} minimum.",
                    impact=-12,
                    kind="negative",
                )
            )
            base -= 12

        target = candidate.target_salary
        if target and (salary_max or 0) >= target:
            reasons.append(
                Reason(
                    f"Range reaches your {_fmt_money(target)} target.", impact=6, kind="positive"
                )
            )
            bonus_pool += 6

    # --- components beyond base ------------------------------------------
    if job.commission_ote:
        reasons.append(
            Reason(
                f"On-target earnings of {_fmt_money(job.commission_ote, currency)} - variable, "
                "so weight it against the base, not on top of it.",
                impact=6,
                kind="positive",
            )
        )
        bonus_pool += 6
    if job.bonus:
        reasons.append(Reason(f"Bonus mentioned: {job.bonus[:120]}", impact=4, kind="positive"))
        bonus_pool += 4
    if job.equity:
        if job.equity_percent_min:
            reasons.append(
                Reason(
                    f"Equity {job.equity_percent_min}%"
                    + (
                        f"-{job.equity_percent_max}%"
                        if job.equity_percent_max
                        and job.equity_percent_max != job.equity_percent_min
                        else ""
                    )
                    + " - see the equity calculator for scenario values.",
                    impact=8,
                    kind="positive",
                )
            )
            bonus_pool += 8
        else:
            reasons.append(
                Reason(
                    "Equity offered but the percentage is not stated - worth asking, since it "
                    "is the difference between a rounding error and life-changing.",
                    impact=3,
                    kind="missing",
                )
            )
            bonus_pool += 3
    elif job.equity is False:
        reasons.append(Reason("No equity offered.", impact=-4, kind="negative"))
        bonus_pool -= 4

    # --- transparency ------------------------------------------------------
    if salary_min is not None and salary_max is not None:
        reasons.append(
            Reason(
                "Range disclosed up front - a good sign about how they negotiate.",
                impact=3,
                kind="positive",
            )
        )
        bonus_pool += 3
    elif salary_min is not None or salary_max is not None:
        base -= 2
    else:
        transparency_penalty = 6.0
        base -= transparency_penalty
        reasons.append(
            Reason(
                "No salary transparency in the source material.",
                impact=-transparency_penalty,
                kind="negative",
            )
        )

    base += max(-MAX_NON_BASE_BONUS, min(MAX_NON_BASE_BONUS, bonus_pool))

    return DimensionScore(
        name="Compensation",
        score=clamp(base),
        reasons=reasons,
        details={
            "salary_min": salary_min,
            "salary_max": salary_max,
            "currency": currency,
            "bands": bands.model_dump(),
            "specified": salary_min is not None or salary_max is not None,
        },
    )


__all__ = ["score_compensation", "UNKNOWN_SCORE"]
