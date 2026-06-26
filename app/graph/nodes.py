from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Mapping

from app.analyzer import EMAIL_RE, ROLE_RE, SALARY_RE, URL_RE, _domain, _looks_like_company, analyze_message
from app.config import load_settings
from app.graph.contracts import make_evidence, make_lane_report
from app.graph.llm_synthesis import default_llm_client, synthesize_lane_report
from app.graph.state import CaseState, Entities, EvidenceItem, LaneReport
from app.observability import traceable_if_configured
from app.reporting import render_final_report
from app.scoring import decide_final_action, evidence_ledger_from_state, score_case
from app.opportunity_read import build_opportunity_read
from app.verification_digest import build_verification_digest
from app.tools.companies_house import companies_house_lookup
from app.tools.dns_checks import check_email_domain
from app.tools.github_public import github_repo_check, parse_github_repo
from app.tools.package_registries import npm_package_check, pypi_package_check
from app.tools.rdap import rdap_domain_lookup
from app.tools.sandbox import sandbox_repo_static_analysis
from app.tools.search import search_web
from app.tools.url_expand import expand_url
from app.tools.web_metadata import fetch_web_metadata

LANES = [
    "original_jd_recon",
    "recruiter_identity",
    "agency_legitimacy",
    "client_company",
    "job_jd_verification",
    "security_assessment",
    "reputation_pattern",
]

LANE_GOALS = {
    "original_jd_recon": "Reverse-search the job description clues to find the likely original public JD and infer the likely end client/company without judging recruiter legitimacy.",
    "recruiter_identity": "Check whether the named recruiter exists and matches the claimed agency.",
    "agency_legitimacy": "Check whether the recruitment agency is real, active, and matched to the sender.",
    "client_company": "Check whether the end client/company exists and has product/hiring activity.",
    "job_jd_verification": "Check official JD existence, freshness, salary realism, repository metadata, and text reuse.",
    "security_assessment": "Check links, code-assessment bait, wallet risk, channel moves, and unsafe requests.",
    "reputation_pattern": "Check review snippets and repeated complaint/warning patterns without treating them as sole proof.",
}

LANE_ALLOWED_TOOLS = {
    "original_jd_recon": {"search_web", "fetch_web_metadata"},
    "recruiter_identity": {"search_web", "check_email_domain", "rdap_domain_lookup"},
    "agency_legitimacy": {"search_web", "companies_house_lookup", "rdap_domain_lookup", "fetch_web_metadata"},
    "client_company": {"search_web", "fetch_web_metadata", "rdap_domain_lookup"},
    "job_jd_verification": {"search_web", "fetch_web_metadata", "github_repo_check"},
    "security_assessment": {"search_web", "expand_url", "github_repo_check", "npm_package_check", "pypi_package_check", "fetch_web_metadata", "sandbox_repo_static_analysis"},
    "reputation_pattern": {"search_web"},
}

TOOL_SCHEMAS = {
    "search_web": {"query": "string"},
    "companies_house_lookup": {"name": "string"},
    "rdap_domain_lookup": {"domain": "string"},
    "check_email_domain": {"email": "string"},
    "fetch_web_metadata": {"url": "string"},
    "expand_url": {"url": "string"},
    "github_repo_check": {"url": "string"},
    "npm_package_check": {"package": "string"},
    "pypi_package_check": {"package": "string"},
    "sandbox_repo_static_analysis": {"url": "string"},
}

NPM_PACKAGE_RE = re.compile(r"npm\s+install\s+([@\w./-]+)", re.I)
PIP_PACKAGE_RE = re.compile(r"pip(?:3)?\s+install\s+([\w./-]+)", re.I)
NPM_INSTALL_COMMAND_RE = re.compile(r"\bnpm\s+(?:i|install)\b", re.I)
PIP_INSTALL_COMMAND_RE = re.compile(r"\bpip(?:3)?\s+install\b", re.I)
CODE_ASSESSMENT_RE = re.compile(r"\b(clone|github|repo|repository|assessment|take[- ]?home|run locally|install dependencies)\b", re.I)


def _append_trace(state: CaseState, node: str) -> List[str]:
    # LangGraph merges this channel via append_lists, so each node returns only its own marker.
    return [node]


