"""Daily sync — atomically caches open, non-combo Kalshi markets.

Run manually or on a schedule:
    python sync_markets.py

The cache excludes dynamically generated multivariate combinations, which are
not useful to Prism's thesis retrieval and can number in the millions.
"""
from __future__ import annotations

import heapq
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
import httpx

load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")
load_dotenv(Path(__file__).parent.parent / "forecaster" / ".env")

try:
    from .kalshi import KalshiClient
    from .cache_paths import (
        MARKETS_CACHE_DB_FILE,
        MARKETS_CACHE_FILE,
        discard_staging_files,
        publish_cache_pair,
        staging_path,
    )
    from .market_cache_db import append_markets_to_cache_db, init_market_cache_db
except ImportError:
    from kalshi import KalshiClient
    from cache_paths import (
        MARKETS_CACHE_DB_FILE,
        MARKETS_CACHE_FILE,
        discard_staging_files,
        publish_cache_pair,
        staging_path,
    )
    from market_cache_db import append_markets_to_cache_db, init_market_cache_db

CACHE_FILE = MARKETS_CACHE_FILE
PAGE_SIZE = 1000
BASE_DELAY_SECONDS = 0.1
MAX_RETRIES = 8
MAX_MARKETS = int(os.environ.get("MARKET_CACHE_MAX_MARKETS", "100000"))
MAX_SECONDS = int(os.environ.get("MARKET_CACHE_MAX_SECONDS", "1800"))


def _write_cache(all_markets: list[dict], cache_file: Path) -> None:
    payload = {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "total_markets": len(all_markets),
        "markets": all_markets,
    }
    cache_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _is_rate_limit_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429
    message = str(exc).lower()
    return "429" in message or "rate limit" in message or "too many requests" in message


def sync(
    verbose: bool = True,
    *,
    cache_file: Path | None = None,
    cache_db_file: Path | None = None,
    archive_snapshots: bool = True,
) -> int:
    target_json = Path(cache_file or CACHE_FILE)
    target_db = Path(cache_db_file or MARKETS_CACHE_DB_FILE)
    staged_json = staging_path(target_json)
    staged_db = staging_path(target_db)
    client = KalshiClient.from_env()

    selected_markets: list[tuple[tuple[float, str], int, dict]] = []
    seen_cursors: set[str] = set()
    cursor = None
    page = 0
    scanned_markets = 0
    started_at = time.monotonic()
    try:
        init_market_cache_db(staged_db, staging=True)
        while True:
            if time.monotonic() - started_at > MAX_SECONDS:
                raise RuntimeError(
                    f"Market refresh exceeded {MAX_SECONDS} seconds; preserving the previous cache"
                )

            markets = None
            next_cursor = None
            for attempt in range(MAX_RETRIES):
                try:
                    markets, next_cursor = client.get_markets(
                        limit=PAGE_SIZE,
                        status="open",
                        cursor=cursor,
                        mve_filter="exclude",
                    )
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
            if not markets:
                break

            for batch_index, market in enumerate(markets):
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
                rank = (float(kept_market["volume"] or 0.0), kept_market["ticker"])
                item = (rank, scanned_markets + batch_index, kept_market)
                if len(selected_markets) < MAX_MARKETS:
                    heapq.heappush(selected_markets, item)
                elif rank > selected_markets[0][0]:
                    heapq.heapreplace(selected_markets, item)
            scanned_markets += len(markets)
            page += 1
            if verbose:
                print(
                    f"  Page {page}: +{len(markets)} markets fetched, "
                    f"{scanned_markets} scanned, {len(selected_markets)} retained ...",
                    end="\r",
                )

            if not next_cursor:
                break
            if next_cursor in seen_cursors:
                raise RuntimeError("Kalshi returned a repeated market cursor; preserving the previous cache")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
            time.sleep(BASE_DELAY_SECONDS)

        deduplicated = {market["ticker"]: market for _, _, market in selected_markets}
        all_markets = sorted(
            deduplicated.values(),
            key=lambda market: (-float(market["volume"] or 0.0), market["ticker"]),
        )
        for start in range(0, len(all_markets), PAGE_SIZE):
            append_markets_to_cache_db(all_markets[start:start + PAGE_SIZE], staged_db)
        _write_cache(all_markets, staged_json)
        publish_cache_pair(
            staged_json=staged_json,
            target_json=target_json,
            staged_db=staged_db,
            target_db=target_db,
        )
    finally:
        discard_staging_files(staged_json, staged_db)

    # Archive daily price snapshots only after a complete cache was published.
    if archive_snapshots:
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
        print(
            f"\nSynced {len(all_markets)} highest-volume non-combo markets "
            f"from {scanned_markets} open markets → {target_json}"
        )

    return len(all_markets)


if __name__ == "__main__":
    try:
        count = sync()
        sys.exit(0)
    except Exception as exc:
        print(f"[ERROR] Sync failed: {exc}", file=sys.stderr)
        sys.exit(1)
