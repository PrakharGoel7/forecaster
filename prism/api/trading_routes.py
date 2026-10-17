"""Authenticated Kalshi connection, basket execution and portfolio API.

Trade submission is deliberately gated by ENABLE_LIVE_TRADING.  A preview is
single-use, short-lived and contains fixed limit prices; retries cannot send
the same order twice.  Public invested amounts use confirmed fills only.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Callable

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from forecaster import db, trading_db
from forecaster.kalshi import _load_private_key
from forecaster.price_history import candle_yes_price, fetch_candlesticks
from forecaster.trading_kalshi import UserKalshiClient

logger = logging.getLogger("prism.trading")
D = Decimal


class PreviewRequest(BaseModel):
    amount_dollars: D = Field(gt=0, le=100000)


class ExecuteRequest(BaseModel):
    preview_id: str
    confirm: bool


def _fernet() -> Fernet:
    key = os.environ.get("KALSHI_CREDENTIALS_ENCRYPTION_KEY", "")
    if not key:
        raise HTTPException(503, "Kalshi credential storage is not configured")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        raise HTTPException(503, "Kalshi credential storage is misconfigured")


def _require_user(request: Request, get_user_id: Callable) -> str:
    user_id = get_user_id(request)
    if not user_id:
        raise HTTPException(401, "Not authenticated")
    return user_id


def _user_client(user_id: str) -> UserKalshiClient:
    row = trading_db.get_connection(user_id)
    if not row:
        raise HTTPException(409, "Connect your Kalshi account first")
    fernet = _fernet()
    try:
        key_id = fernet.decrypt(row["key_id_ciphertext"].encode()).decode()
        private_key = fernet.decrypt(row["private_key_ciphertext"].encode()).decode()
        return UserKalshiClient(key_id=key_id, private_key_pem=private_key)
    except (InvalidToken, ValueError, TypeError):
        raise HTTPException(503, "Stored Kalshi credentials cannot be decrypted")


def _dollars(value: D) -> str:
    return str(value.quantize(D("0.0001")))


def _money(value: D) -> float:
    return float(value.quantize(D("0.01")))


def _record_order_fills(client: UserKalshiClient, order: dict) -> list[dict]:
    raw_fills = client.fills_for_order(order["order_id"])
    result = []
    for fill in raw_fills:
        fill_id = fill.get("fill_id")
        if not fill_id or fill.get("order_id") != order["order_id"]:
            continue
        side = order["side"]
        count = D(str(fill.get("count_fp") or fill.get("count") or "0"))
        price_key = "yes_price_dollars" if side == "YES" else "no_price_dollars"
        price = D(str(fill.get(price_key) or "0"))
        fee = D(str(fill.get("fee_cost") or "0"))
        if count <= 0 or price <= 0 or price >= 1 or fee < 0:
            logger.warning("Skipping invalid Kalshi fill %s", fill_id)
            continue
        cost = count * price + fee
        record = {
            "fill_id": fill_id,
            "investment_id": order["investment_id"],
            "user_id": order["user_id"],
            "basket_id": order["basket_id"],
            "order_id": order["order_id"],
            "ticker": order["ticker"],
            "side": side,
            "count": str(count),
            "price_dollars": str(price),
            "fee_dollars": str(fee),
            "cost_dollars": str(cost),
            "created_at": fill.get("created_time") or datetime.now(timezone.utc).isoformat(),
        }
        trading_db.insert_fill(record)
        result.append(record)
    return result


def _order_view(order: dict) -> dict:
    fills = trading_db.get_order_fills(order["order_id"]) if order.get("order_id") else []
    return {
        "ticker": order["ticker"], "side": order["side"],
        "client_order_id": order["client_order_id"], "order_id": order.get("order_id"),
        "status": order["status"],
        "filled_contracts": float(sum((D(f["count"]) for f in fills), D(0))),
        "filled_cost_dollars": _money(sum((D(f["cost_dollars"]) for f in fills), D(0))),
        "error": order.get("error"),
    }


def _investment_view(investment: dict) -> dict:
    return {"investment_id": investment["id"], "status": investment["status"],
            "orders": [_order_view(o) for o in trading_db.get_investment_orders(investment["id"])]}


def _historical_portfolio(fills: list[dict], market_client,
                          ownership_uncertain: set[str] | None = None) -> list[dict]:
    """Rebuild daily marks from actual fill dates and Kalshi candles on demand.

    No visit-time collection is necessary.  The chart is an indicative mark,
    and closed markets without settlement records are left unvalued.
    """
    if not fills:
        return []
    ordered = sorted(fills, key=lambda f: f["created_at"])
    start_day = date.fromisoformat(ordered[0]["created_at"][:10])
    today = datetime.now(timezone.utc).date()
    if start_day > today:
        return []
    start_ts = int(datetime.combine(start_day, datetime.min.time(), timezone.utc).timestamp())
    end_ts = int(datetime.now(timezone.utc).timestamp())
    tickers = list(dict.fromkeys(f["ticker"] for f in fills))
    candles: dict[str, list[dict]] = {}
    for offset in range(0, len(tickers), 100):
        group = tickers[offset:offset + 100]
        candles.update(fetch_candlesticks(market_client, group, start_ts, end_ts, 1440))
    marks_by_day: dict[str, dict[str, tuple[D, D]]] = defaultdict(dict)
    for ticker, series in candles.items():
        for candle in series:
            ts = candle.get("end_period_ts")
            fallback = candle_yes_price(candle)
            if isinstance(ts, int) and fallback is not None:
                bid_raw = (candle.get("yes_bid") or {}).get("close_dollars")
                ask_raw = (candle.get("yes_ask") or {}).get("close_dollars")
                try:
                    bid = D(str(bid_raw)) if bid_raw is not None else D(str(fallback))
                    ask = D(str(ask_raw)) if ask_raw is not None else D(str(fallback))
                except ValueError:
                    bid = ask = D(str(fallback))
                if not D(0) <= bid <= ask <= D(1):
                    continue
                day = datetime.fromtimestamp(ts - 1, timezone.utc).date().isoformat()
                marks_by_day[day][ticker] = (bid, ask)
    closed_after: dict[str, str] = {}
    for ticker in tickers:
        try:
            market = market_client.get_market(ticker)
            if market.status.lower() not in ("active", "open") and market.close_time:
                closed_after[ticker] = market.close_time[:10]
        except (httpx.HTTPError, ValueError):
            pass
    contracts: dict[tuple[str, str], D] = defaultdict(lambda: D(0))
    marks: dict[str, tuple[D, D]] = {}
    invested = D(0)
    history = []
    cursor = 0
    day = start_day
    while day <= today:
        day_string = day.isoformat()
        while cursor < len(ordered) and ordered[cursor]["created_at"][:10] <= day_string:
            fill = ordered[cursor]
            ticker, side = fill["ticker"], fill["side"]
            contracts[(ticker, side)] += D(fill["count"])
            invested += D(fill["cost_dollars"])
            price = D(fill["price_dollars"])
            entry_yes = price if side == "YES" else D(1) - price
            marks.setdefault(ticker, (entry_yes, entry_yes))
            cursor += 1
        marks.update(marks_by_day.get(day_string, {}))
        if cursor:
            unvalued = any((ticker in closed_after and day_string > closed_after[ticker])
                           or (ticker in (ownership_uncertain or set()))
                           for ticker, _ in contracts)
            value = None if unvalued else sum((count * (marks[ticker][0] if side == "YES" else D(1) - marks[ticker][1])
                                               for (ticker, side), count in contracts.items()), D(0))
            history.append({"date": day_string, "invested_dollars": _money(invested),
                            "current_value_dollars": _money(value) if value is not None else None})
        day += timedelta(days=1)
    return history


def _reconcile(client: UserKalshiClient, user_id: str) -> None:
    orders = trading_db.get_reconcilable_orders(user_id)
    if not orders:
        return
    unknown = [o for o in orders if not o.get("order_id")]
    recent_by_client = {}
    if unknown:
        try:
            recent_by_client = {o.get("client_order_id"): o for o in client.orders()}
        except (httpx.HTTPError, ValueError):
            logger.warning("Could not reconcile unknown Kalshi order IDs")
    affected_investments = set()
    for order in orders:
        affected_investments.add(order["investment_id"])
        order_id = order.get("order_id") or (recent_by_client.get(order["client_order_id"]) or {}).get("order_id")
        if not order_id:
            continue
        order["order_id"] = order_id
        try:
            fills = _record_order_fills(client, order)
            filled_count = sum((D(f["count"]) for f in fills), D(0))
            status = ("filled" if filled_count >= D(order["count"]) else
                      "partial" if filled_count else "unfilled")
            trading_db.update_order(order["client_order_id"], order_id=order_id, status=status)
        except (httpx.HTTPError, ValueError):
            trading_db.update_order(order["client_order_id"], order_id=order_id,
                                    status="pending_reconciliation")
    for investment_id in affected_investments:
        all_orders = trading_db.get_investment_orders(investment_id)
        states = {order["status"] for order in all_orders}
        if "pending_reconciliation" in states or "submitting" in states or "submitted" in states:
            status = "pending_reconciliation"
        elif states == {"filled"}:
            status = "filled"
        elif "filled" in states or "partial" in states:
            status = "partial"
        elif "failed" in states:
            status = "failed"
        else:
            status = "unfilled"
        trading_db.update_investment(investment_id, status)


def create_trading_router(get_user_id: Callable, get_market_client: Callable) -> APIRouter:
    router = APIRouter()

    @router.get("/api/kalshi/credentials")
    def credential_status(request: Request):
        user_id = _require_user(request, get_user_id)
        row = trading_db.get_connection(user_id)
        return {"connected": bool(row), "key_id_masked": row["key_id_masked"] if row else None}

    @router.put("/api/kalshi/credentials")
    async def save_credentials(request: Request):
        user_id = _require_user(request, get_user_id)
        if int(request.headers.get("content-length") or 0) > 20000:
            raise HTTPException(413, "Credential request is too large")
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(422, "Invalid credential request")
        if not isinstance(body, dict):
            raise HTTPException(422, "Invalid credential request")
        raw_key_id = body.get("key_id")
        raw_private_key = body.get("private_key_pem")
        if (not isinstance(raw_key_id, str) or not isinstance(raw_private_key, str)
                or not 1 <= len(raw_key_id) <= 256 or not 64 <= len(raw_private_key) <= 16000):
            raise HTTPException(422, "Invalid credential request")
        fernet = _fernet()
        key_id = raw_key_id.strip()
        private_key = raw_private_key.replace("\\n", "\n").strip()
        try:
            _load_private_key(private_key)
        except (ValueError, TypeError):
            raise HTTPException(422, "Invalid Kalshi private key")
        try:
            client = UserKalshiClient(key_id=key_id, private_key_pem=private_key)
            client.balance()  # Read-only proof that this key belongs to a usable Kalshi account.
            client.positions()  # Execution needs this to avoid offsetting an existing position.
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                raise HTTPException(422, "Kalshi rejected this key or its portfolio-read permission")
            raise HTTPException(502, "Kalshi could not verify this key")
        except httpx.HTTPError:
            raise HTTPException(502, "Kalshi is temporarily unavailable")
        except ValueError:
            raise HTTPException(502, "Kalshi returned incomplete portfolio data")
        masked = ("•" * max(0, len(key_id) - 4)) + key_id[-4:]
        trading_db.put_connection(user_id,
            fernet.encrypt(key_id.encode()).decode(),
            fernet.encrypt(private_key.encode()).decode(), masked)
        return {"connected": True, "key_id_masked": masked}

    @router.delete("/api/kalshi/credentials")
    def remove_credentials(request: Request):
        user_id = _require_user(request, get_user_id)
        trading_db.delete_connection(user_id)
        return {"connected": False}

    @router.post("/api/baskets/{basket_id}/trade/preview")
    def preview_trade(basket_id: int, body: PreviewRequest, request: Request):
        user_id = _require_user(request, get_user_id)
        basket = db.get_basket(basket_id, user_id=user_id)
        if not basket:
            raise HTTPException(404, "Basket not found")
        holdings = basket.get("holdings") or []
        if not holdings or len(holdings) > 20:
            raise HTTPException(422, "Basket must contain 1 to 20 holdings")
        tickers = [h["ticker"] for h in holdings]
        if len(set(tickers)) != len(tickers):
            raise HTTPException(422, "Basket contains duplicate markets")
        total_weight = sum((D(str(h["weight_dollars"])) for h in holdings), D(0))
        if total_weight <= 0:
            raise HTTPException(422, "Basket has no positive weights")
        market_client = get_market_client()
        lines = []
        # 10% of each allocation is left for fees and market movement. Orders
        # are still fixed-price IOC limits, so they cannot drift above the quote.
        for h in holdings:
            side = str(h["side"]).upper()
            if side not in ("YES", "NO"):
                raise HTTPException(422, f"Unsupported side for {h['ticker']}")
            try:
                market = market_client.get_market(h["ticker"])
            except httpx.HTTPError:
                raise HTTPException(502, f"Could not quote {h['ticker']}")
            if market.status.lower() not in ("active", "open"):
                raise HTTPException(422, f"{h['ticker']} is not open")
            yes_quote = D(str(market.yes_ask if side == "YES" else market.yes_bid))
            unit_cost = yes_quote if side == "YES" else D(1) - yes_quote
            if not D(0) < unit_cost < D(1):
                raise HTTPException(422, f"{h['ticker']} has no executable quote")
            weight = D(str(h["weight_dollars"])) / total_weight
            allocation = body.amount_dollars * weight * D("0.90")
            count = int((allocation / unit_cost).to_integral_value(rounding=ROUND_DOWN))
            if count < 1:
                raise HTTPException(422, f"Amount is too small for {h['ticker']}; increase it or edit the basket")
            lines.append({"ticker": h["ticker"], "side": side, "count": count,
                          "limit_price_dollars": _dollars(yes_quote),
                          "estimated_cost_dollars": _money(unit_cost * count),
                          "weight_percent": _money(weight * 100)})
        max_cost = sum((D(str(line["estimated_cost_dollars"])) for line in lines), D(0))
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=60)
        preview_id = str(uuid.uuid4())
        payload = {"preview_id": preview_id, "basket_id": basket_id,
                   "expires_at": expires.isoformat(),
                   "amount_dollars": _money(body.amount_dollars),
                   "estimated_max_cost_dollars": _money(max_cost),
                   "estimated_cost_before_fees_dollars": _money(max_cost),
                   "fees_included": False, "lines": lines}
        trading_db.create_preview(preview_id, user_id, basket_id, expires.isoformat(), payload)
        return payload

    @router.post("/api/baskets/{basket_id}/trade/execute")
    def execute_trade(basket_id: int, body: ExecuteRequest, request: Request):
        user_id = _require_user(request, get_user_id)
        if not body.confirm:
            raise HTTPException(422, "Confirm the basket trade")
        if os.environ.get("ENABLE_LIVE_TRADING", "").lower() != "true":
            raise HTTPException(503, "Live Kalshi trading is not enabled")
        preview = trading_db.get_preview(body.preview_id, user_id, basket_id)
        if not preview:
            raise HTTPException(404, "Trade preview not found")
        existing = trading_db.get_investment_by_preview(body.preview_id, user_id)
        if existing:
            return _investment_view(existing)
        if preview["status"] != "open" or preview["expires_at"] <= datetime.now(timezone.utc).isoformat():
            raise HTTPException(409, "Trade preview expired; request a new quote")
        basket = db.get_basket(basket_id, user_id=user_id)
        if not basket:
            raise HTTPException(404, "Basket not found")
        client = _user_client(user_id)
        payload = json.loads(preview["payload_json"])
        try:
            balance = client.balance()
        except httpx.HTTPError:
            raise HTTPException(502, "Could not check Kalshi balance")
        available = D(str(balance.get("balance_dollars") or D(str(balance.get("balance", 0))) / 100))
        if available < D(str(payload["amount_dollars"])):
            raise HTTPException(422, "Insufficient Kalshi cash balance")
        try:
            positions = {p.get("ticker"): D(str(p.get("position_fp") or "0"))
                         for p in client.positions()}
        except (httpx.HTTPError, ValueError):
            raise HTTPException(502, "Could not check existing Kalshi positions")
        for line in payload["lines"]:
            existing_position = positions.get(line["ticker"], D(0))
            if ((line["side"] == "YES" and existing_position < 0) or
                    (line["side"] == "NO" and existing_position > 0)):
                raise HTTPException(409, f"Existing opposing Kalshi position in {line['ticker']}; close it before this basket trade")
        investment_id = str(uuid.uuid4())
        if not trading_db.claim_preview(body.preview_id, user_id, basket_id, investment_id):
            existing = trading_db.get_investment_by_preview(body.preview_id, user_id)
            if existing:
                return _investment_view(existing)
            raise HTTPException(409, "Trade preview expired or already used")
        any_fill = False
        all_full = True
        pending = False
        failed = False
        for line in payload["lines"]:
            client_order_id = str(uuid.uuid4())
            order = {**line, "id": str(uuid.uuid4()), "investment_id": investment_id,
                     "user_id": user_id, "basket_id": basket_id, "client_order_id": client_order_id}
            trading_db.insert_order(order)
            try:
                response = client.create_ioc_order(
                    ticker=line["ticker"], client_order_id=client_order_id,
                    side="bid" if line["side"] == "YES" else "ask",
                    count=f"{line['count']}.00", price=line["limit_price_dollars"])
                order_id = response["order_id"]
                order["order_id"] = order_id
                trading_db.update_order(client_order_id, order_id=order_id, status="submitted")
                fills = _record_order_fills(client, order)
                filled_count = sum((D(f["count"]) for f in fills), D(0))
                any_fill = any_fill or filled_count > 0
                all_full = all_full and filled_count >= D(line["count"])
                if D(str(response.get("fill_count") or 0)) > filled_count:
                    pending = True
                    trading_db.update_order(client_order_id, order_id=order_id,
                                            status="pending_reconciliation")
                else:
                    trading_db.update_order(client_order_id, order_id=order_id,
                                            status="filled" if filled_count >= D(line["count"]) else
                                                   "partial" if filled_count else "unfilled")
                if filled_count < D(line["count"]):
                    break  # Avoid adding further exposure to an incomplete basket.
            except httpx.HTTPStatusError as exc:
                trading_db.update_order(client_order_id, order_id=None, status="failed",
                                        error=f"Kalshi rejected order ({exc.response.status_code})")
                all_full = False
                failed = True
                break
            except (httpx.HTTPError, KeyError, ValueError):
                # The exchange may have accepted a timed-out request. Never retry
                # automatically; reconcile by client_order_id and then order ID.
                trading_db.update_order(client_order_id, order_id=order.get("order_id"),
                                        status="pending_reconciliation")
                pending = True
                all_full = False
                break
        status = ("pending_reconciliation" if pending else "filled" if all_full else
                  "partial" if any_fill else "failed" if failed else "unfilled")
        trading_db.update_investment(investment_id, status)
        investment = trading_db.get_investment_by_preview(body.preview_id, user_id)
        return _investment_view(investment)

    @router.post("/api/portfolio/reconcile")
    def reconcile_portfolio(request: Request):
        user_id = _require_user(request, get_user_id)
        client = _user_client(user_id)
        _reconcile(client, user_id)
        return {"ok": True}

    @router.get("/api/portfolio/trades")
    def list_trades(request: Request):
        user_id = _require_user(request, get_user_id)
        fills = trading_db.get_user_fills(user_id)
        trades = [{"fill_id": f["fill_id"], "investment_id": f["investment_id"],
                   "basket_id": f["basket_id"], "basket_title": f.get("basket_title"),
                   "ticker": f["ticker"], "side": f["side"],
                   "contracts": float(f["count"]), "price_dollars": float(f["price_dollars"]),
                   "fee_dollars": float(f["fee_dollars"]), "cost_dollars": float(f["cost_dollars"]),
                   "created_at": f["created_at"]} for f in fills]
        orders = [_order_view(o) | {"created_at": o["created_at"],
                                     "basket_id": o["basket_id"], "basket_title": o.get("basket_title")}
                  for o in trading_db.get_user_orders(user_id)]
        return {"trades": trades, "orders": orders}

    @router.get("/api/portfolio")
    def portfolio(request: Request):
        user_id = _require_user(request, get_user_id)
        fills = trading_db.get_user_fills(user_id)
        grouped = defaultdict(lambda: {"contracts": D(0), "invested": D(0), "basket_title": ""})
        for fill in fills:
            key = (fill["basket_id"], fill["ticker"], fill["side"])
            grouped[key]["contracts"] += D(fill["count"])
            grouped[key]["invested"] += D(fill["cost_dollars"])
            grouped[key]["basket_title"] = fill.get("basket_title") or "Basket"
        prism_net: dict[str, D] = defaultdict(lambda: D(0))
        prism_sides: dict[str, set[str]] = defaultdict(set)
        for (_, ticker, side), amounts in grouped.items():
            prism_net[ticker] += amounts["contracts"] if side == "YES" else -amounts["contracts"]
            prism_sides[ticker].add(side)
        cash_balance = None
        kalshi_positions: dict[str, D] | None = None
        if trading_db.get_connection(user_id):
            try:
                user_client = _user_client(user_id)
                kalshi_positions = {p["ticker"]: D(str(p.get("position_fp") or "0"))
                                    for p in user_client.positions() if p.get("ticker")}
                try:
                    balance = user_client.balance()
                    cash_balance = float(balance.get("balance_dollars") or D(str(balance.get("balance", 0))) / 100)
                except (httpx.HTTPError, ValueError):
                    pass
            except (HTTPException, httpx.HTTPError, ValueError):
                pass
        ownership_uncertain: set[str] = set()
        if kalshi_positions is None:
            ownership_uncertain.update(prism_net)
        else:
            for ticker, prism_count in prism_net.items():
                live_count = kalshi_positions.get(ticker, D(0))
                if ((prism_count > 0 and live_count < prism_count) or
                        (prism_count < 0 and live_count > prism_count) or
                        (prism_count == 0 and len(prism_sides[ticker]) > 1)):
                    ownership_uncertain.add(ticker)
        market_client = None
        try:
            market_client = get_market_client()
        except Exception:
            pass
        quote_cache = {}
        positions = []
        invested_total = D(0)
        value_total = D(0)
        all_marked = True
        for (basket_id, ticker, side), amounts in grouped.items():
            invested = amounts["invested"]
            invested_total += invested
            value = None
            position_status = "quote_unavailable"
            if market_client:
                try:
                    if ticker not in quote_cache:
                        quote_cache[ticker] = market_client.get_market(ticker)
                    market = quote_cache[ticker]
                    if market.status.lower() in ("active", "open"):
                        if ticker in ownership_uncertain:
                            position_status = ("position_unverified" if kalshi_positions is None else
                                               "external_activity_unreconciled")
                        else:
                            mark = D(str(market.yes_bid if side == "YES" else 1 - market.yes_ask))
                            if D(0) <= mark <= D(1):
                                value = amounts["contracts"] * mark
                                position_status = "open_marked"
                    else:
                        position_status = "closed_unreconciled"
                except (httpx.HTTPError, ValueError):
                    pass
            if value is None:
                all_marked = False
            else:
                value_total += value
            positions.append({"basket_id": basket_id,
                              "basket_title": amounts["basket_title"], "ticker": ticker,
                              "side": side, "contracts": float(amounts["contracts"]),
                              "status": position_status,
                              "invested_dollars": _money(invested),
                              "current_value_dollars": _money(value) if value is not None else None,
                              "unrealized_pnl_dollars": _money(value - invested) if value is not None else None})
        current_value = _money(value_total) if all_marked else None
        invested_money = _money(invested_total)
        trading_db.save_portfolio_snapshot(user_id, invested_money, current_value)
        try:
            history = _historical_portfolio(fills, market_client, ownership_uncertain) if market_client else []
        except (httpx.HTTPError, ValueError, KeyError):
            history = []
        if not history:
            history = trading_db.get_portfolio_history(user_id)
        return {"summary": {"invested_dollars": invested_money,
                            "current_value_dollars": current_value,
                            "unrealized_pnl_dollars": _money(value_total - invested_total) if all_marked else None,
                            "kalshi_cash_balance_dollars": cash_balance,
                            "valuation_status": "complete" if all_marked else "partial",
                            "position_count": len(positions),
                            "marked_position_count": sum(1 for p in positions if p["current_value_dollars"] is not None)},
                "positions": positions, "history": history}

    return router
