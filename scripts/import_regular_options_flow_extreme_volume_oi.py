from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_regular_options_flow_extreme_source_repair_packet as source_packet
from scripts import build_regular_options_point_in_time_flow_extreme_input as flow_input


REPORT_ID = "regular_options_flow_extreme_volume_oi_source_import"
APPROVAL_TOKEN = "APPROVE_FLOW_EXTREME_VOLUME_OI_SOURCE_IMPORT"
SOURCE_FAMILY = "trusted_option_volume_open_interest_daily_v1"
DEFAULT_SOURCE_ROWS = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-flow-extreme-input" / "source_rows.jsonl"
DEFAULT_FEATURE_STORE = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-flow-extreme-volume-oi-source-import"
DEFAULT_DOC = ROOT / "docs" / "regular-options-flow-extreme-volume-oi-source-import.md"

READ_ONLY_FLAGS = {
    "accepted_profitability": False,
    "historical_replay_performed": False,
    "historical_rows_are_forward_proof": False,
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


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _parse_date(value: Any) -> date:
    return datetime.fromisoformat(str(value)).date()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf8"))
    return payload if isinstance(payload, dict) else {}


def _feature_dates(path: Path, *, start: date, end: date, as_of: date) -> list[str]:
    payload = _load_json(path)
    dates: list[str] = []
    for value in payload.get("shared_quote_dates", []):
        parsed = _parse_date(value)
        if start <= parsed <= end and parsed <= as_of:
            dates.append(parsed.isoformat())
    return sorted(set(dates))


def _split_underlyings(value: str) -> tuple[str, ...]:
    return tuple(item.strip().upper() for item in str(value).replace(";", ",").split(",") if item.strip())


def _pressure_score(volume: Any, open_interest: Any) -> float:
    return round(math.log1p(float(volume)) + 0.25 * math.log1p(float(open_interest)), 6)


def _index_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    indexed: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        indexed[str(row["underlying"]).upper()][str(row["source_date"])] = row
    return indexed


def _materialize_rows(
    rows: list[dict[str, Any]],
    *,
    requested_dates: list[str],
    underlyings: tuple[str, ...],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    indexed = _index_rows(rows)
    materialized: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for input_date in requested_dates:
        for underlying in underlyings:
            source_dates = sorted(day for day in indexed.get(underlying, {}) if day < input_date)
            if not source_dates:
                rejected.append({"input_date_et": input_date, "underlying": underlying, "reason": "no_prior_source_date"})
                continue
            row = indexed[underlying][source_dates[-1]]
            call_score = _pressure_score(row["call_volume"], row["call_open_interest"])
            put_score = _pressure_score(row["put_volume"], row["put_open_interest"])
            ratio = round(put_score / call_score, 6) if call_score > 0 else 0.0
            extreme_state = "neutral"
            if ratio >= 1.15:
                extreme_state = "put_pressure_extreme"
            elif ratio <= 0.85:
                extreme_state = "call_pressure_extreme"
            materialized.append(
                {
                    "input_date_et": input_date,
                    "underlying": underlying,
                    "flow_input_basis": "volume_open_interest",
                    "call_pressure_score": call_score,
                    "put_pressure_score": put_score,
                    "put_call_pressure_ratio": ratio,
                    "extreme_state": extreme_state,
                    "threshold_policy_id": "volume_open_interest_prior_day_trailing_distribution_v1",
                    "source_name": "trusted_option_volume_open_interest_daily_csv",
                    "source_ref": f"{row['source_url_or_file_name']}:{row['source_date']}:{underlying}",
                    "source_timestamp_utc": row["known_at_utc"],
                    "known_at_utc": row["known_at_utc"],
                    "point_in_time_valid": True,
                    "source_provenance_status": "trusted_local_or_contract_declared",
                    "source_frequency": "prior_day_aggregate",
                    "source_family": SOURCE_FAMILY,
                    "source_date_et": row["source_date"],
                    "source_file_hash": row["source_file_hash"],
                    "source_row_hash": row["source_row_hash"],
                    "proof_eligible": False,
                }
            )
    return materialized, rejected


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + ("\n" if rows else ""), encoding="utf8")


def build_report(
    *,
    source_file: Path,
    lookback_start_date: str = "2023-06-01",
    target_start_date: str = "2024-06-01",
    target_end_date: str = "2026-05-31",
    as_of_date: str = "2026-06-04",
    underlyings: str = "SPY,QQQ",
    source_family: str = SOURCE_FAMILY,
    approval_token: str = "",
    no_replay: bool = True,
    source_rows_path: Path = DEFAULT_SOURCE_ROWS,
    feature_store_path: Path = DEFAULT_FEATURE_STORE,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    symbols = _split_underlyings(underlyings)
    blockers: list[str] = []
    if approval_token != APPROVAL_TOKEN:
        blockers.append("missing_or_invalid_approval_token")
    if source_family != SOURCE_FAMILY:
        blockers.append("unsupported_source_family")
    if symbols != source_packet.ALLOWED_UNDERLYINGS:
        blockers.append("unsupported_underlyings")
    if not no_replay:
        blockers.append("no_replay_flag_required")
    if not source_file.exists():
        blockers.append("source_file_missing")

    materialized: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    downstream: dict[str, Any] | None = None
    if not blockers:
        parsed, parser_rejects = source_packet.parse_flow_csv(source_file, underlyings=symbols)
        if parser_rejects:
            blockers.append("flow_source_csv_rows_rejected")
        requested_dates = _feature_dates(
            feature_store_path,
            start=_parse_date(target_start_date),
            end=_parse_date(target_end_date),
            as_of=_parse_date(as_of_date),
        )
        materialized, rejected = _materialize_rows(parsed, requested_dates=requested_dates, underlyings=symbols)
        if rejected:
            blockers.append("flow_input_source_row_materialization_rejected_dates")
        if not materialized:
            blockers.append("no_flow_source_rows_materialized")
        if not blockers:
            _write_jsonl(source_rows_path, materialized)
            downstream = flow_input.build_report(
                source_rows_path=source_rows_path,
                feature_store_path=feature_store_path,
                start_date=target_start_date,
                end_date=target_end_date,
                as_of_date=as_of_date,
                underlyings=",".join(symbols),
                no_write=True,
                generated_at_utc=generated_at_utc,
            )
            if downstream.get("status") != "point_in_time_flow_extreme_input_available":
                blockers.append("downstream_flow_extreme_input_validation_failed")

    status = "flow_extreme_volume_oi_source_import_materialized" if not blockers else "blocked_flow_extreme_volume_oi_source_import"
    coverage = downstream.get("coverage") if downstream else {}
    return {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": status,
        **READ_ONLY_FLAGS,
        "source_file": _rel(source_file),
        "source_family": source_family,
        "approval_token_valid": approval_token == APPROVAL_TOKEN,
        "no_replay": no_replay,
        "lookback_start_date": lookback_start_date,
        "target_start_date": target_start_date,
        "target_end_date": target_end_date,
        "as_of_date": as_of_date,
        "underlyings": list(symbols),
        "source_rows_path": _rel(source_rows_path),
        "source_rows_written": status == "flow_extreme_volume_oi_source_import_materialized",
        "source_row_count": len(materialized),
        "rejected_rows": rejected[:50],
        "blockers": blockers,
        "downstream_flow_extreme_input_status": downstream.get("status") if downstream else None,
        "covered_month_count": coverage.get("covered_month_count") if isinstance(coverage, dict) else None,
        "date_coverage_pct": coverage.get("date_coverage_pct") if isinstance(coverage, dict) else None,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Flow-Extreme Volume/OI Source Import",
        "",
        f"- Status: `{report['status']}`.",
        f"- Source rows written: `{str(report['source_rows_written']).lower()}`.",
        f"- Source rows: `{report['source_row_count']}`.",
        f"- Downstream flow input status: `{report.get('downstream_flow_extreme_input_status')}`.",
        f"- Date coverage: `{report.get('date_coverage_pct')}`.",
        "",
        "This import writes generated flow-extreme source rows only. It does not run replay, import option quotes, mutate evidence stores, create trades, enable live validation, enable auto-track, submit broker orders, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, or promote any lane.",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- `{item}`" for item in report.get("blockers", [])) if report.get("blockers") else lines.append("- None.")
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOC) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"{stamp}.json"
    md_path = output_dir / f"{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    artifacts = {
        "json": _rel(json_path),
        "markdown": _rel(md_path),
        "latest_json": _rel(latest_json),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
    }
    payload = dict(report)
    payload["artifacts"] = artifacts
    markdown = render_markdown(payload)
    for path in (json_path, latest_json):
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")
    for path in (md_path, latest_md, docs_report):
        path.write_text(markdown, encoding="utf8")
    report["artifacts"] = artifacts
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize point-in-time flow-extreme source rows from trusted daily volume/OI CSV.")
    parser.add_argument("--source-file", type=Path, required=True)
    parser.add_argument("--lookback-start-date", default="2023-06-01")
    parser.add_argument("--target-start-date", default="2024-06-01")
    parser.add_argument("--target-end-date", default="2026-05-31")
    parser.add_argument("--as-of-date", default="2026-06-04")
    parser.add_argument("--underlyings", default="SPY,QQQ")
    parser.add_argument("--source-family", default=SOURCE_FAMILY)
    parser.add_argument("--approval-token", default="")
    parser.add_argument("--no-replay", action="store_true")
    parser.add_argument("--source-rows", type=Path, default=DEFAULT_SOURCE_ROWS)
    parser.add_argument("--feature-store", type=Path, default=DEFAULT_FEATURE_STORE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--no-write-report", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    report = build_report(
        source_file=args.source_file,
        lookback_start_date=args.lookback_start_date,
        target_start_date=args.target_start_date,
        target_end_date=args.target_end_date,
        as_of_date=args.as_of_date,
        underlyings=args.underlyings,
        source_family=args.source_family,
        approval_token=args.approval_token,
        no_replay=args.no_replay,
        source_rows_path=args.source_rows,
        feature_store_path=args.feature_store,
    )
    if not args.no_write_report:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    print(json.dumps(report, indent=2, sort_keys=True) if args.json_output else render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
