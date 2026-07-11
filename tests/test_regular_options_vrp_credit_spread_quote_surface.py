from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from scripts import build_regular_options_vrp_credit_spread_quote_surface as surface
from workspace_tempdir import WorkspaceTempDir


def _make_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            create table import_batches (
                id integer primary key,
                source_label text not null,
                dataset_kind text not null default 'intraday_csv',
                data_trust text not null default 'trusted',
                input_path text not null,
                file_hash text not null,
                imported_at_utc text not null,
                total_rows integer not null,
                imported_rows integer not null,
                duplicate_rows integer not null,
                rejected_rows integer not null,
                warnings_json text not null default '[]'
            )
            """
        )
        conn.execute(
            """
            create table option_quote_snapshots (
                id integer primary key,
                as_of_utc text not null,
                quote_date_et text not null,
                quote_minute_et integer not null,
                snapshot_kind text not null default 'intraday',
                underlying text not null,
                contract_symbol text not null,
                expiry text not null,
                option_type text not null,
                strike real not null,
                bid real,
                ask real,
                last real,
                iv real,
                underlying_price real,
                volume integer,
                open_interest integer,
                source_batch_id integer not null
            )
            """
        )
        conn.execute(
            """
            insert into import_batches
            (id, source_label, dataset_kind, data_trust, input_path, file_hash, imported_at_utc, total_rows, imported_rows, duplicate_rows, rejected_rows, warnings_json)
            values (1, 'thetadata_opra_nbbo_1m', 'intraday_csv', 'trusted', 'fixture.csv', 'hash', '2026-06-01T00:00:00Z', 1, 1, 0, 0, '[]')
            """
        )


def _insert_surface(
    conn: sqlite3.Connection, symbol: str, quote_date: str, expiry: str
) -> None:
    rows = [
        (f"{symbol}{expiry.replace('-', '')}P500", 500.0, 1.25, 1.35),
        (f"{symbol}{expiry.replace('-', '')}P495", 495.0, 0.45, 0.55),
    ]
    for contract, strike, bid, ask in rows:
        conn.execute(
            """
            insert into option_quote_snapshots
            (as_of_utc, quote_date_et, quote_minute_et, underlying, contract_symbol, expiry, option_type, strike, bid, ask, source_batch_id)
            values (?, ?, 640, ?, ?, ?, 'put', ?, ?, ?, 1)
            """,
            (
                f"{quote_date}T14:40:00Z",
                quote_date,
                symbol,
                contract,
                expiry,
                strike,
                bid,
                ask,
            ),
        )


class RegularOptionsVrpCreditSpreadQuoteSurfaceTests(unittest.TestCase):
    def test_ready_when_all_symbols_have_required_month_and_latest_coverage(
        self,
    ) -> None:
        with WorkspaceTempDir(prefix="vrp-quote-surface") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _make_db(db)
            with sqlite3.connect(db) as conn:
                for symbol in surface.DEFAULT_UNIVERSE:
                    _insert_surface(conn, symbol, "2026-02-03", "2026-03-06")
                    _insert_surface(conn, symbol, "2026-03-03", "2026-04-03")

            report = surface.build_report(
                quotes_db_path=db,
                start_date="2026-02-01",
                end_date="2026-03-31",
                latest_four_months=("2026-03",),
                required_months=2,
                required_latest_four_months=1,
                quote_minute_et=640,
                generated_at_utc="2026-06-24T00:00:00Z",
            )

        self.assertEqual(report["status"], "credit_spread_quote_surface_ready")
        self.assertTrue(report["credit_spread_quote_surface_ready"])
        self.assertEqual(report["symbols_ready"], list(surface.DEFAULT_UNIVERSE))
        self.assertEqual(report["blockers"], [])
        for key, expected in surface.READ_ONLY_FLAGS.items():
            self.assertIs(report[key], expected)

    def test_blocks_when_one_symbol_lacks_required_months(self) -> None:
        with WorkspaceTempDir(prefix="vrp-quote-surface") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _make_db(db)
            with sqlite3.connect(db) as conn:
                for symbol in ("SPY", "QQQ", "DIA"):
                    _insert_surface(conn, symbol, "2026-02-03", "2026-03-06")
                    _insert_surface(conn, symbol, "2026-03-03", "2026-04-03")
                _insert_surface(conn, "IWM", "2026-03-03", "2026-04-03")

            report = surface.build_report(
                quotes_db_path=db,
                start_date="2026-02-01",
                end_date="2026-03-31",
                latest_four_months=("2026-03",),
                required_months=2,
                required_latest_four_months=1,
                quote_minute_et=640,
            )

        self.assertEqual(report["status"], "blocked_vrp_credit_spread_quote_surface")
        self.assertFalse(report["credit_spread_quote_surface_ready"])
        self.assertEqual(
            report["blockers"], ["missing_index_credit_spread_quote_surface"]
        )
        iwm = next(row for row in report["symbol_rows"] if row["symbol"] == "IWM")
        self.assertIn("insufficient_month_coverage", iwm["blockers"])

    def test_missing_db_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="vrp-quote-surface") as tmp_dir:
            report = surface.build_report(quotes_db_path=Path(tmp_dir) / "missing.db")

        self.assertEqual(report["status"], "blocked_vrp_credit_spread_quote_surface")
        self.assertFalse(report["source_artifacts"]["options_history_db"]["exists"])
        self.assertEqual(report["symbols_ready"], [])

    def test_wrong_quote_minute_does_not_clear_engine_surface(self) -> None:
        with WorkspaceTempDir(prefix="vrp-quote-surface") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _make_db(db)
            with sqlite3.connect(db) as conn:
                for symbol in surface.DEFAULT_UNIVERSE:
                    _insert_surface(conn, symbol, "2026-03-03", "2026-04-03")

            report = surface.build_report(
                quotes_db_path=db,
                start_date="2026-03-01",
                end_date="2026-03-31",
                latest_four_months=("2026-03",),
                required_months=1,
                required_latest_four_months=1,
            )

        self.assertEqual(report["status"], "blocked_vrp_credit_spread_quote_surface")
        self.assertEqual(
            report["geometry_filter"]["required_quote_minute_et"],
            surface.DEFAULT_QUOTE_MINUTE_ET,
        )


if __name__ == "__main__":
    unittest.main()
