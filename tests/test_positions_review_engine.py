import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parents[0]
BACKEND_DIR = ROOT / "python-backend"
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import market_data_service as mds
import options_chatbot as oc
import options_execution as oe
import positions_service as svc
from options_algorithm_fixtures import FrozenDateTime, build_options_algorithm_fixture_bundle, build_tracked_position_scan_pick
from positions_repository import MemoryTrackedPositionsRepository


class PositionsReviewEngineTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.market_db_path = os.path.join(self._tmp.name, "market_data.db")
        env_patch = patch.dict(
            os.environ,
            {
                "OPTIONS_RUN_MODE": "test",
                "OPTIONS_MARKET_DATA_PROVIDER": "yahoo",
                "MARKET_DATA_DB_PATH": self.market_db_path,
            },
            clear=False,
        )
        env_patch.start()
        self.addCleanup(env_patch.stop)
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

    def _build_vertical_spread_scan_pick(self) -> dict[str, object]:
        ticker = self.bundle.tickers["AAA"]
        spot = float(ticker.history()["Close"].iloc[-1])
        expiry = ticker.options[0]
        calls = ticker.option_chain(expiry).calls.reset_index(drop=True)
        long_row = calls.iloc[1]
        short_row = calls.iloc[3]
        long_mid = round((float(long_row["bid"]) + float(long_row["ask"])) / 2.0, 4)
        short_mid = round((float(short_row["bid"]) + float(short_row["ask"])) / 2.0, 4)
        net_debit = round(long_mid - short_mid, 4)
        inflated_entry = round(float(long_row["ask"]) * 1.05, 4)
        legs = [
            {
                "role": "long",
                "contract_symbol": str(long_row["contractSymbol"]),
                "strike": float(long_row["strike"]),
                "bid": float(long_row["bid"]),
                "ask": float(long_row["ask"]),
                "last": float(long_row["lastPrice"]),
                "mid": long_mid,
                "quote_basis": "mid",
            },
            {
                "role": "short",
                "contract_symbol": str(short_row["contractSymbol"]),
                "strike": float(short_row["strike"]),
                "bid": float(short_row["bid"]),
                "ask": float(short_row["ask"]),
                "last": float(short_row["lastPrice"]),
                "mid": short_mid,
                "quote_basis": "mid",
            },
        ]
        return {
            "ticker": "AAA",
            "type": "call",
            "prediction_type": "daily_scan",
            "direction": "call",
            "strategy_type": "vertical_spread",
            "direction_score": 74.0,
            "quality_score": 68.0,
            "tech_score": 72.0,
            "ev_pct": 19.5,
            "dte": 8,
            "stock_price": round(spot, 2),
            "current_spot": round(spot, 2),
            "underlying_price_at_selection": round(spot, 2),
            "strike": float(long_row["strike"]),
            "short_strike": float(short_row["strike"]),
            "premium": net_debit,
            "mid": net_debit,
            "est_premium": net_debit,
            "net_debit": net_debit,
            "contract_symbol": str(long_row["contractSymbol"]),
            "short_contract_symbol": str(short_row["contractSymbol"]),
            "expiry": expiry,
            "asset_class": "equity",
            "stop_loss_pct": 50.0,
            "profit_target_pct": 100.0,
            "time_exit_day": 4,
            "ret5": 2.8,
            "rsi14": 59.0,
            "bid": float(long_row["bid"]),
            "ask": float(long_row["ask"]),
            "last": float(long_row["lastPrice"]),
            "quote_basis": "mid",
            "quote_time_et": "2026-04-06T10:00:00-04:00",
            "quote_time_utc": "2026-04-06T14:00:00Z",
            "options_data_source": "alpaca_opra",
            "selection_source": "live_chain_exact_contract",
            "promotion_class": "promotable_exact_contract",
            "entry_execution_price": inflated_entry,
            "entry_execution_basis": "ask",
            "entry_quote_snapshot": {
                "captured_at_et": "2026-04-06T10:00:00-04:00",
                "captured_at_utc": "2026-04-06T14:00:00Z",
                "ticker": "AAA",
                "direction": "call",
                "strategy_type": "vertical_spread",
                "options_data_source": "alpaca_opra",
                "entry_execution_price": inflated_entry,
                "entry_execution_basis": "ask",
                "net_debit": net_debit,
                "legs": legs,
            },
            "legs": legs,
        }

    def test_build_position_payload_preserves_quote_timestamp_and_entry_snapshot(self):
        scan_pick = dict(self.scan_pick)
        scan_pick.update(
            {
                "quote_time_et": "2026-04-06T10:00:00-04:00",
                "quote_time_utc": "2026-04-06T14:00:00Z",
                "bid": 4.4,
                "ask": 4.6,
                "mid": 4.5,
                "entry_execution_price": 4.5,
                "entry_execution_basis": "mid",
                "entry_underlying_price": scan_pick["stock_price"],
                "underlying_price_at_selection": scan_pick["stock_price"],
                "current_spot": scan_pick["stock_price"],
                "legs": [
                    {
                        "role": "long",
                        "contract_symbol": scan_pick["contract_symbol"],
                        "strike": scan_pick["strike"],
                        "bid": 4.4,
                        "ask": 4.6,
                        "mid": 4.5,
                    }
                ],
            }
        )

        payload = svc.build_position_payload(
            scan_pick=scan_pick,
            fill_price=4.5,
            contracts=1,
            filled_at="2026-04-06T10:00:00-04:00",
            notes="future pick snapshot",
        )

        self.assertEqual(payload["contract_symbol"], scan_pick["contract_symbol"])
        self.assertEqual(payload["entry_execution_price"], 4.5)
        self.assertEqual(payload["entry_underlying_price"], scan_pick["stock_price"])
        self.assertEqual(payload["source_pick_snapshot"]["quote_time_et"], "2026-04-06T10:00:00-04:00")
        self.assertEqual(payload["source_pick_snapshot"]["bid"], 4.4)
        self.assertEqual(payload["source_pick_snapshot"]["ask"], 4.6)
        self.assertEqual(payload["source_pick_snapshot"]["mid"], 4.5)
        self.assertEqual(payload["source_pick_snapshot"]["entry_execution_price"], 4.5)
        self.assertEqual(payload["source_pick_snapshot"]["entry_execution_basis"], "mid")
        self.assertEqual(payload["source_pick_snapshot"]["entry_underlying_price"], scan_pick["stock_price"])
        self.assertEqual(payload["source_pick_snapshot"]["underlying_price_at_selection"], scan_pick["stock_price"])
        self.assertEqual(payload["source_pick_snapshot"]["current_spot"], scan_pick["stock_price"])
        self.assertEqual(payload["source_pick_snapshot"]["legs"], scan_pick["legs"])
        self.assertEqual(payload["source_pick_snapshot"]["quote_time_utc"], "2026-04-06T14:00:00Z")
        self.assertEqual(payload["source_pick_snapshot"]["original_logged_expiry"], scan_pick["expiry"])
        self.assertEqual(payload["source_pick_snapshot"]["resolved_listed_expiry"], scan_pick["expiry"])
        self.assertIn("entry_quote_snapshot", payload["source_pick_snapshot"])
        snapshot = payload["source_pick_snapshot"]["entry_quote_snapshot"]
        self.assertEqual(snapshot["captured_at_et"], "2026-04-06T10:00:00-04:00")
        self.assertEqual(snapshot["captured_at_utc"], "2026-04-06T14:00:00Z")
        self.assertEqual(snapshot["logged_expiry"], scan_pick["expiry"])
        self.assertEqual(snapshot["resolved_listed_expiry"], scan_pick["expiry"])
        self.assertEqual(snapshot["entry_execution_price"], 4.5)
        self.assertEqual(snapshot["legs"], scan_pick["legs"])

    def test_scan_spread_candidate_normalizes_entry_estimate_to_net_debit(self):
        scan_pick = self._build_vertical_spread_scan_pick()

        normalized = oc._normalize_spread_entry_candidate(dict(scan_pick))

        self.assertEqual(normalized["entry_execution_price"], scan_pick["net_debit"])
        self.assertEqual(normalized["entry_execution_basis"], "spread_mid")

    def test_scan_spread_candidate_preserves_executable_spread_entry(self):
        scan_pick = self._build_vertical_spread_scan_pick()
        scan_pick["entry_execution_price"] = 2.75
        scan_pick["entry_execution_basis"] = "spread_ask_bid"
        scan_pick["promotion_class"] = "research_bootstrap"
        scan_pick.pop("bid", None)
        scan_pick.pop("ask", None)
        scan_pick["entry_profitability_blockers"] = []
        scan_pick["entry_display_price"] = scan_pick["net_debit"]
        scan_pick["entry_display_basis"] = "spread_mid"

        normalized = oc._normalize_spread_entry_candidate(dict(scan_pick))

        self.assertEqual(normalized["entry_execution_price"], 2.75)
        self.assertEqual(normalized["entry_execution_basis"], "spread_ask_bid")

    def test_spread_selection_source_requires_two_live_exact_legs(self):
        source = oc._live_contract_selection_source({
            "strategy_type": "vertical_spread",
            "live_chain": True,
            "long_leg": {"contract_symbol": "AAA260515C00100000", "data_source": "alpaca_opra"},
            "short_leg": {"contract_symbol": "AAA260515C00110000", "data_source": "alpaca_opra"},
        })

        self.assertEqual(source, "live_chain_exact_contract")
        self.assertEqual(
            oc._live_contract_selection_source({
                "strategy_type": "vertical_spread",
                "live_chain": True,
                "long_leg": {"contract_symbol": "AAA260515C00100000"},
                "short_leg": {},
            }),
            "model_contract_fallback",
        )

    def test_executable_vertical_spread_entry_uses_long_ask_minus_short_bid(self):
        result = oe.executable_vertical_spread_entry(
            long_leg={"bid": 4.8, "ask": 5.0},
            short_leg={"bid": 1.7, "ask": 1.9},
            quote_freshness_status="fresh",
        )

        self.assertEqual(result["execution_price"], 3.3)
        self.assertEqual(result["execution_basis"], "spread_ask_bid")
        self.assertEqual(result["display_price"], 3.1)
        self.assertEqual(result["profitability_blockers"], [])

    def test_numeric_helpers_reject_booleans(self):
        self.assertIsNone(oe.safe_float(True))
        self.assertIsNone(oe.safe_int(False))

    def test_vertical_spread_entry_requires_positive_short_bid(self):
        result = oe.executable_vertical_spread_entry(
            long_leg={"bid": 4.8, "ask": 5.0},
            short_leg={"bid": 0.0, "ask": 0.1},
            quote_freshness_status="fresh",
        )

        self.assertFalse(result["executable"])
        self.assertIsNone(result["execution_price"])
        self.assertIn("missing_short_leg_bid", result["profitability_blockers"])

    def test_vertical_spread_pnl_rejects_non_positive_debit(self):
        result = oe.vertical_spread_pnl(
            long_entry_price=1.0,
            short_entry_price=1.25,
            long_exit_price=1.5,
            short_exit_price=0.5,
            contracts=1,
        )

        self.assertIsNone(result["net_pnl_pct"])
        self.assertIsNone(result["gross_pnl_pct"])
        self.assertEqual(result["net_debit"], -0.25)

    def test_option_pnl_net_pct_cannot_exceed_full_loss_after_fees(self):
        result = oe.option_pnl_snapshot(
            entry_execution_price=2.597,
            exit_execution_price=0.0,
            contracts=1,
            entry_fee_total_usd=1.30,
            exit_fee_total_usd=1.30,
        )

        self.assertEqual(result["gross_pnl_pct"], -100.0)
        self.assertEqual(result["net_pnl_pct"], -100.0)

    def test_vertical_spread_net_pct_cannot_exceed_full_loss_after_fees(self):
        result = oe.vertical_spread_pnl(
            long_entry_price=3.0,
            short_entry_price=0.5,
            long_exit_price=0.0,
            short_exit_price=0.0,
            contracts=1,
        )

        self.assertEqual(result["gross_pnl_pct"], -100.0)
        self.assertEqual(result["net_pnl_pct"], -100.0)

    def test_vertical_spread_exit_fee_charges_both_legs_when_closed_as_single_order(self):
        result = oe.vertical_spread_pnl(
            long_entry_price=3.0,
            short_entry_price=1.0,
            long_exit_price=4.0,
            short_exit_price=1.0,
            contracts=1,
            close_as_single_order=True,
        )

        self.assertEqual(result["entry_fee_total_usd"], 1.3)
        self.assertEqual(result["exit_fee_total_usd"], 1.3)
        self.assertEqual(result["fee_total_usd"], 2.6)

    def test_executable_option_price_requires_known_fresh_quote(self):
        result = oe.executable_option_price(
            side="entry",
            bid=1.0,
            ask=1.2,
            quote_freshness_status=None,
        )

        self.assertFalse(result["executable"])
        self.assertIsNone(result["execution_price"])
        self.assertEqual(result["quote_freshness_status"], "unknown")
        self.assertIn("unknown_quote_freshness", result["profitability_blockers"])

    def test_vertical_spread_entry_stale_leg_overrides_fresh_aggregate_status(self):
        result = oe.executable_vertical_spread_entry(
            long_leg={"bid": 4.8, "ask": 5.0, "option_chain_status": "fresh"},
            short_leg={"bid": 1.7, "ask": 1.9, "option_chain_status": "stale"},
            quote_freshness_status="fresh",
        )

        self.assertFalse(result["executable"])
        self.assertIsNone(result["execution_price"])
        self.assertEqual(result["quote_freshness_status"], "stale")
        self.assertIn("stale_quote_freshness", result["profitability_blockers"])

    def test_build_position_payload_normalizes_vertical_spread_entry_snapshot_to_net_debit(self):
        scan_pick = self._build_vertical_spread_scan_pick()

        payload = svc.build_position_payload(
            scan_pick=scan_pick,
            fill_price=float(scan_pick["net_debit"]),
            contracts=1,
            filled_at="2026-04-06T10:00:00-04:00",
            notes="spread payload",
        )

        self.assertEqual(payload["entry_execution_price"], scan_pick["net_debit"])
        self.assertEqual(payload["entry_execution_basis"], "spread_mid")
        self.assertEqual(payload["source_pick_snapshot"]["entry_execution_price"], scan_pick["net_debit"])
        self.assertEqual(payload["source_pick_snapshot"]["entry_execution_basis"], "spread_mid")
        snapshot = payload["source_pick_snapshot"]["entry_quote_snapshot"]
        self.assertEqual(snapshot["entry_execution_price"], scan_pick["net_debit"])
        self.assertEqual(snapshot["entry_execution_basis"], "spread_mid")
        self.assertEqual(snapshot["net_debit"], scan_pick["net_debit"])
        self.assertEqual(snapshot["display_price"], scan_pick["net_debit"])
        self.assertFalse(payload["proof_eligible"])
        self.assertEqual(payload["proof_class"], "ineligible")
        self.assertIn("spread_entry_not_bid_ask", payload["proof_ineligibility_reason"])

    def test_build_position_payload_preserves_executable_spread_entry(self):
        scan_pick = self._build_vertical_spread_scan_pick()
        scan_pick["entry_execution_price"] = 2.75
        scan_pick["entry_execution_basis"] = "spread_ask_bid"
        scan_pick["entry_profitability_blockers"] = []
        scan_pick["entry_display_price"] = scan_pick["net_debit"]
        scan_pick["entry_display_basis"] = "spread_mid"
        scan_pick["entry_quote_snapshot"]["entry_execution_price"] = 2.75
        scan_pick["entry_quote_snapshot"]["entry_execution_basis"] = "spread_ask_bid"
        scan_pick["source_scan_session_id"] = 55
        scan_pick["source_scan_event_key"] = "bullish_pullback_observation:rank_1"
        scan_pick["source_scan_run_id"] = "api_scan_20260406T100000Z"
        scan_pick["source_scan_recorded_at_utc"] = "2026-04-06T14:00:00Z"
        scan_pick["quote_freshness_status"] = "fresh"
        scan_pick["pricing_evidence_class"] = "proof_live_opra_exact_contract"
        scan_pick["profitability_evidence_class"] = "research_profitability_calibration"
        scan_pick["source_separation"] = "pricing_proof_profitability_research"
        scan_pick["promotion_class"] = "research_bootstrap"

        payload = svc.build_position_payload(
            scan_pick=scan_pick,
            fill_price=2.75,
            contracts=1,
            filled_at="2026-04-06T10:00:00-04:00",
            notes="spread payload",
            source_scan_lineage_verified=True,
        )

        self.assertEqual(payload["entry_execution_price"], 2.75)
        self.assertEqual(payload["entry_execution_basis"], "spread_ask_bid")
        self.assertEqual(payload["source_pick_snapshot"]["entry_execution_price"], 2.75)
        self.assertEqual(payload["source_pick_snapshot"]["entry_execution_basis"], "spread_ask_bid")
        snapshot = payload["source_pick_snapshot"]["entry_quote_snapshot"]
        self.assertEqual(snapshot["entry_execution_price"], 2.75)
        self.assertEqual(snapshot["entry_execution_basis"], "spread_ask_bid")
        self.assertEqual(snapshot["display_price"], scan_pick["net_debit"])
        self.assertTrue(payload["proof_eligible"])
        self.assertEqual(payload["proof_class"], "live_scan_exact_contract")

    def test_historical_comparable_spread_uses_daily_snapshot_window(self):
        calls: list[dict[str, object]] = []

        class FakeStore:
            def find_entry_contract(self, **kwargs):
                calls.append(kwargs)
                quote = SimpleNamespace(
                    expiry=date(2026, 6, 19),
                    price=5.0 if kwargs["target_strike"] == 100.0 else 2.0,
                    strike=kwargs["target_strike"],
                    contract_symbol=(
                        "AAA260619C00100000"
                        if kwargs["target_strike"] == 100.0
                        else "AAA260619C00110000"
                    ),
                    underlying_price=101.0,
                    quote_minute_et=svc.DAILY_QUOTE_MINUTE_ET,
                )
                return quote

        scan_pick = {
            "ticker": "AAA",
            "direction": "call",
            "strategy_type": "vertical_spread",
            "strike": 100.0,
            "short_strike": 110.0,
            "expiry": "2026-06-19",
        }

        with patch.object(svc, "_historical_store", return_value=FakeStore()):
            result = svc._resolve_historical_comparable_pick(scan_pick, trade_date=date(2026, 5, 22))

        self.assertIsNotNone(result)
        self.assertEqual(len(calls), 2)
        for call in calls:
            self.assertEqual(call["snapshot_kind"], svc.DAILY_SNAPSHOT_KIND)
            self.assertEqual(call["earliest_minute_et"], svc.DAILY_QUOTE_MINUTE_ET)
            self.assertEqual(call["window_minutes"], 0)

    def test_spread_contract_aliases_count_as_resolved_identity(self):
        scan_pick = {
            "ticker": "SPY",
            "direction": "call",
            "strategy_type": "vertical_spread",
            "strike": 500.0,
            "short_strike": 520.0,
            "expiry": "2026-06-19",
            "contractSymbol": "SPY260619C00500000",
            "shortContractSymbol": "SPY260619C00520000",
        }

        fields = svc._pick_context_fields(scan_pick)

        self.assertEqual(fields["contract_symbol"], "SPY260619C00500000")
        self.assertEqual(fields["short_contract_symbol"], "SPY260619C00520000")
        self.assertTrue(svc._has_resolved_contract_identity(scan_pick))

    def test_manual_spread_fill_requires_short_leg_for_broker_exact_class(self):
        scan_pick = self._build_vertical_spread_scan_pick()
        scan_pick.pop("short_contract_symbol", None)
        scan_pick["short_strike"] = 9999.0

        payload = svc.build_position_payload(
            scan_pick=scan_pick,
            fill_price=float(scan_pick["net_debit"]) + 0.25,
            contracts=1,
            filled_at="2026-04-06T10:00:00-04:00",
            notes="spread payload",
            preserve_fill_price=True,
        )

        self.assertFalse(payload["proof_eligible"])
        self.assertEqual(payload["proof_class"], "ineligible")
        self.assertIn("contract_symbol", payload["proof_ineligibility_reason"])

    def test_review_uses_actual_fill_price_for_stop_target_math(self):
        position = self._build_position(fill_price=2.0)
        position["source_pick_snapshot"]["premium"] = 1.0

        with patch.object(svc, "datetime", FrozenDateTime), \
             patch.object(svc, "_fetch_option_quote", return_value={
                 "expired": False,
                 "current_option_price": 2.2,
                 "pricing_source": "mid",
                 "current_execution_price": 2.2,
                 "current_execution_basis": "mid",
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

    def test_vertical_spread_review_uses_bid_ask_close_label(self):
        scan_pick = self._build_vertical_spread_scan_pick()
        scan_pick["entry_execution_price"] = 2.75
        scan_pick["entry_execution_basis"] = "spread_ask_bid"
        scan_pick["entry_profitability_blockers"] = []
        position = svc.build_position_payload(
            scan_pick=scan_pick,
            fill_price=2.75,
            contracts=1,
            filled_at="2026-04-06T10:00:00-04:00",
            notes="spread payload",
        )
        position["id"] = 10

        calls = self.bundle.tickers["AAA"].option_chain(str(position["expiry"])[:10]).calls
        long_row = calls.loc[calls["contractSymbol"] == scan_pick["contract_symbol"]].iloc[0]
        short_row = calls.loc[calls["contractSymbol"] == scan_pick["short_contract_symbol"]].iloc[0]
        profile = svc._get_profile("AAA", "call")
        slippage_pct = float((profile.get("filters") or {}).get("exit_slippage_pct", 0.0))
        long_exec = oe.executable_option_price(
            side="exit",
            bid=float(long_row["bid"]),
            ask=float(long_row["ask"]),
            last=float(long_row["lastPrice"]),
            slippage_pct=slippage_pct,
            quote_freshness_status="fresh",
        )
        short_exec = oe.executable_option_price(
            side="entry",
            bid=float(short_row["bid"]),
            ask=float(short_row["ask"]),
            last=float(short_row["lastPrice"]),
            slippage_pct=slippage_pct,
            quote_freshness_status="fresh",
        )
        expected_exit = round(max(float(long_exec["execution_price"]) - float(short_exec["execution_price"]), 0.0), 4)

        with patch.object(svc, "datetime", FrozenDateTime), \
             patch.object(svc.yf, "Ticker", side_effect=self.bundle.make_ticker), \
             patch.object(svc, "_get_spy_ret5", return_value=0.0), \
             patch.object(svc, "_check_early_exit", return_value=(False, "")):
            review = svc.review_position(position)

        self.assertEqual(review["pricing_source"], "spread_bid_ask_exact")
        self.assertEqual(review["exit_execution_basis"], "spread_bid_ask")
        self.assertEqual(review["exit_execution_price"], expected_exit)

    def test_review_does_not_use_display_price_as_execution_fallback(self):
        position = self._build_position(fill_price=2.0)

        with patch.object(svc, "datetime", FrozenDateTime), \
             patch.object(svc, "_fetch_option_quote", return_value={
                 "expired": False,
                 "current_option_price": 2.1,
                 "pricing_source": "last",
                 "pricing_state": "priced_display_only_last",
                 "current_execution_price": None,
                 "current_execution_basis": None,
                 "price_trigger_ok": True,
                 "warnings": ["Display-only mark"],
                 "underlying_price": 125.0,
             }), \
             patch.object(svc, "_get_spy_ret5", return_value=0.0), \
             patch.object(svc, "_check_indicator_exit_without_price", return_value=(False, "")):
            review = svc.review_position(position)

        self.assertIsNone(review["exit_execution_price"])
        self.assertIsNone(review["current_pnl_pct"])

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
                 "current_execution_price": 2.4,
                 "current_execution_basis": "mid",
                 "price_trigger_ok": True,
                 "warnings": [],
                 "underlying_price": 126.0,
             }), \
             patch.object(svc, "_get_spy_ret5", return_value=0.8), \
             patch.object(svc, "_check_early_exit", return_value=(True, "tech_score collapsed 40%")):
            review = svc.review_position(position)

        self.assertEqual(review["recommendation"], "SELL")
        self.assertIn("Indicator exit triggered", review["reason"])

    def test_review_recommends_sell_for_executable_profit_harvest(self):
        position = self._build_position(fill_price=2.0)
        position["profit_target_pct"] = 25.0

        with patch.object(svc, "datetime", FrozenDateTime), \
             patch.object(svc, "_fetch_option_quote", return_value={
                 "expired": False,
                 "current_option_price": 2.8,
                 "pricing_source": "mid",
                 "pricing_state": "priced_exact",
                 "current_execution_price": 2.8,
                 "current_execution_basis": "mid",
                 "price_trigger_ok": True,
                 "warnings": [],
                 "underlying_price": 126.0,
             }), \
             patch.object(svc, "_get_spy_ret5", return_value=0.0):
            review = svc.review_position(position)

        self.assertEqual(review["recommendation"], "SELL")
        self.assertIn("profit target", review["reason"])
        self.assertEqual(review["exit_execution_price"], 2.8)
        self.assertEqual(review["pricing_state"], "priced_exact")

    def test_tracked_winner_review_harvests_executable_profit_before_large_target(self):
        position = self._build_position(fill_price=2.0)
        position["profit_target_pct"] = 150.0
        position["source_pick_snapshot"]["cohort_id"] = "tracked_winner_primary"

        with patch.object(svc, "datetime", FrozenDateTime), \
             patch.object(svc, "_fetch_option_quote", return_value={
                 "expired": False,
                 "current_option_price": 3.1,
                 "pricing_source": "mid",
                 "pricing_state": "priced_exact",
                 "current_execution_price": 3.1,
                 "current_execution_basis": "mid",
                 "price_trigger_ok": True,
                 "warnings": [],
                 "underlying_price": 126.0,
             }), \
             patch.object(svc, "_get_spy_ret5", return_value=0.0):
            review = svc.review_position(position)

        self.assertEqual(review["recommendation"], "SELL")
        self.assertIn("Mechanical profit harvest", review["reason"])
        self.assertEqual(review["metrics_snapshot"]["profit_harvest"]["trigger_pct"], 50.0)

    def test_bullish_pullback_review_harvests_executable_profit_before_large_target(self):
        position = self._build_position(fill_price=2.0)
        position["profit_target_pct"] = 150.0
        position["source_pick_snapshot"]["cohort_id"] = "bullish_pullback_observation"

        with patch.object(svc, "datetime", FrozenDateTime), \
             patch.object(svc, "_fetch_option_quote", return_value={
                 "expired": False,
                 "current_option_price": 3.1,
                 "pricing_source": "mid",
                 "pricing_state": "priced_exact",
                 "current_execution_price": 3.1,
                 "current_execution_basis": "mid",
                 "price_trigger_ok": True,
                 "warnings": [],
                 "underlying_price": 126.0,
             }), \
             patch.object(svc, "_get_spy_ret5", return_value=0.0):
            review = svc.review_position(position)

        self.assertEqual(review["recommendation"], "SELL")
        self.assertIn("Mechanical profit harvest", review["reason"])
        self.assertEqual(review["metrics_snapshot"]["profit_harvest"]["trigger_pct"], 50.0)

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

    def test_review_holds_loss_inside_configured_90_percent_stop(self):
        position = self._build_position(fill_price=2.0)
        position["stop_loss_pct"] = 90.0
        position["time_exit_day"] = 999

        with patch.object(svc, "datetime", FrozenDateTime), \
             patch.object(svc, "_fetch_option_quote", return_value={
                 "expired": False,
                 "current_option_price": 0.9,
                 "pricing_source": "mid",
                 "pricing_state": "priced_exact",
                 "current_execution_price": 0.9,
                 "current_execution_basis": "mid",
                 "price_trigger_ok": True,
                 "warnings": [],
                 "underlying_price": 123.0,
             }), \
             patch.object(svc, "_get_spy_ret5", return_value=0.0):
            review = svc.review_position(position)

        self.assertEqual(review["recommendation"], "HOLD")
        self.assertEqual(review["current_pnl_pct"], -55.0)
        self.assertEqual(review["metrics_snapshot"]["review_policy_version"], svc.POSITION_REVIEW_POLICY_VERSION)
        self.assertEqual(review["metrics_snapshot"]["max_live_review_stop_loss_pct"], 90.0)
        self.assertEqual(review["metrics_snapshot"]["configured_stop_loss_pct"], 90.0)
        self.assertEqual(review["metrics_snapshot"]["effective_stop_loss_pct"], 90.0)
        self.assertEqual(review["metrics_snapshot"]["stop_option_price"], 0.2)

    def test_review_sells_when_live_executable_loss_hits_configured_90_percent_stop(self):
        position = self._build_position(fill_price=2.0)
        position["stop_loss_pct"] = 90.0
        position["time_exit_day"] = 999

        with patch.object(svc, "datetime", FrozenDateTime), \
             patch.object(svc, "_fetch_option_quote", return_value={
                 "expired": False,
                 "current_option_price": 0.18,
                 "pricing_source": "mid",
                 "pricing_state": "priced_exact",
                 "current_execution_price": 0.18,
                 "current_execution_basis": "mid",
                 "price_trigger_ok": True,
                 "warnings": [],
                 "underlying_price": 123.0,
             }), \
             patch.object(svc, "_get_spy_ret5", return_value=0.0), \
             patch.object(svc, "_check_early_exit", return_value=(False, "")):
            review = svc.review_position(position)

        self.assertEqual(review["recommendation"], "SELL")
        self.assertEqual(review["current_pnl_pct"], -91.0)
        self.assertIn("stop loss", review["reason"])
        self.assertEqual(review["metrics_snapshot"]["configured_stop_loss_pct"], 90.0)
        self.assertEqual(review["metrics_snapshot"]["effective_stop_loss_pct"], 90.0)

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

    def test_review_open_positions_auto_closes_expired_contracts(self):
        repo = MemoryTrackedPositionsRepository()
        payload = self._build_position(fill_price=4.5, filled_at="2026-03-25T10:00:00", expiry="2026-03-30")
        created = repo.create_position(payload)

        with patch.object(svc, "datetime", FrozenDateTime), \
             patch.object(svc, "_get_spy_ret5", return_value=0.0), \
             patch.object(svc, "_get_underlying_close_on_or_before", return_value=470.0):
            reviewed = svc.review_open_positions(repo)

        self.assertEqual(len(reviewed), 1)
        closed = reviewed[0]
        self.assertEqual(closed["id"], created["id"])
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(closed["exit_reason"], "expired_auto_close")
        self.assertEqual(closed["exit_execution_basis"], "expiry_intrinsic_underlying_close")
        self.assertEqual(closed["exit_option_price"], 7.41)
        self.assertEqual(repo.list_positions("open"), [])
        closed_rows = repo.list_positions("closed")
        self.assertEqual(len(closed_rows), 1)
        self.assertEqual(closed_rows[0]["exit_option_price"], 7.41)

    def test_review_open_positions_auto_closes_expired_worthless_contracts_at_zero(self):
        repo = MemoryTrackedPositionsRepository()
        payload = self._build_position(fill_price=4.5, filled_at="2026-03-25T10:00:00", expiry="2026-03-30")
        created = repo.create_position(payload)

        with patch.object(svc, "datetime", FrozenDateTime), \
             patch.object(svc, "_get_spy_ret5", return_value=0.0), \
             patch.object(svc, "_get_underlying_close_on_or_before", return_value=400.0):
            reviewed = svc.review_open_positions(repo)

        self.assertEqual(len(reviewed), 1)
        closed = reviewed[0]
        self.assertEqual(closed["id"], created["id"])
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(closed["exit_reason"], "expired_auto_close")
        self.assertEqual(closed["exit_option_price"], 0.0)
        self.assertEqual(repo.list_positions("open"), [])

    def test_review_open_positions_auto_closes_any_sell_recommendation(self):
        repo = MemoryTrackedPositionsRepository()
        payload = self._build_position(fill_price=4.5, filled_at="2026-03-25T10:00:00")
        payload["time_exit_day"] = 3
        created = repo.create_position(payload)

        with patch.object(svc, "datetime", FrozenDateTime), \
             patch.object(svc, "_fetch_option_quote", return_value={
                 "expired": False,
                 "current_option_price": 5.0,
                 "pricing_source": "mid",
                 "current_execution_price": 5.0,
                 "current_execution_basis": "mid",
                 "price_trigger_ok": True,
                 "warnings": [],
                 "underlying_price": 126.0,
             }), \
             patch.object(svc, "_get_spy_ret5", return_value=0.0), \
             patch.object(svc, "_check_early_exit", return_value=(False, "")):
            reviewed = svc.review_open_positions(repo)

        self.assertEqual(len(reviewed), 1)
        closed = reviewed[0]
        self.assertEqual(closed["id"], created["id"])
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(closed["last_recommendation"], "SELL")
        self.assertEqual(closed["exit_reason"], "auto_sell_recommendation")
        self.assertEqual(closed["exit_execution_basis"], "mid")
        self.assertEqual(closed["exit_option_price"], 5.0)
        self.assertEqual(repo.list_positions("open"), [])

    def test_review_open_positions_auto_closes_executable_zero_exit(self):
        repo = MemoryTrackedPositionsRepository()
        payload = self._build_position(fill_price=2.0, filled_at="2026-03-30T10:00:00")
        payload["stop_loss_pct"] = 90.0
        payload["time_exit_day"] = 999
        created = repo.create_position(payload)

        with patch.object(svc, "datetime", FrozenDateTime), \
             patch.object(svc, "_fetch_option_quote", return_value={
                 "expired": False,
                 "current_option_price": 0.0,
                 "pricing_source": "bid",
                 "pricing_state": "priced_exact",
                 "current_execution_price": 0.0,
                 "current_execution_basis": "bid",
                 "price_trigger_ok": True,
                 "warnings": [],
                 "underlying_price": 126.0,
             }), \
             patch.object(svc, "_get_spy_ret5", return_value=0.0), \
             patch.object(svc, "_check_early_exit", return_value=(False, "")):
            reviewed = svc.review_open_positions(repo)

        self.assertEqual(len(reviewed), 1)
        closed = reviewed[0]
        self.assertEqual(closed["id"], created["id"])
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(closed["last_recommendation"], "SELL")
        self.assertEqual(closed["exit_reason"], "auto_sell_recommendation")
        self.assertEqual(closed["exit_execution_basis"], "bid")
        self.assertEqual(closed["exit_option_price"], 0.0)
        self.assertEqual(repo.list_positions("open"), [])

    def test_review_open_positions_does_not_auto_close_on_display_only_sell_mark(self):
        repo = MemoryTrackedPositionsRepository()
        payload = self._build_position(fill_price=4.5, filled_at="2026-03-25T10:00:00")
        payload["time_exit_day"] = 3
        created = repo.create_position(payload)

        with patch.object(svc, "datetime", FrozenDateTime), \
             patch.object(svc, "_fetch_option_quote", return_value={
                 "expired": False,
                 "current_option_price": 8.0,
                 "pricing_source": "last",
                 "pricing_state": "priced_display_only_last",
                 "current_execution_price": None,
                 "current_execution_basis": None,
                 "price_trigger_ok": False,
                 "warnings": ["Using last trade only for display."],
                 "underlying_price": 126.0,
             }), \
             patch.object(svc, "_get_spy_ret5", return_value=0.0), \
             patch.object(svc, "_check_indicator_exit_without_price", return_value=(False, "")):
            reviewed = svc.review_open_positions(repo)

        self.assertEqual(len(reviewed), 1)
        reviewed_position = reviewed[0]
        self.assertEqual(reviewed_position["id"], created["id"])
        self.assertEqual(reviewed_position["status"], "open")
        self.assertEqual(reviewed_position["last_recommendation"], "SELL")
        self.assertIsNone(reviewed_position["exit_option_price"])
        self.assertEqual(len(repo.list_positions("open")), 1)
        self.assertEqual(repo.list_positions("closed"), [])

    def test_review_open_positions_does_not_auto_close_unpriced_time_exit(self):
        repo = MemoryTrackedPositionsRepository()
        payload = self._build_position(fill_price=4.5, filled_at="2026-03-25T10:00:00")
        payload["time_exit_day"] = 3
        created = repo.create_position(payload)

        with patch.object(svc, "datetime", FrozenDateTime), \
             patch.object(svc, "_fetch_option_quote", return_value={
                 "expired": False,
                 "current_option_price": None,
                 "pricing_source": "unavailable",
                 "pricing_state": "unpriced_chain_fetch_failed",
                 "current_execution_price": None,
                 "current_execution_basis": None,
                 "price_trigger_ok": False,
                 "warnings": ["No live option quote available."],
                 "underlying_price": 126.0,
             }), \
             patch.object(svc, "_get_spy_ret5", return_value=0.0), \
             patch.object(svc, "_check_indicator_exit_without_price", return_value=(False, "")):
            reviewed = svc.review_open_positions(repo)

        self.assertEqual(len(reviewed), 1)
        reviewed_position = reviewed[0]
        self.assertEqual(reviewed_position["id"], created["id"])
        self.assertEqual(reviewed_position["status"], "open")
        self.assertEqual(reviewed_position["last_recommendation"], "SELL")
        self.assertIsNone(reviewed_position["exit_option_price"])
        self.assertEqual(len(repo.list_positions("open")), 1)
        self.assertEqual(repo.list_positions("closed"), [])

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

    def test_review_open_positions_preserves_existing_approximation_reviews(self):
        position = self._build_position(fill_price=2.0)
        position["id"] = 99
        position["notes"] = "Paper trade - broad screenshot backfill approximation (2026-04-10)"
        position["source_pick_snapshot"]["approximation_only"] = True
        position["latest_review"] = {
            "reviewed_at": "2026-04-14T11:32:07",
            "pricing_source": "spread_mid_approx",
            "recommendation": "HOLD",
            "reason": "Approximate broad-lane spread mark using nearest listed expiry; comparison only.",
            "warnings": ["Approximate P&L based on nearest listed expiry because the logged broad expiry may be synthetic."],
            "metrics_snapshot": {"pricing_state": "priced_spread_nearest_listed_expiry"},
        }

        class _Repo:
            def list_positions(self, status="open"):
                return [position]

            def save_review(self, position_id, review):
                raise AssertionError("approximation_only positions with a latest review should not be re-reviewed")

        with patch.object(svc, "review_position", side_effect=AssertionError("review_position should not run")):
            reviews = svc.review_open_positions(_Repo())

        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0]["id"], 99)
        self.assertEqual(reviews[0]["latest_review"]["pricing_source"], "spread_mid_approx")


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
