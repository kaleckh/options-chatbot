from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

from scripts import build_regular_options_vrp_credit_spread_structure_harness as harness
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _valid_preregistration(tmp: Path) -> Path:
    path = tmp / "playbook.json"
    _write_json(
        path,
        {
            "report_id": "regular_options_preregistered_vrp_credit_spread_playbook",
            "status": "preregistered_design_only",
            "concept_id": harness.CONCEPT_ID,
            "structure": harness.EXPECTED_STRUCTURE,
            "accepted_profitability": False,
        },
    )
    return path


def _readiness(tmp: Path) -> Path:
    path = tmp / "readiness.json"
    _write_json(
        path,
        {
            "report_id": "regular_options_vrp_credit_spread_replay_readiness",
            "status": "blocked_vrp_credit_spread_replay_readiness",
            "blockers": [
                "missing_credit_spread_side_aware_pricing_engine",
                "missing_credit_spread_side_aware_exit_pricing_engine",
                "missing_full_denominator_status_mapping",
                "missing_assignment_expiration_classifier",
                "missing_margin_max_loss_convention",
                "missing_point_in_time_vix_bucket",
                "missing_index_credit_spread_quote_surface",
                "missing_protected_holdout_guard",
            ],
        },
    )
    return path


def _candidate(**overrides) -> dict:
    row = {
        "ticker": "SPY",
        "entry_date": "2026-05-20",
        "short_put_bid": 2.0,
        "long_put_ask": 0.75,
        "short_put_ask": 0.9,
        "long_put_bid": 0.25,
        "short_strike": 500,
        "long_strike": 495,
        "fees_usd": 2.0,
        "slippage_usd": 1.0,
        "exercise_style": "american",
    }
    row.update(overrides)
    return row