def _uniq(items: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        clean = " ".join(str(item).strip().split())
        if clean and clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


def _evidence(lane: str, finding: str, source_type: str, source: str, quote: str, confidence: str = "medium") -> EvidenceItem:
    return make_evidence(
        lane=lane,  # type: ignore[arg-type]
        finding=finding,
        source_type=source_type,  # type: ignore[arg-type]
        source=source,
        quote=quote,
        confidence=confidence,  # type: ignore[arg-type]
    )


def extract_entities(state: CaseState) -> CaseState:
    raw = state["raw_input"]
    emails = _uniq(EMAIL_RE.findall(raw))
    urls = _uniq(URL_RE.findall(raw))
    domains = _uniq([_domain(item) for item in [*emails, *urls] if _domain(item)])
    roles = _uniq([m.group(1).strip() for m in ROLE_RE.finditer(raw)])
    salaries = _uniq(SALARY_RE.findall(raw))
    companies = _looks_like_company(raw)

    agency_name = None
    recruiter_name = None
    if " from " in f" {raw.lower()} ":
        # Simple V1.5 heuristic. Later: LLM extractor node.
        parts = raw.replace("\n", " ").split(" from ", 1)
        if len(parts) > 1:
            agency_name = parts[1].split(".", 1)[0].split(",", 1)[0].strip()[:80]
    if "i’m" in raw.lower() or "i'm" in raw.lower():
        marker = "I’m" if "I’m" in raw else "I'm"
        recruiter_name = raw.split(marker, 1)[1].strip().split(" ", 1)[0].strip(" ,.")[:40]

    entities: Entities = {
        "recruiter_name": recruiter_name,
        "agency_name": agency_name,
        "client_company": companies[0] if companies else None,
        "role": roles[0] if roles else None,
        "salary": salaries[0] if salaries else None,
        "emails": emails,
        "urls": urls,
        "domains": domains,
    }
    return {"entities": entities, "trace": _append_trace(state, "extract_entities")}


def deterministic_risk_scan(state: CaseState) -> CaseState:
    result = analyze_message(state["raw_input"])
    flags = [str(item) for item in result["concerning"]]
    return {"deterministic_flags": flags, "trace": _append_trace(state, "deterministic_risk_scan")}


def _report(lane: str, verdict: str, confidence: str, summary: str, evidence: List[EvidenceItem], gaps=None, concerns=None, safe_questions=None) -> CaseState:
    report, validated_evidence = make_lane_report(
        lane=lane,  # type: ignore[arg-type]
        verdict=verdict,  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
        summary=summary,
        evidence=evidence,
        gaps=gaps or [],
        concerns=concerns or [],
        safe_questions=safe_questions or [],
    )
    return {"lane_reports": {lane: report}, "evidence": validated_evidence}


def _agent_json(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    text = str(raw).strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)


def _clip_tool_result(result: Mapping[str, Any]) -> str:
    return json.dumps(result, sort_keys=True, default=str)[:900]


def _tool_result_to_evidence(lane: str, tool: str, args: Dict[str, Any], result: Mapping[str, Any]) -> List[EvidenceItem]:
    evidence: List[EvidenceItem] = []
    if tool == "search_web" and result.get("status") == "ok":
        for item in (result.get("results") or [])[:3]:
            evidence.append(_evidence(
                lane,
                "LLM-selected web search returned a result.",
                "search_result",
                item.get("url") or "Search API",
                f"query={args.get('query')} title={item.get('title')} description={item.get('description')}",
                "medium",
            ))
        return evidence
    source_type = "registry" if tool == "companies_house_lookup" else "technical_scan"
    if tool == "fetch_web_metadata":
        source_type = "official_site"
    evidence.append(_evidence(
        lane,
        f"LLM-selected tool ran: {tool}.",
        source_type,
        str(args.get("url") or args.get("domain") or args.get("email") or args.get("name") or args.get("package") or tool),
        _clip_tool_result(result),
        "high" if result.get("status") == "ok" else "medium",
    ))
    return evidence


def _coerce_str_list(items: Any) -> List[str]:
    if not items:
        return []
    if not isinstance(items, list):
        return [str(items)]
    return [str(item) for item in items]


def _normalize_verdict(value: Any, fallback: str) -> str:
    verdict = str(value or fallback).strip().lower()
    aliases = {
        "concern": "concerning",
        "concerned": "concerning",
        "suspicious": "concerning",
        "red_flag": "concerning",
        "red flag": "concerning",
        "high_risk": "concerning",
        "high risk": "concerning",
        "partially verified": "partially_verified",
        "not applicable": "not_applicable",
    }
    return aliases.get(verdict, verdict)


def _normalize_confidence(value: Any, fallback: str) -> str:
    confidence = str(value or fallback).strip().lower()
    return confidence if confidence in {"low", "medium", "high"} else fallback


def _clamp_score(value: Any) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return 0


def _candidate_recon(candidate: Mapping[str, Any], report: Mapping[str, Any]) -> Dict[str, Any]:
    company = str(candidate.get("inferred_client_company") or candidate.get("inferred_company") or "").strip()
    confidence = _clamp_score(candidate.get("inferred_company_confidence") or candidate.get("confidence_score"))
    matched_url = str(candidate.get("matched_original_jd_url") or candidate.get("matched_job_url") or "").strip()
    fields = _coerce_str_list(candidate.get("matched_fields") or [])
    if not company or confidence < 70:
        return {}
    return {
        "inferred_client_company": company,
        "confidence_score": confidence,
        "matched_original_jd_url": matched_url,
        "matched_fields": fields,
        "summary": str(candidate.get("summary") or report.get("summary") or ""),
    }


@traceable_if_configured(name="triage.agent_tool", run_type="tool")
def _record_agent_tool(tool: str, args: Dict[str, Any], result: Mapping[str, Any]) -> Mapping[str, Any]:
    return result


def _execute_agent_tool(tool: str, args: Dict[str, Any], settings) -> Mapping[str, Any]:
    if tool == "search_web":
        return search_web(str(args.get("query", "")), settings.search_api_provider, settings.search_api_key)
    if tool == "companies_house_lookup":
        return companies_house_lookup(str(args.get("name", "")), settings.companies_house_api_key)
    if tool == "rdap_domain_lookup":
        return rdap_domain_lookup(str(args.get("domain", "")))
    if tool == "check_email_domain":
        return check_email_domain(str(args.get("email", "")))
    if tool == "fetch_web_metadata":
        return fetch_web_metadata(str(args.get("url", "")))
    if tool == "expand_url":
        return expand_url(str(args.get("url", "")))
    if tool == "github_repo_check":
        return github_repo_check(str(args.get("url", "")))
    if tool == "npm_package_check":
        return npm_package_check(str(args.get("package", "")))
    if tool == "pypi_package_check":
        return pypi_package_check(str(args.get("package", "")))
    if tool == "sandbox_repo_static_analysis":
        return sandbox_repo_static_analysis(str(args.get("url", "")), live=settings.security_sandbox_live)
    return {"status": "unknown_tool"}


@traceable_if_configured(name="triage.lane_agent_loop", run_type="chain")
def _maybe_synthesize_lane(lane: str, lane_goal: str, fallback: CaseState, settings=None, source_state: CaseState | None = None) -> CaseState:
    settings = settings or load_settings()
    if not settings.enable_llm_lane_synthesis or lane not in settings.llm_lane_synthesis_lanes:
        return fallback
    try:
        llm_client = default_llm_client()
    except RuntimeError:
        return fallback

    report = (fallback.get("lane_reports") or {}).get(lane)
    if not report:
        return fallback
    allowed_tools = sorted(LANE_ALLOWED_TOOLS.get(lane, set()))
    evidence = list(report.get("evidence", []))
    gaps = list(report.get("gaps", []))
    concerns = list(report.get("concerns", []))
    safe_questions = list(report.get("safe_questions", []))
    tool_history: List[Dict[str, Any]] = []

    system = (
        f"You are the {lane} lane agent. You may choose and run lane-appropriate tools before writing the report. "
        "Use tools to investigate the supplied outreach. Do not invent tool results. "
        "Return JSON only. Either return {\"tool_calls\":[{\"tool\":...,\"args\":{...}}]} to request tools, "
        "or return the final LaneReport JSON. Final evidence will be replaced with actual evidence collected from input/tools."
    )
    if lane == "original_jd_recon":
        system += (
            " For this recon lane, work backwards from title, salary, location, stack, phrasing and assessment clues. "
            "Search for the likely original public JD and infer the likely end client/company. "
            "If confidence is at least 70, include neutral fields inferred_company or inferred_client_company, "
            "inferred_company_confidence as 0-100, matched_original_jd_url, and matched_fields. "
            "Do not conclude recruiter legitimacy or safety."
        )

    context = {
        "lane": lane,
        "lane_goal": lane_goal,
        "raw_input": (source_state or {}).get("raw_input", ""),
        "entities": (source_state or {}).get("entities", {}),
        "deterministic_flags": (source_state or {}).get("deterministic_flags", []),
        "original_jd_recon": (source_state or {}).get("original_jd_recon", {}),
        "current_report": report,
        "allowed_tools": {name: TOOL_SCHEMAS[name] for name in allowed_tools},
    }

    if lane == "security_assessment":
        context["security_escalation_policy"] = {
            "always_run_behavioral_scan": True,
            "link_analysis": "Only when URLs are present.",
            "repo_package_analysis": "Only when GitHub/package/install artifacts are present.",
            "sandbox": "Only for code/artifact cases; default to static Docker/no-network plan, never run unknown project scripts on host.",
        }

    for _turn in range(3):
        prompt = dict(context)
        prompt["evidence_so_far"] = evidence
        prompt["tool_history"] = tool_history
        try:
            candidate = _agent_json(llm_client([
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(prompt, indent=2, sort_keys=True)},
            ]))
        except (ValueError, TypeError, json.JSONDecodeError, RuntimeError, OSError):
            return fallback

        tool_calls = candidate.get("tool_calls") or []
        if tool_calls:
            for call in tool_calls[:4]:
                tool = str(call.get("tool", ""))
                args = dict(call.get("args") or {})
                if tool not in allowed_tools:
                    tool_history.append({"tool": tool, "args": args, "result": {"status": "tool_not_allowed"}})
                    continue
                result = _execute_agent_tool(tool, args, settings)
                _record_agent_tool(tool, args, result)
                tool_history.append({"tool": tool, "args": args, "result": result})
                evidence.extend(_tool_result_to_evidence(lane, tool, args, result))
            continue

        try:
            candidate["lane"] = lane
            candidate["evidence"] = evidence
            candidate.setdefault("gaps", gaps)
            candidate.setdefault("concerns", concerns)
            candidate.setdefault("safe_questions", safe_questions)
            report, validated_evidence = make_lane_report(
                lane=lane,  # type: ignore[arg-type]
                verdict=_normalize_verdict(candidate.get("verdict"), report["verdict"]),  # type: ignore[arg-type]
                confidence=_normalize_confidence(candidate.get("confidence"), report["confidence"]),  # type: ignore[arg-type]
                summary=str(candidate.get("summary") or report["summary"]),
                evidence=candidate["evidence"],
                gaps=_coerce_str_list(candidate.get("gaps", gaps)),
                concerns=_coerce_str_list(candidate.get("concerns", concerns)),
                safe_questions=_coerce_str_list(candidate.get("safe_questions", safe_questions)),
            )
            result_state: CaseState = {"lane_reports": {lane: report}, "evidence": validated_evidence}
            recon = _candidate_recon(candidate, report) if lane == "original_jd_recon" else {}
            if recon:
                result_state["original_jd_recon"] = recon  # type: ignore[typeddict-item]
            return result_state
        except (ValueError, TypeError, KeyError):
            fallback_report, validated_evidence = make_lane_report(
                lane=lane,  # type: ignore[arg-type]
                verdict=report["verdict"],
                confidence=report["confidence"],
                summary=report["summary"],
                evidence=evidence,
                gaps=gaps,
                concerns=concerns,
                safe_questions=safe_questions,
            )
            return {"lane_reports": {lane: fallback_report}, "evidence": validated_evidence}

    synthesized = synthesize_lane_report(
        lane=lane,  # type: ignore[arg-type]
        lane_goal=lane_goal,
        evidence=evidence,
        gaps=gaps,
        concerns=concerns,
        safe_questions=safe_questions,
        fallback_report=report,
        llm_client=llm_client,
    )
    return {"lane_reports": {lane: synthesized}, "evidence": synthesized["evidence"]}


