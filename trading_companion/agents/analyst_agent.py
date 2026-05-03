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

Given a user's belief about the future, you will systematically analyze its ramifications across every major domain. For EACH domain, reason through:
1. Is this belief relevant to this domain? (yes/no/maybe)
2. If relevant: what is the exact causal mechanism?
3. What specific, observable outcomes in this domain would prediction markets capture?

Domains to analyze:
{chr(10).join(f"- {d}" for d in DOMAINS)}

Be rigorous. A belief about Iran war doesn't just affect geopolitics — it affects:
- Oil prices (Strait of Hormuz risk)
- Inflation and Fed policy (oil-driven CPI)
- Defense budgets and legislation
- Airline costs and consumer spending
- Currency markets (USD safe-haven, Iranian rial)
- Crypto (risk-off sentiment)
- Israeli and Saudi political decisions

Go beyond the obvious. Third-order effects matter — they're where the market is underpriced."""

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
                        },
                        "required": ["domain", "relevance", "mechanism", "market_signals"],
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
        """Render the domain analysis as concise text for the screener prompt."""
        lines = ["Domain impact map:"]
        for d in analysis["affected_domains"]:
            if d["relevance"] == "low":
                continue
            signals = ", ".join(d["market_signals"][:3])
            lines.append(f"  [{d['relevance'].upper()}] {d['domain']}: {d['mechanism']} → look for: {signals}")
        if analysis.get("most_surprising_connection"):
            lines.append(f"\nKey non-obvious bet: {analysis['most_surprising_connection']}")
        return "\n".join(lines)
