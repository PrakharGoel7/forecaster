import json
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from forecaster.agents.base import LLMClient
from forecaster.config import ForecasterConfig
from forecaster.models import (
    ComparativeAgentForecast,
    ComparativeForecastMemo,
    ComparativeOptionForecast,
    ComparativeSupervisorReconciliation,
    EvidenceAge,
    EvidenceDirection,
    EvidenceItem,
    EvidenceLedger,
    EvidenceMagnitude,
    Reliability,
    SourceType,
)
from forecaster.tools.search import web_fetch, web_search
from forecaster.utils.temporal import (
    current_date_str,
    estimate_evidence_age,
    score_source_reliability,
)


COMPARATIVE_AGENT_SYSTEM_PROMPT = """You are a comparative forecasting agent for a multi-option prediction market.

You are not forecasting one option independently. Your job is to reason about ALL options jointly and assign a normalized probability distribution across them.

RULES:
- Treat the options as competing outcomes in one event.
- Compare the options against each other directly.
- Do not assign each option in isolation.
- Your probabilities must sum to 1.0 across the full option set.
- Research current evidence that helps distinguish which option is more likely than the others.
- Keep the main uncertainty about relative ordering between options, not generic uncertainty.
- Prefer official sources, primary data, and reputable news.
- Do not use prediction-market commentary as primary evidence.

OUTPUT REQUIREMENTS:
- Provide a probability for every option.
- Include a short rationale for each option explaining why it ranks where it does relative to the others.
- Call submit_comparative_forecast when done.
"""


COMPARATIVE_SUPERVISOR_SYSTEM_PROMPT = """You are the supervisor for a comparative forecasting ensemble.

You receive multiple normalized probability distributions over the same set of options.

Your job:
1. Identify where the agents disagree about relative ranking or spread.
2. If needed, run targeted searches only on the crux that separates the options.
3. Reconcile the option probabilities into one final normalized distribution.

RULES:
- This is a joint comparative forecast, not independent binary forecasts.
- The final option probabilities must sum to 1.0.
- Explain the decisive comparisons between the leading options.
- Keep the reasoning focused on why one option outranks another.
- Call submit_comparative_reconciliation when done.
"""


_COMPARATIVE_AGENT_TOOLS = [
    {
        "name": "web_search",
        "description": "Search for current evidence relevant to comparing the listed options.",
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
        "description": "Fetch the content of a URL to verify a comparative claim.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "add_evidence",
        "description": "Record a piece of comparative evidence in the ledger.",
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
                "magnitude": {
                    "type": "string",
                    "enum": ["strong", "moderate", "weak"],
                },
                "why_it_matters": {"type": "string"},
                "limitations": {"type": "string"},
                "date_published": {"type": "string"},
            },
            "required": [
                "claim", "source_url", "source_title", "source_type",
                "relevant_quote_or_snippet", "magnitude", "why_it_matters",
                "limitations",
            ],
        },
    },
    {
        "name": "submit_comparative_forecast",
        "description": "Submit a normalized probability distribution across all options.",
        "input_schema": {
            "type": "object",
            "properties": {
                "option_forecasts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string"},
                            "probability": {"type": "number"},
                            "rationale": {"type": "string"},
                        },
                        "required": ["ticker", "probability", "rationale"],
                    },
                },
                "key_drivers": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "uncertainty_reasoning": {"type": "string"},
                "epistemic_confidence": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                },
            },
            "required": [
                "option_forecasts", "key_drivers", "uncertainty_reasoning",
                "epistemic_confidence",
            ],
        },
    },
]


