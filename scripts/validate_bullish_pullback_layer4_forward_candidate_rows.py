from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_bullish_pullback_layer4_forward_capture_protocol as protocol


REPORT_ID = "bullish_pullback_layer4_forward_candidate_validation"

EXACT_ENTRY_STATUSES = {"exact_entry_captured", "open_waiting_policy_exit", "exact_exit_captured"}
EXACT_EXIT_STATUS = "exact_exit_captured"
DENOMINATOR_STATUSES = set(protocol.DENOMINATOR_STATUSES)
REJECT_BASIS_TOKENS = {
    "source_mark",
    "spread_mark",
    "mid",
    "midpoint",
    "eod",
    "display",
    "display_only",
    "stale",
    "last_trade",
    "manual",
    "synthetic",
    "lookahead",
    "percent_only",
}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _norm_lower(value: Any) -> str:
    return _norm(value).lower()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source = {"path": _rel(path), "exists": path.exists(), "status": "missing", "row_count": 0, "malformed_row_count": 0}
    if not path.exists():
        return [], source
    rows: list[dict[str, Any]] = []
    malformed = 0
    for line in path.read_text(encoding="utf8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(payload, dict):
            rows.append(payload)
        else:
            malformed += 1
    source.update({"status": "loaded" if malformed == 0 else "malformed", "row_count": len(rows), "malformed_row_count": malformed})
    return rows, source


def _row_id(row: dict[str, Any]) -> str:
    return _norm(row.get("row_id") or row.get("selection_id"))


def _leg(row: dict[str, Any], side: str) -> dict[str, Any]:
    nested = _as_dict(row.get(f"{side}_leg"))
    return {
        "contract_symbol": _norm(row.get(f"{side}_contract_symbol") or nested.get("contract_symbol")),
        "entry_bid": _safe_float(row.get(f"{side}_entry_bid") if row.get(f"{side}_entry_bid") is not None else nested.get("entry_bid")),
        "entry_ask": _safe_float(row.get(f"{side}_entry_ask") if row.get(f"{side}_entry_ask") is not None else nested.get("entry_ask")),
        "exit_bid": _safe_float(row.get(f"{side}_exit_bid") if row.get(f"{side}_exit_bid") is not None else nested.get("exit_bid")),
        "exit_ask": _safe_float(row.get(f"{side}_exit_ask") if row.get(f"{side}_exit_ask") is not None else nested.get("exit_ask")),
    }


def _has_entry_quotes(row: dict[str, Any]) -> bool:
    long = _leg(row, "long")
    short = _leg(row, "short")
    return all(value is not None for value in (long["entry_bid"], long["entry_ask"], short["entry_bid"], short["entry_ask"]))


def _has_exit_quotes(row: dict[str, Any]) -> bool:
    long = _leg(row, "long")
    short = _leg(row, "short")
    return all(value is not None for value in (long["exit_bid"], long["exit_ask"], short["exit_bid"], short["exit_ask"]))


def _has_zero_untradable_quote(row: dict[str, Any]) -> bool:
    values: list[float] = []
    for side in ("long", "short"):
        leg = _leg(row, side)
        values.extend(value for value in (leg["entry_bid"], leg["entry_ask"], leg["exit_bid"], leg["exit_ask"]) if value is not None)
    return bool(row.get("zero_bid_or_untradable")) or any(value <= 0 for value in values)


def _basis_values(row: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for key in ("quote_evidence_class", "entry_quote_evidence_class", "exit_quote_evidence_class", "price_source", "entry_price_source", "exit_price_source", "evidence_basis", "entry_basis", "exit_basis", "pnl_basis"):
        value = _norm_lower(row.get(key))
        if value:
            values.add(value)
    for item in _as_list(row.get("evidence_classes")):
        value = _norm_lower(item)
        if value:
            values.add(value)
    return values


def _uses_rejected_basis(row: dict[str, Any]) -> bool:
    values = _basis_values(row)
    return any(token in value for token in REJECT_BASIS_TOKENS for value in values)


def _validate_row(row: dict[str, Any], seen: set[str]) -> list[str]:
    reasons: list[str] = []
    row_id = _row_id(row)
    if not row_id:
        reasons.append("missing_row_id")
    elif row_id in seen:
        reasons.append("duplicate_row_id")
    if row_id:
        seen.add(row_id)

    if _norm(row.get("lane_id")) != protocol.SELECTED_LANE_ID:
        reasons.append("wrong_lane")
    if _norm(row.get("layer_id")) != protocol.SELECTED_LAYER_ID:
        reasons.append("wrong_layer")
    if _norm(row.get("variant_id")) != protocol.SELECTED_VARIANT_ID:
        reasons.append("wrong_variant")
    if _norm(row.get("ticker")) not in protocol.ALLOWED_SYMBOLS:
        reasons.append("non_allowed_symbol")
    if _norm(row.get("selection_date")) <= protocol.FREEZE_DATE:
        reasons.append("pre_freeze_date")
    if not _norm(row.get("scanner_run_id")) or not _norm(row.get("scanner_policy_hash")):
        reasons.append("missing_scanner_provenance")
    if not _leg(row, "long")["contract_symbol"] or not _leg(row, "short")["contract_symbol"]:
        reasons.append("missing_leg_identity")

    status = _norm_lower(row.get("denominator_status"))
    if status not in DENOMINATOR_STATUSES:
        reasons.append("unknown_denominator_status")
    if status in EXACT_ENTRY_STATUSES and not _has_entry_quotes(row):
        reasons.append("missing_entry_quote")
    if status == EXACT_EXIT_STATUS:
        if not _has_exit_quotes(row):
            reasons.append("missing_exit_quote")
        if not _norm(row.get("policy_exit_condition")):
            reasons.append("missing_policy_exit")
        if _safe_float(row.get("net_pnl_usd")) is None:
            reasons.append("missing_net_pnl_usd")
        if _safe_float(row.get("contract_multiplier")) is None:
            reasons.append("missing_contract_multiplier")
        if _has_zero_untradable_quote(row):
            reasons.append("zero_or_untradable_claimed_as_exact_proof")
    if _uses_rejected_basis(row):
        reasons.append("non_executable_or_source_mark_basis")
    if row.get("net_pnl_pct") is not None and row.get("net_pnl_usd") is None and status == EXACT_EXIT_STATUS:
        reasons.append("percent_only_pnl")
    return reasons


def validate_rows(candidate_rows_path: Path, *, generated_at_utc: str | None = None) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    rows, source = _load_jsonl(candidate_rows_path)
    seen: set[str] = set()
    reject_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    valid_rows = 0
    row_results: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        status = _norm_lower(row.get("denominator_status")) or "unknown"
        status_counts[status] += 1
        reasons = _validate_row(row, seen)
        for reason in reasons:
            reject_counts[reason] += 1
        if not reasons:
            valid_rows += 1
        row_results.append({"row_number": index, "row_id": _row_id(row), "denominator_status": status, "valid": not reasons, "reject_reasons": reasons})

    source_loaded = source["status"] == "loaded"
    candidate_rows_would_be_valid = source_loaded and bool(rows) and valid_rows == len(rows)
    return {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "candidate_rows_path": _rel(candidate_rows_path),
        "candidate_source": source,
        "read_only": True,
        "candidate_validator_read_only": True,
        "cohort_append_performed": False,
        "append_allowed": False,
        "candidate_rows_would_be_valid_for_future_approval": candidate_rows_would_be_valid,
        "overall_status": "candidate_rows_valid_for_future_approval_no_append" if candidate_rows_would_be_valid else "candidate_rows_rejected_or_unavailable_no_append",
        "selected_harness": {
            "lane_id": protocol.SELECTED_LANE_ID,
            "layer_id": protocol.SELECTED_LAYER_ID,
            "variant_id": protocol.SELECTED_VARIANT_ID,
            "allowed_symbols": list(protocol.ALLOWED_SYMBOLS),
            "freeze_date": protocol.FREEZE_DATE,
        },
        "total_candidate_rows": len(rows),
        "valid_candidate_rows": valid_rows,
        "rejected_candidate_rows": len(rows) - valid_rows,
        "exact_completed_candidate_count": status_counts.get("exact_exit_captured", 0),
        "open_waiting_policy_exit_count": status_counts.get("open_waiting_policy_exit", 0),
        "missing_exit_count": status_counts.get("missing_exit", 0),
        "zero_untradable_count": status_counts.get("zero_untradable", 0),
        "missed_entry_count": status_counts.get("missed_entry", 0),
        "stale_display_rejected_count": status_counts.get("stale_display_rejected", 0),
        "failed_or_incomplete_fill_attempt_count": status_counts.get("failed_or_incomplete_fill_attempt", 0),
        "denominator_status_counts": dict(sorted(status_counts.items())),
        "reject_counts": dict(sorted(reject_counts.items())),
        "row_results": row_results,
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
        "promotion_ready": False,
        "imported_quotes": False,
        "mutated_evidence_databases": False,
        "appended_forward_cohort_rows": False,
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate bullish-pullback layer4 forward candidate JSONL rows without appending.")
    parser.add_argument("candidate_rows", type=Path)
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = validate_rows(args.candidate_rows)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["candidate_rows_would_be_valid_for_future_approval"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
