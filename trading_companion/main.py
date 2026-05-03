"""Trading Companion — main entry point.

Four-agent pipeline:
  1. BeliefAgent    — conversational interview to understand the user's belief
  2. AnalystAgent   — maps belief ramifications across 16 domains
  3. ScreenerAgent  — reads local events cache, shortlists relevant event_tickers
  4. CuratorAgent   — fetches real-time markets for shortlisted events, picks best 5-8

Run `python sync_events.py` once per day to keep the cache fresh.
"""
from __future__ import annotations
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / "forecaster" / ".env")

import json

# Make the forecaster package importable
_FORECASTER_PATH = str(Path(__file__).parent.parent / "forecaster")
if _FORECASTER_PATH not in sys.path:
    sys.path.insert(0, _FORECASTER_PATH)

from kalshi import KalshiClient, KalshiMarket
from agents.belief_agent import BeliefAgent
from agents.analyst_agent import AnalystAgent
from agents.screener_agent import ScreenerAgent, CACHE_FILE
from agents.curator_agent import CuratorAgent

DIVIDER = "─" * 60


def _fetch_markets_for_events(client: KalshiClient, event_tickers: list[str]) -> list[KalshiMarket]:
    """Fetch real-time open markets for a list of event_tickers."""
    all_markets: dict[str, KalshiMarket] = {}
    for ticker in event_tickers:
        try:
            markets, _ = client.get_markets(limit=20, status="open", event_ticker=ticker)
            for m in markets:
                if m.ticker not in all_markets:
                    all_markets[m.ticker] = m
        except Exception as e:
            print(f"  Warning: could not fetch markets for {ticker}: {e}")
    return list(all_markets.values())


def _load_event_lookup() -> dict[str, dict]:
    """Return a dict of event_ticker -> {series_ticker, title, sub_title} from cache."""
    if not CACHE_FILE.exists():
        return {}
    data = json.loads(CACHE_FILE.read_text())
    return {e["event_ticker"]: e for e in data["events"]}


def _display_recommendations(recommendations: list[dict], event_lookup: dict) -> None:
    print(f"\n{DIVIDER}")
    print("RECOMMENDED PREDICTION MARKETS")
    print(DIVIDER)

    if not recommendations:
        print("No markets matched — try running sync_events.py to refresh the cache.")
        return

    for i, r in enumerate(recommendations, 1):
        event = event_lookup.get(r.get("event_ticker", ""), {})
        series_ticker = event.get("series_ticker", "—")
        event_title = event.get("title", "")
        event_sub = event.get("sub_title", "")

        print(f"\n{i}. {r['question']}")
        print(f"   Series     : {series_ticker}")
        print(f"   Event      : {r.get('event_ticker', '—')}" + (f"  ({event_title}" + (f" — {event_sub}" if event_sub else "") + ")" if event_title else ""))
        print(f"   Market     : {r['ticker']}")
        print(f"   Current YES: {r['price']:.0%}  |  Closes: {r['close_date']}")
        print(f"   Your trade : Bet {r['direction']}")
        print(f"   Why bet    : {r['rationale']}")
        print(f"   Relevance  : {r['relevance']}")

    print(f"\n{DIVIDER}\n")


