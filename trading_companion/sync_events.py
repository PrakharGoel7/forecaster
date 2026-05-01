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
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / "forecaster" / ".env")

from kalshi import KalshiClient

CACHE_FILE = Path(__file__).parent / "events_cache.json"

# Categories to skip — not useful for most beliefs
SKIP_CATEGORIES = {"Sports", "Entertainment", "Mentions"}


def sync(verbose: bool = True) -> int:
    client = KalshiClient.from_env()

    all_events: list[dict] = []
    cursor = None
    page = 0

    while True:
        params: dict = {"limit": 200, "status": "open"}
        if cursor:
            params["cursor"] = cursor

        resp = client._http.get("/events", params=params)
        resp.raise_for_status()
        data = resp.json()

        batch = data.get("events", [])
        if not batch:
            break

        for e in batch:
            cat = e.get("category", "")
            if cat in SKIP_CATEGORIES:
                continue
            all_events.append({
                "event_ticker": e.get("event_ticker", ""),
                "series_ticker": e.get("series_ticker", ""),
                "title": e.get("title", ""),
                "sub_title": e.get("sub_title", ""),
                "category": cat,
            })

        cursor = data.get("cursor")
        page += 1

        if verbose:
            print(f"  Page {page}: +{len(batch)} events fetched, "
                  f"{len(all_events)} kept after filtering ...", end="\r")

        if not cursor:
            break

    payload = {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "total_events": len(all_events),
        "events": all_events,
    }

    CACHE_FILE.write_text(json.dumps(payload, indent=2))

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
