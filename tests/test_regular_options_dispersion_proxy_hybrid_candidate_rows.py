from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_dispersion_proxy_hybrid_bounded_replay as replay
from scripts import build_regular_options_dispersion_proxy_hybrid_candidate_rows as candidate_rows


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf8")


class RegularOptionsDispersionProxyHybridCandidateRowsTests(unittest.TestCase):
    def test_candidate_rows_are_read_only_and_feed_bounded_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            readiness_path = root / "readiness.json"
            proxy_path = root / "proxy.json"
            source_rows_path = root / "source_rows.jsonl"
            options_db_path = root / "options_history.db"
            out = root / "out"
            candidate_rows_path = out / "candidate_rows.jsonl"
            _write_json(
                readiness_path,
                {
                    "report_id": "regular_options_dispersion_proxy_hybrid_replay_readiness",
                    "status": "dispersion_proxy_hybrid_replay_readiness_ready",
                    "blockers": [],
                },
            )
            proxy_dates = [
                "2026-06-01",
                "2026-06-02",
                "2026-06-03",
                "2026-06-04",
                "2026-06-05",
                "2026-06-08",
                "2026-06-09",
            ]
            _write_json(
                proxy_path,
                {
                    "report_id": "regular_options_point_in_time_dispersion_concentration_proxy",
                    "status": "point_in_time_dispersion_concentration_proxy_available",
                    "blockers": [],
                    "proxy_rows": [
                        {
                            "proxy_date_et": date_value,
                            "index_carrier": "SPY",
                            "broadening_or_narrowing_state": "concentrated_leadership"
                            if index == 0
                            else "broad_or_mixed",
                            "blockers": [],
                        }
                        for index, date_value in enumerate(proxy_dates)
                    ],
                },
            )
            _write_jsonl(
                source_rows_path,
                [
                    {
                        "proxy_date_et": "2026-06-01",
                        "symbol": "SPY",
                        "return_pct": 4.0,
                        "source_family": "fixture_pit_source",
                        "source_timestamp_utc": "2026-05-29T21:15:00Z",
                    },
                    {
                        "proxy_date_et": "2026-06-01",
                        "symbol": "AAPL",
                        "return_pct": 12.0,
                        "source_family": "fixture_pit_source",
                        "source_timestamp_utc": "2026-05-29T21:15:00Z",
                        "upstream_source_row_hash": "aapl-hash",
                    },
                    {
                        "proxy_date_et": "2026-06-01",
                        "symbol": "JNJ",
                        "return_pct": 7.0,
                        "source_family": "fixture_pit_source",
                        "source_timestamp_utc": "2026-05-29T21:15:00Z",
                    },
                ],
            )
            self._write_options_db(options_db_path)

            report = candidate_rows.build_report(
                readiness_path=readiness_path,
                proxy_path=proxy_path,
                source_rows_path=source_rows_path,
                options_db_path=options_db_path,
                generated_at_utc="2026-06-30T00:00:00Z",
            )
            artifacts = candidate_rows.write_outputs(
                report,
                candidate_rows=report["trial_ledger_rows"][:],
                candidate_rows_path=candidate_rows_path,
                output_dir=out,
                docs_report=root / "docs" / "candidate-rows.md",
            )
            replay_report = replay.build_report(
                readiness_path=readiness_path,
                proxy_path=proxy_path,
                candidate_rows_path=candidate_rows_path,
                options_db_path=options_db_path,
                generated_at_utc="2026-06-30T00:00:00Z",
            )

        self.assertEqual(report["status"], "dispersion_proxy_hybrid_candidate_rows_ready_for_bounded_replay")
        self.assertEqual(report["denominator_row_count"], 7)
        self.assertEqual(report["candidate_selected_count"], 1)
        self.assertTrue(report["read_only"])
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["quotes_imported"])
        self.assertIn("candidate_rows_jsonl", artifacts)
        first_selected = next(row for row in report["trial_ledger_rows"] if row["candidate_selected"])
        self.assertEqual(first_selected["constituent_underlying"], "AAPL")
        self.assertEqual(first_selected["index_debit_long_contract"], "SPY260717C00600000")
        self.assertEqual(first_selected["index_debit_short_contract"], "SPY260717C00605000")
        self.assertEqual(first_selected["constituent_credit_short_contract"], "AAPL260717C00210000")
        self.assertEqual(first_selected["constituent_credit_long_contract"], "AAPL260717C00215000")
        self.assertEqual(first_selected["entry_date_et"], "2026-06-02")
        self.assertEqual(first_selected["exit_date_et"], "2026-06-09")
        self.assertFalse(first_selected["protected_holdout_overlap"])
        self.assertFalse(first_selected["historical_rows_are_forward_proof"])
        self.assertNotIn("missing_dispersion_pair_candidate_rows", replay_report["blockers"])
        self.assertEqual(replay_report["priced_exact_rows"], 1)
        self.assertIn("bounded_replay_priced_rows_below_30", replay_report["blockers"])

    def test_missing_options_db_classifies_all_rows_without_writing_trade_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            readiness_path = root / "readiness.json"
            proxy_path = root / "proxy.json"
            source_rows_path = root / "source_rows.jsonl"
            _write_json(readiness_path, {"status": "dispersion_proxy_hybrid_replay_readiness_ready", "blockers": []})
            _write_json(
                proxy_path,
                {
                    "status": "point_in_time_dispersion_concentration_proxy_available",
                    "proxy_rows": [
                        {
                            "proxy_date_et": "2026-06-01",
                            "index_carrier": "SPY",
                            "broadening_or_narrowing_state": "concentrated_leadership",
                            "blockers": [],
                        }
                    ],
                },
            )
            _write_jsonl(
                source_rows_path,
                [
                    {"proxy_date_et": "2026-06-01", "symbol": "SPY", "return_pct": 1.0},
                    {"proxy_date_et": "2026-06-01", "symbol": "AAPL", "return_pct": 2.0},
                ],
            )

            report = candidate_rows.build_report(
                readiness_path=readiness_path,
                proxy_path=proxy_path,
                source_rows_path=source_rows_path,
                options_db_path=root / "missing.db",
                generated_at_utc="2026-06-30T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_dispersion_proxy_hybrid_candidate_rows")
        self.assertEqual(report["candidate_selected_count"], 0)
        self.assertIn("options_history_db_unavailable_for_read_only_quote_lookup", report["blockers"])
        self.assertFalse(report["live_validation_enabled"])
        self.assertFalse(report["auto_track_enabled"])
        self.assertFalse(report["broker_order_allowed"])
        self.assertFalse(report["evidence_stores_mutated"])

    def _write_options_db(self, path: Path) -> None:
        conn = sqlite3.connect(path)
        try:
            conn.executescript(
                """
                create table import_batches (
                    id integer primary key,
                    source_label text not null,
                    data_trust text not null
                );
                create table option_quote_snapshots (
                    contract_symbol text not null,
                    snapshot_kind text not null,
                    underlying text not null,
                    quote_date_et text not null,
                    quote_minute_et integer not null,
                    expiry text not null,
                    option_type text not null,
                    strike real not null,
                    bid real,
                    ask real,
                    underlying_price real,
                    volume integer,
                    open_interest integer,
                    source_batch_id integer not null
                );
                insert into import_batches(id, source_label, data_trust)
                values (1, 'thetadata_opra_nbbo_1m', 'trusted');
                """
            )
            rows = [
                ("SPY260717C00600000", "SPY", "2026-06-02", 590, "2026-07-17", "call", 600.0, 10.0, 10.2, 600.0),
                ("SPY260717C00605000", "SPY", "2026-06-02", 590, "2026-07-17", "call", 605.0, 7.8, 8.0, 600.0),
                ("AAPL260717C00210000", "AAPL", "2026-06-02", 590, "2026-07-17", "call", 210.0, 4.0, 4.2, 203.0),
                ("AAPL260717C00215000", "AAPL", "2026-06-02", 590, "2026-07-17", "call", 215.0, 2.2, 2.4, 203.0),
                ("SPY260717C00600000", "SPY", "2026-06-09", 890, "2026-07-17", "call", 600.0, 12.0, 12.2, 610.0),
                ("SPY260717C00605000", "SPY", "2026-06-09", 890, "2026-07-17", "call", 605.0, 9.0, 9.2, 610.0),
                ("AAPL260717C00210000", "AAPL", "2026-06-09", 890, "2026-07-17", "call", 210.0, 3.0, 3.2, 204.0),
                ("AAPL260717C00215000", "AAPL", "2026-06-09", 890, "2026-07-17", "call", 215.0, 1.2, 1.4, 204.0),
            ]
            conn.executemany(
                """
                insert into option_quote_snapshots(
                    contract_symbol, snapshot_kind, underlying, quote_date_et, quote_minute_et,
                    expiry, option_type, strike, bid, ask, underlying_price, volume, open_interest, source_batch_id
                )
                values (?, 'intraday', ?, ?, ?, ?, ?, ?, ?, ?, ?, 10, 100, 1)
                """,
                rows,
            )
            conn.commit()
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
