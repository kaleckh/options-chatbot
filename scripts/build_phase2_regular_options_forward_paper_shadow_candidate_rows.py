from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_volatility_expansion_forward_paper_shadow_report as report_builder


REPORT_ID = "phase2_regular_options_forward_paper_shadow_candidate_row_stager"

DEFAULT_PREREGISTRATION = ROOT / "data" / "contracts" / "forward-cohort-preregistration.json"
DEFAULT_SCHEMA = ROOT / "data" / "contracts" / "phase2-regular-options-forward-paper-shadow-cohort-schema.json"
DEFAULT_SOURCE_SCAN_PICKS = ROOT / "data" / "forward-tracking" / "scan_picks.jsonl"
DEFAULT_OUTPUT = ROOT / "data" / "forward-tracking" / "phase2_regular_options_forward_paper_shadow_candidate_rows.jsonl"
DEFAULT_LATEST_JSON = ROOT / "data" / "forward-tracking" / "phase2_regular_options_forward_paper_shadow_candidate_rows_latest.json"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-phase2-forward-paper-shadow-candidate-row-stager.md"

ALLOWED_LANES = report_builder.PHASE2_FROZEN_LANE_IDS
NON_EXECUTABLE_SOURCES = {"midpoint", "mid", "eod", "daily_eod", "display", "last", "last_trade", "manual", "model", "synthetic", "lookahead"}


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
    return parsed


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf8"))


