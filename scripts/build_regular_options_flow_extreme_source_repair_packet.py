from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORT_ID = "regular_options_flow_extreme_source_repair_packet"
SOURCE_FAMILY = "trusted_option_volume_open_interest_daily_v1"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-flow-extreme-source-repair-packet"
DEFAULT_DOC = ROOT / "docs" / "regular-options-flow-extreme-source-repair-packet.md"
DEFAULT_FIXTURE = ROOT / "tests" / "fixtures" / "flow" / "spy_qqq_option_volume_oi_daily_sample.csv"
DEFAULT_ORACLE_PACKET = ROOT / "data" / "forward-tracking" / "options_oracle_profit_loop_packet_latest.json"
DEFAULT_POINT_IN_TIME_FLOW_INPUT = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-flow-extreme-input" / "latest.json"
DEFAULT_FLOW_VOLUME_OI_ROWS = ROOT / "data" / "profitability-lab" / "regular-options-flow-extreme-volume-oi-source-rows" / "latest.json"
DEFAULT_FLOW_REPLAY_READINESS = ROOT / "data" / "profitability-lab" / "regular-options-flow-extreme-ratio-backspread-replay-readiness" / "latest.json"
DEFAULT_FLOW_DEDUPE_BRIDGE = ROOT / "data" / "profitability-lab" / "regular-options-flow-extreme-denominator-dedupe-bridge" / "latest.json"
DEFAULT_MULTI_LEG_PRICING = ROOT / "data" / "profitability-lab" / "regular-options-multi-leg-side-aware-pricing-capability" / "latest.json"
DEFAULT_DIRECT_VIX_PACKET = ROOT / "data" / "profitability-lab" / "regular-options-direct-vix-source-repair-packet" / "latest.json"
DEFAULT_FORWARD_HOLDOUT = ROOT / "data" / "contracts" / "forward-holdout-contract.json"

NY = ZoneInfo("America/New_York")
ALLOWED_UNDERLYINGS = ("SPY", "QQQ")
REQUIRED_FIELDS = (
    "source_date",
    "underlying",
    "total_option_volume",
    "call_volume",
    "put_volume",
    "total_open_interest",
    "call_open_interest",
    "put_open_interest",
    "source_name",
    "source_url_or_file_name",
    "source_file_hash",
    "source_row_hash",
    "known_at_utc",
    "tradable_after_et",
    "source_batch_id",
    "data_trust",
    "revision_status",
    "proof_exclusion_reason",
)
CSV_FIELDS = tuple(field for field in REQUIRED_FIELDS if field not in {"source_file_hash", "source_row_hash", "tradable_after_et", "source_batch_id", "proof_exclusion_reason"})
LEAKAGE_FIELDS = {
    "selected_winner",
    "winner",
    "realized_pnl",
    "net_pnl",
    "net_pnl_usd",
    "market_reaction",
    "post_entry_return",
    "future_return",
    "trade_outcome",
}
MARKET_HOLIDAYS = {
    date(2024, 7, 4),
    date(2024, 9, 2),
    date(2024, 11, 28),
    date(2024, 12, 25),
    date(2025, 1, 1),
    date(2025, 1, 20),
    date(2025, 2, 17),
    date(2025, 4, 18),
    date(2025, 5, 26),
    date(2025, 6, 19),
    date(2025, 7, 4),
    date(2025, 9, 1),
    date(2025, 11, 27),
    date(2025, 12, 25),
    date(2026, 1, 1),
    date(2026, 1, 19),
    date(2026, 2, 16),
    date(2026, 4, 3),
    date(2026, 5, 25),
}
READ_ONLY_FLAGS = {
    "accepted_profitability": False,
    "historical_rows_are_forward_proof": False,
    "p_l_replay_performed": False,
    "realized_pnl_used_for_ranking": False,
    "future_import_command_executed": False,
    "downstream_flow_input_command_executed": False,
    "downstream_flow_replay_readiness_command_executed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "promotion_ready": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf8")).hexdigest()


def _parse_date(value: Any) -> date:
    return datetime.strptime(str(value or "").strip(), "%Y-%m-%d").date()


def _parse_utc(value: Any) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_number(value: Any, field: str) -> float:
    if value in (None, ""):
        raise ValueError(f"missing {field}")
    number = float(str(value).strip())
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"invalid {field}")
    return number


def _is_market_day(day: date) -> bool:
    return day.weekday() < 5 and day not in MARKET_HOLIDAYS


