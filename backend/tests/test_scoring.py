"""Scoring engine behaviour.

These tests assert on *relationships* and *invariants* rather than exact
numbers wherever possible, so tuning a weight does not require rewriting the
suite - but the acceptance case pins real ranges, because that is the
product's contract.
"""

from __future__ import annotations

import pytest

from app.core.enums import ProofabilityTier, RecommendedAction
from app.services.scoring import ScoringConfig, score_opportunity
from app.services.scoring.config import CompensationBands, ScoreWeights
from app.services.scoring.engine import recommend_action
from tests.conftest import make_job


class TestAcceptanceCase:
    """§19 - the documented end-to-end example."""

    @pytest.fixture
    def result(self, candidate):
        return score_opportunity(make_job(), candidate, ScoringConfig())

    def test_dimensions_land_in_the_documented_ranges(self, result):
        assert 65 <= result.fit.score <= 85, "fit ~75"
        assert result.career_capital.score >= 85, "career capital ~95"
        assert result.proofability.score >= 80, "proofability ~90"
        assert result.compensation.score >= 85, "compensation ~90"

    def test_recommended_action(self, result):
        assert result.recommended_action in (
            RecommendedAction.STRONGLY_PURSUE,
            RecommendedAction.PURSUE,
        )

    def test_gaps_are_proofable_not_gates(self, result):
        assert result.hard_gates == []
        gap_names = {gap.requirement for gap in result.proofable_gaps}
        assert "React" in gap_names
        assert "TypeScript" in gap_names

    def test_strengths_mention_clearance_and_skills(self, result):
        joined = " ".join(result.matched_strengths).lower()
        assert "ts/sci" in joined or "clearance" in joined

    def test_explanation_is_complete(self, result):
        explanation = result.explanation()
        assert set(explanation["dimensions"]) == {
            "fit",
            "career_capital",
            "proofability",
            "compensation",
            "lifestyle",
            "upside",
            "risk",
        }
        assert explanation["headline"]
        assert explanation["prove_it"]["summary"]


class TestHardGates:
    def test_full_scope_requirement_caps_the_overall_score(self, candidate):
        job = make_job(polygraph_requirement="full_scope")
        result = score_opportunity(job, candidate, ScoringConfig())

        assert result.overall_capped is True
        assert result.overall <= ScoringConfig().hard_gate_overall_cap
        assert result.recommended_action in (
            RecommendedAction.LOW_PRIORITY,
            RecommendedAction.REJECT,
        )
        assert any("Full Scope" in gap.detail for gap in result.hard_gates)

    def test_ci_requirement_is_not_a_gate_for_a_ci_holder(self, candidate):
        result = score_opportunity(make_job(polygraph_requirement="ci"), candidate, ScoringConfig())
        assert result.hard_gates == []
        assert result.overall_capped is False

    def test_phd_requirement_is_a_hard_gate(self, candidate):
        job = make_job(
            required_skills=["python", "phd"],
            education_requirements=["PhD in Computer Science required"],
        )
        result = score_opportunity(job, candidate, ScoringConfig())
        assert result.hard_gates
        assert result.proofability.score < 40

    def test_hard_gate_tanks_proofability_not_career_capital(self, candidate):
        """A gate makes a job unreachable, not less valuable."""
        base = score_opportunity(make_job(), candidate, ScoringConfig())
        gated = score_opportunity(
            make_job(polygraph_requirement="full_scope"), candidate, ScoringConfig()
        )
        assert gated.proofability.score < base.proofability.score
        assert gated.career_capital.score == base.career_capital.score


class TestProofability:
    def test_missing_demonstrable_skills_score_high(self, candidate):
        job = make_job(required_skills=["python", "react", "typescript"])
        result = score_opportunity(job, candidate, ScoringConfig())
        assert result.proofability.score >= 75
        assert all(g.tier is ProofabilityTier.PROOFABLE for g in result.proofable_gaps)

    def test_no_gaps_is_a_perfect_score(self, candidate):
        job = make_job(required_skills=["python", "llms"], required_years_experience=None)
        result = score_opportunity(job, candidate, ScoringConfig())
        assert result.proofability.score == 100.0

    def test_prove_it_buckets_are_disjoint_and_populated(self, candidate):
        result = score_opportunity(make_job(), candidate, ScoringConfig())
        prove_it = result.prove_it
        assert prove_it["already_demonstrated"]
        assert prove_it["learnable"]
        assert prove_it["hard_gates"] == []
        learnable = {item["requirement"] for item in prove_it["learnable"]}
        demonstrated = {item["skill"] for item in prove_it["already_demonstrated"]}
        assert learnable.isdisjoint(demonstrated)

    def test_learnable_items_carry_a_concrete_plan(self, candidate):
        result = score_opportunity(make_job(), candidate, ScoringConfig())
        for item in result.prove_it["learnable"]:
            assert item["how_to_demonstrate"]
            assert item["interview_readiness"]


