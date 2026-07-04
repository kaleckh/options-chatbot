from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_regular_options_point_in_time_earnings_calendar as earnings_calendar


REPORT_ID = "regular_options_earnings_calendar_source_repair_packet"
SOURCE_FAMILY = earnings_calendar.SOURCE_FAMILY
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-earnings-calendar-source-repair-packet"
DEFAULT_DOC = ROOT / "docs" / "regular-options-earnings-calendar-source-repair-packet.md"
DEFAULT_FIXTURE = ROOT / "tests" / "fixtures" / "earnings" / "point_in_time_earnings_calendar_sample.csv"
DEFAULT_EARNINGS_CALENDAR = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-earnings-calendar" / "latest.json"
DEFAULT_HISTORICAL_AUDIT = ROOT / "data" / "profitability-lab" / "regular-options-historical-simulated-forward-audit" / "latest.json"
DEFAULT_HISTORICAL_TRACKER = ROOT / "data" / "profitability-lab" / "regular-options-historical-scanner-input-surface-tracker" / "latest.json"
DEFAULT_FORWARD_HOLDOUT = ROOT / "data" / "contracts" / "forward-holdout-contract.json"

CSV_FIELDS = (
    "symbol",
    "earnings_date_et",
    "earnings_time",
    "source_name",
    "source_url_or_file_name",
    "source_published_at_utc",
    "known_at_utc",
    "revision_status",
    "source_calendar_coverage_start_date_et",
    "source_calendar_coverage_end_date_et",
)
READ_ONLY_FLAGS = {
    "accepted_profitability": False,
    "historical_rows_are_forward_proof": False,
    "historical_replay_performed": False,
    "future_import_command_executed": False,
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
    return datetime.fromisoformat(str(value)[:10]).date()


def _parse_utc(value: Any) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_symbols(value: str | Sequence[str]) -> tuple[str, ...]:
    raw = value.split(",") if isinstance(value, str) else list(value)
    return tuple(str(item).strip().upper() for item in raw if str(item).strip())


def parse_earnings_calendar_csv(
    path: Path,
    *,
    required_symbols: Sequence[str] = earnings_calendar.DEFAULT_EQUITY_SYMBOLS,
    source_family: str = SOURCE_FAMILY,
) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf8")
    file_hash = _sha256_text(raw)
    reader = csv.DictReader(raw.splitlines())
    fieldnames = reader.fieldnames or []
    missing = [field for field in CSV_FIELDS if field not in fieldnames]
    if missing:
        raise ValueError(f"missing required CSV fields: {', '.join(missing)}")
    forbidden = [field for field in fieldnames if field.strip().lower() in earnings_calendar.LEAKAGE_KEYS]
    if forbidden:
        raise ValueError(f"leakage fields are not allowed: {', '.join(forbidden)}")

    allowed = set(_parse_symbols(required_symbols))
    rows: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for index, raw_row in enumerate(reader, start=1):
        symbol = str(raw_row.get("symbol") or "").strip().upper()
        earnings_date = _parse_date(raw_row.get("earnings_date_et"))
        source_published = _parse_utc(raw_row.get("source_published_at_utc"))
        known_at = _parse_utc(raw_row.get("known_at_utc"))
        coverage_start = _parse_date(raw_row.get("source_calendar_coverage_start_date_et"))
        coverage_end = _parse_date(raw_row.get("source_calendar_coverage_end_date_et"))
        revision = str(raw_row.get("revision_status") or "").strip() or "scheduled"
        key = (symbol, earnings_date.isoformat(), revision)
        if symbol not in allowed:
            raise ValueError(f"unexpected symbol on row {index}: {symbol}")
        if key in seen_keys:
            raise ValueError(f"duplicate symbol/date/revision row: {symbol} {earnings_date} {revision}")
        if source_published.date() > earnings_date or known_at.date() > earnings_date:
            raise ValueError(f"known_at/source_published after earnings date for {symbol} {earnings_date}")
        if coverage_start > coverage_end or not (coverage_start <= earnings_date <= coverage_end):
            raise ValueError(f"invalid coverage window for {symbol} {earnings_date}")
        seen_keys.add(key)
        row_key = {
            "symbol": symbol,
            "earnings_date_et": earnings_date.isoformat(),
            "source_name": str(raw_row.get("source_name") or "").strip(),
            "row_number": index,
        }
        rows.append(
            {
                "symbol": symbol,
                "earnings_date_et": earnings_date.isoformat(),
                "earnings_time": str(raw_row.get("earnings_time") or "unknown").strip().lower() or "unknown",
                "known_at_utc": known_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
                "source_name": str(raw_row.get("source_name") or "").strip(),
                "source_ref": str(raw_row.get("source_url_or_file_name") or "").strip(),
                "source_retrieved_at_utc": source_published.isoformat(timespec="seconds").replace("+00:00", "Z"),
                "revision_id": revision,
                "point_in_time_valid": True,
                "source_family": source_family,
                "source_file_hash": file_hash,
                "source_row_hash": _sha256_text(json.dumps(row_key, sort_keys=True)),
                "source_calendar_coverage_start_date_et": coverage_start.isoformat(),
                "source_calendar_coverage_end_date_et": coverage_end.isoformat(),
            }
        )
    return rows


def row_known_before_candidate(row: dict[str, Any], *, candidate_decision_utc: str) -> bool:
    decision = _parse_utc(candidate_decision_utc)
    return _parse_utc(row["known_at_utc"]) <= decision and _parse_utc(row["source_retrieved_at_utc"]) <= decision


def _fixture_validation(path: Path, *, protected_holdout_start: str | None) -> dict[str, Any]:
    errors: list[str] = []
    rows: list[dict[str, Any]] = []
    try:
        rows = parse_earnings_calendar_csv(path)
    except (ValueError, OSError) as exc:
        errors.append(str(exc))
    symbols = sorted(Counter(row["symbol"] for row in rows))
    required = set(earnings_calendar.DEFAULT_EQUITY_SYMBOLS)
    coverage_end_required = _parse_date(earnings_calendar.DEFAULT_WINDOW_END) + earnings_calendar.timedelta(days=earnings_calendar.DEFAULT_MAX_DTE)
    per_symbol_coverage: dict[str, dict[str, Any]] = {}
    for symbol in sorted(required):
        symbol_rows = [row for row in rows if row["symbol"] == symbol]
        starts = [_parse_date(row["source_calendar_coverage_start_date_et"]) for row in symbol_rows]
        ends = [_parse_date(row["source_calendar_coverage_end_date_et"]) for row in symbol_rows]
        start = min(starts) if starts else None
        end = max(ends) if ends else None
        per_symbol_coverage[symbol] = {
            "event_count": len(symbol_rows),
            "coverage_start_date_et": start.isoformat() if start else None,
            "coverage_end_date_et": end.isoformat() if end else None,
            "covers_requested_window_plus_max_dte": bool(
                start
                and end
                and start <= _parse_date(earnings_calendar.DEFAULT_WINDOW_START)
                and end >= coverage_end_required
            ),
        }
    holdout_overlap = 0
    if protected_holdout_start:
        holdout_overlap = sum(1 for row in rows if row["earnings_date_et"] >= protected_holdout_start)
    known_at_safe = bool(rows) and all(row_known_before_candidate(row, candidate_decision_utc=row["known_at_utc"]) for row in rows)
    return {
        "fixture_path": _rel(path),
        "row_count": len(rows),
        "errors": errors,
        "sample_rows": rows[:5],
        "required_fields_present": not errors,
        "covered_equity_symbols": symbols,
        "missing_required_symbols": sorted(required - set(symbols)),
        "per_symbol_coverage": per_symbol_coverage,
        "all_required_symbols_present": required <= set(symbols),
        "all_symbols_cover_requested_window_plus_max_dte": all(
            coverage["covers_requested_window_plus_max_dte"] for coverage in per_symbol_coverage.values()
        ),
        "known_at_safe": known_at_safe,
        "leakage_reject_count": 0 if rows and not errors else 1,
        "protected_holdout_overlap_rows": holdout_overlap,
    }


def build_report(
    *,
    target_start_date: str = earnings_calendar.DEFAULT_WINDOW_START,
    target_end_date: str = earnings_calendar.DEFAULT_WINDOW_END,
    as_of_date: str = "2026-06-04",
    max_dte: int = earnings_calendar.DEFAULT_MAX_DTE,
    required_equity_symbols: Sequence[str] = earnings_calendar.DEFAULT_EQUITY_SYMBOLS,
    fixture_path: Path = DEFAULT_FIXTURE,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOC,
    write_outputs: bool = True,
) -> dict[str, Any]:
    earnings_readiness = _load_json(DEFAULT_EARNINGS_CALENDAR)
    audit = _load_json(DEFAULT_HISTORICAL_AUDIT)
    tracker = _load_json(DEFAULT_HISTORICAL_TRACKER)
    holdout = _load_json(DEFAULT_FORWARD_HOLDOUT)
    protected_holdout_start = holdout.get("protected_holdout_start") or holdout.get("holdout_start_date")
    fixture_validation = _fixture_validation(fixture_path, protected_holdout_start=protected_holdout_start)
    normalized_symbols = tuple(sorted(_parse_symbols(required_equity_symbols)))
    blockers: list[str] = []
    if normalized_symbols != tuple(sorted(earnings_calendar.DEFAULT_EQUITY_SYMBOLS)):
        blockers.append("blocked_no_safe_earnings_calendar_symbol_policy")
    if fixture_validation["errors"] or not fixture_validation["all_required_symbols_present"]:
        blockers.append("blocked_earnings_calendar_parser_contract_unsafe")
    if not fixture_validation["all_symbols_cover_requested_window_plus_max_dte"]:
        blockers.append("blocked_earnings_calendar_fixture_coverage_incomplete")
    status = "blocked_earnings_calendar_source_repair_packet" if blockers else "earnings_calendar_source_repair_packet_ready_for_operator_import_decision"
    future_import_command = (
        "npm run options:source-import:earnings-calendar -- "
        "--source-file data/import-staging/earnings/point_in_time_equity_earnings_calendar.csv "
        f"--target-start-date {target_start_date} --target-end-date {target_end_date} --as-of-date {as_of_date} "
        f"--required-equity-symbols {','.join(normalized_symbols)} "
        "--source-family point_in_time_equity_earnings_calendar_v1 "
        "--approval-token APPROVE_EARNINGS_CALENDAR_SOURCE_IMPORT --no-replay --json"
    )
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": _utc_now(),
        "status": status,
        "blockers": blockers,
        "source_family": SOURCE_FAMILY,
        "target_start_date": target_start_date,
        "target_end_date": target_end_date,
        "as_of_date": as_of_date,
        "max_dte": max_dte,
        "coverage_end_required": (_parse_date(target_end_date) + earnings_calendar.timedelta(days=max_dte)).isoformat(),
        "required_equity_symbols": list(normalized_symbols),
        "current_earnings_calendar_status": earnings_readiness.get("status"),
        "current_earnings_calendar_blockers": _as_list(earnings_readiness.get("blockers")),
        "current_missing_equity_symbols": _as_list(earnings_readiness.get("missing_equity_symbols")),
        "historical_audit_status": audit.get("status"),
        "historical_audit_blockers": _as_list(audit.get("blockers")),
        "historical_audit_selected_exact_rows": _as_dict(audit.get("selected_trade_history")).get("accepted_exact_trade_count", 0),
        "historical_audit_selected_month_count": _as_dict(audit.get("selected_trade_history")).get("available_entry_month_count", 0),
        "historical_tracker_status": tracker.get("status"),
        "future_source_schema": {
            "source_file": "data/import-staging/earnings/point_in_time_equity_earnings_calendar.csv",
            "source_family": SOURCE_FAMILY,
            "required_fields": list(CSV_FIELDS),
            "forbidden_leakage_fields": sorted(earnings_calendar.LEAKAGE_KEYS),
            "acceptable_source_requirement": "operator-supplied vendor/export or archive that preserves known_at/source-published timestamps for scheduled earnings dates; current/live calendar lookups are not sufficient for historical point-in-time proof",
        },
        "known_at_policy": {
            "policy_id": "earnings_calendar_known_before_candidate_decision_v1",
            "rule": "Rows are usable only when known_at_utc and source_published_at_utc are no later than the candidate decision timestamp.",
            "future_scheduled_events_allowed": "true when known_at_utc is no later than the audit as-of/source snapshot and the row contains no actuals, estimates, surprises, realized moves, or P&L fields",
            "no_live_lookup_substitution": True,
        },
        "future_import_readiness_gates": {
            "required_fields_present": True,
            "known_at_safe_required": True,
            "leakage_reject_count_required": 0,
            "all_required_symbols_present": True,
            "source_calendar_coverage_required_through": (_parse_date(target_end_date) + earnings_calendar.timedelta(days=max_dte)).isoformat(),
            "protected_holdout_overlap_rows_required": 0,
        },
        "fixture_validation": fixture_validation,
        "downstream_unlocks_after_future_approval_and_valid_source": [
            "historical_scanner_input_surface_tracker clears missing_point_in_time_earnings_calendar_source",
            "historical_frozen_scanner_replay_adapter can emit deterministic earnings-window no-picks for equity rows",
            "historical_simulated_forward_audit can distinguish full denominator blockers from selected-row month gaps",
        ],
        "remaining_non_earnings_blockers_after_valid_source": [
            item
            for item in _as_list(audit.get("blockers"))
            if "earnings" not in str(item).lower()
        ],
        "future_import_manifest_template": {
            "source_file": "data/import-staging/earnings/point_in_time_equity_earnings_calendar.csv",
            "source_family": SOURCE_FAMILY,
            "write_target": "generated point-in-time earnings-calendar source_rows.jsonl only",
            "date_window": {"target_start": target_start_date, "target_end": target_end_date, "as_of": as_of_date},
            "protected_holdout_consumption_allowed": False,
            "required_approval_token": "APPROVE_EARNINGS_CALENDAR_SOURCE_IMPORT",
            "required_equity_symbols": list(normalized_symbols),
            "required_fields": list(CSV_FIELDS),
        },
        "future_import_command": future_import_command,
        "downstream_readiness_commands": {
            "point_in_time_earnings_calendar": "npm run options:research:point-in-time-earnings-calendar -- --json",
            "historical_scanner_input_surface_tracker": "npm run options:research:historical-scanner-input-surface-tracker -- --json",
            "historical_frozen_adapter": "npm run options:research:historical-frozen-scanner-replay-adapter -- --json",
            "historical_simulated_forward_audit": "npm run options:audit:historical-simulated-forward -- --json",
        },
        **READ_ONLY_FLAGS,
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
        "# Regular Options Earnings Calendar Source Repair Packet",
        "",
        f"- Status: `{report['status']}`",
        f"- Source family: `{report['source_family']}`",
        f"- Current earnings calendar status: `{report['current_earnings_calendar_status']}`",
        f"- Current missing symbols: `{report['current_missing_equity_symbols']}`",
        f"- Future import executed: `{str(report['future_import_command_executed']).lower()}`",
        f"- Accepted profitability: `{str(report['accepted_profitability']).lower()}`",
        "",
        "This is a read-only source-repair packet. It does not import earnings rows, run replay, import quotes, mutate evidence stores, create trades, enable live validation, enable auto-track, touch broker/order paths, lower proof bars, or promote any lane.",
        "",
        "## Future Approval Question",
        "",
        "Approve a future non-live, non-broker, tokened earnings-calendar source import/materialization from an operator-supplied point-in-time earnings-calendar CSV into generated source rows only, with no replay and no protected-holdout consumption.",
        "",
        "## Source Rule",
        "",
        report["future_source_schema"]["acceptable_source_requirement"],
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
    parser = argparse.ArgumentParser(description="Build a read-only earnings-calendar source repair packet.")
    parser.add_argument("--target-start-date", default=earnings_calendar.DEFAULT_WINDOW_START)
    parser.add_argument("--target-end-date", default=earnings_calendar.DEFAULT_WINDOW_END)
    parser.add_argument("--as-of-date", default="2026-06-04")
    parser.add_argument("--max-dte", type=int, default=earnings_calendar.DEFAULT_MAX_DTE)
    parser.add_argument("--required-equity-symbols", default=",".join(sorted(earnings_calendar.DEFAULT_EQUITY_SYMBOLS)))
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    report = build_report(
        target_start_date=args.target_start_date,
        target_end_date=args.target_end_date,
        as_of_date=args.as_of_date,
        max_dte=args.max_dte,
        required_equity_symbols=_parse_symbols(args.required_equity_symbols),
        fixture_path=args.fixture,
        output_dir=args.output_dir,
        docs_report=args.docs_report,
    )
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
