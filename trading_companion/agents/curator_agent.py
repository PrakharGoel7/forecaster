"""Agent 3 — Market Curator.

Takes the full set of Kalshi markets returned from keyword searches and
shortlists the 5-8 most relevant, interesting, and varied bets given the
user's belief.
"""
from __future__ import annotations
import json
import os
from openai import OpenAI

SYSTEM_PROMPT = """You are a prediction market curator helping a user find the best markets to bet on given their belief about the future.

You will receive:
1. The user's belief (structured)
2. A list of available Kalshi markets with their current prices

Your task: select 5-8 markets that together give the user the best portfolio of bets to express their belief. Optimise for:

- RELEVANCE: Does the market directly or indirectly test the user's belief?
- VARIETY: Don't pick 5 versions of the same market — cover different dimensions of the belief
- CONVICTION MATCH: If the user has high confidence, find markets with prices that don't yet reflect their view (best value)
- DIRECTION: For each market, state whether betting YES or NO aligns with the belief

For tickers you choose that don't appear in the market list, skip them. Only recommend markets from the provided list."""

_CURATE_TOOL = {
    "type": "function",
    "function": {
        "name": "curate_markets",
        "description": "Select the best 5-8 prediction markets for the user's belief.",
        "parameters": {
            "type": "object",
            "properties": {
                "recommendations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ticker": {
                                "type": "string",
                                "description": "Exact ticker from the provided market list.",
                            },
                            "relevance_score": {
                                "type": "integer",
                                "description": "Relevance to the belief, 1-10.",
                            },
                            "relevance_explanation": {
                                "type": "string",
                                "description": "Why this market is a good expression of the user's belief.",
                            },
                            "betting_direction": {
                                "type": "string",
                                "enum": ["YES", "NO"],
                                "description": "Which side aligns with the user's belief.",
                            },
                            "betting_rationale": {
                                "type": "string",
                                "description": "Concise explanation of why this direction and why the price is interesting.",
                            },
                        },
                        "required": [
                            "ticker", "relevance_score", "relevance_explanation",
                            "betting_direction", "betting_rationale",
                        ],
                    },
                    "description": "5-8 recommended markets sorted by relevance_score descending.",
                },
            },
            "required": ["recommendations"],
        },
    },
}


class CuratorAgent:
    def __init__(self, api_key: str | None = None, model: str = "openai/gpt-4o"):
        self._client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key or os.environ["OPENROUTER_API_KEY"],
        )
        self._model = model

    def run(self, belief_summary: dict, markets: list, analysis: dict | None = None) -> list[dict]:
        # Cap to 80 markets to stay within token budget; prefer higher-volume ones
        top_markets = sorted(markets, key=lambda m: m.volume, reverse=True)[:80]

        market_lines = "\n".join(
            f"[{m.ticker}] {m.question} | YES price: {m.mid_price:.0%} | Closes: {m.close_date}"
            for m in top_markets
        )

        domain_text = ""
        if analysis:
            high_med = [d for d in analysis["affected_domains"] if d["relevance"] in ("high", "medium")]
            domain_lines = [f"  - {d['domain']}: {d['mechanism']}" for d in high_med]
            domain_text = "\nDomain impact map (use this to explain indirect connections):\n" + "\n".join(domain_lines)
            if analysis.get("most_surprising_connection"):
                domain_text += f"\nKey non-obvious angle: {analysis['most_surprising_connection']}"

        prompt = (
            f"User's belief: {belief_summary['core_belief']}\n"
            f"Time horizon: {belief_summary['time_horizon']}\n"
            f"Key drivers: {', '.join(belief_summary.get('key_drivers', []))}\n"
            f"Scope: {belief_summary.get('scope', '')}\n"
            f"User confidence: {belief_summary['confidence_level']}"
            f"{domain_text}\n\n"
            f"Available markets ({len(top_markets)} shown):\n{market_lines}"
        )

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            tools=[_CURATE_TOOL],
            tool_choice={"type": "function", "function": {"name": "curate_markets"}},
            max_tokens=2048,
        )

        tc = response.choices[0].message.tool_calls[0]
        result = json.loads(tc.function.arguments)

        market_map = {m.ticker: m for m in markets}
        enriched = []
        for rec in result["recommendations"]:
            m = market_map.get(rec["ticker"])
            if m is None:
                continue
            enriched.append({
                "ticker": m.ticker,
                "event_ticker": m.event_ticker,
                "question": m.question,
                "price": m.mid_price,
                "close_date": m.close_date,
                "rules_summary": m.rules_summary,
                "relevance": rec["relevance_explanation"],
                "direction": rec["betting_direction"],
                "rationale": rec["betting_rationale"],
                "score": rec["relevance_score"],
            })

        return sorted(enriched, key=lambda x: x["score"], reverse=True)
