from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_regular_options_base_clean_stack_identity_ledger as ledger
from workspace_tempdir import WorkspaceTempDir


FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "regular_options_base_clean_stack_identity_ledger"
    / "ready_rows.json"
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _row(**patch: object) -> dict:
    row = {
        "candidate_source_id": "fixture_candidate",
        "direction": "long_call_spread",
        "entry_contract_resolution": "exact_contracts",
        "entry_date": "2026-05-01",
        "exact_priced": True,
        "exit_date": "2026-05-08",
        "lane_family": "bullish_pullback",
        "lane_id": "bullish_pullback_core",
        "long_contract_symbol": "QQQ260508C00490000",
        "pnl_pct": 0.24,
        "portfolio_eligible": True,
        "proof_grade": "exact",
        "short_contract_symbol": "QQQ260508C00495000",
        "source_playbook": "bullish_pullback_core_v1",
        "source_result_path": "fixture/source.json",
        "strategy_type": "debit_vertical",
        "ticker": "QQQ",
    }
    row.update(patch)
    return row


class RegularOptionsBaseCleanStackIdentityLedgerTests(unittest.TestCase):
    def test_fixture_rows_can_build_ready_read_only_identity_ledger(self) -> None:
        report = ledger.build_report(
            source_rows_path=FIXTURE,
            expected_base_clean_rows=3,
            generated_at_utc="2026-06-23T00:00:00Z",
        )

        self.assertEqual(report["status"], "base_clean_stack_identity_ledger_ready")
        self.assertEqual(report["ledger_row_count"], 3)
        self.assertEqual(report["unique_identity_count"], 3)
        self.assertEqual(report["duplicate_identity_count"], 0)
        self.assertEqual(report["missing_identity_field_row_count"], 0)
        self.assertEqual(report["future_or_outcome_field_dependency_count"], 0)
        self.assertEqual(report["protected_holdout_overlap_count"], 0)
        self.assertEqual(report["proof_row_count"], 0)
        self.assertFalse(report["accepted_profitability"])
        self.assertTrue(report["read_only"])
        self.assertEqual(report["blockers"], [])
        identity = report["ledger_entries"][0]["identity_payload"]
        self.assertNotIn("pnl_pct", identity)
        self.assertNotIn("exit_date", identity)

    def test_aggregate_only_source_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="base-ledger") as tmp_dir:
            source = Path(tmp_dir) / "aggregate.json"
            _write_json(source, {"base_clean_stack": {"exact_rows": 157}})
            report = ledger.build_report(source_rows_path=source, expected_base_clean_rows=157)

        self.assertEqual(report["status"], "blocked_base_clean_stack_identity_ledger")
        self.assertIn("aggregate_only_base_stack_not_acceptable", report["blockers"])
        self.assertIn("base_clean_stack_row_source_missing", report["blockers"])

    def test_missing_required_identity_field_blocks(self) -> None:
        with WorkspaceTempDir(prefix="base-ledger") as tmp_dir:
            source = Path(tmp_dir) / "rows.json"
            _write_json(source, {"rows": [_row(short_contract_symbol="")]})
            report = ledger.build_report(source_rows_path=source, expected_base_clean_rows=1)

        self.assertEqual(report["status"], "blocked_base_clean_stack_identity_ledger")
        self.assertIn("missing_required_identity_fields", report["blockers"])
        self.assertEqual(report["missing_identity_field_row_count"], 1)
        self.assertIn("short_contract_symbol", report["ledger_entries"][0]["missing_identity_fields"])

    def test_duplicate_identity_hash_blocks(self) -> None:
        with WorkspaceTempDir(prefix="base-ledger") as tmp_dir:
            source = Path(tmp_dir) / "rows.json"
            _write_json(source, {"rows": [_row(), _row()]})
            report = ledger.build_report(source_rows_path=source, expected_base_clean_rows=2)

        self.assertEqual(report["status"], "blocked_base_clean_stack_identity_ledger")
        self.assertIn("duplicate_base_identity_hashes", report["blockers"])
        self.assertEqual(report["duplicate_identity_count"], 1)

    def test_declared_future_or_pnl_identity_dependency_blocks(self) -> None:
        with WorkspaceTempDir(prefix="base-ledger") as tmp_dir:
            source = Path(tmp_dir) / "rows.json"
            _write_json(source, {"rows": [_row(identity_fields=["ticker", "entry_date", "pnl_pct"])]})
            report = ledger.build_report(source_rows_path=source, expected_base_clean_rows=1)

        self.assertEqual(report["status"], "blocked_base_clean_stack_identity_ledger")
        self.assertIn("future_field_dependency_detected", report["blockers"])
        self.assertEqual(report["future_or_outcome_field_dependency_count"], 1)

    def test_protected_holdout_overlap_blocks(self) -> None:
        with WorkspaceTempDir(prefix="base-ledger") as tmp_dir:
            source = Path(tmp_dir) / "rows.json"
            _write_json(source, {"rows": [_row(entry_date="2026-06-05")]})
            report = ledger.build_report(source_rows_path=source, expected_base_clean_rows=1)

        self.assertEqual(report["status"], "blocked_base_clean_stack_identity_ledger")
        self.assertIn("protected_holdout_overlap_detected", report["blockers"])
        self.assertEqual(report["protected_holdout_overlap_count"], 1)

    def test_write_outputs_writes_latest_and_docs(self) -> None:
        with WorkspaceTempDir(prefix="base-ledger") as tmp_dir:
            tmp = Path(tmp_dir)
            report = ledger.build_report(source_rows_path=FIXTURE, expected_base_clean_rows=3)
            artifacts = ledger.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "docs" / "ledger.md")

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "ledger.md").exists())
            self.assertIn("docs_report", artifacts)
            self.assertIn("Base Clean Stack Identity Ledger", (tmp / "docs" / "ledger.md").read_text(encoding="utf8"))


if __name__ == "__main__":
    unittest.main()
