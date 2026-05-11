#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from forecaster.config import ForecasterConfig
from forecaster.forecaster_system import ForecasterSystem
from forecaster.kalshi import KalshiClient, KalshiMarket

try:
    from dotenv import load_dotenv
    load_dotenv(Path(".env"))
except ImportError:
    pass


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the forecaster pipeline locally for one or more Kalshi tickers and record timings."
    )
    parser.add_argument("tickers", nargs="*", help="One or more Kalshi market tickers")
    parser.add_argument("--tickers-file", type=Path, help="Text file with one ticker per line")
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path(f"runtime_logs/forecast_timing_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"),
        help="Where to write the full timing report JSON",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="Optional CSV summary output path",
    )
    parser.add_argument("--model", default="openai/gpt-4o", help="Model to use")
    parser.add_argument("--num-ov-agents", type=int, default=3)
    parser.add_argument("--max-ov-iterations", type=int, default=3)
    parser.add_argument("--num-iv-agents", type=int, default=3)
    parser.add_argument("--max-iv-iterations", type=int, default=4)
    parser.add_argument("--num-ensemble-runs", type=int, default=1)
    return parser.parse_args()


def _load_tickers(args: argparse.Namespace) -> list[str]:
    tickers = list(args.tickers)
    if args.tickers_file:
        tickers.extend(
            line.strip()
            for line in args.tickers_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
    deduped: list[str] = []
    seen = set()
    for ticker in tickers:
        if ticker not in seen:
            deduped.append(ticker)
            seen.add(ticker)
    if not deduped:
        raise SystemExit("Provide at least one ticker or --tickers-file")
    return deduped


def _series_ticker_from_event(event_ticker: str) -> str | None:
    parts = event_ticker.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0]
    return event_ticker or None


def _make_kalshi_client() -> KalshiClient:
    key_id = os.environ.get("KALSHI_API_KEY", "")
    pem = os.environ.get("KALSHI_PRIVATE_KEY_PEM", "")
    pem_b64 = os.environ.get("KALSHI_PRIVATE_KEY_B64", "")
    pem_file = os.environ.get("KALSHI_PRIVATE_KEY_FILE", "")

    if key_id and pem_b64:
        return KalshiClient(key_id=key_id, private_key_pem=pem_b64.strip())
    if key_id and pem:
        return KalshiClient(key_id=key_id, private_key_pem=pem.replace("\\n", "\n").strip().encode())
    if key_id and pem_file and Path(pem_file).exists():
        return KalshiClient.from_files(key_id, pem_file)

    raise ValueError(
        "Kalshi credentials not configured. Set KALSHI_API_KEY and one of "
        "KALSHI_PRIVATE_KEY_B64, KALSHI_PRIVATE_KEY_PEM, or KALSHI_PRIVATE_KEY_FILE."
    )


def _related_markets(markets: list[KalshiMarket]) -> list[dict[str, Any]]:
    return [
        {
            "ticker": m.ticker,
            "label": m.yes_sub_title or m.ticker,
            "question": m.question,
            "market_price": m.mid_price,
        }
        for m in markets
    ]


def _stage_bucket(name: str) -> str:
    if name == "Question Parser":
        return "question_parser"
    if name.startswith("Run ") and "· OV Agent " in name:
        return "outside_view_agents"
    if name.startswith("Run ") and "· OV Reconciler" in name:
        return "outside_view_reconciler"
    if name == "OV Phase":
        return "outside_view_phase"
    if name.startswith("Run ") and "· Agent " in name:
        return "inside_view_agents"
    if name == "IV Phase":
        return "inside_view_phase"
    if name.startswith("Run ") and "· Supervisor" in name:
        return "supervisor"
    return "other"


def _summarize_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    active: dict[str, float] = {}
    by_name: dict[str, float] = {}
    by_bucket: dict[str, float] = {}

    for event in events:
        name = event["name"]
        status = event["status"]
        t = event["elapsed_ms"]
        if status == "running":
            active[name] = t
        elif status == "done":
            start = active.pop(name, None)
            if start is None:
                continue
            duration = round(t - start, 2)
            by_name[name] = by_name.get(name, 0.0) + duration
            bucket = _stage_bucket(name)
            by_bucket[bucket] = round(by_bucket.get(bucket, 0.0) + duration, 2)

    return {
        "by_name_ms": {k: round(v, 2) for k, v in sorted(by_name.items())},
        "by_bucket_ms": by_bucket,
    }


