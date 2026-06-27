from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_strict_forward_operator_queue as queue


NOW = "2026-06-26T06:30:00Z"


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf8")


def _payloads(generated_at: str = NOW) -> dict[str, dict]:
    return {
        "oracle": {
            "generated_at_utc": generated_at,
            "report_id": "options_oracle_profit_loop_packet",
            "status": "ready_for_same_session_gpt55_guidance",
            "profitability_target": {
                "current_forward_rows": 0,
                "minimum_profitable_strict_completed_rows": 30,
            },
            "current_evidence_summary": {
                "direct_vix_source_import_status": "direct_vix_source_import_materialized",
                "point_in_time_vix_bucket_status": "point_in_time_vix_bucket_ready",
                "point_in_time_vix_bucket_blockers": [],
                "candidate_generation_13_symbol_frozen_engine_status": "blocked_frozen_13_symbol_candidate_generation_engine",
                "candidate_generation_13_symbol_frozen_engine_blockers": ["missing_historical_entry_underlying_price_surface"],
                "candidate_generation_13_symbol_candidate_months": 0,
                "candidate_generation_13_symbol_frozen_engine_selected_rows": 0,
                "underlying_daily_source_acquisition_status": "blocked_underlying_daily_source_acquisition_missing",
                "underlying_daily_source_acquisition_blockers": ["trusted_source_csv_missing"],
                "underlying_daily_source_acquisition_ready_candidate_count": 0,
                "source_repair_59_symbol_resume_theta_terminal": {"status": "unavailable"},
                "vrp_credit_spread_replay_readiness_status": "blocked_vrp_credit_spread_bounded_replay_gate",
                "vrp_credit_spread_replay_readiness_blockers": ["missing_index_credit_spread_quote_surface"],
                "term_structure_calendar_replay_readiness_status": "blocked_term_structure_calendar_bounded_replay",
                "term_structure_calendar_replay_readiness_blockers": ["missing_point_in_time_term_structure_inputs"],
                "dispersion_proxy_hybrid_replay_readiness_status": "blocked_dispersion_proxy_hybrid_replay_readiness",
                "dispersion_proxy_hybrid_replay_readiness_blockers": ["missing_dispersion_or_concentration_proxy_inputs"],
                "flow_extreme_ratio_backspread_replay_readiness_status": "blocked_flow_extreme_ratio_backspread_replay_readiness",
                "flow_extreme_ratio_backspread_replay_readiness_blockers": ["missing_point_in_time_flow_extreme_input"],
                "momentum_continuation_bounded_replay_status": "blocked_momentum_continuation_bounded_replay",
                "momentum_continuation_bounded_replay_blockers": ["missing_point_in_time_spy_momentum_confirmation"],
                "preregistered_skew_broken_wing_status": "preregistered_design_only",
            },
        },
        "layer4": {
            "generated_at_utc": generated_at,
            "report_id": "bullish_pullback_layer4_forward_capture_protocol",
            "capture_protocol_status": queue.READY_PROTOCOL_STATUS,
            "overall_status": queue.READY_PROTOCOL_STATUS,
            "selected_harness": {
                "lane_id": "bullish_pullback_observation",
                "layer_id": "layer_4_clean_exact",
                "variant_id": "variant",
                "source_result_path": "data/options-validation/runs/source.json",
                "freeze_date": "2026-06-14",
                "allowed_symbols": ["IWM", "AAPL"],
            },
            "historical_executable_economics": {
                "status": "executable_economics_recomputed_profitable_but_preflight_blocked",
                "harness_decision": "profitable_but_preflight_blocked",
                "tradable_executable_rows": 120,
                "historical_side_aware_pf": 3.7414,
                "historical_side_aware_pf_lb_5pct": 2.27,
            },
            "prohibited_actions": ["do_not_append_forward_cohort_rows_from_bullish_pullback_layer4_forward_capture_protocol"],
        },
        "checklist": {
            "generated_at_utc": generated_at,
            "report_id": "regular_options_market_window_evidence_checklist",
            "overall_status": "waiting_for_market_window",
            "market_window_status": "unknown",
            "commands_to_run": [
                {
                    "priority": 1,
                    "command": "npm run options:gateboard",
                    "purpose": "Refresh operator gateboard.",
                    "read_only": True,
                },
                {
                    "priority": 11,
                    "command": "npm run options:preflight:market-window-approval",
                    "purpose": "Run final no-write preflight.",
                    "read_only": True,
                },
            ],
            "prohibited_actions": ["do_not_create_trades_from_market_window_checklist"],
        },
        "gateboard": {
            "generated_at_utc": generated_at,
            "report_id": "project_operator_gateboard",
            "overall_status": "safe_blocked_no_live_release",
        },
    }


