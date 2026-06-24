from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_regular_options_59_symbol_thetadata_opra_import_repair as repair
from workspace_tempdir import WorkspaceTempDir


def _create_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.execute(
        """
        CREATE TABLE import_batches (
            id INTEGER PRIMARY KEY,
            source_label TEXT,
            data_trust TEXT,
            imported_at_utc TEXT
        )
        """
    )
    con.execute(
        """
        CREATE TABLE option_quote_snapshots (
            id INTEGER PRIMARY KEY,
            as_of_utc TEXT,
            quote_date_et TEXT,
            quote_minute_et INTEGER,
            snapshot_kind TEXT,
            underlying TEXT,
            contract_symbol TEXT,
            expiry TEXT,
            option_type TEXT,
            strike REAL,
            bid REAL,
            ask REAL,
            source_batch_id INTEGER
        )
        """
    )
    con.commit()
    con.close()


class RegularOptions59SymbolThetaDataImportResumeTests(unittest.TestCase):
    def test_resume_parks_without_import_when_theta_terminal_unavailable(self) -> None:
        with WorkspaceTempDir(prefix="repair59-resume") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            with patch.object(repair, "check_theta_terminal", return_value={"available": False, "status": "unavailable"}):
                report = repair.build_report(
                    db_path=db,
                    output_dir=tmp / "out",
                    docs_report=tmp / "doc.md",
                    dry_run=True,
                    resume_missing_only=True,
                    provider_recheck=True,
                )

            self.assertEqual(report["status"], "blocked_thetaterminal_source_unavailable_retry")
            self.assertFalse(report["import_attempted"])
            self.assertFalse(report["quotes_imported"])
            self.assertFalse(report["accepted_profitability"])
            self.assertFalse(report["historical_rows_are_forward_proof"])
            self.assertEqual(report["protected_holdout_overlap_rows"], 0)
            self.assertEqual(report["outside_universe_import_rows"], 0)
            self.assertEqual(report["missing_symbol_date_manifest_row_count"], report["missing_symbol_date_count"])
            self.assertTrue((tmp / "out" / "missing_symbol_date_manifest.jsonl").exists())
            self.assertTrue((tmp / "out" / "post_import_coverage.json").exists())

    def test_resume_requires_provider_recheck(self) -> None:
        with WorkspaceTempDir(prefix="repair59-resume") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            with patch.object(repair, "check_theta_terminal", return_value={"available": True, "status": "available"}):
                report = repair.build_report(
                    db_path=db,
                    output_dir=tmp / "out",
                    docs_report=tmp / "doc.md",
                    dry_run=True,
                    resume_missing_only=True,
                    provider_recheck=False,
                )

        self.assertEqual(report["status"], "blocked_provider_recheck_required_for_resume")
        self.assertIn("provider_recheck_required_for_resume", report["blockers"])

    def test_resume_import_requires_approval_token_even_when_provider_available(self) -> None:
        with WorkspaceTempDir(prefix="repair59-resume") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            with patch.object(repair, "check_theta_terminal", return_value={"available": True, "status": "available"}):
                report = repair.build_report(
                    db_path=db,
                    output_dir=tmp / "out",
                    docs_report=tmp / "doc.md",
                    dry_run=False,
                    resume_missing_only=True,
                    provider_recheck=True,
                    approval_token=None,
                )

        self.assertEqual(report["status"], "blocked_import_approval_token_missing")
        self.assertFalse(report["import_attempted"])
        self.assertIn("approval_token_missing_or_invalid", report["blockers"])

    def test_resume_enforces_exact_universe_and_holdout_boundary(self) -> None:
        with WorkspaceTempDir(prefix="repair59-resume") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            with patch.object(repair, "check_theta_terminal", return_value={"available": True, "status": "available"}):
                report = repair.build_report(
                    db_path=db,
                    output_dir=tmp / "out",
                    docs_report=tmp / "doc.md",
                    dry_run=True,
                    resume_missing_only=True,
                    provider_recheck=True,
                    universe=["SPY"],
                    end_date="2026-06-05",
                )

        self.assertIn("canonical_59_symbol_universe_mismatch", report["blockers"])
        self.assertIn("date_window_exceeds_as_of_or_pre_holdout_boundary", report["blockers"])
        self.assertFalse(report["protected_holdout_consumed"])


if __name__ == "__main__":
    unittest.main()
