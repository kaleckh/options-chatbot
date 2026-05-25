from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from profit_loop_automation import run_profit_loop_canary
from workspace_tempdir import WorkspaceTempDir


def _open_strict_issues(result: dict) -> list[dict]:
    issues: list[dict] = []
    for step in result.get("steps") or []:
        if not isinstance(step, dict):
            continue
        for issue in step.get("issues") or []:
            if isinstance(issue, dict):
                issues.append(issue)
        targeted_issue = step.get("targeted_issue")
        if isinstance(targeted_issue, dict):
            issues.append(targeted_issue)

    strict_issues = []
    seen_issue_keys: set[tuple[str, str]] = set()
    for issue in issues:
        severity = str(issue.get("severity") or "").strip().lower()
        status = str(issue.get("status") or "open").strip().lower()
        if severity in {"high", "critical"} and status not in {"resolved", "closed"}:
            issue_id = str(issue.get("issue_id") or "").strip()
            issue_key = (
                ("issue_id", issue_id)
                if issue_id
                else ("payload", json.dumps(issue, sort_keys=True, default=str))
            )
            if issue_key in seen_issue_keys:
                continue
            seen_issue_keys.add(issue_key)
            strict_issues.append(issue)
    return strict_issues


def build_strict_gate_summary(result: dict) -> dict:
    strict_issues = _open_strict_issues(result)
    base_exit_code = int(result.get("exit_code") or 0)
    passed = base_exit_code == 0 and not strict_issues
    return {
        "status": "passed" if passed else "failed",
        "passed": passed,
        "base_exit_code": base_exit_code,
        "strict_issue_count": len(strict_issues),
        "strict_issue_ids": [str(issue.get("issue_id") or "") for issue in strict_issues],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the three profit-loop automation steps in sequence.")
    parser.add_argument("--state-dir", default=None)
    parser.add_argument("--temp-state-dir", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--strict-gate",
        action="store_true",
        help="Exit nonzero if high/critical open issues are observed, even when the canary ran successfully.",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Print the canary JSON report but exit 0 even when the canary found unhealthy steps.",
    )
    args = parser.parse_args(argv)

    if args.state_dir and args.temp_state_dir:
        raise SystemExit("--state-dir and --temp-state-dir are mutually exclusive")

    state_dir = args.state_dir
    if args.temp_state_dir:
        state_dir = WorkspaceTempDir(prefix="profit-loop-canary").name

    result = run_profit_loop_canary(state_dir=state_dir, dry_run=bool(args.dry_run))
    if args.strict_gate:
        result["strict_gate"] = build_strict_gate_summary(result)
    print(json.dumps(result, indent=2))
    if args.report_only:
        return 0
    if args.strict_gate and not result["strict_gate"]["passed"]:
        return 2
    return int(result.get("exit_code") or 0)


if __name__ == "__main__":
    raise SystemExit(main())
