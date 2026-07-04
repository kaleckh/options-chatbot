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
REPORT_ID = "regular_options_fresh_window_import_scheduler_health"
DEFAULT_TASK_NAME = r"\OptionsFreshWindowThetaDataOPRAImport"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-fresh-window-import-scheduler-health.md"
EXPECTED_TASK_TO_RUN = str(ROOT / "scripts" / "run_fresh_window_thetadata_opra_import.bat")
EXPECTED_START_TIME = "5:30:00 PM"
EXPECTED_STOP_LIMIT = "02:00:00"
RUNTIME_STALE_GRACE = timedelta(minutes=10)
NEVER_RUN_CUTOFF = datetime(2001, 1, 1)
EXPECTED_BATCH_STEPS = [
    "scripts\\import_regular_options_fresh_window_thetadata_opra.py --approval-token APPROVE_FRESH_WINDOW_THETADATA_OPRA_IMPORT --timeout 20 --refresh-after-import --json",
    "scripts\\build_regular_options_fresh_window_import_scheduler_health.py --json",
]
PROHIBITED_BATCH_TOKENS = (
    "--append",
    "APPROVE_PHASE2_FORWARD_COHORT_APPEND",
    "OPTIONS_SCAN_AUTO_TRACK",
    "run_forward_cohort_scan_sweep.py",
    "log_scan_picks.py",
    "append_volatility_expansion_forward_paper_shadow_rows.py",
)
WINDOWS_TASK_DATETIME_FORMATS = (
    "%m/%d/%Y %I:%M:%S %p",
    "%m/%d/%Y %I:%M %p",
    "%m/%d/%y %I:%M:%S %p",
    "%m/%d/%y %I:%M %p",
    "%Y-%m-%d %H:%M:%S",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


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


def _is_never_run(value: str, parsed: datetime | None) -> bool:
    text = _norm(value).lower()
    if not text or text in {"n/a", "na", "never", "none"}:
        return True
    return parsed is not None and parsed < NEVER_RUN_CUTOFF


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
    prohibited = [token for token in PROHIBITED_BATCH_TOKENS if token in text]
    report.update(
        {
            "status": "loaded",
            "missing_steps": missing,
            "order_blockers": order_blockers,
            "prohibited_tokens_present": prohibited,
        }
    )
    return report


def _task_to_run_matches(value: str) -> bool:
    actual = _norm(value)
    expected = EXPECTED_TASK_TO_RUN
    if actual.lower() == expected.lower():
        return True
    match = re.fullmatch(r'cmd\.exe\s+/c\s+"([^"]+)"', actual, flags=re.IGNORECASE)
    if not match:
        return False
    try:
        return Path(match.group(1)).resolve() == Path(expected).resolve()
    except OSError:
        return False


def _config_status(fields: dict[str, str], *, returncode: int) -> tuple[str, list[str]]:
    blockers: list[str] = []
    if returncode != 0:
        return "scheduler_task_missing_or_unqueryable", ["schtasks_query_failed"]
    if _norm(fields.get("TaskName")) != DEFAULT_TASK_NAME:
        blockers.append("task_name_mismatch")
    if _norm(fields.get("Scheduled Task State")).lower() != "enabled":
        blockers.append("task_not_enabled")
    if _norm(fields.get("Status")).lower() not in {"ready", "running"}:
        blockers.append("task_not_ready_or_running")
    if not _task_to_run_matches(fields.get("Task To Run", "")):
        blockers.append("task_to_run_mismatch")
    schedule_type = _field_value(fields, ("Schedule Type", "ScheduleType")).lower()
    if "weekly" not in schedule_type:
        blockers.append("schedule_type_not_weekly")
    days = _field_value(fields, ("Days", "Days of Week", "Schedule Days"))
    for day in ("MON", "TUE", "WED", "THU", "FRI"):
        if day.lower() not in days.lower():
            blockers.append(f"weekday_missing:{day}")
    start_time = _field_value(fields, ("Start Time", "StartTime"))
    if start_time and start_time != EXPECTED_START_TIME:
        blockers.append("start_time_mismatch")
    if _norm(fields.get("Stop Task If Runs X Hours and X Mins")) != EXPECTED_STOP_LIMIT:
        blockers.append("execution_time_limit_mismatch")
    return ("fresh_window_import_scheduler_ready" if not blockers else "fresh_window_import_scheduler_config_blocked", blockers)


def _runtime_status(fields: dict[str, str], *, returncode: int, generated_at_utc: str) -> dict[str, Any]:
    raw_last_run = _field_value(fields, ("Last Run Time", "LastRunTime"))
    raw_last_result = _field_value(fields, ("Last Result", "Last Task Result", "Last Run Result"))
    raw_next_run = _field_value(fields, ("Next Run Time", "NextRunTime"))
    raw_missed_runs = _field_value(fields, ("Number of Missed Runs", "Missed Runs", "Missed Run Count"))
    last_run = _parse_task_datetime(raw_last_run)
    next_run = _parse_task_datetime(raw_next_run)
    last_result = _parse_result_code(raw_last_result)
    missed_runs = _parse_result_code(raw_missed_runs)
    generated_local = _generated_at_local_naive(generated_at_utc)
    never_run = _is_never_run(raw_last_run, last_run)
    blockers: list[str] = []
    if returncode != 0:
        status = "scheduler_runtime_unobservable"
        blockers.append("scheduler_runtime_schtasks_query_failed")
    elif not raw_next_run:
        status = "scheduler_runtime_unobservable"
        blockers.append("scheduler_runtime_next_run_time_missing")
    elif next_run is None:
        status = "scheduler_runtime_unobservable"
        blockers.append("scheduler_runtime_next_run_time_unparseable")
    elif missed_runs is not None and missed_runs > 0:
        status = "scheduler_runtime_stale"
        blockers.append("scheduler_runtime_missed_runs_nonzero")
    elif never_run:
        status = "scheduler_runtime_pending_first_expected_run"
    elif last_result is None:
        status = "scheduler_runtime_unobservable"
        blockers.append("scheduler_runtime_last_result_unparseable")
    elif last_result != 0:
        status = "scheduler_runtime_failed"
        blockers.append("scheduler_runtime_last_result_nonzero")
    elif last_run is None:
        status = "scheduler_runtime_unobservable"
        blockers.append("scheduler_runtime_last_run_time_unparseable")
    elif generated_local >= next_run + RUNTIME_STALE_GRACE and last_run < next_run - timedelta(days=1):
        status = "scheduler_runtime_stale"
        blockers.append("scheduler_runtime_last_run_stale")
    else:
        status = "scheduler_runtime_observed_ok"
    return {
        "status": status,
        "blockers": blockers,
        "runtime_blocking": status in {"scheduler_runtime_failed", "scheduler_runtime_stale", "scheduler_runtime_unobservable"},
        "fields": {
            "last_run_time": raw_last_run,
            "last_result": raw_last_result,
            "next_run_time": raw_next_run,
            "number_of_missed_runs": raw_missed_runs,
        },
        "parsed": {
            "last_run_time_local": last_run.isoformat(timespec="seconds") if last_run else None,
            "last_result_code": last_result,
            "next_run_time_local": next_run.isoformat(timespec="seconds") if next_run else None,
            "number_of_missed_runs": missed_runs,
            "last_run_time_is_never_run_sentinel": never_run,
        },
    }


def build_report(*, generated_at_utc: str | None = None, task_name: str = DEFAULT_TASK_NAME) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    returncode, stdout, stderr = query_task(task_name)
    fields = parse_schtasks_list(stdout)
    config_status, config_blockers = _config_status(fields, returncode=returncode)
    batch = _inspect_batch_file()
    runtime = _runtime_status(fields, returncode=returncode, generated_at_utc=generated_at)
    blockers = list(config_blockers)
    if batch.get("status") != "loaded":
        blockers.append("batch_file_missing_or_unreadable")
    for step in batch.get("missing_steps") if isinstance(batch.get("missing_steps"), list) else []:
        blockers.append(f"batch_missing_step:{step}")
    for blocker in batch.get("order_blockers") if isinstance(batch.get("order_blockers"), list) else []:
        blockers.append(blocker)
    for token in batch.get("prohibited_tokens_present") if isinstance(batch.get("prohibited_tokens_present"), list) else []:
        blockers.append(f"batch_prohibited_token:{token}")
    status = config_status
    if blockers and status == "fresh_window_import_scheduler_ready":
        status = "fresh_window_import_scheduler_config_blocked"
    if status == "fresh_window_import_scheduler_ready" and runtime.get("runtime_blocking"):
        status = "fresh_window_import_scheduler_runtime_blocked"
        blockers.append(f"scheduler_runtime_blocking:{runtime['status']}")
    return {
        "report_id": REPORT_ID,
        "schema_version": 1,
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
            "schedule_type": "Weekly",
            "weekdays_required": ["MON", "TUE", "WED", "THU", "FRI"],
            "start_time": EXPECTED_START_TIME,
            "execution_time_limit": EXPECTED_STOP_LIMIT,
            "batch_steps": EXPECTED_BATCH_STEPS,
        },
        "safety": {
            "scanner_policy_changed": False,
            "live_validation_enabled": False,
            "auto_track_enabled": False,
            "broker_order_allowed": False,
            "proof_bars_changed": False,
            "forward_cohort_appended": False,
            "protected_holdout_consumed": False,
        },
        "artifacts": {},
    }


