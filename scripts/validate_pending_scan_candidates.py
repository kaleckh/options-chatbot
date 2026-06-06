from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_env import load_local_env
from scripts.candidate_lifecycle import STATUS_PENDING_LIVE_VALIDATION
from scripts.pending_audit_candidates import (
    DEFAULT_DISPOSITION_FILE,
    DEFAULT_FILL_ATTEMPT_FILE,
    DEFAULT_QUEUE_FILE,
    append_lane_profitability_gate_validation_rows,
    append_circuit_breaker_validation_rows,
    append_validation_attempt_rows,
    latest_candidate_rows,
    write_validation_disposition_report,
)
from scripts.lane_profitability_gate import (
    DEFAULT_LANE_GATE_REPORT,
    candidate_gate_decision,
    lane_gate_report_health,
    load_lane_gate_report,
)
from scripts.lane_promotion_state import (
    DEFAULT_LANE_PROMOTION_REPORT,
    LANE_PROMOTION_DIAGNOSTIC_STATUS,
    LANE_PROMOTION_PAPER_EVIDENCE_STATUS,
    LANE_PROMOTION_PAPER_ONLY_STATUS,
    candidate_promotion_decision,
    lane_promotion_report_health,
    load_lane_promotion_report,
)
from scripts import build_current_policy_circuit_breaker as circuit_breaker
from supervised_scan import scan_playbook_fresh_live_validation_enabled
from us_equity_market_calendar import is_us_equity_market_day


LOG_SCAN_SCRIPT = ROOT / "scripts" / "log_scan_picks.py"


def _parse_date(value: str | None) -> date:
    if not value:
        return datetime.now().date()
    return date.fromisoformat(value)


def _candidate_scan_date(row: dict[str, Any]) -> str:
    generated = str(row.get("audit_generated_at_utc") or "").strip()
    if generated:
        return generated[:10]
    recorded = str(row.get("queue_recorded_at_utc") or "").strip()
    return recorded[:10]


def pending_playbooks_for_date(scan_date: date, *, queue_file: Path = DEFAULT_QUEUE_FILE) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in latest_candidate_rows(queue_file):
        if str(row.get("candidate_status") or "") != STATUS_PENDING_LIVE_VALIDATION:
            continue
        playbook_id = str(row.get("playbook_id") or "").strip()
        if not scan_playbook_fresh_live_validation_enabled(playbook_id):
            continue
        if _candidate_scan_date(row) != scan_date.isoformat():
            continue
        grouped[playbook_id].append(row)
    return dict(grouped)


def _market_is_open_now() -> bool:
    load_local_env(ROOT)
    try:
        import options_chatbot as oc

        return bool(oc._market_is_open())
    except Exception:
        return False


