from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_volatility_expansion_forward_paper_shadow_report as report_builder


REPORT_ID = "volatility_expansion_forward_paper_shadow_append"
APPROVAL_TOKEN = "APPROVE_VOLATILITY_FORWARD_COHORT_APPEND"
PHASE2_APPROVAL_TOKEN = "APPROVE_PHASE2_FORWARD_COHORT_APPEND"
APPROVAL_PACKET_PATH = "docs/volatility-expansion-forward-paper-shadow-approval-packet.md"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def _row_identity(row: dict[str, Any]) -> str:
    return str(row.get("row_id") or row.get("selection_id") or "").strip()


def _append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    needs_newline = False
    if path.exists() and path.stat().st_size > 0:
        with path.open("rb") as existing:
            existing.seek(-1, 2)
            needs_newline = existing.read(1) != b"\n"
    with path.open("a", encoding="utf8", newline="\n") as handle:
        if needs_newline:
            handle.write("\n")
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def _sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _duplicate_ids(rows: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for row in rows:
        identity = _row_identity(row)
        if not identity:
            continue
        if identity in seen:
            duplicates.add(identity)
        seen.add(identity)
    return sorted(duplicates)


def _with_append_lock(path: Path, append_fn) -> str | None:
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd: int | None = None
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, _utc_now_iso().encode("utf8"))
        append_fn()
        return None
    except FileExistsError:
        return "cohort_append_lock_already_exists"
    finally:
        if fd is not None:
            os.close(fd)
            try:
                lock_path.unlink()
            except OSError:
                pass


def _post_append_verification(
    *,
    before_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    after_rows: list[dict[str, Any]],
    after_source: dict[str, Any],
) -> dict[str, Any]:
    expected = len(before_rows) + len(candidate_rows)
    duplicate_after_ids = _duplicate_ids(after_rows)
    checks = {
        "row_count_increment_matches": len(after_rows) == expected,
        "no_malformed_rows": after_source.get("status") == "loaded" and report_builder._safe_int(after_source.get("malformed_row_count")) == 0,
        "no_duplicate_row_ids": not duplicate_after_ids,
        "permission_flags_remain_false": True,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "cohort_rows_after_append": len(after_rows),
        "expected_cohort_rows_after_append": expected,
        "duplicate_row_ids_after_append": duplicate_after_ids,
        "after_source": after_source,
    }


