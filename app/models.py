from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

LaneName = Literal[
    "original_jd_recon",
    "recruiter_identity",
    "agency_legitimacy",
    "client_company",
    "job_jd_verification",
    "security_assessment",
    "reputation_pattern",
]
Verdict = Literal["verified", "partially_verified", "unverified", "concerning", "not_applicable"]
Confidence = Literal["low", "medium", "high"]
SourceType = Literal[
    "input_text",
    "official_site",
    "registry",
    "search_result",
    "review_snippet",
    "technical_scan",
    "extracted_entities",
    "tool_result",
]
ScoreBand = Literal["low", "medium", "high", "critical"]
SecurityRisk = Literal["low", "medium", "high"]
ActionLevel = Literal["safe", "caution", "deep_check", "stop"]
DigestStatus = Literal["pass", "warn", "info", "fail"]


class CaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    mode: Literal["full"] = "full"

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("text must not be blank")
        return clean


class ExtractedEntities(BaseModel):
    model_config = ConfigDict(extra="allow")

    recruiter_name: Optional[str] = None
    agency_name: Optional[str] = None
    client_company: Optional[str] = None
    role: Optional[str] = None
    salary: Optional[str] = None
    emails: List[str] = Field(default_factory=list)
    urls: List[str] = Field(default_factory=list)
    domains: List[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lane: LaneName
    finding: str = Field(min_length=3)
    source_type: SourceType
    source: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    confidence: Confidence


class LaneReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lane: LaneName
    verdict: Verdict
    confidence: Confidence
    summary: str = Field(min_length=5)
    evidence: List[EvidenceItem] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    concerns: List[str] = Field(default_factory=list)
    safe_questions: List[str] = Field(default_factory=list)


class Score(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall: int = Field(ge=0, le=100)
    band: ScoreBand
    security_risk: SecurityRisk
    confidence: Confidence
    components: Dict[str, int] = Field(default_factory=dict)

    @field_validator("components")
    @classmethod
    def component_values_are_percentages(cls, value: Dict[str, int]) -> Dict[str, int]:
        for key, score in value.items():
            if score < 0 or score > 100:
                raise ValueError(f"component {key} must be 0..100")
        return value


class FinalAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=3)
    level: ActionLevel
    reason: str = Field(min_length=3)


class OriginalJDRecon(BaseModel):
    model_config = ConfigDict(extra="allow")

    inferred_client_company: Optional[str] = None
    confidence_score: Optional[int] = Field(default=None, ge=0, le=100)
    matched_original_jd_url: Optional[str] = None
    matched_fields: List[str] = Field(default_factory=list)
    summary: Optional[str] = None


class VerificationDigestCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3)
    status: DigestStatus
    plain_english: str = Field(min_length=3)
    source: str = Field(min_length=1)
    technical_check: str = Field(min_length=3)
    why_it_matters: str = Field(min_length=3)
    dates: Dict[str, str] = Field(default_factory=dict)
    details: List[str] = Field(default_factory=list)


class OpportunityRead(BaseModel):
    model_config = ConfigDict(extra="allow")

    legitimacy: str = "unknown"
    security_risk: str = "unknown"
    opportunity_fit: str = "unknown"
    recommended_action: str = ""
    salary_stance: str = ""
    role_read: str = ""
    reply_focus: str = ""
    summary: str = ""
    open_questions: List[str] = Field(default_factory=list)
    signals: Dict[str, Any] = Field(default_factory=dict)


class FullCheckDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entities: ExtractedEntities = Field(default_factory=ExtractedEntities)
    original_jd_recon: OriginalJDRecon = Field(default_factory=OriginalJDRecon)
    lane_reports: Dict[str, LaneReport] = Field(default_factory=dict)
    evidence_ledger: List[EvidenceItem] = Field(default_factory=list)
    verification_digest: List[VerificationDigestCard] = Field(default_factory=list)
    opportunity_read: OpportunityRead = Field(default_factory=OpportunityRead)
    gaps: List[str] = Field(default_factory=list)
    conflicts: List[str] = Field(default_factory=list)
    trace: List[str] = Field(default_factory=list)


class FullCheckResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = "ok"
    score: Score
    decision: str = Field(min_length=3)
    reason: str = Field(min_length=3)
    safe_next_question: str = Field(min_length=3)
    key_evidence: List[EvidenceItem] = Field(default_factory=list)
    details: FullCheckDetails
    markdown: str = ""


def _safe_next_question(markdown: str, lane_reports: Dict[str, Any]) -> str:
    marker = "## Safe next question"
    start = markdown.find(marker)
    if start >= 0:
        next_heading = markdown.find("\n## ", start + len(marker))
        body = markdown[start + len(marker): next_heading if next_heading >= 0 else None]
        for line in body.splitlines():
            clean = line.strip().strip('"')
            if clean:
                return clean
    for report in lane_reports.values():
        questions = report.get("safe_questions") or []
        if questions:
            return str(questions[0])
    return "Can you send the official careers-page JD and confirm whether any assessment requires running code or connecting a wallet?"


def to_full_check_response(graph_state: Dict[str, Any]) -> FullCheckResponse:
    lane_reports = graph_state.get("lane_reports") or {}
    ledger = graph_state.get("evidence_ledger") or graph_state.get("evidence") or []
    final_action = FinalAction(**(graph_state.get("final_action") or {
        "label": "Deep check needed",
        "level": "deep_check",
        "reason": "The graph did not produce a final action.",
    }))
    score = Score(**(graph_state.get("score") or {
        "overall": 50,
        "band": "medium",
        "security_risk": "medium",
        "confidence": "low",
        "components": {},
    }))
    markdown = str(graph_state.get("markdown") or graph_state.get("final_report") or "")
    key_evidence = [EvidenceItem(**item) for item in ledger[:5]]
    details = FullCheckDetails(
        entities=ExtractedEntities(**(graph_state.get("entities") or {})),
        original_jd_recon=OriginalJDRecon(**(graph_state.get("original_jd_recon") or {})),
        lane_reports={name: LaneReport(**report) for name, report in lane_reports.items()},
        evidence_ledger=[EvidenceItem(**item) for item in ledger],
        verification_digest=[VerificationDigestCard(**item) for item in (graph_state.get("verification_digest") or [])],
        opportunity_read=OpportunityRead(**(graph_state.get("opportunity_read") or {})),
        gaps=list(graph_state.get("gaps") or []),
        conflicts=list(graph_state.get("conflicts") or []),
        trace=list(graph_state.get("trace") or []),
    )
    return FullCheckResponse(
        status="ok",
        score=score,
        decision=final_action.label,
        reason=final_action.reason,
        safe_next_question=_safe_next_question(markdown, lane_reports),
        key_evidence=key_evidence,
        details=details,
        markdown=markdown,
    )
