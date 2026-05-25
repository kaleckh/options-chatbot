from __future__ import annotations

import os
import sys
import unittest
from contextlib import redirect_stdout
from datetime import UTC, date, datetime
from io import StringIO
from pathlib import Path
from unittest.mock import patch

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from historical_options_store import DAILY_SNAPSHOT_KIND, HistoricalOptionsStore, import_historical_option_snapshots
from ai_commodity_universe import ai_commodity_scan_tickers
from scripts.capture_alpaca_opra_daily_snapshots import (  # noqa: E402
    DAILY_DATASET_KIND,
    DEFAULT_HISTORICAL_DB_PATH,
    _default_csv_path,
    _parse_symbol_list,
    build_alpaca_opra_daily_snapshot,
    load_env_file,
    main,
    resolve_target_trade_date,
    write_snapshot_csv,
)
from workspace_tempdir import WorkspaceTempDir  # noqa: E402


class _FakeAlpacaSnapshotClient:
    def latest_stock_bar(self, symbol):
        return {"c": 44.25}

    def option_contracts(self, symbol, **kwargs):
        return [
            {
                "symbol": "FCX260619C00045000",
                "expiration_date": "2026-06-19",
                "strike_price": "45",
                "type": "call",
                "open_interest": "1200",
                "tradable": True,
                "underlying_symbol": "FCX",
            },
            {
                "symbol": "FCX260619P00042000",
                "expiration_date": "2026-06-19",
                "strike_price": "42",
                "type": "put",
                "open_interest": "900",
                "tradable": True,
                "underlying_symbol": "FCX",
            },
        ]

    def option_chain_snapshots(self, symbol, *, expiration_date, option_type=None):
        if option_type == "call":
            return {
                "FCX260619C00045000": {
                    "latestQuote": {"bp": 1.4, "ap": 1.55, "t": "2026-05-20T19:55:00Z"},
                    "latestTrade": {"p": 1.48, "t": "2026-05-20T19:54:00Z"},
                    "dailyBar": {"v": 321},
                    "greeks": {"delta": 0.48, "iv": 0.32},
                }
            }
        return {
            "FCX260619P00042000": {
                "latestQuote": {"bp": 0.85, "ap": 0.95, "t": "2026-05-19T19:55:00Z"},
                "latestTrade": {"p": 0.9, "t": "2026-05-19T19:54:00Z"},
                "dailyBar": {"v": 111},
                "greeks": {"delta": -0.33, "iv": 0.34},
            }
        }


