from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
import json
import re
from typing import Any, Callable

try:
    from ..cache_paths import MARKETS_CACHE_FILE
    from ..event_cache_db import get_event_lookup, search_events, search_events_fts
    from ..market_cache_db import get_all_markets, get_markets_for_events
except ImportError:
    from cache_paths import MARKETS_CACHE_FILE
    from event_cache_db import get_event_lookup, search_events, search_events_fts
    from market_cache_db import get_all_markets, get_markets_for_events

_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")


@dataclass
class RetrievalConfig:
    per_direct_limit: int = 25
    per_strong_proxy_limit: int = 20
    per_early_signal_limit: int = 10
    global_limit: int = 240
    per_event_limit: int = 3
    direct_event_limit: int = 14
    strong_proxy_event_limit: int = 10
    early_signal_event_limit: int = 6


def _load_markets_from_json_cache(status: str = "open") -> list[dict[str, Any]]:
    if not MARKETS_CACHE_FILE.exists():
        return []
    try:
        payload = json.loads(MARKETS_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    markets = payload.get("markets", [])
    if not isinstance(markets, list):
        return []
    if status:
        markets = [market for market in markets if market.get("status") == status]
    return [market for market in markets if isinstance(market, dict)]


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
        return 0.0, "timeframe_unknown"
    if start and close_date < start:
        delta = (start - close_date).days
        if delta > 60:
            return -2.5, "earlier_than_thesis_but_signal"
        return -1.0, "earlier_than_thesis_but_signal"
    if close_date <= end:
        return 8.0, "timeframe_aligned"
    delta = (close_date - end).days
    if delta <= 45:
        return 1.0, "slightly_beyond_thesis_window"
    if delta <= 180:
        return -2.5, "later_than_thesis_window"
    return -6.0, "much_later_than_thesis_window"


def _liquidity_score(market: dict[str, Any]) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    volume = float(market.get("volume") or 0.0)
    mid = market.get("mid_price")
    if mid is None:
        score -= 4.0
        reasons.append("missing_price")
    if volume <= 0:
        score -= 3.0
        reasons.append("zero_volume")
    elif volume >= 5000:
        score += 3.0
        reasons.append("liquidity_ok")
    elif volume >= 500:
        score += 1.5
        reasons.append("liquidity_ok")
    else:
        reasons.append("thin_liquidity")
    return score, reasons


def _ladder_key(market: dict[str, Any]) -> str:
    title = market.get("question") or market.get("yes_sub_title") or market.get("ticker")
    return re.sub(r"\d+", "#", title.lower())


def _candidate_payload(
    market: dict[str, Any],
    event: dict[str, Any],
    exposure: dict[str, Any],
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
        "route_ring": exposure.get("route_ring", "direct"),
        "yes_price": yes_price,
        "no_price": None if yes_price is None else round(max(0.0, min(1.0, 1.0 - float(yes_price))), 4),
        "volume": market.get("volume"),
        "retrieval_score": round(score, 3),
        "retrieval_reasons": reasons[:6],
    }


def _market_to_dict(market: Any) -> dict[str, Any]:
    if isinstance(market, dict):
        return market
    return {
        "ticker": getattr(market, "ticker", ""),
        "event_ticker": getattr(market, "event_ticker", ""),
        "question": getattr(market, "question", ""),
        "yes_sub_title": getattr(market, "yes_sub_title", ""),
        "no_sub_title": getattr(market, "no_sub_title", ""),
        "yes_bid": getattr(market, "yes_bid", None),
        "yes_ask": getattr(market, "yes_ask", None),
        "last_price": getattr(market, "last_price", None),
        "mid_price": getattr(market, "mid_price", None),
        "volume": getattr(market, "volume", None),
        "status": getattr(market, "status", ""),
        "close_time": getattr(market, "close_time", ""),
        "close_date": getattr(market, "close_date", ""),
        "rules_primary": getattr(market, "rules_primary", ""),
        "rules_secondary": getattr(market, "rules_secondary", ""),
    }


def _group_markets_by_event(markets: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for market in markets:
        event_ticker = market.get("event_ticker", "")
        if event_ticker:
            grouped[event_ticker].append(market)
    return grouped


def _event_query_terms(exposure: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for value in exposure.get("search_terms", []):
        value = (value or "").strip()
        if value and value not in terms:
            terms.append(value)
    for value in exposure.get("resolution_features", []):
        value = (value or "").strip()
        if value and value not in terms:
            terms.append(value)
    exposure_name = (exposure.get("exposure_name") or "").strip()
    if exposure_name and exposure_name not in terms:
        terms.append(exposure_name)
    return terms[:8]


def _ring_event_limit(route_ring: str, config: RetrievalConfig) -> int:
    if route_ring == "direct":
        return config.direct_event_limit
    if route_ring == "strong_proxy":
        return config.strong_proxy_event_limit
    return config.early_signal_event_limit


def _search_events_for_exposure(exposure: dict[str, Any], config: RetrievalConfig) -> list[dict[str, Any]]:
    route_ring = exposure.get("route_ring", "direct")
    event_limit = _ring_event_limit(route_ring, config)
    query_terms = _event_query_terms(exposure)
    if not query_terms:
        return []

    ranked: dict[str, dict[str, Any]] = {}
    search_queries = [
        " ".join(query_terms[:4]),
        " ".join(query_terms[:2]),
        query_terms[0],
    ]
    for query in search_queries:
        query = query.strip()
        if not query:
            continue
        try:
            fts_matches = search_events_fts(query, limit=event_limit * 3)
        except Exception:
            fts_matches = []
        try:
            plain_matches = search_events(query, limit=event_limit * 2)
        except Exception:
            plain_matches = []
        for event in [*fts_matches, *plain_matches]:
            event_ticker = event.get("event_ticker", "")
            if not event_ticker:
                continue
            haystack = _tokenize(
                " ".join(
                    [
                        event.get("title", ""),
                        event.get("sub_title", ""),
                        event.get("event_ticker", ""),
                        event.get("series_ticker", ""),
                        event.get("category", ""),
                    ]
                )
            )
            score = len(_tokenize(query) & haystack) * 2.0 + len(_tokenize(" ".join(query_terms)) & haystack)
            existing = ranked.get(event_ticker)
            if existing is None or score > existing["_event_score"]:
                ranked[event_ticker] = {**event, "_event_score": score}

    events = sorted(ranked.values(), key=lambda event: (-event["_event_score"], event.get("event_ticker", "")))
    return [{k: v for k, v in event.items() if k != "_event_score"} for event in events[:event_limit]]


def _load_json_markets_by_event(status: str = "open") -> dict[str, list[dict[str, Any]]]:
    return _group_markets_by_event(_load_markets_from_json_cache(status=status))


def _fetch_event_markets(
    event_tickers: list[str],
    *,
    json_markets_by_event: dict[str, list[dict[str, Any]]] | None = None,
    live_market_fetcher: Callable[[list[str]], list[Any]] | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], set[str]]:
    results: dict[str, list[dict[str, Any]]] = defaultdict(list)
    sources: set[str] = set()
    if not event_tickers:
        return results, sources

    try:
        cached_rows = get_markets_for_events(event_tickers)
    except Exception:
        cached_rows = []
    if cached_rows:
        for row in cached_rows:
            results[row.get("event_ticker", "")].append(row)
        sources.add("event_cache_db")

    missing = [ticker for ticker in event_tickers if not results.get(ticker)]
    if missing and json_markets_by_event:
        for ticker in missing:
            rows = json_markets_by_event.get(ticker, [])
            if rows:
                results[ticker].extend(rows)
                sources.add("json_cache")
        missing = [ticker for ticker in event_tickers if not results.get(ticker)]

    if missing and live_market_fetcher:
        try:
            live_rows = [_market_to_dict(market) for market in live_market_fetcher(missing)]
        except Exception:
            live_rows = []
        if live_rows:
            for row in live_rows:
                results[row.get("event_ticker", "")].append(row)
            sources.add("live_event_fetch")

    return results, sources


def _score_market_for_exposure(
    market: dict[str, Any],
    event: dict[str, Any],
    exposure: dict[str, Any],
    *,
    start: date | None,
    end: date | None,
    embedding_scores: dict[tuple[str, str], float] | None,
) -> dict[str, Any] | None:
    route_ring = exposure.get("route_ring", "direct")
    search_tokens = _tokenize(" ".join(exposure.get("search_terms", [])))
    negative_tokens = _tokenize(" ".join(exposure.get("negative_search_terms", [])))
    resolution_tokens = _tokenize(" ".join(exposure.get("resolution_features", [])))

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
    matched = search_tokens & haystack
    resolution_matched = resolution_tokens & haystack
    if not matched and not resolution_matched:
        return None

    negative_hits = negative_tokens & haystack
    if negative_hits and len(negative_hits) >= max(1, len(matched)) and route_ring == "direct":
        return None

    score = 0.0
    reasons: list[str] = []
    if matched:
        score += 4.0 + min(len(matched), 4) * 1.5
        reasons.append("exact_term_match")
    if resolution_matched:
        score += 2.5 + min(len(resolution_matched), 3)
        reasons.append("semantic_match")
    if negative_hits:
        score -= min(4.0, len(negative_hits) * 1.5)
        reasons.append("negative_term_penalty")

    tf_score, tf_reason = _timeframe_score(_parse_date(market.get("close_date")), start, end)
    if tf_score <= -100:
        return None
    score += tf_score
    reasons.append(tf_reason)

    liquidity_score, liquidity_reasons = _liquidity_score(market)
    score += liquidity_score
    reasons.extend(liquidity_reasons)

    if exposure.get("tier") == "direct_thesis":
        score += 1.0
    if route_ring == "strong_proxy":
        score += 0.25
        reasons.append("related_mechanism")
    elif route_ring == "early_signal":
        score += 0.15
        reasons.append("broad_proxy")
    if embedding_scores:
        embed = embedding_scores.get((exposure.get("exposure_name", ""), market.get("ticker", "")))
        if embed is not None:
            score += embed * 3.0
            reasons.append("semantic_match")

    return {
        "market": market,
        "event": event,
        "exposure": exposure,
        "score": score,
        "reasons": list(dict.fromkeys(reasons)),
        "ladder_key": _ladder_key(market),
    }


def _collect_corpus_rows(
    exposures: list[dict[str, Any]],
    *,
    config: RetrievalConfig,
    event_lookup: dict[str, dict[str, Any]],
    start: date | None,
    end: date | None,
    embedding_scores: dict[tuple[str, str], float] | None,
) -> tuple[dict[str, list[dict[str, Any]]], str, int]:
    market_source = "db"
    try:
        market_rows = get_all_markets(status="open")
    except Exception:
        market_rows = []
    if not market_rows:
        market_rows = _load_markets_from_json_cache(status="open")
        market_source = "json_cache" if market_rows else "empty"

    scored_by_exposure: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if not market_rows:
        return scored_by_exposure, market_source, 0

    for exposure in exposures:
        name = exposure.get("exposure_name", "")
        for market in market_rows:
            event = event_lookup.get(market.get("event_ticker", ""), {})
            scored = _score_market_for_exposure(
                market,
                event,
                exposure,
                start=start,
                end=end,
                embedding_scores=embedding_scores,
            )
            if scored is not None:
                scored_by_exposure[name].append(scored)
    return scored_by_exposure, market_source, len(market_rows)


def retrieve_markets_for_exposures(
    exposures: list[dict[str, Any]],
    belief_summary: dict[str, Any],
    *,
    config: RetrievalConfig | None = None,
    embedding_scores: dict[tuple[str, str], float] | None = None,
    live_market_fetcher: Callable[[list[str]], list[Any]] | None = None,
) -> dict[str, Any]:
    config = config or RetrievalConfig()
    start, end = _days_from_timeframe(belief_summary)
    global_candidates = 0
    grouped: list[dict[str, Any]] = []
    event_lookup = get_event_lookup()
    json_markets_by_event = _load_json_markets_by_event(status="open")

    corpus_rows_by_exposure, corpus_market_source, corpus_market_count = _collect_corpus_rows(
        exposures,
        config=config,
        event_lookup=event_lookup,
        start=start,
        end=end,
        embedding_scores=embedding_scores,
    )

    total_event_market_rows = 0
    retrieval_sources: set[str] = set()

    for exposure in exposures:
        route_ring = exposure.get("route_ring", "direct")
        per_exposure_limit = (
            config.per_direct_limit if route_ring == "direct"
            else config.per_strong_proxy_limit if route_ring == "strong_proxy"
            else config.per_early_signal_limit
        )
        exposure_name = exposure.get("exposure_name", "")
        ranked_rows: dict[str, dict[str, Any]] = {}

        candidate_events = _search_events_for_exposure(exposure, config)
        event_tickers = [event.get("event_ticker", "") for event in candidate_events if event.get("event_ticker")]
        event_markets_by_event, sources = _fetch_event_markets(
            event_tickers,
            json_markets_by_event=json_markets_by_event,
            live_market_fetcher=live_market_fetcher,
        )
        retrieval_sources.update(sources)
        total_event_market_rows += sum(len(rows) for rows in event_markets_by_event.values())

        for event in candidate_events:
            event_ticker = event.get("event_ticker", "")
            if event_ticker:
                event_lookup[event_ticker] = event
            for market in event_markets_by_event.get(event_ticker, []):
                scored = _score_market_for_exposure(
                    market,
                    event,
                    exposure,
                    start=start,
                    end=end,
                    embedding_scores=embedding_scores,
                )
                if scored is None:
                    continue
                ticker = scored["market"].get("ticker", "")
                existing = ranked_rows.get(ticker)
                if existing is None or scored["score"] > existing["score"]:
                    ranked_rows[ticker] = scored

        corpus_rows = corpus_rows_by_exposure.get(exposure_name, [])
        if len(ranked_rows) < max(4, per_exposure_limit // 2):
            for scored in corpus_rows:
                ticker = scored["market"].get("ticker", "")
                existing = ranked_rows.get(ticker)
                if existing is None or scored["score"] > existing["score"]:
                    ranked_rows[ticker] = scored

        rows = sorted(
            ranked_rows.values(),
            key=lambda item: (
                -item["score"],
                -float(item["market"].get("volume") or 0.0),
                item["market"].get("ticker", ""),
            ),
        )

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
            candidates.append(
                _candidate_payload(row["market"], row["event"], row["exposure"], row["score"], row["reasons"])
            )
            seen_events[event_ticker] = seen_events.get(event_ticker, 0) + 1
            seen_ladders.add(ladder_id)
            global_candidates += 1
            if len(candidates) >= per_exposure_limit:
                break

        grouped.append({
            "exposure_name": exposure_name,
            "exposure": exposure,
            "candidates": candidates,
        })

    if retrieval_sources:
        if corpus_market_count:
            market_source = "hybrid_event_first"
        else:
            market_source = "+".join(sorted(retrieval_sources))
    else:
        market_source = corpus_market_source

    return {
        "exposure_candidates": grouped,
        "market_source": market_source,
        "market_count": total_event_market_rows or corpus_market_count,
        "event_market_count": total_event_market_rows,
        "corpus_market_count": corpus_market_count,
    }
