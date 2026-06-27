from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_regular_options_forward_candidate_throughput_audit as throughput_audit
from scripts import build_regular_options_strict_forward_market_window_readiness_refresh as readiness_refresh
from scripts import run_forward_cohort_scan_sweep as scan_sweep
from scripts import run_phase2_regular_options_forward_paper_shadow_capture as capture_runner
from us_equity_market_calendar import is_us_equity_market_day, next_market_day, previous_market_day


REPORT_ID = "regular_options_strict_forward_30_goal_loop"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-strict-forward-30-goal-loop.md"
DEFAULT_GOAL_JSON = DEFAULT_OUTPUT_DIR / f"{REPORT_ID}_latest.json"
MARKET_TZ = ZoneInfo("America/New_York")
MARKET_OPEN_ET = time(9, 30)
MARKET_CLOSE_ET = time(16, 0)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _market_window_schedule(generated_at_utc: str) -> dict[str, Any]:
    now_utc = _parse_utc(generated_at_utc)
    now_et = now_utc.astimezone(MARKET_TZ)
    today = now_et.date()
    today_is_market_day = is_us_equity_market_day(today)
    open_dt = datetime.combine(today, MARKET_OPEN_ET, tzinfo=MARKET_TZ)
    close_dt = datetime.combine(today, MARKET_CLOSE_ET, tzinfo=MARKET_TZ)
    is_open = bool(today_is_market_day and open_dt <= now_et < close_dt)
    if is_open:
        next_date = today
        next_open = open_dt
        status = "market_window_open_now"
        default_selection_date = today
    elif today_is_market_day and now_et < open_dt:
        next_date = today
        next_open = open_dt
        status = "waiting_for_today_market_open"
        default_selection_date = previous_market_day(today)
    else:
        next_date = next_market_day(today + timedelta(days=1))
        next_open = datetime.combine(next_date, MARKET_OPEN_ET, tzinfo=MARKET_TZ)
        status = "waiting_for_next_market_day"
        default_selection_date = today if today_is_market_day and now_et >= close_dt else previous_market_day(today)
    return {
        "status": status,
        "current_time_utc": now_utc.isoformat().replace("+00:00", "Z"),
        "current_time_et": now_et.isoformat(),
        "current_market_date": today.isoformat(),
        "default_selection_date": default_selection_date.isoformat(),
        "current_date_is_market_day": today_is_market_day,
        "market_window_open_now": is_open,
        "regular_market_open_et": MARKET_OPEN_ET.isoformat(timespec="minutes"),
        "regular_market_close_et": MARKET_CLOSE_ET.isoformat(timespec="minutes"),
        "next_window_trade_date": next_date.isoformat(),
        "next_window_start_et": next_open.isoformat(),
        "next_window_start_utc": next_open.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "safe_no_append_collection_command": (
            "npm run options:goal-loop:strict-forward-30 -- "
            f"--selection-date {next_date.isoformat()} "
            "--market-window-confirmed --market-window-status open --run-scan-sweep --json"
        ),
    }