def original_jd_recon(state: CaseState) -> CaseState:
    lane = "original_jd_recon"
    ent = state.get("entities", {})
    evidence: List[EvidenceItem] = []
    gaps: List[str] = []
    raw = state["raw_input"]
    clues = _uniq([
        str(ent.get("role") or ""),
        str(ent.get("salary") or ""),
        str(ent.get("agency_name") or ""),
    ])
    if clues:
        evidence.append(_evidence(
            lane,
            "JD recon clues extracted for reverse-search.",
            "input_text",
            "pasted outreach",
            ", ".join(clues),
            "medium",
        ))
    else:
        gaps.append("No strong title/salary/company clues for original JD recon.")
    if "confidential" in raw.lower():
        gaps.append("Recruiter withheld the end client, so recon must infer from role clues rather than trust a named company.")
    out = _report(
        lane,
        "unverified",
        "low",
        "Reverse-searches the job description to find a likely original public JD and infer the end client/company.",
        evidence,
        gaps,
        [],
        ["Can you share the official careers-page JD or confirm the inferred end client?"],
    )
    out = _maybe_synthesize_lane(
        lane,
        LANE_GOALS[lane],
        out,
        source_state=state,
    )
    out["trace"] = _append_trace(state, lane)
    return out


def recruiter_identity(state: CaseState) -> CaseState:
    lane = "recruiter_identity"
    ent = state.get("entities", {})
    evidence: List[EvidenceItem] = []
    gaps: List[str] = []
    if ent.get("recruiter_name"):
        evidence.append(_evidence(lane, "Recruiter name extracted from pasted message.", "input_text", "pasted outreach", str(ent["recruiter_name"]), "medium"))
    else:
        gaps.append("Recruiter name not found in pasted message.")
    if ent.get("emails"):
        evidence.append(_evidence(lane, "Recruiter/contact email extracted for domain matching.", "input_text", "pasted outreach", ", ".join(ent["emails"]), "high"))
        for email in ent.get("emails", [])[:2]:
            dns = check_email_domain(email)
            if dns["status"] == "ok":
                evidence.append(_evidence(
                    lane,
                    "Email domain DNS check completed.",
                    "technical_scan",
                    email,
                    f"domain={dns['domain']} has_mx={dns['has_mx']} mx={'; '.join(dns['mx_records'][:2])}",
                    "high" if dns["has_mx"] else "medium",
                ))
                if not dns["has_mx"]:
                    gaps.append(f"Email domain {dns['domain']} has no MX record from local DNS check.")
    else:
        gaps.append("Recruiter email missing; public identity and agency match need search.")
    out = _report(lane, "partially_verified" if evidence else "unverified", "medium" if evidence else "low", "Checks whether the named recruiter exists and matches the claimed agency.", evidence, gaps, [], ["Can you send the recruiter’s official email or LinkedIn profile?"])
    out = _maybe_synthesize_lane(
        lane,
        "Check whether the named recruiter exists and matches the claimed agency.",
        out,
        source_state=state,
    )
    out["trace"] = _append_trace(state, lane)
    return out


