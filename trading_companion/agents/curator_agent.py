"""Agent 4 — Basket Builder.

Builds a weighted $100 prediction-market ETF from the shortlisted markets.
"""
from __future__ import annotations

import json
import os

from openai import OpenAI

SYSTEM_PROMPT = """You are a prediction market basket builder.

The user has a belief about the future. Your job is to turn that belief into a shareable $100 thematic basket of prediction market contracts.

Your output must be a coherent portfolio, not a list of loosely related recommendations.

Objectives:
1. Maximize thematic purity to the user's thesis.
2. Prefer direct_thesis and mechanism markets when available.
3. Use indirect and hedge/falsifier markets sparingly and intentionally.
4. Avoid duplicated exposure.
5. Produce a basket that feels investable, explainable, and balanced.

Portfolio construction rules:
- Total notional must equal exactly $100.
- Include 5 to 10 holdings.
- At least 50% of notional should be in direct_thesis + mechanism markets if available.
- Maximum single holding weight: $35.
- Include at most 1 holding per event_ticker.
- Include at most 2 first_order_consequence holdings.
- Include at most 1 hedge_or_falsifier unless the user's falsifiers clearly justify it.
- Use price only after thematic fit is established.

Role definitions:
- direct: the market most directly expresses the belief's resolution target
- mechanism: tests the causal path the user thinks will drive the thesis
- indirect: captures a meaningful first-order consequence of the thesis
- hedge: weakens or falsifies the thesis

For each holding, decide:
- ticker
- side (YES/NO)
- weight_dollars
- role
- rationale
- main_risk

Also provide:
- basket_title
- basket_summary
- construction_notes

Make the basket easy to explain to a normal user."""

_BUILD_TOOL = {
    "type": "function",
    "function": {
        "name": "build_basket",
        "description": "Construct a weighted $100 prediction market ETF.",
        "parameters": {
            "type": "object",
            "properties": {
                "basket_title": {"type": "string"},
                "basket_summary": {"type": "string"},
                "construction_notes": {"type": "string"},
                "holdings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string"},
                            "side": {"type": "string", "enum": ["YES", "NO"]},
                            "weight_dollars": {"type": "number"},
                            "role": {"type": "string", "enum": ["direct", "mechanism", "indirect", "hedge"]},
                            "rationale": {"type": "string"},
                            "main_risk": {"type": "string"},
                        },
                        "required": ["ticker", "side", "weight_dollars", "role", "rationale", "main_risk"],
                    },
                },
            },
            "required": ["basket_title", "basket_summary", "construction_notes", "holdings"],
        },
    },
}


class BasketBuilderAgent:
    def __init__(self, api_key: str | None = None, model: str = "openai/gpt-4o"):
        self._client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key or os.environ["OPENROUTER_API_KEY"],
        )
        self._model = model

    def run(self, belief_summary: dict, markets: list, analysis: dict | None = None,
            screener_candidates: list | None = None) -> dict:
        candidate_map: dict[str, dict] = {}
        if screener_candidates:
            for candidate in screener_candidates:
                candidate_map[candidate["event_ticker"]] = candidate

        top_markets = markets[:60]
        market_lines = "\n".join(
            f"[{m.ticker}] {m.question}"
            f" | event={m.event_ticker}"
            f" | tier={candidate_map.get(m.event_ticker, {}).get('tier', 'unknown')}"
            f" | alignment={candidate_map.get(m.event_ticker, {}).get('alignment', '?')}"
            f" | YES={m.mid_price:.0%}"
            f" | closes={m.close_date}"
            for m in top_markets
        )

        kept_domains = []
        if analysis:
            kept_domains = [
                d for d in analysis["affected_domains"]
                if d.get("keep_for_market_search") or d.get("relevance") in ("high", "medium")
            ]
        domain_text = "\n".join(
            f"- [{d.get('causal_distance','?')}] {d['domain']}: {d['mechanism']}"
            for d in kept_domains
        )

        prompt = (
            f"Core belief: {belief_summary['core_belief']}\n"
            f"Mode: {belief_summary.get('mode_used', 'thinking')}\n"
            f"Resolution target: {belief_summary.get('resolution_target', '')}\n"
            f"Timeframe: {belief_summary.get('timeframe_start', '')} → {belief_summary.get('timeframe_end', belief_summary.get('time_horizon', ''))}\n"
            f"Mechanism: {belief_summary.get('mechanism', '')}\n"
            f"Key drivers: {', '.join(belief_summary.get('key_drivers', []))}\n"
            f"Falsifiers: {'; '.join(belief_summary.get('falsifiers', []))}\n"
            f"Scope: {belief_summary.get('scope', '')}\n"
            f"Current context: {belief_summary.get('current_context', '')}\n"
            f"Domain map:\n{domain_text or '- none'}\n\n"
            f"Candidate markets ({len(top_markets)} shown):\n{market_lines}"
        )

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            tools=[_BUILD_TOOL],
            tool_choice={"type": "function", "function": {"name": "build_basket"}},
            max_tokens=2400,
        )

        tc = response.choices[0].message.tool_calls[0]
        result = json.loads(tc.function.arguments)

        market_map = {m.ticker: m for m in markets}
        seen_events: set[str] = set()
        holdings: list[dict] = []
        for raw in result.get("holdings", []):
            market = market_map.get(raw["ticker"])
            if not market or market.event_ticker in seen_events:
                continue
            seen_events.add(market.event_ticker)
            holdings.append({
                "ticker": market.ticker,
                "event_ticker": market.event_ticker,
                "question": market.question,
                "market_price": market.mid_price,
                "close_date": market.close_date,
                "side": raw["side"],
                "role": raw["role"],
                "weight_dollars": float(raw["weight_dollars"]),
                "rationale": raw["rationale"],
                "main_risk": raw["main_risk"],
                "tier": candidate_map.get(market.event_ticker, {}).get("tier"),
                "rules_summary": market.rules_summary,
            })

        if not holdings:
            return {
                "basket_title": result.get("basket_title", belief_summary["core_belief"]),
                "basket_summary": result.get("basket_summary", ""),
                "construction_notes": result.get("construction_notes", ""),
                "holdings": [],
                "total_notional": 0.0,
            }

        total = sum(max(0.0, h["weight_dollars"]) for h in holdings)
        normalized = []
        running_total = 0
        for idx, holding in enumerate(sorted(holdings, key=lambda h: h["weight_dollars"], reverse=True)):
            if idx == len(holdings) - 1:
                weight = round(100 - running_total, 2)
            else:
                weight = round((holding["weight_dollars"] / total) * 100, 2) if total > 0 else 0.0
                running_total += weight
            normalized.append({**holding, "weight_dollars": weight})

        if normalized:
            diff = round(100 - sum(h["weight_dollars"] for h in normalized), 2)
            normalized[0]["weight_dollars"] = round(normalized[0]["weight_dollars"] + diff, 2)

        return {
            "basket_title": result.get("basket_title", belief_summary["core_belief"]),
            "basket_summary": result.get("basket_summary", ""),
            "construction_notes": result.get("construction_notes", ""),
            "holdings": normalized,
            "total_notional": round(sum(h["weight_dollars"] for h in normalized), 2),
        }


# Backward-compatible name while the rest of the app is being migrated.
CuratorAgent = BasketBuilderAgent
