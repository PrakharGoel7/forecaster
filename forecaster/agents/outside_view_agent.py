import json
from datetime import datetime, timezone

from forecaster.models import (
    OutsideViewForecast, EvidenceItem, EvidenceLedger,
    SourceType, EvidenceDirection, EvidenceMagnitude, Reliability, EvidenceAge,
    ParsedQuestion, EventType,
)
from forecaster.config import ForecasterConfig
from forecaster.agents.base import LLMClient
from forecaster.tools.search import web_search, web_fetch
from forecaster.utils.temporal import (
    score_source_reliability, estimate_evidence_age, detect_stale_year_in_query, current_year,
)

SYSTEM_PROMPT = """You are an Outside View forecasting agent. Your sole job is to estimate the historical base rate for the statistical object defined by the parser.

DO NOT research the current specific situation.
DO NOT use recent news about the target entities as evidence.
DO NOT produce a probability unless you can explain the denominator.

Your job:
1. Identify the correct statistical object from the parsed question.
2. Find empirical base-rate data or construct an analog set.
3. Estimate how often comparable cases resolved YES.
4. Report uncertainty from reference-class fit and sample size.

CRITICAL RULES:
- relative_ordering questions: do NOT research generic event frequency. You need pairwise ordering among comparable cases.
- threshold questions: do NOT research generic growth. You need historical threshold-crossing frequency.
- election/selection questions: do NOT research generic popularity. You need comparable candidates under comparable rules.
- Generic statistics are context only — not the base rate — unless they directly match the statistical object.
- Every base rate MUST have a denominator: "X successes out of N comparable cases" or a clearly described empirical frequency.
- If no good empirical base rate exists, say so and use an explicit fallback prior with LOW confidence.

SEARCH STRATEGY:
- Search for direct base-rate studies and statistics first.
- If unavailable, search for analog cases to hand-construct a rough success rate.
- Prefer: official data, academic papers, government data, exchanges, reputable financial/news sources.
- Avoid: SEO blogs, generic explainers, speculative articles.
- Cross-check with at least two credible sources.

FALLBACK HIERARCHY (use the strongest available):
A. Direct empirical base rate: same event type, same domain, comparable deadline.
B. Analog case set: 5-30 comparable historical cases, compute rough success rate.
C. Decomposed base rate: break into components with independent estimates.
D. Market-implied outside view: broad market prices for comparable (not target) questions.
E. Weak prior: conservative estimate, mark confidence LOW.

SELF-CHECK before submitting:
1. Does my reference class answer the exact statistical object?
2. Am I accidentally using category frequency instead of event probability?
3. Is my denominator explicit?
4. Is the time horizon comparable?
5. Are my sources credible?

BAD REASONING TO AVOID:
- Using generic category frequency when the question is about relative ordering.
- Treating "many X events happen" as evidence this specific X happens.
- Confusing possibility with probability.
- Moving toward 50% because evidence is uncertain.
- Giving a precise number without a clear basis.
- Treating unsourced speculation as fact.
- Ignoring deadline length.
- Searching stale years when current data is needed.
"""

