from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_volatility_expansion_forward_paper_shadow_report as forward_report


REPORT_ID = "regular_options_strict_forward_30_completion_monitor"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-strict-forward-30-completion-monitor.md"
DEFAULT_COLLECTOR_LATEST = DEFAULT_OUTPUT_DIR / "regular_options_strict_forward_30_market_window_collector_latest.json"
DEFAULT_CANDIDATE_REVIEW_LATEST = DEFAULT_OUTPUT_DIR / "regular_options_strict_forward_30_candidate_review_packet_latest.json"
DEFAULT_SCHEDULER_HEALTH_LATEST = DEFAULT_OUTPUT_DIR / "regular_options_strict_forward_30_scheduler_health_latest.json"
DEFAULT_SCAN_TASK_HEALTH_LATEST = DEFAULT_OUTPUT_DIR / "regular_options_strict_forward_scan_task_health_latest.json"
DEFAULT_EXIT_EVIDENCE_PLAN_LATEST = DEFAULT_OUTPUT_DIR / "regular_options_strict_forward_30_exit_evidence_plan_latest.json"
DEFAULT_EXIT_COMPLETION_STAGER_LATEST = DEFAULT_OUTPUT_DIR / "regular_options_strict_forward_30_exit_completion_stager_latest.json"
DEFAULT_LIFECYCLE_AUDIT_LATEST = DEFAULT_OUTPUT_DIR / "regular_options_strict_forward_30_lifecycle_audit_latest.json"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _parse_utc_iso(value: Any) -> datetime | None:
    text = _norm(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"_source_status": "missing", "_source_path": _rel(path)}
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        return {"_source_status": "malformed", "_source_path": _rel(path), "_error": f"JSONDecodeError:{exc.lineno}:{exc.colno}"}
    if not isinstance(payload, dict):
        return {"_source_status": "invalid", "_source_path": _rel(path), "_error": "json_root_not_object"}
    payload["_source_status"] = "loaded"
    payload["_source_path"] = _rel(path)
    return payload


def _default_aux_path(collector_latest_path: Path, default_path: Path) -> Path:
    if collector_latest_path == DEFAULT_COLLECTOR_LATEST:
        return default_path
    return collector_latest_path.parent / default_path.name


def _safety_violations(*payloads: dict[str, Any]) -> list[str]:
    keys = {
        "live_entry_allowed",
        "auto_track_allowed",
        "broker_order_allowed",
        "promotion_ready",
        "quotes_imported",
        "imported_quotes",
        "proof_bars_changed",
        "changed_proof_bars",
        "historical_rows_are_forward_proof",
    }
    violations: list[str] = []
    for index, payload in enumerate(payloads, start=1):
        for key in sorted(keys):
            if payload.get(key) is True:
                violations.append(f"payload_{index}:{key}")
    return violations


def _accepted_profitability(report: dict[str, Any]) -> bool:
    gates = _as_dict(report.get("gates"))
    acceptance = _as_dict(report.get("acceptance_readiness"))
    return bool(
        gates.get("minimum_continuation_gate_passed")
        and acceptance.get("positive_net_usd_pnl")
        and not _as_list(report.get("hard_fail_states"))
    )


