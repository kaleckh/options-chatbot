from __future__ import annotations

import argparse
import json
import sys
import time as time_module
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_regular_options_strict_forward_30_goal_loop as goal_loop


REPORT_ID = "regular_options_strict_forward_30_market_window_collector"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-strict-forward-30-market-window-collector.md"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_no_append_collector_command(schedule: dict[str, Any]) -> str:
    trade_date = _norm(schedule.get("next_window_trade_date")) or "YYYY-MM-DD"
    return (
        "npm run options:goal-loop:strict-forward-30-collector -- "
        f"--selection-date {trade_date} "
        "--market-window-confirmed --market-window-status open "
        "--run-scan-sweep --max-attempts 3 --sleep-seconds 300 --json"
    )


def _attempt_summary(index: int, report: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt": index,
        "status": report.get("status"),
        "strict_forward_rows": _int(report.get("strict_forward_rows")),
        "required_rows": _int(report.get("required_rows"), 30),
        "remaining_rows": _int(report.get("remaining_rows"), 30),
        "accepted_profitability": bool(report.get("accepted_profitability")),
        "candidate_rows_staged": _int(report.get("candidate_rows_staged")),
        "candidate_jsonl_exists": bool(report.get("candidate_jsonl_exists")),
        "cohort_append_performed": bool(report.get("cohort_append_performed")),
        "scan_sweep_started": bool(report.get("scan_sweep_started")),
        "scan_sweep_exit_code": report.get("scan_sweep_exit_code"),
        "capture_status": report.get("capture_status"),
        "throughput_status": report.get("throughput_status"),
        "candidate_starvation_evidence_status": report.get("candidate_starvation_evidence_status"),
        "scheduled_phase2_drop_count_total": report.get("scheduled_phase2_drop_count_total"),
        "scheduled_phase2_scan_drop_reason_count_total": report.get("scheduled_phase2_scan_drop_reason_count_total"),
        "readiness_status": report.get("readiness_status"),
        "safety_violations": report.get("safety_violations") if isinstance(report.get("safety_violations"), list) else [],
        "next_action": report.get("next_action"),
    }


def _collector_status(*, market_window_confirmed: bool, market_window_status: str, attempts: list[dict[str, Any]], append: bool) -> str:
    if not market_window_confirmed or market_window_status != "open":
        return "waiting_for_valid_market_window"
    if not attempts:
        return "collector_attempts_exhausted_waiting_for_more_rows"
    latest = attempts[-1]
    latest_status = _norm(latest.get("status"))
    if _int(latest.get("strict_forward_rows")) >= _int(latest.get("required_rows"), 30) and bool(latest.get("accepted_profitability")):
        return "collector_completed_goal"
    if latest.get("safety_violations") or latest_status == "blocked_safety_violation":
        return "collector_stopped_safety_violation"
    if latest_status == "blocked_passive_scan_sweep_failed":
        return "collector_stopped_scan_sweep_failed"
    if bool(latest.get("cohort_append_performed")):
        return "collector_stopped_after_guarded_append_waiting_for_exits"
    if _int(latest.get("candidate_rows_staged")) > 0 and not append:
        return "collector_stopped_candidate_review_required"
    if latest_status == "blocked_no_phase2_natural_selections":
        return "collector_attempts_exhausted_waiting_for_more_rows"
    return "collector_attempts_exhausted_waiting_for_more_rows"


def _should_stop_after_attempt(summary: dict[str, Any], *, append: bool) -> bool:
    if _int(summary.get("strict_forward_rows")) >= _int(summary.get("required_rows"), 30) and bool(summary.get("accepted_profitability")):
        return True
    if summary.get("safety_violations") or summary.get("status") == "blocked_safety_violation":
        return True
    if summary.get("status") == "blocked_passive_scan_sweep_failed":
        return True
    if bool(summary.get("cohort_append_performed")):
        return True
    if _int(summary.get("candidate_rows_staged")) > 0 and not append:
        return True
    return False