def _next_market_day(day: date) -> date:
    current = day + timedelta(days=1)
    while not _is_market_day(current):
        current += timedelta(days=1)
    return current


def _tradable_after(source_date: date) -> str:
    return _tradable_after_dt(source_date).replace(tzinfo=None).isoformat(timespec="minutes") + " America/New_York"


def _tradable_after_dt(source_date: date) -> datetime:
    day = _next_market_day(source_date)
    return datetime.combine(day, time(9, 30), tzinfo=NY)


def _percentile(value: float, prior_values: list[float]) -> float | None:
    if not prior_values:
        return None
    return round(sum(1 for prior in prior_values if prior <= value) / len(prior_values) * 100.0, 4)


def parse_flow_csv(path: Path, *, underlyings: tuple[str, ...] = ALLOWED_UNDERLYINGS) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw = path.read_text(encoding="utf8")
    file_hash = _sha256_text(raw)
    reader = csv.DictReader(raw.splitlines())
    fieldnames = reader.fieldnames or []
    missing_header = [field for field in CSV_FIELDS if field not in fieldnames]
    if missing_header:
        raise ValueError(f"missing required CSV fields: {', '.join(missing_header)}")
    forbidden_headers = [field for field in fieldnames if field.strip().lower() in LEAKAGE_FIELDS]
    if forbidden_headers:
        raise ValueError(f"leakage fields are not allowed: {', '.join(forbidden_headers)}")
    rows: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    prior_by_underlying: dict[str, list[float]] = defaultdict(list)
    seen_hashes: set[str] = set()
    for index, raw_row in enumerate(reader, start=1):
        reasons: list[str] = []
        source_date: date | None = None
        underlying = str(raw_row.get("underlying") or "").strip().upper()
        numbers: dict[str, float] = {}
        try:
            source_date = _parse_date(raw_row.get("source_date"))
        except ValueError:
            reasons.append("invalid_source_date")
        if underlying not in underlyings:
            reasons.append("outside_allowed_underlying")
        if str(raw_row.get("data_trust") or "").strip().lower() != "trusted":
            reasons.append("unknown_data_trust")
        try:
            known_at = _parse_utc(raw_row.get("known_at_utc"))
        except ValueError:
            known_at = None
            reasons.append("invalid_known_at_utc")
        for field in (
            "total_option_volume",
            "call_volume",
            "put_volume",
            "total_open_interest",
            "call_open_interest",
            "put_open_interest",
        ):
            try:
                numbers[field] = _parse_number(raw_row.get(field), field)
            except ValueError:
                reasons.append(f"missing_or_invalid_{field}")
        if source_date and known_at:
            if known_at.astimezone(NY) > _tradable_after_dt(source_date):
                reasons.append("known_at_after_tradable_after")
        row_key = {
            "source_date": source_date.isoformat() if source_date else raw_row.get("source_date"),
            "underlying": underlying,
            "source_name": raw_row.get("source_name"),
        }
        row_hash = _sha256_text(json.dumps(row_key, sort_keys=True))
        if row_hash in seen_hashes:
            reasons.append("duplicate_source_row_hash")
        seen_hashes.add(row_hash)
        if reasons:
            rejects.append({"index": index, "source_date": raw_row.get("source_date"), "underlying": underlying, "reasons": reasons})
            continue
        assert source_date is not None
        assert known_at is not None
        prior_values = prior_by_underlying[underlying]
        percentile = _percentile(numbers["total_option_volume"], prior_values)
        rows.append(
            {
                "source_date": source_date.isoformat(),
                "underlying": underlying,
                **numbers,
                "source_name": str(raw_row.get("source_name") or "").strip(),
                "source_url_or_file_name": str(raw_row.get("source_url_or_file_name") or "").strip(),
                "source_file_hash": file_hash,
                "source_row_hash": row_hash,
                "known_at_utc": known_at.isoformat(timespec="minutes").replace("+00:00", "Z"),
                "tradable_after_et": _tradable_after(source_date),
                "source_batch_id": "future_tokened_flow_extreme_volume_oi_import_batch",
                "data_trust": "trusted",
                "revision_status": str(raw_row.get("revision_status") or "").strip() or "final",
                "proof_exclusion_reason": "source_packet_fixture_not_proof_eligible",
                "threshold_policy_id": "volume_open_interest_prior_day_trailing_distribution_v1",
                "total_option_volume_prior_percentile": percentile,
                "flow_extreme": percentile is not None and percentile >= 95.0,
                "call_put_volume_ratio": round(numbers["call_volume"] / numbers["put_volume"], 6) if numbers["put_volume"] else None,
                "volume_open_interest_ratio": round(numbers["total_option_volume"] / numbers["total_open_interest"], 6)
                if numbers["total_open_interest"]
                else None,
                "strictly_prior_rows_used": len(prior_values),
            }
        )
        prior_values.append(numbers["total_option_volume"])
    return rows, rejects