_TOOLS = [
    {
        "name": "web_search",
        "description": "Search for historical base-rate data and reference-class statistics.",
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
        "description": "Fetch a URL to retrieve base-rate data or historical statistics.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "add_evidence",
        "description": "Record a base-rate or contextual data point in the ledger.",
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
                    "description": "base_rate for empirical frequency data; context for background only",
                },
                "magnitude": {
                    "type": "string",
                    "enum": ["strong", "moderate", "weak"],
                    "description": "How strong is this piece of evidence",
                },
                "date_published": {
                    "type": "string",
                    "description": "Publication date YYYY-MM-DD or YYYY-MM (leave blank if unknown)",
                },
                "why_it_matters": {"type": "string"},
                "limitations": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["claim", "source_url", "source_title", "source_type",
                         "relevant_quote_or_snippet", "direction", "magnitude",
                         "why_it_matters", "limitations"],
        },
    },
    {
        "name": "submit_outside_view",
        "description": "Submit your base-rate estimate. Will be validated — missing denominator or statistical object will be rejected.",
        "input_schema": {
            "type": "object",
            "properties": {
                "base_rate": {
                    "type": "number",
                    "description": "Historical base rate P(YES) as decimal 0.001-0.999",
                },
                "statistical_object": {
                    "type": "string",
                    "description": "The exact statistical quantity being estimated, e.g. 'probability that tech unicorn A IPOs before unicorn B among comparable pairs'",
                },
                "reference_class": {
                    "type": "string",
                    "description": "The reference class used",
                },
                "denominator_or_basis": {
                    "type": "string",
                    "description": "REQUIRED: explicit denominator or empirical basis, e.g. '8 out of 23 comparable cases' or 'Fed has cut rates in 4 of 7 comparable pauses'",
                },
                "analog_cases_or_data": {
                    "type": "string",
                    "description": "Specific historical cases or datasets used. If none, document which fallback (A/B/C/D/E) and why no better data exists.",
                },
                "reference_class_limitations": {
                    "type": "string",
                    "description": "Key limitations: sample size, comparability of cases, time-period differences",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Full reasoning connecting evidence to base rate",
                },
                "confidence": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "How well-supported is this base rate. HIGH requires strong empirical backing.",
                },
            },
            "required": [
                "base_rate", "statistical_object", "reference_class",
                "denominator_or_basis", "analog_cases_or_data",
                "reference_class_limitations", "reasoning", "confidence",
            ],
        },
    },
]


def _validate_outside_view(args: dict) -> list[str]:
    errors = []
    if not args.get("denominator_or_basis", "").strip():
        errors.append(
            "VALIDATION ERROR: denominator_or_basis is required. "
            "You must state the empirical basis explicitly: e.g. '8 out of 23 comparable cases' "
            "or 'historical rate of ~35% from Fed data 1990-2024'. Do not submit without this."
        )
    if not args.get("statistical_object", "").strip():
        errors.append(
            "VALIDATION ERROR: statistical_object is required. "
            "Define the exact quantity you are estimating."
        )
    analog = args.get("analog_cases_or_data", "").strip()
    if not analog:
        errors.append(
            "VALIDATION ERROR: analog_cases_or_data is required. "
            "Either provide specific historical cases/datasets, or document which fallback method "
            "(A=direct, B=analog set, C=decomposed, D=market-implied, E=weak prior) you used and why."
        )
    confidence = args.get("confidence", "medium")
    reasoning = args.get("reasoning", "")
    if confidence == "high" and len(reasoning) < 120:
        errors.append(
            "VALIDATION ERROR: Confidence is HIGH but reasoning is too brief. "
            "HIGH confidence requires substantial empirical backing — expand your reasoning."
        )
    return errors


