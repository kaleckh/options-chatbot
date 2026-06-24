from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORT_ID = "regular_options_direct_vix_source_repair_packet"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-direct-vix-source-repair-packet"
DEFAULT_DOC = ROOT / "docs" / "regular-options-direct-vix-source-repair-packet.md"
DEFAULT_FIXTURE = ROOT / "tests" / "fixtures" / "vix" / "cboe_vix_daily_sample.csv"
DEFAULT_ORACLE_PACKET = ROOT / "data" / "forward-tracking" / "options_oracle_profit_loop_packet_latest.json"
DEFAULT_VIX_BUCKET = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-vix-bucket" / "latest.json"
DEFAULT_FORWARD_HOLDOUT = ROOT / "data" / "contracts" / "forward-holdout-contract.json"
REQUIRED_FIELDS = (
    "source_date",
    "vix_open",
    "vix_high",
    "vix_low",
    "vix_close",
    "source_name",
    "source_file_hash",
    "source_row_hash",
    "known_at_utc",
    "tradable_after_et",
    "source_batch_id",
)
CSV_FIELDS = ("Date", "Open", "High", "Low", "Close")
MARKET_HOLIDAYS = {
    date(2024, 5, 27),
    date(2024, 6, 19),
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
    "downstream_vix_bucket_command_executed": False,
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
READINESS_ARTIFACTS = {
    "momentum_continuation": ROOT / "data" / "profitability-lab" / "regular-options-momentum-continuation-bounded-replay" / "latest.json",
    "pmcc_diagonal": ROOT / "data" / "profitability-lab" / "regular-options-pmcc-diagonal-replay-readiness" / "latest.json",
    "macro_event_long_strangle": ROOT / "data" / "profitability-lab" / "regular-options-macro-event-long-strangle-replay-readiness" / "latest.json",
    "vrp_credit_spread": ROOT / "data" / "profitability-lab" / "regular-options-vrp-credit-spread-replay-readiness" / "latest.json",
    "flow_extreme_ratio_backspread": ROOT / "data" / "profitability-lab" / "regular-options-flow-extreme-ratio-backspread-replay-readiness" / "latest.json",
    "dispersion_proxy_hybrid": ROOT / "data" / "profitability-lab" / "regular-options-dispersion-proxy-hybrid-replay-readiness" / "latest.json",
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


def _business_next(day: date) -> date:
    current = day + timedelta(days=1)
    while current.weekday() >= 5 or current in MARKET_HOLIDAYS:
        current += timedelta(days=1)
    return current


def _parse_date(value: str) -> date:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"invalid VIX date: {value!r}")


def _parse_float(value: str, field: str) -> float:
    try:
        return float(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"invalid {field}: {value!r}") from exc


def bucket_for_prior_close(prior_vix_close: float | None) -> dict[str, Any]:
    if prior_vix_close is None:
        return {"bucket": None, "low_mid": None}
    if prior_vix_close < 15:
        bucket = "low"
    elif prior_vix_close <= 25:
        bucket = "mid"
    else:
        bucket = "high"
    return {"bucket": bucket, "low_mid": prior_vix_close <= 25}


def parse_vix_csv(path: Path, *, source_name: str = "operator_supplied_cboe_vix_daily_csv") -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf8")
    file_hash = _sha256_text(raw)
    rows: list[dict[str, Any]] = []
    reader = csv.DictReader(raw.splitlines())
    missing = [field for field in CSV_FIELDS if field not in (reader.fieldnames or [])]
    if missing:
        raise ValueError(f"missing required CSV fields: {', '.join(missing)}")
    prior_closes: list[float] = []
    for index, raw_row in enumerate(reader, start=1):
        source_date = _parse_date(str(raw_row["Date"]))
        values = {
            "vix_open": _parse_float(str(raw_row["Open"]), "Open"),
            "vix_high": _parse_float(str(raw_row["High"]), "High"),
            "vix_low": _parse_float(str(raw_row["Low"]), "Low"),
            "vix_close": _parse_float(str(raw_row["Close"]), "Close"),
        }
        if min(values.values()) < 0:
            raise ValueError("VIX values must be non-negative")
        prior_close = prior_closes[-1] if prior_closes else None
        bucket = bucket_for_prior_close(prior_close)
        row_key = {
            "source_date": source_date.isoformat(),
            **values,
            "source_name": source_name,
            "row_number": index,
        }
        next_session = _business_next(source_date)
        prior_window = prior_closes[-252:]
        rows.append(
            {
                "source_date": source_date.isoformat(),
                **values,
                "source_name": source_name,
                "source_file_hash": file_hash,
                "source_row_hash": _sha256_text(json.dumps(row_key, sort_keys=True)),
                "known_at_utc": f"{source_date.isoformat()}T21:15:00Z",
                "tradable_after_et": f"{next_session.isoformat()}T09:30:00 America/New_York",
                "source_batch_id": "future_tokened_direct_vix_import_batch",
                "prior_vix_close": prior_close,
                "bucket_policy": "vix_prior_close_fixed_buckets_v1",
                "prior_close_bucket": bucket["bucket"],
                "prior_close_low_mid": bucket["low_mid"],
                "rolling_252_percentile": None if not prior_window else sum(1 for value in prior_window if value <= values["vix_close"]) / len(prior_window),
                "rolling_252_percentile_basis": "strictly_prior_rows_only",
            }
        )
        prior_closes.append(values["vix_close"])
    return rows


def row_is_safe_for_candidate(row: dict[str, Any], *, candidate_entry_date: str) -> bool:
    return date.fromisoformat(str(row["source_date"])) < date.fromisoformat(candidate_entry_date)


def _fixture_validation(path: Path, *, protected_holdout_start: str | None) -> dict[str, Any]:
    errors: list[str] = []
    rows: list[dict[str, Any]] = []
    try:
        rows = parse_vix_csv(path)
    except ValueError as exc:
        errors.append(str(exc))
    same_day_safe = False
    next_day_safe = False
    if rows:
        same_day_safe = row_is_safe_for_candidate(rows[0], candidate_entry_date=rows[0]["source_date"])
        next_day_safe = row_is_safe_for_candidate(rows[0], candidate_entry_date=rows[1]["source_date"])
    holdout_overlap = 0
    if protected_holdout_start:
        holdout_overlap = sum(1 for row in rows if row["source_date"] >= protected_holdout_start)
    return {
        "fixture_path": _rel(path),
        "row_count": len(rows),
        "errors": errors,
        "required_fields_present": not errors,
        "sample_rows": rows,
        "weekend_gap_case_present": any(
            (
                date.fromisoformat(rows[index + 1]["source_date"]) - date.fromisoformat(rows[index]["source_date"])
            ).days > 1
            for index in range(max(len(rows) - 1, 0))
        ),
        "same_day_vix_close_safe_for_same_day_entry": same_day_safe,
        "prior_vix_close_safe_for_next_session_entry": next_day_safe,
        "known_at_safe": bool(rows) and not same_day_safe and next_day_safe,
        "protected_holdout_overlap_rows": holdout_overlap,
        "leakage_reject_count": 0 if rows and not same_day_safe else 1,
    }


def _blocked_branch_implications(artifacts: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    implications: list[dict[str, Any]] = []
    for branch, payload in artifacts.items():
        blockers = _as_list(payload.get("blockers")) or _as_list(payload.get("replay_gate_blockers"))
        vix_blockers = [item for item in blockers if "vix" in str(item).lower()]
        implications.append(
            {
                "branch": branch,
                "status": payload.get("status"),
                "vix_blockers": vix_blockers,
                "would_clear_vix_blocker_if_future_source_passes": bool(vix_blockers),
                "remaining_non_vix_blockers": [item for item in blockers if item not in vix_blockers],
            }
        )
    return implications


def build_report(
    *,
    lookback_start_date: str = "2023-05-22",
    target_start_date: str = "2024-06-01",
    target_end_date: str = "2026-05-31",
    as_of_date: str = "2026-06-04",
    source_family: str = "direct_vix_daily_close",
    fixture_path: Path = DEFAULT_FIXTURE,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOC,
    no_import: bool = True,
    write_outputs: bool = True,
) -> dict[str, Any]:
    oracle_packet = _load_json(DEFAULT_ORACLE_PACKET)
    vix_bucket = _load_json(DEFAULT_VIX_BUCKET)
    holdout = _load_json(DEFAULT_FORWARD_HOLDOUT)
    protected_holdout_start = holdout.get("protected_holdout_start") or holdout.get("holdout_start_date")
    artifacts = {name: _load_json(path) for name, path in READINESS_ARTIFACTS.items()}
    fixture_validation = _fixture_validation(fixture_path, protected_holdout_start=protected_holdout_start)
    implications = _blocked_branch_implications(artifacts)
    vix_unblocked_count = sum(1 for item in implications if item["would_clear_vix_blocker_if_future_source_passes"])
    blockers: list[str] = []
    if source_family != "direct_vix_daily_close":
        blockers.append("blocked_no_safe_direct_vix_source_policy")
    if fixture_validation["errors"] or not fixture_validation["known_at_safe"]:
        blockers.append("blocked_vix_parser_contract_unsafe")
    if vix_unblocked_count < 2:
        blockers.append("blocked_vix_packet_only_no_downstream_value")
    status = "blocked_direct_vix_source_repair_packet" if blockers else "direct_vix_source_repair_packet_ready_for_operator_import_decision"
    future_import_command = (
        "npm run options:source-import:direct-vix -- "
        "--source-file data/import-staging/vix/cboe_vix_daily_history.csv "
        "--lookback-start-date 2023-05-22 --target-start-date 2024-06-01 "
        "--target-end-date 2026-05-31 --as-of-date 2026-06-04 "
        "--source-family direct_vix_daily_close "
        "--approval-token APPROVE_DIRECT_VIX_SOURCE_IMPORT --no-replay --json"
    )
    downstream_command = (
        "npm run options:research:point-in-time-vix-bucket -- "
        "--source-family direct_vix_daily_close --as-of-date 2026-06-04 --json"
    )
    current = _as_dict(oracle_packet.get("profitability_target"))
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
        "point_in_time_vix_bucket_status": vix_bucket.get("status"),
        "vix_source_rows_count": vix_bucket.get("source_rows_count"),
        "vix_coverage_pct": vix_bucket.get("coverage_pct"),
        "source_schema": {"family": "direct_vix_daily_close", "required_fields": list(REQUIRED_FIELDS)},
        "known_at_policy": {
            "policy_id": "vix_prior_regular_session_close_known_next_session_v1",
            "rule": "VIX close for market date D is known after the regular session closes and is tradable no earlier than the next market session before regular options candidate entry.",
            "same_day_vix_close_for_same_day_entry_allowed": False,
        },
        "bucket_policy": {
            "policy_id": "vix_prior_close_fixed_buckets_v1",
            "low": "prior_vix_close < 15",
            "mid": "15 <= prior_vix_close <= 25",
            "high": "prior_vix_close > 25",
            "low_mid": "prior_vix_close <= 25",
            "rolling_252_percentile": "diagnostic_only_strictly_prior_rows",
        },
        "future_import_readiness_gates": {
            "minimum_prior_observations_before_target_start": 252,
            "target_window_date_coverage_min_pct": 90.0,
            "latest_four_months": ["2026-02", "2026-03", "2026-04", "2026-05"],
            "latest_four_date_coverage_min_pct": 90.0,
            "known_at_safe_required": True,
            "leakage_reject_count_required": 0,
            "protected_holdout_overlap_rows_required": 0,
            "required_fields_present_required": True,
        },
        "fixture_validation": fixture_validation,
        "vix_blocked_branch_implications": implications,
        "future_import_manifest_template": {
            "source_file": "data/import-staging/vix/cboe_vix_daily_history.csv",
            "source_family": "direct_vix_daily_close",
            "write_target": "generated point-in-time VIX source artifact only",
            "date_window": {"start": lookback_start_date, "end": as_of_date},
            "protected_holdout_consumption_allowed": False,
            "required_approval_token": "APPROVE_DIRECT_VIX_SOURCE_IMPORT",
            "required_fields": list(REQUIRED_FIELDS),
        },
        "future_import_command": future_import_command,
        "downstream_vix_bucket_materialization_command": downstream_command,
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
        "# Regular Options Direct VIX Source Repair Packet",
        "",
        f"- Status: `{report['status']}`",
        f"- Source family: `{report['source_family']}`",
        f"- Current VIX bucket status: `{report['point_in_time_vix_bucket_status']}`",
        f"- VIX source rows: `{report['vix_source_rows_count']}`",
        f"- VIX coverage: `{report['vix_coverage_pct']}`",
        f"- Future import executed: `{str(report['future_import_command_executed']).lower()}`",
        f"- Downstream VIX bucket command executed: `{str(report['downstream_vix_bucket_command_executed']).lower()}`",
        f"- Accepted profitability: `{str(report['accepted_profitability']).lower()}`",
        "",
        "This is a read-only source-repair packet. It does not import VIX rows, mutate evidence stores, run replay, create trades, enable live validation, enable auto-track, touch broker/order paths, lower proof bars, or promote any lane.",
        "",
        "## Future Approval Question",
        "",
        "Approve a future non-live, non-broker, tokened direct VIX source import/materialization from an operator-supplied official daily VIX CSV into a generated point-in-time VIX source artifact only, with no protected-holdout consumption and no replay until coverage and known-at gates pass.",
        "",
        "## VIX-Blocked Branches",
        "",
    ]
    for item in report["vix_blocked_branch_implications"]:
        lines.append(
            f"- `{item['branch']}`: VIX blockers `{item['vix_blockers']}`; remaining non-VIX blockers `{item['remaining_non_vix_blockers']}`"
        )
    lines.extend(["", "## Future Commands", "", "```powershell", report["future_import_command"], report["downstream_vix_bucket_materialization_command"], "```", ""])
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
    parser = argparse.ArgumentParser(description="Build a read-only direct VIX source repair packet.")
    parser.add_argument("--lookback-start-date", default="2023-05-22")
    parser.add_argument("--target-start-date", default="2024-06-01")
    parser.add_argument("--target-end-date", default="2026-05-31")
    parser.add_argument("--as-of-date", default="2026-06-04")
    parser.add_argument("--source-family", default="direct_vix_daily_close")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--no-import", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    report = build_report(
        lookback_start_date=args.lookback_start_date,
        target_start_date=args.target_start_date,
        target_end_date=args.target_end_date,
        as_of_date=args.as_of_date,
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
