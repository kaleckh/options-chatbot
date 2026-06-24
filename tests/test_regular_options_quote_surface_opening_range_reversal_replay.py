from __future__ import annotations

import ast
import json
import sqlite3
import unittest
from datetime import date, timedelta
from pathlib import Path

from scripts import build_regular_options_quote_surface_opening_range_reversal_replay as replay
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _base(path: Path, hashes: list[str] | None = None) -> Path:
    _write_json(path, {"report_id": "regular_options_base_clean_stack_identity_ledger", "identity_hashes": hashes or []})
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


def _insert_quote(
    path: Path,
    *,
    symbol: str = "SPY",
    quote_date: str,
    minute: int,
    contract: str,
    expiry: str = "2026-03-20",
    option_type: str = "call",
    strike: float = 100.0,
    bid: float = 1.0,
    ask: float = 1.1,
    underlying_price: float | None = None,
) -> None:
    con = sqlite3.connect(path)
    con.execute(
        """
        INSERT INTO option_quote_snapshots (
            as_of_utc, quote_date_et, quote_minute_et, snapshot_kind, underlying, contract_symbol, expiry,
            option_type, strike, bid, ask, last, iv, underlying_price, volume, open_interest, source_batch_id
        ) VALUES (?, ?, ?, 'intraday', ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, NULL, NULL, 1)
        """,
        (f"{quote_date}T15:00:00Z", quote_date, minute, symbol, contract, expiry, option_type, strike, bid, ask, underlying_price),
    )
    con.commit()
    con.close()


def _add_underlying_day(path: Path, quote_date: str, *, symbol: str = "SPY", start_price: float, end_price: float) -> None:
    _insert_quote(
        path,
        symbol=symbol,
        quote_date=quote_date,
        minute=replay.OPENING_START_MINUTE,
        contract=f"{symbol}{quote_date.replace('-', '')}CSTART",
        bid=1.0,
        ask=1.1,
        underlying_price=start_price,
    )
    _insert_quote(
        path,
        symbol=symbol,
        quote_date=quote_date,
        minute=replay.OPENING_END_MINUTE,
        contract=f"{symbol}{quote_date.replace('-', '')}CEND",
        bid=1.0,
        ask=1.1,
        underlying_price=end_price,
    )


def _add_vertical(path: Path, quote_date: str, *, symbol: str = "SPY", direction: str = "call", win: bool = True) -> None:
    option_type = "call" if direction == "call" else "put"
    expiry = (date.fromisoformat(quote_date) + timedelta(days=14)).isoformat()
    long_strike = 100.0
    short_strike = 101.0 if direction == "call" else 99.0
    long_contract = f"{symbol}{quote_date.replace('-', '')}{option_type[0].upper()}L"
    short_contract = f"{symbol}{quote_date.replace('-', '')}{option_type[0].upper()}S"
    _insert_quote(
        path,
        symbol=symbol,
        quote_date=quote_date,
        minute=replay.ENTRY_START_MINUTE,
        contract=long_contract,
        expiry=expiry,
        option_type=option_type,
        strike=long_strike,
        bid=1.9,
        ask=2.0,
    )
    _insert_quote(
        path,
        symbol=symbol,
        quote_date=quote_date,
        minute=replay.ENTRY_START_MINUTE,
        contract=short_contract,
        expiry=expiry,
        option_type=option_type,
        strike=short_strike,
        bid=1.0,
        ask=1.1,
    )
    if win:
        exit_long_bid, exit_short_ask = 2.7, 1.2
    else:
        exit_long_bid, exit_short_ask = 1.35, 1.1
    _insert_quote(
        path,
        symbol=symbol,
        quote_date=quote_date,
        minute=replay.EXIT_END_MINUTE,
        contract=long_contract,
        expiry=expiry,
        option_type=option_type,
        strike=long_strike,
        bid=exit_long_bid,
        ask=exit_long_bid + 0.1,
    )
    _insert_quote(
        path,
        symbol=symbol,
        quote_date=quote_date,
        minute=replay.EXIT_END_MINUTE,
        contract=short_contract,
        expiry=expiry,
        option_type=option_type,
        strike=short_strike,
        bid=max(0.01, exit_short_ask - 0.1),
        ask=exit_short_ask,
    )


