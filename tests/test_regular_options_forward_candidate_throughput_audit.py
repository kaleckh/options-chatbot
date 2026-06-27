from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_forward_candidate_throughput_audit as audit


NOW = "2026-06-26T15:00:00Z"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


def _write_ledger(path: Path, *, selection_date: str = "2026-06-26") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE forward_sessions (
                id INTEGER PRIMARY KEY,
                recorded_at_utc TEXT,
                playbook TEXT,
                scan_picks_count INTEGER,
                eligibility_status TEXT,
                eligibility_blockers TEXT,
                notes_json TEXT,
                run_id TEXT,
                source_label TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO forward_sessions (
                id, recorded_at_utc, playbook, scan_picks_count, eligibility_status, eligibility_blockers, notes_json, run_id, source_label
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'scheduled_scan')
            """,
            [
                (
                    1,
                    "2026-06-26T17:00:00Z",
                    "volatility_expansion_observation",
                    0,
                    "ineligible",
                    json.dumps(["no_scan_picks", "missing_truth_source"]),
                    json.dumps({
                        "scan_funnel": {"raw_candidates": 3, "returned_picks": 0, "drop_counts": {"ev_floor": 1, "tech_score": 2}},
                        "symbol_diagnostics": {
                            "scan_drop_reasons": {
                                "SPY": {"drop_key": "tech_score", "details": {"tech_score": 52.0, "min_tech_score": 65.0}},
                                "QQQ": {"drop_key": "ev_floor", "details": {"reason": "negative_ev"}},
                            }
                        },
                    }),
                    f"scheduled_scan:{selection_date}:test:vol",
                ),
                (
                    2,
                    "2026-06-26T17:05:00Z",
                    "bullish_pullback_observation",
                    0,
                    "ineligible",
                    json.dumps(["no_scan_picks"]),
                    json.dumps({"scan_funnel": {"raw_candidates": 59, "returned_picks": 0, "drop_counts": {"momentum": 50, "history_or_liquidity": 8, "option_liquidity": 1}}}),
                    f"scheduled_scan:{selection_date}:test:bp",
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _row(**overrides) -> dict:
    row = {
        "playbook_id": "volatility_expansion_observation",
        "ticker": "SPY",
        "scan_date": "2026-06-26",
        "logged_at": "2026-06-26T14:30:00Z",
        "scanner_policy_hash": "missing_hash_for_fixture",
        "contract_symbol": "SPY260717C00700000",
        "short_contract_symbol": "SPY260717C00710000",
        "entry_quote_source": "opra_nbbo",
        "entry_quote_timestamp_utc": "2026-06-26T14:30:00Z",
        "entry_bid": 1.0,
        "entry_ask": 1.2,
        "denominator_status": "open_waiting_policy_exit",
    }
    row.update(overrides)
    return row


class RegularOptionsForwardCandidateThroughputAuditTests(unittest.TestCase):
    def test_no_same_day_phase2_rows_blocks_throughput(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "scan_picks.jsonl"
            ledger = root / "forward_tracking_authoritative.db"
            _write_ledger(ledger)
            _write_jsonl(
                path,
                [
                    _row(playbook_id="short_term", scan_date="2026-06-26"),
                    _row(playbook_id="volatility_expansion_observation", scan_date="2026-06-16"),
                    _row(playbook_id="volatility_expansion_observation", scan_date="2026-06-26", ticker="MSFT"),
                ],
            )
            report = audit.build_report(scan_picks_path=path, ledger_db_path=ledger, selection_date="2026-06-26", generated_at_utc=NOW)

        self.assertEqual(report["status"], "blocked_no_same_day_phase2_natural_selections")
        self.assertTrue(report["scheduled_phase2_all_lanes_scanned"])
        self.assertEqual(report["scheduled_phase2_scan_picks_count"], 0)
        self.assertEqual(report["scheduled_phase2_raw_candidates"], 62)
        self.assertEqual(report["scheduled_phase2_returned_picks"], 0)
        self.assertEqual(report["scheduled_phase2_drop_count_total"], 62)
        self.assertEqual(report["scheduled_phase2_drop_counts"]["momentum"], 50)
        self.assertEqual(report["scheduled_phase2_drop_counts"]["tech_score"], 2)
        self.assertEqual(report["scheduled_phase2_drop_stage_summary"]["status"], "candidate_starvation_from_scan_filters")
        self.assertEqual(report["scheduled_phase2_drop_stage_summary"]["total_drop_count"], 62)
        self.assertEqual(report["scheduled_phase2_drop_stage_summary"]["top_drop_stages"][0], {"stage": "momentum", "count": 50})
        self.assertEqual(report["scheduled_phase2_scan_drop_reason_count_total"], 2)
        self.assertEqual(report["candidate_starvation_evidence_status"], "raw_symbol_drop_reasons_recorded")
        self.assertEqual(report["scheduled_phase2_scan_drop_reason_sample"][0]["symbol"], "QQQ")
        self.assertEqual(report["scheduled_phase2_scan_drop_reason_sample"][0]["playbook"], "volatility_expansion_observation")
        self.assertNotIn("notes_json", report["scheduled_scan_sessions"][0])
        self.assertIn("scan_funnel_drop_counts", report["scheduled_scan_sessions"][0])
        vol_session = next(session for session in report["scheduled_scan_sessions"] if session["playbook"] == "volatility_expansion_observation")
        self.assertEqual(vol_session["scan_drop_reason_count"], 2)
        self.assertEqual(vol_session["scan_drop_reason_sample"][0]["symbol"], "QQQ")
        self.assertEqual(vol_session["scan_drop_reason_sample"][0]["drop_key"], "ev_floor")
        self.assertEqual(report["scheduled_phase2_eligibility_status_counts"], {"ineligible": 2})
        self.assertEqual(report["scheduled_phase2_eligibility_blocker_counts"]["no_scan_picks"], 2)
        self.assertEqual(report["scheduled_phase2_eligibility_blocker_counts"]["missing_truth_source"], 1)
        self.assertEqual(report["scan_picks_row_count"], 3)
        self.assertEqual(report["post_freeze_phase2_scan_pick_count"], 2)
        self.assertEqual(report["target_date_phase2_scan_pick_count"], 1)
        self.assertEqual(report["candidate_rows_staged"], 0)
        self.assertIn("non_preregistered_symbol", report["stager_rejected_counts"])

    def test_target_date_phase2_row_surfaces_candidate_stager_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "scan_picks.jsonl"
            ledger = root / "forward_tracking_authoritative.db"
            _write_ledger(ledger)
            _write_jsonl(path, [_row(scan_date="2026-06-26")])
            report = audit.build_report(scan_picks_path=path, ledger_db_path=ledger, selection_date="2026-06-26", generated_at_utc=NOW)

        self.assertEqual(report["target_date_phase2_scan_pick_count"], 1)
        self.assertEqual(report["accepted_profitability"], False)
        self.assertFalse(report["cohort_append_performed"])
        self.assertFalse(report["live_entry_allowed"])
        self.assertIn(report["status"], {"blocked_no_same_day_phase2_natural_selections", "candidate_throughput_ready_for_validation"})

    def test_write_outputs_creates_read_only_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "scan_picks.jsonl"
            ledger = root / "forward_tracking_authoritative.db"
            _write_ledger(ledger)
            _write_jsonl(path, [_row(playbook_id="short_term", scan_date="2026-06-26")])
            report = audit.build_report(scan_picks_path=path, ledger_db_path=ledger, selection_date="2026-06-26", generated_at_utc=NOW)
            artifacts = audit.write_outputs(report, output_dir=root / "out", docs_report=root / "doc.md")
            doc = (root / "doc.md").read_text(encoding="utf8")

        self.assertIn("latest_json", artifacts)
        self.assertIn("Forward Candidate Throughput Audit", doc)
        self.assertIn("Actionable Candidate-Starvation Stages", doc)
        self.assertIn("Candidate-starvation evidence status", doc)
        self.assertIn("Symbol Drop-Reason Samples", doc)
        self.assertIn("symbol drop reasons", doc)
        self.assertIn("does not run the scanner", doc)

    def test_stage_counts_without_symbol_reasons_require_next_reason_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "scan_picks.jsonl"
            ledger = root / "forward_tracking_authoritative.db"
            _write_ledger(ledger)
            conn = sqlite3.connect(ledger)
            try:
                conn.execute(
                    """
                    UPDATE forward_sessions
                    SET notes_json = json_remove(notes_json, '$.symbol_diagnostics')
                    """
                )
                conn.commit()
            finally:
                conn.close()
            _write_jsonl(path, [_row(playbook_id="short_term", scan_date="2026-06-26")])
            report = audit.build_report(scan_picks_path=path, ledger_db_path=ledger, selection_date="2026-06-26", generated_at_utc=NOW)

        self.assertEqual(report["scheduled_phase2_drop_count_total"], 62)
        self.assertEqual(report["scheduled_phase2_scan_drop_reason_count_total"], 0)
        self.assertEqual(
            report["candidate_starvation_evidence_status"],
            "stage_counts_only_waiting_for_symbol_drop_reasons",
        )
        self.assertEqual(report["scheduled_phase2_scan_drop_reason_sample"], [])

    def test_missing_scheduled_lane_session_points_to_passive_sweep(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "scan_picks.jsonl"
            ledger = root / "forward_tracking_authoritative.db"
            _write_jsonl(path, [])
            conn = sqlite3.connect(ledger)
            try:
                conn.execute(
                    """
                    CREATE TABLE forward_sessions (
                        id INTEGER PRIMARY KEY,
                        recorded_at_utc TEXT,
                        playbook TEXT,
                        scan_picks_count INTEGER,
                        eligibility_status TEXT,
                        eligibility_blockers TEXT,
                        notes_json TEXT,
                        run_id TEXT,
                        source_label TEXT
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()
            report = audit.build_report(scan_picks_path=path, ledger_db_path=ledger, selection_date="2026-06-26", generated_at_utc=NOW)

        self.assertEqual(report["status"], "blocked_forward_cohort_scheduled_scan_session_missing")
        self.assertEqual(report["next_action"], "run_passive_forward_cohort_scan_sweep_in_valid_market_window")
        self.assertIn("bullish_pullback_observation", report["scheduled_phase2_playbooks_missing_session"])

    def test_default_selection_date_uses_new_york_market_date_not_utc_date(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "scan_picks.jsonl"
            ledger = root / "forward_tracking_authoritative.db"
            _write_ledger(ledger, selection_date="2026-06-26")
            _write_jsonl(path, [_row(scan_date="2026-06-26")])
            report = audit.build_report(
                scan_picks_path=path,
                ledger_db_path=ledger,
                generated_at_utc="2026-06-27T03:25:22Z",
            )

        self.assertEqual(report["target_selection_date"], "2026-06-26")
        self.assertTrue(report["scheduled_phase2_all_lanes_scanned"])
        self.assertNotEqual(report["status"], "blocked_forward_cohort_scheduled_scan_session_missing")

    def test_weekend_default_selection_date_uses_latest_completed_market_day(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "scan_picks.jsonl"
            ledger = root / "forward_tracking_authoritative.db"
            _write_ledger(ledger, selection_date="2026-06-26")
            _write_jsonl(path, [_row(scan_date="2026-06-26")])
            report = audit.build_report(
                scan_picks_path=path,
                ledger_db_path=ledger,
                generated_at_utc="2026-06-27T16:00:00Z",
            )

        self.assertEqual(report["target_selection_date"], "2026-06-26")
        self.assertTrue(report["scheduled_phase2_all_lanes_scanned"])
        self.assertNotEqual(report["status"], "blocked_forward_cohort_scheduled_scan_session_missing")

    def test_row_timestamp_fallback_counts_new_york_market_date_not_utc_date(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "scan_picks.jsonl"
            ledger = root / "forward_tracking_authoritative.db"
            _write_ledger(ledger, selection_date="2026-06-26")
            _write_jsonl(
                path,
                [
                    _row(
                        scan_date=None,
                        logged_at="2026-06-27T01:25:00Z",
                        selection_timestamp_utc="2026-06-27T01:25:00Z",
                    )
                ],
            )
            report = audit.build_report(
                scan_picks_path=path,
                ledger_db_path=ledger,
                generated_at_utc="2026-06-27T03:25:22Z",
            )

        self.assertEqual(report["target_selection_date"], "2026-06-26")
        self.assertEqual(report["target_date_scan_pick_count"], 1)
        self.assertEqual(report["target_date_phase2_scan_pick_count"], 1)
        self.assertEqual(report["last_scan_pick_dates"], ["2026-06-26"])


if __name__ == "__main__":
    unittest.main()
