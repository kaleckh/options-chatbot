from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from scripts import research_regular_options_vrp_credit_spread_replay as replay


GEOMETRY = replay._load_json(replay.CONTRACT)["playbook_binding"]["geometry"]
FROZEN_SPLIT_START, FROZEN_SPLIT_END = replay._frozen_train_window()
REAL_QUOTE_CORPUS_VERIFIER = replay._verified_quote_corpus_from_manifest
VERIFIED_QUOTE_CORPUS_META = {
    "status": "validated",
    "path": "test-verified-manifest.json",
    "manifest_sha256": "a" * 64,
    "corpus_sha256": "b" * 64,
}


def _frozen_market_dates() -> list[str]:
    return replay._expected_us_equity_market_dates(FROZEN_SPLIT_START, FROZEN_SPLIT_END)


def _create_db(path: Path) -> None:
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(
            """
            CREATE TABLE import_batches (
                id INTEGER PRIMARY KEY,
                source_label TEXT NOT NULL,
                dataset_kind TEXT NOT NULL,
                data_trust TEXT NOT NULL,
                input_path TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                total_rows INTEGER NOT NULL,
                imported_rows INTEGER NOT NULL,
                duplicate_rows INTEGER NOT NULL,
                rejected_rows INTEGER NOT NULL
            );
            CREATE TABLE option_quote_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                as_of_utc TEXT NOT NULL,
                quote_date_et TEXT NOT NULL,
                quote_minute_et INTEGER NOT NULL,
                snapshot_kind TEXT NOT NULL,
                underlying TEXT NOT NULL,
                contract_symbol TEXT NOT NULL,
                expiry TEXT NOT NULL,
                option_type TEXT NOT NULL,
                strike REAL NOT NULL,
                bid REAL,
                ask REAL,
                source_batch_id INTEGER NOT NULL
            );
            INSERT INTO import_batches (
                id, source_label, dataset_kind, data_trust, input_path, file_hash,
                total_rows, imported_rows, duplicate_rows, rejected_rows
            ) VALUES
                (1, 'thetadata_opra_nbbo_1m', 'intraday_csv', 'trusted', 'batch-1.csv',
                 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 4, 4, 0, 0),
                (2, 'thetadata_opra_nbbo_1m', 'intraday_csv', 'trusted', 'batch-2.csv',
                 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', 1, 1, 0, 0),
                (3, 'untrusted_source', 'intraday_csv', 'research', 'batch-3.csv',
                 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc', 1, 1, 0, 0);
            """
        )
        conn.commit()