def _dependency_freshness(
    *,
    collector: dict[str, Any],
    candidate_review: dict[str, Any],
    scheduler: dict[str, Any],
    scan_task_health: dict[str, Any],
    exit_evidence_plan: dict[str, Any],
    exit_stager: dict[str, Any],
    lifecycle: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    collector_generated_at = _norm(collector.get("generated_at_utc"))
    candidate_review_generated_at = _norm(candidate_review.get("generated_at_utc"))
    scheduler_generated_at = _norm(scheduler.get("generated_at_utc"))
    scan_task_health_generated_at = _norm(scan_task_health.get("generated_at_utc"))
    exit_evidence_plan_generated_at = _norm(exit_evidence_plan.get("generated_at_utc"))
    exit_stager_generated_at = _norm(exit_stager.get("generated_at_utc"))
    lifecycle_generated_at = _norm(lifecycle.get("generated_at_utc"))
    collector_ts = _parse_utc_iso(collector_generated_at)
    candidate_review_ts = _parse_utc_iso(candidate_review_generated_at)
    scheduler_ts = _parse_utc_iso(scheduler_generated_at)
    scan_task_health_ts = _parse_utc_iso(scan_task_health_generated_at)
    exit_evidence_plan_ts = _parse_utc_iso(exit_evidence_plan_generated_at)
    exit_stager_ts = _parse_utc_iso(exit_stager_generated_at)
    lifecycle_ts = _parse_utc_iso(lifecycle_generated_at)

    for name, payload, timestamp in (
        ("collector", collector, collector_ts),
        ("candidate_review", candidate_review, candidate_review_ts),
        ("scheduler_health", scheduler, scheduler_ts),
        ("scan_task_health", scan_task_health, scan_task_health_ts),
        ("exit_evidence_plan", exit_evidence_plan, exit_evidence_plan_ts),
        ("exit_completion_stager", exit_stager, exit_stager_ts),
        ("lifecycle_audit", lifecycle, lifecycle_ts),
    ):
        if payload.get("_source_status") != "loaded":
            blockers.append(f"{name}_source_not_loaded")
        elif timestamp is None:
            blockers.append(f"{name}_generated_at_missing_or_malformed")

    if collector_ts is not None and candidate_review_ts is not None and candidate_review_ts < collector_ts:
        blockers.append("candidate_review_older_than_collector")
    if collector_ts is not None and scheduler_ts is not None and scheduler_ts < collector_ts:
        blockers.append("scheduler_health_older_than_collector")
    if collector_ts is not None and scan_task_health_ts is not None and scan_task_health_ts < collector_ts:
        blockers.append("scan_task_health_older_than_collector")
    if collector_ts is not None and exit_evidence_plan_ts is not None and exit_evidence_plan_ts < collector_ts:
        blockers.append("exit_evidence_plan_older_than_collector")
    if collector_ts is not None and exit_stager_ts is not None and exit_stager_ts < collector_ts:
        blockers.append("exit_completion_stager_older_than_collector")
    if collector_ts is not None and lifecycle_ts is not None and lifecycle_ts < collector_ts:
        blockers.append("lifecycle_audit_older_than_collector")

    review_freshness = _as_dict(candidate_review.get("scheduler_health_freshness"))
    if review_freshness and not review_freshness.get("fresh"):
        blockers.append(f"candidate_review_scheduler_freshness:{_norm(review_freshness.get('status')) or 'not_fresh'}")
    capture_freshness = _as_dict(candidate_review.get("capture_freshness"))
    if capture_freshness and not capture_freshness.get("fresh"):
        blockers.append(f"candidate_review_capture_freshness:{_norm(capture_freshness.get('status')) or 'not_fresh'}")
    if scan_task_health.get("_source_status") == "loaded" and scan_task_health.get("status") != "scan_tasks_ready_for_next_market_window":
        blockers.append(f"scan_task_health_not_ready:{_norm(scan_task_health.get('status')) or 'unknown'}")

    return {
        "fresh": not blockers,
        "status": "completion_monitor_dependencies_fresh" if not blockers else "completion_monitor_dependencies_stale_or_missing",
        "blockers": blockers,
        "collector_generated_at_utc": collector_generated_at or None,
        "candidate_review_generated_at_utc": candidate_review_generated_at or None,
        "scheduler_generated_at_utc": scheduler_generated_at or None,
        "scan_task_health_generated_at_utc": scan_task_health_generated_at or None,
        "exit_evidence_plan_generated_at_utc": exit_evidence_plan_generated_at or None,
        "exit_completion_stager_generated_at_utc": exit_stager_generated_at or None,
        "lifecycle_audit_generated_at_utc": lifecycle_generated_at or None,
        "candidate_review_scheduler_freshness": review_freshness or None,
        "candidate_review_capture_freshness": capture_freshness or None,
    }


def _status_for(
    *,
    strict_rows: int,
    required_rows: int,
    accepted_profitability: bool,
    cohort_state: str,
    counts: dict[str, Any],
    scheduler: dict[str, Any],
    candidate_review: dict[str, Any],
    scan_task_health: dict[str, Any],
    dependency_freshness: dict[str, Any],
    safety_violations: list[str],
) -> str:
    if safety_violations:
        return "completion_monitor_safety_blocked"
    if not dependency_freshness.get("fresh"):
        return "completion_monitor_dependency_freshness_blocked"
    if strict_rows >= required_rows and accepted_profitability:
        return "completion_monitor_goal_complete"
    if scheduler.get("_source_status") == "loaded" and scheduler.get("status") != "scheduler_ready_for_next_market_window":
        return "completion_monitor_scheduler_blocked"
    if candidate_review.get("_source_status") == "loaded" and candidate_review.get("status") == "candidate_review_required_append_allowed_no_append_performed":
        return "completion_monitor_candidate_review_required"
    if cohort_state in {"cohort_log_missing_blocker", "cohort_log_malformed_blocker", "initialized_empty_zero_of_gate"}:
        return "completion_monitor_waiting_for_first_cohort_row"
    if _int(counts.get("open_waiting_policy_exit_count")) > 0:
        return "completion_monitor_waiting_for_exact_exits"
    if strict_rows < required_rows:
        return "completion_monitor_waiting_for_additional_strict_rows"
    return "completion_monitor_waiting_for_profitable_acceptance"


def build_report(
    *,
    cohort_log_path: Path = forward_report.DEFAULT_PHASE2_COHORT_LOG,
    schema_path: Path = forward_report.DEFAULT_PHASE2_SCHEMA,
    collector_latest_path: Path = DEFAULT_COLLECTOR_LATEST,
    candidate_review_latest_path: Path = DEFAULT_CANDIDATE_REVIEW_LATEST,
    scheduler_health_latest_path: Path = DEFAULT_SCHEDULER_HEALTH_LATEST,
    scan_task_health_latest_path: Path | None = None,
    exit_evidence_plan_latest_path: Path | None = None,
    exit_completion_stager_latest_path: Path | None = None,
    lifecycle_audit_latest_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    scan_task_health_latest_path = scan_task_health_latest_path or _default_aux_path(collector_latest_path, DEFAULT_SCAN_TASK_HEALTH_LATEST)
    exit_evidence_plan_latest_path = exit_evidence_plan_latest_path or _default_aux_path(collector_latest_path, DEFAULT_EXIT_EVIDENCE_PLAN_LATEST)
    exit_completion_stager_latest_path = exit_completion_stager_latest_path or _default_aux_path(collector_latest_path, DEFAULT_EXIT_COMPLETION_STAGER_LATEST)
    lifecycle_audit_latest_path = lifecycle_audit_latest_path or _default_aux_path(collector_latest_path, DEFAULT_LIFECYCLE_AUDIT_LATEST)
    phase2_report = forward_report.build_report(
        cohort_log_path=cohort_log_path,
        schema_path=schema_path,
        allowed_lane_ids=forward_report.PHASE2_FROZEN_LANE_IDS,
        generated_at_utc=generated_at,
    )
    collector = _load_json(collector_latest_path)
    candidate_review = _load_json(candidate_review_latest_path)
    scheduler = _load_json(scheduler_health_latest_path)
    scan_task_health = _load_json(scan_task_health_latest_path)
    exit_evidence_plan = _load_json(exit_evidence_plan_latest_path)
    exit_stager = _load_json(exit_completion_stager_latest_path)
    lifecycle = _load_json(lifecycle_audit_latest_path)
    acceptance = _as_dict(phase2_report.get("acceptance_readiness"))
    counts = _as_dict(phase2_report.get("counts"))
    strict_rows = _int(acceptance.get("post_freeze_strict_exact_completed_rows"))
    required_rows = _int(acceptance.get("minimum_required"), forward_report.MIN_COMPLETED_ROWS_FOR_REVIEW)
    accepted_profitability = _accepted_profitability(phase2_report)
    safety_violations = _safety_violations(phase2_report, collector, candidate_review, scheduler, exit_evidence_plan, exit_stager, lifecycle, scan_task_health)
    dependency_freshness = _dependency_freshness(
        collector=collector,
        candidate_review=candidate_review,
        scheduler=scheduler,
        scan_task_health=scan_task_health,
        exit_evidence_plan=exit_evidence_plan,
        exit_stager=exit_stager,
        lifecycle=lifecycle,
    )
    status = _status_for(
        strict_rows=strict_rows,
        required_rows=required_rows,
        accepted_profitability=accepted_profitability,
        cohort_state=_norm(phase2_report.get("cohort_log_state")),
        counts=counts,
        scheduler=scheduler,
        candidate_review=candidate_review,
        scan_task_health=scan_task_health,
        dependency_freshness=dependency_freshness,
        safety_violations=safety_violations,
    )
    return {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "status": status,
        "strict_forward_rows": strict_rows,
        "required_rows": required_rows,
        "remaining_rows": max(required_rows - strict_rows, 0),
        "accepted_profitability": accepted_profitability,
        "cohort_log_state": phase2_report.get("cohort_log_state"),
        "phase2_overall_status": phase2_report.get("overall_status"),
        "open_waiting_policy_exit_count": _int(counts.get("open_waiting_policy_exit_count")),
        "exact_completed_forward_pnl_count": _int(counts.get("exact_completed_forward_pnl_count")),
        "exact_entry_captured_count": _int(counts.get("exact_entry_captured_count")),
        "total_natural_selections": _int(counts.get("total_natural_selections")),
        "strict_profit_factor_usd": acceptance.get("strict_profit_factor_usd"),
        "bootstrap_pf_lower_bound_5pct_usd": acceptance.get("bootstrap_pf_lower_bound_5pct_usd"),
        "stressed_pf_lower_bound": phase2_report.get("stressed_pf_lower_bound"),
        "hard_fail_states": phase2_report.get("hard_fail_states") if isinstance(phase2_report.get("hard_fail_states"), list) else [],
        "warning_states": phase2_report.get("warning_states") if isinstance(phase2_report.get("warning_states"), list) else [],
        "strict_reject_counts": phase2_report.get("strict_reject_counts") if isinstance(phase2_report.get("strict_reject_counts"), dict) else {},
        "collector_status": collector.get("status"),
        "collector_source_status": collector.get("_source_status"),
        "candidate_review_status": candidate_review.get("status"),
        "candidate_review_source_status": candidate_review.get("_source_status"),
        "scheduler_status": scheduler.get("status"),
        "scheduler_source_status": scheduler.get("_source_status"),
        "scan_task_health_status": scan_task_health.get("status"),
        "scan_task_health_source_status": scan_task_health.get("_source_status"),
        "exit_evidence_plan_status": exit_evidence_plan.get("status"),
        "exit_evidence_plan_source_status": exit_evidence_plan.get("_source_status"),
        "exit_completion_stager_status": exit_stager.get("status"),
        "exit_completion_stager_source_status": exit_stager.get("_source_status"),
        "lifecycle_audit_status": lifecycle.get("status"),
        "lifecycle_audit_source_status": lifecycle.get("_source_status"),
        "dependency_freshness": dependency_freshness,
        "scheduler_blockers": scheduler.get("blockers") if isinstance(scheduler.get("blockers"), list) else [],
        "dependency_blockers": dependency_freshness.get("blockers") if isinstance(dependency_freshness.get("blockers"), list) else [],
        "safety_violations": safety_violations,
        "operator_commands": {
            "refresh_completion_monitor": "npm run options:goal-loop:strict-forward-30-completion-monitor -- --json",
            "refresh_scheduler_health": "npm run options:goal-loop:strict-forward-30-scheduler-health -- --json",
            "refresh_scan_task_health": "npm run options:goal-loop:strict-forward-scan-task-health -- --json",
            "refresh_collector_status": "npm run options:goal-loop:strict-forward-30-auto-window -- --json",
            "review_candidate_handoff": "npm run options:goal-loop:strict-forward-30-candidate-review -- --json",
            "refresh_exit_evidence_plan": "npm run options:goal-loop:strict-forward-30-exit-evidence-plan -- --json",
            "refresh_exit_completion_stager": "npm run options:goal-loop:strict-forward-30-exit-completion-stager -- --json",
            "refresh_lifecycle_audit": "npm run options:goal-loop:strict-forward-30-lifecycle-audit -- --json",
        },
        "prohibited_actions": [
            "do_not_append_from_completion_monitor",
            "do_not_enable_live_validation_from_completion_monitor",
            "do_not_enable_auto_track_from_completion_monitor",
            "do_not_submit_broker_orders_from_completion_monitor",
            "do_not_import_quotes_from_completion_monitor",
            "do_not_lower_proof_bars_from_completion_monitor",
            "do_not_treat_historical_rows_as_forward_proof",
        ],
        "source_artifacts": {
            "phase2_report": {
                "source": "computed_inline",
                "path": None,
                "status": phase2_report.get("overall_status"),
                "report_id": phase2_report.get("report_id"),
                "generated_at_utc": phase2_report.get("generated_at_utc"),
                "proposed_report_path": _rel(forward_report.PROPOSED_PHASE2_REPORT_PATH),
                "proposed_report_exists": forward_report.PROPOSED_PHASE2_REPORT_PATH.exists(),
            },
            "cohort_log": {"path": _rel(cohort_log_path), "state": phase2_report.get("cohort_log_state")},
            "collector_latest": {"path": _rel(collector_latest_path), "status": collector.get("_source_status"), "report_status": collector.get("status")},
            "candidate_review_latest": {"path": _rel(candidate_review_latest_path), "status": candidate_review.get("_source_status"), "report_status": candidate_review.get("status")},
            "scheduler_health_latest": {"path": _rel(scheduler_health_latest_path), "status": scheduler.get("_source_status"), "report_status": scheduler.get("status")},
            "scan_task_health_latest": {"path": _rel(scan_task_health_latest_path), "status": scan_task_health.get("_source_status"), "report_status": scan_task_health.get("status")},
            "exit_evidence_plan_latest": {"path": _rel(exit_evidence_plan_latest_path), "status": exit_evidence_plan.get("_source_status"), "report_status": exit_evidence_plan.get("status")},
            "exit_completion_stager_latest": {"path": _rel(exit_completion_stager_latest_path), "status": exit_stager.get("_source_status"), "report_status": exit_stager.get("status")},
            "lifecycle_audit_latest": {"path": _rel(lifecycle_audit_latest_path), "status": lifecycle.get("_source_status"), "report_status": lifecycle.get("status")},
        },
        "phase2_forward_report": phase2_report,
        "artifacts": {},
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Strict Forward 30 Completion Monitor",
        "",
        f"Status: `{report.get('status')}`.",
        "",
        f"- Strict completed forward rows: `{report.get('strict_forward_rows')}/{report.get('required_rows')}`.",
        f"- Remaining rows: `{report.get('remaining_rows')}`.",
        f"- Accepted profitability: `{str(bool(report.get('accepted_profitability'))).lower()}`.",
        f"- Cohort log state: `{report.get('cohort_log_state')}`.",
        f"- Open rows waiting for policy exit: `{report.get('open_waiting_policy_exit_count')}`.",
        f"- Exact completed forward P&L rows: `{report.get('exact_completed_forward_pnl_count')}`.",
        f"- Scheduler status: `{report.get('scheduler_status')}`.",
        f"- Scan-task health status: `{report.get('scan_task_health_status')}`.",
        f"- Candidate review status: `{report.get('candidate_review_status')}`.",
        f"- Collector status: `{report.get('collector_status')}`.",
        f"- Exit-evidence plan status: `{report.get('exit_evidence_plan_status')}`.",
        f"- Exit-completion stager status: `{report.get('exit_completion_stager_status')}`.",
        f"- Lifecycle audit status: `{report.get('lifecycle_audit_status')}`.",
        f"- Dependency freshness: `{_as_dict(report.get('dependency_freshness')).get('status')}`.",
        "",
        "This monitor is read-only. It recomputes the strict-forward 30 completion count from the Phase 2 cohort report and does not append rows, enable live validation, enable auto-track, submit broker orders, import quotes, lower proof bars, or count historical rows as forward proof.",
        "",
    ]
    blockers = report.get("safety_violations") if isinstance(report.get("safety_violations"), list) else []
    if blockers:
        lines.extend(["## Safety Violations", ""])
        lines.extend(f"- `{item}`" for item in blockers)
        lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = _norm(report.get("generated_at_utc")).replace("-", "").replace(":", "")
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_json = output_dir / f"{REPORT_ID}_latest.json"
    latest_md = output_dir / f"{REPORT_ID}_latest.md"
    artifacts = {
        "json": _rel(json_path),
        "latest_json": _rel(latest_json),
        "markdown": _rel(md_path),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
    }
    payload = dict(report)
    payload["artifacts"] = artifacts
    text = render_markdown(payload)
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    json_path.write_text(serialized, encoding="utf8")
    latest_json.write_text(serialized, encoding="utf8")
    md_path.write_text(text, encoding="utf8")
    latest_md.write_text(text, encoding="utf8")
    docs_report.write_text(text, encoding="utf8")
    return artifacts


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build read-only completion monitor for the strict-forward 30-row goal.")
    parser.add_argument("--cohort-log", type=Path, default=forward_report.DEFAULT_PHASE2_COHORT_LOG)
    parser.add_argument("--schema", type=Path, default=forward_report.DEFAULT_PHASE2_SCHEMA)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_report(cohort_log_path=args.cohort_log, schema_path=args.schema)
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0 if report["status"] != "completion_monitor_safety_blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
