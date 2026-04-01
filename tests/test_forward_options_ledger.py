import os
import sqlite3
import tempfile
import unittest
from contextlib import closing

from forward_options_ledger import (
    init_forward_ledger,
    list_forward_sessions,
    record_forward_snapshot,
    summarize_forward_holdout,
)


class ForwardOptionsLedgerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = os.path.join(self._tmp.name, "forward_tracking.db")

    def test_record_forward_snapshot_persists_scan_and_reviews(self):
        result = record_forward_snapshot(
            scan_snapshot={
                "picks": [
                    {
                        "ticker": "SPY",
                        "direction": "call",
                        "contract_symbol": "SPY260417C00560000",
                        "trade_policy_decision": "watch",
                        "cohort_id": "baseline_broad_control",
                        "cohort_role": "control",
                    }
                ],
                "policy_applied": True,
                "policy": {
                    "truth_source": "historical_imported_daily",
                    "promotion_status": "watch",
                },
                "playbook": {"id": "short_term"},
                "scan_funnel": {
                    "raw_candidates": 3,
                    "post_policy_visible": 2,
                    "post_guardrails_visible": 1,
                    "returned_picks": 1,
                    "policy_filtered_out": 1,
                    "guardrail_filtered_out": 1,
                    "final_trimmed": 0,
                },
                "cohort_funnels": {
                    "baseline_broad_control": {
                        "raw_candidates": 3,
                        "post_policy_visible": 2,
                        "post_guardrails_visible": 1,
                        "returned_picks": 1,
                        "policy_filtered_out": 1,
                        "guardrail_filtered_out": 1,
                        "final_trimmed": 0,
                    }
                },
            },
            reviewed_positions=[
                {
                    "id": 7,
                    "ticker": "SPY",
                    "contract_symbol": "SPY260417C00560000",
                    "source_pick_snapshot": {
                        "contract_symbol": "SPY260417C00560000",
                        "cohort_id": "baseline_broad_control",
                    },
                    "latest_review": {
                        "recommendation": "HOLD",
                        "pricing_source": "mid",
                    },
                }
            ],
            tracked_positions=[
                {
                    "id": 7,
                    "ticker": "SPY",
                    "source_pick_snapshot": {
                        "contract_symbol": "SPY260417C00560000",
                        "cohort_id": "baseline_broad_control",
                    },
                }
            ],
            source_label="unit_test",
            db_path=self.db_path,
        )

        self.assertEqual(result["scan_picks_count"], 1)
        self.assertEqual(result["reviewed_positions_count"], 1)
        self.assertEqual(result["truth_source"], "historical_imported_daily")
        self.assertEqual(result["taken_pick_count"], 1)
        self.assertEqual(result["skipped_pick_count"], 0)
        self.assertEqual(result["blocked_pick_count"], 0)
        self.assertEqual(result["scan_funnel"]["raw_candidates"], 3)

        sessions = list_forward_sessions(db_path=self.db_path)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["source_label"], "unit_test")
        self.assertEqual(sessions[0]["scan_picks_count"], 1)
        self.assertEqual(sessions[0]["reviewed_positions_count"], 1)
        self.assertEqual(sessions[0]["notes"]["scan_funnel"]["post_guardrails_visible"], 1)

        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                """
                SELECT event_type, contract_symbol, policy_state, outcome_state
                FROM forward_events
                WHERE event_type = 'scan_pick'
                """
            ).fetchone()
        self.assertEqual(row[0], "scan_pick")
        self.assertEqual(row[1], "SPY260417C00560000")
        self.assertEqual(row[2], "watch")
        self.assertEqual(row[3], "taken")

        summary = summarize_forward_holdout(cohort_id=None, db_path=self.db_path)
        self.assertTrue(summary["available"])
        self.assertEqual(summary["scan_pick_count"], 1)
        self.assertEqual(summary["taken_pick_count"], 1)
        self.assertEqual(summary["review_count"], 1)
        self.assertEqual(summary["scan_funnel_totals"]["raw_candidates"], 3)
        self.assertEqual(summary["latest_starvation_stage"], None)

    def test_init_forward_ledger_upgrades_legacy_schema_before_indexing(self):
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.executescript(
                """
                CREATE TABLE forward_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at_utc TEXT NOT NULL,
                    source_label TEXT NOT NULL,
                    playbook TEXT,
                    truth_source TEXT,
                    promotion_status TEXT,
                    scan_picks_count INTEGER NOT NULL DEFAULT 0,
                    reviewed_positions_count INTEGER NOT NULL DEFAULT 0,
                    notes_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE forward_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL REFERENCES forward_sessions(id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL,
                    event_key TEXT,
                    ticker TEXT,
                    contract_symbol TEXT,
                    recommendation TEXT,
                    pricing_source TEXT,
                    payload_json TEXT NOT NULL
                );
                """
            )
            conn.commit()

        init_forward_ledger(self.db_path)

        with closing(sqlite3.connect(self.db_path)) as conn:
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(forward_events)").fetchall()
            }
            indexes = {
                row[1]
                for row in conn.execute("PRAGMA index_list(forward_events)").fetchall()
            }

        self.assertIn("cohort_id", columns)
        self.assertIn("outcome_state", columns)
        self.assertIn("idx_forward_events_cohort", indexes)

    def test_summary_counts_recorded_sessions_even_when_no_events_exist(self):
        result = record_forward_snapshot(
            scan_snapshot={
                "picks": [],
                "policy_applied": True,
                "policy": {
                    "truth_source": "historical_imported_daily",
                    "promotion_status": "block",
                },
                "playbook": {"id": "short_term"},
                "cohort_ids": ["broad_ev7"],
                "scan_funnel": {
                    "raw_candidates": 4,
                    "post_policy_visible": 2,
                    "post_guardrails_visible": 0,
                    "returned_picks": 0,
                    "policy_filtered_out": 2,
                    "guardrail_filtered_out": 2,
                    "final_trimmed": 0,
                },
                "cohort_funnels": {
                    "broad_ev7": {
                        "raw_candidates": 4,
                        "post_policy_visible": 2,
                        "post_guardrails_visible": 0,
                        "returned_picks": 0,
                        "policy_filtered_out": 2,
                        "guardrail_filtered_out": 2,
                        "final_trimmed": 0,
                    }
                },
            },
            reviewed_positions=[],
            tracked_positions=[],
            source_label="quiet_day",
            db_path=self.db_path,
        )

        self.assertEqual(result["scan_picks_count"], 0)

        overall = summarize_forward_holdout(cohort_id=None, db_path=self.db_path)
        self.assertTrue(overall["available"])
        self.assertEqual(overall["session_count"], 1)
        self.assertEqual(overall["scan_pick_count"], 0)
        self.assertEqual(overall["truth_sources_seen"], ["historical_imported_daily"])
        self.assertEqual(overall["scan_funnel_totals"]["raw_candidates"], 4)
        self.assertEqual(overall["sessions_with_zero_scan_picks"], 1)
        self.assertEqual(overall["latest_starvation_stage"], "guardrails_filtered_all")

        cohort_summary = summarize_forward_holdout(cohort_id="broad_ev7", db_path=self.db_path)
        self.assertTrue(cohort_summary["available"])
        self.assertEqual(cohort_summary["session_count"], 1)
        self.assertEqual(cohort_summary["scan_pick_count"], 0)
        self.assertEqual(cohort_summary["scan_funnel_totals"]["raw_candidates"], 4)
        self.assertEqual(cohort_summary["latest_starvation_stage"], "guardrails_filtered_all")

    def test_summary_counts_quiet_sessions_in_cohort_funnel_history(self):
        record_forward_snapshot(
            scan_snapshot={
                "picks": [
                    {
                        "ticker": "SPY",
                        "direction": "call",
                        "contract_symbol": "SPY260417C00560000",
                        "trade_policy_decision": "watch",
                        "cohort_id": "broad_ev7",
                        "cohort_role": "broad_challenger",
                    }
                ],
                "policy_applied": True,
                "policy": {
                    "truth_source": "historical_imported_daily",
                    "promotion_status": "watch",
                },
                "playbook": {"id": "short_term"},
                "cohort_ids": ["broad_ev7"],
                "scan_funnel": {
                    "raw_candidates": 2,
                    "post_policy_visible": 1,
                    "post_guardrails_visible": 1,
                    "returned_picks": 1,
                    "policy_filtered_out": 1,
                    "guardrail_filtered_out": 0,
                    "final_trimmed": 0,
                },
                "cohort_funnels": {
                    "broad_ev7": {
                        "raw_candidates": 2,
                        "post_policy_visible": 1,
                        "post_guardrails_visible": 1,
                        "returned_picks": 1,
                        "policy_filtered_out": 1,
                        "guardrail_filtered_out": 0,
                        "final_trimmed": 0,
                    }
                },
            },
            reviewed_positions=[],
            tracked_positions=[],
            source_label="eventful_day",
            db_path=self.db_path,
        )
        record_forward_snapshot(
            scan_snapshot={
                "picks": [],
                "policy_applied": True,
                "policy": {
                    "truth_source": "historical_imported_daily",
                    "promotion_status": "block",
                },
                "playbook": {"id": "short_term"},
                "cohort_ids": ["broad_ev7"],
                "scan_funnel": {
                    "raw_candidates": 5,
                    "post_policy_visible": 2,
                    "post_guardrails_visible": 0,
                    "returned_picks": 0,
                    "policy_filtered_out": 3,
                    "guardrail_filtered_out": 2,
                    "final_trimmed": 0,
                },
                "cohort_funnels": {
                    "broad_ev7": {
                        "raw_candidates": 5,
                        "post_policy_visible": 2,
                        "post_guardrails_visible": 0,
                        "returned_picks": 0,
                        "policy_filtered_out": 3,
                        "guardrail_filtered_out": 2,
                        "final_trimmed": 0,
                    }
                },
            },
            reviewed_positions=[],
            tracked_positions=[],
            source_label="quiet_day",
            db_path=self.db_path,
        )

        summary = summarize_forward_holdout(cohort_id="broad_ev7", db_path=self.db_path)
        self.assertTrue(summary["available"])
        self.assertEqual(summary["session_count"], 2)
        self.assertEqual(summary["scan_pick_count"], 1)
        self.assertEqual(summary["sessions_with_zero_scan_picks"], 1)
        self.assertEqual(summary["scan_funnel_totals"]["raw_candidates"], 7)
        self.assertEqual(summary["scan_funnel_totals"]["guardrail_filtered_out"], 2)
        self.assertEqual(summary["latest_scan_funnel"]["post_guardrails_visible"], 0)
        self.assertEqual(summary["latest_starvation_stage"], "guardrails_filtered_all")


if __name__ == "__main__":
    unittest.main()
