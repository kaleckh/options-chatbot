from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from scripts import build_regular_options_fresh_window_import_scheduler_health as health
from scripts import import_regular_options_fresh_window_thetadata_opra as importer


def _init_store(path: Path, max_date: str = "2026-06-08") -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE import_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_label TEXT NOT NULL,
            dataset_kind TEXT NOT NULL,
            data_trust TEXT NOT NULL,
            input_path TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            imported_at_utc TEXT NOT NULL,
            total_rows INTEGER NOT NULL,
            imported_rows INTEGER NOT NULL,
            duplicate_rows INTEGER NOT NULL,
            rejected_rows INTEGER NOT NULL,
            warnings_json TEXT NOT NULL
        );
        CREATE TABLE option_quote_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            as_of_utc TEXT NOT NULL,
            quote_date_et TEXT NOT NULL,
            quote_minute_et INTEGER NOT NULL,
            snapshot_kind TEXT NOT NULL,
            underlying TEXT NOT NULL,
            contract_symbol TEXT NOT NULL,
            expiry TEXT NOT NULL,
            option_type TEXT NOT NULL,
            strike REAL NOT NULL,
            bid REAL,
            ask REAL,
            last REAL,
            iv REAL,
            underlying_price REAL,
            volume INTEGER,
            open_interest INTEGER,
            source_batch_id INTEGER NOT NULL
        );
        """
    )
    conn.execute(
        """
        INSERT INTO import_batches (
            source_label, dataset_kind, data_trust, input_path, file_hash, imported_at_utc,
            total_rows, imported_rows, duplicate_rows, rejected_rows, warnings_json
        ) VALUES ('thetadata_opra_nbbo_1m', 'intraday_csv', 'trusted', 'seed.csv', 'hash', '2026-07-02T00:00:00Z', 1, 1, 0, 0, '[]')
        """
    )
    batch_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        """
        INSERT INTO option_quote_snapshots (
            as_of_utc, quote_date_et, quote_minute_et, snapshot_kind, underlying, contract_symbol,
            expiry, option_type, strike, bid, ask, source_batch_id
        ) VALUES (?, ?, 955, 'intraday', 'SPY', 'SPY260717C00500000', '2026-07-17', 'call', 500, 1.0, 1.1, ?)
        """,
        (f"{max_date}T19:55:00Z", max_date, batch_id),
    )
    conn.commit()
    conn.close()


class FreshWindowThetaDataImportTests(unittest.TestCase):
    def test_window_defaults_from_store_max_plus_one_to_latest_completed_market_day(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "options_history.db"
            _init_store(db)
            report = importer.compute_window(
                db_path=db,
                source_label="thetadata_opra_nbbo_1m",
                now_utc=datetime(2026, 7, 2, 15, 0, tzinfo=UTC),
            )
        self.assertEqual(report["store_max_intraday_date_before"], "2026-06-08")
        self.assertEqual(report["latest_completed_market_day"], "2026-07-01")
        self.assertEqual(report["date_from"], "2026-06-09")
        self.assertEqual(report["date_to"], "2026-07-01")
        self.assertIn("2026-06-18", report["requested_market_dates"])
        self.assertNotIn("2026-06-19", report["requested_market_dates"])
        self.assertEqual(report["requested_market_date_count"], 16)

    def test_empty_when_store_is_current_for_latest_completed_day(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "options_history.db"
            _init_store(db, max_date="2026-07-01")
            report = importer.compute_window(
                db_path=db,
                source_label="thetadata_opra_nbbo_1m",
                now_utc=datetime(2026, 7, 2, 15, 0, tzinfo=UTC),
            )
        self.assertTrue(report["empty_window"])
        self.assertEqual(report["requested_market_date_count"], 0)

    def test_write_requires_exact_approval_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "options_history.db"
            _init_store(db)
            report = importer.build_report(
                db_path=db,
                forward_cohort_path=Path("missing.json"),
                date_from=importer._parse_date("2026-06-09"),
                date_to=importer._parse_date("2026-06-09"),
                symbols=["SPY"],
                approval_token="wrong",
                dry_run=False,
                generated_at_utc="2026-07-02T15:00:00Z",
            )
        self.assertEqual(report["status"], "blocked_fresh_window_thetadata_opra_import")
        self.assertIn("approval_token_missing_or_invalid", report["blockers"])
        self.assertFalse(report["import_attempted"])

    def test_scope_rejects_symbols_outside_allowed_universe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "options_history.db"
            _init_store(db)
            report = importer.build_report(
                db_path=db,
                forward_cohort_path=Path("missing.json"),
                date_from=importer._parse_date("2026-06-09"),
                date_to=importer._parse_date("2026-06-09"),
                symbols=["SPY", "TLT"],
                approval_token=importer.APPROVAL_TOKEN,
                dry_run=True,
                generated_at_utc="2026-07-02T15:00:00Z",
            )
        self.assertEqual(report["status"], "dry_run_blocked")
        self.assertEqual(report["outside_requested_symbols"], ["TLT"])
        self.assertIn("requested_symbols_outside_allowed_fresh_window_universe", report["blockers"])

    def test_lock_blocks_second_writer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "options_history_import.lock"
            with importer.ImportLock(lock_path, {"owner": "test"}):
                with self.assertRaises(RuntimeError):
                    with importer.ImportLock(lock_path, {"owner": "second"}):
                        pass
            self.assertFalse(lock_path.exists())


class FreshWindowSchedulerHealthTests(unittest.TestCase):
    def test_scheduler_config_accepts_weekday_post_close_task(self) -> None:
        fields = {
            "TaskName": health.DEFAULT_TASK_NAME,
            "Scheduled Task State": "Enabled",
            "Status": "Ready",
            "Task To Run": health.EXPECTED_TASK_TO_RUN,
            "Schedule Type": "Weekly",
            "Days": "MON, TUE, WED, THU, FRI",
            "Start Time": health.EXPECTED_START_TIME,
            "Stop Task If Runs X Hours and X Mins": health.EXPECTED_STOP_LIMIT,
        }
        status, blockers = health._config_status(fields, returncode=0)
        self.assertEqual(status, "fresh_window_import_scheduler_ready")
        self.assertEqual(blockers, [])

    def test_scheduler_config_rejects_scan_or_append_batch_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            batch = Path(tmp) / "runner.bat"
            batch.write_text(
                "\n".join(
                    [
                        health.EXPECTED_BATCH_STEPS[0],
                        "set OPTIONS_SCAN_AUTO_TRACK=1",
                        health.EXPECTED_BATCH_STEPS[1],
                    ]
                ),
                encoding="utf8",
            )
            report = health._inspect_batch_file(batch)
        self.assertIn("OPTIONS_SCAN_AUTO_TRACK", report["prohibited_tokens_present"])


if __name__ == "__main__":
    unittest.main()