def _run_one(
    ticker: str,
    client: KalshiClient,
    system: ForecasterSystem,
) -> dict[str, Any]:
    market = client.get_market(ticker)
    siblings, _ = client.get_markets(limit=50, status="open", event_ticker=market.event_ticker)
    events: list[dict[str, Any]] = []
    started_perf = perf_counter()
    started_at = datetime.now(timezone.utc)

    def on_step(name: str, status: str, data=None) -> None:
        elapsed_ms = round((perf_counter() - started_perf) * 1000, 2)
        events.append({
            "name": name,
            "status": status,
            "elapsed_ms": elapsed_ms,
            "logged_at": datetime.now(timezone.utc).isoformat(),
        })
        print(f"[{ticker}] {name} -> {status} @ {elapsed_ms:.0f}ms")

    try:
        memo = system.forecast(
            question=market.question,
            context=market.resolution_context or None,
            related_markets=_related_markets(siblings),
            on_step=on_step,
            series_ticker=_series_ticker_from_event(market.event_ticker),
            event_title=market.yes_sub_title or market.question,
            ev_sub="",
            ev_category="",
        )
        total_ms = round((perf_counter() - started_perf) * 1000, 2)
        summary = _summarize_events(events)
        return {
            "ticker": ticker,
            "started_at": started_at.isoformat(),
            "success": True,
            "total_duration_ms": total_ms,
            "market": {
                "ticker": market.ticker,
                "event_ticker": market.event_ticker,
                "question": market.question,
                "mid_price": market.mid_price,
                "close_time": market.close_time,
            },
            "memo_summary": {
                "final_probability": memo.final_probability,
                "raw_probability": memo.raw_probability,
                "num_agents": memo.num_agents,
                "num_ensemble_runs": memo.num_ensemble_runs,
            },
            "timings": summary,
            "events": events,
        }
    except Exception as exc:
        total_ms = round((perf_counter() - started_perf) * 1000, 2)
        summary = _summarize_events(events)
        return {
            "ticker": ticker,
            "started_at": started_at.isoformat(),
            "success": False,
            "total_duration_ms": total_ms,
            "market": {
                "ticker": market.ticker,
                "event_ticker": market.event_ticker,
                "question": market.question,
                "mid_price": market.mid_price,
                "close_time": market.close_time,
            },
            "error_type": type(exc).__name__,
            "error": str(exc),
            "timings": summary,
            "events": events,
        }


def _write_csv(path: Path, results: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "ticker",
        "success",
        "total_duration_ms",
        "question_parser_ms",
        "outside_view_agents_ms",
        "outside_view_reconciler_ms",
        "inside_view_agents_ms",
        "supervisor_ms",
        "error_type",
        "error",
        "final_probability",
        "raw_probability",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            buckets = result.get("timings", {}).get("by_bucket_ms", {})
            memo_summary = result.get("memo_summary", {})
            writer.writerow({
                "ticker": result["ticker"],
                "success": result["success"],
                "total_duration_ms": result["total_duration_ms"],
                "question_parser_ms": buckets.get("question_parser"),
                "outside_view_agents_ms": buckets.get("outside_view_agents"),
                "outside_view_reconciler_ms": buckets.get("outside_view_reconciler"),
                "inside_view_agents_ms": buckets.get("inside_view_agents"),
                "supervisor_ms": buckets.get("supervisor"),
                "error_type": result.get("error_type", ""),
                "error": result.get("error", ""),
                "final_probability": memo_summary.get("final_probability", ""),
                "raw_probability": memo_summary.get("raw_probability", ""),
            })


def main() -> None:
    args = _parse_args()
    tickers = _load_tickers(args)

    config = ForecasterConfig(
        model=args.model,
        num_ov_agents=args.num_ov_agents,
        max_ov_iterations=args.max_ov_iterations,
        num_iv_agents=args.num_iv_agents,
        max_iv_iterations=args.max_iv_iterations,
        num_ensemble_runs=args.num_ensemble_runs,
    )
    client = _make_kalshi_client()
    system = ForecasterSystem(config)

    results = [_run_one(ticker, client, system) for ticker in tickers]

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "model": config.model,
            "num_ov_agents": config.num_ov_agents,
            "max_ov_iterations": config.max_ov_iterations,
            "num_iv_agents": config.num_iv_agents,
            "max_iv_iterations": config.max_iv_iterations,
            "num_ensemble_runs": config.num_ensemble_runs,
        },
        "results": results,
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nWrote JSON report to {args.output_json}")

    if args.output_csv:
        _write_csv(args.output_csv, results)
        print(f"Wrote CSV summary to {args.output_csv}")

    failures = [r for r in results if not r["success"]]
    if failures:
        print(f"\n{len(failures)} forecast(s) failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
