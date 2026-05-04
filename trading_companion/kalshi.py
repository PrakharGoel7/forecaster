"""Kalshi API client — standalone copy adapted from forecaster/forecaster/kalshi.py."""
from __future__ import annotations
import base64
import csv
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

PROD_BASE = "https://api.elections.kalshi.com/trade-api/v2"
logger = logging.getLogger("prism.kalshi")
_DEFAULT_LOG_FILE = Path(os.environ.get("KALSHI_API_LOG_FILE", "runtime_logs/kalshi_api_log.csv"))


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

    def _append_csv_rows(self, rows: list[dict]) -> None:
        if not rows:
            return
        log_file = _DEFAULT_LOG_FILE
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "timestamp_ms",
            "endpoint",
            "query",
            "status",
            "cursor",
            "count",
            "item_index",
            "item_kind",
            "event_ticker",
            "series_ticker",
            "title",
            "category",
            "ticker",
            "question",
            "market_status",
            "mid_price",
            "yes_bid",
            "yes_ask",
            "last_price",
            "volume",
            "close_time",
        ]
        write_header = not log_file.exists()
        with log_file.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def _log_request(self, endpoint: str, params: dict | None = None, **extra) -> None:
        payload = {"endpoint": endpoint, "params": params or {}}
        payload.update(extra)
        logger.info("Kalshi request: %s", payload)

    def _log_markets_response(
        self,
        endpoint: str,
        params: dict,
        markets: list[KalshiMarket],
        cursor: str | None = None,
    ) -> None:
        timestamp_ms = int(time.time() * 1000)
        logger.info(
            "Kalshi response: %s",
            {
                "endpoint": endpoint,
                "params": params,
                "count": len(markets),
                "next_cursor": cursor,
                "markets": [
                    {
                        "ticker": m.ticker,
                        "event_ticker": m.event_ticker,
                        "question": m.question,
                        "status": m.status,
                        "mid_price": round(m.mid_price, 4),
                        "yes_bid": round(m.yes_bid, 4),
                        "yes_ask": round(m.yes_ask, 4),
                        "last_price": round(m.last_price, 4),
                        "volume": m.volume,
                        "close_time": m.close_time,
                    }
                    for m in markets
                ],
            },
        )
        self._append_csv_rows([
            {
                "timestamp_ms": timestamp_ms,
                "endpoint": endpoint,
                "query": str(params),
                "status": "ok",
                "cursor": cursor or "",
                "count": len(markets),
                "item_index": i,
                "item_kind": "market",
                "event_ticker": m.event_ticker,
                "series_ticker": "",
                "title": "",
                "category": "",
                "ticker": m.ticker,
                "question": m.question,
                "market_status": m.status,
                "mid_price": round(m.mid_price, 4),
                "yes_bid": round(m.yes_bid, 4),
                "yes_ask": round(m.yes_ask, 4),
                "last_price": round(m.last_price, 4),
                "volume": m.volume,
                "close_time": m.close_time,
            }
            for i, m in enumerate(markets)
        ])

    def _log_events_response(self, endpoint: str, params: dict, events: list[dict], cursor: str | None) -> None:
        timestamp_ms = int(time.time() * 1000)
        logger.info(
            "Kalshi response: %s",
            {
                "endpoint": endpoint,
                "params": params,
                "count": len(events),
                "next_cursor": cursor,
                "events": [
                    {
                        "event_ticker": e.get("event_ticker", ""),
                        "series_ticker": e.get("series_ticker", ""),
                        "title": e.get("title", ""),
                        "category": e.get("category", ""),
                    }
                    for e in events
                ],
            },
        )
        self._append_csv_rows([
            {
                "timestamp_ms": timestamp_ms,
                "endpoint": endpoint,
                "query": str(params),
                "status": "ok",
                "cursor": cursor or "",
                "count": len(events),
                "item_index": i,
                "item_kind": "event",
                "event_ticker": e.get("event_ticker", ""),
                "series_ticker": e.get("series_ticker", ""),
                "title": e.get("title", ""),
                "category": e.get("category", ""),
                "ticker": "",
                "question": "",
                "market_status": "",
                "mid_price": "",
                "yes_bid": "",
                "yes_ask": "",
                "last_price": "",
                "volume": "",
                "close_time": "",
            }
            for i, e in enumerate(events)
        ])

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
            self._log_request("/series", params, query=query)
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
        self._log_request("/markets", params)
        resp = self._http.get("/markets", params=params)
        resp.raise_for_status()
        data = resp.json()
        markets = [self._parse(m) for m in data.get("markets", [])]
        next_cursor = data.get("cursor") or None
        self._log_markets_response("/markets", params, markets, next_cursor)
        return markets, next_cursor

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
        self._log_request("/events", params)
        resp = self._http.get("/events", params=params)
        resp.raise_for_status()
        data = resp.json()
        events = data.get("events", [])
        next_cursor = data.get("cursor") or None
        self._log_events_response("/events", params, events, next_cursor)
        return events, next_cursor

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