def run_outside_view_agent(
    parsed_question: ParsedQuestion,
    agent_id: int,
    config: ForecasterConfig | None = None,
) -> OutsideViewForecast:
    if config is None:
        config = ForecasterConfig()

    llm = LLMClient(config)
    ledger = EvidenceLedger()

    event_type = parsed_question.event_type
    event_type_warning = ""
    if event_type == EventType.RELATIVE_ORDERING:
        event_type_warning = (
            "\n⚠ RELATIVE ORDERING QUESTION: You need PAIRWISE ORDERING data — "
            "how often does one entity in a comparable pair happen before the other. "
            "Do NOT use generic event frequency, total counts, or category statistics. "
            "Search for historical examples of comparable rival pairs and which went first.\n"
        )
    elif event_type == EventType.THRESHOLD:
        event_type_warning = (
            "\n⚠ THRESHOLD QUESTION: You need THRESHOLD CROSSING FREQUENCY data — "
            "how often does a comparable metric exceed/fall below a comparable value "
            "within a comparable timeframe. Do not use generic growth statistics.\n"
        )
    elif event_type == EventType.ELECTION_SELECTION:
        event_type_warning = (
            "\n⚠ ELECTION/SELECTION QUESTION: You need COMPARABLE CANDIDATE base rates — "
            "how often do candidates/entities in comparable positions win under comparable rules. "
            "Do not use generic popularity or name-recognition statistics.\n"
        )

    user_message = (
        f"Establish the historical base rate for the following question.\n\n"
        f"{parsed_question.format_for_prompt()}\n\n"
        f"Current year: {current_year()}{event_type_warning}\n"
        f"YOUR TASK:\n"
        f"  EVENT TYPE: {event_type.value}\n"
        f"  STATISTICAL OBJECT TO ESTIMATE: {parsed_question.outside_view_target or 'see reference class'}\n"
        f"  SELECTED REFERENCE CLASS: {parsed_question.selected_reference_class or 'see above'}\n"
        f"  SUGGESTED BASE RATE QUERIES: {'; '.join(parsed_question.base_rate_queries) or 'derive from reference class'}\n\n"
        "Search ONLY for historical base-rate data matching the statistical object above. "
        "Do not look up the current state of the specific situation. "
        "Add base-rate data points to the ledger as you go. "
        "Call submit_outside_view when you have a grounded estimate. "
        "Remember: every base rate needs an explicit denominator."
    )

    messages = [{"role": "user", "content": user_message}]
    submit_input: dict | None = None

    _SUBMIT_ONLY = [_TOOLS[-1]]

    for iteration in range(config.max_ov_iterations):
        if iteration == config.max_ov_iterations - 2:
            messages.append({
                "role": "user",
                "content": (
                    "One more search available. Then call submit_outside_view. "
                    "Ensure you have an explicit denominator and statistical object."
                ),
            })

        response = llm.complete(SYSTEM_PROMPT, messages, _TOOLS)

        if not response.tool_blocks:
            break

        tool_results = []
        submitted = False

        for tb in response.tool_blocks:
            result = _execute_tool(tb.name, tb.input, ledger, config)

            if tb.name == "submit_outside_view":
                validation_errors = _validate_outside_view(tb.input)
                if validation_errors and iteration < config.max_ov_iterations - 1:
                    # Feed errors back — agent gets another chance
                    result = {
                        "status": "rejected",
                        "errors": validation_errors,
                        "message": "Fix the issues above and resubmit.",
                    }
                else:
                    submit_input = tb.input
                    submitted = True

            tool_results.append({"tool_use_id": tb.id, "content": json.dumps(result)})

        llm.extend_messages(messages, response, tool_results)

        if submitted:
            break

    if submit_input is None:
        ledger.incomplete = True
        messages.append({
            "role": "user",
            "content": (
                "Research complete. You must now call submit_outside_view. "
                "Provide your best estimate with whatever denominator you can establish."
            ),
        })
        final = llm.complete(SYSTEM_PROMPT, messages, _SUBMIT_ONLY, force_tool=True)
        if final.tool_blocks:
            submit_input = final.tool_blocks[0].input
        else:
            raise ValueError(f"Outside View Agent {agent_id} failed to submit")

    return OutsideViewForecast(
        agent_id=agent_id,
        base_rate=float(submit_input["base_rate"]),
        statistical_object=submit_input.get("statistical_object", ""),
        reference_class=submit_input["reference_class"],
        denominator_or_basis=submit_input.get("denominator_or_basis", ""),
        analog_cases_or_data=submit_input.get("analog_cases_or_data", ""),
        reference_class_limitations=submit_input.get("reference_class_limitations", ""),
        reasoning=submit_input["reasoning"],
        confidence=submit_input["confidence"],
        evidence_ledger=ledger,
    )


def _execute_tool(name: str, args: dict, ledger: EvidenceLedger, config: ForecasterConfig) -> dict:
    if name == "web_search":
        query = args["query"]
        result = {"results": web_search(query, args.get("max_results", config.search_max_results))}
        stale_yr = detect_stale_year_in_query(query)
        if stale_yr:
            result["temporal_warning"] = (
                f"Query references {stale_yr} which may be stale. "
                f"Current year is {current_year()}. Consider updating query to use recent years."
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
        return {
            "status": "added",
            "index": len(ledger.items) - 1,
            "auto_reliability": auto_reliability,
        }

    if name == "submit_outside_view":
        return {"status": "received"}

    return {"error": f"Unknown tool: {name}"}