def agency_legitimacy(state: CaseState) -> CaseState:
    lane = "agency_legitimacy"
    ent = state.get("entities", {})
    settings = load_settings()
    evidence: List[EvidenceItem] = []
    gaps: List[str] = []
    if ent.get("agency_name"):
        evidence.append(_evidence(lane, "Agency claim extracted for agent-led checks.", "input_text", "pasted outreach", str(ent["agency_name"]), "medium"))
    else:
        gaps.append("Agency name not found in pasted message.")
    if ent.get("domains"):
        evidence.append(_evidence(lane, "Domain extracted for agent-led legitimacy checks.", "input_text", "pasted outreach", ", ".join(ent["domains"]), "medium"))
    out = _report(lane, "partially_verified" if evidence else "unverified", "low", "Checks whether the recruitment agency is real, active, and matched to the sender.", evidence, gaps, [], ["Can you confirm the agency website and company registration name?"])
    out = _maybe_synthesize_lane(
        lane,
        "Check whether the recruitment agency is real, active, and matched to the sender.",
        out,
        settings,
        source_state=state,
    )
    out["trace"] = _append_trace(state, lane)
    return out


def client_company(state: CaseState) -> CaseState:
    lane = "client_company"
    ent = state.get("entities", {})
    settings = load_settings()
    raw = state["raw_input"]
    recon = state.get("original_jd_recon") or {}
    inferred_company = recon.get("inferred_client_company")
    evidence: List[EvidenceItem] = []
    gaps: List[str] = []
    concerns: List[str] = []
    client_candidate = ent.get("client_company") or inferred_company
    if inferred_company:
        evidence.append(_evidence(
            lane,
            "Original JD recon supplied a threshold-gated inferred client/company lead.",
            "tool_result",
            str(recon.get("matched_original_jd_url") or "original_jd_recon"),
            f"company={inferred_company} confidence={recon.get('confidence_score')} matched_fields={', '.join(recon.get('matched_fields') or [])}",
            "medium" if int(recon.get("confidence_score") or 0) < 85 else "high",
        ))
    if client_candidate:
        evidence.append(_evidence(lane, "Client/company claim extracted for official-site verification.", "input_text", "pasted outreach" if ent.get("client_company") else "original_jd_recon", str(client_candidate), "medium"))
        search = search_web(f"{client_candidate} official website careers", settings.search_api_provider, settings.search_api_key)
        if search["status"] == "ok" and search["results"]:
            top_result = search["results"][0]
            evidence.append(_evidence(
                lane,
                "Search API returned a client/company discovery result.",
                "search_result",
                top_result.get("url") or "Search API",
                f"{top_result.get('title')} — {top_result.get('description')}",
                "medium",
            ))
            if settings.expand_urls_live and top_result.get("url"):
                meta = fetch_web_metadata(top_result["url"])
                if meta["status"] == "ok":
                    evidence.append(_evidence(
                        lane,
                        "Website metadata fetched from top search result.",
                        "official_site",
                        meta.get("final_url") or top_result["url"],
                        f"title={meta.get('title')} description={meta.get('description')}",
                        "medium",
                    ))
        elif search["status"] == "missing_api_key":
            gaps.append("Client/company search skipped: SEARCH_API_KEY missing.")
        else:
            gaps.append(f"Client/company search did not return evidence: {search.get('status')}.")
    else:
        gaps.append("End client/company not clearly named.")
    if "confidential" in raw.lower():
        concerns.append("Client/company is being withheld as confidential.")
    out = _report(lane, "partially_verified" if evidence else "unverified", "low", "Checks whether the end client/company exists and has product/hiring activity.", evidence, gaps, concerns, ["Can you share the end client/company name before a call?"])
    out = _maybe_synthesize_lane(
        lane,
        "Check whether the end client/company exists and has product/hiring activity.",
        out,
        settings,
        source_state=state,
    )
    out["trace"] = _append_trace(state, lane)
    return out


