from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import append_volatility_expansion_forward_paper_shadow_rows as appender
from scripts import build_phase2_regular_options_forward_paper_shadow_candidate_rows as stager


REPORT_ID = "phase2_regular_options_forward_paper_shadow_capture"
DEFAULT_CAPTURE_JSON = ROOT / "data" / "forward-tracking" / "phase2_regular_options_forward_paper_shadow_capture_latest.json"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-phase2-forward-paper-shadow-capture.md"
FORBIDDEN_RUNTIME_TARGETS = (
    "daily-ops",
    "options:log",
    "validate_pending_scan_candidates",
    "alpaca_paper_trading",
    "broker",
    "submit_order",
    "create_position",
    "auto_track",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_outputs(report: dict[str, Any], latest_json_path: Path, docs_report_path: Path) -> None:
    latest_json_path.parent.mkdir(parents=True, exist_ok=True)
    docs_report_path.parent.mkdir(parents=True, exist_ok=True)
    latest_json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    docs_report_path.write_text(render_markdown(report) + "\n", encoding="utf8")


def build_capture_report(
    *,
    market_window_confirmed: bool = False,
    market_window_status: str = "unknown",
    approval_token: str | None = None,
    append: bool = False,
    dry_run: bool = False,
    source_scan_picks_path: Path = stager.DEFAULT_SOURCE_SCAN_PICKS,
    candidate_output_path: Path = stager.DEFAULT_OUTPUT,
    cohort_log_path: Path = appender.report_builder.DEFAULT_PHASE2_COHORT_LOG,
    latest_json_path: Path = DEFAULT_CAPTURE_JSON,
    docs_report_path: Path = DEFAULT_DOCS_REPORT,
    generated_at_utc: str | None = None,
    write_report: bool = True,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    stage_report = stager.build_stage_report(
        source_scan_picks_path=source_scan_picks_path,
        output_path=candidate_output_path,
        market_window_confirmed=market_window_confirmed,
        market_window_status=market_window_status,
        generated_at_utc=generated_at,
    )
    staged_count = int(stage_report.get("candidate_rows_staged") or 0)
    validation = _as_dict(stage_report.get("validation"))
    append_report: dict[str, Any] | None = None
    reason_codes = [str(code) for code in stage_report.get("reason_codes", [])]
    if staged_count == 0:
        if candidate_output_path.exists():
            candidate_output_path.unlink()
        status = "no_phase2_natural_selections_no_append"
        reason_codes = ["no_phase2_natural_selections"]
    elif not validation.get("append_allowed"):
        status = "candidate_rows_not_append_eligible"
        reason_codes = ["candidate_validation_not_append_allowed"]
    elif not append:
        status = "candidate_rows_valid_no_append"
        reason_codes = ["default_no_append"]
    else:
        append_report = appender.build_append_report(
            candidate_rows_path=candidate_output_path,
            cohort_log_path=cohort_log_path,
            schema_path=appender.report_builder.DEFAULT_PHASE2_SCHEMA,
            approval_token=approval_token,
            market_window_confirmed=market_window_confirmed and market_window_status == "open",
            dry_run=dry_run,
            allowed_lane_ids=appender.report_builder.PHASE2_FROZEN_LANE_IDS,
            generated_at_utc=generated_at,
        )
        status = "append_performed" if append_report.get("cohort_append_performed") else str(append_report.get("status"))
        reason_codes = [str(code) for code in append_report.get("reason_codes", [])]

    report = {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "status": status,
        "reason_codes": reason_codes,
        "market_window_confirmed": market_window_confirmed,
        "market_window_status": market_window_status,
        "source_scan_picks_path": _rel(source_scan_picks_path),
        "candidate_output_path": _rel(candidate_output_path),
        "cohort_log_path": _rel(cohort_log_path),
        "append_requested": append,
        "dry_run": dry_run,
        "stage_report": stage_report,
        "append_report": append_report,
        "candidate_rows_staged": staged_count,
        "candidate_jsonl_exists": candidate_output_path.exists(),
        "candidate_batch_sha256": _sha256_file(candidate_output_path),
        "cohort_log_exists": cohort_log_path.exists(),
        "cohort_append_performed": bool(append_report and append_report.get("cohort_append_performed")),
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
        "forbidden_runtime_targets": list(FORBIDDEN_RUNTIME_TARGETS),
        "writes_performed": [],
    }
    if write_report:
        _write_outputs(report, latest_json_path, docs_report_path)
        report["writes_performed"] = [_rel(latest_json_path), _rel(docs_report_path)]
        latest_json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    return report


def render_markdown(report: dict[str, Any]) -> str:
    validation = _as_dict(_as_dict(report.get("stage_report")).get("validation"))
    append_report = _as_dict(report.get("append_report"))
    lines = [
        "# Phase 2 Forward Paper-Shadow Capture",
        "",
        "Passive capture runner. It reads existing scan-pick artifacts only and does not run the scanner or create trades.",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Candidate rows staged: `{report.get('candidate_rows_staged')}`.",
        f"- Validation append allowed: `{validation.get('append_allowed')}`.",
        f"- Append requested: `{str(report.get('append_requested')).lower()}`.",
        f"- Cohort append performed: `{str(report.get('cohort_append_performed')).lower()}`.",
        f"- Append status: `{append_report.get('status')}`.",
        f"- Live entry allowed: `{str(report.get('live_entry_allowed')).lower()}`.",
        f"- Auto-track allowed: `{str(report.get('auto_track_allowed')).lower()}`.",
        f"- Broker order allowed: `{str(report.get('broker_order_allowed')).lower()}`.",
        f"- Candidate JSONL exists: `{str(report.get('candidate_jsonl_exists')).lower()}`.",
        f"- Cohort log exists: `{str(report.get('cohort_log_exists')).lower()}`.",
        "",
        "The runner may append only when explicitly requested and existing validation reports real-market-window Phase 2 rows as append-allowed.",
    ]
    return "\n".join(lines)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Passive Phase 2 forward paper-shadow capture runner.")
    parser.add_argument("--market-window-confirmed", action="store_true")
    parser.add_argument("--market-window-status", choices=["open", "closed", "unknown"], default="unknown")
    parser.add_argument("--approval-token", default=None)
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source-scan-picks", type=Path, default=stager.DEFAULT_SOURCE_SCAN_PICKS)
    parser.add_argument("--candidate-output", type=Path, default=stager.DEFAULT_OUTPUT)
    parser.add_argument("--cohort-log", type=Path, default=appender.report_builder.DEFAULT_PHASE2_COHORT_LOG)
    parser.add_argument("--latest-json", type=Path, default=DEFAULT_CAPTURE_JSON)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_capture_report(
        market_window_confirmed=args.market_window_confirmed,
        market_window_status=args.market_window_status,
        approval_token=args.approval_token,
        append=args.append,
        dry_run=args.dry_run,
        source_scan_picks_path=args.source_scan_picks,
        candidate_output_path=args.candidate_output,
        cohort_log_path=args.cohort_log,
        latest_json_path=args.latest_json,
        docs_report_path=args.docs_report,
    )
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0 if report["status"] in {"no_phase2_natural_selections_no_append", "candidate_rows_valid_no_append", "append_performed", "append_ready_dry_run"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
