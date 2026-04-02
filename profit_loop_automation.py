from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional


ROOT_DIR = Path(__file__).resolve().parent
for candidate in (ROOT_DIR, ROOT_DIR / "python-backend"):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from forward_options_ledger import summarize_forward_holdout
from profit_loop_shared_state import (
    append_run_ledger,
    claim_issue,
    defer_issue,
    ensure_profit_loop_state,
    load_profit_loop_state,
    prioritized_open_issues,
    resolve_issue,
    save_profit_loop_state,
    set_latest_snapshot,
    shared_state_dir,
    upsert_open_issue,
    utc_now_iso,
    validation_prerequisite_blockers,
)
from wfo_optimizer import IMPORTED_DAILY_TRUTH_SOURCE, run_historical_backtest


HEALTH_TEST_MODULES = [
    "tests.test_market_data_service",
    "tests.test_historical_options_store",
    "tests.test_options_api_e2e",
]
VALIDATION_TEST_MODULES = [
    "tests.test_options_api_e2e",
    "tests.test_market_data_service",
    "tests.test_metric_truth_audit",
    "tests.test_expectancy_calibration",
    "tests.test_wfo_optimizer_calibration",
    "tests.test_autoresearch_cycle",
]
VALIDATION_REPLAY_CASES = [
    {"lookback_years": 1, "n_picks": 1, "iv_adj": 1.2, "pricing_lane": "mid"},
    {"lookback_years": 1, "n_picks": 1, "iv_adj": 1.2, "pricing_lane": "pessimistic"},
    {"lookback_years": 2, "n_picks": 1, "iv_adj": 1.2, "pricing_lane": "mid"},
    {"lookback_years": 2, "n_picks": 1, "iv_adj": 1.2, "pricing_lane": "pessimistic"},
]
VALIDATION_PRIORITY_NEXT_ACTION = {
    "truth-lane-live-policy-mismatch": "Trace live scan policy loading and align live policy truth provenance with the scan truth lane before trusting unattended validation.",
    "forward-holdout-no-raw-candidates": "Trace candidate starvation through run_supervised_scan and live scan filters to explain why both raw and policy-gated holdout runs emitted zero candidates.",
    "replay-matrix-collapsed-results": "Trace run_historical_backtest inputs and replay selection surfaces to explain why the required replay matrix collapsed to identical cells.",
}


