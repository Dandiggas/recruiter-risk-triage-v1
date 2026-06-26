from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping

from app.opportunity_read import reply_from_opportunity_read

LANES = [
    "original_jd_recon",
    "recruiter_identity",
    "agency_legitimacy",
    "client_company",
    "job_jd_verification",
    "security_assessment",
    "reputation_pattern",
]


def uniq(items: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        clean = " ".join(str(item).strip().split())
        if clean and clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


def render_final_report(reports: Dict[str, Any], final_action: Dict[str, str], score: Dict[str, Any], opportunity_read: Mapping[str, Any] | None = None) -> str:
    verified: List[str] = []
    unverified: List[str] = []
    concerning: List[str] = []
    for report in reports.values():
        for item in report.get("evidence", []):
            target = verified if item["confidence"] in {"medium", "high"} else unverified
            target.append(f"{item['finding']} — {item['quote']}")
        unverified.extend(report.get("gaps", []))
        concerning.extend(report.get("concerns", []))
    if not verified:
        verified.append("No strong verification evidence collected yet.")
    if not concerning:
        concerning.append("No major security concern found by current graph lanes; live checks may still be needed.")

    lane_lines = []
    for lane in LANES:
        report = reports.get(lane)
        if not report:
            lane_lines.append(f"- {lane}: missing")
        else:
            lane_lines.append(f"- {lane}: {report['verdict']} / {report['confidence']} — {report['summary']}")

    opportunity_read = opportunity_read or {}
    safe_next = f'"{reply_from_opportunity_read(opportunity_read)}"'

    return "\n".join([
        "## Final action",
        f"- {final_action['label']} ({final_action['level']}): {final_action['reason']}",
        f"- Score: {score['overall']}/100 ({score['band']})",
        "",
        "## Opportunity read",
        f"- Legitimacy: {opportunity_read.get('legitimacy', 'unknown')}",
        f"- Security risk: {opportunity_read.get('security_risk', 'unknown')}",
        f"- Opportunity fit: {opportunity_read.get('opportunity_fit', 'unknown')}",
        f"- Recommended action: {opportunity_read.get('recommended_action', '')}",
        f"- Salary stance: {opportunity_read.get('salary_stance', '')}",
        f"- Role read: {opportunity_read.get('role_read', '')}",
        "",
        "## Verified",
        *[f"- {x}" for x in uniq(verified)],
        "",
        "## Unverified",
        *[f"- {x}" for x in uniq(unverified)],
        "",
        "## Concerning",
        *[f"- {x}" for x in uniq(concerning)],
        "",
        "## Safe next question",
        safe_next,
        "",
        "## Lane reports",
        *lane_lines,
    ])
