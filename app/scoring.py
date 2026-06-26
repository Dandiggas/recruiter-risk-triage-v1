from __future__ import annotations

from typing import Any, Dict, List

from app.graph.state import EvidenceItem


SECURITY_STOP_TERMS = [
    "wallet",
    "private key",
    "seed phrase",
    "run code",
    "run locally",
    "clone repo",
    "npm install",
    "pip install",
    "code/assessment bait",
]


def evidence_ledger_from_state(state: Dict[str, Any]) -> List[EvidenceItem]:
    seen = set()
    rows: List[EvidenceItem] = []
    for item in state.get("evidence", []) or []:
        key = (item.get("lane"), item.get("source_type"), item.get("source"), item.get("finding"), item.get("quote"))
        if key in seen:
            continue
        seen.add(key)
        rows.append(item)
    return rows


def _is_positive_proof(report: Dict[str, Any]) -> bool:
    return report.get("verdict") in {"verified", "partially_verified"} and report.get("confidence") in {"medium", "high"}


def decide_final_action(reports: Dict[str, Any], gaps: List[str], conflicts: List[str]) -> Dict[str, str]:
    concerns = []
    for report in reports.values():
        concerns.extend(report.get("concerns", []))
    concern_text = " | ".join(concerns).lower()
    gap_text = " | ".join(gaps + conflicts).lower()

    if any(term in concern_text for term in SECURITY_STOP_TERMS):
        return {
            "label": "Do not engage",
            "level": "stop",
            "reason": "Security lane found wallet/code-execution style assessment bait before the role is proven.",
        }

    core_role_proven = all(_is_positive_proof(reports.get(lane, {})) for lane in ("original_jd_recon", "client_company", "job_jd_verification"))
    recruiter_proven = _is_positive_proof(reports.get("recruiter_identity", {}))
    no_security_concerns = not reports.get("security_assessment", {}).get("concerns")
    if core_role_proven and recruiter_proven and no_security_concerns and not conflicts:
        return {
            "label": "Proceed with qualifying questions",
            "level": "safe",
            "reason": "Original JD, end client, and recruiter identity are verified enough to reply; qualify salary, remote setup, client scope, and assessment safety before giving interview time.",
        }

    if "official jd" in gap_text or "client/company" in gap_text or "confidential" in concern_text:
        return {
            "label": "Hold until basics are confirmed",
            "level": "caution",
            "reason": "Core role/company proof is still missing; ask for official JD and end-client details before booking a call.",
        }
    if conflicts:
        return {
            "label": "Deep check needed",
            "level": "deep_check",
            "reason": "Evidence is mixed or incomplete across lanes; run deeper checks before acting.",
        }
    return {
        "label": "Safe admin reply only",
        "level": "safe",
        "reason": "No high-risk security flags were found and the current evidence has no blocking conflicts; still qualify salary, remote setup, and assessment safety before investing time.",
    }


def score_case(reports: Dict[str, Any], gaps: List[str], conflicts: List[str], final_action: Dict[str, str]) -> Dict[str, Any]:
    concerns: List[str] = []
    components = {
        "recon": 0,
        "identity": 0,
        "agency": 0,
        "client": 0,
        "job": 0,
        "security": 0,
        "reputation": 0,
    }
    lane_to_component = {
        "original_jd_recon": "recon",
        "recruiter_identity": "identity",
        "agency_legitimacy": "agency",
        "client_company": "client",
        "job_jd_verification": "job",
        "security_assessment": "security",
        "reputation_pattern": "reputation",
    }
    for lane, report in reports.items():
        lane_gaps = len(report.get("gaps", []))
        lane_concerns = report.get("concerns", [])
        concerns.extend(lane_concerns)
        risk = min(30, lane_gaps * 8 + len(lane_concerns) * 15)
        if report.get("verdict") == "concerning":
            risk += 25
        elif report.get("verdict") == "unverified":
            risk += 12
        key = lane_to_component.get(lane)
        if key:
            components[key] = min(100, risk)

    concern_text = " | ".join(concerns).lower()
    hard_stop = any(term in concern_text for term in SECURITY_STOP_TERMS)
    base = max(components.values()) if components else 0
    base += min(15, len(gaps) * 3) + min(10, len(conflicts) * 5)
    if final_action.get("level") == "stop" or hard_stop:
        base = max(base, 85)
    elif final_action.get("level") == "caution":
        base = max(base, 45)
    overall = max(0, min(100, int(base)))
    if overall >= 80:
        band = "critical"
    elif overall >= 55:
        band = "high"
    elif overall >= 25:
        band = "medium"
    else:
        band = "low"
    return {
        "overall": overall,
        "band": band,
        "security_risk": "high" if overall >= 65 else "medium" if overall >= 35 else "low",
        "confidence": "high" if len(reports) >= 6 and any(r.get("evidence") for r in reports.values()) else "medium" if reports else "low",
        "components": components,
    }
