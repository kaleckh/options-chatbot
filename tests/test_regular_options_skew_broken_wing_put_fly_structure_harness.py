from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

from scripts import build_regular_options_skew_broken_wing_put_fly_structure_harness as harness
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _playbook(tmp: Path, *, valid: bool = True) -> Path:
    payload = {
        "report_id": "regular_options_preregistered_skew_broken_wing_playbook",
        "status": "preregistered_design_only" if valid else "implemented",
        "concept_id": harness.CONCEPT_ID if valid else "wrong",
        "structure": harness.EXPECTED_STRUCTURE if valid else "wrong",
        "accepted_profitability": False,
    }
    path = tmp / "playbook.json"
    _write_json(path, payload)
    return path


def _candidate(**overrides) -> dict:
    row = {
        "ticker": "SPY",
        "entry_date": "2026-05-20",
        "expiration": "2026-06-19",
        "upper_strike": 525,
        "middle_strike": 515,
        "lower_strike": 500,
        "upper_long_put_ask": 13.0,
        "middle_short_put_bid": 7.0,
        "lower_long_put_ask": 2.5,
        "upper_long_put_bid": 15.0,
        "middle_short_put_ask": 6.0,
        "lower_long_put_bid": 2.0,
        "fees_usd": 2.0,
        "slippage_usd": 1.0,
        "exercise_style": "american",
        "quote_basis": "trusted_opra_nbbo_bid_ask",
    }
    row.update(overrides)
    return row


