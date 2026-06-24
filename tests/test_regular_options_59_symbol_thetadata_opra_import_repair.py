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


class RegularOptions59SymbolThetaDataImportRepairTests(unittest.TestCase):
    def test_dry_run_blocks_when_theta_terminal_unavailable(self) -> None:
        with WorkspaceTempDir(prefix="repair59") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            with patch.object(repair, "check_theta_terminal", return_value={"available": False, "status": "unavailable"}):
                report = repair.build_report(db_path=db, output_dir=tmp / "out", docs_report=tmp / "doc.md", dry_run=True)

        self.assertEqual(report["status"], "blocked_thetaterminal_source_unavailable")
        self.assertFalse(report["quotes_imported"])
        self.assertFalse(report["broker_order_allowed"])
        self.assertIn("thetaterminal_source_unavailable", report["blockers"])

    def test_import_requires_exact_token(self) -> None:
        with WorkspaceTempDir(prefix="repair59") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            with patch.object(repair, "check_theta_terminal", return_value={"available": True, "status": "available"}):
                report = repair.build_report(db_path=db, output_dir=tmp / "out", docs_report=tmp / "doc.md", dry_run=False, approval_token=None)

        self.assertEqual(report["status"], "blocked_import_approval_token_missing")
        self.assertIn("approval_token_missing_or_invalid", report["blockers"])
        self.assertFalse(report["import_attempted"])

    def test_canonical_universe_exactness_is_enforced(self) -> None:
        with WorkspaceTempDir(prefix="repair59") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            with patch.object(repair, "check_theta_terminal", return_value={"available": True, "status": "available"}):
                report = repair.build_report(db_path=db, output_dir=tmp / "out", docs_report=tmp / "doc.md", dry_run=True, universe=["SPY"])

        self.assertEqual(report["status"], "blocked_canonical_universe_mismatch")
        self.assertIn("canonical_59_symbol_universe_mismatch", report["blockers"])

    def test_holdout_window_guard_blocks_dates_after_as_of(self) -> None:
        with WorkspaceTempDir(prefix="repair59") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            with patch.object(repair, "check_theta_terminal", return_value={"available": True, "status": "available"}):
                report = repair.build_report(db_path=db, output_dir=tmp / "out", docs_report=tmp / "doc.md", dry_run=True, end_date="2026-06-05")

        self.assertIn("date_window_exceeds_as_of_or_pre_holdout_boundary", report["blockers"])
        self.assertFalse(report["protected_holdout_consumed"])

    def test_outputs_are_written(self) -> None:
        with WorkspaceTempDir(prefix="repair59") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            with patch.object(repair, "check_theta_terminal", return_value={"available": False, "status": "unavailable"}):
                repair.build_report(db_path=db, output_dir=tmp / "out", docs_report=tmp / "doc.md", dry_run=True)
            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "universe.json").exists())
            self.assertTrue((tmp / "out" / "missing_symbol_date_manifest.jsonl").exists())
            self.assertTrue((tmp / "doc.md").exists())


if __name__ == "__main__":
    unittest.main()
