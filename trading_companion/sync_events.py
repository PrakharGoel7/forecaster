"""Daily sync — pulls all open Kalshi events and writes them to events_cache.json.

Run once per day (or manually before a session):
    python sync_events.py

The cache stores only the lightweight fields needed for screening:
event_ticker, series_ticker, title, sub_title, category.
Real-time market details are fetched on-demand after screening.
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
from cache_paths import EVENTS_CACHE_FILE
from event_cache_db import append_events_to_cache_db, init_event_cache_db

CACHE_FILE = EVENTS_CACHE_FILE

# Categories to skip — not useful for most beliefs
SKIP_CATEGORIES = {"Sports", "Entertainment", "Mentions"}
CHECKPOINT_EVERY_PAGES = 10
BASE_DELAY_SECONDS = 0.1
MAX_RETRIES = 8


def _write_cache(all_events: list[dict]) -> None:
    payload = {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "total_events": len(all_events),
        "events": all_events,
    }
    CACHE_FILE.write_text(json.dumps(payload, indent=2))


def _is_rate_limit_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429
    message = str(exc).lower()
    return "429" in message or "rate limit" in message or "too many requests" in message


def sync(verbose: bool = True) -> int:
    client = KalshiClient.from_env()

    all_events: list[dict] = []
    cursor = None
    page = 0
    init_event_cache_db()

    while True:
        data = None
        for attempt in range(MAX_RETRIES):
            try:
                params: dict = {"limit": 200, "status": "open"}
                if cursor:
                    params["cursor"] = cursor
                resp = client._http.get("/events", params=params)
                resp.raise_for_status()
                data = resp.json()
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
        if data is None:
            raise RuntimeError(f"Failed to fetch page {page + 1} after {MAX_RETRIES} retries")

        batch = data.get("events", [])
        if not batch:
            break

        kept_batch: list[dict] = []
        for e in batch:
            cat = e.get("category", "")
            if cat in SKIP_CATEGORIES:
                continue
            kept_event = {
                "event_ticker": e.get("event_ticker", ""),
                "series_ticker": e.get("series_ticker", ""),
                "title": e.get("title", ""),
                "sub_title": e.get("sub_title", ""),
                "category": cat,
            }
            all_events.append(kept_event)
            kept_batch.append(kept_event)

        append_events_to_cache_db(kept_batch)

        cursor = data.get("cursor")
        page += 1
        if page % CHECKPOINT_EVERY_PAGES == 0:
            _write_cache(all_events)

        if verbose:
            print(f"  Page {page}: +{len(batch)} events fetched, "
                  f"{len(all_events)} kept after filtering ...", end="\r")

        if not cursor:
            break
        time.sleep(BASE_DELAY_SECONDS)

    _write_cache(all_events)

    if verbose:
        print(f"\nSynced {len(all_events)} events → {CACHE_FILE}")

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
