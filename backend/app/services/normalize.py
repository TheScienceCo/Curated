"""Deterministic normalisers for salary, equity, hours, travel and location.

Money and schedules are parsed with regexes, never handed to an LLM. "$190k -
$240k" has exactly one correct interpretation, and a model that occasionally
returns 190 instead of 190000 would silently corrupt every downstream score.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.enums import EmploymentType, RemoteStatus

# --------------------------------------------------------------------------
# Salary
# --------------------------------------------------------------------------

CURRENCY_SYMBOLS = {"$": "USD", "£": "GBP", "€": "EUR", "¥": "JPY"}

_NUM = r"\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?"

#: "$190k-$240k", "190,000 - 240,000", "$190K to $240K"
_RANGE_RE = re.compile(
    rf"(?P<sym1>[$£€¥])?\s*(?P<n1>{_NUM})\s*(?P<k1>[kK])?\s*"
    rf"(?:-|–|—|\bto\b|\bthrough\b)\s*"
    rf"(?P<sym2>[$£€¥])?\s*(?P<n2>{_NUM})\s*(?P<k2>[kK])?",
)

#: "up to $250k", "starting at $180,000", "$200k base"
_SINGLE_RE = re.compile(rf"(?P<sym>[$£€¥])\s*(?P<n>{_NUM})\s*(?P<k>[kK])?")

_SALARY_CONTEXT = re.compile(
    r"salary|compensation|base|pay|comp\b|total comp|tc\b|package|range|ote|earn",
    re.I,
)

_HOURLY_HINT = re.compile(r"\bper\s*hour\b|\b/\s*hr\b|\bhourly\b|\ban\s*hour\b", re.I)

#: "OTE $280,000" / "on-target earnings of $280k" / "$280k OTE".
_OTE_RE = re.compile(
    rf"(?:\bote\b|on[\s-]target\s+earnings)(?:\s+(?:of|is|at))?\s*[:\-]?\s*"
    rf"(?P<sym>[$£€¥])?\s*(?P<n>{_NUM})\s*(?P<k>[kK])?"
    rf"|(?P<sym2>[$£€¥])?\s*(?P<n2>{_NUM})\s*(?P<k2>[kK])?\s+\bote\b",
    re.I,
)

#: Values below this are assumed to be "in thousands" when found in a salary
#: context (e.g. "190-240" or "$190" next to the word "salary").
_THOUSANDS_CUTOFF = 1000
#: Anything below this after normalisation is implausible as an annual US
#: salary and is treated as an hourly rate or a parse failure.
_MIN_PLAUSIBLE_ANNUAL = 15_000


@dataclass
class SalaryRange:
    minimum: int | None = None
    maximum: int | None = None
    currency: str = "USD"
    #: Verbatim text the numbers came from, for auditability.
    source_text: str | None = None
    is_ote: bool = False

    @property
    def midpoint(self) -> int | None:
        if self.minimum is not None and self.maximum is not None:
            return (self.minimum + self.maximum) // 2
        return self.maximum or self.minimum

    @property
    def specified(self) -> bool:
        return self.minimum is not None or self.maximum is not None


def _to_int(number: str, has_k: bool, *, salary_context: bool) -> int | None:
    try:
        value = float(number.replace(",", ""))
    except ValueError:
        return None
    if has_k:
        value *= 1000
    elif value < _THOUSANDS_CUTOFF and salary_context:
        # "190" in "$190-240k salary" means 190,000.
        value *= 1000
    return int(round(value))


def parse_salary(text: str | None) -> SalaryRange:
    """Extract an annual salary range from free text.

    Returns an empty range (``specified is False``) when nothing credible is
    found, which is what drives "compensation missing" detection.
    """
    if not text:
        return SalaryRange()

    for line in _salary_candidate_spans(text):
        has_context = bool(_SALARY_CONTEXT.search(line))
        currency = _detect_currency(line)
        is_ote = bool(re.search(r"\bote\b|on[\s-]target earnings", line, re.I))

        match = _RANGE_RE.search(line)
        if match:
            has_k = bool(match.group("k1") or match.group("k2"))
            low = _to_int(match.group("n1"), bool(match.group("k1")) or has_k, salary_context=True)
            high = _to_int(match.group("n2"), bool(match.group("k2")) or has_k, salary_context=True)
            if low and high and low > high:
                low, high = high, low
            if low and high and high >= _MIN_PLAUSIBLE_ANNUAL and not _HOURLY_HINT.search(line):
                return SalaryRange(low, high, currency, match.group(0).strip(), is_ote)

        if not has_context:
            continue
        singles = list(_SINGLE_RE.finditer(line))
        if len(singles) == 1:
            m = singles[0]
            value = _to_int(m.group("n"), bool(m.group("k")), salary_context=True)
            if value is None or value < _MIN_PLAUSIBLE_ANNUAL or _HOURLY_HINT.search(line):
                continue
            if re.search(r"\bup\s+to\b|\bmax(?:imum)?\b|\bnot\s+to\s+exceed\b", line, re.I):
                return SalaryRange(None, value, currency, m.group(0).strip(), is_ote)
            return SalaryRange(value, None, currency, m.group(0).strip(), is_ote)

    return SalaryRange()


def parse_ote(text: str | None) -> int | None:
    """Extract on-target earnings, which is a different number from base pay.

    Kept separate from `parse_salary` because a posting that quotes both
    ("Base $200k-$235k, OTE $280k") must not report the base midpoint as OTE.
    """
    if not text:
        return None
    match = _OTE_RE.search(text)
    if not match:
        return None
    number = match.group("n") or match.group("n2")
    has_k = bool(match.group("k") or match.group("k2"))
    if number is None:
        return None
    value = _to_int(number, has_k, salary_context=True)
    if value is None or value < _MIN_PLAUSIBLE_ANNUAL:
        return None
    return value


def _salary_candidate_spans(text: str) -> list[str]:
    """Split text into small spans, prioritising ones that mention money.

    Working span-by-span stops a range on one line from being paired with a
    number on another.
    """
    raw_spans = [s.strip() for s in re.split(r"[\n\r]+|(?<=[.;])\s+", text) if s.strip()]
    with_money = [s for s in raw_spans if re.search(r"[$£€¥]|\d", s)]
    scored = sorted(
        with_money,
        key=lambda s: (0 if _SALARY_CONTEXT.search(s) else 1, 0 if re.search(r"[$£€¥]", s) else 1),
    )
    return scored or with_money


def _detect_currency(text: str) -> str:
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in text:
            return code
    match = re.search(r"\b(USD|EUR|GBP|CAD|AUD|JPY|CHF)\b", text, re.I)
    return match.group(1).upper() if match else "USD"


# --------------------------------------------------------------------------
# Equity
# --------------------------------------------------------------------------


@dataclass
class EquityInfo:
    offered: bool | None = None
    percent_min: float | None = None
    percent_max: float | None = None
    notes: str | None = None


_EQUITY_PCT_RE = re.compile(
    rf"(?P<n1>{_NUM})\s*%\s*(?:-|–|to)\s*(?P<n2>{_NUM})\s*%|(?P<n>{_NUM})\s*%"
)
_EQUITY_MENTION_RE = re.compile(
    r"\bequity\b|\bstock\s+options?\b|\brsus?\b|\boptions?\s+grant\b|\bshares\b|"
    r"\bownership\s+stake\b|\bcarry\b",
    re.I,
)
_NO_EQUITY_RE = re.compile(
    r"\bno\s+equity\b|\bequity\s+is\s+not\s+offered\b|\bwithout\s+equity\b", re.I
)


def parse_equity(text: str | None) -> EquityInfo:
    if not text:
        return EquityInfo()
    if _NO_EQUITY_RE.search(text):
        return EquityInfo(offered=False, notes="Explicitly no equity")
    if not _EQUITY_MENTION_RE.search(text):
        return EquityInfo()

    # Only look for a percentage in the sentence that mentions equity, so a
    # "20% travel" elsewhere is not mistaken for an equity grant.
    for sentence in re.split(r"(?<=[.;\n])\s+", text):
        if not _EQUITY_MENTION_RE.search(sentence):
            continue
        match = _EQUITY_PCT_RE.search(sentence)
        if not match:
            continue
        if match.group("n1") and match.group("n2"):
            return EquityInfo(
                offered=True,
                percent_min=float(match.group("n1")),
                percent_max=float(match.group("n2")),
                notes=match.group(0).strip(),
            )
        value = float(match.group("n"))
        if value > 20:  # a >20% grant is almost certainly not equity
            continue
        return EquityInfo(
            offered=True, percent_min=value, percent_max=value, notes=match.group(0).strip()
        )

    return EquityInfo(offered=True, notes="Equity mentioned; percentage not stated")


# --------------------------------------------------------------------------
# Lifestyle: remote status, hours, travel
# --------------------------------------------------------------------------

_REMOTE_RE = re.compile(
    r"\b(?:fully\s+)?remote\b|\bwork\s+from\s+home\b|\bwfh\b|\bdistributed\s+team\b|"
    r"\bremote[\s\-]first\b",
    re.I,
)
_HYBRID_RE = re.compile(
    r"\bhybrid\b|\b\d\s*days?\s+(?:per\s+week\s+)?(?:in[\s\-]office|onsite)\b", re.I
)
_ONSITE_RE = re.compile(
    r"\bon[\s\-]?site\b|\bin[\s\-]?office\b|\bin[\s\-]person\b|\bco[\s\-]?located\b|"
    r"\bsecure\s+facility\b|\bscif\b",
    re.I,
)
_NOT_REMOTE_RE = re.compile(
    r"\bnot\s+(?:a\s+)?remote\b|\bno\s+remote\b|\bremote\s+is\s+not\b", re.I
)


def parse_remote_status(text: str | None) -> RemoteStatus:
    """Classify remote / hybrid / onsite.

    Hybrid wins over both pure signals because hybrid postings routinely
    contain the words "remote" and "onsite" in the same sentence.
    """
    if not text:
        return RemoteStatus.UNSPECIFIED
    if _HYBRID_RE.search(text):
        return RemoteStatus.HYBRID
    onsite = bool(_ONSITE_RE.search(text))
    remote = bool(_REMOTE_RE.search(text)) and not _NOT_REMOTE_RE.search(text)
    if onsite and remote:
        return RemoteStatus.HYBRID
    if onsite:
        return RemoteStatus.ONSITE
    if remote:
        return RemoteStatus.REMOTE
    return RemoteStatus.UNSPECIFIED


_TRAVEL_RE = re.compile(
    rf"(?:up\s+to\s+|approximately\s+|approx\.?\s+|~\s*|about\s+)?(?P<n>{_NUM})\s*%\s*(?:of\s+the\s+time\s+)?travel|travel[^.\n]{{0,30}}?(?P<n2>{_NUM})\s*%",
    re.I,
)
_NO_TRAVEL_RE = re.compile(r"\bno\s+travel\b|\btravel\s*:\s*none\b|\bminimal\s+travel\b", re.I)


def parse_travel(text: str | None) -> int | None:
    """Return expected travel as a percentage, or None when unstated."""
    if not text:
        return None
    if _NO_TRAVEL_RE.search(text):
        return 0
    match = _TRAVEL_RE.search(text)
    if match:
        raw = match.group("n") or match.group("n2")
        try:
            value = int(round(float(raw.replace(",", ""))))
        except (TypeError, ValueError):
            return None
        return value if 0 <= value <= 100 else None
    if re.search(r"\bheavy\s+travel\b|\bfrequent\s+travel\b|\bextensive\s+travel\b", text, re.I):
        return 50
    if re.search(r"\boccasional\s+travel\b|\bsome\s+travel\b|\blight\s+travel\b", text, re.I):
        return 10
    return None


_HOURS_RE = re.compile(
    rf"(?P<n>{_NUM})\s*(?:\+)?\s*(?:hours?|hrs?)\s*(?:per|/|a)\s*week|"
    rf"(?:work(?:ing)?\s+)?week\s*(?:of|:)?\s*(?P<n2>{_NUM})\s*(?:hours?|hrs?)",
    re.I,
)


def parse_weekly_hours(text: str | None) -> int | None:
    if not text:
        return None
    match = _HOURS_RE.search(text)
    if match:
        raw = match.group("n") or match.group("n2")
        try:
            value = int(round(float(raw.replace(",", ""))))
        except (TypeError, ValueError):
            return None
        return value if 1 <= value <= 120 else None
    return None


_ONCALL_RE = re.compile(r"\bon[\s\-]?call\b|\bpager\b|\brotation\b", re.I)
_NIGHTS_RE = re.compile(
    r"\bnights?\s+and\s+weekends?\b|\bweekend\s+work\b|\bafter[\s\-]hours\b", re.I
)
_SHIFT_RE = re.compile(
    r"\bshift\s+work\b|\bswing\s+shift\b|\bnight\s+shift\b|\b24/7\s+operations?\b", re.I
)
_RELOCATION_RE = re.compile(r"\brelocat", re.I)
_NO_RELOCATION_RE = re.compile(
    r"\bno\s+relocation\b|\brelocation\s+(?:is\s+)?not\s+required\b", re.I
)


def parse_oncall(text: str | None) -> bool | None:
    if not text:
        return None
    return True if _ONCALL_RE.search(text) else None


def parse_nights_weekends(text: str | None) -> bool | None:
    if not text:
        return None
    return True if _NIGHTS_RE.search(text) else None


def parse_shift_work(text: str | None) -> bool | None:
    if not text:
        return None
    return True if _SHIFT_RE.search(text) else None


def parse_relocation(text: str | None) -> bool | None:
    if not text:
        return None
    if _NO_RELOCATION_RE.search(text):
        return False
    if _RELOCATION_RE.search(text):
        return True
    return None


# --------------------------------------------------------------------------
# Experience, employment type, location
# --------------------------------------------------------------------------

_YOE_RANGE_RE = re.compile(
    rf"(?P<n1>{_NUM})\s*(?:-|–|to)\s*(?P<n2>{_NUM})\s*\+?\s*(?:years?|yrs?)", re.I
)
_YOE_SINGLE_RE = re.compile(rf"(?P<n>{_NUM})\s*\+?\s*(?:years?|yrs?)", re.I)
_EXPERIENCE_CONTEXT = re.compile(r"experience|background|track record|working with|building", re.I)


def parse_years_experience(text: str | None) -> tuple[float | None, float | None]:
    """Return (required, preferred) years of experience.

    "3-5 years" -> required 3, preferred 5. "5+ years" -> required 5.
    """
    if not text:
        return None, None
    for sentence in re.split(r"(?<=[.;\n])\s+", text):
        if not _EXPERIENCE_CONTEXT.search(sentence):
            continue
        match = _YOE_RANGE_RE.search(sentence)
        if match:
            try:
                low = float(match.group("n1"))
                high = float(match.group("n2"))
            except ValueError:
                continue
            if 0 < low <= high <= 40:
                return low, high
        match = _YOE_SINGLE_RE.search(sentence)
        if match:
            try:
                value = float(match.group("n"))
            except ValueError:
                continue
            if 0 < value <= 40:
                return value, None
    return None, None


_EMPLOYMENT_PATTERNS: list[tuple[re.Pattern[str], EmploymentType]] = [
    (re.compile(r"\bfull[\s\-]?time\b|\bfte\b", re.I), EmploymentType.FULL_TIME),
    (re.compile(r"\bpart[\s\-]?time\b", re.I), EmploymentType.PART_TIME),
    (
        re.compile(r"\bcontract(?:or)?\b|\bc2c\b|\b1099\b|\bcontract[\s\-]to[\s\-]hire\b", re.I),
        EmploymentType.CONTRACT,
    ),
    (re.compile(r"\bintern(?:ship)?\b", re.I), EmploymentType.INTERNSHIP),
    (re.compile(r"\bfractional\b", re.I), EmploymentType.FRACTIONAL),
]


def parse_employment_type(text: str | None) -> EmploymentType:
    if not text:
        return EmploymentType.UNSPECIFIED
    for pattern, value in _EMPLOYMENT_PATTERNS:
        if pattern.search(text):
            return value
    return EmploymentType.UNSPECIFIED


#: A pragmatic list of hubs. Unknown cities are still caught by the
#: "City, ST" pattern below; this list only improves recall for well-known
#: names written without a state.
_KNOWN_CITIES = (
    "San Francisco",
    "South San Francisco",
    "Palo Alto",
    "Mountain View",
    "Menlo Park",
    "Sunnyvale",
    "San Jose",
    "Oakland",
    "Berkeley",
    "Seattle",
    "Bellevue",
    "Redmond",
    "Portland",
    "Los Angeles",
    "El Segundo",
    "Santa Monica",
    "San Diego",
    "Denver",
    "Boulder",
    "Colorado Springs",
    "Austin",
    "Dallas",
    "Houston",
    "Chicago",
    "Boston",
    "Cambridge",
    "New York",
    "Brooklyn",
    "Jersey City",
    "Washington",
    "Washington DC",
    "Arlington",
    "Alexandria",
    "Reston",
    "Herndon",
    "Tysons",
    "McLean",
    "Chantilly",
    "Bethesda",
    "Annapolis Junction",
    "Fort Meade",
    "Columbia",
    "Laurel",
    "Baltimore",
    "Huntsville",
    "Tampa",
    "Melbourne",
    "Atlanta",
    "Miami",
    "Pittsburgh",
    "Ann Arbor",
    "Minneapolis",
    "Salt Lake City",
    "Phoenix",
    "Las Vegas",
    "Nashville",
    "Charlotte",
    "Raleigh",
    "Durham",
    "Philadelphia",
    "London",
    "Remote",
)
_CITY_STATE_RE = re.compile(r"\b([A-Z][a-zA-Z.\-]+(?:\s+[A-Z][a-zA-Z.\-]+){0,2}),\s*([A-Z]{2})\b")
_DC_RE = re.compile(r"\b(?:Washington,?\s*D\.?C\.?|DMV\s+area|National\s+Capital\s+Region)\b", re.I)


def parse_location(text: str | None) -> str | None:
    """Best-effort location extraction. Returns None rather than guessing."""
    if not text:
        return None
    if _DC_RE.search(text):
        return "Washington, DC"
    match = _CITY_STATE_RE.search(text)
    if match:
        return f"{match.group(1)}, {match.group(2)}"
    for city in _KNOWN_CITIES:
        if re.search(rf"(?<![\w]){re.escape(city)}(?![\w])", text, re.I):
            if city.lower() == "remote":
                continue
            return city
    return None


__all__ = [
    "SalaryRange",
    "EquityInfo",
    "parse_salary",
    "parse_ote",
    "parse_equity",
    "parse_remote_status",
    "parse_travel",
    "parse_weekly_hours",
    "parse_oncall",
    "parse_nights_weekends",
    "parse_shift_work",
    "parse_relocation",
    "parse_years_experience",
    "parse_employment_type",
    "parse_location",
]
