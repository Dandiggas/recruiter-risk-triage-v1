from app.opportunity_read import build_opportunity_read, reply_from_opportunity_read
from app.scoring import decide_final_action


def test_opportunity_read_stops_wallet_code_bait():
    state = {
        "lane_reports": {
            "security_assessment": {
                "verdict": "concerning",
                "confidence": "high",
                "concerns": ["Wallet interaction requested before verification.", "Package install command detected."],
                "gaps": [],
            }
        },
        "final_action": {"level": "stop", "label": "Do not engage"},
        "entities": {"role": "AI crypto platform role", "salary": "£90,000 - £110,000"},
    }

    read = build_opportunity_read(state)

    assert read["security_risk"] == "high"
    assert read["opportunity_fit"] == "poor"
    assert "Do not engage" in read["recommended_action"]
    assert "wallet" in reply_from_opportunity_read(read).lower()


def test_opportunity_read_qualifies_real_role_with_official_jd():
    state = {
        "entities": {"role": "Engineer for API/EKS Containerization/MCP"},
        "final_action": {"level": "safe", "label": "Proceed with qualifying questions"},
        "original_jd_recon": {
            "inferred_client_company": "Luxoft",
            "confidence_score": 88,
            "matched_original_jd_url": "https://career.luxoft.com/jobs/engineer-for-apieks-containerizationmcp-25438",
        },
        "evidence_ledger": [
            {
                "lane": "job_jd_verification",
                "finding": "Job/careers URL metadata fetched.",
                "source": "https://career.luxoft.com/jobs/engineer-for-apieks-containerizationmcp-25438",
                "quote": "title=Engineer for API/EKS Containerization/MCP",
                "confidence": "high",
            }
        ],
        "lane_reports": {
            "security_assessment": {"verdict": "partially_verified", "confidence": "medium", "concerns": [], "gaps": []},
            "recruiter_identity": {"verdict": "partially_verified", "confidence": "medium", "concerns": [], "gaps": []},
            "client_company": {"verdict": "verified", "confidence": "high", "concerns": [], "gaps": []},
        },
    }

    read = build_opportunity_read(state)

    assert read["legitimacy"] == "high"
    assert read["security_risk"] == "low"
    assert read["opportunity_fit"] == "medium"
    assert "Proceed" in read["recommended_action"]
    assert "salary range" in reply_from_opportunity_read(read)


def test_decision_wording_uses_qualifying_language_for_verified_case():
    reports = {
        "original_jd_recon": {"verdict": "verified", "confidence": "high", "concerns": [], "gaps": []},
        "recruiter_identity": {"verdict": "verified", "confidence": "high", "concerns": [], "gaps": []},
        "client_company": {"verdict": "verified", "confidence": "high", "concerns": [], "gaps": []},
        "job_jd_verification": {"verdict": "verified", "confidence": "high", "concerns": [], "gaps": []},
        "security_assessment": {"verdict": "partially_verified", "confidence": "medium", "concerns": [], "gaps": []},
    }

    action = decide_final_action(reports, [], [])

    assert action["label"] == "Proceed with qualifying questions"
