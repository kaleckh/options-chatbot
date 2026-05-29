from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import UTC, date, datetime, time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

import historical_options_store as hos
import wfo_optimizer as wfo


def _as_of_utc(quote_date: date, minute_et: int) -> str:
    eastern = ZoneInfo("America/New_York")
    stamp = datetime.combine(
        quote_date,
        time(hour=minute_et // 60, minute=minute_et % 60),
        tzinfo=eastern,
    )
    return stamp.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _insert_quote(
    db_path: Path,
    *,
    contract_symbol: str,
    quote_date: str,
    source_batch_id: int,
    bid: float = 1.0,
    ask: float = 1.2,
) -> None:
    quote_day = date.fromisoformat(quote_date)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO option_quote_snapshots (
                as_of_utc, quote_date_et, quote_minute_et, snapshot_kind,
                underlying, contract_symbol, expiry, option_type, strike,
                bid, ask, last, iv, underlying_price, volume, open_interest, source_batch_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _as_of_utc(quote_day, hos.ENTRY_QUOTE_MINUTE_ET),
                quote_date,
                hos.ENTRY_QUOTE_MINUTE_ET,
                hos.INTRADAY_SNAPSHOT_KIND,
                "AAA",
                contract_symbol,
                "2026-02-20",
                "call",
                100.0,
                bid,
                ask,
                (bid + ask) / 2.0,
                0.25,
                100.0,
                10,
                100,
                source_batch_id,
            ),
        )
        conn.commit()


