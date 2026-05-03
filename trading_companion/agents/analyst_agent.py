"""Agent 2 — Belief Analyst.

Takes the belief summary and reasons deeply about its ramifications across
every major domain. Produces a structured impact map that feeds into the
ScreenerAgent, enabling it to find indirect and second/third-order markets
it would otherwise miss.
"""
from __future__ import annotations
import json
import os

from openai import OpenAI

DOMAINS = [
    "Energy & Commodities (oil, gas, metals, agriculture)",
    "Financial Markets (equities, indices, volatility)",
    "Currencies & Forex",
    "Fixed Income & Monetary Policy (central banks, interest rates, inflation)",
    "Geopolitics & International Relations",
    "US Domestic Politics & Legislation",
    "Defense & Military",
    "Trade, Tariffs & Supply Chains",
    "Technology & Innovation (AI, semiconductors, space)",
    "Healthcare & Pharmaceuticals",
    "Labor Markets & Employment",
    "Real Estate & Housing",
    "Crypto & Digital Assets",
    "Climate, Energy Transition & Environment",
    "Consumer & Retail",
    "Media, Social & Cultural",
]

SYSTEM_PROMPT = f"""You are a macro analyst specializing in second and third-order thinking.

Given a user's belief about the future, systematically analyze its ramifications across every major domain. For EACH domain, reason through:
1. Is this belief directly relevant, indirectly relevant, or not relevant?
2. If relevant: what is the exact causal mechanism?
3. What specific, observable outcomes would prediction markets capture?
4. Score the domain for market search utility.

Domains to analyze:
{chr(10).join(f"- {d}" for d in DOMAINS)}

SCORING GUIDE — assess each domain on four dimensions:

causal_distance — how directly does the belief cause effects here?
  direct: the belief IS about this domain
  precursor: the belief is a necessary precondition that directly enables effects here
  first_order: the belief causes an immediate, well-established effect here
  second_order: requires one additional causal step to reach this domain
  speculative: connection is plausible but weak or uncertain

expressiveness_score (1–5) — how well would a prediction market in this domain express the user's thesis?
  5 = a market here directly resolves the belief
  3 = a market here is a meaningful proxy
  1 = only tangentially related

causal_purity_score (1–5) — is the belief a primary driver of this domain, or one minor factor among many?
  5 = the belief dominates outcomes here
  3 = the belief is a meaningful contributor
  1 = the belief is a marginal factor

timeframe_alignment_score (1–5) — do typical market resolutions in this domain align with the user's timeframe?
  5 = most relevant markets resolve within the stated timeframe
  3 = partial alignment
  1 = markets resolve much earlier or later

keep_for_market_search — set true only when ALL THREE hold:
  - expressiveness_score >= 3 (markets here meaningfully express the thesis)
  - causal_purity_score >= 3 (the belief is a significant driver, not background noise)
  - causal_distance is direct, precursor, or first_order (OR second_order with expressiveness >= 4)

Be rigorous. A belief about an Iran-Israel war doesn't just affect geopolitics — trace the causal chains:
- Oil (Strait of Hormuz risk premium) → first_order
- Inflation and Fed policy (oil-driven CPI) → second_order, but high expressiveness if timely
- Defense budgets → first_order
- Airline costs → second_order
- Crypto risk-off → second_order, low causal_purity (many other drivers)

Only set keep_for_market_search=true on domains where prediction markets would give clean exposure to the belief."""

_ANALYZE_TOOL = {
    "type": "function",
    "function": {
        "name": "analyze_belief",
        "description": "Produce a structured domain-by-domain impact map of the belief.",
        "parameters": {
            "type": "object",
            "properties": {
                "affected_domains": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "domain": {"type": "string"},
                            "relevance": {
                                "type": "string",
                                "enum": ["high", "medium", "low"],
                            },
                            "mechanism": {
                                "type": "string",
                                "description": "The causal chain from the belief to this domain.",
                            },
                            "market_signals": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Specific observable outcomes prediction markets would capture (e.g. 'oil above $90', 'Fed holds in June', 'defense bill passes').",
                            },
                            "causal_distance": {
                                "type": "string",
                                "enum": ["direct", "precursor", "first_order", "second_order", "speculative"],
                                "description": "How directly does the belief cause effects in this domain.",
                            },
                            "expressiveness_score": {
                                "type": "integer",
                                "description": "1–5: how well would a market in this domain express the user's thesis.",
                            },
                            "causal_purity_score": {
                                "type": "integer",
                                "description": "1–5: is the belief a primary driver here, or one minor factor among many.",
                            },
                            "timeframe_alignment_score": {
                                "type": "integer",
                                "description": "1–5: do likely market resolutions align with the user's timeframe.",
                            },
                            "keep_for_market_search": {
                                "type": "boolean",
                                "description": "True only if this domain gives meaningful tradable exposure to the belief.",
                            },
                        },
                        "required": ["domain", "relevance", "mechanism", "market_signals",
                                     "causal_distance", "expressiveness_score", "causal_purity_score",
                                     "timeframe_alignment_score", "keep_for_market_search"],
                    },
                    "description": "Analysis for every domain — include all domains, even low-relevance ones.",
                },
                "most_surprising_connection": {
                    "type": "string",
                    "description": "The most non-obvious third-order effect worth betting on.",
                },
            },
            "required": ["affected_domains", "most_surprising_connection"],
        },
    },
}


class AnalystAgent:
    def __init__(self, api_key: str | None = None, model: str = "openai/gpt-4o"):
        self._client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key or os.environ["OPENROUTER_API_KEY"],
        )
        self._model = model

    def run(self, belief_summary: dict) -> dict:
        prompt = (
            f"Core belief: {belief_summary['core_belief']}\n"
            f"Time horizon: {belief_summary['time_horizon']}\n"
            f"Key drivers: {', '.join(belief_summary['key_drivers'])}\n"
            f"Scope: {belief_summary['scope']}\n"
            f"User's reasoning: {belief_summary['supporting_reasoning']}\n"
            f"Current context: {belief_summary.get('current_context', '')}"
        )

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            tools=[_ANALYZE_TOOL],
            tool_choice={"type": "function", "function": {"name": "analyze_belief"}},
            max_tokens=2048,
        )

        tc = response.choices[0].message.tool_calls[0]
        return json.loads(tc.function.arguments)

    def format_for_screener(self, analysis: dict) -> str:
        """Render the domain analysis as structured text for the screener prompt."""
        lines = ["Domain impact map (keep_for_market_search=True only):"]
        kept = [d for d in analysis["affected_domains"] if d.get("keep_for_market_search")]
        for d in kept:
            signals = ", ".join(d["market_signals"][:3])
            lines.append(
                f"  [{d.get('causal_distance','?').upper()}] {d['domain']}"
                f" | expr={d.get('expressiveness_score','?')}"
                f" purity={d.get('causal_purity_score','?')}"
                f" time={d.get('timeframe_alignment_score','?')}"
                f": {d['mechanism']} → signals: {signals}"
            )
        if analysis.get("most_surprising_connection"):
            lines.append(f"\nKey non-obvious angle: {analysis['most_surprising_connection']}")
        return "\n".join(lines)
