from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_daily_ops"
DEFAULT_OUTPUT_JSON = ROOT / "data" / "forward-tracking" / "regular_options_daily_ops_latest.json"
DEFAULT_OUTPUT_MD = ROOT / "docs" / "regular-options-daily-ops.md"


DAILY_OP_STEPS: tuple[dict[str, Any], ...] = (
    {
        "id": "point_in_time_earnings_calendar",
        "label": "Point-in-time earnings calendar readiness",
        "stage": "historical_input_surface_tracking",
        "command": [sys.executable, "scripts/build_regular_options_point_in_time_earnings_calendar.py"],
        "read_only_safe": True,
    },
    {
        "id": "earnings_calendar_source_repair_packet",
        "label": "Earnings calendar source-repair packet",
        "stage": "historical_input_surface_tracking",
        "command": [sys.executable, "scripts/build_regular_options_earnings_calendar_source_repair_packet.py"],
        "read_only_safe": True,
    },
    {
        "id": "historical_scanner_input_surface_tracker",
        "label": "Historical scanner input-surface tracker",
        "stage": "historical_input_surface_tracking",
        "command": [sys.executable, "scripts/build_regular_options_historical_scanner_input_surface_tracker.py"],
        "read_only_safe": True,
    },
    {
        "id": "historical_frozen_scanner_replay_adapter",
        "label": "Historical frozen scanner replay adapter",
        "stage": "historical_candidate_generation_audit",
        "command": [sys.executable, "scripts/build_regular_options_historical_frozen_scanner_replay_adapter.py"],
        "read_only_safe": True,
    },
    {
        "id": "historical_frozen_adapter_exit_quote_repair_demand",
        "label": "Historical frozen adapter exit quote repair demand",
        "stage": "historical_candidate_generation_audit",
        "command": [sys.executable, "scripts/build_regular_options_historical_frozen_adapter_exit_quote_repair_demand.py"],
        "read_only_safe": True,
    },
    {
        "id": "frozen_daily_candidate_decisions",
        "label": "Frozen daily candidate decisions",
        "stage": "historical_candidate_generation_audit",
        "command": [sys.executable, "scripts/build_regular_options_13_symbol_frozen_daily_candidate_decisions.py"],
        "read_only_safe": True,
    },
    {
        "id": "frozen_candidate_generation_entrypoint",
        "label": "Frozen candidate-generation entrypoint",
        "stage": "historical_candidate_generation_audit",
        "command": [sys.executable, "scripts/regular_options_frozen_candidate_generation_entrypoint.py", "--no-write"],
        "read_only_safe": True,
    },
    {
        "id": "frozen_candidate_generation_source_surface",
        "label": "Frozen candidate-generation source surface",
        "stage": "historical_candidate_generation_audit",
        "command": [sys.executable, "scripts/build_regular_options_13_symbol_frozen_candidate_generation_source_surface.py", "--no-write"],
        "read_only_safe": True,
    },
    {
        "id": "frozen_candidate_generation_engine",
        "label": "Frozen candidate-generation engine",
        "stage": "historical_candidate_generation_audit",
        "command": [sys.executable, "scripts/build_regular_options_13_symbol_frozen_candidate_generation_engine.py", "--no-write"],
        "read_only_safe": True,
    },
    {
        "id": "historical_simulated_forward_audit",
        "label": "Historical simulated-forward audit",
        "stage": "historical_candidate_generation_audit",
        "command": [sys.executable, "scripts/build_regular_options_historical_simulated_forward_audit.py"],
        "read_only_safe": True,
    },
    {
        "id": "historical_profitability_filter_iteration",
        "label": "Historical profitability filter iteration",
        "stage": "historical_candidate_generation_audit",
        "command": [sys.executable, "scripts/build_regular_options_historical_profitability_filter_iteration.py", "--record-consumption"],
        "read_only_safe": True,
    },
    {
        "id": "historical_filtered_simulated_forward_audit",
        "label": "Historical filtered simulated-forward audit",
        "stage": "historical_candidate_generation_audit",
        "command": [sys.executable, "scripts/build_regular_options_historical_filtered_simulated_forward_audit.py"],
        "read_only_safe": True,
    },
    {
        "id": "filtered_forward_paper_shadow_tracker",
        "label": "Filtered forward paper-shadow tracker",
        "stage": "paper_shadow_collection",
        "command": [sys.executable, "scripts/build_regular_options_filtered_forward_paper_shadow_tracker.py"],
        "read_only_safe": True,
    },
    {
        "id": "filtered_forward_exit_evidence_capture",
        "label": "Filtered forward exit-evidence capture",
        "stage": "exit_evidence_capture",
        "command": [sys.executable, "scripts/capture_regular_options_filtered_forward_exit_evidence.py", "--no-write"],
        "read_only_safe": True,
    },
    {
        "id": "filtered_forward_evidence_bar_evaluation",
        "label": "Filtered forward evidence-bar evaluation",
        "stage": "paper_shadow_collection",
        "command": [sys.executable, "scripts/build_regular_options_filtered_forward_evidence_bar_evaluation.py"],
        "read_only_safe": True,
    },
    {
        "id": "open_risk_exit_evidence_plan",
        "label": "Open-risk exit-evidence plan",
        "stage": "exit_evidence_capture",
        "command": [sys.executable, "scripts/build_regular_options_open_risk_resolution_plan.py"],
        "read_only_safe": True,
    },
    {
        "id": "suggested_trade_review_plan",
        "label": "Suggested-trade review plan",
        "stage": "suggested_trade_review_plan_execution",
        "command": [sys.executable, "scripts/build_regular_options_suggested_trade_review_plan.py"],
        "read_only_safe": True,
    },
    {
        "id": "fill_attempt_evidence_capture_plan",
        "label": "Fill-attempt evidence capture plan",
        "stage": "paper_shadow_collection",
        "command": [sys.executable, "scripts/build_regular_options_fill_attempt_evidence_capture_plan.py"],
        "read_only_safe": True,
    },
    {
        "id": "paper_shadow_monitor",
        "label": "Paper-shadow entry-filter monitor",
        "stage": "paper_shadow_collection",
        "command": [sys.executable, "scripts/monitor_current_policy_entry_filter_paper.py"],
        "read_only_safe": True,
    },
    {
        "id": "paper_shortlist_gate",
        "label": "Paper-shortlist release gate",
        "stage": "paper_shadow_collection",
        "command": [sys.executable, "scripts/build_regular_options_paper_shortlist.py", "--strict-gate"],
        "read_only_safe": True,
    },
    {
        "id": "fresh_evidence_loop",
        "label": "Fresh executable evidence loop",
        "stage": "paper_shadow_collection",
        "command": [sys.executable, "scripts/build_regular_options_fresh_evidence_loop.py"],
        "read_only_safe": True,
    },
    {
        "id": "candidate_outcome_ledger",
        "label": "Candidate outcome ledger",
        "stage": "paper_shadow_collection",
        "command": [sys.executable, "scripts/build_regular_options_candidate_outcome_ledger.py"],
        "read_only_safe": True,
    },
    {
        "id": "scheduled_scan_heartbeat_health",
        "label": "Scheduled-scan heartbeat health",
        "stage": "heartbeat_check",
        "command": [sys.executable, "scripts/scan_heartbeat.py", "--health"],
        "read_only_safe": True,
        "continue_after_failure": True,
    },
    {
        "id": "operator_gateboard",
        "label": "Operator gateboard",
        "stage": "gateboard_refresh",
        "command": [sys.executable, "scripts/build_project_operator_gateboard.py"],
        "read_only_safe": True,
    },
)

