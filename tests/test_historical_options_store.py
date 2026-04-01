import os
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for candidate in (ROOT, TESTS_DIR):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from historical_options_store import (
    DAILY_SNAPSHOT_KIND,
    HistoricalOptionsStore,
    import_daily_option_parquet,
    import_historical_option_snapshots,
    load_import_batches,
)
from historical_options_fixtures import (
    make_validation_history,
    write_daily_options_parquet,
    write_historical_options_csv,
    write_underlying_daily_parquet,
)


class HistoricalOptionsStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = os.path.join(self._tmp.name, "options_history.db")
        self.csv_path = os.path.join(self._tmp.name, "snapshots.csv")
        self.daily_parquet_path = os.path.join(self._tmp.name, "spy_options.parquet")
        self.underlying_parquet_path = os.path.join(self._tmp.name, "spy_underlying.parquet")
        self.histories = {
            "SPY": make_validation_history(length=12, start=500.0, step=0.8),
        }
        write_historical_options_csv(self.csv_path, self.histories, strike_span=4)
        write_daily_options_parquet(self.daily_parquet_path, self.histories, symbol="SPY", strike_span=4)
        write_underlying_daily_parquet(self.underlying_parquet_path, self.histories, symbol="SPY")

    def test_import_normalizes_rows_and_dedupes_repeat_imports(self):
        first = import_historical_option_snapshots(self.csv_path, "lab_intraday", db_path=self.db_path)
        second = import_historical_option_snapshots(self.csv_path, "lab_intraday_repeat", db_path=self.db_path)

        self.assertGreater(first["imported_rows"], 0)
        self.assertEqual(second["imported_rows"], 0)
        self.assertGreater(second["duplicate_rows"], 0)

        batches = load_import_batches(self.db_path)
        self.assertEqual(len(batches), 2)
        self.assertTrue(all("warnings" in batch for batch in batches))
        self.assertTrue(all(batch["data_trust"] == "trusted" for batch in batches))

    def test_entry_window_and_exact_contract_resolution(self):
        import_historical_option_snapshots(self.csv_path, "lab_intraday", db_path=self.db_path)
        store = HistoricalOptionsStore(self.db_path)
        available_dates = store.list_available_underlyings()
        self.assertEqual(available_dates, ["SPY"])
        trade_date = self.histories["SPY"].index[0].date()

        quote = store.find_entry_contract(
            underlying="SPY",
            trade_date_et=trade_date,
            option_type="call",
            target_expiry=trade_date,
            target_strike=501.0,
        )
        self.assertIsNotNone(quote)
        self.assertEqual(quote.quote_minute_et, 10 * 60 + 15)
        self.assertEqual(quote.option_type, "call")

        closing = store.get_closing_quote(contract_symbol=quote.contract_symbol, quote_date_et=trade_date)
        self.assertIsNotNone(closing)
        self.assertEqual(closing.quote_minute_et, 15 * 60 + 55)

        exact = store.get_exact_quote(
            quote_date_et=trade_date,
            underlying="SPY",
            expiry=quote.expiry,
            option_type="call",
            strike=quote.strike,
        )
        self.assertIsNotNone(exact)
        self.assertEqual(exact.contract_symbol, quote.contract_symbol)

    def test_import_rejects_rows_missing_contract_identity(self):
        bad_csv = Path(self._tmp.name) / "bad.csv"
        bad_csv.write_text(
            "as_of,underlying,expiry,option_type,strike,bid,ask,last\n"
            "2026-03-30T10:15:00,SPY,2026-04-03,call,510,1.0,1.2,1.1\n",
            encoding="utf8",
        )

        result = import_historical_option_snapshots(bad_csv, "bad_import", db_path=self.db_path)
        self.assertEqual(result["imported_rows"], 0)
        self.assertEqual(result["rejected_rows"], 1)
        self.assertTrue(result["warnings"])

    def test_import_daily_parquet_and_filter_by_snapshot_kind(self):
        result = import_daily_option_parquet(
            self.daily_parquet_path,
            "spy_daily",
            underlying="SPY",
            underlying_input=self.underlying_parquet_path,
            db_path=self.db_path,
        )
        self.assertGreater(result["imported_rows"], 0)
        self.assertEqual(result["snapshot_kind"], DAILY_SNAPSHOT_KIND)

        store = HistoricalOptionsStore(self.db_path)
        self.assertTrue(store.has_quotes(snapshot_kind=DAILY_SNAPSHOT_KIND))
        self.assertEqual(store.list_available_underlyings(snapshot_kind=DAILY_SNAPSHOT_KIND), ["SPY"])

        trade_date = self.histories["SPY"].index[0].date()
        entry = store.find_entry_contract(
            underlying="SPY",
            trade_date_et=trade_date,
            option_type="call",
            target_expiry=trade_date,
            target_strike=501.0,
            earliest_minute_et=15 * 60 + 55,
            window_minutes=0,
            snapshot_kind=DAILY_SNAPSHOT_KIND,
        )
        self.assertIsNotNone(entry)
        self.assertEqual(entry.snapshot_kind, DAILY_SNAPSHOT_KIND)
        self.assertEqual(entry.quote_minute_et, 15 * 60 + 55)
        self.assertIsNotNone(entry.underlying_price)

    def test_intraday_and_daily_rows_can_coexist_for_same_contract_and_time(self):
        intraday_result = import_historical_option_snapshots(self.csv_path, "lab_intraday", db_path=self.db_path)
        daily_result = import_daily_option_parquet(
            self.daily_parquet_path,
            "spy_daily",
            underlying="SPY",
            underlying_input=self.underlying_parquet_path,
            db_path=self.db_path,
        )

        self.assertGreater(intraday_result["imported_rows"], 0)
        self.assertGreater(daily_result["imported_rows"], 0)

        store = HistoricalOptionsStore(self.db_path)
        intraday_summary = store.snapshot_summary("intraday")
        daily_summary = store.snapshot_summary(DAILY_SNAPSHOT_KIND)
        self.assertGreater(intraday_summary["quote_count"], 0)
        self.assertGreater(daily_summary["quote_count"], 0)
        self.assertEqual(intraday_summary["trust_levels"], ["trusted"])
        self.assertEqual(daily_summary["trust_levels"], ["trusted"])

    def test_shared_quote_dates_can_intersect_underlyings_for_trusted_daily_data(self):
        histories = {
            "SPY": make_validation_history(length=14, start=500.0, step=0.8),
            "QQQ": make_validation_history(length=14, start=420.0, step=0.9),
        }
        spy_path = Path(self._tmp.name) / "spy_daily_full.parquet"
        qqq_path = Path(self._tmp.name) / "qqq_daily_missing.parquet"
        write_daily_options_parquet(spy_path, histories, symbol="SPY", strike_span=3)
        write_daily_options_parquet(qqq_path, histories, symbol="QQQ", strike_span=3)

        missing_date = str(pd.Timestamp(histories["QQQ"].index[5]).date())
        qqq_frame = pd.read_parquet(qqq_path)
        qqq_frame = qqq_frame.loc[qqq_frame["date"] != missing_date].copy()
        qqq_frame.to_parquet(qqq_path, index=False)

        import_daily_option_parquet(spy_path, "spy_daily", underlying="SPY", db_path=self.db_path)
        import_daily_option_parquet(qqq_path, "qqq_daily", underlying="QQQ", db_path=self.db_path)

        store = HistoricalOptionsStore(self.db_path)
        spy_dates = store.available_quote_dates("SPY", snapshot_kind=DAILY_SNAPSHOT_KIND, trusted_only=True)
        shared_dates = store.shared_quote_dates(
            ["SPY", "QQQ"],
            snapshot_kind=DAILY_SNAPSHOT_KIND,
            trusted_only=True,
        )

        self.assertIn(missing_date, spy_dates)
        self.assertNotIn(missing_date, shared_dates)
        self.assertEqual(len(shared_dates), len(spy_dates) - 1)


if __name__ == "__main__":
    unittest.main()
