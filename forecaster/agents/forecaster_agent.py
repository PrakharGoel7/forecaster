import json
from datetime import datetime, timezone

from forecaster.models import (
    AgentForecast, ReconciledOutsideView, EvidenceItem, EvidenceLedger,
    SourceType, EvidenceDirection, EvidenceMagnitude, Reliability, EvidenceAge,
    ParsedQuestion,
)
from forecaster.config import ForecasterConfig
from forecaster.agents.base import LLMClient
from forecaster.tools.search import web_search, web_fetch
from forecaster.utils.temporal import (
    score_source_reliability, estimate_evidence_age, detect_stale_year_in_query,
    current_date_str, current_year,
)

SYSTEM_PROMPT = """You are an Inside View forecasting agent.

The historical outside-view base rate has already been established. Your job is to find current, situation-specific evidence about THIS case and update from that base rate.

DO NOT re-research historical base rates.
DO NOT use current evidence to redefine the reference class.
DO NOT use stale evidence unless structurally important.
DO NOT treat speculation as fact.
DO NOT drift toward 50% because evidence is mixed.

Your job:
1. Determine the current state of the specific situation.
2. Find recent, high-quality evidence relevant to the key unknowns.
3. Identify which evidence updates the base rate upward or downward.
4. Quantify each update.
5. Produce a calibrated final probability.

TEMPORAL RULES:
- Prefer evidence from the last 12 months unless older evidence is structurally important.
- Include the current year or recent phrasing in search queries.
- If using older evidence, explain why it still applies.
- Check whether the event may already be resolved.
- Explicitly account for time remaining until resolution.

SOURCE QUALITY RULES:
Prefer:
- official statements
- filings
- regulators
- exchanges
- primary data
- reputable news outlets

Use caution with:
- blogs
- SEO finance sites
- prediction-market commentary
- anonymous claims
- unsourced speculation

Low-reliability evidence should not drive large updates.

UPDATE RULES:
Start from the given outside-view base rate.

For each distinct piece of evidence, report:
- evidence
- source quality
- whether it is independent or repeats other evidence
- direction
- magnitude
- probability-point adjustment
- reason for adjustment

Use this scale:
- strong_raise: +15pp or more
- modest_raise: +5 to +15pp
- slight_raise: +1 to +5pp
- neutral: -1 to +1pp
- slight_lower: -1 to -5pp
- modest_lower: -5 to -15pp
- strong_lower: -15pp or more

Do not double-count repeated evidence.
If multiple sources report the same fact, treat it as one update with higher confidence, not multiple updates.

CALIBRATION RULES:
- Weak or mixed evidence should leave the forecast near the base rate.
- Uncertainty does not imply 50%.
- Large updates require strong, direct, high-quality evidence.
- If final probability differs from base rate by more than 20pp, explicitly justify why.
- If the event is close to resolution, direct current-state evidence may deserve larger weight.
- If the deadline is far away, avoid over-updating on transient signals.
- Final probability must be between 1% and 99% unless the event is already effectively resolved.

BAD REASONING TO AVOID:
- Overweighting rumors.
- Treating “possible” as “likely.”
- Confusing activity, popularity, valuation, or media attention with event probability.
- Ignoring the deadline.
- Double-counting repeated news.
- Moving to 50% just because evidence exists on both sides.
- Making large updates from weak evidence.

MULTI-OPTION CONTEXT:
You may be given sibling options from the same event.
Use them only to understand competition, overlap, and market structure.
Return only the selected option forecast.

MULTI-LOOP RESEARCH DISCIPLINE:
You may have multiple search/tool loops.

Across loops:
1. Keep a running ledger of situation-specific evidence.
2. After each search, classify evidence as:
   - direct update
   - weak/contextual update
   - rejected/duplicative
3. Do not repeat equivalent searches unless refining a failed query.
4. Search around key unknowns, not just the question wording.
5. Submit only when:
   - current state is established, and
   - major key unknowns have been checked, and
   - update ledger explains the move from base rate to final probability.
"""

