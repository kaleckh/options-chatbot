import os
import sys
import unittest
import json
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import options_chatbot as oc
import market_data_service as mds
import supervised_scan as ss
import wfo_optimizer as wfo
from positions_repository import MemoryTrackedPositionsRepository, UnavailableTrackedPositionsRepository
from positions_service import build_position_payload

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from options_algorithm_fixtures import (
    FrozenDateTime,
    build_options_algorithm_fixture_bundle,
    build_tracked_position_scan_pick,
    load_backend_main,
    make_history,
)
from workspace_tempdir import WorkspaceTempDir


class OptionsAlgorithmApiE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._backend_tmp = WorkspaceTempDir(prefix="options-api-e2e-backend")
        db_path = os.path.join(cls._backend_tmp.name, "chat_history.db")
        cls.backend = load_backend_main(db_path)
        cls.client = TestClient(cls.backend.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls._backend_tmp.cleanup()

    def setUp(self):
        self._tmp = WorkspaceTempDir(prefix="options-api-e2e")
        self.bundle = build_options_algorithm_fixture_bundle()
        self.results_path = os.path.join(self._tmp.name, "wfo_results.json")
        self.imported_results_dir = os.path.join(self._tmp.name, "options_validation_runs")
        self.imported_latest_path = os.path.join(self.imported_results_dir, "latest.json")
        self.imported_daily_latest_path = os.path.join(self.imported_results_dir, "latest_daily.json")
        self.imported_daily_forward_latest_path = os.path.join(self.imported_results_dir, "latest_daily_forward.json")
        self.historical_db_path = os.path.join(self._tmp.name, "options_history.db")
        self.market_data_db_path = os.path.join(self._tmp.name, "market_data.db")
        self.forward_ledger_db_path = os.path.join(self._tmp.name, "forward_tracking.db")
        self.options_profit_state_dir = os.path.join(self._tmp.name, "options_profit")
        mds._MEMORY_CACHE.clear()
        mds._SCHEMA_READY.clear()
        mds.reset_cache_stats()
        self.stack = ExitStack()
        self.addCleanup(self._cleanup)

        self.stack.enter_context(
            patch.dict(
                os.environ,
                {
                    "MARKET_DATA_DB_PATH": self.market_data_db_path,
                    "HISTORICAL_OPTIONS_DB_PATH": self.historical_db_path,
                    "FORWARD_OPTIONS_LEDGER_DB_PATH": self.forward_ledger_db_path,
                    "FORWARD_OPTIONS_AUTHORITATIVE_LEDGER_DB_PATH": self.forward_ledger_db_path,
                    "OPTIONS_PROFIT_STATE_DIR": self.options_profit_state_dir,
                },
                clear=False,
            )
        )
        self.stack.enter_context(patch.object(oc, "DEFAULT_WATCHLIST", self.bundle.watchlist))
        self.stack.enter_context(patch.object(wfo, "DEFAULT_WATCHLIST", self.bundle.watchlist))
        self.stack.enter_context(patch.object(oc.yf, "Ticker", side_effect=self.bundle.make_ticker))
        self.stack.enter_context(patch.object(wfo.yf, "Ticker", side_effect=self.bundle.make_ticker))
        self.stack.enter_context(patch.object(oc, "datetime", FrozenDateTime))
        self.stack.enter_context(patch.object(wfo, "datetime", FrozenDateTime))
        self.stack.enter_context(patch.object(mds, "datetime", FrozenDateTime))
        self.stack.enter_context(patch.object(oc, "_market_is_open", return_value=False))
        self.stack.enter_context(patch.object(oc, "_load_expectancy_surface_for_live", return_value=None))
        self.stack.enter_context(patch.object(self.backend, "POSITIONS_REPOSITORY", MemoryTrackedPositionsRepository()))
        self.stack.enter_context(patch.object(wfo, "WFO_RESULTS_FILE", self.results_path))
        self.stack.enter_context(patch.object(wfo, "OPTIONS_VALIDATION_RESULTS_DIR", self.imported_results_dir))
        self.stack.enter_context(patch.object(wfo, "OPTIONS_VALIDATION_LATEST_FILE", self.imported_latest_path))
        self.stack.enter_context(patch.object(wfo, "OPTIONS_VALIDATION_DAILY_LATEST_FILE", self.imported_daily_latest_path))
        self.stack.enter_context(
            patch.object(wfo, "OPTIONS_VALIDATION_DAILY_FORWARD_LATEST_FILE", self.imported_daily_forward_latest_path)
        )

    def _cleanup(self):
        mds.reset_cache_stats()
        self.stack.close()
        self._tmp.cleanup()

    def test_options_profit_status_endpoint_returns_read_only_status_surface(self):
        self.assertFalse(Path(self.options_profit_state_dir).exists())
        response = self.client.get("/api/options-profit/status")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertIn("measurement_gate", payload)
        self.assertIn("active_incumbents", payload)
        self.assertIn("current_canary", payload)
        self.assertIn("last_decision", payload)
        self.assertIn("blockers", payload)
        self.assertIn("SPY", payload["active_incumbents"])
        self.assertIn("QQQ", payload["active_incumbents"])
        self.assertIn("call", payload["active_incumbents"]["SPY"])
        self.assertIn("put", payload["active_incumbents"]["SPY"])
        self.assertTrue(payload["active_incumbents"]["SPY"]["call"]["candidate_id"].startswith("SPY__call__"))
        self.assertTrue(payload["active_incumbents"]["QQQ"]["put"]["candidate_id"].startswith("QQQ__put__"))
        self.assertFalse(Path(self.options_profit_state_dir).exists())

    def test_options_profit_status_endpoint_normalizes_legacy_symbol_status_artifact(self):
        state_dir = Path(self.options_profit_state_dir)
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "status.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-04-01T00:00:00Z",
                    "active_incumbents": {
                        "SPY": {
                            "symbol": "SPY",
                            "candidate_id": "SPY__broad_ev7",
                            "cohort_id": "broad_ev7",
                            "base_profile": "index",
                            "overrides": {"entry": {"min_tech_score": 88.0}},
                            "source": "legacy_test",
                            "mode": "incumbent",
                            "status": "incumbent",
                        }
                    },
                    "current_canary": {"symbol": "SPY", "candidate_id": "SPY__broad_ev7"},
                    "last_decision": {"action": "legacy_status"},
                    "blockers": [],
                },
                indent=2,
            ),
            encoding="utf8",
        )

        response = self.client.get("/api/options-profit/status")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["active_incumbents"]["SPY"]["call"]["candidate_id"], "SPY__call__broad_ev7")
        self.assertEqual(payload["active_incumbents"]["SPY"]["put"]["candidate_id"], "SPY__put__broad_ev7")
        self.assertEqual(payload["active_incumbents"]["SPY"]["call"]["overrides"]["entry"]["min_tech_score"], 88.0)
        self.assertIsNone(payload["current_canary"]["SPY"]["call"])
        self.assertIsNone(payload["current_canary"]["SPY"]["put"])
        self.assertTrue(payload["active_incumbents"]["QQQ"]["call"]["candidate_id"].startswith("QQQ__call__"))

    def test_options_profit_status_endpoint_fills_partial_state_with_default_side_entries(self):
        state_dir = Path(self.options_profit_state_dir)
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "incumbents.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-04-01T00:00:00Z",
                    "symbols": {
                        "SPY": {
                            "call": {
                                "symbol": "SPY",
                                "direction": "call",
                                "active": {},
                            }
                        }
                    },
                },
                indent=2,
            ),
            encoding="utf8",
        )

        response = self.client.get("/api/options-profit/status")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertTrue(payload["active_incumbents"]["SPY"]["call"]["candidate_id"].startswith("SPY__call__"))
        self.assertTrue(payload["active_incumbents"]["SPY"]["put"]["candidate_id"].startswith("SPY__put__"))
        self.assertTrue(payload["active_incumbents"]["QQQ"]["call"]["candidate_id"].startswith("QQQ__call__"))

    def test_scan_endpoint_returns_sorted_normalized_contract(self):
        response = self.client.post("/api/scan", json={"n_picks": 3, "use_recommended_policy": False})
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertIn("picks", payload)
        picks = payload["picks"]
        self.assertLessEqual(len(picks), 3)
        self.assertTrue(picks)

        required = {
            "ticker",
            "type",
            "prediction_type",
            "direction",
            "direction_score",
            "quality_score",
            "ev",
            "dte",
            "target_move_pct",
            "avg_volume_20d",
            "avg_dollar_volume_20d",
            "underlying_liquidity_tier",
            "contract_symbol",
            "expiry",
            "selection_source",
            "promotion_class",
            "candidate_rank",
            "quote_basis",
            "entry_execution_price",
            "entry_execution_basis",
            "entry_fee_total_usd",
            "profitability_eligibility",
            "profitability_blockers",
        }
        for pick in picks:
            self.assertTrue(required.issubset(pick.keys()))
            self.assertEqual(pick["prediction_type"], "daily_scan")
            self.assertEqual(pick["type"], pick["direction"])
            self.assertIn(pick["type"], {"call", "put"})
            self.assertEqual(pick["entry_fee_total_usd"], 0.65)
            self.assertIn(pick["profitability_eligibility"], {"eligible", "ineligible"})
            self.assertIsInstance(pick["profitability_blockers"], list)

        self.assertEqual(
            picks,
            sorted(picks, key=oc._candidate_rank_tuple, reverse=True),
        )
        returned_tickers = {pick["ticker"] for pick in picks}
        self.assertIn("AAA", returned_tickers)
        self.assertNotIn("ILLQ", returned_tickers)
        self.assertNotIn("FAIL", returned_tickers)
        self.assertTrue(payload["forward_truth_recorded"])
        self.assertIsInstance(payload["forward_truth_session_id"], int)
        self.assertIsNone(payload["forward_truth_error"])
        self.assertEqual(payload["forward_truth_evidence_class"], "live_production")
        self.assertTrue(payload["forward_truth_authoritative"])

        evidence_response = self.client.get("/api/backtest/forward-evidence")
        self.assertEqual(evidence_response.status_code, 200)
        evidence = evidence_response.json()
        self.assertEqual(evidence["source_label"], "api_scan_auto")
        self.assertEqual(evidence["recent_session_count"], 1)
        self.assertGreaterEqual(evidence["authoritative_session_count"], 0)
        self.assertGreaterEqual(evidence["scan_pick_count"], len(picks))
        self.assertGreaterEqual(evidence["eligible_scan_pick_count"], 0)
        self.assertGreaterEqual(evidence["ledger_summary"]["observation_scan_pick_count"], len(picks))
        self.assertTrue(evidence["activation_check"]["active"])
        self.assertEqual(evidence["activation_check"]["status"], "active")
        self.assertEqual(evidence["forward_truth_recording_failure_count"], 0)
        self.assertGreaterEqual(evidence["exact_contract_capture_counts"]["with_contract_count"], 1)

    def test_scan_endpoint_ranks_dense_calibrated_live_picks_by_expectancy(self):
        def _lookup(_surface, *, direction_score, **_kwargs):
            expectancy = 12.0 if float(direction_score) >= 50.0 else 28.0
            return {
                "avg_pnl_pct": expectancy,
                "avg_pnl_pct_raw": expectancy,
                "parent_avg_pnl_pct": expectancy,
                "used_parent_shrinkage": False,
                "sparse_warning": None,
                "calibration_density": "dense",
                "dense_cohort": True,
                "lookup_source": "regime_direction_dir_quality",
                "trades": 12,
                "surface_provenance": {"truth_source": "historical_imported_daily"},
            }

        with patch.object(oc, "_load_expectancy_surface_for_live", return_value={"available": True}), \
             patch.object(oc, "lookup_calibrated_expectancy", side_effect=_lookup):
            response = self.client.post("/api/scan", json={"n_picks": 2, "use_recommended_policy": False})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        picks = payload["picks"]
        self.assertGreaterEqual(len(picks), 1)
        self.assertTrue(all(pick["calibrated_expectancy_pct"] is not None for pick in picks))
        self.assertTrue(all(pick["expectancy_selection_source"] == "replay_calibrated" for pick in picks))
        self.assertEqual(picks, sorted(picks, key=oc._candidate_rank_tuple, reverse=True))

    def test_scan_endpoint_records_bootstrap_expectancy_source_when_dense_calibration_is_missing(self):
        response = self.client.post("/api/scan", json={"n_picks": 2, "use_recommended_policy": False})
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        picks = payload["picks"]
        self.assertTrue(picks)
        self.assertTrue(all(pick["expectancy_selection_source"] == "bootstrap_heuristic" for pick in picks))
        self.assertTrue(all(pick["ev"] is not None for pick in picks))

    def test_scan_fails_closed_when_playbook_exit_audit_errors(self):
        backtest_response = self.client.post(
            "/api/backtest",
            json={"lookback_years": 1, "iv_adj": 1.2, "truth_lane": "synthetic"},
        )
        self.assertEqual(backtest_response.status_code, 200)

        with patch.object(ss, "build_playbook_exit_audit", return_value={"error": "exit audit unavailable"}):
            response = self.client.post(
                "/api/scan",
                json={"n_picks": 2, "use_recommended_policy": True, "min_trades": 1, "truth_lane": "synthetic"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["policy_fail_closed"])
        self.assertEqual(payload["picks"], [])
        self.assertIn("exit audit unavailable", payload["policy_error"])
        self.assertEqual(payload["playbook_exit_audit"], None)

    def test_scan_playbook_guardrails_fail_closed_when_positions_storage_is_unavailable(self):
        unavailable = UnavailableTrackedPositionsRepository("tracked positions unavailable")
        with patch.object(self.backend, "POSITIONS_REPOSITORY", unavailable):
            response = self.client.post(
                "/api/scan",
                json={
                    "n_picks": 3,
                    "playbook": "short_term",
                    "use_recommended_policy": False,
                    "include_blocked_guardrail_picks": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["picks"])
        self.assertFalse(payload["exposure_snapshot"]["available"])
        self.assertEqual(payload["guardrail_decision_counts"]["blocked"], len(payload["picks"]))
        for pick in payload["picks"]:
            self.assertEqual(pick["guardrail_decision"], "blocked")
            self.assertEqual(pick["suggested_size_tier"], "blocked")
            self.assertTrue(any("failed closed" in reason.lower() for reason in pick["guardrail_reasons"]))

    def test_scan_endpoint_fail_open_when_forward_truth_recording_fails(self):
        with patch.object(self.backend, "record_forward_snapshot", side_effect=RuntimeError("ledger down")):
            response = self.client.post("/api/scan", json={"n_picks": 2, "use_recommended_policy": False})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["picks"])
        self.assertFalse(payload["forward_truth_recorded"])
        self.assertIsNone(payload["forward_truth_session_id"])
        self.assertIn("ledger down", payload["forward_truth_error"])

        evidence_response = self.client.get("/api/backtest/forward-evidence")
        self.assertEqual(evidence_response.status_code, 200)
        evidence = evidence_response.json()
        self.assertEqual(evidence["forward_truth_recording_failure_count"], 1)
        self.assertFalse(evidence["activation_check"]["active"])
        self.assertIn("ledger down", evidence["recording_health"]["latest_failure"]["forward_truth_error"])

    def test_archived_forward_backtest_endpoint_returns_clean_insufficient_result_without_scan_evidence(self):
        response = self.client.post("/api/backtest/archived-forward", json={})
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload["insufficient_archived_evidence"])
        self.assertEqual(payload["status"], "insufficient_archived_evidence")
        self.assertEqual(payload["candidate_source"], wfo.FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE)
        self.assertEqual(payload["evidence_status"], wfo.ARCHIVED_EXACT_INSUFFICIENT_STATUS)

    def test_forward_evidence_report_marks_latest_authoritative_empty_scan_as_archived_unavailable(self):
        first = self.client.post("/api/scan", json={"n_picks": 2, "use_recommended_policy": False})
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()["forward_truth_recorded"])
        self.assertEqual(first.json()["forward_truth_evidence_class"], "live_production")
        self.assertTrue(first.json()["forward_truth_authoritative"])

        empty_scan_result = {
            "picks": [],
            "ranked_picks": [],
            "policy_applied": False,
            "policy": {},
            "playbook": {"id": "short_term"},
            "truth_lane": "historical_imported_daily",
            "candidate_count": 0,
            "returned_count": 0,
            "scan_funnel": {
                "raw_candidates": 0,
                "post_policy_visible": 0,
                "post_guardrails_visible": 0,
                "returned_picks": 0,
                "policy_filtered_out": 0,
                "guardrail_filtered_out": 0,
                "final_trimmed": 0,
            },
            "policy_decision_counts": {},
            "guardrail_decision_counts": {},
        }
        with patch.object(self.backend, "run_supervised_scan", return_value=empty_scan_result):
            second = self.client.post("/api/scan", json={"n_picks": 2, "use_recommended_policy": False})
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["forward_truth_recorded"])
        self.assertEqual(second.json()["forward_truth_evidence_class"], "live_production")
        self.assertTrue(second.json()["forward_truth_authoritative"])
        self.assertEqual(second.json()["picks"], [])

        evidence_response = self.client.get("/api/backtest/forward-evidence")
        self.assertEqual(evidence_response.status_code, 200)
        evidence = evidence_response.json()
        self.assertFalse(evidence["activation_check"]["active"])
        self.assertEqual(
            evidence["activation_check"]["status"],
            "historical_evidence_only_latest_scan_empty",
        )
        self.assertTrue(evidence["activation_check"]["historical_evidence_available"])
        self.assertEqual(evidence["activation_check"]["latest_recorded_scan_pick_count"], 0)
        self.assertGreaterEqual(evidence["authoritative_session_count"], 0)
        self.assertGreaterEqual(evidence["ledger_summary"]["observation_scan_pick_count"], 0)

    def test_sector_endpoint_reuses_cached_history_between_calls(self):
        sector_tickers = {}
        for idx, symbol in enumerate(["XLK", "XLV", "XLF", "XLE", "XLY", "XLP", "XLI", "XLB", "XLRE", "XLU", "XLC"], start=1):
            class _SectorTicker:
                def __init__(self, ticker_symbol: str, start_price: float):
                    self.ticker_symbol = ticker_symbol
                    self.start_price = start_price
                    self.history_calls = []

                def history(self, period=None, start=None, end=None, interval=None):
                    self.history_calls.append((period, str(start), str(end), interval))
                    return make_history(length=820, start=self.start_price, step=0.15, wave=1.0, volume=10_000_000)

            sector_tickers[symbol] = _SectorTicker(symbol, 50.0 + idx * 5.0)

        with patch.object(mds.yf, "Ticker", side_effect=lambda symbol: sector_tickers[symbol]), \
             patch.object(mds, "_recent_refresh_start", return_value=FrozenDateTime.now().date() + mds.timedelta(days=365)):
            first = self.client.get("/api/sectors")
            second = self.client.get("/api/sectors")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(len(first.json()), 11)
        self.assertEqual(len(second.json()), 11)

    def test_market_data_cache_stats_endpoint_reports_and_resets_counters(self):
        sector_tickers = {}
        for idx, symbol in enumerate(["XLK", "XLV", "XLF", "XLE", "XLY", "XLP", "XLI", "XLB", "XLRE", "XLU", "XLC"], start=1):
            class _SectorTicker:
                def __init__(self, start_price: float):
                    self.start_price = start_price

                def history(self, period=None, start=None, end=None, interval=None):
                    return make_history(length=820, start=self.start_price, step=0.1, wave=0.6, volume=9_000_000)

            sector_tickers[symbol] = _SectorTicker(45.0 + idx * 4.0)

        with patch.object(mds.yf, "Ticker", side_effect=lambda symbol: sector_tickers[symbol]), \
             patch.object(mds, "_recent_refresh_start", return_value=FrozenDateTime.now().date() + mds.timedelta(days=365)):
            sectors_response = self.client.get("/api/sectors")
            self.assertEqual(sectors_response.status_code, 200)

            stats_response = self.client.get("/api/market-data/cache-stats")
            self.assertEqual(stats_response.status_code, 200)
            payload = stats_response.json()
            self.assertIn("stats", payload)
            self.assertIn("totals", payload)
            self.assertGreaterEqual(payload["stats"]["download_history_batch"]["cache_hits"], 1)
            history_stats = payload["stats"].get("history", {})
            self.assertEqual(history_stats.get("persistent_misses"), 11)
            self.assertEqual(payload["totals"].get("network_fetches"), 11)

            reset_response = self.client.post("/api/market-data/cache-stats/reset")
            self.assertEqual(reset_response.status_code, 200)
            reset_payload = reset_response.json()
            self.assertGreaterEqual(reset_payload["before"]["stats"]["download_history_batch"]["cache_hits"], 1)
            self.assertEqual(reset_payload["after"]["stats"], {})

            cleared_response = self.client.get("/api/market-data/cache-stats")
            self.assertEqual(cleared_response.status_code, 200)
            self.assertEqual(cleared_response.json()["stats"], {})

    def test_backtest_endpoint_persists_result_and_report_contract(self):
        self.stack.enter_context(patch.dict(wfo.STRATEGY_PROFILES["equity"], {"strategy_type": "single_leg"}))
        self.stack.enter_context(patch.dict(wfo.STRATEGY_PROFILES["index"], {"strategy_type": "single_leg"}))
        response = self.client.post("/api/backtest", json={"lookback_years": 1, "iv_adj": 1.0})
        self.assertEqual(response.status_code, 200)
        result = response.json()

        required = {
            "run_at",
            "mode",
            "lookback_years",
            "n_picks",
            "pricing_lane",
            "total_days",
            "total_trades",
            "win_rate_pct",
            "full_hit_rate_pct",
            "directional_accuracy_pct",
            "profit_factor",
            "avg_pnl_pct",
            "avg_picks_per_day",
            "sharpe",
            "max_drawdown_pct",
            "universe_filters",
            "eligible_tickers",
            "excluded_tickers",
            "equity_curve",
            "trades",
        }
        self.assertTrue(required.issubset(result.keys()))
        self.assertEqual(result["mode"], "backtest")
        self.assertGreater(result["total_trades"], 0)
        self.assertTrue(os.path.exists(self.results_path))

        sample_trade = result["trades"][0]
        self.assertTrue(
            {
                "ticker",
                "date",
                "type",
                "direction_score",
                "quality_score",
                "tech_score",
                "ev",
                "sector",
                "target_move_pct",
                "prediction_outcome",
                "strike",
                "entry_px",
                "exit_px",
                "exit_day_idx",
                "pricing_lane",
                "pnl_pct",
                "exit_reason",
                "exit_fill_basis",
            }.issubset(sample_trade.keys())
        )
        self.assertTrue(result["equity_curve"])
        self.assertTrue({"date", "cum_pnl_pct"}.issubset(result["equity_curve"][0].keys()))
        self.assertTrue({"history_days_min", "avg_volume_20d_min", "avg_dollar_volume_20d_min", "rolling_window_days"}.issubset(result["universe_filters"].keys()))

        last_response = self.client.get("/api/backtest/last")
        self.assertEqual(last_response.status_code, 200)
        last_result = last_response.json()
        self.assertEqual(last_result["run_at"], result["run_at"])
        self.assertEqual(last_result["total_trades"], result["total_trades"])

        report_response = self.client.get("/api/backtest/report", params={"min_trades": 1})
        self.assertEqual(report_response.status_code, 200)
        report = report_response.json()
        self.assertTrue(
            {
                "generated_at",
                "source",
                "overall",
                "by_direction_score",
                "by_ticker",
                "by_sector",
                "by_regime",
                "best_segments",
                "weakest_segments",
                "risk_flags",
            }.issubset(report.keys())
        )
        self.assertEqual(report["source"]["total_trades"], result["total_trades"])
        self.assertEqual(report["source"]["evidence_status"], wfo.SYNTHETIC_ONLY_STATUS)
        self.assertEqual(
            report["source"]["preferred_evidence_source"]["status"],
            wfo.SYNTHETIC_ONLY_STATUS,
        )
        self.assertEqual(
            [row["value"] for row in report["by_direction_score"]],
            ["00-39", "40-49", "50-59", "60-69", "70-79", "80-100"],
        )
        bucket_required = {
            "group",
            "value",
            "trades",
            "share_of_total_pct",
            "full_hit_rate_pct",
            "directional_accuracy_pct",
            "avg_pnl_pct",
            "profit_factor",
            "avg_ev",
        }
        self.assertTrue(bucket_required.issubset(report["by_direction_score"][-1].keys()))

        metric_truth_response = self.client.get(
            "/api/backtest/metric-truth",
            params={"min_trades": 1, "bucket_size": 10},
        )
        self.assertEqual(metric_truth_response.status_code, 200)
        metric_truth = metric_truth_response.json()
        self.assertTrue(
            {
                "source",
                "quality_bar",
                "overall",
                "metric_buckets",
                "metric_floors",
                "metric_health",
                "risk_flags",
                "recommendations",
            }.issubset(metric_truth.keys())
        )
        self.assertEqual(metric_truth["source"]["total_trades"], result["total_trades"])
        self.assertIn("pricing_lane", metric_truth["source"])
        self.assertIn("playbook", metric_truth["source"])
        self.assertIn("direction_score", metric_truth["metric_buckets"])
        self.assertTrue(metric_truth["metric_buckets"]["direction_score"])
        self.assertIn("direction_score", metric_truth["metric_health"])
        self.assertIn("best_floor", metric_truth["metric_health"]["direction_score"])

        profitability_forensics_response = self.client.get(
            "/api/backtest/profitability-forensics",
            params={"min_trades": 1},
        )
        self.assertEqual(profitability_forensics_response.status_code, 200)
        profitability_forensics = profitability_forensics_response.json()
        self.assertTrue(
            {
                "source",
                "quality_bar",
                "overall",
                "exactness_view",
                "category_order",
                "by_category",
                "best_dense_slices",
                "worst_dense_slices",
                "blockers",
                "recommendations",
            }.issubset(profitability_forensics.keys())
        )
        self.assertEqual(profitability_forensics["source"]["total_trades"], result["total_trades"])
        self.assertIn("symbol", profitability_forensics["by_category"])
        self.assertIn("side", profitability_forensics["by_category"])
        self.assertIn("contract_resolution", profitability_forensics["by_category"])
        self.assertIn("exact_only", profitability_forensics["exactness_view"])

        summary_response = self.client.get(
            "/api/backtest/summary",
            params={"min_trades": 1, "bucket_size": 10},
        )
        self.assertEqual(summary_response.status_code, 200)
        summary = summary_response.json()
        self.assertTrue({"last", "report", "metricTruth", "profitabilityForensics", "comparison"}.issubset(summary.keys()))
        self.assertEqual(summary["last"]["run_at"], result["run_at"])
        self.assertEqual(summary["report"]["source"]["total_trades"], result["total_trades"])
        self.assertEqual(summary["metricTruth"]["source"]["total_trades"], result["total_trades"])
        self.assertEqual(summary["profitabilityForensics"]["source"]["total_trades"], result["total_trades"])

        experiments_response = self.client.post(
            "/api/backtest/experiments",
            json={
                "min_trades": 1,
                "score_floors": [60, 70, 80],
                "max_tickers": 4,
                "max_sectors": 4,
            },
        )
        self.assertEqual(experiments_response.status_code, 200)
        experiments = experiments_response.json()
        self.assertTrue(
            {
                "generated_at",
                "source",
                "strategy_domain",
                "trade_types",
                "quality_bar",
                "overall",
                "category_order",
                "by_category",
                "experiments",
                "passing_experiments",
                "near_miss_experiments",
                "recommendations",
            }.issubset(experiments.keys())
        )
        self.assertEqual(experiments["strategy_domain"], "options")
        self.assertEqual(experiments["trade_types"], ["call", "put"])
        self.assertEqual(experiments["source"]["total_trades"], result["total_trades"])
        self.assertEqual(
            experiments["category_order"],
            ["score_floors", "score_bands", "asset_class", "regime", "asset_class_by_regime", "ticker", "sector"],
        )
        self.assertTrue(
            {
                "score_floors",
                "score_bands",
                "asset_class",
                "regime",
                "asset_class_by_regime",
                "ticker",
                "sector",
            }.issubset(experiments["by_category"].keys())
        )
        self.assertTrue(experiments["experiments"])
        experiment_required = {
            "group",
            "value",
            "category",
            "label",
            "experiment_id",
            "filters",
            "trades",
            "profit_factor",
            "avg_pnl_pct",
            "directional_accuracy_pct",
            "profit_factor_delta",
            "avg_pnl_pct_delta",
            "directional_accuracy_delta_pct",
            "passes_quality_bar",
            "sparse",
        }
        self.assertTrue(experiment_required.issubset(experiments["experiments"][0].keys()))

        stability_response = self.client.get("/api/backtest/stability", params={"min_trades": 1})
        self.assertEqual(stability_response.status_code, 200)
        stability = stability_response.json()
        self.assertTrue(
            {
                "generated_at",
                "source",
                "overall_status",
                "quality_bar",
                "scenario_results",
                "rolling_summary",
                "slice_statuses",
                "promotion_recommendations",
                "recommendations",
            }.issubset(stability.keys())
        )
        self.assertIn(stability["overall_status"], {"promote", "watch", "block"})

        live_policy_response = self.client.get("/api/backtest/live-policy", params={"min_trades": 1})
        self.assertEqual(live_policy_response.status_code, 200)
        live_policy = live_policy_response.json()
        self.assertTrue(
            {
                "generated_at",
                "source",
                "strategy_domain",
                "trade_types",
                "overall",
                "stability",
                "scan_policy",
            }.issubset(live_policy.keys())
        )
        self.assertEqual(live_policy["strategy_domain"], "options")
        self.assertTrue(
            {
                "source_run_at",
                "lookback_years",
                "pricing_lane",
                "playbook",
                "promotion_status",
                "managed_lane_status",
                "truth_window_status",
                "authoritative_evidence_source",
                "authoritative_evidence_status",
                "watch_priority_symbols",
                "watch_deprioritized_symbols",
            }.issubset(live_policy.keys())
        )
        self.assertIn(live_policy["scan_policy"]["mode"], {"replay_backed_focus", "replay_backed_watch"})
        self.assertTrue(
            {
                "promotion_status",
                "managed_lane_status",
                "truth_window_status",
                "hard_filters",
                "preferred_filters",
                "highlighted_tickers",
                "watch_priority_symbols",
                "watch_deprioritized_symbols",
                "rationale",
                "warnings",
                "supporting_slices",
            }.issubset(live_policy["scan_policy"].keys())
        )

        focused_scan_response = self.client.post(
            "/api/scan",
            json={"n_picks": 3, "use_recommended_policy": True, "min_trades": 1, "truth_lane": "synthetic"},
        )
        self.assertEqual(focused_scan_response.status_code, 200)
        focused_scan = focused_scan_response.json()
        self.assertTrue(focused_scan["policy_applied"])
        self.assertIn("policy", focused_scan)
        self.assertIn("playbook_exit_audit", focused_scan)
        self.assertIn("policy_decision_counts", focused_scan)
        self.assertIn("watch_picks", focused_scan)
        self.assertIn("managed_lane_status", focused_scan)
        self.assertIn("truth_window_status", focused_scan)
        self.assertGreaterEqual(focused_scan["candidate_count"], focused_scan["returned_count"])
        self.assertTrue(
            {
                "playbook",
                "promotion_status",
                "approved",
                "watch",
                "blocked",
            }.issubset(focused_scan["playbook_exit_audit"].keys())
        )
        self.assertEqual(focused_scan["picks"], [])
        for pick in focused_scan["watch_picks"]:
            self.assertEqual(pick["policy_decision"], "watch")
            self.assertIn("policy_fit_reasons", pick)
            self.assertIn("market_regime", pick)
            self.assertIn("sector", pick)
            self.assertFalse(pick["managed_eligible"])

        hard_filters = live_policy["scan_policy"]["hard_filters"]
        if hard_filters.get("direction_score_min") is not None:
            for pick in focused_scan["watch_picks"]:
                self.assertGreaterEqual(pick["direction_score"], hard_filters["direction_score_min"])
        if hard_filters.get("direction_score_max") is not None:
            for pick in focused_scan["watch_picks"]:
                self.assertLessEqual(pick["direction_score"], hard_filters["direction_score_max"])

        exit_audit_response = self.client.get(
            "/api/backtest/exit-audit",
            params={"playbook": "short_term", "min_trades": 1},
        )
        self.assertEqual(exit_audit_response.status_code, 200)
        exit_audit = exit_audit_response.json()
        self.assertTrue(
            {
                "generated_at",
                "source_run_at",
                "lookback_years",
                "pricing_lane",
                "playbook",
                "promotion_status",
                "overall_playbook_trades",
                "policy_summary",
                "approved",
                "watch",
                "blocked",
            }.issubset(exit_audit.keys())
        )
        self.assertEqual(exit_audit["playbook"], "short_term")
        self.assertTrue(
            {
                "trades",
                "avg_pnl_pct",
                "profit_factor",
                "directional_accuracy_pct",
                "exit_reasons",
            }.issubset(exit_audit["approved"].keys())
        )

    def test_scan_playbook_guardrails_block_duplicate_ticker_exposure(self):
        repo = MemoryTrackedPositionsRepository()
        open_pick = build_tracked_position_scan_pick(self.bundle)
        existing_position = build_position_payload(
            scan_pick=open_pick,
            fill_price=3.2,
            contracts=1,
            filled_at="2026-03-31T09:35:00",
            notes="Existing open position",
        )
        repo.create_position(existing_position)

        spy_pick = dict(open_pick)
        spy_pick.update({
            "ticker": "SPY",
            "direction": "call",
            "asset_class": "index",
            "sector": "Index ETF",
            "direction_score": 68.0,
            "quality_score": 74.0,
        })

        with patch.object(self.backend, "POSITIONS_REPOSITORY", repo), \
             patch.object(self.backend, "scan_daily_top_trades", return_value=[open_pick, spy_pick]):
            response = self.client.post(
                "/api/scan",
                json={
                    "n_picks": 4,
                    "playbook": "short_term",
                    "use_recommended_policy": False,
                    "include_blocked_guardrail_picks": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["playbook"]["id"], "short_term")
        self.assertIn("exposure_snapshot", payload)
        self.assertEqual(payload["exposure_snapshot"]["open_positions"], 1)
        self.assertIn("guardrail_decision_counts", payload)

        aaa_pick = next((pick for pick in payload["picks"] if pick["ticker"] == "AAA"), None)
        self.assertIsNotNone(aaa_pick)
        self.assertEqual(aaa_pick["guardrail_decision"], "blocked")
        self.assertEqual(aaa_pick["suggested_size_tier"], "blocked")
        self.assertTrue(aaa_pick["guardrail_reasons"])

    def test_scan_backfills_after_blocked_top_pick(self):
        repo = MemoryTrackedPositionsRepository()
        open_pick = build_tracked_position_scan_pick(self.bundle)
        repo.create_position(
            build_position_payload(
                scan_pick=open_pick,
                fill_price=3.2,
                contracts=1,
                filled_at="2026-03-31T09:35:00",
                notes="Existing open position",
            )
        )
        replacement_pick = dict(open_pick)
        replacement_pick.update(
            {
                "ticker": "SPY",
                "direction": "call",
                "asset_class": "index",
                "sector": "Index ETF",
                "direction_score": 68.0,
                "quality_score": 74.0,
            }
        )

        with patch.object(self.backend, "POSITIONS_REPOSITORY", repo), \
             patch.object(self.backend, "scan_daily_top_trades", return_value=[open_pick, replacement_pick]):
            response = self.client.post(
                "/api/scan",
                json={
                    "n_picks": 1,
                    "playbook": "short_term",
                    "use_recommended_policy": False,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["returned_count"], 1)
        self.assertEqual(payload["picks"][0]["ticker"], "SPY")
        self.assertEqual(payload["picks"][0]["guardrail_decision"], "caution")

    def test_scan_pick_carries_active_profit_candidate_context(self):
        scan_pick = build_tracked_position_scan_pick(self.bundle)
        expected_profit_context = {
            "candidate_id": "SPY__call__baseline_broad_control",
            "cohort_id": "baseline_broad_control",
            "mode": "incumbent",
            "status": "incumbent",
        }

        with patch.object(self.backend, "scan_daily_top_trades", return_value=[scan_pick]), \
             patch.object(self.backend, "live_profile_entry_for_symbol", return_value=expected_profit_context):
            response = self.client.post(
                "/api/scan",
                json={
                    "n_picks": 1,
                    "use_recommended_policy": False,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["picks"]), 1)
        pick = payload["picks"][0]
        self.assertEqual(pick["profit_candidate_id"], expected_profit_context["candidate_id"])
        self.assertEqual(pick["policy_artifact_id"], expected_profit_context["candidate_id"])
        self.assertEqual(pick["cohort_id"], expected_profit_context["cohort_id"])
        self.assertEqual(pick["cohort_role"], expected_profit_context["mode"])

    def test_speculative_playbook_stays_observation_only_and_keeps_its_own_cohort(self):
        speculative_pick = {
            "ticker": "SPY",
            "direction": "call",
            "direction_score": 84.0,
            "quality_score": 78.0,
            "tech_score": 73.0,
            "ev_pct": 13.8,
            "stock_price": 520.0,
            "strike_est": 528.0,
            "est_premium": 1.15,
            "delta": 0.28,
            "dte": 5,
            "iv_percentile": 42.0,
            "expiry": "2026-04-17",
            "asset_class": "index",
            "sector": "Index ETF",
            "market_regime": "bullish",
            "spy_ret5": 0.8,
            "quote_freshness_status": "fresh",
            "target_move_pct": 2.4,
            "type": "daily_scan",
        }
        off_playbook_pick = {
            "ticker": "IWM",
            "direction": "call",
            "direction_score": 82.0,
            "quality_score": 77.0,
            "tech_score": 71.0,
            "ev_pct": 12.9,
            "stock_price": 216.0,
            "strike_est": 221.0,
            "est_premium": 1.2,
            "delta": 0.27,
            "dte": 5,
            "iv_percentile": 44.0,
            "expiry": "2026-04-17",
            "asset_class": "index",
            "sector": "Index ETF",
            "market_regime": "bullish",
            "spy_ret5": 0.8,
            "quote_freshness_status": "fresh",
            "target_move_pct": 2.6,
            "type": "daily_scan",
        }
        baseline_context = {
            "candidate_id": "SPY__call__baseline_broad_control",
            "cohort_id": "baseline_broad_control",
            "mode": "incumbent",
            "status": "incumbent",
        }

        with patch.object(self.backend, "scan_daily_top_trades", return_value=[speculative_pick, off_playbook_pick]), \
             patch.object(self.backend, "live_profile_entry_for_symbol", return_value=baseline_context):
            response = self.client.post(
                "/api/scan",
                json={
                    "playbook": "speculative",
                    "n_picks": 5,
                    "use_recommended_policy": False,
                    "include_blocked_guardrail_picks": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["playbook"]["id"], "speculative")
        self.assertTrue(any(item["id"] == "speculative" for item in payload["playbooks"]))
        picks = {pick["ticker"]: pick for pick in payload["picks"]}
        self.assertEqual(picks["SPY"]["guardrail_decision"], "clear")
        self.assertEqual(picks["SPY"]["suggested_size_tier"], "starter")
        self.assertTrue(picks["SPY"]["observation_only"])
        self.assertTrue(picks["SPY"]["speculative_flag"])
        self.assertEqual(picks["SPY"]["convexity_class"], "speculative")
        self.assertGreaterEqual(picks["SPY"]["risk_tier"], 4)
        self.assertGreaterEqual(picks["SPY"]["upside_tier"], 4)
        self.assertEqual(picks["SPY"]["profit_candidate_id"], "SPY__call__speculative_short_dte")
        self.assertEqual(picks["SPY"]["policy_artifact_id"], "SPY__call__speculative_short_dte")
        self.assertEqual(picks["SPY"]["cohort_id"], "speculative_short_dte")
        self.assertEqual(picks["SPY"]["cohort_role"], "observation")
        self.assertEqual(picks["IWM"]["guardrail_decision"], "blocked")
        self.assertTrue(picks["IWM"]["guardrail_reasons"])

    def test_bearish_defensive_playbook_only_clears_matching_slice(self):
        bearish_pick = {
            "ticker": "PFE",
            "direction": "put",
            "direction_score": 82.0,
            "quality_score": 78.0,
            "tech_score": 74.0,
            "ev_pct": 12.5,
            "stock_price": 38.5,
            "strike_est": 37.0,
            "est_premium": 1.45,
            "expiry": "2026-04-17",
            "asset_class": "equity",
            "sector": "Healthcare",
            "market_regime": "bearish",
            "spy_ret5": -1.2,
            "target_move_pct": 4.2,
            "type": "daily_scan",
        }
        off_playbook_pick = {
            "ticker": "MSFT",
            "direction": "call",
            "direction_score": 85.0,
            "quality_score": 80.0,
            "tech_score": 79.0,
            "ev_pct": 14.0,
            "stock_price": 420.0,
            "strike_est": 430.0,
            "est_premium": 3.4,
            "expiry": "2026-04-17",
            "asset_class": "equity",
            "sector": "Technology",
            "market_regime": "bullish",
            "spy_ret5": 1.4,
            "target_move_pct": 3.8,
            "type": "daily_scan",
        }

        with patch.object(self.backend, "scan_daily_top_trades", return_value=[bearish_pick, off_playbook_pick]):
            response = self.client.post(
                "/api/scan",
                json={
                    "playbook": "bearish_defensive",
                    "n_picks": 5,
                    "use_recommended_policy": False,
                    "include_blocked_guardrail_picks": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["playbook"]["id"], "bearish_defensive")
        self.assertTrue(any(item["id"] == "bearish_defensive" for item in payload["playbooks"]))
        picks = {pick["ticker"]: pick for pick in payload["picks"]}
        self.assertEqual(picks["PFE"]["guardrail_decision"], "clear")
        self.assertEqual(picks["MSFT"]["guardrail_decision"], "blocked")
        self.assertTrue(picks["MSFT"]["guardrail_reasons"])

    def test_bullish_momentum_playbook_only_clears_matching_slice(self):
        bullish_pick = {
            "ticker": "AAA",
            "direction": "call",
            "direction_score": 84.0,
            "quality_score": 79.0,
            "tech_score": 76.0,
            "ev_pct": 15.5,
            "stock_price": 138.5,
            "strike_est": 145.0,
            "est_premium": 2.15,
            "expiry": "2026-04-17",
            "asset_class": "equity",
            "sector": "Technology",
            "market_regime": "bullish",
            "spy_ret5": 1.3,
            "target_move_pct": 4.6,
            "type": "daily_scan",
        }
        off_playbook_pick = {
            "ticker": "SPY",
            "direction": "call",
            "direction_score": 87.0,
            "quality_score": 82.0,
            "tech_score": 80.0,
            "ev_pct": 16.2,
            "stock_price": 520.0,
            "strike_est": 525.0,
            "est_premium": 3.9,
            "expiry": "2026-04-17",
            "asset_class": "index",
            "sector": "Index ETF",
            "market_regime": "bullish",
            "spy_ret5": 1.3,
            "target_move_pct": 2.8,
            "type": "daily_scan",
        }

        with patch.object(self.backend, "scan_daily_top_trades", return_value=[bullish_pick, off_playbook_pick]):
            response = self.client.post(
                "/api/scan",
                json={
                    "playbook": "bullish_momentum",
                    "n_picks": 5,
                    "use_recommended_policy": False,
                    "include_blocked_guardrail_picks": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["playbook"]["id"], "bullish_momentum")
        self.assertTrue(any(item["id"] == "bullish_momentum" for item in payload["playbooks"]))
        picks = {pick["ticker"]: pick for pick in payload["picks"]}
        self.assertEqual(picks["AAA"]["guardrail_decision"], "clear")
        self.assertEqual(picks["SPY"]["guardrail_decision"], "blocked")
        self.assertTrue(picks["SPY"]["guardrail_reasons"])

    def test_report_endpoint_returns_error_when_no_backtest_exists(self):
        response = self.client.get("/api/backtest/report", params={"min_trades": 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"error": "No backtest results found"})

        experiments_response = self.client.post("/api/backtest/experiments", json={"min_trades": 1})
        self.assertEqual(experiments_response.status_code, 200)
        self.assertEqual(experiments_response.json(), {"error": "No backtest results found"})

        live_policy_response = self.client.get("/api/backtest/live-policy", params={"min_trades": 1})
        self.assertEqual(live_policy_response.status_code, 200)
        self.assertEqual(live_policy_response.json(), {"error": "No backtest results found"})

        focused_scan_response = self.client.post(
            "/api/scan",
            json={"n_picks": 3, "use_recommended_policy": True, "min_trades": 1},
        )
        self.assertEqual(focused_scan_response.status_code, 200)
        focused_scan = focused_scan_response.json()
        self.assertFalse(focused_scan["policy_applied"])
        self.assertIn("No backtest results found", focused_scan["policy_error"])
        self.assertTrue(focused_scan["policy_fail_closed"])
        self.assertEqual(focused_scan["picks"], [])

        roll_response = self.client.post("/api/scan/roll", json={"n_picks": 3})
        self.assertEqual(roll_response.status_code, 200)
        self.assertTrue(roll_response.json()["policy_fail_closed"])

        recommendations_response = self.client.post("/api/scan/recommendations", json={"n_picks": 3})
        self.assertEqual(recommendations_response.status_code, 200)
        self.assertTrue(recommendations_response.json()["policy_fail_closed"])

        exit_audit_response = self.client.get("/api/backtest/exit-audit", params={"playbook": "short_term", "min_trades": 1})
        self.assertEqual(exit_audit_response.status_code, 200)
        self.assertEqual(exit_audit_response.json(), {"error": "No backtest results found"})

    def test_secondary_scan_routes_return_success_payloads_with_policy_context(self):
        pending = [
            {
                **build_tracked_position_scan_pick(self.bundle),
                "type": "daily_scan",
                "outcome": None,
                "current_pnl_pct": 0.0,
            }
        ]

        backtest_response = self.client.post(
            "/api/backtest",
            json={"lookback_years": 1, "iv_adj": 1.2, "truth_lane": "synthetic"},
        )
        self.assertEqual(backtest_response.status_code, 200)

        with patch.object(self.backend, "_load_predictions", return_value=pending):
            roll_response = self.client.post(
                "/api/scan/roll",
                json={"n_picks": 3, "use_recommended_policy": True, "min_trades": 1, "truth_lane": "synthetic"},
            )
            recommendations_response = self.client.post(
                "/api/scan/recommendations",
                json={"n_picks": 3, "use_recommended_policy": True, "min_trades": 1, "truth_lane": "synthetic"},
            )

        self.assertEqual(roll_response.status_code, 200)
        roll_payload = roll_response.json()
        self.assertIn("rolled", roll_payload)
        self.assertIn("new", roll_payload)
        self.assertIn("dropped", roll_payload)
        self.assertIn("policy_applied", roll_payload)
        self.assertIn("policy", roll_payload)
        self.assertIn("playbook", roll_payload)
        self.assertIn("truth_lane", roll_payload)
        self.assertIn("watch_picks", roll_payload)
        self.assertIn("managed_lane_status", roll_payload)
        self.assertIn("truth_window_status", roll_payload)

        self.assertEqual(recommendations_response.status_code, 200)
        rec_payload = recommendations_response.json()
        self.assertIn("active_positions", rec_payload)
        self.assertIn("new_opportunities", rec_payload)
        self.assertIn("policy_applied", rec_payload)
        self.assertIn("policy", rec_payload)
        self.assertIn("playbook", rec_payload)
        self.assertIn("truth_lane", rec_payload)
        self.assertIn("watch_picks", rec_payload)
        self.assertIn("managed_lane_status", rec_payload)
        self.assertIn("truth_window_status", rec_payload)

    def test_imported_daily_endpoint_hides_stale_artifact_without_backing_store(self):
        os.makedirs(self.imported_results_dir, exist_ok=True)
        with open(self.imported_daily_latest_path, "w", encoding="utf8") as handle:
            json.dump(
                {
                    "run_at": "2026-03-30T23:44:16",
                    "mode": "backtest",
                    "truth_source": "historical_imported_daily",
                    "pricing_lane": "historical_imported_daily",
                    "playbook": "broad",
                    "lookback_years": 1,
                    "total_trades": 9,
                    "quote_coverage_pct": 3.4,
                    "truth_store": {
                        "snapshot_kind": "daily_eod",
                        "quote_count": 10,
                        "batch_count": 1,
                        "latest_imported_at_utc": "2026-03-30T23:44:16Z",
                        "available_underlyings": ["QQQ", "SPY"],
                    },
                },
                handle,
            )

        response = self.client.get("/api/backtest/last", params={"truth_lane": "historical_imported_daily"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"error": "No backtest results found"})

    def test_live_policy_explicit_imported_lane_fails_closed_when_only_synthetic_exists(self):
        backtest_response = self.client.post(
            "/api/backtest",
            json={"lookback_years": 1, "iv_adj": 1.2, "truth_lane": "synthetic"},
        )
        self.assertEqual(backtest_response.status_code, 200)

        last_imported = self.client.get("/api/backtest/last", params={"truth_lane": "historical_imported_daily"})
        self.assertEqual(last_imported.status_code, 200)
        self.assertEqual(last_imported.json(), {"error": "No backtest results found"})

        policy_response = self.client.get(
            "/api/backtest/live-policy",
            params={"min_trades": 1, "truth_lane": "historical_imported_daily"},
        )
        self.assertEqual(policy_response.status_code, 200)
        self.assertEqual(
            policy_response.json(),
            {"error": "No backtest results found for truth_lane=historical_imported_daily"},
        )

    def test_live_policy_explicit_imported_lane_refuses_caller_supplied_synthetic_result(self):
        backtest_response = self.client.post(
            "/api/backtest",
            json={"lookback_years": 1, "iv_adj": 1.2, "truth_lane": "synthetic"},
        )
        self.assertEqual(backtest_response.status_code, 200)
        synthetic_result = backtest_response.json()

        policy = wfo.build_live_options_trade_policy(
            result=synthetic_result,
            truth_lane="historical_imported_daily",
            min_trades=1,
        )

        self.assertEqual(
            policy,
            {"error": "No backtest results found for truth_lane=historical_imported_daily"},
        )

    def test_live_policy_default_fallback_is_explicitly_synthetic_when_imported_lanes_are_unavailable(self):
        backtest_response = self.client.post(
            "/api/backtest",
            json={"lookback_years": 1, "iv_adj": 1.2, "truth_lane": "synthetic"},
        )
        self.assertEqual(backtest_response.status_code, 200)

        policy_response = self.client.get("/api/backtest/live-policy", params={"min_trades": 1})
        self.assertEqual(policy_response.status_code, 200)
        payload = policy_response.json()
        self.assertEqual(payload["truth_source"], "synthetic_research")
        self.assertTrue(payload["synthetic_only"])
        self.assertIn(payload["managed_lane_status"], {wfo.SYNTHETIC_ONLY_STATUS, "blocked_no_approved_symbols"})
        self.assertIn(payload["truth_window_status"], {"synthetic_only", "unknown"})

    def test_fixture_replay_golden_snapshot_stays_stable(self):
        self.stack.enter_context(patch.dict(wfo.STRATEGY_PROFILES["equity"], {"strategy_type": "single_leg"}))
        self.stack.enter_context(patch.dict(wfo.STRATEGY_PROFILES["index"], {"strategy_type": "single_leg"}))
        backtest_response = self.client.post(
            "/api/backtest",
            json={"lookback_years": 1, "iv_adj": 1.2, "truth_lane": "synthetic"},
        )
        self.assertEqual(backtest_response.status_code, 200)
        backtest = backtest_response.json()

        policy_response = self.client.get(
            "/api/backtest/live-policy",
            params={"min_trades": 1, "truth_lane": "synthetic"},
        )
        self.assertEqual(policy_response.status_code, 200)
        policy = policy_response.json()

        scan_response = self.client.post(
            "/api/scan",
            json={"n_picks": 3, "use_recommended_policy": False},
        )
        self.assertEqual(scan_response.status_code, 200)
        scan = scan_response.json()

        self.assertEqual(backtest["total_trades"], 137)
        self.assertEqual(backtest["selection_source_counts"], {"bootstrap_heuristic": 137})
        self.assertEqual(round(backtest["profit_factor"], 2), 0.70)
        self.assertEqual(policy["scan_policy"]["promotion_status"], "block")
        self.assertEqual(len(scan["picks"]), 1)

        top_pick = scan["picks"][0]
        self.assertEqual(top_pick["ticker"], "SPY")
        self.assertEqual(top_pick["type"], "call")
        self.assertEqual(top_pick["direction_score"], 56.5)
        self.assertEqual(top_pick["quality_score"], 86.0)
        self.assertIsNone(top_pick["calibrated_expectancy_pct"])
        self.assertEqual(top_pick["promotion_class"], "research_bootstrap")
        self.assertEqual(top_pick["selection_source"], "live_chain_exact_contract")


if __name__ == "__main__":
    unittest.main()
