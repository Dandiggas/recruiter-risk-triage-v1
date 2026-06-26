from datetime import datetime, timezone

from app.verification_digest import build_verification_digest


def test_verification_digest_translates_dns_and_rdap_with_dates():
    evidence = [
        {
            "lane": "recruiter_identity",
            "finding": "Email domain DNS check completed.",
            "source_type": "technical_scan",
            "source": "recruiter@talentco.example",
            "quote": "domain=talentco.example has_mx=True mx=10 mx1.talentco.example; 20 mx2.talentco.example",
            "confidence": "high",
        },
        {
            "lane": "recruiter_identity",
            "finding": "LLM-selected tool ran: rdap_domain_lookup.",
            "source_type": "technical_scan",
            "source": "talentco.example",
            "quote": '{"status":"ok","domain":"talentco.example","registration_date":"1996-04-11T04:00:00Z","last_changed":"2025-03-12T10:00:00Z","expiration_date":"2027-04-12T04:00:00Z","registrar":"CSC Corporate Domains"}',
            "confidence": "high",
        },
    ]

    cards = build_verification_digest(evidence, checked_at=datetime(2026, 6, 25, tzinfo=timezone.utc))

    assert cards[0]["title"] == "Email domain can receive mail"
    assert cards[0]["technical_check"] == "DNS/MX lookup"
    assert cards[0]["dates"]["checked"] == "2026-06-25"
    assert "talentco.example" in cards[0]["plain_english"]
    assert cards[1]["title"] == "Domain registration found"
    assert cards[1]["dates"]["registered"] == "1996-04-11T04:00:00Z"
    assert cards[1]["dates"]["last_updated"] == "2025-03-12T10:00:00Z"


def test_verification_digest_translates_companies_house_and_official_jd():
    evidence = [
        {
            "lane": "agency_legitimacy",
            "finding": "LLM-selected tool ran: companies_house_lookup.",
            "source_type": "registry",
            "source": "Luxoft UK Limited",
            "quote": '{"status":"ok","source":"companies_house","query":"Luxoft UK Limited","results":[{"company_name":"LUXOFT UK LIMITED","company_number":"04965442","company_status":"active","date_of_creation":"2003-11-17","address_snippet":"Farnborough Business Park","company_type":"ltd"}]}',
            "confidence": "high",
        },
        {
            "lane": "job_jd_verification",
            "finding": "Original JD recon found a likely source JD to verify independently.",
            "source_type": "search_result",
            "source": "https://career.luxoft.com/jobs/engineer-for-apieks-containerizationmcp-25438",
            "quote": "company=Luxoft confidence=88 matched_fields=title, remote UK, MCP, EKS",
            "confidence": "high",
        },
    ]

    cards = build_verification_digest(evidence, checked_at=datetime(2026, 6, 25, tzinfo=timezone.utc))

    company = next(card for card in cards if card["technical_check"] == "Companies House lookup")
    assert company["title"] == "Company is active"
    assert company["dates"]["incorporated"] == "2003-11-17"
    assert "04965442" in " ".join(company["details"])

    jd = next(card for card in cards if card["technical_check"] == "Careers page / web metadata / search result")
    assert jd["title"] == "Official job/JD evidence found"
    assert jd["dates"]["observed"] == "2026-06-25"
    assert "career.luxoft.com" in jd["source"]


def test_verification_digest_labels_generic_search_results_as_candidates_not_verified():
    cards = build_verification_digest([
        {
            "lane": "original_jd_recon",
            "finding": "LLM-selected web search returned a result.",
            "source_type": "search_result",
            "source": "https://uk.indeed.com/q-lch-l-london-jobs.html",
            "quote": "query=LCH clearing house jobs title=Lch Jobs in London",
            "confidence": "medium",
        }
    ], checked_at=datetime(2026, 6, 25, tzinfo=timezone.utc))

    assert cards[0]["title"] == "Candidate job/JD search result found"
    assert cards[0]["status"] == "info"
    assert "lead, not verification" in cards[0]["plain_english"]
