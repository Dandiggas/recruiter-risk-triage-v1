from app.analyzer import analyze_message


def test_flags_crypto_assessment_wallet_and_channel_move_risks():
    text = """
    Hi Dan, urgent AI crypto role, £100k. Client confidential for now.
    Can we move to Telegram today? Assessment is in this zip: https://bit.ly/abc
    You may need to connect your wallet and run npm install locally.
    """

    result = analyze_message(text)

    concerning = "\n".join(result["concerning"])
    do_not_do = "\n".join(result["do_not_do"])

    assert result["scores"]["security_risk"] == "High"
    assert "shortened or redirected link" in concerning
    assert "wallet" in concerning.lower()
    assert "run code" in concerning.lower() or "assessment" in concerning.lower()
    assert "Don’t run code" in do_not_do
    assert "Don’t connect a wallet" in do_not_do
    assert "official careers-page JD" in result["safe_next_question"]


def test_extracts_verified_clues_but_keeps_them_as_claims_not_truth():
    text = """
    I’m Sarah from Acme Talent. My email is sarah@acmetalent.co.uk.
    Hiring for a Senior AI Platform Engineer at Example Labs.
    Official JD: https://example.com/careers/senior-ai-platform-engineer
    Salary £85,000 - £100,000, remote UK.
    """

    result = analyze_message(text)

    verified_text = "\n".join(result["verified"])
    unverified_text = "\n".join(result["unverified"])

    assert "sarah@acmetalent.co.uk" in verified_text
    assert "example.com" in verified_text
    assert "Example Labs" in unverified_text
    assert "recruiter identity" in unverified_text.lower()
    assert result["scores"]["legitimacy"] >= 2
    assert result["scores"]["confidence"] in {"Low", "Medium", "High"}


def test_plain_message_outputs_required_sections_and_default_safety():
    result = analyze_message("Saw your profile. AI engineer role, interested?")

    assert set(result) >= {
        "verified",
        "unverified",
        "concerning",
        "safe_next_question",
        "do_not_do",
        "scores",
        "research_links",
    }
    assert result["verified"]
    assert result["unverified"]
    assert result["scores"]["security_risk"] in {"Low", "Medium", "High"}
