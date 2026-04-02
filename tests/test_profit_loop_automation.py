from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from profit_loop_automation import (
    defer_profit_validation_issue,
    prepare_profit_validation,
    resolve_profit_validation_issue,
    run_operational_health,
    run_profit_loop_canary,
    run_truth_holdout,
)
from profit_loop_shared_state import (
    empty_profit_loop_state,
    list_run_ledger_events,
    load_profit_loop_state,
    save_profit_loop_state,
    upsert_open_issue,
)


class ProfitLoopAutomationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.state_dir = Path(self._tmp.name) / "shared-state"
        save_profit_loop_state(empty_profit_loop_state(), state_dir=self.state_dir)

    def test_operational_health_updates_latest_snapshot_and_opens_mismatch_issue(self):
        smoke_payload = {
            "scan_truth_lane": "historical_imported_daily",
            "live_policy_truth_source": "synthetic_research",
            "live_policy_promotion_status": "block",
            "live_policy_quote_coverage_pct": 100.0,
        }
        smoke_record = {"command": "python scripts/options_algorithm_smoke.py --fixture", "passed": True}
        test_record = {"command": "python -m unittest ...", "passed": True, "stdout": "Ran 9 tests\nOK", "stderr": ""}

        with patch("profit_loop_automation._run_json_command", return_value=(smoke_payload, smoke_record)), \
             patch("profit_loop_automation._run_unittest_modules", return_value=test_record):
            result = run_operational_health(state_dir=self.state_dir)

        state = load_profit_loop_state(self.state_dir)
        self.assertEqual(result["snapshot"]["verdict"], "degraded-watch")
        self.assertEqual(state["latest_operational_health"]["verdict"], "degraded-watch")
        self.assertEqual(state["open_issues"][0]["issue_id"], "truth-lane-live-policy-mismatch")

    def test_truth_holdout_updates_latest_snapshot_and_opens_starvation_issue(self):
        policy_payload = {"session_id": 101, "scan_picks_count": 0, "promotion_status": "block", "policy_fail_closed": False}
        raw_payload = {"session_id": 102, "scan_picks_count": 0, "promotion_status": "block", "policy_fail_closed": False}
        policy_record = {"command": "policy", "passed": True}
        raw_record = {"command": "raw", "passed": True}

        with patch("profit_loop_automation._run_json_command", side_effect=[(policy_payload, policy_record), (raw_payload, raw_record)]), \
             patch("profit_loop_automation.summarize_forward_holdout", return_value={"eligible_event_count": 0, "session_count": 2}):
            result = run_truth_holdout(state_dir=self.state_dir)

        state = load_profit_loop_state(self.state_dir)
        self.assertEqual(result["snapshot"]["verdict"], "recorded-no-candidates")
        self.assertEqual(state["latest_truth_holdout"]["results"]["raw_session_id"], 102)
        self.assertTrue(any(item["issue_id"] == "forward-holdout-no-raw-candidates" for item in state["open_issues"]))

    def test_profit_validation_reads_open_issue_queue_first(self):
        state = load_profit_loop_state(self.state_dir)
        state["latest_operational_health"] = {"ran_at": "2026-04-02T11:30:00Z", "verdict": "healthy"}
        state["latest_truth_holdout"] = {"ran_at": "2026-04-02T11:45:00Z", "verdict": "recorded"}
        upsert_open_issue(
            state,
            {
                "issue_id": "truth-lane-live-policy-mismatch",
                "source_automation": "hourly-operational-health",
                "severity": "high",
                "blocker_class": "truth_lane_mismatch",
                "summary": "Mismatch",
                "evidence": ["one"],
                "suggested_fix_targets": ["options_chatbot.py"],
                "status": "open",
            },
            now_iso="2026-04-02T11:50:00Z",
        )
        save_profit_loop_state(state, state_dir=self.state_dir)

        with patch("profit_loop_automation.validation_prerequisite_blockers", return_value=[]), \
             patch(
                 "profit_loop_automation._capture_validation_baseline",
                 return_value={"validation_tests_passed": True, "validation_test_count": 57, "smoke_summary": {}, "replay_cases": []},
             ):
            result = prepare_profit_validation(state_dir=self.state_dir, auto_defer=False)

        state = load_profit_loop_state(self.state_dir)
        self.assertEqual(result["action"], "claimed_issue")
        self.assertEqual(result["targeted_issue"]["issue_id"], "truth-lane-live-policy-mismatch")
        self.assertEqual(state["latest_profit_validation"]["targeted_issue_id"], "truth-lane-live-policy-mismatch")

    def test_profit_validation_auto_defer_records_reason_and_next_action(self):
        state = load_profit_loop_state(self.state_dir)
        state["latest_operational_health"] = {"ran_at": "2026-04-02T11:30:00Z", "verdict": "healthy"}
        state["latest_truth_holdout"] = {"ran_at": "2026-04-02T11:45:00Z", "verdict": "recorded"}
        upsert_open_issue(
            state,
            {
                "issue_id": "replay-matrix-collapsed-results",
                "source_automation": "daily-profit-validation",
                "severity": "medium",
                "blocker_class": "replay_matrix_suspicious",
                "summary": "Matrix collapsed",
                "evidence": ["all four cells match"],
                "suggested_fix_targets": ["wfo_optimizer.py"],
                "status": "open",
            },
            now_iso="2026-04-02T11:50:00Z",
        )
        save_profit_loop_state(state, state_dir=self.state_dir)

        with patch("profit_loop_automation.validation_prerequisite_blockers", return_value=[]), \
             patch(
                 "profit_loop_automation._capture_validation_baseline",
                 return_value={"validation_tests_passed": True, "validation_test_count": 57, "smoke_summary": {}, "replay_cases": []},
             ):
            result = prepare_profit_validation(state_dir=self.state_dir, auto_defer=True)

        state = load_profit_loop_state(self.state_dir)
        deferred = next(item for item in state["open_issues"] if item["issue_id"] == "replay-matrix-collapsed-results")
        self.assertEqual(result["action"], "deferred")
        self.assertEqual(deferred["status"], "deferred")
        self.assertEqual(deferred["deferred_reason"], "no_safe_fix_plan")
        self.assertTrue(str(deferred["next_action"]).strip())

    def test_profit_validation_resolve_records_branch_commit_and_proof(self):
        state = load_profit_loop_state(self.state_dir)
        state["latest_operational_health"] = {"ran_at": "2026-04-02T11:30:00Z", "verdict": "healthy"}
        state["latest_truth_holdout"] = {"ran_at": "2026-04-02T11:45:00Z", "verdict": "recorded"}
        upsert_open_issue(
            state,
            {
                "issue_id": "truth-lane-live-policy-mismatch",
                "source_automation": "hourly-operational-health",
                "severity": "high",
                "blocker_class": "truth_lane_mismatch",
                "summary": "Mismatch",
                "evidence": ["one"],
                "suggested_fix_targets": ["options_chatbot.py"],
                "status": "open",
            },
            now_iso="2026-04-02T11:50:00Z",
        )
        save_profit_loop_state(state, state_dir=self.state_dir)

        result = resolve_profit_validation_issue(
            issue_id="truth-lane-live-policy-mismatch",
            resolution_branch="codex/automation/20260402-1200-truth-lane-live-policy-mismatch",
            resolution_commit="abc1234",
            proof_commands=["python -m unittest tests.test_options_api_e2e -v"],
            state_dir=self.state_dir,
        )

        state = load_profit_loop_state(self.state_dir)
        self.assertEqual(result["action"], "resolved")
        self.assertEqual(state["resolved_issues"][0]["resolution_branch"], "codex/automation/20260402-1200-truth-lane-live-policy-mismatch")
        self.assertEqual(state["latest_profit_validation"]["resolution_commit"], "abc1234")

    def test_canary_runner_reuses_external_shared_state_across_repeated_runs(self):
        for _ in range(3):
            run_profit_loop_canary(state_dir=self.state_dir, dry_run=True)

        state = load_profit_loop_state(self.state_dir)
        ledger = list_run_ledger_events(self.state_dir)
        self.assertIsNotNone(state["latest_operational_health"])
        self.assertIsNotNone(state["latest_truth_holdout"])
        self.assertIsNotNone(state["latest_profit_validation"])
        self.assertGreaterEqual(len(ledger), 9)
        self.assertTrue(any(item.get("automation_id") == "daily-profit-validation" for item in ledger))


if __name__ == "__main__":
    unittest.main()
