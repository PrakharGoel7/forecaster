import json
from datetime import datetime, timezone

from forecaster.models import (
    AgentForecast, EvidenceItem, EvidenceDirection, SourceType,
    SupervisorReconciliation, ParsedQuestion,
)
from forecaster.config import ForecasterConfig
from forecaster.agents.base import LLMClient
from forecaster.calibration import logit
from forecaster.tools.search import web_search, web_fetch

SYSTEM_PROMPT = """You are the Supervisor in a multi-agent forecasting system. You receive N independent probability estimates from agents who searched and reasoned independently.

YOUR JOB:
1. Assess the spread of estimates. If tight (spread < 0.15 in log-odds), aggregate directly.
2. If spread is wide, identify the CRUX: what specific factual claim or information gap drives the divergence?
3. Run targeted searches to resolve the crux — not general searches, but searches aimed at the specific disputed fact.
4. Produce a reconciled probability that reflects what the targeted searches revealed.

RECONCILIATION PRINCIPLES:
- Do NOT simply average. Think about which agents had better evidence and why.
- If one agent found a key piece of evidence others missed, weight toward that agent's reasoning.
- If searches resolve the crux in one direction, update accordingly.
- If searches cannot resolve the crux, widen your uncertainty and move toward the geometric mean.
- Your reconciled estimate should be defensible: explain exactly what drove it.

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
        "description": "Fetch a URL to verify or expand on a specific claim.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "submit_reconciliation",
        "description": "Submit the reconciled forecast.",
        "input_schema": {
            "type": "object",
            "properties": {
                "disagreement_level": {
                    "type": "string", "enum": ["low", "medium", "high"],
                    "description": "How much agents disagreed",
                },
                "crux_of_disagreement": {
                    "type": "string",
                    "description": "The specific factual question that drove divergence (null if disagreement was low)",
                },
                "targeted_searches_conducted": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Queries you searched to resolve the crux",
                },
                "reconciled_probability": {
                    "type": "number",
                    "description": "Your reconciled P(YES) as a decimal between 0.001 and 0.999",
                },
                "reconciliation_reasoning": {
                    "type": "string",
                    "description": "Explain exactly what drove your reconciled estimate",
                },
            },
            "required": [
                "disagreement_level", "reconciled_probability", "reconciliation_reasoning",
                "targeted_searches_conducted",
            ],
        },
    },
]


def _fmt_agent_forecasts(forecasts: list[AgentForecast]) -> str:
    lines = []
    for f in forecasts:
        lines += [
            f"\n── Agent {f.agent_id} ── P(YES) = {f.probability:.3f}",
            f"Outside view: {f.outside_view_reasoning}",
            f"Inside view: {f.inside_view_reasoning}",
            f"For: {'; '.join(f.key_factors_for)}",
            f"Against: {'; '.join(f.key_factors_against)}",
            f"Uncertainty: {f.uncertainty_reasoning}",
            f"Confidence: {f.epistemic_confidence}",
            f"{f.evidence_ledger.format_for_prompt()}",
        ]
    return "\n".join(lines)


def run_supervisor(
    parsed_question: ParsedQuestion,
    agent_forecasts: list[AgentForecast],
    config: ForecasterConfig | None = None,
) -> SupervisorReconciliation:
    if config is None:
        config = ForecasterConfig()

    llm = LLMClient(config)
    raw_probs = [f.probability for f in agent_forecasts]

    # Compute log-odds spread to determine how much reconciliation is needed
    log_odds = [logit(p) for p in raw_probs]
    spread = max(log_odds) - min(log_odds)

    user_message = (
        f"QUESTION:\n{parsed_question.format_for_prompt()}\n\n"
        f"AGENT FORECASTS (log-odds spread = {spread:.3f}):\n"
        f"{_fmt_agent_forecasts(agent_forecasts)}\n\n"
        f"Reconcile these forecasts. "
        f"{'Spread is wide — identify the crux and run targeted searches.' if spread >= config.supervisor_search_threshold else 'Spread is tight — aggregate directly with brief reasoning.'}"
        " Call submit_reconciliation when done."
    )

    messages = [{"role": "user", "content": user_message}]
    reconciliation_input: dict | None = None
    additional_evidence: list[EvidenceItem] = []

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
        # Fallback: geometric mean
        from forecaster.calibration import ensemble_average
        fallback_prob = ensemble_average(raw_probs)
        return SupervisorReconciliation(
            raw_probabilities=raw_probs,
            disagreement_level="low",
            reconciled_probability=fallback_prob,
            reconciliation_reasoning="Supervisor did not complete; defaulting to geometric mean of agent estimates.",
            targeted_searches_conducted=[],
        )

    return SupervisorReconciliation(
        raw_probabilities=raw_probs,
        disagreement_level=reconciliation_input["disagreement_level"],
        crux_of_disagreement=reconciliation_input.get("crux_of_disagreement"),
        targeted_searches_conducted=reconciliation_input.get("targeted_searches_conducted", []),
        reconciled_probability=float(reconciliation_input["reconciled_probability"]),
        reconciliation_reasoning=reconciliation_input["reconciliation_reasoning"],
        additional_evidence=additional_evidence,
    )
