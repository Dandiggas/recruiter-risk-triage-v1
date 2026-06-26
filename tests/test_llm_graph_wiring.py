from app.graph.nodes import agency_legitimacy, original_jd_recon, security_assessment
from app.graph.workflow import build_graph


def test_lane_agent_can_choose_and_run_search_tool_before_report(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_LANE_SYNTHESIS", "true")
    monkeypatch.setenv("LLM_LANE_SYNTHESIS_LANES", "agency_legitimacy")

    llm_calls = []

    def fake_client(messages):
        llm_calls.append(messages[-1]["content"])
        if len(llm_calls) == 1:
            return '{"tool_calls":[{"tool":"search_web","args":{"query":"ChainHire recruiter complaints"}}]}'
        return '''{
            "lane":"agency_legitimacy",
            "verdict":"partially_verified",
            "confidence":"medium",
            "summary":"LLM agent searched ChainHire recruiter complaints and found one public search result.",
            "evidence":[],
            "gaps":[],
            "concerns":[],
            "safe_questions":["Can you confirm the agency website?"]
        }'''

    search_queries = []

    def fake_search(query, provider, api_key):
        search_queries.append(query)
        return {
            "status": "ok",
            "results": [
                {
                    "title": "ChainHire - recruitment profile",
                    "description": "Public recruitment result",
                    "url": "https://example.com/chainhire",
                }
            ],
        }

    monkeypatch.setattr("app.graph.nodes.default_llm_client", lambda: fake_client)
    monkeypatch.setattr("app.graph.nodes.search_web", fake_search)
    monkeypatch.setattr("app.graph.nodes.companies_house_lookup", lambda *_args: {"status": "missing_api_key", "results": []})

    result = agency_legitimacy(
        {
            "raw_input": "I am Alex from ChainHire. Remote crypto role.",
            "entities": {"agency_name": "ChainHire", "domains": []},
            "deterministic_flags": [],
        }
    )

    report = result["lane_reports"]["agency_legitimacy"]
    assert search_queries == ["ChainHire recruiter complaints"]
    assert len(llm_calls) == 2
    assert report["summary"].startswith("LLM agent searched")
    assert any(item["source"] == "https://example.com/chainhire" for item in report["evidence"])


def test_lane_agent_falls_back_to_deterministic_report_when_llm_unavailable(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_LANE_SYNTHESIS", "true")
    monkeypatch.setenv("LLM_LANE_SYNTHESIS_LANES", "security_assessment")
    monkeypatch.setattr(
        "app.graph.nodes.default_llm_client",
        lambda: (_ for _ in ()).throw(RuntimeError("missing key")),
    )

    result = security_assessment(
        {
            "raw_input": "Crypto AI role. Please run npm install and connect wallet.",
            "entities": {"urls": []},
            "deterministic_flags": ["Wallet interaction requested"],
        }
    )

    assert result["lane_reports"]["security_assessment"]["summary"] == (
        "Checks links, code-assessment bait, wallet risk, channel moves, and unsafe requests."
    )


def test_workflow_routes_lane_nodes_directly_to_merge_without_central_synthesis_stage():
    graph = build_graph()
    node_names = set(graph.get_graph().nodes)
    assert "synthesize_lane_reports" not in node_names




def test_original_jd_recon_shares_high_confidence_inferred_company(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_LANE_SYNTHESIS", "true")
    monkeypatch.setenv("LLM_LANE_SYNTHESIS_LANES", "original_jd_recon")

    def fake_client(messages):
        content = messages[-1]["content"]
        if '"tool_history": []' in content:
            return '{"tool_calls":[{"tool":"search_web","args":{"query":"Senior AI Platform Engineer £100000 remote UK LLM security"}}]}'
        return '''{
            "lane":"original_jd_recon",
            "verdict":"partially_verified",
            "confidence":"high",
            "summary":"Found a likely original JD at Example Labs matching title, salary and remote UK clues.",
            "inferred_company":"Example Labs",
            "inferred_company_confidence":82,
            "matched_original_jd_url":"https://examplelabs.com/careers/senior-ai-platform-engineer",
            "matched_fields":["title","salary","remote UK","LLM security"],
            "evidence":[],
            "gaps":[],
            "concerns":[],
            "safe_questions":["Can you confirm this is for Example Labs?"]
        }'''

    def fake_search(query, provider, api_key):
        return {"status": "ok", "results": [{"title": "Senior AI Platform Engineer - Example Labs", "description": "Remote UK, £90k-£110k, LLM security platform", "url": "https://examplelabs.com/careers/senior-ai-platform-engineer"}]}

    monkeypatch.setattr("app.graph.nodes.default_llm_client", lambda: fake_client)
    monkeypatch.setattr("app.graph.nodes.search_web", fake_search)

    result = original_jd_recon({
        "raw_input": "Confidential Senior AI Platform Engineer, remote UK, £90k-£110k, LLM security.",
        "entities": {"role": "Senior AI Platform Engineer", "salary": "£90k-£110k", "urls": []},
        "deterministic_flags": [],
    })

    recon = result["original_jd_recon"]
    assert recon["inferred_client_company"] == "Example Labs"
    assert recon["confidence_score"] == 82
    assert recon["matched_original_jd_url"].endswith("senior-ai-platform-engineer")
    assert "title" in recon["matched_fields"]
    assert result["lane_reports"]["original_jd_recon"]["confidence"] == "high"


def test_original_jd_recon_does_not_share_low_confidence_guess(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_LANE_SYNTHESIS", "true")
    monkeypatch.setenv("LLM_LANE_SYNTHESIS_LANES", "original_jd_recon")

    def fake_client(_messages):
        return '''{
            "lane":"original_jd_recon",
            "verdict":"unverified",
            "confidence":"low",
            "summary":"Search did not find a reliable original JD.",
            "inferred_company":"MaybeCo",
            "inferred_company_confidence":49,
            "matched_fields":["title"],
            "evidence":[],
            "gaps":["No reliable public JD match."],
            "concerns":[],
            "safe_questions":[]
        }'''

    monkeypatch.setattr("app.graph.nodes.default_llm_client", lambda: fake_client)

    result = original_jd_recon({
        "raw_input": "Vague AI role.",
        "entities": {"role": "AI role", "urls": []},
        "deterministic_flags": [],
    })

    assert "original_jd_recon" not in result
    assert result["lane_reports"]["original_jd_recon"]["verdict"] == "unverified"


def test_lane_agents_are_parallel_and_independent_after_recon_lead_stage():
    graph = build_graph().get_graph()
    edges = {(edge.source, edge.target) for edge in graph.edges}
    lanes = {
        "recruiter_identity",
        "agency_legitimacy",
        "client_company",
        "job_jd_verification",
        "security_assessment",
        "reputation_pattern",
    }

    assert ("deterministic_risk_scan", "original_jd_recon") in edges
    assert {("original_jd_recon", lane) for lane in lanes}.issubset(edges)
    assert {(lane, "merge_evidence") for lane in lanes}.issubset(edges)
    assert not any(source in lanes and target in lanes for source, target in edges)