def _write_sources(root: Path, payloads: dict[str, dict] | None = None) -> dict[str, Path]:
    payloads = payloads or _payloads()
    paths = {
        "oracle_packet_path": root / "oracle.json",
        "layer4_protocol_path": root / "layer4.json",
        "market_window_checklist_path": root / "checklist.json",
        "gateboard_path": root / "gateboard.json",
    }
    _write(paths["oracle_packet_path"], payloads["oracle"])
    _write(paths["layer4_protocol_path"], payloads["layer4"])
    _write(paths["market_window_checklist_path"], payloads["checklist"])
    _write(paths["gateboard_path"], payloads["gateboard"])
    return paths


class RegularOptionsStrictForwardOperatorQueueTests(unittest.TestCase):
    def test_ready_queue_is_approval_and_market_window_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = _write_sources(Path(temp_dir))
            report = queue.build_report(generated_at_utc=NOW, **paths)

        self.assertEqual(report["overall_status"], "strict_forward_queue_ready_approval_and_market_window_blocked")
        self.assertEqual(report["strict_forward_rows"], 0)
        self.assertEqual(report["required_rows"], 30)
        self.assertFalse(report["profitability_readiness"])
        self.assertEqual(report["fresh_forward_capture_status"], "approval_and_market_window_blocked")
        self.assertFalse(report["live_entry_allowed"])
        self.assertFalse(report["broker_order_allowed"])
        self.assertFalse(report["cohort_append_performed"])
        self.assertIn("do_not_reopen_vix_selector_term_dispersion_vrp_cleanup_as_next_step", report["prohibited_actions"])

    def test_missing_oracle_packet_blocks_readback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = _write_sources(root)
            paths["oracle_packet_path"].unlink()
            report = queue.build_report(generated_at_utc=NOW, **paths)

        self.assertEqual(report["overall_status"], "blocked_missing_readbacks")
        self.assertEqual(report["fresh_forward_capture_status"], "blocked_readback_unavailable")

    def test_protocol_not_ready_blocks_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _payloads()
            payloads["layer4"]["capture_protocol_status"] = "blocked_capture_protocol"
            paths = _write_sources(Path(temp_dir), payloads)
            report = queue.build_report(generated_at_utc=NOW, **paths)

        self.assertEqual(report["overall_status"], "blocked_layer4_protocol_not_ready")
        self.assertEqual(report["fresh_forward_capture_status"], "blocked_protocol_not_ready")

    def test_branches_categorize_vix_as_cleared_and_preserve_current_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = _write_sources(Path(temp_dir))
            report = queue.build_report(generated_at_utc=NOW, **paths)

        branches = {item["branch_id"]: item for item in report["blocked_or_superseded_branches"]}
        self.assertEqual(branches["direct_vix_source"]["classification"], "superseded_cleared")
        self.assertEqual(branches["direct_vix_bucket"]["status"], "point_in_time_vix_bucket_ready")
        self.assertIn("missing_index_credit_spread_quote_surface", branches["vrp_credit_spread"]["blockers"])
        self.assertIn("missing_point_in_time_term_structure_inputs", branches["term_structure_calendar"]["blockers"])
        self.assertIn("missing_dispersion_or_concentration_proxy_inputs", branches["dispersion_proxy_hybrid"]["blockers"])
        self.assertIn("missing_point_in_time_flow_extreme_input", branches["flow_extreme_ratio_backspread"]["blockers"])
        self.assertIn("missing_point_in_time_downside_skew_inputs", branches["skew_broken_wing"]["blockers"])

    def test_write_outputs_creates_json_and_doc_without_append_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = _write_sources(root)
            report = queue.build_report(generated_at_utc=NOW, **paths)
            artifacts = queue.write_outputs(report, output_dir=root / "out", docs_report=root / "doc.md")
            doc = (root / "doc.md").read_text(encoding="utf8")
            latest = json.loads((root / "out" / f"{queue.REPORT_ID}_latest.json").read_text(encoding="utf8"))

        self.assertIn("latest_json", artifacts)
        self.assertEqual(latest["strict_forward_rows"], 0)
        self.assertIn("Strict forward proof: `0/30`", doc)
        self.assertIn("do not append from this queue", doc)


if __name__ == "__main__":
    unittest.main()
