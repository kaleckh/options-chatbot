import os
import sys
import unittest
import json
import copy
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd
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


PROOF_GRADE_SCAN_FIELDS = {
    "selection_source": "live_chain_exact_contract",
    "contract_selection_source": "live_chain_exact_contract",
    "promotion_class": "promotable_exact_contract",
    "source_scan_session_id": 55,
    "source_scan_event_key": "short_term:rank_1",
    "source_scan_run_id": "api_scan_20260330T133500Z",
    "source_scan_recorded_at_utc": "2026-03-30T13:35:00Z",
    "entry_date": "2026-03-30",
    "quote_time_et": "2026-03-30T09:35:00-04:00",
    "quote_time_utc": "2026-03-30T13:35:00Z",
    "quote_freshness_status": "fresh",
    "options_data_source": "alpaca_opra",
    "quote_source": "alpaca_opra",
    "entry_execution_basis": "ask",
    "entry_execution_price": 3.2,
    "bid": 3.1,
    "ask": 3.2,
}


def _proof_grade_scan_pick(scan_pick: dict) -> dict:
    proof_pick = dict(scan_pick)
    proof_pick.update(PROOF_GRADE_SCAN_FIELDS)
    return proof_pick


def _proof_grade_closed_snapshot_row() -> dict:
    return {
        "status": "closed",
        "contract_symbol": "SPY260619C00500000",
        "contracts": 1,
        "entry_execution_price": 2.0,
        "entry_execution_basis": "ask",
        "exit_execution_price": 4.0,
        "exit_execution_basis": "spread_bid_ask_exact",
        "net_pnl_pct": 99.0,
        "gross_pnl_pct": 100.0,
        "net_pnl_usd": 198.0,
        "gross_pnl_usd": 200.0,
        "proof_eligible": True,
        "proof_class": "live_scan_exact_contract",
        "source_scan_lineage_verified": True,
        "selection_source": "live_chain_exact_contract",
        "contract_selection_source": "live_chain_exact_contract",
        "source_scan_session_id": 55,
        "source_scan_event_key": "short_term:rank_1",
        "source_scan_run_id": "api_scan_20260330T133500Z",
        "source_scan_recorded_at_utc": "2026-03-30T13:35:00Z",
        "entry_date": "2026-03-30",
        "quote_time_et": "2026-03-30T09:35:00-04:00",
        "quote_time_utc": "2026-03-30T13:35:00Z",
        "quote_freshness_status": "fresh",
        "options_data_source": "alpaca_opra",
        "quote_source": "alpaca_opra",
        "source_pick_snapshot": {
            "contract_symbol": "SPY260619C00500000",
            "proof_class": "live_scan_exact_contract",
            "source_scan_lineage_verified": True,
            "selection_source": "live_chain_exact_contract",
            "contract_selection_source": "live_chain_exact_contract",
            "source_scan_session_id": 55,
            "source_scan_event_key": "short_term:rank_1",
            "source_scan_run_id": "api_scan_20260330T133500Z",
            "source_scan_recorded_at_utc": "2026-03-30T13:35:00Z",
            "entry_date": "2026-03-30",
            "quote_time_et": "2026-03-30T09:35:00-04:00",
            "quote_time_utc": "2026-03-30T13:35:00Z",
            "quote_freshness_status": "fresh",
            "options_data_source": "alpaca_opra",
            "quote_source": "alpaca_opra",
            "entry_execution_price": 2.0,
            "entry_execution_basis": "ask",
        },
    }