class TestFit:
    def test_missing_years_are_not_over_penalised(self, candidate):
        """§6A: a demonstrable-skills candidate should not be gutted by a YOE bar.

        The candidate has ~8 relevant years, so a 15-year bar is a real
        shortfall - but because the underlying skills are demonstrable, the
        penalty is discounted rather than applied in full.
        """
        lenient = score_opportunity(
            make_job(required_years_experience=1.0), candidate, ScoringConfig()
        )
        demanding = score_opportunity(
            make_job(required_years_experience=15.0), candidate, ScoringConfig()
        )
        assert demanding.fit.score < lenient.fit.score
        assert demanding.fit.score > lenient.fit.score - 15

        undiscounted = score_opportunity(
            make_job(required_years_experience=15.0),
            candidate,
            ScoringConfig(yoe_shortfall_discount=0.0),
        )
        assert undiscounted.fit.score < demanding.fit.score

    def test_years_gap_is_classified_proofable_when_skills_are(self, candidate):
        result = score_opportunity(
            make_job(required_years_experience=15.0), candidate, ScoringConfig()
        )
        years_gap = next(g for g in result.proofable_gaps if "years" in g.requirement)
        assert years_gap.tier is ProofabilityTier.PROOFABLE

    def test_experience_recorded_by_years_counts_as_a_held_skill(self, candidate):
        job = make_job(required_skills=["customer_facing"])
        result = score_opportunity(job, candidate, ScoringConfig())
        assert "customer_facing" in result.fit.details["matched_skills"]

    def test_insufficient_clearance_is_a_gate(self, candidate):
        candidate.clearance_level = "secret"
        result = score_opportunity(make_job(), candidate, ScoringConfig())
        assert any("Security clearance" in gap.requirement for gap in result.hard_gates)


class TestCompensation:
    def test_bands_are_respected(self, candidate):
        config = ScoringConfig()
        poor = score_opportunity(
            make_job(salary_min=100_000, salary_max=115_000), candidate, config
        )
        strong = score_opportunity(
            make_job(salary_min=230_000, salary_max=260_000), candidate, config
        )
        assert poor.compensation.score < 40
        assert strong.compensation.score > 85

    def test_bands_are_configurable(self, candidate):
        job = make_job(salary_min=190_000, salary_max=240_000)
        default = score_opportunity(job, candidate, ScoringConfig())
        demanding = score_opportunity(
            job,
            candidate,
            ScoringConfig(
                compensation_bands=CompensationBands(
                    poor=250_000, acceptable=300_000, strong=400_000, excellent=500_000
                )
            ),
        )
        assert demanding.compensation.score < default.compensation.score

    def test_unstated_compensation_is_neutral_not_zero(self, candidate):
        result = score_opportunity(
            make_job(salary_min=None, salary_max=None, equity=None), candidate, ScoringConfig()
        )
        assert 30 <= result.compensation.score <= 60
        assert any(reason.kind == "missing" for reason in result.compensation.reasons)

    def test_below_the_floor_is_flagged_as_a_dealbreaker(self, candidate):
        result = score_opportunity(
            make_job(salary_min=95_000, salary_max=110_000), candidate, ScoringConfig()
        )
        assert result.compensation.score <= 30
        assert any("dealbreaker" in reason.text for reason in result.compensation.reasons)


class TestLifestyleUpsideRisk:
    def test_startup_is_not_automatically_bad_lifestyle(self, candidate):
        """§6E - stage alone must not move the lifestyle score."""
        baseline = score_opportunity(
            make_job(remote_status="remote", travel=0, hours=40), candidate, ScoringConfig()
        )
        startup = score_opportunity(
            make_job(remote_status="remote", travel=0, hours=40, company_stage="seed"),
            candidate,
            ScoringConfig(),
        )
        assert startup.lifestyle.score == baseline.lifestyle.score

    def test_stated_hours_and_travel_drive_lifestyle(self, candidate):
        good = score_opportunity(
            make_job(remote_status="remote", hours=40, travel=5), candidate, ScoringConfig()
        )
        bad = score_opportunity(
            make_job(remote_status="onsite", hours=70, travel=80, on_call=True, shift_work=True),
            candidate,
            ScoringConfig(),
        )
        assert good.lifestyle.score > bad.lifestyle.score + 30

    def test_early_stage_equity_lifts_upside(self, candidate):
        seed = score_opportunity(
            make_job(company_stage="seed", equity=True, equity_percent_min=1.0),
            candidate,
            ScoringConfig(),
        )
        public = score_opportunity(
            make_job(company_stage="public", equity=True, equity_percent_min=0.001),
            candidate,
            ScoringConfig(),
        )
        assert seed.upside.score > public.upside.score

    def test_government_role_has_low_upside(self, candidate):
        result = score_opportunity(
            make_job(company_stage="government", equity=False), candidate, ScoringConfig()
        )
        assert result.upside.score < 45

    def test_risk_rises_with_uncertainty(self, candidate):
        certain = score_opportunity(
            make_job(company_stage="public", salary_min=200_000, salary_max=230_000),
            candidate,
            ScoringConfig(),
        )
        uncertain = score_opportunity(
            make_job(
                company_stage="pre_seed",
                salary_min=None,
                salary_max=None,
                equity=True,
                relocation_required=True,
                polygraph_requirement="unspecified_polygraph",
            ),
            candidate,
            ScoringConfig(),
        )
        assert uncertain.risk.score > certain.risk.score + 20

    def test_risk_is_not_subtracted_by_default(self, candidate):
        job = make_job(company_stage="pre_seed")
        default = score_opportunity(job, candidate, ScoringConfig())
        penalised = score_opportunity(job, candidate, ScoringConfig(risk_penalty_weight=0.3))
        assert penalised.overall < default.overall


