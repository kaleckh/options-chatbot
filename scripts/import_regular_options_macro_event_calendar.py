from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_regular_options_macro_event_calendar as calendar
from scripts import build_regular_options_macro_event_calendar_source_repair_packet as source_packet


REPORT_ID = "regular_options_macro_event_calendar_source_import"
APPROVAL_TOKEN = "APPROVE_MACRO_EVENT_CALENDAR_SOURCE_IMPORT"
SOURCE_FAMILY = "scheduled_macro_event_calendar_v1"
DEFAULT_SOURCE_ROWS = ROOT / "data" / "profitability-lab" / "regular-options-macro-event-calendar" / "source_rows.jsonl"
DEFAULT_FEATURE_STORE = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-macro-event-calendar-source-import"
DEFAULT_DOC = ROOT / "docs" / "regular-options-macro-event-calendar-source-import.md"

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


def _parse_date(value: Any) -> date:
    return datetime.fromisoformat(str(value)).date()


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + ("\n" if rows else ""), encoding="utf8")


def _normalize_required(value: str) -> list[str]:
    return [source_packet._normalize_category(item) for item in str(value).split(",") if item.strip()]


def _event_date(row: dict[str, Any]) -> date:
    return _parse_date(str(row["scheduled_event_datetime_et"])[:10])


def _materialize_rows(rows: list[dict[str, Any]], *, target_start: date, target_end: date, as_of: date) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    materialized: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for row in rows:
        event_day = _event_date(row)
        if event_day < target_start or event_day > target_end:
            continue
        if event_day > as_of:
            rejected.append({"event_id": row.get("event_id"), "reason": "event_after_as_of_date"})
            continue
        materialized.append(
            {
                "event_id": row["event_id"],
                "event_category": row["event_category"],
                "event_timestamp_utc": row["scheduled_event_datetime_utc"],
                "event_date_et": event_day.isoformat(),
                "known_at_utc": row["known_at_utc"],
                "source_name": row["source_name"],
                "source_ref": row["source_url_or_file_name"],
                "source_retrieved_at_utc": row["source_published_at_utc"],
                "revision_id": row["revision_status"],
                "point_in_time_valid": True,
                "source_family": SOURCE_FAMILY,
                "source_file_hash": row["source_file_hash"],
                "source_row_hash": row["source_row_hash"],
                "tradable_after_et": row["tradable_after_et"],
                "proof_eligible": False,
            }
        )
    return materialized, rejected


def build_report(
    *,
    source_file: Path,
    target_start_date: str = "2024-06-01",
    target_end_date: str = "2026-05-31",
    as_of_date: str = "2026-06-04",
    source_family: str = SOURCE_FAMILY,
    required_categories: str = ",".join(source_packet.REQUIRED_CATEGORIES),
    approval_token: str = "",
    no_replay: bool = True,
    source_rows_path: Path = DEFAULT_SOURCE_ROWS,
    feature_store_path: Path = DEFAULT_FEATURE_STORE,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    required = _normalize_required(required_categories)
    if approval_token != APPROVAL_TOKEN:
        blockers.append("missing_or_invalid_approval_token")
    if source_family != SOURCE_FAMILY:
        blockers.append("unsupported_source_family")
    if sorted(required) != sorted(source_packet.REQUIRED_CATEGORIES):
        blockers.append("required_categories_mismatch")
    if not no_replay:
        blockers.append("no_replay_flag_required")
    if not source_file.exists():
        blockers.append("source_file_missing")

    materialized: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    downstream: dict[str, Any] | None = None
    if not blockers:
        parsed = source_packet.parse_macro_event_csv(source_file)
        materialized, rejected = _materialize_rows(
            parsed,
            target_start=_parse_date(target_start_date),
            target_end=_parse_date(target_end_date),
            as_of=_parse_date(as_of_date),
        )
        covered = {row["event_category"] for row in materialized}
        missing = sorted(set(source_packet.REQUIRED_CATEGORIES) - covered)
        if rejected:
            blockers.append("macro_event_rows_rejected")
        if missing:
            blockers.append("missing_required_macro_event_categories")
        if not materialized:
            blockers.append("no_macro_event_rows_materialized")
        if not blockers:
            _write_jsonl(source_rows_path, materialized)
            downstream = calendar.build_report(
                source_rows_path=source_rows_path,
                feature_store_path=feature_store_path,
                generated_at_utc=generated_at_utc,
            )
            if downstream.get("status") != "macro_event_calendar_ready_for_readiness_recheck":
                blockers.append("downstream_macro_event_calendar_validation_failed")

    status = "macro_event_calendar_source_import_materialized" if not blockers else "blocked_macro_event_calendar_source_import"
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
        "source_rows_written": status == "macro_event_calendar_source_import_materialized",
        "source_row_count": len(materialized),
        "rejected_rows": rejected[:50],
        "blockers": blockers,
        "downstream_macro_event_calendar_status": downstream.get("status") if downstream else None,
        "covered_categories": downstream.get("covered_categories") if downstream else sorted({row["event_category"] for row in materialized}),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Macro-Event Calendar Source Import",
        "",
        f"- Status: `{report['status']}`.",
        f"- Source rows written: `{str(report['source_rows_written']).lower()}`.",
        f"- Source rows: `{report['source_row_count']}`.",
        f"- Downstream calendar status: `{report.get('downstream_macro_event_calendar_status')}`.",
        "",
        "This import writes generated macro-event calendar source rows only. It does not run replay, import option quotes, mutate evidence stores, create trades, enable live validation, enable auto-track, submit broker orders, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, or promote any lane.",
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
    parser = argparse.ArgumentParser(description="Materialize point-in-time macro-event calendar source rows from a trusted CSV.")
    parser.add_argument("--source-file", type=Path, required=True)
    parser.add_argument("--target-start-date", default="2024-06-01")
    parser.add_argument("--target-end-date", default="2026-05-31")
    parser.add_argument("--as-of-date", default="2026-06-04")
    parser.add_argument("--source-family", default=SOURCE_FAMILY)
    parser.add_argument("--required-categories", default=",".join(source_packet.REQUIRED_CATEGORIES))
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
        target_start_date=args.target_start_date,
        target_end_date=args.target_end_date,
        as_of_date=args.as_of_date,
        source_family=args.source_family,
        required_categories=args.required_categories,
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
