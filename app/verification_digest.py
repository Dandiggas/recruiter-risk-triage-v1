from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional


STATUS_PASS = "pass"
STATUS_WARN = "warn"
STATUS_INFO = "info"
STATUS_FAIL = "fail"


def _checked_date(checked_at: Optional[datetime] = None) -> str:
    dt = checked_at or datetime.now(timezone.utc)
    return dt.date().isoformat()


def _json_or_none(value: str) -> Optional[Dict[str, Any]]:
    value = (value or "").strip()
    if not value.startswith("{"):
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _kv_text(value: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    # Handles simple evidence quotes like: domain=talentco.example has_mx=True mx=a; b
    for key, val in re.findall(r"([a-zA-Z_]+)=([^=]+?)(?=\s+[a-zA-Z_]+=|$)", value or ""):
        out[key] = val.strip().strip(",")
    return out


def _card(
    *,
    title: str,
    status: str,
    plain_english: str,
    source: str,
    technical_check: str,
    why_it_matters: str,
    checked_at: str,
    dates: Optional[Mapping[str, str]] = None,
    details: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    return {
        "title": title,
        "status": status,
        "plain_english": plain_english,
        "source": source,
        "technical_check": technical_check,
        "why_it_matters": why_it_matters,
        "dates": {"checked": checked_at, **{k: v for k, v in (dates or {}).items() if v}},
        "details": [str(item) for item in (details or []) if str(item).strip()],
    }


def _add_dns_card(cards: List[Dict[str, Any]], item: Mapping[str, Any], checked: str) -> bool:
    finding = str(item.get("finding") or "")
    quote = str(item.get("quote") or "")
    if "Email domain DNS check" not in finding and "check_email_domain" not in finding:
        return False
    payload = _json_or_none(quote) or _kv_text(quote)
    domain = str(payload.get("domain") or item.get("source") or "").split("@")[-1]
    has_mx = str(payload.get("has_mx") or "").lower() in {"true", "1", "yes"}
    mx = payload.get("mx_records") or payload.get("mx") or ""
    if isinstance(mx, list):
        mx_details = "; ".join(str(x) for x in mx[:3])
    else:
        mx_details = str(mx)
    cards.append(_card(
        title="Email domain can receive mail" if has_mx else "Email domain has no mail records",
        status=STATUS_PASS if has_mx else STATUS_WARN,
        plain_english=f"{domain} resolves as a mail-capable domain." if has_mx else f"{domain} did not return MX mail records in the local DNS check.",
        source=domain,
        technical_check="DNS/MX lookup",
        why_it_matters="A real recruiter domain should normally resolve and be able to receive corporate email.",
        checked_at=checked,
        details=[f"MX records: {mx_details}" if mx_details else "MX records: none returned"],
    ))
    return True


def _add_rdap_card(cards: List[Dict[str, Any]], item: Mapping[str, Any], checked: str) -> bool:
    finding = str(item.get("finding") or "")
    quote = str(item.get("quote") or "")
    if "rdap_domain_lookup" not in finding and "RDAP" not in finding and "registration_date" not in quote:
        return False
    payload = _json_or_none(quote)
    if not payload:
        return False
    domain = str(payload.get("domain") or item.get("source") or "")
    if payload.get("status") != "ok":
        cards.append(_card(
            title="Domain registration lookup failed",
            status=STATUS_WARN,
            plain_english=f"Hermes could not confirm RDAP registration data for {domain}.",
            source=domain,
            technical_check="RDAP domain lookup",
            why_it_matters="RDAP helps show whether a domain is real, established, and registered through a recognised registry.",
            checked_at=checked,
            details=[str(payload.get("error") or payload.get("status"))],
        ))
        return True
    cards.append(_card(
        title="Domain registration found",
        status=STATUS_PASS,
        plain_english=f"{domain} has public domain registration data.",
        source=domain,
        technical_check="RDAP domain lookup",
        why_it_matters="Established corporate domains are harder to fake than newly registered throwaway domains.",
        checked_at=checked,
        dates={
            "registered": str(payload.get("registration_date") or ""),
            "last_updated": str(payload.get("last_changed") or ""),
            "expires": str(payload.get("expiration_date") or ""),
        },
        details=[f"Registrar: {payload.get('registrar')}" if payload.get("registrar") else "Registration data returned by RDAP"],
    ))
    return True


def _add_companies_house_card(cards: List[Dict[str, Any]], item: Mapping[str, Any], checked: str) -> bool:
    finding = str(item.get("finding") or "")
    quote = str(item.get("quote") or "")
    if "companies_house_lookup" not in finding and "Companies House" not in finding and "company_number" not in quote:
        return False
    payload = _json_or_none(quote)
    if not payload:
        return False
    results = payload.get("results") or []
    if payload.get("status") != "ok" or not results:
        cards.append(_card(
            title="Companies House check incomplete",
            status=STATUS_WARN,
            plain_english=f"Companies House did not return a clear company match for {payload.get('query') or item.get('source')}.",
            source="Companies House",
            technical_check="Companies House lookup",
            why_it_matters="A UK legal-entity match helps distinguish real employers/recruiters from invented names.",
            checked_at=checked,
            details=[str(payload.get("status") or "No company results returned")],
        ))
        return True
    result = results[0]
    name = result.get("company_name") or payload.get("query") or item.get("source")
    status = str(result.get("company_status") or "").lower()
    active = status == "active"
    cards.append(_card(
        title="Company is active" if active else "Company found on Companies House",
        status=STATUS_PASS if active else STATUS_INFO,
        plain_english=f"{name} is listed on Companies House with status: {result.get('company_status') or 'unknown'}.",
        source="Companies House",
        technical_check="Companies House lookup",
        why_it_matters="Confirms the UK company exists as a registered legal entity and shows how established it is.",
        checked_at=checked,
        dates={"incorporated": str(result.get("date_of_creation") or "")},
        details=[
            f"Company number: {result.get('company_number')}" if result.get("company_number") else "",
            f"Type: {result.get('company_type')}" if result.get("company_type") else "",
            f"Address: {result.get('address_snippet')}" if result.get("address_snippet") else "",
        ],
    ))
    return True


def _add_official_jd_card(cards: List[Dict[str, Any]], item: Mapping[str, Any], checked: str) -> bool:
    finding = str(item.get("finding") or "")
    source = str(item.get("source") or "")
    quote = str(item.get("quote") or "")
    haystack = (source + " " + quote).lower()
    if not any(token in haystack for token in ["career", "careers", "jobs", "job"]):
        return False
    payload = _json_or_none(quote) or _kv_text(quote)
    title = payload.get("title") or None
    is_direct_or_official = (
        item.get("source_type") == "official_site"
        or "source jd" in finding.lower()
        or source.lower().startswith(("https://career.", "http://career.", "https://careers.", "http://careers."))
    )
    cards.append(_card(
        title="Official job/JD evidence found" if is_direct_or_official else "Candidate job/JD search result found",
        status=STATUS_PASS if is_direct_or_official else STATUS_INFO,
        plain_english=(
            f"Hermes found a careers/job source that appears to match the recruiter message{f': {title}' if title else ''}."
            if is_direct_or_official
            else f"Hermes found a web-search candidate that may relate to the role{f': {title}' if title else ''}. Treat this as a lead, not verification."
        ),
        source=source,
        technical_check="Careers page / web metadata / search result",
        why_it_matters="A matching official JD is stronger evidence than a recruiter summary or copied job-board text; generic search results are only leads until verified.",
        checked_at=checked,
        dates={"observed": checked},
        details=[quote[:260] if quote else "Job/careers source present"],
    ))
    return True


def _add_website_card(cards: List[Dict[str, Any]], item: Mapping[str, Any], checked: str) -> bool:
    finding = str(item.get("finding") or "")
    quote = str(item.get("quote") or "")
    if "Website metadata" not in finding and "fetch_web_metadata" not in finding:
        return False
    payload = _json_or_none(quote) or _kv_text(quote)
    source = str(payload.get("final_url") or item.get("source") or "")
    cards.append(_card(
        title="Company website resolves",
        status=STATUS_PASS,
        plain_english="Hermes reached the company website or careers page and extracted page metadata.",
        source=source,
        technical_check="Website metadata fetch",
        why_it_matters="A reachable official site supports that the company/JD source exists outside the recruiter message.",
        checked_at=checked,
        dates={"observed": checked},
        details=[f"Title: {payload.get('title')}" if payload.get("title") else "Metadata fetched"],
    ))
    return True


def build_verification_digest(evidence: Iterable[Mapping[str, Any]], checked_at: Optional[datetime] = None) -> List[Dict[str, Any]]:
    checked = _checked_date(checked_at)
    cards: List[Dict[str, Any]] = []
    seen = set()
    for item in evidence or []:
        before = len(cards)
        handled = (
            _add_dns_card(cards, item, checked)
            or _add_rdap_card(cards, item, checked)
            or _add_companies_house_card(cards, item, checked)
            or _add_official_jd_card(cards, item, checked)
            or _add_website_card(cards, item, checked)
        )
        if not handled or len(cards) == before:
            continue
        card = cards[-1]
        key = (card["title"], card["source"], card["technical_check"])
        if key in seen:
            cards.pop()
            continue
        seen.add(key)
    return cards
