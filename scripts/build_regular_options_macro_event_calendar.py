from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_macro_event_calendar"
DEFAULT_SOURCE_ROWS = ROOT / "data" / "profitability-lab" / "regular-options-macro-event-calendar" / "source_rows.jsonl"
DEFAULT_FEATURE_STORE = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-macro-event-calendar"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-macro-event-calendar.md"

REQUIRED_EVENT_CATEGORIES = (
    "fomc_rate_decision",
    "fomc_minutes",
    "cpi",
    "pce",
    "nonfarm_payrolls",
    "scheduled_fed_chair_testimony",
)
REQUIRED_ROW_FIELDS = (
    "event_id",
    "event_category",
    "event_timestamp_utc",
    "event_date_et",
    "known_at_utc",
    "source_name",
    "revision_id",
)
LEAKAGE_KEYS = {
    "actual",
    "forecast",
    "surprise",
    "event_outcome",
    "outcome",
    "realized_move",
    "realized_vol",
    "realized_volatility",
    "future_iv",
    "post_event_iv",
    "option_return",
    "post_event_return",
    "pnl",
    "net_pnl",
    "net_pnl_usd",
}
READ_ONLY_FLAGS = {
    "read_only": True,
    "accepted_profitability": False,
    "historical_replay_performed": False,
    "event_calendar_implemented": True,
    "source_rows_proof_eligible": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "promotion_ready": False,
}
FORBIDDEN_ACTIONS = (
    "broker_orders",
    "broker_order_preparation",
    "live_validation",
    "auto_track",
    "production_scanner_changes",
    "strategy_logic_changes",
    "stop_changes",
    "sizing_changes",
    "proof_bar_changes",
    "quote_import",
    "options_history_db_mutation",
    "forward_or_evidence_store_mutation",
    "protected_holdout_consumption",
    "promotion",
    "historical_option_replay",
    "treating_calendar_rows_as_profitability_proof",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalize_category(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    synonyms = {
        "nfp": "nonfarm_payrolls",
        "non_farm_payrolls": "nonfarm_payrolls",
        "fed_chair_testimony": "scheduled_fed_chair_testimony",
        "fed_chair": "scheduled_fed_chair_testimony",
        "chair_testimony": "scheduled_fed_chair_testimony",
        "fomc": "fomc_rate_decision",
    }
    return synonyms.get(text, text)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _load_json(path: Path, *, required: bool) -> tuple[Any, dict[str, Any]]:
    meta = {"path": _rel(path), "required": required, "exists": path.exists(), "status": "missing", "error": None}
    if not path.exists():
        return {}, meta
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        meta["status"] = "malformed"
        meta["error"] = f"JSONDecodeError:{exc.lineno}:{exc.colno}"
        return {}, meta
    except OSError as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return {}, meta
    meta["status"] = "loaded"
    if isinstance(payload, dict):
        meta["generated_at_utc"] = payload.get("generated_at_utc")
        meta["report_id"] = payload.get("report_id")
    return payload, meta


def _load_source_rows(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta = {"path": _rel(path), "required": False, "exists": path.exists(), "status": "missing", "error": None, "row_count": 0}
    if not path.exists():
        return [], meta
    rows: list[dict[str, Any]] = []
    try:
        if path.suffix.lower() == ".jsonl":
            for line_number, line in enumerate(path.read_text(encoding="utf8").splitlines(), start=1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
                else:
                    meta.setdefault("non_object_lines", []).append(line_number)
        else:
            payload = json.loads(path.read_text(encoding="utf8"))
            if isinstance(payload, list):
                rows = [row for row in payload if isinstance(row, dict)]
            elif isinstance(payload, dict):
                for key in ("source_rows", "events", "macro_events", "calendar"):
                    if isinstance(payload.get(key), list):
                        rows = [row for row in payload[key] if isinstance(row, dict)]
                        break
    except json.JSONDecodeError as exc:
        meta["status"] = "malformed"
        meta["error"] = f"JSONDecodeError:{exc.lineno}:{exc.colno}"
        return [], meta
    except OSError as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return [], meta
    meta["status"] = "loaded"
    meta["row_count"] = len(rows)
    return rows, meta


def _find_leakage_keys(row: dict[str, Any]) -> list[str]:
    hits: list[str] = []

    def walk(value: Any, prefix: str = "") -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                key_text = str(key).lower()
                path = f"{prefix}.{key}" if prefix else str(key)
                if key_text in LEAKAGE_KEYS:
                    hits.append(path)
                walk(nested, path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{prefix}[{index}]")

    walk(row)
    return hits


def _source_ref_present(row: dict[str, Any]) -> bool:
    return bool(row.get("source_ref") or row.get("source_url"))


def _source_time_present(row: dict[str, Any]) -> bool:
    return bool(row.get("source_retrieved_at_utc") or row.get("source_published_at_utc"))


def _validate_row(row: dict[str, Any], index: int) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    reasons: list[str] = []
    missing = [field for field in REQUIRED_ROW_FIELDS if row.get(field) in (None, "")]
    if missing:
        reasons.append("missing_required_fields")
    if not _source_ref_present(row):
        reasons.append("missing_source_ref_or_url")
    if not _source_time_present(row):
        reasons.append("missing_source_time")
    category = _normalize_category(row.get("event_category"))
    if category not in REQUIRED_EVENT_CATEGORIES:
        reasons.append("unexpected_event_category")
    event_time = _parse_dt(row.get("event_timestamp_utc"))
    known_at = _parse_dt(row.get("known_at_utc"))
    if not event_time or not known_at:
        reasons.append("missing_or_invalid_event_or_known_at_timestamp")
    elif known_at > event_time:
        reasons.append("known_at_after_event_timestamp")
    if row.get("point_in_time_valid") is not True:
        reasons.append("point_in_time_valid_not_true")
    leakage = _find_leakage_keys(row)
    if leakage:
        reasons.append("leakage_fields_present")
    if reasons:
        return None, {
            "index": index,
            "event_id": row.get("event_id"),
            "event_category": category,
            "reasons": reasons,
            "missing_fields": missing,
            "leakage_keys": leakage,
        }
    accepted = {
        "event_id": str(row["event_id"]),
        "event_category": category,
        "event_timestamp_utc": str(row["event_timestamp_utc"]),
        "event_date_et": str(row["event_date_et"]),
        "known_at_utc": str(row["known_at_utc"]),
        "source_name": str(row["source_name"]),
        "source_ref": str(row.get("source_ref") or row.get("source_url")),
        "source_retrieved_at_utc": str(row.get("source_retrieved_at_utc") or row.get("source_published_at_utc")),
        "revision_id": str(row["revision_id"]),
        "point_in_time_valid": True,
        "proof_eligible": False,
    }
    return accepted, None


def _feature_store_window(payload: Any) -> dict[str, Any]:
    summary = _as_dict(_as_dict(payload).get("summary"))
    return {
        "first_shared_quote_date_et": summary.get("first_shared_quote_date_et"),
        "latest_shared_quote_date_et": summary.get("latest_shared_quote_date_et"),
        "shared_quote_date_count": summary.get("shared_quote_date_count"),
        "feature_store_status": summary.get("overall_status") or _as_dict(payload).get("status"),
    }


def _status(source_meta: dict[str, Any], accepted: list[dict[str, Any]], rejected: list[dict[str, Any]], missing_categories: list[str]) -> str:
    if source_meta.get("status") == "missing" or source_meta.get("row_count") == 0:
        return "blocked_macro_event_calendar_source_missing"
    if rejected or missing_categories:
        return "blocked_macro_event_calendar_validation"
    if accepted:
        return "macro_event_calendar_ready_for_readiness_recheck"
    return "blocked_macro_event_calendar_validation"


def build_report(
    *,
    source_rows_path: Path = DEFAULT_SOURCE_ROWS,
    feature_store_path: Path = DEFAULT_FEATURE_STORE,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    source_rows, source_meta = _load_source_rows(source_rows_path)
    feature_store, feature_store_meta = _load_json(feature_store_path, required=False)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, row in enumerate(source_rows):
        clean, reject = _validate_row(row, index)
        if clean:
            accepted.append(clean)
        if reject:
            rejected.append(reject)
    category_counts = Counter(row["event_category"] for row in accepted)
    covered_categories = sorted(category_counts)
    missing_categories = sorted(set(REQUIRED_EVENT_CATEGORIES) - set(covered_categories))
    leakage_reject_count = sum(1 for row in rejected if "leakage_fields_present" in row["reasons"])
    status = _status(source_meta, accepted, rejected, missing_categories)
    blockers: list[str] = []
    if status == "blocked_macro_event_calendar_source_missing":
        blockers.append("macro_event_calendar_source_missing")
    if missing_categories:
        blockers.append("missing_required_macro_event_categories")
    if rejected:
        blockers.append("macro_event_calendar_row_validation_failed")
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": status,
        **READ_ONLY_FLAGS,
        "source_artifacts": {
            "source_rows": source_meta,
            "feature_store": feature_store_meta,
        },
        "research_window": _feature_store_window(feature_store),
        "required_event_categories": list(REQUIRED_EVENT_CATEGORIES),
        "covered_categories": covered_categories,
        "missing_categories": missing_categories,
        "event_count": len(accepted),
        "source_row_count": source_meta.get("row_count", 0),
        "category_counts": dict(sorted(category_counts.items())),
        "events": accepted,
        "rejected_rows": rejected,
        "leakage_reject_count": leakage_reject_count,
        "blockers": blockers,
        "future_join_policy": "A future replay may join only events where known_at_utc <= candidate_entry_timestamp_utc and event_timestamp_utc is in the frozen entry/exit window.",
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }
    _validate_report(report)
    return report


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    if report["status"] not in {
        "blocked_macro_event_calendar_source_missing",
        "blocked_macro_event_calendar_validation",
        "macro_event_calendar_ready_for_readiness_recheck",
    }:
        raise ValueError(f"unexpected status: {report['status']}")
    for row in _as_list(report.get("events")):
        row_dict = _as_dict(row)
        missing = [field for field in REQUIRED_ROW_FIELDS if row_dict.get(field) in (None, "")]
        if missing:
            raise ValueError(f"accepted event missing required fields: {missing}")
        if row_dict.get("proof_eligible") is not False:
            raise ValueError("calendar row cannot be proof eligible")


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Macro-Event Calendar",
        "",
        "This report is generated from `scripts/build_regular_options_macro_event_calendar.py`. It is a read-only point-in-time calendar validator for scheduled macro-event research. It does not run option replay, import quotes, mutate evidence stores, create trades, enable live validation or auto-track, submit broker orders, change scanner/strategy/stops/sizing/proof bars, consume protected holdout, or promote any lane.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Accepted events: `{report['event_count']}`.",
        f"- Source rows: `{report['source_row_count']}`.",
        f"- Leakage rejects: `{report['leakage_reject_count']}`.",
        "",
        "## Categories",
        "",
        f"- Required: `{json.dumps(report['required_event_categories'])}`.",
        f"- Covered: `{json.dumps(report['covered_categories'])}`.",
        f"- Missing: `{json.dumps(report['missing_categories'])}`.",
        "",
        "## Blockers",
        "",
    ]
    if report.get("blockers"):
        lines.extend(f"- `{item}`" for item in _as_list(report.get("blockers")))
    else:
        lines.append("- None.")
    lines.extend(["", "## Rejected Rows", ""])
    if report.get("rejected_rows"):
        for row in _as_list(report.get("rejected_rows"))[:20]:
            lines.append(f"- `{_as_dict(row).get('event_id')}`: `{json.dumps(_as_dict(row).get('reasons'))}`")
    else:
        lines.append("- None.")
    lines.extend(["", "## Forbidden Actions", ""])
    lines.extend(f"- `{item}`" for item in _as_list(report.get("forbidden_actions")))
    lines.append("")
    return "\n".join(lines)


def write_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOCS_REPORT,
) -> dict[str, str]:
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
    report_with_artifacts = dict(report)
    report_with_artifacts["artifacts"] = artifacts
    markdown = render_markdown(report_with_artifacts)
    for path in (json_path, latest_json):
        path.write_text(json.dumps(report_with_artifacts, indent=2, sort_keys=True) + "\n", encoding="utf8")
    for path in (md_path, latest_md, docs_report):
        path.write_text(markdown, encoding="utf8")
    report["artifacts"] = artifacts
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a read-only point-in-time macro-event calendar artifact.")
    parser.add_argument("--source-rows", type=Path, default=DEFAULT_SOURCE_ROWS)
    parser.add_argument("--feature-store", type=Path, default=DEFAULT_FEATURE_STORE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(source_rows_path=args.source_rows, feature_store_path=args.feature_store)
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
