"""Agent 4 — Basket Builder."""
from __future__ import annotations

import json
import os

from openai import OpenAI

SYSTEM_PROMPT = """You are building a coherent $100 thematic prediction-market basket.

Think in exposure buckets first, holdings second. Avoid duplicated exposure. The result should feel like an investable retail product, not a list of related markets.

Rules:
- Total weight must equal exactly $100.
- Include 5 to 10 holdings when enough quality exists.
- At least 50% of notional should be direct_thesis + mechanism if available.
- Max single holding: $35.
- At most 1 holding per exact market ticker.
- At most 1 holding per event_ticker unless intentionally using a threshold ladder.
- At most 2 first_order_consequence holdings.
- At most 1 hedge_or_falsifier unless strongly justified.
- Avoid duplicated exposure.
- Use price only after thematic fit.
- If not enough high-quality markets exist, build a smaller basket and state the limitation in construction_notes.
"""

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
                "exposure_allocations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "bucket": {
                                "type": "string",
                                "enum": ["direct_thesis", "mechanism", "first_order_consequence", "hedge_or_falsifier"],
                            },
                            "weight_dollars": {"type": "number"},
                            "reason": {"type": "string"},
                        },
                        "required": ["bucket", "weight_dollars", "reason"],
                    },
                },
                "holdings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string"},
                            "side": {"type": "string", "enum": ["YES", "NO"]},
                            "weight_dollars": {"type": "number"},
                            "role": {"type": "string", "enum": ["direct", "mechanism", "indirect", "hedge"]},
                            "linked_exposure_name": {"type": "string"},
                            "rationale": {"type": "string"},
                            "main_risk": {"type": "string"},
                        },
                        "required": ["ticker", "side", "weight_dollars", "role", "linked_exposure_name", "rationale", "main_risk"],
                    },
                },
            },
            "required": ["basket_title", "basket_summary", "construction_notes", "exposure_allocations", "holdings"],
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

    def run(self, belief_summary: dict, markets: list, exposures: list[dict] | None = None,
            selected_markets: list[dict] | None = None, mode: str = "thinking") -> dict:
        selected_market_map: dict[str, dict] = {}
        if selected_markets:
            for market in selected_markets:
                selected_market_map[market["ticker"]] = market

        top_markets = markets[:60]
        market_lines = "\n".join(
            f"[{m.ticker}] {m.question}"
            f" | event={m.event_ticker}"
            f" | tier={selected_market_map.get(m.ticker, {}).get('tier', 'unknown')}"
            f" | side={selected_market_map.get(m.ticker, {}).get('recommended_side', '?')}"
            f" | YES={m.mid_price:.0%}"
            f" | closes={m.close_date}"
            for m in top_markets
        )

        exposure_text = "\n".join(
            f"- [{e.get('tier')}] {e.get('exposure_name')}: {e.get('causal_path')}"
            for e in (exposures or [])
        )

        prompt = (
            f"Core belief: {belief_summary['core_belief']}\n"
            f"Mode: {mode or belief_summary.get('mode_used', 'thinking')}\n"
            f"Resolution target: {belief_summary.get('resolution_target', '')}\n"
            f"Timeframe: {belief_summary.get('timeframe_start', '')} → {belief_summary.get('timeframe_end', belief_summary.get('time_horizon', ''))}\n"
            f"Desired exposure: {belief_summary.get('desired_exposure', '')}\n"
            f"Mechanism: {', '.join(belief_summary.get('mechanism', []))}\n"
            f"Key drivers: {', '.join(belief_summary.get('key_drivers', []))}\n"
            f"Falsifiers: {'; '.join(belief_summary.get('falsifiers', []))}\n"
            f"Scope: {belief_summary.get('scope', '')}\n"
            f"Current context: {belief_summary.get('current_context', '')}\n"
            f"Exposure routes:\n{exposure_text or '- none'}\n\n"
            f"Selected candidate markets ({len(top_markets)} shown):\n{market_lines}"
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
            selected_meta = selected_market_map.get(market.ticker, {})
            holdings.append({
                "ticker": market.ticker,
                "event_ticker": market.event_ticker,
                "question": market.question,
                "market_price": market.mid_price,
                "close_date": market.close_date,
                "side": raw["side"],
                "role": raw["role"],
                "weight_dollars": float(raw["weight_dollars"]),
                "linked_exposure_name": raw.get("linked_exposure_name", selected_meta.get("linked_exposure_name", "")),
                "rationale": raw["rationale"],
                "main_risk": raw["main_risk"],
                "tier": selected_meta.get("tier"),
                "rules_summary": market.rules_summary,
            })

        if not holdings:
            return {
                "basket_title": result.get("basket_title", belief_summary["core_belief"]),
                "basket_summary": result.get("basket_summary", ""),
                "construction_notes": result.get("construction_notes", ""),
                "exposure_allocations": result.get("exposure_allocations", []),
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
            "exposure_allocations": result.get("exposure_allocations", []),
            "holdings": normalized,
            "total_notional": round(sum(h["weight_dollars"] for h in normalized), 2),
        }


# Backward-compatible name while the rest of the app is being migrated.
CuratorAgent = BasketBuilderAgent
