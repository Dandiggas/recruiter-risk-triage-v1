from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Union
from urllib.error import URLError
from urllib.request import Request, urlopen

from pydantic import ValidationError

from app.graph.contracts import LaneName, LaneReportModel
from app.observability import traceable_if_configured

LLMClient = Callable[[List[Dict[str, str]]], Union[Mapping[str, Any], str]]

LANE_SYNTHESIS_PROMPTS: Dict[LaneName, str] = {
    "original_jd_recon": """You are the Original JD Recon lane.
Use only the supplied evidence, gaps, concerns, and safe questions.
Do not invent original job descriptions, company names, careers pages, or sources.
Return JSON matching the LaneReport contract.""",
    "recruiter_identity": """You are the Recruiter Identity lane.
Use only the supplied evidence, gaps, concerns, and safe questions.
Do not invent people, profiles, emails, employers, sources, or checks.
Return JSON matching the LaneReport contract.""",
    "agency_legitimacy": """You are the Agency Legitimacy lane.
Use only the supplied evidence, gaps, concerns, and safe questions.
Do not invent registry results, websites, Companies House records, domains, or sources.
Return JSON matching the LaneReport contract.""",
    "client_company": """You are the Client / Company lane.
Use only the supplied evidence, gaps, concerns, and safe questions.
Do not invent official sites, careers pages, companies, hiring activity, or sources.
Return JSON matching the LaneReport contract.""",
    "job_jd_verification": """You are the Job / JD Verification lane.
Use only the supplied evidence, gaps, concerns, and safe questions.
Do not invent job descriptions, salaries, careers pages, repository facts, or sources.
Return JSON matching the LaneReport contract.""",
    "security_assessment": """You are the Security Assessment lane.
Use only the supplied evidence, gaps, concerns, and safe questions.
Do not invent malware findings, package metadata, URL destinations, wallet risks, or sources.
Return JSON matching the LaneReport contract.""",
    "reputation_pattern": """You are the Reputation Pattern lane.
Use only the supplied evidence, gaps, concerns, and safe questions.
Do not invent reviews, scam reports, complaints, search snippets, or sources.
Return JSON matching the LaneReport contract.""",
}


def _build_user_payload(
    *,
    lane: LaneName,
    lane_goal: str,
    evidence: List[Dict],
    gaps: List[str],
    concerns: List[str],
    safe_questions: List[str],
) -> str:
    return json.dumps(
        {
            "task": "Write a concise lane summary and verdict from the supplied evidence only.",
            "lane": lane,
            "lane_goal": lane_goal,
            "allowed_verdicts": ["verified", "partially_verified", "unverified", "concerning", "not_applicable"],
            "allowed_confidence": ["low", "medium", "high"],
            "supplied_evidence": evidence,
            "supplied_gaps": gaps,
            "supplied_concerns": concerns,
            "supplied_safe_questions": safe_questions,
            "required_json_shape": {
                "lane": lane,
                "verdict": "one allowed verdict",
                "confidence": "low|medium|high",
                "summary": "short human-readable lane summary",
                "evidence": "copy supplied evidence only; invented evidence will be discarded",
                "gaps": "list of gaps grounded in supplied gaps/evidence",
                "concerns": "list of concerns grounded in supplied concerns/evidence",
                "safe_questions": "list of safe follow-up questions",
            },
        },
        indent=2,
        sort_keys=True,
    )


def _coerce_llm_output(raw: Union[Mapping[str, Any], str]) -> Dict[str, Any]:
    if isinstance(raw, str):
        cleaned = raw.strip()
        fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.S)
        if fence:
            cleaned = fence.group(1).strip()
        return json.loads(cleaned)
    return dict(raw)


