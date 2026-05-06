"""Trading Companion — local CLI for building prediction market ETFs."""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / "forecaster" / ".env")

_FORECASTER_PATH = str(Path(__file__).parent.parent / "forecaster")
if _FORECASTER_PATH not in sys.path:
    sys.path.insert(0, _FORECASTER_PATH)

from kalshi import KalshiClient, KalshiMarket
from agents.belief_agent import BeliefAgent
from agents.analyst_agent import AnalystAgent
from agents.screener_agent import ScreenerAgent
from agents.curator_agent import BasketBuilderAgent

DIVIDER = "─" * 60


def _fetch_markets_for_events(client: KalshiClient, event_tickers: list[str]) -> list[KalshiMarket]:
    all_markets: dict[str, KalshiMarket] = {}
    for ticker in event_tickers:
        try:
            markets, _ = client.get_markets(limit=20, status="open", event_ticker=ticker)
            for market in markets:
                if market.ticker not in all_markets:
                    all_markets[market.ticker] = market
        except Exception as exc:
            print(f"  Warning: could not fetch markets for {ticker}: {exc}")
    return list(all_markets.values())


def _display_basket(basket: dict) -> None:
    print(f"\n{DIVIDER}")
    print(basket.get("basket_title", "PREDICTION MARKET ETF"))
    print(DIVIDER)
    print(basket.get("basket_summary", ""))
    print(f"\nTotal notional: ${basket.get('total_notional', 0):.0f}\n")

    holdings = basket.get("holdings", [])
    if not holdings:
        print("No holdings qualified for the basket.")
        return

    for idx, holding in enumerate(holdings, 1):
        print(f"{idx}. {holding['question']}")
        print(f"   Ticker   : {holding['ticker']}")
        print(f"   Position : {holding['side']} | ${holding['weight_dollars']:.0f} | {holding['role']}")
        print(f"   Market   : YES {holding['market_price']:.0%} | Closes {holding['close_date']}")
        print(f"   Why own  : {holding['rationale']}")
        print(f"   Risk     : {holding['main_risk']}\n")

    if basket.get("construction_notes"):
        print("Construction notes:")
        print(basket["construction_notes"])


def main() -> None:
    print(f"\n{DIVIDER}")
    print("  PREDICTION MARKET ETF BUILDER")
    print("  Turn a future thesis into a weighted Kalshi basket")
    print(f"{DIVIDER}\n")

    try:
        kalshi = KalshiClient.from_env()
    except Exception as exc:
        print(f"[ERROR] Could not connect to Kalshi: {exc}")
        sys.exit(1)

    mode = input("Mode (instant/thinking) [thinking]: ").strip().lower() or "thinking"
    if mode not in {"instant", "thinking"}:
        mode = "thinking"

    print("\n[ Agent 1 ] Belief Intake\n")
    belief_summary = BeliefAgent().run(mode=mode)

    print("\n[ Agent 2 ] Exposure Mapping")
    analysis = AnalystAgent().run(belief_summary)

    print("\n[ Agent 3 ] Market Screening")
    screener_result = ScreenerAgent().run(belief_summary, analysis)
    candidates = screener_result.get("candidates", [])
    event_tickers = [c["event_ticker"] for c in candidates]
    print(f"  Screened into {len(event_tickers)} relevant events")
    if not event_tickers:
        print("\nNo relevant events found. Try refreshing the cache with: python sync_events.py")
        sys.exit(0)

    print(f"\nFetching live market details for {len(event_tickers)} events ...")
    markets = _fetch_markets_for_events(kalshi, event_tickers)
    print(f"  Found {len(markets)} open markets.")
    if not markets:
        print("\nNo open markets found for the shortlisted events.")
        sys.exit(0)

    print("\n[ Agent 4 ] Basket Construction")
    basket = BasketBuilderAgent().run(belief_summary, markets, analysis, screener_candidates=candidates)
    _display_basket(basket)


if __name__ == "__main__":
    main()
