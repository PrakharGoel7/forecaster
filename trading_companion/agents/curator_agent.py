"""Agent 4 — Basket Builder."""
from __future__ import annotations

import json
import os

from openai import OpenAI

SYSTEM_PROMPT = """You are building a coherent $100 thematic prediction-market basket.

Think in exposure buckets first, holdings second. Avoid duplicated exposure. The result should feel like an investable retail product, not a list of related markets.

Rules:
- Total weight must equal exactly $100.
- Include 5 to 10 holdings when possible.
- If fewer than 5 good holdings exist, allow 3 to 4 holdings and explain thin coverage.
- Direct_thesis + strong_proxy should target 50–70% when available.
- Good_proxy can be up to 40%.
- Partial_proxy + early_signal should be max 25%.
- Hedge should be max 10%.
- Direct_thesis or strong_proxy holdings should usually be $15–$30.
- Good_proxy holdings should usually be $8–$18.
- Partial_proxy or early_signal holdings should usually be $5–$12.
- Hedge holdings should usually be $5–$10.
- Max single holding: $35.
- At most 1 holding per exact market ticker.
- At most 1 holding per event_ticker unless intentionally using a threshold ladder.
- At most 2 first_order_consequence holdings when possible.
- At most 1 hedge_or_falsifier unless strongly justified.
- Avoid duplicated exposure.
- Use price only after thematic fit.
- Prefer clean markets but do not fail solely because only proxy markets exist.
- Every proxy holding must preserve fit labels and warnings.
- Basket summary should clearly state whether this is a Direct basket, Strong proxy basket, Mixed proxy basket, or Thin market coverage basket.
- Create 2 to 5 topic-specific basket buckets that would make sense to a retail user reading this thesis.
- Group holdings into those topic buckets using plain-English labels tailored to the thesis, not generic labels like direct, mechanism, hedge, or consequence.
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
                "basket_quality": {
                    "type": "string",
                    "enum": ["direct", "strong_proxy", "mixed_proxy", "thin_market_coverage"],
                },
                "basket_quality_explanation": {"type": "string"},
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
                "basket_buckets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                        },
                        "required": ["name", "description"],
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
                            "topic_bucket": {"type": "string"},
                            "bucket_thesis": {"type": ["string", "null"]},
                            "linked_exposure_name": {"type": "string"},
                            "fit_type": {
                                "type": "string",
                                "enum": ["direct_thesis", "strong_proxy", "good_proxy", "partial_proxy", "early_signal", "hedge"],
                            },
                            "fit_confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                            "fit_warning": {"type": ["string", "null"]},
                            "proxy_reason": {"type": ["string", "null"]},
                            "rationale": {"type": "string"},
                            "main_risk": {"type": "string"},
                        },
                        "required": [
                            "ticker", "side", "weight_dollars", "topic_bucket", "bucket_thesis", "linked_exposure_name",
                            "fit_type", "fit_confidence", "fit_warning", "proxy_reason", "rationale", "main_risk",
                        ],
                    },
                },
            },
            "required": [
                "basket_title", "basket_summary", "construction_notes",
                "basket_quality", "basket_quality_explanation", "exposure_allocations", "basket_buckets", "holdings",
            ],
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

        def _compat_role(selected_meta: dict, fit_type: str | None) -> str:
            tier = selected_meta.get("tier")
            if tier == "hedge_or_falsifier" or fit_type == "hedge":
                return "hedge"
            if tier == "direct_thesis":
                return "direct"
            if tier == "mechanism":
                return "mechanism"
            return "indirect"

        for raw in result.get("holdings", []):
            market = market_map.get(raw["ticker"])
            if not market or market.event_ticker in seen_events:
                continue
            seen_events.add(market.event_ticker)
            selected_meta = selected_market_map.get(market.ticker, {})
            fit_type = raw.get("fit_type", selected_meta.get("fit_type"))
            holdings.append({
                "ticker": market.ticker,
                "event_ticker": market.event_ticker,
                "question": market.question,
                "market_price": market.mid_price,
                "close_date": market.close_date,
                "side": raw["side"],
                "role": _compat_role(selected_meta, fit_type),
                "weight_dollars": float(raw["weight_dollars"]),
                "topic_bucket": raw.get("topic_bucket", ""),
                "bucket_thesis": raw.get("bucket_thesis"),
                "linked_exposure_name": raw.get("linked_exposure_name", selected_meta.get("linked_exposure_name", "")),
                "route_ring": selected_meta.get("route_ring"),
                "fit_type": fit_type,
                "fit_confidence": raw.get("fit_confidence", selected_meta.get("fit_confidence")),
                "fit_warning": raw.get("fit_warning", selected_meta.get("fit_warning")),
                "proxy_reason": raw.get("proxy_reason", selected_meta.get("proxy_reason")),
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
                "basket_quality": result.get("basket_quality", "thin_market_coverage"),
                "basket_quality_explanation": result.get("basket_quality_explanation", "No usable holdings were available."),
                "exposure_allocations": result.get("exposure_allocations", []),
                "basket_buckets": result.get("basket_buckets", []),
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
            "basket_quality": result.get("basket_quality"),
            "basket_quality_explanation": result.get("basket_quality_explanation", ""),
            "exposure_allocations": result.get("exposure_allocations", []),
            "basket_buckets": result.get("basket_buckets", []),
            "holdings": normalized,
            "total_notional": round(sum(h["weight_dollars"] for h in normalized), 2),
        }


# Backward-compatible name while the rest of the app is being migrated.
CuratorAgent = BasketBuilderAgent