class QuoteSurfaceOpeningRangeReversalReplayTests(unittest.TestCase):
    def test_realistic_missing_underlying_price_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="opening-range") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            _insert_quote(
                db,
                quote_date="2026-02-02",
                minute=replay.OPENING_START_MINUTE,
                contract="SPY260220C00100000",
                underlying_price=None,
            )
            report = replay.build_report(
                quotes_db_path=db,
                base_ledger_path=_base(tmp / "base.json"),
                holdout_contract_path=_holdout(tmp / "holdout.json"),
                start_date="2026-02-01",
                end_date="2026-02-28",
                as_of_date="2026-06-04",
            )

        self.assertEqual(report["status"], "blocked_quote_surface_opening_range_reversal_replay")
        self.assertIn("blocked_missing_quote_surface_underlying_price", report["blockers"])
        self.assertEqual(report["metrics"]["denominator_status_counts"]["blocked_missing_underlying_price"], 1)
        self.assertTrue(report["read_only_db_open"])
        self.assertFalse(report["broker_order_allowed"])
        self.assertFalse(report["accepted_profitability"])

    def test_prior_day_distribution_prevents_lookahead_thresholds(self) -> None:
        with WorkspaceTempDir(prefix="opening-range") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            for day in range(1, 21):
                _add_underlying_day(db, f"2026-02-{day:02d}", start_price=100.0, end_price=100.1)
            _add_underlying_day(db, "2026-02-21", start_price=100.0, end_price=95.0)
            _add_vertical(db, "2026-02-21", direction="call")
            report = replay.build_report(
                quotes_db_path=db,
                base_ledger_path=_base(tmp / "base.json"),
                holdout_contract_path=_holdout(tmp / "holdout.json"),
                start_date="2026-02-01",
                end_date="2026-02-28",
                as_of_date="2026-06-04",
            )

        statuses = report["metrics"]["denominator_status_counts"]
        self.assertEqual(statuses["blocked_insufficient_prior_20_day_distribution"], 20)
        self.assertEqual(statuses["candidate_generated"], 1)
        candidate = report["_candidate_rows"][0]
        self.assertEqual(candidate["direction"], "call")
        self.assertLess(candidate["opening_range_return"], candidate["prior_20_p10"])

    def test_zero_bid_exit_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="opening-range") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            for day in range(1, 21):
                _add_underlying_day(db, f"2026-02-{day:02d}", start_price=100.0, end_price=100.1)
            _add_underlying_day(db, "2026-02-21", start_price=100.0, end_price=95.0)
            _add_vertical(db, "2026-02-21", direction="call")
            con = sqlite3.connect(db)
            con.execute("UPDATE option_quote_snapshots SET bid = 0 WHERE quote_date_et = '2026-02-21' AND quote_minute_et = ?", (replay.EXIT_END_MINUTE,))
            con.commit()
            con.close()
            report = replay.build_report(
                quotes_db_path=db,
                base_ledger_path=_base(tmp / "base.json"),
                holdout_contract_path=_holdout(tmp / "holdout.json"),
                start_date="2026-02-01",
                end_date="2026-02-28",
                as_of_date="2026-06-04",
            )

        self.assertEqual(report["metrics"]["denominator_status_counts"]["blocked_zero_bid_or_untradable"], 1)
        self.assertEqual(report["metrics"]["full_window"]["exact_completed_rows"], 0)

    def test_base_stack_dedupe_blocks_overlap(self) -> None:
        with WorkspaceTempDir(prefix="opening-range") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            for day in range(1, 21):
                _add_underlying_day(db, f"2026-02-{day:02d}", start_price=100.0, end_price=100.1)
            _add_underlying_day(db, "2026-02-21", start_price=100.0, end_price=95.0)
            _add_vertical(db, "2026-02-21", direction="call")
            first = replay.build_report(
                quotes_db_path=db,
                base_ledger_path=_base(tmp / "base_empty.json"),
                holdout_contract_path=_holdout(tmp / "holdout.json"),
                start_date="2026-02-01",
                end_date="2026-02-28",
                as_of_date="2026-06-04",
            )
            identity = first["_candidate_rows"][0]["opportunity_identity_hash"]
            second = replay.build_report(
                quotes_db_path=db,
                base_ledger_path=_base(tmp / "base_with_hash.json", [identity]),
                holdout_contract_path=_holdout(tmp / "holdout.json"),
                start_date="2026-02-01",
                end_date="2026-02-28",
                as_of_date="2026-06-04",
            )

        self.assertEqual(second["metrics"]["denominator_status_counts"]["duplicate_existing_base_stack"], 1)
        self.assertEqual(second["metrics"]["full_window"]["exact_completed_rows"], 0)

    def test_synthetic_clean_fixture_can_reach_candidate_review(self) -> None:
        with WorkspaceTempDir(prefix="opening-range") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            current = date(2024, 6, 3)
            generated = 0
            symbols = ("SPY", "QQQ")
            while generated < 520:
                if current.weekday() >= 5:
                    current += timedelta(days=1)
                    continue
                quote_date = current.isoformat()
                for symbol in symbols:
                    if generated < 20:
                        _add_underlying_day(db, quote_date, symbol=symbol, start_price=100.0, end_price=100.1)
                    else:
                        _add_underlying_day(db, quote_date, symbol=symbol, start_price=100.0, end_price=95.0)
                        _add_vertical(db, quote_date, symbol=symbol, direction="call", win=(generated % 5 != 0))
                generated += 1
                current += timedelta(days=1)
            report = replay.build_report(
                quotes_db_path=db,
                base_ledger_path=_base(tmp / "base.json"),
                holdout_contract_path=_holdout(tmp / "holdout.json"),
                start_date="2024-06-01",
                end_date="2026-05-31",
                as_of_date="2026-06-04",
            )

        self.assertEqual(report["status"], "quote_surface_opening_range_reversal_candidate_for_forward_freeze_review")
        self.assertGreaterEqual(report["metrics"]["full_window"]["exact_completed_rows"], 200)
        self.assertGreaterEqual(report["metrics"]["latest_four_months"]["strict_executable_completed_rows_after_opportunity_dedupe"], 30)
        self.assertGreater(report["metrics"]["full_window"]["profit_factor_lower_bound_5pct"], 1.0)

    def test_write_outputs_and_runner_avoid_trading_paths(self) -> None:
        with WorkspaceTempDir(prefix="opening-range") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            _insert_quote(db, quote_date="2026-02-02", minute=replay.OPENING_START_MINUTE, contract="SPY260220C00100000")
            report = replay.build_report(
                quotes_db_path=db,
                base_ledger_path=_base(tmp / "base.json"),
                holdout_contract_path=_holdout(tmp / "holdout.json"),
                start_date="2026-02-01",
                end_date="2026-02-28",
                as_of_date="2026-06-04",
            )
            artifacts = replay.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "doc.md")
            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "daily_denominator.jsonl").exists())
            self.assertTrue((tmp / "out" / "candidate_rows.jsonl").exists())
            self.assertTrue((tmp / "doc.md").exists())
            self.assertIn("candidate_rows_jsonl", artifacts)

        source = Path(replay.__file__).read_text(encoding="utf8")
        tree = ast.parse(source)
        called_names: set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                called_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_names.add(node.func.attr)
        forbidden = {"run_daily_ops", "log_scan_picks", "validate_pending_scan_candidates", "submit_order", "create_position", "auto_track", "import_quotes"}
        self.assertTrue(forbidden.isdisjoint(called_names))


if __name__ == "__main__":
    unittest.main()
