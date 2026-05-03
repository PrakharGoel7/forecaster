import json
from datetime import datetime, timezone

from forecaster.models import (
    AgentForecast, OutsideViewConsensus, EvidenceItem, EvidenceDirection, SourceType,
    SupervisorReconciliation, ParsedQuestion,
)
from forecaster.config import ForecasterConfig
from forecaster.agents.base import LLMClient
from forecaster.calibration import logit
from forecaster.tools.search import web_search, web_fetch

SYSTEM_PROMPT = """You are the Supervisor in a multi-agent forecasting system. You receive independent probability estimates from inside-view agents and a pre-established outside-view base rate.

YOUR JOB (in order):

STEP 1 — AUDIT THE OUTSIDE VIEW:
Before reconciling inside-view estimates, audit the outside view:
1. Does the reference class match the event type? (e.g. for relative_ordering, did OV agents use pairwise ordering data — not generic frequency?)
2. Is the base rate backed by an explicit denominator or analog set?
3. Was the base rate derived from direct evidence, analogs, decomposition, or a weak prior?
4. Are any inside-view estimates anchored to a flawed base rate?

If the outside view is weak or mismatched:
- Explicitly flag it as low-confidence.
- Reduce its authority in your reconciliation.
- Rely more on robust inside-view evidence with high-reliability sources.
- Widen your uncertainty.

STEP 2 — ASSESS INSIDE-VIEW DISAGREEMENT:
1. Check the log-odds spread. If tight (< 0.15), aggregate directly.
2. If wide, identify the CRUX — what specific factual claim drives divergence? Options:
   - Different base-rate interpretation
   - Different evidence quality assessment
   - Different timeline assumptions
   - Different resolution-rule interpretation
   - Different causal models
3. Run targeted searches to resolve the crux — NOT general research, only the specific disputed fact.

STEP 3 — RECONCILE:
RECONCILIATION PRINCIPLES:
- Do NOT simply average. Think about which agents had better evidence and why.
- Give explicit weighting boost to evidence from: official sources, primary data, reputable news.
- Give explicit weighting penalty to evidence from: blogs, unsourced claims, low-reliability sources.
- If one agent found a key primary-source fact others missed, weight toward that agent.
- If searches resolve the crux, update accordingly.
- If searches cannot resolve the crux, widen uncertainty and move toward the geometric mean.
- Your reconciled estimate must be defensible: state exactly what drove it.

BAD RECONCILIATION TO AVOID:
- Averaging without thinking about evidence quality.
- Ignoring a flawed outside view and anchoring estimates to it anyway.
- Running general research instead of crux-targeted searches.
- Giving a precise number without explaining what drove it.

Call submit_reconciliation when done.
"""

_TOOLS = [
    {
        "name": "web_search",
        "description": "Run a targeted search to resolve a specific disagreement between agents.",
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
        "description": "Fetch a URL to verify a specific claim.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "submit_reconciliation",
        "description": "Submit the reconciled forecast with outside-view audit.",
        "input_schema": {
            "type": "object",
            "properties": {
                "outside_view_audit": {
                    "type": "string",
                    "description": "Your assessment of outside-view quality: did the reference class match the event type? Was the denominator explicit? Rate: solid / weak / possibly_flawed — and explain.",
                },
                "outside_view_authority": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "How much weight you gave the outside view in reconciliation",
                },
                "disagreement_level": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                },
                "crux_of_disagreement": {
                    "type": "string",
                    "description": "The specific factual or interpretive question that drove divergence (null if disagreement was low)",
                },
                "crux_type": {
                    "type": "string",
                    "enum": [
                        "base_rate_interpretation", "evidence_quality",
                        "timeline_assumptions", "resolution_rule", "causal_model", "none",
                    ],
                },
                "targeted_searches_conducted": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "reconciled_probability": {
                    "type": "number",
                    "description": "Reconciled P(YES) as decimal 0.001-0.999",
                },
                "reconciliation_reasoning": {
                    "type": "string",
                    "description": "Explain exactly what drove the reconciled estimate, including source quality weighting",
                },
            },
            "required": [
                "outside_view_audit", "outside_view_authority",
                "disagreement_level", "reconciled_probability",
                "reconciliation_reasoning", "targeted_searches_conducted",
            ],
        },
    },
]