def row_is_safe_for_input(row: dict[str, Any], *, input_date_et: str) -> bool:
    return date.fromisoformat(str(row["source_date"])) < date.fromisoformat(input_date_et)


def _fixture_validation(path: Path, *, protected_holdout_start: str | None) -> dict[str, Any]:
    errors: list[str] = []
    rows: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    try:
        rows, rejects = parse_flow_csv(path)
    except (ValueError, OSError) as exc:
        errors.append(str(exc))
    holdout_overlap = 0
    if protected_holdout_start:
        holdout_overlap = sum(1 for row in rows if row["source_date"] >= protected_holdout_start)
    return {
        "fixture_path": _rel(path),
        "row_count": len(rows),
        "reject_count": len(rejects),
        "errors": errors,
        "sample_rows": rows,
        "rejected_rows": rejects,
        "required_fields_present": not errors,
        "underlyings_covered": [symbol for symbol in ALLOWED_UNDERLYINGS if symbol in {row["underlying"] for row in rows}],
        "known_at_safe": bool(rows) and not errors,
        "same_day_aggregate_safe_for_same_day_entry": bool(rows) and row_is_safe_for_input(rows[0], input_date_et=rows[0]["source_date"]),
        "prior_day_aggregate_safe_for_next_session_entry": bool(rows) and row_is_safe_for_input(rows[0], input_date_et=rows[2]["source_date"]),
        "holiday_gap_case_present": any(row["source_date"] == "2024-07-03" and row["tradable_after_et"].startswith("2024-07-05") for row in rows),
        "missing_value_reject_count": sum(1 for reject in rejects if any("missing_or_invalid" in reason for reason in reject["reasons"])),
        "late_known_at_reject_count": sum(1 for reject in rejects if "known_at_after_tradable_after" in reject["reasons"]),
        "leakage_reject_count": 0 if rows and not errors else 1,
        "protected_holdout_overlap_rows": holdout_overlap,
        "duplicate_source_row_hash_reject_count": sum(1 for reject in rejects if "duplicate_source_row_hash" in reject["reasons"]),
    }