def build_report(
    *,
    market_window_confirmed: bool = False,
    market_window_status: str = "unknown",
    selection_date: str | None = None,
    run_scan_sweep: bool = False,
    append: bool = False,
    approval_token: str | None = None,
    dry_run: bool = False,
    max_attempts: int = 1,
    sleep_seconds: float = 300.0,
    source_scan_picks_path: Path = goal_loop.capture_runner.stager.DEFAULT_SOURCE_SCAN_PICKS,
    candidate_output_path: Path = goal_loop.capture_runner.stager.DEFAULT_OUTPUT,
    cohort_log_path: Path = goal_loop.capture_runner.appender.report_builder.DEFAULT_PHASE2_COHORT_LOG,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOCS_REPORT,
    generated_at_utc: str | None = None,
    write_outputs: bool = True,
    sleep_func: Callable[[float], None] = time_module.sleep,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    attempts: list[dict[str, Any]] = []
    child_reports: list[dict[str, Any]] = []
    bounded_max_attempts = max(1, int(max_attempts))
    bounded_sleep_seconds = max(0.0, float(sleep_seconds))

    if not market_window_confirmed or market_window_status != "open":
        child = goal_loop.build_report(
            market_window_confirmed=market_window_confirmed,
            market_window_status=market_window_status,
            selection_date=selection_date,
            run_scan_sweep=False,
            append=False,
            approval_token=None,
            dry_run=dry_run,
            source_scan_picks_path=source_scan_picks_path,
            candidate_output_path=candidate_output_path,
            cohort_log_path=cohort_log_path,
            generated_at_utc=generated_at,
            write_outputs=write_outputs,
        )
        child_reports.append(child)
        attempts.append(_attempt_summary(1, child))
    else:
        for attempt_index in range(1, bounded_max_attempts + 1):
            attempt_generated_at = generated_at if generated_at_utc else _utc_now_iso()
            child = goal_loop.build_report(
                market_window_confirmed=True,
                market_window_status="open",
                selection_date=selection_date,
                run_scan_sweep=run_scan_sweep,
                append=append,
                approval_token=approval_token,
                dry_run=dry_run,
                source_scan_picks_path=source_scan_picks_path,
                candidate_output_path=candidate_output_path,
                cohort_log_path=cohort_log_path,
                generated_at_utc=attempt_generated_at,
                write_outputs=write_outputs,
            )
            child_reports.append(child)
            summary = _attempt_summary(attempt_index, child)
            attempts.append(summary)
            if _should_stop_after_attempt(summary, append=append):
                break
            if attempt_index < bounded_max_attempts and bounded_sleep_seconds > 0:
                sleep_func(bounded_sleep_seconds)

    latest_child = child_reports[-1] if child_reports else {}
    market_schedule = _as_dict(latest_child.get("market_window_schedule"))
    status = _collector_status(
        market_window_confirmed=market_window_confirmed,
        market_window_status=market_window_status,
        attempts=attempts,
        append=append,
    )
    next_action = {
        "waiting_for_valid_market_window": "wait_for_valid_market_window_then_run_safe_no_append_collector_command",
        "collector_completed_goal": "verify_goal_artifacts_then_close_active_goal",
        "collector_attempts_exhausted_waiting_for_more_rows": "keep_bounded_collector_available_for_next_confirmed_open_market_window",
        "collector_stopped_candidate_review_required": "review_candidate_jsonl_and_only_append_with_explicit_operator_approval_token",
        "collector_stopped_after_guarded_append_waiting_for_exits": "wait_for_policy_exits_and_exact_realized_pnl_before_counting_completed_rows",
        "collector_stopped_safety_violation": "stop_and_inspect_safety_violation",
        "collector_stopped_scan_sweep_failed": "inspect_forward_cohort_scan_sweep_before_retry",
    }.get(status, "inspect_collector_report")

    report = {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "status": status,
        "strict_forward_rows": _int(latest_child.get("strict_forward_rows")),
        "required_rows": _int(latest_child.get("required_rows"), 30),
        "remaining_rows": _int(latest_child.get("remaining_rows"), 30),
        "accepted_profitability": bool(latest_child.get("accepted_profitability")),
        "profitability_readiness": bool(latest_child.get("profitability_readiness")),
        "market_window_confirmed": market_window_confirmed,
        "market_window_status": market_window_status,
        "selection_date": selection_date or latest_child.get("selection_date"),
        "run_scan_sweep_requested": run_scan_sweep,
        "append_requested": append,
        "dry_run": dry_run,
        "max_attempts": bounded_max_attempts,
        "sleep_seconds": bounded_sleep_seconds,
        "attempt_count": len(attempts),
        "attempt_reports": attempts,
        "latest_goal_loop_status": latest_child.get("status"),
        "latest_capture_status": latest_child.get("capture_status"),
        "latest_throughput_status": latest_child.get("throughput_status"),
        "latest_candidate_starvation_evidence_status": latest_child.get("candidate_starvation_evidence_status"),
        "latest_scheduled_phase2_drop_count_total": latest_child.get("scheduled_phase2_drop_count_total"),
        "latest_scheduled_phase2_scan_drop_reason_count_total": latest_child.get("scheduled_phase2_scan_drop_reason_count_total"),
        "latest_readiness_status": latest_child.get("readiness_status"),
        "candidate_rows_staged": _int(latest_child.get("candidate_rows_staged")),
        "candidate_jsonl_exists": bool(latest_child.get("candidate_jsonl_exists")),
        "cohort_append_performed": bool(latest_child.get("cohort_append_performed")),
        "safety_violations": latest_child.get("safety_violations") if isinstance(latest_child.get("safety_violations"), list) else [],
        "next_action": next_action,
        "market_window_schedule": market_schedule,
        "safe_no_append_collector_command": _safe_no_append_collector_command(market_schedule),
        "prohibited_actions": [
            "do_not_fabricate_forward_rows",
            "do_not_count_historical_rows_as_forward_proof",
            "do_not_lower_proof_bars",
            "do_not_enable_live_validation",
            "do_not_enable_auto_track",
            "do_not_submit_broker_orders",
            "do_not_import_quotes_from_collector",
            "do_not_mutate_evidence_stores_outside_existing_guarded_append",
            "do_not_consume_protected_holdout",
        ],
        "latest_goal_loop_report": latest_child,
        "artifacts": {},
    }
    if write_outputs:
        report["artifacts"] = write_outputs_report(report, output_dir=output_dir, docs_report=docs_report)
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Strict Forward 30 Market-Window Collector",
        "",
        f"Status: `{report.get('status')}`.",
        "",
        f"- Strict completed forward rows: `{report.get('strict_forward_rows')}/{report.get('required_rows')}`.",
        f"- Remaining rows: `{report.get('remaining_rows')}`.",
        f"- Accepted profitability: `{str(bool(report.get('accepted_profitability'))).lower()}`.",
        f"- Market-window status: `{report.get('market_window_status')}`.",
        f"- Attempt count: `{report.get('attempt_count')}/{report.get('max_attempts')}`.",
        f"- Sleep seconds: `{report.get('sleep_seconds')}`.",
        f"- Run scan sweep requested: `{str(bool(report.get('run_scan_sweep_requested'))).lower()}`.",
        f"- Candidate rows staged: `{report.get('candidate_rows_staged')}`.",
        f"- Candidate JSONL exists: `{str(bool(report.get('candidate_jsonl_exists'))).lower()}`.",
        f"- Cohort append performed: `{str(bool(report.get('cohort_append_performed'))).lower()}`.",
        f"- Latest goal-loop status: `{report.get('latest_goal_loop_status')}`.",
        f"- Latest capture status: `{report.get('latest_capture_status')}`.",
        f"- Latest throughput status: `{report.get('latest_throughput_status')}`.",
        f"- Latest candidate-starvation evidence status: `{report.get('latest_candidate_starvation_evidence_status')}`.",
        f"- Latest scheduled Phase 2 drop-count total: `{report.get('latest_scheduled_phase2_drop_count_total')}`.",
        f"- Latest scheduled Phase 2 symbol drop reasons: `{report.get('latest_scheduled_phase2_scan_drop_reason_count_total')}`.",
        f"- Latest readiness status: `{report.get('latest_readiness_status')}`.",
        f"- Safe no-append collector command: `{report.get('safe_no_append_collector_command')}`.",
        f"- Next action: `{report.get('next_action')}`.",
        "",
        "This collector only repeats the existing strict-forward goal-loop coordinator during a confirmed open market window. It is bounded by `max_attempts`, defaults to no append, and stops on candidate review, guarded append, safety violations, scan failure, or goal completion.",
        "",
    ]
    attempts = report.get("attempt_reports") if isinstance(report.get("attempt_reports"), list) else []
    if attempts:
        lines.extend(["## Attempts", ""])
        for attempt in attempts:
            lines.append(
                "- "
                f"`{attempt.get('attempt')}` "
                f"status=`{attempt.get('status')}` "
                f"strict_rows=`{attempt.get('strict_forward_rows')}/{attempt.get('required_rows')}` "
                f"candidates=`{attempt.get('candidate_rows_staged')}` "
                f"append=`{str(bool(attempt.get('cohort_append_performed'))).lower()}`"
            )
        lines.append("")
    violations = report.get("safety_violations") if isinstance(report.get("safety_violations"), list) else []
    if violations:
        lines.extend(["## Safety Violations", ""])
        lines.extend(f"- `{item}`" for item in violations)
        lines.append("")
    return "\n".join(lines)


