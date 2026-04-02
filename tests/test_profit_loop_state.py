from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from profit_loop_shared_state import (
    append_run_ledger,
    begin_active_run,
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
            validate_profit_loop_state({"schema_version": 2})

    def test_validate_migrates_schema_v1_payload(self):
        normalized = validate_profit_loop_state(
            {
                "schema_version": 1,
                "updated_at": "2026-04-02T12:00:00Z",
                "latest_operational_health": None,
                "latest_truth_holdout": None,
                "latest_profit_validation": None,
                "open_issues": [],
                "resolved_issues": [],
            }
        )
        self.assertEqual(normalized["schema_version"], 2)
        self.assertIsNone(normalized["active_run"])

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

    def test_expired_claims_and_runs_reopen_on_load(self):
        state = empty_profit_loop_state()
        issue = {
            "issue_id": "truth-lane-live-policy-mismatch",
            "source_automation": "hourly-operational-health",
            "severity": "high",
            "blocker_class": "truth_lane_mismatch",
            "summary": "Mismatch",
            "evidence": ["one"],
            "suggested_fix_targets": ["options_chatbot.py"],
            "status": "open",
        }
        upsert_open_issue(state, issue, now_iso="2026-04-02T12:00:00Z")
        claim_issue(
            state,
            "truth-lane-live-policy-mismatch",
            now_iso="2026-04-02T12:05:00Z",
            claim_run_id="run-1",
            claim_ttl_minutes=1,
        )
        begin_active_run(
            state,
            automation_id="daily-profit-validation",
            phase="capture_baseline",
            commit_sha="abc123",
            env_hash="env123",
            proof_bundle_dir=str(self.state_dir / "runs" / "run-1"),
            run_id="run-1",
            now_iso="2026-04-02T12:05:00Z",
            lease_minutes=1,
        )
        save_profit_loop_state(state, state_dir=self.state_dir)

        with patch("profit_loop_shared_state._utc_now", return_value=datetime(2026, 4, 2, 12, 7, tzinfo=UTC)):
            loaded = load_profit_loop_state(self.state_dir)

        self.assertEqual(loaded["open_issues"][0]["status"], "open")
        self.assertEqual(loaded["active_run"]["status"], "expired")

    def test_validation_prerequisites_block_when_operational_health_is_recent_but_blocked(self):
        state = empty_profit_loop_state()
        state["latest_operational_health"] = {
            "ran_at": "2026-04-02T11:30:00Z",
            "verdict": "blocked",
            "loop_execution_status": "blocked",
        }
        state["latest_truth_holdout"] = {
            "ran_at": "2026-04-02T11:45:00Z",
            "verdict": "recorded",
            "loop_execution_status": "healthy",
            "results": {"daily_truth_refresh": {"status": "disabled"}},
        }
        blockers = validation_prerequisite_blockers(
            state,
            now=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
        )
        self.assertIn("blocked_operational_health", {item["code"] for item in blockers})

    def test_validation_prerequisites_block_when_truth_holdout_refresh_failed(self):
        state = empty_profit_loop_state()
        state["latest_operational_health"] = {
            "ran_at": "2026-04-02T11:30:00Z",
            "verdict": "healthy",
            "loop_execution_status": "healthy",
        }
        state["latest_truth_holdout"] = {
            "ran_at": "2026-04-02T11:45:00Z",
            "verdict": "blocked-daily-truth-refresh",
            "loop_execution_status": "blocked",
            "results": {"daily_truth_refresh": {"status": "failed"}},
        }
        blockers = validation_prerequisite_blockers(
            state,
            now=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
        )
        self.assertIn("failed_truth_holdout", {item["code"] for item in blockers})

    def test_validation_prerequisites_block_when_another_validation_run_is_active(self):
        state = empty_profit_loop_state()
        state["latest_operational_health"] = {
            "ran_at": "2026-04-02T11:30:00Z",
            "verdict": "healthy",
            "loop_execution_status": "healthy",
        }
        state["latest_truth_holdout"] = {
            "ran_at": "2026-04-02T11:45:00Z",
            "verdict": "recorded",
            "loop_execution_status": "healthy",
            "results": {"daily_truth_refresh": {"status": "disabled"}},
        }
        begin_active_run(
            state,
            automation_id="daily-profit-validation",
            phase="capture_baseline",
            commit_sha="abc123",
            env_hash="env123",
            proof_bundle_dir=str(self.state_dir / "runs" / "run-2"),
            run_id="run-2",
            now_iso="2026-04-02T11:55:00Z",
            lease_minutes=30,
        )
        blockers = validation_prerequisite_blockers(
            state,
            now=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
        )
        self.assertIn("active_profit_validation_run", {item["code"] for item in blockers})

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
