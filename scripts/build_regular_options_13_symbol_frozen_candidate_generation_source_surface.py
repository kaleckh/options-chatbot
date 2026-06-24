from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_regular_options_13_symbol_candidate_generation_surface_audit import (  # noqa: E402
    ALLOWED_UNIVERSE,
    DEFAULT_AS_OF_DATE,
    DEFAULT_WINDOW_END,
    DEFAULT_WINDOW_START,
    _as_dict,
    _as_list,
    _candidate_months,
    _candidate_selected_rows,
    _candidate_universe,
    _month_range,
    _parse_date,
    _row_month,
    _row_symbol,
)
from scripts.build_regular_options_robust_search_evaluation import _load_json  # noqa: E402


REPORT_ID = "regular_options_13_symbol_frozen_candidate_generation_source_surface"
DEFAULT_SOURCE_CANDIDATE_GENERATION = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-13-symbol-frozen-candidate-generation-entrypoint"
    / "latest.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-13-symbol-frozen-candidate-generation-source-surface"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-13-symbol-frozen-candidate-generation-source-surface.md"
READ_ONLY_FALSE_FLAGS = {
    "accepted_profitability": False,
    "historical_rows_are_forward_proof": False,
    "promotion_ready": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "production_scanner_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
}
FORBIDDEN_ACTIONS = [
    "broker_orders",
    "broker_order_preparation",
    "live_validation",
    "auto_track",
    "production_scanner_change",
    "production_strategy_change",
    "stop_change",
    "sizing_change",
    "proof_bar_change",
    "quote_import",
    "external_market_data_fetch",
    "options_history_db_mutation",
    "canonical_selected_trade_artifact_mutation",
    "canonical_multilane_artifact_mutation",
    "forward_cohort_append",
    "protected_holdout_consumption",
    "promotion",
    "posthoc_filter_broad_source_as_frozen_13_symbol_proof",
    "count_quote_depth_as_no_pick_proof",
    "count_historical_rows_as_forward_proof",
]


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _parse_universe(value: str | Sequence[str]) -> list[str]:
    if isinstance(value, str):
        raw = value.split(",")
    else:
        raw = list(value)
    return [str(item).strip().upper() for item in raw if str(item).strip()]


def _audit_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    item = dict(row)
    item.setdefault("row_id", item.get("dedupe_key") or f"frozen_13_symbol_candidate_{index}")
    item.setdefault("candidate_entry_month", _row_month(item))
    item.setdefault("protected_holdout_overlap", False)
    item.setdefault("historical_rows_are_forward_proof", False)
    item.setdefault("production_proof", False)
    item.setdefault("research_backfill", True)
    item.setdefault("selection_timestamp_basis", "frozen_13_symbol_candidate_generation_source_surface")
    return item


