"""Agent 3 — Market Curator.

Takes the full set of Kalshi markets returned from keyword searches and
shortlists the 5-8 most relevant, interesting, and varied bets given the
user's belief.
"""
from __future__ import annotations
import json
import os
from openai import OpenAI

SYSTEM_PROMPT = """You are a prediction market curator. The user has a belief about the future, and your job is to recommend a small portfolio of markets that best expresses that belief.

Optimize for:
1. Expressiveness: the market captures the user's thesis or stated mechanism
2. Causal purity: the market is not mostly driven by unrelated factors
3. Time alignment: the market resolves within or near the user's timeframe
4. Variety: the portfolio covers direct_thesis, mechanism, first_order_consequence, and hedge_or_falsifier where useful
5. Price/value: mention price only after relevance is established

For each recommendation:
- State the tier (from the market listing)
- State betting direction (YES or NO)
- Explain expressiveness, causal purity, and time alignment briefly
- Explain why this belongs in the portfolio (not just why it's related)
- Name the main risk or confounder

Rules:
- Recommend 5–8 markets total.
- At least 3 must be direct_thesis or mechanism if available.
- Do not recommend markets that are merely adjacent to the belief.
- Do not recommend broad macro markets unless the causal link is clear and tight.
- If no good direct markets exist, explicitly say the portfolio uses proxy markets.
- Include at most 2 first_order_consequence markets.
- Include at most 1 hedge_or_falsifier unless the user specifically asked for hedges.
- Include at most 1 market per event (event_ticker). If multiple contracts from the same event qualify, pick the single best one."""

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
                            "ticker": {"type": "string"},
                            "tier": {
                                "type": "string",
                                "enum": ["direct_thesis", "mechanism",
                                         "first_order_consequence", "hedge_or_falsifier"],
                            },
                            "betting_direction": {"type": "string", "enum": ["YES", "NO"]},
                            "relevance_score": {
                                "type": "integer",
                                "description": "Overall fit for the portfolio, 1–10.",
                            },
                            "expressiveness_score": {
                                "type": "integer",
                                "description": "1–5: how directly does this market express the thesis.",
                            },
                            "causal_purity_score": {
                                "type": "integer",
                                "description": "1–5: is the belief the primary driver of this market.",
                            },
                            "timeframe_alignment_score": {
                                "type": "integer",
                                "description": "1–5: does the market resolve within the user's timeframe.",
                            },
                            "rationale": {
                                "type": "string",
                                "description": "Why this market expresses or tests the belief.",
                            },
                            "why_this_belongs_in_portfolio": {
                                "type": "string",
                                "description": "What role this market plays in the portfolio (not just relevance).",
                            },
                            "main_risk_or_confounder": {
                                "type": "string",
                                "description": "The biggest reason this market might move independent of the belief.",
                            },
                        },
                        "required": [
                            "ticker", "tier", "betting_direction", "relevance_score",
                            "expressiveness_score", "causal_purity_score",
                            "timeframe_alignment_score", "rationale",
                            "why_this_belongs_in_portfolio", "main_risk_or_confounder",
                        ],
                    },
                    "description": "5–8 recommended markets sorted by relevance_score descending.",
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

    def run(self, belief_summary: dict, markets: list, analysis: dict | None = None,
            screener_candidates: list | None = None) -> list[dict]:
        # Build tier lookup from screener candidates
        candidate_map: dict = {}
        if screener_candidates:
            for c in screener_candidates:
                candidate_map[c["event_ticker"]] = c

        # Markets are pre-sorted by main.py; just cap count
        top_markets = markets[:60]

        market_lines = "\n".join(
            f"[{m.ticker}] {m.question}"
            f" | tier: {candidate_map.get(m.event_ticker, {}).get('tier', 'unknown')}"
            f" | alignment: {candidate_map.get(m.event_ticker, {}).get('alignment', '?')}"
            f" | YES: {m.mid_price:.0%} | Closes: {m.close_date}"
            for m in top_markets
        )

        domain_text = ""
        if analysis:
            high_med = [d for d in analysis["affected_domains"]
                        if d.get("keep_for_market_search") or d["relevance"] in ("high", "medium")]
            domain_lines = [
                f"  - [{d.get('causal_distance','?')}] {d['domain']}: {d['mechanism']}"
                for d in high_med
            ]
            domain_text = "\nDomain impact map:\n" + "\n".join(domain_lines)
            if analysis.get("most_surprising_connection"):
                domain_text += f"\nKey non-obvious angle: {analysis['most_surprising_connection']}"

        resolution_target = belief_summary.get("resolution_target", "")
        falsifiers = belief_summary.get("falsifiers", [])

        prompt = (
            f"User's belief: {belief_summary['core_belief']}\n"
            f"Resolution target: {resolution_target}\n"
            f"Timeframe: {belief_summary.get('timeframe_start', '')} → {belief_summary.get('timeframe_end', belief_summary.get('time_horizon', ''))}\n"
            f"Key drivers: {', '.join(belief_summary.get('key_drivers', []))}\n"
            f"Mechanism: {belief_summary.get('mechanism', '')}\n"
            f"Falsifiers: {'; '.join(falsifiers)}\n"
            f"Confidence: {belief_summary['confidence_level']}"
            f"{domain_text}\n\n"
            f"Available markets ({len(top_markets)} shown, pre-sorted by relevance):\n{market_lines}"
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
        seen_events: set[str] = set()
        for rec in result["recommendations"]:
            m = market_map.get(rec["ticker"])
            if m is None:
                continue
            if m.event_ticker in seen_events:
                continue
            seen_events.add(m.event_ticker)
            enriched.append({
                "ticker": m.ticker,
                "event_ticker": m.event_ticker,
                "question": m.question,
                "price": m.mid_price,
                "close_date": m.close_date,
                "rules_summary": m.rules_summary,
                "tier": rec["tier"],
                "direction": rec["betting_direction"],
                "rationale": rec["rationale"],
                "relevance": rec["why_this_belongs_in_portfolio"],
                "score": rec["relevance_score"],
                "expressiveness_score": rec["expressiveness_score"],
                "causal_purity_score": rec["causal_purity_score"],
                "timeframe_alignment_score": rec["timeframe_alignment_score"],
                "main_risk": rec["main_risk_or_confounder"],
            })

        return sorted(enriched, key=lambda x: x["score"], reverse=True)
