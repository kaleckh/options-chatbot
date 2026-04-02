from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from profit_loop_shared_state import (
    append_run_ledger,
    claim_issue,
    defer_issue,
    empty_profit_loop_state,
    ensure_profit_loop_state,
    list_run_ledger_events,
    load_profit_loop_state,
    resolve_issue,
    save_profit_loop_state,
    upsert_open_issue,
    validate_profit_loop_state,
    validation_prerequisite_blockers,
)


class ProfitLoopStateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.state_dir = Path(self._tmp.name) / "profit-loop"

    def test_validate_rejects_missing_top_level_keys(self):
        with self.assertRaises(ValueError):
            validate_profit_loop_state({"schema_version": 1})

    def test_upsert_refreshes_existing_issue_instead_of_duplicating(self):
        state = empty_profit_loop_state()
        issue = {
            "issue_id": "truth-lane-live-policy-mismatch",
            "source_automation": "hourly-operational-health",
            "severity": "high",
            "blocker_class": "truth_lane_mismatch",
            "summary": "Initial mismatch",
            "evidence": ["first"],
            "suggested_fix_targets": ["options_chatbot.py"],
            "status": "open",
        }
        upsert_open_issue(state, issue, now_iso="2026-04-02T12:00:00Z")
        refreshed = dict(issue)
        refreshed["summary"] = "Refreshed mismatch"
        refreshed["evidence"] = ["first", "second"]
        upsert_open_issue(state, refreshed, now_iso="2026-04-02T13:00:00Z")

        self.assertEqual(len(state["open_issues"]), 1)
        self.assertEqual(state["open_issues"][0]["first_seen_at"], "2026-04-02T12:00:00Z")
        self.assertEqual(state["open_issues"][0]["last_seen_at"], "2026-04-02T13:00:00Z")
        self.assertIn("second", state["open_issues"][0]["evidence"])

    def test_resolve_moves_issue_to_resolved(self):
        state = empty_profit_loop_state()
        issue = {
            "issue_id": "forward-holdout-no-raw-candidates",
            "source_automation": "daily-truth-holdout",
            "severity": "high",
            "blocker_class": "scan_starvation",
            "summary": "Zero picks",
            "evidence": ["raw_scan_picks=0"],
            "suggested_fix_targets": ["supervised_scan.py"],
            "status": "open",
        }
        upsert_open_issue(state, issue, now_iso="2026-04-02T12:00:00Z")
        resolved = resolve_issue(
            state,
            "forward-holdout-no-raw-candidates",
            resolution_branch="codex/automation/20260402-1200-forward-holdout-no-raw-candidates",
            resolution_commit="abc1234",
            now_iso="2026-04-02T12:30:00Z",
        )

        self.assertEqual(len(state["open_issues"]), 0)
        self.assertEqual(len(state["resolved_issues"]), 1)
        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(resolved["resolution_commit"], "abc1234")

    def test_defer_requires_next_action(self):
        state = empty_profit_loop_state()
        issue = {
            "issue_id": "replay-matrix-collapsed-results",
            "source_automation": "daily-profit-validation",
            "severity": "medium",
            "blocker_class": "replay_matrix_suspicious",
            "summary": "Collapsed matrix",
            "evidence": ["all four cells match"],
            "suggested_fix_targets": ["wfo_optimizer.py"],
            "status": "open",
        }
        upsert_open_issue(state, issue, now_iso="2026-04-02T12:00:00Z")
        claim_issue(state, "replay-matrix-collapsed-results", now_iso="2026-04-02T12:05:00Z")

        with self.assertRaises(ValueError):
            defer_issue(
                state,
                "replay-matrix-collapsed-results",
                deferred_reason="needs work",
                next_action="",
                now_iso="2026-04-02T12:06:00Z",
            )

    def test_validation_prerequisites_block_when_health_or_holdout_are_stale(self):
        state = empty_profit_loop_state()
        state["latest_operational_health"] = {
            "ran_at": "2026-04-02T07:00:00Z",
            "verdict": "healthy",
        }
        state["latest_truth_holdout"] = {
            "ran_at": "2026-04-01T23:30:00Z",
            "verdict": "recorded",
        }
        blockers = validation_prerequisite_blockers(
            state,
            now=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
            operational_max_age_hours=2,
        )

        codes = {item["code"] for item in blockers}
        self.assertIn("stale_operational_health", codes)
        self.assertIn("stale_truth_holdout", codes)

    def test_state_initialization_and_ledger_work_in_temp_dir(self):
        ensure_profit_loop_state(self.state_dir)
        state = load_profit_loop_state(self.state_dir)
        append_run_ledger({"automation_id": "hourly-operational-health", "verdict": "healthy"}, state_dir=self.state_dir)
        save_profit_loop_state(state, state_dir=self.state_dir)

        events = list_run_ledger_events(self.state_dir)
        self.assertTrue((self.state_dir / "profit-loop-state.json").exists())
        self.assertTrue((self.state_dir / "profit-loop-runs.jsonl").exists())
        self.assertEqual(events[0]["automation_id"], "hourly-operational-health")


if __name__ == "__main__":
    unittest.main()
