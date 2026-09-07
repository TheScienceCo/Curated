"""Deterministic clearance and polygraph classification.

This module is intentionally rule-based, not LLM-driven. Clearance
eligibility is a binary legal fact with expensive consequences if you get it
wrong, and the vocabulary is small and stable enough to parse exactly.

The single most important invariant, stated in the product spec and enforced
by tests: **a counterintelligence (CI) polygraph is never treated as
equivalent to a full-scope / expanded-scope polygraph (FSP / ESP).**
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.enums import (
    CLEARANCE_RANK,
    POLYGRAPH_SATISFIES,
    ClearanceLevel,
    PolygraphType,
)

# --------------------------------------------------------------------------
# Clearance level parsing
# --------------------------------------------------------------------------

# Ordered most-specific first: "TS/SCI" must win before plain "TS".
_CLEARANCE_PATTERNS: list[tuple[re.Pattern[str], ClearanceLevel]] = [
    (re.compile(r"\bts\s*/\s*sci\b", re.I), ClearanceLevel.TS_SCI),
    (re.compile(r"\btssci\b", re.I), ClearanceLevel.TS_SCI),
    (re.compile(r"\btop[\s\-]secret\b[^.\n]{0,30}\bsci\b", re.I), ClearanceLevel.TS_SCI),
    (re.compile(r"\bsci\b[^.\n]{0,20}\beligib", re.I), ClearanceLevel.TS_SCI),
    (re.compile(r"\bts\b[^.\n]{0,10}\bsci\b", re.I), ClearanceLevel.TS_SCI),
    (re.compile(r"\btop[\s\-]secret\b", re.I), ClearanceLevel.TOP_SECRET),
    (re.compile(r"\bts\s+clearance\b", re.I), ClearanceLevel.TOP_SECRET),
    (re.compile(r"\bsecret\b", re.I), ClearanceLevel.SECRET),
    (re.compile(r"\bconfidential\s+clearance\b", re.I), ClearanceLevel.CONFIDENTIAL),
    (re.compile(r"\bpublic\s+trust\b", re.I), ClearanceLevel.PUBLIC_TRUST),
]

_NO_CLEARANCE_PATTERNS = [
    re.compile(r"\bno\s+(?:security\s+)?clearance\s+(?:is\s+)?(?:required|needed)\b", re.I),
    re.compile(r"\bclearance\s+(?:is\s+)?not\s+required\b", re.I),
    re.compile(r"\bdoes\s+not\s+require\s+a?\s*(?:security\s+)?clearance\b", re.I),
    re.compile(r"\bnon[\s\-]cleared\b", re.I),
]

# --------------------------------------------------------------------------
# Polygraph parsing
# --------------------------------------------------------------------------

_FULL_SCOPE_PATTERNS = [
    re.compile(r"\bfull[\s\-]?scope\b", re.I),
    re.compile(r"\bfsp\b", re.I),
    re.compile(r"\bexpanded[\s\-]?scope\b", re.I),
    re.compile(r"\besp\s+poly", re.I),
    re.compile(r"\blifestyle\s+poly", re.I),
    re.compile(r"\bfs\s+poly", re.I),
]

_CI_PATTERNS = [
    re.compile(r"\bci\s*(?:-|\s)?\s*poly", re.I),
    re.compile(r"\bcounter[\s\-]?intelligence\s+poly", re.I),
    re.compile(r"\bcounterintel\s+poly", re.I),
    re.compile(r"\bci\s+polygraph\b", re.I),
]

_GENERIC_POLY_PATTERNS = [
    re.compile(r"\bpolygraph\b", re.I),
    re.compile(r"\bpoly\b", re.I),
]

_NO_POLY_PATTERNS = [
    re.compile(r"\bno\s+polygraph\b", re.I),
    re.compile(r"\bpolygraph\s+(?:is\s+)?not\s+required\b", re.I),
    re.compile(r"\bwithout\s+a\s+polygraph\b", re.I),
]

_POLY_LABELS = {
    PolygraphType.NONE: "No polygraph",
    PolygraphType.CI: "Counterintelligence (CI) Polygraph",
    PolygraphType.FULL_SCOPE: "Full Scope / Expanded Scope Polygraph",
    PolygraphType.UNSPECIFIED_POLYGRAPH: "Polygraph required (type unspecified)",
    PolygraphType.UNKNOWN: "Not specified",
}

_CLEARANCE_LABELS = {
    ClearanceLevel.NONE: "None required",
    ClearanceLevel.PUBLIC_TRUST: "Public Trust",
    ClearanceLevel.CONFIDENTIAL: "Confidential",
    ClearanceLevel.SECRET: "Secret",
    ClearanceLevel.TOP_SECRET: "Top Secret",
    ClearanceLevel.TS_SCI: "TS/SCI",
    ClearanceLevel.UNSPECIFIED: "Not specified",
}


def clearance_label(level: str) -> str:
    return _CLEARANCE_LABELS.get(ClearanceLevel(level) if _is_clearance(level) else level, level)


def polygraph_label(poly: str) -> str:
    return _POLY_LABELS.get(PolygraphType(poly) if _is_poly(poly) else poly, poly)


def _is_clearance(value: str) -> bool:
    return value in {c.value for c in ClearanceLevel}


def _is_poly(value: str) -> bool:
    return value in {p.value for p in PolygraphType}


def parse_clearance(text: str | None) -> ClearanceLevel:
    """Classify the clearance level a piece of text requires.

    Returns UNSPECIFIED when the text says nothing about clearance — which is
    itself an important signal, because "unspecified" feeds the
    missing-information detector rather than being silently treated as "none".
    """
    if not text:
        return ClearanceLevel.UNSPECIFIED
    for pattern in _NO_CLEARANCE_PATTERNS:
        if pattern.search(text):
            return ClearanceLevel.NONE
    for pattern, level in _CLEARANCE_PATTERNS:
        if pattern.search(text):
            return level
    return ClearanceLevel.UNSPECIFIED


def parse_polygraph(text: str | None) -> PolygraphType:
    """Classify the polygraph requirement in a piece of text.

    Distinguishes four outcomes:
      * NONE                    - explicitly not required
      * CI                      - counterintelligence scope
      * FULL_SCOPE              - full scope / expanded scope / lifestyle
      * UNSPECIFIED_POLYGRAPH   - a poly is required but the scope is not stated
      * UNKNOWN                 - the text does not mention a polygraph at all
    """
    if not text:
        return PolygraphType.UNKNOWN
    for pattern in _NO_POLY_PATTERNS:
        if pattern.search(text):
            return PolygraphType.NONE
    # Full scope is checked first: "full scope polygraph" also contains "poly".
    for pattern in _FULL_SCOPE_PATTERNS:
        if pattern.search(text):
            return PolygraphType.FULL_SCOPE
    for pattern in _CI_PATTERNS:
        if pattern.search(text):
            return PolygraphType.CI
    for pattern in _GENERIC_POLY_PATTERNS:
        if pattern.search(text):
            return PolygraphType.UNSPECIFIED_POLYGRAPH
    return PolygraphType.UNKNOWN


@dataclass
class EligibilityVerdict:
    """Result of comparing candidate credentials to a job's requirement."""

    meets_clearance: bool
    meets_polygraph: bool
    clearance_gap: str | None
    polygraph_gap: str | None
    #: True when the shortfall cannot be closed by demonstration or study.
    hard_gate: bool
    notes: list[str]

    @property
    def eligible(self) -> bool:
        return self.meets_clearance and self.meets_polygraph


