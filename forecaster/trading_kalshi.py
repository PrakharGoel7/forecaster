"""Small wrapper around Kalshi's current V2 order and portfolio endpoints."""
from __future__ import annotations

from forecaster.kalshi import KalshiClient


class UserKalshiClient(KalshiClient):
    def __init__(self, key_id: str, private_key_pem: str | bytes):
        super().__init__(key_id, private_key_pem)
        # Use the host documented for authenticated V2 portfolio/order calls.
        self._http.base_url = "https://external-api.kalshi.com/trade-api/v2"

    def balance(self) -> dict:
        response = self._http.get("/portfolio/balance")
        response.raise_for_status()
        return response.json()

    def positions(self) -> list[dict]:
        positions: list[dict] = []
        cursor = ""
        for _ in range(20):
            params = {"limit": 1000, "settlement_status": "unsettled", "count_filter": "position"}
            if cursor:
                params["cursor"] = cursor
            response = self._http.get("/portfolio/positions", params=params)
            response.raise_for_status()
            data = response.json()
            positions.extend(data.get("market_positions") or [])
            next_cursor = data.get("cursor") or ""
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
        else:
            raise ValueError("Kalshi position pagination limit reached")
        return positions

    def create_ioc_order(self, *, ticker: str, client_order_id: str,
                         side: str, count: str, price: str) -> dict:
        response = self._http.post("/portfolio/events/orders", json={
            "ticker": ticker,
            "client_order_id": client_order_id,
            "side": side,
            "count": count,
            "price": price,
            "time_in_force": "immediate_or_cancel",
            "self_trade_prevention_type": "taker_at_cross",
        })
        response.raise_for_status()
        return response.json()

    def fills_for_order(self, order_id: str) -> list[dict]:
        fills: list[dict] = []
        cursor = ""
        for _ in range(20):
            params = {"order_id": order_id, "limit": 1000}
            if cursor:
                params["cursor"] = cursor
            response = self._http.get("/portfolio/fills", params=params)
            response.raise_for_status()
            data = response.json()
            fills.extend(data.get("fills") or [])
            next_cursor = data.get("cursor") or ""
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
        else:
            raise ValueError("Kalshi fill pagination limit reached")
        return fills

    def orders(self, *, min_ts: int | None = None) -> list[dict]:
        """Read recent orders so a timed-out submission can be reconciled."""
        orders: list[dict] = []
        cursor = ""
        for _ in range(20):
            params = {"limit": 1000}
            if min_ts is not None:
                params["min_ts"] = min_ts
            if cursor:
                params["cursor"] = cursor
            response = self._http.get("/portfolio/orders", params=params)
            response.raise_for_status()
            data = response.json()
            orders.extend(data.get("orders") or [])
            next_cursor = data.get("cursor") or ""
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
        else:
            raise ValueError("Kalshi order pagination limit reached")
        return orders