_COMPARATIVE_SUPERVISOR_TOOLS = [
    {
        "name": "web_search",
        "description": "Run a targeted search to resolve disagreement between comparative agent distributions.",
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
        "description": "Fetch a URL to verify a specific comparative claim.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "submit_comparative_reconciliation",
        "description": "Submit the final normalized probability distribution across all options.",
        "input_schema": {
            "type": "object",
            "properties": {
                "option_forecasts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string"},
                            "probability": {"type": "number"},
                            "rationale": {"type": "string"},
                        },
                        "required": ["ticker", "probability", "rationale"],
                    },
                },
                "disagreement_level": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                },
                "crux_of_disagreement": {"type": "string"},
                "targeted_searches_conducted": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "reconciliation_reasoning": {"type": "string"},
            },
            "required": [
                "option_forecasts", "disagreement_level",
                "targeted_searches_conducted", "reconciliation_reasoning",
            ],
        },
    },
]


def _format_options(markets: list[dict]) -> str:
    lines = []
    for market in markets:
        lines.append(
            f"- {market['ticker']}: {market['label']} | market price {market['market_price']:.3f} | question: {market['question']}"
        )
    return "\n".join(lines)


def _normalize_option_forecasts(raw_option_forecasts: list[dict], markets: list[dict]) -> list[ComparativeOptionForecast]:
    by_ticker = {m["ticker"]: m for m in markets}
    kept = [o for o in raw_option_forecasts if o.get("ticker") in by_ticker]
    if not kept:
        raise ValueError("No valid option forecasts returned")

    seen_tickers = {o["ticker"] for o in kept}
    for market in markets:
        if market["ticker"] not in seen_tickers:
            kept.append({
                "ticker": market["ticker"],
                "probability": 0.001,
                "rationale": "This option was omitted from the raw response and was backfilled at minimal weight.",
            })

    total = sum(max(0.001, float(o.get("probability", 0.0))) for o in kept)
    normalized: list[ComparativeOptionForecast] = []
    for option in kept:
        market = by_ticker[option["ticker"]]
        normalized.append(
            ComparativeOptionForecast(
                ticker=market["ticker"],
                label=market["label"],
                question=market["question"],
                market_price=float(market["market_price"]),
                probability=max(0.001, float(option.get("probability", 0.0))) / total,
                rationale=(option.get("rationale") or "").strip() or "Relative positioning not explained.",
            )
        )

    ordered = {o.ticker: o for o in normalized}
    return [ordered[m["ticker"]] for m in markets if m["ticker"] in ordered]


def _add_evidence_to_ledger(ledger: EvidenceLedger, inp: dict) -> dict:
    source_type = SourceType(inp.get("source_type", "unknown"))
    date_published = inp.get("date_published")
    ledger.items.append(
        EvidenceItem(
            claim=inp["claim"],
            source_url=inp["source_url"],
            source_title=inp["source_title"],
            source_type=source_type,
            reliability=score_source_reliability(source_type, inp["source_title"], inp["source_url"]),
            retrieved_at=datetime.now(timezone.utc),
            date_published=date_published or None,
            evidence_age=estimate_evidence_age(date_published),
            relevant_quote_or_snippet=inp["relevant_quote_or_snippet"],
            direction=EvidenceDirection.CONTEXT,
            magnitude=EvidenceMagnitude(inp.get("magnitude", "weak")),
            why_it_matters=inp.get("why_it_matters", ""),
            limitations=inp.get("limitations", ""),
            notes="comparative",
        )
    )
    return {"status": "ok", "items": len(ledger.items)}


