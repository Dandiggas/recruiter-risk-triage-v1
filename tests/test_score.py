from app.graph.workflow import run_full_check


def test_full_check_returns_compact_score():
    state = run_full_check(
        "Hi Dan, I’m Alex from ChainHire. Move to Telegram. "
        "Assessment asks you to clone repo, run npm install and connect wallet."
    )

    score = state["score"]
    assert 0 <= score["overall"] <= 100
    assert score["band"] in {"low", "medium", "high", "critical"}
    assert score["security_risk"] in {"low", "medium", "high"}
    assert score["confidence"] in {"low", "medium", "high"}
    assert set(score["components"].keys()) == {"recon", "identity", "agency", "client", "job", "security", "reputation"}


def test_wallet_code_bait_gets_critical_score_band():
    state = run_full_check(
        "Crypto role. Connect wallet, sign message, clone repo and run npm install. Telegram today."
    )

    assert state["score"]["band"] == "critical"
    assert state["score"]["security_risk"] == "high"
    assert state["score"]["overall"] >= 80


def test_missing_jd_without_wallet_gets_medium_or_high_but_not_critical():
    state = run_full_check(
        "Hi Dan, I’m Sarah from Real Talent, sarah@example.com. "
        "Senior AI Platform Engineer role, client confidential until call."
    )

    assert state["score"]["band"] in {"medium", "high"}
    assert state["score"]["overall"] < 80


def test_verified_recon_recruiter_client_and_jd_can_be_safe_to_reply_without_security_bait():
    reports = {
        "original_jd_recon": {"verdict": "verified", "confidence": "high", "concerns": [], "gaps": []},
        "recruiter_identity": {"verdict": "verified", "confidence": "high", "concerns": [], "gaps": []},
        "client_company": {"verdict": "verified", "confidence": "high", "concerns": [], "gaps": []},
        "job_jd_verification": {"verdict": "verified", "confidence": "high", "concerns": [], "gaps": []},
        "security_assessment": {"verdict": "partially_verified", "confidence": "medium", "concerns": [], "gaps": ["Live URL expansion skipped"]},
        "agency_legitimacy": {"verdict": "partially_verified", "confidence": "low", "concerns": [], "gaps": []},
        "reputation_pattern": {"verdict": "unverified", "confidence": "low", "concerns": [], "gaps": ["Review search not connected"]},
    }

    from app.scoring import decide_final_action, score_case

    action = decide_final_action(reports, ["official JD missing", "client/company proof missing", "Review search not connected"], [])
    score = score_case(reports, ["official JD missing", "client/company proof missing", "Review search not connected"], [], action)

    assert action["label"] == "Proceed with qualifying questions"
    assert score["overall"] < 45