_TOOLS = [
    {
        "name": "web_search",
        "description": "Search for current, situation-specific evidence.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "web_fetch",
        "description": "Fetch the full content of a specific URL.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "add_evidence",
        "description": "Record a piece of situation-specific evidence in the ledger.",
        "input_schema": {
            "type": "object",
            "properties": {
                "claim": {"type": "string"},
                "source_url": {"type": "string"},
                "source_title": {"type": "string"},
                "source_type": {
                    "type": "string",
                    "enum": ["official", "primary_data", "reputable_news",
                             "expert_analysis", "market_data", "blog", "unknown"],
                },
                "relevant_quote_or_snippet": {"type": "string"},
                "direction": {
                    "type": "string",
                    "enum": ["raises", "lowers", "neutral", "context"],
                    "description": "How this evidence moves P(YES) relative to the base rate",
                },
                "magnitude": {
                    "type": "string",
                    "enum": ["strong", "moderate", "modest", "weak", "slight"],
                    "description": "How large is the update this evidence justifies",
                },
                "date_published": {
                    "type": "string",
                    "description": "Publication date YYYY-MM-DD or YYYY-MM (leave blank if unknown)",
                },
                "why_it_matters": {
                    "type": "string",
                    "description": "Why this evidence is relevant to the forecast",
                },
                "limitations": {
                    "type": "string",
                    "description": "Reliability caveats or reasons to discount this evidence",
                },
                "notes": {"type": "string"},
            },
            "required": ["claim", "source_url", "source_title", "source_type",
                         "relevant_quote_or_snippet", "direction", "magnitude",
                         "why_it_matters", "limitations"],
        },
    },
    {
        "name": "submit_forecast",
        "description": "Submit your final probability estimate.",
        "input_schema": {
            "type": "object",
            "properties": {
                "starting_base_rate": {
                    "type": "number",
                    "description": "The outside-view base rate you started from.",
                },
                "final_probability": {
                    "type": "number",
                    "description": "Final P(YES) as decimal 0.01-0.99 unless already effectively resolved.",
                },
                "current_state_summary": {
                    "type": "string",
                    "description": "Concise summary of the current state of the situation and what remains unresolved.",
                },
                "resolved_or_partially_resolved": {
                    "type": "boolean",
                    "description": "Whether the event is already resolved or materially partially resolved.",
                },
                "update_ledger": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "evidence": {"type": "string"},
                            "source_quality": {"type": "string"},
                            "independence": {
                                "type": "string",
                                "enum": ["independent", "duplicative", "context_only", "rejected"],
                            },
                            "direction": {
                                "type": "string",
                                "enum": [
                                    "strong_raise", "modest_raise", "slight_raise",
                                    "neutral",
                                    "slight_lower", "modest_lower", "strong_lower",
                                ],
                            },
                            "probability_point_adjustment": {"type": "number"},
                            "rationale": {"type": "string"},
                        },
                        "required": [
                            "evidence", "source_quality", "independence", "direction",
                            "probability_point_adjustment", "rationale",
                        ],
                    },
                },
                "key_updates_from_base": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Concise text summary of the main updates from the base rate.",
                },
                "inside_view_reasoning": {
                    "type": "string",
                    "description": "Explain how current evidence moved you from the outside-view base rate to the final estimate.",
                },
                "large_deviation_justification": {
                    "type": ["string", "null"],
                    "description": "Required if final probability differs from the base rate by more than 20 percentage points.",
                },
                "key_factors_for": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "3-5 most important factors increasing P(YES)",
                },
                "key_factors_against": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "3-5 most important factors decreasing P(YES)",
                },
                "unresolved_cruxes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Key factual questions that remain unresolved and would most change the forecast",
                },
                "uncertainty_reasoning": {
                    "type": "string",
                    "description": "Main sources of uncertainty in your estimate",
                },
                "confidence": {
                    "type": "string",
                    "enum": ["LOW", "MEDIUM", "HIGH"],
                    "description": "Your confidence in this probability estimate",
                },
            },
            "required": [
                "starting_base_rate", "final_probability", "current_state_summary",
                "resolved_or_partially_resolved", "update_ledger",
                "key_updates_from_base", "inside_view_reasoning",
                "key_factors_for", "key_factors_against",
                "unresolved_cruxes", "uncertainty_reasoning", "confidence",
            ],
        },
    },
]


