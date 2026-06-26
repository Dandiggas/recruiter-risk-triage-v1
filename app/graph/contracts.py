from __future__ import annotations

from typing import Dict, List, Literal, Tuple

from pydantic import BaseModel, ConfigDict, Field

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


class EvidenceItemModel(BaseModel):
    """Validated evidence atom produced by a lane node.

    Lane agents can be cheap/small models later, but this boundary stays strict:
    no source-less claims enter the evidence ledger.
    """

    model_config = ConfigDict(extra="forbid")

    lane: LaneName
    finding: str = Field(min_length=3)
    source_type: SourceType
    source: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    confidence: Confidence


class LaneReportModel(BaseModel):
    """Validated report contract for specialist lane nodes."""

    model_config = ConfigDict(extra="forbid")

    lane: LaneName
    verdict: Verdict
    confidence: Confidence
    summary: str = Field(min_length=5)
    evidence: List[EvidenceItemModel] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    concerns: List[str] = Field(default_factory=list)
    safe_questions: List[str] = Field(default_factory=list)


def make_evidence(
    lane: LaneName,
    finding: str,
    source_type: SourceType,
    source: str,
    quote: str,
    confidence: Confidence = "medium",
) -> Dict:
    return EvidenceItemModel(
        lane=lane,
        finding=finding,
        source_type=source_type,
        source=source,
        quote=quote,
        confidence=confidence,
    ).model_dump()


def make_lane_report(
    *,
    lane: LaneName,
    verdict: Verdict,
    confidence: Confidence,
    summary: str,
    evidence: List[Dict] | None = None,
    gaps: List[str] | None = None,
    concerns: List[str] | None = None,
    safe_questions: List[str] | None = None,
) -> Tuple[Dict, List[Dict]]:
    report = LaneReportModel(
        lane=lane,
        verdict=verdict,
        confidence=confidence,
        summary=summary,
        evidence=[EvidenceItemModel(**item) for item in (evidence or [])],
        gaps=gaps or [],
        concerns=concerns or [],
        safe_questions=safe_questions or [],
    )
    dumped = report.model_dump()
    return dumped, dumped["evidence"]
