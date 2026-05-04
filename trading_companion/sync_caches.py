"""Refresh the Kalshi caches used by product features.

Runs the full open-markets sync first, then refreshes the lightweight event
cache used by the screener and recommendation enrichment paths.

Usage:
    python sync_caches.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")
load_dotenv(Path(__file__).parent.parent / "forecaster" / ".env")

from sync_events import sync as sync_events
from sync_markets import sync as sync_markets


def main() -> int:
    print("Refreshing full open-markets cache...")
    market_count = sync_markets(verbose=True)

    print("\nRefreshing event cache used by product screening...")
    event_count = sync_events(verbose=True)

    print(
        f"\nCache refresh complete: {market_count} markets synced, "
        f"{event_count} events synced."
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"[ERROR] Cache refresh failed: {exc}", file=sys.stderr)
        sys.exit(1)
