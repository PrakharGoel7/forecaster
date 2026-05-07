from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from trading_companion.pipeline_utils import exposure_analysis_payload, normalize_weights, validate_and_repair_basket
from trading_companion.retrieval.market_retrieval import retrieve_markets_for_exposures


class RetrievalSmokeTests(unittest.TestCase):
    @patch("trading_companion.retrieval.market_retrieval.get_all_markets")
    @patch("trading_companion.retrieval.market_retrieval.get_event_lookup")
    def test_retrieval_groups_candidates(self, mock_event_lookup, mock_all_markets):
        mock_event_lookup.return_value = {
            "EV1": {"title": "Will BTC hit 250K?", "series_ticker": "CRYPTO", "category": "Crypto"},
        }
        mock_all_markets.return_value = [
            {
                "ticker": "BTC-250K",
                "event_ticker": "EV1",
                "question": "Will Bitcoin hit $250K by Dec 2026?",
                "yes_sub_title": "Yes",
                "no_sub_title": "No",
                "mid_price": 0.21,
                "volume": 1200,
                "status": "open",
                "close_date": "2026-12-31",
                "rules_primary": "",
                "rules_secondary": "",
            }
        ]
        result = retrieve_markets_for_exposures(
            [{
                "exposure_name": "Bitcoin hits 250K",
                "search_terms": ["bitcoin", "250k"],
                "negative_search_terms": ["ethereum"],
                "resolution_features": ["250k"],
                "tier": "direct_thesis",
            }],
            {"timeframe_end": "2026-12-31"},
        )
        self.assertEqual(len(result["exposure_candidates"]), 1)
        self.assertEqual(result["exposure_candidates"][0]["candidates"][0]["ticker"], "BTC-250K")


class ValidationSmokeTests(unittest.TestCase):
    def test_weight_normalization_hits_100(self):
        normalized = normalize_weights([
            {"ticker": "A", "weight_dollars": 30},
            {"ticker": "B", "weight_dollars": 20},
        ])
        self.assertAlmostEqual(sum(h["weight_dollars"] for h in normalized), 100.0, places=2)

    def test_validation_dedupes_duplicate_events(self):
        class Market:
            def __init__(self, ticker, event_ticker):
                self.ticker = ticker
                self.event_ticker = event_ticker
                self.question = ticker
                self.mid_price = 0.5
                self.close_date = "2026-12-31"
                self.rules_summary = ""

        basket, warnings = validate_and_repair_basket(
            {
                "holdings": [
                    {"ticker": "A", "event_ticker": "EV1", "weight_dollars": 60, "side": "YES", "role": "direct"},
                    {"ticker": "B", "event_ticker": "EV1", "weight_dollars": 40, "side": "YES", "role": "indirect"},
                ]
            },
            [
                {"ticker": "A", "event_ticker": "EV1", "question": "A", "recommended_side": "YES", "tier": "direct_thesis"},
                {"ticker": "B", "event_ticker": "EV1", "question": "B", "recommended_side": "YES", "tier": "first_order_consequence"},
            ],
            {"A": Market("A", "EV1"), "B": Market("B", "EV1")},
        )
        self.assertEqual(len(basket["holdings"]), 1)
        self.assertTrue(any("duplicate event exposure" in warning for warning in warnings))


class SchemaSmokeTests(unittest.TestCase):
    def test_belief_schema_includes_new_required_fields(self):
        belief_agent = Path("trading_companion/agents/belief_agent.py").read_text(encoding="utf-8")
        self.assertIn('"desired_exposure"', belief_agent)
        self.assertIn('"belief_direction"', belief_agent)
        self.assertIn('"timeframe_inferred"', belief_agent)

    def test_exposure_payload_keeps_frontend_compatibility(self):
        payload = exposure_analysis_payload({
            "exposures": [{
                "exposure_name": "Oil spikes",
                "causal_path": "Conflict tightens supply",
                "resolution_features": ["oil above $90"],
                "causal_distance": "first_order",
                "expressiveness_score": 4,
                "causal_purity_score": 4,
                "timeframe_fit": "strong",
            }],
            "rejected_routes": [{"route": "broad equities", "reason": "too loose"}],
        })
        self.assertIn("affected_domains", payload)
        self.assertIn("exposures", payload)


if __name__ == "__main__":
    unittest.main()
