"""API contract tests against a real (in-memory) database."""

from __future__ import annotations

import pytest


def test_health_reports_configuration(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    # With no API key the app must still work, in deterministic mode.
    assert body["extraction_mode"] == "rules-only (deterministic)"


class TestProfile:
    def test_create_read_and_patch(self, client):
        created = client.post(
            "/api/profile",
            json={"name": "Alex", "clearance_level": "secret", "minimum_salary": 150000},
        )
        assert created.status_code == 201

        read = client.get("/api/profile").json()
        assert read["name"] == "Alex"
        assert read["clearance_level"] == "secret"

        patched = client.patch("/api/profile", json={"minimum_salary": 180000}).json()
        assert patched["minimum_salary"] == 180000
        assert patched["name"] == "Alex", "PATCH must not clear untouched fields"

    def test_missing_profile_is_a_clear_404(self, client):
        response = client.get("/api/profile")
        assert response.status_code == 404
        assert "POST /api/profile" in response.json()["error"]["message"]

    def test_invalid_scoring_config_is_rejected(self, client, candidate):
        response = client.patch(
            "/api/profile",
            json={
                "scoring_config": {
                    "compensation_bands": {
                        "poor": 300000,
                        "acceptable": 1,
                        "strong": 2,
                        "excellent": 3,
                    }
                }
            },
        )
        assert response.status_code == 422
        assert "scoring_config" in response.json()["error"]["message"]

    def test_scoring_defaults_are_exposed(self, client):
        defaults = client.get("/api/profile/scoring-config/defaults").json()
        assert defaults["weights"]["career_capital"] == 0.25
        assert defaults["compensation_bands"]["excellent"] == 250000


class TestAnalyze:
    def test_analyze_saves_and_scores(self, client, candidate, fde_text):
        response = client.post("/api/jobs/analyze", json={"raw_text": fde_text})
        assert response.status_code == 200
        body = response.json()

        assert body["saved"] is True
        assert body["opportunity"]["title"] == "Forward Deployed Engineer"
        assert body["opportunity"]["salary_min"] == 190000
        assert body["opportunity"]["security_clearance"] == "ts_sci"
        assert body["score"]["overall_score"] > 70
        assert body["draft"]["body"]
        assert body["prove_it"]["summary"]

    def test_preview_mode_does_not_persist(self, client, candidate, fde_text):
        body = client.post("/api/jobs/analyze", json={"raw_text": fde_text, "save": False}).json()
        assert body["saved"] is False
        assert body["score"]["overall_score"] > 0
        assert client.get("/api/jobs").json() == []

    def test_analyze_requires_a_profile(self, client, fde_text):
        response = client.post("/api/jobs/analyze", json={"raw_text": fde_text})
        assert response.status_code == 404

    def test_empty_text_is_rejected(self, client, candidate):
        assert client.post("/api/jobs/analyze", json={"raw_text": ""}).status_code == 422


class TestJobs:
    @pytest.fixture
    def job_id(self, client, candidate, fde_text) -> str:
        return client.post("/api/jobs/analyze", json={"raw_text": fde_text}).json()["opportunity"][
            "id"
        ]

    def test_list_and_detail(self, client, job_id):
        assert len(client.get("/api/jobs").json()) == 1

        detail = client.get(f"/api/jobs/{job_id}").json()
        assert detail["opportunity"]["id"] == job_id
        assert detail["score"]["recommended_action"]
        assert len(detail["messages"]) == 1
        assert detail["missing_information"]

    def test_unknown_job_is_404(self, client, candidate):
        assert client.get("/api/jobs/does-not-exist").status_code == 404

    def test_manual_correction_marks_high_confidence(self, client, job_id):
        patched = client.patch(
            f"/api/jobs/{job_id}", json={"hours": 45, "polygraph_requirement": "ci"}
        ).json()
        assert patched["hours"] == 45
        assert patched["polygraph_requirement"] == "ci"
        assert patched["confidence"]["hours"] == "high"
        assert "manual" in patched["extraction_method"]

    def test_patch_rejects_unknown_fields(self, client, job_id):
        assert client.patch(f"/api/jobs/{job_id}", json={"nope": 1}).status_code == 422

    def test_rescore_appends_history(self, client, job_id):
        first = client.post(f"/api/jobs/{job_id}/score").json()
        second = client.post(f"/api/jobs/{job_id}/score").json()
        assert first["id"] != second["id"]
        assert len(client.get(f"/api/jobs/{job_id}/scores").json()) == 3

    def test_rescore_reflects_updated_fields(self, client, job_id):
        before = client.get(f"/api/jobs/{job_id}").json()["score"]["overall_score"]
        client.patch(f"/api/jobs/{job_id}", json={"polygraph_requirement": "full_scope"})
        after = client.post(f"/api/jobs/{job_id}/score").json()
        assert after["overall_score"] < before
        assert after["hard_gates"]

    def test_delete(self, client, job_id):
        assert client.delete(f"/api/jobs/{job_id}").status_code == 204
        assert client.get(f"/api/jobs/{job_id}").status_code == 404

    def test_draft_response_endpoint(self, client, job_id):
        draft = client.post(f"/api/jobs/{job_id}/draft-response", json={"tone": "direct"}).json()
        assert draft["tone"] == "direct"
        assert draft["body"]
        assert draft["message_id"]

    @pytest.mark.parametrize("approved_text", [None, "My own wording."])
    def test_regenerating_does_not_clobber_a_sign_off(self, client, job_id, approved_text):
        """An approval - edited or not - survives a later regeneration."""
        message_id = client.get(f"/api/jobs/{job_id}").json()["messages"][0]["id"]
        draft_text = client.get(f"/api/messages/{message_id}").json()["response_draft"]
        payload = {"status": "approved", "approved_response": approved_text or draft_text}
        signed_off = client.patch(f"/api/messages/{message_id}", json=payload).json()

        client.post(f"/api/jobs/{job_id}/draft-response", json={"tone": "warm"})

        message = client.get(f"/api/messages/{message_id}").json()
        assert message["status"] == signed_off["status"]
        assert message["status"] in ("approved", "edited")
        assert message["approved_response"] == (approved_text or draft_text)


class TestResumesAndMatching:
    def test_create_and_list(self, client, candidate):
        created = client.post(
            "/api/resumes",
            json={
                "title": "FDE Resume",
                "raw_text": "Python, FastAPI, RAG, LLMs, agents. TS/SCI with CI poly.",
                "target_families": ["forward_deployed_engineer"],
            },
        )
        assert created.status_code == 201
        body = created.json()
        assert "python" in body["skills"]
        assert body["has_embedding"] is False
        assert len(client.get("/api/resumes").json()) == 1

    def test_match_ranks_the_targeted_variant_first(self, client, candidate, resumes, fde_text):
        job_id = client.post("/api/jobs/analyze", json={"raw_text": fde_text}).json()[
            "opportunity"
        ]["id"]
        match = client.post(f"/api/jobs/{job_id}/resume-match").json()

        assert match["best"]["title"] == "Forward Deployed AI Resume"
        assert len(match["ranked"]) == 2
        assert match["ranked"][0]["score"] > match["ranked"][1]["score"]
        assert match["semantic_enabled"] is False

    def test_match_without_resumes_is_empty_not_an_error(self, client, candidate, fde_text):
        job_id = client.post("/api/jobs/analyze", json={"raw_text": fde_text}).json()[
            "opportunity"
        ]["id"]
        match = client.post(f"/api/jobs/{job_id}/resume-match").json()
        assert match["best"] is None
        assert match["ranked"] == []


class TestDecisionsAndMessages:
    @pytest.fixture
    def job_id(self, client, candidate, fde_text) -> str:
        return client.post("/api/jobs/analyze", json={"raw_text": fde_text}).json()["opportunity"][
            "id"
        ]

    def test_record_a_decision(self, client, job_id):
        response = client.post(
            "/api/decisions",
            json={"opportunity_id": job_id, "decision": "pursue", "reason": "Great comp"},
        )
        assert response.status_code == 201
        assert client.get("/api/decisions").json()[0]["decision"] == "pursue"

    def test_rejecting_updates_the_message_status(self, client, job_id):
        client.post("/api/decisions", json={"opportunity_id": job_id, "decision": "reject"})
        message = client.get(f"/api/jobs/{job_id}").json()["messages"][0]
        assert message["status"] == "rejected"

    def test_editing_a_response_is_tracked_separately(self, client, job_id):
        message_id = client.get(f"/api/jobs/{job_id}").json()["messages"][0]["id"]
        original = client.get(f"/api/messages/{message_id}").json()["response_draft"]

        updated = client.patch(
            f"/api/messages/{message_id}",
            json={"status": "approved", "approved_response": "My own wording."},
        ).json()

        assert updated["status"] == "edited"
        assert updated["approved_response"] == "My own wording."
        assert updated["response_draft"] == original, "the generated draft stays auditable"

    def test_decision_on_unknown_job_is_404(self, client, candidate):
        response = client.post(
            "/api/decisions", json={"opportunity_id": "nope", "decision": "pursue"}
        )
        assert response.status_code == 404


class TestDashboard:
    def test_rows_carry_every_dimension(self, client, candidate, fde_text):
        client.post("/api/jobs/analyze", json={"raw_text": fde_text})
        body = client.get("/api/dashboard").json()

        assert body["total"] == 1
        row = body["rows"][0]
        for key in (
            "overall_score",
            "fit_score",
            "career_capital_score",
            "proofability_score",
            "compensation_score",
            "lifestyle_score",
            "upside_score",
            "risk_score",
        ):
            assert isinstance(row[key], float)
        assert row["recommended_action"]
        assert body["candidate"]["name"] == candidate.name

    def test_sorting(self, client, candidate, fde_text):
        client.post("/api/jobs/analyze", json={"raw_text": fde_text})
        client.post(
            "/api/jobs/analyze",
            json={
                "raw_text": "Intelligence Analyst III. Salary: $105,000 - $115,000. "
                "Active TS/SCI with CI polygraph. Level of effort contract."
            },
        )
        rows = client.get("/api/dashboard?sort=overall&order=desc").json()["rows"]
        assert rows[0]["overall_score"] >= rows[1]["overall_score"]

        ascending = client.get("/api/dashboard?sort=salary&order=asc").json()["rows"]
        assert (ascending[0]["salary_max"] or 0) <= (ascending[1]["salary_max"] or 0)

    def test_stats(self, client, candidate, fde_text):
        client.post("/api/jobs/analyze", json={"raw_text": fde_text})
        stats = client.get("/api/dashboard").json()["stats"]
        assert stats["count"] == 1
        assert stats["average_overall"] > 0
        assert sum(stats["by_action"].values()) == 1

    def test_empty_dashboard(self, client, candidate):
        body = client.get("/api/dashboard").json()
        assert body["rows"] == []
        assert body["stats"]["count"] == 0


class TestReferenceAndEquity:
    def test_equity_matches_the_documented_example(self, client):
        body = client.post(
            "/api/equity/calculate", json={"equity_percent": 0.25, "dilution_percent": 40}
        ).json()

        assert body["post_dilution_percent"] == 0.15
        values = {s["label"]: s["gross_value"] for s in body["scenarios"]}
        assert values["$100M"] == 150_000
        assert values["$500M"] == 750_000
        assert values["$1B"] == 1_500_000
        assert values["$5B"] == 7_500_000
        assert "hypothetical" in body["disclaimer"]

    def test_equity_rejects_impossible_dilution(self, client):
        assert (
            client.post(
                "/api/equity/calculate", json={"equity_percent": 1, "dilution_percent": 100}
            ).status_code
            == 422
        )

    def test_job_family_reference(self, client):
        groups = client.get("/api/reference/job-families").json()["groups"]
        assert "AI / Engineering" in groups
        assert "Cyber" in groups

    def test_skill_reference(self, client):
        body = client.get("/api/reference/skills").json()
        assert body["total"] > 50
        assert "ai" in body["categories"]
