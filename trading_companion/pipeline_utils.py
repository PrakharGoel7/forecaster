from __future__ import annotations

from typing import Any


def exposure_analysis_payload(exposure_result: dict[str, Any]) -> dict[str, Any]:
    exposures = exposure_result.get("exposures", [])
    affected_domains = []
    for exposure in exposures:
        purity = float(exposure.get("causal_purity_score", 0))
        relevance = "high" if purity >= 4 else "medium" if purity >= 2.5 else "low"
        affected_domains.append({
            "domain": exposure.get("exposure_name", ""),
            "relevance": relevance,
            "mechanism": exposure.get("causal_path", ""),
            "market_signals": exposure.get("resolution_features", [])[:3],
            "causal_distance": exposure.get("causal_distance", ""),
            "expressiveness_score": exposure.get("expressiveness_score", 0),
            "causal_purity_score": exposure.get("causal_purity_score", 0),
            "timeframe_alignment_score": 5 if exposure.get("timeframe_fit") == "strong" else 3 if exposure.get("timeframe_fit") == "partial" else 1,
            "keep_for_market_search": exposure.get("timeframe_fit") != "weak" and float(exposure.get("expressiveness_score", 0)) >= 3,
        })
    return {
        "affected_domains": affected_domains,
        "most_surprising_connection": exposure_result.get("rejected_routes", [{}])[0].get("route", "") if exposure_result.get("rejected_routes") else "",
        "exposures": exposures,
        "rejected_routes": exposure_result.get("rejected_routes", []),
    }


def normalize_weights(holdings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not holdings:
        return holdings
    total = sum(max(0.0, float(h.get("weight_dollars", 0.0))) for h in holdings)
    if total <= 0:
        even = round(100.0 / len(holdings), 2)
        normalized = [{**h, "weight_dollars": even} for h in holdings]
    else:
        normalized = []
        running = 0.0
        for idx, holding in enumerate(sorted(holdings, key=lambda h: float(h.get("weight_dollars", 0.0)), reverse=True)):
            if idx == len(holdings) - 1:
                weight = round(100.0 - running, 2)
            else:
                weight = round((max(0.0, float(holding.get("weight_dollars", 0.0))) / total) * 100.0, 2)
                running += weight
            normalized.append({**holding, "weight_dollars": weight})
    diff = round(100.0 - sum(float(h.get("weight_dollars", 0.0)) for h in normalized), 2)
    normalized[0]["weight_dollars"] = round(float(normalized[0].get("weight_dollars", 0.0)) + diff, 2)
    return normalized


def apply_critic_repairs(basket: dict[str, Any], selected_markets: list[dict[str, Any]], critique: dict[str, Any]) -> dict[str, Any]:
    selected_by_ticker = {m["ticker"]: m for m in selected_markets}
    holdings = [h for h in basket.get("holdings", []) if h.get("ticker") not in set(critique.get("suggested_removals", []))]
    for replacement in critique.get("suggested_replacements", []):
        remove_ticker = replacement.get("remove_ticker")
        add_ticker = replacement.get("add_ticker")
        to_remove = next((h for h in holdings if h.get("ticker") == remove_ticker), None)
        target = selected_by_ticker.get(add_ticker)
        if not to_remove or not target:
            continue
        holdings = [h for h in holdings if h.get("ticker") != remove_ticker]
        holdings.append({
            **to_remove,
            "ticker": target["ticker"],
            "event_ticker": target["event_ticker"],
            "question": target["question"],
            "side": target.get("recommended_side", "YES"),
            "linked_exposure_name": target.get("linked_exposure_name", ""),
            "tier": target.get("tier"),
            "rationale": replacement.get("reason", to_remove.get("rationale", "")),
        })
    return {**basket, "holdings": holdings}


def validate_and_repair_basket(
    basket: dict[str, Any],
    selected_markets: list[dict[str, Any]],
    selected_market_rows: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    selected_by_ticker = {m["ticker"]: m for m in selected_markets}
    seen_tickers: set[str] = set()
    seen_events: set[str] = set()
    repaired: list[dict[str, Any]] = []

    for holding in basket.get("holdings", []):
        ticker = holding.get("ticker")
        if not ticker or ticker in seen_tickers:
            warnings.append(f"Removed duplicate ticker {ticker}")
            continue
        source = selected_by_ticker.get(ticker)
        market = selected_market_rows.get(ticker)
        if not source or not market:
            warnings.append(f"Removed holding with unknown ticker {ticker}")
            continue
        event_ticker = holding.get("event_ticker") or source.get("event_ticker") or market.event_ticker
        if event_ticker in seen_events:
            warnings.append(f"Removed duplicate event exposure {event_ticker}")
            continue
        side = holding.get("side", "YES")
        if side not in ("YES", "NO"):
            side = source.get("recommended_side", "YES")
            warnings.append(f"Corrected invalid side for {ticker}")
        repaired.append({
            **holding,
            "event_ticker": event_ticker,
            "question": holding.get("question") or source.get("question") or market.question,
            "side": side,
            "linked_exposure_name": holding.get("linked_exposure_name") or source.get("linked_exposure_name", ""),
            "tier": holding.get("tier") or source.get("tier"),
            "market_price": float(getattr(market, "mid_price", 0.0)),
            "close_date": getattr(market, "close_date", ""),
            "rules_summary": getattr(market, "rules_summary", ""),
        })
        seen_tickers.add(ticker)
        seen_events.add(event_ticker)

    repaired = normalize_weights(repaired)
    first_order = [h for h in repaired if h.get("tier") == "first_order_consequence"]
    if len(first_order) > 2:
        keep = {h["ticker"] for h in first_order[:2]}
        repaired = [h for h in repaired if h.get("tier") != "first_order_consequence" or h["ticker"] in keep]
        warnings.append("Trimmed first-order consequence holdings to 2")
    hedges = [h for h in repaired if h.get("tier") == "hedge_or_falsifier" or h.get("role") == "hedge"]
    if len(hedges) > 1:
        keep = hedges[0]["ticker"]
        repaired = [h for h in repaired if not ((h.get("tier") == "hedge_or_falsifier" or h.get("role") == "hedge") and h["ticker"] != keep)]
        warnings.append("Trimmed hedge holdings to 1")
    for holding in repaired:
        if float(holding.get("weight_dollars", 0.0)) > 35.0:
            warnings.append(f"Capped overweight holding {holding['ticker']} at $35")
            holding["weight_dollars"] = 35.0
    repaired = normalize_weights(repaired)
    if len(repaired) > 10:
        repaired = normalize_weights(repaired[:10])
        warnings.append("Trimmed holdings to 10")
    if len(repaired) < 5:
        warnings.append("Fewer than 5 high-quality holdings were available")
    basket = {**basket, "holdings": repaired, "total_notional": round(sum(float(h.get("weight_dollars", 0.0)) for h in repaired), 2)}
    return basket, warnings
