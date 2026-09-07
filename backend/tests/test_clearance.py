"""Clearance and polygraph classification.

The CI-is-not-FSP invariant is the most consequential rule in the system, so
it gets the most tests.
"""

from __future__ import annotations

import pytest

from app.core.enums import ClearanceLevel, PolygraphType
from app.services.clearance import (
    clearance_satisfies,
    evaluate_eligibility,
    parse_clearance,
    parse_polygraph,
    polygraph_satisfies,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Requires TS/SCI", ClearanceLevel.TS_SCI),
        ("Must hold TS/SCI with polygraph", ClearanceLevel.TS_SCI),
        ("Active TSSCI required", ClearanceLevel.TS_SCI),
        ("Top Secret clearance with SCI access", ClearanceLevel.TS_SCI),
        ("Requires an active Top Secret clearance", ClearanceLevel.TOP_SECRET),
        ("Secret clearance required", ClearanceLevel.SECRET),
        ("Public Trust position", ClearanceLevel.PUBLIC_TRUST),
        ("No clearance required for this role", ClearanceLevel.NONE),
        ("Clearance is not required", ClearanceLevel.NONE),
        ("This is a commercial software role", ClearanceLevel.UNSPECIFIED),
        ("", ClearanceLevel.UNSPECIFIED),
        (None, ClearanceLevel.UNSPECIFIED),
    ],
)
def test_parse_clearance(text, expected):
    assert parse_clearance(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("TS/SCI with CI poly", PolygraphType.CI),
        ("Requires a counterintelligence polygraph", PolygraphType.CI),
        ("CI polygraph required", PolygraphType.CI),
        ("Requires a full scope polygraph", PolygraphType.FULL_SCOPE),
        ("Must have an FSP", PolygraphType.FULL_SCOPE),
        ("Expanded scope polygraph required", PolygraphType.FULL_SCOPE),
        ("Lifestyle polygraph required", PolygraphType.FULL_SCOPE),
        ("TS/SCI with polygraph", PolygraphType.UNSPECIFIED_POLYGRAPH),
        ("A polygraph is required", PolygraphType.UNSPECIFIED_POLYGRAPH),
        ("No polygraph required", PolygraphType.NONE),
        ("Requires TS/SCI", PolygraphType.UNKNOWN),
        ("", PolygraphType.UNKNOWN),
    ],
)
def test_parse_polygraph(text, expected):
    assert parse_polygraph(text) == expected


def test_full_scope_wins_over_generic_poly_mention():
    """ "Full scope polygraph" contains the word "polygraph"; scope must win."""
    assert parse_polygraph("Requires a full scope polygraph") == PolygraphType.FULL_SCOPE


class TestPolygraphEquivalence:
    """A CI polygraph must never be treated as a full scope polygraph."""

    def test_ci_does_not_satisfy_full_scope(self):
        assert polygraph_satisfies(PolygraphType.CI, PolygraphType.FULL_SCOPE) is False

    def test_full_scope_satisfies_ci(self):
        assert polygraph_satisfies(PolygraphType.FULL_SCOPE, PolygraphType.CI) is True

    def test_ci_satisfies_ci(self):
        assert polygraph_satisfies(PolygraphType.CI, PolygraphType.CI) is True

    def test_none_satisfies_nothing_but_none(self):
        assert polygraph_satisfies(PolygraphType.NONE, PolygraphType.CI) is False
        assert polygraph_satisfies(PolygraphType.NONE, PolygraphType.FULL_SCOPE) is False
        assert polygraph_satisfies(PolygraphType.NONE, PolygraphType.NONE) is True

    def test_unspecified_requirement_needs_some_polygraph(self):
        assert polygraph_satisfies(PolygraphType.CI, PolygraphType.UNSPECIFIED_POLYGRAPH) is True
        assert (
            polygraph_satisfies(PolygraphType.FULL_SCOPE, PolygraphType.UNSPECIFIED_POLYGRAPH)
            is True
        )
        assert polygraph_satisfies(PolygraphType.NONE, PolygraphType.UNSPECIFIED_POLYGRAPH) is False

    def test_unknown_requirement_is_not_a_barrier(self):
        assert polygraph_satisfies(PolygraphType.NONE, PolygraphType.UNKNOWN) is True


@pytest.mark.parametrize(
    ("candidate", "required", "expected"),
    [
        (ClearanceLevel.TS_SCI, ClearanceLevel.SECRET, True),
        (ClearanceLevel.TS_SCI, ClearanceLevel.TS_SCI, True),
        (ClearanceLevel.SECRET, ClearanceLevel.TS_SCI, False),
        (ClearanceLevel.NONE, ClearanceLevel.SECRET, False),
        (ClearanceLevel.NONE, ClearanceLevel.UNSPECIFIED, True),
        (ClearanceLevel.NONE, ClearanceLevel.NONE, True),
        (ClearanceLevel.TOP_SECRET, ClearanceLevel.TS_SCI, False),
    ],
)
def test_clearance_satisfies(candidate, required, expected):
    assert clearance_satisfies(candidate, required) is expected


def test_ci_holder_against_fsp_job_is_a_hard_gate():
    verdict = evaluate_eligibility(
        candidate_clearance=ClearanceLevel.TS_SCI,
        candidate_polygraph=PolygraphType.CI,
        required_clearance=ClearanceLevel.TS_SCI,
        required_polygraph=PolygraphType.FULL_SCOPE,
    )
    assert verdict.eligible is False
    assert verdict.meets_clearance is True
    assert verdict.meets_polygraph is False
    assert verdict.hard_gate is True
    assert "does NOT satisfy" in verdict.polygraph_gap


def test_ci_holder_against_ci_job_is_eligible():
    verdict = evaluate_eligibility(
        candidate_clearance=ClearanceLevel.TS_SCI,
        candidate_polygraph=PolygraphType.CI,
        required_clearance=ClearanceLevel.TS_SCI,
        required_polygraph=PolygraphType.CI,
    )
    assert verdict.eligible is True
    assert verdict.hard_gate is False


def test_ambiguous_polygraph_produces_a_note():
    verdict = evaluate_eligibility(
        candidate_clearance=ClearanceLevel.TS_SCI,
        candidate_polygraph=PolygraphType.CI,
        required_clearance=ClearanceLevel.TS_SCI,
        required_polygraph=PolygraphType.UNSPECIFIED_POLYGRAPH,
    )
    assert verdict.eligible is True
    assert any("CI and Full Scope are very different" in note for note in verdict.notes)


def test_cleared_role_without_stated_poly_prompts_the_question():
    verdict = evaluate_eligibility(
        candidate_clearance=ClearanceLevel.TS_SCI,
        candidate_polygraph=PolygraphType.CI,
        required_clearance=ClearanceLevel.TS_SCI,
        required_polygraph=PolygraphType.UNKNOWN,
    )
    assert any("no polygraph stated" in note for note in verdict.notes)
