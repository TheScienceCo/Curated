"""Missing-information detection and recruiter response drafting."""

from __future__ import annotations

import pytest

from app.core.enums import DraftIntent, DraftTone
from app.services.missing_info import blocking_missing_fields, detect_missing_information
from app.services.response_draft import (
    choose_intent,
    draft_clearance_clarification,
    draft_missing_info_response,
    generate_response_draft,
)
from app.services.scoring import ScoringConfig, score_opportunity
from tests.conftest import make_job


class TestMissingInformation:
    def test_content_free_message_is_missing_everything_important(self):
        job = make_job(
            salary_min=None,
            salary_max=None,
            hours=None,
            travel=None,
            remote_status="unspecified",
            location=None,
            security_clearance="unspecified",
            polygraph_requirement="unknown",
            equity=None,
            bonus=None,
        )
        fields = {field.field for field in detect_missing_information(job)}
        assert {
            "compensation",
            "hours",
            "remote_status",
            "location",
            "travel",
            "security_clearance",
            "equity",
            "bonus",
            "interview_process",
        } <= fields

    def test_priority_order_matches_the_spec(self):
        job = make_job(
            salary_min=None,
            salary_max=None,
            hours=None,
            travel=None,
            remote_status="unspecified",
            location=None,
        )
        missing = detect_missing_information(job)
        priorities = [field.priority for field in missing]
        assert priorities == sorted(priorities)
        assert missing[0].field == "compensation"

    def test_complete_posting_leaves_only_the_interview_process(self):
        job = make_job(
            hours=40,
            travel=10,
            remote_status="remote",
            location="Remote",
            security_clearance="none",
            polygraph_requirement="none",
            equity=True,
            equity_percent_min=0.1,
            bonus="10% annual",
        )
        fields = [field.field for field in detect_missing_information(job)]
        assert fields == ["interview_process"]

    def test_ambiguous_polygraph_is_flagged_with_the_ci_versus_fsp_warning(self):
        job = make_job(polygraph_requirement="unspecified_polygraph")
        poly = next(
            f for f in detect_missing_information(job) if f.field == "polygraph_requirement"
        )
        assert "CI" in poly.question and "full scope" in poly.question.lower()
        assert "interchangeable" in poly.rationale

    def test_cleared_role_with_no_poly_stated_still_asks(self):
        job = make_job(security_clearance="ts_sci", polygraph_requirement="unknown")
        fields = {f.field for f in detect_missing_information(job)}
        assert "polygraph_requirement" in fields

    def test_unquantified_equity_is_flagged(self):
        job = make_job(equity=True, equity_percent_min=None)
        equity = next(f for f in detect_missing_information(job) if f.field == "equity_percent")
        assert "percentage" in equity.question

    def test_blocking_fields_are_the_top_five_priorities(self):
        job = make_job(salary_min=None, salary_max=None, hours=None)
        blocking = blocking_missing_fields(detect_missing_information(job))
        assert all(field.priority <= 5 for field in blocking)


class TestDrafts:
    def test_missing_info_draft_matches_the_spec_tone(self):
        job = make_job(
            recruiter_name="Dana Whitfield",
            salary_min=None,
            salary_max=None,
            hours=None,
            travel=None,
            remote_status="unspecified",
            location=None,
            security_clearance="unspecified",
        )
        draft = draft_missing_info_response(
            job, detect_missing_information(job), candidate_name="Eric"
        )
        body = draft.body

        assert body.startswith("Hi Dana,")
        assert "Thanks for reaching out" in body
        assert "compensation" in body.lower() or "salary range" in body.lower()
        assert "weekly hours" in body.lower()
        assert "remote" in body.lower()
        assert "travel" in body.lower()
        assert "clearance" in body.lower()
        assert body.rstrip().endswith("Eric")

    def test_draft_avoids_slang_unless_humorous_is_selected(self):
        job = make_job(salary_min=None, salary_max=None)
        for tone in (DraftTone.PROFESSIONAL, DraftTone.WARM, DraftTone.DIRECT):
            body = draft_missing_info_response(
                job, detect_missing_information(job), tone=tone
            ).body.lower()
            assert "scratch" not in body
            assert "kinda" not in body

    def test_greeting_falls_back_when_the_recruiter_is_unknown(self):
        job = make_job(recruiter_name=None, salary_min=None, salary_max=None)
        draft = draft_missing_info_response(job, detect_missing_information(job))
        assert draft.body.startswith("Hi there,")

    def test_clearance_clarification_asks_all_four_questions(self):
        draft = draft_clearance_clarification(make_job(), candidate_name="Eric")
        body = draft.body.lower()
        assert "ts/sci" in body
        assert "ci polygraph" in body
        assert "full scope" in body
        assert "sponsor" in body

    def test_questions_asked_is_populated(self):
        job = make_job(salary_min=None, salary_max=None, hours=None)
        draft = draft_missing_info_response(job, detect_missing_information(job))
        assert draft.questions_asked


