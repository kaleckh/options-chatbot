"""End-to-end test proving the profitability feedback loop works."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


class TestProfitLoopEndToEnd(unittest.TestCase):
    """Full closed-loop test: trades → surface → lookup → decisions."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="profit_loop_e2e_")
        os.environ["OPTIONS_PROFIT_STATE_DIR"] = self._tmpdir

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        os.environ.pop("OPTIONS_PROFIT_STATE_DIR", None)

    def _make_synthetic_trades(self, count: int = 50) -> list[dict]:
        """Generate synthetic trades with realistic score distributions."""
        import random
        random.seed(42)
        trades = []
        for i in range(count):
            direction = "call" if i % 2 == 0 else "put"
            direction_score = random.uniform(55, 85)
            quality_score = random.uniform(50, 90)
            tech_score = random.uniform(60, 85)
            # Win rate roughly tracks direction score
            win = random.random() < (direction_score / 100.0 * 0.8)
            pnl_pct = random.uniform(10, 60) if win else random.uniform(-35, -5)
            trades.append({
                "ticker": random.choice(["SPY", "QQQ", "AAPL", "NVDA", "MSFT"]),
                "type": direction,
                "direction": direction,
                "direction_score": round(direction_score, 1),
                "quality_score": round(quality_score, 1),
                "tech_score": round(tech_score, 1),
                "pnl_pct": round(pnl_pct, 2),
                "market_regime": random.choice(["bullish", "neutral", "bearish"]),
                "spy_ret5": random.uniform(-2, 2),
                "directional_correct": win,
                "expectancy_selection_source": "replay_calibrated" if i < 40 else "bootstrap_heuristic",
                "contract_selection_basis": "exact_target_contract",
            })
        return trades

    def test_01_surface_build_and_persist(self):
        """Surface builds from trades and persists to disk."""
        from expectancy_calibration import (
            build_expectancy_surface_from_trades,
            save_expectancy_surface,
            load_persisted_expectancy_surface,
        )
        trades = self._make_synthetic_trades(50)
        surface = build_expectancy_surface_from_trades(trades, source_metadata={"mode": "test"})
        self.assertIsNotNone(surface)
        self.assertIn("levels", surface)
        self.assertIn("overall", surface)

        # Persist and reload
        path = save_expectancy_surface(surface)
        self.assertIsNotNone(path)
        self.assertTrue(os.path.exists(path))

        loaded = load_persisted_expectancy_surface()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["levels"].keys(), surface["levels"].keys())

    def test_02_calibration_lookup_returns_results(self):
        """Lookup finds calibrated expectancy from the surface."""
        from expectancy_calibration import (
            build_expectancy_surface_from_trades,
            lookup_calibrated_expectancy,
        )
        trades = self._make_synthetic_trades(50)
        surface = build_expectancy_surface_from_trades(trades)

        result = lookup_calibrated_expectancy(
            surface,
            direction_score=70,
            quality_score=70,
            market_regime="bullish",
            trade_type="call",
            tech_score=75,
        )
        # Should find at least overall level
        self.assertIsNotNone(result)
        self.assertIn("avg_pnl_pct", result)
        self.assertIn("trades", result)

    def test_03_confidence_intervals_present(self):
        """Surface cohorts include CI bounds."""
        from expectancy_calibration import build_expectancy_surface_from_trades
        trades = self._make_synthetic_trades(50)
        surface = build_expectancy_surface_from_trades(trades)
        overall = surface.get("overall") or {}
        # Overall should have CI fields
        self.assertIn("ci_lower_95", overall)
        self.assertIn("ci_upper_95", overall)

    def test_04_auto_resolve_seeded_blockers(self):
        """Seeded blockers auto-resolve when conditions are met."""
        from profit_loop_shared_state import (
            auto_resolve_seeded_issues,
            ensure_profit_loop_state,
            load_profit_loop_state,
        )
        ensure_profit_loop_state(state_dir=self._tmpdir)
        state = load_profit_loop_state(state_dir=self._tmpdir)

        # Before: should have open seeded issues
        open_ids = [i["issue_id"] for i in state.get("open_issues", [])]
        self.assertIn("truth-lane-live-policy-mismatch", open_ids)
        self.assertIn("forward-holdout-no-raw-candidates", open_ids)

        # Resolve truth lane mismatch
        resolved = auto_resolve_seeded_issues(
            state,
            live_truth_lane="historical_imported_daily",
            policy_truth_source="historical_imported_daily",
            forward_events_count=5,
        )
        self.assertIn("truth-lane-live-policy-mismatch", resolved)
        self.assertIn("forward-holdout-no-raw-candidates", resolved)

        # After: issues should be in resolved list
        open_ids_after = [i["issue_id"] for i in state.get("open_issues", [])]
        self.assertNotIn("truth-lane-live-policy-mismatch", open_ids_after)
        self.assertNotIn("forward-holdout-no-raw-candidates", open_ids_after)

    def test_05_bootstrap_recovery_detection(self):
        """Bootstrap dominance is detected with recovery actions."""
        from profit_loop_automation import check_bootstrap_recovery_needed

        # All bootstrap trades → should need recovery
        result_all_bootstrap = {
            "lookback_years": 1,
            "trades": [
                {"expectancy_selection_source": "bootstrap_heuristic"} for _ in range(10)
            ],
        }
        recovery = check_bootstrap_recovery_needed(result_all_bootstrap)
        self.assertTrue(recovery["recovery_needed"])
        self.assertGreaterEqual(recovery["bootstrap_pct"], 80.0)
        self.assertIn("actions", recovery)

        # Mixed trades → should not need recovery
        result_mixed = {
            "lookback_years": 1,
            "trades": [
                {"expectancy_selection_source": "replay_calibrated"} for _ in range(8)
            ] + [
                {"expectancy_selection_source": "bootstrap_heuristic"} for _ in range(2)
            ],
        }
        recovery_mixed = check_bootstrap_recovery_needed(result_mixed)
        self.assertFalse(recovery_mixed["recovery_needed"])

    def test_06_metric_auto_tune_suggestions(self):
        """Metric truth audit produces auto-tune suggestions."""
        from metric_truth_audit import suggest_parameter_adjustments

        report = {
            "risk_flags": [
                "direction_score calibration gap exceeds threshold",
                "profit_factor below 1.0",
            ],
            "metric_floors": {
                "direction_score": {"best_floor": 60},
            },
        }
        suggestions = suggest_parameter_adjustments(
            report,
            auto_tune_config={"enabled": True, "direction_score_step": 5, "calibration_gap_threshold_pct": 10.0},
        )
        self.assertTrue(len(suggestions) >= 2)
        param_names = [s["parameter"] for s in suggestions]
        self.assertIn("entry.min_direction_score", param_names)
        self.assertIn("risk.stop_loss_pct", param_names)

    def test_07_lenient_profitability_assessment(self):
        """Best-effort eligibility gives partial credit."""
        from options_execution import scan_profitability_assessment_lenient

        # Fully eligible
        status, blockers, weight = scan_profitability_assessment_lenient(
            contract_symbol="SPY250418C00500000",
            promotion_class="promotable_exact_contract",
            selection_source="live_chain_exact_contract",
            entry_execution_price=1.50,
            quote_freshness_status="fresh",
        )
        self.assertEqual(status, "eligible")
        self.assertEqual(weight, 1.0)

        # Stale quote only → best effort at 50%
        status2, blockers2, weight2 = scan_profitability_assessment_lenient(
            contract_symbol="SPY250418C00500000",
            promotion_class="promotable_exact_contract",
            selection_source="live_chain_exact_contract",
            entry_execution_price=1.50,
            quote_freshness_status="stale",
        )
        self.assertEqual(status2, "best_effort_eligible")
        self.assertEqual(weight2, 0.5)

        # Missing contract → fully ineligible
        status3, blockers3, weight3 = scan_profitability_assessment_lenient(
            contract_symbol="",
            promotion_class="research_bootstrap",
            selection_source="",
            entry_execution_price=None,
            quote_freshness_status="unknown",
        )
        self.assertEqual(status3, "ineligible")
        self.assertEqual(weight3, 0.0)


if __name__ == "__main__":
    unittest.main()