def _load_rows(path: Path) -> tuple[list[dict[str, Any]], int]:
    text = path.read_text(encoding="utf8")
    stripped = text.strip()
    if not stripped:
        return [], 0
    if stripped.startswith("["):
        payload = json.loads(stripped)
        rows = [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []
        malformed = 0 if isinstance(payload, list) else 1
        return rows, malformed
    rows: list[dict[str, Any]] = []
    malformed = 0
    for raw in text.splitlines():
        line = raw.strip().lstrip("\ufeff")
        if not line:
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
    return rows, malformed


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _policy_maps(preregistration: dict[str, Any]) -> tuple[dict[str, str], dict[str, set[str]], str]:
    lanes = {
        _norm(row.get("lane_id")): _as_dict(row)
        for row in _as_list(preregistration.get("lanes"))
        if isinstance(row, dict) and _norm(row.get("lane_id"))
    }
    hashes: dict[str, str] = {}
    symbols: dict[str, set[str]] = {}
    for lane_id in ALLOWED_LANES:
        lane = _as_dict(lanes.get(lane_id))
        policy = _as_dict(_as_dict(_as_dict(preregistration.get("byte_frozen_policy_snapshot")).get("lanes")).get(lane_id))
        hashes[lane_id] = _norm(lane.get("policy_snapshot_sha256") or policy.get("sha256"))
        symbols[lane_id] = {_norm(symbol) for symbol in _as_list(lane.get("symbols")) if _norm(symbol)}
    freeze_date = _norm(_as_dict(preregistration.get("cohort")).get("freeze_date"))
    return hashes, symbols, freeze_date


def _contract_key(row: dict[str, Any]) -> str:
    long_symbol = _norm(row.get("long_contract_symbol") or row.get("contract_symbol"))
    short_symbol = _norm(row.get("short_contract_symbol"))
    direct = _norm(row.get("contract_or_spread_key"))
    if direct:
        return direct
    if long_symbol and short_symbol:
        return f"{long_symbol}/{short_symbol}"
    return long_symbol


def _leg_prices(row: dict[str, Any]) -> tuple[float | None, float | None]:
    legs = _as_list(_as_dict(row.get("entry_quote_snapshot")).get("legs") or row.get("legs"))
    by_role = {_norm_lower(_as_dict(leg).get("role")): _as_dict(leg) for leg in legs if isinstance(leg, dict)}
    long_leg = by_role.get("long")
    short_leg = by_role.get("short")
    if long_leg and short_leg:
        long_bid = _safe_float(long_leg.get("bid"))
        long_ask = _safe_float(long_leg.get("ask"))
        short_bid = _safe_float(short_leg.get("bid"))
        short_ask = _safe_float(short_leg.get("ask"))
        if None not in (long_bid, long_ask, short_bid, short_ask):
            return round(float(long_bid) - float(short_ask), 4), round(float(long_ask) - float(short_bid), 4)
    entry_ask = _safe_float(row.get("entry_ask") or row.get("entry_execution_price") or row.get("spread_entry_debit") or row.get("net_debit"))
    entry_bid = _safe_float(row.get("entry_bid") or row.get("net_debit"))
    return entry_bid, entry_ask


def _entry_quote_timestamp(row: dict[str, Any]) -> str:
    snapshot = _as_dict(row.get("entry_quote_snapshot"))
    return _norm(
        row.get("entry_quote_timestamp_utc")
        or row.get("quote_timestamp_utc")
        or row.get("quote_time_utc")
        or snapshot.get("quote_timestamp_utc")
        or snapshot.get("captured_at_utc")
        or row.get("selection_timestamp_utc")
    )


def _lane_id(row: dict[str, Any]) -> str:
    return _norm(row.get("lane_id") or row.get("playbook_id") or row.get("cohort_id"))


def _selection_timestamp(row: dict[str, Any]) -> str:
    return _norm(row.get("selection_timestamp_utc") or row.get("quote_time_utc") or row.get("quote_timestamp_utc") or row.get("logged_at"))


def _selection_date(row: dict[str, Any]) -> str:
    return _norm(row.get("selection_date") or row.get("scan_date") or _selection_timestamp(row)[:10])


def _has_non_executable_source(row: dict[str, Any]) -> bool:
    fields = [
        row.get("entry_quote_source"),
        row.get("quote_evidence_class"),
        row.get("entry_evidence_class"),
        row.get("selection_source"),
    ]
    return any(_norm_lower(value) in NON_EXECUTABLE_SOURCES for value in fields if _norm(value))


def _normalize_row(
    row: dict[str, Any],
    *,
    policy_hashes: dict[str, str],
    allowed_symbols: dict[str, set[str]],
    freeze_date: str,
    generated_at_utc: str,
    source_mode: str,
    target_selection_date: str,
    source_artifact_path: Path,
    source_artifact_sha256: str,
    market_window_status: str,
) -> tuple[dict[str, Any] | None, str | None]:
    lane_id = _lane_id(row)
    ticker = _norm(row.get("ticker") or row.get("symbol"))
    selection_date = _selection_date(row)
    if lane_id not in ALLOWED_LANES:
        return None, "non_phase2_lane"
    if ticker not in allowed_symbols.get(lane_id, set()):
        return None, "non_preregistered_symbol"
    if freeze_date and selection_date <= freeze_date:
        return None, "pre_freeze_selection"
    if source_mode == "scan_picks" and selection_date != target_selection_date:
        return None, "not_current_market_window_selection"
    policy_hash = _norm(row.get("scanner_policy_hash") or row.get("policy_snapshot_sha256") or policy_hashes.get(lane_id))
    if policy_hash != policy_hashes.get(lane_id):
        return None, "scanner_hash_drift"
    contract_key = _contract_key(row)
    if not contract_key:
        return None, "missing_contract_or_spread_key"
    if _has_non_executable_source(row):
        return None, "non_executable_or_midpoint_source"

    status = _norm_lower(row.get("denominator_status")) or "open_waiting_policy_exit"
    if status not in report_builder.DENOMINATOR_STATUSES:
        return None, "unknown_denominator_status"
    selection_timestamp = _selection_timestamp(row) or f"{selection_date}T00:00:00Z"
    scanner_run_id = _norm(row.get("scanner_run_id") or row.get("source_scan_run_id") or f"phase2_stager:{selection_date}")
    selection_id = _norm(row.get("selection_id") or f"{lane_id}:{ticker}:{selection_date}:{contract_key}:{scanner_run_id}")
    row_id = _norm(row.get("row_id") or f"phase2:{selection_id}:{status}")
    entry_bid, entry_ask = _leg_prices(row)
    normalized = {
        "schema_version": int(row.get("schema_version") or 1),
        "row_id": row_id,
        "selection_id": selection_id,
        "lane_id": lane_id,
        "selection_timestamp_utc": selection_timestamp,
        "selection_date": selection_date,
        "scanner_run_id": scanner_run_id,
        "scanner_policy_hash": policy_hash,
        "denominator_status": status,
        "ticker": ticker,
        "contract_or_spread_key": contract_key,
        "strategy_type": _norm(row.get("strategy_type") or "vertical_spread"),
        "direction": _norm(row.get("direction")),
        "expiration": _norm(row.get("expiration") or row.get("expiry") or row.get("resolved_listed_expiry")),
        "long_contract_symbol": _norm(row.get("long_contract_symbol") or row.get("contract_symbol")),
        "short_contract_symbol": _norm(row.get("short_contract_symbol")),
        "entry_evidence_status": _norm(row.get("entry_evidence_status") or "exact_entry_captured"),
        "entry_quote_source": _norm(row.get("entry_quote_source") or row.get("quote_source") or row.get("options_data_source") or "opra_nbbo"),
        "entry_quote_timestamp_utc": _entry_quote_timestamp(row) or selection_timestamp,
        "entry_bid": entry_bid,
        "entry_ask": entry_ask,
        "exit_evidence_status": _norm(row.get("exit_evidence_status") or ("exact_exit_captured" if status == "exact_exit_captured" else "open_waiting_policy_exit")),
        "candidate_source_mode": "fixture" if source_mode == "fixture" else "real_market_window_scan_picks",
        "fixture_mode": source_mode == "fixture",
        "source_artifact_path": _rel(source_artifact_path),
        "source_artifact_sha256": source_artifact_sha256,
        "market_window_status": market_window_status,
        "captured_at_utc": generated_at_utc,
        "policy_drift": False,
        "evidence_drift": False,
        "notes": f"staged_by={REPORT_ID}; source_mode={source_mode}; generated_at_utc={generated_at_utc}",
    }
    for key in ("exit_quote_source", "exit_quote_timestamp_utc", "exit_bid", "exit_ask", "policy_exit_condition", "net_pnl_pct", "net_pnl_usd"):
        if key in row and row.get(key) not in (None, ""):
            normalized[key] = row.get(key)
    return normalized, None


def _dedupe_lifecycle(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    seen_row_ids: set[str] = set()
    exact_exit_selection_ids: set[str] = set()
    deduped: list[dict[str, Any]] = []
    blockers: list[str] = []
    for row in rows:
        row_id = _norm(row.get("row_id"))
        selection_id = _norm(row.get("selection_id") or row_id)
        if not row_id or row_id in seen_row_ids:
            blockers.append("phase2_append_only_lifecycle_identity_not_safe")
            continue
        seen_row_ids.add(row_id)
        if _norm_lower(row.get("denominator_status")) == "exact_exit_captured":
            if selection_id in exact_exit_selection_ids:
                blockers.append("phase2_append_only_lifecycle_identity_not_safe")
                continue
            exact_exit_selection_ids.add(selection_id)
        deduped.append(row)
    return deduped, sorted(set(blockers))


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows) + ("\n" if rows else ""), encoding="utf8")


