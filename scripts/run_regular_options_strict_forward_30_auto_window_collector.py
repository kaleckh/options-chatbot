from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_regular_options_strict_forward_30_market_window_collector as collector
from us_equity_market_calendar import is_us_equity_market_day, previous_market_day


REPORT_ID = "regular_options_strict_forward_30_auto_window_collector"
MARKET_TZ = ZoneInfo("America/New_York")
MARKET_OPEN_ET = time(9, 30)
MARKET_CLOSE_ET = time(16, 0)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-strict-forward-30-auto-window-collector.md"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


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


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _paths_match(reported: str, actual: Path) -> bool:
    if not reported:
        return False
    if reported == _rel(actual):
        return True
    try:
        return Path(reported).resolve() == actual.resolve()
    except OSError:
        return False


def pending_candidate_review(
    *,
    candidate_output_path: Path = collector.goal_loop.capture_runner.stager.DEFAULT_OUTPUT,
    capture_latest_path: Path = collector.goal_loop.capture_runner.DEFAULT_CAPTURE_JSON,
) -> dict[str, Any]:
    capture = _load_json(capture_latest_path)
    candidate_sha = _sha256_file(candidate_output_path)
    capture_path = _norm(capture.get("candidate_output_path"))
    capture_sha = _norm(capture.get("candidate_batch_sha256"))
    pending = bool(
        candidate_sha
        and capture.get("status") == "candidate_rows_valid_no_append"
        and _int(capture.get("candidate_rows_staged")) > 0
        and capture.get("candidate_jsonl_exists") is True
        and capture.get("append_requested") is False
        and capture.get("cohort_append_performed") is False
        and _paths_match(capture_path, candidate_output_path)
        and capture_sha == candidate_sha
    )
    return {
        "pending": pending,
        "candidate_jsonl_path": _rel(candidate_output_path),
        "candidate_jsonl_exists": candidate_output_path.exists(),
        "candidate_batch_sha256": candidate_sha,
        "capture_latest_path": _rel(capture_latest_path),
        "capture_status": capture.get("status"),
        "capture_generated_at_utc": capture.get("generated_at_utc"),
        "capture_candidate_rows_staged": _int(capture.get("candidate_rows_staged")),
        "capture_candidate_output_path": capture_path or None,
        "capture_candidate_batch_sha256": capture_sha or None,
    }


def market_window_state(generated_at_utc: str) -> dict[str, Any]:
    now_utc = _parse_utc(generated_at_utc)
    now_et = now_utc.astimezone(MARKET_TZ)
    trade_date = now_et.date()
    is_market_day = is_us_equity_market_day(trade_date)
    open_dt = datetime.combine(trade_date, MARKET_OPEN_ET, tzinfo=MARKET_TZ)
    close_dt = datetime.combine(trade_date, MARKET_CLOSE_ET, tzinfo=MARKET_TZ)
    is_open = bool(is_market_day and open_dt <= now_et < close_dt)
    if is_open:
        status = "open"
        timing_status = "market_window_open"
        default_selection_date = trade_date
    elif is_market_day and now_et < open_dt:
        status = "closed"
        timing_status = "before_market_open"
        default_selection_date = previous_market_day(trade_date)
    else:
        status = "closed"
        timing_status = "after_market_close_or_non_market_day"
        default_selection_date = trade_date if is_market_day and now_et >= close_dt else previous_market_day(trade_date)
    return {
        "market_window_status": status,
        "timing_status": timing_status,
        "market_window_confirmed": is_open,
        "current_time_utc": now_utc.isoformat().replace("+00:00", "Z"),
        "current_time_et": now_et.isoformat(),
        "current_market_date": trade_date.isoformat(),
        "default_selection_date": default_selection_date.isoformat(),
        "current_date_is_market_day": is_market_day,
        "regular_market_open_et": MARKET_OPEN_ET.isoformat(timespec="minutes"),
        "regular_market_close_et": MARKET_CLOSE_ET.isoformat(timespec="minutes"),
    }


