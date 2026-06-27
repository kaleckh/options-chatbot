from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
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


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def _norm(value: Any) -> str:
    return str(value or "").strip()


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
    prohibited_tokens = [token for token in ("--append", "OPTIONS_SCAN_AUTO_TRACK=1") if token in text]
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
    status, blockers = _status_for(fields, returncode=returncode)
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
    return {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "status": status,
        "blockers": blockers,
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
    lines = [
        "# Regular Options Strict Forward 30 Scheduler Health",
        "",
        f"Status: `{report.get('status')}`.",
        "",
        f"- Task name: `{report.get('task_name')}`.",
        f"- Scheduled task state: `{task.get('Scheduled Task State')}`.",
        f"- Runtime status: `{task.get('Status')}`.",
        f"- Next run time: `{task.get('Next Run Time')}`.",
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
