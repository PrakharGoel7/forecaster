"""Prism API — FastAPI backend wrapping the forecaster package."""
import asyncio
import contextlib
import csv
import dataclasses
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, AsyncIterator
from zoneinfo import ZoneInfo

# Repo root is three levels up from prism/api/main.py; forecaster package lives there
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

# Trading companion lives inside the repo
_TC_PATH = _REPO_ROOT / "trading_companion"
if _TC_PATH.exists() and str(_TC_PATH) not in sys.path:
    sys.path.append(str(_TC_PATH))

try:
    from dotenv import load_dotenv
    load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

# ── Supabase JWT verification ─────────────────────────────────────────────────

_SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")
_KALSHI_API_LOG_FILE = (_REPO_ROOT / os.environ.get("KALSHI_API_LOG_FILE", "runtime_logs/kalshi_api_log.csv")).resolve()
_PACIFIC_TZ = ZoneInfo("America/Los_Angeles")
_ENABLE_CACHE_REFRESH_SCHEDULER = os.environ.get("ENABLE_CACHE_REFRESH_SCHEDULER", "").lower() == "true"
_cache_refresh_logger = logging.getLogger("prism.cache_refresh")
_cache_refresh_lock = asyncio.Lock()
_cache_refresh_task: asyncio.Task | None = None

