"""Account ownership, creator discovery, and published basket social counts."""

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from jose import jwt

from forecaster import db, trading_db
from prism.api import main


def _basket(owner: str, *, public: bool = True) -> int:
    return db.save_basket(
        title="A thesis", summary="A summary", core_belief="A thesis", mode="manual",
        time_horizon="2027", timeframe_start="now", timeframe_end="2027",
        resolution_target="Test resolution", mechanism="Test", scope="Test",
        key_drivers=[], belief_summary={}, analysis={}, basket={"holdings": []},
        total_notional=100, screened_count=0, holdings=[], is_public=public,
        user_id=owner,
    )


class BasketSocialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / "test.sqlite"

        def connect():
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            return conn

        self.patches = [
            patch.object(db, "_use_pg", return_value=False),
            patch.object(db, "_sqlite_conn", side_effect=connect),
            patch.object(main, "_SUPABASE_JWT_SECRET", "test-signing-secret"),
            patch.object(main, "_SUPABASE_URL", ""),
        ]
        for p in self.patches:
            p.start()
        self.client = TestClient(main.app)
        db.save_profile("alice-id", "alice")
        db.save_profile("bob-id", "bob")

    def auth(self, user_id: str) -> dict[str, str]:
        token = jwt.encode(
            {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            "test-signing-secret", algorithm="HS256",
        )
        return {"Authorization": f"Bearer {token}"}

    def tearDown(self):
        self.client.close()
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_creator_search_matches_username_and_supports_offset(self):
        db.save_profile("alicia-id", "alicia")
        self.assertEqual(
            [c["username"] for c in self.client.get("/api/creators", params={"q": "ALI", "limit": 1}).json()],
            ["alice"],
        )
        self.assertEqual(
            [c["username"] for c in self.client.get("/api/creators", params={"q": "ali", "limit": 1, "offset": 1}).json()],
            ["alicia"],
        )
        self.assertEqual(self.client.get("/api/creators", params={"limit": 101}).status_code, 400)

    def test_display_name_is_searchable_and_shown_on_public_basket(self):
        conn = db._conn()
        try:
            conn.execute("UPDATE profiles SET display_name = ? WHERE user_id = ?", ("Alice Smith", "alice-id"))
            conn.commit()
        finally:
            conn.close()
        creators = self.client.get("/api/creators", params={"q": "SMITH"})
        self.assertEqual(creators.status_code, 200)
        self.assertEqual([(c["username"], c["display_name"]) for c in creators.json()], [("alice", "Alice Smith")])
        basket_id = _basket("alice-id")
        basket = self.client.get(f"/api/baskets/{basket_id}")
        self.assertEqual(basket.status_code, 200)
        self.assertEqual(basket.json()["display_name"], "Alice Smith")

    def test_manual_basket_requires_account_and_private_basket_has_owner(self):
        payload = {
            "title": "Test basket", "summary": "Test", "is_public": False,
            "holdings": [{
                "ticker": "TEST-TICKER", "event_ticker": "TEST", "question": "Will it happen?",
                "market_price": 0.5, "close_date": "2027-01-01", "side": "YES",
                "weight_dollars": 100,
            }],
        }
        self.assertEqual(self.client.post("/api/baskets/manual", json=payload).status_code, 401)
        self.assertEqual(db.get_baskets(public_only=False), [])

        response = self.client.post("/api/baskets/manual", json=payload, headers=self.auth("alice-id"))
        self.assertEqual(response.status_code, 200, response.text)
        saved = response.json()["basket"]
        self.assertEqual(saved["user_id"], "alice-id")
        self.assertEqual(saved["is_public"], 0)
        self.assertIsNotNone(db.get_basket(saved["id"], user_id="alice-id"))
        self.assertIsNone(db.get_basket(saved["id"], user_id="bob-id"))
        self.assertIsNone(db.get_basket(saved["id"]))
        self.assertEqual(self.client.get(f"/api/baskets/{saved['id']}").status_code, 404)
        self.assertEqual(
            self.client.get(f"/api/baskets/{saved['id']}", headers=self.auth("bob-id")).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(f"/api/baskets/{saved['id']}", headers=self.auth("alice-id")).status_code,
            200,
        )
        self.assertEqual(self.client.get("/api/baskets/public").json(), [])

    def test_signed_account_can_create_profile_publish_and_follow(self):
        headers = self.auth("cara-id")
        self.assertEqual(self.client.get("/api/profiles/me", headers=headers).status_code, 404)
        basket_id = _basket("cara-id", public=False)
        self.assertEqual(
            self.client.patch(f"/api/baskets/{basket_id}/visibility", json={"is_public": True},
                              headers=headers).status_code,
            400,
        )
        profile = self.client.post("/api/profiles", json={"username": "cara"}, headers=headers)
        self.assertEqual(profile.status_code, 200, profile.text)
        self.assertEqual(self.client.get("/api/profiles/me", headers=headers).json()["username"], "cara")
        self.assertEqual(
            self.client.patch(f"/api/baskets/{basket_id}/visibility", json={"is_public": True},
                              headers=self.auth("bob-id")).status_code,
            404,
        )
        self.assertEqual(
            self.client.patch(f"/api/baskets/{basket_id}/visibility", json={"is_public": True},
                              headers=headers).status_code,
            200,
        )
        self.assertIsNotNone(db.get_basket(basket_id))
        follow = self.client.post("/api/follows/cara", headers=self.auth("bob-id"))
        self.assertEqual(follow.status_code, 200, follow.text)
        self.assertEqual(follow.json()["follower_count"], 1)

    def test_watchlist_count_is_distinct_and_private_baskets_stay_hidden(self):
        public_id = _basket("alice-id")
        private_id = _basket("alice-id", public=False)
        db.bookmark_basket("bob-id", public_id)
        db.bookmark_basket("bob-id", public_id)
        self.assertEqual(db.get_watchlist_counts([public_id, private_id]), {public_id: 1})
        self.assertEqual([b["id"] for b in db.get_baskets(public_only=True)], [public_id])
        self.assertEqual([b["id"] for b in db.get_baskets(by_username="alice")], [public_id])
        self.assertEqual([b["id"] for b in db.get_bookmarks("bob-id")], [public_id])

    def test_public_counters_use_confirmed_fills_and_distinct_users(self):
        basket_id = _basket("alice-id")
        for fill_id, user_id, cost in (
            ("fill-1", "bob-id", "10.00"),
            ("fill-2", "bob-id", "5.50"),
            ("fill-3", "alice-id", "20.00"),
        ):
            trading_db.insert_fill({
                "fill_id": fill_id, "investment_id": "investment-test", "user_id": user_id,
                "basket_id": basket_id, "order_id": fill_id, "ticker": "TEST", "side": "yes",
                "count": "1", "price_dollars": "0.50", "fee_dollars": "0.00",
                "cost_dollars": cost, "created_at": "2026-10-16T00:00:00Z",
            })
        detail = self.client.get(f"/api/baskets/{basket_id}")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["investor_count"], 2)
        self.assertEqual(detail.json()["invested_dollars"], 35.5)
        self.assertEqual(detail.json()["watchlist_count"], 0)

        watch = self.client.post(f"/api/bookmarks/{basket_id}", headers=self.auth("bob-id"))
        self.assertEqual(watch.status_code, 200, watch.text)
        self.assertEqual(watch.json()["watchlist_count"], 1)
        self.assertEqual(self.client.get(f"/api/baskets/{basket_id}").json()["watchlist_count"], 1)
        cards = self.client.get("/api/baskets/public")
        self.assertEqual(cards.status_code, 200, cards.text)
        self.assertEqual(cards.json()[0]["investor_count"], 2)
        self.assertEqual(cards.json()[0]["watchlist_count"], 1)
        unwatch = self.client.delete(f"/api/bookmarks/{basket_id}", headers=self.auth("bob-id"))
        self.assertEqual(unwatch.json()["watchlist_count"], 0)

    def test_discovery_and_watchlist_surface_storage_failures(self):
        with patch.object(db, "get_baskets", side_effect=RuntimeError("storage unavailable")):
            with self.assertLogs("prism.db", level="ERROR"):
                self.assertEqual(self.client.get("/api/baskets").status_code, 503)
                self.assertEqual(self.client.get("/api/baskets/public").status_code, 503)
        with patch.object(db, "get_creators", side_effect=RuntimeError("storage unavailable")):
            with self.assertLogs("prism.db", level="ERROR"):
                self.assertEqual(self.client.get("/api/creators").status_code, 503)
        with patch.object(db, "get_bookmarks", side_effect=RuntimeError("storage unavailable")):
            with self.assertLogs("prism.db", level="ERROR"):
                self.assertEqual(self.client.get("/api/bookmarks", headers=self.auth("bob-id")).status_code, 503)
        with patch.object(db, "get_feed", side_effect=RuntimeError("storage unavailable")):
            with self.assertLogs("prism.db", level="ERROR"):
                self.assertEqual(self.client.get("/api/feed", headers=self.auth("bob-id")).status_code, 503)


if __name__ == "__main__":
    unittest.main()
