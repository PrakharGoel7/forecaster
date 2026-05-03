from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ── Structured enums ──────────────────────────────────────────────────────────

class EventType(str, Enum):
    BINARY_OCCURRENCE  = "binary_occurrence"   # Will X happen by date D?
    THRESHOLD          = "threshold"           # Will metric X exceed Y by D?
    RELATIVE_ORDERING  = "relative_ordering"   # Will A happen before B?
    ELECTION_SELECTION = "election_selection"  # Will X win/be chosen?
    MARKET_PRICE       = "market_price"        # Will asset reach level X?
    COUNT_FREQUENCY    = "count_frequency"     # Will there be at least N events?
    CONDITIONAL        = "conditional"         # Depends on definitions/external criteria
    OTHER              = "other"


class SourceType(str, Enum):
    OFFICIAL       = "official"        # .gov, company IR, exchanges, regulators
    PRIMARY_DATA   = "primary_data"    # academic papers, datasets, filings
    REPUTABLE_NEWS = "reputable_news"  # Reuters, AP, Bloomberg, FT, BBC
    EXPERT_ANALYSIS = "expert_analysis"
    MARKET_DATA    = "market_data"     # prediction markets, exchanges
    BLOG           = "blog"            # SEO sites, Medium, Substack, Reddit
    UNKNOWN        = "unknown"

    @classmethod
    def _missing_(cls, value):
        # Map legacy enum values from old memos
        _legacy = {
            "official_primary": cls.OFFICIAL,
            "regulatory": cls.OFFICIAL,
            "reputable_secondary": cls.REPUTABLE_NEWS,
            "social_media": cls.BLOG,
        }
        return _legacy.get(value, cls.UNKNOWN)


class Reliability(str, Enum):
    HIGH   = "high"
    MEDIUM = "medium"
    LOW    = "low"


class EvidenceAge(str, Enum):
    CURRENT = "current"   # < 3 months
    RECENT  = "recent"    # 3–12 months
    STALE   = "stale"     # > 12 months


class EvidenceDirection(str, Enum):
    RAISES    = "raises"
    LOWERS    = "lowers"
    NEUTRAL   = "neutral"
    BASE_RATE = "base_rate"
    CONTEXT   = "context"


class EvidenceMagnitude(str, Enum):
    STRONG   = "strong"
    MODERATE = "moderate"
    WEAK     = "weak"


class UpdateMagnitude(str, Enum):
    STRONG_RAISE  = "strong_raise"
    MODEST_RAISE  = "modest_raise"
    NEUTRAL       = "neutral"
    MODEST_LOWER  = "modest_lower"
    STRONG_LOWER  = "strong_lower"


class ForeknowledgeRisk(str, Enum):
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"


# ── Evidence ──────────────────────────────────────────────────────────────────

class EvidenceItem(BaseModel):
    claim: str
    source_url: str
    source_title: str
    source_type: SourceType
    reliability: Reliability = Reliability.MEDIUM
    retrieved_at: datetime
    date_published: Optional[str] = None
    evidence_age: EvidenceAge = EvidenceAge.STALE
    relevant_quote_or_snippet: str
    direction: EvidenceDirection
    magnitude: Optional[EvidenceMagnitude] = None
    why_it_matters: str = ""
    limitations: str = ""
    notes: str = ""


class EvidenceLedger(BaseModel):
    items: list[EvidenceItem] = Field(default_factory=list)
    research_notes: str = ""
    incomplete: bool = False

    def format_for_prompt(self) -> str:
        if not self.items:
            return "EVIDENCE LEDGER: Empty."
        lines = ["EVIDENCE LEDGER:"]
        for i, item in enumerate(self.items):
            rel = item.reliability.value if item.reliability else "?"
            age = item.evidence_age.value if item.evidence_age else "?"
            mag = f" — magnitude: {item.magnitude.value}" if item.magnitude else ""
            lines += [
                f"\n[{i}] {item.direction.value.upper()}{mag}",
                f"    CLAIM: {item.claim}",
                f"    SOURCE: {item.source_title} ({item.source_type.value}) "
                f"| reliability: {rel} | age: {age}"
                + (f" ({item.date_published})" if item.date_published else ""),
                f"    URL: {item.source_url}",
                f"    QUOTE: \"{item.relevant_quote_or_snippet}\"",
            ]
            if item.why_it_matters:
                lines.append(f"    WHY IT MATTERS: {item.why_it_matters}")
            if item.limitations:
                lines.append(f"    LIMITATIONS: {item.limitations}")
            if item.notes:
                lines.append(f"    NOTES: {item.notes}")
        if self.research_notes:
            lines.append(f"\nRESEARCH NOTES: {self.research_notes}")
        if self.incomplete:
            lines.append("\nWARNING: Research incomplete.")
        return "\n".join(lines)


# ── Parsed question ───────────────────────────────────────────────────────────

