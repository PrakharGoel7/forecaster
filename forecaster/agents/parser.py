import json
from forecaster.models import ParsedQuestion, ForeknowledgeRisk, EventType
from forecaster.config import ForecasterConfig
from forecaster.agents.base import LLMClient

SYSTEM_PROMPT = """You are a Prediction Question Analyst. Decompose a forecasting question into structural components for probabilistic forecasting.

DO NOT forecast. DO NOT estimate probability.

First classify the question's EVENT TYPE. Choose the closest:
- binary_occurrence: Will X happen by date D?
- threshold: Will metric X exceed/fall below Y by date D?
- relative_ordering: Will A happen before B? (two specific actors, timing race)
- election_selection: Will candidate/entity X win/be chosen?
- market_price: Will asset/metric reach level X?
- count_frequency: Will there be at least N events?
- conditional: Depends on definitions or external resolution criteria
- other: explain

CRITICAL — EVENT TYPE DETERMINES THE STATISTICAL OBJECT:
- relative_ordering → you need PAIRWISE ORDERING data: among comparable pairs of entities, how often does A happen before B? Do NOT use generic event frequency.
- threshold → you need THRESHOLD CROSSING data: how often does metric X exceed Y by comparable deadlines?
- election_selection → you need COMPARABLE CANDIDATE data: base rate for entities in similar positions winning.
- binary_occurrence → you need EVENT OCCURRENCE data: how often does this class of event happen by comparable deadlines?

Your outputs:
1. EVENT TYPE — one of the above with a one-sentence explanation.
2. RESOLUTION CRITERIA — exactly what must happen for YES. Include thresholds, dates, time zones, actors, scope, and resolution source.
3. OUTSIDE VIEW TARGET — define the EXACT statistical object needed:
   - For relative_ordering: "Historical probability that [entity class A] confirms [event] before [entity class B] among comparable pairs of rival late-stage firms."
   - For threshold: "Historical frequency of [metric] exceeding [value] within [timeframe] for comparable [entities]."
   - For election_selection: "Base rate of [candidate class] winning under [comparable rules]."
4. CANDIDATE REFERENCE CLASSES — 2-4 options:
   - broad class (risk: dilutes signal)
   - narrow class (risk: too few cases)
   - closest analog class (best fit)
   For each: name, breadth (broad/medium/narrow), pros, cons.
5. SELECTED REFERENCE CLASS — the best one, directly matching the statistical object. For relative_ordering this MUST be a pairwise comparison class, not a generic event class.
6. BASE RATE SEARCH QUERIES — 3-5 queries targeting empirical base-rate data for the selected reference class.
7. INSIDE VIEW FACTORS — 3-5 instance-specific factors that update from base rate.
8. KEY UNKNOWNS — 2-4 factual uncertainties that most change the forecast.
9. FOREKNOWLEDGE RISK — HIGH/MEDIUM/LOW.
10. AMBIGUITIES — underspecified terms affecting resolution.

Call submit_parsed_question when complete.
"""

_SUBMIT_TOOL = {
    "name": "submit_parsed_question",
    "description": "Submit the fully parsed question structure.",
    "input_schema": {
        "type": "object",
        "properties": {
            "event_type": {
                "type": "string",
                "enum": [
                    "binary_occurrence", "threshold", "relative_ordering",
                    "election_selection", "market_price", "count_frequency",
                    "conditional", "other",
                ],
            },
            "event_type_explanation": {
                "type": "string",
                "description": "One sentence explaining why this event type applies",
            },
            "resolution_criteria": {
                "type": "string",
                "description": "Exact conditions for YES including thresholds, dates, scope, and resolution source",
            },
            "resolution_deadline": {"type": "string"},
            "relevant_timezone": {"type": "string"},
            "outside_view_target": {
                "type": "string",
                "description": (
                    "The EXACT statistical object to estimate. "
                    "For relative_ordering: must describe pairwise ordering among comparable pairs. "
                    "E.g. 'Historical probability that one rival late-stage tech firm IPOs before its "
                    "main competitor among comparable pairs of competing unicorns.'"
                ),
            },
            "candidate_reference_classes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "class_name": {"type": "string"},
                        "breadth": {"type": "string", "enum": ["broad", "medium", "narrow"]},
                        "pros": {"type": "string"},
                        "cons": {"type": "string"},
                    },
                    "required": ["class_name", "breadth", "pros", "cons"],
                },
                "description": "2-4 candidate reference classes with tradeoffs",
            },
            "selected_reference_class": {
                "type": "string",
                "description": (
                    "The chosen reference class. "
                    "For relative_ordering this MUST be a pairwise comparison class."
                ),
            },
            "selected_reference_class_rationale": {
                "type": "string",
                "description": "Why this directly matches the statistical object",
            },
            "base_rate_queries": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3-5 search queries targeting empirical base-rate data for the selected reference class",
            },
            "key_unknowns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "2-4 factual uncertainties that most affect the forecast",
            },
            "inside_view_factors": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3-5 instance-specific factors that update from the base rate",
            },
            "foreknowledge_risk": {
                "type": "string",
                "enum": ["low", "medium", "high"],
            },
            "ambiguity_notes": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": [
            "event_type", "event_type_explanation", "resolution_criteria",
            "outside_view_target", "candidate_reference_classes",
            "selected_reference_class", "selected_reference_class_rationale",
            "base_rate_queries", "key_unknowns", "inside_view_factors",
            "foreknowledge_risk",
        ],
    },
}

