from app.graph.workflow import run_full_check


def test_full_check_returns_final_action_and_evidence_ledger():
    state = run_full_check(
        "Hi Dan, I’m Alex from ChainHire. Can we move to Telegram? "
        "Assessment: https://bit.ly/test — clone repo and connect wallet."
    )

    action = state["final_action"]
    assert action["label"] in {"Safe to reply", "Ask verification question first", "Deep check needed", "Do not engage"}
    assert action["level"] in {"safe", "caution", "deep_check", "stop"}
    assert action["reason"]

    ledger = state["evidence_ledger"]
    assert ledger
    assert {"lane", "source_type", "source", "finding", "quote", "confidence"}.issubset(ledger[0])
    assert any(row["lane"] == "security_assessment" for row in ledger)


def test_wallet_or_code_execution_bait_becomes_do_not_engage():
    state = run_full_check(
        "Crypto AI role. Assessment asks you to connect wallet, sign message, "
        "clone repo and run npm install. Move to Telegram today."
    )

    assert state["final_action"]["label"] == "Do not engage"
    assert state["final_action"]["level"] == "stop"


def test_missing_official_jd_but_no_high_risk_becomes_ask_verification_first():
    state = run_full_check(
        "Hi Dan, I’m Sarah from Real Talent, sarah@example.com. "
        "Senior AI Platform Engineer role, client confidential until call."
    )

    assert state["final_action"]["label"] in {"Hold until basics are confirmed", "Deep check needed"}
