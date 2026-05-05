import json
from datetime import datetime, timezone

from forecaster.models import (
    OutsideViewEstimate, ReconciledOutsideView, EvidenceItem, EvidenceLedger,
    SourceType, EvidenceDirection, EvidenceMagnitude, Reliability, EvidenceAge,
    ParsedQuestion, EventType,
)
from forecaster.config import ForecasterConfig
from forecaster.agents.base import LLMClient
from forecaster.tools.search import web_search, web_fetch
from forecaster.utils.temporal import (
    score_source_reliability, estimate_evidence_age, detect_stale_year_in_query, current_year,
)


def _normalize_confidence(value: str | None, default: str = "low") -> str:
    if not value:
        return default
    normalized = value.lower()
    return normalized if normalized in {"low", "medium", "high"} else default

SHARED_USER_PROMPT = """Establish an outside-view base rate for the following parsed forecasting question.

{parsed_question}

Current year: {current_year}{event_type_warning}

SIBLING OPTIONS FROM SAME EVENT, CONTEXT ONLY:
{related_markets}

EVENT TYPE:
{event_type}

STATISTICAL OBJECT:
{outside_view_target}

TIME HORIZON:
{time_horizon}

THRESHOLD / COMPARISON STRUCTURE:
{structure}

BASE-RATE SEARCH HINTS, NON-BINDING:
{search_hints}

Important:
- Do not look up the current state of the specific situation.
- Do not use sibling options as evidence.
- Use sibling options only to understand the event structure.
- Every valid base rate requires an explicit denominator.
- If no valid estimate exists, say so.

Call your relevant submit function when complete.
"""

AGENT_A_SYSTEM_PROMPT = """You are Outside View Agent A: Direct Empirical Base Rates.

Your job is to find the most direct historical base rate for the statistical object defined by the parser.

You must answer:
"How often has this exact type of event occurred in comparable historical cases over a comparable time horizon?"

DO NOT research the current specific situation as evidence.
DO NOT use recent news about the target entity as evidence.
DO NOT use vague category frequency.
DO NOT produce a probability without a denominator.

Prioritize:
- official datasets
- academic papers
- government data
- exchange data
- structured historical records
- reputable financial/statistical sources

Your process:
1. Restate the statistical object.
2. Search for direct empirical frequency data.
3. Ensure time horizon matches.
4. Extract denominator N and successes X.
5. Estimate base rate = X/N.
6. Report uncertainty from sample size, fit, time horizon, and source quality.

If no direct base rate exists, say so. Do not force one.
"""

AGENT_B_SYSTEM_PROMPT = """You are Outside View Agent B: Conditional and Narrow Reference Classes.

Your job is to construct a better-fitting conditional base rate by filtering historical cases.

You must answer:
"Among cases that share the most important structural features with this question, how often did YES occur?"

DO NOT research the current specific situation as evidence.
DO NOT use target-specific news.
DO NOT overfit to a tiny reference class without warning.

Your process:
1. Identify 2-4 structural filters that matter.
2. Construct one or more conditional reference classes.
3. For each, estimate X successes out of N cases.
4. Prefer the class with the best balance of fit and sample size.
5. Report where the class may be too narrow or biased.
"""

AGENT_C_SYSTEM_PROMPT = """You are Outside View Agent C: Analog and Decomposed Base Rates.

Your job is to estimate a base rate when direct empirical data is weak, sparse, or mismatched.

You may use:
1. Analog case sets
2. Decomposition into sub-events
3. Historical distributions
4. Broad comparable market-implied priors, but not the target market

DO NOT research the current specific situation as evidence.
DO NOT use vibes or narrative plausibility.
DO NOT cherry-pick analogs.

Your process:
1. Decide whether analogs, decomposition, or distributional reasoning is most appropriate.
2. If using analogs:
   - build 5-30 comparable cases where possible
   - state inclusion criteria
   - compute X/N
3. If decomposing:
   - break event into components
   - estimate each component’s base rate
   - combine transparently
4. If using distributions:
   - estimate how often comparable outcomes crossed the relevant threshold/window.
5. Clearly mark uncertainty.
"""

