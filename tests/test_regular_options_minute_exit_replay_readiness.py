from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_minute_exit_replay_readiness as readiness


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


def _write_quote_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE import_batches (
                id INTEGER PRIMARY KEY,
                source_label TEXT NOT NULL,
                data_trust TEXT NOT NULL
            );
            CREATE TABLE option_quote_snapshots (
                source_batch_id INTEGER NOT NULL,
                contract_symbol TEXT NOT NULL,
                snapshot_kind TEXT NOT NULL,
                quote_date_et TEXT NOT NULL,
                quote_minute_et INTEGER NOT NULL,
                as_of_utc TEXT NOT NULL,
                bid REAL,
                ask REAL,
                underlying_price REAL
            );
            CREATE INDEX idx_option_quotes_contract_date
                ON option_quote_snapshots(contract_symbol, quote_date_et);
            """
        )
        conn.execute(
            "INSERT INTO import_batches(id, source_label, data_trust) VALUES (1, 'thetadata_opra_nbbo_1m', 'trusted')"
        )
        rows = [
            ("QQQ260618C00728000", 639, "2026-06-05T14:39:00Z", 11.77, 11.85),
            ("QQQ260618C00750000", 639, "2026-06-05T14:39:00Z", 3.17, 3.22),
            ("QQQ260618C00728000", 955, "2026-06-05T19:55:00Z", 6.13, 6.50),
            ("QQQ260618C00750000", 955, "2026-06-05T19:55:00Z", 1.41, 1.47),
            ("SPY260626C00760000", 640, "2026-06-05T14:40:00Z", 7.00, 7.10),
            ("SPY260626C00775000", 640, "2026-06-05T14:40:00Z", 1.00, 1.10),
            ("SPY260626C00760000", 955, "2026-06-05T19:55:00Z", 8.00, 8.10),
            ("SPY260626C00775000", 955, "2026-06-05T19:55:00Z", 2.00, 2.10),
        ]
        conn.executemany(
            """
            INSERT INTO option_quote_snapshots(
                source_batch_id,
                contract_symbol,
                snapshot_kind,
                quote_date_et,
                quote_minute_et,
                as_of_utc,
                bid,
                ask,
                underlying_price
            )
            VALUES (1, ?, 'intraday', '2026-06-05', ?, ?, ?, ?, 500.0)
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def _fixture_paths(root: Path) -> dict[str, Path]:
    paths = {key: root / f"{key}.json" for key in readiness.DEFAULT_ARTIFACT_PATHS}
    _write_json(
        paths["fresh_evidence_loop"],
        {
            "generated_at_utc": "2026-06-06T00:00:00Z",
            "summary": {
                "candidate_count": 2,
                "exact_exit_bridge_count": 1,
                "live_policy_change": False,
            },
        },
    )
    _write_json(
        paths["current_policy_stop_grid"],
        {
            "generated_at_utc": "2026-06-06T00:00:00Z",
            "evidence_boundary": {"not_claimed": "This is not yet a minute-by-minute intraday stop simulation."},
            "inputs": {"source_labels": ["thetadata_opra_nbbo_1m"]},
            "coverage": {"replayed_count": 10, "unresolved_count": 0},
            "rows": [
                {
                    "contract_symbol": "QQQ260618C00728000",
                    "short_contract_symbol": "QQQ260618C00750000",
                    "entry_execution_price": 9.04,
                }
            ],
        },
    )
    _write_json(
        paths["open_risk"],
        {
            "generated_at_utc": "2026-06-06T00:00:00Z",
            "open_risk_governor": {
                "status": "open_risk_governor_blocked",
                "live_entry_allowed": False,
                "live_exact_negative_ids": [537],
            },
        },
    )
    return paths


