from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_feature_store as feature_store


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
                '2026-01-03T00:00:00Z', 3, 3, 0, 0, '[]')
        """
    )
    conn.execute(
        """
        INSERT INTO import_batches
        VALUES (2, 'free_research_vendor', 'intraday_csv', 'research', 'fixture.csv', 'def',
                '2026-01-03T00:00:00Z', 1, 1, 0, 0, '[]')
        """
    )
    rows = [
        (
            "2026-01-02T15:10:00Z",
            "2026-01-02",
            610,
            "intraday",
            "SPY",
            "SPY260220C00500000",
            "2026-02-20",
            "call",
            500.0,
            1.0,
            1.2,
            None,
            0.22,
            501.0,
            10,
            100,
            1,
        ),
        (
            "2026-01-03T15:10:00Z",
            "2026-01-03",
            610,
            "intraday",
            "SPY",
            "SPY260220C00510000",
            "2026-02-20",
            "call",
            510.0,
            0.0,
            0.5,
            None,
            None,
            None,
            None,
            None,
            1,
        ),
        (
            "2026-01-02T15:10:00Z",
            "2026-01-02",
            610,
            "intraday",
            "QQQ",
            "QQQ260220C00450000",
            "2026-02-20",
            "call",
            450.0,
            2.0,
            2.4,
            None,
            0.31,
            451.0,
            20,
            200,
            1,
        ),
        (
            "2026-01-02T15:10:00Z",
            "2026-01-02",
            610,
            "intraday",
            "SPY",
            "SPY260220C00600000",
            "2026-02-20",
            "call",
            600.0,
            9.0,
            9.5,
            None,
            0.99,
            501.0,
            10,
            100,
            2,
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


class RegularOptionsFeatureStoreTests(unittest.TestCase):
    def test_build_report_uses_trusted_theta_rows_and_shared_dates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "options_history.db"
            _init_db(db_path)

            report = feature_store.build_report(
                db_path=db_path,
                symbols=("SPY", "QQQ"),
                generated_at_utc="2026-01-04T00:00:00Z",
            )

        self.assertEqual(report["status"], "feature_store_built")
        self.assertEqual(report["summary"]["available_symbol_count"], 2)
        self.assertEqual(report["summary"]["quote_row_count"], 3)
        self.assertEqual(report["summary"]["shared_quote_date_count"], 1)
        by_symbol = {row["symbol"]: row for row in report["symbol_surface_rows"]}
        self.assertEqual(by_symbol["SPY"]["quote_row_count"], 2)
        self.assertEqual(by_symbol["SPY"]["positive_bid_ask_quote_count"], 1)
        self.assertEqual(by_symbol["SPY"]["zero_bid_positive_ask_count"], 1)
        self.assertEqual(by_symbol["SPY"]["iv_coverage_pct"], 50.0)
        self.assertIn("dte_46_60", by_symbol["SPY"]["dte_bucket_counts"])
        self.assertEqual(
            report["feature_contract"]["point_in_time_join_rule"],
            "candidate joins must require feature.tradable_after_time <= candidate_entry_time; if multiple rows match, use the latest tradable_after_time at or before candidate_entry_time",
        )

    def test_latest_tradable_features_excludes_future_rows(self) -> None:
        rows = [
            {"feature_key": "SPY_CALL", "tradable_after_time": "2026-01-02T15:10:00Z", "value": 1},
            {"feature_key": "SPY_CALL", "tradable_after_time": "2026-01-02T15:12:00Z", "value": 2},
            {"feature_key": "SPY_CALL", "tradable_after_time": "2026-01-02T15:15:00Z", "value": 3},
            {"feature_key": "QQQ_CALL", "tradable_after_time": "2026-01-02T15:11:00Z", "value": 4},
        ]

        joined = feature_store.latest_tradable_features(rows, candidate_entry_time="2026-01-02T15:12:30Z")

        by_key = {row["feature_key"]: row for row in joined}
        self.assertEqual(by_key["SPY_CALL"]["value"], 2)
        self.assertEqual(by_key["QQQ_CALL"]["value"], 4)

    def test_write_outputs_creates_latest_and_docs_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "options_history.db"
            _init_db(db_path)
            report = feature_store.build_report(db_path=db_path, symbols=("SPY",))
            artifacts = feature_store.write_outputs(
                report,
                output_dir=root / "out",
                docs_report=root / "docs" / "regular-options-feature-store.md",
            )

            for artifact in artifacts.values():
                self.assertTrue(Path(artifact).exists(), artifact)
            latest = json.loads(Path(artifacts["latest_json"]).read_text(encoding="utf8"))
            self.assertEqual(latest["report_id"], feature_store.REPORT_ID)


if __name__ == "__main__":
    unittest.main()
