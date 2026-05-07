"""Prism API — FastAPI backend wrapping the forecaster package."""
import asyncio
import contextlib
import csv
import dataclasses
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, AsyncIterator, Callable
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
_TRADING_PIPELINE_DEBUG_DIR = (_REPO_ROOT / os.environ.get("TRADING_PIPELINE_DEBUG_DIR", "runtime_logs/trading_pipeline_runs")).resolve()
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
if _TC_AVAILABLE:
    from pipeline_utils import (
        apply_critic_repairs as _apply_critic_repairs,
        exposure_analysis_payload as _exposure_analysis_payload,
        normalize_weights as _normalize_weights,
        validate_and_repair_basket as _validate_and_repair_basket,
    )

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

    one_off_target = datetime(2026, 5, 7, 10, 42, tzinfo=_PACIFIC_TZ)
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


def _ensure_trading_pipeline_debug_dir() -> Path:
    _TRADING_PIPELINE_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    return _TRADING_PIPELINE_DEBUG_DIR


def _trading_pipeline_debug_path(run_id: str) -> Path:
    return _ensure_trading_pipeline_debug_dir() / f"{run_id}.json"


def _save_trading_pipeline_debug_run(run_id: str, payload: dict[str, Any]) -> Path:
    path = _trading_pipeline_debug_path(run_id)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