def write_outputs_report(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
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
    parser = argparse.ArgumentParser(description="Bounded market-window collector for the strict regular-options 30-row forward-audit goal.")
    parser.add_argument("--market-window-confirmed", action="store_true")
    parser.add_argument("--market-window-status", choices=["open", "closed", "unknown"], default="unknown")
    parser.add_argument("--selection-date", default=None)
    parser.add_argument("--run-scan-sweep", action="store_true")
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--approval-token", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-attempts", type=int, default=1)
    parser.add_argument("--sleep-seconds", type=float, default=300.0)
    parser.add_argument("--source-scan-picks", type=Path, default=goal_loop.capture_runner.stager.DEFAULT_SOURCE_SCAN_PICKS)
    parser.add_argument("--candidate-output", type=Path, default=goal_loop.capture_runner.stager.DEFAULT_OUTPUT)
    parser.add_argument("--cohort-log", type=Path, default=goal_loop.capture_runner.appender.report_builder.DEFAULT_PHASE2_COHORT_LOG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_report(
        market_window_confirmed=args.market_window_confirmed,
        market_window_status=args.market_window_status,
        selection_date=args.selection_date,
        run_scan_sweep=args.run_scan_sweep,
        append=args.append,
        approval_token=args.approval_token,
        dry_run=args.dry_run,
        max_attempts=args.max_attempts,
        sleep_seconds=args.sleep_seconds,
        source_scan_picks_path=args.source_scan_picks,
        candidate_output_path=args.candidate_output,
        cohort_log_path=args.cohort_log,
        output_dir=args.output_dir,
        docs_report=args.docs_report,
        write_outputs=not args.no_write,
    )
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0 if report["status"] not in {"collector_stopped_safety_violation", "collector_stopped_scan_sweep_failed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
