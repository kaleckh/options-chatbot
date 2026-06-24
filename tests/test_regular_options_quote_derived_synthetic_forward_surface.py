from __future__ import annotations

import json
import sqlite3
import unittest
from datetime import date
from pathlib import Path

from scripts import build_regular_options_quote_derived_synthetic_forward_surface as surface
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _opening(path: Path) -> Path:
    _write_json(
        path,
        {
            "report_id": "regular_options_quote_surface_opening_range_reversal_replay",
            "status": "blocked_quote_surface_opening_range_reversal_replay",
            "blockers": ["blocked_missing_quote_surface_underlying_price", "blocked_latest_four_rows_below_30"],
            "metrics": {
                "daily_denominator_rows": 1976,
                "candidate_rows": 0,
                "denominator_status_counts": {"blocked_missing_underlying_price": 1976},
                "full_window": {"exact_completed_rows": 0},
                "latest_four_months": {"strict_executable_completed_rows_after_opportunity_dedupe": 0},
            },
        },
    )
    return path


def _holdout(path: Path) -> Path:
    _write_json(path, {"protected_range": {"start_date": "2026-06-05"}})
    return path


def _create_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.execute(
        """
        CREATE TABLE option_quote_snapshots (
            id INTEGER PRIMARY KEY,
            as_of_utc TEXT NOT NULL,
            quote_date_et TEXT NOT NULL,
            quote_minute_et INTEGER NOT NULL,
            snapshot_kind TEXT NOT NULL DEFAULT 'intraday',
            underlying TEXT NOT NULL,
            contract_symbol TEXT NOT NULL,
            expiry TEXT NOT NULL,
            option_type TEXT NOT NULL,
            strike REAL NOT NULL,
            bid REAL,
            ask REAL,
            last REAL,
            iv REAL,
            underlying_price REAL,
            volume INTEGER,
            open_interest INTEGER,
            source_batch_id INTEGER NOT NULL
        )
        """
    )
    con.commit()
    con.close()


def _insert_leg(
    path: Path,
    *,
    symbol: str = "SPY",
    quote_date: str,
    minute: int,
    expiry: str,
    strike: float,
    option_type: str,
    bid: float,
    ask: float,
    as_of_utc: str | None = None,
) -> None:
    con = sqlite3.connect(path)
    contract = f"{symbol}{quote_date.replace('-', '')}{option_type[0].upper()}{int(strike * 1000):08d}"
    con.execute(
        """
        INSERT INTO option_quote_snapshots (
            as_of_utc, quote_date_et, quote_minute_et, snapshot_kind, underlying, contract_symbol, expiry,
            option_type, strike, bid, ask, last, iv, underlying_price, volume, open_interest, source_batch_id
        ) VALUES (?, ?, ?, 'intraday', ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, 1)
        """,
        (as_of_utc or f"{quote_date}T15:00:00Z", quote_date, minute, symbol, contract, expiry, option_type, strike, bid, ask),
    )
    con.commit()
    con.close()


def _add_pairs(
    path: Path,
    *,
    quote_date: str,
    symbol: str = "SPY",
    bucket: str = "09:35",
    pair_count: int = 5,
    crossed: bool = False,
    zero_bid: bool = False,
    unstable: bool = False,
    future: bool = False,
) -> None:
    minute = surface._bucket_to_minute(bucket)
    expiry = date.fromisoformat(quote_date).replace(day=28).isoformat()
    as_of = "2026-06-05T00:00:00Z" if future else None
    for index in range(pair_count):
        strike = 100.0 + index
        drift = index * 5.0 if unstable else 0.0
        call_bid = 8.0 - index + drift
        call_ask = 8.2 - index + drift
        put_bid = 4.0
        put_ask = 4.2
        if zero_bid and index == 0:
            call_bid = 0.0
        if crossed and index == 0:
            call_bid, call_ask = 5.5, 5.0
        _insert_leg(
            path,
            symbol=symbol,
            quote_date=quote_date,
            minute=minute,
            expiry=expiry,
            strike=strike,
            option_type="call",
            bid=call_bid,
            ask=call_ask,
            as_of_utc=as_of,
        )
        _insert_leg(
            path,
            symbol=symbol,
            quote_date=quote_date,
            minute=minute,
            expiry=expiry,
            strike=strike,
            option_type="put",
            bid=put_bid,
            ask=put_ask,
            as_of_utc=as_of,
        )


def _add_ready_day(path: Path, quote_date: str, *, symbol: str = "SPY") -> None:
    for bucket in surface.DEFAULT_BUCKETS:
        _add_pairs(path, quote_date=quote_date, symbol=symbol, bucket=bucket, pair_count=5)


