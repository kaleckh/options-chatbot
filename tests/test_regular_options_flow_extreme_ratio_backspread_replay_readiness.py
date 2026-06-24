from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_regular_options_flow_extreme_ratio_backspread_replay_readiness as readiness
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf8")


class RegularOptionsFlowExtremeRatioBackspreadReplayReadinessTests(unittest.TestCase):
    def _valid_preregistration(self, tmp: Path) -> Path:
        path = tmp / "latest.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_preregistered_flow_extreme_ratio_backspread_playbook",
                "status": "preregistered_design_only",
                "concept_id": readiness.CONCEPT_ID,
                "structure": readiness.EXPECTED_STRUCTURE,
                "accepted_profitability": False,
                "historical_replay_performed": False,
                "lane_implementation_performed": False,
                "undefined_risk_allowed": False,
                "concept": {"undefined_risk_allowed": False, "naked_ratio_spreads_allowed": False},
            },
        )
        return path

    def _feature_store(self, tmp: Path) -> Path:
        path = tmp / "feature.json"
        _write_json(
            path,
            {
                "source_label": "thetadata_opra_nbbo_1m",
                "quote_evidence_class": "trusted_intraday_opra_nbbo",
                "join_contract": "feature.tradable_after_time <= candidate_entry_time",
                "symbols": ["SPY", "QQQ"],
            },
        )
        return path

    def _blocked_vix(self, tmp: Path) -> Path:
        path = tmp / "vix.json"
        _write_json(path, {"status": "blocked_point_in_time_vix_source_missing", "point_in_time_vix_low_mid_bucket_available": False})
        return path

    def _ready_vix(self, tmp: Path) -> Path:
        path = tmp / "vix-ready.json"
        _write_json(path, {"status": "ready", "point_in_time_vix_low_mid_bucket_available": True})
        return path

    def _blocked_flow_input(self, tmp: Path) -> Path:
        path = tmp / "flow-input.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_point_in_time_flow_extreme_input",
                "status": "blocked_point_in_time_flow_extreme_input",
                "accepted_profitability": False,
                "historical_replay_performed": False,
                "historical_rows_are_forward_proof": False,
                "live_validation_enabled": False,
                "auto_track_enabled": False,
                "broker_order_allowed": False,
                "quotes_imported": False,
                "evidence_stores_mutated": False,
                "protected_holdout_consumed": False,
                "production_scanner_changed": False,
                "strategy_logic_changed": False,
                "stops_changed": False,
                "sizing_changed": False,
                "proof_bars_changed": False,
                "promotion_ready": False,
                "blockers": ["missing_point_in_time_flow_extreme_source"],
            },
        )
        return path

    def _ready_flow_input(self, tmp: Path) -> Path:
        path = tmp / "flow-input-ready.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_point_in_time_flow_extreme_input",
                "status": "point_in_time_flow_extreme_input_available",
                "accepted_profitability": False,
                "historical_replay_performed": False,
                "historical_rows_are_forward_proof": False,
                "live_validation_enabled": False,
                "auto_track_enabled": False,
                "broker_order_allowed": False,
                "quotes_imported": False,
                "evidence_stores_mutated": False,
                "protected_holdout_consumed": False,
                "production_scanner_changed": False,
                "strategy_logic_changed": False,
                "stops_changed": False,
                "sizing_changed": False,
                "proof_bars_changed": False,
                "promotion_ready": False,
                "coverage": {"covered_month_count": 24, "date_coverage_pct": 99.0},
                "proxy_basis": ["volume_open_interest"],
                "blockers": [],
            },
        )
        return path

    def _blocked_pricing_capability(self, tmp: Path) -> Path:
        path = tmp / "pricing-capability-blocked.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_multi_leg_side_aware_pricing_capability",
                "status": "blocked_multi_leg_side_aware_pricing_capability",
                "accepted_profitability": False,
                "historical_replay_performed": False,
                "historical_rows_are_forward_proof": False,
                "fixture_source_not_proof_eligible": True,
                "live_validation_enabled": False,
                "auto_track_enabled": False,
                "broker_order_allowed": False,
                "quotes_imported": False,
                "evidence_stores_mutated": False,
                "options_history_db_mutated": False,
                "protected_holdout_consumed": False,
                "production_scanner_changed": False,
                "strategy_logic_changed": False,
                "stops_changed": False,
                "sizing_changed": False,
                "proof_bars_changed": False,
                "scanner_strategy_stop_sizing_or_proof_bar_changed": False,
                "promotion_ready": False,
                "pricing_capability_blockers": ["missing_leg_quote"],
                "structure_support": {
                    "ratio_backspread_bounded": {
                        "status": "blocked",
                        "denominator_mapping_status": "blocked",
                    }
                },
            },
        )
        return path

    def _ready_pricing_capability(self, tmp: Path) -> Path:
        path = tmp / "pricing-capability-ready.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_multi_leg_side_aware_pricing_capability",
                "status": "multi_leg_side_aware_pricing_capability_available",
                "accepted_profitability": False,
                "historical_replay_performed": False,
                "historical_rows_are_forward_proof": False,
                "fixture_source_not_proof_eligible": True,
                "live_validation_enabled": False,
                "auto_track_enabled": False,
                "broker_order_allowed": False,
                "quotes_imported": False,
                "evidence_stores_mutated": False,
                "options_history_db_mutated": False,
                "protected_holdout_consumed": False,
                "production_scanner_changed": False,
                "strategy_logic_changed": False,
                "stops_changed": False,
                "sizing_changed": False,
                "proof_bars_changed": False,
                "scanner_strategy_stop_sizing_or_proof_bar_changed": False,
                "promotion_ready": False,
                "pricing_capability_blockers": [],
                "structure_support": {
                    "ratio_backspread_bounded": {
                        "status": "available",
                        "denominator_mapping_status": "ready",
                    }
                },
            },
        )
        return path

    def _blocked_denominator_dedupe_bridge(self, tmp: Path) -> Path:
        path = tmp / "denominator-dedupe-blocked.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_flow_extreme_denominator_dedupe_bridge",
                "status": "blocked_flow_extreme_denominator_dedupe_bridge",
                "concept_id": readiness.CONCEPT_ID,
                "structure": "ratio_backspread_bounded",
                "accepted_profitability": False,
                "proof_row_count": 0,
                "historical_replay_performed": False,
                "replay_performed": False,
                "historical_rows_are_forward_proof": False,
                "fixture_source_not_proof_eligible": True,
                "live_validation_enabled": False,
                "auto_track_enabled": False,
                "broker_order_allowed": False,
                "quotes_imported": False,
                "evidence_stores_mutated": False,
                "protected_holdout_consumed": False,
                "production_scanner_changed": False,
                "strategy_logic_changed": False,
                "stops_changed": False,
                "sizing_changed": False,
                "proof_bars_changed": False,
                "promotion_ready": False,
                "full_denominator_mapping_status": "ready",
                "strict_new_dedupe_status": "blocked",
                "bridge_blockers": ["base_stack_identity_ledger_missing"],
            },
        )
        return path

    def _ready_denominator_dedupe_bridge(self, tmp: Path) -> Path:
        path = tmp / "denominator-dedupe-ready.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_flow_extreme_denominator_dedupe_bridge",
                "status": "flow_extreme_denominator_dedupe_bridge_ready",
                "concept_id": readiness.CONCEPT_ID,
                "structure": "ratio_backspread_bounded",
                "accepted_profitability": False,
                "proof_row_count": 0,
                "historical_replay_performed": False,
                "replay_performed": False,
                "historical_rows_are_forward_proof": False,
                "fixture_source_not_proof_eligible": True,
                "live_validation_enabled": False,
                "auto_track_enabled": False,
                "broker_order_allowed": False,
                "quotes_imported": False,
                "evidence_stores_mutated": False,
                "protected_holdout_consumed": False,
                "production_scanner_changed": False,
                "strategy_logic_changed": False,
                "stops_changed": False,
                "sizing_changed": False,
                "proof_bars_changed": False,
                "promotion_ready": False,
                "full_denominator_mapping_status": "ready",
                "strict_new_dedupe_status": "ready",
                "bridge_blockers": [],
            },
        )
        return path

    def _holdout(self, tmp: Path) -> Path:
        path = tmp / "holdout.json"
        _write_json(path, {"contract_id": "forward_holdout_contract", "status": "active"})
        return path

    def test_report_is_read_only_and_blocks_missing_flow_and_vix(self) -> None:
        with WorkspaceTempDir(prefix="flow-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            evidence = tmp / "evidence.py"
            _write_text(evidence, "overextension design mention without point in time rows")
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_preregistration(tmp),
                feature_store_path=self._feature_store(tmp),
                point_in_time_flow_extreme_input_path=self._blocked_flow_input(tmp),
                multi_leg_side_aware_pricing_capability_path=self._blocked_pricing_capability(tmp),
                flow_extreme_denominator_dedupe_bridge_path=self._blocked_denominator_dedupe_bridge(tmp),
                point_in_time_vix_bucket_path=self._blocked_vix(tmp),
                forward_holdout_contract_path=self._holdout(tmp),
                evidence_paths=[evidence],
                generated_at_utc="2026-06-23T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_flow_extreme_ratio_backspread_replay_readiness")
        for key, expected in readiness.READ_ONLY_FLAGS.items():
            self.assertIs(report[key], expected)
        self.assertIn("missing_point_in_time_flow_extreme_input", report["blockers"])
        self.assertIn("missing_point_in_time_vix_bucket", report["blockers"])

    def test_invalid_undefined_risk_preregistration_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="flow-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            invalid = tmp / "bad.json"
            _write_json(
                invalid,
                {
                    "status": "preregistered_design_only",
                    "concept_id": readiness.CONCEPT_ID,
                    "structure": readiness.EXPECTED_STRUCTURE,
                    "accepted_profitability": False,
                    "historical_replay_performed": False,
                    "lane_implementation_performed": False,
                    "undefined_risk_allowed": True,
                    "concept": {"undefined_risk_allowed": True, "naked_ratio_spreads_allowed": True},
                },
            )
            report = readiness.build_report(
                preregistered_playbook_path=invalid,
                feature_store_path=self._feature_store(tmp),
                point_in_time_flow_extreme_input_path=self._ready_flow_input(tmp),
                multi_leg_side_aware_pricing_capability_path=self._ready_pricing_capability(tmp),
                flow_extreme_denominator_dedupe_bridge_path=self._ready_denominator_dedupe_bridge(tmp),
                point_in_time_vix_bucket_path=self._ready_vix(tmp),
                forward_holdout_contract_path=self._holdout(tmp),
                evidence_paths=[],
            )

        self.assertEqual(report["status"], "blocked_invalid_flow_extreme_ratio_backspread_preregistration")
        self.assertFalse(report["preregistration_validation"]["valid"])
        self.assertIn("undefined_risk_allowed_not_false", report["preregistration_validation"]["reasons"])
        self.assertEqual(report["critical_prerequisites"], [])

    def test_exact_evidence_can_reach_ready_status(self) -> None:
        with WorkspaceTempDir(prefix="flow-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            exact = tmp / "exact.py"
            _write_text(
                exact,
                """
point_in_time_flow_extreme_input = True
point_in_time_overextension_signal = True
entry_net_premium = (long_leg_ask * long_quantity_bought) - (short_leg_bid * short_quantity_sold)
exit_net_value = (long_leg_bid * long_quantity_sold_to_close) - (short_leg_ask * short_quantity_bought_to_close)
net_pnl_usd = 1
max_loss_usd = 100
required collateral = 100
rejected_undefined_risk = True
assignment and expiration classifier
denominator = ["rejected_overextension_signal_missing", "rejected_vix_bucket", "rejected_width_or_liquidity", "rejected_undefined_risk", "missing_leg_quote", "zero_bid_or_untradable", "exact_entry_captured", "open_waiting_policy_exit_or_expiry", "assignment_or_expiration_blocked", "exact_exit_captured", "missing_exit"]
strict-new dedupe versus 157-row clean base stack
proof_eligible = False
production proof is forbidden
""",
            )
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_preregistration(tmp),
                feature_store_path=self._feature_store(tmp),
                point_in_time_flow_extreme_input_path=self._ready_flow_input(tmp),
                multi_leg_side_aware_pricing_capability_path=self._ready_pricing_capability(tmp),
                flow_extreme_denominator_dedupe_bridge_path=self._ready_denominator_dedupe_bridge(tmp),
                point_in_time_vix_bucket_path=self._ready_vix(tmp),
                forward_holdout_contract_path=self._holdout(tmp),
                evidence_paths=[exact],
            )

        self.assertEqual(report["status"], "flow_extreme_ratio_backspread_replay_readiness_ready")
        self.assertEqual(report["blockers"], [])
        self.assertIsNone(report["smallest_next_blocker_clearing_slice"])

    def test_bridge_can_clear_denominator_while_preserving_strict_new_blocker(self) -> None:
        with WorkspaceTempDir(prefix="flow-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            exact = tmp / "exact.py"
            _write_text(
                exact,
                """
max_loss_usd = 100
required collateral = 100
rejected_undefined_risk = True
assignment and expiration classifier
proof_eligible = False
trusted_intraday_opra_nbbo
production proof is forbidden
""",
            )
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_preregistration(tmp),
                feature_store_path=self._feature_store(tmp),
                point_in_time_flow_extreme_input_path=self._ready_flow_input(tmp),
                multi_leg_side_aware_pricing_capability_path=self._ready_pricing_capability(tmp),
                flow_extreme_denominator_dedupe_bridge_path=self._blocked_denominator_dedupe_bridge(tmp),
                point_in_time_vix_bucket_path=self._ready_vix(tmp),
                forward_holdout_contract_path=self._holdout(tmp),
                evidence_paths=[exact],
            )

        self.assertEqual(report["status"], "blocked_flow_extreme_ratio_backspread_replay_readiness")
        self.assertNotIn("missing_full_denominator_mapping", report["blockers"])
        self.assertIn("missing_strict_new_dedupe", report["blockers"])

    def test_write_outputs_writes_latest_and_docs(self) -> None:
        with WorkspaceTempDir(prefix="flow-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            evidence = tmp / "evidence.py"
            _write_text(evidence, "overextension")
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_preregistration(tmp),
                feature_store_path=self._feature_store(tmp),
                point_in_time_flow_extreme_input_path=self._blocked_flow_input(tmp),
                multi_leg_side_aware_pricing_capability_path=self._blocked_pricing_capability(tmp),
                flow_extreme_denominator_dedupe_bridge_path=self._blocked_denominator_dedupe_bridge(tmp),
                point_in_time_vix_bucket_path=self._blocked_vix(tmp),
                forward_holdout_contract_path=self._holdout(tmp),
                evidence_paths=[evidence],
            )
            artifacts = readiness.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "docs" / "readiness.md")

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "readiness.md").exists())
            self.assertIn("docs_report", artifacts)
            markdown = (tmp / "docs" / "readiness.md").read_text(encoding="utf8")
            self.assertIn("Regular Options Flow-Extreme Ratio/Backspread Replay Readiness", markdown)
            self.assertIn("Critical Prerequisites", markdown)


if __name__ == "__main__":
    unittest.main()
