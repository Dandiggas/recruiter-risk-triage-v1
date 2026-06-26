import pytest
from pydantic import ValidationError

from app.models import CaseInput, FullCheckResponse, to_full_check_response


def test_case_input_requires_non_empty_text():
    with pytest.raises(ValidationError):
        CaseInput(text="   ")


def test_full_check_response_contract_accepts_graph_state():
    graph_state = {
        "entities": {"emails": ["a@example.com"], "urls": [], "domains": ["example.com"]},
        "score": {
            "overall": 85,
            "band": "critical",
            "security_risk": "high",
            "confidence": "high",
            "components": {"identity": 0, "agency": 0, "client": 0, "job": 0, "security": 85, "reputation": 12},
        },
        "final_action": {"label": "Do not engage", "level": "stop", "reason": "Wallet bait."},
        "final_report": "## Final action\n- Do not engage",
        "lane_reports": {},
        "evidence_ledger": [
            {
                "lane": "security_assessment",
                "finding": "Wallet bait",
                "source_type": "input_text",
                "source": "pasted outreach",
                "quote": "connect wallet",
                "confidence": "high",
            }
        ],
        "verification_digest": [
            {
                "title": "Email domain can receive mail",
                "status": "pass",
                "plain_english": "talentco.example resolves as a mail-capable domain.",
                "source": "talentco.example",
                "technical_check": "DNS/MX lookup",
                "why_it_matters": "Real recruiter domains should receive mail.",
                "dates": {"checked": "2026-06-25"},
                "details": ["MX records found"],
            }
        ],
        "opportunity_read": {
            "legitimacy": "unclear",
            "security_risk": "high",
            "opportunity_fit": "poor",
            "recommended_action": "Do not engage",
            "salary_stance": "Do not discuss salary yet.",
            "role_read": "Crypto role.",
            "reply_focus": "Safety proof first.",
            "summary": "High-risk assessment behaviour dominates.",
        },
        "gaps": ["official JD missing"],
        "conflicts": [],
        "trace": ["extract_entities", "final_report"],
    }

    response = to_full_check_response(graph_state)

    assert isinstance(response, FullCheckResponse)
    assert response.status == "ok"
    assert response.score.overall == 85
    assert response.decision == "Do not engage"
    assert response.key_evidence[0].finding == "Wallet bait"
    assert response.details.verification_digest[0].technical_check == "DNS/MX lookup"
    assert response.details.opportunity_read.security_risk == "high"
    assert response.details.lane_reports == {}
    assert response.markdown.startswith("## Final action")


def test_full_check_response_rejects_bad_score_band():
    with pytest.raises(ValidationError):
        FullCheckResponse(
            status="ok",
            score={"overall": 10, "band": "meh", "security_risk": "low", "confidence": "low", "components": {}},
            decision="Safe to reply",
            reason="No concern.",
            safe_next_question="Can you send the JD?",
            key_evidence=[],
            details={"entities": {}, "lane_reports": {}, "evidence_ledger": [], "gaps": [], "conflicts": [], "trace": []},
            markdown="",
        )
