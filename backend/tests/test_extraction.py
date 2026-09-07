"""Structured extraction: normalisers, skill mining and the rule pipeline."""

from __future__ import annotations

import pytest

from app.core.enums import (
    ClearanceLevel,
    EmploymentType,
    JobFamily,
    PolygraphType,
    RemoteStatus,
)
from app.services import normalize as nz
from app.services.extraction import merge_extractions, rule_extract
from app.services.job_families import classify_job_family
from app.services.skills import extract_skills_from_text, normalize_phrase, normalize_skill


class TestSalary:
    @pytest.mark.parametrize(
        ("text", "low", "high"),
        [
            ("Salary is $190k-$240k plus equity", 190_000, 240_000),
            ("Compensation: $190,000 - $240,000", 190_000, 240_000),
            ("The base salary range is $150K to $200K", 150_000, 200_000),
            ("Comp band: 180-220k", 180_000, 220_000),
            ("Salary $215,000 - $265,000 with a 15% bonus", 215_000, 265_000),
        ],
    )
    def test_ranges(self, text, low, high):
        salary = nz.parse_salary(text)
        assert (salary.minimum, salary.maximum) == (low, high)

    def test_single_value_with_floor_semantics(self):
        salary = nz.parse_salary("Base is $150,000 with equity")
        assert salary.minimum == 150_000
        assert salary.maximum is None

    def test_up_to_is_a_ceiling(self):
        salary = nz.parse_salary("Salary up to $250,000")
        assert salary.minimum is None
        assert salary.maximum == 250_000

    def test_unstated_compensation(self):
        assert nz.parse_salary("Competitive compensation and great benefits").specified is False

    def test_hourly_rate_is_not_an_annual_salary(self):
        assert nz.parse_salary("Pay is $85 per hour").specified is False

    def test_travel_percentage_is_not_a_salary(self):
        assert nz.parse_salary("Position involves 20% travel").specified is False

    def test_currency_detection(self):
        assert nz.parse_salary("Salary £90,000 - £110,000").currency == "GBP"


class TestEquity:
    def test_percentage_range(self):
        equity = nz.parse_equity("0.8% - 1.2% equity")
        assert equity.offered is True
        assert (equity.percent_min, equity.percent_max) == (0.8, 1.2)

    def test_mentioned_without_a_number(self):
        equity = nz.parse_equity("Salary is $190k-$240k plus equity")
        assert equity.offered is True
        assert equity.percent_min is None

    def test_explicitly_none(self):
        assert nz.parse_equity("Salary: $105,000. No equity.").offered is False

    def test_unmentioned(self):
        assert nz.parse_equity("Salary is $190k").offered is None

    def test_travel_percentage_is_not_equity(self):
        """A 20% travel figure elsewhere must not become a 20% equity grant."""
        equity = nz.parse_equity("Equity is included. Expect 20% travel.")
        assert equity.percent_min is None


class TestLifestyle:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Fully remote position", RemoteStatus.REMOTE),
            ("Hybrid, 3 days per week in office", RemoteStatus.HYBRID),
            ("Position is onsite in San Francisco", RemoteStatus.ONSITE),
            ("Work happens in a SCIF", RemoteStatus.ONSITE),
            ("Great team, great mission", RemoteStatus.UNSPECIFIED),
        ],
    )
    def test_remote_status(self, text, expected):
        assert nz.parse_remote_status(text) == expected

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("approximately 20% travel", 20),
            ("Travel: up to 50% travel", 50),
            ("Expect up to 30% travel to customer sites", 30),
            ("No travel required", 0),
            ("Occasional travel", 10),
            ("Onsite role in Denver", None),
        ],
    )
    def test_travel(self, text, expected):
        assert nz.parse_travel(text) == expected

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Expect roughly 50 hours per week", 50),
            ("40 hours per week", 40),
            ("Standard schedule", None),
        ],
    )
    def test_weekly_hours(self, text, expected):
        assert nz.parse_weekly_hours(text) == expected

    def test_on_call_and_shift_work(self):
        assert nz.parse_oncall("You'll join the on-call rotation") is True
        assert nz.parse_shift_work("Shift work may be required") is True
        assert nz.parse_nights_weekends("Nights and weekends expected") is True


class TestExperience:
    def test_range(self):
        assert nz.parse_years_experience("3-5 years full-stack engineering experience") == (
            3.0,
            5.0,
        )

    def test_plus(self):
        assert nz.parse_years_experience("5+ years of all-source experience") == (5.0, None)

    def test_absent(self):
        assert nz.parse_years_experience("Strong engineering background") == (None, None)