def render_markdown(report: dict[str, Any]) -> str:
    task = report.get("task") if isinstance(report.get("task"), dict) else {}
    runtime = report.get("runtime_telemetry") if isinstance(report.get("runtime_telemetry"), dict) else {}
    runtime_fields = runtime.get("fields") if isinstance(runtime.get("fields"), dict) else {}
    lines = [
        "# Regular Options Fresh-Window Import Scheduler Health",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Config status: `{report.get('config_status')}`.",
        f"- Runtime status: `{report.get('runtime_status')}`.",
        f"- Task name: `{report.get('task_name')}`.",
        f"- Scheduled task state: `{task.get('Scheduled Task State')}`.",
        f"- Windows task state: `{task.get('Status')}`.",
        f"- Next run time: `{task.get('Next Run Time')}`.",
        f"- Last run time: `{runtime_fields.get('last_run_time')}`.",
        f"- Last result: `{runtime_fields.get('last_result')}`.",
        f"- Task to run: `{task.get('Task To Run')}`.",
        "",
        "This report verifies the weekday post-close fresh-window quote-import scheduler and wrapper contents. It does not run scanners, append rows, enable live validation, enable auto-track, submit broker orders, change proof bars, or promote lanes.",
        "",
    ]
    blockers = report.get("blockers") if isinstance(report.get("blockers"), list) else []
    if blockers:
        lines.extend(["## Blockers", ""])
        lines.extend(f"- `{item}`" for item in blockers)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


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
    parser = argparse.ArgumentParser(description="Verify fresh-window ThetaData import scheduler health.")
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
    return 0 if report["status"] == "fresh_window_import_scheduler_ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
