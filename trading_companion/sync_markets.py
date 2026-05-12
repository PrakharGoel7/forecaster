"""Daily sync — pulls all open Kalshi markets and writes them to markets_cache.json.

Run manually or on a schedule:
    python sync_markets.py

The cache stores the full set of open markets with the lightweight fields most
useful for browsing, debugging, and downstream filtering.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
import httpx

load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")
load_dotenv(Path(__file__).parent.parent / "forecaster" / ".env")

from kalshi import KalshiClient
from cache_paths import MARKETS_CACHE_FILE
from market_cache_db import append_markets_to_cache_db, init_market_cache_db

CACHE_FILE = MARKETS_CACHE_FILE
CHECKPOINT_EVERY_PAGES = 10
BASE_DELAY_SECONDS = 0.1
MAX_RETRIES = 8


def _write_cache(all_markets: list[dict]) -> None:
    payload = {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "total_markets": len(all_markets),
        "markets": all_markets,
    }
    CACHE_FILE.write_text(json.dumps(payload, indent=2))


def _is_rate_limit_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429
    message = str(exc).lower()
    return "429" in message or "rate limit" in message or "too many requests" in message


def sync(verbose: bool = True) -> int:
    client = KalshiClient.from_env()

    all_markets: list[dict] = []
    seen_tickers: set[str] = set()
    cursor = None
    page = 0
    init_market_cache_db()

    while True:
        markets = None
        next_cursor = None
        for attempt in range(MAX_RETRIES):
            try:
                markets, next_cursor = client.get_markets(limit=200, status="open", cursor=cursor)
                break
            except Exception as exc:
                if not _is_rate_limit_error(exc):
                    raise
                delay = min(30.0, BASE_DELAY_SECONDS * (2 ** attempt))
                if verbose:
                    print(
                        f"\n  Rate limited by Kalshi on page {page + 1}; "
                        f"sleeping {delay:.1f}s before retry {attempt + 1}/{MAX_RETRIES}...",
                        end="",
                        flush=True,
                    )
                time.sleep(delay)
        if markets is None:
            raise RuntimeError(f"Failed to fetch page {page + 1} after {MAX_RETRIES} retries")

        cursor = next_cursor
        if not markets:
            break

        added = 0
        kept_batch: list[dict] = []
        for market in markets:
            if market.ticker in seen_tickers:
                continue
            seen_tickers.add(market.ticker)
            kept_market = {
                "ticker": market.ticker,
                "event_ticker": market.event_ticker,
                "question": market.question,
                "yes_sub_title": market.yes_sub_title,
                "no_sub_title": getattr(market, "no_sub_title", ""),
                "yes_bid": market.yes_bid,
                "yes_ask": market.yes_ask,
                "last_price": market.last_price,
                "mid_price": market.mid_price,
                "volume": market.volume,
                "status": market.status,
                "close_time": market.close_time,
                "close_date": market.close_date,
                "rules_primary": market.rules_primary,
                "rules_secondary": getattr(market, "rules_secondary", ""),
            }
            all_markets.append(kept_market)
            kept_batch.append(kept_market)
            added += 1
        append_markets_to_cache_db(kept_batch)

        page += 1
        if page % CHECKPOINT_EVERY_PAGES == 0:
            _write_cache(all_markets)
        if verbose:
            print(
                f"  Page {page}: +{len(markets)} markets fetched, "
                f"{added} new, {len(all_markets)} total ...",
                end="\r",
            )

        if not cursor:
            break

        time.sleep(BASE_DELAY_SECONDS)

    _write_cache(all_markets)

    # Archive daily price snapshot for performance tracking
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent.parent / "forecaster"))
        import db as _forecaster_db
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        saved = _forecaster_db.save_price_snapshots(all_markets, today)
        if verbose:
            print(f"Archived {saved} price snapshots for {today}")
    except Exception as _exc:
        if verbose:
            print(f"[warn] price snapshot archiving skipped: {_exc}")

    if verbose:
        print(f"\nSynced {len(all_markets)} open markets → {CACHE_FILE}")

    return len(all_markets)


if __name__ == "__main__":
    try:
        count = sync()
        sys.exit(0)
    except Exception as exc:
        print(f"[ERROR] Sync failed: {exc}", file=sys.stderr)
        sys.exit(1)
