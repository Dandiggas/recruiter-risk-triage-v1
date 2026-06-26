from app.graph.workflow import run_full_check


LANES = {
    "original_jd_recon",
    "recruiter_identity",
    "agency_legitimacy",
    "client_company",
    "job_jd_verification",
    "security_assessment",
    "reputation_pattern",
}


def test_full_check_runs_all_six_specialist_lanes_and_final_report():
    text = """
    Hi Dan, I’m Sarah from Acme Talent, sarah@acmetalent.co.uk.
    Hiring for Senior AI Platform Engineer at Example Labs, £90,000 - £100,000.
    Client is confidential until call. Can we move to Telegram?
    Assessment: https://bit.ly/example-test — clone repo and run npm install.
    """

    state = run_full_check(text)

    assert set(state["lane_reports"].keys()) == LANES
    assert state["final_report"].startswith("## Final action")
    assert "## Verified" in state["final_report"]
    assert "## Lane reports" in state["final_report"]
    assert len(state["evidence"]) >= 6
    assert any(item["lane"] == "security_assessment" for item in state["evidence"])
    assert any("Telegram" in concern or "Channel" in concern for concern in state["lane_reports"]["security_assessment"]["concerns"])


def test_lane_reports_are_structured_and_do_not_make_final_verdicts():
    state = run_full_check("AI role from Acme Talent. Official JD https://example.com/careers/ai-platform-engineer")

    for lane, report in state["lane_reports"].items():
        assert report["lane"] == lane
        assert report["verdict"] in {"verified", "partially_verified", "unverified", "concerning", "not_applicable"}
        assert report["confidence"] in {"low", "medium", "high"}
        assert isinstance(report["evidence"], list)
        assert "final_verdict" not in report


def test_graph_trace_records_node_order_and_parallel_lane_names():
    state = run_full_check("Crypto AI role, connect wallet, run locally.")

    trace = state["trace"]
    assert trace[0] == "extract_entities"
    assert "deterministic_risk_scan" in trace
    assert "merge_evidence" in trace
    assert trace[-1] == "final_report"
    for lane in LANES:
        assert lane in trace
