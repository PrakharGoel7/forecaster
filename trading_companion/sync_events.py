"""Daily sync — pulls all open Kalshi events and writes them to events_cache.json.

Run once per day (or manually before a session):
    python sync_events.py

The cache stores only the lightweight fields needed for screening:
event_ticker, series_ticker, title, sub_title, category.
Real-time market details are fetched on-demand after screening.
"""
from __future__ import annotations

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
        EVENTS_CACHE_DB_FILE,
        EVENTS_CACHE_FILE,
        discard_staging_files,
        publish_cache_pair,
        staging_path,
    )
    from .event_cache_db import append_events_to_cache_db, init_event_cache_db
except ImportError:
    from kalshi import KalshiClient
    from cache_paths import (
        EVENTS_CACHE_DB_FILE,
        EVENTS_CACHE_FILE,
        discard_staging_files,
        publish_cache_pair,
        staging_path,
    )
    from event_cache_db import append_events_to_cache_db, init_event_cache_db

CACHE_FILE = EVENTS_CACHE_FILE

BASE_DELAY_SECONDS = 0.1
MAX_RETRIES = 8
MAX_EVENTS = int(os.environ.get("EVENT_CACHE_MAX_EVENTS", "100000"))
MAX_SECONDS = int(os.environ.get("EVENT_CACHE_MAX_SECONDS", "900"))


def _write_cache(all_events: list[dict], cache_file: Path) -> None:
    payload = {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "total_events": len(all_events),
        "events": all_events,
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
) -> int:
    target_json = Path(cache_file or CACHE_FILE)
    target_db = Path(cache_db_file or EVENTS_CACHE_DB_FILE)
    staged_json = staging_path(target_json)
    staged_db = staging_path(target_db)
    client = KalshiClient.from_env()

    all_events: list[dict] = []
    seen_tickers: set[str] = set()
    seen_cursors: set[str] = set()
    cursor = None
    page = 0
    started_at = time.monotonic()
    try:
        init_event_cache_db(staged_db, staging=True)
        while True:
            if time.monotonic() - started_at > MAX_SECONDS:
                raise RuntimeError(
                    f"Event refresh exceeded {MAX_SECONDS} seconds; preserving the previous cache"
                )

            batch = None
            next_cursor = None
            for attempt in range(MAX_RETRIES):
                try:
                    batch, next_cursor = client.get_events(limit=200, status="open", cursor=cursor)
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
            if batch is None:
                raise RuntimeError(f"Failed to fetch page {page + 1} after {MAX_RETRIES} retries")
            if not batch:
                break

            kept_batch: list[dict] = []
            for event in batch:
                ticker = event.get("event_ticker", "")
                if not ticker or ticker in seen_tickers:
                    continue
                seen_tickers.add(ticker)
                kept_batch.append({
                    "event_ticker": ticker,
                    "series_ticker": event.get("series_ticker", ""),
                    "title": event.get("title", ""),
                    "sub_title": event.get("sub_title", ""),
                    "category": event.get("category", ""),
                })

            if len(all_events) + len(kept_batch) > MAX_EVENTS:
                raise RuntimeError(
                    f"Event refresh exceeded the {MAX_EVENTS}-event safety limit; "
                    "preserving the previous cache"
                )

            all_events.extend(kept_batch)
            append_events_to_cache_db(kept_batch, staged_db)
            page += 1
            if verbose:
                print(
                    f"  Page {page}: +{len(batch)} events fetched, "
                    f"{len(all_events)} kept after filtering ...",
                    end="\r",
                )

            if not next_cursor:
                break
            if next_cursor in seen_cursors:
                raise RuntimeError("Kalshi returned a repeated event cursor; preserving the previous cache")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
            time.sleep(BASE_DELAY_SECONDS)

        _write_cache(all_events, staged_json)
        publish_cache_pair(
            staged_json=staged_json,
            target_json=target_json,
            staged_db=staged_db,
            target_db=target_db,
        )
    finally:
        discard_staging_files(staged_json, staged_db)

    if verbose:
        print(f"\nSynced {len(all_events)} events → {target_json}")

        from collections import Counter
        cats = Counter(e["category"] for e in all_events)
        for cat, count in cats.most_common():
            print(f"  {cat}: {count}")

    return len(all_events)


if __name__ == "__main__":
    try:
        count = sync()
        sys.exit(0)
    except Exception as e:
        print(f"[ERROR] Sync failed: {e}", file=sys.stderr)
        sys.exit(1)