RECONCILER_SYSTEM_PROMPT = """You are the Outside View Reconciler.

Your job is to compare independent outside-view estimates and produce one final outside-view prior.

DO NOT introduce current target-specific evidence.
DO NOT perform inside-view updating.
DO NOT average blindly.

Evaluate each estimate on:
1. Reference-class fit
2. Denominator clarity
3. Sample size
4. Time-horizon match
5. Source quality
6. Selection bias risk
7. Regime-change risk
8. Whether it answers the exact statistical object

Reject estimates that:
- lack a denominator
- mismatch the event type
- use generic category frequency
- mismatch the time horizon
- rely on anecdotes
- use target-specific current evidence
- are structurally irrelevant

Then blend valid estimates.

Blending guidance:
- Prefer direct empirical estimates when fit and denominator are strong.
- Prefer conditional estimates when direct estimates are too broad.
- Use analog/decomposed estimates when direct data is weak.
- If estimates disagree, give a range and explain why.
- If all estimates are weak, use a LOW-confidence fallback prior.
"""

SEARCH_TOOLS = [
    {
        "name": "web_search",
        "description": "Search for historical base-rate evidence.",
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
        "description": "Fetch a URL to inspect historical statistics or records.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "add_evidence",
        "description": "Record a base-rate or contextual datapoint in the ledger.",
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
                    "enum": ["base_rate", "context"],
                },
                "magnitude": {
                    "type": "string",
                    "enum": ["strong", "moderate", "modest", "weak", "slight", "neutral"],
                },
                "date_published": {"type": "string"},
                "why_it_matters": {"type": "string"},
                "limitations": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["claim", "source_url", "source_title", "source_type",
                         "relevant_quote_or_snippet", "direction", "magnitude",
                         "why_it_matters", "limitations"],
        },
    },
]

SUBMIT_A_TOOL = {
    "name": "submit_direct_empirical_estimate",
    "description": "Submit the direct empirical outside-view estimate, or explicitly say none exists.",
    "input_schema": {
        "type": "object",
        "properties": {
            "statistical_object": {"type": "string"},
            "searched_reference_class": {"type": "string"},
            "denominator": {"type": "string"},
            "successes": {"type": "string"},
            "empirical_rate": {"type": ["number", "null"]},
            "time_horizon_match": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "string", "enum": ["low", "medium", "high", "LOW", "MEDIUM", "HIGH"]},
            "key_weaknesses": {"type": "array", "items": {"type": "string"}},
            "final_direct_empirical_estimate": {"type": ["number", "null"]},
            "no_valid_direct_estimate": {"type": "boolean"},
            "reasoning": {"type": "string"},
        },
        "required": [
            "statistical_object", "searched_reference_class", "denominator", "successes",
            "empirical_rate", "time_horizon_match", "sources", "confidence",
            "key_weaknesses", "final_direct_empirical_estimate", "no_valid_direct_estimate", "reasoning",
        ],
    },
}

SUBMIT_B_TOOL = {
    "name": "submit_conditional_estimate",
    "description": "Submit the strongest conditional outside-view estimate.",
    "input_schema": {
        "type": "object",
        "properties": {
            "candidate_conditional_reference_classes": {"type": "array", "items": {"type": "string"}},
            "inclusion_exclusion_criteria": {"type": "array", "items": {"type": "string"}},
            "denominator": {"type": "string"},
            "successes": {"type": "string"},
            "empirical_rate": {"type": ["number", "null"]},
            "sources": {"type": "array", "items": {"type": "string"}},
            "strongest_conditional_estimate": {"type": ["number", "null"]},
            "confidence": {"type": "string", "enum": ["low", "medium", "high", "LOW", "MEDIUM", "HIGH"]},
            "key_weaknesses": {"type": "array", "items": {"type": "string"}},
            "strongest_reference_class": {"type": "string"},
            "reasoning": {"type": "string"},
        },
        "required": [
            "candidate_conditional_reference_classes", "inclusion_exclusion_criteria", "denominator",
            "successes", "empirical_rate", "sources", "strongest_conditional_estimate",
            "confidence", "key_weaknesses", "strongest_reference_class", "reasoning",
        ],
    },
}

