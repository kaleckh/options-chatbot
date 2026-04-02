from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from profit_loop_automation import (
    _load_local_env,
    _require_daily_truth_refresh,
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
        self.env = patch.dict(os.environ, {"OPTIONS_DAILY_TRUTH_AUTO_REFRESH": "0"}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        save_profit_loop_state(empty_profit_loop_state(), state_dir=self.state_dir)

    def test_load_local_env_reads_env_local_without_overwriting_existing_values(self):
        env_root = Path(self._tmp.name) / "env-root"
        env_root.mkdir(parents=True, exist_ok=True)
        (env_root / ".env.local").write_text(
            "DATABASE_URL=postgresql://fresh\nOPTIONS_DAILY_TRUTH_AUTO_REFRESH=1\n",
            encoding="utf8",
        )

        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://existing"}, clear=True):
            loaded = _load_local_env(env_root)
            self.assertEqual(os.environ["DATABASE_URL"], "postgresql://existing")
            self.assertEqual(os.environ["OPTIONS_DAILY_TRUTH_AUTO_REFRESH"], "1")

        self.assertEqual(loaded, [str(env_root / ".env.local")])

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

        refresh_result = {"status": "refreshed", "commands": []}
        with patch("profit_loop_automation._refresh_daily_truth", return_value=refresh_result), \
             patch("profit_loop_automation._run_json_command", side_effect=[(policy_payload, policy_record), (raw_payload, raw_record)]), \
             patch("profit_loop_automation.summarize_forward_holdout", return_value={"eligible_event_count": 0, "session_count": 2}):
            result = run_truth_holdout(state_dir=self.state_dir)

        state = load_profit_loop_state(self.state_dir)
        self.assertEqual(result["snapshot"]["verdict"], "recorded-no-candidates")
        self.assertEqual(result["snapshot"]["results"]["daily_truth_refresh"]["status"], "refreshed")
        self.assertEqual(state["latest_truth_holdout"]["results"]["raw_session_id"], 102)
        self.assertTrue(any(item["issue_id"] == "forward-holdout-no-raw-candidates" for item in state["open_issues"]))

    def test_truth_holdout_skips_raw_pass_when_policy_scan_is_decisive(self):
        policy_payload = {"session_id": 201, "scan_picks_count": 1, "promotion_status": "watch", "policy_fail_closed": False}
        policy_record = {"command": "policy", "passed": True}
        refresh_result = {"status": "refreshed", "commands": []}
        with patch("profit_loop_automation._refresh_daily_truth", return_value=refresh_result), \
             patch("profit_loop_automation._run_json_command", return_value=(policy_payload, policy_record)), \
             patch("profit_loop_automation.summarize_forward_holdout", return_value={"eligible_event_count": 1, "session_count": 1}):
            result = run_truth_holdout(state_dir=self.state_dir)

        self.assertEqual(result["snapshot"]["results"]["raw_pass_state"], "skipped")
        self.assertIsNone(result["snapshot"]["results"]["raw_scan_picks"])

    def test_truth_holdout_blocks_when_daily_truth_refresh_fails(self):
        refresh_result = {
            "status": "failed",
            "stage": "import",
            "error": "manifest missing",
            "manifest_source": "env",
            "manifest_path": "C:/bad/manifest.json",
            "commands": ["python scripts/import_historical_options_snapshots.py --manifest C:/bad/manifest.json --json"],
        }

        with patch("profit_loop_automation._refresh_daily_truth", return_value=refresh_result):
            result = run_truth_holdout(state_dir=self.state_dir)

        state = load_profit_loop_state(self.state_dir)
        self.assertEqual(result["snapshot"]["verdict"], "blocked-daily-truth-refresh")
        self.assertEqual(state["latest_truth_holdout"]["results"]["daily_truth_refresh"]["status"], "failed")
        self.assertTrue(any(item["issue_id"] == "daily-truth-refresh-failed" for item in state["open_issues"]))

    def test_require_daily_truth_refresh_accepts_artifact_refresh_without_new_import(self):
        refresh_result = {"status": "artifact_refreshed", "commands": ["run_historical_backtest ..."]}
        result = _require_daily_truth_refresh(refresh_result=refresh_result)
        self.assertEqual(result["status"], "artifact_refreshed")

    def test_truth_holdout_accepts_artifact_refresh_without_blocking(self):
        policy_payload = {"session_id": 301, "scan_picks_count": 1, "promotion_status": "watch", "policy_fail_closed": False}
        policy_record = {"command": "policy", "passed": True}
        refresh_result = {"status": "artifact_refreshed", "commands": ["run_historical_backtest ..."]}
        with patch("profit_loop_automation._refresh_daily_truth", return_value=refresh_result), \
             patch("profit_loop_automation._run_json_command", return_value=(policy_payload, policy_record)), \
             patch("profit_loop_automation.summarize_forward_holdout", return_value={"eligible_event_count": 1, "session_count": 1}):
            result = run_truth_holdout(state_dir=self.state_dir)

        self.assertEqual(result["snapshot"]["verdict"], "recorded")
        self.assertEqual(result["snapshot"]["results"]["daily_truth_refresh"]["status"], "artifact_refreshed")

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

        refresh_result = {"status": "refreshed", "commands": []}
        with patch("profit_loop_automation.validation_prerequisite_blockers", return_value=[]), \
             patch("profit_loop_automation._refresh_daily_truth", return_value=refresh_result), \
             patch(
                 "profit_loop_automation._capture_validation_baseline",
                 return_value={"validation_tests_passed": True, "validation_test_count": 57, "smoke_summary": {}, "replay_cases": []},
             ):
            result = prepare_profit_validation(state_dir=self.state_dir, auto_defer=False)

        state = load_profit_loop_state(self.state_dir)
        self.assertEqual(result["action"], "claimed_issue")
        self.assertEqual(result["targeted_issue"]["issue_id"], "truth-lane-live-policy-mismatch")
        self.assertEqual(state["latest_profit_validation"]["targeted_issue_id"], "truth-lane-live-policy-mismatch")

    def test_profit_validation_reuses_smoke_from_recent_operational_health(self):
        state = load_profit_loop_state(self.state_dir)
        state["latest_operational_health"] = {
            "ran_at": "2026-04-02T11:30:00Z",
            "verdict": "healthy",
            "loop_execution_status": "healthy",
            "results": {
                "smoke_summary": {"scan_truth_lane": "historical_imported_daily"},
                "unittest_passed": True,
                "executed_test_modules": ["tests.test_options_api_e2e"],
            },
            "proof_context": {"base_fingerprint": "match"},
        }
        state["latest_truth_holdout"] = {
            "ran_at": "2026-04-02T11:45:00Z",
            "verdict": "recorded",
            "loop_execution_status": "healthy",
            "results": {"daily_truth_refresh": {"status": "refreshed"}},
        }
        upsert_open_issue(
            state,
            {
                "issue_id": "forward-holdout-no-raw-candidates",
                "source_automation": "daily-truth-holdout",
                "severity": "high",
                "blocker_class": "scan_starvation",
                "summary": "Zero picks",
                "evidence": ["raw_scan_picks=0"],
                "suggested_fix_targets": ["supervised_scan.py"],
                "status": "open",
            },
            now_iso="2026-04-02T11:50:00Z",
        )
        save_profit_loop_state(state, state_dir=self.state_dir)

        refresh_result = {"status": "refreshed", "commands": []}
        with patch("profit_loop_automation.validation_prerequisite_blockers", return_value=[]), \
             patch("profit_loop_automation._refresh_daily_truth", return_value=refresh_result), \
             patch("profit_loop_automation._proof_context", return_value={"commit_sha": "abc", "env_hash": "env", "base_fingerprint": "match", "env_files_loaded": []}):
            result = prepare_profit_validation(state_dir=self.state_dir, auto_defer=False)

        baseline = result["snapshot"]["baseline"]
        self.assertIn("latest_operational_health.smoke", baseline["proof_reuse"])
        self.assertIn("latest_operational_health.tests", baseline["proof_reuse"])

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

        refresh_result = {"status": "refreshed", "commands": []}
        with patch("profit_loop_automation.validation_prerequisite_blockers", return_value=[]), \
             patch("profit_loop_automation._refresh_daily_truth", return_value=refresh_result), \
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
            before_after_comparison={
                "comparison_spec": {
                    "playbook": "broad",
                    "truth_lane": "historical_imported_daily",
                    "pricing_lane": "mid",
                    "lookback_years": 1,
                    "n_picks": 1,
                    "iv_adj": 1.2,
                },
                "baseline": {"profit_factor": 0.8, "avg_pnl_pct": -1.0},
                "after": {"profit_factor": 0.9, "avg_pnl_pct": -0.5},
                "forward_evidence_status": "non_worse",
                "truth_quality_regressed": False,
                "safety_regressed": False,
                "material_drawdown_worsened": False,
            },
            state_dir=self.state_dir,
        )

        state = load_profit_loop_state(self.state_dir)
        self.assertEqual(result["action"], "resolved")
        self.assertEqual(state["resolved_issues"][0]["resolution_branch"], "codex/automation/20260402-1200-truth-lane-live-policy-mismatch")
        self.assertEqual(state["latest_profit_validation"]["resolution_commit"], "abc1234")
        self.assertEqual(state["latest_profit_validation"]["profitability_verdict"], "improved")

    def test_profit_validation_resolve_requires_before_after_comparison(self):
        state = load_profit_loop_state(self.state_dir)
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
        with self.assertRaises(ValueError):
            resolve_profit_validation_issue(
                issue_id="truth-lane-live-policy-mismatch",
                resolution_branch="codex/automation/20260402-1200-truth-lane-live-policy-mismatch",
                resolution_commit="abc1234",
                proof_commands=["python -m unittest tests.test_options_api_e2e -v"],
                state_dir=self.state_dir,
            )

    def test_canary_runner_reuses_external_shared_state_across_repeated_runs(self):
        refresh_result = {"status": "dry_run", "commands": []}
        with patch("profit_loop_automation._refresh_daily_truth", return_value=refresh_result) as refresh_mock:
            for _ in range(3):
                run_profit_loop_canary(state_dir=self.state_dir, dry_run=True)

        state = load_profit_loop_state(self.state_dir)
        ledger = list_run_ledger_events(self.state_dir)
        self.assertIsNotNone(state["latest_operational_health"])
        self.assertIsNotNone(state["latest_truth_holdout"])
        self.assertIsNotNone(state["latest_profit_validation"])
        self.assertGreaterEqual(len(ledger), 9)
        self.assertEqual(refresh_mock.call_count, 3)
        self.assertTrue(any(item.get("automation_id") == "daily-profit-validation" for item in ledger))

    def test_canary_returns_exit_code_two_when_truth_holdout_blocks(self):
        refresh_result = {
            "status": "failed",
            "stage": "import",
            "error": "manifest missing",
            "manifest_source": "env",
            "manifest_path": "C:/bad/manifest.json",
            "commands": ["python scripts/import_historical_options_snapshots.py --manifest C:/bad/manifest.json --json"],
        }
        with patch("profit_loop_automation._refresh_daily_truth", return_value=refresh_result):
            result = run_profit_loop_canary(state_dir=self.state_dir, dry_run=False)
        self.assertEqual(result["exit_code"], 2)


if __name__ == "__main__":
    unittest.main()
