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


DAILY_OP_STEPS: tuple[dict[str, Any], ...] = (
    {
        "id": "open_risk_exit_evidence_plan",
        "label": "Open-risk exit-evidence plan",
        "command": [sys.executable, "scripts/build_regular_options_open_risk_resolution_plan.py"],
        "read_only_safe": True,
    },
    {
        "id": "suggested_trade_review_plan",
        "label": "Suggested-trade review plan",
        "command": [sys.executable, "scripts/build_regular_options_suggested_trade_review_plan.py"],
        "read_only_safe": True,
    },
    {
        "id": "fill_attempt_evidence_capture_plan",
        "label": "Fill-attempt evidence capture plan",
        "command": [sys.executable, "scripts/build_regular_options_fill_attempt_evidence_capture_plan.py"],
        "read_only_safe": True,
    },
    {
        "id": "paper_shadow_monitor",
        "label": "Paper-shadow entry-filter monitor",
        "command": [sys.executable, "scripts/monitor_current_policy_entry_filter_paper.py"],
        "read_only_safe": True,
    },
    {
        "id": "paper_shortlist_gate",
        "label": "Paper-shortlist release gate",
        "command": [sys.executable, "scripts/build_regular_options_paper_shortlist.py", "--strict-gate"],
        "read_only_safe": True,
    },
    {
        "id": "fresh_evidence_loop",
        "label": "Fresh executable evidence loop",
        "command": [sys.executable, "scripts/build_regular_options_fresh_evidence_loop.py"],
        "read_only_safe": True,
    },
    {
        "id": "candidate_outcome_ledger",
        "label": "Candidate outcome ledger",
        "command": [sys.executable, "scripts/build_regular_options_candidate_outcome_ledger.py"],
        "read_only_safe": True,
    },
    {
        "id": "operator_gateboard",
        "label": "Operator gateboard",
        "command": [sys.executable, "scripts/build_project_operator_gateboard.py"],
        "read_only_safe": True,
    },
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


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
            "command": " ".join(step["command"]),
            "read_only_safe": bool(step["read_only_safe"]),
            "returncode": result.returncode,
            "status": "pass" if result.returncode == 0 else "fail",
            "stdout_tail": result.stdout.strip().splitlines()[-5:],
            "stderr_tail": result.stderr.strip().splitlines()[-5:],
        }
        results.append(step_result)
        if result.returncode != 0 and stop_on_failure:
            break
    failed = [step for step in results if step["status"] == "fail"]
    return {
        "report_id": REPORT_ID,
        "status": "failed" if failed else "completed",
        "started_at_utc": started,
        "completed_at_utc": _utc_now_iso(),
        "step_count": len(results),
        "failed_step_count": len(failed),
        "steps": results,
        "boundary": (
            "This runner refreshes read-only operator artifacts and row plans. "
            "It does not submit broker orders, create trades, mutate tracked-position rows, "
            "change scanner policy, or lower proof bars."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run regular-options daily operator chores in order.")
    parser.add_argument("--continue-on-failure", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = run_daily_ops(stop_on_failure=not args.continue_on_failure)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"{REPORT_ID}: {report['status']}")
        for step in report["steps"]:
            print(f"- {step['id']}: {step['status']}")
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