SUBMIT_C_TOOL = {
    "name": "submit_analog_decomposed_estimate",
    "description": "Submit the analog, decomposed, or distributional outside-view estimate.",
    "input_schema": {
        "type": "object",
        "properties": {
            "method_used": {"type": "string", "enum": ["analog", "decomposed", "distributional"]},
            "reference_cases_or_components": {"type": "array", "items": {"type": "string"}},
            "denominator_or_component_estimates": {"type": "string"},
            "empirical_or_computed_rate": {"type": ["number", "null"]},
            "assumptions": {"type": "array", "items": {"type": "string"}},
            "sources": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "string", "enum": ["low", "medium", "high", "LOW", "MEDIUM", "HIGH"]},
            "key_weaknesses": {"type": "array", "items": {"type": "string"}},
            "final_analog_decomposed_estimate": {"type": ["number", "null"]},
            "reasoning": {"type": "string"},
        },
        "required": [
            "method_used", "reference_cases_or_components", "denominator_or_component_estimates",
            "empirical_or_computed_rate", "assumptions", "sources", "confidence",
            "key_weaknesses", "final_analog_decomposed_estimate", "reasoning",
        ],
    },
}

RECONCILER_TOOLS = [
    {
        "name": "submit_reconciled_outside_view",
        "description": "Submit the reconciled outside-view prior.",
        "input_schema": {
            "type": "object",
            "properties": {
                "valid_estimates_considered": {"type": "array", "items": {"type": "string"}},
                "rejected_estimates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"agent_name": {"type": "string"}, "reason": {"type": "string"}},
                        "required": ["agent_name", "reason"],
                    },
                },
                "comparison_table": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "agent_name": {"type": "string"},
                            "estimate": {"type": "string"},
                            "reference_class_fit": {"type": "string"},
                            "denominator_clarity": {"type": "string"},
                            "time_horizon_match": {"type": "string"},
                            "source_quality": {"type": "string"},
                            "bias_risks": {"type": "string"},
                        },
                        "required": [
                            "agent_name", "estimate", "reference_class_fit", "denominator_clarity",
                            "time_horizon_match", "source_quality", "bias_risks",
                        ],
                    },
                },
                "final_prior": {"type": "number"},
                "plausible_range": {"type": "string"},
                "confidence": {"type": "string", "enum": ["low", "medium", "high", "LOW", "MEDIUM", "HIGH"]},
                "rationale": {"type": "string"},
                "notes_for_inside_view": {"type": "string"},
                "reference_class_summary": {"type": "string"},
                "denominator_summary": {"type": "string"},
            },
            "required": [
                "valid_estimates_considered", "rejected_estimates", "comparison_table",
                "final_prior", "plausible_range", "confidence", "rationale",
                "notes_for_inside_view", "reference_class_summary", "denominator_summary",
            ],
        },
    }
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


def _event_type_warning(event_type: EventType) -> str:
    if event_type == EventType.RELATIVE_ORDERING:
        return (
            "\n⚠ RELATIVE ORDERING QUESTION: Use pairwise ordering data among comparable pairs. "
            "Do NOT use generic event frequency.\n"
        )
    if event_type == EventType.THRESHOLD:
        return (
            "\n⚠ THRESHOLD QUESTION: Use threshold-crossing frequency over comparable windows. "
            "Do NOT use generic growth statistics.\n"
        )
    if event_type == EventType.ELECTION_SELECTION:
        return (
            "\n⚠ ELECTION/SELECTION QUESTION: Use comparable candidate/entity win rates under similar rules.\n"
        )
    if event_type == EventType.MARKET_PRICE:
        return (
            "\n⚠ MARKET PRICE QUESTION: Use historical distributions of comparable price moves over comparable windows.\n"
        )
    if event_type == EventType.COUNT_FREQUENCY:
        return (
            "\n⚠ COUNT FREQUENCY QUESTION: Use historical count distributions, not a generic event-occurrence rate.\n"
        )
    return ""


def _shared_user_prompt(parsed_question: ParsedQuestion, related_markets: list[dict]) -> str:
    return SHARED_USER_PROMPT.format(
        parsed_question=parsed_question.format_for_prompt(),
        current_year=current_year(),
        event_type_warning=_event_type_warning(parsed_question.event_type),
        related_markets=_format_related_markets(related_markets),
        event_type=parsed_question.event_type.value,
        outside_view_target=parsed_question.outside_view_target,
        time_horizon=parsed_question.time_horizon or "not specified",
        structure=parsed_question.threshold_or_comparison_structure or "not specified",
        search_hints="; ".join(parsed_question.base_rate_search_hints or parsed_question.base_rate_queries) or "derive independently",
    )


