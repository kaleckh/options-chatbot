import os
import sqlite3
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

import sys


ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from options_algorithm_fixtures import FrozenDateTime, make_history, make_option_frame
from workspace_tempdir import WorkspaceTempDir

import market_data_service as mds


class _RecordingTicker:
    def __init__(self, symbol: str, *, history_df: pd.DataFrame, sector: str = "Technology", option_spot: float = 120.0):
        self.symbol = symbol
        self._history_df = history_df
        self._sector = sector
        self._option_spot = option_spot
        self.history_calls: list[tuple[tuple, dict]] = []
        self.option_calls = 0
        self.option_chain_calls: list[str] = []
        self.fast_info_calls = 0
        self.info_calls = 0
        self.earnings_calls = 0
        self._option_expiries = [
            "2026-04-10",
            "2026-04-17",
        ]
        self._option_chains = {
            exp: SimpleNamespace(
                calls=make_option_frame(self.symbol, exp, "call", self._option_spot, illiquid=False),
                puts=make_option_frame(self.symbol, exp, "put", self._option_spot, illiquid=False),
            )
            for exp in self._option_expiries
        }
        self._fast_info = SimpleNamespace(last_price=float(self._history_df["Close"].iloc[-1]))
        self.earnings_dates = pd.DataFrame()

    @property
    def info(self):
        self.info_calls += 1
        return {
            "sector": self._sector,
            "marketCap": 1_000_000_000,
            "previousClose": float(self._history_df["Close"].iloc[-2]),
            "regularMarketPreviousClose": float(self._history_df["Close"].iloc[-2]),
            "currentPrice": float(self._history_df["Close"].iloc[-1]),
            "regularMarketPrice": float(self._history_df["Close"].iloc[-1]),
            "regularMarketOpen": float(self._history_df["Open"].iloc[-1]),
            "dayHigh": float(self._history_df["High"].iloc[-1]),
            "dayLow": float(self._history_df["Low"].iloc[-1]),
            "regularMarketVolume": float(self._history_df["Volume"].iloc[-1]),
        }

    @property
    def options(self):
        self.option_calls += 1
        return list(self._option_expiries)

    @property
    def fast_info(self):
        self.fast_info_calls += 1
        return self._fast_info

    def history(self, *args, **kwargs):
        self.history_calls.append((args, kwargs))
        return self._history_df.copy()

    def option_chain(self, expiry: str):
        self.option_chain_calls.append(expiry)
        if expiry not in self._option_chains:
            raise KeyError(expiry)
        snap = self._option_chains[expiry]
        return SimpleNamespace(calls=snap.calls.copy(), puts=snap.puts.copy())