def run_comparative_agent(
    event_title: str,
    event_subtitle: str,
    event_category: str,
    resolution_rules: str,
    markets: list[dict],
    agent_id: int,
    config: ForecasterConfig | None = None,
) -> ComparativeAgentForecast:
    if config is None:
        config = ForecasterConfig()

    llm = LLMClient(config)
    ledger = EvidenceLedger()
    today = current_date_str()

    user_message = (
        f"Forecast this multi-option market event jointly.\n\n"
        f"Current date: {today}\n"
        f"EVENT: {event_title}\n"
        f"CATEGORY: {event_category or 'unknown'}\n"
        f"SUBTITLE: {event_subtitle or 'none'}\n"
        f"RESOLUTION RULES:\n{resolution_rules or 'not provided'}\n\n"
        f"OPTIONS:\n{_format_options(markets)}\n\n"
        "Research the current state of the event and compare the options directly. "
        "Your final probabilities must sum to 1.0 across all options. "
        "Add evidence items to the ledger as you go. "
        "Call submit_comparative_forecast when done."
    )

    messages = [{"role": "user", "content": user_message}]
    forecast_input: dict | None = None

    for iteration in range(config.max_iv_iterations):
        if iteration == config.max_iv_iterations - 2:
            messages.append({
                "role": "user",
                "content": "One more search available. Then submit one normalized distribution across all options.",
            })

        response = llm.complete(COMPARATIVE_AGENT_SYSTEM_PROMPT, messages, _COMPARATIVE_AGENT_TOOLS)
        if not response.tool_blocks:
            break

        tool_results = []
        submitted = False
        for tb in response.tool_blocks:
            if tb.name == "web_search":
                content = json.dumps({"results": web_search(tb.input["query"], tb.input.get("max_results", 5))})
            elif tb.name == "web_fetch":
                content = json.dumps(web_fetch(tb.input["url"], config.fetch_max_chars))
            elif tb.name == "add_evidence":
                content = json.dumps(_add_evidence_to_ledger(ledger, tb.input))
            elif tb.name == "submit_comparative_forecast":
                forecast_input = tb.input
                submitted = True
                content = json.dumps({"status": "received"})
            else:
                content = json.dumps({"error": f"unknown tool {tb.name}"})
            tool_results.append({"tool_use_id": tb.id, "content": content})

        llm.extend_messages(messages, response, tool_results)
        if submitted:
            break

    if forecast_input is None:
        ledger.incomplete = True
        final = llm.complete(
            COMPARATIVE_AGENT_SYSTEM_PROMPT,
            messages + [{"role": "user", "content": "Research is complete. Submit your normalized option distribution now."}],
            [_COMPARATIVE_AGENT_TOOLS[-1]],
            force_tool=True,
        )
        if not final.tool_blocks:
            raise ValueError("Comparative forecasting agent did not submit a forecast")
        forecast_input = final.tool_blocks[0].input

    return ComparativeAgentForecast(
        agent_id=agent_id,
        option_forecasts=_normalize_option_forecasts(forecast_input["option_forecasts"], markets),
        key_drivers=forecast_input.get("key_drivers", []),
        uncertainty_reasoning=forecast_input.get("uncertainty_reasoning", ""),
        epistemic_confidence=forecast_input.get("epistemic_confidence", "medium"),
        evidence_ledger=ledger,
    )


def _fmt_comparative_agent_forecasts(agent_forecasts: list[ComparativeAgentForecast]) -> str:
    chunks = []
    for forecast in agent_forecasts:
        option_lines = [
            f"  - {opt.label} ({opt.ticker}): {opt.probability:.3f} — {opt.rationale}"
            for opt in forecast.option_forecasts
        ]
        chunks.append(
            f"Agent {forecast.agent_id}\n"
            f"Options:\n" + "\n".join(option_lines) + "\n"
            f"Key drivers: {'; '.join(forecast.key_drivers) or 'none'}\n"
            f"Uncertainty: {forecast.uncertainty_reasoning}\n"
            f"Confidence: {forecast.epistemic_confidence}\n"
            f"{forecast.evidence_ledger.format_for_prompt()}"
        )
    return "\n\n".join(chunks)


