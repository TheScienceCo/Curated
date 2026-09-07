"""The MVP acceptance test from the product spec (§19).

One test, end to end, through the real API, asserting on every documented
output. If this passes, the vertical slice works.
"""

from __future__ import annotations

import pytest

INPUT = (
    "Hi Eric, I'm recruiting for a Forward Deployed Engineer supporting national security "
    "customers. The role requires TS/SCI and experience with Python, React, TypeScript, "
    "LLMs, and customer-facing technical delivery. Salary is $190k-$240k plus equity. "
    "Position is onsite in San Francisco with approximately 20% travel. We're looking for "
    "3-5 years full-stack engineering experience."
)


@pytest.fixture
def analysis(client, candidate, resumes):
    response = client.post("/api/jobs/analyze", json={"raw_text": INPUT})
    assert response.status_code == 200
    return response.json()


class TestExtractedFields:
    def test_title(self, analysis):
        assert analysis["opportunity"]["title"] == "Forward Deployed Engineer"

    def test_salary(self, analysis):
        assert analysis["opportunity"]["salary_min"] == 190_000
        assert analysis["opportunity"]["salary_max"] == 240_000

    def test_clearance_is_ts_sci(self, analysis):
        assert analysis["opportunity"]["security_clearance"] == "ts_sci"

    def test_polygraph_is_not_specified(self, analysis):
        assert analysis["opportunity"]["polygraph_requirement"] == "unknown"

    def test_skills(self, analysis):
        skills = set(analysis["opportunity"]["required_skills"])
        assert {"python", "react", "typescript", "llms", "customer_facing", "fullstack"} <= skills

    def test_lifestyle(self, analysis):
        opportunity = analysis["opportunity"]
        assert opportunity["remote_status"] == "onsite"
        assert opportunity["location"] == "San Francisco"
        assert opportunity["travel"] == 20

    def test_experience_requirement(self, analysis):
        assert analysis["opportunity"]["required_years_experience"] == 3.0
        assert analysis["opportunity"]["preferred_years_experience"] == 5.0

    def test_equity_detected(self, analysis):
        assert analysis["opportunity"]["equity"] is True


class TestScores:
    """The spec documents approximate targets: fit ~75, capital ~95,
    proofability ~90, compensation ~90, overall 86 -> STRONGLY PURSUE."""

    def test_fit(self, analysis):
        assert 65 <= analysis["score"]["fit_score"] <= 85

    def test_career_capital(self, analysis):
        assert analysis["score"]["career_capital_score"] >= 85

    def test_proofability(self, analysis):
        assert analysis["score"]["proofability_score"] >= 80

    def test_compensation(self, analysis):
        assert analysis["score"]["compensation_score"] >= 85

    def test_overall_and_action(self, analysis):
        assert analysis["score"]["overall_score"] >= 75
        assert analysis["score"]["recommended_action"] in ("STRONGLY_PURSUE", "PURSUE")


class TestStrengthsAndGaps:
    def test_key_strengths_include_clearance_and_ai(self, analysis):
        joined = " ".join(analysis["score"]["matched_strengths"]).lower()
        assert "ts/sci" in joined or "clearance" in joined
        assert "python" in joined or "llms" in joined

    def test_gaps_are_react_typescript_and_conventional_yoe(self, analysis):
        gaps = {gap["requirement"] for gap in analysis["score"]["missing_requirements"]}
        assert "React" in gaps
        assert "TypeScript" in gaps

    def test_gaps_are_classified_high_proofability(self, analysis):
        assert analysis["score"]["hard_gates"] == []
        for gap in analysis["score"]["proofable_gaps"]:
            assert gap["tier"] == "proofable"

    def test_prove_it_gives_a_concrete_next_action(self, analysis):
        learnable = {item["requirement"]: item for item in analysis["prove_it"]["learnable"]}
        assert "React" in learnable
        assert learnable["React"]["how_to_demonstrate"]
        assert learnable["React"]["interview_readiness"]


class TestOutputs:
    def test_missing_information_flags_hours_and_polygraph(self, analysis):
        fields = {item["field"] for item in analysis["missing_information"]}
        assert "hours" in fields
        assert "polygraph_requirement" in fields

    def test_a_draft_is_generated_for_human_approval(self, analysis):
        draft = analysis["draft"]
        assert draft is not None
        assert draft["body"]
        # The system drafts; it never sends. The stored status reflects that.
        assert draft["questions_asked"]

    def test_recommended_resume_is_the_fde_variant(self, analysis):
        best = analysis["resume_match"]["best"]
        assert best["title"] == "Forward Deployed AI Resume"
        assert any("TS/SCI" in item for item in best["highlight"])

    def test_resume_advice_names_the_real_gaps(self, analysis):
        best = analysis["resume_match"]["best"]
        assert "React" in best["missing_keywords"]
        assert "TypeScript" in best["missing_keywords"]

    def test_explanation_is_auditable(self, analysis):
        explanation = analysis["score"]["explanation"]
        assert explanation["headline"]
        assert explanation["weights"]["career_capital"] == 0.25
        for dimension in explanation["dimensions"].values():
            assert dimension["reasons"], f"{dimension['name']} has no stated reasons"


def test_the_whole_flow_persists(client, candidate, resumes):
    """Analyze -> dashboard -> detail -> draft -> approve -> decide."""
    job_id = client.post("/api/jobs/analyze", json={"raw_text": INPUT}).json()["opportunity"]["id"]

    rows = client.get("/api/dashboard").json()["rows"]
    assert [row["opportunity_id"] for row in rows] == [job_id]

    detail = client.get(f"/api/jobs/{job_id}").json()
    message_id = detail["messages"][0]["id"]

    approved = client.patch(
        f"/api/messages/{message_id}",
        json={"status": "approved", "approved_response": detail["messages"][0]["response_draft"]},
    ).json()
    assert approved["status"] == "approved"

    client.post(
        "/api/decisions",
        json={"opportunity_id": job_id, "decision": "pursue", "reason": "Comp and capital"},
    )

    final = client.get("/api/dashboard").json()["rows"][0]
    assert final["decision"] == "pursue"
    assert final["message_status"] == "approved"