REQUIRED_STAGE_ORDER: tuple[str, ...] = (
    "historical_input_surface_tracking",
    "historical_candidate_generation_audit",
    "exit_evidence_capture",
    "suggested_trade_review_plan_execution",
    "paper_shadow_collection",
    "heartbeat_check",
    "gateboard_refresh",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Daily Ops",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Started: `{report.get('started_at_utc')}`.",
        f"- Completed: `{report.get('completed_at_utc')}`.",
        f"- Steps: `{report.get('step_count')}`.",
        f"- Failed steps: `{report.get('failed_step_count')}`.",
        "",
        "## Steps",
        "",
        "| Step | Stage | Status | Return Code |",
        "|---|---|---:|---:|",
    ]
    for step in report.get("steps", []):
        if not isinstance(step, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{step.get('id')}`",
                    f"`{step.get('stage')}`",
                    f"`{step.get('status')}`",
                    f"`{step.get('returncode')}`",
                ]
            )
            + " |"
        )
    lines.extend(["", "## Boundary", "", str(report.get("boundary") or ""), ""])
    return "\n".join(lines)


def write_outputs(
    report: dict[str, Any],
    *,
    output_json: Path = DEFAULT_OUTPUT_JSON,
    output_md: Path = DEFAULT_OUTPUT_MD,
) -> dict[str, str]:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "latest_json": _rel(output_json),
        "latest_markdown": _rel(output_md),
    }
    report["artifacts"] = artifacts
    output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    output_md.write_text(render_markdown(report), encoding="utf8")
    return artifacts


def run_daily_ops(*, stop_on_failure: bool = True) -> dict[str, Any]:
    started = _utc_now_iso()
    results: list[dict[str, Any]] = []
    for step in DAILY_OP_STEPS:
        result = subprocess.run(
            list(step["command"]),
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        step_result = {
            "id": step["id"],
            "label": step["label"],
            "stage": step["stage"],
            "command": " ".join(step["command"]),
            "read_only_safe": bool(step["read_only_safe"]),
            "continue_after_failure": bool(step.get("continue_after_failure")),
            "returncode": result.returncode,
            "status": "pass" if result.returncode == 0 else "fail",
            "stdout_tail": result.stdout.strip().splitlines()[-5:],
            "stderr_tail": result.stderr.strip().splitlines()[-5:],
        }
        results.append(step_result)
        if result.returncode != 0 and stop_on_failure and not bool(step.get("continue_after_failure")):
            break
    failed = [step for step in results if step["status"] == "fail"]
    return {
        "report_id": REPORT_ID,
        "status": "failed" if failed else "completed",
        "started_at_utc": started,
        "completed_at_utc": _utc_now_iso(),
        "step_count": len(results),
        "failed_step_count": len(failed),
        "required_stage_order": list(REQUIRED_STAGE_ORDER),
        "steps": results,
        "boundary": (
            "This runner refreshes read-only operator artifacts and row plans. "
            "It refreshes point-in-time earnings readiness and source-repair planning before tracking historical scanner input source-surface coverage. "
            "It refreshes the frozen candidate-generation replay, source-surface, engine, and historical simulated-forward audit every run. "
            "It also tracks the historical profitability filter iteration and filtered simulated-forward audit every run. "
            "It tracks prospective matches to the filtered policy as forward paper-shadow dashboard rows. "
            "It refreshes filtered-forward exit evidence in no-write mode and evaluates the pre-registered forward evidence bar. "
            "It checks scheduled-scan heartbeat health before the gateboard refresh. "
            "It does not submit broker orders, create trades, mutate tracked-position rows, "
            "import quotes, change scanner policy, or lower proof bars."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run regular-options daily operator chores in order.")
    parser.add_argument("--continue-on-failure", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = run_daily_ops(stop_on_failure=not args.continue_on_failure)
    write_outputs(report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"{REPORT_ID}: {report['status']}")
        for step in report["steps"]:
            print(f"- {step['id']}: {step['status']}")
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
