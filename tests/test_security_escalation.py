from app.graph.nodes import security_assessment


def test_security_lane_runs_behavioral_only_without_artifacts(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_LANE_SYNTHESIS", "false")
    result = security_assessment(
        {
            "raw_input": "Crypto role. Move to Telegram before details.",
            "entities": {"urls": []},
            "deterministic_flags": ["Channel move requested before the role/company is proven."],
        }
    )

    report = result["lane_reports"]["security_assessment"]
    assert report["verdict"] == "concerning"
    assert any("behavioural-risk analysis" in gap for gap in report["gaps"])
    assert not any("sandbox" in item["finding"].lower() for item in report["evidence"])


def test_security_lane_escalates_github_artifact_to_sandbox_gate(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_LANE_SYNTHESIS", "false")
    monkeypatch.setattr(
        "app.graph.nodes.github_repo_check",
        lambda url: {"status": "ok", "repo": "evil/test", "created_at": "2026-01-01", "updated_at": "2026-01-02", "stars": 0, "forks": 0},
    )
    monkeypatch.setattr(
        "app.graph.nodes.sandbox_repo_static_analysis",
        lambda url, live=False: {"status": "planned", "repo": "evil/test", "sandbox_profile": {"network": "none"}},
    )

    result = security_assessment(
        {
            "raw_input": "Clone https://github.com/evil/test and run npm install before connecting wallet.",
            "entities": {"urls": ["https://github.com/evil/test"]},
            "deterministic_flags": [],
        }
    )

    report = result["lane_reports"]["security_assessment"]
    quotes = "\n".join(item["quote"] for item in report["evidence"])
    assert report["verdict"] == "concerning"
    assert "repo=evil/test" in quotes
    assert "sandbox_profile" in quotes
    assert any("sandbox" in concern.lower() for concern in report["concerns"])
    assert any("Install command" in concern for concern in report["concerns"])