def build_report(
    *,
    generated_at_utc: str | None = None,
    max_attempts: int = 1,
    sleep_seconds: float = 0.0,
    skip_scan_sweep: bool = False,
    candidate_output_path: Path = collector.goal_loop.capture_runner.stager.DEFAULT_OUTPUT,
    capture_latest_path: Path = collector.goal_loop.capture_runner.DEFAULT_CAPTURE_JSON,
    collector_latest_path: Path = collector.DEFAULT_OUTPUT_DIR / f"{collector.REPORT_ID}_latest.json",
    write_outputs: bool = True,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOCS_REPORT,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    window = market_window_state(generated_at)
    pending_review = pending_candidate_review(
        candidate_output_path=candidate_output_path,
        capture_latest_path=capture_latest_path,
    )
    if window["market_window_confirmed"] and pending_review["pending"]:
        child = _load_json(collector_latest_path)
        status = "auto_window_collector_paused_pending_candidate_review"
        run_scan_sweep_requested = False
        next_action = "review_candidate_jsonl_and_only_append_with_explicit_operator_approval_token"
    else:
        child = collector.build_report(
            market_window_confirmed=bool(window["market_window_confirmed"]),
            market_window_status=str(window["market_window_status"]),
            selection_date=str(window["default_selection_date"]),
            run_scan_sweep=bool(window["market_window_confirmed"] and not skip_scan_sweep),
            append=False,
            max_attempts=max(1, int(max_attempts)),
            sleep_seconds=max(0.0, float(sleep_seconds)),
            generated_at_utc=generated_at,
            write_outputs=write_outputs,
        )
        status = (
            "auto_window_collector_ran_open_window"
            if window["market_window_confirmed"]
            else "auto_window_collector_waiting_for_open_market_window"
        )
        run_scan_sweep_requested = child.get("run_scan_sweep_requested")
        next_action = child.get("next_action")
    report = {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "status": status,
        "market_window": window,
        "collector_status": child.get("status"),
        "strict_forward_rows": child.get("strict_forward_rows"),
        "required_rows": child.get("required_rows"),
        "remaining_rows": child.get("remaining_rows"),
        "accepted_profitability": child.get("accepted_profitability"),
        "candidate_rows_staged": child.get("candidate_rows_staged"),
        "candidate_jsonl_exists": child.get("candidate_jsonl_exists"),
        "cohort_append_performed": child.get("cohort_append_performed"),
        "run_scan_sweep_requested": run_scan_sweep_requested,
        "skip_scan_sweep_requested": skip_scan_sweep,
        "append_requested": child.get("append_requested"),
        "safety_violations": child.get("safety_violations") if isinstance(child.get("safety_violations"), list) else [],
        "next_action": next_action,
        "pending_candidate_review": pending_review,
        "collector_report": child,
        "prohibited_actions": [
            "do_not_fabricate_forward_rows",
            "do_not_count_historical_rows_as_forward_proof",
            "do_not_lower_proof_bars",
            "do_not_enable_live_validation",
            "do_not_enable_auto_track",
            "do_not_submit_broker_orders",
            "do_not_append_without_existing_guarded_operator_token_path",
        ],
        "artifacts": {},
    }
    if write_outputs:
        report["artifacts"] = write_outputs_report(report, output_dir=output_dir, docs_report=docs_report)
    return report


def render_markdown(report: dict[str, Any]) -> str:
    window = report.get("market_window") if isinstance(report.get("market_window"), dict) else {}
    lines = [
        "# Regular Options Strict Forward 30 Auto-Window Collector",
        "",
        f"Status: `{report.get('status')}`.",
        "",
        f"- Market-window status: `{window.get('market_window_status')}`.",
        f"- Timing status: `{window.get('timing_status')}`.",
        f"- Current market date: `{window.get('current_market_date')}`.",
        f"- Strict completed forward rows: `{report.get('strict_forward_rows')}/{report.get('required_rows')}`.",
        f"- Remaining rows: `{report.get('remaining_rows')}`.",
        f"- Accepted profitability: `{str(bool(report.get('accepted_profitability'))).lower()}`.",
        f"- Collector status: `{report.get('collector_status')}`.",
        f"- Candidate rows staged: `{report.get('candidate_rows_staged')}`.",
        f"- Candidate JSONL exists: `{str(bool(report.get('candidate_jsonl_exists'))).lower()}`.",
        f"- Pending candidate review: `{str(bool(_as_dict(report.get('pending_candidate_review')).get('pending'))).lower()}`.",
        f"- Cohort append performed: `{str(bool(report.get('cohort_append_performed'))).lower()}`.",
        f"- Run scan sweep requested: `{str(bool(report.get('run_scan_sweep_requested'))).lower()}`.",
        f"- Skip scan sweep requested: `{str(bool(report.get('skip_scan_sweep_requested'))).lower()}`.",
        f"- Next action: `{report.get('next_action')}`.",
        "",
        "This wrapper checks the US equity regular market window before invoking the bounded strict-forward collector. Outside the window it refreshes status without scan or append; during an open window it pauses if a current candidate batch is already pending review, otherwise it runs the collector with scan sweep enabled unless `--skip-scan-sweep` is set.",
        "",
    ]
    violations = report.get("safety_violations") if isinstance(report.get("safety_violations"), list) else []
    if violations:
        lines.extend(["## Safety Violations", ""])
        lines.extend(f"- `{item}`" for item in violations)
        lines.append("")
    return "\n".join(lines)


def write_outputs_report(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = str(report.get("generated_at_utc") or _utc_now_iso()).replace("-", "").replace(":", "")
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
    text = render_markdown(payload)
    json_path.write_text(serialized, encoding="utf8")
    latest_json.write_text(serialized, encoding="utf8")
    md_path.write_text(text, encoding="utf8")
    latest_md.write_text(text, encoding="utf8")
    docs_report.write_text(text, encoding="utf8")
    return artifacts


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Auto-window wrapper for the strict-forward 30-row collector.")
    parser.add_argument("--max-attempts", type=int, default=1)
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    parser.add_argument("--skip-scan-sweep", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_report(
        max_attempts=args.max_attempts,
        sleep_seconds=args.sleep_seconds,
        skip_scan_sweep=args.skip_scan_sweep,
        write_outputs=not args.no_write,
        output_dir=args.output_dir,
        docs_report=args.docs_report,
    )
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"{REPORT_ID}: {report['status']}")
        print(f"- collector_status: {report.get('collector_status')}")
        print(f"- strict_forward_rows: {report.get('strict_forward_rows')}/{report.get('required_rows')}")
    return 0 if not report.get("safety_violations") else 1


if __name__ == "__main__":
    raise SystemExit(main())
