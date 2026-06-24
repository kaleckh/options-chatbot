from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

from scripts import build_regular_options_term_structure_calendar_structure_harness as harness
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _playbook(tmp: Path, *, geometry: bool = False) -> Path:
    payload = {
        "report_id": "regular_options_preregistered_term_structure_calendar_playbook",
        "status": "preregistered_design_only",
        "concept_id": harness.CONCEPT_ID,
        "structure": harness.EXPECTED_STRUCTURE,
        "accepted_profitability": False,
    }
    if geometry:
        payload["candidate_geometry"] = {
            "front_back_expiry_spacing": "30_60_dte",
            "strike_delta_or_moneyness_rule": "same_strike_or_fixed_delta_proxy",
            "max_debit": 4.0,
            "max_bid_ask_width": 0.25,
            "exit_policy": "time_exit_or_front_expiry",
        }
    path = tmp / "playbook.json"
    _write_json(path, payload)
    return path


def _readiness(tmp: Path) -> Path:
    path = tmp / "readiness.json"
    _write_json(
        path,
        {
            "report_id": "regular_options_term_structure_calendar_replay_readiness",
            "status": "blocked_term_structure_calendar_replay_readiness",
            "blockers": [
                "missing_calendar_diagonal_side_aware_pricing_engine",
                "missing_calendar_diagonal_exit_or_expiry_engine",
                "missing_full_denominator_status_mapping",
                "missing_front_leg_assignment_expiration_classifier",
                "missing_roll_or_expiry_policy",
                "missing_point_in_time_term_structure_inputs",
                "missing_index_calendar_quote_surface",
                "missing_strict_new_dedupe",
            ],
        },
    )
    return path


def _candidate(**overrides) -> dict:
    row = {
        "ticker": "SPY",
        "entry_date": "2026-05-20",
        "long_back_month_ask": 6.5,
        "short_front_month_bid": 2.0,
        "long_back_month_bid": 7.2,
        "short_front_month_ask": 1.0,
        "fees_usd": 2.0,
        "slippage_usd": 1.0,
        "exercise_style": "american",
    }
    row.update(overrides)
    return row


class RegularOptionsTermStructureCalendarStructureHarnessTests(unittest.TestCase):
    def test_side_aware_calendar_math_and_pnl(self) -> None:
        row = _candidate()
        classified = harness.classify_candidate(row)

        self.assertEqual(harness.entry_debit(row), 4.5)
        self.assertEqual(harness.exit_value(row), 6.2)
        self.assertEqual(harness.max_loss_usd(row, 4.5), 453.0)
        self.assertEqual(harness.net_pnl_usd(row, 4.5, 6.2), 167.0)
        self.assertEqual(classified["denominator_status"], "exact_exit_captured")
        self.assertEqual(classified["assignment_expiration"]["classification"], "etf_american_front_assignment_exposure")

    def test_missing_zero_front_expiry_holdout_and_future_extension_statuses(self) -> None:
        missing = harness.classify_candidate(_candidate(long_back_month_ask=None))
        zero = harness.classify_candidate(_candidate(long_back_month_ask=1.0, short_front_month_bid=2.0))
        front_expired = harness.classify_candidate(_candidate(long_back_month_bid=None, short_front_month_ask=None, front_leg_expired=True))
        holdout = harness.classify_candidate(_candidate(entry_date="2026-06-01"))
        future = harness.classify_candidate(_candidate(ticker="IWM"))

        self.assertEqual(missing["denominator_status"], "missing_leg_quote")
        self.assertEqual(zero["denominator_status"], "zero_bid_or_untradable")
        self.assertEqual(front_expired["denominator_status"], "front_expired_waiting_back_exit")
        self.assertEqual(holdout["denominator_status"], "protected_holdout_blocked")
        self.assertEqual(future["denominator_status"], "rejected_geometry")

    def test_report_resolves_mechanics_and_preserves_input_blockers(self) -> None:
        with WorkspaceTempDir(prefix="term-harness") as tmp_dir:
            tmp = Path(tmp_dir)
            report = harness.build_report(
                preregistered_playbook_path=_playbook(tmp),
                readiness_path=_readiness(tmp),
                feature_store_report_path=tmp / "missing_feature.json",
                quote_surface_report_path=tmp / "missing_quote.json",
                generated_at_utc="2026-06-23T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_term_structure_calendar_structure_harness")
        self.assertIn("missing_point_in_time_term_structure_inputs", report["remaining_blockers"])
        self.assertIn("missing_index_calendar_quote_surface", report["remaining_blockers"])
        self.assertIn("missing_preregistered_calendar_diagonal_geometry", report["remaining_blockers"])
        self.assertIn("missing_strict_new_dedupe", report["remaining_blockers"])
        burndown = {row["blocker"]: row["status"] for row in report["blocker_burndown"]}
        self.assertEqual(burndown["missing_calendar_diagonal_side_aware_pricing_engine"], "satisfied_by_harness")
        self.assertEqual(burndown["missing_roll_or_expiry_policy"], "satisfied_by_harness")
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["historical_replay_performed"])

    def test_ready_status_requires_geometry_inputs_quote_surface_and_dedupe(self) -> None:
        with WorkspaceTempDir(prefix="term-harness") as tmp_dir:
            tmp = Path(tmp_dir)
            feature = tmp / "feature.json"
            quote = tmp / "quote.json"
            _write_json(feature, {"point_in_time_term_structure_inputs_ready": True, "point_in_time_vix_bucket_ready": True})
            _write_json(quote, {"calendar_diagonal_quote_surface_ready": True, "symbols_ready": ["SPY", "QQQ"]})
            readiness = tmp / "readiness.json"
            _write_json(readiness, {"status": "blocked", "blockers": []})
            report = harness.build_report(
                preregistered_playbook_path=_playbook(tmp, geometry=True),
                readiness_path=readiness,
                feature_store_report_path=feature,
                quote_surface_report_path=quote,
            )

        self.assertEqual(report["status"], "blocked_term_structure_calendar_structure_harness")
        self.assertEqual(report["remaining_blockers"], ["missing_strict_new_dedupe"])

    def test_invalid_preregistration_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="term-harness") as tmp_dir:
            tmp = Path(tmp_dir)
            invalid = tmp / "bad.json"
            _write_json(invalid, {"status": "implemented", "concept_id": "wrong", "accepted_profitability": True})
            report = harness.build_report(
                preregistered_playbook_path=invalid,
                readiness_path=_readiness(tmp),
                feature_store_report_path=tmp / "missing_feature.json",
                quote_surface_report_path=tmp / "missing_quote.json",
            )

        self.assertEqual(report["status"], "blocked_invalid_term_structure_calendar_preregistration")
        self.assertFalse(report["preregistration_validation"]["valid"])
        self.assertEqual(report["blocker_burndown"], [])

    def test_write_outputs_writes_latest_and_docs(self) -> None:
        with WorkspaceTempDir(prefix="term-harness") as tmp_dir:
            tmp = Path(tmp_dir)
            report = harness.build_report(
                preregistered_playbook_path=_playbook(tmp),
                readiness_path=_readiness(tmp),
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