def _format_related_markets(related_markets: list[dict]) -> str:
    if not related_markets:
        return "No sibling options provided."
    lines = []
    for market in related_markets:
        lines.append(
            f"- {market.get('ticker', '?')}: "
            f"{market.get('label') or market.get('question') or market.get('ticker', '?')} "
            f"| market price {float(market.get('market_price') or 0.0):.3f}"
        )
    return "\n".join(lines)


def run_forecasting_agent(
    parsed_question: ParsedQuestion,
    agent_id: int,
    ov_reconciliation: ReconciledOutsideView,
    related_markets: list[dict] | None = None,
    config: ForecasterConfig | None = None,
) -> AgentForecast:
    if config is None:
        config = ForecasterConfig()

    llm = LLMClient(config, client_name=f"inside_view_agent_{agent_id}")
    ledger = EvidenceLedger()
    today = current_date_str()
    related_markets = related_markets or []

    user_message = (
        f"Forecast the following question.\n\n"
        f"Current date: {today}\n\n"
        f"{parsed_question.format_for_prompt()}\n\n"
        f"ESTABLISHED OUTSIDE VIEW:\n"
        f"  Base rate: {ov_reconciliation.final_prior:.3f} ({ov_reconciliation.final_prior * 100:.0f}%)\n"
        f"  Statistical object: {ov_reconciliation.statistical_object or parsed_question.outside_view_target or 'see reference class'}\n"
        f"  Reference class / basis: {ov_reconciliation.reference_class_summary or 'see rationale'}\n"
        f"  Denominator / basis: {ov_reconciliation.denominator_summary or 'see reasoning'}\n"
        f"  Plausible range: {ov_reconciliation.plausible_range or 'not provided'}\n"
        f"  Confidence: {ov_reconciliation.confidence or 'not provided'}\n"
        f"  Limitations: none noted\n"
        f"  Reasoning: {ov_reconciliation.rationale}\n"
        f"  Notes for inside view: {ov_reconciliation.notes_for_inside_view or 'none'}\n\n"
        f"SELECTED OPTION:\n"
        f"  Question: {parsed_question.question}\n\n"
        f"SIBLING OPTIONS FROM THE SAME EVENT:\n{_format_related_markets(related_markets)}\n\n"
        "YOUR TASK:\n"
        "1. Check whether the event is already resolved or partially resolved.\n"
        "2. Determine the current state of the specific situation.\n"
        "3. Search for recent, situation-specific evidence relevant to the key unknowns.\n"
        "4. Build an update ledger from the outside-view base rate.\n"
        "5. Produce a final probability for the selected option only.\n\n"
        "For each update, include:\n"
        "- evidence\n"
        "- source quality\n"
        "- direction\n"
        "- magnitude\n"
        "- probability-point adjustment\n"
        "- whether the evidence is independent or duplicative\n"
        "- short rationale\n\n"
        "Important:\n"
        "- Start from the outside-view base rate.\n"
        "- Do not re-research historical base rates.\n"
        "- Do not use sibling options as evidence except to understand competition/overlap.\n"
        "- Do not double-count repeated facts from multiple sources.\n"
        "- Include the current year or recent phrasing in searches.\n"
        "- If final probability differs from the base rate by more than 20pp, explicitly justify why.\n"
        "- Call submit_forecast when you have a well-reasoned estimate."
    )

    messages = [{"role": "user", "content": user_message}]
    forecast_input: dict | None = None

    _SUBMIT_ONLY = [_TOOLS[-1]]

    for iteration in range(config.max_iv_iterations):
        if iteration == config.max_iv_iterations - 2:
            messages.append({
                "role": "user",
                "content": (
                    "One more search available. Then call submit_forecast.\n\n"
                    "Before submitting, make sure you have:\n"
                    "- checked whether the event is already resolved\n"
                    "- established the current state\n"
                    "- listed each update from the outside-view base rate\n"
                    "- assigned direction and probability-point magnitude to each update\n"
                    "- avoided double-counting duplicated evidence\n"
                    "- justified any move greater than 20pp from the base rate"
                ),
            })

        response = llm.complete(SYSTEM_PROMPT, messages, _TOOLS)

        if not response.tool_blocks:
            break

        tool_results = []
        submitted = False

        for tb in response.tool_blocks:
            result = _execute_tool(tb.name, tb.input, ledger, config)
            tool_results.append({"tool_use_id": tb.id, "content": json.dumps(result)})
            if tb.name == "submit_forecast":
                forecast_input = tb.input
                submitted = True

        llm.extend_messages(messages, response, tool_results)

        if submitted:
            break

    if forecast_input is None:
        ledger.incomplete = True
        messages.append({
            "role": "user",
            "content": (
                "Research complete. You must now call submit_forecast with your best estimate.\n\n"
                "Your final forecast must include:\n"
                "- starting outside-view base rate\n"
                "- current-state summary\n"
                "- update ledger\n"
                "- final probability\n"
                "- confidence\n"
                "- explanation for any large deviation from the base rate"
            ),
        })
        final = llm.complete(SYSTEM_PROMPT, messages, _SUBMIT_ONLY, force_tool=True)
        if final.tool_blocks:
            forecast_input = final.tool_blocks[0].input
        else:
            raise ValueError(f"Inside View Agent {agent_id} failed to submit")

    return AgentForecast(
        agent_id=agent_id,
        probability=float(forecast_input["final_probability"]),
        outside_view_base_rate=ov_reconciliation.final_prior,
        outside_view_reasoning=ov_reconciliation.rationale,
        inside_view_reasoning=forecast_input["inside_view_reasoning"],
        key_factors_for=forecast_input.get("key_factors_for", []),
        key_factors_against=forecast_input.get("key_factors_against", []),
        uncertainty_reasoning=forecast_input["uncertainty_reasoning"],
        epistemic_confidence=forecast_input["confidence"].lower(),
        evidence_ledger=ledger,
        starting_base_rate=float(forecast_input.get("starting_base_rate", ov_reconciliation.final_prior)),
        current_state_summary=forecast_input.get("current_state_summary", ""),
        resolved_or_partially_resolved=bool(forecast_input.get("resolved_or_partially_resolved", False)),
        update_ledger=forecast_input.get("update_ledger", []),
        large_deviation_justification=forecast_input.get("large_deviation_justification"),
        key_updates_from_base=forecast_input.get("key_updates_from_base", []),
        unresolved_cruxes=forecast_input.get("unresolved_cruxes", []),
    )


