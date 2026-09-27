from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trading_companion import sync_events, sync_markets


class _Market:
    ticker = "KXRATE-27-JUN-CUT"
    event_ticker = "KXRATE-27-JUN"
    question = "Will the Federal Reserve cut rates before July 2027?"
    yes_sub_title = "Yes"
    no_sub_title = "No"
    yes_bid = 0.42
    yes_ask = 0.44
    last_price = 0.43
    mid_price = 0.43
    volume = 1200.0
    status = "open"
    close_time = "2027-06-30T23:59:00Z"
    close_date = "2027-06-30"
    rules_primary = "Resolves yes if the target range is reduced."
    rules_secondary = ""


class CacheSyncTests(unittest.TestCase):
    def test_market_sync_excludes_combos_and_atomically_replaces_cache(self):
        class Client:
            def __init__(self):
                self.calls = []

            def get_markets(self, **kwargs):
                self.calls.append(kwargs)
                return [_Market()], None

        client = Client()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_json = root / "markets_cache.json"
            cache_db = root / "markets_cache.db"
            cache_json.write_text("previous-json", encoding="utf-8")
            cache_db.write_bytes(b"previous-db")

            with patch.object(sync_markets.KalshiClient, "from_env", return_value=client):
                count = sync_markets.sync(
                    verbose=False,
                    cache_file=cache_json,
                    cache_db_file=cache_db,
                    archive_snapshots=False,
                )

            self.assertEqual(count, 1)
            self.assertEqual(client.calls[0]["mve_filter"], "exclude")
            self.assertEqual(client.calls[0]["limit"], 1000)
            payload = json.loads(cache_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["total_markets"], 1)
            self.assertEqual(payload["markets"][0]["ticker"], _Market.ticker)
            with sqlite3.connect(cache_db) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM markets").fetchone()[0], 1)
                self.assertEqual(conn.execute("PRAGMA quick_check").fetchone()[0], "ok")
            self.assertEqual(list(root.glob(".*.tmp*")), [])

    def test_market_sync_retains_highest_volume_when_catalog_is_large(self):
        class Market(_Market):
            def __init__(self, ticker: str, volume: float):
                self.ticker = ticker
                self.volume = volume

        class Client:
            def get_markets(self, **kwargs):
                return ([Market("LOW", 1), Market("HIGH", 100), Market("MID", 20)], None)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_json = root / "markets_cache.json"
            cache_db = root / "markets_cache.db"
            with (
                patch.object(sync_markets.KalshiClient, "from_env", return_value=Client()),
                patch.object(sync_markets, "MAX_MARKETS", 2),
            ):
                sync_markets.sync(
                    verbose=False,
                    cache_file=cache_json,
                    cache_db_file=cache_db,
                    archive_snapshots=False,
                )

            payload = json.loads(cache_json.read_text(encoding="utf-8"))
            self.assertEqual([market["ticker"] for market in payload["markets"]], ["HIGH", "MID"])

    def test_failed_market_sync_preserves_previous_cache(self):
        class Client:
            def get_markets(self, **kwargs):
                raise RuntimeError("upstream unavailable")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_json = root / "markets_cache.json"
            cache_db = root / "markets_cache.db"
            cache_json.write_text("previous-json", encoding="utf-8")
            cache_db.write_bytes(b"previous-db")

            with patch.object(sync_markets.KalshiClient, "from_env", return_value=Client()):
                with self.assertRaisesRegex(RuntimeError, "upstream unavailable"):
                    sync_markets.sync(
                        verbose=False,
                        cache_file=cache_json,
                        cache_db_file=cache_db,
                        archive_snapshots=False,
                    )

            self.assertEqual(cache_json.read_text(encoding="utf-8"), "previous-json")
            self.assertEqual(cache_db.read_bytes(), b"previous-db")
            self.assertEqual(list(root.glob(".*.tmp*")), [])

    def test_event_sync_replaces_cache_only_after_completion(self):
        class Client:
            def get_events(self, **kwargs):
                return ([{
                    "event_ticker": "KXRATE-27-JUN",
                    "series_ticker": "KXRATE",
                    "title": "Federal Reserve decision",
                    "sub_title": "June 2027",
                    "category": "Economics",
                }], None)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_json = root / "events_cache.json"
            cache_db = root / "events_cache.db"
            with patch.object(sync_events.KalshiClient, "from_env", return_value=Client()):
                count = sync_events.sync(
                    verbose=False,
                    cache_file=cache_json,
                    cache_db_file=cache_db,
                )

            self.assertEqual(count, 1)
            payload = json.loads(cache_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["total_events"], 1)
            with sqlite3.connect(cache_db) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)
                self.assertEqual(conn.execute("PRAGMA quick_check").fetchone()[0], "ok")


if __name__ == "__main__":
    unittest.main()