def _get_user_id(request: Request) -> str | None:
    """Extract and verify Supabase JWT; return user_id (sub) or None."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    if not _SUPABASE_JWT_SECRET:
        return None
    try:
        from jose import jwt
        payload = jwt.decode(token, _SUPABASE_JWT_SECRET, algorithms=["HS256"],
                             options={"verify_aud": False})
        return payload.get("sub")
    except Exception:
        return None

from forecaster.kalshi import KalshiClient
from forecaster.config import ForecasterConfig
from forecaster.forecaster_system import ForecasterSystem
from forecaster import db

# Oracle agents (from trading_companion) — imported lazily inside endpoints
# so a missing trading_companion path doesn't break the rest of the API.
_TC_AVAILABLE = _TC_PATH.exists()

app = FastAPI(title="Prism API")
logging.getLogger("prism.kalshi").setLevel(logging.INFO)
_cache_refresh_logger.setLevel(logging.INFO)

_raw_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001")
_origins = list({o.strip() for o in _raw_origins.split(",") if o.strip()} | {
    "https://forecaster-black.vercel.app",
})

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


def _get_client() -> KalshiClient:
    key_id = os.environ.get("KALSHI_API_KEY", "")
    pem      = os.environ.get("KALSHI_PRIVATE_KEY_PEM", "")
    pem_b64  = os.environ.get("KALSHI_PRIVATE_KEY_B64", "")
    pem_file = os.environ.get("KALSHI_PRIVATE_KEY_FILE", "")
    if key_id and pem_b64:
        # Base64-encoded DER — safe for env vars (no newline issues)
        return KalshiClient(key_id=key_id, private_key_pem=pem_b64.strip())
    if key_id and pem:
        # Replace literal \n in case the env var had newlines collapsed
        pem = pem.replace("\\n", "\n").strip()
        return KalshiClient(key_id=key_id, private_key_pem=pem.encode())
    if key_id and pem_file and Path(pem_file).exists():
        return KalshiClient.from_files(key_id, pem_file)
    raise HTTPException(status_code=503, detail="Kalshi credentials not configured")


def _market_dict(m) -> dict:
    return {
        "ticker": m.ticker, "event_ticker": m.event_ticker,
        "yes_sub_title": m.yes_sub_title, "no_sub_title": m.no_sub_title,
        "yes_bid": m.yes_bid, "yes_ask": m.yes_ask, "last_price": m.last_price,
        "volume": m.volume, "rules_primary": m.rules_primary,
        "rules_secondary": m.rules_secondary, "close_time": m.close_time,
        "close_date": m.close_date, "mid_price": m.mid_price,
        "question": m.question, "status": m.status,
    }


def _get_live_markets_for_events(client: KalshiClient, event_tickers: list[str]) -> list:
    all_markets: dict[str, Any] = {}
    for event_ticker in event_tickers:
        try:
            markets, _ = client.get_markets(limit=50, status="open", event_ticker=event_ticker)
        except Exception:
            continue
        for market in markets:
            if market.ticker not in all_markets:
                all_markets[market.ticker] = market
    return list(all_markets.values())


def _seconds_until_next_cache_refresh(now: datetime | None = None) -> float:
    now = now or datetime.now(_PACIFIC_TZ)
    targets: list[datetime] = []

    daily_target = now.replace(hour=1, minute=0, second=0, microsecond=0)
    if now >= daily_target:
        daily_target += timedelta(days=1)
    targets.append(daily_target)

    one_off_target = datetime(2026, 5, 6, 16, 42, tzinfo=_PACIFIC_TZ)
    if now < one_off_target:
        targets.append(one_off_target)

    next_target = min(targets)
    return max((next_target - now).total_seconds(), 0.0)


async def _run_cache_refresh() -> None:
    if _cache_refresh_lock.locked():
        _cache_refresh_logger.warning("Skipping cache refresh because a previous run is still in progress")
        return

    async with _cache_refresh_lock:
        started_at = datetime.now(_PACIFIC_TZ).isoformat()
        _cache_refresh_logger.info("Starting scheduled cache refresh at %s", started_at)
        try:
            from sync_caches import main as sync_caches_main

            await asyncio.to_thread(sync_caches_main)
            finished_at = datetime.now(_PACIFIC_TZ).isoformat()
            _cache_refresh_logger.info("Scheduled cache refresh succeeded at %s", finished_at)
        except Exception:
            _cache_refresh_logger.exception("Scheduled cache refresh failed")


async def _cache_refresh_scheduler_loop() -> None:
    _cache_refresh_logger.info("Cache refresh scheduler started")
    while True:
        sleep_seconds = _seconds_until_next_cache_refresh()
        next_run = datetime.now(_PACIFIC_TZ) + timedelta(seconds=sleep_seconds)
        _cache_refresh_logger.info(
            "Next cache refresh scheduled for %s",
            next_run.isoformat(),
        )
        await asyncio.sleep(sleep_seconds)
        await _run_cache_refresh()


@app.on_event("startup")
async def _startup_cache_refresh_scheduler() -> None:
    global _cache_refresh_task

    if not _ENABLE_CACHE_REFRESH_SCHEDULER:
        _cache_refresh_logger.info("Cache refresh scheduler disabled")
        return
    if not _TC_AVAILABLE:
        _cache_refresh_logger.warning("Cache refresh scheduler not started because trading_companion is unavailable")
        return
    if _cache_refresh_task is not None and not _cache_refresh_task.done():
        _cache_refresh_logger.warning("Cache refresh scheduler already running")
        return

    _cache_refresh_task = asyncio.create_task(_cache_refresh_scheduler_loop())


@app.on_event("shutdown")
async def _shutdown_cache_refresh_scheduler() -> None:
    global _cache_refresh_task

    if _cache_refresh_task is None:
        return
    _cache_refresh_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await _cache_refresh_task
    _cache_refresh_task = None


def _read_kalshi_log_rows(limit: int) -> list[dict[str, str]]:
    if not _KALSHI_API_LOG_FILE.exists():
        return []
    with _KALSHI_API_LOG_FILE.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if limit <= 0:
        return rows
    return rows[-limit:]


@app.get("/api/me")
async def me(request: Request):
    """Debug: returns the user_id extracted from the Bearer token."""
    user_id = _get_user_id(request)
    return {"user_id": user_id, "error": None if user_id else "invalid or missing token"}


@app.get("/api/debug/kalshi-log")
async def get_kalshi_log(limit: int = 200):
    rows = _read_kalshi_log_rows(limit)
    return {
        "path": str(_KALSHI_API_LOG_FILE),
        "exists": _KALSHI_API_LOG_FILE.exists(),
        "row_count": len(rows),
        "rows": rows,
    }


@app.get("/api/debug/kalshi-log/download")
async def download_kalshi_log():
    if not _KALSHI_API_LOG_FILE.exists():
        raise HTTPException(status_code=404, detail="Kalshi API log file not found")
    return FileResponse(
        path=_KALSHI_API_LOG_FILE,
        media_type="text/csv",
        filename=_KALSHI_API_LOG_FILE.name,
    )


@app.get("/api/events/categories")
async def list_event_categories():
    from event_cache_db import list_event_categories as list_cached_event_categories

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, list_cached_event_categories)


@app.get("/api/events")
async def search_events(query: str = "", limit: int = 24, category: str = ""):
    from event_cache_db import search_events as search_cached_events

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: search_cached_events(query, limit, category or None))


@app.get("/api/events/{event_ticker}/markets")
async def get_markets(event_ticker: str):
    client = _get_client()
    loop = asyncio.get_event_loop()
    markets, _ = await loop.run_in_executor(
        None, lambda: client.get_markets(limit=50, event_ticker=event_ticker)
    )
    return [_market_dict(m) for m in markets]


@app.get("/api/markets/{ticker}")
async def get_market(ticker: str):
    client = _get_client()
    loop = asyncio.get_event_loop()
    m = await loop.run_in_executor(None, lambda: client.get_market(ticker))
    return _market_dict(m)


@app.get("/api/forecasts")
async def list_forecasts(request: Request, limit: int = 48):
    user_id = _get_user_id(request)
    try:
        return db.get_forecasts(limit=limit, user_id=user_id)
    except Exception as e:
        return {"error": str(e), "items": []}


class ForecastRequest(BaseModel):
    ticker: str
    event_title: str
    ev_sub: str = ""
    ev_category: str = ""
    # Optional: pre-fetched market data from the frontend (avoids a second Kalshi round-trip)
    market: dict | None = None
    related_markets: list[dict] = Field(default_factory=list)


@app.post("/api/forecasts/stream")
async def stream_forecast(req: ForecastRequest, request: Request):
    client = _get_client()
    loop = asyncio.get_event_loop()

    # Use pre-supplied market data if available; otherwise fetch from Kalshi
    if req.market:
        from forecaster.kalshi import KalshiMarket
        mkt = KalshiMarket(**{k: req.market[k] for k in KalshiMarket.__dataclass_fields__})
    else:
        try:
            mkt = await loop.run_in_executor(None, lambda: client.get_market(req.ticker))
        except Exception as exc:
            # Return the error as an SSE message rather than a 500 crash
            async def _err():
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            return StreamingResponse(_err(), media_type="text/event-stream",
                                     headers={"Cache-Control": "no-cache"})

    async def _generate() -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def on_step(name: str, stage: str, data=None):
            if name == "OV Phase" and stage == "complete" and data is not None:
                asyncio.run_coroutine_threadsafe(queue.put({
                    "type": "ov_complete",
                    "base_rate": data.final_prior,
                    "reference_class": data.reference_class_summary,
                    "reasoning": data.rationale,
                }), loop)
            elif name == "IV Phase" and stage == "complete" and data is not None:
                asyncio.run_coroutine_threadsafe(queue.put({
                    "type": "iv_complete",
                    "agent_forecasts": [
                        {"key_factors_for": f.key_factors_for, "key_factors_against": f.key_factors_against}
                        for f in data
                    ],
                }), loop)
            elif "OV Agent" in name and stage == "done":
                asyncio.run_coroutine_threadsafe(
                    queue.put({"type": "progress", "label": "Researching base rate..."}), loop
                )
            elif "Agent" in name and stage == "done":
                try:
                    i, n = map(int, name.split("Agent ")[1].split("/"))
                    label = (f"Collecting evidence ({int(i / n * 100)}%)"
                             if i < n else "Analyzing findings...")
                    asyncio.run_coroutine_threadsafe(queue.put({"type": "progress", "label": label}), loop)
                except Exception:
                    pass
            elif "Supervisor" in name and stage == "done":
                asyncio.run_coroutine_threadsafe(
                    queue.put({"type": "progress", "label": "Drawing conclusions..."}), loop
                )

        async def _run():
            try:
                config = ForecasterConfig()
                # Derive series ticker by stripping the trailing -NN segment from event_ticker
                event_tk = mkt.event_ticker or ""
                parts = event_tk.rsplit("-", 1)
                series_tk = parts[0] if len(parts) == 2 and parts[1].isdigit() else event_tk or None

                memo = await loop.run_in_executor(
                    None,
                    lambda: ForecasterSystem(config).forecast(
                        question=mkt.question,
                        context=mkt.resolution_context or None,
                        related_markets=req.related_markets,
                        on_step=on_step,
                        series_ticker=series_tk,
                        event_title=req.event_title or None,
                        ev_sub=req.ev_sub or None,
                        ev_category=req.ev_category or None,
                    ),
                )
                try:
                    db.save_forecast(
                        ticker=mkt.ticker,
                        event_title=req.event_title,
                        question=mkt.question,
                        close_date=mkt.close_date,
                        category=req.ev_category,
                        kalshi_price=mkt.mid_price,
                        memo=memo,
                        context_dict={
                            "market": dataclasses.asdict(mkt),
                            "related_markets": req.related_markets,
                            "event": {
                                "title": req.event_title,
                                "sub_title": req.ev_sub,
                                "category": req.ev_category,
                            },
                        },
                        user_id=_get_user_id(request),
                    )
                except Exception:
                    pass  # don't fail the whole stream if save fails
                await queue.put({
                    "type": "complete",
                    "memo": json.loads(memo.model_dump_json()),
                    "kalshi_price": mkt.mid_price,
                    "close_date": mkt.close_date,
                })
            except Exception as ex:
                await queue.put({"type": "error", "message": str(ex)})

        task = asyncio.create_task(_run())
        try:
            while True:
                try:
                    # shield queue.get() so a timeout doesn't cancel the coroutine
                    msg = await asyncio.wait_for(asyncio.shield(queue.get()), timeout=360.0)
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Forecast timed out after 6 minutes'})}\n\n"
                    task.cancel()
                    break
                yield f"data: {json.dumps(msg)}\n\n"
                if msg["type"] in ("complete", "error"):
                    break
        finally:
            # Always clean up the task — swallow any leftover exceptions
            try:
                await asyncio.wait_for(task, timeout=10.0)
            except Exception:
                pass

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Oracle endpoints (legacy) ─────────────────────────────────────────────────

class OracleTurnRequest(BaseModel):
    history: list[Any] = []
    message: str

    model_config = {"arbitrary_types_allowed": True}


class OraclePipelineRequest(BaseModel):
    belief_summary: dict[str, Any]


@app.post("/api/oracle/turn")
async def oracle_turn(req: OracleTurnRequest):
    if not _TC_AVAILABLE:
        raise HTTPException(status_code=503, detail="Oracle not available: trading_companion not found")

    from agents.belief_agent import BeliefAgent

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, lambda: BeliefAgent().step(req.history, req.message)
    )
    return result


@app.post("/api/oracle/pipeline/stream")
async def oracle_pipeline_stream(req: OraclePipelineRequest):
    if not _TC_AVAILABLE:
        async def _err():
            yield f"data: {json.dumps({'type': 'error', 'message': 'trading_companion not found'})}\n\n"
        return StreamingResponse(_err(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    from agents.analyst_agent import AnalystAgent
    from agents.screener_agent import ScreenerAgent
    from agents.curator_agent import CuratorAgent
    from event_cache_db import get_event_lookup
    from kalshi import KalshiClient as TradingKalshiClient

    async def _generate() -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        async def _run():
            try:
                belief = req.belief_summary

                # Stage 1: Analyst
                await queue.put({"type": "stage", "stage": "analyst", "status": "running"})
                analysis = await loop.run_in_executor(None, lambda: AnalystAgent().run(belief))
                high_med = [d for d in analysis["affected_domains"] if d["relevance"] in ("high", "medium")]
                await queue.put({
                    "type": "stage", "stage": "analyst", "status": "done",
                    "data": {"domains": high_med, "insight": analysis.get("most_surprising_connection", "")},
                })

                # Stage 2: Screener
                await queue.put({"type": "stage", "stage": "screener", "status": "running"})
                _screener_result = await loop.run_in_executor(
                    None, lambda: ScreenerAgent().run(belief, analysis)
                )
                event_tickers = [c["event_ticker"] for c in _screener_result.get("candidates", [])]
                await queue.put({
                    "type": "stage", "stage": "screener", "status": "done",
                    "data": {"event_count": len(event_tickers)},
                })

                if not event_tickers:
                    await queue.put({"type": "error", "message": "No relevant events found. Run sync_events.py to refresh the cache."})
                    return

                # Stage 3: Fetch markets
                await queue.put({"type": "stage", "stage": "markets", "status": "running"})

                def _fetch_markets():
                    client = TradingKalshiClient.from_env()
                    all_markets: dict = {}
                    for ticker in event_tickers:
                        try:
                            mkts, _ = client.get_markets(limit=20, status="open", event_ticker=ticker)
                            for m in mkts:
                                if m.ticker not in all_markets:
                                    all_markets[m.ticker] = m
                        except Exception:
                            pass
                    return list(all_markets.values())

                markets = await loop.run_in_executor(None, _fetch_markets)
                await queue.put({
                    "type": "stage", "stage": "markets", "status": "done",
                    "data": {"market_count": len(markets)},
                })

                if not markets:
                    await queue.put({"type": "error", "message": "No open markets found for the shortlisted events."})
                    return

                # Stage 4: Curator
                await queue.put({"type": "stage", "stage": "curator", "status": "running"})
                recommendations = await loop.run_in_executor(
                    None, lambda: CuratorAgent().run(belief, markets, analysis)
                )

                await queue.put({
                    "type": "complete",
                    "data": {
                        "recommendations": recommendations,
                        "analysis": {
                            "domains": high_med,
                            "insight": analysis.get("most_surprising_connection", ""),
                        },
                    },
                })

            except FileNotFoundError as exc:
                await queue.put({"type": "error", "message": f"Events cache missing — run sync_events.py first. ({exc})"})
            except Exception as exc:
                await queue.put({"type": "error", "message": str(exc)})

        task = asyncio.create_task(_run())
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(asyncio.shield(queue.get()), timeout=360.0)
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Pipeline timed out'})}\n\n"
                    task.cancel()
                    break
                yield f"data: {json.dumps(msg)}\n\n"
                if msg["type"] in ("complete", "error"):
                    break
        finally:
            try:
                await asyncio.wait_for(task, timeout=10.0)
            except Exception:
                pass

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Trading Companion (Compass) ───────────────────────────────────────────────

class TradingChatRequest(BaseModel):
    history: list[dict]
    message: str
    mode: str = "thinking"


@app.get("/api/baskets")
async def list_baskets(request: Request, limit: int = 20):
    user_id = _get_user_id(request)
    try:
        return db.get_baskets(limit=limit, user_id=user_id, public_only=not bool(user_id))
    except Exception as e:
        return {"error": str(e), "items": []}


@app.get("/api/baskets/{basket_id}")
async def get_basket(basket_id: int, request: Request):
    user_id = _get_user_id(request)
    basket = db.get_basket(basket_id, user_id=user_id)
    if not basket:
        raise HTTPException(status_code=404, detail="Basket not found")
    return basket


@app.post("/api/trading/chat")
async def trading_chat(req: TradingChatRequest):
    if not _TC_AVAILABLE:
        raise HTTPException(status_code=503, detail="Trading companion not available")
    loop = asyncio.get_event_loop()

    def _run():
        from agents.belief_agent import BeliefAgent
        return BeliefAgent().step(req.history, req.message, mode=req.mode)

    try:
        result = await loop.run_in_executor(None, _run)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return result


class TradingAnalyzeRequest(BaseModel):
    belief_summary: dict
    mode: str = "thinking"


class ManualBasketHoldingRequest(BaseModel):
    ticker: str
    event_ticker: str
    question: str
    market_price: float
    close_date: str
    side: str
    role: str
    weight_dollars: float
    rationale: str = ""
    main_risk: str = ""
    rules_summary: str = ""


class ManualBasketRequest(BaseModel):
    title: str
    summary: str
    timeframe: str = ""
    holdings: list[ManualBasketHoldingRequest]
    is_public: bool = True


@app.post("/api/trading/analyze")
async def trading_analyze(req: TradingAnalyzeRequest, request: Request):
    if not _TC_AVAILABLE:
        async def _unavail():
            yield f"data: {json.dumps({'type': 'error', 'message': 'Trading companion not available'})}\n\n"
        return StreamingResponse(_unavail(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    async def _tc_generate() -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def _run():
            try:
                from agents.analyst_agent import AnalystAgent
                from agents.screener_agent import ScreenerAgent
                from agents.curator_agent import BasketBuilderAgent

                asyncio.run_coroutine_threadsafe(
                    queue.put({"type": "progress", "label": "Mapping the thesis across key domains…"}), loop
                )
                analysis = AnalystAgent().run(req.belief_summary)
                asyncio.run_coroutine_threadsafe(
                    queue.put({"type": "analyst_done", "analysis": analysis}), loop
                )

                asyncio.run_coroutine_threadsafe(
                    queue.put({"type": "progress", "label": "Screening Kalshi event catalog…"}), loop
                )
                screener_result = ScreenerAgent().run(req.belief_summary, analysis)
                all_candidates = screener_result["candidates"]
                rejected_patterns = screener_result.get("rejected_patterns", [])

                # Debug logging
                print(f"\n[COMPASS] Belief: {req.belief_summary.get('core_belief', '')}")
                print(f"[COMPASS] Resolution target: {req.belief_summary.get('resolution_target', 'not set')}")
                print(f"[COMPASS] Mechanism: {req.belief_summary.get('mechanism', 'not set')}")
                print(f"[COMPASS] Timeframe: {req.belief_summary.get('timeframe_start', '?')} → {req.belief_summary.get('timeframe_end', req.belief_summary.get('time_horizon', '?'))}")
                if analysis:
                    kept_domains = [d for d in analysis.get("affected_domains", []) if d.get("keep_for_market_search")]
                    print(f"[COMPASS] Domains kept for search ({len(kept_domains)}):")
                    for d in kept_domains:
                        print(f"  [{d.get('causal_distance','?')}] {d['domain']} | expr={d.get('expressiveness_score')} purity={d.get('causal_purity_score')} time={d.get('timeframe_alignment_score')}")
                print(f"[COMPASS] Screener raw candidates: {len(all_candidates)}")
                tier_groups: dict = {}
                for c in all_candidates:
                    t = c.get("tier", "unknown")
                    tier_groups.setdefault(t, []).append(c)
                for tier, cs in tier_groups.items():
                    print(f"  [{tier}] {len(cs)} events: {', '.join(c['event_ticker'] for c in cs)}")
                print(f"[COMPASS] Rejected patterns: {rejected_patterns}")

                # Relevance filter
                TIER_PRIORITY = {"direct_thesis": 0, "mechanism": 1, "first_order_consequence": 2, "hedge_or_falsifier": 3}
                filtered_candidates = [
                    c for c in all_candidates
                    if c.get("overall_score", 0) >= 3.0
                    and c.get("expressiveness_score", 0) >= 3
                    and c.get("timeframe_alignment_score", 0) >= 2
                    and not (c.get("tier") == "first_order_consequence" and c.get("causal_purity_score", 0) < 3)
                ]
                print(f"[COMPASS] After filter: {len(filtered_candidates)} candidates")

                if not filtered_candidates:
                    asyncio.run_coroutine_threadsafe(
                        queue.put({"type": "error", "message": "No relevant markets found matching quality thresholds."}), loop
                    )
                    return

                event_tickers = [c["event_ticker"] for c in filtered_candidates]
                asyncio.run_coroutine_threadsafe(
                    queue.put({"type": "screener_done", "tickers": event_tickers, "count": len(event_tickers)}), loop
                )

                from event_cache_db import get_event_lookup
                from market_cache_db import get_markets_for_events

                asyncio.run_coroutine_threadsafe(
                    queue.put({"type": "progress", "label": f"Loading cached markets for {len(event_tickers)} events…"}), loop
                )

                candidate_by_event: dict = {c["event_ticker"]: c for c in filtered_candidates}
                try:
                    cached_rows = get_markets_for_events(event_tickers)
                except Exception:
                    cached_rows = []

                if cached_rows:
                    from forecaster.kalshi import KalshiMarket

                    markets = [
                        KalshiMarket(**{
                            "ticker": row["ticker"],
                            "event_ticker": row["event_ticker"],
                            "yes_sub_title": row["yes_sub_title"],
                            "no_sub_title": row["no_sub_title"],
                            "yes_bid": row["yes_bid"],
                            "yes_ask": row["yes_ask"],
                            "last_price": row["last_price"],
                            "volume": row["volume"],
                            "rules_primary": row["rules_primary"],
                            "rules_secondary": row["rules_secondary"],
                            "close_time": row["close_time"],
                            "status": row["status"],
                        })
                        for row in cached_rows
                    ]
                else:
                    asyncio.run_coroutine_threadsafe(
                        queue.put({"type": "progress", "label": "Cached market DB is empty; fetching open markets live…"}), loop
                    )
                    kalshi_client = _get_client()
                    markets = _get_live_markets_for_events(kalshi_client, event_tickers)

                if not markets:
                    asyncio.run_coroutine_threadsafe(
                        queue.put({"type": "error", "message": "No open markets found for the shortlisted events."}), loop
                    )
                    return

                # Sort markets: screener score desc → tier priority → volume desc
                def _market_sort_key(m):
                    c = candidate_by_event.get(m.event_ticker, {})
                    score = c.get("overall_score", 0)
                    tier_rank = TIER_PRIORITY.get(c.get("tier", ""), 99)
                    return (-score, tier_rank, -m.volume)

                markets.sort(key=_market_sort_key)

                asyncio.run_coroutine_threadsafe(
                    queue.put({"type": "progress", "label": f"Building a $100 prediction market ETF from {len(markets)} candidate markets…"}), loop
                )
                basket = BasketBuilderAgent().run(req.belief_summary, markets, analysis,
                                                  screener_candidates=filtered_candidates)

                # Debug: final basket
                print(f"[COMPASS] Final basket ({len(basket.get('holdings', []))} holdings):")
                for holding in basket.get("holdings", []):
                    print(f"  [{holding.get('role','?')}] {holding['ticker']} | {holding['side']} | ${holding['weight_dollars']}")

                event_lookup = get_event_lookup([holding.get("event_ticker", "") for holding in basket.get("holdings", [])])
                for holding in basket.get("holdings", []):
                    evt = event_lookup.get(holding.get("event_ticker", ""), {})
                    holding["event_title"] = evt.get("title", "")
                    holding["series_ticker"] = evt.get("series_ticker", "")
                    holding["category"] = evt.get("category", "")

                basket_id: int | None = None
                try:
                    basket_id = db.save_basket(
                        title=basket.get("basket_title", req.belief_summary.get("core_belief", "Prediction Market ETF")),
                        summary=basket.get("basket_summary", ""),
                        core_belief=req.belief_summary.get("core_belief", ""),
                        mode=req.mode or req.belief_summary.get("mode_used", "thinking"),
                        time_horizon=req.belief_summary.get("time_horizon", ""),
                        timeframe_start=req.belief_summary.get("timeframe_start", ""),
                        timeframe_end=req.belief_summary.get("timeframe_end", req.belief_summary.get("time_horizon", "")),
                        resolution_target=req.belief_summary.get("resolution_target", ""),
                        mechanism=req.belief_summary.get("mechanism", ""),
                        scope=req.belief_summary.get("scope", ""),
                        key_drivers=req.belief_summary.get("key_drivers", []),
                        belief_summary=req.belief_summary,
                        analysis=analysis,
                        basket=basket,
                        total_notional=basket.get("total_notional", 100.0),
                        screened_count=len(filtered_candidates),
                        holdings=basket.get("holdings", []),
                        user_id=_get_user_id(request),
                    )
                except Exception:
                    pass

                asyncio.run_coroutine_threadsafe(
                    queue.put({"type": "basket_done", "basket": basket, "basket_id": basket_id}), loop
                )

            except Exception as exc:
                asyncio.run_coroutine_threadsafe(
                    queue.put({"type": "error", "message": str(exc)}), loop
                )

        task = loop.run_in_executor(None, _run)
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(asyncio.shield(queue.get()), timeout=300.0)
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Analysis timed out'})}\n\n"
                    break
                yield f"data: {json.dumps(msg)}\n\n"
                if msg["type"] in ("basket_done", "error"):
                    break
        finally:
            try:
                await asyncio.wait_for(task, timeout=10.0)
            except Exception:
                pass

    return StreamingResponse(
        _tc_generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/baskets/manual")
async def create_manual_basket(req: ManualBasketRequest, request: Request):
    if not req.holdings:
        raise HTTPException(status_code=400, detail="At least one holding is required")

    total_notional = round(sum(max(0.0, h.weight_dollars) for h in req.holdings), 2)
    if total_notional <= 0:
        raise HTTPException(status_code=400, detail="Basket total must be positive")

    normalized_holdings = []
    running_total = 0.0
    holdings = sorted(req.holdings, key=lambda h: h.weight_dollars, reverse=True)
    for idx, holding in enumerate(holdings):
        if idx == len(holdings) - 1:
            weight = round(100.0 - running_total, 2)
        else:
            weight = round((holding.weight_dollars / total_notional) * 100.0, 2)
            running_total += weight
        normalized_holdings.append({
            "ticker": holding.ticker,
            "event_ticker": holding.event_ticker,
            "question": holding.question,
            "market_price": holding.market_price,
            "close_date": holding.close_date,
            "side": holding.side,
            "role": holding.role,
            "weight_dollars": weight,
            "rationale": holding.rationale,
            "main_risk": holding.main_risk,
            "rules_summary": holding.rules_summary,
        })

    basket_payload = {
        "basket_title": req.title,
        "basket_summary": req.summary,
        "construction_notes": "Manually constructed by the user from selected Kalshi contracts.",
        "holdings": normalized_holdings,
        "total_notional": 100.0,
    }
    belief_summary = {
        "core_belief": req.title,
        "time_horizon": req.timeframe,
        "key_drivers": [],
        "scope": "Manual basket",
        "confidence_level": "medium",
        "supporting_reasoning": req.summary,
        "current_context": "",
        "resolution_target": req.summary,
        "timeframe_start": "now",
        "timeframe_end": req.timeframe,
        "mechanism": "User-selected basket",
        "falsifiers": [],
        "mode_used": "manual",
    }
    analysis = {"affected_domains": [], "most_surprising_connection": ""}

    basket_id = db.save_basket(
        title=req.title,
        summary=req.summary,
        core_belief=req.title,
        mode="manual",
        time_horizon=req.timeframe,
        timeframe_start="now",
        timeframe_end=req.timeframe,
        resolution_target=req.summary,
        mechanism="User-selected basket",
        scope="Manual basket",
        key_drivers=[],
        belief_summary=belief_summary,
        analysis=analysis,
        basket=basket_payload,
        total_notional=100.0,
        screened_count=len(normalized_holdings),
        holdings=normalized_holdings,
        is_public=req.is_public,
        user_id=_get_user_id(request),
    )
    saved = db.get_basket(basket_id, user_id=_get_user_id(request))
    return {"basket_id": basket_id, "basket": saved}
