"""On-demand Kalshi price history and basket marks.

The basket creation quote is the baseline. Later marks use Kalshi candle bid/ask
midpoints, falling back to the candle's last traded price when no quote exists.
"""
from __future__ import annotations

import math
import threading
import time
from datetime import datetime, timezone
from typing import Any


_cache: dict[tuple, tuple[float, dict[str, list[dict]]]] = {}
_cache_lock = threading.Lock()
_CACHE_SECONDS = 300


def _price(value: Any) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if math.isfinite(price) and 0 <= price <= 1 else None


def candle_yes_price(candle: dict) -> float | None:
    bid = _price((candle.get("yes_bid") or {}).get("close_dollars"))
    ask = _price((candle.get("yes_ask") or {}).get("close_dollars"))
    if bid is not None and ask is not None and ask > 0 and bid <= ask:
        return (bid + ask) / 2
    return _price((candle.get("price") or {}).get("close_dollars"))


def _timestamp(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def period_for_basket(age_seconds: int, holding_count: int) -> int:
    """Use the finest period that stays below Kalshi's 10,000-candle batch cap."""
    for period in (1, 60, 1440):
        if math.ceil(age_seconds / (period * 60)) * holding_count <= 9000:
            return period
    return 1440


def fetch_candlesticks(client, tickers: list[str], start_ts: int, end_ts: int,
                       period_interval: int) -> dict[str, list[dict]]:
    unique = list(dict.fromkeys(tickers))
    if not unique or len(unique) > 100:
        raise ValueError("Price history requires 1 to 100 market tickers")
    # Ask only for completed periods, and reuse recent responses across viewers.
    end_ts = end_ts - end_ts % (period_interval * 60)
    if end_ts <= start_ts:
        return {ticker: [] for ticker in unique}
    key = (tuple(unique), start_ts, end_ts, period_interval)
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
    result: dict[str, list[dict]] = {ticker: [] for ticker in unique}
    # A long-lived basket can exceed Kalshi's 10,000-candle response limit.
    window = max(1, 9000 // len(unique)) * period_interval * 60
    cursor = start_ts
    while cursor < end_ts:
        chunk_end = min(cursor + window, end_ts)
        data = client.get_candlesticks(unique, cursor, chunk_end, period_interval)
        for ticker in unique:
            result[ticker].extend(data.get(ticker, []))
        cursor = chunk_end + 1
    with _cache_lock:
        for expired in [cache_key for cache_key, item in _cache.items() if item[0] <= now]:
            del _cache[expired]
        if len(_cache) >= 32:
            del _cache[next(iter(_cache))]
        _cache[key] = (now + _CACHE_SECONDS, result)
    return result


def market_history(client, ticker: str, days: int, now_ts: int | None = None) -> dict:
    now_ts = now_ts or int(time.time())
    period = 60 if days <= 7 else 1440
    candles = fetch_candlesticks(client, [ticker], now_ts - days * 86400, now_ts, period)[ticker]
    points = []
    for candle in sorted(candles, key=lambda item: item["end_period_ts"]):
        price = candle_yes_price(candle)
        if price is not None:
            points.append({"timestamp": _timestamp(candle["end_period_ts"]), "yes_price": round(price, 4)})
    return {"ticker": ticker, "period_minutes": period, "points": points}


def basket_performance(client, basket: dict, now_ts: int | None = None) -> dict:
    now_ts = now_ts or int(time.time())
    created_ts = int(datetime.fromisoformat(basket["created_at"].replace("Z", "+00:00")).timestamp())
    manual = basket.get("mode") == "manual"
    holdings = []
    for raw in basket.get("holdings", []):
        entry = _price(raw.get("market_price_at_create"))
        side = raw.get("side")
        weight = float(raw.get("weight_dollars") or 0)
        if not raw.get("ticker") or entry is None or weight <= 0 or side not in ("YES", "NO"):
            continue
        # Manual baskets store the selected contract price. Older generated
        # baskets store the YES quote for either side.
        entry_side = entry if (side == "YES" or manual) else 1 - entry
        entry_yes = entry if (side == "YES" or not manual) else 1 - entry
        if entry_side <= 0:
            continue
        holdings.append({"ticker": raw["ticker"], "side": side, "entry_side": entry_side,
                         "entry_yes": entry_yes, "weight": weight})

    baseline = {"dates": [_timestamp(created_ts)], "values": [100.0],
                "current_return": 0.0, "period_minutes": None,
                "updated_holdings": 0, "total_holdings": len(holdings)}
    if not holdings or now_ts <= created_ts:
        return baseline

    period = period_for_basket(now_ts - created_ts, len(holdings))
    candles = fetch_candlesticks(client, [h["ticker"] for h in holdings], created_ts, now_ts, period)
    updates: dict[int, dict[str, float]] = {}
    for ticker, series in candles.items():
        for candle in series:
            ts = candle.get("end_period_ts")
            price = candle_yes_price(candle)
            if isinstance(ts, int) and ts > created_ts and price is not None:
                updates.setdefault(ts, {})[ticker] = price

    current_yes = {h["ticker"]: h["entry_yes"] for h in holdings}
    seen: set[str] = set()
    total_weight = sum(h["weight"] for h in holdings)
    dates = baseline["dates"][:]
    values = baseline["values"][:]
    for ts in sorted(updates):
        current_yes.update(updates[ts])
        seen.update(updates[ts])
        value = sum(
            h["weight"] / total_weight *
            ((current_yes[h["ticker"]] if h["side"] == "YES" else 1 - current_yes[h["ticker"]]) / h["entry_side"])
            for h in holdings
        ) * 100
        dates.append(_timestamp(ts))
        values.append(round(value, 2))

    return {"dates": dates, "values": values, "current_return": round(values[-1] - 100, 2),
            "period_minutes": period, "updated_holdings": len(seen), "total_holdings": len(holdings)}
