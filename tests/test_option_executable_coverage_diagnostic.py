from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts import diagnose_option_executable_coverage as diagnostic


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE import_batches (
            id INTEGER PRIMARY KEY,
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
            id INTEGER PRIMARY KEY,
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
        INSERT INTO import_batches
        VALUES (1, 'thetadata_opra_nbbo_1m', 'intraday_csv', 'trusted', 'fixture.csv', 'abc',
                '2026-01-03T00:00:00Z', 5, 5, 0, 0, '[]')
        """
    )
    rows = [
        (
            "2026-01-02T14:45:00Z",
            "2026-01-02",
            585,
            "intraday",
            "CVX",
            "CVX260220C00150000",
            "2026-02-20",
            "call",
            150.0,
            1.0,
            1.2,
            None,
            None,
            149.5,
            None,
            None,
            1,
        ),
        (
            "2026-01-02T15:45:00Z",
            "2026-01-02",
            645,
            "intraday",
            "CVX",
            "CVX260220C00155000",
            "2026-02-20",
            "call",
            155.0,
            0.0,
            0.4,
            None,
            None,
            149.5,
            None,
            None,
            1,
        ),
        (
            "2026-01-03T14:45:00Z",
            "2026-01-03",
            585,
            "intraday",
            "CVX",
            "CVX260220C00160000",
            "2026-02-20",
            "call",
            160.0,
            0.0,
            0.3,
            None,
            None,
            150.0,
            None,
            None,
            1,
        ),
        (
            "2026-01-03T15:45:00Z",
            "2026-01-03",
            645,
            "intraday",
            "CVX",
            "CVX260220P00145000",
            "2026-02-20",
            "put",
            145.0,
            0.8,
            1.0,
            None,
            None,
            150.0,
            None,
            None,
            1,
        ),
        (
            "2026-01-03T16:45:00Z",
            "2026-01-03",
            705,
            "intraday",
            "CVX",
            "CVX260220P00140000",
            "2026-02-20",
            "put",
            140.0,
            0.0,
            0.2,
            None,
            None,
            150.0,
            None,
            None,
            1,
        ),
    ]
    conn.executemany(
        """
        INSERT INTO option_quote_snapshots (
            as_of_utc, quote_date_et, quote_minute_et, snapshot_kind, underlying,
            contract_symbol, expiry, option_type, strike, bid, ask, last, iv,
            underlying_price, volume, open_interest, source_batch_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


class OptionExecutableCoverageDiagnosticTests(unittest.TestCase):
    def test_build_report_classifies_zero_bid_failure_and_candidate_membership(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "options_history.db"
            candidate_report = root / "candidate.json"
            _init_db(db_path)
            candidate_report.write_text(
                json.dumps(
                    {
                        "selected_trades": [{"ticker": "SPY", "lane_id": "lane_a"}],
                        "suppressed_duplicates": [{"ticker": "CVX", "lane_id": "lane_b"}],
                    }
                ),
                encoding="utf8",
            )

            report = diagnostic.build_report(
                db_path=db_path,
                symbols=("CVX",),
                candidate_report=candidate_report,
                generated_at_utc="2026-01-04T00:00:00Z",
            )

        self.assertEqual(report["status"], "coverage_diagnostic_built")
        cvx = report["symbol_reports"]["CVX"]
        summary = cvx["summary"]
        self.assertEqual(summary["quote_rows"], 5)
        self.assertEqual(summary["executable_quote_rows"], 2)
        self.assertEqual(summary["zero_bid_positive_ask_rows"], 3)
        self.assertEqual(summary["zero_bid_share_of_non_executable_pct"], 100.0)
        self.assertEqual(summary["assessment"]["status"], "zero_bid_tradability_floor_failure")
        self.assertEqual(cvx["non_executable_reasons"][0]["reason"], "zero_bid_positive_ask")
        self.assertEqual(report["candidate_membership"]["symbols"]["CVX"]["selected_trade_count"], 0)
        self.assertEqual(report["candidate_membership"]["symbols"]["CVX"]["suppressed_duplicate_count"], 1)

    def test_write_outputs_creates_latest_and_docs_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "options_history.db"
            _init_db(db_path)
            report = diagnostic.build_report(db_path=db_path, symbols=("CVX",))
            artifacts = diagnostic.write_outputs(
                report,
                output_dir=root / "out",
                docs_report=root / "docs" / "regular-options-cvx-executable-coverage.md",
            )

            for artifact in artifacts.values():
                self.assertTrue(Path(artifact).exists(), artifact)
            latest = json.loads(Path(artifacts["latest_json"]).read_text(encoding="utf8"))
            self.assertEqual(latest["report_id"], diagnostic.REPORT_ID)
            markdown = Path(artifacts["docs_report"]).read_text(encoding="utf8")
            self.assertIn("zero_bid_tradability_floor_failure", markdown)


if __name__ == "__main__":
    unittest.main()
