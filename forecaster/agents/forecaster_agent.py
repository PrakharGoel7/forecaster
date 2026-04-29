import json
from datetime import datetime, timezone

from forecaster.models import (
    AgentForecast, EvidenceItem, EvidenceLedger, SourceType, EvidenceDirection, ParsedQuestion,
)
from forecaster.config import ForecasterConfig
from forecaster.agents.base import LLMClient
from forecaster.tools.search import web_search, web_fetch

SYSTEM_PROMPT = """You are an independent probabilistic forecasting agent. Estimate the probability that a prediction question resolves YES.

METHODOLOGY — follow this order strictly:
1. OUTSIDE VIEW FIRST: Search for the historical base rate of this type of event. What fraction of similar situations resolved YES historically? Anchor on this.
2. INSIDE VIEW SECOND: What is specific about this situation? Search for current evidence that updates you from the base rate — upward or downward.
3. SYNTHESIZE: Combine outside view and inside view into a final probability. Be explicit about how much each view moves you.

CALIBRATION RULES:
- Avoid anchoring to 50% without strong justification. Most questions have informative base rates.
- "Uncertain" ≠ 50%. Uncertainty about a rare event should still yield a low probability.
- State your probability as a single number, not a range. Express uncertainty through your confidence level.
- Consider what would have to be true for the question to resolve YES. Is that scenario plausible given the evidence?
- For questions near a deadline, consider how much new information could realistically arrive.

SEARCH STRATEGY:
- First searches: base rates, historical frequencies, reference class data
- Second searches: current state, recent developments, expert forecasts
- Third searches: specific facts that resolve key unknowns

Add evidence with add_evidence as you go. When you have enough to form a well-reasoned estimate, call submit_forecast.
"""

_TOOLS = [
    {
        "name": "web_search",
        "description": "Search the web for evidence relevant to the forecast.",
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
        "description": "Record a piece of evidence in the ledger.",
        "input_schema": {
            "type": "object",
            "properties": {
                "claim": {"type": "string"},
                "source_url": {"type": "string"},
                "source_title": {"type": "string"},
                "source_type": {
                    "type": "string",
                    "enum": ["official_primary", "regulatory", "reputable_secondary", "social_media", "unknown"],
                },
                "relevant_quote_or_snippet": {"type": "string"},
                "direction": {
                    "type": "string",
                    "enum": ["raises", "lowers", "base_rate", "context"],
                    "description": "Whether this evidence raises P(YES), lowers it, is a base rate, or is context",
                },
                "notes": {"type": "string"},
            },
            "required": ["claim", "source_url", "source_title", "source_type",
                         "relevant_quote_or_snippet", "direction", "notes"],
        },
    },
    {
        "name": "submit_forecast",
        "description": "Submit your final probability estimate with full reasoning.",
        "input_schema": {
            "type": "object",
            "properties": {
                "probability": {
                    "type": "number",
                    "description": "P(YES) as a decimal between 0.001 and 0.999",
                },
                "outside_view_base_rate": {
                    "type": "number",
                    "description": "Your base rate estimate from the reference class before inside-view adjustments",
                },
                "outside_view_reasoning": {
                    "type": "string",
                    "description": "What reference class you used and what the historical rate was",
                },
                "inside_view_reasoning": {
                    "type": "string",
                    "description": "What specific factors about this situation updated you from the base rate, and in which direction",
                },
                "key_factors_for": {
                    "type": "array", "items": {"type": "string"},
                    "description": "3-5 most important factors that increase P(YES)",
                },
                "key_factors_against": {
                    "type": "array", "items": {"type": "string"},
                    "description": "3-5 most important factors that decrease P(YES)",
                },
                "uncertainty_reasoning": {
                    "type": "string",
                    "description": "Main sources of uncertainty in your estimate",
                },
                "epistemic_confidence": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Your confidence in your own probability estimate (not whether YES will happen)",
                },
            },
            "required": [
                "probability", "outside_view_base_rate", "outside_view_reasoning",
                "inside_view_reasoning", "key_factors_for", "key_factors_against",
                "uncertainty_reasoning", "epistemic_confidence",
            ],
        },
    },
]


def run_forecasting_agent(
    parsed_question: ParsedQuestion,
    agent_id: int,
    config: ForecasterConfig | None = None,
) -> AgentForecast:
    if config is None:
        config = ForecasterConfig()

    llm = LLMClient(config)
    ledger = EvidenceLedger()

    user_message = (
        f"Forecast the following question.\n\n"
        f"{parsed_question.format_for_prompt()}\n\n"
        "Start with the OUTSIDE VIEW: search for base rates in the reference class. "
        "Then gather inside-view evidence. Add items to the ledger as you go. "
        "Call submit_forecast when you have a well-reasoned estimate."
    )

    messages = [{"role": "user", "content": user_message}]
    forecast_input: dict | None = None

    _SUBMIT_ONLY = [_TOOLS[-1]]  # just submit_forecast

    for iteration in range(config.max_search_iterations):
        # On the penultimate iteration, nudge the agent to wrap up
        if iteration == config.max_search_iterations - 2:
            messages.append({
                "role": "user",
                "content": "You have one more search available. After that, please call submit_forecast with your best estimate.",
            })

        response = llm.complete(SYSTEM_PROMPT, messages, _TOOLS)

        if not response.tool_blocks:
            # Model stopped generating tool calls — force a submission
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

    # Forced fallback: if agent never called submit_forecast, require it now
    if forecast_input is None:
        ledger.incomplete = True
        messages.append({
            "role": "user",
            "content": "Research complete. You must now submit your probability estimate by calling submit_forecast.",
        })
        final = llm.complete(SYSTEM_PROMPT, messages, _SUBMIT_ONLY, force_tool=True)
        if final.tool_blocks:
            forecast_input = final.tool_blocks[0].input
        else:
            raise ValueError(f"Forecasting Agent {agent_id} failed to submit even after forced prompt")

    return AgentForecast(
        agent_id=agent_id,
        probability=float(forecast_input["probability"]),
        outside_view_base_rate=float(forecast_input["outside_view_base_rate"]),
        outside_view_reasoning=forecast_input["outside_view_reasoning"],
        inside_view_reasoning=forecast_input["inside_view_reasoning"],
        key_factors_for=forecast_input.get("key_factors_for", []),
        key_factors_against=forecast_input.get("key_factors_against", []),
        uncertainty_reasoning=forecast_input["uncertainty_reasoning"],
        epistemic_confidence=forecast_input["epistemic_confidence"],
        evidence_ledger=ledger,
    )


def _execute_tool(name: str, args: dict, ledger: EvidenceLedger, config: ForecasterConfig) -> dict:
    if name == "web_search":
        return {"results": web_search(args["query"], args.get("max_results", config.search_max_results))}

    if name == "web_fetch":
        return web_fetch(args["url"], config.fetch_max_chars)

    if name == "add_evidence":
        item = EvidenceItem(
            claim=args["claim"],
            source_url=args["source_url"],
            source_title=args["source_title"],
            source_type=SourceType(args["source_type"]),
            retrieved_at=datetime.now(timezone.utc),
            relevant_quote_or_snippet=args["relevant_quote_or_snippet"],
            direction=EvidenceDirection(args["direction"]),
            notes=args["notes"],
        )
        ledger.items.append(item)
        return {"status": "added", "index": len(ledger.items) - 1}

    if name == "submit_forecast":
        return {"status": "received"}

    return {"error": f"Unknown tool: {name}"}
