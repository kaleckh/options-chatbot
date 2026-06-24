from __future__ import annotations

import json
import sqlite3
import unittest
from datetime import date, timedelta
from pathlib import Path

from scripts import build_regular_options_all_local_quote_minute_structure_capability_atlas as atlas
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _support_files(tmp: Path, *, cvx_excluded: bool = False) -> dict[str, Path]:
    prior = tmp / "prior.json"
    packet = tmp / "packet.json"
    ledger = tmp / "ledger.json"
    opening = tmp / "opening.json"
    synthetic = tmp / "synthetic.json"
    policy = tmp / "policy.json"
    holdout = tmp / "holdout.json"
    _write_json(
        prior,
        {
            "report_id": "regular_options_local_quote_structure_capability_matrix",
            "status": "local_quote_surface_only_structures_exhausted_under_current_data",
            "metrics": {"replay_feasible_structure_count": 0},
            "next_replay_candidate": None,
        },
    )
    _write_json(packet, {"status": "ready_for_same_session_gpt55_guidance"})
    _write_json(ledger, {"status": "base_clean_stack_identity_ledger_ready", "ledger_row_count": 157, "identity_hashes": []})
    _write_json(opening, {"status": "blocked_quote_surface_opening_range_reversal_replay", "blockers": ["blocked_missing_quote_surface_underlying_price"]})
    _write_json(synthetic, {"status": "blocked_quote_derived_synthetic_forward_surface", "metrics": {"bucket_status_counts": {"blocked_missing_call_put_pairs": 7904}}})
    rules = []
    if cvx_excluded:
        rules.append(
            {
                "rule_id": "cvx_zero_bid_tradability_candidate_scope_v1",
                "status": "active",
                "symbols": ["CVX"],
                "reason": "zero_bid_tradability_floor_failure",
                "minimum_executable_quote_pct": 90.0,
                "observed_executable_quote_pct": 88.66,
            }
        )
    _write_json(policy, {"policy_id": "regular_options_source_quality_scope_policy", "status": "active", "rules": rules})
    _write_json(holdout, {"contract_id": "forward_holdout_contract", "status": "active"})
    return {
        "prior_matrix_path": prior,
        "packet_path": packet,
        "base_ledger_path": ledger,
        "opening_replay_path": opening,
        "synthetic_forward_path": synthetic,
        "source_quality_policy_path": policy,
        "holdout_path": holdout,
    }


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
    con.execute("INSERT INTO import_batches (id, source_label, data_trust) VALUES (2, 'manual_source', 'research')")
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
) -> None:
    con = sqlite3.connect(path)
    contract = f"{symbol}{expiry.replace('-', '')}{option_type[0].upper()}{int(strike * 1000):08d}"
    con.execute(
        """
        INSERT INTO option_quote_snapshots (
            as_of_utc, quote_date_et, quote_minute_et, snapshot_kind, underlying, contract_symbol, expiry,
            option_type, strike, bid, ask, last, iv, underlying_price, volume, open_interest, source_batch_id
        ) VALUES (?, ?, ?, 'intraday', ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, ?)
        """,
        (f"{quote_date}T15:00:00Z", quote_date, minute, symbol, contract, expiry, option_type, strike, bid, ask, batch_id),
    )
    con.commit()
    con.close()


def _add_surface_day(
    path: Path,
    quote_date: str,
    *,
    symbol: str = "SPY",
    zero_bid: bool = False,
    crossed: bool = False,
    missing_exit: bool = False,
    research_only: bool = False,
) -> None:
    expiry = (date.fromisoformat(quote_date) + timedelta(days=14)).isoformat()
    batch_id = 2 if research_only else 1
    minutes = (600,) if missing_exit else (600, 605, 950, 955)
    for minute in minutes:
        for option_type in ("call", "put"):
            for index, strike in enumerate((100.0, 101.0, 102.0, 103.0)):
                bid = 1.0 + index * 0.1
                ask = 1.1 + index * 0.1
                if zero_bid and option_type == "call" and index == 0:
                    bid = 0.0
                if crossed and option_type == "call" and index == 0:
                    bid, ask = 1.2, 1.0
                _insert_quote(path, symbol=symbol, quote_date=quote_date, minute=minute, expiry=expiry, option_type=option_type, strike=strike, bid=bid, ask=ask, batch_id=batch_id)