class RegularOptionsVrpCreditSpreadStructureHarnessTests(unittest.TestCase):
    def test_pricing_margin_and_closed_pnl_are_side_aware(self) -> None:
        row = _candidate()
        classified = harness.classify_candidate(row)

        self.assertEqual(harness.entry_credit(row), 1.25)
        self.assertEqual(harness.exit_debit(row), 0.65)
        self.assertEqual(harness.max_loss_usd(row, 1.25), 378.0)
        self.assertEqual(classified["denominator_status"], "exact_closed")
        self.assertEqual(classified["net_pnl_usd"], 57.0)
        self.assertEqual(classified["assignment_expiration"]["classification"], "etf_american_assignment_exposure")

    def test_expiration_settlement_uses_intrinsic_vertical_value(self) -> None:
        row = _candidate(
            short_put_ask=None,
            long_put_bid=None,
            expiration_date="2026-05-31",
            underlying_close=497,
        )
        classified = harness.classify_candidate(row)

        self.assertEqual(harness.expiration_settlement_debit(row), 3.0)
        self.assertEqual(classified["denominator_status"], "expired_settled")
        self.assertEqual(classified["net_pnl_usd"], -178.0)

    def test_rejects_zero_credit_missing_quote_malformed_and_holdout_rows(self) -> None:
        zero_credit = harness.classify_candidate(_candidate(short_put_bid=0.5, long_put_ask=0.75))
        missing_quote = harness.classify_candidate(_candidate(short_put_bid=None))
        malformed = harness.classify_candidate(_candidate(ticker="TSLA"))
        holdout = harness.classify_candidate(_candidate(entry_date="2026-06-01"))

        self.assertEqual(zero_credit["denominator_status"], "zero_bid_untradable")
        self.assertEqual(missing_quote["denominator_status"], "missing_required_quote")
        self.assertEqual(malformed["denominator_status"], "malformed_candidate")
        self.assertEqual(holdout["denominator_status"], "protected_holdout_blocked")

    def test_unknown_assignment_metadata_fails_closed(self) -> None:
        classified = harness.classify_candidate(
            _candidate(ticker="DIA", exercise_style="", settlement_style="", short_put_ask=None, long_put_bid=None)
        )

        self.assertEqual(classified["denominator_status"], "entry_priced_exit_missing")
        self.assertEqual(classified["assignment_expiration"]["classification"], "etf_american_assignment_exposure")

        unknown = harness.assignment_expiration_classification({"ticker": "ABC"})
        self.assertEqual(unknown["status"], "blocked")
        self.assertEqual(unknown["blocker"], "assignment_expiration_metadata_uncertain")

    def test_report_resolves_structure_blockers_and_fails_closed_on_missing_inputs(self) -> None:
        with WorkspaceTempDir(prefix="vrp-structure") as tmp_dir:
            tmp = Path(tmp_dir)
            report = harness.build_report(
                preregistered_playbook_path=_valid_preregistration(tmp),
                readiness_path=_readiness(tmp),
                feature_store_report_path=tmp / "missing_feature.json",
                quote_surface_report_path=tmp / "missing_quote.json",
                generated_at_utc="2026-06-23T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_vrp_credit_spread_structure_harness")
        for key, expected in harness.READ_ONLY_FLAGS.items():
            self.assertIs(report[key], expected)
        self.assertIn("missing_point_in_time_vix_bucket", report["remaining_blockers"])
        self.assertIn("missing_index_credit_spread_quote_surface", report["remaining_blockers"])
        burndown = {row["blocker"]: row["status"] for row in report["blocker_burndown"]}
        self.assertEqual(burndown["missing_credit_spread_side_aware_pricing_engine"], "resolved_by_harness")
        self.assertEqual(burndown["missing_assignment_expiration_classifier"], "resolved_by_harness")
        self.assertEqual(burndown["missing_protected_holdout_guard"], "resolved_by_harness")

    def test_ready_status_requires_vix_and_quote_surface_inputs(self) -> None:
        with WorkspaceTempDir(prefix="vrp-structure") as tmp_dir:
            tmp = Path(tmp_dir)
            feature = tmp / "feature.json"
            quote = tmp / "quote.json"
            _write_json(feature, {"point_in_time_vix_bucket_ready": True})
            _write_json(quote, {"credit_spread_quote_surface_ready": True, "symbols_ready": ["SPY", "QQQ", "IWM", "DIA"]})
            report = harness.build_report(
                preregistered_playbook_path=_valid_preregistration(tmp),
                readiness_path=_readiness(tmp),
                feature_store_report_path=feature,
                quote_surface_report_path=quote,
            )

        self.assertEqual(report["status"], "ready_for_bounded_read_only_vrp_replay")
        self.assertEqual(report["remaining_blockers"], [])

    def test_invalid_preregistration_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="vrp-structure") as tmp_dir:
            tmp = Path(tmp_dir)
            invalid = tmp / "bad.json"
            _write_json(invalid, {"status": "implemented", "concept_id": "wrong", "accepted_profitability": True})
            report = harness.build_report(
                preregistered_playbook_path=invalid,
                readiness_path=_readiness(tmp),
                feature_store_report_path=tmp / "missing_feature.json",
                quote_surface_report_path=tmp / "missing_quote.json",
            )

        self.assertEqual(report["status"], "blocked_invalid_vrp_preregistration")
        self.assertFalse(report["preregistration_validation"]["valid"])
        self.assertEqual(report["blocker_burndown"], [])

    def test_write_outputs_writes_latest_and_docs(self) -> None:
        with WorkspaceTempDir(prefix="vrp-structure") as tmp_dir:
            tmp = Path(tmp_dir)
            report = harness.build_report(
                preregistered_playbook_path=_valid_preregistration(tmp),
                readiness_path=_readiness(tmp),
                feature_store_report_path=tmp / "missing_feature.json",
                quote_surface_report_path=tmp / "missing_quote.json",
            )
            artifacts = harness.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "docs" / "harness.md")

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "harness.md").exists())
            self.assertIn("docs_report", artifacts)
            markdown = (tmp / "docs" / "harness.md").read_text(encoding="utf8")
            self.assertIn("Regular Options VRP Credit Spread Structure Harness", markdown)
            self.assertIn("Blocker Burndown", markdown)

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

        forbidden_calls = {
            "run_daily_ops",
            "log_scan_picks",
            "validate_pending_scan_candidates",
            "submit_order",
            "create_position",
            "auto_track",
            "import_quotes",
        }
        self.assertTrue(forbidden_calls.isdisjoint(called_names))


if __name__ == "__main__":
    unittest.main()