def build_report(
    *,
    lookback_start_date: str = "2023-06-01",
    target_start_date: str = "2024-06-01",
    target_end_date: str = "2026-05-31",
    as_of_date: str = "2026-06-04",
    underlyings: tuple[str, ...] = ALLOWED_UNDERLYINGS,
    source_family: str = SOURCE_FAMILY,
    fixture_path: Path = DEFAULT_FIXTURE,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOC,
    no_import: bool = True,
    write_outputs: bool = True,
) -> dict[str, Any]:
    oracle_packet = _load_json(DEFAULT_ORACLE_PACKET)
    flow_input = _load_json(DEFAULT_POINT_IN_TIME_FLOW_INPUT)
    flow_rows = _load_json(DEFAULT_FLOW_VOLUME_OI_ROWS)
    flow_readiness = _load_json(DEFAULT_FLOW_REPLAY_READINESS)
    dedupe_bridge = _load_json(DEFAULT_FLOW_DEDUPE_BRIDGE)
    pricing = _load_json(DEFAULT_MULTI_LEG_PRICING)
    direct_vix = _load_json(DEFAULT_DIRECT_VIX_PACKET)
    holdout = _load_json(DEFAULT_FORWARD_HOLDOUT)
    protected_holdout_start = holdout.get("protected_holdout_start") or holdout.get("holdout_start_date")
    fixture_validation = _fixture_validation(fixture_path, protected_holdout_start=protected_holdout_start)
    blockers: list[str] = []
    if tuple(underlyings) != ALLOWED_UNDERLYINGS or source_family != SOURCE_FAMILY:
        blockers.append("blocked_no_safe_flow_source_policy")
    if fixture_validation["errors"] or not fixture_validation["known_at_safe"] or fixture_validation["underlyings_covered"] != list(ALLOWED_UNDERLYINGS):
        blockers.append("blocked_flow_parser_contract_unsafe")
    if not any("missing_point_in_time_flow_extreme_input" in str(item) for item in _as_list(flow_readiness.get("blockers"))):
        blockers.append("blocked_flow_packet_only_no_downstream_value")
    status = "blocked_flow_extreme_source_repair_packet" if blockers else "flow_extreme_source_repair_packet_ready_for_operator_import_decision"
    current = _as_dict(oracle_packet.get("profitability_target"))
    future_import_command = (
        "npm run options:source-import:flow-extreme-volume-oi -- "
        "--source-file data/import-staging/flow/spy_qqq_option_volume_oi_daily.csv "
        f"--lookback-start-date {lookback_start_date} --target-start-date {target_start_date} "
        f"--target-end-date {target_end_date} --as-of-date {as_of_date} "
        "--underlyings SPY,QQQ --source-family trusted_option_volume_open_interest_daily_v1 "
        "--approval-token APPROVE_FLOW_EXTREME_VOLUME_OI_SOURCE_IMPORT --no-replay --json"
    )
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": _utc_now(),
        "status": status,
        "blockers": blockers,
        "source_family": source_family,
        "lookback_start_date": lookback_start_date,
        "target_start_date": target_start_date,
        "target_end_date": target_end_date,
        "as_of_date": as_of_date,
        "current_forward_rows": current.get("current_forward_rows", 0),
        "target_forward_rows": current.get("minimum_profitable_strict_completed_rows", 30),
        "point_in_time_flow_extreme_input_status": flow_input.get("status") or "blocked_point_in_time_flow_extreme_input",
        "flow_extreme_volume_oi_source_rows_status": flow_rows.get("status") or "blocked_flow_extreme_volume_oi_source_rows",
        "covered_month_count": _as_dict(flow_input.get("coverage")).get("covered_month_count", 0),
        "date_coverage_pct": _as_dict(flow_input.get("coverage")).get("date_coverage_pct", 0.0),
        "flow_extreme_ratio_backspread_replay_readiness_status": flow_readiness.get("status") or "blocked_flow_extreme_ratio_backspread_replay_readiness",
        "denominator_dedupe_status": dedupe_bridge.get("status"),
        "multi_leg_pricing_status": pricing.get("status"),
        "direct_vix_source_repair_status": direct_vix.get("status"),
        "source_schema": {"family": SOURCE_FAMILY, "required_fields": list(REQUIRED_FIELDS)},
        "allowed_underlyings": list(ALLOWED_UNDERLYINGS),
        "known_at_policy": {
            "policy_id": "trusted_flow_prior_source_date_known_before_candidate_v1",
            "rule": "source_date D aggregate volume/OI is usable only when known_at_utc is no later than candidate decision time and source_date is strictly before input_date_et",
            "same_day_aggregate_volume_oi_allowed_for_same_day_entry": False,
        },
        "threshold_policy": {
            "policy_id": "volume_open_interest_prior_day_trailing_distribution_v1",
            "flow_extreme_rule": "flow_extreme=true only when prior-day flow percentile >= 95.0 using strictly prior source rows only",
            "call_put_volume_ratio": "diagnostic_only_unless_separately_preregistered",
            "volume_open_interest_ratio": "diagnostic_only_unless_separately_preregistered",
            "realized_pnl_used": False,
            "outcome_tuned": False,
            "selected_winners_used": False,
            "plain_bid_ask_used_as_flow": False,
        },
        "future_import_readiness_gates": {
            "required_fields_present": True,
            "known_at_safe_required": True,
            "leakage_reject_count_required": 0,
            "protected_holdout_overlap_rows_required": 0,
            "underlyings_covered": list(ALLOWED_UNDERLYINGS),
            "train_months_covered_min": 20,
            "latest_four_months_covered_required": 4,
            "date_coverage_pct_min": 90.0,
            "latest_four_date_coverage_pct_min": 90.0,
        },
        "fixture_validation": fixture_validation,
        "downstream_branch_implications": [
            {
                "branch": "flow_extreme_ratio_backspread",
                "status": flow_readiness.get("status"),
                "flow_blockers": [item for item in _as_list(flow_readiness.get("blockers")) if "flow" in str(item)],
                "remaining_non_flow_blockers": [item for item in _as_list(flow_readiness.get("blockers")) if "flow" not in str(item)],
                "would_clear_flow_blocker_if_future_source_passes": True,
            },
            {
                "branch": "direct_vix_source_repair",
                "status": direct_vix.get("status"),
                "flow_blockers": [],
                "remaining_non_flow_blockers": []
                if direct_vix.get("status") == "direct_vix_source_repair_packet_superseded_by_materialized_vix"
                else ["direct_vix_source_import_materialization_pending"],
                "would_clear_flow_blocker_if_future_source_passes": False,
            },
        ],
        "future_import_manifest_template": {
            "source_file": "data/import-staging/flow/spy_qqq_option_volume_oi_daily.csv",
            "source_family": SOURCE_FAMILY,
            "write_target": "generated point-in-time flow-extreme source artifact only",
            "date_window": {"lookback_start": lookback_start_date, "target_start": target_start_date, "target_end": target_end_date, "as_of": as_of_date},
            "protected_holdout_consumption_allowed": False,
            "required_approval_token": "APPROVE_FLOW_EXTREME_VOLUME_OI_SOURCE_IMPORT",
            "underlyings": list(ALLOWED_UNDERLYINGS),
            "required_fields": list(REQUIRED_FIELDS),
        },
        "future_import_command": future_import_command,
        "downstream_readiness_commands": {
            "point_in_time_flow_extreme_input": "npm run options:research:point-in-time-flow-extreme-input -- --no-write --json",
            "flow_extreme_ratio_backspread_replay_readiness": "npm run options:research:flow-extreme-ratio-backspread-replay-readiness -- --json",
        },
        **READ_ONLY_FLAGS,
        "no_import": no_import,
        "artifacts": {
            "docs_report": _rel(docs_report),
            "latest_json": _rel(output_dir / "latest.json"),
            "latest_markdown": _rel(output_dir / "latest.md"),
            "future_import_manifest_template": _rel(output_dir / "future_import_manifest_template.json"),
            "parser_fixture_validation": _rel(output_dir / "parser_fixture_validation.json"),
        },
    }
    if write_outputs:
        write_report(report, output_dir=output_dir, docs_report=docs_report)
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Flow-Extreme Source Repair Packet",
        "",
        f"- Status: `{report['status']}`",
        f"- Source family: `{report['source_family']}`",
        f"- Current flow input status: `{report['point_in_time_flow_extreme_input_status']}`",
        f"- Future import executed: `{str(report['future_import_command_executed']).lower()}`",
        f"- Accepted profitability: `{str(report['accepted_profitability']).lower()}`",
        "",
        "This is a read-only source-repair packet. It does not import flow rows, write real source_rows.jsonl, mutate evidence stores, run replay, create trades, enable live validation, enable auto-track, touch broker/order paths, lower proof bars, or promote any lane.",
        "",
        "## Future Commands",
        "",
        "```powershell",
        report["future_import_command"],
    ]
    lines.extend(report["downstream_readiness_commands"].values())
    lines.extend(["```", ""])
    return "\n".join(lines)