def _run_playbook_validation(playbook_id: str) -> int:
    env = dict(os.environ)
    env["OPTIONS_SCAN_PLAYBOOK"] = playbook_id
    env["OPTIONS_SCAN_AUTO_TRACK"] = "1"
    env["OPTIONS_SCAN_ENFORCE_PORTFOLIO_CAPS"] = "1"
    env["OPTIONS_ENFORCE_LANE_PROFITABILITY_GATE"] = "1"
    env["OPTIONS_SCAN_VALIDATION_SOURCE"] = "pending_candidate_queue"
    completed = subprocess.run(
        [sys.executable, str(LOG_SCAN_SCRIPT)],
        cwd=str(ROOT),
        env=env,
        check=False,
    )
    return int(completed.returncode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate pending audit candidates during a fresh market-hours scan."
    )
    parser.add_argument("--date", dest="scan_date", help="YYYY-MM-DD audit date to validate; defaults to today.")
    parser.add_argument("--queue-file", type=Path, default=DEFAULT_QUEUE_FILE)
    parser.add_argument("--fill-attempt-file", type=Path, default=DEFAULT_FILL_ATTEMPT_FILE)
    parser.add_argument("--disposition-file", type=Path, default=DEFAULT_DISPOSITION_FILE)
    parser.add_argument("--circuit-breaker", type=Path, default=circuit_breaker.DEFAULT_CIRCUIT_BREAKER)
    parser.add_argument("--lane-gate-report", type=Path, default=DEFAULT_LANE_GATE_REPORT)
    parser.add_argument("--lane-promotion-report", type=Path, default=DEFAULT_LANE_PROMOTION_REPORT)
    parser.add_argument("--ignore-lane-profitability-gate", action="store_true")
    parser.add_argument("--ignore-lane-promotion-state", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    scan_date = _parse_date(args.scan_date)
    stamp = datetime.now().isoformat(timespec="seconds")
    if not is_us_equity_market_day(scan_date):
        print(f"{stamp} skip market-closed pending_validation_date={scan_date.isoformat()}")
        return 0
    grouped = pending_playbooks_for_date(scan_date, queue_file=args.queue_file)
    if not grouped:
        print(f"{stamp} no pending candidates for validation date={scan_date.isoformat()}")
        return 0
    if not _market_is_open_now():
        print(
            f"{stamp} skip market-not-open pending_validation_date={scan_date.isoformat()} "
            f"playbooks={','.join(sorted(grouped))}"
        )
        return 0

    print(
        f"{stamp} validating pending candidates date={scan_date.isoformat()} "
        f"playbooks={','.join(sorted(grouped))} candidates={sum(len(rows) for rows in grouped.values())}"
    )
    if args.dry_run:
        print("dry-run: pending candidate validation scans not started")
        return 0

    breaker_payload: dict[str, Any] = circuit_breaker.load_report(args.circuit_breaker)
    validation_hold_playbooks = circuit_breaker.validation_hold_playbooks(breaker_payload)
    lane_gate_report = None if args.ignore_lane_profitability_gate else load_lane_gate_report(args.lane_gate_report)
    ignore_promotion_state = args.ignore_lane_profitability_gate or args.ignore_lane_promotion_state
    lane_promotion_report = None if ignore_promotion_state else load_lane_promotion_report(args.lane_promotion_report)
    lane_gate_health = (
        {"usable": True, "reason": "lane_profitability_gate_ignored"}
        if args.ignore_lane_profitability_gate
        else lane_gate_report_health(lane_gate_report)
    )
    lane_promotion_health = (
        {"usable": True, "reason": "lane_promotion_state_ignored"}
        if ignore_promotion_state
        else lane_promotion_report_health(lane_promotion_report)
    )

    failures = 0
    if not args.ignore_lane_profitability_gate and not bool(lane_gate_health.get("usable")):
        failures += 1
        print(
            f"{datetime.now().isoformat(timespec='seconds')} "
            f"lane_profitability_gate_report_unusable validation_fail_closed "
            f"reason={lane_gate_health.get('reason')} "
            f"generated_at_utc={lane_gate_health.get('generated_at_utc')} "
            f"age_hours={lane_gate_health.get('age_hours')}"
        )
    if not ignore_promotion_state and not bool(lane_promotion_health.get("usable")):
        failures += 1
        print(
            f"{datetime.now().isoformat(timespec='seconds')} "
            f"lane_promotion_state_report_unusable validation_fail_closed "
            f"reason={lane_promotion_health.get('reason')} "
            f"generated_at_utc={lane_promotion_health.get('generated_at_utc')} "
            f"age_hours={lane_promotion_health.get('age_hours')}"
        )
    for playbook_id in sorted(grouped):
        rows_to_validate = list(grouped[playbook_id])
        if not args.ignore_lane_profitability_gate:
            blocked_rows: list[dict[str, Any]] = []
            blocked_decisions: dict[str, dict[str, Any]] = {}
            allowed_rows: list[dict[str, Any]] = []
            for row in rows_to_validate:
                decision = candidate_gate_decision(
                    playbook_id=playbook_id,
                    candidate=row,
                    report=lane_gate_report,
                    require_fresh_report=True,
                    probation_paper_only=ignore_promotion_state,
                    require_present_self_guardrail_metrics=True,
                )
                if decision.get("allowed") and not ignore_promotion_state:
                    promotion_decision = candidate_promotion_decision(
                        playbook_id=playbook_id,
                        report=lane_promotion_report,
                        require_fresh_report=True,
                    )
                    promotion_decision["lane_profitability_gate_decision"] = decision
                    if (
                        str(promotion_decision.get("candidate_status") or "")
                        in {LANE_PROMOTION_DIAGNOSTIC_STATUS, LANE_PROMOTION_PAPER_EVIDENCE_STATUS}
                    ):
                        promotion_decision = dict(promotion_decision)
                        promotion_decision["candidate_status"] = LANE_PROMOTION_PAPER_ONLY_STATUS
                    decision = promotion_decision
                if decision.get("allowed"):
                    allowed_rows.append(row)
                    continue
                blocked_rows.append(row)
                key = str(row.get("candidate_key") or "")
                if key:
                    blocked_decisions[key] = decision
            if blocked_rows:
                appended = append_lane_profitability_gate_validation_rows(
                    blocked_rows,
                    queue_file=args.queue_file,
                    decisions=blocked_decisions,
                )
                print(
                    f"{datetime.now().isoformat(timespec='seconds')} "
                    f"playbook={playbook_id} promotion_safety_paper_only_rows={appended}"
                )
            rows_to_validate = allowed_rows
            if not rows_to_validate:
                continue

        if playbook_id in validation_hold_playbooks:
            appended = append_circuit_breaker_validation_rows(
                rows_to_validate,
                queue_file=args.queue_file,
                playbook_id=playbook_id,
                circuit_breaker=breaker_payload,
            )
            print(
                f"{datetime.now().isoformat(timespec='seconds')} "
                f"playbook={playbook_id} circuit_breaker_paper_only_rows={appended}"
            )
            continue
        exit_code = _run_playbook_validation(playbook_id)
        appended = append_validation_attempt_rows(
            rows_to_validate,
            queue_file=args.queue_file,
            playbook_id=playbook_id,
            exit_code=exit_code,
        )
        print(
            f"{datetime.now().isoformat(timespec='seconds')} "
            f"playbook={playbook_id} validation_status_rows={appended}"
        )
        if exit_code != 0:
            failures += 1
            print(f"{datetime.now().isoformat(timespec='seconds')} playbook={playbook_id} failed exit={exit_code}")
    disposition = write_validation_disposition_report(
        queue_file=args.queue_file,
        fill_attempt_file=args.fill_attempt_file,
        output_file=args.disposition_file,
        scan_date=scan_date.isoformat(),
    )
    print(
        f"{datetime.now().isoformat(timespec='seconds')} "
        f"validation_disposition_file={args.disposition_file} "
        f"candidates={disposition['summary']['candidate_count']}"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
