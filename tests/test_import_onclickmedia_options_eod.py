from __future__ import annotations

import gzip
import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.import_onclickmedia_options_eod import (  # noqa: E402
    SOURCE_LABEL,
    _chain_path,
    _occ_contract_symbol,
    import_onclickmedia_eod,
    normalize_chain_row,
    select_recent_shared_dates,
)
from historical_options_store import DAILY_SNAPSHOT_KIND, HistoricalOptionsStore  # noqa: E402
from workspace_tempdir import WorkspaceTempDir  # noqa: E402


class _FakeOnclickClient:
    base_url = "https://fake.onclickmedia.test/options/"

    def __init__(self):
        self.date_calls: list[str] = []
        self.chain_calls: list[tuple[str, str]] = []
        self.availability = {
            "FCX": [date(2026, 5, 20), date(2026, 5, 21), date(2026, 5, 22)],
            "SLV": [date(2026, 5, 21), date(2026, 5, 22)],
        }

    def available_dates(self, symbol: str):
        self.date_calls.append(symbol)
        return self.availability[symbol]

    def option_chain(self, symbol: str, quote_date: date):
        self.chain_calls.append((symbol, quote_date.isoformat()))
        return [
            {
                "expiration": "2026-06-19",
                "strike": 50.0,
                "type": "call",
                "last": 1.0,
                "bid": 0.95,
                "bid_size": 10,
                "ask": 1.05,
                "ask_size": 12,
                "mark": 1.0,
                "volume": 20,
                "open_interest": 200,
                "greeks": {"delta": 0.45, "theta": -0.01},
            },
            {
                "expiration": "2026-06-19",
                "strike": 45.0,
                "type": "put",
                "last": 0.0,
                "bid": 0.0,
                "bid_size": 0,
                "ask": 0.05,
                "ask_size": 5,
                "volume": 0,
                "open_interest": 0,
            },
        ]


class ImportOnclickMediaOptionsEodTests(unittest.TestCase):
    def setUp(self):
        self._tmp = WorkspaceTempDir(prefix="onclickmedia-eod")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_occ_contract_symbol_matches_repo_format(self):
        self.assertEqual(
            _occ_contract_symbol("fcx", date(2026, 6, 19), "call", 50),
            "FCX260619C00050000",
        )

    def test_normalize_row_preserves_bid_ask_and_quality_flags(self):
        row = normalize_chain_row(
            "SLV",
            date(2026, 5, 22),
            {
                "expiration": "2026-06-19",
                "strike": 30.0,
                "type": "call",
                "last": 0.01,
                "bid": 0.01,
                "bid_size": 3549,
                "ask": 0.02,
                "ask_size": 4716,
                "mark": 0.015,
                "volume": 475,
                "open_interest": 153351,
                "greeks": {"delta": 0.02853},
            },
            retrieved_at_utc="2026-05-23T20:00:00Z",
        )

        self.assertEqual(row["source_label"], SOURCE_LABEL)
        self.assertFalse(row["proof_grade"])
        self.assertEqual(row["contract_symbol"], "SLV260619C00030000")
        self.assertEqual(row["bid"], 0.01)
        self.assertEqual(row["ask"], 0.02)
        self.assertEqual(row["greek_delta"], 0.02853)
        self.assertIn("executable_bid_ask", row["quality_flags"])
        self.assertIn("has_greeks", row["quality_flags"])

    def test_select_recent_shared_dates_uses_intersection_and_latest_window(self):
        selected = select_recent_shared_dates(
            {
                "FCX": [date(2026, 5, 20), date(2026, 5, 21), date(2026, 5, 22)],
                "SLV": [date(2026, 5, 19), date(2026, 5, 21), date(2026, 5, 22)],
            },
            target_count=1,
        )

        self.assertEqual(selected, [date(2026, 5, 22)])

    def test_select_recent_shared_dates_excludes_market_holidays(self):
        selected = select_recent_shared_dates(
            {
                "FCX": [date(2026, 5, 22), date(2026, 5, 25), date(2026, 5, 26)],
                "SLV": [date(2026, 5, 22), date(2026, 5, 25), date(2026, 5, 26)],
            },
            target_count=2,
        )

        self.assertEqual(selected, [date(2026, 5, 22), date(2026, 5, 26)])

    def test_import_writes_resumable_chain_files_and_summary(self):
        client = _FakeOnclickClient()

        summary = import_onclickmedia_eod(
            output_dir=self.tmp,
            symbols=["FCX", "SLV"],
            target_shared_dates=2,
            delay_seconds=0,
            client=client,
        )

        self.assertEqual(summary["selected_shared_dates"]["count"], 2)
        self.assertEqual(summary["request_pairs"], 4)
        self.assertEqual(summary["row_count"], 8)
        self.assertEqual(summary["executable_bid_ask_rows"], 4)
        self.assertEqual(summary["executable_with_volume_oi_rows"], 4)
        self.assertEqual(summary["source_grade"], "research_grade_eod_bidask")
        self.assertFalse(summary["proof_grade"])
        chain_path = _chain_path(self.tmp, "FCX", date(2026, 5, 22))
        with gzip.open(chain_path, "rt", encoding="utf8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
        self.assertEqual(len(rows), 2)
        latest = json.loads((self.tmp / "latest.json").read_text(encoding="utf8"))
        self.assertEqual(latest["row_count"], 8)

        second = import_onclickmedia_eod(
            output_dir=self.tmp,
            symbols=["FCX", "SLV"],
            target_shared_dates=2,
            delay_seconds=0,
            client=client,
        )

        self.assertEqual(second["skipped_existing_pairs"], 4)
        self.assertEqual(len(client.chain_calls), 4)
        self.assertEqual(second["row_count"], 8)

    def test_import_can_write_research_rows_to_history_store(self):
        client = _FakeOnclickClient()
        db_path = self.tmp / "options_history.db"

        summary = import_onclickmedia_eod(
            output_dir=self.tmp,
            symbols=["FCX", "SLV"],
            target_shared_dates=1,
            delay_seconds=0,
            db_path=db_path,
            client=client,
        )

        self.assertEqual(summary["import_csv"]["csv_rows"], 4)
        self.assertEqual(summary["db_import_result"]["imported_rows"], 4)
        self.assertEqual(summary["db_import_result"]["data_trust"], "research")
        store = HistoricalOptionsStore(db_path)
        all_summary = store.snapshot_summary(DAILY_SNAPSHOT_KIND, trusted_only=False)
        trusted_summary = store.snapshot_summary(DAILY_SNAPSHOT_KIND, trusted_only=True)
        self.assertEqual(all_summary["quote_count"], 4)
        self.assertEqual(trusted_summary["quote_count"], 0)


if __name__ == "__main__":
    unittest.main()