class AlpacaOpraDailySnapshotCaptureTests(unittest.TestCase):
    def setUp(self):
        self._tmp = WorkspaceTempDir(prefix="alpaca-opra-capture")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_resolve_target_trade_date_rejects_future_weekend_or_market_holiday_targets(self):
        now_utc = datetime(2026, 5, 21, 2, 30, tzinfo=UTC)

        self.assertEqual(
            resolve_target_trade_date(now_utc=now_utc, requested_target_date="2026-05-20"),
            date(2026, 5, 20),
        )
        with self.assertRaisesRegex(ValueError, "later than the latest snapshot-capturable trade date"):
            resolve_target_trade_date(now_utc=now_utc, requested_target_date="2026-05-21")
        with self.assertRaisesRegex(ValueError, "not a US equity market"):
            resolve_target_trade_date(now_utc=now_utc, requested_target_date="2026-05-23")
        with self.assertRaisesRegex(ValueError, "not a US equity market"):
            resolve_target_trade_date(now_utc=datetime(2026, 5, 26, 21, 0, tzinfo=UTC), requested_target_date="2026-05-25")

    def test_resolve_target_trade_date_waits_until_after_market_close_and_skips_holidays(self):
        before_open_utc = datetime(2026, 5, 21, 4, 7, tzinfo=UTC)
        after_close_utc = datetime(2026, 5, 21, 20, 30, tzinfo=UTC)
        memorial_day_after_close_utc = datetime(2026, 5, 25, 20, 30, tzinfo=UTC)
        day_after_memorial_day_before_close_utc = datetime(2026, 5, 26, 19, 0, tzinfo=UTC)

        self.assertEqual(resolve_target_trade_date(now_utc=before_open_utc), date(2026, 5, 20))
        with self.assertRaisesRegex(ValueError, "later than the latest snapshot-capturable trade date"):
            resolve_target_trade_date(now_utc=before_open_utc, requested_target_date="2026-05-21")
        self.assertEqual(resolve_target_trade_date(now_utc=after_close_utc), date(2026, 5, 21))
        self.assertEqual(resolve_target_trade_date(now_utc=memorial_day_after_close_utc), date(2026, 5, 22))
        self.assertEqual(
            resolve_target_trade_date(now_utc=day_after_memorial_day_before_close_utc),
            date(2026, 5, 22),
        )

    def test_default_symbol_capture_scope_is_full_ai_commodity_scan_universe(self):
        symbols = _parse_symbol_list(None)

        self.assertEqual(symbols, ai_commodity_scan_tickers())
        self.assertGreater(len(symbols), 9)
        self.assertEqual(
            _default_csv_path(self.tmp, symbols, date(2026, 5, 20)).name,
            "alpaca_opra_daily_ai_commodity_scan_2026-05-20.csv",
        )

    def test_load_env_file_sets_missing_capture_credentials_without_overwriting(self):
        env_path = self.tmp / ".env.local"
        env_path.write_text(
            "\n".join(
                [
                    "APCA_API_KEY_ID=file-key",
                    "APCA_API_SECRET_KEY='file-secret'",
                    "ALPACA_OPTIONS_FEED=opra",
                ]
            ),
            encoding="utf8",
        )

        with patch.dict(os.environ, {"APCA_API_KEY_ID": "existing-key"}, clear=False):
            os.environ.pop("APCA_API_SECRET_KEY", None)
            os.environ.pop("ALPACA_OPTIONS_FEED", None)
            loaded = load_env_file(env_path)

            self.assertEqual(os.environ["APCA_API_KEY_ID"], "existing-key")
            self.assertEqual(os.environ["APCA_API_SECRET_KEY"], "file-secret")
            self.assertEqual(os.environ["ALPACA_OPTIONS_FEED"], "opra")
            self.assertEqual(loaded, {"APCA_API_SECRET_KEY": "file-secret", "ALPACA_OPTIONS_FEED": "opra"})

    def test_main_defaults_to_canonical_lane_db_path(self):
        captured: dict[str, Path] = {}

        class _FakeStore:
            def __init__(self, db_path):
                captured["db_path"] = Path(db_path)

            def snapshot_summary(self, *args, **kwargs):
                return {"quote_count": 0}

        def _fake_build(**kwargs):
            return {
                "provider": "alpaca:sip:opra",
                "options_source": "alpaca_opra",
                "captured_at_utc": "2026-05-21T06:00:00Z",
                "target_date": "2026-05-20",
                "symbols": kwargs["symbols"],
                "min_dte": kwargs["min_dte"],
                "max_dte": kwargs["max_dte"],
                "require_fresh_quote_date": kwargs["require_fresh_quote_date"],
                "request_count": 0,
                "generated_rows": 0,
                "rows_by_symbol": {},
                "skips_by_symbol": {},
                "errors": [],
                "rows": [],
            }

        env_file = self.tmp / "missing.env"
        argv = [
            "capture_alpaca_opra_daily_snapshots.py",
            "--env-file",
            str(env_file),
            "--symbols",
            "FCX",
            "--target-date",
            "2026-05-20",
            "--dry-run",
            "--json",
        ]
        with patch.dict(os.environ, {"HISTORICAL_OPTIONS_DB_PATH": "tmp_public/bad.db"}, clear=False), \
            patch.object(sys, "argv", argv), \
            patch("scripts.capture_alpaca_opra_daily_snapshots.alpaca_enabled", return_value=True), \
            patch("scripts.capture_alpaca_opra_daily_snapshots.build_alpaca_opra_daily_snapshot", side_effect=_fake_build), \
            patch("scripts.capture_alpaca_opra_daily_snapshots.HistoricalOptionsStore", _FakeStore), \
            redirect_stdout(StringIO()):
            self.assertEqual(main(), 0)
            self.assertEqual(Path(os.environ["HISTORICAL_OPTIONS_DB_PATH"]), DEFAULT_HISTORICAL_DB_PATH)

        self.assertEqual(captured["db_path"], DEFAULT_HISTORICAL_DB_PATH)

    def test_build_snapshot_keeps_only_fresh_executable_opra_quotes(self):
        with patch.dict(os.environ, {"ALPACA_OPTIONS_FEED": "opra"}, clear=False):
            result = build_alpaca_opra_daily_snapshot(
                symbols=["FCX"],
                client=_FakeAlpacaSnapshotClient(),
                captured_at_utc=datetime(2026, 5, 20, 20, 5, tzinfo=UTC),
                target_date=date(2026, 5, 20),
                min_dte=5,
                max_dte=60,
            )

        self.assertEqual(result["options_source"], "alpaca_opra")
        self.assertEqual(result["generated_rows"], 1)
        self.assertEqual(result["rows_by_symbol"], {"FCX": 1})
        self.assertEqual(result["skips_by_symbol"]["FCX"]["stale_quote_date"], 1)
        row = result["rows"][0]
        self.assertEqual(row["contract_symbol"], "FCX260619C00045000")
        self.assertEqual(row["as_of_utc"], "2026-05-20T19:55:00Z")
        self.assertEqual(row["underlying_price"], 44.25)
        self.assertEqual(row["bid"], 1.4)
        self.assertEqual(row["ask"], 1.55)

    def test_snapshot_csv_imports_as_trusted_daily_replay_data(self):
        with patch.dict(os.environ, {"ALPACA_OPTIONS_FEED": "opra"}, clear=False):
            result = build_alpaca_opra_daily_snapshot(
                symbols=["FCX"],
                client=_FakeAlpacaSnapshotClient(),
                captured_at_utc=datetime(2026, 5, 20, 20, 5, tzinfo=UTC),
                target_date=date(2026, 5, 20),
                min_dte=5,
                max_dte=60,
            )

        csv_path = self.tmp / "alpaca_opra_daily.csv"
        db_path = self.tmp / "options_history.db"
        write_snapshot_csv(csv_path, result["rows"])
        import_result = import_historical_option_snapshots(
            csv_path,
            "alpaca_opra_daily_snapshot",
            dataset_kind=DAILY_DATASET_KIND,
            snapshot_kind=DAILY_SNAPSHOT_KIND,
            db_path=db_path,
        )
        store = HistoricalOptionsStore(db_path)

        self.assertEqual(import_result["imported_rows"], 1)
        self.assertEqual(store.list_available_underlyings(DAILY_SNAPSHOT_KIND, trusted_only=True), ["FCX"])
        self.assertEqual(store.available_quote_dates("FCX", snapshot_kind=DAILY_SNAPSHOT_KIND, trusted_only=True), ["2026-05-20"])
        quote = store.find_entry_quote_for_contract(
            contract_symbol="FCX260619C00045000",
            trade_date_et="2026-05-20",
            snapshot_kind=DAILY_SNAPSHOT_KIND,
            allow_last_price=False,
        )
        self.assertIsNotNone(quote)
        self.assertEqual(quote.price_basis, "mid")


if __name__ == "__main__":
    unittest.main()
