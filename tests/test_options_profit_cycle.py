from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import options_chatbot as oc
from options_profit_flywheel import _candidate_position_metrics, run_options_profit_cycle
from options_profit_state import (
    ensure_options_profit_state,
    live_profile_path,
    load_incumbents_state,
    load_live_profile_state,
    load_profit_status,
    save_incumbents_state,
    save_live_profile_state,
)
from workspace_tempdir import WorkspaceTempDir


class OptionsProfitCycleTests(unittest.TestCase):
    def setUp(self):
        self._tmp = WorkspaceTempDir(prefix="options-profit-cycle")
        self.addCleanup(self._tmp.cleanup)
        self.state_dir = os.path.join(self._tmp.name, "options_profit")
        self.forward_db_path = os.path.join(self._tmp.name, "forward_tracking.db")
        self.env = patch.dict(
            os.environ,
            {
                "OPTIONS_PROFIT_STATE_DIR": self.state_dir,
                "FORWARD_OPTIONS_LEDGER_DB_PATH": self.forward_db_path,
                "FORWARD_OPTIONS_AUTHORITATIVE_LEDGER_DB_PATH": self.forward_db_path,
                "OPTIONS_DAILY_TRUTH_AUTO_REFRESH": "0",
            },
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def _live_proof_position(
        self,
        *,
        ticker: str = "SPY",
        direction: str = "call",
        candidate_id: str = "candidate-1",
        contract_symbol: str = "SPY240101C00500000",
        **overrides,
    ) -> dict:
        source = {
            "profit_candidate_id": candidate_id,
            "selection_source": "live_chain_exact_contract",
            "options_data_source": "alpaca_opra",
            "quote_time_et": "2026-04-01T10:00:00-04:00",
            "quote_freshness_status": "fresh",
            "entry_execution_price": 1.0,
            "entry_execution_basis": "ask",
            "source_scan_lineage_verified": True,
        }
        source.update(overrides.pop("source_pick_snapshot", {}))
        row = {
            "status": "closed",
            "ticker": ticker,
            "direction": direction,
            "contract_symbol": contract_symbol,
            "proof_eligible": True,
            "proof_class": "live_scan_exact_contract",
            "entry_execution_price": 1.0,
            "entry_execution_basis": "ask",
            "exit_execution_price": 1.5,
            "exit_execution_basis": "spread_bid_ask_exact",
            "source_scan_session_id": 101,
            "source_scan_event_key": "short_term:rank_1",
            "source_scan_run_id": "api_scan_20260401T140000Z",
            "source_scan_recorded_at_utc": "2026-04-01T14:00:00Z",
            "source_pick_snapshot": source,
        }
        row.update(overrides)
        return row

    def _write_promoted_replay_policy(self) -> str:
        path = Path(self._tmp.name) / "promoted_replay_policy.json"
        path.write_text(
            json.dumps(
                {
                    "promotion_status": "promote",
                    "overall": {
                        "profit_factor": 2.0,
                        "directional_accuracy_pct": 72.0,
                    },
                    "source": {"quote_coverage_pct": 99.0},
                    "stability": {
                        "overall_status": "promote",
                        "quality_bar": {"min_trades": 25},
                    },
                },
                indent=2,
            ),
            encoding="utf8",
        )
        return str(path)

    def _forward_event(
        self,
        *,
        ticker: str = "SPY",
        direction: str = "call",
        cohort_id: str = "broad_ev7",
        net_pnl_pct: float = 5.0,
    ) -> dict:
        return {
            "ticker": ticker,
            "direction": direction,
            "option_type": direction,
            "cohort_id": cohort_id,
            "evidence_class": "live_production",
            "eligibility_status": "eligible",
            "net_pnl_pct": net_pnl_pct,
        }

    def _install_canary(
        self,
        *,
        candidate_id: str = "SPY__call__broad_ev7",
        baseline_objective: dict | None = None,
        required_outcomes: int = 1,
    ) -> None:
        ensure_options_profit_state()
        live_profile = load_live_profile_state(refresh=True)
        live_profile["symbols"]["SPY"]["call"].update(
            {
                "candidate_id": candidate_id,
                "cohort_id": "broad_ev7",
                "mode": "canary",
                "status": "candidate",
                "source": "test_canary",
            }
        )
        save_live_profile_state(live_profile)

        incumbents = load_incumbents_state()
        incumbents["symbols"]["SPY"]["call"] = {
            "symbol": "SPY",
            "direction": "call",
            "active": dict(live_profile["symbols"]["SPY"]["call"]),
            "previous": {
                "symbol": "SPY",
                "direction": "call",
                "candidate_id": "SPY__call__baseline_broad_control",
                "cohort_id": "baseline_broad_control",
                "base_profile": "index",
                "overrides": {},
                "manifest_source": None,
                "source": "bootstrap_default",
                "mode": "incumbent",
                "status": "incumbent",
                "applied_at": "2026-04-01T00:00:00Z",
            },
            "canary": {
                "candidate_id": candidate_id,
                "symbol": "SPY",
                "direction": "call",
                "required_outcomes": required_outcomes,
                "baseline_objective": baseline_objective or {"objective_score": -100.0},
            },
            "objective": {"objective_score": 0.0},
        }
        save_incumbents_state(incumbents)

    def test_candidate_position_metrics_fee_aware_fallback_for_missing_net_pnl(self):
        metrics = _candidate_position_metrics(
            "SPY",
            "call",
            "candidate-1",
            [
                self._live_proof_position(
                    entry_execution_price=1.0,
                    exit_execution_price=1.01,
                    contracts=1,
                    fee_total_usd=2.60,
                    source_pick_snapshot={"entry_execution_price": 1.0},
                )
            ],
        )

        self.assertEqual(metrics["closed_position_count"], 1)
        self.assertEqual(metrics["exact_outcome_count"], 1)
        self.assertEqual(metrics["avg_net_pnl_pct"], -1.5595)
        self.assertEqual(metrics["profit_factor"], 0.0)

    def test_candidate_position_metrics_excludes_missing_proof_eligible_rows(self):
        metrics = _candidate_position_metrics(
            "SPY",
            "call",
            "candidate-1",
            [
                {
                    "ticker": "SPY",
                    "direction": "call",
                    "contract_symbol": "SPY240101C00500000",
                    "net_pnl_pct": -99.0,
                    "source_pick_snapshot": {"profit_candidate_id": "candidate-1"},
                },
                self._live_proof_position(
                    contract_symbol="SPY240101C00510000",
                    net_pnl_pct=15.0,
                ),
            ],
        )

        self.assertEqual(metrics["closed_position_count"], 1)
        self.assertEqual(metrics["exact_outcome_count"], 1)
        self.assertEqual(metrics["avg_net_pnl_pct"], 15.0)

    def test_candidate_position_metrics_excludes_non_proof_rows_and_scores_all_winners(self):
        metrics = _candidate_position_metrics(
            "SPY",
            "call",
            "candidate-1",
            [
                {
                    "ticker": "SPY",
                    "direction": "call",
                    "contract_symbol": "SPY240101C00500000",
                    "proof_eligible": False,
                    "net_pnl_pct": -99.0,
                    "source_pick_snapshot": {"profit_candidate_id": "candidate-1"},
                },
                self._live_proof_position(
                    contract_symbol="SPY240101C00510000",
                    net_pnl_pct=15.0,
                ),
            ],
        )

        self.assertEqual(metrics["closed_position_count"], 1)
        self.assertEqual(metrics["exact_outcome_count"], 1)
        self.assertEqual(metrics["profit_factor"], 999.0)

    def test_candidate_position_metrics_excludes_non_opra_proof_flag_rows(self):
        metrics = _candidate_position_metrics(
            "SPY",
            "call",
            "candidate-1",
            [
                {
                    "ticker": "SPY",
                    "direction": "call",
                    "contract_symbol": "SPY240101C00500000",
                    "proof_eligible": True,
                    "proof_class": "live_scan_exact_contract",
                    "source_label": "non_opra_vendor",
                    "net_pnl_pct": 99.0,
                    "source_pick_snapshot": {"profit_candidate_id": "candidate-1"},
                },
                self._live_proof_position(
                    contract_symbol="SPY240101C00510000",
                    net_pnl_pct=-5.0,
                ),
            ],
        )

        self.assertEqual(metrics["closed_position_count"], 1)
        self.assertEqual(metrics["exact_outcome_count"], 1)
        self.assertEqual(metrics["avg_net_pnl_pct"], -5.0)

    def test_candidate_position_metrics_requires_explicit_opra_provenance(self):
        metrics = _candidate_position_metrics(
            "SPY",
            "call",
            "candidate-1",
            [
                {
                    "ticker": "SPY",
                    "direction": "call",
                    "contract_symbol": "SPY240101C00500000",
                    "proof_eligible": True,
                    "net_pnl_pct": 99.0,
                    "source_pick_snapshot": {"profit_candidate_id": "candidate-1"},
                }
            ],
        )

        self.assertEqual(metrics["closed_position_count"], 0)
        self.assertEqual(metrics["exact_outcome_count"], 0)

    def test_live_profile_overlay_applies_only_to_target_symbol(self):
        ensure_options_profit_state()
        current = load_live_profile_state(refresh=True)
        current["symbols"]["SPY"]["call"]["overrides"] = {
            "entry": {"min_tech_score": 91.0},
            "filters": {"min_calibrated_expectancy_pct": 11.0},
        }
        save_live_profile_state(current)

        spy_call_profile = oc._get_profile("SPY", "call")
        spy_put_profile = oc._get_profile("SPY", "put")
        neutral_spy_profile = oc._get_profile("SPY")
        qqq_call_profile = oc._get_profile("QQQ", "call")

        self.assertEqual(spy_call_profile["entry"]["min_tech_score"], 91.0)
        self.assertEqual(spy_call_profile["filters"]["min_calibrated_expectancy_pct"], 11.0)
        self.assertNotEqual(spy_put_profile["entry"]["min_tech_score"], 91.0)
        self.assertNotEqual(neutral_spy_profile["entry"]["min_tech_score"], 91.0)
        self.assertNotEqual(qqq_call_profile["entry"]["min_tech_score"], 91.0)

    def test_profit_cycle_bootstraps_and_records_read_only_when_gate_is_unhealthy(self):
        result = run_options_profit_cycle()

        self.assertEqual(result["decision"]["action"], "no_op")
        self.assertTrue(str(result["decision"].get("reason") or "").startswith("measurement_gate_"))
        status = load_profit_status()
        self.assertIn(status["measurement_gate"]["state"], {"blocked", "pending_truth", "degraded-watch"})
        self.assertTrue(Path(live_profile_path()).exists())
        incumbents = load_incumbents_state()
        self.assertIn("SPY", incumbents["symbols"])
        self.assertIn("QQQ", incumbents["symbols"])

    def test_profit_cycle_keeps_put_challenger_shadow_only(self):
        ensure_options_profit_state()
        shadow_candidate = {
            "candidate_id": "QQQ__put__shadow_winner",
            "symbol": "QQQ",
            "direction": "put",
            "base_profile": "index",
            "overrides": {"entry": {"min_tech_score": 88.0}},
            "evaluation": {
                "replay_gate": {"passes": True, "promotion_status": "promote", "stability_status": "promote"},
                "forward_exact_contract": {
                    "eligible_trade_count": 30,
                    "avg_pnl_pct": 12.0,
                    "avg_net_pnl_pct": 11.4,
                    "profit_factor": 1.5,
                    "net_profit_factor": 1.45,
                },
                "tracked_realized": {
                    "closed_position_count": 4,
                    "avg_pnl_pct": 8.0,
                    "avg_net_pnl_pct": 7.2,
                    "profit_factor": 1.3,
                    "net_profit_factor": 1.25,
                },
            },
        }

        with patch("options_profit_flywheel._require_daily_truth_refresh", return_value={"status": "refreshed", "commands": []}), \
             patch("options_profit_flywheel.evaluate_measurement_gate", return_value={"state": "healthy", "blockers": [], "checks": {}}), \
             patch("options_profit_flywheel.list_candidate_manifests", return_value=[shadow_candidate]), \
             patch("options_profit_flywheel._load_closed_positions", return_value=[]):
            result = run_options_profit_cycle()

        self.assertEqual(result["decision"]["action"], "no_op")
        self.assertEqual(result["decision"]["reason"], "no_eligible_symbol_side_challenger")
        ranking = result["status"]["candidate_rankings"][0]
        self.assertEqual(ranking["symbol"], "QQQ")
        self.assertEqual(ranking["direction"], "put")
        self.assertFalse(ranking["eligible"])
        self.assertIn("shadow_only_side", ranking["blockers"])

    def test_profit_cycle_derives_candidate_evaluation_from_policy_forward_and_positions(self):
        candidate_id = "SPY__call__broad_ev7"
        candidate = {
            "candidate_id": candidate_id,
            "symbol": "SPY",
            "direction": "call",
            "cohort_id": "broad_ev7",
            "base_profile": "index",
            "overrides": {"entry": {"min_tech_score": 72.0}},
            "replay_policy_path": self._write_promoted_replay_policy(),
        }
        forward_events = [
            self._forward_event(cohort_id="broad_ev7", net_pnl_pct=5.0)
            for _ in range(30)
        ]
        closed_positions = [
            self._live_proof_position(
                ticker="SPY",
                direction="call",
                candidate_id=candidate_id,
                contract_symbol=f"SPY260417C005{i:05d}",
                net_pnl_pct=5.0,
            )
            for i in range(10)
        ]
        healthy_gate = {
            "state": "healthy",
            "blockers": [],
            "checks": {},
            "eligible_forward_evidence": forward_events,
        }

        with patch("options_profit_flywheel._require_daily_truth_refresh", return_value={"status": "refreshed", "commands": []}), \
             patch("options_profit_flywheel.evaluate_measurement_gate", return_value=healthy_gate), \
             patch("options_profit_flywheel.list_candidate_manifests", return_value=[candidate]), \
             patch("options_profit_flywheel._load_closed_positions", return_value=closed_positions):
            apply_result = run_options_profit_cycle()

        self.assertEqual(apply_result["decision"]["action"], "apply_candidates")
        ranking = apply_result["status"]["candidate_rankings"][0]
        self.assertTrue(ranking["eligible"])
        self.assertNotIn("replay_gate_failed", ranking["blockers"])
        self.assertNotIn("insufficient_exact_forward_support", ranking["blockers"])
        self.assertNotIn("missing_tracked_realized_support", ranking["blockers"])

        with patch("options_profit_flywheel._require_daily_truth_refresh", return_value={"status": "refreshed", "commands": []}), \
             patch("options_profit_flywheel.evaluate_measurement_gate", return_value=healthy_gate), \
             patch("options_profit_flywheel.list_candidate_manifests", return_value=[]), \
             patch("options_profit_flywheel._load_closed_positions", return_value=closed_positions):
            finalize_result = run_options_profit_cycle()

        self.assertTrue(any(action.get("action") == "finalize_canary" for action in finalize_result["canary_actions"]))
        refreshed_status = load_profit_status()
        self.assertIsNone(refreshed_status["current_canary"]["SPY"]["call"])
        self.assertEqual(refreshed_status["active_incumbents"]["SPY"]["call"]["candidate_id"], candidate_id)

    def test_canary_pending_truth_holds_instead_of_rolling_back(self):
        candidate_id = "SPY__call__broad_ev7"
        self._install_canary(candidate_id=candidate_id, required_outcomes=1)
        closed_positions = [
            self._live_proof_position(
                ticker="SPY",
                direction="call",
                candidate_id=candidate_id,
                contract_symbol="SPY260417C00500000",
                net_pnl_pct=15.0,
            )
        ]

        with patch("options_profit_flywheel._require_daily_truth_refresh", return_value={"status": "refreshed", "commands": []}), \
             patch("options_profit_flywheel.evaluate_measurement_gate", return_value={"state": "pending_truth", "blockers": [], "checks": {}}), \
             patch("options_profit_flywheel.list_candidate_manifests", return_value=[]), \
             patch("options_profit_flywheel._load_closed_positions", return_value=closed_positions):
            result = run_options_profit_cycle()

        self.assertTrue(any(action.get("action") == "canary_hold" for action in result["canary_actions"]))
        self.assertFalse(any(action.get("action") == "rollback_canary" for action in result["canary_actions"]))
        refreshed_status = load_profit_status()
        self.assertEqual(refreshed_status["current_canary"]["SPY"]["call"]["candidate_id"], candidate_id)
        self.assertEqual(refreshed_status["active_incumbents"]["SPY"]["call"]["mode"], "canary")

    def test_canary_compares_tracked_only_scores_when_observed_forward_metrics_are_absent(self):
        candidate_id = "SPY__call__broad_ev7"
        self._install_canary(
            candidate_id=candidate_id,
            required_outcomes=2,
            baseline_objective={
                "forward_exact_contract": {
                    "eligible_trade_count": 30,
                    "avg_net_pnl_pct": 10.0,
                    "net_profit_factor": 5.0,
                },
                "tracked_realized": {
                    "closed_position_count": 10,
                    "avg_net_pnl_pct": -5.0,
                    "net_profit_factor": 0.5,
                },
                "objective_score": 94.0,
            },
        )
        closed_positions = [
            self._live_proof_position(
                ticker="SPY",
                direction="call",
                candidate_id=candidate_id,
                contract_symbol="SPY260417C00500000",
                net_pnl_pct=15.0,
            ),
            self._live_proof_position(
                ticker="SPY",
                direction="call",
                candidate_id=candidate_id,
                contract_symbol="SPY260417C00510000",
                net_pnl_pct=-5.0,
            ),
        ]

        with patch("options_profit_flywheel._require_daily_truth_refresh", return_value={"status": "refreshed", "commands": []}), \
             patch("options_profit_flywheel.evaluate_measurement_gate", return_value={"state": "healthy", "blockers": [], "checks": {}}), \
             patch("options_profit_flywheel.list_candidate_manifests", return_value=[]), \
             patch("options_profit_flywheel._load_closed_positions", return_value=closed_positions):
            result = run_options_profit_cycle()

        self.assertTrue(any(action.get("action") == "finalize_canary" for action in result["canary_actions"]))
        self.assertFalse(any(action.get("action") == "rollback_canary" for action in result["canary_actions"]))
        refreshed_status = load_profit_status()
        self.assertIsNone(refreshed_status["current_canary"]["SPY"]["call"])

    def test_profit_cycle_clears_legacy_symbol_canary_before_pending_evaluation(self):
        state_root = Path(self.state_dir)
        state_root.mkdir(parents=True, exist_ok=True)
        (state_root / "live_profile.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-04-01T00:00:00Z",
                    "symbols": {
                        "SPY": {
                            "symbol": "SPY",
                            "candidate_id": "SPY__broad_ev7",
                            "cohort_id": "broad_ev7",
                            "base_profile": "index",
                            "overrides": {},
                            "source": "legacy_test",
                            "mode": "canary",
                            "status": "candidate",
                        }
                    },
                },
                indent=2,
            ),
            encoding="utf8",
        )
        (state_root / "incumbents.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-04-01T00:00:00Z",
                    "symbols": {
                        "SPY": {
                            "symbol": "SPY",
                            "active": {
                                "symbol": "SPY",
                                "candidate_id": "SPY__broad_ev7",
                                "cohort_id": "broad_ev7",
                                "base_profile": "index",
                                "overrides": {},
                                "source": "legacy_test",
                                "mode": "canary",
                                "status": "candidate",
                            },
                            "previous": None,
                            "canary": {
                                "symbol": "SPY",
                                "candidate_id": "SPY__broad_ev7",
                                "required_outcomes": 1,
                            },
                            "objective": {"objective_score": 1.25},
                        }
                    },
                },
                indent=2,
            ),
            encoding="utf8",
        )
        (state_root / "status.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-04-01T00:00:00Z",
                    "active_incumbents": {
                        "SPY": {
                            "symbol": "SPY",
                            "candidate_id": "SPY__broad_ev7",
                            "cohort_id": "broad_ev7",
                            "base_profile": "index",
                            "overrides": {},
                            "source": "legacy_test",
                            "mode": "canary",
                            "status": "candidate",
                        }
                    },
                    "current_canary": {"symbol": "SPY", "candidate_id": "SPY__broad_ev7"},
                    "candidate_rankings": [],
                    "last_decision": {"action": "legacy"},
                    "blockers": [],
                },
                indent=2,
            ),
            encoding="utf8",
        )

        with patch("options_profit_flywheel._require_daily_truth_refresh", return_value={"status": "refreshed", "commands": []}), \
             patch("options_profit_flywheel.evaluate_measurement_gate", return_value={"state": "healthy", "blockers": [], "checks": {}}), \
             patch("options_profit_flywheel.list_candidate_manifests", return_value=[]), \
             patch("options_profit_flywheel._load_closed_positions", return_value=[]):
            result = run_options_profit_cycle()

        self.assertEqual(result["decision"]["action"], "no_op")
        self.assertFalse(any(action.get("action") == "canary_pending" for action in result["canary_actions"]))
        status = load_profit_status()
        self.assertIsNone(status["current_canary"]["SPY"]["call"])
        self.assertIsNone(status["current_canary"]["SPY"]["put"])

    def test_finalize_canary_resets_live_profile_mode_to_incumbent(self):
        ensure_options_profit_state()
        live_profile = load_live_profile_state(refresh=True)
        candidate_id = "SPY__call__broad_ev7"
        live_profile["symbols"]["SPY"]["call"].update(
            {
                "candidate_id": candidate_id,
                "cohort_id": "broad_ev7",
                "mode": "canary",
                "status": "candidate",
                "source": "test_canary",
            }
        )
        save_live_profile_state(live_profile)

        incumbents = load_incumbents_state()
        incumbents["symbols"]["SPY"]["call"] = {
            "symbol": "SPY",
            "direction": "call",
            "active": dict(live_profile["symbols"]["SPY"]["call"]),
            "previous": {
                "symbol": "SPY",
                "direction": "call",
                "candidate_id": "SPY__call__baseline_broad_control",
                "cohort_id": "baseline_broad_control",
                "base_profile": "index",
                "overrides": {},
                "manifest_source": None,
                "source": "bootstrap_default",
                "mode": "incumbent",
                "status": "incumbent",
                "applied_at": "2026-04-01T00:00:00Z",
            },
            "canary": {
                "candidate_id": candidate_id,
                "symbol": "SPY",
                "direction": "call",
                "required_outcomes": 1,
                "baseline_objective": {"objective_score": -100.0},
            },
            "objective": {"objective_score": 0.0},
        }
        save_incumbents_state(incumbents)

        closed_positions = [
            self._live_proof_position(
                ticker="SPY",
                direction="call",
                candidate_id=candidate_id,
                contract_symbol="SPY260417C00500000",
                net_pnl_pct=15.0,
                source_pick_snapshot={
                    "ticker": "SPY",
                    "direction": "call",
                    "contract_symbol": "SPY260417C00500000",
                },
            )
        ]

        with patch("options_profit_flywheel._require_daily_truth_refresh", return_value={"status": "refreshed", "commands": []}), \
             patch("options_profit_flywheel.evaluate_measurement_gate", return_value={"state": "healthy", "blockers": [], "checks": {}}), \
             patch("options_profit_flywheel.list_candidate_manifests", return_value=[]), \
             patch("options_profit_flywheel._load_closed_positions", return_value=closed_positions):
            result = run_options_profit_cycle()

        self.assertTrue(any(action.get("action") == "finalize_canary" for action in result["canary_actions"]))
        refreshed_live = load_live_profile_state(refresh=True)
        refreshed_status = load_profit_status()
        self.assertEqual(refreshed_live["symbols"]["SPY"]["call"]["mode"], "incumbent")
        self.assertEqual(refreshed_live["symbols"]["SPY"]["call"]["status"], "incumbent")
        self.assertIsNone(refreshed_status["current_canary"]["SPY"]["call"])
        self.assertEqual(refreshed_status["active_incumbents"]["SPY"]["call"]["mode"], "incumbent")
        self.assertEqual(refreshed_status["active_incumbents"]["SPY"]["call"]["status"], "incumbent")


if __name__ == "__main__":
    unittest.main()