def run_comparative_supervisor(
    event_title: str,
    event_subtitle: str,
    event_category: str,
    resolution_rules: str,
    markets: list[dict],
    agent_forecasts: list[ComparativeAgentForecast],
    config: ForecasterConfig | None = None,
) -> ComparativeSupervisorReconciliation:
    if config is None:
        config = ForecasterConfig()

    llm = LLMClient(config)
    messages = [{
        "role": "user",
        "content": (
            f"Reconcile comparative multi-option forecasts.\n\n"
            f"EVENT: {event_title}\n"
            f"CATEGORY: {event_category or 'unknown'}\n"
            f"SUBTITLE: {event_subtitle or 'none'}\n"
            f"RESOLUTION RULES:\n{resolution_rules or 'not provided'}\n\n"
            f"OPTIONS:\n{_format_options(markets)}\n\n"
            f"AGENT FORECASTS:\n{_fmt_comparative_agent_forecasts(agent_forecasts)}\n\n"
            "Return one normalized final distribution across all options."
        ),
    }]

    reconciliation_input: dict | None = None

    for _ in range(5):
        response = llm.complete(COMPARATIVE_SUPERVISOR_SYSTEM_PROMPT, messages, _COMPARATIVE_SUPERVISOR_TOOLS)
        if not response.tool_blocks:
            break

        tool_results = []
        submitted = False
        for tb in response.tool_blocks:
            if tb.name == "web_search":
                content = json.dumps({"results": web_search(tb.input["query"], tb.input.get("max_results", 5))})
            elif tb.name == "web_fetch":
                content = json.dumps(web_fetch(tb.input["url"], config.fetch_max_chars))
            elif tb.name == "submit_comparative_reconciliation":
                reconciliation_input = tb.input
                submitted = True
                content = json.dumps({"status": "received"})
            else:
                content = json.dumps({"error": f"unknown tool {tb.name}"})
            tool_results.append({"tool_use_id": tb.id, "content": content})

        llm.extend_messages(messages, response, tool_results)
        if submitted:
            break

    if reconciliation_input is None:
        raise ValueError("Comparative supervisor did not submit a reconciliation")

    return ComparativeSupervisorReconciliation(
        option_forecasts=_normalize_option_forecasts(reconciliation_input["option_forecasts"], markets),
        disagreement_level=reconciliation_input.get("disagreement_level", "medium"),
        crux_of_disagreement=(reconciliation_input.get("crux_of_disagreement") or "").strip() or None,
        targeted_searches_conducted=reconciliation_input.get("targeted_searches_conducted", []),
        reconciliation_reasoning=reconciliation_input.get("reconciliation_reasoning", ""),
    )


def forecast_event_options(
    event_title: str,
    event_subtitle: str,
    event_category: str,
    resolution_rules: str,
    markets: list[dict],
    on_step=None,
    config: ForecasterConfig | None = None,
) -> ComparativeForecastMemo:
    if config is None:
        config = ForecasterConfig()

    agent_forecasts: list[ComparativeAgentForecast] = []
    with ThreadPoolExecutor(max_workers=config.num_iv_agents) as executor:
        future_to_idx = {}
        for i in range(config.num_iv_agents):
            if on_step:
                on_step(f"Agent {i+1}/{config.num_iv_agents}", "running")
            future_to_idx[executor.submit(
                run_comparative_agent,
                event_title,
                event_subtitle,
                event_category,
                resolution_rules,
                markets,
                i,
                config,
            )] = i

        ordered_results = [None] * config.num_iv_agents
        for future in as_completed(future_to_idx):
            i = future_to_idx[future]
            ordered_results[i] = future.result()
            if on_step:
                on_step(f"Agent {i+1}/{config.num_iv_agents}", "done")

    agent_forecasts = ordered_results

    if on_step:
        on_step("Supervisor", "running")
    reconciliation = run_comparative_supervisor(
        event_title=event_title,
        event_subtitle=event_subtitle,
        event_category=event_category,
        resolution_rules=resolution_rules,
        markets=markets,
        agent_forecasts=agent_forecasts,
        config=config,
    )
    if on_step:
        on_step("Supervisor", "done")

    return ComparativeForecastMemo(
        event_title=event_title,
        event_subtitle=event_subtitle,
        event_category=event_category,
        resolution_rules=resolution_rules,
        option_forecasts=reconciliation.option_forecasts,
        agent_forecasts=agent_forecasts,
        supervisor_reconciliation=reconciliation,
        num_agents=config.num_iv_agents,
    )