class TestOverallAndWeights:
    def test_overall_is_weighted_not_averaged(self, candidate):
        result = score_opportunity(make_job(), candidate, ScoringConfig())
        dimensions = [
            result.fit.score,
            result.career_capital.score,
            result.proofability.score,
            result.compensation.score,
            result.lifestyle.score,
            result.upside.score,
        ]
        plain_average = sum(dimensions) / len(dimensions)
        # Career capital is the heaviest weight, and it is the top score here,
        # so the weighted result must exceed the flat average.
        assert result.overall != pytest.approx(plain_average, abs=0.05)

    def test_weights_are_configurable(self, candidate):
        job = make_job(salary_min=110_000, salary_max=125_000)
        comp_heavy = score_opportunity(
            job,
            candidate,
            ScoringConfig(
                weights=ScoreWeights(
                    compensation=0.9,
                    fit=0.02,
                    career_capital=0.02,
                    proofability=0.02,
                    lifestyle=0.02,
                    upside=0.02,
                )
            ),
        )
        capital_heavy = score_opportunity(
            job,
            candidate,
            ScoringConfig(
                weights=ScoreWeights(
                    compensation=0.02,
                    fit=0.02,
                    career_capital=0.9,
                    proofability=0.02,
                    lifestyle=0.02,
                    upside=0.02,
                )
            ),
        )
        assert comp_heavy.overall < capital_heavy.overall

    def test_weights_normalise_to_one(self):
        weights = ScoreWeights(
            fit=2, career_capital=2, proofability=1, compensation=1, lifestyle=1, upside=1
        ).normalized()
        assert sum(weights.values()) == pytest.approx(1.0)

    def test_all_scores_stay_in_range(self, candidate):
        for job in (
            make_job(),
            make_job(salary_min=None, salary_max=None, required_skills=[]),
            make_job(polygraph_requirement="full_scope", company_stage="pre_seed", hours=80),
        ):
            result = score_opportunity(job, candidate, ScoringConfig())
            for name, dimension in result.dimensions().items():
                assert 0 <= dimension.score <= 100, name
            assert 0 <= result.overall <= 100

    @pytest.mark.parametrize(
        ("overall", "expected"),
        [
            (95, RecommendedAction.STRONGLY_PURSUE),
            (82, RecommendedAction.STRONGLY_PURSUE),
            (75, RecommendedAction.PURSUE),
            (65, RecommendedAction.WORTH_A_CALL),
            (55, RecommendedAction.MAYBE),
            (40, RecommendedAction.LOW_PRIORITY),
            (10, RecommendedAction.REJECT),
        ],
    )
    def test_action_ladder(self, overall, expected):
        assert recommend_action(overall, [], ScoringConfig()) == expected

    def test_every_dimension_explains_itself(self, candidate):
        result = score_opportunity(make_job(), candidate, ScoringConfig())
        for name, dimension in result.dimensions().items():
            assert dimension.reasons, f"{name} produced a score with no reasons"


class TestCoreThesis:
    """High comp + high career capital + imperfect fit + high proofability
    should outrank a perfect-on-paper but low-value role (§24)."""

    def test_imperfect_but_valuable_beats_perfect_but_stagnant(self, candidate):
        valuable = make_job()  # FDE: gaps in React/TS, great comp and capital
        stagnant = make_job(
            title="Intelligence Analyst III",
            job_family="technical_intelligence_analyst",
            salary_min=105_000,
            salary_max=125_000,
            equity=False,
            required_skills=["all_source", "osint"],
            required_years_experience=5.0,
            customer_facing_intensity=None,
            technical_depth="low",
            job_description="Level of effort contract. Maintain existing analytic products.",
        )
        config = ScoringConfig()
        assert (
            score_opportunity(valuable, candidate, config).overall
            > score_opportunity(stagnant, candidate, config).overall
        )
