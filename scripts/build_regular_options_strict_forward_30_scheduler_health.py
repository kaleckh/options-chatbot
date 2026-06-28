from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_strict_forward_30_scheduler_health"
DEFAULT_TASK_NAME = r"\OptionsStrictForward30Collector"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-strict-forward-30-scheduler-health.md"
EXPECTED_TASK_TO_RUN = str(ROOT / "scripts" / "run_strict_forward_30_auto_window_collector.bat")
EXPECTED_REPEAT = "0 Hour(s), 30 Minute(s)"
EXPECTED_DURATION = "6 Hour(s), 30 Minute(s)"
EXPECTED_STOP_LIMIT = "00:45:00"
RUNTIME_STALE_GRACE = timedelta(minutes=5)
NEVER_RUN_CUTOFF = datetime(2001, 1, 1)
RUNTIME_BLOCKING_STATUSES = {
    "scheduler_runtime_failed",
    "scheduler_runtime_stale",
    "scheduler_runtime_unobservable",
}
WINDOWS_TASK_DATETIME_FORMATS = (
    "%m/%d/%Y %I:%M:%S %p",
    "%m/%d/%Y %I:%M %p",
    "%m/%d/%y %I:%M:%S %p",
    "%m/%d/%y %I:%M %p",
    "%Y-%m-%d %H:%M:%S",
)
EXPECTED_BATCH_STEPS = [
    "set OPTIONS_SCAN_AUTO_TRACK=0",
    "set OPTIONS_SCAN_ENFORCE_PORTFOLIO_CAPS=1",
    "set OPTIONS_ENFORCE_LANE_PROFITABILITY_GATE=1",
    "scripts\\run_regular_options_strict_forward_30_auto_window_collector.py --max-attempts 3 --sleep-seconds 300 --json",
    "scripts\\build_regular_options_strict_forward_30_scheduler_health.py --json",
    "scripts\\build_regular_options_strict_forward_scan_task_health.py --json",
    "scripts\\build_regular_options_strict_forward_30_candidate_review_packet.py --json",
    "scripts\\build_regular_options_strict_forward_30_exit_evidence_plan.py --json",
    "scripts\\build_regular_options_strict_forward_30_exit_completion_stager.py --json",
    "scripts\\build_regular_options_strict_forward_30_lifecycle_audit.py --json",
    "scripts\\build_regular_options_strict_forward_30_completion_monitor.py --json",
]
PROHIBITED_BATCH_TOKENS = (
    "--append",
    "APPROVE_PHASE2_FORWARD_COHORT_APPEND",
    "OPTIONS_SCAN_AUTO_TRACK=1",
    "OPTIONS_SCAN_AUTO_TRACK=true",
    "OPTIONS_SCAN_AUTO_TRACK=True",
    "append_volatility_expansion_forward_paper_shadow_rows.py",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _normal_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _field_value(fields: dict[str, str], names: tuple[str, ...]) -> str:
    for name in names:
        if name in fields:
            return _norm(fields.get(name))
    normalized = {_normal_key(key): value for key, value in fields.items()}
    for name in names:
        value = normalized.get(_normal_key(name))
        if value is not None:
            return _norm(value)
    return ""


def _parse_task_datetime(value: str) -> datetime | None:
    text = _norm(value)
    if not text or text.lower() in {"n/a", "na", "never", "none"}:
        return None
    for fmt in WINDOWS_TASK_DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _generated_at_local_naive(generated_at_utc: str) -> datetime:
    text = _norm(generated_at_utc)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now().astimezone().replace(tzinfo=None)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone().replace(tzinfo=None)


def _parse_result_code(value: str) -> int | None:
    text = _norm(value)
    if not text or text.lower() in {"n/a", "na", "none"}:
        return None
    hex_match = re.search(r"0x[0-9a-fA-F]+", text)
    if hex_match:
        return int(hex_match.group(0), 16)
    int_match = re.search(r"-?\d+", text)
    if int_match:
        return int(int_match.group(0))
    return None


def _is_never_run(value: str, parsed: datetime | None) -> bool:
    text = _norm(value).lower()
    if not text or text in {"n/a", "na", "never", "none"}:
        return True
    return parsed is not None and parsed < NEVER_RUN_CUTOFF


def _parse_start_datetime(fields: dict[str, str]) -> datetime | None:
    start_date = _field_value(fields, ("Start Date", "StartDate"))
    start_time = _field_value(fields, ("Start Time", "StartTime"))
    if not start_date or not start_time:
        return None
    return _parse_task_datetime(f"{start_date} {start_time}")


def parse_schtasks_list(output: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw_line in output.splitlines():
        match = re.match(r"^(.+?):\s{2,}(.*)$", raw_line)
        if match:
            key, value = match.groups()
        elif raw_line.startswith("Stop Task If Runs X Hours and X Mins:"):
            key = "Stop Task If Runs X Hours and X Mins"
            value = raw_line.split(":", 1)[1]
        elif ":" in raw_line:
            key, value = raw_line.split(":", 1)
        else:
            continue
        fields[key.strip()] = value.strip()
    return fields


def query_task(task_name: str = DEFAULT_TASK_NAME) -> tuple[int, str, str]:
    result = subprocess.run(
        ["schtasks", "/Query", "/TN", task_name, "/FO", "LIST", "/V"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def _status_for(fields: dict[str, str], *, returncode: int) -> tuple[str, list[str]]:
    blockers: list[str] = []
    if returncode != 0:
        return "scheduler_task_missing_or_unqueryable", ["schtasks_query_failed"]
    if _norm(fields.get("TaskName")) != DEFAULT_TASK_NAME:
        blockers.append("task_name_mismatch")
    if _norm(fields.get("Scheduled Task State")).lower() != "enabled":
        blockers.append("task_not_enabled")
    if _norm(fields.get("Status")).lower() not in {"ready", "running"}:
        blockers.append("task_not_ready_or_running")
    if _norm(fields.get("Task To Run")).lower() != EXPECTED_TASK_TO_RUN.lower():
        blockers.append("task_to_run_mismatch")
    if _norm(fields.get("Repeat: Every")) != EXPECTED_REPEAT:
        blockers.append("repeat_interval_mismatch")
    if _norm(fields.get("Repeat: Until: Duration")) != EXPECTED_DURATION:
        blockers.append("repeat_duration_mismatch")
    if _norm(fields.get("Stop Task If Runs X Hours and X Mins")) != EXPECTED_STOP_LIMIT:
        blockers.append("execution_time_limit_mismatch")
    return ("scheduler_ready_for_next_market_window" if not blockers else "scheduler_config_blocked", blockers)


def build_runtime_telemetry(
    fields: dict[str, str],
    *,
    returncode: int,
    generated_at_utc: str,
) -> dict[str, Any]:
    raw_last_run = _field_value(fields, ("Last Run Time", "LastRunTime"))
    raw_last_result = _field_value(fields, ("Last Result", "Last Task Result", "Last Run Result"))
    raw_next_run = _field_value(fields, ("Next Run Time", "NextRunTime"))
    raw_missed_runs = _field_value(fields, ("Number of Missed Runs", "Missed Runs", "Missed Run Count"))

    last_run = _parse_task_datetime(raw_last_run)
    next_run = _parse_task_datetime(raw_next_run)
    start_run = _parse_start_datetime(fields)
    last_result = _parse_result_code(raw_last_result)
    missed_runs = _parse_result_code(raw_missed_runs)
    generated_local = _generated_at_local_naive(generated_at_utc)
    never_run = _is_never_run(raw_last_run, last_run)
    blockers: list[str] = []

    if returncode != 0:
        status = "scheduler_runtime_unobservable"
        blockers.append("scheduler_runtime_schtasks_query_failed")
    elif not any((raw_last_run, raw_last_result, raw_next_run, raw_missed_runs)):
        status = "scheduler_runtime_unobservable"
        blockers.append("scheduler_runtime_fields_missing")
    elif not raw_last_run:
        status = "scheduler_runtime_unobservable"
        blockers.append("scheduler_runtime_last_run_time_missing")
    elif not raw_last_result:
        status = "scheduler_runtime_unobservable"
        blockers.append("scheduler_runtime_last_result_missing")
    elif not raw_next_run:
        status = "scheduler_runtime_unobservable"
        blockers.append("scheduler_runtime_next_run_time_missing")
    elif last_run is None and not never_run:
        status = "scheduler_runtime_unobservable"
        blockers.append("scheduler_runtime_last_run_time_unparseable")
    elif next_run is None:
        status = "scheduler_runtime_unobservable"
        blockers.append("scheduler_runtime_next_run_time_unparseable")
    elif last_result is None:
        status = "scheduler_runtime_unobservable"
        blockers.append("scheduler_runtime_last_result_unparseable")
    elif raw_missed_runs and missed_runs is None:
        status = "scheduler_runtime_unobservable"
        blockers.append("scheduler_runtime_missed_runs_unparseable")
    elif missed_runs is not None and missed_runs > 0:
        status = "scheduler_runtime_stale"
        blockers.append("scheduler_runtime_missed_runs_nonzero")
    elif never_run:
        if start_run is None:
            status = "scheduler_runtime_unobservable"
            blockers.append("scheduler_runtime_never_run_start_metadata_missing_or_unparseable")
        elif generated_local < start_run + RUNTIME_STALE_GRACE:
            status = "scheduler_runtime_pending_first_expected_run"
        else:
            status = "scheduler_runtime_stale"
            blockers.append("scheduler_runtime_last_run_never_after_expected_window")
    elif last_result is not None and last_result != 0:
        status = "scheduler_runtime_failed"
        blockers.append("scheduler_runtime_last_result_nonzero")
    else:
        expected_cutoff = next_run if generated_local >= next_run else next_run - timedelta(minutes=30)
        if generated_local >= expected_cutoff + RUNTIME_STALE_GRACE and last_run < expected_cutoff - RUNTIME_STALE_GRACE:
            status = "scheduler_runtime_stale"
            blockers.append("scheduler_runtime_last_run_stale")
        else:
            status = "scheduler_runtime_observed_ok"

    return {
        "status": status,
        "blockers": blockers,
        "runtime_blocking": status in RUNTIME_BLOCKING_STATUSES,
        "generated_at_local": generated_local.isoformat(timespec="seconds"),
        "fields": {
            "last_run_time": raw_last_run,
            "last_result": raw_last_result,
            "next_run_time": raw_next_run,
            "number_of_missed_runs": raw_missed_runs,
            "start_date": _field_value(fields, ("Start Date", "StartDate")),
            "start_time": _field_value(fields, ("Start Time", "StartTime")),
        },
        "parsed": {
            "last_run_time_local": last_run.isoformat(timespec="seconds") if last_run else None,
            "last_result_code": last_result,
            "next_run_time_local": next_run.isoformat(timespec="seconds") if next_run else None,
            "start_run_time_local": start_run.isoformat(timespec="seconds") if start_run else None,
            "number_of_missed_runs": missed_runs,
            "last_run_time_is_never_run_sentinel": never_run,
        },
        "notes": [
            "Runtime telemetry is separate from top-level scheduler configuration readiness.",
            "Runtime blockers do not authorize append, live validation, auto-track, broker orders, quote import, proof-bar changes, or evidence mutation.",
        ],
    }


def _inspect_batch_file(path: Path = Path(EXPECTED_TASK_TO_RUN)) -> dict[str, Any]:
    report: dict[str, Any] = {
        "path": _rel(path),
        "exists": path.exists(),
        "status": "missing",
        "missing_steps": [],
        "order_blockers": [],
        "prohibited_tokens_present": [],
    }
    if not path.exists():
        report["missing_steps"] = list(EXPECTED_BATCH_STEPS)
        return report
    text = path.read_text(encoding="utf8", errors="replace")
    missing = [step for step in EXPECTED_BATCH_STEPS if step not in text]
    order_blockers: list[str] = []
    last_index = -1
    for step in EXPECTED_BATCH_STEPS:
        index = text.find(step)
        if index == -1:
            continue
        if index < last_index:
            order_blockers.append(f"step_out_of_order:{step}")
        last_index = index
    prohibited_tokens = [token for token in PROHIBITED_BATCH_TOKENS if token in text]
    report.update(
        {
            "status": "loaded",
            "missing_steps": missing,
            "order_blockers": order_blockers,
            "prohibited_tokens_present": prohibited_tokens,
        }
    )
    return report


def build_report(
    *,
    generated_at_utc: str | None = None,
    task_name: str = DEFAULT_TASK_NAME,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    returncode, stdout, stderr = query_task(task_name)
    fields = parse_schtasks_list(stdout)
    config_status, config_blockers = _status_for(fields, returncode=returncode)
    status = config_status
    blockers = list(config_blockers)
    runtime = build_runtime_telemetry(fields, returncode=returncode, generated_at_utc=generated_at)
    batch = _inspect_batch_file()
    if batch.get("status") != "loaded":
        blockers.append("batch_file_missing_or_unreadable")
    for step in batch.get("missing_steps") if isinstance(batch.get("missing_steps"), list) else []:
        blockers.append(f"batch_missing_step:{step}")
    for blocker in batch.get("order_blockers") if isinstance(batch.get("order_blockers"), list) else []:
        blockers.append(blocker)
    for token in batch.get("prohibited_tokens_present") if isinstance(batch.get("prohibited_tokens_present"), list) else []:
        blockers.append(f"batch_prohibited_token:{token}")
    if blockers and status == "scheduler_ready_for_next_market_window":
        status = "scheduler_config_blocked"
    if status == "scheduler_ready_for_next_market_window" and runtime.get("runtime_blocking"):
        status = "scheduler_runtime_blocked"
        blockers.append(f"scheduler_runtime_blocking:{runtime['status']}")
    return {
        "report_id": REPORT_ID,
        "schema_version": 2,
        "generated_at_utc": generated_at,
        "status": status,
        "blockers": blockers,
        "config_status": config_status,
        "config_blockers": config_blockers,
        "runtime_status": runtime["status"],
        "runtime_blockers": runtime["blockers"],
        "runtime_telemetry": runtime,
        "task_name": task_name,
        "query_returncode": returncode,
        "query_stderr": stderr.strip().splitlines()[-5:],
        "task": fields,
        "batch_file": batch,
        "expected": {
            "task_name": DEFAULT_TASK_NAME,
            "task_to_run": EXPECTED_TASK_TO_RUN,
            "scheduled_task_state": "Enabled",
            "acceptable_statuses": ["Ready", "Running"],
            "repeat_every": EXPECTED_REPEAT,
            "repeat_duration": EXPECTED_DURATION,
            "execution_time_limit": EXPECTED_STOP_LIMIT,
            "batch_steps": EXPECTED_BATCH_STEPS,
        },
        "safety": {
            "append_allowed": False,
            "live_entry_allowed": False,
            "auto_track_allowed": False,
            "broker_order_allowed": False,
            "quotes_imported": False,
            "proof_bars_changed": False,
            "historical_rows_are_forward_proof": False,
        },
        "prohibited_actions": [
            "do_not_append_from_scheduler_health",
            "do_not_enable_live_validation_from_scheduler_health",
            "do_not_enable_auto_track_from_scheduler_health",
            "do_not_submit_broker_orders_from_scheduler_health",
            "do_not_import_quotes_from_scheduler_health",
            "do_not_lower_proof_bars_from_scheduler_health",
            "do_not_treat_historical_rows_as_forward_proof",
        ],
        "artifacts": {},
    }


def render_markdown(report: dict[str, Any]) -> str:
    task = report.get("task") if isinstance(report.get("task"), dict) else {}
    runtime = report.get("runtime_telemetry") if isinstance(report.get("runtime_telemetry"), dict) else {}
    runtime_fields = runtime.get("fields") if isinstance(runtime.get("fields"), dict) else {}
    lines = [
        "# Regular Options Strict Forward 30 Scheduler Health",
        "",
        f"Status: `{report.get('status')}`.",
        f"Config readiness status: `{report.get('config_status')}`.",
        f"Scheduler runtime telemetry status: `{report.get('runtime_status')}`.",
        "",
        f"- Task name: `{report.get('task_name')}`.",
        f"- Scheduled task state: `{task.get('Scheduled Task State')}`.",
        f"- Windows task state: `{task.get('Status')}`.",
        f"- Next run time: `{task.get('Next Run Time')}`.",
        f"- Last run time: `{runtime_fields.get('last_run_time')}`.",
        f"- Last result: `{runtime_fields.get('last_result')}`.",
        f"- Number of missed runs: `{runtime_fields.get('number_of_missed_runs')}`.",
        f"- Task to run: `{task.get('Task To Run')}`.",
        f"- Repeat every: `{task.get('Repeat: Every')}`.",
        f"- Repeat duration: `{task.get('Repeat: Until: Duration')}`.",
        f"- Execution time limit: `{task.get('Stop Task If Runs X Hours and X Mins')}`.",
        f"- Batch file status: `{_as_batch_status(report)}`.",
        "",
        "This health report verifies scheduler configuration and the strict-forward batch wrapper contents. It does not append rows, enable live validation, enable auto-track, submit broker orders, import quotes, lower proof bars, or count historical rows as forward proof.",
        "",
    ]
    blockers = report.get("blockers") if isinstance(report.get("blockers"), list) else []
    if blockers:
        lines.extend(["## Blockers", ""])
        lines.extend(f"- `{item}`" for item in blockers)
        lines.append("")
    runtime_blockers = report.get("runtime_blockers") if isinstance(report.get("runtime_blockers"), list) else []
    if runtime_blockers:
        lines.extend(["## Runtime Blockers", ""])
        lines.extend(f"- `{item}`" for item in runtime_blockers)
        lines.append("")
    return "\n".join(lines)


def _as_batch_status(report: dict[str, Any]) -> str:
    batch = report.get("batch_file") if isinstance(report.get("batch_file"), dict) else {}
    if batch.get("status") != "loaded":
        return _norm(batch.get("status")) or "missing"
    missing = batch.get("missing_steps") if isinstance(batch.get("missing_steps"), list) else []
    order = batch.get("order_blockers") if isinstance(batch.get("order_blockers"), list) else []
    prohibited = batch.get("prohibited_tokens_present") if isinstance(batch.get("prohibited_tokens_present"), list) else []
    if missing or order or prohibited:
        return "batch_config_blocked"
    return "batch_chain_ready"


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
    parser = argparse.ArgumentParser(description="Verify strict-forward 30-row collector Windows scheduler health.")
    parser.add_argument("--task-name", default=DEFAULT_TASK_NAME)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_report(task_name=args.task_name)
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0 if report["status"] == "scheduler_ready_for_next_market_window" else 1


if __name__ == "__main__":
    raise SystemExit(main())