def _run_forecaster_on_markets(recommendations: list[dict]) -> None:
    """Let user pick a recommended market and run it through the forecaster."""
    from types import SimpleNamespace

    try:
        from forecaster.config import ForecasterConfig
        from forecaster.forecaster_system import ForecasterSystem
        from forecaster.cli import _print_memo, _comparison_panel
        from rich.console import Console
    except ImportError as e:
        print(f"\n[ERROR] Could not load forecaster: {e}")
        return

    console = Console()

    while True:
        print(f"\nEnter a market number (1-{len(recommendations)}) to forecast, or press Enter to quit: ", end="", flush=True)
        choice = input().strip().lower()
        if not choice or choice == "q":
            break
        if not choice.isdigit():
            print("Please enter a number or press Enter to quit.")
            continue
        idx = int(choice) - 1
        if not (0 <= idx < len(recommendations)):
            print(f"Please enter a number between 1 and {len(recommendations)}.")
            continue

        r = recommendations[idx]
        console.print(f"\n[bold]Forecasting:[/bold] {r['question']}")
        console.print(f"[dim]{r['ticker']} | Current YES: {r['price']:.1%} | Closes: {r['close_date']}[/dim]\n")

        config = ForecasterConfig()
        system = ForecasterSystem(config)
        console.print("[bold]Pipeline:[/bold]")

        def on_step(name: str, status: str) -> None:
            if status == "running":
                console.print(f"  [dim]→[/dim] {name}...", end="")
            else:
                console.print(" [green]✓[/green]")

        try:
            memo = system.forecast(
                question=r["question"],
                context=r.get("rules_summary") or None,
                on_step=on_step,
            )
        except Exception as e:
            console.print(f"\n[red]Forecaster error:[/red] {e}")
            continue

        _print_memo(memo)

        fake_market = SimpleNamespace(
            mid_price=r["price"],
            ticker=r["ticker"],
            close_date=r["close_date"],
        )
        console.print(_comparison_panel(memo, fake_market))


def main() -> None:
    print(f"\n{DIVIDER}")
    print("  TRADING COMPANION")
    print("  Turn your beliefs about the future into prediction market bets")
    print(f"{DIVIDER}\n")

    # ── Connect to Kalshi ──────────────────────────────────────────────────
    try:
        kalshi = KalshiClient.from_env()
    except Exception as e:
        print(f"[ERROR] Could not connect to Kalshi: {e}")
        sys.exit(1)

    # ── Agent 1: Understand the belief ────────────────────────────────────
    print("[ Agent 1 ] Belief Elicitor\n")
    belief_agent = BeliefAgent()
    belief_summary = belief_agent.run()

    print(f"\n{DIVIDER}")
    print(f"Belief captured: {belief_summary['core_belief']}")
    print(DIVIDER)

    # ── Agent 2: Deep domain analysis ────────────────────────────────────
    print("\n[ Agent 2 ] Belief Analyst — mapping ramifications across domains ...")
    analyst = AnalystAgent()
    analysis = analyst.run(belief_summary)
    high_med = [d for d in analysis["affected_domains"] if d["relevance"] in ("high", "medium")]
    for d in high_med:
        print(f"  [{d['relevance'].upper():6}] {d['domain']}: {d['mechanism']}")
    if analysis.get("most_surprising_connection"):
        print(f"  [INSIGHT] {analysis['most_surprising_connection']}")

    # ── Agent 3: Screen cached events for relevance ───────────────────────
    print("\n[ Agent 3 ] Market Screener — reading event cache ...")
    screener = ScreenerAgent()
    event_tickers = screener.run(belief_summary, analysis)
    print(f"  Shortlisted {len(event_tickers)} events: {event_tickers}")

    if not event_tickers:
        print("\nNo relevant events found. Try refreshing the cache with: python sync_events.py")
        sys.exit(0)

    # ── Fetch real-time markets for shortlisted events ────────────────────
    print(f"\nFetching live market details for {len(event_tickers)} events ...")
    markets = _fetch_markets_for_events(kalshi, event_tickers)
    print(f"  Found {len(markets)} open markets.")

    if not markets:
        print("\nNo open markets found for the shortlisted events.")
        sys.exit(0)

    # ── Agent 4: Curate ───────────────────────────────────────────────────
    print("\n[ Agent 4 ] Market Curator — picking the best bets ...")
    curator = CuratorAgent()
    recommendations = curator.run(belief_summary, markets, analysis)

    # ── Display results ───────────────────────────────────────────────────
    event_lookup = _load_event_lookup()
    _display_recommendations(recommendations, event_lookup)

    # ── Optional: run forecaster on selected markets ──────────────────────
    _run_forecaster_on_markets(recommendations)


if __name__ == "__main__":
    main()
