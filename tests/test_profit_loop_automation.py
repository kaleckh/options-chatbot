from __future__ import annotations

import json
import os
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from profit_loop_automation import (
    _load_local_env,
    _proof_context,
    _capture_validation_baseline,
    _shared_replay_matrix_artifact_path,
    _require_daily_truth_refresh,
    _validation_fingerprint,
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
    set_latest_snapshot,
    upsert_open_issue,
)
from workspace_tempdir import WorkspaceTempDir


class ProfitLoopAutomationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = WorkspaceTempDir(prefix="profit-loop-automation")
        self.addCleanup(self._tmp.cleanup)
        self.state_dir = Path(self._tmp.name) / "shared-state"
        self.env = patch.dict(os.environ, {"OPTIONS_DAILY_TRUTH_AUTO_REFRESH": "0"}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        save_profit_loop_state(empty_profit_loop_state(), state_dir=self.state_dir)

    def _healthy_context(self) -> dict[str, object]:
        return dict(_proof_context())

    def _seed_healthy_validation_artifacts(
        self,
        *,
        issue_id: str,
        blocker_class: str,
        proof_commands: list[str],
        proof_dir_name: str = "resolve-proof",
        proof_plan_overrides: dict[str, object] | None = None,
        forward_evidence_status: str = "non_worse",
    ) -> Path:
        context = self._healthy_context()
        now = datetime.now(UTC).replace(microsecond=0)
        health_ran_at = now - timedelta(minutes=30)
        holdout_ran_at = now - timedelta(minutes=15)
        health_iso = health_ran_at.isoformat().replace("+00:00", "Z")
        holdout_iso = holdout_ran_at.isoformat().replace("+00:00", "Z")
        proof_dir = self.state_dir / "runs" / proof_dir_name
        proof_dir.mkdir(parents=True, exist_ok=True)
        proof_plan = {
            "blocker_class": blocker_class,
            "test_tier": "verify:research",
            "modules": ["tests.test_options_api_e2e", "tests.test_expectancy_calibration", "tests.test_wfo_optimizer_calibration"],
            "needs_smoke": True,
            "needs_replay_matrix": False,
            "needs_holdout": blocker_class in {"scan_starvation", "fail_open"},
            "playbook": "broad",
            "truth_lane": "historical_imported_daily",
            "pricing_spec": "targeted",
        }
        if proof_plan_overrides:
            proof_plan.update(proof_plan_overrides)
        baseline = {
            "run_id": "daily-profit-validation-seed",
            "targeted_issue_id": issue_id,
            "commands": [{"command": command, "passed": True, "stdout": "", "stderr": ""} for command in proof_commands],
            "validation_tests_passed": True,
            "validation_test_count": len(proof_commands),
            "smoke_summary": {"scan_truth_lane": "historical_imported_daily"},
            "replay_cases": [],
            "holdout_evidence": {"raw_scan_picks": 1} if proof_plan["needs_holdout"] else None,
            "proof_plan": proof_plan,
            "proof_context": {
                **context,
                "validation_fingerprint": _validation_fingerprint(
                    commit_sha=context["commit_sha"],
                    env_hash=context["env_hash"],
                    truth_lane=str(proof_plan["truth_lane"]),
                    playbook=str(proof_plan["playbook"]),
                    blocker_class=str(proof_plan["blocker_class"]),
                    pricing_spec=str(proof_plan["pricing_spec"]),
                    modules=list(proof_plan["modules"]),
                ),
            },
            "proof_reuse": [],
            "executed_test_modules": list(proof_plan["modules"]),
            "reused_test_modules": [],
        }
        if proof_plan["needs_replay_matrix"]:
            baseline["replay_cases"] = [
                {
                    "lookback_years": 1,
                    "n_picks": 1,
                    "iv_adj": 1.2,
                    "pricing_lane": "mid",
                    "truth_source": "historical_imported_daily",
                    "total_trades": 10,
                    "profit_factor": 1.1,
                    "avg_pnl_pct": 0.4,
                    "directional_accuracy_pct": 55.0,
                    "max_drawdown_pct": -3.1,
                    "selection_source_counts": {"replay_calibrated": 10},
                    "error": None,
                }
            ]
        (proof_dir / "validation_baseline.json").write_text(
            json.dumps(baseline, indent=2, sort_keys=True) + "\n",
            encoding="utf8",
        )
        state = load_profit_loop_state(self.state_dir)
        set_latest_snapshot(
            state,
            key="latest_operational_health",
            payload={
                "run_id": "operational-health-seed",
                "ran_at": health_iso,
                "verdict": "healthy",
                "run_status": "completed",
                "loop_execution_status": "healthy",
                "evidence_status": "trusted",
                "profitability_verdict": "unproven",
                "evidence_complete": True,
                "proof_reuse": [],
                "proof_bundle_dir": str(proof_dir),
                "proof_context": context,
                "commands": ["python scripts/options_algorithm_smoke.py --fixture"],
                "results": {"smoke_summary": {"scan_truth_lane": "historical_imported_daily"}},
            },
            now_iso=health_iso,
        )
        set_latest_snapshot(
            state,
            key="latest_truth_holdout",
            payload={
                "run_id": "truth-holdout-seed",
                "ran_at": holdout_iso,
                "verdict": "recorded",
                "run_status": "completed",
                "loop_execution_status": "healthy",
                "evidence_status": "trusted",
                "profitability_verdict": "unproven",
                "evidence_complete": True,
                "proof_reuse": [],
                "proof_bundle_dir": str(proof_dir),
                "proof_context": context,
                "commands": ["python scripts/record_options_forward_truth.py --json [policy-gated]"],
                "results": {
                    "daily_truth_refresh": {"status": "refreshed"},
                    "forward_summary": {"available": True, "session_count": 1},
                    "policy_fail_closed": False,
                    "policy_gated_scan_picks": 1,
                    "policy_gated_session_id": 1,
                    "promotion_status": "watch",
                    "raw_pass_state": "skipped",
                    "raw_required": False,
                    "raw_scan_picks": 1,
                    "raw_session_id": 1,
                },
            },
            now_iso=holdout_iso,
        )
        set_latest_snapshot(
            state,
            key="latest_profit_validation",
            payload={
                "run_id": "daily-profit-validation-seed",
                "ran_at": "2026-04-02T11:50:00Z",
                "verdict": "deferred",
                "run_status": "completed",
                "loop_execution_status": "healthy",
                "evidence_status": "trusted",
                "profitability_verdict": "unproven",
                "evidence_complete": True,
                "proof_reuse": [],
                "proof_bundle_dir": str(proof_dir),
                "proof_context": context,
                "targeted_issue_id": issue_id,
                "prerequisite_blockers": [],
                "daily_truth_refresh": {"status": "refreshed"},
                "baseline": baseline,
            },
            now_iso="2026-04-02T11:50:00Z",
        )
        save_profit_loop_state(state, state_dir=self.state_dir)
        return proof_dir

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
            "requested_policy_truth_lane": "historical_imported_daily",
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
        self.assertIsNone(state["active_run"])
        self.assertEqual(state["open_issues"][0]["issue_id"], "truth-lane-live-policy-mismatch")

    def test_operational_health_stays_healthy_when_smoke_provenance_aligns(self):
        smoke_payload = {
            "scan_truth_lane": "historical_imported_daily",
            "live_policy_truth_source": "historical_imported_daily",
            "requested_policy_truth_lane": "historical_imported_daily",
            "live_policy_promotion_status": "watch",
            "live_policy_quote_coverage_pct": 97.7,
        }
        smoke_record = {"command": "python scripts/options_algorithm_smoke.py --fixture", "passed": True}
        test_record = {"command": "python -m unittest ...", "passed": True, "stdout": "Ran 9 tests\nOK", "stderr": ""}

        with patch("profit_loop_automation._run_json_command", return_value=(smoke_payload, smoke_record)), \
             patch("profit_loop_automation._run_unittest_modules", return_value=test_record):
            result = run_operational_health(state_dir=self.state_dir)

        state = load_profit_loop_state(self.state_dir)
        self.assertEqual(result["snapshot"]["verdict"], "healthy")
        self.assertEqual(result["snapshot"]["results"]["smoke_live_policy_truth_source"], "historical_imported_daily")
        self.assertEqual(result["snapshot"]["results"]["smoke_requested_policy_truth_lane"], "historical_imported_daily")
        self.assertEqual(state["latest_operational_health"]["verdict"], "healthy")
        self.assertEqual(state["open_issues"], [])

    def test_operational_health_clears_stale_truth_lane_issue_when_provenance_recovers(self):
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
            now_iso="2026-04-02T11:00:00Z",
        )
        save_profit_loop_state(state, state_dir=self.state_dir)
        smoke_payload = {
            "scan_truth_lane": "historical_imported_daily",
            "live_policy_truth_source": "historical_imported_daily",
            "requested_policy_truth_lane": "historical_imported_daily",
            "live_policy_promotion_status": "watch",
            "live_policy_quote_coverage_pct": 97.7,
        }
        smoke_record = {"command": "python scripts/options_algorithm_smoke.py --fixture", "passed": True}
        test_record = {"command": "python -m unittest ...", "passed": True, "stdout": "Ran 9 tests\nOK", "stderr": ""}

        with patch("profit_loop_automation._run_json_command", return_value=(smoke_payload, smoke_record)), \
             patch("profit_loop_automation._run_unittest_modules", return_value=test_record):
            result = run_operational_health(state_dir=self.state_dir)

        state = load_profit_loop_state(self.state_dir)
        self.assertEqual(result["snapshot"]["verdict"], "healthy")
        self.assertEqual(state["open_issues"], [])
        self.assertTrue(any(item["issue_id"] == "truth-lane-live-policy-mismatch" for item in state["resolved_issues"]))

    def test_operational_health_degrades_when_live_policy_truth_source_is_unavailable(self):
        smoke_payload = {
            "scan_truth_lane": "historical_imported_daily",
            "requested_policy_truth_lane": "historical_imported_daily",
            "live_policy_truth_source": None,
            "live_policy_error": "No backtest results found for truth_lane=historical_imported_daily",
            "live_policy_promotion_status": None,
            "live_policy_quote_coverage_pct": None,
        }
        smoke_record = {"command": "python scripts/options_algorithm_smoke.py --fixture", "passed": True}
        test_record = {"command": "python -m unittest ...", "passed": True, "stdout": "Ran 9 tests\nOK", "stderr": ""}

        with patch("profit_loop_automation._run_json_command", return_value=(smoke_payload, smoke_record)), \
             patch("profit_loop_automation._run_unittest_modules", return_value=test_record):
            result = run_operational_health(state_dir=self.state_dir)

        state = load_profit_loop_state(self.state_dir)
        self.assertEqual(result["snapshot"]["verdict"], "degraded-watch")
        self.assertEqual(result["snapshot"]["results"]["smoke_live_policy_error"], smoke_payload["live_policy_error"])
        self.assertEqual(state["open_issues"][0]["issue_id"], "truth-lane-live-policy-mismatch")
        self.assertTrue(any("smoke_live_policy_error=" in item for item in state["open_issues"][0]["evidence"]))

    def test_truth_holdout_records_empty_market_without_opening_issue(self):
        policy_payload = {
            "session_id": 101,
            "scan_picks_count": 0,
            "promotion_status": "block",
            "policy_fail_closed": False,
            "scan_funnel": {
                "raw_candidates": 0,
                "post_policy_visible": 0,
                "post_guardrails_visible": 0,
                "returned_picks": 0,
                "policy_filtered_out": 0,
                "guardrail_filtered_out": 0,
                "final_trimmed": 0,
                "policy_counts": {"approved": 0, "watch": 0, "blocked": 0},
                "guardrail_counts": {"clear": 0, "caution": 0, "blocked": 0},
                "policy_applied": True,
                "policy_fail_closed": False,
                "include_blocked_policy_picks": False,
                "include_blocked_guardrail_picks": False,
            },
        }
        raw_payload = {
            "session_id": 102,
            "scan_picks_count": 0,
            "promotion_status": "block",
            "policy_fail_closed": False,
            "scan_funnel": {
                "raw_candidates": 0,
                "post_policy_visible": 0,
                "post_guardrails_visible": 0,
                "returned_picks": 0,
                "policy_filtered_out": 0,
                "guardrail_filtered_out": 0,
                "final_trimmed": 0,
                "policy_counts": {"approved": 0, "watch": 0, "blocked": 0},
                "guardrail_counts": {"clear": 0, "caution": 0, "blocked": 0},
                "policy_applied": True,
                "policy_fail_closed": False,
                "include_blocked_policy_picks": True,
                "include_blocked_guardrail_picks": True,
            },
        }
        policy_record = {"command": "policy", "passed": True}
        raw_record = {"command": "raw", "passed": True}

        refresh_result = {"status": "refreshed", "commands": []}
        with patch("profit_loop_automation._run_json_command", side_effect=[(policy_payload, policy_record), (raw_payload, raw_record)]), \
             patch("profit_loop_automation.summarize_forward_holdout", return_value={"eligible_event_count": 0, "session_count": 2}):
            result = run_truth_holdout(state_dir=self.state_dir, daily_truth_refresh=refresh_result)

        state = load_profit_loop_state(self.state_dir)
        self.assertEqual(result["snapshot"]["verdict"], "recorded-empty-market")
        self.assertEqual(result["snapshot"]["loop_execution_status"], "healthy")
        self.assertEqual(result["snapshot"]["evidence_status"], "trusted")
        self.assertTrue(result["snapshot"]["evidence_complete"])
        self.assertEqual(result["snapshot"]["results"]["daily_truth_refresh"]["status"], "refreshed")
        self.assertIsNone(result["snapshot"]["results"]["evidence_blocker"])
        self.assertTrue(result["snapshot"]["results"]["empty_market"])
        self.assertEqual(result["snapshot"]["results"]["holdout_funnel"]["policy"]["stage"], "raw_candidates_zero")
        self.assertEqual(result["snapshot"]["results"]["holdout_funnel"]["raw"]["stage"], "raw_candidates_zero")
        self.assertEqual(result["snapshot"]["results"]["candidate_flow_breakdown"]["classification"], "no_candidates_from_scan")
        self.assertEqual(state["latest_truth_holdout"]["results"]["raw_session_id"], 102)
        self.assertFalse(any(item["issue_id"] == "forward-holdout-no-raw-candidates" for item in state["open_issues"]))

    def test_truth_holdout_opens_starvation_issue_when_zero_candidates_reflect_data_or_liquidity_limits(self):
        policy_payload = {
            "session_id": 101,
            "scan_picks_count": 0,
            "promotion_status": "block",
            "policy_fail_closed": False,
            "scan_funnel": {
                "raw_candidates": 0,
                "post_policy_visible": 0,
                "post_guardrails_visible": 0,
                "returned_picks": 0,
                "policy_filtered_out": 0,
                "guardrail_filtered_out": 0,
                "final_trimmed": 0,
                "policy_counts": {"approved": 0, "watch": 0, "blocked": 0},
                "guardrail_counts": {"clear": 0, "caution": 0, "blocked": 0},
                "policy_applied": True,
                "policy_fail_closed": False,
                "include_blocked_policy_picks": False,
                "include_blocked_guardrail_picks": False,
                "drop_counts": {"option_liquidity": 2},
            },
        }
        raw_payload = {
            "session_id": 102,
            "scan_picks_count": 0,
            "promotion_status": "block",
            "policy_fail_closed": False,
            "scan_funnel": {
                "raw_candidates": 0,
                "post_policy_visible": 0,
                "post_guardrails_visible": 0,
                "returned_picks": 0,
                "policy_filtered_out": 0,
                "guardrail_filtered_out": 0,
                "final_trimmed": 0,
                "policy_counts": {"approved": 0, "watch": 0, "blocked": 0},
                "guardrail_counts": {"clear": 0, "caution": 0, "blocked": 0},
                "policy_applied": True,
                "policy_fail_closed": False,
                "include_blocked_policy_picks": True,
                "include_blocked_guardrail_picks": True,
                "drop_counts": {"option_liquidity": 2},
            },
        }
        policy_record = {"command": "policy", "passed": True}
        raw_record = {"command": "raw", "passed": True}

        refresh_result = {"status": "refreshed", "commands": []}
        with patch("profit_loop_automation._run_json_command", side_effect=[(policy_payload, policy_record), (raw_payload, raw_record)]) as run_json_mock, \
             patch("profit_loop_automation.summarize_forward_holdout", return_value={"eligible_event_count": 0, "session_count": 2}):
            result = run_truth_holdout(state_dir=self.state_dir, daily_truth_refresh=refresh_result)

        state = load_profit_loop_state(self.state_dir)
        self.assertEqual(result["snapshot"]["verdict"], "recorded-no-candidates")
        self.assertEqual(result["snapshot"]["loop_execution_status"], "degraded")
        self.assertEqual(result["snapshot"]["evidence_status"], "inconclusive")
        self.assertEqual(result["snapshot"]["results"]["candidate_flow_breakdown"]["classification"], "filtered_by_history_or_liquidity")
        self.assertEqual(result["snapshot"]["results"]["evidence_blocker"], "option_liquidity")
        self.assertEqual(result["snapshot"]["results"]["candidate_flow_breakdown"]["primary_starving_gate"], "option_liquidity")
        raw_command = run_json_mock.call_args_list[1].args[0]
        self.assertNotIn("--record-frozen-cohorts", raw_command)
        self.assertNotIn("--cohort-id", raw_command)
        self.assertEqual(raw_command.count("--watchlist-symbol"), 2)
        self.assertIn("SPY", raw_command)
        self.assertIn("QQQ", raw_command)
        self.assertTrue(any(item["issue_id"] == "forward-holdout-no-raw-candidates" for item in state["open_issues"]))

    def test_truth_holdout_skips_raw_pass_when_policy_scan_is_decisive(self):
        state = load_profit_loop_state(self.state_dir)
        upsert_open_issue(
            state,
            {
                "issue_id": "forward-holdout-no-raw-candidates",
                "source_automation": "daily-truth-holdout",
                "severity": "high",
                "blocker_class": "scan_starvation",
                "summary": "Zero picks",
                "evidence": ["raw_candidates=0"],
                "suggested_fix_targets": ["supervised_scan.py"],
                "status": "open",
            },
            now_iso="2026-04-02T11:00:00Z",
        )
        save_profit_loop_state(state, state_dir=self.state_dir)
        policy_payload = {
            "session_id": 201,
            "scan_picks_count": 1,
            "promotion_status": "watch",
            "policy_fail_closed": False,
            "scan_funnel": {
                "raw_candidates": 1,
                "post_policy_visible": 1,
                "post_guardrails_visible": 1,
                "returned_picks": 1,
                "policy_filtered_out": 0,
                "guardrail_filtered_out": 0,
                "final_trimmed": 0,
                "policy_counts": {"approved": 1, "watch": 0, "blocked": 0},
                "guardrail_counts": {"clear": 1, "caution": 0, "blocked": 0},
                "policy_applied": True,
                "policy_fail_closed": False,
                "include_blocked_policy_picks": False,
                "include_blocked_guardrail_picks": False,
            },
        }
        policy_record = {"command": "policy", "passed": True}
        refresh_result = {"status": "refreshed", "commands": []}
        with patch("profit_loop_automation._run_json_command", return_value=(policy_payload, policy_record)), \
             patch("profit_loop_automation.summarize_forward_holdout", return_value={"eligible_event_count": 1, "session_count": 1}):
            result = run_truth_holdout(state_dir=self.state_dir, daily_truth_refresh=refresh_result)

        state = load_profit_loop_state(self.state_dir)
        self.assertEqual(result["snapshot"]["results"]["raw_pass_state"], "skipped")
        self.assertEqual(result["snapshot"]["results"]["raw_skip_reason"], "policy_decisive")
        self.assertIsNone(result["snapshot"]["results"]["raw_scan_picks"])
        self.assertEqual(result["snapshot"]["results"]["holdout_funnel"]["policy"]["stage"], "candidates_visible")
        self.assertIsNone(result["snapshot"]["results"]["holdout_funnel"]["raw"])
        self.assertEqual(result["snapshot"]["results"]["candidate_flow_breakdown"]["classification"], "recorded")
        self.assertFalse(any(item["issue_id"] == "forward-holdout-no-raw-candidates" for item in state["open_issues"]))
        self.assertTrue(any(item["issue_id"] == "forward-holdout-no-raw-candidates" for item in state["resolved_issues"]))

    def test_truth_holdout_blocks_when_daily_truth_refresh_fails(self):
        refresh_result = {
            "status": "failed",
            "stage": "import",
            "error": "manifest missing",
            "manifest_source": "env",
            "manifest_path": "C:/bad/manifest.json",
            "commands": ["python scripts/import_historical_options_snapshots.py --manifest C:/bad/manifest.json --json"],
        }

        result = run_truth_holdout(state_dir=self.state_dir, daily_truth_refresh=refresh_result)

        state = load_profit_loop_state(self.state_dir)
        self.assertEqual(result["snapshot"]["verdict"], "blocked-daily-truth-refresh")
        self.assertEqual(state["latest_truth_holdout"]["results"]["daily_truth_refresh"]["status"], "failed")
        self.assertIsNone(state["active_run"])
        self.assertTrue(any(item["issue_id"] == "daily-truth-refresh-failed" for item in state["open_issues"]))

    def test_require_daily_truth_refresh_accepts_artifact_refresh_without_new_import(self):
        refresh_result = {"status": "artifact_refreshed", "commands": ["run_historical_backtest ..."]}
        result = _require_daily_truth_refresh(refresh_result=refresh_result)
        self.assertEqual(result["status"], "artifact_refreshed")

    def test_truth_holdout_accepts_artifact_refresh_without_blocking(self):
        policy_payload = {
            "session_id": 301,
            "scan_picks_count": 1,
            "promotion_status": "watch",
            "policy_fail_closed": False,
            "scan_funnel": {
                "raw_candidates": 1,
                "post_policy_visible": 1,
                "post_guardrails_visible": 1,
                "returned_picks": 1,
                "policy_filtered_out": 0,
                "guardrail_filtered_out": 0,
                "final_trimmed": 0,
                "policy_counts": {"approved": 1, "watch": 0, "blocked": 0},
                "guardrail_counts": {"clear": 1, "caution": 0, "blocked": 0},
                "policy_applied": True,
                "policy_fail_closed": False,
                "include_blocked_policy_picks": False,
                "include_blocked_guardrail_picks": False,
            },
        }
        policy_record = {"command": "policy", "passed": True}
        refresh_result = {"status": "artifact_refreshed", "commands": ["run_historical_backtest ..."]}
        with patch("profit_loop_automation._run_json_command", return_value=(policy_payload, policy_record)), \
             patch("profit_loop_automation.summarize_forward_holdout", return_value={"eligible_event_count": 1, "session_count": 1}):
            result = run_truth_holdout(state_dir=self.state_dir, daily_truth_refresh=refresh_result)

        self.assertEqual(result["snapshot"]["verdict"], "recorded")
        self.assertEqual(result["snapshot"]["results"]["daily_truth_refresh"]["status"], "artifact_refreshed")
        self.assertEqual(result["snapshot"]["results"]["raw_pass_state"], "skipped")
        self.assertEqual(result["snapshot"]["results"]["raw_skip_reason"], "policy_decisive")

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
             patch(
                 "profit_loop_automation._capture_validation_baseline",
                 return_value={"validation_tests_passed": True, "validation_test_count": 57, "smoke_summary": {}, "replay_cases": []},
             ):
            result = prepare_profit_validation(state_dir=self.state_dir, auto_defer=False, daily_truth_refresh=refresh_result)

        state = load_profit_loop_state(self.state_dir)
        self.assertEqual(result["action"], "claimed_issue")
        self.assertEqual(result["targeted_issue"]["issue_id"], "truth-lane-live-policy-mismatch")
        self.assertIsNone(state["active_run"])
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
             patch("profit_loop_automation._proof_context", return_value={"commit_sha": "abc", "env_hash": "env", "base_fingerprint": "match", "env_files_loaded": []}):
            result = prepare_profit_validation(state_dir=self.state_dir, auto_defer=False, daily_truth_refresh=refresh_result)

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
             patch(
                 "profit_loop_automation._capture_validation_baseline",
                 return_value={"validation_tests_passed": True, "validation_test_count": 57, "smoke_summary": {}, "replay_cases": []},
             ):
            result = prepare_profit_validation(state_dir=self.state_dir, auto_defer=True, daily_truth_refresh=refresh_result)

        state = load_profit_loop_state(self.state_dir)
        deferred = next(item for item in state["open_issues"] if item["issue_id"] == "replay-matrix-collapsed-results")
        self.assertEqual(result["action"], "deferred")
        self.assertEqual(deferred["status"], "deferred")
        self.assertEqual(deferred["deferred_reason"], "no_safe_fix_plan")
        self.assertTrue(str(deferred["next_action"]).strip())

    def test_capture_validation_baseline_reuses_shared_replay_matrix_cache(self):
        state = load_profit_loop_state(self.state_dir)
        proof_context = {
            "commit_sha": "abc1234",
            "env_hash": "env456",
            "base_fingerprint": "match",
            "env_files_loaded": [],
        }
        proof_plan_modules = ["tests.test_metric_truth_audit", "tests.test_wfo_optimizer_calibration"]
        state["latest_operational_health"] = {
            "ran_at": "2026-04-02T11:30:00Z",
            "verdict": "healthy",
            "loop_execution_status": "healthy",
            "results": {
                "smoke_summary": {"scan_truth_lane": "historical_imported_daily"},
                "unittest_passed": True,
                "executed_test_modules": proof_plan_modules,
            },
            "proof_context": {"base_fingerprint": "match"},
        }
        state["latest_truth_holdout"] = {
            "ran_at": "2026-04-02T11:45:00Z",
            "verdict": "recorded",
            "loop_execution_status": "healthy",
            "results": {"daily_truth_refresh": {"status": "refreshed"}},
        }
        save_profit_loop_state(state, state_dir=self.state_dir)

        replay_fingerprint = _validation_fingerprint(
            commit_sha=proof_context["commit_sha"],
            env_hash=proof_context["env_hash"],
            truth_lane="historical_imported_daily",
            playbook="broad",
            blocker_class="replay_matrix_suspicious",
            pricing_spec="matrix",
            modules=proof_plan_modules,
        )
        replay_cases = [
            {
                "lookback_years": 1,
                "requested_pricing_lane": "mid",
                "effective_pricing_lane": "historical_imported_daily",
                "truth_source": "historical_imported_daily",
                "selection_source_counts": {"bootstrap_heuristic": 70},
                "calibration_summary": {"status": "sparse_calibrated"},
                "total_trades": 70,
                "profit_factor": 0.45,
                "avg_pnl_pct": -21.27,
                "directional_accuracy_pct": 50.0,
                "max_drawdown_pct": 100.0,
                "error": None,
            },
            {
                "lookback_years": 2,
                "requested_pricing_lane": "mid",
                "effective_pricing_lane": "historical_imported_daily",
                "truth_source": "historical_imported_daily",
                "selection_source_counts": {"bootstrap_heuristic": 351, "replay_calibrated": 3},
                "calibration_summary": {"status": "sparse_calibrated"},
                "total_trades": 354,
                "profit_factor": 0.48,
                "avg_pnl_pct": -20.03,
                "directional_accuracy_pct": 41.5,
                "max_drawdown_pct": 100.0,
                "error": None,
            },
            {
                "lookback_years": 1,
                "requested_pricing_lane": "pessimistic",
                "effective_pricing_lane": "historical_imported_daily",
                "truth_source": "historical_imported_daily",
                "selection_source_counts": {"bootstrap_heuristic": 70},
                "calibration_summary": {"status": "sparse_calibrated"},
                "total_trades": 70,
                "profit_factor": 0.45,
                "avg_pnl_pct": -21.27,
                "directional_accuracy_pct": 50.0,
                "max_drawdown_pct": 100.0,
                "error": None,
            },
            {
                "lookback_years": 2,
                "requested_pricing_lane": "pessimistic",
                "effective_pricing_lane": "historical_imported_daily",
                "truth_source": "historical_imported_daily",
                "selection_source_counts": {"bootstrap_heuristic": 351, "replay_calibrated": 3},
                "calibration_summary": {"status": "sparse_calibrated"},
                "total_trades": 354,
                "profit_factor": 0.48,
                "avg_pnl_pct": -20.03,
                "directional_accuracy_pct": 41.5,
                "max_drawdown_pct": 100.0,
                "error": None,
            },
        ]
        shared_cache_path = _shared_replay_matrix_artifact_path(replay_fingerprint, state_dir=self.state_dir)
        shared_cache_path.parent.mkdir(parents=True, exist_ok=True)
        shared_cache_path.write_text(
            json.dumps(
                {
                    "run_id": "seeded-replay",
                    "proof_fingerprint": replay_fingerprint,
                    "replay_cases": replay_cases,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf8",
        )

        issue = {
            "issue_id": "replay-matrix-collapsed-results",
            "blocker_class": "replay_matrix_suspicious",
        }
        with patch("profit_loop_automation._proof_context", return_value=proof_context), \
             patch(
                 "profit_loop_automation._run_proof_modules",
                 return_value={"record": {"command": "", "passed": True, "stdout": "", "stderr": ""}, "passed": True, "count": 0, "module_status": {}},
             ), \
             patch("profit_loop_automation._baseline_replay_matrix", side_effect=AssertionError("shared replay cache should be reused")):
            baseline = _capture_validation_baseline(
                issue=issue,
                state=state,
                run_id="daily-profit-validation-run",
                state_dir=self.state_dir,
                dry_run=False,
            )

        proof_replay_path = self.state_dir / "runs" / "daily-profit-validation-run" / "replay_matrix.json"
        self.assertEqual(baseline["replay_cases"], replay_cases)
        self.assertIn("shared_state.replay_matrix", baseline["proof_reuse"])
        self.assertTrue(proof_replay_path.exists())

    def test_profit_validation_resolve_records_branch_commit_and_proof(self):
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
        proof_dir = self._seed_healthy_validation_artifacts(
            issue_id="truth-lane-live-policy-mismatch",
            blocker_class="truth_lane_mismatch",
            proof_commands=["python -m unittest tests.test_options_api_e2e -v"],
            proof_plan_overrides={
                "needs_holdout": False,
                "needs_replay_matrix": False,
            },
        )

        with patch("profit_loop_automation.validation_prerequisite_blockers", return_value=[]), \
             patch("profit_loop_automation.evaluate_measurement_gate", return_value={"state": "healthy", "blockers": [], "checks": {}}):
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
        self.assertEqual(state["latest_profit_validation"]["measurement_gate"]["state"], "healthy")
        self.assertTrue((proof_dir / "validation_baseline.json").exists())

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

    def test_profit_validation_resolve_rejects_stale_or_blocked_prerequisites(self):
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
        self._seed_healthy_validation_artifacts(
            issue_id="truth-lane-live-policy-mismatch",
            blocker_class="truth_lane_mismatch",
            proof_commands=["python -m unittest tests.test_options_api_e2e -v"],
        )

        blocked_state = load_profit_loop_state(self.state_dir)
        set_latest_snapshot(
            blocked_state,
            key="latest_operational_health",
            payload={
                "run_id": "operational-health-seed",
                "ran_at": "2026-04-02T09:00:00Z",
                "verdict": "blocked",
                "run_status": "completed",
                "loop_execution_status": "blocked",
                "evidence_status": "untrusted",
                "profitability_verdict": "unproven",
                "evidence_complete": False,
                "proof_reuse": [],
                "proof_bundle_dir": str(self.state_dir / "runs" / "resolve-proof"),
                "proof_context": self._healthy_context(),
                "commands": [],
                "results": {},
            },
            now_iso="2026-04-02T09:00:00Z",
        )
        save_profit_loop_state(blocked_state, state_dir=self.state_dir)

        with patch("profit_loop_automation.validation_prerequisite_blockers", return_value=[]):
            try:
                resolve_profit_validation_issue(
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
            except ValueError as exc:
                self.assertIn("operational_health_not_healthy", str(exc))
            else:
                self.fail("Expected resolve_profit_validation_issue to reject stale prerequisites")

    def test_profit_validation_resolve_rejects_missing_proof_artifact(self):
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
        self._seed_healthy_validation_artifacts(
            issue_id="truth-lane-live-policy-mismatch",
            blocker_class="truth_lane_mismatch",
            proof_commands=["python -m unittest tests.test_options_api_e2e -v"],
        )
        proof_dir = self.state_dir / "runs" / "resolve-proof"
        (proof_dir / "validation_baseline.json").unlink()

        with self.assertRaises(ValueError):
            with patch("profit_loop_automation.validation_prerequisite_blockers", return_value=[]):
                resolve_profit_validation_issue(
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

    def test_profit_validation_resolve_does_not_claim_improved_for_sparse_forward_evidence(self):
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
        self._seed_healthy_validation_artifacts(
            issue_id="truth-lane-live-policy-mismatch",
            blocker_class="truth_lane_mismatch",
            proof_commands=["python -m unittest tests.test_options_api_e2e -v"],
        )

        with patch("profit_loop_automation.validation_prerequisite_blockers", return_value=[]), \
             patch("profit_loop_automation.evaluate_measurement_gate", return_value={"state": "healthy", "blockers": [], "checks": {}}):
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
                    "forward_evidence_status": "sparse",
                    "truth_quality_regressed": False,
                    "safety_regressed": False,
                    "material_drawdown_worsened": False,
                },
                state_dir=self.state_dir,
            )

        self.assertEqual(result["snapshot"]["profitability_verdict"], "inconclusive")
        state = load_profit_loop_state(self.state_dir)
        self.assertEqual(state["latest_profit_validation"]["profitability_verdict"], "inconclusive")

    def test_profit_validation_resolve_downgrades_improved_when_measurement_gate_is_unhealthy(self):
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
        self._seed_healthy_validation_artifacts(
            issue_id="truth-lane-live-policy-mismatch",
            blocker_class="truth_lane_mismatch",
            proof_commands=["python -m unittest tests.test_options_api_e2e -v"],
        )

        with patch("profit_loop_automation.validation_prerequisite_blockers", return_value=[]), \
             patch("profit_loop_automation.evaluate_measurement_gate", return_value={"state": "blocked", "blockers": [{"code": "trusted_truth_stale"}], "checks": {}}):
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

        self.assertEqual(result["snapshot"]["profitability_verdict"], "inconclusive")
        self.assertEqual(result["snapshot"]["evidence_status"], "inconclusive")
        self.assertEqual(result["snapshot"]["measurement_gate"]["state"], "blocked")

    def test_canary_runner_reuses_external_shared_state_across_repeated_runs(self):
        refresh_result = {"status": "dry_run", "commands": []}
        with patch("profit_loop_automation._require_daily_truth_refresh", return_value=refresh_result) as refresh_mock:
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
        with patch("profit_loop_automation._require_daily_truth_refresh", return_value=refresh_result):
            result = run_profit_loop_canary(state_dir=self.state_dir, dry_run=False)
        self.assertEqual(result["exit_code"], 2)

    def test_canary_skips_later_steps_when_truth_refresh_times_out(self):
        refresh_result = {
            "status": "failed",
            "stage": "subprocess_timeout",
            "error": "timed out",
            "timed_out": True,
            "commands": ["python profit_loop_automation.py daily-truth-refresh --json"],
        }
        with patch("profit_loop_automation._require_daily_truth_refresh", return_value=refresh_result), \
             patch("profit_loop_automation.run_operational_health") as health_mock, \
             patch("profit_loop_automation.run_truth_holdout") as holdout_mock, \
             patch("profit_loop_automation.prepare_profit_validation") as validation_mock:
            result = run_profit_loop_canary(state_dir=self.state_dir, dry_run=False)

        self.assertEqual(result["exit_code"], 2)
        health_mock.assert_not_called()
        holdout_mock.assert_not_called()
        validation_mock.assert_not_called()

    def test_canary_ignores_non_run_ledger_rows_when_expected_run_ids_are_present(self):
        refresh_result = {"status": "artifact_refreshed", "commands": ["run_historical_backtest ..."]}
        health = {"automation_id": "hourly-operational-health", "snapshot": {"run_id": "health-1", "loop_execution_status": "degraded"}}
        holdout = {"automation_id": "daily-truth-holdout", "snapshot": {"run_id": "holdout-1", "loop_execution_status": "degraded"}}
        validation = {"automation_id": "daily-profit-validation", "snapshot": {"run_id": "validation-1", "loop_execution_status": "healthy"}}
        before_events = [{"automation_id": "seed", "run_id": "seed-1"}]
        after_events = before_events + [
            {"automation_id": "hourly-operational-health", "verdict": "degraded-watch"},
            {"automation_id": "daily-profit-validation", "verdict": "resolved"},
            {"automation_id": "hourly-operational-health", "run_id": "health-1", "verdict": "degraded-watch"},
            {"automation_id": "daily-truth-holdout", "run_id": "holdout-1", "verdict": "recorded-no-candidates"},
            {"automation_id": "daily-profit-validation", "run_id": "validation-1", "verdict": "deferred"},
        ]
        state = load_profit_loop_state(self.state_dir)
        state["latest_operational_health"] = {"run_id": "health-1"}
        state["latest_truth_holdout"] = {"run_id": "holdout-1"}
        state["latest_profit_validation"] = {"run_id": "validation-1"}

        with patch("profit_loop_automation._require_daily_truth_refresh", return_value=refresh_result), \
             patch("profit_loop_automation.run_operational_health", return_value=health), \
             patch("profit_loop_automation.run_truth_holdout", return_value=holdout), \
             patch("profit_loop_automation.prepare_profit_validation", return_value=validation), \
             patch("profit_loop_automation.load_profit_loop_state", return_value=state), \
             patch("profit_loop_automation.list_run_ledger_events", side_effect=[before_events, after_events]):
            result = run_profit_loop_canary(state_dir=self.state_dir, dry_run=False)

        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["consistency"]["new_event_count"], 3)
        self.assertEqual(result["consistency"]["raw_new_event_count"], 5)
        self.assertEqual(
            result["consistency"]["ledger_run_ids"],
            ["health-1", "holdout-1", "validation-1"],
        )


if __name__ == "__main__":
    unittest.main()
