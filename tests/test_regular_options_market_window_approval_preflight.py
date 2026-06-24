from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_bullish_pullback_layer4_forward_capture_protocol as protocol
from scripts import build_regular_options_market_window_approval_preflight as preflight


NOW = "2026-06-21T20:45:00Z"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf8")


def _selected() -> dict:
    return {
        "lane_id": protocol.SELECTED_LANE_ID,
        "layer_id": protocol.SELECTED_LAYER_ID,
        "variant_id": protocol.SELECTED_VARIANT_ID,
        "allowed_symbols": list(protocol.ALLOWED_SYMBOLS),
        "freeze_date": protocol.FREEZE_DATE,
        "source_result_path": protocol.SELECTED_SOURCE_RUN,
    }


def _historical_economics() -> dict:
    return {
        "status": "executable_economics_recomputed_profitable_but_preflight_blocked",
        "harness_decision": "profitable_but_preflight_blocked",
        "historical_side_aware_net_usd_total": 45610.0,
        "historical_side_aware_pf": 3.7414,
        "historical_side_aware_pf_lb_5pct": 2.27,
        "historical_side_aware_avg_net_lb_5pct": 235.07,
        "tradable_executable_rows": 120,
        "row_counts": {
            "selected_rows": 129,
            "tradable_executable_rows": 120,
            "missing_required_quote_rows": 3,
            "zero_or_untradable_rows": 6,
            "source_mark_mismatch_rows": 129,
        },
    }


def _execution_safety() -> dict:
    return {
        "status": "blocked_execution_safety_preflight",
        "row_counts": {
            "total_selected_rows": 129,
            "crossed_or_missing_quote_rows": 3,
            "zero_bid_or_untradable_rows": 6,
            "rows_with_side_aware_price_mismatch": 129,
        },
    }


def _base_payloads(generated_at: str = NOW) -> dict[str, dict]:
    action_type = "bullish_pullback_layer4_capture_protocol_ready_waiting_for_market_window_and_operator_approval"
    return {
        "gateboard": {
            "generated_at_utc": generated_at,
            "overall_status": "safe_blocked_no_live_release",
            "no_chase_manifest": {"status": "no_chase_active", "prohibited_actions": ["do_not_chase"]},
            "live_entry_allowed": False,
            "auto_track_allowed": False,
            "broker_order_allowed": False,
            "promotion_ready": False,
        },
        "trade_qualification": {
            "generated_at_utc": generated_at,
            "overall_status": "blocked_no_live_release",
            "live_entry_allowed": False,
            "auto_track_allowed": False,
            "broker_order_allowed": False,
            "promotion_ready": False,
        },
        "goal_loop": {
            "generated_at_utc": generated_at,
            "report_id": "options_goal_loop",
            "live_entry_allowed": False,
            "auto_track_allowed": False,
            "broker_order_allowed": False,
            "promotion_ready": False,
            "acceptance_readiness": {
                "post_freeze_strict_exact_completed_rows": 0,
                "minimum_required": 30,
                "bootstrap_pf_lower_bound_5pct_usd": None,
            },
            "forward_evidence_accounting": {
                "state": "log_missing_blocker",
                "cohort_log_exists": False,
                "post_freeze_strict_exact_completed_rows": 0,
                "minimum_required": 30,
                "strict_usd_pf_lower_bound_5pct": None,
                "live_entry_allowed": False,
                "auto_track_allowed": False,
                "broker_order_allowed": False,
                "promotion_ready": False,
                "cohort_append_performed": False,
            },
        },
        "market_window_checklist": {
            "generated_at_utc": generated_at,
            "overall_status": "waiting_for_market_window",
            "live_entry_allowed": False,
            "auto_track_allowed": False,
            "broker_order_allowed": False,
            "promotion_ready": False,
            "checklist_steps": [
                {
                    "step_type": action_type,
                    "status": "waiting_for_market_window_and_operator_approval",
                    "market_window_required": True,
                }
            ],
        },
        "paper_shadow_plan": {
            "generated_at_utc": generated_at,
            "overall_status": "paper_shadow_evidence_collecting",
            "live_entry_allowed": False,
            "auto_track_allowed": False,
            "broker_order_allowed": False,
            "promotion_ready": False,
            "operator_actions": [
                {
                    "action_type": action_type,
                    "status": "waiting_for_market_window_and_operator_approval",
                    "lane_id": protocol.SELECTED_LANE_ID,
                    "selected_layer_id": protocol.SELECTED_LAYER_ID,
                    "selected_variant_id": protocol.SELECTED_VARIANT_ID,
                }
            ],
        },
        "layer4_protocol": {
            "generated_at_utc": generated_at,
            "report_id": "bullish_pullback_layer4_forward_capture_protocol",
            "capture_protocol_status": "protocol_ready_waiting_for_market_window_and_operator_approval",
            "read_only": True,
            "historical_rows_are_forward_proof": False,
            "cohort_append_performed": False,
            "candidate_validator_read_only": True,
            "live_entry_allowed": False,
            "auto_track_allowed": False,
            "broker_order_allowed": False,
            "promotion_ready": False,
            "selected_harness": _selected(),
            "historical_executable_economics": _historical_economics(),
            "execution_safety_preflight": _execution_safety(),
        },
        "execution_safety": {
            "generated_at_utc": generated_at,
            "report_id": "bullish_pullback_layer_execution_safety_audit",
            "overall_status": "blocked_execution_safety_preflight",
            "row_counts": _execution_safety()["row_counts"],
        },
        "executable_economics": {
            "generated_at_utc": generated_at,
            "report_id": "bullish_pullback_layer_executable_economics",
            "overall_status": "executable_economics_recomputed_profitable_but_preflight_blocked",
            "harness_decision": "profitable_but_preflight_blocked",
            "row_counts": _historical_economics()["row_counts"],
        },
    }


