from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_regular_options_point_in_time_earnings_calendar as earnings_calendar


REPORT_ID = "regular_options_earnings_calendar_source_import"
APPROVAL_TOKEN = "APPROVE_EARNINGS_CALENDAR_SOURCE_IMPORT"
SOURCE_FAMILY = earnings_calendar.SOURCE_FAMILY
DEFAULT_SOURCE_ROWS = earnings_calendar.DEFAULT_SOURCE_ROWS
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-earnings-calendar-source-import"
DEFAULT_DOC = ROOT / "docs" / "regular-options-earnings-calendar-source-import.md"
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
    "historical_replay_performed": False,
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


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf8")).hexdigest()


def _parse_date(value: Any) -> date:
    return datetime.fromisoformat(str(value)[:10]).date()


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + ("\n" if rows else ""), encoding="utf8")


def parse_earnings_calendar_csv(path: Path, *, source_family: str = SOURCE_FAMILY) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf8")
    file_hash = _sha256_text(raw)
    reader = csv.DictReader(raw.splitlines())
    fields = reader.fieldnames or []
    missing = [field for field in CSV_FIELDS if field not in fields]
    if missing:
        raise ValueError(f"missing required CSV fields: {', '.join(missing)}")
    forbidden = [field for field in fields if field.strip().lower() in earnings_calendar.LEAKAGE_KEYS]
    if forbidden:
        raise ValueError(f"leakage fields are not allowed: {', '.join(forbidden)}")
    rows: list[dict[str, Any]] = []
    for index, raw_row in enumerate(reader, start=1):
        symbol = str(raw_row.get("symbol") or "").strip().upper()
        earnings_date = str(raw_row.get("earnings_date_et") or "").strip()[:10]
        row_key = {
            "symbol": symbol,
            "earnings_date_et": earnings_date,
            "source_name": str(raw_row.get("source_name") or "").strip(),
            "row_number": index,
        }
        rows.append(
            {
                "symbol": symbol,
                "earnings_date_et": earnings_date,
                "earnings_time": str(raw_row.get("earnings_time") or "unknown").strip().lower() or "unknown",
                "known_at_utc": str(raw_row.get("known_at_utc") or "").strip(),
                "source_name": str(raw_row.get("source_name") or "").strip(),
                "source_ref": str(raw_row.get("source_url_or_file_name") or "").strip(),
                "source_retrieved_at_utc": str(raw_row.get("source_published_at_utc") or "").strip(),
                "revision_id": str(raw_row.get("revision_status") or "").strip() or "scheduled",
                "point_in_time_valid": True,
                "source_family": source_family,
                "source_file_hash": file_hash,
                "source_row_hash": _sha256_text(json.dumps(row_key, sort_keys=True)),
                "source_calendar_coverage_start_date_et": str(raw_row.get("source_calendar_coverage_start_date_et") or "").strip()[:10],
                "source_calendar_coverage_end_date_et": str(raw_row.get("source_calendar_coverage_end_date_et") or "").strip()[:10],
            }
        )
    return rows


def _parse_utc(value: Any) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _filter_rows(rows: list[dict[str, Any]], *, target_start: date, target_end: date, as_of: date) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    materialized: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for row in rows:
        earnings_date = _parse_date(row["earnings_date_et"])
        coverage_start = _parse_date(row["source_calendar_coverage_start_date_et"])
        coverage_end = _parse_date(row["source_calendar_coverage_end_date_et"])
        if coverage_end < target_start or coverage_start > target_end:
            continue
        known_at = _parse_utc(row.get("known_at_utc"))
        if known_at.date() > as_of:
            rejected.append({"symbol": row.get("symbol"), "earnings_date_et": row.get("earnings_date_et"), "reason": "known_at_after_as_of_date"})
            continue
        materialized.append(row)
    return materialized, rejected