class AllLocalQuoteMinuteStructureCapabilityAtlasTests(unittest.TestCase):
    def _report(self, tmp: Path, db: Path, **kwargs: object) -> dict:
        support = _support_files(tmp, cvx_excluded=bool(kwargs.pop("cvx_excluded", False)))
        return atlas.build_report(
            db_path=db,
            start_date=str(kwargs.pop("start_date", "2026-02-01")),
            end_date=str(kwargs.pop("end_date", "2026-05-31")),
            bucket_width_minutes=int(kwargs.pop("bucket_width_minutes", 5)),
            min_train_months=int(kwargs.pop("min_train_months", 1)),
            min_latest_four_months=int(kwargs.pop("min_latest_four_months", 1)),
            min_full_window_opportunities=int(kwargs.pop("min_full_window_opportunities", 2)),
            min_latest_four_opportunities=int(kwargs.pop("min_latest_four_opportunities", 2)),
            max_detailed_surfaces=int(kwargs.pop("max_detailed_surfaces", 10)),
            generated_at_utc="2026-06-23T00:00:00Z",
            **support,
            **kwargs,
        )

    def test_missing_exit_quotes_fail_closed(self) -> None:
        with WorkspaceTempDir(prefix="all-local-atlas") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            _add_surface_day(db, "2026-02-03", missing_exit=True)
            report = self._report(tmp, db)

        self.assertEqual(report["metrics"]["replay_feasible_surface_count"], 0)
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["broker_order_allowed"])
        self.assertIn("blocked_no_stable_quote_minute_buckets", report["blockers"])

    def test_zero_bid_crossed_and_research_quotes_do_not_create_opportunities(self) -> None:
        with WorkspaceTempDir(prefix="all-local-atlas") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            _add_surface_day(db, "2026-02-03", zero_bid=True)
            _add_surface_day(db, "2026-02-04", crossed=True)
            _add_surface_day(db, "2026-02-05", symbol="QQQ", research_only=True)
            report = self._report(tmp, db)

        self.assertIn("SPY", report["symbol_inventory"])
        self.assertNotIn("QQQ", report["symbol_inventory"])
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["realized_pnl_used_for_ranking"])

    def test_clean_fixture_can_emit_ready_without_trading_state(self) -> None:
        with WorkspaceTempDir(prefix="all-local-atlas") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            for quote_date in ("2025-12-03", "2026-02-03", "2026-03-03", "2026-04-03", "2026-05-03"):
                _add_surface_day(db, quote_date)
            report = self._report(tmp, db, start_date="2025-12-01", end_date="2026-05-31")

        self.assertEqual(report["status"], "all_local_quote_minute_structure_capability_ready_for_replay_selection")
        self.assertIsNotNone(report["next_replay_candidate"])
        self.assertFalse(report["p_l_replay_performed"])
        self.assertFalse(report["live_validation_enabled"])
        self.assertFalse(report["auto_track_enabled"])

    def test_strict_new_dedupe_against_base_ledger_is_applied(self) -> None:
        with WorkspaceTempDir(prefix="all-local-atlas") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            for quote_date in ("2025-12-03", "2026-02-03"):
                _add_surface_day(db, quote_date)
            support = _support_files(tmp)
            first = atlas.build_report(
                db_path=db,
                start_date="2025-12-01",
                end_date="2026-02-28",
                min_train_months=1,
                min_latest_four_months=1,
                min_full_window_opportunities=1,
                min_latest_four_opportunities=1,
                generated_at_utc="2026-06-23T00:00:00Z",
                **support,
            )
            rep = first["_representative_opportunities"][0]
            _write_json(support["base_ledger_path"], {"status": "base_clean_stack_identity_ledger_ready", "ledger_row_count": 157, "identity_hashes": [rep["opportunity_identity_hash"]]})
            deduped = atlas.build_report(
                db_path=db,
                start_date="2025-12-01",
                end_date="2026-02-28",
                min_train_months=1,
                min_latest_four_months=1,
                min_full_window_opportunities=1,
                min_latest_four_opportunities=1,
                generated_at_utc="2026-06-23T00:00:00Z",
                **support,
            )

        first_top = first["surface_summaries"][0]["full_window_constructible_completed_opportunities_after_dedupe"]
        deduped_top = deduped["surface_summaries"][0]["full_window_constructible_completed_opportunities_after_dedupe"]
        self.assertLessEqual(deduped_top, first_top)

    def test_source_quality_policy_excludes_symbol_from_feasible_surfaces(self) -> None:
        with WorkspaceTempDir(prefix="all-local-atlas") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            for quote_date in ("2025-12-03", "2026-02-03", "2026-03-03"):
                _add_surface_day(db, quote_date, symbol="CVX")
            report = self._report(tmp, db, start_date="2025-12-01", end_date="2026-03-31", cvx_excluded=True)

        self.assertIn("CVX", report["universe_segments"]["source_quality_excluded"])
        self.assertEqual(report["metrics"]["replay_feasible_surface_count"], 0)
        self.assertFalse(report["promotion_ready"])

    def test_write_outputs_creates_expected_artifacts(self) -> None:
        with WorkspaceTempDir(prefix="all-local-atlas") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            _add_surface_day(db, "2026-02-03")
            report = self._report(tmp, db)
            artifacts = atlas.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "doc.md")

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertIn("daily_bucket_structure_status_jsonl", artifacts)
            self.assertIn("replay_surface_candidates_jsonl", artifacts)


if __name__ == "__main__":
    unittest.main()
