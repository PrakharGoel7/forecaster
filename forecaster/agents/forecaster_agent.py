import json
from datetime import datetime, timezone

from forecaster.models import (
    AgentForecast, OutsideViewConsensus, EvidenceItem, EvidenceLedger,
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

SYSTEM_PROMPT = """You are an Inside View forecasting agent. The historical base rate has already been established and will be given to you. Your job is to find specific, current evidence about THIS situation that updates from that base rate.

DO NOT re-research historical base rates — that work is done.
DO NOT use stale evidence unless it is structurally important.
DO NOT treat speculation as fact.
DO NOT drift toward 50% because evidence is mixed.

Your job:
1. Determine the current state of the specific situation.
2. Find recent, high-quality evidence relevant to the key unknowns.
3. Identify which evidence updates the base rate upward or downward, and by how much.
4. Produce a calibrated probability.

TEMPORAL RULES:
- Prefer evidence from the last 12 months unless older evidence is structurally important.
- Include the current year or recent phrasing in search queries.
- If using older evidence, explicitly explain why it still applies.
- Check whether the event may already be resolved.

SOURCE QUALITY RULES:
- Prefer: official statements, filings, regulators, exchanges, reputable news outlets, primary data.
- Low reliability: blogs, SEO finance sites, prediction-market commentary, unsourced claims.
- Low-reliability evidence should not drive large updates.

CALIBRATION RULES:
- Start from the given base rate. Each update must include direction AND rough magnitude:
  - strong_raise / modest_raise / neutral / modest_lower / strong_lower
- If evidence is weak or mixed, stay near the base rate.
- "Uncertain" does not mean 50%.
- State a single probability.

BAD REASONING TO AVOID:
- Overweighting speculative rumors or low-reliability sources.
- Confusing valuation/size/activity with event probability.
- Treating "possible" as "likely."
- Ignoring the time horizon to resolution.
- Large updates from weak evidence.
- Drifting to 50% because both sides have some evidence.
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
                    "enum": ["strong", "moderate", "weak"],
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
                "probability": {
                    "type": "number",
                    "description": "P(YES) as decimal 0.001-0.999",
                },
                "starting_base_rate": {
                    "type": "number",
                    "description": "The base rate you started from (should match the OV consensus given to you)",
                },
                "adjustment_from_base": {
                    "type": "number",
                    "description": "Net adjustment: positive = raised from base rate, negative = lowered",
                },
                "key_updates_from_base": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List each update with magnitude, e.g. 'strong_raise: CEO confirmed IPO target by Q3 2025'",
                },
                "inside_view_reasoning": {
                    "type": "string",
                    "description": "What specific factors about this situation updated you from the base rate and in which direction",
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
                "epistemic_confidence": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Your confidence in this probability estimate",
                },
            },
            "required": [
                "probability", "starting_base_rate", "adjustment_from_base",
                "key_updates_from_base", "inside_view_reasoning",
                "key_factors_for", "key_factors_against",
                "unresolved_cruxes", "uncertainty_reasoning", "epistemic_confidence",
            ],
        },
    },
]


def run_forecasting_agent(
    parsed_question: ParsedQuestion,
    agent_id: int,
    ov_consensus: OutsideViewConsensus,
    config: ForecasterConfig | None = None,
) -> AgentForecast:
    if config is None:
        config = ForecasterConfig()

    llm = LLMClient(config)
    ledger = EvidenceLedger()
    today = current_date_str()

    user_message = (
        f"Forecast the following question.\n\n"
        f"Current date: {today}\n\n"
        f"{parsed_question.format_for_prompt()}\n\n"
        f"ESTABLISHED OUTSIDE VIEW:\n"
        f"  Base rate: {ov_consensus.base_rate:.3f} ({ov_consensus.base_rate * 100:.0f}%)\n"
        f"  Statistical object: {ov_consensus.statistical_object or 'see reference class'}\n"
        f"  Reference class: {ov_consensus.reference_class}\n"
        f"  Basis: {ov_consensus.denominator_or_basis or 'see reasoning'}\n"
        f"  Limitations: {ov_consensus.reference_class_limitations or 'none noted'}\n"
        f"  Reasoning: {ov_consensus.reasoning}\n\n"
        "Start from this base rate. Search for CURRENT, SITUATION-SPECIFIC evidence. "
        "Include the current year in search queries. "
        "Add items to the ledger as you go. "
        "Call submit_forecast when you have a well-reasoned estimate."
    )

    messages = [{"role": "user", "content": user_message}]
    forecast_input: dict | None = None

    _SUBMIT_ONLY = [_TOOLS[-1]]

    for iteration in range(config.max_iv_iterations):
        if iteration == config.max_iv_iterations - 2:
            messages.append({
                "role": "user",
                "content": (
                    "One more search available. Then call submit_forecast. "
                    "List each update from base rate with its direction and magnitude."
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
            "content": "Research complete. You must now call submit_forecast with your best estimate.",
        })
        final = llm.complete(SYSTEM_PROMPT, messages, _SUBMIT_ONLY, force_tool=True)
        if final.tool_blocks:
            forecast_input = final.tool_blocks[0].input
        else:
            raise ValueError(f"Inside View Agent {agent_id} failed to submit")

    return AgentForecast(
        agent_id=agent_id,
        probability=float(forecast_input["probability"]),
        outside_view_base_rate=ov_consensus.base_rate,
        outside_view_reasoning=ov_consensus.reasoning,
        inside_view_reasoning=forecast_input["inside_view_reasoning"],
        key_factors_for=forecast_input.get("key_factors_for", []),
        key_factors_against=forecast_input.get("key_factors_against", []),
        uncertainty_reasoning=forecast_input["uncertainty_reasoning"],
        epistemic_confidence=forecast_input["epistemic_confidence"],
        evidence_ledger=ledger,
        starting_base_rate=float(forecast_input.get("starting_base_rate", ov_consensus.base_rate)),
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
            magnitude=EvidenceMagnitude(args["magnitude"]) if args.get("magnitude") else None,
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
