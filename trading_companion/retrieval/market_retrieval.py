from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import math
import re
from typing import Any

try:
    from ..event_cache_db import get_event_lookup
    from ..market_cache_db import get_all_markets
except ImportError:
    from event_cache_db import get_event_lookup
    from market_cache_db import get_all_markets

_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")


@dataclass
class RetrievalConfig:
    per_exposure_limit: int = 20
    global_limit: int = 180
    per_event_limit: int = 2


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    raw = value.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _days_from_timeframe(belief_summary: dict[str, Any]) -> tuple[date | None, date | None]:
    return (
        _parse_date(belief_summary.get("timeframe_start")),
        _parse_date(belief_summary.get("timeframe_end") or belief_summary.get("time_horizon")),
    )


def _timeframe_score(close_date: date | None, start: date | None, end: date | None) -> tuple[float, str]:
    today = date.today()
    if close_date and close_date < today:
        return -100.0, "expired"
    if not close_date or not end:
        return 0.0, "timeframe unknown"
    if start and close_date < start:
        delta = (start - close_date).days
        if delta > 60:
            return -10.0, "resolves too early"
        return -3.0, "slightly early"
    if close_date <= end:
        return 8.0, "resolves in thesis window"
    delta = (close_date - end).days
    if delta <= 45:
        return 1.0, "slightly beyond thesis window"
    if delta <= 180:
        return -4.0, "late for thesis window"
    return -10.0, "much later than thesis window"


def _liquidity_score(market: dict[str, Any]) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    volume = float(market.get("volume") or 0.0)
    mid = market.get("mid_price")
    if mid is None:
        score -= 4.0
        reasons.append("missing price")
    if volume <= 0:
        score -= 3.0
        reasons.append("zero volume")
    elif volume >= 5000:
        score += 3.0
        reasons.append("active liquidity")
    elif volume >= 500:
        score += 1.5
        reasons.append("usable liquidity")
    else:
        reasons.append("thin liquidity")
    return score, reasons


def _ladder_key(market: dict[str, Any]) -> str:
    title = market.get("question") or market.get("yes_sub_title") or market.get("ticker")
    return re.sub(r"\d+", "#", title.lower())


def _candidate_payload(
    market: dict[str, Any],
    event: dict[str, Any],
    score: float,
    reasons: list[str],
) -> dict[str, Any]:
    yes_price = market.get("mid_price")
    return {
        "event_ticker": market.get("event_ticker", ""),
        "ticker": market.get("ticker", ""),
        "question": market.get("question", ""),
        "event_title": event.get("title", ""),
        "category": event.get("category", ""),
        "close_date": market.get("close_date", ""),
        "yes_price": yes_price,
        "no_price": None if yes_price is None else round(max(0.0, min(1.0, 1.0 - float(yes_price))), 4),
        "volume": market.get("volume"),
        "retrieval_score": round(score, 3),
        "retrieval_reasons": reasons[:6],
    }


def retrieve_markets_for_exposures(
    exposures: list[dict[str, Any]],
    belief_summary: dict[str, Any],
    *,
    config: RetrievalConfig | None = None,
    embedding_scores: dict[tuple[str, str], float] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    config = config or RetrievalConfig()
    event_lookup = get_event_lookup()
    market_rows = get_all_markets(status="open")
    start, end = _days_from_timeframe(belief_summary)
    global_candidates = 0
    grouped: list[dict[str, Any]] = []

    for exposure in exposures:
        search_tokens = _tokenize(" ".join(exposure.get("search_terms", [])))
        negative_tokens = _tokenize(" ".join(exposure.get("negative_search_terms", [])))
        resolution_tokens = _tokenize(" ".join(exposure.get("resolution_features", [])))
        rows: list[dict[str, Any]] = []

        for market in market_rows:
            event = event_lookup.get(market.get("event_ticker", ""), {})
            searchable = " ".join(
                filter(
                    None,
                    [
                        market.get("question", ""),
                        market.get("yes_sub_title", ""),
                        market.get("no_sub_title", ""),
                        market.get("ticker", ""),
                        event.get("title", ""),
                        event.get("series_ticker", ""),
                        event.get("category", ""),
                        market.get("rules_primary", ""),
                        market.get("rules_secondary", ""),
                    ],
                )
            )
            haystack = _tokenize(searchable)
            if not search_tokens and not resolution_tokens:
                continue

            matched = search_tokens & haystack
            resolution_matched = resolution_tokens & haystack
            if not matched and not resolution_matched:
                continue

            negative_hits = negative_tokens & haystack
            if negative_hits and len(negative_hits) >= max(1, len(matched)):
                continue

            score = 0.0
            reasons: list[str] = []
            if matched:
                score += 4.0 + min(len(matched), 4) * 1.5
                reasons.append(f"matched terms: {', '.join(sorted(matched)[:3])}")
            if resolution_matched:
                score += 2.5 + min(len(resolution_matched), 3)
                reasons.append(f"resolution fit: {', '.join(sorted(resolution_matched)[:2])}")
            if negative_hits:
                score -= min(4.0, len(negative_hits) * 1.5)
                reasons.append(f"negative terms: {', '.join(sorted(negative_hits)[:2])}")

            tf_score, tf_reason = _timeframe_score(_parse_date(market.get("close_date")), start, end)
            if tf_score <= -100:
                continue
            score += tf_score
            reasons.append(tf_reason)

            liquidity_score, liquidity_reasons = _liquidity_score(market)
            score += liquidity_score
            reasons.extend(liquidity_reasons)

            if exposure.get("tier") == "direct_thesis":
                score += 1.0
            if embedding_scores:
                embed = embedding_scores.get((exposure.get("exposure_name", ""), market.get("ticker", "")))
                if embed is not None:
                    score += embed * 3.0
                    reasons.append("embedding similarity")

            rows.append({
                "market": market,
                "event": event,
                "score": score,
                "reasons": reasons,
                "ladder_key": _ladder_key(market),
            })

        rows.sort(key=lambda item: (-item["score"], -float(item["market"].get("volume") or 0.0), item["market"].get("ticker", "")))
        seen_events: dict[str, int] = {}
        seen_ladders: set[tuple[str, str]] = set()
        candidates: list[dict[str, Any]] = []
        for row in rows:
            if global_candidates >= config.global_limit:
                break
            event_ticker = row["market"].get("event_ticker", "")
            ladder_key = row["ladder_key"]
            ladder_id = (event_ticker, ladder_key)
            if seen_events.get(event_ticker, 0) >= config.per_event_limit:
                continue
            if ladder_id in seen_ladders:
                continue
            candidates.append(_candidate_payload(row["market"], row["event"], row["score"], row["reasons"]))
            seen_events[event_ticker] = seen_events.get(event_ticker, 0) + 1
            seen_ladders.add(ladder_id)
            global_candidates += 1
            if len(candidates) >= config.per_exposure_limit:
                break

        grouped.append({
            "exposure_name": exposure.get("exposure_name", ""),
            "exposure": exposure,
            "candidates": candidates,
        })

    return {"exposure_candidates": grouped}
