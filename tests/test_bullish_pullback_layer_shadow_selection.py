from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_bullish_pullback_layer_shadow_selection as selector


NOW = "2026-06-21T18:00:00Z"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf8")


def _layer(
    layer_id: str,
    *,
    variant_id: str,
    candidate_trade_count=None,
    exact_trade_count=None,
    profit_factor=None,
    quote_coverage_pct=None,
    stress_5pct_per_side_profit_factor=None,
    rolling_status=None,
    unpriced_trade_count=None,
    symbols=None,
) -> dict:
    row = {
        "layer_id": layer_id,
        "variant_id": variant_id,
        "decision": "paper_shadow",
        "source_result_path": f"data/options-validation/runs/{variant_id}.json",
        "metrics": {
            "candidate_trade_count": candidate_trade_count,
            "exact_trade_count": exact_trade_count,
            "profit_factor": profit_factor,
            "quote_coverage_pct": quote_coverage_pct,
            "stress_5pct_per_side_profit_factor": stress_5pct_per_side_profit_factor,
            "rolling_status": rolling_status,
            "unpriced_trade_count": unpriced_trade_count,
        },
        "gate_read": {"status": "test"},
    }
    if symbols is not None:
        row["symbols"] = symbols
    return row


def _layer_stack(generated_at: str = "2026-06-01T00:00:00Z") -> dict:
    return {
        "generated_at": generated_at,
        "scope": "bullish_pullback_observation next profitability layer stack",
        "paper_shadow_only": True,
        "target_read": {
            "preferred_target_exact_trades": 200,
            "current_best_exact_trades": 130,
            "gap_to_200": 70,
            "honest_status": "not_reached",
        },
        "ordered_layers": [
            _layer(
                "layer_0_confidence_core_s_a_b",
                variant_id="confidence_s_a_b_queue",
                exact_trade_count=108,
                profit_factor=4.86,
                symbols=list(selector.ALLOWED_SYMBOLS),
            ),
            _layer(
                "layer_4_clean_exact",
                variant_id="sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1",
                candidate_trade_count=129,
                exact_trade_count=129,
                profit_factor=2.20,
                quote_coverage_pct=100.0,
                stress_5pct_per_side_profit_factor=1.67,
                rolling_status="passed",
                unpriced_trade_count=0,
            ),
            _layer(
                "layer_5_count_expanded",
                variant_id="sleeve_pf59_coverage_a_refill_v1",
                candidate_trade_count=133,
                exact_trade_count=130,
                profit_factor=2.04,
                quote_coverage_pct=97.7,
                stress_5pct_per_side_profit_factor=1.53,
                unpriced_trade_count=3,
            ),
        ],
    }


class BullishPullbackLayerShadowSelectionTests(unittest.TestCase):
    def test_selects_clean_layer_and_preserves_reference_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "layer-stack.json"
            _write_json(path, _layer_stack())
            report = selector.build_report(layer_stack_path=path, generated_at_utc=NOW)

        self.assertEqual(report["overall_status"], "layer_shadow_selection_ready")
        self.assertTrue(report["read_only"])
        self.assertTrue(report["paper_shadow_only"])
        self.assertFalse(report["live_entry_allowed"])
        self.assertFalse(report["broker_order_allowed"])
        primary = report["primary_harness_layer"]
        self.assertEqual(primary["layer_id"], "layer_4_clean_exact")
        self.assertEqual(primary["metrics"]["exact_trade_count"], 129)
        self.assertEqual(primary["metrics"]["candidate_trade_count"], 129)
        self.assertEqual(primary["metrics"]["profit_factor"], 2.20)
        self.assertEqual(primary["metrics"]["quote_coverage_pct"], 100.0)
        self.assertEqual(primary["metrics"]["stress_5pct_per_side_profit_factor"], 1.67)
        self.assertEqual(primary["metrics"]["rolling_status"], "passed")
        self.assertEqual(primary["metrics"]["unpriced_trade_count"], 0)
        count_ref = report["count_expanded_reference"]
        self.assertEqual(count_ref["layer_id"], "layer_5_count_expanded")
        self.assertEqual(count_ref["status"], "count_expanded_reference_blocked_by_unpriced_candidates")
        self.assertEqual(count_ref["metrics"]["exact_trade_count"], 130)
        self.assertEqual(count_ref["metrics"]["unpriced_trade_count"], 3)
        core = report["high_pf_core_reference"]
        self.assertEqual(core["layer_id"], "layer_0_confidence_core_s_a_b")
        self.assertEqual(core["metrics"]["profit_factor"], 4.86)
        self.assertEqual(report["target_truth"]["gap_to_200"], 70)
        self.assertEqual(report["allowed_symbols"], list(selector.ALLOWED_SYMBOLS))

    def test_missing_layer_stack_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = selector.build_report(layer_stack_path=Path(temp_dir) / "missing.json", generated_at_utc=NOW)

        self.assertEqual(report["overall_status"], "blocked_layer_shadow_selection")
        self.assertIn("missing_layer_stack", report["blockers"])

    def test_malformed_layer_stack_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "layer-stack.json"
            path.write_text("{bad", encoding="utf8")
            report = selector.build_report(layer_stack_path=path, generated_at_utc=NOW)

        self.assertEqual(report["overall_status"], "blocked_layer_shadow_selection")
        self.assertIn("malformed_layer_stack", report["blockers"])

    def test_non_paper_shadow_layer_stack_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "layer-stack.json"
            payload = _layer_stack()
            payload["paper_shadow_only"] = False
            _write_json(path, payload)
            report = selector.build_report(layer_stack_path=path, generated_at_utc=NOW)

        self.assertEqual(report["overall_status"], "blocked_layer_shadow_selection")
        self.assertIn("layer_stack_not_paper_shadow_only", report["blockers"])

    def test_missing_required_layer_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "layer-stack.json"
            payload = _layer_stack()
            payload["ordered_layers"] = [row for row in payload["ordered_layers"] if row["layer_id"] != "layer_4_clean_exact"]
            _write_json(path, payload)
            report = selector.build_report(layer_stack_path=path, generated_at_utc=NOW)

        self.assertEqual(report["overall_status"], "blocked_layer_shadow_selection")
        self.assertIn("missing_required_layer:layer_4_clean_exact", report["blockers"])

    def test_stale_layer_stack_fails_closed_when_age_limit_is_tight(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "layer-stack.json"
            _write_json(path, _layer_stack(generated_at="2026-06-01T00:00:00Z"))
            report = selector.build_report(layer_stack_path=path, generated_at_utc=NOW, max_source_age_hours=24)

        self.assertEqual(report["overall_status"], "blocked_layer_shadow_selection")
        self.assertIn("stale_layer_stack", report["blockers"])

    def test_symbol_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "layer-stack.json"
            payload = _layer_stack()
            payload["ordered_layers"][0]["symbols"] = ["SPY"]
            _write_json(path, payload)
            report = selector.build_report(layer_stack_path=path, generated_at_utc=NOW)

        self.assertEqual(report["overall_status"], "blocked_layer_shadow_selection")
        self.assertIn("high_pf_core_symbols_do_not_match_allowed_carrier_set", report["blockers"])


if __name__ == "__main__":
    unittest.main()