class ProfitLoopAutomationError(RuntimeError):
    """Raised when a profit-loop automation step cannot finish safely."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _command_text(command: list[str]) -> str:
    rendered: list[str] = []
    for item in command:
        rendered.append("python" if str(item) == sys.executable else str(item))
    return " ".join(rendered)


def _run_command(command: list[str], *, cwd: Path = ROOT_DIR) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": _command_text(command),
        "returncode": int(completed.returncode),
        "passed": completed.returncode == 0,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _run_json_command(command: list[str], *, cwd: Path = ROOT_DIR) -> tuple[dict[str, Any], dict[str, Any]]:
    record = _run_command(command, cwd=cwd)
    if not record["passed"]:
        raise ProfitLoopAutomationError(
            f"Command failed: {record['command']}\n{record['stderr'] or record['stdout']}"
        )
    try:
        payload = json.loads(record["stdout"])
    except json.JSONDecodeError as exc:
        raise ProfitLoopAutomationError(
            f"Command did not emit valid JSON: {record['command']}"
        ) from exc
    return payload, record


def _run_unittest_modules(modules: list[str], *, cwd: Path = ROOT_DIR) -> dict[str, Any]:
    return _run_command([sys.executable, "-m", "unittest", *modules, "-v"], cwd=cwd)


def _extract_unittest_count(output: str) -> int | None:
    match = re.search(r"Ran\s+(\d+)\s+tests?", str(output or ""))
    return int(match.group(1)) if match else None


def _issue_payload(
    *,
    issue_id: str,
    source_automation: str,
    severity: str,
    blocker_class: str,
    summary: str,
    evidence: list[str],
    suggested_fix_targets: list[str],
) -> dict[str, Any]:
    return {
        "issue_id": issue_id,
        "source_automation": source_automation,
        "severity": severity,
        "blocker_class": blocker_class,
        "summary": summary,
        "evidence": evidence,
        "suggested_fix_targets": suggested_fix_targets,
        "status": "open",
    }


def _baseline_replay_matrix(*, playbook: str = "broad", truth_lane: str = IMPORTED_DAILY_TRUTH_SOURCE) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for case in VALIDATION_REPLAY_CASES:
        output = run_historical_backtest(
            lookback_years=int(case["lookback_years"]),
            n_picks=int(case["n_picks"]),
            iv_adj=float(case["iv_adj"]),
            pricing_lane=str(case["pricing_lane"]),
            playbook=playbook,
            truth_lane=truth_lane,
        )
        results.append(
            {
                **case,
                "truth_source": output.get("truth_source"),
                "total_trades": output.get("total_trades"),
                "profit_factor": output.get("profit_factor"),
                "avg_pnl_pct": output.get("avg_pnl_pct"),
                "directional_accuracy_pct": output.get("directional_accuracy_pct"),
                "max_drawdown_pct": output.get("max_drawdown_pct"),
                "selection_source_counts": dict(output.get("selection_source_counts") or {}),
                "error": output.get("error"),
            }
        )
    return results


def _capture_validation_baseline(*, repo_root: Path = ROOT_DIR, dry_run: bool = False) -> dict[str, Any]:
    if dry_run:
        return {
            "commands": [],
            "validation_tests_passed": True,
            "validation_test_count": 0,
            "smoke_summary": {"mode": "dry_run"},
            "replay_cases": [],
        }
    smoke_payload, smoke_record = _run_json_command(
        [sys.executable, "scripts/options_algorithm_smoke.py", "--fixture"],
        cwd=repo_root,
    )
    test_record = _run_unittest_modules(VALIDATION_TEST_MODULES, cwd=repo_root)
    replay_cases = _baseline_replay_matrix()
    return {
        "commands": [smoke_record, test_record],
        "validation_tests_passed": bool(test_record["passed"]),
        "validation_test_count": _extract_unittest_count(test_record["stdout"]),
        "smoke_summary": smoke_payload,
        "replay_cases": replay_cases,
    }


def run_operational_health(
    *,
    state_dir: str | Path | None = None,
    repo_root: Path = ROOT_DIR,
    dry_run: bool = False,
) -> dict[str, Any]:
    ensure_profit_loop_state(state_dir)
    state = load_profit_loop_state(state_dir)
    now_iso = utc_now_iso()
    issues: list[dict[str, Any]] = []

    if dry_run:
        smoke_payload = {"mode": "dry_run", "scan_truth_lane": IMPORTED_DAILY_TRUTH_SOURCE}
        smoke_record = {"command": "python scripts/options_algorithm_smoke.py --fixture", "passed": True}
        test_record = {"command": "python -m unittest ...", "passed": True, "stdout": "", "stderr": ""}
    else:
        smoke_payload, smoke_record = _run_json_command(
            [sys.executable, "scripts/options_algorithm_smoke.py", "--fixture"],
            cwd=repo_root,
        )
        test_record = _run_unittest_modules(HEALTH_TEST_MODULES, cwd=repo_root)

    verdict = "healthy"
    if not bool(smoke_record.get("passed")) or not bool(test_record.get("passed")):
        verdict = "blocked"
        issues.append(
            _issue_payload(
                issue_id="operational-health-command-failure",
                source_automation="hourly-operational-health",
                severity="high",
                blocker_class="test_gap",
                summary="Operational health evidence commands failed, so unattended validation cannot trust the current system state.",
                evidence=[
                    f"smoke_passed={bool(smoke_record.get('passed'))}",
                    f"unittest_passed={bool(test_record.get('passed'))}",
                ],
                suggested_fix_targets=["scripts/options_algorithm_smoke.py", "scripts/automation_operational_health.py"],
            )
        )
    else:
        smoke_scan_truth_lane = str(smoke_payload.get("scan_truth_lane") or "").strip().lower() or None
        live_policy_truth_source = str(smoke_payload.get("live_policy_truth_source") or "").strip().lower() or None
        if smoke_scan_truth_lane and live_policy_truth_source and smoke_scan_truth_lane != live_policy_truth_source:
            verdict = "degraded-watch"
            issues.append(
                _issue_payload(
                    issue_id="truth-lane-live-policy-mismatch",
                    source_automation="hourly-operational-health",
                    severity="high",
                    blocker_class="truth_lane_mismatch",
                    summary=(
                        "Operational smoke still shows a mismatch between the scan truth lane and the live policy truth source."
                    ),
                    evidence=[
                        f"smoke_scan_truth_lane={smoke_scan_truth_lane}",
                        f"smoke_live_policy_truth_source={live_policy_truth_source}",
                        f"smoke_live_policy_promotion_status={smoke_payload.get('live_policy_promotion_status')}",
                    ],
                    suggested_fix_targets=["options_chatbot.py", "supervised_scan.py", "wfo_optimizer.py"],
                )
            )

    snapshot = {
        "ran_at": now_iso,
        "verdict": verdict,
        "commands": [smoke_record.get("command"), test_record.get("command")],
        "results": {
            "smoke_passed": bool(smoke_record.get("passed")),
            "unittest_passed": bool(test_record.get("passed")),
            "unittest_count": _extract_unittest_count(str(test_record.get("stdout") or "")),
            "smoke_scan_truth_lane": smoke_payload.get("scan_truth_lane"),
            "smoke_live_policy_truth_source": smoke_payload.get("live_policy_truth_source"),
            "smoke_live_policy_promotion_status": smoke_payload.get("live_policy_promotion_status"),
            "smoke_quote_coverage_pct": smoke_payload.get("live_policy_quote_coverage_pct"),
        },
    }
    set_latest_snapshot(state, key="latest_operational_health", payload=snapshot, now_iso=now_iso)
    for issue in issues:
        upsert_open_issue(state, issue, now_iso=now_iso)
    save_profit_loop_state(state, state_dir=state_dir)
    append_run_ledger(
        {
            "automation_id": "hourly-operational-health",
            "ran_at": now_iso,
            "verdict": verdict,
            "issue_ids": [issue["issue_id"] for issue in issues],
        },
        state_dir=state_dir,
    )
    return {
        "automation_id": "hourly-operational-health",
        "state_dir": str(shared_state_dir(state_dir)),
        "snapshot": snapshot,
        "issues": issues,
    }


def run_truth_holdout(
    *,
    state_dir: str | Path | None = None,
    repo_root: Path = ROOT_DIR,
    dry_run: bool = False,
) -> dict[str, Any]:
    ensure_profit_loop_state(state_dir)
    state = load_profit_loop_state(state_dir)
    now = _utc_now()
    now_iso = now.isoformat().replace("+00:00", "Z")
    label_prefix = now.date().isoformat()

    if dry_run:
        policy_payload = {
            "session_id": 0,
            "scan_picks_count": 0,
            "promotion_status": "block",
            "policy_fail_closed": False,
        }
        raw_payload = dict(policy_payload)
        policy_record = {
            "command": "python scripts/record_options_forward_truth.py --json [policy-gated]",
            "passed": True,
        }
        raw_record = {
            "command": "python scripts/record_options_forward_truth.py --json [raw]",
            "passed": True,
        }
        forward_summary = {"available": False, "session_count": 0}
    else:
        policy_payload, policy_record = _run_json_command(
            [
                sys.executable,
                "scripts/record_options_forward_truth.py",
                "--source",
                f"{label_prefix}_policy_gated_broad_holdout",
                "--playbook",
                "broad",
                "--truth-lane",
                IMPORTED_DAILY_TRUTH_SOURCE,
                "--n-picks",
                "1",
                "--use-recommended-policy",
                "--record-frozen-cohorts",
                "--cohort-id",
                "baseline_broad_control",
                "--cohort-id",
                "broad_ev7_momentum070_exit_time33",
                "--json",
            ],
            cwd=repo_root,
        )
        raw_payload, raw_record = _run_json_command(
            [
                sys.executable,
                "scripts/record_options_forward_truth.py",
                "--source",
                f"{label_prefix}_raw_broad_holdout",
                "--playbook",
                "broad",
                "--truth-lane",
                IMPORTED_DAILY_TRUTH_SOURCE,
                "--n-picks",
                "1",
                "--use-recommended-policy",
                "--include-blocked-policy-picks",
                "--include-blocked-guardrail-picks",
                "--record-frozen-cohorts",
                "--cohort-id",
                "baseline_broad_control",
                "--cohort-id",
                "broad_ev7_momentum070_exit_time33",
                "--json",
            ],
            cwd=repo_root,
        )
        forward_summary = summarize_forward_holdout()

    issues: list[dict[str, Any]] = []
    verdict = "recorded"
    if int(raw_payload.get("scan_picks_count") or 0) <= 0 and int(policy_payload.get("scan_picks_count") or 0) <= 0:
        verdict = "recorded-no-candidates"
        issues.append(
            _issue_payload(
                issue_id="forward-holdout-no-raw-candidates",
                source_automation="daily-truth-holdout",
                severity="high",
                blocker_class="scan_starvation",
                summary="Forward holdout recorded successfully but both the policy-gated and raw scans produced zero candidates.",
                evidence=[
                    f"policy_gated_session_id={policy_payload.get('session_id')}",
                    f"raw_session_id={raw_payload.get('session_id')}",
                    f"policy_gated_scan_picks={policy_payload.get('scan_picks_count')}",
                    f"raw_scan_picks={raw_payload.get('scan_picks_count')}",
                    f"promotion_status={raw_payload.get('promotion_status') or policy_payload.get('promotion_status')}",
                    f"policy_fail_closed={raw_payload.get('policy_fail_closed')}",
                ],
                suggested_fix_targets=["supervised_scan.py", "options_chatbot.py", "docs/autoresearch/truth-first-champions.json"],
            )
        )

    snapshot = {
        "ran_at": now_iso,
        "verdict": verdict,
        "commands": [policy_record.get("command"), raw_record.get("command")],
        "results": {
            "policy_gated_session_id": policy_payload.get("session_id"),
            "raw_session_id": raw_payload.get("session_id"),
            "policy_gated_scan_picks": policy_payload.get("scan_picks_count"),
            "raw_scan_picks": raw_payload.get("scan_picks_count"),
            "promotion_status": raw_payload.get("promotion_status") or policy_payload.get("promotion_status"),
            "policy_fail_closed": raw_payload.get("policy_fail_closed"),
            "forward_summary": forward_summary,
        },
    }
    set_latest_snapshot(state, key="latest_truth_holdout", payload=snapshot, now_iso=now_iso)
    for issue in issues:
        upsert_open_issue(state, issue, now_iso=now_iso)
    save_profit_loop_state(state, state_dir=state_dir)
    append_run_ledger(
        {
            "automation_id": "daily-truth-holdout",
            "ran_at": now_iso,
            "verdict": verdict,
            "issue_ids": [issue["issue_id"] for issue in issues],
        },
        state_dir=state_dir,
    )
    return {
        "automation_id": "daily-truth-holdout",
        "state_dir": str(shared_state_dir(state_dir)),
        "snapshot": snapshot,
        "issues": issues,
    }


def _prerequisite_issue(blocker: dict[str, Any]) -> dict[str, Any]:
    code = str(blocker.get("code") or "validation-prerequisite-blocker").strip()
    return _issue_payload(
        issue_id=f"profit-validation-{code}",
        source_automation="daily-profit-validation",
        severity="high",
        blocker_class="storage",
        summary=str(blocker.get("message") or "Profit validation prerequisites are missing or stale."),
        evidence=[f"{key}={value}" for key, value in sorted(dict(blocker).items()) if key != "message"],
        suggested_fix_targets=["profit_loop_shared_state.py", "profit_loop_automation.py", "scripts/automation_profit_validation.py"],
    )


def prepare_profit_validation(
    *,
    state_dir: str | Path | None = None,
    repo_root: Path = ROOT_DIR,
    dry_run: bool = False,
    auto_defer: bool = True,
) -> dict[str, Any]:
    ensure_profit_loop_state(state_dir)
    state = load_profit_loop_state(state_dir)
    now_iso = utc_now_iso()

    blockers = validation_prerequisite_blockers(state)
    if blockers:
        issues = []
        for blocker in blockers:
            issue = _prerequisite_issue(blocker)
            issues.append(issue)
            upsert_open_issue(state, issue, now_iso=now_iso)
        snapshot = {
            "ran_at": now_iso,
            "verdict": "blocked-prerequisites",
            "targeted_issue_id": None,
            "prerequisite_blockers": blockers,
            "baseline": None,
        }
        set_latest_snapshot(state, key="latest_profit_validation", payload=snapshot, now_iso=now_iso)
        save_profit_loop_state(state, state_dir=state_dir)
        append_run_ledger(
            {
                "automation_id": "daily-profit-validation",
                "ran_at": now_iso,
                "verdict": "blocked-prerequisites",
                "issue_ids": [issue["issue_id"] for issue in issues],
            },
            state_dir=state_dir,
        )
        return {
            "automation_id": "daily-profit-validation",
            "action": "blocked_prerequisites",
            "state_dir": str(shared_state_dir(state_dir)),
            "snapshot": snapshot,
            "issues": issues,
        }

    open_issues = prioritized_open_issues(state)
    if not open_issues:
        snapshot = {
            "ran_at": now_iso,
            "verdict": "queue-empty",
            "targeted_issue_id": None,
            "prerequisite_blockers": [],
            "baseline": None,
        }
        set_latest_snapshot(state, key="latest_profit_validation", payload=snapshot, now_iso=now_iso)
        save_profit_loop_state(state, state_dir=state_dir)
        append_run_ledger(
            {
                "automation_id": "daily-profit-validation",
                "ran_at": now_iso,
                "verdict": "queue-empty",
                "issue_ids": [],
            },
            state_dir=state_dir,
        )
        return {
            "automation_id": "daily-profit-validation",
            "action": "queue_empty",
            "state_dir": str(shared_state_dir(state_dir)),
            "snapshot": snapshot,
            "issues": [],
        }

    targeted_issue = claim_issue(
        state,
        open_issues[0]["issue_id"],
        now_iso=now_iso,
        next_action=VALIDATION_PRIORITY_NEXT_ACTION.get(
            open_issues[0]["issue_id"],
            "Investigate the claimed blocker and either land a verified deterministic fix or defer it with exact next steps.",
        ),
    )
    baseline = _capture_validation_baseline(repo_root=repo_root, dry_run=dry_run)
    snapshot = {
        "ran_at": now_iso,
        "verdict": "claimed-issue" if not auto_defer else "deferred",
        "targeted_issue_id": targeted_issue["issue_id"],
        "prerequisite_blockers": [],
        "baseline": baseline,
    }

    result_action = "claimed_issue"
    if auto_defer:
        deferred = defer_issue(
            state,
            targeted_issue["issue_id"],
            deferred_reason="no_safe_fix_plan",
            next_action=VALIDATION_PRIORITY_NEXT_ACTION.get(
                targeted_issue["issue_id"],
                "Investigate the claimed blocker and either land a verified deterministic fix or defer it with exact next steps.",
            ),
            now_iso=now_iso,
        )
        result_action = "deferred"
        snapshot["deferred_issue"] = deferred["issue_id"]

    set_latest_snapshot(state, key="latest_profit_validation", payload=snapshot, now_iso=now_iso)
    save_profit_loop_state(state, state_dir=state_dir)
    append_run_ledger(
        {
            "automation_id": "daily-profit-validation",
            "ran_at": now_iso,
            "verdict": snapshot["verdict"],
            "issue_ids": [targeted_issue["issue_id"]],
        },
        state_dir=state_dir,
    )
    return {
        "automation_id": "daily-profit-validation",
        "action": result_action,
        "state_dir": str(shared_state_dir(state_dir)),
        "snapshot": snapshot,
        "targeted_issue": targeted_issue,
    }


def resolve_profit_validation_issue(
    *,
    issue_id: str,
    resolution_branch: str,
    resolution_commit: str,
    proof_commands: list[str] | None = None,
    state_dir: str | Path | None = None,
) -> dict[str, Any]:
    state = load_profit_loop_state(state_dir)
    now_iso = utc_now_iso()
    resolved = resolve_issue(
        state,
        issue_id,
        resolution_branch=resolution_branch,
        resolution_commit=resolution_commit,
        now_iso=now_iso,
    )
    snapshot = {
        "ran_at": now_iso,
        "verdict": "resolved",
        "targeted_issue_id": issue_id,
        "resolution_branch": resolution_branch,
        "resolution_commit": resolution_commit,
        "proof_commands": list(proof_commands or []),
    }
    set_latest_snapshot(state, key="latest_profit_validation", payload=snapshot, now_iso=now_iso)
    save_profit_loop_state(state, state_dir=state_dir)
    append_run_ledger(
        {
            "automation_id": "daily-profit-validation",
            "ran_at": now_iso,
            "verdict": "resolved",
            "issue_ids": [issue_id],
            "resolution_branch": resolution_branch,
            "resolution_commit": resolution_commit,
        },
        state_dir=state_dir,
    )
    return {
        "automation_id": "daily-profit-validation",
        "action": "resolved",
        "state_dir": str(shared_state_dir(state_dir)),
        "resolved_issue": resolved,
        "snapshot": snapshot,
    }


def defer_profit_validation_issue(
    *,
    issue_id: str,
    deferred_reason: str,
    next_action: str,
    state_dir: str | Path | None = None,
) -> dict[str, Any]:
    state = load_profit_loop_state(state_dir)
    now_iso = utc_now_iso()
    deferred = defer_issue(
        state,
        issue_id,
        deferred_reason=deferred_reason,
        next_action=next_action,
        now_iso=now_iso,
    )
    snapshot = {
        "ran_at": now_iso,
        "verdict": "deferred",
        "targeted_issue_id": issue_id,
        "deferred_reason": deferred_reason,
        "next_action": next_action,
    }
    set_latest_snapshot(state, key="latest_profit_validation", payload=snapshot, now_iso=now_iso)
    save_profit_loop_state(state, state_dir=state_dir)
    append_run_ledger(
        {
            "automation_id": "daily-profit-validation",
            "ran_at": now_iso,
            "verdict": "deferred",
            "issue_ids": [issue_id],
        },
        state_dir=state_dir,
    )
    return {
        "automation_id": "daily-profit-validation",
        "action": "deferred",
        "state_dir": str(shared_state_dir(state_dir)),
        "deferred_issue": deferred,
        "snapshot": snapshot,
    }


def run_profit_loop_canary(
    *,
    state_dir: str | Path | None = None,
    repo_root: Path = ROOT_DIR,
    dry_run: bool = False,
) -> dict[str, Any]:
    health = run_operational_health(state_dir=state_dir, repo_root=repo_root, dry_run=dry_run)
    holdout = run_truth_holdout(state_dir=state_dir, repo_root=repo_root, dry_run=dry_run)
    validation = prepare_profit_validation(
        state_dir=state_dir,
        repo_root=repo_root,
        dry_run=dry_run,
        auto_defer=True,
    )
    return {
        "ran_at": utc_now_iso(),
        "state_dir": str(shared_state_dir(state_dir)),
        "dry_run": bool(dry_run),
        "steps": [health, holdout, validation],
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Shared-state automation drivers for the options profit loop.")
    parser.add_argument(
        "mode",
        choices=[
            "operational-health",
            "truth-holdout",
            "profit-validation",
            "profit-validation-resolve",
            "profit-validation-defer",
            "canary",
        ],
    )
    parser.add_argument("--state-dir", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-code-change", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--issue-id", default=None)
    parser.add_argument("--resolution-branch", default=None)
    parser.add_argument("--resolution-commit", default=None)
    parser.add_argument("--proof-command", action="append", default=[])
    parser.add_argument("--deferred-reason", default=None)
    parser.add_argument("--next-action", default=None)
    args = parser.parse_args(argv)

    if args.mode == "operational-health":
        result = run_operational_health(state_dir=args.state_dir, dry_run=args.dry_run)
    elif args.mode == "truth-holdout":
        result = run_truth_holdout(state_dir=args.state_dir, dry_run=args.dry_run)
    elif args.mode == "profit-validation":
        result = prepare_profit_validation(
            state_dir=args.state_dir,
            dry_run=args.dry_run,
            auto_defer=not bool(args.prepare_only),
        )
    elif args.mode == "profit-validation-resolve":
        if not args.issue_id or not args.resolution_branch or not args.resolution_commit:
            raise SystemExit("--issue-id, --resolution-branch, and --resolution-commit are required")
        result = resolve_profit_validation_issue(
            issue_id=args.issue_id,
            resolution_branch=args.resolution_branch,
            resolution_commit=args.resolution_commit,
            proof_commands=list(args.proof_command or []),
            state_dir=args.state_dir,
        )
    elif args.mode == "profit-validation-defer":
        if not args.issue_id or not args.deferred_reason or not args.next_action:
            raise SystemExit("--issue-id, --deferred-reason, and --next-action are required")
        result = defer_profit_validation_issue(
            issue_id=args.issue_id,
            deferred_reason=args.deferred_reason,
            next_action=args.next_action,
            state_dir=args.state_dir,
        )
    else:
        result = run_profit_loop_canary(state_dir=args.state_dir, dry_run=args.dry_run)

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
