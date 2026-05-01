"""Kalshi API client — standalone copy adapted from forecaster/forecaster/kalshi.py."""
from __future__ import annotations
import base64
import os
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

PROD_BASE = "https://api.elections.kalshi.com/trade-api/v2"


def _strip_html(text: str) -> str:
    if not text:
        return ""
    return BeautifulSoup(text, "html.parser").get_text(separator=" ", strip=True)


def _parse_price(value) -> float:
    if value is None:
        return 0.0
    try:
        return max(0.0, min(1.0, float(value)))
    except (ValueError, TypeError):
        return 0.0


def _parse_volume(value) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


class _KalshiAuth(httpx.Auth):
    def __init__(self, key_id: str, private_key):
        self._key_id = key_id
        self._private_key = private_key

    def auth_flow(self, request: httpx.Request):
        timestamp_str = str(int(time.time() * 1000))
        message = (timestamp_str + request.method + request.url.path).encode()
        sig_bytes = self._private_key.sign(
            message,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
        request.headers["KALSHI-ACCESS-KEY"] = self._key_id
        request.headers["KALSHI-ACCESS-TIMESTAMP"] = timestamp_str
        request.headers["KALSHI-ACCESS-SIGNATURE"] = base64.b64encode(sig_bytes).decode()
        yield request


def _load_private_key(pem: str | bytes):
    if isinstance(pem, str):
        pem = pem.encode()
    pem = pem.strip()
    if pem.startswith(b"-----"):
        return serialization.load_pem_private_key(pem, password=None)
    der = base64.b64decode(pem)
    return serialization.load_der_private_key(der, password=None)


@dataclass
class KalshiMarket:
    ticker: str
    event_ticker: str
    yes_sub_title: str
    yes_bid: float
    yes_ask: float
    last_price: float
    volume: float
    rules_primary: str
    close_time: str
    status: str

    @property
    def mid_price(self) -> float:
        if self.yes_bid > 0 and self.yes_ask > 0:
            return (self.yes_bid + self.yes_ask) / 2
        return self.last_price

    @property
    def question(self) -> str:
        title = self.yes_sub_title or self.ticker
        if title and not title.lower().startswith(("will ", "does ", "is ", "are ", "has ", "did ")):
            return f"Will {title}?"
        return title if title.endswith("?") else f"{title}?"

    @property
    def close_date(self) -> str:
        if not self.close_time:
            return "—"
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(self.close_time.replace("Z", "+00:00"))
            return dt.strftime("%b %-d, %Y")
        except Exception:
            return self.close_time[:10]

    @property
    def rules_summary(self) -> str:
        return _strip_html(self.rules_primary)[:300] if self.rules_primary else ""


class KalshiClient:
    def __init__(self, key_id: str, private_key_pem: str | bytes):
        private_key = _load_private_key(private_key_pem)
        self._http = httpx.Client(
            base_url=PROD_BASE,
            headers={"Content-Type": "application/json"},
            auth=_KalshiAuth(key_id, private_key),
            timeout=15,
        )

    @classmethod
    def from_env(cls) -> "KalshiClient":
        key_id = os.environ.get("KALSHI_API_KEY", "")
        pem_file = os.environ.get("KALSHI_PRIVATE_KEY_FILE", "")
        if not key_id or not pem_file:
            raise ValueError(
                "Set KALSHI_API_KEY and KALSHI_PRIVATE_KEY_FILE in your .env"
            )
        return cls(key_id=key_id, private_key_pem=Path(pem_file).read_bytes())

    def search_series(self, query: str, limit: int = 10) -> list[str]:
        """Return series tickers whose title or ticker contains the query string."""
        q = query.lower()
        tickers: list[str] = []
        cursor = None
        for _ in range(20):
            params: dict = {"limit": 200}
            if cursor:
                params["cursor"] = cursor
            resp = self._http.get("/series", params=params)
            resp.raise_for_status()
            data = resp.json()
            for s in data.get("series", []):
                combined = (s.get("title", "") + " " + s.get("ticker", "")).lower()
                if q in combined:
                    tickers.append(s["ticker"])
                    if len(tickers) >= limit:
                        return tickers
            cursor = data.get("cursor")
            if not cursor:
                break
        return tickers

    def get_markets(
        self,
        limit: int = 20,
        status: str = "open",
        cursor: str | None = None,
        series_ticker: str | None = None,
        event_ticker: str | None = None,
    ) -> tuple[list[KalshiMarket], str | None]:
        params: dict = {"limit": limit, "status": status}
        if cursor:
            params["cursor"] = cursor
        if series_ticker:
            params["series_ticker"] = series_ticker
        if event_ticker:
            params["event_ticker"] = event_ticker
        resp = self._http.get("/markets", params=params)
        resp.raise_for_status()
        data = resp.json()
        markets = [self._parse(m) for m in data.get("markets", [])]
        return markets, data.get("cursor") or None

    def get_events(
        self,
        limit: int = 50,
        status: str = "open",
        cursor: str | None = None,
        series_ticker: str | None = None,
    ) -> tuple[list[dict], str | None]:
        params: dict = {"limit": limit, "status": status}
        if cursor:
            params["cursor"] = cursor
        if series_ticker:
            params["series_ticker"] = series_ticker
        resp = self._http.get("/events", params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("events", []), data.get("cursor") or None

    def _parse(self, m: dict) -> KalshiMarket:
        return KalshiMarket(
            ticker=m.get("ticker", ""),
            event_ticker=m.get("event_ticker", ""),
            yes_sub_title=m.get("yes_sub_title") or m.get("title") or "",
            yes_bid=_parse_price(m.get("yes_bid_dollars") or m.get("yes_bid")),
            yes_ask=_parse_price(m.get("yes_ask_dollars") or m.get("yes_ask")),
            last_price=_parse_price(m.get("last_price_dollars") or m.get("last_price")),
            volume=_parse_volume(m.get("volume_fp") or m.get("volume")),
            rules_primary=m.get("rules_primary", ""),
            close_time=m.get("close_time", ""),
            status=m.get("status", ""),
        )