def _approval_packet() -> str:
    return "\n".join(
        [
            "This packet is informational until a future valid market-data window.",
            "It does not approve appending rows by itself.",
            "Any future approval must still forbid broker orders, live validation, auto-track, quote import,",
            "protected-holdout consumption, and promotion.",
        ]
    )


def _write_sources(root: Path, payloads: dict[str, dict]) -> dict[str, Path]:
    paths = {
        "gateboard_path": root / "gateboard.json",
        "trade_qualification_path": root / "trade.json",
        "goal_loop_path": root / "goal.json",
        "market_window_checklist_path": root / "checklist.json",
        "paper_shadow_plan_path": root / "plan.json",
        "layer4_capture_protocol_path": root / "protocol.json",
        "execution_safety_path": root / "safety.json",
        "executable_economics_path": root / "economics.json",
        "approval_packet_path": root / "approval.md",
    }
    key_map = {
        "gateboard_path": "gateboard",
        "trade_qualification_path": "trade_qualification",
        "goal_loop_path": "goal_loop",
        "market_window_checklist_path": "market_window_checklist",
        "paper_shadow_plan_path": "paper_shadow_plan",
        "layer4_capture_protocol_path": "layer4_protocol",
        "execution_safety_path": "execution_safety",
        "executable_economics_path": "executable_economics",
    }
    for path_name, key in key_map.items():
        _write_json(paths[path_name], payloads[key])
    _write_text(paths["approval_packet_path"], _approval_packet())
    return paths


class RegularOptionsMarketWindowApprovalPreflightTests(unittest.TestCase):
    def _build(self, root: Path, payloads: dict[str, dict] | None = None, **kwargs):
        paths = _write_sources(root, payloads or _base_payloads())
        paths.update(kwargs)
        return preflight.build_report(generated_at_utc=NOW, **paths)

    def test_unknown_market_status_blocks_without_append(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir))

        self.assertEqual(report["overall_status"], "blocked_market_window_unknown")
        self.assertFalse(report["append_allowed"])
        self.assertFalse(report["cohort_append_performed"])
        self.assertFalse(report["live_entry_allowed"])
        self.assertEqual(report["readback_summary"]["volatility_post_freeze_strict_exact_completed_rows"], 0)

    def test_market_closed_blocks_even_with_clean_readbacks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir), market_window_status="market_closed")

        self.assertEqual(report["overall_status"], "blocked_market_closed")
        self.assertEqual(report["next_operator_action"], "wait_for_valid_market_window_then_run_preflight_again")
        self.assertFalse(report["market_window_valid"])

    def test_stale_source_blocks_before_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _base_payloads(generated_at="2026-06-01T00:00:00Z")
            report = self._build(Path(temp_dir), payloads)

        self.assertEqual(report["overall_status"], "blocked_stale_or_missing_readbacks")
        self.assertEqual(report["source_artifacts"]["gateboard"]["status"], "stale")

    def test_market_open_without_operator_approval_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(Path(temp_dir), market_window_status="market_open")

        self.assertEqual(report["overall_status"], "blocked_operator_approval_missing")
        self.assertFalse(report["operator_approval_granted"])

    def test_invalid_candidate_rows_block_validation_without_append(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(
                Path(temp_dir),
                market_window_status="market_open",
                operator_approval_token=preflight.APPROVAL_TOKEN,
                candidate_jsonl_path=FIXTURES / "bullish_pullback_layer4_forward_candidate_invalid.jsonl",
            )

        self.assertEqual(report["overall_status"], "blocked_candidate_validation_failed")
        self.assertGreater(report["candidate_validation"]["rejected_candidate_rows"], 0)
        self.assertFalse(report["append_allowed"])
        self.assertFalse(report["cohort_append_performed"])

    def test_valid_candidate_rows_are_review_only_after_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build(
                Path(temp_dir),
                market_window_status="market_open",
                operator_approval_token=preflight.APPROVAL_TOKEN,
                candidate_jsonl_path=FIXTURES / "bullish_pullback_layer4_forward_candidate_valid.jsonl",
            )

        self.assertEqual(report["overall_status"], "candidate_rows_valid_for_future_approval_no_append")
        self.assertTrue(report["candidate_validation"]["candidate_rows_valid_for_future_approval_no_append"])
        self.assertFalse(report["append_allowed"])
        self.assertFalse(report["cohort_append_performed"])

    def test_live_or_selected_harness_drift_blocks_gateboard_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _base_payloads()
            payloads["layer4_protocol"]["selected_harness"]["layer_id"] = "layer_5_count_expanded"
            report = self._build(Path(temp_dir), payloads, market_window_status="market_open")

        self.assertEqual(report["overall_status"], "blocked_gateboard_or_no_chase")
        self.assertIn("selected_layer_drift", {row["code"] for row in report["invariant_blockers"]})


if __name__ == "__main__":
    unittest.main()