class RegularOptionsSkewBrokenWingStructureHarnessTests(unittest.TestCase):
    def test_side_aware_entry_exit_net_and_credit_debit_cases(self) -> None:
        debit_row = _candidate()
        credit_row = _candidate(upper_long_put_ask=8.0, middle_short_put_bid=7.0, lower_long_put_ask=2.5)

        classified = harness.classify_candidate(debit_row)
        credit = harness.classify_candidate(credit_row)

        self.assertEqual(harness.side_aware_entry_cost(debit_row), 1.5)
        self.assertEqual(harness.side_aware_exit_value(debit_row), 5.0)
        self.assertEqual(harness.net_pnl_usd(debit_row, 1.5, 5.0), 347.0)
        self.assertEqual(classified["denominator_status"], "exact_exit_priced")
        self.assertEqual(classified["entry_type"], "debit")
        self.assertEqual(credit["entry_type"], "credit")
        self.assertEqual(harness.side_aware_entry_cost(credit_row), -3.5)

    def test_max_loss_uses_expiry_payoff_grid(self) -> None:
        row = _candidate()
        loss = harness.max_loss_usd(row, harness.side_aware_entry_cost(row))

        self.assertEqual(loss, 653.0)
        self.assertEqual(harness.expiry_position_value(row, 515), 10.0)
        self.assertEqual(harness.expiry_position_value(row, 600), 0.0)

    def test_geometry_and_quote_rejections(self) -> None:
        unordered = harness.classify_candidate(_candidate(upper_strike=515, middle_strike=525))
        equal_width = harness.classify_candidate(_candidate(upper_strike=530, middle_strike=515, lower_strike=500))
        missing = harness.classify_candidate(_candidate(upper_long_put_ask=None))
        zero = harness.classify_candidate(_candidate(middle_short_put_bid=0.0))
        non_proof = harness.classify_candidate(_candidate(quote_basis="midpoint_model"))

        self.assertEqual(unordered["denominator_status"], "rejected_geometry")
        self.assertEqual(equal_width["denominator_status"], "rejected_geometry")
        self.assertEqual(missing["denominator_status"], "missing_leg_quote")
        self.assertEqual(zero["denominator_status"], "zero_bid_or_untradable")
        self.assertEqual(non_proof["denominator_status"], "missing_leg_quote")
        self.assertIn("non_proof_quote_basis", non_proof["blockers"])

    def test_mixed_expiration_assignment_holdout_and_identity(self) -> None:
        mixed = harness.classify_candidate(
            _candidate(
                legs=[
                    {"role": "upper_long", "option_type": "put", "expiration": "2026-06-19"},
                    {"role": "middle_short", "option_type": "put", "expiration": "2026-06-26"},
                    {"role": "lower_long", "option_type": "put", "expiration": "2026-06-19"},
                ]
            )
        )
        assignment = harness.classify_candidate(_candidate(assignment_or_expiration_unresolved=True))
        holdout = harness.classify_candidate(_candidate(entry_date="2026-06-01"))
        identity = harness.strict_new_identity(_candidate(entry_timestamp="2026-05-20T15:00:00Z", pricing_timestamp_basis="entry_nbbo"))

        self.assertEqual(mixed["denominator_status"], "rejected_geometry")
        self.assertEqual(assignment["denominator_status"], "assignment_or_expiration_blocked")
        self.assertEqual(holdout["denominator_status"], "protected_holdout_blocked")
        self.assertIn("skew_broken_wing_put_fly|SPY|2026-05-20T15:00:00Z", identity)
        self.assertIn("|525.0|515.0|500.0|entry_nbbo|", identity)

    def test_report_blocks_on_missing_input_surfaces_and_preserves_read_only_flags(self) -> None:
        with WorkspaceTempDir(prefix="skew-harness") as tmp_dir:
            tmp = Path(tmp_dir)
            report = harness.build_report(
                preregistered_playbook_path=_playbook(tmp),
                feature_store_report_path=tmp / "missing_feature.json",
                quote_surface_report_path=tmp / "missing_quote.json",
                generated_at_utc="2026-06-23T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_skew_broken_wing_structure_harness")
        self.assertIn("missing_point_in_time_vix_bucket", report["remaining_blockers"])
        self.assertIn("missing_point_in_time_downside_skew_inputs", report["remaining_blockers"])
        self.assertIn("missing_index_broken_wing_quote_surface", report["remaining_blockers"])
        self.assertFalse(report["historical_replay_performed"])
        self.assertFalse(report["lane_implementation_performed"])
        self.assertFalse(report["accepted_profitability"])

    def test_ready_status_requires_all_read_only_inputs(self) -> None:
        with WorkspaceTempDir(prefix="skew-harness") as tmp_dir:
            tmp = Path(tmp_dir)
            feature = tmp / "feature.json"
            quote = tmp / "quote.json"
            _write_json(feature, {"point_in_time_vix_bucket_ready": True, "point_in_time_downside_skew_ready": True})
            _write_json(quote, {"skew_broken_wing_quote_surface_ready": True, "symbols_ready": ["SPY", "QQQ", "IWM", "DIA"]})
            report = harness.build_report(
                preregistered_playbook_path=_playbook(tmp),
                feature_store_report_path=feature,
                quote_surface_report_path=quote,
            )

        self.assertEqual(report["status"], "ready_for_skew_broken_wing_bounded_read_only_replay")
        self.assertEqual(report["remaining_blockers"], [])

    def test_invalid_preregistration_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="skew-harness") as tmp_dir:
            tmp = Path(tmp_dir)
            report = harness.build_report(
                preregistered_playbook_path=_playbook(tmp, valid=False),
                feature_store_report_path=tmp / "missing_feature.json",
                quote_surface_report_path=tmp / "missing_quote.json",
            )

        self.assertEqual(report["status"], "blocked_invalid_skew_broken_wing_preregistration")
        self.assertFalse(report["preregistration_validation"]["valid"])
        self.assertEqual(report["blocker_burndown"], [])

    def test_write_outputs_writes_latest_and_docs(self) -> None:
        with WorkspaceTempDir(prefix="skew-harness") as tmp_dir:
            tmp = Path(tmp_dir)
            report = harness.build_report(
                preregistered_playbook_path=_playbook(tmp),
                feature_store_report_path=tmp / "missing_feature.json",
                quote_surface_report_path=tmp / "missing_quote.json",
            )
            artifacts = harness.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "docs" / "harness.md")

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "harness.md").exists())
            self.assertIn("docs_report", artifacts)

    def test_harness_does_not_call_scanner_or_trading_paths(self) -> None:
        source = Path(harness.__file__).read_text(encoding="utf8")
        tree = ast.parse(source)
        called_names: set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                called_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_names.add(node.func.attr)
        forbidden_calls = {"run_daily_ops", "log_scan_picks", "validate_pending_scan_candidates", "submit_order", "create_position", "auto_track", "import_quotes"}
        self.assertTrue(forbidden_calls.isdisjoint(called_names))


if __name__ == "__main__":
    unittest.main()