class QuoteDerivedSyntheticForwardSurfaceTests(unittest.TestCase):
    def _report(self, tmp: Path, db: Path, **kwargs: object) -> dict:
        return surface.build_report(
            quotes_db_path=db,
            opening_replay_path=_opening(tmp / "opening.json"),
            holdout_contract_path=_holdout(tmp / "holdout.json"),
            generated_at_utc="2026-06-23T00:00:00Z",
            **kwargs,
        )

    def test_missing_same_minute_call_put_pairs_blocks(self) -> None:
        with WorkspaceTempDir(prefix="synthetic-forward") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            _insert_leg(
                db,
                quote_date="2026-02-02",
                minute=surface._bucket_to_minute("09:35"),
                expiry="2026-02-28",
                strike=100.0,
                option_type="call",
                bid=1.0,
                ask=1.1,
            )
            report = self._report(tmp, db, start_date="2026-02-01", end_date="2026-02-28")

        self.assertEqual(report["status"], "blocked_quote_derived_synthetic_forward_surface")
        self.assertIn("blocked_missing_call_put_pair_surface", report["blockers"])
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["broker_order_allowed"])

    def test_zero_bid_and_crossed_quotes_fail_closed(self) -> None:
        with WorkspaceTempDir(prefix="synthetic-forward") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            _add_pairs(db, quote_date="2026-02-02", bucket="09:35", zero_bid=True)
            _add_pairs(db, quote_date="2026-02-02", bucket="10:35", crossed=True)
            report = self._report(tmp, db, start_date="2026-02-01", end_date="2026-02-28")

        preview = report["daily_symbol_surface_preview"][0]
        self.assertEqual(preview["bucket_reject_counts"]["09:35"]["blocked_zero_bid_or_untradable"], 1)
        self.assertEqual(preview["bucket_reject_counts"]["10:35"]["blocked_crossed_or_stale_quote"], 1)
        self.assertIn("blocked_execution_quote_quality", report["blockers"])

    def test_future_asof_pairs_do_not_clear_surface(self) -> None:
        with WorkspaceTempDir(prefix="synthetic-forward") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            _add_pairs(db, quote_date="2026-02-02", bucket="09:35", future=True)
            report = self._report(tmp, db, start_date="2026-02-01", end_date="2026-02-28", as_of_date="2026-06-04")

        preview = report["daily_symbol_surface_preview"][0]
        self.assertEqual(preview["bucket_statuses"]["09:35"], "blocked_missing_call_put_pairs")
        self.assertFalse(report["synthetic_forward_surface_ready"])

    def test_unstable_parity_surface_blocks(self) -> None:
        with WorkspaceTempDir(prefix="synthetic-forward") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            _add_pairs(db, quote_date="2026-02-02", bucket="09:35", unstable=True)
            report = self._report(tmp, db, start_date="2026-02-01", end_date="2026-02-28")

        preview = report["daily_symbol_surface_preview"][0]
        self.assertEqual(preview["bucket_statuses"]["09:35"], "blocked_inconsistent_parity_surface")
        self.assertIn("blocked_inconsistent_parity_surface", report["blockers"])

    def test_clean_fixture_can_reach_surface_ready(self) -> None:
        with WorkspaceTempDir(prefix="synthetic-forward") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            months = [f"2024-{month:02d}-03" for month in range(6, 13)]
            months += [f"2025-{month:02d}-03" for month in range(1, 13)]
            months += [f"2026-{month:02d}-03" for month in range(1, 6)]
            for quote_date in months:
                _add_ready_day(db, quote_date)
            report = self._report(tmp, db, start_date="2024-06-01", end_date="2026-05-31")

        self.assertEqual(report["status"], "quote_derived_synthetic_forward_surface_ready")
        self.assertTrue(report["synthetic_forward_surface_ready"])
        self.assertEqual(report["metrics"]["requested_symbol_date_bucket_coverage_pct"], 100.0)
        self.assertEqual(report["metrics"]["train_months_covered"], 20)
        self.assertEqual(report["metrics"]["latest_four_months_covered"], 4)
        self.assertIsNotNone(report["next_replay_command"])
        first = report["daily_symbol_surface_preview"][0]
        estimate = first["bucket_estimates"]["09:35"]
        self.assertTrue(estimate["research_signal_only"])
        self.assertFalse(estimate["executable_fill_or_pnl_evidence"])

    def test_write_outputs_creates_latest_and_surface_jsonl(self) -> None:
        with WorkspaceTempDir(prefix="synthetic-forward") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            _add_ready_day(db, "2026-02-03")
            report = self._report(tmp, db, start_date="2026-02-01", end_date="2026-02-28")
            artifacts = surface.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "doc.md")

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "out" / "daily_symbol_surface.jsonl").exists())
            self.assertTrue((tmp / "doc.md").exists())
            self.assertIn("daily_symbol_surface_jsonl", artifacts)


if __name__ == "__main__":
    unittest.main()
