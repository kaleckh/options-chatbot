from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_dispersion_proxy_hybrid_bounded_replay as replay


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf8")


class RegularOptionsDispersionProxyHybridBoundedReplayTests(unittest.TestCase):
    def test_missing_artifacts_fail_closed_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = replay.build_report(
                readiness_path=root / "missing-readiness.json",
                proxy_path=root / "missing-proxy.json",
                candidate_rows_path=root / "missing-candidates.jsonl",
                options_db_path=root / "missing-options.db",
                generated_at_utc="2026-06-28T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_dispersion_proxy_hybrid_bounded_replay")
        self.assertEqual(
            report["blockers"],
            [
                "dispersion_proxy_hybrid_readiness_not_ready",
                "point_in_time_dispersion_proxy_artifact_missing",
                "missing_dispersion_pair_candidate_rows",
                "options_history_db_unavailable_for_read_only_quote_lookup",
            ],
        )
        self.assertTrue(report["read_only"])
        self.assertTrue(report["research_only"])
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["quotes_imported"])
        self.assertFalse(report["evidence_stores_mutated"])
        self.assertFalse(report["live_validation_enabled"])
        self.assertFalse(report["auto_track_enabled"])
        self.assertFalse(report["broker_order_allowed"])

    def test_exact_trusted_side_aware_pair_candidate_prices_net_pnl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            readiness_path = root / "readiness.json"
            proxy_path = root / "proxy.json"
            candidates_path = root / "candidate_rows.jsonl"
            options_db_path = root / "options_history.db"
            _write_json(
                readiness_path,
                {
                    "report_id": "regular_options_dispersion_proxy_hybrid_replay_readiness",
                    "status": "dispersion_proxy_hybrid_replay_readiness_ready",
                    "blockers": [],
                },
            )
            _write_json(
                proxy_path,
                {
                    "report_id": "regular_options_point_in_time_dispersion_concentration_proxy",
                    "status": "point_in_time_dispersion_concentration_proxy_available",
                    "proxy_rows": [],
                },
            )
            candidates_path.write_text(
                json.dumps(
                    {
                        "pair_id": "pair-1",
                        "concept_id": replay.CONCEPT_ID,
                        "proxy_date_et": "2026-06-01",
                        "entry_date_et": "2026-06-02",
                        "exit_date_et": "2026-06-09",
                        "entry_minute_et": 600,
                        "exit_minute_et": 900,
                        "index_debit_long_contract": "SPY260717C00700000",
                        "index_debit_short_contract": "SPY260717C00710000",
                        "constituent_credit_short_contract": "AAPL260717P00190000",
                        "constituent_credit_long_contract": "AAPL260717P00185000",
                        "pair_max_loss_usd": 500,
                        "required_collateral_usd": 500,
                        "undefined_or_uncapped_pair_risk_allowed": False,
                        "protected_holdout_overlap": False,
                    }
                )
                + "\n",
                encoding="utf8",
            )
            conn = sqlite3.connect(options_db_path)
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
                        quote_date_et text not null,
                        quote_minute_et integer not null,
                        bid real,
                        ask real,
                        source_batch_id integer not null
                    );
                    insert into import_batches(id, source_label, data_trust)
                    values (1, 'thetadata_opra_nbbo_1m', 'trusted');
                    """
                )
                rows = [
                    ("SPY260717C00700000", "2026-06-02", 590, 2.0, 2.2),
                    ("SPY260717C00710000", "2026-06-02", 590, 1.0, 1.1),
                    ("AAPL260717P00190000", "2026-06-02", 590, 1.5, 1.6),
                    ("AAPL260717P00185000", "2026-06-02", 590, 0.6, 0.7),
                    ("SPY260717C00700000", "2026-06-09", 900, 3.0, 3.2),
                    ("SPY260717C00710000", "2026-06-09", 900, 1.2, 1.3),
                    ("AAPL260717P00190000", "2026-06-09", 900, 0.8, 0.9),
                    ("AAPL260717P00185000", "2026-06-09", 900, 0.4, 0.5),
                ]
                conn.executemany(
                    """
                    insert into option_quote_snapshots(
                        contract_symbol, snapshot_kind, quote_date_et, quote_minute_et, bid, ask, source_batch_id
                    )
                    values (?, 'intraday', ?, ?, ?, ?, 1)
                    """,
                    rows,
                )
                conn.commit()
            finally:
                conn.close()

            report = replay.build_report(
                readiness_path=readiness_path,
                proxy_path=proxy_path,
                candidate_rows_path=candidates_path,
                options_db_path=options_db_path,
                generated_at_utc="2026-06-28T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_dispersion_proxy_hybrid_bounded_replay")
        self.assertEqual(report["denominator_rows"], 1)
        self.assertEqual(report["strict_new_exact_completed_rows"], 0)
        self.assertEqual(report["priced_exact_rows"], 1)
        self.assertEqual(report["quote_coverage_pct"], 100.0)
        self.assertEqual(report["profit_metrics"]["net_pnl_usd"], 74.8)
        self.assertEqual(report["resolved_rows"][0]["denominator_status"], "priced_exact_research_only_insufficient_proof")
        self.assertEqual(report["resolved_rows"][0]["side_aware_entry_quote_status"], "resolved")
        self.assertEqual(report["resolved_rows"][0]["side_aware_exit_quote_status"], "resolved")
        self.assertIn("Current Evidence Boundary", replay.render_markdown(report))
        self.assertIn("bounded_replay_priced_rows_below_30", report["blockers"])
        self.assertIn("bounded_replay_pf_lower_bound_missing", report["blockers"])
        self.assertIn("bounded_replay_stress_pf_missing", report["blockers"])
        self.assertIn("bounded_replay_no_proof_qualified_rows", report["blockers"])
        self.assertFalse(report["resolved_rows"][0]["proof_qualified"])
        self.assertFalse(report["historical_rows_are_forward_proof"])

    def test_missing_entry_or_exit_minutes_do_not_use_latest_same_day_quotes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            readiness_path, proxy_path, candidates_path, options_db_path = self._priced_fixture(root)
            rows = [json.loads(candidates_path.read_text(encoding="utf8"))]
            rows[0].pop("entry_minute_et")
            rows[0].pop("exit_minute_et")
            candidates_path.write_text(json.dumps(rows[0]) + "\n", encoding="utf8")

            report = replay.build_report(
                readiness_path=readiness_path,
                proxy_path=proxy_path,
                candidate_rows_path=candidates_path,
                options_db_path=options_db_path,
                generated_at_utc="2026-06-28T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_dispersion_proxy_hybrid_bounded_replay")
        self.assertEqual(report["priced_exact_rows"], 0)
        self.assertEqual(report["strict_new_exact_completed_rows"], 0)
        blockers = report["resolved_rows"][0]["blockers"]
        self.assertIn("missing_candidate_field:entry_minute_et", blockers)
        self.assertIn("missing_candidate_field:exit_minute_et", blockers)
        self.assertIn("entry_missing_leg_quote", blockers)
        self.assertIn("exit_missing_leg_quote", blockers)
        self.assertFalse(report["resolved_rows"][0]["proof_qualified"])

    def test_trusted_data_flag_without_executable_source_label_does_not_price(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            readiness_path, proxy_path, candidates_path, options_db_path = self._priced_fixture(
                root,
                source_label="unknown_vendor",
            )

            report = replay.build_report(
                readiness_path=readiness_path,
                proxy_path=proxy_path,
                candidate_rows_path=candidates_path,
                options_db_path=options_db_path,
                generated_at_utc="2026-06-28T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_dispersion_proxy_hybrid_bounded_replay")
        self.assertEqual(report["priced_exact_rows"], 0)
        self.assertEqual(report["strict_new_exact_completed_rows"], 0)
        self.assertIn("entry_missing_leg_quote", report["resolved_rows"][0]["blockers"])
        self.assertIn("exit_missing_leg_quote", report["resolved_rows"][0]["blockers"])
        self.assertFalse(report["resolved_rows"][0]["proof_qualified"])

    def test_proxy_rows_without_pair_candidates_form_blocked_denominator(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            readiness_path = root / "readiness.json"
            proxy_path = root / "proxy.json"
            _write_json(
                readiness_path,
                {
                    "status": "dispersion_proxy_hybrid_replay_readiness_ready",
                    "blockers": [],
                },
            )
            _write_json(
                proxy_path,
                {
                    "status": "point_in_time_dispersion_concentration_proxy_available",
                    "proxy_rows": [
                        {
                            "proxy_date_et": "2026-06-01",
                            "index_carrier": "SPY",
                            "blockers": [],
                        }
                    ],
                },
            )

            report = replay.build_report(
                readiness_path=readiness_path,
                proxy_path=proxy_path,
                candidate_rows_path=root / "missing-candidates.jsonl",
                options_db_path=root / "missing-options.db",
                generated_at_utc="2026-06-28T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_dispersion_proxy_hybrid_bounded_replay")
        self.assertEqual(report["denominator_rows"], 1)
        self.assertEqual(
            report["denominator_status_counts"],
            {"blocked_missing_pair_contract_selection_surface": 1},
        )
        self.assertEqual(report["resolved_rows"][0]["blockers"], ["missing_dispersion_pair_candidate_rows"])
        self.assertIn("missing_dispersion_pair_candidate_rows", report["blockers"])
        self.assertFalse(report["resolved_rows"][0]["proof_qualified"])

    def _priced_fixture(
        self,
        root: Path,
        *,
        source_label: str = "thetadata_opra_nbbo_1m",
    ) -> tuple[Path, Path, Path, Path]:
        readiness_path = root / "readiness.json"
        proxy_path = root / "proxy.json"
        candidates_path = root / "candidate_rows.jsonl"
        options_db_path = root / "options_history.db"
        _write_json(
            readiness_path,
            {
                "report_id": "regular_options_dispersion_proxy_hybrid_replay_readiness",
                "status": "dispersion_proxy_hybrid_replay_readiness_ready",
                "blockers": [],
            },
        )
        _write_json(
            proxy_path,
            {
                "report_id": "regular_options_point_in_time_dispersion_concentration_proxy",
                "status": "point_in_time_dispersion_concentration_proxy_available",
                "proxy_rows": [],
            },
        )
        candidates_path.write_text(
            json.dumps(
                {
                    "pair_id": "pair-1",
                    "concept_id": replay.CONCEPT_ID,
                    "proxy_date_et": "2026-06-01",
                    "entry_date_et": "2026-06-02",
                    "exit_date_et": "2026-06-09",
                    "entry_minute_et": 600,
                    "exit_minute_et": 900,
                    "index_debit_long_contract": "SPY260717C00700000",
                    "index_debit_short_contract": "SPY260717C00710000",
                    "constituent_credit_short_contract": "AAPL260717P00190000",
                    "constituent_credit_long_contract": "AAPL260717P00185000",
                    "pair_max_loss_usd": 500,
                    "required_collateral_usd": 500,
                    "undefined_or_uncapped_pair_risk_allowed": False,
                    "protected_holdout_overlap": False,
                }
            )
            + "\n",
            encoding="utf8",
        )
        conn = sqlite3.connect(options_db_path)
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
                    quote_date_et text not null,
                    quote_minute_et integer not null,
                    bid real,
                    ask real,
                    source_batch_id integer not null
                );
                """
            )
            conn.execute(
                "insert into import_batches(id, source_label, data_trust) values (1, ?, 'trusted')",
                (source_label,),
            )
            rows = [
                ("SPY260717C00700000", "2026-06-02", 590, 2.0, 2.2),
                ("SPY260717C00710000", "2026-06-02", 590, 1.0, 1.1),
                ("AAPL260717P00190000", "2026-06-02", 590, 1.5, 1.6),
                ("AAPL260717P00185000", "2026-06-02", 590, 0.6, 0.7),
                ("SPY260717C00700000", "2026-06-09", 900, 3.0, 3.2),
                ("SPY260717C00710000", "2026-06-09", 900, 1.2, 1.3),
                ("AAPL260717P00190000", "2026-06-09", 900, 0.8, 0.9),
                ("AAPL260717P00185000", "2026-06-09", 900, 0.4, 0.5),
            ]
            conn.executemany(
                """
                insert into option_quote_snapshots(
                    contract_symbol, snapshot_kind, quote_date_et, quote_minute_et, bid, ask, source_batch_id
                )
                values (?, 'intraday', ?, ?, ?, ?, 1)
                """,
                rows,
            )
            conn.commit()
        finally:
            conn.close()
        return readiness_path, proxy_path, candidates_path, options_db_path


if __name__ == "__main__":
    unittest.main()