class ParsedQuestion(BaseModel):
    question: str
    event_type: EventType = EventType.OTHER
    event_type_explanation: str = ""
    resolution_criteria: str
    resolution_deadline: Optional[str] = None
    relevant_timezone: Optional[str] = None
    outside_view_target: str = ""           # statistical object to estimate
    candidate_reference_classes: list[dict] = Field(default_factory=list)
    selected_reference_class: str = ""
    selected_reference_class_rationale: str = ""
    base_rate_queries: list[str] = Field(default_factory=list)
    key_unknowns: list[str] = Field(default_factory=list)
    inside_view_factors: list[str] = Field(default_factory=list)
    foreknowledge_risk: ForeknowledgeRisk = ForeknowledgeRisk.LOW
    ambiguity_notes: list[str] = Field(default_factory=list)

    # Legacy alias — kept so old serialised data still loads
    outside_view_reference_class: str = ""

    def format_for_prompt(self) -> str:
        def fmt(items: list, fallback: str = "none") -> str:
            return "; ".join(str(i) for i in items) if items else fallback

        ref_class = self.selected_reference_class or self.outside_view_reference_class or "not specified"
        lines = [
            f"QUESTION: {self.question}",
            f"EVENT TYPE: {self.event_type.value} — {self.event_type_explanation or 'see resolution criteria'}",
            f"RESOLUTION CRITERIA: {self.resolution_criteria}",
            f"DEADLINE: {self.resolution_deadline or 'not specified'}",
            f"TIMEZONE: {self.relevant_timezone or 'not specified'}",
            f"STATISTICAL OBJECT (outside-view target): {self.outside_view_target or 'not specified'}",
            f"SELECTED REFERENCE CLASS: {ref_class}",
        ]
        if self.selected_reference_class_rationale:
            lines.append(f"REFERENCE CLASS RATIONALE: {self.selected_reference_class_rationale}")
        if self.candidate_reference_classes:
            lines.append("CANDIDATE REFERENCE CLASSES:")
            for rc in self.candidate_reference_classes:
                lines.append(f"  • {rc.get('class_name','?')} — pros: {rc.get('pros','?')} | cons: {rc.get('cons','?')}")
        lines += [
            f"BASE RATE QUERIES: {fmt(self.base_rate_queries)}",
            f"KEY UNKNOWNS: {fmt(self.key_unknowns)}",
            f"INSIDE VIEW FACTORS: {fmt(self.inside_view_factors)}",
            f"FOREKNOWLEDGE RISK: {self.foreknowledge_risk.value}",
            f"AMBIGUITIES: {fmt(self.ambiguity_notes)}",
        ]
        return "\n".join(lines)


# ── Outside view ──────────────────────────────────────────────────────────────

class OutsideViewForecast(BaseModel):
    agent_id: int
    base_rate: float
    statistical_object: str = ""
    reference_class: str
    denominator_or_basis: str = ""
    analog_cases_or_data: str = ""
    reference_class_limitations: str = ""
    reasoning: str
    confidence: str  # low / medium / high
    evidence_ledger: EvidenceLedger

    @field_validator("base_rate")
    @classmethod
    def clamp_base_rate(cls, v: float) -> float:
        return max(0.001, min(0.999, v))


class OutsideViewConsensus(BaseModel):
    base_rate: float
    reference_class: str
    statistical_object: str = ""
    denominator_or_basis: str = ""
    reference_class_limitations: str = ""
    reasoning: str
    agent_forecasts: list[OutsideViewForecast]

    @field_validator("base_rate")
    @classmethod
    def clamp(cls, v: float) -> float:
        return max(0.001, min(0.999, v))


# ── Agent forecast ────────────────────────────────────────────────────────────

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
    # New fields
    starting_base_rate: float = 0.0
    key_updates_from_base: list[str] = Field(default_factory=list)
    unresolved_cruxes: list[str] = Field(default_factory=list)

    @field_validator("probability", "outside_view_base_rate")
    @classmethod
    def clamp_probability(cls, v: float) -> float:
        return max(0.001, min(0.999, v))


# ── Supervisor ────────────────────────────────────────────────────────────────

class SupervisorReconciliation(BaseModel):
    raw_probabilities: list[float]
    disagreement_level: str  # low / medium / high
    crux_of_disagreement: Optional[str] = None
    targeted_searches_conducted: list[str] = Field(default_factory=list)
    reconciled_probability: float
    reconciliation_reasoning: str
    additional_evidence: list[EvidenceItem] = Field(default_factory=list)
    outside_view_audit: str = ""   # supervisor's assessment of OV quality

    @field_validator("reconciled_probability")
    @classmethod
    def clamp(cls, v: float) -> float:
        return max(0.001, min(0.999, v))


# ── Calibration ───────────────────────────────────────────────────────────────

class CalibrationResult(BaseModel):
    raw_probability: float
    calibrated_probability: float
    platt_coefficient: float


# ── Final memo ────────────────────────────────────────────────────────────────

class ForecastMemo(BaseModel):
    question: str
    final_probability: float
    raw_probability: float
    ensemble_run_probabilities: list[float]
    probability_spread: tuple[float, float]
    calibration: CalibrationResult
    parsed_question: ParsedQuestion
    ov_forecasts: list[OutsideViewForecast] = Field(default_factory=list)
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
