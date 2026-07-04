from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


REPORT_ID = "regular_options_point_in_time_earnings_calendar"
SOURCE_FAMILY = "point_in_time_equity_earnings_calendar_v1"
DEFAULT_SOURCE_ROWS = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-earnings-calendar" / "source_rows.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-earnings-calendar"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-point-in-time-earnings-calendar.md"
DEFAULT_WINDOW_START = "2024-06-01"
DEFAULT_WINDOW_END = "2026-05-31"
DEFAULT_MAX_DTE = 45
DEFAULT_EQUITY_SYMBOLS = ("AAPL", "GOOGL", "UNH", "LLY", "JNJ", "XOM", "CVX", "COP", "NEM")

REQUIRED_ROW_FIELDS = (
    "symbol",
    "earnings_date_et",
    "known_at_utc",
    "source_name",
    "source_ref",
    "source_retrieved_at_utc",
    "revision_id",
    "source_calendar_coverage_start_date_et",
    "source_calendar_coverage_end_date_et",
)
LEAKAGE_KEYS = {
    "actual",
    "actual_eps",
    "actual_revenue",
    "estimate",
    "estimated_eps",
    "consensus",
    "surprise",
    "beat_miss",
    "market_reaction",
    "realized_move",
    "post_earnings_iv",
    "pnl",
    "net_pnl",
}
READ_ONLY_FLAGS = {
    "read_only": True,
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
FORBIDDEN_ACTIONS = (
    "broker_orders",
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
    "using_earnings_actuals_estimates_or_reactions",
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


def _parse_date(value: Any) -> date | None:
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except (TypeError, ValueError):
        return None


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_symbols(value: str | Sequence[str]) -> tuple[str, ...]:
    raw = value.split(",") if isinstance(value, str) else list(value)
    return tuple(str(item).strip().upper() for item in raw if str(item).strip())


def _load_source_rows(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta = {"path": _rel(path), "exists": path.exists(), "status": "missing", "error": None, "row_count": 0}
    if not path.exists():
        return [], meta
    rows: list[dict[str, Any]] = []
    try:
        for line_number, line in enumerate(path.read_text(encoding="utf8").splitlines(), start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
            else:
                meta.setdefault("non_object_lines", []).append(line_number)
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
                path = f"{prefix}.{key}" if prefix else str(key)
                if str(key).strip().lower() in LEAKAGE_KEYS:
                    hits.append(path)
                walk(nested, path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{prefix}[{index}]")

    walk(row)
    return hits


def _validate_row(row: dict[str, Any], index: int, allowed_symbols: set[str]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    missing = [field for field in REQUIRED_ROW_FIELDS if row.get(field) in (None, "")]
    reasons: list[str] = []
    symbol = str(row.get("symbol") or "").strip().upper()
    earnings_date = _parse_date(row.get("earnings_date_et"))
    known_at = _parse_utc(row.get("known_at_utc"))
    retrieved_at = _parse_utc(row.get("source_retrieved_at_utc") or row.get("source_published_at_utc"))
    coverage_start = _parse_date(row.get("source_calendar_coverage_start_date_et"))
    coverage_end = _parse_date(row.get("source_calendar_coverage_end_date_et"))
    leakage = _find_leakage_keys(row)
    if missing:
        reasons.append("missing_required_fields")
    if symbol not in allowed_symbols:
        reasons.append("unexpected_symbol")
    if earnings_date is None or known_at is None or retrieved_at is None:
        reasons.append("invalid_date_or_timestamp")
    elif known_at.date() > earnings_date or retrieved_at.date() > earnings_date:
        reasons.append("known_at_or_source_time_after_earnings_date")
    if coverage_start is None or coverage_end is None or (coverage_start and coverage_end and coverage_start > coverage_end):
        reasons.append("invalid_source_calendar_coverage_window")
    elif earnings_date is not None and not (coverage_start <= earnings_date <= coverage_end):
        reasons.append("earnings_date_outside_source_calendar_coverage_window")
    if row.get("point_in_time_valid") is not True:
        reasons.append("point_in_time_valid_not_true")
    if leakage:
        reasons.append("leakage_fields_present")
    if reasons:
        return None, {
            "index": index,
            "symbol": symbol,
            "earnings_date_et": str(row.get("earnings_date_et") or ""),
            "reasons": reasons,
            "missing_fields": missing,
            "leakage_keys": leakage,
        }
    accepted = {
        "symbol": symbol,
        "earnings_date_et": earnings_date.isoformat(),
        "earnings_time": str(row.get("earnings_time") or "unknown").strip().lower() or "unknown",
        "known_at_utc": str(row["known_at_utc"]),
        "source_name": str(row["source_name"]),
        "source_ref": str(row["source_ref"]),
        "source_retrieved_at_utc": str(row.get("source_retrieved_at_utc") or row.get("source_published_at_utc")),
        "revision_id": str(row["revision_id"]),
        "point_in_time_valid": True,
        "source_family": str(row.get("source_family") or SOURCE_FAMILY),
        "source_row_hash": str(row.get("source_row_hash") or ""),
        "source_calendar_coverage_start_date_et": coverage_start.isoformat(),
        "source_calendar_coverage_end_date_et": coverage_end.isoformat(),
        "proof_eligible": False,
    }
    return accepted, None


def build_report(
    *,
    source_rows_path: Path = DEFAULT_SOURCE_ROWS,
    window_start: str = DEFAULT_WINDOW_START,
    window_end: str = DEFAULT_WINDOW_END,
    max_dte: int = DEFAULT_MAX_DTE,
    required_equity_symbols: Sequence[str] = DEFAULT_EQUITY_SYMBOLS,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    start = _parse_date(window_start)
    end = _parse_date(window_end)
    if start is None or end is None or end < start:
        raise ValueError("window_start and window_end must be valid YYYY-MM-DD values with start <= end")
    coverage_end_required = end + timedelta(days=int(max_dte))
    symbols = tuple(sorted(_parse_symbols(required_equity_symbols)))
    source_rows, source_meta = _load_source_rows(source_rows_path)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, row in enumerate(source_rows):
        clean, reject = _validate_row(row, index, set(symbols))
        if clean:
            accepted.append(clean)
        if reject:
            rejected.append(reject)
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for row in accepted:
        by_symbol.setdefault(str(row["symbol"]), []).append(row)
    covered_symbols: list[str] = []
    symbol_coverage: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        rows = by_symbol.get(symbol, [])
        starts = [_parse_date(row.get("source_calendar_coverage_start_date_et")) for row in rows]
        ends = [_parse_date(row.get("source_calendar_coverage_end_date_et")) for row in rows]
        starts = [value for value in starts if value is not None]
        ends = [value for value in ends if value is not None]
        coverage_start = min(starts) if starts else None
        coverage_end = max(ends) if ends else None
        covers_window = bool(coverage_start and coverage_end and coverage_start <= start and coverage_end >= coverage_end_required)
        if covers_window:
            covered_symbols.append(symbol)
        symbol_coverage[symbol] = {
            "event_count": len(rows),
            "coverage_start_date_et": coverage_start.isoformat() if coverage_start else None,
            "coverage_end_date_et": coverage_end.isoformat() if coverage_end else None,
            "covers_requested_window_plus_max_dte": covers_window,
        }
    missing_symbols = [symbol for symbol in symbols if symbol not in set(covered_symbols)]
    blockers: list[str] = []
    if source_meta.get("status") == "missing" or source_meta.get("row_count") == 0:
        blockers.append("point_in_time_earnings_calendar_source_missing")
    if rejected:
        blockers.append("point_in_time_earnings_calendar_row_validation_failed")
    if missing_symbols:
        blockers.append("point_in_time_earnings_calendar_symbol_coverage_incomplete")
    status = "point_in_time_earnings_calendar_ready" if not blockers else "blocked_point_in_time_earnings_calendar"
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": status,
        **READ_ONLY_FLAGS,
        "source_family": SOURCE_FAMILY,
        "source_artifacts": {"source_rows": source_meta},
        "required_equity_symbols": list(symbols),
        "covered_equity_symbols": covered_symbols,
        "missing_equity_symbols": missing_symbols,
        "requested_window": {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "max_dte": int(max_dte),
            "coverage_end_required": coverage_end_required.isoformat(),
        },
        "source_row_count": source_meta.get("row_count", 0),
        "accepted_event_count": len(accepted),
        "rejected_row_count": len(rejected),
        "leakage_reject_count": sum(1 for row in rejected if "leakage_fields_present" in _as_list(row.get("reasons"))),
        "symbol_event_counts": dict(sorted(Counter(row["symbol"] for row in accepted).items())),
        "symbol_coverage": symbol_coverage,
        "earnings_events": accepted,
        "rejected_rows": rejected,
        "blockers": blockers,
        "adapter_join_policy": "Historical scanner rows may use this calendar only when source coverage proves each required equity symbol is covered from the requested start through requested end plus max DTE; rows then skip candidates with earnings inside the policy hold window.",
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    return report


def render_markdown(report: dict[str, Any]) -> str:
    window = _as_dict(report.get("requested_window"))
    lines = [
        "# Regular Options Point-In-Time Earnings Calendar",
        "",
        "This generated artifact validates a point-in-time earnings calendar source for the frozen equity symbols. It is read-only and does not use earnings actuals, estimates, surprises, realized moves, or P&L.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Window: `{window.get('window_start')}` through `{window.get('window_end')}` plus max DTE `{window.get('max_dte')}`.",
        f"- Accepted events: `{report.get('accepted_event_count')}`.",
        f"- Covered equity symbols: `{len(_as_list(report.get('covered_equity_symbols')))}` / `{len(_as_list(report.get('required_equity_symbols')))}`.",
        f"- Rejected rows: `{report.get('rejected_row_count')}`.",
        "",
        "## Blockers",
        "",
    ]
    blockers = _as_list(report.get("blockers"))
    lines.extend(f"- `{item}`" for item in blockers) if blockers else lines.append("- None.")
    lines.extend(["", "## Symbol Coverage", "", "| Symbol | Events | Coverage Start | Coverage End | Covers Window |", "|---|---:|---|---|---:|"])
    for symbol, coverage in _as_dict(report.get("symbol_coverage")).items():
        coverage_dict = _as_dict(coverage)
        lines.append(
            f"| `{symbol}` | `{coverage_dict.get('event_count')}` | `{coverage_dict.get('coverage_start_date_et')}` | `{coverage_dict.get('coverage_end_date_et')}` | `{str(coverage_dict.get('covers_requested_window_plus_max_dte')).lower()}` |"
        )
    lines.extend(["", "## Boundary", "", "No replay, quote import, evidence mutation, broker action, live validation, auto-track, scanner policy change, proof-bar change, protected-holdout consumption, or promotion is performed.", ""])
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
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
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
    parser = argparse.ArgumentParser(description="Build the point-in-time earnings calendar readiness artifact.")
    parser.add_argument("--source-rows", type=Path, default=DEFAULT_SOURCE_ROWS)
    parser.add_argument("--start-date", default=DEFAULT_WINDOW_START)
    parser.add_argument("--end-date", default=DEFAULT_WINDOW_END)
    parser.add_argument("--max-dte", type=int, default=DEFAULT_MAX_DTE)
    parser.add_argument("--required-equity-symbols", default=",".join(DEFAULT_EQUITY_SYMBOLS))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    report = build_report(
        source_rows_path=args.source_rows,
        window_start=args.start_date,
        window_end=args.end_date,
        max_dte=args.max_dte,
        required_equity_symbols=_parse_symbols(args.required_equity_symbols),
    )
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    print(json.dumps(report, indent=2, sort_keys=True) if args.json_output else render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