def build_report(
    *,
    source_candidate_generation_path: Path = DEFAULT_SOURCE_CANDIDATE_GENERATION,
    window_start: str = DEFAULT_WINDOW_START,
    window_end: str = DEFAULT_WINDOW_END,
    as_of_date: str = DEFAULT_AS_OF_DATE,
    universe: Sequence[str] = ALLOWED_UNIVERSE,
    no_write: bool = True,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    start = _parse_date(window_start)
    end = _parse_date(window_end)
    as_of = _parse_date(as_of_date)
    frozen_universe = tuple(_parse_universe(universe))
    if start is None or end is None or as_of is None or end < start:
        raise ValueError("window-start, window-end, and as-of-date must be valid YYYY-MM-DD values with start <= end")
    if frozen_universe != ALLOWED_UNIVERSE:
        raise ValueError("universe must exactly match the frozen 13-symbol universe")
    if not no_write:
        raise ValueError("--no-write is required")

    source, source_meta = _load_json(source_candidate_generation_path)
    requested_months = _month_range(start, end)
    source_universe = _candidate_universe(source)
    source_months = _candidate_months(source)
    source_blockers = [str(item) for item in _as_list(source.get("blockers"))]
    covered_months = set(source_months.get("covered_months") or [])
    zero_months = set(source_months.get("zero_selection_months") or [])
    selected_by_month = _as_dict(source_months.get("selected_by_month"))
    allowed = set(ALLOWED_UNIVERSE)
    exact_source = bool(source_universe.get("frozen_universe_exact_13_symbols"))
    outside_by_month: dict[str, int] = defaultdict(int)
    for row in _candidate_selected_rows(source):
        month = _row_month(row)
        symbol = _row_symbol(row)
        if month and symbol and symbol not in allowed:
            outside_by_month[month] += 1

    month_diagnostics: list[dict[str, Any]] = []
    selected_rows: list[dict[str, Any]] = []
    for month in requested_months:
        raw_rows = [_as_dict(item) for item in _as_list(selected_by_month.get(month))]
        outside_count = int(outside_by_month.get(month, 0))
        selected_allowed = [row for row in raw_rows if _row_symbol(row) in allowed]
        attempted = month in covered_months
        blockers: list[str] = []
        if source_meta.get("status") != "loaded":
            blockers.append("source_candidate_generation_artifact_not_loaded")
        blockers.extend(source_blockers)
        if not attempted:
            blockers.append("missing_daily_candidate_generation_diagnostics")
        if not exact_source:
            blockers.append("source_artifact_universe_not_13_symbol")
            blockers.append("missing_frozen_13_symbol_candidate_generation_engine")
        if outside_count:
            blockers.append("outside_universe_source_rows_present")
        proven = bool(attempted and exact_source and not outside_count)
        explicit_no_pick = bool(proven and month in zero_months and not selected_allowed)
        if proven:
            for row in selected_allowed:
                selected_rows.append(_audit_row(row, len(selected_rows) + 1))
        month_diagnostics.append(
            {
                "month": month,
                "candidate_generation_attempted": attempted,
                "candidate_generation_proven": proven,
                "explicit_no_pick_proof": explicit_no_pick,
                "selected_trade_count": len(selected_allowed) if proven else 0,
                "outside_universe_source_row_count": outside_count,
                "protected_holdout_overlap": False,
                "audit_coverable": bool(proven and (selected_allowed or explicit_no_pick)),
                "blockers": sorted(dict.fromkeys(blockers)),
            }
        )

    proven_months = [row["month"] for row in month_diagnostics if row["candidate_generation_proven"]]
    zero_selection_months = [row["month"] for row in month_diagnostics if row["explicit_no_pick_proof"]]
    blockers = sorted({blocker for row in month_diagnostics for blocker in row["blockers"]})
    if len(proven_months) < len(requested_months):
        blockers.append(f"candidate_generation_months_{len(proven_months)}_below_requested_{len(requested_months)}")
    blockers = sorted(dict.fromkeys(blockers))
    stage_counts = Counter("proven" if row["candidate_generation_proven"] else "blocked" for row in month_diagnostics)
    status = (
        "ready_13_symbol_frozen_candidate_generation_source_surface"
        if not blockers
        else "blocked_13_symbol_frozen_candidate_generation_source_surface"
    )
    report = {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "schema_version": 1,
        "read_only": True,
        "research_only": True,
        "no_write": True,
        **READ_ONLY_FALSE_FLAGS,
        "scope": "regular_options_13_symbol_frozen_candidate_generation_source_surface",
        "inputs": {"source_candidate_generation": source_meta},
        "requested_window": {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "as_of_date": as_of.isoformat(),
            "requested_months": requested_months,
            "requested_month_count": len(requested_months),
        },
        "allowed_universe": list(ALLOWED_UNIVERSE),
        "source_surface": {
            **source_universe,
            "source_artifact_universe_exact_13_symbols": exact_source,
            "posthoc_filtering_allowed_as_proof": False,
        },
        "calendar_coverage": {
            "status": "calendar_coverage_proven" if not blockers else "calendar_coverage_not_proven",
            "coverage_basis": (
                "explicit_frozen_13_symbol_candidate_generation_calendar_coverage"
                if not blockers
                else "source_surface_not_frozen_13_symbol_or_missing_month_diagnostics"
            ),
            "covered_months": proven_months,
            "calendar_months_covered": proven_months,
            "calendar_months_covered_count": len(proven_months),
            "zero_selection_months": zero_selection_months,
            "zero_selection_months_explicit": bool(zero_selection_months) and not blockers,
            "unproven_requested_months": [row["month"] for row in month_diagnostics if not row["candidate_generation_proven"]],
        },
        "selected_trade_summary": {
            "selected_rows_in_window": len(selected_rows),
            "selected_entry_months_with_rows": sorted({str(_row_month(row)) for row in selected_rows if _row_month(row)}),
        },
        "selected_trades": selected_rows,
        "source_artifact_inventory": _as_list(source.get("source_artifact_inventory")),
        "month_diagnostics": month_diagnostics,
        "stage_status_counts": dict(sorted(stage_counts.items())),
        "blockers": blockers,
        "proof_policy": {
            "readback_is": "read-only materialization or fail-closed parking of a frozen 13-symbol candidate-generation source surface",
            "readback_is_not": "profitability proof, fresh forward proof, quote import, scanner change, evidence mutation, live validation, broker permission, protected-holdout consumption, proof-bar change, or promotion",
            "posthoc_filtering_rule": "broad-source rows may be diagnostic only and cannot become frozen 13-symbol proof by filtering",
        },
        "forbidden_actions": FORBIDDEN_ACTIONS,
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    window = _as_dict(report.get("requested_window"))
    coverage = _as_dict(report.get("calendar_coverage"))
    source = _as_dict(report.get("source_surface"))
    lines = [
        "# Regular Options 13-Symbol Frozen Candidate Generation Source Surface",
        "",
        "This generated artifact attempts to materialize a frozen 13-symbol candidate-generation source surface from trusted local artifacts. It fails closed rather than treating broad-source or quote-history-only data as proof.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Requested window: `{window.get('window_start')}` through `{window.get('window_end')}` as of `{window.get('as_of_date')}`.",
        f"- Source exact 13-symbol: `{source.get('source_artifact_universe_exact_13_symbols')}`.",
        f"- Covered months: `{coverage.get('calendar_months_covered_count')}` / `{window.get('requested_month_count')}`.",
        f"- Selected rows: `{_as_dict(report.get('selected_trade_summary')).get('selected_rows_in_window')}`.",
        "",
        "## Month Diagnostics",
        "",
        "| Month | Attempted | Proven | Explicit No-Pick | Selected | Outside Universe | Coverable | Blockers |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in _as_list(report.get("month_diagnostics")):
        row = _as_dict(row)
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{row.get('month')}`",
                    str(row.get("candidate_generation_attempted")),
                    str(row.get("candidate_generation_proven")),
                    str(row.get("explicit_no_pick_proof")),
                    str(row.get("selected_trade_count")),
                    str(row.get("outside_universe_source_row_count")),
                    str(row.get("audit_coverable")),
                    ", ".join(str(item) for item in _as_list(row.get("blockers"))),
                ]
            )
            + " |"
        )
    if blockers := _as_list(report.get("blockers")):
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{blocker}`" for blocker in blockers)
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
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    artifacts = {
        "json": _rel(json_path),
        "latest_json": _rel(latest_json),
        "markdown": _rel(md_path),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
    }
    report["artifacts"] = artifacts
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(report) + "\n"
    json_path.write_text(payload, encoding="utf8")
    latest_json.write_text(payload, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return artifacts


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build frozen 13-symbol candidate-generation source-surface readback.")
    parser.add_argument("--source-candidate-generation", type=Path, default=DEFAULT_SOURCE_CANDIDATE_GENERATION)
    parser.add_argument("--start-date", default=DEFAULT_WINDOW_START)
    parser.add_argument("--end-date", default=DEFAULT_WINDOW_END)
    parser.add_argument("--as-of-date", default=DEFAULT_AS_OF_DATE)
    parser.add_argument("--universe", default=",".join(ALLOWED_UNIVERSE))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(list(argv))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(
        source_candidate_generation_path=args.source_candidate_generation,
        window_start=args.start_date,
        window_end=args.end_date,
        as_of_date=args.as_of_date,
        universe=_parse_universe(args.universe),
        no_write=args.no_write,
    )
    if args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif not args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
