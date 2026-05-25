from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for candidate in (ROOT, TESTS_DIR):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from scripts.lane_data_shortfall_report import build_lane_data_shortfall_report  # noqa: E402
from workspace_tempdir import WorkspaceTempDir  # noqa: E402


class LaneDataShortfallReportTests(unittest.TestCase):
    def setUp(self):
        self._tmp = WorkspaceTempDir(prefix="lane-data-shortfall")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.db_path = self.tmp / "options_history.db"

    def _seed_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE import_batches (
                    id INTEGER PRIMARY KEY,
                    source_label TEXT NOT NULL,
                    dataset_kind TEXT NOT NULL,
                    data_trust TEXT NOT NULL
                );
                CREATE TABLE option_quote_snapshots (
                    snapshot_kind TEXT NOT NULL,
                    underlying TEXT NOT NULL,
                    contract_symbol TEXT NOT NULL,
                    quote_date_et TEXT NOT NULL,
                    bid REAL,
                    ask REAL,
                    source_batch_id INTEGER NOT NULL
                );
                INSERT INTO import_batches VALUES
                    (1, 'alpaca_opra_daily_snapshot', 'daily_parquet', 'trusted'),
                    (2, 'onclickmedia_research_grade_eod_bidask', 'daily_parquet', 'research');
                """
            )
            for source_batch_id, symbols in ((1, ["SPY", "QQQ"]), (2, ["SPY", "QQQ", "FCX"])):
                for quote_date in ("2026-05-20", "2026-05-21"):
                    for symbol in symbols:
                        conn.execute(
                            """
                            INSERT INTO option_quote_snapshots
                                (snapshot_kind, underlying, contract_symbol, quote_date_et, bid, ask, source_batch_id)
                            VALUES ('daily_eod', ?, ?, ?, 1.0, 1.2, ?)
                            """,
                            (symbol, f"{symbol}260619C00100000", quote_date, source_batch_id),
                        )
            conn.commit()

    def test_report_keeps_regular_and_commodity_lanes_separate_by_scope(self):
        self._seed_db()

        with patch(
            "scripts.lane_data_shortfall_report.lane_universe_symbols",
            return_value=["SPY", "QQQ"],
        ), patch(
            "scripts.lane_data_shortfall_report.ai_commodity_scan_tickers",
            return_value=["FCX"],
        ):
            report = build_lane_data_shortfall_report(
                db_path=self.db_path,
                min_trusted_shared_dates=2,
                min_research_shared_dates=2,
            )

        by_lane = {lane["id"]: lane for lane in report["lanes"]}
        self.assertEqual(report["proof_ready_lanes"], ["bullish_pullback_observation", "regular_bearish_put_primary"])
        self.assertEqual(
            sorted(report["research_ready_lanes"]),
            ["ai_commodity_infra_observation", "bullish_pullback_observation", "regular_bearish_put_primary"],
        )
        self.assertEqual(by_lane["bullish_pullback_observation"]["symbols"], ["SPY", "QQQ"])
        self.assertEqual(by_lane["regular_bearish_put_primary"]["symbols"], ["SPY", "QQQ"])
        self.assertEqual(by_lane["ai_commodity_infra_observation"]["symbols"], ["FCX"])
        self.assertEqual(
            by_lane["ai_commodity_infra_observation"]["coverage"]["trusted_alpaca"]["status"],
            "missing_symbols",
        )
        self.assertEqual(
            by_lane["ai_commodity_infra_observation"]["coverage"]["all_research_and_trusted"]["status"],
            "ready_for_research_replay",
        )


if __name__ == "__main__":
    unittest.main()
