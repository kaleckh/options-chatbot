from __future__ import annotations

import json
import sqlite3
import unittest
from datetime import date, timedelta
from pathlib import Path

from scripts import build_regular_options_local_quote_structure_capability_matrix as matrix
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _support_files(tmp: Path) -> dict[str, Path]:
    packet = tmp / "packet.json"
    ledger = tmp / "ledger.json"
    opening = tmp / "opening.json"
    synthetic = tmp / "synthetic.json"
    holdout = tmp / "holdout.json"
    _write_json(packet, {"status": "underpowered_forward_evidence"})
    _write_json(ledger, {"report_id": "regular_options_base_clean_stack_identity_ledger", "status": "base_clean_stack_identity_ledger_ready", "ledger_row_count": 157, "identity_hashes": []})
    _write_json(opening, {"report_id": "regular_options_quote_surface_opening_range_reversal_replay", "status": "blocked_quote_surface_opening_range_reversal_replay", "blockers": ["blocked_missing_quote_surface_underlying_price"]})
    _write_json(synthetic, {"report_id": "regular_options_quote_derived_synthetic_forward_surface", "status": "blocked_quote_derived_synthetic_forward_surface", "metrics": {"bucket_status_counts": {"blocked_missing_call_put_pairs": 7904}}})
    _write_json(holdout, {"contract_id": "forward_holdout_contract", "status": "active"})
    return {"packet_path": packet, "base_ledger_path": ledger, "opening_replay_path": opening, "synthetic_forward_path": synthetic, "holdout_path": holdout}


def _create_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.execute(
        """
        CREATE TABLE import_batches (
            id INTEGER PRIMARY KEY,
            source_label TEXT NOT NULL,
            data_trust TEXT NOT NULL
        )
        """
    )
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
    con.execute("INSERT INTO import_batches (id, source_label, data_trust) VALUES (1, 'thetadata_opra_nbbo_1m', 'trusted')")
    con.commit()
    con.close()


def _insert_quote(
    path: Path,
    *,
    symbol: str = "SPY",
    quote_date: str,
    minute: int,
    expiry: str,
    option_type: str,
    strike: float,
    bid: float,
    ask: float,
    batch_id: int = 1,
    snapshot_kind: str = "intraday",
) -> None:
    con = sqlite3.connect(path)
    contract = f"{symbol}{expiry.replace('-', '')}{option_type[0].upper()}{int(strike * 1000):08d}"
    con.execute(
        """
        INSERT INTO option_quote_snapshots (
            as_of_utc, quote_date_et, quote_minute_et, snapshot_kind, underlying, contract_symbol, expiry,
            option_type, strike, bid, ask, last, iv, underlying_price, volume, open_interest, source_batch_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, ?)
        """,
        (f"{quote_date}T15:00:00Z", quote_date, minute, snapshot_kind, symbol, contract, expiry, option_type, strike, bid, ask, batch_id),
    )
    con.commit()
    con.close()


def _add_surface_day(path: Path, quote_date: str, *, zero_bid: bool = False, crossed: bool = False, missing_exit: bool = False) -> None:
    entry_minutes = [matrix._bucket_to_minute("10:40"), matrix._bucket_to_minute("14:30")]
    exit_minute = matrix._bucket_to_minute("15:50")
    expiry = (date.fromisoformat(quote_date) + timedelta(days=14)).isoformat()
    strikes = [100.0, 101.0, 102.0, 103.0]
    for minute in entry_minutes + ([] if missing_exit else [exit_minute]):
        for option_type in ("call", "put"):
            for index, strike in enumerate(strikes):
                bid = 1.0 + index * 0.1
                ask = 1.1 + index * 0.1
                if zero_bid and index == 0 and option_type == "call":
                    bid = 0.0
                if crossed and index == 0 and option_type == "call":
                    bid, ask = 1.2, 1.0
                _insert_quote(path, quote_date=quote_date, minute=minute, expiry=expiry, option_type=option_type, strike=strike, bid=bid, ask=ask)


