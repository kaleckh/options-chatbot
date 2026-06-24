from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_regular_options_robust_search_evaluation import (  # noqa: E402
    DEFAULT_FEATURE_STORE_REPORT,
    DEFAULT_SOURCE_QUALITY_POLICY,
    DEFAULT_SOURCE_REPORT,
    _load_json,
    apply_source_quality_scope_policy,
    normalize_trades,
)


REPORT_ID = "regular_options_historical_depth_selected_trades"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-historical-depth-selected-trades"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-historical-depth-selected-trades.md"
DEFAULT_HOLDOUT_CONTRACT = ROOT / "data" / "contracts" / "forward-holdout-contract.json"
DEFAULT_WINDOW_START = "2024-06-01"
DEFAULT_WINDOW_END = "2026-05-31"
DEFAULT_AS_OF_DATE = "2026-06-04"

PROHIBITED_ACTIONS = (
    "do_not_import_quotes_from_historical_depth_selected_trades",
    "do_not_mutate_evidence_stores_from_historical_depth_selected_trades",
    "do_not_create_forward_cohort_rows_from_historical_depth_selected_trades",
    "do_not_submit_broker_orders_from_historical_depth_selected_trades",
    "do_not_enable_live_validation_from_historical_depth_selected_trades",
    "do_not_enable_auto_track_from_historical_depth_selected_trades",
    "do_not_change_scanner_policy_from_historical_depth_selected_trades",
    "do_not_change_strategy_logic_from_historical_depth_selected_trades",
    "do_not_change_stops_or_sizing_from_historical_depth_selected_trades",
    "do_not_lower_proof_bars_from_historical_depth_selected_trades",
    "do_not_consume_protected_holdout_from_historical_depth_selected_trades",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _parse_date(value: Any) -> date | None:
    raw = "" if value is None else str(value).strip()[:10]
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _month_key(value: Any) -> str | None:
    parsed = _parse_date(value)
    return f"{parsed.year:04d}-{parsed.month:02d}" if parsed else None


def _month_range(start: date, end: date) -> list[str]:
    months: list[str] = []
    year = start.year
    month = start.month
    while (year, month) <= (end.year, end.month):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            year += 1
            month = 1
    return months


def _source_covered_months(source: dict[str, Any]) -> list[str]:
    coverage = _as_dict(source.get("calendar_coverage"))
    months = [
        str(item)
        for item in _as_list(coverage.get("covered_months") or coverage.get("calendar_months_covered"))
        if str(item).strip()
    ]
    return sorted(set(months))


def _holdout_start(contract: dict[str, Any]) -> date | None:
    return _parse_date(_as_dict(contract.get("protected_range")).get("start_date"))


def _selected_months(rows: list[dict[str, Any]]) -> list[str]:
    return sorted({month for row in rows if (month := _month_key(row.get("entry_date")))})


def _filter_window(rows: list[dict[str, Any]], *, start: date, end: date, as_of_date: date) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for row in rows:
        entry = _parse_date(row.get("entry_date"))
        if entry is None or entry < start or entry > end or entry > as_of_date:
            continue
        filtered.append(dict(row))
    filtered.sort(key=lambda item: (str(item.get("entry_date")), str(item.get("ticker")), str(item.get("lane_id"))))
    return filtered


def _audit_ready_selected_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    audit_rows: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item.setdefault("exact_priced", True)
        item.setdefault("entry_contract_resolution", "exact_listed_spread_contract")
        item.setdefault("fill_basis", "imported_spread_mark")
        item.setdefault("priced", True)
        audit_rows.append(item)
    return audit_rows


def _source_summary(source: dict[str, Any], feature: dict[str, Any]) -> dict[str, Any]:
    feature_summary = _as_dict(feature.get("summary"))
    return {
        "source_selected_trade_count": len(_as_list(source.get("selected_trades"))),
        "feature_store_status": feature.get("status"),
        "feature_store_shared_quote_date_count": feature_summary.get("shared_quote_date_count"),
        "feature_store_first_shared_quote_date_et": feature_summary.get("first_shared_quote_date_et"),
        "feature_store_latest_shared_quote_date_et": feature_summary.get("latest_shared_quote_date_et"),
        "distinction": "quote-history depth does not prove selected-trade calendar coverage",
    }


def _proven_covered_months(
    *,
    requested_months: list[str],
    source_explicit_months: list[str],
    selected_months_with_rows: list[str],
) -> tuple[list[str], str]:
    if source_explicit_months:
        return sorted(set(source_explicit_months).intersection(requested_months)), "source_explicit_calendar_coverage"
    return selected_months_with_rows, "row_months_only_calendar_coverage_not_proven"


def build_report(
    *,
    source_report_path: Path = DEFAULT_SOURCE_REPORT,
    feature_store_report_path: Path = DEFAULT_FEATURE_STORE_REPORT,
    source_quality_policy_path: Path | None = DEFAULT_SOURCE_QUALITY_POLICY,
    holdout_contract_path: Path = DEFAULT_HOLDOUT_CONTRACT,
    window_start: str = DEFAULT_WINDOW_START,
    window_end: str = DEFAULT_WINDOW_END,
    as_of_date: str = DEFAULT_AS_OF_DATE,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    source, source_meta = _load_json(source_report_path)
    feature, feature_meta = _load_json(feature_store_report_path)
    policy, policy_meta = (
        _load_json(source_quality_policy_path)
        if source_quality_policy_path
        else ({}, {"status": "missing", "path": None, "exists": False, "error": "policy_not_configured"})
    )
    holdout, holdout_meta = _load_json(holdout_contract_path)

    start = _parse_date(window_start)
    end = _parse_date(window_end)
    as_of = _parse_date(as_of_date)
    if start is None or end is None or as_of is None or end < start:
        raise ValueError("window-start, window-end, and as-of-date must be valid YYYY-MM-DD values with start <= end")

    raw_rows, rejected = normalize_trades(_as_list(source.get("selected_trades")))
    scoped_rows, source_quality_exclusions = apply_source_quality_scope_policy(
        raw_rows,
        policy=policy,
        policy_meta=policy_meta,
    )
    selected_rows = _filter_window(scoped_rows, start=start, end=end, as_of_date=as_of)
    requested_months = _month_range(start, end)
    selected_months_with_rows = _selected_months(selected_rows)
    explicit_source_months = _source_covered_months(source)
    covered_months, coverage_basis = _proven_covered_months(
        requested_months=requested_months,
        source_explicit_months=explicit_source_months,
        selected_months_with_rows=selected_months_with_rows,
    )
    zero_selection_months = sorted(set(covered_months) - set(selected_months_with_rows))
    unproven_months = sorted(set(requested_months) - set(covered_months))
    protected_start = _holdout_start(holdout)
    overlap_rows = [
        row
        for row in selected_rows
        if protected_start is not None and (entry := _parse_date(row.get("entry_date"))) is not None and entry >= protected_start
    ]

    blockers: list[str] = []
    if source_meta.get("status") != "loaded":
        blockers.append("source_report_not_loaded")
    if feature_meta.get("status") != "loaded":
        blockers.append("feature_store_report_not_loaded")
    if holdout_meta.get("status") != "loaded" or protected_start is None:
        blockers.append("protected_holdout_contract_not_loaded")
    if coverage_basis != "source_explicit_calendar_coverage":
        blockers.append("selected_trade_calendar_coverage_not_proven")
    if len(covered_months) < len(requested_months):
        blockers.append(f"calendar_months_covered_{len(covered_months)}_below_requested_{len(requested_months)}")
    if overlap_rows:
        blockers.append("protected_holdout_overlap_blocked")

    status = "historical_depth_selected_trades_ready_for_audit" if not blockers else "blocked_historical_depth_selected_trades"
    by_lane = Counter(str(row.get("lane_id") or "unknown") for row in selected_rows)
    by_month = Counter(_month_key(row.get("entry_date")) or "unknown" for row in selected_rows)

    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "schema_version": 1,
        "read_only": True,
        "live_policy_change": False,
        "quotes_imported": False,
        "evidence_stores_mutated": False,
        "scanner_policy_changed": False,
        "strategy_logic_changed": False,
        "stops_changed": False,
        "sizing_changed": False,
        "proof_bars_changed": False,
        "protected_holdout_consumed": False,
        "scope": "regular_options_historical_depth_selected_trade_readback",
        "inputs": {
            "source_report": source_meta,
            "feature_store_report": feature_meta,
            "source_quality_policy": policy_meta,
            "holdout_contract": holdout_meta,
        },
        "source_summary": _source_summary(source, feature),
        "requested_calendar_window": {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "as_of_date": as_of.isoformat(),
            "requested_months": requested_months,
            "requested_calendar_month_count": len(requested_months),
        },
        "protected_holdout_guard": {
            "protected_holdout_start": protected_start.isoformat() if protected_start else None,
            "protected_holdout_overlap": bool(overlap_rows),
            "overlap_row_count": len(overlap_rows),
            "status": "blocked" if overlap_rows or protected_start is None else "passed",
        },
        "calendar_coverage": {
            "status": "calendar_coverage_proven" if coverage_basis == "source_explicit_calendar_coverage" else "calendar_coverage_not_proven",
            "coverage_basis": coverage_basis,
            "covered_months": covered_months,
            "calendar_months_covered_count": len(covered_months),
            "selected_entry_months_with_rows": selected_months_with_rows,
            "selected_entry_months_with_rows_count": len(selected_months_with_rows),
            "zero_selection_months": zero_selection_months,
            "zero_selection_months_explicit": coverage_basis == "source_explicit_calendar_coverage",
            "unproven_requested_months": unproven_months,
            "unproven_requested_month_count": len(unproven_months),
        },
        "selected_trade_summary": {
            "accepted_exact_trade_count_before_source_quality_scope": len(raw_rows),
            "source_quality_excluded_trade_count": len(source_quality_exclusions),
            "selected_rows_in_window": len(selected_rows),
            "rejected_row_counts": dict(sorted(rejected.items())),
            "by_lane": dict(sorted(by_lane.items())),
            "by_month": dict(sorted(by_month.items())),
        },
        "selected_trades": _audit_ready_selected_rows(selected_rows),
        "source_quality_exclusions": source_quality_exclusions,
        "blockers": blockers,
        "proof_policy": {
            "readback_is": "historical selected-trade calendar-depth readback over existing selected exact rows",
            "readback_is_not": "fresh forward proof, selected-trade regeneration by itself, live-validation eligibility, broker action, scanner policy change, proof-bar reduction, quote import, evidence-store mutation, or protected-holdout consumption",
            "next_if_blocked": "run or implement a point-in-time selected-trade generator over the older trusted quote-history window",
        },
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }


def _cell(value: Any) -> str:
    return ("" if value is None else str(value)).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict[str, Any]) -> str:
    source = _as_dict(report.get("source_summary"))
    window = _as_dict(report.get("requested_calendar_window"))
    coverage = _as_dict(report.get("calendar_coverage"))
    selected = _as_dict(report.get("selected_trade_summary"))
    holdout = _as_dict(report.get("protected_holdout_guard"))
    lines = [
        "# Regular Options Historical Depth Selected Trades",
        "",
        "This report is generated from `scripts/build_regular_options_historical_depth_selected_trades.py`. It checks whether the current selected-trade source proves enough calendar-month coverage to support a 20-month train plus latest-4-month historical simulated-forward audit. It is read-only and does not import quotes, mutate evidence stores, consume protected holdout, create trades, or change policy.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Requested window: `{window.get('window_start')}` through `{window.get('window_end')}` as of `{window.get('as_of_date')}`.",
        f"- Requested months: `{window.get('requested_calendar_month_count')}`.",
        f"- Proven covered months: `{coverage.get('calendar_months_covered_count')}`.",
        f"- Selected months with rows: `{coverage.get('selected_entry_months_with_rows_count')}`.",
        f"- Selected rows in window: `{selected.get('selected_rows_in_window')}`.",
        f"- Zero-selection months explicit: `{coverage.get('zero_selection_months_explicit')}`.",
        f"- Protected holdout starts: `{holdout.get('protected_holdout_start')}`; overlap `{holdout.get('protected_holdout_overlap')}`.",
        f"- Quote-history shared dates: `{source.get('feature_store_shared_quote_date_count')}` through `{source.get('feature_store_latest_shared_quote_date_et')}`.",
        "",
        "## Coverage",
        "",
        f"- Coverage basis: `{coverage.get('coverage_basis')}`.",
        f"- Covered months: `{', '.join(str(item) for item in _as_list(coverage.get('covered_months'))) or 'none'}`.",
        f"- Selected row months: `{', '.join(str(item) for item in _as_list(coverage.get('selected_entry_months_with_rows'))) or 'none'}`.",
        f"- Unproven requested months: `{', '.join(str(item) for item in _as_list(coverage.get('unproven_requested_months'))) or 'none'}`.",
        "",
        "## Selected Rows By Month",
        "",
        "| Month | Rows |",
        "|---|---:|",
    ]
    for month, count in _as_dict(selected.get("by_month")).items():
        lines.append(f"| `{_cell(month)}` | {_cell(count)} |")
    blockers = _as_list(report.get("blockers"))
    if blockers:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This is a selected-trade calendar-depth readback. It does not regenerate older candidates by itself. If calendar coverage is not proven, the next valid step is a bounded point-in-time selected-trade generator over the older trusted quote-history window.",
            "",
        ]
    )
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
        "json": str(json_path),
        "latest_json": str(latest_json),
        "markdown": str(md_path),
        "latest_markdown": str(latest_md),
        "docs_report": str(docs_report),
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


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the read-only historical-depth selected-trade readback.")
    parser.add_argument("--source-report", type=Path, default=DEFAULT_SOURCE_REPORT)
    parser.add_argument("--feature-store-report", type=Path, default=DEFAULT_FEATURE_STORE_REPORT)
    parser.add_argument("--source-quality-policy", type=Path, default=DEFAULT_SOURCE_QUALITY_POLICY)
    parser.add_argument("--holdout-contract", type=Path, default=DEFAULT_HOLDOUT_CONTRACT)
    parser.add_argument("--window-start", default=DEFAULT_WINDOW_START)
    parser.add_argument("--window-end", default=DEFAULT_WINDOW_END)
    parser.add_argument("--as-of-date", default=DEFAULT_AS_OF_DATE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(
        source_report_path=args.source_report,
        feature_store_report_path=args.feature_store_report,
        source_quality_policy_path=args.source_quality_policy,
        holdout_contract_path=args.holdout_contract,
        window_start=args.window_start,
        window_end=args.window_end,
        as_of_date=args.as_of_date,
    )
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
