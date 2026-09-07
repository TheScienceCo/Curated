"""Résumé matching, the equity calculator, and the LLM abstraction."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.errors import LlmError
from app.db.models import ResumeDocument
from app.llm.base import parse_json_payload
from app.llm.factory import build_provider
from app.services.equity import calculate_equity
from app.services.resume_match import cosine_similarity, rank_resumes, score_resume_for_job
from tests.conftest import make_job


def _resume(title: str, text: str, families: list[str], active: bool = True) -> ResumeDocument:
    from app.services.skills import extract_skills_from_text

    return ResumeDocument(
        id=title.lower().replace(" ", "-"),
        candidate_id="c1",
        title=title,
        raw_text=text,
        parsed_sections={},
        target_families=families,
        skills=extract_skills_from_text(text),
        active=active,
        embedding=None,
    )


FDE_RESUME = _resume(
    "Forward Deployed AI Resume",
    "TS/SCI with CI poly. Built agentic AI with RAG, FastAPI, Python, embeddings and "
    "TypeScript. Owned customer-facing delivery with government customers end to end. HUMINT.",
    ["forward_deployed_engineer", "ai_engineer"],
)

SCIENCE_RESUME = _resume(
    "Intelligence / Science Resume",
    "All-source intelligence, HUMINT, OSINT, targeting. Biochemistry, stem cells, "
    "tissue engineering, LC-MS wet lab work. Mandarin.",
    ["technical_intelligence_analyst"],
)


class TestResumeMatching:
    def test_targeted_variant_wins(self):
        job = make_job()
        ranked = rank_resumes([SCIENCE_RESUME, FDE_RESUME], job)
        assert ranked[0].title == "Forward Deployed AI Resume"
        assert ranked[0].score > ranked[1].score

    def test_highlights_lead_with_the_clearance_on_a_cleared_role(self):
        match = score_resume_for_job(FDE_RESUME, make_job())
        assert match.highlight[0] == "TS/SCI"
        assert "Counterintelligence (CI) Polygraph" in match.highlight

    def test_highlights_only_contain_things_the_resume_says(self):
        """§11: never invent experience."""
        match = score_resume_for_job(SCIENCE_RESUME, make_job())
        text = SCIENCE_RESUME.raw_text.lower()
        for item in match.highlight:
            token = item.split()[0].lower().strip(",.")
            assert token in text or item in ("Customer-facing delivery experience",)

    def test_missing_keywords_are_reported_not_inserted(self):
        match = score_resume_for_job(SCIENCE_RESUME, make_job())
        assert "python" in match.missing_keywords
        assert "python" not in SCIENCE_RESUME.raw_text.lower()

    def test_de_emphasis_suggests_off_topic_content(self):
        match = score_resume_for_job(SCIENCE_RESUME, make_job())
        assert any(
            "Biochem" in item or "LC-MS" in item or "Stem" in item for item in match.de_emphasize
        )

    def test_de_emphasis_never_touches_required_skills(self):
        job = make_job(required_skills=["biochemistry", "python"])
        match = score_resume_for_job(SCIENCE_RESUME, job)
        assert "Biochemistry" not in match.de_emphasize

    def test_inactive_variant_is_penalised(self):
        inactive = _resume(
            "Old FDE Resume", FDE_RESUME.raw_text, ["forward_deployed_engineer"], active=False
        )
        job = make_job()
        assert (
            score_resume_for_job(inactive, job).score < score_resume_for_job(FDE_RESUME, job).score
        )

    def test_summary_is_honest_about_gaps(self):
        match = score_resume_for_job(FDE_RESUME, make_job())
        assert "do not have" in match.summary or not match.missing_keywords

    def test_rationale_explains_the_ranking(self):
        match = score_resume_for_job(FDE_RESUME, make_job())
        assert any("required skills" in reason for reason in match.rationale)


class TestCosineSimilarity:
    def test_identical_vectors(self):
        assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_missing_or_mismatched_vectors_return_none(self):
        assert cosine_similarity(None, [1.0]) is None
        assert cosine_similarity([1.0], None) is None
        assert cosine_similarity([1.0, 2.0], [1.0]) is None
        assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) is None


class TestEquityCalculator:
    def test_documented_example(self):
        """§14 - 0.25% at 40% dilution."""
        analysis = calculate_equity(equity_percent=0.25, dilution_percent=40)
        assert analysis.post_dilution_percent == pytest.approx(0.15)

        values = {s.label: s.gross_value for s in analysis.scenarios}
        assert values["$100M"] == pytest.approx(150_000)
        assert values["$500M"] == pytest.approx(750_000)
        assert values["$1B"] == pytest.approx(1_500_000)
        assert values["$5B"] == pytest.approx(7_500_000)

    def test_zero_dilution_keeps_the_full_stake(self):
        analysis = calculate_equity(equity_percent=1.0, dilution_percent=0)
        assert analysis.post_dilution_percent == pytest.approx(1.0)

    def test_strike_cost_is_subtracted_from_net(self):
        analysis = calculate_equity(
            equity_percent=1.0, dilution_percent=0, strike_price=0.5, shares=100_000
        )
        scenario = next(s for s in analysis.scenarios if s.exit_valuation == 100_000_000)
        assert scenario.gross_value == pytest.approx(1_000_000)
        assert scenario.net_value == pytest.approx(950_000)

    def test_net_value_never_goes_negative(self):
        analysis = calculate_equity(
            equity_percent=0.001, dilution_percent=0, strike_price=100.0, shares=100_000
        )
        assert all(s.net_value >= 0 for s in analysis.scenarios)

    def test_current_paper_value(self):
        analysis = calculate_equity(
            equity_percent=0.5, dilution_percent=40, current_valuation=80_000_000
        )
        assert analysis.current_paper_value == pytest.approx(400_000)

    def test_custom_exit_valuations(self):
        analysis = calculate_equity(
            equity_percent=1.0, dilution_percent=0, exit_valuations=[50_000_000]
        )
        assert len(analysis.scenarios) == 1
        assert analysis.scenarios[0].label == "$50M"

    def test_everything_is_labelled_hypothetical(self):
        assert "hypothetical" in calculate_equity(equity_percent=1.0).disclaimer

    @pytest.mark.parametrize(("equity", "dilution"), [(-1.0, 40), (1.0, 100), (1.0, -5)])
    def test_invalid_input_raises(self, equity, dilution):
        with pytest.raises(ValueError):
            calculate_equity(equity_percent=equity, dilution_percent=dilution)


class TestLlmAbstraction:
    def test_mock_provider_is_unavailable_by_design(self):
        provider = build_provider(Settings(llm_provider="mock"))
        assert provider.name == "mock"
        assert provider.available is False

    def test_provider_selection_by_setting(self):
        anthropic = build_provider(Settings(llm_provider="anthropic", anthropic_api_key="k"))
        openai = build_provider(Settings(llm_provider="openai", openai_api_key="k"))
        assert anthropic.name == "anthropic" and anthropic.available
        assert openai.name == "openai" and openai.available

    def test_provider_without_a_key_reports_unavailable(self):
        assert build_provider(Settings(llm_provider="anthropic")).available is False

    @pytest.mark.parametrize(
        "raw",
        [
            '{"a": 1}',
            '```json\n{"a": 1}\n```',
            '```\n{"a": 1}\n```',
            'Sure, here you go: {"a": 1}',
            '{"a": 1}\n\nHope that helps!',
        ],
    )
    def test_json_payload_parsing_tolerates_model_habits(self, raw):
        assert parse_json_payload(raw) == {"a": 1}

    @pytest.mark.parametrize("raw", ["not json at all", "[1, 2, 3]", ""])
    def test_unparseable_payloads_raise(self, raw):
        with pytest.raises(LlmError):
            parse_json_payload(raw)

    def test_retries_then_gives_up(self):
        from app.llm.base import LlmProvider, LlmRequest

        class _AlwaysFails(LlmProvider):
            name = "flaky"
            attempts = 0

            def _invoke(self, request):
                type(self).attempts += 1
                raise RuntimeError("boom")

        provider = _AlwaysFails(max_retries=2)
        with pytest.raises(LlmError):
            provider.complete(LlmRequest(system="s", user="u"))
        assert _AlwaysFails.attempts == 2

    def test_extraction_degrades_gracefully_when_the_provider_fails(self, fde_text):
        """A dead provider must not break analysis - rules carry the load."""
        from app.services.extraction import extract

        class _Broken:
            name = "broken"
            available = True

            def complete_json(self, request):
                raise RuntimeError("provider down")

        result = extract(fde_text, provider=_Broken())
        assert result.compensation.salary_min == 190_000
        assert result.extraction_method == "rules"


def test_a_polygraph_that_does_not_meet_the_requirement_is_not_highlighted():
    """Leading with a CI poly on a full-scope role invites a rejection."""
    match = score_resume_for_job(FDE_RESUME, make_job(polygraph_requirement="full_scope"))
    assert not any("Polygraph" in item for item in match.highlight)


def test_a_polygraph_that_meets_the_requirement_is_highlighted():
    match = score_resume_for_job(FDE_RESUME, make_job(polygraph_requirement="ci"))
    assert any("Counterintelligence" in item for item in match.highlight)
