import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import market_data_service as mds
import positions_service as svc
from options_algorithm_fixtures import FrozenDateTime, build_options_algorithm_fixture_bundle, build_tracked_position_scan_pick


class PositionsReviewEngineTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.market_db_path = os.path.join(self._tmp.name, "market_data.db")
        mds._MEMORY_CACHE.clear()
        mds._SCHEMA_READY.clear()
        self.bundle = build_options_algorithm_fixture_bundle()
        self.scan_pick = build_tracked_position_scan_pick(self.bundle)

    def _build_position(self, *, fill_price: float = 4.5, filled_at: str = "2026-03-30T10:00:00", expiry: str | None = None):
        scan_pick = dict(self.scan_pick)
        if expiry is not None:
            scan_pick["expiry"] = expiry
        payload = svc.build_position_payload(
            scan_pick=scan_pick,
            fill_price=fill_price,
            contracts=1,
            filled_at=filled_at,
            notes="test position",
        )
        payload["id"] = 1
        return payload

    def test_review_uses_actual_fill_price_for_stop_target_math(self):
        position = self._build_position(fill_price=2.0)
        position["source_pick_snapshot"]["premium"] = 1.0

        with patch.object(svc, "datetime", FrozenDateTime), \
             patch.object(svc, "_fetch_option_quote", return_value={
                 "expired": False,
                 "current_option_price": 2.2,
                 "pricing_source": "mid",
                 "price_trigger_ok": True,
                 "warnings": [],
                 "underlying_price": 125.0,
             }), \
             patch.object(svc, "_get_spy_ret5", return_value=0.0), \
             patch.object(svc, "_check_early_exit", return_value=(False, "")):
            review = svc.review_position(position)

        self.assertEqual(review["recommendation"], "HOLD")
        self.assertEqual(review["current_pnl_pct"], 10.0)
        self.assertEqual(review["metrics_snapshot"]["target_option_price"], 4.0)

    def test_review_uses_exact_contract_quote_when_available(self):
        position = self._build_position(fill_price=3.2)

        with patch.object(svc, "datetime", FrozenDateTime), \
             patch.object(svc.yf, "Ticker", side_effect=self.bundle.make_ticker), \
             patch.object(svc, "_get_spy_ret5", return_value=0.0), \
             patch.object(svc, "_check_early_exit", return_value=(False, "")):
            review = svc.review_position(position)

        self.assertEqual(review["pricing_source"], "mid")
        self.assertIsNotNone(review["current_option_price"])
        self.assertEqual(review["metrics_snapshot"]["contract_symbol"], position["contract_symbol"])
        self.assertFalse(any("unpriced" in warning.lower() for warning in review["warnings"]))

    def test_review_returns_unpriced_warning_when_exact_contract_is_missing(self):
        position = self._build_position(fill_price=3.2)
        position["contract_symbol"] = "AAA260407C99999999"
        position["source_pick_snapshot"]["contract_symbol"] = position["contract_symbol"]

        with patch.object(svc, "datetime", FrozenDateTime), \
             patch.object(svc.yf, "Ticker", side_effect=self.bundle.make_ticker), \
             patch.object(svc, "_check_indicator_exit_without_price", return_value=(False, "")):
            review = svc.review_position(position)

        self.assertEqual(review["pricing_source"], "unavailable")
        self.assertIsNone(review["current_option_price"])
        self.assertTrue(any("exact stored contract" in warning.lower() for warning in review["warnings"]))

    def test_review_maps_indicator_exit_to_sell(self):
        position = self._build_position(fill_price=2.0)

        with patch.object(svc, "datetime", FrozenDateTime), \
             patch.object(svc, "_fetch_option_quote", return_value={
                 "expired": False,
                 "current_option_price": 2.4,
                 "pricing_source": "mid",
                 "price_trigger_ok": True,
                 "warnings": [],
                 "underlying_price": 126.0,
             }), \
             patch.object(svc, "_get_spy_ret5", return_value=0.8), \
             patch.object(svc, "_check_early_exit", return_value=(True, "tech_score collapsed 40%")):
            review = svc.review_position(position)

        self.assertEqual(review["recommendation"], "SELL")
        self.assertIn("Indicator exit triggered", review["reason"])

    def test_review_maps_time_exit_to_sell(self):
        position = self._build_position(fill_price=4.5, filled_at="2026-03-25T10:00:00")
        position["time_exit_day"] = 3

        with patch.object(svc, "datetime", FrozenDateTime), \
             patch.object(svc, "_fetch_option_quote", return_value={
                 "expired": False,
                 "current_option_price": None,
                 "pricing_source": "unavailable",
                 "price_trigger_ok": False,
                 "warnings": ["No live option quote available."],
                 "underlying_price": 123.0,
             }):
            review = svc.review_position(position)

        self.assertEqual(review["recommendation"], "SELL")
        self.assertIn("Time exit reached", review["reason"])

    def test_review_holds_unpriced_non_expired_contracts_with_warning(self):
        position = self._build_position(fill_price=4.5)

        with patch.object(svc, "datetime", FrozenDateTime), \
             patch.object(svc, "_fetch_option_quote", return_value={
                 "expired": False,
                 "current_option_price": None,
                 "pricing_source": "unavailable",
                 "price_trigger_ok": False,
                 "warnings": ["No live option quote available."],
                 "underlying_price": 123.0,
             }), \
             patch.object(svc, "_check_indicator_exit_without_price", return_value=(False, "")):
            review = svc.review_position(position)

        self.assertEqual(review["recommendation"], "HOLD")
        self.assertTrue(review["warnings"])

    def test_review_suppresses_stop_and_target_triggers_when_only_last_price_is_available(self):
        position = self._build_position(fill_price=4.5)

        with patch.object(svc, "datetime", FrozenDateTime), \
             patch.object(svc, "_fetch_option_quote", return_value={
                 "expired": False,
                 "current_option_price": 0.5,
                 "pricing_source": "last_price",
                 "price_trigger_ok": False,
                 "warnings": ["Using last trade only for display."],
                 "underlying_price": 123.0,
             }), \
             patch.object(svc, "_check_indicator_exit_without_price", return_value=(False, "")):
            review = svc.review_position(position)

        self.assertEqual(review["recommendation"], "HOLD")
        self.assertEqual(review["pricing_source"], "last_price")

    def test_review_marks_expired_contracts_for_sell(self):
        position = self._build_position(fill_price=4.5, expiry="2026-03-28")

        with patch.object(svc, "datetime", FrozenDateTime), \
             patch.object(svc, "_fetch_option_quote", return_value={
                 "expired": True,
                 "current_option_price": None,
                 "pricing_source": "expired",
                 "price_trigger_ok": False,
                 "warnings": [],
                 "underlying_price": 121.0,
             }):
            review = svc.review_position(position)

        self.assertEqual(review["recommendation"], "SELL")
        self.assertIn("expiry has passed", review["reason"].lower())

    def test_review_open_positions_reuses_market_data_reads_for_same_ticker_and_expiry(self):
        class _RecordingTicker:
            def __init__(self, inner):
                self.inner = inner
                self.history_calls = []
                self.options_calls = 0
                self.option_chain_calls = []

            @property
            def options(self):
                self.options_calls += 1
                return self.inner.options

            def history(self, *args, **kwargs):
                self.history_calls.append((args, kwargs))
                return self.inner.history(*args, **kwargs)

            def option_chain(self, expiry):
                self.option_chain_calls.append(expiry)
                return self.inner.option_chain(expiry)

        position_a = self._build_position(fill_price=2.0)
        position_b = self._build_position(fill_price=2.0)
        position_b["id"] = 2
        repo_positions = [position_a, position_b]

        class _Repo:
            def list_positions(self, status="open"):
                return list(repo_positions)

            def save_review(self, position_id, review):
                return review

        tickers = {
            symbol: _RecordingTicker(inner)
            for symbol, inner in self.bundle.tickers.items()
        }

        with patch.dict(os.environ, {"MARKET_DATA_DB_PATH": self.market_db_path}, clear=False), \
             patch.object(svc, "datetime", FrozenDateTime), \
             patch.object(mds, "datetime", FrozenDateTime), \
             patch.object(svc.yf, "Ticker", side_effect=lambda symbol: tickers[symbol]), \
             patch.object(svc, "_check_early_exit", return_value=(False, "")), \
             patch.object(svc, "_check_indicator_exit_without_price", return_value=(False, "")):
            reviews = svc.review_open_positions(_Repo())

        self.assertEqual(len(reviews), 2)
        self.assertEqual(tickers[position_a["ticker"]].options_calls, 1)
        self.assertEqual(tickers[position_a["ticker"]].option_chain_calls.count(str(position_a["expiry"])[:10]), 1)
        self.assertEqual(len(tickers[position_a["ticker"]].history_calls), 1)
        self.assertEqual(len(tickers["SPY"].history_calls), 1)


    def test_review_includes_pricing_state_priced_exact(self):
        position = self._build_position(fill_price=2.0)

        with patch.object(svc, "datetime", FrozenDateTime), \
             patch.object(svc, "_fetch_option_quote", return_value={
                 "expired": False,
                 "current_option_price": 2.2,
                 "pricing_source": "mid",
                 "pricing_state": "priced_exact",
                 "current_execution_price": 2.2,
                 "current_execution_basis": "mid",
                 "price_trigger_ok": True,
                 "warnings": [],
                 "underlying_price": 125.0,
             }), \
             patch.object(svc, "_get_spy_ret5", return_value=0.0), \
             patch.object(svc, "_check_early_exit", return_value=(False, "")):
            review = svc.review_position(position)

        self.assertEqual(review["pricing_state"], "priced_exact")
        self.assertEqual(review["metrics_snapshot"]["pricing_state"], "priced_exact")

    def test_review_includes_pricing_state_unpriced(self):
        position = self._build_position(fill_price=3.2)
        position["contract_symbol"] = "AAA260407C99999999"
        position["source_pick_snapshot"]["contract_symbol"] = position["contract_symbol"]

        with patch.object(svc, "datetime", FrozenDateTime), \
             patch.object(svc.yf, "Ticker", side_effect=self.bundle.make_ticker), \
             patch.object(svc, "_check_indicator_exit_without_price", return_value=(False, "")):
            review = svc.review_position(position)

        self.assertEqual(review["pricing_state"], "unpriced_exact_contract_not_in_chain")
        self.assertEqual(review["metrics_snapshot"]["pricing_state"], "unpriced_exact_contract_not_in_chain")

    def test_review_includes_pricing_state_display_only_last(self):
        position = self._build_position(fill_price=2.0)

        with patch.object(svc, "datetime", FrozenDateTime), \
             patch.object(svc, "_fetch_option_quote", return_value={
                 "expired": False,
                 "current_option_price": 2.1,
                 "pricing_source": "last",
                 "pricing_state": "priced_display_only_last",
                 "current_execution_price": None,
                 "current_execution_basis": None,
                 "price_trigger_ok": False,
                 "warnings": ["Using last trade only for display"],
                 "underlying_price": 125.0,
             }), \
             patch.object(svc, "_get_spy_ret5", return_value=0.0), \
             patch.object(svc, "_check_indicator_exit_without_price", return_value=(False, "")):
            review = svc.review_position(position)

        self.assertEqual(review["pricing_state"], "priced_display_only_last")


if __name__ == "__main__":
    unittest.main()
