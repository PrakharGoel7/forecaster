from __future__ import annotations

import unittest
from datetime import datetime, timezone

from forecaster.price_history import basket_performance, candle_yes_price, market_history, period_for_basket


CREATED = "2026-10-16T00:00:00Z"
CREATED_TS = int(datetime.fromisoformat(CREATED.replace("Z", "+00:00")).timestamp())


class Client:
    def __init__(self, candles):
        self.candles = candles
        self.calls = []

    def get_candlesticks(self, tickers, start_ts, end_ts, period_interval):
        self.calls.append((tickers, start_ts, end_ts, period_interval))
        return {ticker: self.candles.get(ticker, []) for ticker in tickers}


def candle(ts, bid, ask):
    return {"end_period_ts": ts, "yes_bid": {"close_dollars": str(bid)},
            "yes_ask": {"close_dollars": str(ask)}, "price": {"close_dollars": str((bid + ask) / 2)}}


class PriceHistoryTests(unittest.TestCase):
    def test_quote_midpoint_falls_back_to_last_trade_without_a_book(self):
        self.assertEqual(candle_yes_price(candle(CREATED_TS, .1, .3)), .2)
        self.assertEqual(candle_yes_price({"yes_bid": {"close_dollars": "0"},
                                           "yes_ask": {"close_dollars": "0"},
                                           "price": {"close_dollars": "0.42"}}), .42)

    def test_manual_no_uses_no_entry_price_and_generated_no_uses_yes_entry(self):
        for mode, entry in (("manual", .8), ("instant", .2)):
            with self.subTest(mode=mode):
                ticker = f"NO-{mode}"
                client = Client({ticker: [candle(CREATED_TS + 60, .09, .11)]})
                basket = {"created_at": CREATED, "mode": mode, "holdings": [
                    {"ticker": ticker, "side": "NO", "weight_dollars": 100,
                     "market_price_at_create": entry}]}
                result = basket_performance(client, basket, CREATED_TS + 120)
                self.assertEqual(result["values"], [100.0, 112.5])
                self.assertEqual(result["current_return"], 12.5)
                self.assertEqual(client.calls[0][0], [ticker])

    def test_missing_candle_keeps_entry_quote_and_reports_coverage(self):
        client = Client({"UPDATED": [candle(CREATED_TS + 60, .59, .61)]})
        basket = {"created_at": CREATED, "mode": "manual", "holdings": [
            {"ticker": "UPDATED", "side": "YES", "weight_dollars": 50, "market_price_at_create": .5},
            {"ticker": "QUIET", "side": "YES", "weight_dollars": 50, "market_price_at_create": .5}]}
        result = basket_performance(client, basket, CREATED_TS + 120)
        self.assertEqual(result["values"], [100.0, 110.0])
        self.assertEqual((result["updated_holdings"], result["total_holdings"]), (1, 2))

    def test_market_history_only_requests_clicked_ticker(self):
        client = Client({"CLICKED": [candle(CREATED_TS + 3600, .49, .51)]})
        result = market_history(client, "CLICKED", 7, CREATED_TS + 7200)
        self.assertEqual(client.calls[0][0], ["CLICKED"])
        self.assertEqual(result["points"][0]["yes_price"], .5)

    def test_batch_period_stays_under_candle_limit(self):
        self.assertEqual(period_for_basket(3600, 10), 1)
        self.assertEqual(period_for_basket(14 * 86400, 10), 60)
        self.assertEqual(period_for_basket(90 * 86400, 10), 1440)


if __name__ == "__main__":
    unittest.main()