def write_report(report: dict[str, Any], *, output_dir: Path, docs_report: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    (output_dir / "latest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    (output_dir / "latest.md").write_text(render_markdown(report), encoding="utf8")
    docs_report.write_text(render_markdown(report), encoding="utf8")
    (output_dir / "future_import_manifest_template.json").write_text(
        json.dumps(report["future_import_manifest_template"], indent=2, sort_keys=True) + "\n",
        encoding="utf8",
    )
    (output_dir / "parser_fixture_validation.json").write_text(
        json.dumps(report["fixture_validation"], indent=2, sort_keys=True) + "\n",
        encoding="utf8",
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a read-only flow-extreme source repair packet.")
    parser.add_argument("--lookback-start-date", default="2023-06-01")
    parser.add_argument("--target-start-date", default="2024-06-01")
    parser.add_argument("--target-end-date", default="2026-05-31")
    parser.add_argument("--as-of-date", default="2026-06-04")
    parser.add_argument("--underlyings", default="SPY,QQQ")
    parser.add_argument("--source-family", default=SOURCE_FAMILY)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--no-import", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    underlyings = tuple(item.strip().upper() for item in args.underlyings.split(",") if item.strip())
    report = build_report(
        lookback_start_date=args.lookback_start_date,
        target_start_date=args.target_start_date,
        target_end_date=args.target_end_date,
        as_of_date=args.as_of_date,
        underlyings=underlyings,
        source_family=args.source_family,
        fixture_path=args.fixture,
        output_dir=args.output_dir,
        docs_report=args.docs_report,
        no_import=args.no_import,
    )
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