def _load_trading_pipeline_debug_run(run_id: str) -> tuple[Path, dict[str, Any]]:
    path = _trading_pipeline_debug_path(run_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Trading pipeline debug run not found")
    with path.open("r", encoding="utf-8") as f:
        return path, json.load(f)


def _list_trading_pipeline_debug_runs(limit: int = 20) -> list[dict[str, Any]]:
    debug_dir = _ensure_trading_pipeline_debug_dir()
    runs: list[dict[str, Any]] = []
    for path in sorted(debug_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:max(limit, 0)]:
        try:
            with path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            continue
        runs.append({
            "run_id": payload.get("run_id", path.stem),
            "created_at": payload.get("created_at"),
            "label": payload.get("label", ""),
            "mode": payload.get("mode", ""),
            "example_count": payload.get("summary", {}).get("example_count", len(payload.get("examples", []))),
            "completed_count": payload.get("summary", {}).get("completed_count", 0),
            "error_count": payload.get("summary", {}).get("error_count", 0),
            "path": str(path),
        })
    return runs


def _default_trading_pipeline_examples() -> list[dict[str, Any]]:
    return [
        {
            "label": "AI labor shock",
            "message": "By the end of 2028, AI coding agents handle most routine entry-level software work. Junior engineering hiring drops meaningfully as a result.",
            "belief_summary": {
                "core_belief": "By the end of 2028, AI coding agents handle most routine entry-level software work and materially reduce junior engineering hiring.",
                "time_horizon": "through the end of 2028",
                "belief_direction": "happen",
                "desired_exposure": "Markets that benefit if AI automation and labor displacement accelerate.",
                "key_drivers": ["rapid coding-agent capability gains", "enterprise cost pressure", "wider production adoption"],
                "scope": "AI software tooling and entry-level technology labor markets",
                "confidence_level": "medium",
                "confidence_style": "strong_directional",
                "supporting_reasoning": "Coding agents are improving quickly and employers have a direct incentive to replace repetitive junior tasks with automation.",
                "current_context": "Agentic coding products are being adopted broadly across software teams in 2026.",
                "resolution_target": "AI coding agents perform most routine entry-level software work and reduce junior hiring demand by the end of 2028.",
                "resolution_type": "other",
                "timeframe_start": "now",
                "timeframe_end": "2028-12-31",
                "mechanism": ["routine coding tasks become automatable", "teams reduce junior headcount", "AI tooling spend rises"],
                "falsifiers": ["coding agents stall technically", "enterprises reject production deployment", "junior hiring remains resilient"],
                "timeframe_inferred": False,
                "mode_used": "thinking",
            },
        },
        {
            "label": "Taiwan conflict",
            "message": "Before the end of 2029, China initiates a direct military attack or blockade against Taiwan. The move triggers a major geopolitical shock.",
            "belief_summary": {
                "core_belief": "Before the end of 2029, China initiates a direct military attack or blockade against Taiwan.",
                "time_horizon": "before the end of 2029",
                "belief_direction": "happen",
                "desired_exposure": "Markets that benefit from a China-Taiwan military crisis and the resulting geopolitical repricing.",
                "key_drivers": ["Beijing reunification incentives", "military buildup", "cross-strait deterrence failure"],
                "scope": "Taiwan, US-China geopolitics, defense, and global risk markets",
                "confidence_level": "medium",
                "confidence_style": "speculative",
                "supporting_reasoning": "The strategic incentives and military preparation point to rising conflict risk over the rest of the decade.",
                "current_context": "Cross-strait military tensions remain elevated in 2026.",
                "resolution_target": "China launches a direct military attack, invasion, or sustained blockade against Taiwan.",
                "resolution_type": "formal_resolution",
                "timeframe_start": "now",
                "timeframe_end": "2029-12-31",
                "mechanism": ["deterrence weakens", "China escalates coercion", "military action becomes politically acceptable"],
                "falsifiers": ["long-term diplomatic stabilization", "credible deterrence strengthens", "Chinese leadership deprioritizes Taiwan"],
                "timeframe_inferred": False,
                "mode_used": "thinking",
            },
        },
        {
            "label": "GLP-1 adoption",
            "message": "By the end of 2028, GLP-1 drugs materially reduce US obesity rates. Adoption becomes broad enough to reshape healthcare demand.",
            "belief_summary": {
                "core_belief": "By the end of 2028, GLP-1 drugs materially reduce US obesity rates and reshape healthcare demand.",
                "time_horizon": "by the end of 2028",
                "belief_direction": "decrease",
                "desired_exposure": "Markets that benefit if GLP-1 adoption improves obesity outcomes and changes healthcare demand.",
                "key_drivers": ["insurance coverage expansion", "better drug availability", "strong patient adherence"],
                "scope": "US obesity, pharmaceuticals, healthcare utilization, and consumer health",
                "confidence_level": "medium",
                "confidence_style": "strong_directional",
                "supporting_reasoning": "The drugs are effective and broader reimbursement plus manufacturing scale could make them systemically important.",
                "current_context": "GLP-1 uptake is rising in the US in 2026, but access and supply remain constraints.",
                "resolution_target": "US obesity rates fall materially because GLP-1 use reaches broad enough scale by the end of 2028.",
                "resolution_type": "other",
                "timeframe_start": "now",
                "timeframe_end": "2028-12-31",
                "mechanism": ["coverage broadens", "supply expands", "weight-loss outcomes persist"],
                "falsifiers": ["coverage remains narrow", "side effects limit adoption", "supply bottlenecks persist"],
                "timeframe_inferred": False,
                "mode_used": "thinking",
            },
        },
        {
            "label": "Rates higher for longer",
            "message": "US interest rates stay elevated through 2027 and the Fed does not ease as aggressively as markets expect. Inflation and growth stay sticky enough to delay cuts.",
            "belief_summary": {
                "core_belief": "US interest rates stay elevated through 2027 and the Fed does not ease as aggressively as markets expect.",
                "time_horizon": "through 2027",
                "belief_direction": "not_happen",
                "desired_exposure": "Markets that benefit if rate cuts are delayed and inflation remains sticky.",
                "key_drivers": ["sticky services inflation", "resilient labor market", "fiscal support to growth"],
                "scope": "US monetary policy, inflation, rates markets, and macro-sensitive sectors",
                "confidence_level": "medium",
                "confidence_style": "strong_directional",
                "supporting_reasoning": "Inflation persistence and still-resilient growth could keep the Fed cautious for longer than consensus expects.",
                "current_context": "Markets in 2026 are highly sensitive to the path of Fed easing.",
                "resolution_target": "The Fed delivers fewer or later rate cuts than consensus expects through 2027.",
                "resolution_type": "policy_change",
                "timeframe_start": "now",
                "timeframe_end": "2027-12-31",
                "mechanism": ["inflation stays sticky", "growth avoids a hard slowdown", "Fed keeps restrictive policy longer"],
                "falsifiers": ["rapid disinflation", "labor market deterioration", "recession forcing faster cuts"],
                "timeframe_inferred": False,
                "mode_used": "thinking",
            },
        },
        {
            "label": "Bitcoin breakout",
            "message": "Bitcoin reaches $250,000 before the end of 2028. Institutional demand and macro debasement fears drive the move.",
            "belief_summary": {
                "core_belief": "Bitcoin reaches $250,000 before the end of 2028.",
                "time_horizon": "before the end of 2028",
                "belief_direction": "happen",
                "desired_exposure": "Markets that benefit if Bitcoin experiences a major upside breakout.",
                "key_drivers": ["institutional adoption", "ETF and treasury demand", "macro debasement concerns"],
                "scope": "Bitcoin and crypto market sentiment",
                "confidence_level": "medium",
                "confidence_style": "speculative",
                "supporting_reasoning": "A mix of institutional adoption and macro demand could drive a large upside repricing.",
                "current_context": "Bitcoin remains one of the most actively traded macro-sensitive digital assets in 2026.",
                "resolution_target": "Bitcoin price reaches or exceeds $250,000.",
                "resolution_type": "price_move",
                "timeframe_start": "now",
                "timeframe_end": "2028-12-31",
                "mechanism": ["capital inflows accelerate", "supply remains constrained", "macro demand for scarce assets rises"],
                "falsifiers": ["regulatory crackdown", "major security failure", "institutional demand fades"],
                "timeframe_inferred": False,
                "mode_used": "thinking",
            },
        },
        {
            "label": "Climate insurance stress",
            "message": "Over the next two years, repeated climate disasters materially strain US property insurance markets. Premiums rise and carrier withdrawals accelerate in exposed states.",
            "belief_summary": {
                "core_belief": "Over the next two years, repeated climate disasters materially strain US property insurance markets.",
                "time_horizon": "over the next two years",
                "belief_direction": "increase",
                "desired_exposure": "Markets that benefit if climate-driven insurance stress intensifies in the US.",
                "key_drivers": ["more frequent severe disasters", "underpriced catastrophe risk", "insurer balance-sheet pressure"],
                "scope": "US property insurance, climate risk, housing, and disaster-sensitive markets",
                "confidence_level": "medium",
                "confidence_style": "strong_directional",
                "supporting_reasoning": "Repeated losses and repricing pressure could force insurers to raise premiums and retreat from exposed regions.",
                "current_context": "US insurers in disaster-prone states are already facing pricing and underwriting pressure in 2026.",
                "resolution_target": "Climate disasters cause a visible worsening in US property insurance conditions within two years.",
                "resolution_type": "other",
                "timeframe_start": "now",
                "timeframe_end": "2028-05-07",
                "mechanism": ["large losses accumulate", "premiums rise sharply", "carriers reduce exposure in vulnerable states"],
                "falsifiers": ["mild disaster seasons", "public backstops stabilize losses", "private markets absorb the shocks smoothly"],
                "timeframe_inferred": False,
                "mode_used": "thinking",
            },
        },
    ]


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


class TradingPipelineExampleRequest(BaseModel):
    label: str = ""
    message: str = ""
    history: list[dict[str, Any]] = Field(default_factory=list)
    follow_up_messages: list[str] = Field(default_factory=list)
    belief_summary: dict[str, Any] | None = None
    mode: str | None = None


class TradingPipelineBatchRequest(BaseModel):
    label: str = ""
    mode: str = "thinking"
    examples: list[TradingPipelineExampleRequest] = Field(default_factory=list)
    save_baskets: bool = False
    include_kalshi_log_tail: int = 0


class TradingPipelineTraceError(Exception):
    def __init__(self, message: str, trace: dict[str, Any] | None = None):
        super().__init__(message)
        self.trace = trace or {}


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


_ENABLE_FAST_CRITIC = os.environ.get("ENABLE_FAST_BASKET_CRITIC", "").lower() == "true"


def _market_from_row(row: dict[str, Any]):
    from forecaster.kalshi import KalshiMarket
    return KalshiMarket(**{
        "ticker": row["ticker"],
        "event_ticker": row["event_ticker"],
        "yes_sub_title": row.get("yes_sub_title", ""),
        "no_sub_title": row.get("no_sub_title", ""),
        "yes_bid": row.get("yes_bid", 0.0),
        "yes_ask": row.get("yes_ask", 0.0),
        "last_price": row.get("last_price", 0.0),
        "volume": row.get("volume", 0.0),
        "rules_primary": row.get("rules_primary", ""),
        "rules_secondary": row.get("rules_secondary", ""),
        "close_time": row.get("close_time", ""),
        "status": row.get("status", "open"),
    })


def _count_by_key(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = item.get(key)
        if not value:
            continue
        counts[str(value)] = counts.get(str(value), 0) + 1
    return counts


def _run_belief_chat_sequence(
    *,
    message: str,
    history: list[dict[str, Any]] | None = None,
    follow_up_messages: list[str] | None = None,
    mode: str = "thinking",
) -> dict[str, Any]:
    from agents.belief_agent import BeliefAgent

    agent = BeliefAgent()
    current_history = list(history or [])
    pending_messages = [message, *(follow_up_messages or [])]
    turns: list[dict[str, Any]] = []
    response: dict[str, Any] | None = None

    while pending_messages:
        current_message = pending_messages.pop(0)
        request_payload = {
            "history": current_history,
            "message": current_message,
            "mode": mode,
        }
        response = agent.step(current_history, current_message, mode=mode)
        turns.append({
            "request": request_payload,
            "response": response,
        })
        current_history = response.get("history", current_history)
        if response.get("status") == "finalized":
            break

    if response is None:
        raise ValueError("Belief chat sequence received no user messages")

    return {
        "status": response.get("status", "error"),
        "turns": turns,
        "history": current_history,
        "agent_message": response.get("agent_message"),
        "belief_summary": response.get("belief_summary"),
        "search_queries": response.get("search_queries", []),
        "remaining_follow_ups": pending_messages,
    }


def _run_trading_pipeline(
    *,
    belief_summary: dict[str, Any],
    mode: str,
    request_user_id: str | None = None,
    save_basket: bool = True,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    include_trace: bool = False,
) -> dict[str, Any]:
    from agents.basket_critic_agent import BasketCriticAgent
    from agents.curator_agent import BasketBuilderAgent
    from agents.exposure_agent import ExposureAgent
    from agents.screener_agent import MarketScreenerAgent
    from event_cache_db import get_event_lookup
    from market_cache_db import get_markets_for_events
    from retrieval.market_retrieval import retrieve_markets_for_exposures

    trace: dict[str, Any] = {
        "belief_summary": belief_summary,
        "mode": mode,
        "stream_messages": [],
        "stages": {},
    } if include_trace else {}

    def _emit(msg: dict[str, Any]) -> None:
        if include_trace:
            trace["stream_messages"].append(msg)
        if progress_callback:
            progress_callback(msg)

    _emit({"type": "progress", "label": "Mapping tradable exposure routes…"})
    exposure_result = ExposureAgent().run(belief_summary)
    analysis = _exposure_analysis_payload(exposure_result)
    if include_trace:
        exposure_ring_counts = _count_by_key(exposure_result.get("exposures", []), "route_ring")
        trace["stages"]["exposure"] = {
            "input": {"belief_summary": belief_summary},
            "output": exposure_result,
            "observability": {
                "routes_by_ring": exposure_ring_counts,
            },
        }
    # Preserve the legacy stream shape expected by the frontend, but back it
    # with exposure-route analysis instead of the old domain map.
    _emit({"type": "analyst_done", "analysis": analysis})

    _emit({"type": "progress", "label": "Retrieving candidate markets from the cache…"})
    retrieval_result = retrieve_markets_for_exposures(exposure_result.get("exposures", []), belief_summary)
    if include_trace:
        retrieval_by_ring: dict[str, int] = {}
        for group in retrieval_result.get("exposure_candidates", []):
            route_ring = group.get("exposure", {}).get("route_ring", "direct")
            retrieval_by_ring[route_ring] = retrieval_by_ring.get(route_ring, 0) + len(group.get("candidates", []))
        trace["stages"]["retrieval"] = {
            "input": {
                "exposures": exposure_result.get("exposures", []),
                "belief_summary": belief_summary,
            },
            "output": retrieval_result,
            "observability": {
                "candidates_by_ring": retrieval_by_ring,
                "market_source": retrieval_result.get("market_source"),
                "market_count": retrieval_result.get("market_count"),
            },
        }

    _emit({"type": "progress", "label": "Scoring tradable market exposures…"})
    screener_result = MarketScreenerAgent().run(
        belief_summary,
        exposure_result.get("exposures", []),
        retrieval_result.get("exposure_candidates", []),
    )
    selected_markets = screener_result.get("selected_markets", [])
    coverage_summary = screener_result.get("coverage_summary", {})
    if include_trace:
        trace["stages"]["screener"] = {
            "input": {
                "belief_summary": belief_summary,
                "exposures": exposure_result.get("exposures", []),
                "exposure_candidates": retrieval_result.get("exposure_candidates", []),
            },
            "output": screener_result,
            "observability": {
                "selected_by_fit_type": _count_by_key(selected_markets, "fit_type"),
                "coverage_summary": coverage_summary,
            },
        }

    if not selected_markets:
        if include_trace:
            trace["error"] = "No relevant markets found matching quality thresholds."
        raise TradingPipelineTraceError("No relevant markets found matching quality thresholds.", trace)

    event_tickers = list(dict.fromkeys(m["event_ticker"] for m in selected_markets))
    screener_msg = {
        "type": "screener_done",
        "tickers": [m["ticker"] for m in selected_markets],
        "count": len(selected_markets),
        "selected_markets": selected_markets,
        "coverage_summary": coverage_summary,
    }
    # Preserve legacy `screener_done` fields while attaching the richer
    # contract-level selection payload for debugging and future UI use.
    _emit(screener_msg)

    _emit({"type": "progress", "label": f"Loading cached markets for {len(event_tickers)} events…"})
    try:
        cached_rows = get_markets_for_events(event_tickers)
    except Exception:
        cached_rows = []

    selected_tickers = {m["ticker"] for m in selected_markets}
    market_load_source = "cache"
    if cached_rows:
        markets = [_market_from_row(row) for row in cached_rows if row["ticker"] in selected_tickers]
    else:
        market_load_source = "live_fallback"
        _emit({"type": "progress", "label": "Cached market DB is empty; fetching open markets live…"})
        kalshi_client = _get_client()
        markets = [m for m in _get_live_markets_for_events(kalshi_client, event_tickers) if m.ticker in selected_tickers]

    if include_trace:
        trace["stages"]["market_loading"] = {
            "input": {"event_tickers": event_tickers, "selected_tickers": sorted(selected_tickers)},
            "output": {
                "source": market_load_source,
                "market_count": len(markets),
                "markets": [_market_dict(m) for m in markets],
            },
        }

    if not markets:
        if include_trace:
            trace["error"] = "No open markets found for the shortlisted contracts."
        raise TradingPipelineTraceError("No open markets found for the shortlisted contracts.", trace)

    selected_by_ticker = {m["ticker"]: m for m in selected_markets}
    markets.sort(key=lambda m: (-selected_by_ticker.get(m.ticker, {}).get("overall_score", 0), -float(getattr(m, "volume", 0.0))))

    _emit({"type": "progress", "label": f"Building a $100 prediction market basket from {len(markets)} selected contracts…"})
    basket = BasketBuilderAgent().run(
        belief_summary,
        markets,
        exposures=exposure_result.get("exposures", []),
        selected_markets=selected_markets,
        mode=mode,
    )
    if include_trace:
        trace["stages"]["basket_builder"] = {
            "input": {
                "belief_summary": belief_summary,
                "exposures": exposure_result.get("exposures", []),
                "selected_markets": selected_markets,
                "markets": [_market_dict(m) for m in markets],
                "mode": mode,
            },
            "output": basket,
            "observability": {
                "holdings_by_fit_type": _count_by_key(basket.get("holdings", []), "fit_type"),
                "basket_quality": basket.get("basket_quality"),
            },
        }

    critique = None
    if mode != "instant" or _ENABLE_FAST_CRITIC:
        _emit({"type": "progress", "label": "Critiquing basket coherence…"})
        critique = BasketCriticAgent().run(
            belief_summary,
            exposure_result.get("exposures", []),
            selected_markets,
            basket,
        )
        _emit({"type": "critic_done", "critique": critique})
        if include_trace:
            trace["stages"]["critic"] = {
                "input": {
                    "belief_summary": belief_summary,
                    "exposures": exposure_result.get("exposures", []),
                    "selected_markets": selected_markets,
                    "draft_basket": basket,
                },
                "output": critique,
            }
        if critique.get("verdict") == "needs_repair":
            basket = _apply_critic_repairs(basket, selected_markets, critique)

    selected_market_rows = {m.ticker: m for m in markets}
    basket, validation_warnings = _validate_and_repair_basket(basket, selected_markets, selected_market_rows)
    if validation_warnings:
        notes = basket.get("construction_notes", "")
        basket["construction_notes"] = (notes + ("\n\n" if notes else "") + "Validation notes: " + "; ".join(validation_warnings)).strip()

    event_lookup = get_event_lookup([holding.get("event_ticker", "") for holding in basket.get("holdings", [])])
    for holding in basket.get("holdings", []):
        evt = event_lookup.get(holding.get("event_ticker", ""), {})
        holding["event_title"] = evt.get("title", "")
        holding["series_ticker"] = evt.get("series_ticker", "")
        holding["category"] = evt.get("category", "")

    basket_id: int | None = None
    if save_basket:
        try:
            basket_id = db.save_basket(
                title=basket.get("basket_title", belief_summary.get("core_belief", "Prediction Market ETF")),
                summary=basket.get("basket_summary", ""),
                core_belief=belief_summary.get("core_belief", ""),
                mode=mode or belief_summary.get("mode_used", "thinking"),
                time_horizon=belief_summary.get("time_horizon", ""),
                timeframe_start=belief_summary.get("timeframe_start", ""),
                timeframe_end=belief_summary.get("timeframe_end", belief_summary.get("time_horizon", "")),
                resolution_target=belief_summary.get("resolution_target", ""),
                mechanism=", ".join(belief_summary.get("mechanism", [])) if isinstance(belief_summary.get("mechanism"), list) else belief_summary.get("mechanism", ""),
                scope=belief_summary.get("scope", ""),
                key_drivers=belief_summary.get("key_drivers", []),
                belief_summary=belief_summary,
                analysis=analysis,
                basket=basket,
                total_notional=basket.get("total_notional", 100.0),
                screened_count=len(selected_markets),
                holdings=basket.get("holdings", []),
                user_id=request_user_id,
            )
        except Exception as exc:
            if include_trace:
                trace.setdefault("save_warning", str(exc))

    result = {
        "analysis": analysis,
        "exposure_result": exposure_result,
        "retrieval_result": retrieval_result,
        "screener_result": screener_result,
        "selected_markets": selected_markets,
        "coverage_summary": coverage_summary,
        "basket": basket,
        "basket_id": basket_id,
        "critique": critique,
        "validation_warnings": validation_warnings,
    }
    if include_trace:
        trace["stages"]["validation"] = {
            "input": {
                "basket": basket,
                "selected_markets": selected_markets,
            },
            "output": {
                "warnings": validation_warnings,
                "basket": basket,
            },
            "observability": {
                "holdings_by_fit_type": _count_by_key(basket.get("holdings", []), "fit_type"),
                "basket_quality": basket.get("basket_quality"),
            },
        }
        trace["result"] = {
            "basket_id": basket_id,
            "selected_market_count": len(selected_markets),
            "holding_count": len(basket.get("holdings", [])),
        }
        result["trace"] = trace
    return result


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
                def _progress(msg: dict[str, Any]) -> None:
                    asyncio.run_coroutine_threadsafe(queue.put(msg), loop)

                result = _run_trading_pipeline(
                    belief_summary=req.belief_summary,
                    mode=req.mode,
                    request_user_id=_get_user_id(request),
                    save_basket=True,
                    progress_callback=_progress,
                )
                asyncio.run_coroutine_threadsafe(
                    queue.put({"type": "basket_done", "basket": result["basket"], "basket_id": result.get("basket_id")}), loop
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


@app.get("/api/debug/trading-pipeline-runs")
async def list_trading_pipeline_runs(limit: int = 20):
    runs = _list_trading_pipeline_debug_runs(limit)
    return {
        "path": str(_TRADING_PIPELINE_DEBUG_DIR),
        "count": len(runs),
        "runs": runs,
    }


@app.get("/api/debug/trading-pipeline-runs/{run_id}")
async def get_trading_pipeline_run(run_id: str):
    _, payload = _load_trading_pipeline_debug_run(run_id)
    return payload


@app.get("/api/debug/trading-pipeline-runs/{run_id}/download")
async def download_trading_pipeline_run(run_id: str):
    path, _ = _load_trading_pipeline_debug_run(run_id)
    return FileResponse(
        path=path,
        media_type="application/json",
        filename=path.name,
    )


@app.post("/api/debug/trading-pipeline-runs")
async def run_trading_pipeline_batch(req: TradingPipelineBatchRequest):
    if not _TC_AVAILABLE:
        raise HTTPException(status_code=503, detail="Trading companion not available")

    loop = asyncio.get_event_loop()

    def _run_batch() -> dict[str, Any]:
        created_at = datetime.now(_PACIFIC_TZ).isoformat()
        run_id = datetime.now(_PACIFIC_TZ).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8]
        examples = req.examples or [TradingPipelineExampleRequest(**example) for example in _default_trading_pipeline_examples()]
        mode = req.mode or "thinking"

        run_payload: dict[str, Any] = {
            "run_id": run_id,
            "created_at": created_at,
            "label": req.label or "Trading pipeline batch run",
            "mode": mode,
            "save_baskets": req.save_baskets,
            "examples": [],
            "kalshi_log_file": str(_KALSHI_API_LOG_FILE),
        }

        completed_count = 0
        clarification_count = 0
        error_count = 0

        for idx, example in enumerate(examples, start=1):
            example_mode = example.mode or mode
            example_record: dict[str, Any] = {
                "index": idx,
                "label": example.label or f"Example {idx}",
                "mode": example_mode,
                "input": {
                    "message": example.message,
                    "history": example.history,
                    "follow_up_messages": example.follow_up_messages,
                    "belief_summary": example.belief_summary,
                },
            }
            try:
                if example.belief_summary:
                    belief_trace = {
                        "status": "finalized",
                        "source": "provided_belief_summary",
                        "belief_summary": example.belief_summary,
                        "turns": [],
                    }
                    belief_summary = example.belief_summary
                else:
                    belief_trace = _run_belief_chat_sequence(
                        message=example.message,
                        history=example.history,
                        follow_up_messages=example.follow_up_messages,
                        mode=example_mode,
                    )
                    belief_summary = belief_trace.get("belief_summary")

                example_record["belief_trace"] = belief_trace
                if not belief_summary or belief_trace.get("status") != "finalized":
                    clarification_count += 1
                    example_record["status"] = "needs_clarification"
                    example_record["error"] = "BeliefAgent did not finalize a tradable belief summary."
                    run_payload["examples"].append(example_record)
                    continue

                result = _run_trading_pipeline(
                    belief_summary=belief_summary,
                    mode=example_mode,
                    request_user_id=None,
                    save_basket=req.save_baskets,
                    progress_callback=None,
                    include_trace=True,
                )
                completed_count += 1
                example_record["status"] = "completed"
                example_record["pipeline_trace"] = result.get("trace", {})
                example_record["result"] = {
                    "analysis": result["analysis"],
                    "selected_market_count": len(result["selected_markets"]),
                    "selected_markets": result["selected_markets"],
                    "basket": result["basket"],
                    "basket_id": result.get("basket_id"),
                    "validation_warnings": result.get("validation_warnings", []),
                    "critique": result.get("critique"),
                }
            except TradingPipelineTraceError as exc:
                error_count += 1
                example_record["status"] = "error"
                example_record["error"] = str(exc)
                if exc.trace:
                    example_record["pipeline_trace"] = exc.trace
            except Exception as exc:
                error_count += 1
                example_record["status"] = "error"
                example_record["error"] = str(exc)
            run_payload["examples"].append(example_record)

        if req.include_kalshi_log_tail > 0:
            run_payload["kalshi_log_tail"] = _read_kalshi_log_rows(req.include_kalshi_log_tail)

        run_payload["summary"] = {
            "example_count": len(run_payload["examples"]),
            "completed_count": completed_count,
            "needs_clarification_count": clarification_count,
            "error_count": error_count,
        }

        path = _save_trading_pipeline_debug_run(run_id, run_payload)
        run_payload["download_url"] = f"/api/debug/trading-pipeline-runs/{run_id}/download"
        run_payload["detail_url"] = f"/api/debug/trading-pipeline-runs/{run_id}"
        run_payload["path"] = str(path)
        _save_trading_pipeline_debug_run(run_id, run_payload)
        return run_payload

    try:
        return await loop.run_in_executor(None, _run_batch)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


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
