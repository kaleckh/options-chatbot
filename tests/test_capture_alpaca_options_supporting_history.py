from __future__ import annotations

import json
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from historical_options_store import DAILY_SNAPSHOT_KIND, import_historical_option_snapshots
from scripts.capture_alpaca_opra_daily_snapshots import DAILY_DATASET_KIND, write_snapshot_csv
from scripts.capture_alpaca_options_supporting_history import (
    capture_supporting_history,
    select_supporting_contracts,
)
from workspace_tempdir import WorkspaceTempDir


class _FakeAlpacaHistoryClient:
    def __init__(self):
        self.bar_calls = []
        self.trade_calls = []

    def historical_option_bars(self, symbols, *, start, end, timeframe="1Min", limit=10000):
        self.bar_calls.append(
            {
                "symbols": list(symbols),
                "start": start,
                "end": end,
                "timeframe": timeframe,
                "limit": limit,
            }
        )
        return {
            symbol: [{"t": "2026-05-22T14:30:00Z", "o": 1.0, "h": 1.2, "l": 0.9, "c": 1.1, "v": 10}]
            for symbol in symbols
        }

    def historical_option_trades(self, symbols, *, start, end, limit=10000):
        self.trade_calls.append({"symbols": list(symbols), "start": start, "end": end, "limit": limit})
        return {
            symbol: [{"t": "2026-05-22T14:31:00Z", "p": 1.11, "s": 2, "x": "C", "c": ["I"]}]
            for symbol in symbols
        }


class AlpacaSupportingHistoryCaptureTests(unittest.TestCase):
    def setUp(self):
        self._tmp = WorkspaceTempDir(prefix="alpaca-supporting-history")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.db_path = self.tmp / "options_history.db"
        csv_path = self.tmp / "quotes.csv"
        write_snapshot_csv(
            csv_path,
            [
                {
                    "as_of_utc": "2026-05-22T19:59:00Z",
                    "underlying": "FCX",
                    "contract_symbol": "FCX260619C00050000",
                    "expiry": "2026-06-19",
                    "option_type": "call",
                    "strike": 50,
                    "bid": 1.0,
                    "ask": 1.1,
                    "last": 1.05,
                    "iv": 0.3,
                    "underlying_price": 49.0,
                    "volume": 100,
                    "open_interest": 1000,
                },
                {
                    "as_of_utc": "2026-05-22T19:59:00Z",
                    "underlying": "FCX",
                    "contract_symbol": "FCX260619C00055000",
                    "expiry": "2026-06-19",
                    "option_type": "call",
                    "strike": 55,
                    "bid": 0.5,
                    "ask": 0.6,
                    "last": 0.55,
                    "iv": 0.3,
                    "underlying_price": 49.0,
                    "volume": 20,
                    "open_interest": 500,
                },
            ],
        )
        import_historical_option_snapshots(
            csv_path,
            "alpaca_opra_daily_snapshot",
            dataset_kind=DAILY_DATASET_KIND,
            snapshot_kind=DAILY_SNAPSHOT_KIND,
            db_path=self.db_path,
        )

    def test_selects_contracts_from_alpaca_daily_quote_store(self):
        contracts = select_supporting_contracts(
            db_path=self.db_path,
            symbols=["FCX"],
            start_utc=datetime(2026, 5, 22, tzinfo=UTC),
            end_utc=datetime(2026, 5, 23, tzinfo=UTC),
            max_contracts=1,
        )

        self.assertEqual(len(contracts), 1)
        self.assertEqual(contracts[0]["contract_symbol"], "FCX260619C00050000")

    def test_capture_writes_bars_and_trades_as_supporting_not_proof(self):
        output_dir = self.tmp / "supporting"
        client = _FakeAlpacaHistoryClient()

        summary = capture_supporting_history(
            db_path=self.db_path,
            output_dir=output_dir,
            symbols=["FCX"],
            start="2026-05-22",
            end="2026-05-22",
            max_contracts=2,
            client=client,
        )

        self.assertEqual(summary["contract_count"], 2)
        self.assertEqual(summary["bars"]["row_count"], 2)
        self.assertEqual(summary["trades"]["row_count"], 2)
        self.assertFalse(summary["proof_grade_bid_ask"])
        self.assertEqual(summary["proof_blocker"], "alpaca_historical_option_quotes_endpoint_unavailable")
        latest = json.loads((output_dir / "latest.json").read_text(encoding="utf8"))
        self.assertEqual(latest["usage_policy"], "supporting_trade_and_bar_context_only_not_entry_or_exit_fill_proof")
        bars_rows = (output_dir / Path(summary["bars"]["output_path"]).name).read_text(encoding="utf8").splitlines()
        self.assertEqual(len(bars_rows), 2)
        self.assertEqual(json.loads(bars_rows[0])["source_label"], "alpaca_historical_option_bars")


if __name__ == "__main__":
    unittest.main()