def _validate_rows(rows: list[dict[str, Any]], generated_at_utc: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as temp_dir:
        candidate_path = Path(temp_dir) / "candidate.jsonl"
        _write_jsonl(candidate_path, rows)
        return report_builder.build_report(
            candidate_rows_path=candidate_path,
            cohort_log_path=report_builder.DEFAULT_PHASE2_COHORT_LOG,
            schema_path=DEFAULT_SCHEMA,
            allowed_lane_ids=ALLOWED_LANES,
            generated_at_utc=generated_at_utc,
        )


def build_stage_report(
    *,
    fixture_path: Path | None = None,
    source_scan_picks_path: Path = DEFAULT_SOURCE_SCAN_PICKS,
    output_path: Path = DEFAULT_OUTPUT,
    latest_json_path: Path = DEFAULT_LATEST_JSON,
    docs_report_path: Path = DEFAULT_DOCS_REPORT,
    preregistration_path: Path = DEFAULT_PREREGISTRATION,
    no_write: bool = False,
    market_window_confirmed: bool = False,
    market_window_status: str = "unknown",
    selection_date: str | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    target_selection_date = selection_date or generated_at[:10]
    if fixture_path is None and (not market_window_confirmed or market_window_status != "open"):
        return _final_report(
            generated_at,
            status="blocked_market_window_not_confirmed",
            reason_codes=["market_window_not_confirmed"],
            source_path=source_scan_picks_path,
            source_mode="scan_picks",
            output_path=output_path,
            latest_json_path=latest_json_path,
            docs_report_path=docs_report_path,
            rows=[],
            rejected_counts={},
            validation=None,
            no_write=no_write,
            writes_performed=[],
        )

    preregistration = _load_json(preregistration_path)
    policy_hashes, allowed_symbols, freeze_date = _policy_maps(preregistration)
    source_path = fixture_path or source_scan_picks_path
    if not source_path.exists():
        status = "missing_phase2_natural_selection_source" if fixture_path is None else "fixture_missing"
        return _final_report(
            generated_at,
            status=status,
            reason_codes=[status],
            source_path=source_path,
            source_mode="fixture" if fixture_path else "scan_picks",
            output_path=output_path,
            latest_json_path=latest_json_path,
            docs_report_path=docs_report_path,
            rows=[],
            rejected_counts={},
            validation=None,
            no_write=no_write,
            writes_performed=[],
        )

    source_rows, malformed = _load_rows(source_path)
    source_mode = "fixture" if fixture_path else "scan_picks"
    source_sha256 = _sha256_file(source_path)
    staged: list[dict[str, Any]] = []
    rejected_counts: dict[str, int] = {}
    for row in source_rows:
        normalized, reason = _normalize_row(
            row,
            policy_hashes=policy_hashes,
            allowed_symbols=allowed_symbols,
            freeze_date=freeze_date,
            generated_at_utc=generated_at,
            source_mode=source_mode,
            target_selection_date=target_selection_date,
            source_artifact_path=source_path,
            source_artifact_sha256=source_sha256,
            market_window_status=market_window_status if source_mode != "fixture" else "closed",
        )
        if normalized is None:
            rejected_counts[reason or "rejected"] = rejected_counts.get(reason or "rejected", 0) + 1
            continue
        staged.append(normalized)
    if malformed:
        rejected_counts["malformed_source_rows"] = malformed
    staged, lifecycle_blockers = _dedupe_lifecycle(staged)
    for blocker in lifecycle_blockers:
        rejected_counts[blocker] = rejected_counts.get(blocker, 0) + 1

    validation = _validate_rows(staged, generated_at) if staged else None
    validation_allowed = bool(validation and validation.get("candidate_append_validation", {}).get("append_allowed"))
    fixture_canonical_output = source_mode == "fixture" and output_path.resolve() == DEFAULT_OUTPUT.resolve()
    if lifecycle_blockers:
        status = "phase2_append_only_lifecycle_identity_not_safe"
    elif not staged and fixture_path is None:
        status = "no_phase2_natural_selections"
    elif not staged:
        status = "no_fixture_rows_staged"
    elif source_mode == "fixture":
        status = "fixture_rows_staged_append_ineligible"
    elif validation_allowed:
        status = "candidate_rows_staged_validation_passed"
    else:
        status = "candidate_rows_staged_validation_failed"

    writes_performed: list[str] = []
    report = _final_report(
        generated_at,
        status=status,
        reason_codes=[status],
        source_path=source_path,
        source_mode=source_mode,
        output_path=output_path,
        latest_json_path=latest_json_path,
        docs_report_path=docs_report_path,
        rows=staged,
        rejected_counts=rejected_counts,
        validation=validation,
        no_write=no_write,
        writes_performed=writes_performed,
    )
    if not no_write:
        if fixture_canonical_output and output_path.exists():
            output_path.unlink()
        if staged and (validation_allowed or (source_mode == "fixture" and not fixture_canonical_output)):
            _write_jsonl(output_path, staged)
            writes_performed.append(_rel(output_path))
        latest_json_path.parent.mkdir(parents=True, exist_ok=True)
        latest_json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
        writes_performed.append(_rel(latest_json_path))
        docs_report_path.parent.mkdir(parents=True, exist_ok=True)
        docs_report_path.write_text(render_markdown(report) + "\n", encoding="utf8")
        writes_performed.append(_rel(docs_report_path))
        report["writes_performed"] = writes_performed
        report["candidate_jsonl_written"] = _rel(output_path) in writes_performed
        latest_json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    return report


def _final_report(
    generated_at: str,
    *,
    status: str,
    reason_codes: list[str],
    source_path: Path,
    source_mode: str,
    output_path: Path,
    latest_json_path: Path,
    docs_report_path: Path,
    rows: list[dict[str, Any]],
    rejected_counts: dict[str, int],
    validation: dict[str, Any] | None,
    no_write: bool,
    writes_performed: list[str],
) -> dict[str, Any]:
    validation_summary = {}
    if validation:
        validation_summary = {
            "overall_status": validation.get("overall_status"),
            "append_allowed": validation.get("candidate_append_validation", {}).get("append_allowed"),
            "append_ready_rows": validation.get("candidate_append_validation", {}).get("append_ready_rows"),
            "append_rejected_rows": validation.get("candidate_append_validation", {}).get("append_rejected_rows"),
            "append_reject_counts": validation.get("candidate_append_validation", {}).get("append_reject_counts"),
            "total_natural_selections": validation.get("total_natural_selections"),
        }
    return {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "status": status,
        "reason_codes": reason_codes,
        "source_mode": source_mode,
        "source_path": _rel(source_path),
        "output_path": _rel(output_path),
        "latest_json_path": _rel(latest_json_path),
        "docs_report_path": _rel(docs_report_path),
        "target_allowed_lanes": list(ALLOWED_LANES),
        "candidate_rows_staged": len(rows),
        "candidate_row_ids": [_norm(row.get("row_id")) for row in rows],
        "selection_ids": sorted({_norm(row.get("selection_id")) for row in rows if _norm(row.get("selection_id"))}),
        "rejected_counts": rejected_counts,
        "validation": validation_summary,
        "no_write": no_write,
        "candidate_jsonl_written": False if no_write else bool(rows and validation_summary.get("append_allowed")),
        "cohort_append_performed": False,
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
        "promotion_ready": False,
        "scanner_policy_changed": False,
        "strategy_logic_changed": False,
        "quotes_imported": False,
        "evidence_stores_mutated": False,
        "protected_holdout_consumed": False,
        "writes_performed": writes_performed,
    }


def render_markdown(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 2 Forward Paper-Shadow Candidate Row Stager",
            "",
            "This artifact stages append-only candidate rows only. It does not append the cohort log or authorize live trading.",
            "",
            f"- Status: `{report.get('status')}`.",
            f"- Source mode: `{report.get('source_mode')}`.",
            f"- Source path: `{report.get('source_path')}`.",
            f"- Candidate rows staged: `{report.get('candidate_rows_staged')}`.",
            f"- Candidate JSONL written: `{str(report.get('candidate_jsonl_written')).lower()}`.",
            f"- Cohort append performed: `{str(report.get('cohort_append_performed')).lower()}`.",
            f"- Live entry allowed: `{str(report.get('live_entry_allowed')).lower()}`.",
            f"- Auto-track allowed: `{str(report.get('auto_track_allowed')).lower()}`.",
            f"- Broker order allowed: `{str(report.get('broker_order_allowed')).lower()}`.",
            f"- Rejected counts: `{json.dumps(report.get('rejected_counts'), sort_keys=True)}`.",
            f"- Validation: `{json.dumps(report.get('validation'), sort_keys=True)}`.",
            "",
            "Fresh real-mode rows require a confirmed open market window and same-day natural selections. Fixture mode is the closed-market test path.",
        ]
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage Phase 2 regular-options forward paper-shadow candidate rows.")
    parser.add_argument("--fixture", type=Path, default=None)
    parser.add_argument("--source-scan-picks", type=Path, default=DEFAULT_SOURCE_SCAN_PICKS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--latest-json", type=Path, default=DEFAULT_LATEST_JSON)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--forward-cohort-preregistration", type=Path, default=DEFAULT_PREREGISTRATION)
    parser.add_argument("--market-window-confirmed", action="store_true")
    parser.add_argument("--market-window-status", choices=["open", "closed", "unknown"], default="unknown")
    parser.add_argument("--selection-date", default=None)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_stage_report(
        fixture_path=args.fixture,
        source_scan_picks_path=args.source_scan_picks,
        output_path=args.output,
        latest_json_path=args.latest_json,
        docs_report_path=args.docs_report,
        preregistration_path=args.forward_cohort_preregistration,
        no_write=args.no_write,
        market_window_confirmed=args.market_window_confirmed,
        market_window_status=args.market_window_status,
        selection_date=args.selection_date,
    )
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