class TestSkillOntology:
    def test_alias_normalisation(self):
        assert normalize_skill("ReactJS") == "react"
        assert normalize_skill("GenAI") == "machine_learning" or normalize_skill("GenAI") == "llms"
        assert normalize_skill("ML") == "machine_learning"
        assert normalize_skill("Retrieval Augmented Generation") == "rag"

    def test_phrase_aliases(self):
        assert normalize_phrase("CI Poly") == "Counterintelligence Polygraph"
        assert normalize_phrase("FSP") == "Full Scope Polygraph"

    def test_strips_experience_prefix(self):
        assert normalize_skill("5+ years of TypeScript") == "typescript"

    def test_mining_from_prose(self):
        skills = extract_skills_from_text(
            "Experience with Python, React, TypeScript, LLMs and customer-facing delivery."
        )
        assert {"python", "react", "typescript", "llms", "customer_facing"} <= set(skills)

    def test_apostrophes_do_not_create_false_positives(self):
        """ "We're" must not yield "re" -> reverse engineering."""
        assert "reverse_engineering" not in extract_skills_from_text("We're looking for someone.")

    def test_state_abbreviation_is_not_a_medical_licence(self):
        assert "md_license" not in extract_skills_from_text("Located in Annapolis Junction, MD.")

    def test_c_does_not_match_inside_cpp(self):
        skills = extract_skills_from_text("Strong C++ background.")
        assert "cpp" in skills
        assert "c" not in skills

    def test_ts_sci_is_not_typescript(self):
        assert "typescript" not in extract_skills_from_text("Requires an active TS/SCI clearance.")


class TestJobFamily:
    @pytest.mark.parametrize(
        ("title", "expected"),
        [
            ("Forward Deployed Engineer", JobFamily.FORWARD_DEPLOYED_ENGINEER),
            ("Forward-Deployed AI Engineer", JobFamily.FORWARD_DEPLOYED_ENGINEER),
            ("Senior AI Engineer", JobFamily.AI_ENGINEER),
            ("Machine Learning Engineer", JobFamily.ML_ENGINEER),
            ("Malware Reverse Engineer", JobFamily.MALWARE_REVERSE_ENGINEER),
            ("Vulnerability Researcher", JobFamily.VULNERABILITY_RESEARCHER),
            ("Chief of Staff", JobFamily.CHIEF_OF_STAFF),
            ("Federal Solutions Engineer", JobFamily.SOLUTIONS_ENGINEER),
            ("Computational Biology ML Scientist", JobFamily.COMPUTATIONAL_BIOLOGY_ML),
            ("Widget Coordinator", JobFamily.OTHER),
        ],
    )
    def test_classification(self, title, expected):
        assert classify_job_family(title, "").family == expected

    def test_title_outranks_body(self):
        match = classify_job_family("AI Engineer", "You'll work alongside our reverse engineers.")
        assert match.family == JobFamily.AI_ENGINEER


class TestRulePipeline:
    def test_acceptance_example(self, fde_text):
        """The spec's §19 example must extract exactly as documented."""
        result = rule_extract(fde_text)

        assert result.title == "Forward Deployed Engineer"
        assert result.compensation.salary_min == 190_000
        assert result.compensation.salary_max == 240_000
        assert result.compensation.equity is True
        assert result.requirements.security_clearance == ClearanceLevel.TS_SCI
        assert result.requirements.polygraph_requirement == PolygraphType.UNKNOWN
        assert {"python", "react", "typescript", "llms", "customer_facing"} <= set(
            result.requirements.required_skills
        )
        assert result.requirements.required_years_experience == 3.0
        assert result.requirements.preferred_years_experience == 5.0
        assert result.lifestyle.remote_status == RemoteStatus.ONSITE
        assert result.lifestyle.location == "San Francisco"
        assert result.lifestyle.travel_percent == 20
        assert result.characteristics.job_family == JobFamily.FORWARD_DEPLOYED_ENGINEER

    def test_content_free_message_extracts_almost_nothing(self):
        result = rule_extract(
            "Hi! I think you'd be a great fit for an exciting opportunity. "
            "Competitive compensation. Free for a quick chat?"
        )
        assert result.compensation.specified is False
        assert result.requirements.security_clearance == ClearanceLevel.UNSPECIFIED
        assert result.lifestyle.remote_status == RemoteStatus.UNSPECIFIED

    def test_confidence_marks_absent_fields(self, fde_text):
        result = rule_extract(fde_text)
        assert result.confidence["salary_min"].value == "high"
        assert result.confidence["polygraph_requirement"].value == "absent"

    def test_employment_type(self):
        assert rule_extract("This is a full-time role").employment_type == EmploymentType.FULL_TIME
        assert rule_extract("6 month contract").employment_type == EmploymentType.CONTRACT

    def test_preferred_versus_required_skills(self):
        result = rule_extract(
            "You will use Python daily. Experience with Kubernetes is a nice-to-have."
        )
        assert "python" in result.requirements.required_skills
        assert "kubernetes" in result.requirements.preferred_skills


class TestMerge:
    def test_llm_cannot_override_deterministic_salary(self, fde_text):
        """The model does not get to rewrite money or eligibility fields."""
        rules = rule_extract(fde_text)
        merged = merge_extractions(rules, {"company": "Nightingale", "required_skills": ["Go"]})

        assert merged.compensation.salary_min == 190_000
        assert merged.compensation.salary_max == 240_000
        assert merged.requirements.security_clearance == ClearanceLevel.TS_SCI
        assert merged.company == "Nightingale"
        assert "go" in merged.requirements.required_skills
        assert merged.extraction_method == "llm+rules"

    def test_llm_fills_only_empty_fields(self):
        rules = rule_extract("Company: Acme Corp\nSalary: $200,000")
        merged = merge_extractions(rules, {"company": "Wrong Corp", "required_skills": []})
        assert merged.company == "Acme Corp"

    def test_no_llm_output_is_a_no_op(self, fde_text):
        rules = rule_extract(fde_text)
        assert merge_extractions(rules, None) is rules
        assert merge_extractions(rules, {}) is rules