def clearance_satisfies(candidate: str, required: str) -> bool:
    """Does the candidate's clearance meet or exceed the requirement?

    UNSPECIFIED requirements are treated as satisfied for scoring purposes and
    surfaced separately by the missing-information detector.
    """
    if required in (ClearanceLevel.UNSPECIFIED, ClearanceLevel.NONE):
        return True
    return CLEARANCE_RANK.get(candidate, 0) >= CLEARANCE_RANK.get(required, 0)


def polygraph_satisfies(candidate: str, required: str) -> bool:
    """Does the candidate's polygraph meet the requirement?

    A CI poly does NOT satisfy a full-scope requirement. A full-scope poly
    does satisfy a CI requirement. An unspecified requirement is satisfied by
    any polygraph the candidate actually holds, but not by holding none.
    """
    if required in (PolygraphType.UNKNOWN, PolygraphType.NONE):
        return True
    if required == PolygraphType.UNSPECIFIED_POLYGRAPH:
        # We cannot know the scope; holding any poly is a plausible match, and
        # the ambiguity is reported as missing information instead.
        return candidate in (PolygraphType.CI, PolygraphType.FULL_SCOPE)
    return required in POLYGRAPH_SATISFIES.get(candidate, {PolygraphType.NONE})


def evaluate_eligibility(
    *,
    candidate_clearance: str,
    candidate_polygraph: str,
    required_clearance: str,
    required_polygraph: str,
) -> EligibilityVerdict:
    """Full clearance/poly comparison with human-readable gap descriptions."""
    notes: list[str] = []
    meets_clearance = clearance_satisfies(candidate_clearance, required_clearance)
    meets_poly = polygraph_satisfies(candidate_polygraph, required_polygraph)

    clearance_gap = None
    if not meets_clearance:
        clearance_gap = (
            f"Requires {clearance_label(required_clearance)}; "
            f"candidate holds {clearance_label(candidate_clearance)}."
        )

    polygraph_gap = None
    if not meets_poly:
        if (
            required_polygraph == PolygraphType.FULL_SCOPE
            and candidate_polygraph == PolygraphType.CI
        ):
            polygraph_gap = (
                "Requires a Full Scope / Expanded Scope polygraph; candidate holds a CI "
                "polygraph. A CI poly does NOT satisfy an FSP requirement - this is a hard "
                "eligibility gap unless the employer sponsors the upgrade."
            )
        else:
            polygraph_gap = (
                f"Requires {polygraph_label(required_polygraph)}; "
                f"candidate holds {polygraph_label(candidate_polygraph)}."
            )

    if required_clearance == ClearanceLevel.UNSPECIFIED:
        notes.append("Clearance requirement not stated - confirm with the recruiter.")
    if required_polygraph == PolygraphType.UNSPECIFIED_POLYGRAPH:
        notes.append(
            "A polygraph is required but the scope is not stated. CI and Full Scope are very "
            "different asks - confirm which one before investing time."
        )
    if required_polygraph == PolygraphType.UNKNOWN and required_clearance in (
        ClearanceLevel.TS_SCI,
        ClearanceLevel.TOP_SECRET,
    ):
        notes.append(
            "Cleared role with no polygraph stated - many TS/SCI billets add a poly later. "
            "Worth asking explicitly."
        )

    # A clearance or polygraph shortfall is a hard gate: it is granted by a
    # government adjudication process, not demonstrated in an interview.
    hard_gate = bool(clearance_gap or polygraph_gap)

    return EligibilityVerdict(
        meets_clearance=meets_clearance,
        meets_polygraph=meets_poly,
        clearance_gap=clearance_gap,
        polygraph_gap=polygraph_gap,
        hard_gate=hard_gate,
        notes=notes,
    )


__all__ = [
    "parse_clearance",
    "parse_polygraph",
    "clearance_satisfies",
    "polygraph_satisfies",
    "evaluate_eligibility",
    "EligibilityVerdict",
    "clearance_label",
    "polygraph_label",
]
