import json
from forecaster.models import ParsedQuestion, ForeknowledgeRisk, EventType
from forecaster.config import ForecasterConfig
from forecaster.agents.base import LLMClient

SYSTEM_PROMPT = """You are a Prediction Question Analyst. Decompose a forecasting question into structural components for probabilistic forecasting.

DO NOT forecast.
DO NOT estimate probability.
DO NOT choose the final reference class.

Your job is to define the statistical object that outside-view agents must estimate.

Classify EVENT TYPE:
- binary_occurrence: Will X happen by date D?
- threshold: Will metric X exceed/fall below Y by date D?
- relative_ordering: Will A happen before B?
- election_selection: Will candidate/entity X win/be chosen?
- market_price: Will asset/metric reach level X?
- count_frequency: Will there be at least N events?
- conditional: Depends on definitions or external resolution criteria
- other: explain

CRITICAL:
Event type determines the statistical object.

- relative_ordering → needs pairwise ordering data
- threshold → needs threshold-crossing frequency
- election_selection → needs comparable candidate/entity win rates
- binary_occurrence → needs event occurrence frequency by comparable deadline
- market_price → needs historical distribution of comparable price moves
- count_frequency → needs historical count distribution

Your outputs:
1. EVENT TYPE — with one-sentence explanation.
2. RESOLUTION CRITERIA — exactly what must happen for YES.
3. OUTSIDE VIEW TARGET — exact statistical object needed.
4. TIME HORIZON — deadline/window that base rates must match.
5. THRESHOLD / COMPARISON STRUCTURE — if relevant.
6. BASE-RATE SEARCH HINTS — optional, non-binding queries.
7. INSIDE VIEW FACTORS — 3-5 instance-specific updating factors.
8. KEY UNKNOWNS — 2-4 high-impact uncertainties.
9. FOREKNOWLEDGE RISK — HIGH/MEDIUM/LOW.
10. AMBIGUITIES — underspecified terms affecting resolution.

Important:
Do NOT output “selected reference class.”
Do NOT collapse the reference-class search space.
The parser should frame the problem, not solve it.

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
            "time_horizon": {
                "type": "string",
                "description": "The deadline/window the outside-view base rate must match",
            },
            "threshold_or_comparison_structure": {
                "type": "string",
                "description": "Threshold, pairwise comparison, or count structure relevant to the statistical object",
            },
            "base_rate_search_hints": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional, non-binding search hints targeting base-rate data",
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
            "outside_view_target", "time_horizon",
            "threshold_or_comparison_structure",
            "base_rate_search_hints", "key_unknowns", "inside_view_factors",
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

    if not parsed.time_horizon.strip():
        errors.append(
            "time_horizon is empty. You must specify the deadline or comparison window the base rate should match."
        )

    if parsed.event_type == EventType.RELATIVE_ORDERING:
        target_lower = parsed.outside_view_target.lower()
        structure_lower = parsed.threshold_or_comparison_structure.lower()

        if not any(kw in target_lower for kw in _PAIRWISE_KEYWORDS):
            errors.append(
                f"event_type is relative_ordering but outside_view_target does not describe "
                f"pairwise ordering. Got: '{parsed.outside_view_target}'. "
                f"It must describe which of two comparable entities happens first — "
                f"NOT generic event frequency or total count statistics."
            )

        if not any(kw in structure_lower for kw in _PAIRWISE_KEYWORDS):
            errors.append(
                "event_type is relative_ordering but threshold_or_comparison_structure does not "
                "describe a pairwise comparison."
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
        time_horizon=inp.get("time_horizon", ""),
        threshold_or_comparison_structure=inp.get("threshold_or_comparison_structure", ""),
        base_rate_search_hints=inp.get("base_rate_search_hints", []),
        base_rate_queries=inp.get("base_rate_search_hints", []),
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

    llm = LLMClient(config, client_name="parser")

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
                "and pairwise comparison structure."
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
