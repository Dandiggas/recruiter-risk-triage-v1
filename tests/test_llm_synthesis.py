from app.graph.contracts import make_evidence, make_lane_report
from app.graph.llm_synthesis import LANE_SYNTHESIS_PROMPTS, synthesize_lane_report


def _sample_evidence():
    return [
        make_evidence(
            lane="security_assessment",
            finding="Code execution requested",
            source_type="input_text",
            source="pasted outreach",
            quote="please run npm install and execute the assessment",
            confidence="high",
        )
    ]


def _fallback_report(evidence):
    report, _ = make_lane_report(
        lane="security_assessment",
        verdict="concerning",
        confidence="high",
        summary="Deterministic security scan found code execution risk.",
        evidence=evidence,
        concerns=["Code execution requested before verification"],
        safe_questions=["Does the assessment require running code locally?"],
    )
    return report


def test_all_lane_prompts_exist_and_ban_invented_evidence():
    expected_lanes = {
        "original_jd_recon",
        "recruiter_identity",
        "agency_legitimacy",
        "client_company",
        "job_jd_verification",
        "security_assessment",
        "reputation_pattern",
    }

    assert set(LANE_SYNTHESIS_PROMPTS) == expected_lanes
    for prompt in LANE_SYNTHESIS_PROMPTS.values():
        assert "Use only the supplied evidence" in prompt
        assert "Do not invent" in prompt
        assert "LaneReport" in prompt


def test_synthesize_lane_report_validates_json_and_preserves_tool_evidence():
    evidence = _sample_evidence()
    fallback = _fallback_report(evidence)

    def fake_llm(messages):
        assert messages[0]["role"] == "system"
        assert "Security Assessment" in messages[0]["content"]
        assert messages[1]["role"] == "user"
        assert "please run npm install" in messages[1]["content"]
        return {
            "lane": "security_assessment",
            "verdict": "concerning",
            "confidence": "high",
            "summary": "The supplied evidence shows assessment code execution risk.",
            "evidence": [
                {
                    "lane": "security_assessment",
                    "finding": "Invented malware finding",
                    "source_type": "tool_result",
                    "source": "not supplied",
                    "quote": "not supplied",
                    "confidence": "high",
                }
            ],
            "gaps": [],
            "concerns": ["Assessment asks for local code execution."],
            "safe_questions": ["Can they provide a read-only assessment brief first?"],
        }

    report = synthesize_lane_report(
        lane="security_assessment",
        lane_goal="Check links, code-assessment bait, wallet risk, channel moves, and unsafe requests.",
        evidence=evidence,
        gaps=[],
        concerns=["Code execution requested before verification"],
        safe_questions=["Does the assessment require running code locally?"],
        fallback_report=fallback,
        llm_client=fake_llm,
    )

    assert report["summary"] == "The supplied evidence shows assessment code execution risk."
    assert report["evidence"] == evidence
    assert report["evidence"][0]["finding"] == "Code execution requested"


def test_synthesize_lane_report_falls_back_when_llm_output_is_invalid():
    evidence = _sample_evidence()
    fallback = _fallback_report(evidence)

    def broken_llm(_messages):
        return {"lane": "security_assessment", "verdict": "made_up"}

    report = synthesize_lane_report(
        lane="security_assessment",
        lane_goal="Check links, code-assessment bait, wallet risk, channel moves, and unsafe requests.",
        evidence=evidence,
        gaps=[],
        concerns=["Code execution requested before verification"],
        safe_questions=["Does the assessment require running code locally?"],
        fallback_report=fallback,
        llm_client=broken_llm,
    )

    assert report == fallback