class ChainNativeContinuityTests(unittest.TestCase):
    def test_contract_quote_continuity_is_past_only_and_source_scoped(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_path = Path(tmp) / "options.db"
            hos.init_schema(db_path)
            with sqlite3.connect(db_path) as conn:
                trusted_batch_id = conn.execute(
                    """
                    INSERT INTO import_batches (
                        source_label, dataset_kind, data_trust, input_path, file_hash,
                        imported_at_utc, total_rows, imported_rows, duplicate_rows, rejected_rows
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "thetadata_opra_nbbo_1m",
                        "intraday_csv",
                        "trusted",
                        "trusted.csv",
                        "hash1",
                        "2026-01-01T00:00:00Z",
                        3,
                        3,
                        0,
                        0,
                    ),
                ).lastrowid
                other_batch_id = conn.execute(
                    """
                    INSERT INTO import_batches (
                        source_label, dataset_kind, data_trust, input_path, file_hash,
                        imported_at_utc, total_rows, imported_rows, duplicate_rows, rejected_rows
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "other_source",
                        "intraday_csv",
                        "trusted",
                        "other.csv",
                        "hash2",
                        "2026-01-01T00:00:00Z",
                        1,
                        1,
                        0,
                        0,
                    ),
                ).lastrowid
                conn.commit()

            _insert_quote(db_path, contract_symbol="AAA260220C00100000", quote_date="2026-01-10", source_batch_id=trusted_batch_id)
            _insert_quote(db_path, contract_symbol="AAA260220C00100000", quote_date="2026-01-14", source_batch_id=trusted_batch_id)
            _insert_quote(db_path, contract_symbol="AAA260220C00100000", quote_date="2026-01-15", source_batch_id=trusted_batch_id)
            _insert_quote(db_path, contract_symbol="AAA260220C00100000", quote_date="2026-01-13", source_batch_id=other_batch_id)

            store = hos.HistoricalOptionsStore(db_path)
            metrics = store.contract_quote_continuity_metrics(
                contract_symbol="AAA260220C00100000",
                before_date_et="2026-01-15",
                lookback_calendar_days=14,
                snapshot_kind=hos.INTRADAY_SNAPSHOT_KIND,
                source_labels=["thetadata_opra_nbbo_1m"],
            )

        self.assertEqual(metrics["quote_date_count"], 2)
        self.assertEqual(metrics["first_quote_date_et"], "2026-01-10")
        self.assertEqual(metrics["last_quote_date_et"], "2026-01-14")

    def test_chain_native_selection_skips_short_leg_without_prior_continuity(self):
        entry_date = date(2026, 1, 15)
        quotes = [
            SimpleNamespace(
                contract_symbol="AAA260220C00100000",
                expiry="2026-02-20",
                strike=100.0,
                bid=4.9,
                ask=5.1,
                last=5.0,
                volume=10,
                open_interest=100,
            ),
            SimpleNamespace(
                contract_symbol="AAA260220C00105000",
                expiry="2026-02-20",
                strike=105.0,
                bid=1.9,
                ask=2.1,
                last=2.0,
                volume=10,
                open_interest=100,
            ),
            SimpleNamespace(
                contract_symbol="AAA260220C00110000",
                expiry="2026-02-20",
                strike=110.0,
                bid=0.9,
                ask=1.1,
                last=1.0,
                volume=10,
                open_interest=100,
            ),
        ]

        class _Store:
            def list_entry_contracts(self, **kwargs):
                return quotes

            def contract_quote_continuity_metrics(self, *, contract_symbol, **kwargs):
                counts = {
                    "AAA260220C00100000": 3,
                    "AAA260220C00105000": 0,
                    "AAA260220C00110000": 3,
                }
                return {"contract_symbol": contract_symbol, "quote_date_count": counts[contract_symbol]}

        def _delta(quote, **kwargs):
            return {
                "AAA260220C00100000": 0.50,
                "AAA260220C00105000": 0.20,
                "AAA260220C00110000": 0.25,
            }[quote.contract_symbol]

        with patch.object(wfo, "_option_delta_for_quote", side_effect=_delta):
            selected = wfo._select_chain_native_spread(
                store=_Store(),
                ticker="AAA",
                entry_date=entry_date,
                trade_type="call",
                S0=100.0,
                hv30=0.25,
                long_delta_target=0.50,
                short_delta_target=0.20,
                target_dte=35,
                min_dte=28,
                max_dte=45,
                max_width_pct=20.0,
                max_debit_pct_of_width=90.0,
                iv_adj=1.0,
                requested_pricing_lane="pessimistic",
                entry_slippage_pct=0.0,
                snapshot_kind=hos.INTRADAY_SNAPSHOT_KIND,
                entry_quote_minute_et=hos.ENTRY_QUOTE_MINUTE_ET,
                entry_window_minutes=15,
                source_labels=["thetadata_opra_nbbo_1m"],
                min_prior_quote_days=2,
                prior_quote_lookback_days=14,
            )

        self.assertIsNotNone(selected)
        self.assertEqual(selected[1].contract_symbol, "AAA260220C00110000")

    def test_chain_native_selection_can_require_short_leg_continuity_only(self):
        entry_date = date(2026, 1, 15)
        quotes = [
            SimpleNamespace(
                contract_symbol="AAA260220C00100000",
                expiry="2026-02-20",
                strike=100.0,
                bid=4.9,
                ask=5.1,
                last=5.0,
                volume=10,
                open_interest=100,
            ),
            SimpleNamespace(
                contract_symbol="AAA260220C00105000",
                expiry="2026-02-20",
                strike=105.0,
                bid=1.9,
                ask=2.1,
                last=2.0,
                volume=10,
                open_interest=100,
            ),
            SimpleNamespace(
                contract_symbol="AAA260220C00110000",
                expiry="2026-02-20",
                strike=110.0,
                bid=0.9,
                ask=1.1,
                last=1.0,
                volume=10,
                open_interest=100,
            ),
        ]

        class _Store:
            def list_entry_contracts(self, **kwargs):
                return quotes

            def contract_quote_continuity_metrics(self, *, contract_symbol, **kwargs):
                counts = {
                    "AAA260220C00100000": 0,
                    "AAA260220C00105000": 0,
                    "AAA260220C00110000": 3,
                }
                return {"contract_symbol": contract_symbol, "quote_date_count": counts[contract_symbol]}

        def _delta(quote, **kwargs):
            return {
                "AAA260220C00100000": 0.50,
                "AAA260220C00105000": 0.20,
                "AAA260220C00110000": 0.25,
            }[quote.contract_symbol]

        with patch.object(wfo, "_option_delta_for_quote", side_effect=_delta):
            selected = wfo._select_chain_native_spread(
                store=_Store(),
                ticker="AAA",
                entry_date=entry_date,
                trade_type="call",
                S0=100.0,
                hv30=0.25,
                long_delta_target=0.50,
                short_delta_target=0.20,
                target_dte=35,
                min_dte=28,
                max_dte=45,
                max_width_pct=20.0,
                max_debit_pct_of_width=90.0,
                iv_adj=1.0,
                requested_pricing_lane="pessimistic",
                entry_slippage_pct=0.0,
                snapshot_kind=hos.INTRADAY_SNAPSHOT_KIND,
                entry_quote_minute_et=hos.ENTRY_QUOTE_MINUTE_ET,
                entry_window_minutes=15,
                source_labels=["thetadata_opra_nbbo_1m"],
                min_prior_quote_days=0,
                min_short_prior_quote_days=2,
                prior_quote_lookback_days=14,
            )

        self.assertIsNotNone(selected)
        self.assertEqual(selected[0].contract_symbol, "AAA260220C00100000")
        self.assertEqual(selected[1].contract_symbol, "AAA260220C00110000")

    def test_chain_native_selection_can_score_short_leg_continuity(self):
        entry_date = date(2026, 1, 15)
        quotes = [
            SimpleNamespace(
                contract_symbol="AAA260220C00100000",
                expiry="2026-02-20",
                strike=100.0,
                bid=4.9,
                ask=5.1,
                last=5.0,
                volume=10,
                open_interest=100,
            ),
            SimpleNamespace(
                contract_symbol="AAA260220C00105000",
                expiry="2026-02-20",
                strike=105.0,
                bid=1.9,
                ask=2.1,
                last=2.0,
                volume=10,
                open_interest=100,
            ),
            SimpleNamespace(
                contract_symbol="AAA260220C00110000",
                expiry="2026-02-20",
                strike=110.0,
                bid=0.9,
                ask=1.1,
                last=1.0,
                volume=10,
                open_interest=100,
            ),
        ]

        class _Store:
            def list_entry_contracts(self, **kwargs):
                return quotes

            def contract_quote_continuity_metrics(self, *, contract_symbol, **kwargs):
                counts = {
                    "AAA260220C00100000": 5,
                    "AAA260220C00105000": 1,
                    "AAA260220C00110000": 5,
                }
                return {"contract_symbol": contract_symbol, "quote_date_count": counts[contract_symbol]}

        def _delta(quote, **kwargs):
            return {
                "AAA260220C00100000": 0.50,
                "AAA260220C00105000": 0.20,
                "AAA260220C00110000": 0.25,
            }[quote.contract_symbol]

        with patch.object(wfo, "_option_delta_for_quote", side_effect=_delta):
            selected = wfo._select_chain_native_spread(
                store=_Store(),
                ticker="AAA",
                entry_date=entry_date,
                trade_type="call",
                S0=100.0,
                hv30=0.25,
                long_delta_target=0.50,
                short_delta_target=0.20,
                target_dte=35,
                min_dte=28,
                max_dte=45,
                max_width_pct=20.0,
                max_debit_pct_of_width=90.0,
                iv_adj=1.0,
                requested_pricing_lane="pessimistic",
                entry_slippage_pct=0.0,
                snapshot_kind=hos.INTRADAY_SNAPSHOT_KIND,
                entry_quote_minute_et=hos.ENTRY_QUOTE_MINUTE_ET,
                entry_window_minutes=15,
                source_labels=["thetadata_opra_nbbo_1m"],
                min_prior_quote_days=1,
                prior_quote_lookback_days=14,
                short_prior_quote_score_weight=2.0,
                prior_quote_score_cap=5,
            )

        self.assertIsNotNone(selected)
        self.assertEqual(selected[1].contract_symbol, "AAA260220C00110000")

    def test_chain_native_selection_can_move_short_leg_one_strike_inside(self):
        entry_date = date(2026, 1, 15)
        quotes = [
            SimpleNamespace(
                contract_symbol="AAA260220C00100000",
                expiry="2026-02-20",
                strike=100.0,
                bid=4.9,
                ask=5.1,
                last=5.0,
                volume=10,
                open_interest=100,
            ),
            SimpleNamespace(
                contract_symbol="AAA260220C00105000",
                expiry="2026-02-20",
                strike=105.0,
                bid=2.4,
                ask=2.6,
                last=2.5,
                volume=10,
                open_interest=100,
            ),
            SimpleNamespace(
                contract_symbol="AAA260220C00110000",
                expiry="2026-02-20",
                strike=110.0,
                bid=0.9,
                ask=1.1,
                last=1.0,
                volume=10,
                open_interest=100,
            ),
        ]

        class _Store:
            def list_entry_contracts(self, **kwargs):
                return quotes

            def contract_quote_continuity_metrics(self, *, contract_symbol, **kwargs):
                return {"contract_symbol": contract_symbol, "quote_date_count": 3}

        def _delta(quote, **kwargs):
            return {
                "AAA260220C00100000": 0.50,
                "AAA260220C00105000": 0.35,
                "AAA260220C00110000": 0.20,
            }[quote.contract_symbol]

        with patch.object(wfo, "_option_delta_for_quote", side_effect=_delta):
            selected = wfo._select_chain_native_spread(
                store=_Store(),
                ticker="AAA",
                entry_date=entry_date,
                trade_type="call",
                S0=100.0,
                hv30=0.25,
                long_delta_target=0.50,
                short_delta_target=0.20,
                target_dte=35,
                min_dte=28,
                max_dte=45,
                max_width_pct=20.0,
                max_debit_pct_of_width=60.0,
                iv_adj=1.0,
                requested_pricing_lane="pessimistic",
                entry_slippage_pct=0.0,
                snapshot_kind=hos.INTRADAY_SNAPSHOT_KIND,
                entry_quote_minute_et=hos.ENTRY_QUOTE_MINUTE_ET,
                entry_window_minutes=15,
                source_labels=["thetadata_opra_nbbo_1m"],
                min_prior_quote_days=1,
                prior_quote_lookback_days=14,
                short_inside_steps=1,
            )

        self.assertIsNotNone(selected)
        self.assertEqual(selected[1].contract_symbol, "AAA260220C00105000")

    def test_time_only_spread_exit_checks_expiry_date_quote_before_settlement(self):
        entry_quote = SimpleNamespace(
            contract_symbol="AAA260108C00100000",
            expiry="2026-01-08",
            strike=100.0,
            bid=4.8,
            ask=5.0,
            last=4.9,
            price_basis="bid_ask",
        )
        short_quote = SimpleNamespace(
            contract_symbol="AAA260108C00110000",
            expiry="2026-01-08",
            strike=110.0,
            bid=1.0,
            ask=1.2,
            last=1.1,
            price_basis="bid_ask",
        )
        expiry_quotes = {
            entry_quote.contract_symbol: SimpleNamespace(
                contract_symbol=entry_quote.contract_symbol,
                bid=8.0,
                ask=8.2,
                last=8.1,
            ),
            short_quote.contract_symbol: SimpleNamespace(
                contract_symbol=short_quote.contract_symbol,
                bid=0.8,
                ask=1.0,
                last=0.9,
            ),
        }

        class _Store:
            def get_closing_quote(self, *, contract_symbol, quote_date_et, **kwargs):
                if quote_date_et == date(2026, 1, 8):
                    return expiry_quotes[contract_symbol]
                return None

        dates = [
            date(2026, 1, 1),
            date(2026, 1, 2),
            date(2026, 1, 5),
            date(2026, 1, 6),
            date(2026, 1, 7),
            date(2026, 1, 8),
            date(2026, 1, 9),
        ]
        prices = [100.0, 101.0, 102.0, 103.0, 104.0, 109.0, 109.0]

        with patch.object(
            wfo,
            "_select_chain_native_spread",
            return_value=(entry_quote, short_quote, 3.8, 10.0, 0.5, 0.2),
        ):
            result = wfo._simulate_spread_outcome_imported(
                prices=prices,
                dates=dates,
                i=0,
                store=_Store(),
                ticker="AAA",
                trade_type="call",
                hv30=0.25,
                long_delta_target=0.50,
                short_delta_target=0.20,
                dte_at_entry=7,
                stop_loss_pct=90.0,
                profit_target_pct=300.0,
                time_exit_pct=90.0,
                trailing_profit_pct=999.0,
                trailing_giveback_pct=0.0,
                max_width_pct=20.0,
                exit_monitoring_mode="time_only",
                entry_S0=100.0,
                chain_native_spread_selection=True,
            )

        self.assertTrue(result["priced"])
        self.assertEqual(result["exit_reason"], "time_exit")

    def test_calendar_basis_time_only_spread_exit_uses_elapsed_calendar_date(self):
        entry_quote = SimpleNamespace(
            contract_symbol="AAA260108C00100000",
            expiry="2026-01-08",
            strike=100.0,
            bid=4.8,
            ask=5.0,
            last=4.9,
            price_basis="bid_ask",
        )
        short_quote = SimpleNamespace(
            contract_symbol="AAA260108C00110000",
            expiry="2026-01-08",
            strike=110.0,
            bid=1.0,
            ask=1.2,
            last=1.1,
            price_basis="bid_ask",
        )
        exit_quotes = {
            date(2026, 1, 5): {
                entry_quote.contract_symbol: SimpleNamespace(
                    contract_symbol=entry_quote.contract_symbol,
                    bid=5.0,
                    ask=5.2,
                    last=5.1,
                ),
                short_quote.contract_symbol: SimpleNamespace(
                    contract_symbol=short_quote.contract_symbol,
                    bid=0.8,
                    ask=1.0,
                    last=0.9,
                ),
            },
            date(2026, 1, 7): {
                entry_quote.contract_symbol: SimpleNamespace(
                    contract_symbol=entry_quote.contract_symbol,
                    bid=8.0,
                    ask=8.2,
                    last=8.1,
                ),
                short_quote.contract_symbol: SimpleNamespace(
                    contract_symbol=short_quote.contract_symbol,
                    bid=0.8,
                    ask=1.0,
                    last=0.9,
                ),
            },
        }

        class _Store:
            def get_closing_quote(self, *, contract_symbol, quote_date_et, **kwargs):
                day_quotes = exit_quotes.get(quote_date_et)
                if day_quotes is None:
                    return None
                return day_quotes[contract_symbol]

        dates = [
            date(2026, 1, 1),
            date(2026, 1, 2),
            date(2026, 1, 5),
            date(2026, 1, 6),
            date(2026, 1, 7),
            date(2026, 1, 8),
        ]
        prices = [100.0, 101.0, 102.0, 103.0, 104.0, 109.0]

        with patch.object(
            wfo,
            "_select_chain_native_spread",
            return_value=(entry_quote, short_quote, 3.8, 10.0, 0.5, 0.2),
        ):
            result = wfo._simulate_spread_outcome_imported(
                prices=prices,
                dates=dates,
                i=0,
                store=_Store(),
                ticker="AAA",
                trade_type="call",
                hv30=0.25,
                long_delta_target=0.50,
                short_delta_target=0.20,
                dte_at_entry=7,
                stop_loss_pct=90.0,
                profit_target_pct=300.0,
                time_exit_pct=55.0,
                trailing_profit_pct=999.0,
                trailing_giveback_pct=0.0,
                max_width_pct=20.0,
                exit_monitoring_mode="time_only",
                time_exit_basis="calendar_elapsed",
                entry_S0=100.0,
                chain_native_spread_selection=True,
            )

        self.assertTrue(result["priced"])
        self.assertEqual(result["exit_reason"], "time_exit")
        self.assertEqual(result["exit_day_idx"], 2)
        self.assertEqual(result["time_exit_basis"], "calendar_elapsed")
        self.assertEqual(result["time_exit_target_date"], "2026-01-05")


if __name__ == "__main__":
    unittest.main()
