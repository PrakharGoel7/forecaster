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

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ── Clerk JWT verification ────────────────────────────────────────────────────

def _derive_jwks_url() -> str:
    """Derive JWKS URL from CLERK_PUBLISHABLE_KEY if CLERK_JWKS_URL not set."""
    explicit = os.environ.get("CLERK_JWKS_URL", "")
    if explicit:
        return explicit
    # Support both naming conventions
    pk = (os.environ.get("CLERK_PUBLISHABLE_KEY", "")
          or os.environ.get("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", ""))
    if not pk:
        return ""
    try:
        import base64
        # pk format: pk_test_<b64> or pk_live_<b64>
        encoded = pk.split("_", 2)[2]
        padded = encoded + "=" * (-len(encoded) % 4)
        frontend_api = base64.b64decode(padded).decode().rstrip("$")
        return f"https://{frontend_api}/.well-known/jwks.json"
    except Exception:
        return ""

_CLERK_JWKS_URL = _derive_jwks_url()
_jwks_cache: dict = {}

def _get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache:
        return _jwks_cache
    if not _CLERK_JWKS_URL:
        return {}
    try:
        import httpx as _httpx
        resp = _httpx.get(_CLERK_JWKS_URL, timeout=5)
        _jwks_cache = resp.json()
    except Exception:
        pass
    return _jwks_cache

def _get_user_id(request: Request) -> str | None:
    """Extract and verify Clerk JWT; return user_id (sub) or None."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    try:
        from jose import jwt, jwk
        header = jwt.get_unverified_header(token)
        kid = header.get("kid", "")
        keys = _get_jwks().get("keys", [])
        key_data = next((k for k in keys if k.get("kid") == kid), None)
        if not key_data:
            return None
        public_key = jwk.construct(key_data)
        payload = jwt.decode(token, public_key, algorithms=["RS256"],
                             options={"verify_aud": False, "verify_at_hash": False})
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


@app.get("/api/me")
async def me(request: Request):
    """Debug: returns the user_id extracted from the Bearer token."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return {"user_id": None, "jwks_url": _CLERK_JWKS_URL or "(not set)", "error": "no Bearer token"}
    token = auth[7:]
    try:
        from jose import jwt, jwk
        header = jwt.get_unverified_header(token)
        kid = header.get("kid", "")
        keys = _get_jwks().get("keys", [])
        key_data = next((k for k in keys if k.get("kid") == kid), None)
        if not key_data:
            return {"user_id": None, "jwks_url": _CLERK_JWKS_URL or "(not set)",
                    "error": f"kid '{kid}' not found in JWKS. Available kids: {[k.get('kid') for k in keys]}"}
        public_key = jwk.construct(key_data)
        payload = jwt.decode(token, public_key, algorithms=["RS256"],
                             options={"verify_aud": False, "verify_at_hash": False})
        return {"user_id": payload.get("sub"), "jwks_url": _CLERK_JWKS_URL or "(not set)", "error": None}
    except Exception as e:
        return {"user_id": None, "jwks_url": _CLERK_JWKS_URL or "(not set)", "error": str(e)}


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
                    "base_rate": data.base_rate,
                    "reference_class": data.reference_class,
                    "reasoning": data.reasoning,
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
                try:
                    i, n = map(int, name.split("OV Agent ")[1].split("/"))
                    asyncio.run_coroutine_threadsafe(
                        queue.put({"type": "progress", "label": f"Researching base rate ({int(i / n * 100)}%)"}), loop
                    )
                except Exception:
                    pass
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


@app.get("/api/trading/sessions")
async def list_trading_sessions(request: Request, limit: int = 20):
    user_id = _get_user_id(request)
    try:
        return db.get_trading_sessions(limit=limit, user_id=user_id)
    except Exception as e:
        return {"error": str(e), "items": []}


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

                client = _get_client()
                asyncio.run_coroutine_threadsafe(
                    queue.put({"type": "progress", "label": f"Fetching live markets for {len(event_tickers)} events…"}), loop
                )

                # Fetch live markets
                candidate_by_event: dict = {c["event_ticker"]: c for c in filtered_candidates}
                markets: list = []
                seen: set = set()
                for ticker in event_tickers:
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
                    queue.put({"type": "progress", "label": f"Curating best bets from {len(markets)} live markets…"}), loop
                )
                recommendations = CuratorAgent().run(req.belief_summary, markets, analysis,
                                                     screener_candidates=filtered_candidates)

                # Debug: final portfolio
                print(f"[COMPASS] Final portfolio ({len(recommendations)} markets):")
                for r in recommendations:
                    print(f"  [{r.get('tier','?')}] {r['ticker']} | {r['direction']} | score={r['score']}")

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
                        user_id=_get_user_id(request),
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