def _fmt_agent_forecasts(forecasts: list[AgentForecast]) -> str:
    lines = []
    for f in forecasts:
        high_rel = sum(1 for item in f.evidence_ledger.items if item.reliability and item.reliability.value == "high")
        low_rel  = sum(1 for item in f.evidence_ledger.items if item.reliability and item.reliability.value == "low")
        lines += [
            f"\n── Agent {f.agent_id} ── P(YES) = {f.probability:.3f}",
            f"Starting base rate: {f.starting_base_rate:.3f}  →  Adjustment: {f.probability - f.starting_base_rate:+.3f}",
            f"Inside view: {f.inside_view_reasoning}",
            f"Key updates: {'; '.join(f.key_updates_from_base) or 'none listed'}",
            f"For: {'; '.join(f.key_factors_for)}",
            f"Against: {'; '.join(f.key_factors_against)}",
            f"Unresolved cruxes: {'; '.join(f.unresolved_cruxes) or 'none'}",
            f"Uncertainty: {f.uncertainty_reasoning}",
            f"Confidence: {f.epistemic_confidence}",
            f"Evidence quality: {high_rel} high-reliability, {low_rel} low-reliability items",
            f"{f.evidence_ledger.format_for_prompt()}",
        ]
    return "\n".join(lines)


def run_supervisor(
    parsed_question: ParsedQuestion,
    agent_forecasts: list[AgentForecast],
    ov_consensus: OutsideViewConsensus,
    config: ForecasterConfig | None = None,
) -> SupervisorReconciliation:
    if config is None:
        config = ForecasterConfig()

    llm = LLMClient(config)
    raw_probs = [f.probability for f in agent_forecasts]

    log_odds = [logit(p) for p in raw_probs]
    spread = max(log_odds) - min(log_odds)

    user_message = (
        f"QUESTION:\n{parsed_question.format_for_prompt()}\n\n"
        f"OUTSIDE VIEW CONSENSUS:\n"
        f"  Base rate: {ov_consensus.base_rate:.3f} ({ov_consensus.base_rate * 100:.0f}%)\n"
        f"  Statistical object: {ov_consensus.statistical_object or 'not specified'}\n"
        f"  Reference class: {ov_consensus.reference_class}\n"
        f"  Denominator / basis: {ov_consensus.denominator_or_basis or 'not provided'}\n"
        f"  Limitations: {ov_consensus.reference_class_limitations or 'none noted'}\n"
        f"  Reasoning: {ov_consensus.reasoning}\n\n"
        f"INSIDE VIEW AGENT FORECASTS (log-odds spread = {spread:.3f}):\n"
        f"{_fmt_agent_forecasts(agent_forecasts)}\n\n"
        f"BEGIN WITH THE OUTSIDE VIEW AUDIT (Step 1), then assess disagreement (Step 2), "
        f"then reconcile (Step 3). "
        f"{'Spread is wide — identify the crux and run targeted searches.' if spread >= config.supervisor_search_threshold else 'Spread is tight — aggregate with brief reasoning.'}"
        " Call submit_reconciliation when done."
    )

    messages = [{"role": "user", "content": user_message}]
    reconciliation_input: dict | None = None

    for _ in range(5):
        response = llm.complete(SYSTEM_PROMPT, messages, _TOOLS)

        if not response.tool_blocks:
            break

        tool_results = []
        submitted = False

        for tb in response.tool_blocks:
            if tb.name == "web_search":
                content = json.dumps({"results": web_search(tb.input["query"], tb.input.get("max_results", 5))})
            elif tb.name == "web_fetch":
                content = json.dumps(web_fetch(tb.input["url"], config.fetch_max_chars))
            elif tb.name == "submit_reconciliation":
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
        from forecaster.calibration import ensemble_average
        fallback_prob = ensemble_average(raw_probs)
        return SupervisorReconciliation(
            raw_probabilities=raw_probs,
            disagreement_level="low",
            reconciled_probability=fallback_prob,
            reconciliation_reasoning="Supervisor did not complete; defaulting to geometric mean.",
            targeted_searches_conducted=[],
            outside_view_audit="Supervisor did not complete audit.",
        )

    return SupervisorReconciliation(
        raw_probabilities=raw_probs,
        disagreement_level=reconciliation_input["disagreement_level"],
        crux_of_disagreement=reconciliation_input.get("crux_of_disagreement"),
        targeted_searches_conducted=reconciliation_input.get("targeted_searches_conducted", []),
        reconciled_probability=float(reconciliation_input["reconciled_probability"]),
        reconciliation_reasoning=reconciliation_input["reconciliation_reasoning"],
        outside_view_audit=reconciliation_input.get("outside_view_audit", ""),
    )
