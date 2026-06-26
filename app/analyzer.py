"""Core triage logic for Recruiter Risk Triage V1.

This deliberately does NOT claim to verify companies. It turns pasted outreach into:
- extracted claims/clues
- risk flags
- safe next question
- live-research links for the agent/human to verify
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from typing import Dict, List
from urllib.parse import quote_plus, urlparse

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
URL_RE = re.compile(r"https?://[^\s)>'\"]+", re.I)
SALARY_RE = re.compile(r"(?:£|GBP\s*)\s?\d{2,3}(?:,?\d{3})?(?:\s?[-–]\s?(?:£|GBP\s*)?\d{2,3}(?:,?\d{3})?)?", re.I)
ROLE_RE = re.compile(
    r"\b((?:senior|staff|lead|principal|mid|junior)?\s*(?:ai|ml|machine learning|platform|backend|full[- ]stack|security|crypto|rust|node|python)\s+(?:engineer|developer|architect|lead|consultant))\b",
    re.I,
)

SHORTENER_DOMAINS = {
    "bit.ly",
    "tinyurl.com",
    "t.co",
    "goo.gl",
    "ow.ly",
    "buff.ly",
    "shorturl.at",
    "cutt.ly",
    "rebrand.ly",
}

HIGH_RISK_PATTERNS = [
    (re.compile(r"\b(seed phrase|private key|recovery phrase)\b", re.I), "Wallet secret requested or mentioned."),
    (re.compile(r"\b(connect (?:your )?wallet|wallet connect|sign (?:a )?message)\b", re.I), "Wallet interaction requested before verification."),
    (re.compile(r"\b(npm install|pip install|pnpm install|yarn install|run locally|clone (?:this )?repo|github repo|zip file|assessment repo)\b", re.I), "Code/assessment bait: they may ask you to run code locally."),
    (re.compile(r"\b(telegram|whatsapp|signal)\b", re.I), "Channel move requested before the role/company is proven."),
]

MEDIUM_RISK_PATTERNS = [
    (re.compile(r"\b(urgent|today|asap|immediately|quick call)\b", re.I), "Urgency pressure."),
    (re.compile(r"\b(confidential client|client confidential|stealth client|cannot disclose)\b", re.I), "Client/company name withheld."),
    (re.compile(r"\b(crypto|web3|defi|wallet|token|blockchain)\b", re.I), "Crypto/Web3 context — extra scam and assessment caution needed."),
    (re.compile(r"\b(passport|driving licence|bank details|national insurance|ni number|references)\b", re.I), "Personal info requested or likely too early."),
]


def _uniq(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        clean = " ".join(item.strip().split())
        if clean and clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


def _domain(url_or_email: str) -> str:
    if "@" in url_or_email and not url_or_email.startswith("http"):
        return url_or_email.split("@", 1)[1].lower()
    parsed = urlparse(url_or_email)
    host = parsed.netloc.lower().split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def _looks_like_company(text: str) -> List[str]:
    # Claim extraction only. Do not treat as verified truth.
    patterns = [
        r"\bat\s+([A-Z][A-Za-z0-9&. -]{2,40})(?:[\.,\n]|$)",
        r"\bfrom\s+([A-Z][A-Za-z0-9&. -]{2,40})(?:[\.,\n]|$)",
        r"\bfor\s+(?:a|an|the)?\s*(?:role\s+)?(?:at\s+)?([A-Z][A-Za-z0-9&. -]{2,40})(?:[\.,\n]|$)",
    ]
    found: List[str] = []
    for pat in patterns:
        for match in re.finditer(pat, text):
            name = match.group(1).strip()
            if not re.search(r"\b(role|engineer|developer|salary|remote|today|urgent)\b", name, re.I):
                found.append(name)
    return _uniq(found[:5])


def build_research_links(text: str, emails: List[str], urls: List[str], companies: List[str]) -> List[Dict[str, str]]:
    domains = _uniq([_domain(item) for item in emails + urls if _domain(item)])
    query_base = " ".join(companies[:2] + domains[:2]) or text[:120]
    searches = [
        ("DuckDuckGo: exact recruiter/company search", f"https://duckduckgo.com/?q={quote_plus(query_base)}"),
        ("Companies House search", f"https://find-and-update.company-information.service.gov.uk/search?q={quote_plus(query_base)}"),
        ("LinkedIn public search", f"https://www.google.com/search?q={quote_plus(query_base + ' LinkedIn recruiter')}") ,
        ("Official careers/JD search", f"https://www.google.com/search?q={quote_plus(query_base + ' careers job')}") ,
        ("Reputation snippets", f"https://www.google.com/search?q={quote_plus(query_base + ' Glassdoor Indeed Reddit reviews')}") ,
    ]
    return [{"label": label, "url": url} for label, url in searches]


def analyze_message(text: str) -> Dict[str, object]:
    raw = text or ""
    lowered = raw.lower()
    emails = _uniq(EMAIL_RE.findall(raw))
    urls = _uniq(URL_RE.findall(raw))
    salaries = _uniq(SALARY_RE.findall(raw))
    roles = _uniq([m.group(1).strip() for m in ROLE_RE.finditer(raw)])
    companies = _looks_like_company(raw)
    domains = _uniq([_domain(x) for x in emails + urls if _domain(x)])

    verified: List[str] = []
    if emails:
        verified.append("Pasted message contains email/contact clue(s): " + ", ".join(emails))
    if urls:
        verified.append("Pasted message contains URL clue(s): " + ", ".join(urls))
    if domains:
        verified.append("Extracted domain(s) to verify: " + ", ".join(domains))
    if salaries:
        verified.append("Pasted message claims salary/rate: " + ", ".join(salaries))
    if roles:
        verified.append("Pasted message claims role type: " + ", ".join(roles))
    if not verified:
        verified.append("No hard external proof in the pasted text yet — only the outreach wording itself.")

    unverified: List[str] = [
        "Recruiter identity: needs public profile + agency match.",
        "Agency legitimacy: needs official site, Companies House/registry, team/niche check.",
        "Official careers-page JD: not proven until found on the end-client/company domain.",
        "Client/company status: active website, funding/product activity and shutdown signals still need live checks.",
    ]
    for company in companies:
        unverified.insert(0, f"Company/client claim to verify live: {company}")

    concerning: List[str] = []
    high_hits = 0
    medium_hits = 0

    for url in urls:
        domain = _domain(url)
        if domain in SHORTENER_DOMAINS:
            high_hits += 1
            concerning.append(f"Uses shortened or redirected link: {domain}")

    for pattern, message in HIGH_RISK_PATTERNS:
        if pattern.search(raw):
            high_hits += 1
            concerning.append(message)

    for pattern, message in MEDIUM_RISK_PATTERNS:
        if pattern.search(raw):
            medium_hits += 1
            concerning.append(message)

    if salaries and re.search(r"\b(junior|entry|graduate)\b", lowered) and re.search(r"£\s?\d{3},?\d{3}|£\s?100", raw):
        medium_hits += 1
        concerning.append("Salary may be unusually high for stated level — verify before engaging deeply.")

    if not concerning:
        concerning.append("No major scam pattern detected from wording alone, but legitimacy is still unverified.")

    safe_next_question = (
        "Can you share the end client/company name, the official careers-page JD, "
        "and confirm whether any assessment requires running code or connecting a wallet before I book a call?"
    )

    do_not_do = [
        "Don’t run code, install packages, open zips, or clone assessment repos until the company and assessment source are verified.",
        "Don’t connect a wallet, sign wallet messages, share seed phrases, or share private keys.",
        "Don’t send ID, bank details, NI number, references, or detailed personal info before the role and counterparty are proven.",
        "Don’t move to WhatsApp/Telegram as the main channel before there is an official JD/company trail.",
        "Don’t treat reviews as verdicts — use them for patterns only.",
    ]

    legitimacy = 1
    if emails:
        legitimacy += 1
    if urls:
        legitimacy += 1
    if any("careers" in u.lower() or "jobs" in u.lower() for u in urls):
        legitimacy += 1
    if companies:
        legitimacy += 1
    legitimacy = min(5, legitimacy)

    role_fit = 2
    if re.search(r"\b(ai|ml|platform|backend|python|security|infra|infrastructure|agent)\b", lowered):
        role_fit += 2
    if re.search(r"\b(react|frontend|kotlin|mobile)\b", lowered):
        role_fit -= 1
    role_fit = max(0, min(5, role_fit))

    if high_hits:
        security_risk = "High"
    elif medium_hits >= 2:
        security_risk = "Medium"
    else:
        security_risk = "Low"

    confidence = "Low"
    if emails or urls or companies:
        confidence = "Medium"
    if urls and emails and companies and not high_hits:
        confidence = "High"

    return {
        "verified": _uniq(verified),
        "unverified": _uniq(unverified),
        "concerning": _uniq(concerning),
        "safe_next_question": safe_next_question,
        "do_not_do": do_not_do,
        "scores": {
            "legitimacy": legitimacy,
            "role_fit": role_fit,
            "security_risk": security_risk,
            "confidence": confidence,
        },
        "research_links": build_research_links(raw, emails, urls, companies),
        "extracted": {
            "emails": emails,
            "urls": urls,
            "domains": domains,
            "companies": companies,
            "roles": roles,
            "salaries": salaries,
        },
    }


def render_markdown(result: Dict[str, object]) -> str:
    def bullets(items: List[str]) -> str:
        return "\n".join(f"- {item}" for item in items)

    scores = result["scores"]  # type: ignore[index]
    return f"""## Verified
{bullets(result['verified'])}

## Unverified
{bullets(result['unverified'])}

## Concerning
{bullets(result['concerning'])}

## Safe next question
\"{result['safe_next_question']}\"

## Do-not-do list
{bullets(result['do_not_do'])}

## Score
Legitimacy: {scores['legitimacy']}/5
Role fit: {scores['role_fit']}/5
Security risk: {scores['security_risk']}
Confidence: {scores['confidence']}
"""