def _safety_violations(*payloads: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    must_false = {
        "live_entry_allowed",
        "auto_track_allowed",
        "broker_order_allowed",
        "promotion_ready",
        "quotes_imported",
        "imported_quotes",
        "evidence_stores_mutated",
        "mutated_evidence_databases",
        "protected_holdout_consumed",
        "scanner_policy_changed",
        "changed_scanner_policy",
        "strategy_logic_changed",
        "changed_strategy_logic",
        "stops_changed",
        "changed_stops",
        "sizing_changed",
        "changed_sizing",
        "proof_bars_changed",
        "changed_proof_bars",
        "lowered_proof_bars",
    }
    for idx, payload in enumerate(payloads, start=1):
        for key in sorted(must_false):
            if payload.get(key) is True:
                violations.append(f"payload_{idx}:{key}")
    return violations


def _status_for(
    *,
    strict_rows: int,
    required_rows: int,
    accepted_profitability: bool,
    market_window_confirmed: bool,
    market_window_status: str,
    scan_sweep_exit_code: int | None,
    capture_status: str,
    candidate_rows_staged: int,
    append_requested: bool,
    cohort_append_performed: bool,
    safety_violations: list[str],
) -> str:
    if strict_rows >= required_rows and accepted_profitability:
        return "strict_forward_30_goal_complete"
    if safety_violations:
        return "blocked_safety_violation"
    if scan_sweep_exit_code not in (None, 0):
        return "blocked_passive_scan_sweep_failed"
    if not market_window_confirmed or market_window_status != "open":
        return "waiting_for_valid_market_window"
    if candidate_rows_staged <= 0:
        return "blocked_no_phase2_natural_selections"
    if cohort_append_performed:
        return "append_performed_waiting_for_strict_completed_rows"
    if not append_requested:
        return "candidate_rows_valid_no_append_requested"
    return capture_status or "strict_forward_30_goal_waiting"


def build_report(
    *,
    market_window_confirmed: bool = False,
    market_window_status: str = "unknown",
    selection_date: str | None = None,
    run_scan_sweep: bool = False,
    append: bool = False,
    approval_token: str | None = None,
    dry_run: bool = False,
    source_scan_picks_path: Path = capture_runner.stager.DEFAULT_SOURCE_SCAN_PICKS,
    candidate_output_path: Path = capture_runner.stager.DEFAULT_OUTPUT,
    cohort_log_path: Path = capture_runner.appender.report_builder.DEFAULT_PHASE2_COHORT_LOG,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOCS_REPORT,
    generated_at_utc: str | None = None,
    write_outputs: bool = True,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    market_schedule = _market_window_schedule(generated_at)
    target_date = selection_date or _norm(market_schedule.get("default_selection_date")) or generated_at[:10]
    scan_sweep_exit_code: int | None = None
    scan_sweep_started = False
    if run_scan_sweep:
        scan_sweep_started = True
        scan_args = ["--date", target_date]
        if market_window_confirmed and market_window_status == "open":
            scan_args.append("--force")
        else:
            scan_args.append("--dry-run")
        scan_sweep_exit_code = scan_sweep.main(scan_args)

    if market_window_confirmed and market_window_status == "open":
        capture = capture_runner.build_capture_report(
            market_window_confirmed=market_window_confirmed,
            market_window_status=market_window_status,
            approval_token=approval_token,
            append=append,
            dry_run=dry_run,
            source_scan_picks_path=source_scan_picks_path,
            candidate_output_path=candidate_output_path,
            cohort_log_path=cohort_log_path,
            generated_at_utc=generated_at,
            write_report=write_outputs,
        )
    else:
        capture = {
            "report_id": "phase2_regular_options_forward_paper_shadow_capture",
            "generated_at_utc": generated_at,
            "status": "market_window_not_confirmed_no_capture_started",
            "reason_codes": ["market_window_not_confirmed"],
            "market_window_confirmed": market_window_confirmed,
            "market_window_status": market_window_status,
            "candidate_rows_staged": 0,
            "candidate_jsonl_exists": candidate_output_path.exists(),
            "candidate_output_path": _rel(candidate_output_path),
            "cohort_log_path": _rel(cohort_log_path),
            "append_requested": append,
            "cohort_append_performed": False,
            "scanner_executed": False,
            "created_trades": False,
            "live_entry_allowed": False,
            "auto_track_allowed": False,
            "broker_order_allowed": False,
            "promotion_ready": False,
            "changed_scanner_policy": False,
            "changed_strategy_logic": False,
            "changed_stops": False,
            "changed_sizing": False,
            "changed_proof_bars": False,
            "imported_quotes": False,
            "protected_holdout_consumed": False,
            "writes_performed": [],
        }
    throughput = throughput_audit.build_report(
        scan_picks_path=source_scan_picks_path,
        selection_date=target_date,
        generated_at_utc=generated_at,
    )
    if write_outputs:
        throughput_audit.write_outputs(throughput)
    readiness = readiness_refresh.build_report(generated_at_utc=generated_at)

    if write_outputs:
        readiness_refresh.write_outputs(readiness)

    strict_rows = _int(readiness.get("strict_forward_rows"))
    required_rows = _int(readiness.get("required_rows"), 30)
    accepted_profitability = bool(readiness.get("accepted_profitability"))
    safety_violations = _safety_violations(capture, throughput, readiness)
    status = _status_for(
        strict_rows=strict_rows,
        required_rows=required_rows,
        accepted_profitability=accepted_profitability,
        market_window_confirmed=market_window_confirmed,
        market_window_status=market_window_status,
        scan_sweep_exit_code=scan_sweep_exit_code,
        capture_status=_norm(capture.get("status")),
        candidate_rows_staged=_int(capture.get("candidate_rows_staged")),
        append_requested=append,
        cohort_append_performed=bool(capture.get("cohort_append_performed")),
        safety_violations=safety_violations,
    )
    remaining_rows = max(required_rows - strict_rows, 0)
    next_action = {
        "strict_forward_30_goal_complete": "verify and close the active goal",
        "waiting_for_valid_market_window": "wait_for_valid_market_window_then_run_with_--market-window-confirmed_--market-window-status_open_--run-scan-sweep",
        "blocked_no_phase2_natural_selections": "keep_passive_sweep_enabled_for_next_valid_market_window",
        "candidate_rows_valid_no_append_requested": "review_candidate_jsonl_and_run_guarded_append_only_if_operator_approval_is_explicit",
        "append_performed_waiting_for_strict_completed_rows": "wait_for_policy_exits_and_exact_realized_pnl_before_counting_completed_rows",
        "blocked_passive_scan_sweep_failed": "inspect_scan_sweep_logs_before_retry",
        "blocked_safety_violation": "stop_and_inspect_safety_violation",
    }.get(status, "inspect_goal_loop_report")

    report = {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "status": status,
        "strict_forward_rows": strict_rows,
        "required_rows": required_rows,
        "remaining_rows": remaining_rows,
        "accepted_profitability": accepted_profitability,
        "profitability_readiness": bool(readiness.get("profitability_readiness")),
        "market_window_confirmed": market_window_confirmed,
        "market_window_status": market_window_status,
        "selection_date": target_date,
        "run_scan_sweep_requested": run_scan_sweep,
        "scan_sweep_started": scan_sweep_started,
        "scan_sweep_exit_code": scan_sweep_exit_code,
        "append_requested": append,
        "dry_run": dry_run,
        "cohort_append_performed": bool(capture.get("cohort_append_performed")),
        "candidate_rows_staged": _int(capture.get("candidate_rows_staged")),
        "candidate_jsonl_exists": bool(capture.get("candidate_jsonl_exists")),
        "candidate_output_path": _rel(candidate_output_path),
        "cohort_log_path": _rel(cohort_log_path),
        "source_scan_picks_path": _rel(source_scan_picks_path),
        "capture_status": capture.get("status"),
        "throughput_status": throughput.get("status"),
        "scheduled_phase2_drop_count_total": throughput.get("scheduled_phase2_drop_count_total"),
        "scheduled_phase2_scan_drop_reason_count_total": throughput.get("scheduled_phase2_scan_drop_reason_count_total"),
        "candidate_starvation_evidence_status": throughput.get("candidate_starvation_evidence_status"),
        "readiness_status": readiness.get("overall_status"),
        "scheduled_phase2_all_lanes_scanned": _as_dict(readiness.get("candidate_throughput")).get("scheduled_phase2_all_lanes_scanned"),
        "scheduled_phase2_scan_picks_count": _as_dict(readiness.get("candidate_throughput")).get("scheduled_phase2_scan_picks_count"),
        "safety_violations": safety_violations,
        "next_action": next_action,
        "market_window_schedule": market_schedule,
        "prohibited_actions": [
            "do_not_fabricate_forward_rows",
            "do_not_count_historical_rows_as_forward_proof",
            "do_not_lower_proof_bars",
            "do_not_enable_live_validation",
            "do_not_enable_auto_track",
            "do_not_submit_broker_orders",
            "do_not_import_quotes_from_goal_loop",
            "do_not_mutate_evidence_stores_outside_guarded_append",
            "do_not_consume_protected_holdout",
        ],
        "capture_report": capture,
        "throughput_report": throughput,
        "readiness_report": readiness,
        "artifacts": {},
    }
    if write_outputs:
        report["artifacts"] = write_goal_outputs(report, output_dir=output_dir, docs_report=docs_report)
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Strict Forward 30 Goal Loop",
        "",
        f"Status: `{report.get('status')}`.",
        "",
        f"- Strict completed forward rows: `{report.get('strict_forward_rows')}/{report.get('required_rows')}`.",
        f"- Remaining rows: `{report.get('remaining_rows')}`.",
        f"- Accepted profitability: `{str(bool(report.get('accepted_profitability'))).lower()}`.",
        f"- Market-window status: `{report.get('market_window_status')}`.",
        f"- Next window trade date: `{_as_dict(report.get('market_window_schedule')).get('next_window_trade_date')}`.",
        f"- Next window start ET: `{_as_dict(report.get('market_window_schedule')).get('next_window_start_et')}`.",
        f"- Safe no-append collection command: `{_as_dict(report.get('market_window_schedule')).get('safe_no_append_collection_command')}`.",
        f"- Scan sweep started: `{str(bool(report.get('scan_sweep_started'))).lower()}`.",
        f"- Scan sweep exit code: `{report.get('scan_sweep_exit_code')}`.",
        f"- Candidate rows staged: `{report.get('candidate_rows_staged')}`.",
        f"- Candidate JSONL exists: `{str(bool(report.get('candidate_jsonl_exists'))).lower()}`.",
        f"- Cohort append performed: `{str(bool(report.get('cohort_append_performed'))).lower()}`.",
        f"- Capture status: `{report.get('capture_status')}`.",
        f"- Throughput status: `{report.get('throughput_status')}`.",
        f"- Candidate-starvation evidence status: `{report.get('candidate_starvation_evidence_status')}`.",
        f"- Scheduled Phase 2 drop-count total: `{report.get('scheduled_phase2_drop_count_total')}`.",
        f"- Scheduled Phase 2 symbol drop reasons: `{report.get('scheduled_phase2_scan_drop_reason_count_total')}`.",
        f"- Readiness status: `{report.get('readiness_status')}`.",
        f"- Scheduled Phase 2 scan picks: `{report.get('scheduled_phase2_scan_picks_count')}`.",
        f"- Next action: `{report.get('next_action')}`.",
        "",
        "This coordinator preserves the existing proof rules. It does not fabricate rows, lower proof bars, count historical rows as forward proof, submit broker orders, enable live validation, enable auto-track, import quotes, or mutate evidence stores outside the existing guarded append path.",
        "",
    ]
    violations = report.get("safety_violations") if isinstance(report.get("safety_violations"), list) else []
    if violations:
        lines.extend(["## Safety Violations", ""])
        lines.extend(f"- `{item}`" for item in violations)
        lines.append("")
    return "\n".join(lines)


def write_goal_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
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
    parser = argparse.ArgumentParser(description="Coordinate strict regular-options forward-audit progress toward 30 completed rows.")
    parser.add_argument("--market-window-confirmed", action="store_true")
    parser.add_argument("--market-window-status", choices=["open", "closed", "unknown"], default="unknown")
    parser.add_argument("--selection-date", default=None)
    parser.add_argument("--run-scan-sweep", action="store_true")
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--approval-token", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source-scan-picks", type=Path, default=capture_runner.stager.DEFAULT_SOURCE_SCAN_PICKS)
    parser.add_argument("--candidate-output", type=Path, default=capture_runner.stager.DEFAULT_OUTPUT)
    parser.add_argument("--cohort-log", type=Path, default=capture_runner.appender.report_builder.DEFAULT_PHASE2_COHORT_LOG)
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
    return 0 if report["status"] != "blocked_safety_violation" else 1


if __name__ == "__main__":
    raise SystemExit(main())