def _execute_search_tool(name: str, args: dict, ledger: EvidenceLedger, config: ForecasterConfig) -> dict:
    if name == "web_search":
        query = args["query"]
        result = {"results": web_search(query, args.get("max_results", config.search_max_results))}
        stale_yr = detect_stale_year_in_query(query)
        if stale_yr:
            result["temporal_warning"] = (
                f"Query references {stale_yr} which may be stale. Current year is {current_year()}."
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
            "neutral": "weak",
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
        return {"status": "added", "index": len(ledger.items) - 1, "auto_reliability": auto_reliability}

    return {"status": "received"}


def _run_ov_agent(
    *,
    agent_name: str,
    method_type: str,
    system_prompt: str,
    submit_tool: dict,
    parsed_question: ParsedQuestion,
    related_markets: list[dict],
    config: ForecasterConfig,
) -> OutsideViewEstimate:
    llm = LLMClient(config, client_name=agent_name.lower().replace(" ", "_"))
    ledger = EvidenceLedger()
    messages = [{"role": "user", "content": _shared_user_prompt(parsed_question, related_markets)}]
    tools = SEARCH_TOOLS + [submit_tool]
    submit_input: dict | None = None

    for iteration in range(config.max_ov_iterations):
        if iteration == config.max_ov_iterations - 2:
            messages.append({
                "role": "user",
                "content": "One more search available. Then submit your best outside-view estimate with an explicit denominator or say no valid estimate exists.",
            })

        response = llm.complete(system_prompt, messages, tools)
        if not response.tool_blocks:
            break

        tool_results = []
        submitted = False
        for tb in response.tool_blocks:
            result = _execute_search_tool(tb.name, tb.input, ledger, config)
            tool_results.append({"tool_use_id": tb.id, "content": json.dumps(result)})
            if tb.name == submit_tool["name"]:
                submit_input = tb.input
                submitted = True
        llm.extend_messages(messages, response, tool_results)
        if submitted:
            break

    if submit_input is None:
        ledger.incomplete = True
        messages.append({"role": "user", "content": "Research complete. You must now submit your best outside-view estimate."})
        final = llm.complete(system_prompt, messages, [submit_tool], force_tool=True)
        if not final.tool_blocks:
            raise ValueError(f"{agent_name} failed to submit")
        submit_input = final.tool_blocks[0].input

    reference_class = (
        submit_input.get("searched_reference_class")
        or submit_input.get("strongest_reference_class")
        or submit_input.get("method_used")
        or "not specified"
    )
    denominator = submit_input.get("denominator") or submit_input.get("denominator_or_component_estimates") or ""
    successes = submit_input.get("successes") or ""
    rate = (
        submit_input.get("empirical_rate")
        if "empirical_rate" in submit_input else submit_input.get("empirical_or_computed_rate")
    )
    final_estimate = (
        submit_input.get("final_direct_empirical_estimate")
        if "final_direct_empirical_estimate" in submit_input else
        submit_input.get("strongest_conditional_estimate")
        if "strongest_conditional_estimate" in submit_input else
        submit_input.get("final_analog_decomposed_estimate")
    )
    if final_estimate is None:
        final_estimate = rate

    weaknesses = submit_input.get("key_weaknesses", [])
    validity_flags = []
    if not denominator:
        validity_flags.append("missing_denominator")
    if final_estimate is None:
        validity_flags.append("no_valid_estimate")
    if submit_input.get("no_valid_direct_estimate"):
        validity_flags.append("no_valid_estimate")

    return OutsideViewEstimate(
        agent_name=agent_name,
        method_type=method_type,
        statistical_object=submit_input.get("statistical_object", parsed_question.outside_view_target),
        reference_class=reference_class,
        denominator=denominator,
        successes=successes,
        rate=float(rate) if rate is not None else None,
        plausible_range="",
        time_horizon_match=submit_input.get("time_horizon_match", parsed_question.time_horizon),
        sources=submit_input.get("sources", []),
        weaknesses=weaknesses,
        validity_flags=validity_flags,
        reasoning=submit_input.get("reasoning", ""),
        confidence=_normalize_confidence(submit_input.get("confidence"), default="low"),
        final_estimate=float(final_estimate) if final_estimate is not None else None,
        evidence_ledger=ledger,
    )


def run_outside_view_agent_a(parsed_question: ParsedQuestion, related_markets: list[dict] | None = None, config: ForecasterConfig | None = None) -> OutsideViewEstimate:
    config = config or ForecasterConfig()
    return _run_ov_agent(
        agent_name="Agent A",
        method_type="direct_empirical",
        system_prompt=AGENT_A_SYSTEM_PROMPT,
        submit_tool=SUBMIT_A_TOOL,
        parsed_question=parsed_question,
        related_markets=related_markets or [],
        config=config,
    )


def run_outside_view_agent_b(parsed_question: ParsedQuestion, related_markets: list[dict] | None = None, config: ForecasterConfig | None = None) -> OutsideViewEstimate:
    config = config or ForecasterConfig()
    return _run_ov_agent(
        agent_name="Agent B",
        method_type="conditional_narrow",
        system_prompt=AGENT_B_SYSTEM_PROMPT,
        submit_tool=SUBMIT_B_TOOL,
        parsed_question=parsed_question,
        related_markets=related_markets or [],
        config=config,
    )


def run_outside_view_agent_c(parsed_question: ParsedQuestion, related_markets: list[dict] | None = None, config: ForecasterConfig | None = None) -> OutsideViewEstimate:
    config = config or ForecasterConfig()
    return _run_ov_agent(
        agent_name="Agent C",
        method_type="analog_decomposed",
        system_prompt=AGENT_C_SYSTEM_PROMPT,
        submit_tool=SUBMIT_C_TOOL,
        parsed_question=parsed_question,
        related_markets=related_markets or [],
        config=config,
    )


def _fmt_ov_estimates(estimates: list[OutsideViewEstimate]) -> str:
    lines = []
    for est in estimates:
        lines += [
            f"\n{est.agent_name} ({est.method_type})",
            f"Statistical object: {est.statistical_object}",
            f"Reference class: {est.reference_class}",
            f"Denominator: {est.denominator or 'missing'}",
            f"Successes: {est.successes or 'missing'}",
            f"Rate: {est.rate if est.rate is not None else 'none'}",
            f"Final estimate: {est.final_estimate if est.final_estimate is not None else 'none'}",
            f"Time horizon match: {est.time_horizon_match or 'not specified'}",
            f"Sources: {'; '.join(est.sources) or 'none listed'}",
            f"Weaknesses: {'; '.join(est.weaknesses) or 'none listed'}",
            f"Validity flags: {'; '.join(est.validity_flags) or 'none'}",
            f"Reasoning: {est.reasoning}",
        ]
    return "\n".join(lines)


def reconcile_outside_view(
    parsed_question: ParsedQuestion,
    estimates: list[OutsideViewEstimate],
    config: ForecasterConfig | None = None,
) -> ReconciledOutsideView:
    config = config or ForecasterConfig()
    llm = LLMClient(config, client_name="outside_view_reconciler")
    messages = [{
        "role": "user",
        "content": (
            f"Reconcile outside-view estimates for the following parsed question.\n\n"
            f"{parsed_question.format_for_prompt()}\n\n"
            f"OUTSIDE-VIEW ESTIMATES:\n{_fmt_ov_estimates(estimates)}\n"
        ),
    }]

    response = llm.complete(RECONCILER_SYSTEM_PROMPT, messages, RECONCILER_TOOLS, force_tool=True)
    if not response.tool_blocks:
        raise ValueError("Outside View Reconciler failed to submit")
    inp = response.tool_blocks[0].input

    valid_names = set(inp.get("valid_estimates_considered", []))
    valid_estimates = [est for est in estimates if est.agent_name in valid_names]
    return ReconciledOutsideView(
        final_prior=float(inp["final_prior"]),
        plausible_range=inp.get("plausible_range", ""),
        confidence=_normalize_confidence(inp.get("confidence"), default="low"),
        valid_estimates=valid_estimates,
        rejected_estimates=inp.get("rejected_estimates", []),
        rationale=inp["rationale"],
        notes_for_inside_view=inp.get("notes_for_inside_view", ""),
        statistical_object=parsed_question.outside_view_target,
        reference_class_summary=inp.get("reference_class_summary", ""),
        denominator_summary=inp.get("denominator_summary", ""),
    )