def job_jd_verification(state: CaseState) -> CaseState:
    lane = "job_jd_verification"
    ent = state.get("entities", {})
    settings = load_settings()
    urls = ent.get("urls", []) or []
    recon = state.get("original_jd_recon") or {}
    evidence: List[EvidenceItem] = []
    gaps: List[str] = []
    concerns: List[str] = []
    if ent.get("role"):
        evidence.append(_evidence(lane, "Role title/type extracted from message.", "input_text", "pasted outreach", str(ent["role"]), "medium"))
    if ent.get("salary"):
        evidence.append(_evidence(lane, "Salary/rate claim extracted for realism check.", "input_text", "pasted outreach", str(ent["salary"]), "medium"))
    if recon.get("matched_original_jd_url"):
        evidence.append(_evidence(
            lane,
            "Original JD recon found a likely source JD to verify independently.",
            "search_result",
            str(recon.get("matched_original_jd_url")),
            f"company={recon.get('inferred_client_company')} confidence={recon.get('confidence_score')} matched_fields={', '.join(recon.get('matched_fields') or [])}",
            "medium" if int(recon.get("confidence_score") or 0) < 85 else "high",
        ))
    if any("careers" in url.lower() or "jobs" in url.lower() for url in urls):
        evidence.append(_evidence(lane, "Potential official/careers JD URL present.", "input_text", "pasted outreach", ", ".join(urls), "medium"))
        if settings.expand_urls_live:
            for url in [u for u in urls if "careers" in u.lower() or "jobs" in u.lower()][:2]:
                meta = fetch_web_metadata(url)
                if meta["status"] == "ok":
                    evidence.append(_evidence(
                        lane,
                        "Job/careers URL metadata fetched.",
                        "official_site",
                        meta.get("final_url") or url,
                        f"title={meta.get('title')} description={meta.get('description')}",
                        "medium",
                    ))
                else:
                    gaps.append(f"Job/careers URL metadata fetch failed for {url}: {meta.get('error')}")
    else:
        gaps.append("No obvious official careers-page JD found in pasted message.")
    for url in urls:
        if parse_github_repo(url):
            gh = github_repo_check(url)
            if gh["status"] == "ok":
                evidence.append(_evidence(
                    lane,
                    "GitHub assessment repository public metadata checked.",
                    "technical_scan",
                    url,
                    f"repo={gh['repo']} created={gh.get('created_at')} updated={gh.get('updated_at')} stars={gh.get('stars')} forks={gh.get('forks')}",
                    "medium",
                ))
            else:
                gaps.append(f"GitHub repository check failed for {url}: {gh.get('status')}")
    if any("bit.ly" in url.lower() for url in urls):
        concerns.append("Job/assessment link uses a shortener rather than a canonical careers URL.")
    out = _report(lane, "partially_verified" if evidence else "unverified", "medium" if evidence else "low", "Checks official JD existence, freshness, salary realism, and text reuse.", evidence, gaps, concerns, ["Can you send the official careers-page JD, not a job-board mirror?"])
    out = _maybe_synthesize_lane(
        lane,
        "Check official JD existence, freshness, salary realism, repository metadata, and text reuse.",
        out,
        settings,
        source_state=state,
    )
    out["trace"] = _append_trace(state, lane)
    return out