def _fill_rows() -> list[dict]:
    return [
        {
            "event_type": "candidate_shown",
            "logged_at": "2026-06-05T14:43:31Z",
            "scan_date": "2026-06-05",
            "playbook_id": "volatility_expansion_observation",
            "ticker": "QQQ",
            "pricing_evidence_class": "proof_live_opra_exact_contract",
            "selection_source": "live_chain_exact_contract",
            "fill_status": "auto_tracked",
            "fill_outcome": "paper_fill_recorded",
            "auto_track_position_id": 537,
            "filled": True,
            "filled_price": 9.0405,
            "selected_spread": {
                "expiry": "2026-06-18",
                "long_contract_symbol": "QQQ260618C00728000",
                "short_contract_symbol": "QQQ260618C00750000",
                "entry_execution_price": 9.0405,
                "quote_time_utc": "2026-06-05T14:39:44Z",
            },
            "fill_discipline_snapshot": {"fill_degradation_vs_mid_pct": 5.49},
            "top_alternatives": [{"rank": 1}],
        },
        {
            "event_type": "candidate_shown",
            "logged_at": "2026-06-05T14:44:00Z",
            "playbook_id": "swing",
            "ticker": "SPY",
            "pricing_evidence_class": "proof_live_opra_exact_contract",
            "selection_source": "live_chain_exact_contract",
            "fill_status": "not_filled_auto_track_skipped",
            "fill_outcome": "no_fill",
            "attempted_limit_price": 5.88,
            "attempted_limit_quote_time_utc": "2026-06-05T14:40:00Z",
            "selected_spread": {
                "expiry": "2026-06-26",
                "long_contract_symbol": "SPY260626C00760000",
                "short_contract_symbol": "SPY260626C00775000",
            },
        },
        {
            "event_type": "candidate_shown",
            "playbook_id": "short_term",
            "ticker": "QQQ",
            "pricing_evidence_class": "diagnostic_midpoint",
            "selected_spread": {"long_contract_symbol": "QQQ260612C00728000"},
        },
    ]