def _insert_quote(
    path: Path,
    *,
    day: str,
    expiry: str,
    option_type: str,
    strike: float,
    bid: float,
    ask: float,
    as_of_utc: str,
    symbol: str = "SPY",
    batch_id: int = 1,
    contract_symbol: str | None = None,
) -> None:
    contract = (
        contract_symbol
        or f"{symbol}-{expiry}-{option_type}-{strike}-{batch_id}-{as_of_utc}"
    )
    with closing(sqlite3.connect(path)) as conn:
        conn.execute(
            """
            INSERT INTO option_quote_snapshots (
                as_of_utc, quote_date_et, quote_minute_et, snapshot_kind,
                underlying, contract_symbol, expiry, option_type, strike,
                bid, ask, source_batch_id
            ) VALUES (?, ?, ?, 'intraday', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                as_of_utc,
                day,
                replay.EXIT_MINUTE,
                symbol,
                contract,
                expiry,
                option_type,
                strike,
                bid,
                ask,
                batch_id,
            ),
        )
        conn.commit()


def _entry_surface(
    path: Path,
    *,
    symbol: str = "SPY",
    day: str = "2020-01-02",
    expiry: str = "2020-01-31",
) -> None:
    stamp = replay._event_timestamp_utc(day).isoformat().replace("+00:00", "Z")
    _insert_quote(
        path,
        symbol=symbol,
        day=day,
        expiry=expiry,
        option_type="call",
        strike=100,
        bid=5.0,
        ask=5.1,
        as_of_utc=stamp,
        contract_symbol=f"{symbol}-{expiry}-C-100",
    )
    _insert_quote(
        path,
        symbol=symbol,
        day=day,
        expiry=expiry,
        option_type="put",
        strike=100,
        bid=5.0,
        ask=5.1,
        as_of_utc=stamp,
        contract_symbol=f"{symbol}-{expiry}-P-100",
    )
    _insert_quote(
        path,
        symbol=symbol,
        day=day,
        expiry=expiry,
        option_type="put",
        strike=95,
        bid=1.5,
        ask=1.6,
        as_of_utc=stamp,
        contract_symbol=f"{symbol}-{expiry}-P-95",
    )
    _insert_quote(
        path,
        symbol=symbol,
        day=day,
        expiry=expiry,
        option_type="put",
        strike=90,
        bid=0.4,
        ask=0.5,
        as_of_utc=stamp,
        contract_symbol=f"{symbol}-{expiry}-P-90",
    )


def _exit_surface(
    path: Path,
    *,
    symbol: str = "SPY",
    day: str = "2020-01-03",
    expiry: str = "2020-01-31",
) -> None:
    stamp = replay._event_timestamp_utc(day).isoformat().replace("+00:00", "Z")
    _insert_quote(
        path,
        symbol=symbol,
        day=day,
        expiry=expiry,
        option_type="put",
        strike=95,
        bid=0.5,
        ask=0.6,
        as_of_utc=stamp,
        contract_symbol=f"{symbol}-{expiry}-P-95",
    )
    _insert_quote(
        path,
        symbol=symbol,
        day=day,
        expiry=expiry,
        option_type="put",
        strike=90,
        bid=0.1,
        ask=0.2,
        as_of_utc=stamp,
        contract_symbol=f"{symbol}-{expiry}-P-90",
    )


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf8")


def _vix_row(day: str) -> dict[str, object]:
    prior = date.fromisoformat(day) - timedelta(days=1)
    return {
        "bucket_date_et": day,
        "vix_value": 18.0,
        "known_at_utc": f"{prior.isoformat()}T21:00:00Z",
        "point_in_time_valid": True,
        "source_provenance_status": "trusted_local_or_contract_declared",
    }


def _crash_row(day: str, *, crash: bool = False) -> dict[str, object]:
    prior = date.fromisoformat(day) - timedelta(days=1)
    return {
        "input_date_et": day,
        "crash_regime": crash,
        "known_at_utc": f"{prior.isoformat()}T21:00:00Z",
        "point_in_time_valid": True,
        "proof_eligible": True,
        "historical_prior_bar_reconstruction": False,
        "blockers": [],
    }


def _write_complete_regime_inputs(
    vix_path: Path,
    crash_path: Path,
    *,
    non_crash_dates: frozenset[str] = frozenset(),
) -> list[str]:
    market_dates = _frozen_market_dates()
    _write_jsonl(vix_path, [_vix_row(day) for day in market_dates])
    crash_path.write_text(
        json.dumps(
            {
                "input_rows": [
                    _crash_row(day, crash=day not in non_crash_dates)
                    for day in market_dates
                ]
            }
        ),
        encoding="utf8",
    )
    return market_dates


class VrpCreditSpreadReplayTest(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(
            replay,
            "_verified_quote_corpus_from_manifest",
            return_value=((1,), VERIFIED_QUOTE_CORPUS_META, []),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_trusted_quote_dedupe_is_deterministic_and_entry_requires_synchrony_and_valid_credit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Path(temp_dir) / "quotes.db"
            _create_db(db)
            _entry_surface(db)
            expiry = "2020-01-31"
            _insert_quote(
                db,
                day="2020-01-02",
                expiry=expiry,
                option_type="put",
                strike=95,
                bid=9.0,
                ask=9.1,
                as_of_utc="2020-01-02T20:55:30Z",
                batch_id=2,
                contract_symbol="LATER-TRUSTED-DUPLICATE",
            )
            _insert_quote(
                db,
                day="2020-01-02",
                expiry=expiry,
                option_type="put",
                strike=95,
                bid=99.0,
                ask=99.1,
                as_of_utc="2020-01-02T20:54:00Z",
                batch_id=3,
                contract_symbol="UNTRUSTED-DUPLICATE",
            )
            with closing(
                sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro", uri=True)
            ) as conn:
                conn.row_factory = sqlite3.Row
                quotes = replay._quotes(conn, "SPY", "2020-01-02", (1,))

            short = next(
                row
                for row in quotes
                if row["option_type"] == "put" and row["strike"] == 95
            )
            self.assertEqual(short["bid"], 1.5)
            self.assertEqual(
                len(
                    [
                        row
                        for row in quotes
                        if row["option_type"] == "put" and row["strike"] == 95
                    ]
                ),
                1,
            )
            entry, status = replay._select_entry(quotes, "2020-01-02", GEOMETRY)
            self.assertEqual(status, "exact_entry_captured")
            self.assertEqual(entry["entry_credit"], 1.0)
            self.assertTrue(entry["entry_quote_pair_synchronized"])

            with closing(
                sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro", uri=True)
            ) as conn:
                conn.row_factory = sqlite3.Row
                all_validated_quotes = replay._quotes(conn, "SPY", "2020-01-02", (1, 2))
            self.assertEqual(
                len(
                    [
                        row
                        for row in all_validated_quotes
                        if row["option_type"] == "put" and row["strike"] == 95
                    ]
                ),
                2,
            )
            self.assertEqual(
                replay._select_entry(all_validated_quotes, "2020-01-02", GEOMETRY)[1],
                "ambiguous_contract_series_at_strike",
            )

            unsynchronized = [dict(row) for row in quotes]
            next(
                row
                for row in unsynchronized
                if row["option_type"] == "put" and row["strike"] == 90
            )["as_of_utc"] = "2020-01-02T20:56:00Z"
            self.assertEqual(
                replay._select_entry(unsynchronized, "2020-01-02", GEOMETRY)[1],
                "missing_synchronized_entry_leg_pair",
            )

            for stamp in (
                "2020-01-02T20:56:00Z",
                "2020-01-03T20:55:00Z",
            ):
                identically_wrong = [dict(row) for row in quotes]
                for row in identically_wrong:
                    row["as_of_utc"] = stamp
                self.assertEqual(
                    replay._select_entry(identically_wrong, "2020-01-02", GEOMETRY)[1],
                    "missing_synchronized_entry_leg_pair",
                )

            invalid_credit = [dict(row) for row in quotes]
            invalid_short = next(
                row
                for row in invalid_credit
                if row["option_type"] == "put" and row["strike"] == 95
            )
            invalid_short.update({"bid": 6.0, "ask": 6.1})
            self.assertEqual(
                replay._select_entry(invalid_credit, "2020-01-02", GEOMETRY)[1],
                "rejected_width_or_credit",
            )

    def test_exit_debit_requires_a_synchronized_pair_and_sane_vertical_value(
        self,
    ) -> None:
        position = {
            "expiry": "2020-01-31",
            "short_strike": 95.0,
            "long_strike": 90.0,
            "width": 5.0,
            "entry_short_contract_symbol": "SPY-2020-01-31-P-95",
            "entry_long_contract_symbol": "SPY-2020-01-31-P-90",
        }
        for mode, expected_status in (
            ("valid", "exact_exit_quote_pair"),
            ("unsynchronized", "missing_synchronized_exit_leg_pair"),
            ("identically_late", "missing_synchronized_exit_leg_pair"),
            ("identically_next_day", "missing_synchronized_exit_leg_pair"),
            ("different_contracts", "missing_exact_entry_contract_exit_quote"),
            ("insane", "invalid_exit_debit"),
        ):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp_dir:
                db = Path(temp_dir) / "quotes.db"
                _create_db(db)
                _exit_surface(db)
                with closing(sqlite3.connect(db)) as conn:
                    if mode == "unsynchronized":
                        conn.execute(
                            "UPDATE option_quote_snapshots SET as_of_utc = ? WHERE strike = 90",
                            ("2020-01-03T20:56:00Z",),
                        )
                    elif mode == "identically_late":
                        conn.execute(
                            "UPDATE option_quote_snapshots SET as_of_utc = ?",
                            ("2020-01-03T20:56:00Z",),
                        )
                    elif mode == "identically_next_day":
                        conn.execute(
                            "UPDATE option_quote_snapshots SET as_of_utc = ?",
                            ("2020-01-04T20:55:00Z",),
                        )
                    elif mode == "different_contracts":
                        conn.execute(
                            "UPDATE option_quote_snapshots SET contract_symbol = 'ADJUSTED-' || contract_symbol"
                        )
                    elif mode == "insane":
                        conn.execute(
                            "UPDATE option_quote_snapshots SET bid = 5.9, ask = 6.0 WHERE strike = 95"
                        )
                    conn.commit()
                with closing(
                    sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro", uri=True)
                ) as conn:
                    conn.row_factory = sqlite3.Row
                    debit, status, quote_meta = replay._exit_debit(
                        conn, "SPY", "2020-01-03", position, (1,)
                    )
                self.assertEqual(status, expected_status)
                if mode == "valid":
                    self.assertEqual(debit, 0.5)
                    self.assertTrue(quote_meta["exit_quote_pair_synchronized"])
                else:
                    self.assertIsNone(debit)

    def test_complete_replay_metrics_and_tail_report_are_fee_aware(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db = root / "quotes.db"
            vix = root / "vix.jsonl"
            crash = root / "crash.json"
            _create_db(db)
            for symbol in replay.UNIVERSE:
                _entry_surface(db, symbol=symbol)
                _exit_surface(db, symbol=symbol)
            market_dates = _write_complete_regime_inputs(
                vix,
                crash,
                non_crash_dates=frozenset({"2020-01-02"}),
            )

            result = replay.run_split(
                split_name="family_train",
                split_start=FROZEN_SPLIT_START,
                split_end=FROZEN_SPLIT_END,
                vix_rows_path=vix,
                crash_guard_path=crash,
                vix_policy={"low_max": 15.0, "mid_max": 25.0},
                market_dates=market_dates,
                db_path=db,
                geometry=GEOMETRY,
                bootstrap_draws=replay.FROZEN_BOOTSTRAP_DRAWS,
            )

            self.assertTrue(result["evaluation_ready"])
            self.assertEqual(result["evaluation_blockers"], [])
            self.assertEqual(result["completed_trades"], 4)
            self.assertEqual(result["metrics"]["total_net_pnl_usd"], 189.6)
            self.assertEqual(result["metrics"]["total_round_trip_fees_usd"], 10.4)
            self.assertEqual(
                result["metrics"]["pnl_basis"], "net_after_frozen_round_trip_fees"
            )
            self.assertEqual(result["rows"][0]["gross_pnl_usd_before_fees"], 50.0)
            self.assertEqual(result["rows"][0]["net_pnl_usd"], 47.4)
            self.assertTrue(result["rows"][0]["entry_quote_pair_synchronized"])
            self.assertTrue(result["rows"][0]["exit_quote_pair_synchronized"])
            self.assertEqual(result["tail_report"]["max_drawdown_usd"], 0.0)
            self.assertEqual(result["tail_report"]["worst_month"]["month"], "2020-01")
            self.assertIsNone(
                result["tail_report"]["trade_net_pnl_usd_skewness_population"]
            )
            self.assertIsNone(
                result["tail_report"]["trade_net_pnl_usd_excess_kurtosis_population"]
            )

    def test_missing_crash_guard_and_unresolved_positions_block_metrics_and_remain_in_rows(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db = root / "quotes.db"
            vix = root / "vix.jsonl"
            crash = root / "crash.json"
            _create_db(db)
            market_dates = _frozen_market_dates()
            _write_jsonl(vix, [_vix_row(day) for day in market_dates])

            missing_guard = replay.run_split(
                split_name="family_train",
                split_start=FROZEN_SPLIT_START,
                split_end=FROZEN_SPLIT_END,
                vix_rows_path=vix,
                crash_guard_path=root / "missing-crash.json",
                vix_policy={"low_max": 15.0, "mid_max": 25.0},
                market_dates=market_dates,
                db_path=db,
                geometry=GEOMETRY,
                bootstrap_draws=replay.FROZEN_BOOTSTRAP_DRAWS,
            )
            self.assertFalse(missing_guard["evaluation_ready"])
            self.assertIn(
                "missing_required_point_in_time_crash_regime_inputs",
                missing_guard["evaluation_blockers"],
            )
            self.assertEqual(missing_guard["metrics"], {})

            market_dates = _write_complete_regime_inputs(
                vix,
                crash,
                non_crash_dates=frozenset({FROZEN_SPLIT_END}),
            )
            _entry_surface(
                db,
                day=FROZEN_SPLIT_END,
                expiry="2020-07-31",
            )
            still_open = replay.run_split(
                split_name="family_train",
                split_start=FROZEN_SPLIT_START,
                split_end=FROZEN_SPLIT_END,
                vix_rows_path=vix,
                crash_guard_path=crash,
                vix_policy={"low_max": 15.0, "mid_max": 25.0},
                market_dates=market_dates,
                db_path=db,
                geometry=GEOMETRY,
                bootstrap_draws=replay.FROZEN_BOOTSTRAP_DRAWS,
            )
            self.assertFalse(still_open["evaluation_ready"])
            self.assertIn(
                "open_at_split_end_unresolved", still_open["evaluation_blockers"]
            )
            self.assertEqual(still_open["blocked_unresolved_trade_rows"], 1)
            self.assertEqual(still_open["rows"][0]["row_status"], "blocked_unresolved")
            self.assertIsNone(still_open["rows"][0]["net_pnl_usd"])
            self.assertEqual(still_open["metrics"], {})

    def test_missing_daily_exit_and_expiration_each_block_without_dropping_the_trade(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db = root / "quotes.db"
            vix = root / "vix.jsonl"
            crash = root / "crash.json"
            _create_db(db)
            _entry_surface(db)
            market_dates = _write_complete_regime_inputs(
                vix,
                crash,
                non_crash_dates=frozenset({"2020-01-02"}),
            )
            result = replay.run_split(
                split_name="family_train",
                split_start=FROZEN_SPLIT_START,
                split_end=FROZEN_SPLIT_END,
                vix_rows_path=vix,
                crash_guard_path=crash,
                vix_policy={"low_max": 15.0, "mid_max": 25.0},
                market_dates=market_dates,
                db_path=db,
                geometry=GEOMETRY,
                bootstrap_draws=replay.FROZEN_BOOTSTRAP_DRAWS,
            )
            self.assertFalse(result["evaluation_ready"])
            self.assertIn(
                "missing_exact_entry_contract_exit_quote",
                result["evaluation_blockers"],
            )
            self.assertEqual(
                result["rows"][0]["blocking_status"],
                "missing_exact_entry_contract_exit_quote",
            )
            self.assertEqual(result["metrics"], {})
            self.assertEqual(
                replay._unresolved_exit_blocker(
                    0, "missing_exact_entry_contract_exit_quote"
                ),
                "unresolved_expiration_or_assignment",
            )

    def test_family_validation_stays_blocked_and_discloses_no_formal_path(self) -> None:
        control = replay._validation_control()
        self.assertEqual(control["formal_evaluation_path"], None)
        self.assertIn(replay.MISSING_FORMAL_VALIDATION_PATH, control["blockers"])
        with self.assertRaises(SystemExit) as raised:
            replay.main(["--split", "family_validation"])
        self.assertIn(replay.MISSING_FORMAL_VALIDATION_PATH, str(raised.exception))
        self.assertIn(
            "no formal registry-consuming evaluation path is implemented",
            str(raised.exception),
        )

    def test_public_run_split_blocks_validation_before_loading_data_or_db(self) -> None:
        blocked = replay.run_split(
            split_name="family_validation",
            split_start="2020-07-01",
            split_end="2020-07-31",
            vix_rows_path=Path("missing-vix.jsonl"),
            crash_guard_path=Path("missing-crash.json"),
            vix_policy={"low_max": 15.0, "mid_max": 25.0},
            market_dates=["2020-07-01"],
            db_path=Path("missing-options.db"),
            geometry=GEOMETRY,
            bootstrap_draws=replay.FROZEN_BOOTSTRAP_DRAWS,
        )
        self.assertEqual(blocked["status"], "blocked_split_not_authorized")
        self.assertFalse(blocked["evaluation_ready"])
        self.assertIn(
            replay.MISSING_FORMAL_VALIDATION_PATH,
            blocked["evaluation_blockers"],
        )
        self.assertEqual(blocked["rows"], [])
        self.assertEqual(blocked["metrics"], {})

    def test_empty_market_dates_and_missing_regime_sources_block_zero_row_readiness(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            vix = root / "vix.jsonl"
            crash = root / "crash.json"
            market_dates = _write_complete_regime_inputs(vix, crash)
            empty_dates = replay.run_split(
                split_name="family_train",
                split_start=FROZEN_SPLIT_START,
                split_end=FROZEN_SPLIT_END,
                vix_rows_path=vix,
                crash_guard_path=crash,
                vix_policy={"low_max": 15.0, "mid_max": 25.0},
                market_dates=[],
                db_path=root / "missing-options.db",
                geometry=GEOMETRY,
                bootstrap_draws=replay.FROZEN_BOOTSTRAP_DRAWS,
            )
            self.assertFalse(empty_dates["evaluation_ready"])
            self.assertIn(
                "missing_required_market_dates", empty_dates["evaluation_blockers"]
            )

            missing_sources = replay.run_split(
                split_name="family_train",
                split_start=FROZEN_SPLIT_START,
                split_end=FROZEN_SPLIT_END,
                vix_rows_path=root / "missing-vix.jsonl",
                crash_guard_path=root / "missing-crash.json",
                vix_policy={"low_max": 15.0, "mid_max": 25.0},
                market_dates=market_dates,
                db_path=root / "missing-options.db",
                geometry=GEOMETRY,
                bootstrap_draws=replay.FROZEN_BOOTSTRAP_DRAWS,
            )
            self.assertFalse(missing_sources["evaluation_ready"])
            self.assertIn(
                "missing_required_point_in_time_vix_inputs",
                missing_sources["evaluation_blockers"],
            )
            self.assertIn(
                "missing_required_point_in_time_crash_regime_inputs",
                missing_sources["evaluation_blockers"],
            )

    def test_quote_timestamp_binding_is_dst_aware_and_rejects_mutually_wrong_rows(
        self,
    ) -> None:
        def quote(stamp: str) -> dict[str, object]:
            return {
                "quote_date_et": "2020-07-02",
                "quote_minute_et": replay.EXIT_MINUTE,
                "as_of_utc": stamp,
            }

        self.assertTrue(
            replay._same_minute_pair(
                quote("2020-07-02T19:55:00Z"),
                quote("2020-07-02T19:55:00Z"),
                event_day="2020-07-02",
            )
        )
        self.assertFalse(
            replay._same_minute_pair(
                quote("2020-07-02T19:55:01Z"),
                quote("2020-07-02T19:55:59Z"),
                event_day="2020-07-02",
            )
        )
        for stamp in (
            "2020-07-02T20:55:00Z",
            "2020-07-03T19:55:00Z",
            "2020-07-02T19:55:00",
        ):
            self.assertFalse(
                replay._same_minute_pair(
                    quote(stamp), quote(stamp), event_day="2020-07-02"
                )
            )

    def test_real_month_end_and_frozen_scoring_knobs_are_enforced(self) -> None:
        self.assertEqual(replay._month_end("2020-06"), "2020-06-30")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            vix = root / "vix.jsonl"
            crash = root / "crash.json"
            market_dates = _write_complete_regime_inputs(vix, crash)
            for policy, draws, blocker in (
                (
                    {"low_max": 14.0, "mid_max": 25.0},
                    replay.FROZEN_BOOTSTRAP_DRAWS,
                    "vix_thresholds_do_not_match_frozen_policy",
                ),
                (
                    {"low_max": 15.000000001, "mid_max": 25.0},
                    replay.FROZEN_BOOTSTRAP_DRAWS,
                    "vix_thresholds_do_not_match_frozen_policy",
                ),
                (
                    {"low_max": 15.0, "mid_max": 25.0},
                    9999,
                    "bootstrap_draws_do_not_match_frozen_10000",
                ),
            ):
                with self.subTest(blocker=blocker):
                    blocked = replay.run_split(
                        split_name="family_train",
                        split_start=FROZEN_SPLIT_START,
                        split_end=FROZEN_SPLIT_END,
                        vix_rows_path=vix,
                        crash_guard_path=crash,
                        vix_policy=policy,
                        market_dates=market_dates,
                        db_path=root / "missing-options.db",
                        geometry=GEOMETRY,
                        bootstrap_draws=draws,
                    )
                    self.assertFalse(blocked["evaluation_ready"])
                    self.assertIn(blocker, blocked["evaluation_blockers"])
                    self.assertEqual(blocked["metrics"], {})

    def test_sparse_calendar_subwindow_and_geometry_mismatch_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            vix = root / "vix.jsonl"
            crash = root / "crash.json"
            market_dates = _write_complete_regime_inputs(vix, crash)

            sparse = replay.run_split(
                split_name="family_train",
                split_start=FROZEN_SPLIT_START,
                split_end=FROZEN_SPLIT_END,
                vix_rows_path=vix,
                crash_guard_path=crash,
                vix_policy={"low_max": 15.0, "mid_max": 25.0},
                market_dates=market_dates[:-1],
                db_path=root / "missing-options.db",
                geometry=GEOMETRY,
                bootstrap_draws=replay.FROZEN_BOOTSTRAP_DRAWS,
            )
            self.assertFalse(sparse["evaluation_ready"])
            self.assertIn(
                "market_dates_do_not_match_authoritative_us_equity_calendar",
                sparse["evaluation_blockers"],
            )
            self.assertEqual(
                sparse["market_calendar_audit"]["missing_market_day_count"], 1
            )
            self.assertEqual(
                sparse["market_calendar_audit"]["missing_market_days"],
                [market_dates[-1]],
            )

            subwindow = replay.run_split(
                split_name="family_train",
                split_start="2020-01-02",
                split_end="2020-01-03",
                vix_rows_path=Path("missing-vix.jsonl"),
                crash_guard_path=Path("missing-crash.json"),
                vix_policy={"low_max": 15.0, "mid_max": 25.0},
                market_dates=["2020-01-02", "2020-01-03"],
                db_path=Path("missing-options.db"),
                geometry=GEOMETRY,
                bootstrap_draws=replay.FROZEN_BOOTSTRAP_DRAWS,
            )
            self.assertEqual(subwindow["status"], "blocked_split_not_authorized")
            self.assertIn(
                "split_window_does_not_match_exact_frozen_family_train",
                subwindow["evaluation_blockers"],
            )

            changed_geometry = {**GEOMETRY, "time_exit_dte": 8}
            geometry_block = replay.run_split(
                split_name="family_train",
                split_start=FROZEN_SPLIT_START,
                split_end=FROZEN_SPLIT_END,
                vix_rows_path=vix,
                crash_guard_path=crash,
                vix_policy={"low_max": 15.0, "mid_max": 25.0},
                market_dates=market_dates,
                db_path=root / "missing-options.db",
                geometry=changed_geometry,
                bootstrap_draws=replay.FROZEN_BOOTSTRAP_DRAWS,
            )
            self.assertFalse(geometry_block["evaluation_ready"])
            self.assertIn(
                "geometry_does_not_match_frozen_playbook_binding",
                geometry_block["evaluation_blockers"],
            )

    def test_regime_date_identity_rejects_unexpected_and_invalid_extras(self) -> None:
        for source_name, blocker, meta_key, date_field in (
            (
                "vix",
                "point_in_time_vix_date_identity_mismatch",
                "vix_rows",
                "bucket_date_et",
            ),
            (
                "crash",
                "point_in_time_crash_regime_date_identity_mismatch",
                "crash_guard",
                "input_date_et",
            ),
        ):
            for extra_date, audit_key in (
                ("2020-07-01", "unexpected_dates"),
                ("not-a-date", "invalid_dates"),
            ):
                with (
                    self.subTest(source=source_name, extra_date=extra_date),
                    tempfile.TemporaryDirectory() as temp_dir,
                ):
                    root = Path(temp_dir)
                    vix = root / "vix.jsonl"
                    crash = root / "crash.json"
                    market_dates = _write_complete_regime_inputs(vix, crash)
                    if source_name == "vix":
                        rows = [_vix_row(day) for day in market_dates]
                        extra = _vix_row("2020-07-01")
                        extra[date_field] = extra_date
                        _write_jsonl(vix, [*rows, extra])
                    else:
                        rows = [_crash_row(day, crash=True) for day in market_dates]
                        extra = _crash_row("2020-07-01", crash=True)
                        extra[date_field] = extra_date
                        crash.write_text(
                            json.dumps({"input_rows": [*rows, extra]}),
                            encoding="utf8",
                        )

                    blocked = replay.run_split(
                        split_name="family_train",
                        split_start=FROZEN_SPLIT_START,
                        split_end=FROZEN_SPLIT_END,
                        vix_rows_path=vix,
                        crash_guard_path=crash,
                        vix_policy={"low_max": 15.0, "mid_max": 25.0},
                        market_dates=market_dates,
                        db_path=root / "missing-options.db",
                        geometry=GEOMETRY,
                        bootstrap_draws=replay.FROZEN_BOOTSTRAP_DRAWS,
                    )
                    self.assertFalse(blocked["evaluation_ready"])
                    self.assertIn(blocker, blocked["evaluation_blockers"])
                    source_meta = blocked["input_sources"][meta_key]
                    self.assertFalse(source_meta["exact_date_identity"])
                    self.assertEqual(source_meta[audit_key], [extra_date])
                    self.assertEqual(source_meta[f"{audit_key[:-1]}_count"], 1)

    def test_missing_or_unproved_quote_corpus_blocks_before_database_access(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            missing = root / "missing-manifest.json"
            unproved = root / "unproved-manifest.json"
            unproved.write_text(
                json.dumps(
                    {
                        "chain_completeness": {
                            "status": "not_established",
                            "standard_satisfied": False,
                        },
                        "downstream_corpus_binding": {
                            "status": "exact",
                            "exact_row_set": True,
                            "errors": [],
                            "manifest_eligible_row_set_sha256": "a" * 64,
                            "database_eligible_row_set_sha256": "a" * 64,
                        },
                    }
                ),
                encoding="utf8",
            )
            fabricated_normalized = root / "fabricated-normalized.json"
            fabricated_normalized.write_text(
                json.dumps(
                    {
                        "quote_corpus_binding": {
                            "manifest_bound": True,
                            "exact_set_validated": True,
                            "chain_completeness_status": "established",
                            "manifest_sha256": "a" * 64,
                            "corpus_sha256": "b" * 64,
                            "source_batch_ids": [1],
                        }
                    }
                ),
                encoding="utf8",
            )
            for manifest_path, blocker in (
                (missing, "missing_manifest_bound_quote_corpus"),
                (unproved, "provider_chain_completeness_not_established"),
                (fabricated_normalized, "provider_chain_completeness_not_established"),
            ):
                with self.subTest(blocker=blocker):
                    batch_ids, meta, blockers = REAL_QUOTE_CORPUS_VERIFIER(
                        manifest_path, root / "missing-options.db"
                    )
                    self.assertEqual(batch_ids, ())
                    self.assertNotEqual(meta.get("status"), "validated")
                    self.assertIn(blocker, blockers)

    def test_invalid_manifest_bound_batch_and_zero_completed_trades_are_not_ready(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db = root / "quotes.db"
            vix = root / "vix.jsonl"
            crash = root / "crash.json"
            _create_db(db)
            market_dates = _write_complete_regime_inputs(vix, crash)
            with closing(sqlite3.connect(db)) as conn:
                conn.execute("UPDATE import_batches SET rejected_rows = 1 WHERE id = 2")
                conn.commit()
            with mock.patch.object(
                replay,
                "_verified_quote_corpus_from_manifest",
                return_value=((2,), VERIFIED_QUOTE_CORPUS_META, []),
            ):
                invalid_batch = replay.run_split(
                    split_name="family_train",
                    split_start=FROZEN_SPLIT_START,
                    split_end=FROZEN_SPLIT_END,
                    vix_rows_path=vix,
                    crash_guard_path=crash,
                    vix_policy={"low_max": 15.0, "mid_max": 25.0},
                    market_dates=market_dates,
                    db_path=db,
                    geometry=GEOMETRY,
                    bootstrap_draws=replay.FROZEN_BOOTSTRAP_DRAWS,
                )
            self.assertFalse(invalid_batch["evaluation_ready"])
            self.assertIn(
                "manifest_bound_quote_batch_failed_integrity_contract",
                invalid_batch["evaluation_blockers"],
            )

            zero_trades = replay.run_split(
                split_name="family_train",
                split_start=FROZEN_SPLIT_START,
                split_end=FROZEN_SPLIT_END,
                vix_rows_path=vix,
                crash_guard_path=crash,
                vix_policy={"low_max": 15.0, "mid_max": 25.0},
                market_dates=market_dates,
                db_path=db,
                geometry=GEOMETRY,
                bootstrap_draws=replay.FROZEN_BOOTSTRAP_DRAWS,
            )
            self.assertFalse(zero_trades["evaluation_ready"])
            self.assertIn("zero_completed_trades", zero_trades["evaluation_blockers"])
            self.assertEqual(zero_trades["completed_trades"], 0)
            self.assertEqual(zero_trades["metrics"], {})


if __name__ == "__main__":
    unittest.main()