def security_assessment(state: CaseState) -> CaseState:
    lane = "security_assessment"
    ent = state.get("entities", {})
    settings = load_settings()
    flags = state.get("deterministic_flags") or []
    evidence = [_evidence(lane, "Deterministic safety scanner flagged risk pattern.", "input_text", "pasted outreach", flag, "high") for flag in flags]
    concerns = [flag for flag in flags if "No major scam" not in flag]
    gaps: List[str] = []
    urls = ent.get("urls", []) or []
    raw = state["raw_input"]
    has_code_assessment = bool(CODE_ASSESSMENT_RE.search(raw))
    has_install_command = bool(NPM_INSTALL_COMMAND_RE.search(raw) or PIP_INSTALL_COMMAND_RE.search(raw))

    if urls:
        evidence.append(_evidence(
            lane,
            "Security lane escalated from behavioural scan to link analysis because URLs are present.",
            "input_text",
            "pasted outreach",
            ", ".join(urls[:3]),
            "high",
        ))
        for url in urls[:3]:
            if parse_github_repo(url):
                gh = github_repo_check(url)
                if gh["status"] == "ok":
                    evidence.append(_evidence(
                        lane,
                        "GitHub assessment repository metadata checked before any code execution.",
                        "technical_scan",
                        url,
                        f"repo={gh['repo']} created={gh.get('created_at')} updated={gh.get('updated_at')} stars={gh.get('stars')} forks={gh.get('forks')}",
                        "high",
                    ))
                else:
                    gaps.append(f"GitHub repository check failed for {url}: {gh.get('status')}.")
                sandbox = sandbox_repo_static_analysis(url, live=settings.security_sandbox_live)
                evidence.append(_evidence(
                    lane,
                    "GitHub assessment triggered sandbox gate; static Docker analysis is planned or executed without running project scripts.",
                    "technical_scan",
                    url,
                    _clip_tool_result(sandbox),
                    "high" if sandbox.get("status") in {"ok", "planned"} else "medium",
                ))
            elif settings.expand_urls_live:
                expanded = expand_url(url)
                if expanded["status"] == "ok":
                    evidence.append(_evidence(
                        lane,
                        "URL expander resolved link destination.",
                        "technical_scan",
                        url,
                        f"final_url={expanded.get('final_url')} final_domain={expanded.get('final_domain')}",
                        "high" if expanded.get("is_shortener") else "medium",
                    ))
                else:
                    gaps.append(f"URL expansion failed for {url}: {expanded.get('error')}")
            else:
                gaps.append("Live URL expansion skipped: set EXPAND_URLS_LIVE=true to enable redirect/metadata checks.")
    else:
        gaps.append("No URL/repository/package artifact present; security lane stayed at behavioural-risk analysis and did not sandbox anything.")

    if has_code_assessment:
        evidence.append(_evidence(
            lane,
            "Code-assessment language detected; unknown code should not be executed on the host.",
            "input_text",
            "pasted outreach",
            "clone/repo/assessment/run locally/install dependencies",
            "high",
        ))
        concerns.append("Code assessment or local-run language present; require static inspection/sandbox before any execution.")
    if has_install_command:
        evidence.append(_evidence(
            lane,
            "Package install command detected; treat as dependency-supply-chain risk until inspected.",
            "input_text",
            "pasted outreach",
            "npm/pip install command",
            "high",
        ))
        concerns.append("Install command requested before role/company verification.")

    for package in _uniq(NPM_PACKAGE_RE.findall(raw))[:3]:
        npm = npm_package_check(package)
        if npm["status"] == "ok":
            evidence.append(_evidence(
                lane,
                "NPM package registry metadata checked for assessment dependency.",
                "technical_scan",
                f"npm:{package}",
                f"package={npm['package']} version={npm.get('version')} created={npm.get('created')} modified={npm.get('modified')}",
                "medium",
            ))
        else:
            gaps.append(f"NPM package check failed for {package}: {npm.get('status')}")

    for package in _uniq(PIP_PACKAGE_RE.findall(raw))[:3]:
        pypi = pypi_package_check(package)
        if pypi["status"] == "ok":
            evidence.append(_evidence(
                lane,
                "PyPI package registry metadata checked for assessment dependency.",
                "technical_scan",
                f"pypi:{package}",
                f"package={pypi['package']} version={pypi.get('version')} releases={pypi.get('release_count')} summary={pypi.get('summary')}",
                "medium",
            ))
        else:
            gaps.append(f"PyPI package check failed for {package}: {pypi.get('status')}")

    verdict = "concerning" if concerns else "partially_verified"
    confidence = "high" if concerns else "medium"
    out = _report(lane, verdict, confidence, "Checks links, code-assessment bait, wallet risk, channel moves, and unsafe requests.", evidence, gaps, concerns, ["Does any assessment require running code, installing packages, or connecting a wallet?"])
    out = _maybe_synthesize_lane(
        lane,
        "Check links, code-assessment bait, wallet risk, channel moves, and unsafe requests.",
        out,
        settings,
        source_state=state,
    )
    out["trace"] = _append_trace(state, lane)
    return out