# ── Validation ────────────────────────────────────────────────────────────────

_PAIRWISE_KEYWORDS = {
    "before", "pairwise", "ordering", "first", "ahead", "prior to",
    "race", "which", "rival", "competing", "pair",
}

def _validate(parsed: ParsedQuestion) -> list[str]:
    errors = []

    if not parsed.event_type or parsed.event_type == EventType.OTHER:
        if not parsed.event_type_explanation:
            errors.append(
                "event_type is 'other' without explanation. "
                "Classify more specifically using one of the defined types."
            )

    if not parsed.outside_view_target.strip():
        errors.append(
            "outside_view_target is empty. You must define the exact statistical object to estimate."
        )

    if not parsed.selected_reference_class.strip():
        errors.append("selected_reference_class is empty.")

    if parsed.event_type == EventType.RELATIVE_ORDERING:
        target_lower = parsed.outside_view_target.lower()
        ref_lower = parsed.selected_reference_class.lower()

        if not any(kw in target_lower for kw in _PAIRWISE_KEYWORDS):
            errors.append(
                f"event_type is relative_ordering but outside_view_target does not describe "
                f"pairwise ordering. Got: '{parsed.outside_view_target}'. "
                f"It must describe which of two comparable entities happens first — "
                f"NOT generic event frequency or total count statistics."
            )

        if not any(kw in ref_lower for kw in _PAIRWISE_KEYWORDS):
            errors.append(
                f"event_type is relative_ordering but selected_reference_class does not describe "
                f"a pairwise comparison. Got: '{parsed.selected_reference_class}'. "
                f"Use a reference class comparing pairs of comparable entities, "
                f"e.g. 'Pairwise IPO ordering among competing late-stage tech unicorns'."
            )

    return errors


def _build_parsed_question(question: str, inp: dict) -> ParsedQuestion:
    return ParsedQuestion(
        question=question,
        event_type=EventType(inp.get("event_type", "other")),
        event_type_explanation=inp.get("event_type_explanation", ""),
        resolution_criteria=inp["resolution_criteria"],
        resolution_deadline=inp.get("resolution_deadline"),
        relevant_timezone=inp.get("relevant_timezone"),
        outside_view_target=inp.get("outside_view_target", ""),
        candidate_reference_classes=inp.get("candidate_reference_classes", []),
        selected_reference_class=inp.get("selected_reference_class", ""),
        selected_reference_class_rationale=inp.get("selected_reference_class_rationale", ""),
        base_rate_queries=inp.get("base_rate_queries", []),
        key_unknowns=inp.get("key_unknowns", []),
        inside_view_factors=inp.get("inside_view_factors", []),
        foreknowledge_risk=ForeknowledgeRisk(inp["foreknowledge_risk"]),
        ambiguity_notes=inp.get("ambiguity_notes", []),
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def parse_question(
    question: str,
    context: str | None = None,
    config: ForecasterConfig | None = None,
    series_ticker: str | None = None,
    event_title: str | None = None,
    ev_sub: str | None = None,
    ev_category: str | None = None,
) -> ParsedQuestion:
    if config is None:
        config = ForecasterConfig()

    llm = LLMClient(config)

    blocks = []
    if series_ticker:
        blocks.append(f"SERIES: {series_ticker}")
    if event_title or ev_category or ev_sub:
        event_block = f"EVENT: {event_title or '(unknown)'}"
        if ev_category:
            event_block += f"\nCategory: {ev_category}"
        if ev_sub:
            event_block += f"\nSubtitle: {ev_sub}"
        blocks.append(event_block)
    blocks.append(f"QUESTION: {question}")
    if context:
        blocks.append(f"RESOLUTION RULES:\n{context}")

    messages = [{"role": "user", "content": "\n\n".join(blocks)}]

    response = llm.complete(SYSTEM_PROMPT, messages, [_SUBMIT_TOOL], force_tool=True)
    if not response.tool_blocks:
        raise ValueError("Question Parser did not call submit_parsed_question")

    inp = response.tool_blocks[0].input
    parsed = _build_parsed_question(question, inp)
    errors = _validate(parsed)

    if errors:
        # Feed errors back as a rejected tool result and give the parser one retry
        rejection = {
            "status": "rejected",
            "errors": errors,
            "instructions": (
                "Fix ALL errors above and call submit_parsed_question again. "
                "Pay close attention to the event_type-specific requirements: "
                "relative_ordering questions require pairwise outside_view_target "
                "and pairwise selected_reference_class."
            ),
        }
        llm.extend_messages(
            messages, response,
            [{"tool_use_id": response.tool_blocks[0].id, "content": json.dumps(rejection)}]
        )
        retry = llm.complete(SYSTEM_PROMPT, messages, [_SUBMIT_TOOL], force_tool=True)
        if not retry.tool_blocks:
            raise ValueError(f"Question Parser failed validation and did not resubmit: {errors}")

        inp = retry.tool_blocks[0].input
        parsed = _build_parsed_question(question, inp)
        errors_after_retry = _validate(parsed)
        if errors_after_retry:
            raise ValueError(
                f"Question Parser failed validation after retry: {'; '.join(errors_after_retry)}"
            )

    return parsed
