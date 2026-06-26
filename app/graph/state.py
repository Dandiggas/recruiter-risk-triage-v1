from __future__ import annotations

from typing import Annotated, Dict, List, Literal, Optional, TypedDict

Verdict = Literal["verified", "partially_verified", "unverified", "concerning", "not_applicable"]
Confidence = Literal["low", "medium", "high"]


def merge_dicts(left: Dict, right: Dict) -> Dict:
    return {**(left or {}), **(right or {})}


def append_lists(left: List, right: List) -> List:
    return [*(left or []), *(right or [])]


class Entities(TypedDict, total=False):
    recruiter_name: Optional[str]
    agency_name: Optional[str]
    client_company: Optional[str]
    role: Optional[str]
    salary: Optional[str]
    emails: List[str]
    urls: List[str]
    domains: List[str]


class EvidenceItem(TypedDict):
    lane: str
    finding: str
    source_type: str
    source: str
    quote: str
    confidence: Confidence


class LaneReport(TypedDict):
    lane: str
    verdict: Verdict
    confidence: Confidence
    summary: str
    evidence: List[EvidenceItem]
    gaps: List[str]
    concerns: List[str]
    safe_questions: List[str]


class OriginalJDRecon(TypedDict, total=False):
    inferred_client_company: str
    confidence_score: int
    matched_original_jd_url: str
    matched_fields: List[str]
    summary: str


class VerificationDigestCard(TypedDict):
    title: str
    status: str
    plain_english: str
    source: str
    technical_check: str
    why_it_matters: str
    dates: Dict[str, str]
    details: List[str]


class OpportunityRead(TypedDict, total=False):
    legitimacy: str
    security_risk: str
    opportunity_fit: str
    recommended_action: str
    salary_stance: str
    role_read: str
    reply_focus: str
    summary: str
    open_questions: List[str]
    signals: Dict[str, object]


class FinalAction(TypedDict):
    label: str
    level: str
    reason: str


class Score(TypedDict):
    overall: int
    band: str
    security_risk: str
    confidence: str
    components: Dict[str, int]


class CaseState(TypedDict, total=False):
    raw_input: str
    entities: Entities
    deterministic_flags: List[str]
    original_jd_recon: OriginalJDRecon
    lane_reports: Annotated[Dict[str, LaneReport], merge_dicts]
    evidence: Annotated[List[EvidenceItem], append_lists]
    gaps: List[str]
    conflicts: List[str]
    final_action: FinalAction
    score: Score
    evidence_ledger: List[EvidenceItem]
    verification_digest: List[VerificationDigestCard]
    opportunity_read: OpportunityRead
    final_report: str
    trace: Annotated[List[str], append_lists]