def _execute_tool(name: str, args: dict, ledger: EvidenceLedger, config: ForecasterConfig) -> dict:
    if name == "web_search":
        query = args["query"]
        result = {"results": web_search(query, args.get("max_results", config.search_max_results))}
        stale_yr = detect_stale_year_in_query(query)
        if stale_yr:
            result["temporal_warning"] = (
                f"Query references {stale_yr} which may be stale. "
                f"Current year is {current_year()}. Prefer recent evidence."
            )
        return result

    if name == "web_fetch":
        return web_fetch(args["url"], config.fetch_max_chars)

    if name == "add_evidence":
        url = args["source_url"]
        auto_reliability = score_source_reliability(url, args.get("source_title", ""))
        date_pub = args.get("date_published") or None
        raw_magnitude = args.get("magnitude")
        normalized_magnitude = {
            "slight": "weak",
            "modest": "moderate",
        }.get(raw_magnitude, raw_magnitude)
        item = EvidenceItem(
            claim=args["claim"],
            source_url=url,
            source_title=args["source_title"],
            source_type=SourceType(args["source_type"]),
            reliability=Reliability(auto_reliability),
            retrieved_at=datetime.now(timezone.utc),
            date_published=date_pub,
            evidence_age=EvidenceAge(estimate_evidence_age(date_pub)),
            relevant_quote_or_snippet=args["relevant_quote_or_snippet"],
            direction=EvidenceDirection(args["direction"]),
            magnitude=EvidenceMagnitude(normalized_magnitude) if normalized_magnitude else None,
            why_it_matters=args.get("why_it_matters", ""),
            limitations=args.get("limitations", ""),
            notes=args.get("notes", ""),
        )
        ledger.items.append(item)
        feedback = {"status": "added", "index": len(ledger.items) - 1, "auto_reliability": auto_reliability}
        if auto_reliability == "low":
            feedback["reliability_warning"] = (
                "Source auto-scored as LOW reliability. "
                "Do not make large updates based on this evidence alone."
            )
        return feedback

    if name == "submit_forecast":
        return {"status": "received"}

    return {"error": f"Unknown tool: {name}"}