def _read_env_files() -> Dict[str, str]:
    """Read project env first, then fill missing values from Hermes user env.

    The project should not copy personal API keys into its .env. This lets the
    app use Dan's existing Hermes-held provider keys while keeping repo-local
    config limited to provider/model choices.
    """
    values: Dict[str, str] = {}
    for env_path in (Path(".env"), Path.home() / ".hermes" / ".env"):
        if not env_path.exists():
            continue
        for line in env_path.read_text(errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return values


def _pick_env(name: str, local_env: Dict[str, str], default: str = "") -> str:
    return os.environ.get(name) or local_env.get(name) or default


def default_llm_client() -> LLMClient:
    """Build a minimal OpenAI-compatible chat-completions client from env vars.

    Env:
    - LLM_API_KEY or OPENAI_API_KEY
    - LLM_API_BASE_URL, default https://api.openai.com/v1
    - LLM_MODEL, default gpt-4o-mini
    """

    env = _read_env_files()
    provider = _pick_env("LLM_PROVIDER", env, "openai_compatible").lower()
    if provider == "anthropic" or (provider == "claude"):
        return _anthropic_client(env)
    return _openai_compatible_client(env)


def _openai_compatible_client(env: Dict[str, str]) -> LLMClient:
    api_key = (
        _pick_env("LLM_API_KEY", env)
        or _pick_env("OPENAI_API_KEY", env)
        or _pick_env("OPENROUTER_API_KEY", env)
    )
    if not api_key:
        raise RuntimeError("Missing LLM_API_KEY, OPENAI_API_KEY, or OPENROUTER_API_KEY for lane synthesis")
    base_url = _pick_env("LLM_API_BASE_URL", env, "https://api.openai.com/v1").rstrip("/")
    model = _pick_env("LLM_MODEL", env, "gpt-4o-mini")

    def call(messages: List[Dict[str, str]]) -> Union[Mapping[str, Any], str]:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0,
        }
        response_format = _pick_env("LLM_RESPONSE_FORMAT", env).strip()
        if response_format:
            payload["response_format"] = {"type": response_format}
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=45) as response:  # noqa: S310 - configured API endpoint
            payload = json.loads(response.read().decode("utf-8"))
        return payload["choices"][0]["message"]["content"]

    return traceable_if_configured(name="triage.llm.openai_compatible", run_type="llm")(call)


def _anthropic_client(env: Dict[str, str]) -> LLMClient:
    api_key = (
        _pick_env("ANTHROPIC_API_KEY", env)
        or _pick_env("CLAUDE_API_KEY", env)
        or _pick_env("ANTHROPIC_TOKEN", env)
    )
    if not api_key:
        raise RuntimeError("Missing ANTHROPIC_API_KEY, CLAUDE_API_KEY, or ANTHROPIC_TOKEN for lane synthesis")
    base_url = _pick_env("ANTHROPIC_API_BASE_URL", env, "https://api.anthropic.com/v1").rstrip("/")
    model = _pick_env("LLM_MODEL", env) or _pick_env("ANTHROPIC_MODEL", env, "claude-sonnet-4-5-20250929")

    def call(messages: List[Dict[str, str]]) -> Union[Mapping[str, Any], str]:
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        user_messages = [m for m in messages if m.get("role") != "system"]
        body = json.dumps(
            {
                "model": model,
                "max_tokens": 1200,
                "temperature": 0,
                "system": "\n\n".join(system_parts),
                "messages": user_messages,
            }
        ).encode("utf-8")
        request = Request(
            f"{base_url}/messages",
            data=body,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=60) as response:  # noqa: S310 - configured API endpoint
            payload = json.loads(response.read().decode("utf-8"))
        for block in payload.get("content", []):
            if block.get("type") == "text":
                return block.get("text", "")
        return ""

    return traceable_if_configured(name="triage.llm.anthropic_sonnet", run_type="llm")(call)


def synthesize_lane_report(
    *,
    lane: LaneName,
    lane_goal: str,
    evidence: List[Dict],
    gaps: List[str],
    concerns: List[str],
    safe_questions: List[str],
    fallback_report: Dict,
    llm_client: LLMClient,
) -> Dict:
    """Ask an LLM to synthesize one lane report from already-collected tool evidence.

    The LLM is not allowed to add evidence. Tool-produced evidence is authoritative;
    any evidence returned by the model is replaced with the supplied evidence before
    validation. Invalid model output falls back to the deterministic report.
    """

    messages = [
        {"role": "system", "content": LANE_SYNTHESIS_PROMPTS[lane]},
        {
            "role": "user",
            "content": _build_user_payload(
                lane=lane,
                lane_goal=lane_goal,
                evidence=evidence,
                gaps=gaps,
                concerns=concerns,
                safe_questions=safe_questions,
            ),
        },
    ]

    try:
        candidate = _coerce_llm_output(llm_client(messages))
        candidate["lane"] = lane
        candidate["evidence"] = evidence
        candidate.setdefault("gaps", gaps)
        candidate.setdefault("concerns", concerns)
        candidate.setdefault("safe_questions", safe_questions)
        return LaneReportModel(**candidate).model_dump()
    except (ValidationError, ValueError, TypeError, json.JSONDecodeError, KeyError, RuntimeError, URLError, OSError):
        return fallback_report