class TestIntentSelection:
    def test_ambiguous_polygraph_wins_over_everything(self, candidate):
        job = make_job(polygraph_requirement="unspecified_polygraph")
        result = score_opportunity(job, candidate, ScoringConfig())
        missing = detect_missing_information(job)
        assert choose_intent(job, result, missing) is DraftIntent.CLEARANCE_CLARIFICATION

    def test_weak_opportunity_gets_a_polite_decline(self, candidate):
        job = make_job(
            title="Documentation Coordinator III",
            salary_min=70_000,
            salary_max=85_000,
            equity=False,
            job_family="technical_program_seta",
            technical_depth="low",
            ownership_level="low",
            customer_facing_intensity=None,
            company_stage="government",
            required_skills=["program_management", "govt_contracting"],
            required_years_experience=10.0,
            remote_status="onsite",
            location="Huntsville",
            hours=45,
            travel=0,
            job_description=(
                "Level of effort contract supporting an existing program. Maintain existing "
                "products and respond to customer RFIs via the ticket queue."
            ),
        )
        result = score_opportunity(job, candidate, ScoringConfig())
        missing = detect_missing_information(job)
        draft = generate_response_draft(job, result, missing, candidate_name="Eric", polish=False)
        assert draft.intent is DraftIntent.POLITE_DECLINE
        assert "pass on" in draft.body

    def test_strong_and_complete_opportunity_asks_to_schedule(self, candidate):
        job = make_job(
            hours=40,
            travel=10,
            remote_status="remote",
            location="Remote",
            equity=True,
            equity_percent_min=0.2,
            bonus="10%",
            polygraph_requirement="ci",
        )
        result = score_opportunity(job, candidate, ScoringConfig())
        missing = detect_missing_information(job)
        draft = generate_response_draft(job, result, missing, candidate_name="Eric", polish=False)
        assert draft.intent is DraftIntent.ENTHUSIASTIC_SCHEDULE
        assert "calendar" in draft.body.lower()

    def test_incomplete_message_asks_for_the_missing_pieces(self, candidate):
        job = make_job(
            salary_min=None,
            salary_max=None,
            hours=None,
            travel=None,
            remote_status="unspecified",
            location=None,
        )
        result = score_opportunity(job, candidate, ScoringConfig())
        missing = detect_missing_information(job)
        draft = generate_response_draft(job, result, missing, candidate_name="Eric", polish=False)
        assert draft.intent is DraftIntent.REQUEST_MISSING_INFO


class TestPolishGuardrails:
    """The model may improve the prose; it may not drop the questions."""

    class _DroppingProvider:
        name = "test"
        available = True

        def complete_text(self, request):
            return "Hi! Sounds great, when can we chat? " + "x" * 40

    class _GoodProvider:
        name = "test"
        available = True

        def __init__(self, text):
            self._text = text

        def complete_text(self, request):
            return self._text

    def test_polish_is_rejected_when_it_drops_a_required_question(self, candidate):
        job = make_job(salary_min=None, salary_max=None, hours=None)
        result = score_opportunity(job, candidate, ScoringConfig())
        missing = detect_missing_information(job)
        draft = generate_response_draft(
            job,
            result,
            missing,
            candidate_name="Eric",
            provider=self._DroppingProvider(),
            polish=True,
        )
        assert draft.generated_by == "template"

    def test_polish_is_accepted_when_the_questions_survive(self, candidate):
        job = make_job(salary_min=None, salary_max=None, hours=None)
        result = score_opportunity(job, candidate, ScoringConfig())
        missing = detect_missing_information(job)
        template = generate_response_draft(
            job, result, missing, candidate_name="Eric", polish=False
        )
        polished_text = (
            "Hi there,\n\nThanks for reaching out. Could you share the base salary range for "
            "the role, the expected weekly hours and work schedule, the equity grant size "
            "(percentage and current valuation), and whether a polygraph is required and at "
            "which scope?\n\nEric"
        )
        draft = generate_response_draft(
            job,
            result,
            missing,
            candidate_name="Eric",
            provider=self._GoodProvider(polished_text),
            polish=True,
        )
        assert draft.generated_by == "llm-polished"
        assert draft.questions_asked == template.questions_asked

    def test_provider_failure_falls_back_to_the_template(self, candidate):
        class _Failing:
            name = "test"
            available = True

            def complete_text(self, request):
                raise RuntimeError("provider exploded")

        job = make_job(salary_min=None, salary_max=None)
        result = score_opportunity(job, candidate, ScoringConfig())
        missing = detect_missing_information(job)
        draft = generate_response_draft(job, result, missing, provider=_Failing(), polish=True)
        assert draft.generated_by == "template"
        assert draft.body


@pytest.mark.parametrize("tone", list(DraftTone))
def test_every_tone_produces_a_usable_draft(tone, candidate):
    job = make_job(salary_min=None, salary_max=None, recruiter_name="Dana")
    result = score_opportunity(job, candidate, ScoringConfig())
    missing = detect_missing_information(job)
    draft = generate_response_draft(
        job, result, missing, tone=tone, candidate_name="Eric", polish=False
    )
    assert len(draft.body) > 80
    assert "Dana" in draft.body
