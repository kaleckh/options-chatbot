import os
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for candidate in (ROOT, TESTS_DIR):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from historical_options_store import (
    DAILY_SNAPSHOT_KIND,
    DAILY_QUOTE_MINUTE_ET,
    HistoricalOptionsStore,
    RESEARCH_DATA_TRUST,
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
from workspace_tempdir import WorkspaceTempDir


class HistoricalOptionsStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = WorkspaceTempDir(prefix="historical-options-store")
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

    def test_schema_has_snapshot_summary_query_path_indexes(self):
        HistoricalOptionsStore(self.db_path)
        with sqlite3.connect(self.db_path) as conn:
            indexes = {
                row[1]: [info[2] for info in conn.execute(f"PRAGMA index_info('{row[1]}')").fetchall()]
                for row in conn.execute("PRAGMA index_list(option_quote_snapshots)").fetchall()
            }

        self.assertEqual(indexes["idx_option_quotes_snapshot_underlying"], ["snapshot_kind", "underlying"])
        self.assertEqual(indexes["idx_option_quotes_snapshot_asof"], ["snapshot_kind", "as_of_utc"])
        self.assertEqual(
            indexes["idx_option_quotes_snapshot_quote_date"],
            ["snapshot_kind", "quote_date_et", "underlying"],
        )

    def test_free_vendor_imports_are_research_not_trusted(self):
        result = import_daily_option_parquet(
            self.daily_parquet_path,
            "marketdata_free_eod",
            underlying="SPY",
            db_path=self.db_path,
        )

        self.assertEqual(result["data_trust"], RESEARCH_DATA_TRUST)
        store = HistoricalOptionsStore(self.db_path)
        all_summary = store.snapshot_summary(DAILY_SNAPSHOT_KIND, trusted_only=False)
        trusted_summary = store.snapshot_summary(DAILY_SNAPSHOT_KIND, trusted_only=True)
        self.assertGreater(all_summary["quote_count"], 0)
        self.assertEqual(trusted_summary["quote_count"], 0)

        trade_date = self.histories["SPY"].index[0].date()
        all_entry = store.find_entry_contract(
            underlying="SPY",
            trade_date_et=trade_date,
            option_type="call",
            target_expiry=trade_date,
            target_strike=501.0,
            earliest_minute_et=DAILY_QUOTE_MINUTE_ET,
            window_minutes=0,
            snapshot_kind=DAILY_SNAPSHOT_KIND,
        )
        trusted_entry = store.find_entry_contract(
            underlying="SPY",
            trade_date_et=trade_date,
            option_type="call",
            target_expiry=trade_date,
            target_strike=501.0,
            earliest_minute_et=DAILY_QUOTE_MINUTE_ET,
            window_minutes=0,
            snapshot_kind=DAILY_SNAPSHOT_KIND,
            trusted_only=True,
        )
        self.assertIsNotNone(all_entry)
        self.assertIsNone(trusted_entry)

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

    def test_replay_quote_lookups_reuse_store_cache(self):
        import_historical_option_snapshots(self.csv_path, "lab_intraday", db_path=self.db_path)
        store = HistoricalOptionsStore(self.db_path)
        trade_date = self.histories["SPY"].index[0].date()
        quote = store.find_entry_contract(
            underlying="SPY",
            trade_date_et=trade_date,
            option_type="call",
            target_expiry=trade_date,
            target_strike=501.0,
        )
        self.assertIsNotNone(quote)

        with patch.object(store, "_connect", wraps=store._connect) as connect:
            first = store.get_closing_quote(contract_symbol=quote.contract_symbol, quote_date_et=trade_date)
            second = store.get_closing_quote(contract_symbol=quote.contract_symbol, quote_date_et=trade_date)

        self.assertIsNotNone(first)
        self.assertEqual(second, first)
        self.assertEqual(connect.call_count, 1)

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

    def test_import_daily_parquet_accepts_capital_date_column(self):
        capital_date_path = Path(self._tmp.name) / "spy_options_capital_date.parquet"
        frame = pd.read_parquet(self.daily_parquet_path)
        frame = frame.rename(columns={"date": "Date"})
        frame.to_parquet(capital_date_path, index=False)

        result = import_daily_option_parquet(
            capital_date_path,
            "spy_daily_capital_date",
            underlying="SPY",
            underlying_input=self.underlying_parquet_path,
            db_path=self.db_path,
        )

        self.assertGreater(result["imported_rows"], 0)
        self.assertEqual(result["rejected_rows"], 0)

    def test_import_daily_parquet_accepts_numeric_timestamp_columns(self):
        timestamp_path = Path(self._tmp.name) / "spy_options_timestamp.parquet"
        frame = pd.read_parquet(self.daily_parquet_path)
        frame["timestamp"] = (pd.to_datetime(frame.pop("date"), utc=True).astype("int64") // 1_000_000_000)
        frame.to_parquet(timestamp_path, index=False)

        underlying_timestamp_path = Path(self._tmp.name) / "spy_underlying_timestamp.parquet"
        underlying_frame = pd.read_parquet(self.underlying_parquet_path)
        underlying_date_column = "date" if "date" in underlying_frame.columns else "Date"
        underlying_frame["timestamp"] = (
            pd.to_datetime(underlying_frame.pop(underlying_date_column), utc=True).astype("int64") // 1_000_000
        )
        underlying_frame.to_parquet(underlying_timestamp_path, index=False)

        result = import_daily_option_parquet(
            timestamp_path,
            "spy_daily_timestamp",
            underlying="SPY",
            underlying_input=underlying_timestamp_path,
            db_path=self.db_path,
        )

        self.assertGreater(result["imported_rows"], 0)
        self.assertEqual(result["rejected_rows"], 0)
        store = HistoricalOptionsStore(self.db_path)
        trade_date = self.histories["SPY"].index[0].date()
        entry = store.find_entry_contract(
            underlying="SPY",
            trade_date_et=trade_date,
            option_type="call",
            target_expiry=trade_date,
            target_strike=501.0,
            earliest_minute_et=DAILY_QUOTE_MINUTE_ET,
            window_minutes=0,
            snapshot_kind=DAILY_SNAPSHOT_KIND,
        )
        self.assertIsNotNone(entry)
        self.assertIsNotNone(entry.underlying_price)

    def test_import_daily_parquet_rejects_unrecognized_numeric_timestamps(self):
        timestamp_path = Path(self._tmp.name) / "spy_options_bad_timestamp.parquet"
        frame = pd.read_parquet(self.daily_parquet_path).head(3)
        frame["timestamp"] = 1_774_915
        frame = frame.drop(columns=["date"])
        frame.to_parquet(timestamp_path, index=False)

        result = import_daily_option_parquet(
            timestamp_path,
            "spy_daily_bad_timestamp",
            underlying="SPY",
            db_path=self.db_path,
        )

        self.assertEqual(result["imported_rows"], 0)
        self.assertGreater(result["rejected_rows"], 0)
        store = HistoricalOptionsStore(self.db_path)
        self.assertEqual(store.snapshot_summary(DAILY_SNAPSHOT_KIND)["quote_count"], 0)

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

    def test_snapshot_summary_excludes_duplicate_only_batches(self):
        first_result = import_daily_option_parquet(
            self.daily_parquet_path,
            "spy_daily_primary",
            underlying="SPY",
            underlying_input=self.underlying_parquet_path,
            db_path=self.db_path,
        )
        duplicate_result = import_daily_option_parquet(
            self.daily_parquet_path,
            "spy_daily_duplicate",
            underlying="SPY",
            underlying_input=self.underlying_parquet_path,
            db_path=self.db_path,
        )

        self.assertGreater(first_result["imported_rows"], 0)
        self.assertEqual(duplicate_result["imported_rows"], 0)
        self.assertGreater(duplicate_result["duplicate_rows"], 0)

        store = HistoricalOptionsStore(self.db_path)
        daily_summary = store.snapshot_summary(DAILY_SNAPSHOT_KIND)

        self.assertEqual(daily_summary["batch_count"], 1)
        self.assertEqual(daily_summary["source_labels"], ["spy_daily_primary"])
        self.assertEqual(daily_summary["quote_count"], first_result["imported_rows"])

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

    def test_snapshot_summary_can_filter_by_source_label(self):
        histories = {
            "SPY": make_validation_history(length=8, start=500.0, step=0.8),
            "QQQ": make_validation_history(length=8, start=420.0, step=0.9),
        }
        spy_path = Path(self._tmp.name) / "spy_summary_filter.parquet"
        qqq_path = Path(self._tmp.name) / "qqq_summary_filter.parquet"
        write_daily_options_parquet(spy_path, histories, symbol="SPY", strike_span=2)
        write_daily_options_parquet(qqq_path, histories, symbol="QQQ", strike_span=2)

        spy_result = import_daily_option_parquet(
            spy_path,
            "alpaca_opra_daily_snapshot",
            underlying="SPY",
            db_path=self.db_path,
        )
        qqq_result = import_daily_option_parquet(
            qqq_path,
            "other_paid_vendor",
            underlying="QQQ",
            db_path=self.db_path,
        )

        store = HistoricalOptionsStore(self.db_path)
        all_summary = store.snapshot_summary(DAILY_SNAPSHOT_KIND, trusted_only=True)
        alpaca_summary = store.snapshot_summary(
            DAILY_SNAPSHOT_KIND,
            trusted_only=True,
            source_labels=["alpaca_opra_daily_snapshot"],
        )

        self.assertEqual(all_summary["quote_count"], spy_result["imported_rows"] + qqq_result["imported_rows"])
        self.assertEqual(sorted(all_summary["available_underlyings"]), ["QQQ", "SPY"])
        self.assertEqual(alpaca_summary["quote_count"], spy_result["imported_rows"])
        self.assertEqual(alpaca_summary["available_underlyings"], ["SPY"])
        self.assertEqual(alpaca_summary["source_labels"], ["alpaca_opra_daily_snapshot"])
        self.assertEqual(alpaca_summary["source_labels_requested"], ["alpaca_opra_daily_snapshot"])

    def test_quote_date_queries_can_filter_by_source_label(self):
        histories = {
            "SPY": make_validation_history(length=8, start=500.0, step=0.8),
            "QQQ": make_validation_history(length=8, start=420.0, step=0.9),
        }
        spy_path = Path(self._tmp.name) / "spy_source_filter.parquet"
        qqq_path = Path(self._tmp.name) / "qqq_source_filter.parquet"
        write_daily_options_parquet(spy_path, histories, symbol="SPY", strike_span=2)
        write_daily_options_parquet(qqq_path, histories, symbol="QQQ", strike_span=2)

        import_daily_option_parquet(spy_path, "alpaca_opra_daily_snapshot", underlying="SPY", db_path=self.db_path)
        import_daily_option_parquet(qqq_path, "thetadata_free_eod", underlying="QQQ", db_path=self.db_path)

        store = HistoricalOptionsStore(self.db_path)
        spy_alpaca_dates = store.available_quote_dates(
            "SPY",
            snapshot_kind=DAILY_SNAPSHOT_KIND,
            trusted_only=True,
            source_labels=["alpaca_opra_daily_snapshot"],
        )
        spy_theta_dates = store.available_quote_dates(
            "SPY",
            snapshot_kind=DAILY_SNAPSHOT_KIND,
            trusted_only=True,
            source_labels=["thetadata_free_eod"],
        )
        source_shared_dates = store.shared_quote_dates(
            ["SPY", "QQQ"],
            snapshot_kind=DAILY_SNAPSHOT_KIND,
            trusted_only=True,
            source_labels=["alpaca_opra_daily_snapshot"],
        )

        self.assertGreater(len(spy_alpaca_dates), 0)
        self.assertEqual(spy_theta_dates, [])
        self.assertEqual(source_shared_dates, [])

        inventory = store.source_inventory(
            snapshot_kind=DAILY_SNAPSHOT_KIND,
            trusted_only=True,
            underlyings=["SPY", "QQQ"],
        )
        inventory_by_source = {entry["source_label"]: entry for entry in inventory["sources"]}
        self.assertEqual(inventory["status"], "summarized")
        self.assertIn("alpaca_opra_daily_snapshot", inventory["source_labels_seen"])
        self.assertEqual(
            inventory["source_labels_with_quotes_in_scope"],
            ["alpaca_opra_daily_snapshot"],
        )
        self.assertEqual(inventory_by_source["alpaca_opra_daily_snapshot"]["batch_count"], 1)
        self.assertEqual(inventory_by_source["alpaca_opra_daily_snapshot"]["quote_dates"]["count"], len(spy_alpaca_dates))
        self.assertEqual(inventory_by_source["alpaca_opra_daily_snapshot"]["underlyings_in_scope"], ["SPY"])
        self.assertEqual(inventory_by_source["alpaca_opra_daily_snapshot"]["dataset_kinds"], ["daily_parquet"])
        self.assertEqual(inventory_by_source["alpaca_opra_daily_snapshot"]["trust_levels"], ["trusted"])

        all_inventory = store.source_inventory(
            snapshot_kind=DAILY_SNAPSHOT_KIND,
            trusted_only=False,
            underlyings=["SPY", "QQQ"],
        )
        all_inventory_by_source = {entry["source_label"]: entry for entry in all_inventory["sources"]}
        self.assertIn("thetadata_free_eod", all_inventory["source_labels_seen"])
        self.assertEqual(all_inventory_by_source["thetadata_free_eod"]["trust_levels"], ["research"])

        alpaca_inventory = store.source_inventory(
            snapshot_kind=DAILY_SNAPSHOT_KIND,
            trusted_only=True,
            source_labels=["alpaca_opra_daily_snapshot"],
            underlyings=["SPY", "QQQ"],
        )
        self.assertEqual(alpaca_inventory["source_labels_seen"], ["alpaca_opra_daily_snapshot"])
        self.assertEqual(alpaca_inventory["source_labels_with_quotes_in_scope"], ["alpaca_opra_daily_snapshot"])
        self.assertEqual(alpaca_inventory["sources"][0]["underlying_count_in_scope"], 1)

        quote_date = spy_alpaca_dates[0]
        alpaca_quote = store.find_entry_contract(
            underlying="SPY",
            trade_date_et=quote_date,
            option_type="call",
            target_expiry=pd.Timestamp(quote_date).date(),
            target_strike=round(float(histories["SPY"]["Close"].iloc[0]), 0),
            earliest_minute_et=DAILY_QUOTE_MINUTE_ET,
            window_minutes=0,
            snapshot_kind=DAILY_SNAPSHOT_KIND,
            source_labels=["alpaca_opra_daily_snapshot"],
        )
        theta_quote = store.get_exact_quote(
            quote_date_et=quote_date,
            contract_symbol=alpaca_quote.contract_symbol if alpaca_quote else "SPY260101C00000000",
            snapshot_kind=DAILY_SNAPSHOT_KIND,
            source_labels=["thetadata_free_eod"],
        )
        self.assertIsNotNone(alpaca_quote)
        self.assertIsNone(theta_quote)


if __name__ == "__main__":
    unittest.main()