class LocalQuoteStructureCapabilityMatrixTests(unittest.TestCase):
    def _report(self, tmp: Path, db: Path, **kwargs: object) -> dict:
        support = _support_files(tmp)
        start_date = str(kwargs.pop("start_date", "2026-02-01"))
        end_date = str(kwargs.pop("end_date", "2026-05-31"))
        return matrix.build_report(
            db_path=db,
            start_date=start_date,
            end_date=end_date,
            universe=("SPY",),
            generated_at_utc="2026-06-23T00:00:00Z",
            **support,
            **kwargs,
        )

    def test_missing_exit_quotes_fail_closed(self) -> None:
        with WorkspaceTempDir(prefix="structure-matrix") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            _add_surface_day(db, "2026-02-03", missing_exit=True)
            report = self._report(tmp, db)

        self.assertEqual(report["status"], "local_quote_surface_only_structures_exhausted_under_current_data")
        self.assertEqual(report["metrics"]["replay_feasible_structure_count"], 0)
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["broker_order_allowed"])

    def test_zero_bid_and_crossed_quotes_do_not_create_opportunities(self) -> None:
        with WorkspaceTempDir(prefix="structure-matrix") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            _add_surface_day(db, "2026-02-03", zero_bid=True)
            _add_surface_day(db, "2026-02-04", crossed=True)
            report = self._report(tmp, db)

        single = next(row for row in report["structure_summaries"] if row["structure"] == "long_single_leg_calls_puts")
        self.assertGreater(single["full_window_constructible_completed_opportunities_after_dedupe"], 0)
        self.assertFalse(single["replay_feasible"])

    def test_same_minute_multi_leg_matching_and_no_midpoint_proof(self) -> None:
        with WorkspaceTempDir(prefix="structure-matrix") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            _add_surface_day(db, "2026-02-03")
            report = self._report(tmp, db)

        vertical = next(row for row in report["structure_summaries"] if row["structure"] == "same_expiration_same_type_verticals")
        self.assertGreater(vertical["full_window_constructible_completed_opportunities_after_dedupe"], 0)
        representative = next(row for row in report["_representative_opportunities"] if row["structure"] == "same_expiration_same_type_verticals")
        self.assertEqual(representative["quote_quality_basis"], "bid_ask_only_quote_quality_diagnostic_not_fill_or_pnl")
        self.assertFalse(representative["accepted_profitability"])

    def test_latest_four_below_30_blocks_replay_feasibility(self) -> None:
        with WorkspaceTempDir(prefix="structure-matrix") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            _add_surface_day(db, "2026-02-03")
            report = self._report(tmp, db)

        self.assertIsNone(report["next_replay_candidate"])
        self.assertIn("insufficient_latest_four_rows", report["blockers"])

    def test_clean_fixture_can_emit_ready_without_trading_state(self) -> None:
        with WorkspaceTempDir(prefix="structure-matrix") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            months = [f"2024-{month:02d}-03" for month in range(6, 13)]
            months += [f"2025-{month:02d}-03" for month in range(1, 13)]
            months += [f"2026-{month:02d}-03" for month in range(1, 6)]
            for quote_date in months:
                _add_surface_day(db, quote_date)
            report = self._report(tmp, db, start_date="2024-06-01", end_date="2026-05-31")

        self.assertEqual(report["status"], "local_quote_structure_capability_ready_for_replay_selection")
        self.assertIsNotNone(report["next_replay_candidate"])
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["live_entry_allowed"])
        self.assertFalse(report["auto_track_allowed"])

    def test_strict_new_dedupe_against_base_ledger_is_applied(self) -> None:
        with WorkspaceTempDir(prefix="structure-matrix") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            _add_surface_day(db, "2026-02-03")
            support = _support_files(tmp)
            report = matrix.build_report(
                db_path=db,
                start_date="2026-02-01",
                end_date="2026-02-28",
                universe=("SPY",),
                generated_at_utc="2026-06-23T00:00:00Z",
                **support,
            )
            rep = next(row for row in report["_representative_opportunities"] if row["structure"] == "long_single_leg_calls_puts")
            _write_json(support["base_ledger_path"], {"status": "base_clean_stack_identity_ledger_ready", "ledger_row_count": 157, "identity_hashes": [rep["opportunity_identity_hash"]]})
            deduped = matrix.build_report(
                db_path=db,
                start_date="2026-02-01",
                end_date="2026-02-28",
                universe=("SPY",),
                generated_at_utc="2026-06-23T00:00:00Z",
                **support,
            )

        single = next(row for row in deduped["structure_summaries"] if row["structure"] == "long_single_leg_calls_puts")
        self.assertLess(single["full_window_constructible_completed_opportunities_after_dedupe"], report["structure_summaries"][0]["full_window_constructible_completed_opportunities_after_dedupe"])

    def test_write_outputs_creates_expected_artifacts(self) -> None:
        with WorkspaceTempDir(prefix="structure-matrix") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            _add_surface_day(db, "2026-02-03")
            report = self._report(tmp, db)
            artifacts = matrix.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "doc.md")

            self.assertIn("daily_structure_status_jsonl", artifacts)
            self.assertIn("representative_opportunities_jsonl", artifacts)
            self.assertTrue((tmp / "out" / "latest.json").exists())


if __name__ == "__main__":
    unittest.main()
