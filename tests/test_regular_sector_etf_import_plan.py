from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from historical_options_store import init_schema
from scripts.plan_regular_sector_etf_imports import (
    DEFAULT_SOURCE_LABEL,
    build_regular_sector_etf_import_plan,
    check_theta_terminal,
)
from workspace_tempdir import WorkspaceTempDir


class RegularSectorEtfImportPlanTests(unittest.TestCase):
    def setUp(self):
        self._tmp = WorkspaceTempDir(prefix="sector-etf-import-plan")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.db_path = self.tmp / "options_history.db"
        init_schema(self.db_path)

    def _insert_intraday_dates(self, symbol: str, dates: list[str], *, source_label: str = DEFAULT_SOURCE_LABEL) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO import_batches (
                    source_label, dataset_kind, data_trust, input_path, file_hash,
                    imported_at_utc, total_rows, imported_rows, duplicate_rows,
                    rejected_rows, warnings_json
                ) VALUES (?, 'intraday_csv', 'trusted', 'fixture.csv', ?, '2026-05-31T00:00:00Z', ?, ?, 0, 0, '[]')
                """,
                (source_label, f"hash-{symbol}", len(dates), len(dates)),
            )
            batch_id = int(cursor.lastrowid)
            for index, trade_date in enumerate(dates, start=1):
                conn.execute(
                    """
                    INSERT INTO option_quote_snapshots (
                        as_of_utc, quote_date_et, quote_minute_et, snapshot_kind,
                        underlying, contract_symbol, expiry, option_type, strike,
                        bid, ask, source_batch_id
                    ) VALUES (?, ?, 600, 'intraday', ?, ?, '2026-07-17', 'call', 200, 1.0, 1.1, ?)
                    """,
                    (
                        f"{trade_date}T14:00:00Z",
                        trade_date,
                        symbol,
                        f"{symbol}260717C{index:08d}",
                        batch_id,
                    ),
                )

    def test_plan_blocks_on_theta_when_sector_symbols_are_missing(self):
        self._insert_intraday_dates("IWM", ["2026-01-02", "2026-01-05"])

        plan = build_regular_sector_etf_import_plan(
            db_path=self.db_path,
            sector_symbols=["GLD", "SMH"],
            control_symbols=["IWM"],
            theta_status={"available": False, "status": "unavailable", "error": "connection refused"},
            min_quote_dates=2,
            min_shared_quote_dates=2,
            generated_at="2026-05-31T00:00:00Z",
        )

        self.assertEqual(plan["status"], "blocked_theta_unavailable")
        self.assertEqual(plan["symbols_needing_import"], ["GLD", "SMH"])
        self.assertEqual(plan["import_window"]["interval"], "1h")
        self.assertIn("theta_terminal_unavailable", plan["blockers"])
        self.assertEqual(plan["control_readiness"]["status"], "ready_for_exact_replay")
        self.assertIn("--symbols GLD", plan["import_commands"][0]["dry_run_command"])
        self.assertIn("--dry-run", plan["import_commands"][0]["dry_run_command"])
        self.assertIn("--interval 1h", plan["import_commands"][0]["dry_run_command"])
        self.assertIn("--timeout 30", plan["import_commands"][0]["dry_run_command"])
        self.assertIn("--snapshot-kind intraday", plan["import_commands"][0]["full_import_command"])

    def test_plan_is_ready_when_all_sector_symbols_have_trusted_intraday_depth(self):
        self._insert_intraday_dates("GLD", ["2026-01-02", "2026-01-05"])
        self._insert_intraday_dates("SMH", ["2026-01-02", "2026-01-05"])
        self._insert_intraday_dates("IWM", ["2026-01-02", "2026-01-05"])

        plan = build_regular_sector_etf_import_plan(
            db_path=self.db_path,
            sector_symbols=["GLD", "SMH"],
            control_symbols=["IWM"],
            theta_status={"available": False, "status": "unavailable"},
            min_quote_dates=2,
            min_shared_quote_dates=2,
            generated_at="2026-05-31T00:00:00Z",
        )

        self.assertEqual(plan["status"], "ready_for_sector_replay")
        self.assertEqual(plan["ready_sector_symbols"], ["GLD", "SMH"])
        self.assertEqual(plan["symbols_needing_import"], [])
        self.assertEqual(plan["import_commands"], [])

    def test_plan_marks_theta_available_import_state(self):
        self._insert_intraday_dates("GLD", ["2026-01-02", "2026-01-05"])

        plan = build_regular_sector_etf_import_plan(
            db_path=self.db_path,
            sector_symbols=["GLD", "KRE"],
            control_symbols=[],
            theta_status={"available": True, "status": "available", "http_status": 200},
            min_quote_dates=2,
            min_shared_quote_dates=2,
            generated_at="2026-05-31T00:00:00Z",
        )

        self.assertEqual(plan["status"], "ready_to_import_sector_etfs")
        self.assertEqual(plan["ready_sector_symbols"], ["GLD"])
        self.assertEqual(plan["symbols_needing_import"], ["KRE"])
        self.assertEqual(plan["control_readiness"]["status"], "not_requested")
        self.assertIn("--symbols KRE", plan["import_commands"][0]["full_import_command"])
        self.assertIn("--interval 1h", plan["import_commands"][0]["full_import_command"])

    def test_plan_next_action_continues_imports_when_symbols_are_thin_not_missing(self):
        self._insert_intraday_dates("GLD", ["2026-01-02"])
        self._insert_intraday_dates("KRE", ["2026-01-02"])

        plan = build_regular_sector_etf_import_plan(
            db_path=self.db_path,
            sector_symbols=["GLD", "KRE"],
            control_symbols=[],
            theta_status={"available": True, "status": "available", "http_status": 200},
            min_quote_dates=2,
            min_shared_quote_dates=2,
            generated_at="2026-05-31T00:00:00Z",
        )

        self.assertEqual(plan["status"], "ready_to_import_sector_etfs")
        self.assertEqual(plan["sector_readiness"]["missing_required_underlyings"], [])
        self.assertEqual(plan["sector_readiness"]["thin_required_underlyings"], ["GLD", "KRE"])
        self.assertIn("Continue the full-import commands", plan["next_action"])

    def test_theta_v3_gone_status_endpoint_still_marks_terminal_reachable(self):
        error = HTTPError(
            "http://127.0.0.1:25503/v2/system/status",
            410,
            "Gone",
            hdrs=None,
            fp=Mock(read=Mock(return_value=b"gone")),
        )
        with patch("scripts.plan_regular_sector_etf_imports.urlopen", side_effect=error):
            status = check_theta_terminal()

        self.assertTrue(status["available"])
        self.assertEqual(status["status"], "available_status_endpoint_gone")
        self.assertEqual(status["http_status"], 410)


if __name__ == "__main__":
    unittest.main()
