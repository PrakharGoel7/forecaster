from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class SourceType(str, Enum):
    OFFICIAL_PRIMARY = "official_primary"
    REGULATORY = "regulatory"
    REPUTABLE_SECONDARY = "reputable_secondary"
    SOCIAL_MEDIA = "social_media"
    UNKNOWN = "unknown"


class EvidenceDirection(str, Enum):
    RAISES = "raises"    # raises P(YES)
    LOWERS = "lowers"    # lowers P(YES)
    BASE_RATE = "base_rate"
    CONTEXT = "context"


class EvidenceItem(BaseModel):
    claim: str
    source_url: str
    source_title: str
    source_type: SourceType
    retrieved_at: datetime
    relevant_quote_or_snippet: str
    direction: EvidenceDirection
    notes: str


class EvidenceLedger(BaseModel):
    items: list[EvidenceItem] = Field(default_factory=list)
    research_notes: str = ""
    incomplete: bool = False

    def format_for_prompt(self) -> str:
        if not self.items:
            return "EVIDENCE LEDGER: Empty."
        lines = ["EVIDENCE LEDGER:"]
        for i, item in enumerate(self.items):
            lines += [
                f"\n[{i}] CLAIM: {item.claim}",
                f"    SOURCE: {item.source_title} ({item.source_type.value})",
                f"    URL: {item.source_url}",
                f"    RETRIEVED: {item.retrieved_at.isoformat()}",
                f"    QUOTE: \"{item.relevant_quote_or_snippet}\"",
                f"    DIRECTION: {item.direction.value}",
            ]
            if item.notes:
                lines.append(f"    NOTES: {item.notes}")
        if self.research_notes:
            lines.append(f"\nRESEARCH NOTES: {self.research_notes}")
        if self.incomplete:
            lines.append("\nWARNING: Research incomplete.")
        return "\n".join(lines)


class ForeknowledgeRisk(str, Enum):
    LOW = "low"        # genuinely future event
    MEDIUM = "medium"  # partial information already public
    HIGH = "high"      # may already be resolvable


class ParsedQuestion(BaseModel):
    question: str
    resolution_criteria: str
    resolution_deadline: Optional[str] = None
    relevant_timezone: Optional[str] = None
    base_rate_queries: list[str] = Field(default_factory=list)
    key_unknowns: list[str] = Field(default_factory=list)
    outside_view_reference_class: str = ""
    inside_view_factors: list[str] = Field(default_factory=list)
    foreknowledge_risk: ForeknowledgeRisk = ForeknowledgeRisk.LOW
    ambiguity_notes: list[str] = Field(default_factory=list)
    initial_search_queries: list[str] = Field(default_factory=list)

    def format_for_prompt(self) -> str:
        def fmt(items: list[str], fallback: str = "none") -> str:
            return "; ".join(items) if items else fallback

        return "\n".join([
            f"QUESTION: {self.question}",
            f"RESOLUTION CRITERIA: {self.resolution_criteria}",
            f"DEADLINE: {self.resolution_deadline or 'not specified'}",
            f"TIMEZONE: {self.relevant_timezone or 'not specified'}",
            f"REFERENCE CLASS (outside view): {self.outside_view_reference_class or 'not specified'}",
            f"BASE RATE QUERIES: {fmt(self.base_rate_queries)}",
            f"KEY UNKNOWNS: {fmt(self.key_unknowns)}",
            f"INSIDE VIEW FACTORS: {fmt(self.inside_view_factors)}",
            f"FOREKNOWLEDGE RISK: {self.foreknowledge_risk.value}",
            f"AMBIGUITIES: {fmt(self.ambiguity_notes)}",
            f"SUGGESTED SEARCHES: {fmt(self.initial_search_queries)}",
        ])


class AgentForecast(BaseModel):
    agent_id: int
    probability: float
    outside_view_base_rate: float
    outside_view_reasoning: str
    inside_view_reasoning: str
    key_factors_for: list[str]
    key_factors_against: list[str]
    uncertainty_reasoning: str
    epistemic_confidence: str  # low / medium / high
    evidence_ledger: EvidenceLedger

    @field_validator("probability", "outside_view_base_rate")
    @classmethod
    def clamp_probability(cls, v: float) -> float:
        return max(0.001, min(0.999, v))


class SupervisorReconciliation(BaseModel):
    raw_probabilities: list[float]
    disagreement_level: str  # low / medium / high
    crux_of_disagreement: Optional[str] = None
    targeted_searches_conducted: list[str] = Field(default_factory=list)
    reconciled_probability: float
    reconciliation_reasoning: str
    additional_evidence: list[EvidenceItem] = Field(default_factory=list)

    @field_validator("reconciled_probability")
    @classmethod
    def clamp(cls, v: float) -> float:
        return max(0.001, min(0.999, v))


class CalibrationResult(BaseModel):
    raw_probability: float
    calibrated_probability: float
    platt_coefficient: float


class ForecastMemo(BaseModel):
    question: str
    final_probability: float         # calibrated + ensemble-averaged
    raw_probability: float           # before Platt scaling
    ensemble_run_probabilities: list[float]
    probability_spread: tuple[float, float]  # (min, max) across runs
    calibration: CalibrationResult
    parsed_question: ParsedQuestion
    agent_forecasts: list[AgentForecast]
    supervisor_reconciliation: SupervisorReconciliation
    inside_view_summary: str
    outside_view_summary: str
    key_evidence_summary: str
    open_questions: list[str]
    foreknowledge_flags: list[str]
    num_agents: int
    num_ensemble_runs: int
    forecasted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
