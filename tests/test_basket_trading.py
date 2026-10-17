"""End-to-end API tests using a simulated Kalshi exchange and isolated SQLite."""
from __future__ import annotations

import base64
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from fastapi.testclient import TestClient
import httpx
from jose import jwt

from forecaster import db, trading_db
from forecaster.kalshi import _KalshiAuth
from prism.api import main, trading_routes


class FakeMarketClient:
    def get_market(self, ticker):
        return SimpleNamespace(ticker=ticker, status="active", yes_bid=0.49,
                               yes_ask=0.51, close_time="2027-12-31T00:00:00Z")

    def get_candlesticks(self, tickers, start_ts, end_ts, period_interval):
        return {ticker: [] for ticker in tickers}


class FakeUserKalshiClient:
    orders_created = []
    fills = {}
    partial = False
    existing_positions = None

    def __init__(self, key_id, private_key_pem):
        self.key_id = key_id

    def balance(self):
        return {"balance_dollars": "1000.0000"}

    def positions(self):
        if self.existing_positions is not None:
            return self.existing_positions
        net = {}
        for order in self.orders_created:
            ticker = order["ticker"]
            delta = float(order["count"]) * (1 if order["side"] == "bid" else -1)
            net[ticker] = net.get(ticker, 0) + delta
        return [{"ticker": ticker, "position_fp": f"{count:.2f}"} for ticker, count in net.items()]

    def create_ioc_order(self, **kwargs):
        self.orders_created.append(kwargs)
        order_id = f"kalshi-{len(self.orders_created)}"
        filled_count = float(kwargs["count"]) / 2 if self.partial else float(kwargs["count"])
        self.fills[order_id] = [{"fill_id": f"fill-{len(self.orders_created)}",
                                 "order_id": order_id, "count_fp": f"{filled_count:.2f}",
                                 "yes_price_dollars": kwargs["price"],
                                 "no_price_dollars": str(1 - float(kwargs["price"])),
                                 "fee_cost": "0.0200", "created_time": datetime.now(timezone.utc).isoformat()}]
        return {"order_id": order_id, "fill_count": f"{filled_count:.2f}",
                "remaining_count": f"{float(kwargs['count']) - filled_count:.2f}"}

    def fills_for_order(self, order_id):
        return self.fills[order_id]

    def orders(self):
        return []


class BasketTradingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / "test.sqlite"

        def connect():
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            return conn

        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()).decode()
        self.patches = [
            patch.object(db, "_use_pg", return_value=False),
            patch.object(db, "_sqlite_conn", side_effect=connect),
            patch.object(main, "_SUPABASE_JWT_SECRET", "test-secret"),
            patch.object(main, "_SUPABASE_URL", ""),
            patch.object(main, "_get_client", return_value=FakeMarketClient()),
            patch.object(trading_routes, "UserKalshiClient", FakeUserKalshiClient),
            patch.dict(os.environ, {"KALSHI_CREDENTIALS_ENCRYPTION_KEY": Fernet.generate_key().decode(),
                                 "ENABLE_LIVE_TRADING": "false"}),
        ]
        for item in self.patches:
            item.start()
        FakeUserKalshiClient.orders_created = []
        FakeUserKalshiClient.fills = {}
        FakeUserKalshiClient.partial = False
        FakeUserKalshiClient.existing_positions = None
        self.client = TestClient(main.app)
        self.basket_id = db.save_basket(
            title="Two markets", summary="Test", core_belief="Test", mode="manual",
            time_horizon="2027", timeframe_start="now", timeframe_end="2027",
            resolution_target="Test", mechanism="Test", scope="Test", key_drivers=[],
            belief_summary={}, analysis={}, basket={}, total_notional=100,
            screened_count=2, is_public=True, user_id="alice", holdings=[
                {"ticker": "YES-MARKET", "event_ticker": "Y", "question": "Yes?", "side": "YES",
                 "role": "direct", "weight_dollars": 50, "rationale": "", "main_risk": "",
                 "market_price": 0.51, "close_date": "2027-12-31"},
                {"ticker": "NO-MARKET", "event_ticker": "N", "question": "No?", "side": "NO",
                 "role": "direct", "weight_dollars": 50, "rationale": "", "main_risk": "",
                 "market_price": 0.51, "close_date": "2027-12-31"},
            ])

    def tearDown(self):
        self.client.close()
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def auth(self, user_id="alice"):
        token = jwt.encode({"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                           "test-secret", algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}

    def connect(self):
        return self.client.put("/api/kalshi/credentials", headers=self.auth(),
                               json={"key_id": "secret-key-1234", "private_key_pem": self.private_key})

    def test_credentials_are_authenticated_encrypted_and_removable(self):
        self.assertEqual(self.client.get("/api/kalshi/credentials").status_code, 401)
        self.assertEqual(self.connect().status_code, 200)
        row = trading_db.get_connection("alice")
        self.assertNotIn("BEGIN PRIVATE KEY", str(row))
        self.assertNotIn("secret-key-1234", str(row))
        status = self.client.get("/api/kalshi/credentials", headers=self.auth()).json()
        self.assertTrue(status["connected"])
        self.assertTrue(status["key_id_masked"].endswith("1234"))
        self.assertFalse(self.client.get("/api/kalshi/credentials", headers=self.auth("bob")).json()["connected"])
        self.assertEqual(self.client.delete("/api/kalshi/credentials", headers=self.auth()).status_code, 200)
        self.assertIsNone(trading_db.get_connection("alice"))

    def test_ed25519_kalshi_signature_matches_documented_scheme(self):
        private = ed25519.Ed25519PrivateKey.generate()
        request = httpx.Request("GET", "https://external-api.kalshi.com/trade-api/v2/portfolio/balance")
        signed = next(_KalshiAuth("key-id", private).auth_flow(request))
        message = (signed.headers["KALSHI-ACCESS-TIMESTAMP"] + "GET" + signed.url.path).encode()
        private.public_key().verify(base64.b64decode(signed.headers["KALSHI-ACCESS-SIGNATURE"]), message)
        self.assertEqual(signed.headers["KALSHI-ACCESS-KEY"], "key-id")

    def test_invalid_private_key_is_not_reflected_in_error(self):
        secret = "SECRET_INVALID_PRIVATE_KEY_MATERIAL"
        response = self.client.put("/api/kalshi/credentials", headers=self.auth(),
                                   json={"key_id": "x", "private_key_pem": secret})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(secret, response.text)
        longer_secret = secret * 3
        response = self.client.put("/api/kalshi/credentials", headers=self.auth(),
                                   json={"key_id": "x", "private_key_pem": longer_secret})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(longer_secret, response.text)

    def test_preview_requires_auth_and_execution_gate_blocks_live_orders(self):
        url = f"/api/baskets/{self.basket_id}/trade/preview"
        self.assertEqual(self.client.post(url, json={"amount_dollars": 100}).status_code, 401)
        preview = self.client.post(url, headers=self.auth(), json={"amount_dollars": 100})
        self.assertEqual(preview.status_code, 200, preview.text)
        body = preview.json()
        self.assertEqual(len(body["lines"]), 2)
        self.assertLess(body["estimated_max_cost_dollars"], 100)
        blocked = self.client.post(f"/api/baskets/{self.basket_id}/trade/execute",
                                   headers=self.auth(), json={"preview_id": body["preview_id"], "confirm": True})
        self.assertEqual(blocked.status_code, 503)
        self.assertEqual(FakeUserKalshiClient.orders_created, [])

    def test_private_basket_preview_is_owner_only(self):
        db.update_basket_visibility(self.basket_id, "alice", False)
        url = f"/api/baskets/{self.basket_id}/trade/preview"
        self.assertEqual(self.client.post(url, headers=self.auth("bob"),
                                          json={"amount_dollars": 100}).status_code, 404)
        self.assertEqual(self.client.post(url, headers=self.auth("alice"),
                                          json={"amount_dollars": 100}).status_code, 200)

    def test_existing_opposing_kalshi_position_blocks_trade(self):
        self.assertEqual(self.connect().status_code, 200)
        preview = self.client.post(f"/api/baskets/{self.basket_id}/trade/preview",
                                   headers=self.auth(), json={"amount_dollars": 100}).json()
        FakeUserKalshiClient.existing_positions = [{"ticker": "NO-MARKET", "position_fp": "2.00"}]
        with patch.dict(os.environ, {"ENABLE_LIVE_TRADING": "true"}):
            response = self.client.post(f"/api/baskets/{self.basket_id}/trade/execute",
                                        headers=self.auth(), json={"preview_id": preview["preview_id"],
                                                                   "confirm": True})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(FakeUserKalshiClient.orders_created, [])

    def test_external_sale_suppresses_prism_portfolio_valuation(self):
        self.assertEqual(self.connect().status_code, 200)
        preview = self.client.post(f"/api/baskets/{self.basket_id}/trade/preview",
                                   headers=self.auth(), json={"amount_dollars": 100}).json()
        with patch.dict(os.environ, {"ENABLE_LIVE_TRADING": "true"}):
            result = self.client.post(f"/api/baskets/{self.basket_id}/trade/execute",
                                      headers=self.auth(), json={"preview_id": preview["preview_id"],
                                                                 "confirm": True})
        self.assertEqual(result.json()["status"], "filled")
        original = self.client.get("/api/portfolio", headers=self.auth()).json()
        self.assertEqual(original["summary"]["valuation_status"], "complete")
        self.assertIsNotNone(original["summary"]["current_value_dollars"])
        yes_order = next(o for o in FakeUserKalshiClient.orders_created if o["side"] == "bid")
        no_order = next(o for o in FakeUserKalshiClient.orders_created if o["side"] == "ask")
        FakeUserKalshiClient.existing_positions = [
            {"ticker": "YES-MARKET", "position_fp": f"{float(yes_order['count']) - 1:.2f}"},
            {"ticker": "NO-MARKET", "position_fp": f"{-float(no_order['count']):.2f}"},
        ]
        changed = self.client.get("/api/portfolio", headers=self.auth()).json()
        self.assertEqual(changed["summary"]["valuation_status"], "partial")
        self.assertIsNone(changed["summary"]["current_value_dollars"])
        yes_position = next(p for p in changed["positions"] if p["ticker"] == "YES-MARKET")
        self.assertEqual(yes_position["status"], "external_activity_unreconciled")
        self.assertIsNone(yes_position["current_value_dollars"])
        self.assertTrue(all(point["current_value_dollars"] is None for point in changed["history"]))
        self.assertEqual(changed["summary"]["invested_dollars"], original["summary"]["invested_dollars"])
        # Extra same-direction Kalshi holdings do not make Prism's allocation uncertain.
        FakeUserKalshiClient.existing_positions = [
            {"ticker": "YES-MARKET", "position_fp": f"{float(yes_order['count']) + 1:.2f}"},
            {"ticker": "NO-MARKET", "position_fp": f"{-float(no_order['count']) - 1:.2f}"},
        ]
        larger = self.client.get("/api/portfolio", headers=self.auth()).json()
        self.assertEqual(larger["summary"]["valuation_status"], "complete")

    def test_partial_fill_stops_next_leg_and_reconciliation_keeps_actual_cost(self):
        self.assertEqual(self.connect().status_code, 200)
        FakeUserKalshiClient.partial = True
        preview = self.client.post(f"/api/baskets/{self.basket_id}/trade/preview",
                                   headers=self.auth(), json={"amount_dollars": 100}).json()
        url = f"/api/baskets/{self.basket_id}/trade/execute"
        body = {"preview_id": preview["preview_id"], "confirm": True}
        with patch.dict(os.environ, {"ENABLE_LIVE_TRADING": "true"}):
            first = self.client.post(url, headers=self.auth(), json=body)
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(first.json()["status"], "partial")
            self.assertEqual(len(FakeUserKalshiClient.orders_created), 1)
            self.assertEqual(first.json()["orders"][0]["status"], "partial")
            again = self.client.post(url, headers=self.auth(), json=body)
            self.assertEqual(again.json()["investment_id"], first.json()["investment_id"])
            self.assertEqual(len(FakeUserKalshiClient.orders_created), 1)
        stats_before = trading_db.get_basket_stats(self.basket_id)
        order = trading_db.get_investment_orders(first.json()["investment_id"])[0]
        trading_db.update_order(order["client_order_id"], order_id=order["order_id"],
                                status="pending_reconciliation")
        reconciled = self.client.post("/api/portfolio/reconcile", headers=self.auth())
        self.assertEqual(reconciled.status_code, 200, reconciled.text)
        self.assertEqual(trading_db.get_basket_stats(self.basket_id), stats_before)
        self.assertEqual(trading_db.get_investment(first.json()["investment_id"])["status"], "partial")

    def test_rejected_order_is_failed_and_never_counts_as_invested(self):
        self.assertEqual(self.connect().status_code, 200)
        preview = self.client.post(f"/api/baskets/{self.basket_id}/trade/preview",
                                   headers=self.auth(), json={"amount_dollars": 100}).json()
        request = httpx.Request("POST", "https://external-api.kalshi.com/trade-api/v2/portfolio/events/orders")
        response = httpx.Response(403, request=request)
        rejection = httpx.HTTPStatusError("Rejected", request=request, response=response)
        with (patch.dict(os.environ, {"ENABLE_LIVE_TRADING": "true"}),
              patch.object(FakeUserKalshiClient, "create_ioc_order", side_effect=rejection)):
            result = self.client.post(f"/api/baskets/{self.basket_id}/trade/execute",
                                      headers=self.auth(), json={"preview_id": preview["preview_id"],
                                                                 "confirm": True})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["status"], "failed")
        self.assertEqual(result.json()["orders"][0]["status"], "failed")
        self.assertEqual(trading_db.get_basket_stats(self.basket_id)["invested_dollars"], 0)

    def test_execution_is_single_use_and_counts_only_confirmed_fills(self):
        self.assertEqual(self.connect().status_code, 200)
        preview = self.client.post(f"/api/baskets/{self.basket_id}/trade/preview",
                                   headers=self.auth(), json={"amount_dollars": 100}).json()
        execute_url = f"/api/baskets/{self.basket_id}/trade/execute"
        body = {"preview_id": preview["preview_id"], "confirm": True}
        self.assertEqual(self.client.post(execute_url, headers=self.auth(), json=body).status_code, 503)
        with patch.dict(os.environ, {"ENABLE_LIVE_TRADING": "true"}):
            first = self.client.post(execute_url, headers=self.auth(), json=body)
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(first.json()["status"], "filled")
            self.assertEqual(len(FakeUserKalshiClient.orders_created), 2)
            again = self.client.post(execute_url, headers=self.auth(), json=body)
            self.assertEqual(again.status_code, 200)
            self.assertEqual(again.json()["investment_id"], first.json()["investment_id"])
            self.assertEqual(len(FakeUserKalshiClient.orders_created), 2)
        self.assertEqual(FakeUserKalshiClient.orders_created[0]["side"], "bid")
        self.assertEqual(FakeUserKalshiClient.orders_created[1]["side"], "ask")
        stats = trading_db.get_basket_stats(self.basket_id)
        self.assertEqual(stats["investor_count"], 1)
        self.assertGreater(stats["invested_dollars"], 0)
        trades = self.client.get("/api/portfolio/trades", headers=self.auth()).json()
        self.assertEqual(len(trades["trades"]), 2)
        self.assertEqual(len(trades["orders"]), 2)
        portfolio = self.client.get("/api/portfolio", headers=self.auth()).json()
        self.assertEqual(len(portfolio["positions"]), 2)
        self.assertGreater(portfolio["summary"]["invested_dollars"], 0)
        self.assertTrue(portfolio["history"])
        self.assertEqual(self.client.get("/api/portfolio", headers=self.auth("bob")).json()["positions"], [])

    def test_historical_portfolio_rebuilds_days_without_account_visits(self):
        first_day = datetime.now(timezone.utc).date() - timedelta(days=2)
        candle_end = datetime.combine(first_day + timedelta(days=2), datetime.min.time(), timezone.utc)

        class CandleClient(FakeMarketClient):
            def get_candlesticks(self, tickers, start_ts, end_ts, period_interval):
                return {"HISTORY-MARKET": [{
                    "end_period_ts": int(candle_end.timestamp()),
                    "yes_bid": {"close_dollars": "0.6000"},
                    "yes_ask": {"close_dollars": "0.6200"},
                }]}

        fills = [{"ticker": "HISTORY-MARKET", "side": "YES", "count": "10.00",
                  "price_dollars": "0.5000", "cost_dollars": "5.00",
                  "created_at": f"{first_day.isoformat()}T12:00:00Z"}]
        history = trading_routes._historical_portfolio(fills, CandleClient())
        self.assertGreaterEqual(len(history), 3)
        self.assertEqual(history[0]["current_value_dollars"], 5.0)
        self.assertEqual(history[1]["current_value_dollars"], 6.0)


if __name__ == "__main__":
    unittest.main()
