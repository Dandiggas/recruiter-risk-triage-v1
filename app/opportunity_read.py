from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping

SECURITY_TERMS = ("wallet", "connect wallet", "private key", "seed phrase", "npm install", "pip install", "run locally", "clone repo", "install dependencies")
OFFICIAL_JD_TERMS = ("official", "careers", "career.", "jobs", "job/careers")


def _text(items: Iterable[Any]) -> str:
    return " | ".join(str(item) for item in items if item).lower()


def _has_official_jd(evidence: List[Mapping[str, Any]], recon: Mapping[str, Any]) -> bool:
    if recon.get("matched_original_jd_url") and recon.get("confidence_score", 0) and int(recon.get("confidence_score") or 0) >= 70:
        return True
    for item in evidence:
        haystack = f"{item.get('finding')} {item.get('source')} {item.get('quote')}".lower()
        if any(term in haystack for term in OFFICIAL_JD_TERMS) and item.get("confidence") in {"medium", "high"}:
            return True
    return False


def _security_risk(reports: Mapping[str, Any]) -> str:
    concerns = []
    for report in reports.values():
        concerns.extend(report.get("concerns", []) or [])
    concern_text = _text(concerns)
    if any(term in concern_text for term in SECURITY_TERMS):
        return "high"
    if concerns:
        return "medium"
    return "low"


def build_opportunity_read(state: Mapping[str, Any]) -> Dict[str, Any]:
    reports = state.get("lane_reports") or {}
    evidence = list(state.get("evidence_ledger") or state.get("evidence") or [])
    recon = state.get("original_jd_recon") or {}
    entities = state.get("entities") or {}
    gaps = list(state.get("gaps") or [])
    conflicts = list(state.get("conflicts") or [])
    final_action = state.get("final_action") or {}

    security = _security_risk(reports)
    official_jd = _has_official_jd(evidence, recon)
    recruiter_ok = reports.get("recruiter_identity", {}).get("verdict") in {"verified", "partially_verified"}
    client_ok = bool(recon.get("inferred_client_company") or entities.get("client_company")) or reports.get("client_company", {}).get("verdict") == "verified"
    salary = str(entities.get("salary") or "").strip()
    role = str(entities.get("role") or "role").strip()

    if security == "high" or final_action.get("level") == "stop":
        legitimacy = "unclear"
        fit = "poor"
        recommended_action = "Do not engage unless they first provide official company/JD proof and remove any wallet/local-code assessment requirement."
        summary = "High-risk assessment behaviour dominates the opportunity. Treat this as unsafe until independently proven otherwise."
        salary_stance = "Do not discuss salary until legitimacy and assessment safety are proven."
        reply_focus = "Ask for official JD/company proof and confirmation that no wallet, package install, or local code execution is required."
    elif official_jd and security == "low":
        legitimacy = "high" if recruiter_ok or client_ok else "medium"
        fit = "medium"
        recommended_action = "Proceed with qualifying questions before giving time to interviews."
        summary = f"The role looks real enough to qualify, but it still needs salary, remote setup, client and work-split confirmation."
        salary_stance = "Minimum to consider: £75k base. Target: £85k–£95k+. Push higher for senior AWS/EKS/API/MCP plus finance infrastructure."
        reply_focus = "Ask salary range, UK remote/London expectations, end client, and Python/API vs EKS/Terraform split."
    else:
        legitimacy = "medium" if recruiter_ok or official_jd else "unclear"
        fit = "unknown"
        recommended_action = "Hold until basics are confirmed."
        summary = "There is not enough role/company proof yet to judge the opportunity cleanly. Ask for the official JD and end client before booking a call."
        salary_stance = "Do not spend interview time until salary range and remote expectations are stated."
        reply_focus = "Ask for official careers-page JD, end client/company, salary range, remote policy, and assessment safety."

    return {
        "legitimacy": legitimacy,
        "security_risk": security,
        "opportunity_fit": fit,
        "recommended_action": recommended_action,
        "salary_stance": salary_stance,
        "role_read": f"Role clue: {role}. Salary clue: {salary or 'not provided'}." if role or salary else "Role and salary are not clear enough yet.",
        "reply_focus": reply_focus,
        "summary": summary,
        "open_questions": [
            "What is the salary range?",
            "Is the role fully remote in the UK, hybrid, or London/client-site based?",
            "Who is the end client/company?",
            "How much of the work is Python/API architecture versus EKS/Terraform/platform delivery?",
            "Does any assessment require running code, installing packages, or connecting a wallet?",
        ],
        "signals": {
            "official_jd_found": official_jd,
            "recruiter_partially_verified": recruiter_ok,
            "client_or_recon_lead_found": client_ok,
            "gaps_count": len(gaps),
            "conflicts_count": len(conflicts),
        },
    }


def reply_from_opportunity_read(read: Mapping[str, Any]) -> str:
    security = read.get("security_risk")
    action = str(read.get("recommended_action") or "").lower()
    if security == "high" or "do not engage" in action:
        return "Can you send the official company careers-page JD and confirm the assessment does not require running local code, installing packages, or connecting a wallet? I won't proceed with any assessment until those basics are clear."
    if "proceed" in action:
        return "Thanks — this looks relevant. Before arranging a call, could you share the salary range, confirm whether it is fully remote within the UK or needs London/client visits, confirm the end client, and clarify how much of the work is Python/API development versus EKS/Terraform/platform engineering?"
    return "Can you share the official careers-page JD, end client/company name, salary range, remote/London expectations, and confirm whether any assessment requires running code, installing packages, or connecting a wallet before I book a call?"