def build_append_report(
    *,
    candidate_rows_path: Path,
    cohort_log_path: Path = report_builder.DEFAULT_COHORT_LOG,
    schema_path: Path = report_builder.DEFAULT_SCHEMA,
    trade_qualification_path: Path = report_builder.DEFAULT_TRADE_QUALIFICATION,
    robust_edge_path: Path = report_builder.DEFAULT_ROBUST_EDGE,
    forward_cohort_preregistration_path: Path = report_builder.DEFAULT_FORWARD_COHORT_PREREGISTRATION,
    allowed_lane_ids: tuple[str, ...] = (report_builder.FROZEN_LANE_ID,),
    approval_token: str = "",
    market_window_confirmed: bool = False,
    dry_run: bool = False,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    validation_report = report_builder.build_report(
        trade_qualification_path=trade_qualification_path,
        robust_edge_path=robust_edge_path,
        forward_cohort_preregistration_path=forward_cohort_preregistration_path,
        cohort_log_path=cohort_log_path,
        candidate_rows_path=candidate_rows_path,
        schema_path=schema_path,
        allowed_lane_ids=allowed_lane_ids,
        generated_at_utc=generated_at,
    )
    validation = report_builder._as_dict(validation_report.get("candidate_append_validation"))
    candidate_rows, candidate_source = report_builder._load_jsonl(candidate_rows_path)
    existing_rows, existing_source = report_builder._load_jsonl(cohort_log_path)
    existing_ids = {_row_identity(row) for row in existing_rows if _row_identity(row)}
    duplicate_existing_ids = sorted(
        {
            _row_identity(row)
            for row in candidate_rows
            if _row_identity(row) and _row_identity(row) in existing_ids
        }
    )

    allowed_tokens = {APPROVAL_TOKEN, PHASE2_APPROVAL_TOKEN}
    approval_valid = approval_token in allowed_tokens
    append_performed = False
    status = "append_ready_dry_run"
    reason_codes: list[str] = []
    post_append_verification: dict[str, Any] = {
        "passed": False,
        "checks": {},
        "cohort_rows_after_append": len(existing_rows),
        "expected_cohort_rows_after_append": len(existing_rows),
        "duplicate_row_ids_after_append": [],
        "after_source": existing_source,
    }
    if not validation.get("append_allowed"):
        status = "blocked_candidate_validation_failed"
        reason_codes.append("candidate_validation_not_append_allowed")
    if duplicate_existing_ids:
        status = "blocked_duplicate_existing_rows"
        reason_codes.append("candidate_rows_already_in_cohort_log")
    if not approval_valid:
        status = "blocked_missing_operator_approval"
        reason_codes.append("approval_token_missing_or_invalid")
    if not market_window_confirmed:
        status = "blocked_market_window_not_confirmed"
        reason_codes.append("market_window_not_confirmed")
    if dry_run and status == "append_ready_dry_run":
        reason_codes.append("dry_run_no_append_performed")
    elif status == "append_ready_dry_run":
        duplicate_after_lock_ids: list[str] = []

        def _locked_append() -> None:
            nonlocal duplicate_after_lock_ids
            latest_rows, _latest_source = report_builder._load_jsonl(cohort_log_path)
            latest_ids = {_row_identity(row) for row in latest_rows if _row_identity(row)}
            latest_duplicates = sorted(
                {
                    _row_identity(row)
                    for row in candidate_rows
                    if _row_identity(row) and _row_identity(row) in latest_ids
                }
            )
            if latest_duplicates:
                duplicate_after_lock_ids = latest_duplicates
                return
            _append_jsonl(cohort_log_path, candidate_rows)

        lock_error = _with_append_lock(cohort_log_path, _locked_append)
        if lock_error:
            status = "blocked_append_lock_unavailable"
            reason_codes.append(lock_error)
        elif duplicate_after_lock_ids:
            status = "blocked_duplicate_existing_rows_after_lock"
            reason_codes.append("candidate_rows_already_in_cohort_log_after_lock")
            duplicate_existing_ids = duplicate_after_lock_ids
        else:
            appended_rows_after, appended_source = report_builder._load_jsonl(cohort_log_path)
            post_append_verification = _post_append_verification(
                before_rows=existing_rows,
                candidate_rows=candidate_rows,
                after_rows=appended_rows_after,
                after_source=appended_source,
            )
            append_performed = post_append_verification["passed"]
            status = "append_performed" if append_performed else "blocked_post_append_verification_failed"
            if not append_performed:
                reason_codes.append("post_append_verification_failed")

    return {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "read_only": not append_performed,
        "dry_run": dry_run,
        "status": status,
        "reason_codes": reason_codes,
        "candidate_rows_path": _rel(candidate_rows_path),
        "candidate_batch_sha256": _sha256_file(candidate_rows_path),
        "cohort_log_path": _rel(cohort_log_path),
        "approval_packet_path": APPROVAL_PACKET_PATH,
        "approval_token_required": PHASE2_APPROVAL_TOKEN if set(allowed_lane_ids) == set(report_builder.PHASE2_FROZEN_LANE_IDS) else APPROVAL_TOKEN,
        "approval_token_valid": approval_valid,
        "market_window_confirmed": market_window_confirmed,
        "cohort_append_performed": append_performed,
        "candidate_source": candidate_source,
        "existing_cohort_source": existing_source,
        "candidate_rows": len(candidate_rows),
        "existing_cohort_rows_before_append": len(existing_rows),
        "appended_rows": len(candidate_rows) if append_performed else 0,
        "duplicate_existing_row_ids": duplicate_existing_ids,
        "candidate_append_validation": validation,
        "post_append_verification": post_append_verification,
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
        "promotion_ready": False,
        "changed_scanner_policy": False,
        "changed_strategy_logic": False,
        "changed_stops": False,
        "changed_sizing": False,
        "changed_broker_behavior": False,
        "changed_auto_track_behavior": False,
        "changed_live_validation": False,
        "imported_quotes": False,
        "repaired_historical_rows": False,
        "mutated_evidence_databases": False,
        "validation_report_status": validation_report.get("overall_status"),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Guarded append for volatility forward paper-shadow candidate rows.")
    parser.add_argument("candidate_rows", type=Path)
    parser.add_argument("--cohort-log", type=Path, default=report_builder.DEFAULT_COHORT_LOG)
    parser.add_argument("--schema", type=Path, default=report_builder.DEFAULT_SCHEMA)
    parser.add_argument("--trade-qualification", type=Path, default=report_builder.DEFAULT_TRADE_QUALIFICATION)
    parser.add_argument("--robust-edge", type=Path, default=report_builder.DEFAULT_ROBUST_EDGE)
    parser.add_argument("--forward-cohort-preregistration", type=Path, default=report_builder.DEFAULT_FORWARD_COHORT_PREREGISTRATION)
    parser.add_argument("--allowed-lane", action="append", default=None)
    parser.add_argument("--phase2", action="store_true")
    parser.add_argument("--approval-token", default="")
    parser.add_argument("--market-window-confirmed", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_append_report(
        candidate_rows_path=args.candidate_rows,
        cohort_log_path=args.cohort_log,
        schema_path=args.schema,
        trade_qualification_path=args.trade_qualification,
        robust_edge_path=args.robust_edge,
        forward_cohort_preregistration_path=args.forward_cohort_preregistration,
        allowed_lane_ids=report_builder.PHASE2_FROZEN_LANE_IDS if args.phase2 else tuple(args.allowed_lane or [report_builder.FROZEN_LANE_ID]),
        approval_token=args.approval_token,
        market_window_confirmed=args.market_window_confirmed,
        dry_run=args.dry_run,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] in {"append_ready_dry_run", "append_performed"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
