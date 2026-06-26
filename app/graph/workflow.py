from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.graph.nodes import (
    agency_legitimacy,
    client_company,
    deterministic_risk_scan,
    extract_entities,
    final_report,
    job_jd_verification,
    merge_evidence,
    original_jd_recon,
    recruiter_identity,
    reputation_pattern,
    security_assessment,
)
from app.graph.state import CaseState
from app.observability import traceable_if_configured

LANE_NODES = [
    "recruiter_identity",
    "agency_legitimacy",
    "client_company",
    "job_jd_verification",
    "security_assessment",
    "reputation_pattern",
]


def _traced_node(name: str, fn):
    return traceable_if_configured(name=f"triage.node.{name}", run_type="chain")(fn)


@lru_cache(maxsize=1)
def build_graph():
    graph = StateGraph(CaseState)
    graph.add_node("extract_entities", _traced_node("extract_entities", extract_entities))
    graph.add_node("deterministic_risk_scan", _traced_node("deterministic_risk_scan", deterministic_risk_scan))
    graph.add_node("original_jd_recon", _traced_node("original_jd_recon", original_jd_recon))
    graph.add_node("recruiter_identity", _traced_node("recruiter_identity", recruiter_identity))
    graph.add_node("agency_legitimacy", _traced_node("agency_legitimacy", agency_legitimacy))
    graph.add_node("client_company", _traced_node("client_company", client_company))
    graph.add_node("job_jd_verification", _traced_node("job_jd_verification", job_jd_verification))
    graph.add_node("security_assessment", _traced_node("security_assessment", security_assessment))
    graph.add_node("reputation_pattern", _traced_node("reputation_pattern", reputation_pattern))
    graph.add_node("merge_evidence", _traced_node("merge_evidence", merge_evidence))
    graph.add_node("final_report", _traced_node("final_report", final_report))

    graph.add_edge(START, "extract_entities")
    graph.add_edge("extract_entities", "deterministic_risk_scan")
    graph.add_edge("deterministic_risk_scan", "original_jd_recon")
    for lane in LANE_NODES:
        graph.add_edge("original_jd_recon", lane)
        graph.add_edge(lane, "merge_evidence")
    graph.add_edge("merge_evidence", "final_report")
    graph.add_edge("final_report", END)
    return graph.compile()


@traceable_if_configured(name="triage.run_full_check", run_type="chain")
def run_full_check(text: str) -> CaseState:
    initial: CaseState = {
        "raw_input": text,
        "lane_reports": {},
        "evidence": [],
        "trace": [],
    }
    return build_graph().invoke(initial)
