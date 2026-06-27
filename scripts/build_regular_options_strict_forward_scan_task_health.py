from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_regular_options_strict_forward_30_scheduler_health import parse_schtasks_list


REPORT_ID = "regular_options_strict_forward_scan_task_health"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-strict-forward-scan-task-health.md"

EXPECTED_TASKS = {
    r"\OptionsScanPicks": {
        "batch_file": ROOT / "scripts" / "run_scan_picks.bat",
        "start_time": "11:00:00 AM",
    },
    r"\OptionsScanPicksSafetyNet": {
        "batch_file": ROOT / "scripts" / "run_scan_picks_safety_net.bat",
        "start_time": "11:30:00 AM",
    },
}

EXPECTED_BATCH_STEPS = [
    "set OPTIONS_SCAN_AUTO_TRACK=0",
    "set OPTIONS_SCAN_ENFORCE_PORTFOLIO_CAPS=1",
    "set OPTIONS_ENFORCE_LANE_PROFITABILITY_GATE=1",
    "scripts\\run_forward_cohort_scan_sweep.py --force",
    "scripts\\run_regular_options_strict_forward_30_auto_window_collector.py --skip-scan-sweep --json",
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


def query_task(task_name: str) -> tuple[int, str, str]:
    result = subprocess.run(
        ["schtasks", "/Query", "/TN", task_name, "/FO", "LIST", "/V"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def _inspect_batch_file(path: Path) -> dict[str, Any]:
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
    prohibited = [token for token in ("--append", "OPTIONS_SCAN_AUTO_TRACK=1") if token in text]
    report.update(
        {
            "status": "loaded",
            "missing_steps": missing,
            "order_blockers": order_blockers,
            "prohibited_tokens_present": prohibited,
        }
    )
    return report


def _task_blockers(task_name: str, fields: dict[str, str], *, returncode: int, expected_batch: Path, expected_start: str) -> list[str]:
    blockers: list[str] = []
    if returncode != 0:
        return ["schtasks_query_failed"]
    if _norm(fields.get("TaskName")) != task_name:
        blockers.append("task_name_mismatch")
    if _norm(fields.get("Scheduled Task State")).lower() != "enabled":
        blockers.append("task_not_enabled")
    if _norm(fields.get("Status")).lower() not in {"ready", "running"}:
        blockers.append("task_not_ready_or_running")
    if _norm(fields.get("Task To Run")).lower() != str(expected_batch).lower():
        blockers.append("task_to_run_mismatch")
    if expected_start and _norm(fields.get("Start Time")) != expected_start:
        blockers.append("start_time_mismatch")
    days = _norm(fields.get("Days")).upper()
    for day in ("MON", "TUE", "WED", "THU", "FRI"):
        if day not in days:
            blockers.append(f"weekday_missing:{day}")
    return blockers


def _batch_blockers(batch: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if batch.get("status") != "loaded":
        blockers.append("batch_file_missing_or_unreadable")
    for step in batch.get("missing_steps") if isinstance(batch.get("missing_steps"), list) else []:
        blockers.append(f"batch_missing_step:{step}")
    for blocker in batch.get("order_blockers") if isinstance(batch.get("order_blockers"), list) else []:
        blockers.append(blocker)
    for token in batch.get("prohibited_tokens_present") if isinstance(batch.get("prohibited_tokens_present"), list) else []:
        blockers.append(f"batch_prohibited_token:{token}")
    return blockers


def build_report(*, generated_at_utc: str | None = None) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    task_reports: dict[str, Any] = {}
    all_blockers: list[str] = []
    for task_name, expected in EXPECTED_TASKS.items():
        returncode, stdout, stderr = query_task(task_name)
        fields = parse_schtasks_list(stdout)
        batch_path = expected["batch_file"]
        batch = _inspect_batch_file(batch_path)
        blockers = [
            *_task_blockers(
                task_name,
                fields,
                returncode=returncode,
                expected_batch=batch_path,
                expected_start=str(expected["start_time"]),
            ),
            *_batch_blockers(batch),
        ]
        task_reports[task_name] = {
            "status": "ready" if not blockers else "blocked",
            "blockers": blockers,
            "query_returncode": returncode,
            "query_stderr": stderr.strip().splitlines()[-5:],
            "task": fields,
            "batch_file": batch,
        }
        all_blockers.extend(f"{task_name}:{blocker}" for blocker in blockers)
    status = "scan_tasks_ready_for_next_market_window" if not all_blockers else "scan_task_config_blocked"
    return {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "status": status,
        "blockers": all_blockers,
        "task_reports": task_reports,
        "expected": {
            "tasks": {
                name: {"task_to_run": str(meta["batch_file"]), "start_time": meta["start_time"]}
                for name, meta in EXPECTED_TASKS.items()
            },
            "batch_steps": EXPECTED_BATCH_STEPS,
            "acceptable_statuses": ["Ready", "Running"],
            "scheduled_task_state": "Enabled",
            "weekdays_required": ["MON", "TUE", "WED", "THU", "FRI"],
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
            "do_not_append_from_scan_task_health",
            "do_not_enable_live_validation_from_scan_task_health",
            "do_not_enable_auto_track_from_scan_task_health",
            "do_not_submit_broker_orders_from_scan_task_health",
            "do_not_import_quotes_from_scan_task_health",
            "do_not_lower_proof_bars_from_scan_task_health",
            "do_not_treat_historical_rows_as_forward_proof",
        ],
        "artifacts": {},
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Strict Forward Scan Task Health",
        "",
        f"Status: `{report.get('status')}`.",
        "",
        "This read-only report verifies the two scheduled scan tasks that feed strict-forward collection. It does not run scans, append rows, enable live validation, enable auto-track, submit broker orders, import quotes, lower proof bars, or count historical rows as forward proof.",
        "",
        "## Tasks",
        "",
    ]
    for task_name, task_report in sorted((report.get("task_reports") or {}).items()):
        if not isinstance(task_report, dict):
            continue
        task = task_report.get("task") if isinstance(task_report.get("task"), dict) else {}
        lines.extend(
            [
                f"### `{task_name}`",
                "",
                f"- Status: `{task_report.get('status')}`.",
                f"- Runtime status: `{task.get('Status')}`.",
                f"- Scheduled state: `{task.get('Scheduled Task State')}`.",
                f"- Next run time: `{task.get('Next Run Time')}`.",
                f"- Last result: `{task.get('Last Result')}`.",
                f"- Task to run: `{task.get('Task To Run')}`.",
                f"- Start time: `{task.get('Start Time')}`.",
                f"- Batch status: `{_batch_status(task_report)}`.",
                "",
            ]
        )
        blockers = task_report.get("blockers") if isinstance(task_report.get("blockers"), list) else []
        if blockers:
            lines.extend(f"- Blocker: `{item}`." for item in blockers)
            lines.append("")
    blockers = report.get("blockers") if isinstance(report.get("blockers"), list) else []
    lines.extend(["## Blockers", ""])
    lines.extend(f"- `{item}`" for item in blockers) if blockers else lines.append("- None.")
    lines.append("")
    return "\n".join(lines)


def _batch_status(task_report: dict[str, Any]) -> str:
    batch = task_report.get("batch_file") if isinstance(task_report.get("batch_file"), dict) else {}
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
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(payload)
    json_path.write_text(serialized, encoding="utf8")
    latest_json.write_text(serialized, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return artifacts


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify strict-forward scheduled scan task health.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_report()
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0 if report["status"] == "scan_tasks_ready_for_next_market_window" else 1


if __name__ == "__main__":
    raise SystemExit(main())