class _SourceRecordingTicker(_RecordingTicker):
    def __init__(self, *args, market_data_source: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.market_data_source = market_data_source

    def option_chain(self, expiry: str):
        chain = super().option_chain(expiry)
        chain.market_data_source = self.market_data_source
        chain.source = self.market_data_source
        return chain


class _FailingOptionTicker:
    def __init__(self, symbol: str):
        self.symbol = symbol

    @property
    def options(self):
        raise AssertionError("option expiries should have been served from persistence")

    def option_chain(self, expiry: str):
        raise AssertionError("option chain should have been served from persistence")


class _ExplodingOptionTicker:
    def __init__(self, symbol: str):
        self.symbol = symbol

    @property
    def options(self):
        raise RuntimeError("option expiries unavailable")

    def option_chain(self, expiry: str):
        raise RuntimeError("option chain unavailable")


class MarketDataServiceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = WorkspaceTempDir(prefix="market-data-service")
        self.addCleanup(self._tmp.cleanup)
        self._env_snapshot = {
            key: os.environ.get(key)
            for key in (
                "OPTIONS_MARKET_DATA_PROVIDER",
                "ALPACA_ENABLE_DURING_TESTS",
                "OPTIONS_RUN_MODE",
            )
        }
        os.environ["OPTIONS_MARKET_DATA_PROVIDER"] = "yahoo"
        os.environ.pop("ALPACA_ENABLE_DURING_TESTS", None)
        os.environ["OPTIONS_RUN_MODE"] = "test"
        self.db_path = os.path.join(self._tmp.name, "market_data.db")
        self.history_df = make_history(length=320, start=100.0, step=0.7, wave=1.5, volume=8_000_000)
        self.ticker = _RecordingTicker("AAA", history_df=self.history_df, option_spot=float(self.history_df["Close"].iloc[-1]))
        self.spy_ticker = _RecordingTicker("^VIX", history_df=make_history(length=40, start=18.0, volume=0), sector=None, option_spot=18.0)
        mds._MEMORY_CACHE.clear()
        mds._SCHEMA_READY.clear()
        mds.reset_cache_stats()
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        for key, value in self._env_snapshot.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _service(self):
        return mds

    def _make_ticker_factory(self):
        def _make_ticker(symbol: str):
            if symbol == "^VIX":
                return self.spy_ticker
            return self.ticker

        return _make_ticker

    def test_daily_history_normalizes_period_and_date_range(self):
        service = self._service()
        with patch.dict(os.environ, {"MARKET_DATA_DB_PATH": self.db_path}, clear=False), \
             patch.object(service.yf, "Ticker", side_effect=self._make_ticker_factory()), \
             patch.object(service, "datetime", FrozenDateTime), \
             patch.object(service, "_recent_refresh_start", return_value=FrozenDateTime.now().date() + timedelta(days=365)):
            period_hist = service.get_history("AAA", period="90d", interval="1d")
            start = (FrozenDateTime.now().date() - timedelta(days=90)).isoformat()
            end = (FrozenDateTime.now().date() + timedelta(days=1)).isoformat()
            range_hist = service.get_history("AAA", start=start, end=end, interval="1d")

        self.assertFalse(period_hist.empty)
        self.assertEqual(period_hist["Close"].tolist(), range_hist["Close"].tolist())
        self.assertEqual(len(self.ticker.history_calls), 1)

    def test_recent_window_daily_requests_refresh_trailing_buffer(self):
        service = self._service()
        with patch.dict(os.environ, {"MARKET_DATA_DB_PATH": self.db_path}, clear=False), \
             patch.object(service.yf, "Ticker", side_effect=self._make_ticker_factory()), \
             patch.object(service, "datetime", FrozenDateTime):
            first = service.get_history("AAA", period="10d", interval="1d")
            second = service.get_history("AAA", period="10d", interval="1d")

        self.assertFalse(first.empty)
        self.assertEqual(first["Close"].tolist(), second["Close"].tolist())
        self.assertGreaterEqual(len(self.ticker.history_calls), 2)

    def test_recent_refresh_failures_return_cached_daily_history(self):
        service = self._service()
        with patch.dict(os.environ, {"MARKET_DATA_DB_PATH": self.db_path}, clear=False), \
             patch.object(service.yf, "Ticker", side_effect=self._make_ticker_factory()), \
             patch.object(service, "datetime", FrozenDateTime):
            seeded = service.get_history("AAA", period="10d", interval="1d")

        self.assertFalse(seeded.empty)

        with patch.dict(os.environ, {"MARKET_DATA_DB_PATH": self.db_path}, clear=False), \
             patch.object(service, "_fetch_history_direct", side_effect=RuntimeError("recent refresh unavailable")), \
             patch.object(service, "datetime", FrozenDateTime):
            recovered = service.get_history("AAA", period="10d", interval="1d")

        self.assertEqual(seeded["Close"].tolist(), recovered["Close"].tolist())
        history_stats = service.get_cache_stats()["stats"]["history"]
        self.assertEqual(history_stats["full_refresh_failures"], 1)
        self.assertEqual(history_stats["stale_cache_returns"], 1)

    def test_daily_history_query_uses_native_sqlite_connection_for_pandas(self):
        service = self._service()
        captured: dict[str, object] = {}
        raw_conn = sqlite3.connect(":memory:")
        self.addCleanup(raw_conn.close)
        raw_conn.execute(
            """
            CREATE TABLE daily_history (
                symbol TEXT NOT NULL,
                bar_date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                adj_close REAL,
                volume REAL,
                fetched_at TEXT NOT NULL
            )
            """
        )
        raw_conn.execute(
            """
            INSERT INTO daily_history(symbol, bar_date, open, high, low, close, adj_close, volume, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("AAA", "2026-04-10", 100.0, 101.0, 99.0, 100.5, 100.4, 1000.0, "2026-04-10T00:00:00"),
        )
        raw_conn.commit()
        original_read_sql_query = pd.read_sql_query

        def _fake_read_sql_query(query, conn, params=()):
            captured["conn"] = conn
            return original_read_sql_query(query, conn, params=params)

        proxy = service._SQLiteConnectionProxy(raw_conn, persistent=False)
        with patch.object(service, "_sqlite_connection", return_value=proxy), \
             patch.object(service.pd, "read_sql_query", side_effect=_fake_read_sql_query):
            rows = service._load_daily_history_rows("AAA", pd.Timestamp("2026-04-10").date(), pd.Timestamp("2026-04-10").date())

        self.assertFalse(rows.empty)
        self.assertIsInstance(captured["conn"], sqlite3.Connection)

    def test_ttl_cache_reuses_options_and_fast_info(self):
        service = self._service()
        with patch.dict(os.environ, {"MARKET_DATA_DB_PATH": self.db_path}, clear=False), \
             patch.object(service.yf, "Ticker", side_effect=self._make_ticker_factory()), \
             patch.object(service, "datetime", FrozenDateTime):
            first_options = service.get_options("AAA")
            second_options = service.get_options("AAA")
            first_fast = service.get_fast_info("AAA")
            second_fast = service.get_fast_info("AAA")
            first_chain = service.get_option_chain("AAA", first_options[0])
            second_chain = service.get_option_chain("AAA", first_options[0])

        self.assertEqual(first_options, second_options)
        self.assertEqual(first_fast.last_price, second_fast.last_price)
        self.assertEqual(first_chain.calls["strike"].tolist(), second_chain.calls["strike"].tolist())
        self.assertEqual(self.ticker.option_calls, 1)
        self.assertEqual(self.ticker.fast_info_calls, 1)
        self.assertEqual(self.ticker.option_chain_calls.count(first_options[0]), 1)

    def test_option_expiries_and_chain_snapshots_persist_across_cache_clears(self):
        service = self._service()
        with patch.dict(os.environ, {"MARKET_DATA_DB_PATH": self.db_path}, clear=False), \
             patch.object(service.yf, "Ticker", side_effect=self._make_ticker_factory()), \
             patch.object(service, "datetime", FrozenDateTime):
            expiries = service.get_options("AAA")
            chain = service.get_option_chain("AAA", expiries[0])

        self.assertEqual(self.ticker.option_calls, 1)
        self.assertEqual(self.ticker.option_chain_calls.count(expiries[0]), 1)

        service._MEMORY_CACHE.clear()
        service._SCHEMA_READY.clear()

        with patch.dict(os.environ, {"MARKET_DATA_DB_PATH": self.db_path}, clear=False), \
             patch.object(service.yf, "Ticker", side_effect=lambda symbol: _FailingOptionTicker(symbol)), \
             patch.object(service, "datetime", FrozenDateTime):
            reloaded_expiries = service.get_options("AAA")
            reloaded_chain = service.get_option_chain("AAA", expiries[0])

        self.assertEqual(reloaded_expiries, expiries)
        self.assertEqual(reloaded_chain.calls["strike"].tolist(), chain.calls["strike"].tolist())
        self.assertEqual(reloaded_chain.puts["strike"].tolist(), chain.puts["strike"].tolist())
        self.assertEqual(self.ticker.option_calls, 1)
        self.assertEqual(self.ticker.option_chain_calls.count(expiries[0]), 1)

    def test_option_metadata_reports_fresh_and_stale_states(self):
        service = self._service()

        class _FutureDateTime(FrozenDateTime):
            @classmethod
            def now(cls, tz=None):
                return super().now(tz) + timedelta(minutes=10)

        with patch.dict(os.environ, {"MARKET_DATA_DB_PATH": self.db_path}, clear=False), \
             patch.object(service.yf, "Ticker", side_effect=self._make_ticker_factory()), \
             patch.object(service, "datetime", FrozenDateTime):
            fresh_options = service.get_options("AAA", include_metadata=True)
            fresh_chain = service.get_option_chain("AAA", fresh_options.value[0], include_metadata=True)

        self.assertEqual(fresh_options.status, "fresh")
        self.assertTrue(fresh_options.freshness.fresh)
        self.assertEqual(fresh_chain.status, "fresh")
        self.assertTrue(fresh_chain.freshness.fresh)

        service._MEMORY_CACHE.clear()
        service._SCHEMA_READY.clear()

        with patch.dict(os.environ, {"MARKET_DATA_DB_PATH": self.db_path}, clear=False), \
             patch.object(service.yf, "Ticker", side_effect=lambda symbol: _FailingOptionTicker(symbol)), \
             patch.object(service, "datetime", _FutureDateTime):
            stale_options = service.get_options("AAA", include_metadata=True)
            stale_chain = service.get_option_chain("AAA", fresh_options.value[0], include_metadata=True)

        self.assertEqual(stale_options.status, "stale")
        self.assertTrue(stale_options.freshness.stale)
        self.assertGreater(stale_options.freshness.age_seconds, stale_options.freshness.ttl_seconds)
        self.assertEqual(stale_options.value, fresh_options.value)
        self.assertEqual(stale_chain.status, "stale")
        self.assertTrue(stale_chain.freshness.stale)
        self.assertGreater(stale_chain.freshness.age_seconds, stale_chain.freshness.ttl_seconds)
        self.assertEqual(stale_chain.value.calls["strike"].tolist(), fresh_chain.value.calls["strike"].tolist())
        self.assertEqual(stale_chain.value.puts["strike"].tolist(), fresh_chain.value.puts["strike"].tolist())

    def test_option_metadata_refreshes_stale_cache_when_network_is_available(self):
        service = self._service()

        class _FutureDateTime(FrozenDateTime):
            @classmethod
            def now(cls, tz=None):
                return super().now(tz) + timedelta(minutes=10)

        with patch.dict(os.environ, {"MARKET_DATA_DB_PATH": self.db_path}, clear=False), \
             patch.object(service.yf, "Ticker", side_effect=self._make_ticker_factory()), \
             patch.object(service, "datetime", FrozenDateTime):
            fresh_options = service.get_options("AAA", include_metadata=True)
            fresh_chain = service.get_option_chain("AAA", fresh_options.value[0], include_metadata=True)

        service._MEMORY_CACHE.clear()
        service._SCHEMA_READY.clear()

        with patch.dict(os.environ, {"MARKET_DATA_DB_PATH": self.db_path}, clear=False), \
             patch.object(service.yf, "Ticker", side_effect=self._make_ticker_factory()), \
             patch.object(service, "datetime", _FutureDateTime):
            refreshed_options = service.get_options("AAA", include_metadata=True)
            refreshed_chain = service.get_option_chain("AAA", fresh_options.value[0], include_metadata=True)

        self.assertEqual(refreshed_options.status, "fresh")
        self.assertEqual(refreshed_chain.status, "fresh")
        self.assertEqual(refreshed_options.value, fresh_options.value)
        self.assertEqual(refreshed_chain.value.calls["strike"].tolist(), fresh_chain.value.calls["strike"].tolist())
        self.assertGreaterEqual(self.ticker.option_calls, 2)
        self.assertGreaterEqual(self.ticker.option_chain_calls.count(fresh_options.value[0]), 2)

    def test_alpaca_opra_mode_refreshes_fresh_non_opra_option_cache(self):
        service = self._service()
        alpaca_ticker = _SourceRecordingTicker(
            "AAA",
            history_df=self.history_df,
            option_spot=float(self.history_df["Close"].iloc[-1]),
            market_data_source="alpaca_opra",
        )

        with patch.dict(os.environ, {"MARKET_DATA_DB_PATH": self.db_path}, clear=False), \
             patch.object(service.yf, "Ticker", side_effect=self._make_ticker_factory()), \
             patch.object(service, "datetime", FrozenDateTime):
            stale_provider_options = service.get_options("AAA", include_metadata=True)
            stale_provider_chain = service.get_option_chain("AAA", stale_provider_options.value[0], include_metadata=True)

        self.assertEqual(stale_provider_options.source, "network")
        self.assertEqual(stale_provider_chain.source, "network")

        service._MEMORY_CACHE.clear()
        service._SCHEMA_READY.clear()

        alpaca_env = {
            "MARKET_DATA_DB_PATH": self.db_path,
            "PYTEST_CURRENT_TEST": "market-data-service-provider-cache",
            "ALPACA_ENABLE_DURING_TESTS": "1",
            "OPTIONS_MARKET_DATA_PROVIDER": "alpaca",
            "OPTIONS_RUN_MODE": "live",
            "OPTIONS_IS_FIXTURE": "0",
            "APCA_API_KEY_ID": "test-key",
            "APCA_API_SECRET_KEY": "test-secret",
            "ALPACA_OPTIONS_FEED": "opra",
        }
        with patch.dict(os.environ, alpaca_env, clear=False), \
             patch.object(service, "make_alpaca_ticker_factory", return_value=lambda symbol: alpaca_ticker), \
             patch.object(service, "datetime", FrozenDateTime):
            refreshed_options = service.get_options("AAA", include_metadata=True)
            refreshed_chain = service.get_option_chain("AAA", refreshed_options.value[0], include_metadata=True)

        self.assertEqual(refreshed_options.source, "alpaca_opra")
        self.assertEqual(refreshed_chain.source, "alpaca_opra")
        self.assertEqual(alpaca_ticker.option_calls, 1)
        self.assertEqual(alpaca_ticker.option_chain_calls.count(refreshed_options.value[0]), 1)
        self.assertEqual(service.get_cache_stats()["stats"]["options"]["persistent_provider_mismatches"], 1)
        self.assertEqual(service.get_cache_stats()["stats"]["option_chain"]["persistent_provider_mismatches"], 1)

    def test_alpaca_requested_requires_alpaca_cache_source_even_without_credentials(self):
        service = self._service()
        env = {
            "PYTEST_CURRENT_TEST": "market-data-service-provider-cache",
            "ALPACA_ENABLE_DURING_TESTS": "1",
            "OPTIONS_MARKET_DATA_PROVIDER": "alpaca",
            "OPTIONS_RUN_MODE": "live",
            "OPTIONS_IS_FIXTURE": "0",
            "ALPACA_STOCK_FEED": "sip",
            "ALPACA_OPTIONS_FEED": "opra",
        }
        with patch.dict(os.environ, env, clear=False):
            self.assertEqual(service._required_stock_cache_source(), "alpaca_sip")
            self.assertEqual(service._required_options_cache_source(), "alpaca_opra")

    def test_alpaca_mode_default_factory_does_not_call_yfinance(self):
        service = self._service()
        alpaca_ticker = _SourceRecordingTicker(
            "AAA",
            history_df=self.history_df,
            option_spot=float(self.history_df["Close"].iloc[-1]),
            market_data_source="alpaca_sip",
        )
        env = {
            "MARKET_DATA_DB_PATH": self.db_path,
            "PYTEST_CURRENT_TEST": "market-data-service-provider-cache",
            "ALPACA_ENABLE_DURING_TESTS": "1",
            "OPTIONS_MARKET_DATA_PROVIDER": "alpaca",
            "OPTIONS_RUN_MODE": "live",
            "OPTIONS_IS_FIXTURE": "0",
            "APCA_API_KEY_ID": "test-key",
            "APCA_API_SECRET_KEY": "test-secret",
            "ALPACA_STOCK_FEED": "sip",
        }
        with patch.dict(os.environ, env, clear=False), \
             patch.object(service, "make_alpaca_ticker_factory", return_value=lambda symbol: alpaca_ticker), \
             patch.object(service.yf, "Ticker", side_effect=AssertionError("yfinance should not be called")):
            history = service.get_history("AAA", period="5d")

        self.assertFalse(history.empty)
        self.assertEqual(history.attrs["market_data_source"], "alpaca_sip")

    def test_option_metadata_marks_network_failures_as_error(self):
        service = self._service()
        with patch.dict(os.environ, {"MARKET_DATA_DB_PATH": self.db_path}, clear=False), \
             patch.object(service.yf, "Ticker", side_effect=lambda symbol: _FailingOptionTicker(symbol)), \
             patch.object(service, "datetime", FrozenDateTime):
            options = service.get_options("AAA", include_metadata=True)
            chain = service.get_option_chain("AAA", "2026-04-10", include_metadata=True)

        self.assertEqual(options.status, "error")
        self.assertFalse(options.freshness.fresh)
        self.assertEqual(options.value, [])
        self.assertEqual(chain.status, "error")
        self.assertFalse(chain.freshness.fresh)
        self.assertTrue(chain.value.calls.empty)
        self.assertTrue(chain.value.puts.empty)

    def test_non_metadata_option_fetch_raises_when_no_truth_is_available(self):
        service = self._service()
        with patch.dict(os.environ, {"MARKET_DATA_DB_PATH": self.db_path}, clear=False), \
             patch.object(service.yf, "Ticker", side_effect=lambda symbol: _ExplodingOptionTicker(symbol)), \
             patch.object(service, "datetime", FrozenDateTime):
            with self.assertRaisesRegex(RuntimeError, "option expiries fetch failed"):
                service.get_options("AAA")
            with self.assertRaisesRegex(RuntimeError, "option chain fetch failed"):
                service.get_option_chain("AAA", "2026-04-10")

    def test_ticker_info_cache_reuses_reference_fields(self):
        service = self._service()
        with patch.dict(os.environ, {"MARKET_DATA_DB_PATH": self.db_path}, clear=False), \
             patch.object(service.yf, "Ticker", side_effect=self._make_ticker_factory()), \
             patch.object(service, "datetime", FrozenDateTime):
            first = service.get_ticker_info("AAA")
            second = service.get_ticker_info("AAA")

        self.assertEqual(first["sector"], "Technology")
        self.assertEqual(first["marketCap"], 1_000_000_000)
        self.assertEqual(first["regularMarketVolume"], float(self.history_df["Volume"].iloc[-1]))
        self.assertEqual(second["currentPrice"], first["currentPrice"])
        self.assertEqual(self.ticker.info_calls, 1)

    def test_download_history_batch_reuses_cached_daily_histories(self):
        service = self._service()
        ticker_b = _RecordingTicker("BBB", history_df=make_history(length=320, start=75.0, step=0.4, wave=1.0, volume=7_500_000))
        tickers = {
            "AAA": self.ticker,
            "BBB": ticker_b,
        }

        def _factory(symbol: str):
            return tickers[symbol]

        def _unexpected_download(*args, **kwargs):
            raise AssertionError("batch download should not be needed when per-symbol cache is available")

        with patch.dict(os.environ, {"MARKET_DATA_DB_PATH": self.db_path}, clear=False), \
             patch.object(service.yf, "Ticker", side_effect=_factory), \
             patch.object(service, "datetime", FrozenDateTime), \
             patch.object(service, "_recent_refresh_start", return_value=FrozenDateTime.now().date() + timedelta(days=365)):
            first = service.download_history_batch(["AAA", "BBB"], period="90d", download_fn=_unexpected_download)
            second = service.download_history_batch(["AAA", "BBB"], period="90d", download_fn=_unexpected_download)

        self.assertFalse(first.empty)
        self.assertEqual(first["Close"]["AAA"].tolist(), second["Close"]["AAA"].tolist())
        self.assertEqual(len(self.ticker.history_calls), 1)
        self.assertEqual(len(ticker_b.history_calls), 1)
        self.assertEqual(self.ticker.history_calls[0][1]["start"], "2025-12-31")
        self.assertEqual(self.ticker.history_calls[0][1]["end"], "2026-04-01")
        self.assertEqual(self.ticker.history_calls[0][1]["interval"], "1d")
        self.assertEqual(ticker_b.history_calls[0][1]["start"], "2025-12-31")

    def test_cache_stats_track_memory_hits_request_hits_and_network_fetches(self):
        service = self._service()
        with patch.dict(os.environ, {"MARKET_DATA_DB_PATH": self.db_path}, clear=False), \
             patch.object(service.yf, "Ticker", side_effect=self._make_ticker_factory()), \
             patch.object(service, "datetime", FrozenDateTime):
            with service.request_scope():
                first_options = service.get_options("AAA")
                second_options = service.get_options("AAA")
                self.assertEqual(first_options, second_options)
            first_fast = service.get_fast_info("AAA")
            second_fast = service.get_fast_info("AAA")
            self.assertEqual(first_fast.last_price, second_fast.last_price)

        stats = service.get_cache_stats()["stats"]
        self.assertEqual(stats["options"]["memory_misses"], 1)
        self.assertEqual(stats["options"]["network_fetches"], 1)
        self.assertEqual(stats["options"]["request_memo_hits"], 1)
        self.assertEqual(stats["fast_info"]["memory_misses"], 1)
        self.assertEqual(stats["fast_info"]["memory_hits"], 1)
        self.assertEqual(stats["fast_info"]["network_fetches"], 1)

    def test_cache_stats_track_daily_history_hits_and_refreshes(self):
        service = self._service()
        with patch.dict(os.environ, {"MARKET_DATA_DB_PATH": self.db_path}, clear=False), \
             patch.object(service.yf, "Ticker", side_effect=self._make_ticker_factory()), \
             patch.object(service, "datetime", FrozenDateTime), \
             patch.object(service, "_recent_refresh_start", return_value=FrozenDateTime.now().date() + timedelta(days=365)):
            first = service.get_history("AAA", period="90d", interval="1d")
            second = service.get_history("AAA", period="90d", interval="1d")

        self.assertFalse(first.empty)
        self.assertEqual(first["Close"].tolist(), second["Close"].tolist())
        history_stats = service.get_cache_stats()["stats"]["history"]
        self.assertEqual(history_stats["persistent_misses"], 1)
        self.assertEqual(history_stats["full_refreshes"], 1)
        self.assertEqual(history_stats["persistent_hits"], 1)
        self.assertEqual(history_stats["network_fetches"], 1)

    def test_cache_stats_track_fallback_fetches_on_cache_failure(self):
        service = self._service()
        with patch.dict(os.environ, {"MARKET_DATA_DB_PATH": self.db_path}, clear=False), \
             patch.object(service.yf, "Ticker", side_effect=self._make_ticker_factory()), \
             patch.object(sqlite3, "connect", side_effect=sqlite3.OperationalError("cache unavailable")), \
             patch.object(service, "datetime", FrozenDateTime):
            hist = service.get_history("AAA", period="90d", interval="1d")

        self.assertFalse(hist.empty)
        history_stats = service.get_cache_stats()["stats"]["history"]
        self.assertEqual(history_stats["cache_failures"], 1)
        self.assertEqual(history_stats["fallback_fetches"], 1)
        self.assertEqual(history_stats["network_fetches"], 1)

    def test_cache_db_failures_fall_back_to_direct_yahoo_fetch(self):
        service = self._service()
        with patch.dict(os.environ, {"MARKET_DATA_DB_PATH": self.db_path}, clear=False), \
             patch.object(service.yf, "Ticker", side_effect=self._make_ticker_factory()), \
             patch.object(sqlite3, "connect", side_effect=sqlite3.OperationalError("cache unavailable")), \
             patch.object(service, "datetime", FrozenDateTime):
            hist = service.get_history("AAA", period="90d", interval="1d")

        self.assertFalse(hist.empty)
        self.assertEqual(len(self.ticker.history_calls), 1)