def reputation_pattern(state: CaseState) -> CaseState:
    lane = "reputation_pattern"
    ent = state.get("entities", {})
    recon = state.get("original_jd_recon") or {}
    evidence: List[EvidenceItem] = []
    gaps = ["Review/reputation snippet search not connected yet."]
    targets = _uniq([str(x) for x in [ent.get("agency_name"), ent.get("client_company"), recon.get("inferred_client_company"), *(ent.get("domains") or [])] if x])
    if targets:
        evidence.append(_evidence(lane, "Reputation search targets identified.", "input_text", "extracted entities", ", ".join(targets), "medium"))
    out = _report(lane, "unverified", "low", "Checks review snippets and repeated complaint/warning patterns; never acts as sole verdict.", evidence, gaps, [], ["Any review signal should be treated as pattern evidence, not proof."])
    out = _maybe_synthesize_lane(
        lane,
        "Check review snippets and repeated complaint/warning patterns without treating them as sole proof.",
        out,
        source_state=state,
    )
    out["trace"] = _append_trace(state, lane)
    return out


def merge_evidence(state: CaseState) -> CaseState:
    reports = state.get("lane_reports") or {}
    evidence: List[EvidenceItem] = []
    gaps: List[str] = []
    conflicts: List[str] = []
    for report in reports.values():
        evidence.extend(report.get("evidence", []))
        gaps.extend(report.get("gaps", []))
    if reports.get("agency_legitimacy", {}).get("verdict") in {"partially_verified", "verified"} and reports.get("job_jd_verification", {}).get("gaps"):
        conflicts.append("Agency/recruiter may have clues, but official JD is still not verified.")
    return {"gaps": _uniq(gaps), "conflicts": conflicts, "trace": _append_trace(state, "merge_evidence")}



def final_report(state: CaseState) -> CaseState:
    reports = state.get("lane_reports") or {}
    gaps = state.get("gaps", []) or []
    conflicts = state.get("conflicts", []) or []
    final_action = decide_final_action(reports, gaps, conflicts)
    score = score_case(reports, gaps, conflicts, final_action)
    evidence_ledger = evidence_ledger_from_state(state)
    verification_digest = build_verification_digest(evidence_ledger)
    opportunity_state = dict(state)
    opportunity_state.update({"final_action": final_action, "score": score, "evidence_ledger": evidence_ledger})
    opportunity_read = build_opportunity_read(opportunity_state)
    report_md = render_final_report(reports, final_action, score, opportunity_read)
    return {
        "final_action": final_action,
        "score": score,
        "evidence_ledger": evidence_ledger,
        "verification_digest": verification_digest,
        "opportunity_read": opportunity_read,
        "final_report": report_md,
        "trace": _append_trace(state, "final_report"),
    }