def build_report(
    *,
    source_file: Path,
    target_start_date: str = earnings_calendar.DEFAULT_WINDOW_START,
    target_end_date: str = earnings_calendar.DEFAULT_WINDOW_END,
    as_of_date: str = "2026-06-04",
    source_family: str = SOURCE_FAMILY,
    required_equity_symbols: str = ",".join(earnings_calendar.DEFAULT_EQUITY_SYMBOLS),
    approval_token: str = "",
    no_replay: bool = True,
    source_rows_path: Path = DEFAULT_SOURCE_ROWS,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    if approval_token != APPROVAL_TOKEN:
        blockers.append("missing_or_invalid_approval_token")
    if source_family != SOURCE_FAMILY:
        blockers.append("unsupported_source_family")
    if not no_replay:
        blockers.append("no_replay_flag_required")
    if not source_file.exists():
        blockers.append("source_file_missing")
    materialized: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    downstream: dict[str, Any] | None = None
    if not blockers:
        parsed = parse_earnings_calendar_csv(source_file, source_family=source_family)
        materialized, rejected = _filter_rows(
            parsed,
            target_start=_parse_date(target_start_date),
            target_end=_parse_date(target_end_date),
            as_of=_parse_date(as_of_date),
        )
        if rejected:
            blockers.append("earnings_calendar_rows_rejected")
        if not materialized:
            blockers.append("no_earnings_calendar_rows_materialized")
        if not blockers:
            validation_path = source_rows_path.with_suffix(source_rows_path.suffix + ".validation_tmp")
            _write_jsonl(validation_path, materialized)
            downstream = earnings_calendar.build_report(
                source_rows_path=validation_path,
                window_start=target_start_date,
                window_end=target_end_date,
                required_equity_symbols=earnings_calendar._parse_symbols(required_equity_symbols),
                generated_at_utc=generated_at_utc,
            )
            if downstream.get("status") != "point_in_time_earnings_calendar_ready":
                blockers.append("downstream_earnings_calendar_validation_failed")
            else:
                _write_jsonl(source_rows_path, materialized)
            if validation_path.exists():
                validation_path.unlink()
    status = "earnings_calendar_source_import_materialized" if not blockers else "blocked_earnings_calendar_source_import"
    return {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": status,
        **READ_ONLY_FLAGS,
        "source_file": _rel(source_file),
        "source_family": source_family,
        "approval_token_valid": approval_token == APPROVAL_TOKEN,
        "no_replay": no_replay,
        "target_start_date": target_start_date,
        "target_end_date": target_end_date,
        "as_of_date": as_of_date,
        "source_rows_path": _rel(source_rows_path),
        "source_rows_written": status == "earnings_calendar_source_import_materialized",
        "source_row_count": len(materialized),
        "rejected_rows": rejected[:50],
        "required_equity_symbols": list(earnings_calendar._parse_symbols(required_equity_symbols)),
        "blockers": blockers,
        "downstream_earnings_calendar_status": downstream.get("status") if downstream else None,
        "covered_equity_symbols": downstream.get("covered_equity_symbols") if downstream else [],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Earnings Calendar Source Import",
        "",
        f"- Status: `{report['status']}`.",
        f"- Source rows written: `{str(report['source_rows_written']).lower()}`.",
        f"- Source rows: `{report['source_row_count']}`.",
        f"- Downstream earnings calendar status: `{report.get('downstream_earnings_calendar_status')}`.",
        "",
        "This import writes generated earnings-calendar source rows only. It does not run replay, import quotes, mutate evidence stores, create trades, enable live validation, enable auto-track, submit broker orders, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, or promote any lane.",
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
    parser = argparse.ArgumentParser(description="Materialize point-in-time earnings calendar source rows from a trusted CSV.")
    parser.add_argument("--source-file", type=Path, required=True)
    parser.add_argument("--target-start-date", default=earnings_calendar.DEFAULT_WINDOW_START)
    parser.add_argument("--target-end-date", default=earnings_calendar.DEFAULT_WINDOW_END)
    parser.add_argument("--as-of-date", default="2026-06-04")
    parser.add_argument("--source-family", default=SOURCE_FAMILY)
    parser.add_argument("--required-equity-symbols", default=",".join(earnings_calendar.DEFAULT_EQUITY_SYMBOLS))
    parser.add_argument("--approval-token", default="")
    parser.add_argument("--no-replay", action="store_true")
    parser.add_argument("--source-rows", type=Path, default=DEFAULT_SOURCE_ROWS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--no-write-report", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    report = build_report(
        source_file=args.source_file,
        target_start_date=args.target_start_date,
        target_end_date=args.target_end_date,
        as_of_date=args.as_of_date,
        source_family=args.source_family,
        required_equity_symbols=args.required_equity_symbols,
        approval_token=args.approval_token,
        no_replay=args.no_replay,
        source_rows_path=args.source_rows,
    )
    if not args.no_write_report:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    print(json.dumps(report, indent=2, sort_keys=True) if args.json_output else render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
