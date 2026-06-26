import pytest
from pydantic import ValidationError

from app.graph.contracts import EvidenceItemModel, LaneReportModel, make_lane_report


def test_lane_report_model_rejects_invalid_lane_verdict_and_confidence():
    with pytest.raises(ValidationError):
        LaneReportModel(
            lane="random_agent",
            verdict="looks_ok",
            confidence="maybe",
            summary="bad",
            evidence=[],
        )


def test_evidence_model_requires_non_empty_source_and_quote():
    with pytest.raises(ValidationError):
        EvidenceItemModel(
            lane="security_assessment",
            finding="Wallet interaction requested",
            source_type="input_text",
            source="",
            quote="",
            confidence="high",
        )


def test_make_lane_report_returns_plain_dicts_for_langgraph_state():
    report, evidence = make_lane_report(
        lane="security_assessment",
        verdict="concerning",
        confidence="high",
        summary="Checks assessment safety.",
        evidence=[
            {
                "lane": "security_assessment",
                "finding": "Code execution requested",
                "source_type": "input_text",
                "source": "pasted outreach",
                "quote": "run npm install",
                "confidence": "high",
            }
        ],
        concerns=["Local code execution before verification"],
    )

    assert isinstance(report, dict)
    assert isinstance(evidence[0], dict)
    assert report["lane"] == "security_assessment"
    assert report["verdict"] == "concerning"
    assert report["evidence"][0]["quote"] == "run npm install"
