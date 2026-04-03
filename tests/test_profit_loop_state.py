from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from profit_loop_shared_state import (
    append_run_ledger,
    begin_active_run,
    claim_issue,
    clear_active_run,
    complete_active_run,
    defer_issue,
    empty_profit_loop_state,
    ensure_profit_loop_state,
    list_run_ledger_events,
    load_profit_loop_state,
    reconcile_source_open_issues,
    resolve_issue,
    save_profit_loop_state,
    upsert_open_issue,
    validate_profit_loop_state,
    validation_prerequisite_blockers,
)
from workspace_tempdir import WorkspaceTempDir


class ProfitLoopStateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = WorkspaceTempDir(prefix="profit-loop-state")
        self.addCleanup(self._tmp.cleanup)
        self.state_dir = Path(self._tmp.name) / "profit-loop"

    def test_validate_backfills_missing_top_level_keys_for_schema_v2(self):
        normalized = validate_profit_loop_state({"schema_version": 2})
        self.assertEqual(normalized["schema_version"], 2)
        self.assertIsNone(normalized["active_run"])
        self.assertEqual(normalized["open_issues"], [])
        self.assertEqual(normalized["resolved_issues"], [])

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

    def test_validate_schema_v2_payload_backfills_missing_active_run(self):
        normalized = validate_profit_loop_state(
            {
                "schema_version": 2,
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

    def test_validate_normalizes_legacy_degraded_snapshot_evidence_status(self):
        normalized = validate_profit_loop_state(
            {
                "schema_version": 2,
                "updated_at": "2026-04-02T12:00:00Z",
                "latest_operational_health": None,
                "latest_truth_holdout": {
                    "ran_at": "2026-04-02T11:45:00Z",
                    "verdict": "recorded-no-candidates",
                    "loop_execution_status": "degraded",
                    "evidence_status": "degraded",
                    "profitability_verdict": "unproven",
                    "evidence_complete": False,
                    "proof_reuse": [],
                    "results": {"daily_truth_refresh": {"status": "artifact_refreshed"}},
                },
                "latest_profit_validation": None,
                "open_issues": [],
                "resolved_issues": [],
            }
        )
        self.assertEqual(normalized["latest_truth_holdout"]["evidence_status"], "inconclusive")
        self.assertEqual(normalized["latest_truth_holdout"]["loop_execution_status"], "degraded")

    def test_terminal_runs_can_be_cleared_from_live_state(self):
        for status in ("completed", "failed"):
            with self.subTest(status=status):
                state = empty_profit_loop_state()
                begin_active_run(
                    state,
                    automation_id="daily-profit-validation",
                    phase="capture_baseline",
                    commit_sha="abc123",
                    env_hash="env123",
                    proof_bundle_dir=str(self.state_dir / "runs" / f"run-{status}"),
                    run_id=f"run-{status}",
                    now_iso="2026-04-02T12:05:00Z",
                    lease_minutes=30,
                )
                complete_active_run(
                    state,
                    run_id=f"run-{status}",
                    status=status,
                    phase="completed",
                    result_verdict=status,
                    loop_execution_status="healthy" if status == "completed" else "blocked",
                    evidence_status="trusted" if status == "completed" else "untrusted",
                    profitability_verdict="unproven",
                    now_iso="2026-04-02T12:10:00Z",
                )
                cleared = clear_active_run(
                    state,
                    run_id=f"run-{status}",
                    now_iso="2026-04-02T12:10:00Z",
                )
                self.assertEqual(cleared["status"], status)
                save_profit_loop_state(state, state_dir=self.state_dir)
                loaded = load_profit_loop_state(self.state_dir)
                self.assertIsNone(loaded["active_run"])

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

    def test_reconcile_source_open_issues_resolves_absent_blockers(self):
        state = empty_profit_loop_state()
        upsert_open_issue(
            state,
            {
                "issue_id": "truth-lane-live-policy-mismatch",
                "source_automation": "hourly-operational-health",
                "severity": "high",
                "blocker_class": "truth_lane_mismatch",
                "summary": "Mismatch",
                "evidence": ["mismatch"],
                "suggested_fix_targets": ["options_chatbot.py"],
                "status": "open",
            },
            now_iso="2026-04-02T12:00:00Z",
        )
        upsert_open_issue(
            state,
            {
                "issue_id": "forward-holdout-no-raw-candidates",
                "source_automation": "daily-truth-holdout",
                "severity": "high",
                "blocker_class": "scan_starvation",
                "summary": "No candidates",
                "evidence": ["raw_candidates=0"],
                "suggested_fix_targets": ["supervised_scan.py"],
                "status": "open",
            },
            now_iso="2026-04-02T12:05:00Z",
        )

        cleared = reconcile_source_open_issues(
            state,
            source_automation="hourly-operational-health",
            active_issue_ids=[],
            now_iso="2026-04-02T13:00:00Z",
            resolution_note="Healthy again",
        )

        self.assertEqual(len(cleared), 1)
        self.assertEqual(cleared[0]["issue_id"], "truth-lane-live-policy-mismatch")
        self.assertEqual(len(state["open_issues"]), 1)
        self.assertEqual(state["open_issues"][0]["issue_id"], "forward-holdout-no-raw-candidates")
        self.assertEqual(len(state["resolved_issues"]), 1)
        self.assertEqual(state["resolved_issues"][0]["status"], "resolved")
        self.assertEqual(state["resolved_issues"][0]["resolution_kind"], "no_longer_observed")
        self.assertEqual(
            state["resolved_issues"][0]["before_after_comparison"]["resolution_kind"],
            "no_longer_observed",
        )

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
        with self.assertRaises(ValueError):
            resolve_issue(
                state,
                "forward-holdout-no-raw-candidates",
                resolution_branch="codex/automation/20260402-1200-forward-holdout-no-raw-candidates",
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
                now_iso="2026-04-02T12:30:00Z",
            )

        proof_dir = self.state_dir / "runs" / "resolve-proof"
        proof_dir.mkdir(parents=True, exist_ok=True)
        resolved = resolve_issue(
            state,
            "forward-holdout-no-raw-candidates",
            resolution_branch="codex/automation/20260402-1200-forward-holdout-no-raw-candidates",
            resolution_commit="abc1234",
            proof_bundle_dir=str(proof_dir),
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
            now_iso="2026-04-02T12:30:00Z",
        )

        self.assertEqual(len(state["open_issues"]), 0)
        self.assertEqual(len(state["resolved_issues"]), 1)
        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(resolved["resolution_commit"], "abc1234")
        self.assertEqual(resolved["resolution_kind"], "proof_resolved")

    def test_resolve_requires_branch_and_commit(self):
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
        proof_dir = self.state_dir / "runs" / "resolve-proof"
        proof_dir.mkdir(parents=True, exist_ok=True)

        with self.assertRaises(ValueError):
            resolve_issue(
                state,
                "forward-holdout-no-raw-candidates",
                resolution_branch="",
                resolution_commit="abc1234",
                proof_bundle_dir=str(proof_dir),
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
                now_iso="2026-04-02T12:30:00Z",
            )

    def test_resolve_requires_proof_bundle_directory(self):
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
        with self.assertRaises(ValueError):
            resolve_issue(
                state,
                "forward-holdout-no-raw-candidates",
                resolution_branch="codex/automation/20260402-1200-forward-holdout-no-raw-candidates",
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
                now_iso="2026-04-02T12:30:00Z",
            )

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
        self.assertIsNone(loaded["active_run"])
        recovery_events = list_run_ledger_events(self.state_dir)
        self.assertEqual(recovery_events[-1]["verdict"], "recovered-expired-lease")
        self.assertEqual(recovery_events[-1]["run_id"], "run-1")
        self.assertIn("truth-lane-live-policy-mismatch", recovery_events[-1]["reopened_issue_ids"])

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

    def test_validation_prerequisites_block_when_latest_profit_validation_snapshot_is_still_running_without_timestamp(self):
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
        state["latest_profit_validation"] = {
            "run_status": "running",
            "verdict": "claimed-issue",
        }
        blockers = validation_prerequisite_blockers(
            state,
            now=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
        )
        self.assertIn("stale_profit_validation_snapshot", {item["code"] for item in blockers})

    def test_validation_prerequisites_are_empty_when_recent_health_and_holdout_are_healthy(self):
        state = empty_profit_loop_state()
        state["latest_operational_health"] = {
            "ran_at": "2026-04-02T11:30:00Z",
            "verdict": "healthy",
            "loop_execution_status": "healthy",
            "evidence_status": "trusted",
        }
        state["latest_truth_holdout"] = {
            "ran_at": "2026-04-02T11:45:00Z",
            "verdict": "recorded",
            "loop_execution_status": "healthy",
            "evidence_status": "trusted",
            "results": {"daily_truth_refresh": {"status": "refreshed"}},
        }
        blockers = validation_prerequisite_blockers(
            state,
            now=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
        )
        self.assertEqual(blockers, [])

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