class _ProfitStatusSnapshotOnlyRepository:
    is_available = True
    error_message = None
    database_url = "postgresql://example/test"

    def profit_status_snapshot(self):
        return {
            "open_position_count": 2,
            "total_closed_position_count": 2,
            "closed_positions": [
                _proof_grade_closed_snapshot_row(),
                {
                    "contract_symbol": "QQQ260619C00400000",
                    "contracts": 1,
                    "entry_execution_price": 3.0,
                    "exit_execution_price": 1.0,
                    "net_pnl_pct": -67.0,
                    "gross_pnl_pct": -66.7,
                    "proof_eligible": False,
                    "quote_source": "research_backfill",
                },
            ],
        }

    def list_positions(self, *args, **kwargs):
        raise AssertionError("status overlay should use the narrow profit_status_snapshot")


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
        self.forward_tracking_dir = os.path.join(self._tmp.name, "forward_tracking")
        self.profitability_lab_dir = os.path.join(self._tmp.name, "profitability_lab")
        self.original_strategy_profiles = oc.get_strategy_profiles_snapshot()
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
                    "OPTIONS_FORWARD_TRACKING_DIR": self.forward_tracking_dir,
                    "OPTIONS_PROFITABILITY_LAB_DIR": self.profitability_lab_dir,
                    "OPTIONS_MARKET_DATA_PROVIDER": "yahoo",
                    "OPTIONS_RUN_MODE": "test",
                    "OPTIONS_ENFORCE_LANE_PROFITABILITY_GATE": "0",
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
        with oc._STRATEGY_PROFILE_LOCK:
            oc._swap_strategy_profiles_unlocked(copy.deepcopy(self.original_strategy_profiles))
            oc._PROFILE_LOAD_FINGERPRINT = None
            oc._PROFILE_LOADED_SNAPSHOT = copy.deepcopy(self.original_strategy_profiles)
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
        self.assertEqual(
            payload["paper_gate_operator_workflow"]["primary_state"],
            "paper_gate_artifacts_missing",
        )
        self.assertFalse(Path(self.options_profit_state_dir).exists())

    def test_options_profit_status_endpoint_overlays_paper_gate_operator_workflow(self):
        paper_dir = Path(self.profitability_lab_dir) / "regular-options-paper-shortlist"
        forward_dir = Path(self.forward_tracking_dir)
        paper_dir.mkdir(parents=True, exist_ok=True)
        forward_dir.mkdir(parents=True, exist_ok=True)

        (paper_dir / "latest.json").write_text(
            json.dumps(
                {
                    "report_id": "regular_options_paper_shortlist",
                    "generated_at_utc": "2026-06-04T18:00:00Z",
                    "summary": {
                        "release_gate_status": "paper_review_candidates_available",
                        "eligible_count": 1,
                        "invariant_violation_count": 0,
                        "live_policy_change": False,
                    },
                    "eligible_paper_review_candidates": [
                        {
                            "symbol": "AAPL",
                            "playbook_id": "swing",
                            "bridge_status": "fresh_executable_tier_a_paper_shortlist_candidate",
                            "matched_tier_a_lanes": ["swing"],
                            "blockers": [],
                            "match_type": "lane_signature",
                            "guardrail_decision": "clear",
                            "fresh_executable_quote_window": True,
                        }
                    ],
                    "fresh_scan_non_eligible_preview": [],
                    "proof_policy": {
                        "readback_is_not": "scanner promotion or broker action",
                    },
                }
            ),
            encoding="utf8",
        )
        (forward_dir / "pending_scan_candidate_validation_latest.json").write_text(
            json.dumps(
                {
                    "report_id": "pending_scan_candidate_validation_disposition",
                    "generated_at_utc": "2026-06-04T18:01:00Z",
                    "summary": {
                        "candidate_count": 2,
                        "outcome_counts": {"proof_ineligible": 1, "no_longer_matched": 1},
                    },
                    "candidates": [
                        {
                            "candidate_key": "AAPL|swing",
                            "ticker": "AAPL",
                            "playbook_id": "swing",
                            "direction": "call",
                            "expiry": "2026-06-26",
                            "contract_symbol": "AAPL260626C00200000",
                            "outcome": "proof_ineligible",
                            "outcome_reason": "auto_track_skipped_or_missing_fill_price",
                            "fill_attempt_status": "logged",
                            "fill_status": "not_filled_auto_track_skipped",
                            "fill_outcome": "no_fill",
                            "fill_outcome_reason": "auto_track_skipped_or_missing_fill_price",
                            "auto_track_skip_reason": "proof_gate_detail_kept_for_operator_audit",
                        },
                        {
                            "candidate_key": "MSFT|swing",
                            "ticker": "MSFT",
                            "playbook_id": "swing",
                            "outcome": "no_longer_matched",
                            "outcome_reason": "candidate_not_returned_by_market_hours_validation_scan",
                        },
                    ],
                }
            ),
            encoding="utf8",
        )
        (forward_dir / "regular_options_fresh_evidence_loop_latest.json").write_text(
            json.dumps(
                {
                    "report_id": "regular_options_fresh_evidence_loop",
                    "generated_at_utc": "2026-06-04T18:02:00Z",
                    "summary": {
                        "candidate_count": 2,
                        "promotion_discussion_ready_count": 0,
                        "live_policy_change": False,
                    },
                    "candidates": [
                        {
                            "candidate_key": "AAPL|swing",
                            "ticker": "AAPL",
                            "playbook_id": "swing",
                            "validation_outcome": "proof_ineligible",
                            "entry_evidence_status": "fresh_executable_exact_entry",
                            "fill_attempt_status": "logged",
                            "fill_status": "not_filled_auto_track_skipped",
                            "fill_outcome": "no_fill",
                            "fill_outcome_reason": "auto_track_skipped_or_missing_fill_price",
                            "auto_track_skip_reason": "proof_gate_detail_kept_for_operator_audit",
                            "position_link_status": "no_tracked_or_suggested_link",
                            "realized_pnl_status": "no_position_link",
                        }
                    ],
                }
            ),
            encoding="utf8",
        )
        (forward_dir / "current_policy_circuit_breaker_latest.json").write_text(
            json.dumps(
                {
                    "report_id": "current_policy_circuit_breaker",
                    "generated_at_utc": "2026-06-04T18:03:00Z",
                    "summary": {
                        "breaker_active": True,
                        "paper_validation_only_lane_count": 1,
                        "live_policy_change": False,
                    },
                    "lane_routes": [
                        {
                            "lane_id": "short_term",
                            "route_status": "paper_validation_only",
                            "route_reason": "recovery_gates_failed",
                            "recovery_gate_failures": ["fresh_current_policy_rows"],
                            "lane_deleted": False,
                            "live_policy_change": False,
                        }
                    ],
                }
            ),
            encoding="utf8",
        )

        response = self.client.get("/api/options-profit/status")
        self.assertEqual(response.status_code, 200)
        workflow = response.json()["paper_gate_operator_workflow"]

        self.assertEqual(workflow["primary_state"], "paper_review_candidates_available")
        self.assertFalse(workflow["live_policy_change"])
        self.assertEqual(workflow["summary"]["eligible_count"], 1)
        self.assertEqual(workflow["summary"]["no_fill_or_auto_track_skipped_count"], 1)
        self.assertEqual(
            workflow["summary"]["pending_outcome_counts"],
            {"proof_ineligible": 1, "no_longer_matched": 1},
        )
        bridge_row = workflow["paper_shortlist"]["eligible_rows"][0]
        self.assertEqual(bridge_row["matched_tier_a_lanes"], ["swing"])
        self.assertEqual(bridge_row["blockers"], [])
        no_fill_row = workflow["no_fill_and_auto_track"]["rows"][0]
        self.assertIn("no executable fill price", no_fill_row["fill_discipline_explanation"])
        self.assertEqual(
            no_fill_row["auto_track_skip_reason"],
            "proof_gate_detail_kept_for_operator_audit",
        )
        self.assertEqual(
            workflow["current_policy_circuit_breaker"]["lane_routes"][0]["route_status"],
            "paper_validation_only",
        )

    def test_options_profit_status_endpoint_keeps_invariant_bad_paper_gate_fail_closed(self):
        paper_dir = Path(self.profitability_lab_dir) / "regular-options-paper-shortlist"
        forward_dir = Path(self.forward_tracking_dir)
        paper_dir.mkdir(parents=True, exist_ok=True)
        forward_dir.mkdir(parents=True, exist_ok=True)

        (paper_dir / "latest.json").write_text(
            json.dumps(
                {
                    "report_id": "regular_options_paper_shortlist",
                    "summary": {
                        "release_gate_status": "blocked_invariant_violations",
                        "eligible_count": 1,
                        "invariant_violation_count": 1,
                        "live_policy_change": False,
                    },
                    "eligible_paper_review_candidates": [{"symbol": "AAPL", "playbook_id": "swing"}],
                }
            ),
            encoding="utf8",
        )
        (forward_dir / "pending_scan_candidate_validation_latest.json").write_text(
            json.dumps({"summary": {"candidate_count": 0, "outcome_counts": {}}, "candidates": []}),
            encoding="utf8",
        )
        (forward_dir / "regular_options_fresh_evidence_loop_latest.json").write_text(
            json.dumps({"summary": {"candidate_count": 0, "live_policy_change": False}, "candidates": []}),
            encoding="utf8",
        )
        (forward_dir / "current_policy_circuit_breaker_latest.json").write_text(
            json.dumps({"summary": {"breaker_active": False, "live_policy_change": False}, "lane_routes": []}),
            encoding="utf8",
        )

        response = self.client.get("/api/options-profit/status")
        self.assertEqual(response.status_code, 200)
        workflow = response.json()["paper_gate_operator_workflow"]

        self.assertEqual(workflow["primary_state"], "paper_gate_invariant_violations")
        self.assertEqual(workflow["summary"]["eligible_count"], 1)
        self.assertEqual(workflow["summary"]["invariant_violation_count"], 1)

    def test_supervised_scan_request_defaults_portfolio_caps_on(self):
        captured: dict[str, object] = {}

        def _fake_scan(**kwargs):
            captured.update(kwargs)
            return {
                "picks": [],
                "watch_picks": [],
                "ranked_picks": [],
                "candidate_audit_picks": [],
                "playbooks": [],
                "exposure_snapshot": {"portfolio_caps_enforced": True},
            }

        with patch.object(self.backend, "run_supervised_scan", side_effect=_fake_scan):
            result = self.backend._run_supervised_scan_request({}, n_picks=2, include_policy_flags=True)

        self.assertTrue(captured["enforce_portfolio_caps"])
        self.assertEqual(result["scan_mode"], "production")

    def test_supervised_scan_request_rejects_accidental_caps_off_production_scan(self):
        with self.assertRaises(ValueError):
            self.backend._run_supervised_scan_request(
                {"enforce_portfolio_caps": False},
                n_picks=2,
                include_policy_flags=True,
            )

    def test_options_profit_status_endpoint_overlays_current_tracked_positions_health(self):
        state_dir = Path(self.options_profit_state_dir)
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "status.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-04-01T00:00:00Z",
                    "measurement_gate": {
                        "state": "blocked",
                        "blockers": [{"code": "daily_truth_refresh_failed"}],
                        "checks": {
                            "tracked_positions": {
                                "available": False,
                                "closed_position_count": 0,
                                "database_url_configured": True,
                            }
                        },
                    },
                    "blockers": [{"code": "daily_truth_refresh_failed"}],
                },
                indent=2,
            ),
            encoding="utf8",
        )

        repo = self.backend.POSITIONS_REPOSITORY
        open_pick = build_tracked_position_scan_pick(self.bundle)
        repo.create_position(
            build_position_payload(
                scan_pick=open_pick,
                fill_price=3.2,
                contracts=1,
                filled_at="2026-03-31T09:35:00",
                notes="Open position",
            )
        )
        closed_scan_pick = _proof_grade_scan_pick(open_pick)
        closed_payload = build_position_payload(
            scan_pick=closed_scan_pick,
            fill_price=3.2,
            contracts=1,
            filled_at="2026-03-30T09:35:00",
            notes="Closed proof position",
            preserve_fill_price=True,
            source_scan_lineage_verified=True,
        )
        closed_position = repo.create_position(closed_payload)
        repo.close_position(
            closed_position["id"],
            4.8,
            datetime(2026, 4, 2, 20, 0, tzinfo=UTC),
            "test_exit",
            exit_execution_basis="spread_bid_ask_exact",
        )

        response = self.client.get("/api/options-profit/status")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        tracked_check = payload["measurement_gate"]["checks"]["tracked_positions"]

        self.assertEqual(payload["measurement_gate"]["state"], "blocked")
        self.assertTrue(tracked_check["available"])
        self.assertIsNone(tracked_check["error_message"])
        self.assertEqual(tracked_check["open_position_count"], 1)
        self.assertEqual(tracked_check["total_closed_position_count"], 1)
        self.assertEqual(tracked_check["closed_position_count"], 1)
        self.assertEqual(tracked_check["runtime_source"], "positions_repository")

    def test_options_profit_status_endpoint_uses_narrow_tracked_snapshot_when_available(self):
        with patch.object(self.backend, "POSITIONS_REPOSITORY", _ProfitStatusSnapshotOnlyRepository()):
            response = self.client.get("/api/options-profit/status")

        self.assertEqual(response.status_code, 200)
        tracked_check = response.json()["measurement_gate"]["checks"]["tracked_positions"]
        self.assertTrue(tracked_check["available"])
        self.assertEqual(tracked_check["open_position_count"], 2)
        self.assertEqual(tracked_check["total_closed_position_count"], 2)
        self.assertEqual(tracked_check["closed_position_count"], 1)
        self.assertEqual(tracked_check["non_proof_closed_position_count"], 1)
        self.assertEqual(tracked_check["runtime_snapshot_source"], "positions_repository_profit_status_snapshot")

    def test_tool_endpoint_accepts_empty_body_and_decodes_json_string_results(self):
        with patch.object(
            self.backend,
            "TOOL_DISPATCH",
            {"fixture_tool": lambda: json.dumps({"ok": True, "items": [1, 2]})},
        ):
            response = self.client.post("/api/tools/fixture_tool")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"result": {"ok": True, "items": [1, 2]}})

    def test_tool_endpoint_preserves_non_json_string_results(self):
        with patch.object(
            self.backend,
            "TOOL_DISPATCH",
            {"fixture_tool": lambda: "plain text result"},
        ):
            response = self.client.post("/api/tools/fixture_tool", json={})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"result": "plain text result"})

    def test_backtest_endpoint_accepts_empty_body_and_uses_defaults(self):
        captured: dict[str, object] = {}

        def _fake_backtest(**kwargs):
            captured.update(kwargs)
            return {"ok": True, "total_trades": 0}

        with patch.object(self.backend, "run_historical_backtest", side_effect=_fake_backtest):
            response = self.client.post("/api/backtest")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "total_trades": 0})
        self.assertEqual(captured["lookback_years"], 5)
        self.assertEqual(captured["iv_adj"], 1.20)
        self.assertEqual(captured["n_picks"], self.backend.DEFAULT_SCAN_PICKS)
        self.assertEqual(captured["pricing_lane"], "pessimistic")
        self.assertIsNone(captured["truth_lane"])
        self.assertIsNone(captured["playbook"])

    def test_backtest_endpoint_rejects_bool_numeric_knobs(self):
        for payload, field in (
            ({"lookback_years": True}, "lookback_years"),
            ({"iv_adj": True}, "iv_adj"),
            ({"n_picks": True}, "n_picks"),
        ):
            with self.subTest(field=field):
                response = self.client.post("/api/backtest", json=payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json()["detail"])

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

    def test_scan_endpoint_uses_bullish_pullback_routing_fallback(self):
        captured: dict[str, object] = {}
        scan_pick = {
            "ticker": "IWM",
            "type": "daily_scan",
            "prediction_type": "daily_scan",
            "option_type": "call",
            "direction": "call",
            "direction_score": 78.0,
            "quality_score": 62.0,
            "tech_score": 54.0,
            "ev": 18.5,
            "ev_pct": 18.5,
            "dte": 34,
            "target_move_pct": 2.5,
            "stock_price": 210.0,
            "current_spot": 210.0,
            "underlying_price_at_selection": 210.0,
            "strike": 210.0,
            "short_strike": 240.0,
            "spread_width": 30.0,
            "net_debit": 3.0,
            "premium": 3.0,
            "mid": 3.0,
            "entry_execution_price": 3.0,
            "entry_execution_basis": "spread_ask_bid",
            "entry_fee_total_usd": 1.3,
            "contract_symbol": "IWM260626C00210000",
            "short_contract_symbol": "IWM260626C00240000",
            "expiry": "2026-06-26",
            "asset_class": "equity",
            "sector": "Small Cap ETF",
            "market_regime": "neutral",
            "strategy_type": "vertical_spread",
            "candidate_execution_label": "executable_opra_paper_candidate",
            "selection_source": "live_chain_exact_contract",
            "promotion_class": "promotable_exact_contract",
            "promotable": True,
            "quote_basis": "spread_ask_bid",
            "quote_time_et": "2026-05-22T15:55:00-04:00",
            "quote_time_utc": "2026-05-22T19:55:00Z",
            "original_logged_expiry": "2026-06-26",
            "resolved_listed_expiry": "2026-06-26",
            "profitability_eligibility": "eligible",
            "profitability_blockers": [],
        }

        def _scan_func(**kwargs):
            captured.update(kwargs)
            return [scan_pick]

        with patch.object(self.backend, "scan_daily_top_trades", side_effect=_scan_func):
            response = self.client.post("/api/scan", json={"n_picks": 1, "use_recommended_policy": False})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["playbook"]["id"], "bullish_pullback_observation")
        self.assertEqual(payload["playbook"]["label"], "Bullish Pullback")
        self.assertEqual(payload["playbook"]["lane_role"], "regular_peer_strategy")
        self.assertEqual(captured["symbols"], list(ss.BULLISH_PULLBACK_SCAN_TICKERS))
        self.assertEqual(captured["allowed_directions"], ["call"])
        self.assertEqual(captured["signal_variant"], "pullback_uptrend")
        self.assertEqual(payload["picks"][0]["cohort_id"], "bullish_pullback_observation")
        self.assertEqual(payload["picks"][0]["cohort_role"], "candidate")

    def test_scan_request_parsing_rejects_ambiguous_numeric_and_boolean_inputs(self):
        invalid_cases = [
            ("/api/scan", {"n_picks": True}, "n_picks"),
            ("/api/scan", {"n_picks": 1, "min_trades": True}, "min_trades"),
            ("/api/scan", {"n_picks": 1, "include_blocked_policy_picks": "sometimes"}, "include_blocked_policy_picks"),
            ("/api/scan", {"n_picks": 1, "playbook": True}, "playbook"),
            ("/api/scan/recommendations", {"n_picks": True}, "n_picks"),
            ("/api/scan/roll", {"n_picks": True}, "n_picks"),
        ]

        for path, payload, expected_field in invalid_cases:
            with self.subTest(path=path, payload=payload):
                response = self.client.post(path, json=payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn(expected_field, response.text)

    def test_scan_request_parsing_rejects_string_false_caps_off_in_production(self):
        scan_pick = {
            "ticker": "SPY",
            "type": "call",
            "prediction_type": "call",
            "direction": "call",
            "direction_score": 72.0,
            "quality_score": 74.0,
            "tech_score": 70.0,
            "ev": 10.0,
            "dte": 21,
            "strike": 650.0,
            "premium": 2.1,
            "expiry": "2026-06-26",
            "asset_class": "index",
            "sector": "Index ETF",
            "market_regime": "neutral",
        }

        with patch.object(self.backend, "scan_daily_top_trades", return_value=[scan_pick]):
            response = self.client.post(
                "/api/scan",
                json={
                    "n_picks": "1",
                    "use_recommended_policy": "false",
                    "enforce_portfolio_caps": "false",
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Caps-off scans require", response.text)

    def test_scan_endpoint_returns_sorted_normalized_contract(self):
        response = self.client.post(
            "/api/scan",
            json={"playbook": "short_term", "n_picks": 3, "use_recommended_policy": False},
        )
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
            "quote_time_utc",
            "original_logged_expiry",
            "resolved_listed_expiry",
            "entry_quote_snapshot",
            "profitability_eligibility",
            "profitability_blockers",
            "source_scan_session_id",
            "source_scan_event_key",
            "source_scan_run_id",
            "source_scan_recorded_at_utc",
        }
        for pick in picks:
            self.assertTrue(required.issubset(pick.keys()))
            self.assertEqual(pick["prediction_type"], "daily_scan")
            self.assertEqual(pick["type"], pick["direction"])
            self.assertIn(pick["type"], {"call", "put"})
            expected_fee = 1.3 if str(pick.get("strategy_type") or "").strip().lower() == "vertical_spread" else 0.65
            self.assertEqual(pick["entry_fee_total_usd"], expected_fee)
            self.assertIn(pick["profitability_eligibility"], {"eligible", "ineligible"})
            self.assertIsInstance(pick["profitability_blockers"], list)
            self.assertIsInstance(pick["entry_quote_snapshot"], dict)
            self.assertEqual(pick["entry_quote_snapshot"].get("captured_at_et"), pick["quote_time_et"])
            self.assertEqual(pick["entry_quote_snapshot"].get("captured_at_utc"), pick["quote_time_utc"])
            self.assertIsInstance(pick["source_scan_session_id"], int)
            self.assertTrue(str(pick["source_scan_event_key"]).endswith(f"rank_{pick['candidate_rank']}"))
            self.assertTrue(str(pick["source_scan_run_id"]).startswith("api_scan_"))
            self.assertTrue(str(pick["source_scan_recorded_at_utc"]).endswith("Z"))

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
        self.assertTrue(payload["forward_truth_run_id"].startswith("api_scan_"))
        self.assertTrue(payload["forward_truth_recorded_at_utc"].endswith("Z"))
        self.assertIsNone(payload["forward_truth_error"])
        self.assertEqual(payload["forward_truth_evidence_class"], "live_production")
        self.assertTrue(payload["forward_truth_authoritative"])
        self.assertTrue(all(pick["source_scan_session_id"] == payload["forward_truth_session_id"] for pick in picks))
        self.assertTrue(all(pick["source_scan_run_id"] == payload["forward_truth_run_id"] for pick in picks))
        self.assertTrue(all(pick["source_scan_recorded_at_utc"] == payload["forward_truth_recorded_at_utc"] for pick in picks))

        evidence_response = self.client.get("/api/backtest/forward-evidence")
        self.assertEqual(evidence_response.status_code, 200)
        evidence = evidence_response.json()
        self.assertEqual(evidence["source_label"], "api_scan_auto")
        self.assertEqual(evidence["recent_session_count"], 1)
        self.assertGreaterEqual(evidence["authoritative_session_count"], 0)
        self.assertGreaterEqual(evidence["scan_pick_count"], len(picks))
        self.assertGreaterEqual(evidence["eligible_scan_pick_count"], 0)
        self.assertGreaterEqual(evidence["ledger_summary"]["observation_scan_pick_count"], len(picks))
        self.assertFalse(evidence["activation_check"]["active"])
        self.assertEqual(evidence["activation_check"]["status"], "archived_forward_unavailable")
        self.assertEqual(evidence["forward_truth_recording_failure_count"], 0)
        self.assertEqual(evidence["exact_contract_capture_counts"]["with_contract_count"], 0)
        self.assertGreaterEqual(evidence["exact_contract_capture_counts"]["all_with_contract_count"], 1)

        proof_response = self.client.get("/api/proof-summary")
        self.assertEqual(proof_response.status_code, 200)
        proof_counts = proof_response.json()["evidence_counts"]
        self.assertGreaterEqual(proof_counts["forward_event_count"], len(picks))
        self.assertGreaterEqual(proof_counts["scan_pick_event_count"], len(picks))

    def test_position_created_from_scan_pick_preserves_live_scan_provenance(self):
        scan_response = self.client.post(
            "/api/scan",
            json={"playbook": "short_term", "n_picks": 2, "use_recommended_policy": False},
        )
        self.assertEqual(scan_response.status_code, 200)
        scan_payload = scan_response.json()
        scan_pick = scan_payload["picks"][0]
        self.assertIsNotNone(scan_pick["source_scan_session_id"])
        self.assertIsNotNone(scan_pick["source_scan_event_key"])

        scanner_response = self.client.post(
            "/api/positions",
            json={
                "scan_pick": scan_pick,
                "fill_price": scan_pick["entry_execution_price"],
                "contracts": 1,
            },
        )
        self.assertEqual(scanner_response.status_code, 409)
        self.assertIn("candidate_execution_label:fallback_delayed", str(scanner_response.json()["detail"]))

        create_response = self.client.post(
            "/api/positions",
            json={
                "creation_mode": "manual_paper",
                "scan_pick": scan_pick,
                "fill_price": scan_pick["entry_execution_price"],
                "contracts": 1,
            },
        )
        self.assertEqual(create_response.status_code, 200)
        position = create_response.json()["position"]
        self.assertEqual(position["source_scan_session_id"], scan_payload["forward_truth_session_id"])
        self.assertEqual(position["source_scan_event_key"], scan_pick["source_scan_event_key"])
        self.assertEqual(position["source_scan_run_id"], scan_payload["forward_truth_run_id"])
        self.assertEqual(position["source_scan_recorded_at_utc"], scan_payload["forward_truth_recorded_at_utc"])
        self.assertEqual(
            position["source_pick_snapshot"]["source_scan_session_id"],
            scan_payload["forward_truth_session_id"],
        )
        self.assertEqual(
            position["source_pick_snapshot"]["source_scan_event_key"],
            scan_pick["source_scan_event_key"],
        )
        self.assertEqual(
            position["source_pick_snapshot"]["source_scan_run_id"],
            scan_payload["forward_truth_run_id"],
        )
        self.assertEqual(
            position["source_pick_snapshot"]["source_scan_recorded_at_utc"],
            scan_payload["forward_truth_recorded_at_utc"],
        )
        self.assertTrue(position["source_pick_snapshot"]["source_scan_lineage_verified"])
        self.assertNotIn("source_scan_lineage_unverified", position["proof_ineligibility_reason"] or "")

    def test_mutated_scanner_origin_scan_pick_entry_price_rejects_unverified_lineage(self):
        scan_response = self.client.post(
            "/api/scan",
            json={"playbook": "short_term", "n_picks": 2, "use_recommended_policy": False},
        )
        self.assertEqual(scan_response.status_code, 200)
        scan_pick = dict(scan_response.json()["picks"][0])
        self.assertIsNotNone(scan_pick["source_scan_session_id"])
        original_price = float(scan_pick["entry_execution_price"])
        scan_pick["entry_execution_price"] = round(original_price + 0.25, 4)

        create_response = self.client.post(
            "/api/positions",
            json={
                "scan_pick": scan_pick,
                "fill_price": scan_pick["entry_execution_price"],
                "contracts": 1,
            },
        )

        self.assertEqual(create_response.status_code, 409)
        self.assertIn("source_scan_lineage_unverified", str(create_response.json()["detail"]))

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
            response = self.client.post(
                "/api/scan",
                json={"playbook": "short_term", "n_picks": 2, "use_recommended_policy": False},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        picks = payload["picks"]
        self.assertGreaterEqual(len(picks), 1)
        self.assertTrue(all(pick["calibrated_expectancy_pct"] is not None for pick in picks))
        self.assertTrue(all(pick["expectancy_selection_source"] == "replay_calibrated" for pick in picks))
        self.assertEqual(picks, sorted(picks, key=oc._candidate_rank_tuple, reverse=True))

    def test_scan_endpoint_records_bootstrap_expectancy_source_when_dense_calibration_is_missing(self):
        response = self.client.post(
            "/api/scan",
            json={"playbook": "short_term", "n_picks": 2, "use_recommended_policy": False},
        )
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

    def test_scan_playbook_guardrails_warn_when_positions_storage_is_unavailable(self):
        unavailable = UnavailableTrackedPositionsRepository("tracked positions unavailable")
        with patch.object(self.backend, "POSITIONS_REPOSITORY", unavailable):
            response = self.client.post(
                "/api/scan",
                json={
                    "n_picks": 3,
                    "playbook": "short_term",
                    "use_recommended_policy": False,
                    "enforce_portfolio_caps": True,
                    "include_blocked_guardrail_picks": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["picks"])
        self.assertFalse(payload["exposure_snapshot"]["available"])
        self.assertEqual(payload["guardrail_decision_counts"], {"clear": 0, "caution": 1, "blocked": 1})
        aaa_pick = next(pick for pick in payload["picks"] if pick["ticker"] == "AAA")
        self.assertEqual(aaa_pick["guardrail_decision"], "caution")
        self.assertNotEqual(aaa_pick["suggested_size_tier"], "blocked")
        self.assertTrue(any("storage" in reason.lower() for reason in aaa_pick["guardrail_reasons"]))
        spy_pick = next(pick for pick in payload["picks"] if pick["ticker"] == "SPY")
        self.assertEqual(spy_pick["guardrail_decision"], "blocked")
        self.assertTrue(any("quarantined" in reason.lower() for reason in spy_pick["guardrail_reasons"]))

    def test_scan_endpoint_fail_open_when_forward_truth_recording_fails(self):
        with patch.object(self.backend, "record_forward_snapshot", side_effect=RuntimeError("ledger down")):
            response = self.client.post(
                "/api/scan",
                json={"playbook": "short_term", "n_picks": 2, "use_recommended_policy": False},
            )

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
        eligible_pick = build_tracked_position_scan_pick(self.bundle)
        eligible_pick.update(
            {
                "policy_decision": "approved",
                "guardrail_decision": "clear",
                "profitability_eligibility": "eligible",
                "profitability_blockers": [],
                "selection_source": "live_chain_exact_contract",
                "entry_execution_basis": "spread_ask_bid",
                "entry_execution_price": 2.4,
                "quote_basis": "spread_ask_bid",
                "quote_freshness_status": "fresh",
                "options_data_source": "alpaca_opra",
                "bid": 2.35,
                "ask": 2.4,
                "short_bid": 0.9,
                "short_ask": 0.95,
                "long_leg": {
                    "contract_symbol": eligible_pick.get("contract_symbol"),
                    "bid": 2.35,
                    "ask": 2.4,
                    "data_source": "alpaca_opra",
                },
                "short_leg": {
                    "contract_symbol": eligible_pick.get("short_contract_symbol"),
                    "bid": 0.9,
                    "ask": 0.95,
                    "data_source": "alpaca_opra",
                },
            }
        )
        eligible_scan_result = {
            "picks": [eligible_pick],
            "watch_picks": [],
            "ranked_picks": [eligible_pick],
            "policy_applied": True,
            "policy": {
                "truth_source": "historical_imported_daily",
                "promotion_status": "observed",
            },
            "playbook": {"id": "short_term"},
            "truth_lane": "historical_imported_daily",
            "candidate_count": 1,
            "returned_count": 1,
            "scan_funnel": {
                "raw_candidates": 1,
                "post_policy_visible": 1,
                "post_guardrails_visible": 1,
                "returned_picks": 1,
                "policy_filtered_out": 0,
                "guardrail_filtered_out": 0,
                "final_trimmed": 0,
            },
            "policy_decision_counts": {"approved": 1},
            "guardrail_decision_counts": {"clear": 1},
        }
        with patch.object(self.backend, "run_supervised_scan", return_value=eligible_scan_result):
            first = self.client.post(
                "/api/scan",
                json={"playbook": "short_term", "n_picks": 2, "use_recommended_policy": True},
            )
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
            "archived_forward_unavailable",
        )
        self.assertFalse(evidence["activation_check"]["historical_evidence_available"])
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

    def test_sector_endpoint_marks_missing_etf_data_unavailable(self):
        sector_symbols = ["XLK", "XLV", "XLF", "XLE", "XLY", "XLP", "XLI", "XLB", "XLRE", "XLU", "XLC"]
        close_frame = pd.DataFrame(
            {
                symbol: make_history(length=820, start=50.0 + idx * 5.0, step=0.15, wave=1.0)["Close"]
                for idx, symbol in enumerate(sector_symbols, start=1)
                if symbol != "XLV"
            }
        )

        with patch.object(self.backend, "_md_download_history_batch", return_value={"Close": close_frame}):
            response = self.client.get("/api/sectors")

        self.assertEqual(response.status_code, 200)
        rows = {row["etf"]: row for row in response.json()}
        self.assertEqual(rows["XLV"]["data_status"], "unavailable")
        self.assertEqual(rows["XLV"]["near_sent"], "Unavailable")
        self.assertIsNone(rows["XLV"]["near_ret"])
        self.assertNotEqual(rows["XLV"]["near_sent"], "Neutral")

    def test_sector_endpoint_marks_short_history_windows_partial(self):
        sector_symbols = ["XLK", "XLV", "XLF", "XLE", "XLY", "XLP", "XLI", "XLB", "XLRE", "XLU", "XLC"]
        close_frame = pd.DataFrame(
            {
                symbol: make_history(length=40, start=50.0 + idx * 5.0, step=0.15, wave=1.0)["Close"]
                for idx, symbol in enumerate(sector_symbols, start=1)
            }
        )

        with patch.object(self.backend, "_md_download_history_batch", return_value={"Close": close_frame}):
            response = self.client.get("/api/sectors")

        self.assertEqual(response.status_code, 200)
        rows = {row["etf"]: row for row in response.json()}
        self.assertEqual(rows["XLK"]["data_status"], "partial")
        self.assertNotEqual(rows["XLK"]["near_sent"], "Unavailable")
        self.assertEqual(rows["XLK"]["med_sent"], "Unavailable")
        self.assertIsNone(rows["XLK"]["med_ret"])
        self.assertEqual(rows["XLK"]["long_sent"], "Unavailable")
        self.assertIsNone(rows["XLK"]["long_ret"])

    def test_market_data_cache_stats_endpoint_reports_and_resets_counters(self):
        sector_tickers = {}
        batch_frames = {}
        for idx, symbol in enumerate(["XLK", "XLV", "XLF", "XLE", "XLY", "XLP", "XLI", "XLB", "XLRE", "XLU", "XLC"], start=1):
            history_frame = make_history(length=820, start=45.0 + idx * 4.0, step=0.1, wave=0.6, volume=9_000_000)
            batch_frames[symbol] = history_frame

            class _SectorTicker:
                def __init__(self, frame: pd.DataFrame):
                    self.frame = frame

                def history(self, period=None, start=None, end=None, interval=None):
                    return self.frame

            sector_tickers[symbol] = _SectorTicker(history_frame)

        batch_download = pd.concat(batch_frames, axis=1)
        with patch.object(mds.yf, "Ticker", side_effect=lambda symbol: sector_tickers[symbol]), \
             patch.object(mds.yf, "download", return_value=batch_download), \
             patch.object(mds, "_recent_refresh_start", return_value=FrozenDateTime.now().date() + mds.timedelta(days=365)):
            sectors_response = self.client.get("/api/sectors")
            self.assertEqual(sectors_response.status_code, 200)

            stats_response = self.client.get("/api/market-data/cache-stats")
            self.assertEqual(stats_response.status_code, 200)
            payload = stats_response.json()
            self.assertIn("stats", payload)
            self.assertIn("totals", payload)
            self.assertGreaterEqual(payload["stats"]["download_history_batch"]["cache_hits"], 1)
            self.assertEqual(payload["stats"]["download_history_batch"]["batch_network_fetches"], 1)
            history_stats = payload["stats"].get("history", {})
            self.assertEqual(history_stats.get("persistent_misses"), 11)
            self.assertEqual(history_stats.get("full_refreshes"), 11)
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

    def test_scan_playbook_guardrails_warn_duplicate_ticker_exposure(self):
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
                    "enforce_portfolio_caps": True,
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
        self.assertEqual(aaa_pick["guardrail_decision"], "caution")
        self.assertNotEqual(aaa_pick["suggested_size_tier"], "blocked")
        self.assertTrue(aaa_pick["guardrail_reasons"])

    def test_scan_keeps_portfolio_caution_top_pick(self):
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
                "ticker": "BBB",
                "direction": "call",
                "asset_class": "equity",
                "sector": "Healthcare",
                "direction_score": 68.0,
                "quality_score": 74.0,
                "contract_symbol": "BBB260408C00462590",
                "short_contract_symbol": "BBB260408C00467590",
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
                    "enforce_portfolio_caps": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["returned_count"], 1)
        self.assertEqual(payload["scan_funnel"]["guardrail_filtered_out"], 0)
        self.assertEqual(payload["picks"][0]["ticker"], "AAA")
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
                    "playbook": "short_term",
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

    def test_speculative_playbook_keeps_its_own_candidate_cohort(self):
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
        self.assertFalse(picks["SPY"].get("observation_only", False))
        self.assertTrue(picks["SPY"]["speculative_flag"])
        self.assertEqual(picks["SPY"]["convexity_class"], "speculative")
        self.assertGreaterEqual(picks["SPY"]["risk_tier"], 4)
        self.assertGreaterEqual(picks["SPY"]["upside_tier"], 4)
        self.assertEqual(picks["SPY"]["profit_candidate_id"], "SPY__call__speculative_short_dte")
        self.assertEqual(picks["SPY"]["policy_artifact_id"], "SPY__call__speculative_short_dte")
        self.assertEqual(picks["SPY"]["cohort_id"], "speculative_short_dte")
        self.assertEqual(picks["SPY"]["cohort_role"], "candidate")
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

        roll_response = self.client.post("/api/scan/roll", json={"n_picks": 3, "use_recommended_policy": True})
        self.assertEqual(roll_response.status_code, 200)
        self.assertTrue(roll_response.json()["policy_fail_closed"])

        recommendations_response = self.client.post(
            "/api/scan/recommendations",
            json={"n_picks": 3, "use_recommended_policy": True},
        )
        self.assertEqual(recommendations_response.status_code, 200)
        self.assertTrue(recommendations_response.json()["policy_fail_closed"])

        exit_audit_response = self.client.get("/api/backtest/exit-audit", params={"playbook": "short_term", "min_trades": 1})
        self.assertEqual(exit_audit_response.status_code, 200)
        self.assertEqual(exit_audit_response.json(), {"error": "No backtest results found"})

    def test_secondary_scan_routes_return_success_payloads_with_policy_context(self):
        pending_pick = {
            **build_tracked_position_scan_pick(self.bundle),
            "ticker": "OLD",
            "type": "daily_scan",
            "prediction_type": "daily_scan",
            "option_type": "call",
            "direction": "call",
            "direction_score": 20.0,
            "quality_score": 20.0,
            "outcome": None,
            "current_pnl_pct": 0.0,
        }
        replacement_pick = {
            **build_tracked_position_scan_pick(self.bundle),
            "ticker": "AAA",
            "type": "daily_scan",
            "prediction_type": "daily_scan",
            "option_type": "call",
            "direction": "call",
            "direction_score": 82.0,
            "quality_score": 82.0,
            "entry_date": "2026-05-22",
        }
        new_pick = {
            **build_tracked_position_scan_pick(self.bundle),
            "ticker": "BBB",
            "type": "daily_scan",
            "prediction_type": "daily_scan",
            "option_type": "put",
            "direction": "put",
            "direction_score": 76.0,
            "quality_score": 76.0,
            "entry_date": "2026-05-22",
        }
        pending = [pending_pick]
        supervised_scan_result = {
            "picks": [replacement_pick, new_pick],
            "watch_picks": [],
            "ranked_picks": [replacement_pick, new_pick],
            "policy_applied": False,
            "policy": {},
            "playbook": {"id": "short_term"},
            "truth_lane": "synthetic",
            "candidate_count": 2,
            "returned_count": 2,
            "scan_funnel": {
                "raw_candidates": 2,
                "post_policy_visible": 2,
                "post_guardrails_visible": 2,
                "returned_picks": 2,
                "policy_filtered_out": 0,
                "guardrail_filtered_out": 0,
                "final_trimmed": 0,
            },
            "policy_decision_counts": {},
            "guardrail_decision_counts": {},
        }

        backtest_response = self.client.post(
            "/api/backtest",
            json={"lookback_years": 1, "iv_adj": 1.2, "truth_lane": "synthetic"},
        )
        self.assertEqual(backtest_response.status_code, 200)

        with patch.object(self.backend, "_load_predictions", return_value=pending), \
             patch.object(self.backend, "_run_supervised_scan_request", return_value=supervised_scan_result):
            roll_response = self.client.post(
                "/api/scan/roll",
                json={"n_picks": 3, "use_recommended_policy": False, "min_trades": 1, "truth_lane": "synthetic"},
            )
            recommendations_response = self.client.post(
                "/api/scan/recommendations",
                json={"n_picks": 3, "use_recommended_policy": False, "min_trades": 1, "truth_lane": "synthetic"},
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
        normalized_roll_picks = roll_payload["rolled"] + roll_payload["new"] + roll_payload["dropped"]
        self.assertTrue(normalized_roll_picks)
        for pick in normalized_roll_picks:
            self.assertEqual(pick["prediction_type"], "daily_scan")
            self.assertIn(pick["type"], {"call", "put"})

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
        normalized_recommendation_picks = list(rec_payload["new_opportunities"])
        normalized_recommendation_picks.extend(
            item["replace_with"]
            for item in rec_payload["active_positions"]
            if isinstance(item.get("replace_with"), dict)
        )
        self.assertTrue(normalized_recommendation_picks)
        for pick in normalized_recommendation_picks:
            self.assertEqual(pick["prediction_type"], "daily_scan")
            self.assertIn(pick["type"], {"call", "put"})

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
            json={"playbook": "short_term", "n_picks": 3, "use_recommended_policy": False},
        )
        self.assertEqual(scan_response.status_code, 200)
        scan = scan_response.json()

        self.assertEqual(backtest["total_trades"], 137)
        self.assertEqual(backtest["selection_source_counts"], {"bootstrap_heuristic": 137})
        self.assertEqual(round(backtest["profit_factor"], 2), 0.70)
        self.assertEqual(policy["scan_policy"]["promotion_status"], "block")
        self.assertEqual(len(scan["picks"]), 1)
        self.assertEqual(scan["returned_count"], 1)
        self.assertEqual(scan["candidate_count"], 2)
        self.assertEqual(
            {
                "raw_candidates": scan["scan_funnel"]["raw_candidates"],
                "post_policy_visible": scan["scan_funnel"]["post_policy_visible"],
                "post_guardrails_visible": scan["scan_funnel"]["post_guardrails_visible"],
                "returned_picks": scan["scan_funnel"]["returned_picks"],
                "guardrail_filtered_out": scan["scan_funnel"]["guardrail_filtered_out"],
                "include_blocked_guardrail_picks": scan["scan_funnel"]["include_blocked_guardrail_picks"],
            },
            {
                "raw_candidates": 2,
                "post_policy_visible": 2,
                "post_guardrails_visible": 1,
                "returned_picks": 1,
                "guardrail_filtered_out": 1,
                "include_blocked_guardrail_picks": False,
            },
        )
        self.assertEqual(scan["guardrail_decision_counts"], {"clear": 1, "caution": 0, "blocked": 1})

        top_pick = scan["picks"][0]
        self.assertEqual(top_pick["ticker"], "AAA")
        self.assertEqual(top_pick["type"], "call")
        self.assertEqual(top_pick["direction_score"], 61.6)
        self.assertEqual(top_pick["quality_score"], 79.2)
        self.assertIsNone(top_pick["calibrated_expectancy_pct"])
        self.assertEqual(top_pick["promotion_class"], "research_bootstrap")
        self.assertEqual(top_pick["selection_source"], "live_chain_exact_contract")


if __name__ == "__main__":
    unittest.main()
