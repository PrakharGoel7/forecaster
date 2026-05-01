"""Prism API — FastAPI backend wrapping the forecaster package."""
import asyncio
import dataclasses
import json
import os
import sys
from pathlib import Path
from typing import Any, AsyncIterator

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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from forecaster.kalshi import KalshiClient
from forecaster.config import ForecasterConfig
from forecaster.forecaster_system import ForecasterSystem
from forecaster import db

# Oracle agents (from trading_companion) — imported lazily inside endpoints
# so a missing trading_companion path doesn't break the rest of the API.
_TC_AVAILABLE = _TC_PATH.exists()

app = FastAPI(title="Prism API")

_raw_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001")
_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.get("/api/events")
async def search_events(query: str = "", limit: int = 24):
    client = _get_client()
    loop = asyncio.get_event_loop()

    def _fetch():
        pages = 10 if query else 3
        events, cursor = [], None
        for _ in range(pages):
            batch, cursor = client.get_events(limit=100, cursor=cursor)
            events += batch
            if not cursor:
                break
        if query:
            q = query.lower()
            events = [e for e in events if e.matches(q)]
        return events[:limit]

    events = await loop.run_in_executor(None, _fetch)
    return [
        {"event_ticker": e.event_ticker, "series_ticker": e.series_ticker,
         "title": e.title, "sub_title": e.sub_title, "category": e.category}
        for e in events
    ]


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
async def list_forecasts(limit: int = 48):
    return db.get_forecasts(limit=limit)


class ForecastRequest(BaseModel):
    ticker: str
    event_title: str
    ev_sub: str = ""
    ev_category: str = ""
    # Optional: pre-fetched market data from the frontend (avoids a second Kalshi round-trip)
    market: dict | None = None


@app.post("/api/forecasts/stream")
async def stream_forecast(req: ForecastRequest):
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

        def on_step(name: str, stage: str):
            if "Agent" in name:
                try:
                    i, n = map(int, name.split("Agent ")[1].split("/"))
                    if stage == "done":
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
                            "event": {
                                "title": req.event_title,
                                "sub_title": req.ev_sub,
                                "category": req.ev_category,
                            },
                        },
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
                event_tickers = await loop.run_in_executor(
                    None, lambda: ScreenerAgent().run(belief, analysis)
                )
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


@app.get("/api/trading/sessions")
async def list_trading_sessions(limit: int = 20):
    return db.get_trading_sessions(limit=limit)


@app.post("/api/trading/chat")
async def trading_chat(req: TradingChatRequest):
    if not _TC_AVAILABLE:
        raise HTTPException(status_code=503, detail="Trading companion not available")
    loop = asyncio.get_event_loop()

    def _run():
        from agents.belief_agent import BeliefAgent
        return BeliefAgent().step(req.history, req.message)

    try:
        result = await loop.run_in_executor(None, _run)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return result


class TradingAnalyzeRequest(BaseModel):
    belief_summary: dict


@app.post("/api/trading/analyze")
async def trading_analyze(req: TradingAnalyzeRequest):
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
                from agents.screener_agent import ScreenerAgent, CACHE_FILE
                from agents.curator_agent import CuratorAgent

                asyncio.run_coroutine_threadsafe(
                    queue.put({"type": "progress", "label": "Analyzing ramifications across 16 domains…"}), loop
                )
                analysis = AnalystAgent().run(req.belief_summary)
                asyncio.run_coroutine_threadsafe(
                    queue.put({"type": "analyst_done", "analysis": analysis}), loop
                )

                asyncio.run_coroutine_threadsafe(
                    queue.put({"type": "progress", "label": "Screening Kalshi event catalog…"}), loop
                )
                tickers = ScreenerAgent().run(req.belief_summary, analysis)
                asyncio.run_coroutine_threadsafe(
                    queue.put({"type": "screener_done", "tickers": tickers, "count": len(tickers)}), loop
                )

                if not tickers:
                    asyncio.run_coroutine_threadsafe(
                        queue.put({"type": "error", "message": "No relevant markets found."}), loop
                    )
                    return

                client = _get_client()
                asyncio.run_coroutine_threadsafe(
                    queue.put({"type": "progress", "label": f"Fetching live markets for {len(tickers)} events…"}), loop
                )
                markets: list = []
                seen: set = set()
                for ticker in tickers:
                    try:
                        batch, _ = client.get_markets(limit=20, status="open", event_ticker=ticker)
                        for m in batch:
                            if m.ticker not in seen:
                                seen.add(m.ticker)
                                markets.append(m)
                    except Exception:
                        pass

                if not markets:
                    asyncio.run_coroutine_threadsafe(
                        queue.put({"type": "error", "message": "No open markets found."}), loop
                    )
                    return

                asyncio.run_coroutine_threadsafe(
                    queue.put({"type": "progress", "label": f"Curating best bets from {len(markets)} live markets…"}), loop
                )
                recommendations = CuratorAgent().run(req.belief_summary, markets, analysis)

                event_lookup: dict = {}
                if CACHE_FILE.exists():
                    _data = json.loads(CACHE_FILE.read_text())
                    event_lookup = {e["event_ticker"]: e for e in _data.get("events", [])}
                for rec in recommendations:
                    evt = event_lookup.get(rec.get("event_ticker", ""), {})
                    rec["event_title"]   = evt.get("title", "")
                    rec["series_ticker"] = evt.get("series_ticker", "")
                    rec["category"]      = evt.get("category", "")

                session_id: int | None = None
                try:
                    session_id = db.save_trading_session(
                        core_belief=req.belief_summary.get("core_belief", ""),
                        time_horizon=req.belief_summary.get("time_horizon", ""),
                        scope=req.belief_summary.get("scope", ""),
                        key_drivers=req.belief_summary.get("key_drivers", []),
                        belief_summary=req.belief_summary,
                        analysis=analysis,
                        recommendations=recommendations,
                    )
                except Exception:
                    pass

                asyncio.run_coroutine_threadsafe(
                    queue.put({"type": "curator_done", "recommendations": recommendations, "session_id": session_id}), loop
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
                if msg["type"] in ("curator_done", "error"):
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