class RegularOptionsMinuteExitReplayReadinessTests(unittest.TestCase):
    def test_build_report_counts_seed_rows_without_claiming_minute_pnl_when_quotes_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture_paths(root)
            fills = root / "fills.jsonl"
            _write_jsonl(fills, _fill_rows())

            report = readiness.build_report(
                artifact_paths=paths,
                fill_attempts_path=fills,
                db_path=root / "missing_options_history.db",
                generated_at_utc="2026-06-06T00:00:00Z",
            )

        self.assertEqual(report["status"], "minute_exit_replay_readiness_readback")
        self.assertEqual(report["summary"]["overall_status"], "blocked_ready_seed_missing_minute_engine")
        self.assertEqual(report["summary"]["entry_seed_ready_count"], 2)
        self.assertEqual(report["summary"]["position_seed_ready_count"], 1)
        self.assertEqual(report["summary"]["true_minute_exit_pnl_count"], 0)
        self.assertEqual(report["summary"]["minute_quote_coverage_status"], "missing")
        self.assertEqual(report["summary"]["quote_store_error"], "options_history_db_missing")
        self.assertIn("daily_stop_grid_is_not_minute_level_proof", report["summary"]["blockers"])
        first = report["candidate_queue"][0]
        self.assertEqual(first["readiness_status"], "position_seed_ready_engine_missing")
        self.assertEqual(first["auto_track_position_id"], 537)
        self.assertEqual(first["entry_time_utc"], "2026-06-05T14:39:44Z")
        self.assertIn("minute_level_exit_replay_engine_missing", first["blockers"])

    def test_exact_quote_rows_emit_true_side_aware_minute_pnl_and_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture_paths(root)
            fills = root / "fills.jsonl"
            quotes = root / "options_history.db"
            _write_jsonl(fills, _fill_rows())
            _write_quote_db(quotes)

            report = readiness.build_report(
                artifact_paths=paths,
                fill_attempts_path=fills,
                db_path=quotes,
                generated_at_utc="2026-06-06T00:00:00Z",
            )

        self.assertEqual(report["summary"]["overall_status"], "minute_exit_replay_coverage_ready")
        self.assertEqual(report["summary"]["true_minute_exit_pnl_count"], 2)
        self.assertEqual(report["summary"]["position_linked_true_minute_exit_pnl_count"], 1)
        self.assertEqual(report["summary"]["minute_quote_coverage_status"], "full")
        self.assertEqual(report["summary"]["minute_exit_replay_engine_status"], "read_only_side_aware_engine_partial")
        self.assertEqual(report["summary"]["blockers"], [])
        decisions = report["summary"]["minute_exit_decision_counts"]
        self.assertEqual(decisions["hold_for_current_open_risk_review"], 1)
        self.assertEqual(decisions["reject_production_use_without_fill_or_position_link"], 1)
        first = report["minute_exit_replay_rows"][0]
        self.assertTrue(first["true_side_aware_pnl_available"])
        self.assertEqual(first["entry_side_aware_debit"], 8.68)
        self.assertEqual(first["exit_side_aware_value"], 4.66)
        self.assertEqual(first["gross_pnl_pct"], -46.31)
        self.assertEqual(first["entry_long_quote"]["bid"], 11.77)
        self.assertEqual(first["exit_short_quote"]["ask"], 1.47)

    def test_missing_required_input_blocks_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture_paths(root)
            paths["current_policy_stop_grid"].unlink()
            fills = root / "fills.jsonl"
            _write_jsonl(fills, _fill_rows())

            report = readiness.build_report(artifact_paths=paths, fill_attempts_path=fills)

        self.assertEqual(report["status"], "blocked_missing_inputs")
        self.assertIn("current_policy_stop_grid", report["summary"]["missing_required_inputs"])

    def test_non_exact_or_missing_contract_rows_are_not_seed_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture_paths(root)
            fills = root / "fills.jsonl"
            _write_jsonl(
                fills,
                [
                    {
                        "event_type": "candidate_shown",
                        "ticker": "QQQ",
                        "pricing_evidence_class": "diagnostic_midpoint",
                        "selected_spread": {"long_contract_symbol": "QQQ260612C00728000"},
                    }
                ],
            )

            report = readiness.build_report(artifact_paths=paths, fill_attempts_path=fills)

        self.assertEqual(report["summary"]["entry_seed_ready_count"], 0)
        self.assertEqual(report["summary"]["blocked_missing_exact_entry_seed_count"], 1)
        self.assertEqual(report["candidate_queue"][0]["readiness_status"], "blocked_missing_exact_entry_seed")
        self.assertIn("entry_not_proof_live_exact_contract", report["candidate_queue"][0]["blockers"])

    def test_live_policy_change_invalidates_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture_paths(root)
            payload = json.loads(paths["fresh_evidence_loop"].read_text(encoding="utf8"))
            payload["live_policy_change"] = True
            _write_json(paths["fresh_evidence_loop"], payload)
            fills = root / "fills.jsonl"
            _write_jsonl(fills, _fill_rows())

            report = readiness.build_report(artifact_paths=paths, fill_attempts_path=fills)

        self.assertEqual(report["status"], "invalid_live_policy_change")
        self.assertTrue(report["summary"]["live_policy_change"])

    def test_markdown_renders_boundary_and_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture_paths(root)
            fills = root / "fills.jsonl"
            _write_jsonl(fills, _fill_rows())
            report = readiness.build_report(artifact_paths=paths, fill_attempts_path=fills, db_path=root / "missing.db")
            markdown = readiness.render_markdown(report)

        self.assertIn("# Regular Options Minute Exit Replay Readiness", markdown)
        self.assertIn("## Candidate Queue", markdown)
        self.assertIn("does not create trades", markdown)
        self.assertIn("fixed-minute exit replay", markdown)

    def test_write_outputs_creates_latest_and_timestamped_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture_paths(root / "inputs")
            fills = root / "fills.jsonl"
            _write_jsonl(fills, _fill_rows())
            report = readiness.build_report(
                artifact_paths=paths,
                fill_attempts_path=fills,
                db_path=root / "missing.db",
                generated_at_utc="2026-06-06T00:00:00Z",
            )

            artifacts = readiness.write_outputs(
                report,
                output_dir=root / "out",
                docs_report=root / "docs" / "regular-options-minute-exit-replay-readiness.md",
            )

            for artifact_path in artifacts.values():
                self.assertTrue(Path(artifact_path).exists(), artifact_path)
            latest = json.loads(Path(artifacts["latest_json"]).read_text(encoding="utf8"))
            self.assertEqual(latest["report_id"], readiness.REPORT_ID)


if __name__ == "__main__":
    unittest.main()
