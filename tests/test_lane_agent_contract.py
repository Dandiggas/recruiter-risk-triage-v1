from app.graph.contracts import make_lane_report
from app.graph.nodes import _maybe_synthesize_lane


def test_lane_agent_normalizes_common_risk_verdicts_and_keeps_tool_evidence(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_LANE_SYNTHESIS", "true")
    monkeypatch.setenv("LLM_LANE_SYNTHESIS_LANES", "agency_legitimacy")
    calls = []

    def fake_client(_messages):
        calls.append(1)
        if len(calls) == 1:
            return '{"tool_calls":[{"tool":"search_web","args":{"query":"ChainHire recruitment"}}]}'
        return '{"lane":"agency_legitimacy","verdict":"concern","confidence":"high","summary":"Recent entity with conflicting signals.","concerns":[{"risk":"recent registration"}],"gaps":[],"safe_questions":[]}'

    def fake_search(query, provider, api_key):
        return {"status": "ok", "results": [{"title": "ChainHire", "description": "Result", "url": "https://example.com"}]}

    monkeypatch.setattr("app.graph.nodes.default_llm_client", lambda: fake_client)
    monkeypatch.setattr("app.graph.nodes.search_web", fake_search)

    fallback, evidence = make_lane_report(
        lane="agency_legitimacy",
        verdict="partially_verified",
        confidence="low",
        summary="fallback",
        evidence=[],
    )

    result = _maybe_synthesize_lane(
        "agency_legitimacy",
        "Check agency legitimacy",
        {"lane_reports": {"agency_legitimacy": fallback}, "evidence": evidence},
        source_state={"raw_input": "Alex from ChainHire", "entities": {"agency_name": "ChainHire"}, "deterministic_flags": []},
    )

    report = result["lane_reports"]["agency_legitimacy"]
    assert report["verdict"] == "concerning"
    assert report["concerns"] == ["{'risk': 'recent registration'}"]
    assert any(item["source"] == "https://example.com" for item in report["evidence"])


def test_lane_agent_preserves_tool_evidence_when_final_json_violates_contract(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_LANE_SYNTHESIS", "true")
    monkeypatch.setenv("LLM_LANE_SYNTHESIS_LANES", "job_jd_verification")
    calls = []

    def fake_client(_messages):
        calls.append(1)
        if len(calls) == 1:
            return '{"tool_calls":[{"tool":"search_web","args":{"query":"ChainHire job"}}]}'
        return '{"lane":"wrong_lane","verdict":"impossible","confidence":"certain","summary":"bad"}'

    monkeypatch.setattr("app.graph.nodes.default_llm_client", lambda: fake_client)
    monkeypatch.setattr(
        "app.graph.nodes.search_web",
        lambda query, provider, api_key: {"status": "ok", "results": [{"title": "Job page", "description": "desc", "url": "https://jobs.example.com"}]},
    )

    fallback, evidence = make_lane_report(
        lane="job_jd_verification",
        verdict="unverified",
        confidence="low",
        summary="fallback jd",
        evidence=[],
    )

    result = _maybe_synthesize_lane(
        "job_jd_verification",
        "Check JD",
        {"lane_reports": {"job_jd_verification": fallback}, "evidence": evidence},
        source_state={"raw_input": "ChainHire job", "entities": {}, "deterministic_flags": []},
    )

    report = result["lane_reports"]["job_jd_verification"]
    assert report["summary"] == "fallback jd"
    assert any(item["source"] == "https://jobs.example.com" for item in report["evidence"])
