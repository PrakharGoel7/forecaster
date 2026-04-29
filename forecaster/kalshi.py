"""Kalshi API client using RSA-PSS signed request authentication."""
from __future__ import annotations
import base64
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

PROD_BASE = "https://api.elections.kalshi.com/trade-api/v2"


def _strip_html(text: str) -> str:
    if not text:
        return ""
    return BeautifulSoup(text, "html.parser").get_text(separator=" ", strip=True)


def _parse_price(value: str | int | float | None) -> float:
    """Convert Kalshi price (dollars string or cents int) to 0-1 probability."""
    if value is None:
        return 0.0
    try:
        f = float(value)
        return max(0.0, min(1.0, f))
    except (ValueError, TypeError):
        return 0.0


def _parse_volume(value: str | int | float | None) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


class _KalshiAuth(httpx.Auth):
    """Attaches Kalshi's three signed-request headers to every request."""

    def __init__(self, key_id: str, private_key):
        self._key_id = key_id
        self._private_key = private_key

    def auth_flow(self, request: httpx.Request):
        timestamp_str = str(int(time.time() * 1000))
        # Signature covers: timestamp + METHOD + path (no query string)
        path = request.url.path
        message = (timestamp_str + request.method + path).encode()

        sig_bytes = self._private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        sig_b64 = base64.b64encode(sig_bytes).decode()

        request.headers["KALSHI-ACCESS-KEY"] = self._key_id
        request.headers["KALSHI-ACCESS-TIMESTAMP"] = timestamp_str
        request.headers["KALSHI-ACCESS-SIGNATURE"] = sig_b64
        yield request


def _load_private_key(pem: str | bytes):
    if isinstance(pem, str):
        pem = pem.encode()
    pem = pem.strip()
    if pem.startswith(b"-----"):
        return serialization.load_pem_private_key(pem, password=None)
    # Raw base64 DER (no PEM headers) — decode and load directly
    import base64
    der = base64.b64decode(pem)
    return serialization.load_der_private_key(der, password=None)


@dataclass
class KalshiEvent:
    event_ticker: str
    series_ticker: str
    title: str
    sub_title: str
    category: str

    def matches(self, query: str) -> bool:
        q = query.lower()
        return q in (self.title + " " + self.sub_title + " " + self.event_ticker).lower()


@dataclass
class KalshiMarket:
    ticker: str
    event_ticker: str
    yes_sub_title: str
    no_sub_title: str
    yes_bid: float    # 0-1
    yes_ask: float    # 0-1
    last_price: float # 0-1
    volume: float
    rules_primary: str
    rules_secondary: str
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
    def resolution_context(self) -> str:
        parts = []
        if self.rules_primary:
            parts.append(_strip_html(self.rules_primary))
        if self.rules_secondary:
            parts.append(_strip_html(self.rules_secondary))
        if self.close_time:
            parts.append(f"Market closes: {self.close_time}")
        return "\n".join(parts)

    @property
    def close_date(self) -> str:
        if not self.close_time:
            return "—"
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(self.close_time.replace("Z", "+00:00"))
            return dt.strftime("%b %-d")
        except Exception:
            return self.close_time[:10]


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
        """Load key ID from KALSHI_API_KEY and private key from KALSHI_PRIVATE_KEY_FILE."""
        key_id = os.environ.get("KALSHI_API_KEY", "")
        pem_file = os.environ.get("KALSHI_PRIVATE_KEY_FILE", "")
        if not key_id or not pem_file:
            raise ValueError(
                "Set KALSHI_API_KEY (your key ID) and "
                "KALSHI_PRIVATE_KEY_FILE (path to your .pem / .txt private key file)"
            )
        return cls(key_id=key_id, private_key_pem=Path(pem_file).read_bytes())

    @classmethod
    def from_files(cls, key_id: str, private_key_path: str) -> "KalshiClient":
        return cls(key_id=key_id, private_key_pem=Path(private_key_path).read_bytes())

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
        next_cursor = data.get("cursor") or None
        return markets, next_cursor

    def get_events(
        self,
        limit: int = 100,
        status: str = "open",
        cursor: str | None = None,
    ) -> tuple[list[KalshiEvent], str | None]:
        params: dict = {"limit": limit, "status": status}
        if cursor:
            params["cursor"] = cursor
        resp = self._http.get("/events", params=params)
        resp.raise_for_status()
        data = resp.json()
        events = [
            KalshiEvent(
                event_ticker=e.get("event_ticker", ""),
                series_ticker=e.get("series_ticker", ""),
                title=e.get("title", ""),
                sub_title=e.get("sub_title", ""),
                category=e.get("category", ""),
            )
            for e in data.get("events", [])
        ]
        return events, data.get("cursor") or None

    def get_market(self, ticker: str) -> KalshiMarket:
        resp = self._http.get(f"/markets/{ticker}")
        resp.raise_for_status()
        return self._parse(resp.json().get("market", {}))

    def _parse(self, m: dict) -> KalshiMarket:
        return KalshiMarket(
            ticker=m.get("ticker", ""),
            event_ticker=m.get("event_ticker", ""),
            yes_sub_title=m.get("yes_sub_title") or m.get("title") or "",
            no_sub_title=m.get("no_sub_title") or m.get("subtitle") or "",
            yes_bid=_parse_price(m.get("yes_bid_dollars") or m.get("yes_bid")),
            yes_ask=_parse_price(m.get("yes_ask_dollars") or m.get("yes_ask")),
            last_price=_parse_price(m.get("last_price_dollars") or m.get("last_price")),
            volume=_parse_volume(m.get("volume_fp") or m.get("volume")),
            rules_primary=m.get("rules_primary", ""),
            rules_secondary=m.get("rules_secondary", ""),
            close_time=m.get("close_time", ""),
            status=m.get("status", ""),
        )
