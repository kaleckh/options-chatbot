from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
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


REPORT_ID = "regular_options_point_in_time_selected_trade_depth"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-selected-trade-depth"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-point-in-time-selected-trade-depth.md"
DEFAULT_HOLDOUT_CONTRACT = ROOT / "data" / "contracts" / "forward-holdout-contract.json"
DEFAULT_WINDOW_START = "2024-06-01"
DEFAULT_WINDOW_END = "2026-05-31"
DEFAULT_AS_OF_DATE = "2026-06-04"

PROHIBITED_ACTIONS = (
    "do_not_import_quotes_from_point_in_time_selected_trade_depth",
    "do_not_mutate_evidence_stores_from_point_in_time_selected_trade_depth",
    "do_not_overwrite_regular_options_multilane_latest_from_point_in_time_selected_trade_depth",
    "do_not_create_trades_from_point_in_time_selected_trade_depth",
    "do_not_submit_broker_orders_from_point_in_time_selected_trade_depth",
    "do_not_enable_live_validation_from_point_in_time_selected_trade_depth",
    "do_not_enable_auto_track_from_point_in_time_selected_trade_depth",
    "do_not_change_scanner_policy_from_point_in_time_selected_trade_depth",
    "do_not_change_strategy_logic_from_point_in_time_selected_trade_depth",
    "do_not_change_stops_or_sizing_from_point_in_time_selected_trade_depth",
    "do_not_lower_proof_bars_from_point_in_time_selected_trade_depth",
    "do_not_consume_protected_holdout_from_point_in_time_selected_trade_depth",
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


def _holdout_start(contract: dict[str, Any]) -> date | None:
    return _parse_date(_as_dict(contract.get("protected_range")).get("start_date"))


def _shared_quote_months(feature: dict[str, Any]) -> set[str]:
    months = {_month_key(item) for item in _as_list(feature.get("shared_quote_dates"))}
    months.discard(None)
    summary = _as_dict(feature.get("summary"))
    first = _parse_date(summary.get("first_shared_quote_date_et"))
    latest = _parse_date(summary.get("latest_shared_quote_date_et"))
    if first and latest:
        months.update(_month_range(first, latest))
    return {str(month) for month in months if month}


def _selected_rows_by_month(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        month = _month_key(row.get("entry_date"))
        if month:
            grouped[month].append(dict(row))
    return dict(grouped)


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
    for index, row in enumerate(rows, start=1):
        item = dict(row)
        item.setdefault("row_id", item.get("dedupe_key") or f"selected_trade_{index}")
        item.setdefault("exact_priced", True)
        item.setdefault("entry_contract_resolution", "exact_listed_spread_contract")
        item.setdefault("fill_basis", "imported_spread_mark")
        item.setdefault("priced", True)
        item.setdefault("research_backfill", True)
        item.setdefault("production_proof", False)
        item.setdefault("current_definition_historical_replay", True)
        item.setdefault("protected_holdout_overlap", False)
        return_source = item.get("source_result_path")
        item.setdefault("source_id", return_source or item.get("lane_id") or "unknown")
        item.setdefault("variant_id", return_source or item.get("lane_id") or "unknown")
        item.setdefault("candidate_entry_month", _month_key(item.get("entry_date")))
        item.setdefault("selection_timestamp_basis", "current_definition_historical_replay_from_existing_selected_trade_source")
        item.setdefault("feature_asof_gate", "not_reconstructed_in_this_trace")
        item.setdefault("entry_quote_evidence_class", item.get("proof_grade"))
        item.setdefault("exit_quote_evidence_class", item.get("proof_grade"))
        audit_rows.append(item)
    return audit_rows


def _source_has_explicit_generation_coverage(source: dict[str, Any]) -> bool:
    coverage = _as_dict(source.get("calendar_coverage"))
    explicit = _as_list(coverage.get("covered_months") or coverage.get("calendar_months_covered"))
    if not explicit:
        return False
    coverage_status = str(coverage.get("status") or "")
    coverage_basis = str(coverage.get("coverage_basis") or "")
    return coverage_status != "calendar_coverage_not_proven" and "not_proven" not in coverage_basis


def _month_diagnostic(
    *,
    month: str,
    rows: list[dict[str, Any]],
    quote_history_available: bool,
    feature_store_available: bool,
    candidate_generation_proven: bool,
    as_of_date: date,
    protected_holdout_start: date | None,
) -> dict[str, Any]:
    month_start = _parse_date(f"{month}-01")
    holdout_overlap = (
        month_start is not None
        and protected_holdout_start is not None
        and month_start >= protected_holdout_start.replace(day=1)
    )
    selected_count = len(rows)
    if holdout_overlap:
        stage_status = "historical_depth_protected_holdout_overlap_blocked"
    elif selected_count > 0:
        stage_status = "selected_trades_available"
    elif not quote_history_available:
        stage_status = "historical_depth_quote_history_missing"
    elif not feature_store_available:
        stage_status = "historical_depth_feature_join_not_point_in_time_safe"
    elif candidate_generation_proven:
        stage_status = "historical_depth_no_natural_selections_after_current_policy"
    else:
        stage_status = "historical_depth_no_candidate_generator_for_month"

    selected_trade_calendar_covered = selected_count > 0 or (
        candidate_generation_proven and quote_history_available and feature_store_available and not holdout_overlap
    )
    stage_reasons = []
    stage_reasons.append("quote_history_available" if quote_history_available else "quote_history_missing")
    stage_reasons.append("feature_store_available" if feature_store_available else "feature_store_missing")
    stage_reasons.append(
        "candidate_generation_proven"
        if candidate_generation_proven
        else "candidate_generation_not_proven_for_zero_selection_month"
    )
    if selected_count > 0:
        stage_reasons.append("selected_rows_present")
    elif selected_trade_calendar_covered:
        stage_reasons.append("zero_selection_month_explicit")
    else:
        stage_reasons.append("zero_selection_month_not_proven")
    if holdout_overlap:
        stage_reasons.append("protected_holdout_overlap")

    return {
        "month": month,
        "as_of_date": as_of_date.isoformat(),
        "quote_history_available": quote_history_available,
        "calendar_month_covered": selected_trade_calendar_covered,
        "selected_trade_calendar_covered": selected_trade_calendar_covered,
        "selected_trade_count": selected_count,
        "exact_selected_trade_count": selected_count,
        "zero_selection_month": selected_count == 0,
        "zero_selection_month_explicit": selected_count == 0 and selected_trade_calendar_covered,
        "stage_status": stage_status,
        "stage_reasons": stage_reasons,
        "evidence_inputs": {
            "quote_history_available": quote_history_available,
            "feature_store_available": feature_store_available,
            "underlying_bar_or_signal_history_available": feature_store_available,
            "scanner_or_candidate_runner_available": candidate_generation_proven,
            "option_chain_resolution_available": selected_count > 0,
            "outcome_pricing_available": selected_count > 0,
            "protected_holdout_overlap": holdout_overlap,
        },
    }


def build_report(
    *,
    source_report_path: Path = DEFAULT_SOURCE_REPORT,
    feature_store_report_path: Path = DEFAULT_FEATURE_STORE_REPORT,
    source_quality_policy_path: Path | None = DEFAULT_SOURCE_QUALITY_POLICY,
    holdout_contract_path: Path = DEFAULT_HOLDOUT_CONTRACT,
    window_start: str = DEFAULT_WINDOW_START,
    window_end: str = DEFAULT_WINDOW_END,
    as_of_date: str = DEFAULT_AS_OF_DATE,
    candidate_generation_proven: bool = False,
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
    rows_by_month = _selected_rows_by_month(selected_rows)
    requested_months = _month_range(start, end)
    feature_summary = _as_dict(feature.get("summary"))
    feature_store_available = (
        feature_meta.get("status") == "loaded"
        and str(feature.get("status") or feature_summary.get("overall_status") or "").startswith("feature_store_built")
    )
    quote_months = _shared_quote_months(feature)
    protected_start = _holdout_start(holdout)
    candidate_generation_available = bool(candidate_generation_proven or _source_has_explicit_generation_coverage(source))

    month_diagnostics = [
        _month_diagnostic(
            month=month,
            rows=rows_by_month.get(month, []),
            quote_history_available=month in quote_months,
            feature_store_available=feature_store_available,
            candidate_generation_proven=candidate_generation_available,
            as_of_date=as_of,
            protected_holdout_start=protected_start,
        )
        for month in requested_months
    ]
    covered_months = [row["month"] for row in month_diagnostics if row["selected_trade_calendar_covered"]]
    selected_months = [row["month"] for row in month_diagnostics if row["selected_trade_count"] > 0]
    zero_selection_months = [row["month"] for row in month_diagnostics if row["zero_selection_month_explicit"]]
    unproven_months = [row["month"] for row in month_diagnostics if not row["selected_trade_calendar_covered"]]
    stage_counts = Counter(str(row["stage_status"]) for row in month_diagnostics)
    by_lane = Counter(str(row.get("lane_id") or "unknown") for row in selected_rows)
    by_month = Counter(_month_key(row.get("entry_date")) or "unknown" for row in selected_rows)

    blockers: list[str] = []
    if source_meta.get("status") != "loaded":
        blockers.append("source_report_not_loaded")
    if feature_meta.get("status") != "loaded":
        blockers.append("feature_store_report_not_loaded")
    if holdout_meta.get("status") != "loaded" or protected_start is None:
        blockers.append("protected_holdout_contract_not_loaded")
    if not candidate_generation_available:
        blockers.append("historical_depth_no_candidate_generator_for_month")
        blockers.append("historical_depth_current_definition_replay_only")
    if len(covered_months) < len(requested_months):
        blockers.append(f"calendar_months_covered_{len(covered_months)}_below_requested_{len(requested_months)}")
    if unproven_months:
        blockers.append("selected_trade_calendar_coverage_not_proven")
    if any(row["stage_status"] == "historical_depth_protected_holdout_overlap_blocked" for row in month_diagnostics):
        blockers.append("historical_depth_protected_holdout_overlap_blocked")
    if len(selected_months) == 8:
        blockers.append("historical_depth_existing_artifact_only_8_months")

    status = "point_in_time_selected_trade_depth_ready_for_audit" if not blockers else "blocked_point_in_time_selected_trade_depth"
    coverage_basis = (
        "explicit_candidate_generation_calendar_coverage"
        if candidate_generation_available
        else "selected_rows_plus_feature_store_trace_candidate_generation_not_proven"
    )

    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "schema_version": 1,
        "read_only": True,
        "live_policy_change": False,
        "quotes_imported": False,
        "evidence_stores_mutated": False,
        "canonical_multilane_latest_overwritten": False,
        "scanner_policy_changed": False,
        "strategy_logic_changed": False,
        "stops_changed": False,
        "sizing_changed": False,
        "proof_bars_changed": False,
        "protected_holdout_consumed": False,
        "scope": "regular_options_point_in_time_selected_trade_depth_trace",
        "inputs": {
            "source_report": source_meta,
            "feature_store_report": feature_meta,
            "source_quality_policy": policy_meta,
            "holdout_contract": holdout_meta,
        },
        "requested_calendar_window": {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "as_of_date": as_of.isoformat(),
            "requested_months": requested_months,
            "requested_calendar_month_count": len(requested_months),
        },
        "source_summary": {
            "source_selected_trade_count": len(_as_list(source.get("selected_trades"))),
            "feature_store_status": feature.get("status"),
            "feature_store_shared_quote_date_count": feature_summary.get("shared_quote_date_count"),
            "feature_store_first_shared_quote_date_et": feature_summary.get("first_shared_quote_date_et"),
            "feature_store_latest_shared_quote_date_et": feature_summary.get("latest_shared_quote_date_et"),
            "candidate_generation_proven": candidate_generation_available,
            "current_definition_historical_replay": True,
            "distinction": "quote-history depth does not prove selected-trade calendar coverage",
        },
        "protected_holdout_guard": {
            "protected_holdout_start": protected_start.isoformat() if protected_start else None,
            "protected_holdout_overlap": any(
                row["stage_status"] == "historical_depth_protected_holdout_overlap_blocked"
                for row in month_diagnostics
            ),
            "status": "passed" if protected_start else "blocked",
        },
        "calendar_coverage": {
            "status": "calendar_coverage_proven" if candidate_generation_available else "calendar_coverage_not_proven",
            "coverage_basis": coverage_basis,
            "covered_months": covered_months,
            "calendar_months_covered": covered_months,
            "calendar_months_covered_count": len(covered_months),
            "selected_entry_months_with_rows": selected_months,
            "selected_entry_months_with_rows_count": len(selected_months),
            "zero_selection_months": zero_selection_months,
            "zero_selection_months_explicit": candidate_generation_available,
            "unproven_requested_months": unproven_months,
            "unproven_requested_month_count": len(unproven_months),
        },
        "month_diagnostics": month_diagnostics,
        "stage_status_counts": dict(sorted(stage_counts.items())),
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
            "readback_is": "read-only monthly selected-trade depth trace over current definitions and existing selected-trade rows",
            "readback_is_not": "fresh forward proof, true historical policy snapshot reconstruction by itself, live-validation eligibility, broker action, scanner policy change, proof-bar reduction, quote import, evidence-store mutation, or protected-holdout consumption",
            "current_limitation": "months without selected rows are not proven zero-selection months unless candidate generation coverage is proven",
            "next_if_blocked": "build or run the missing point-in-time candidate generator for unproven months",
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
    lines = [
        "# Regular Options Point-In-Time Selected Trade Depth",
        "",
        "This report is generated from `scripts/build_regular_options_point_in_time_selected_trade_depth.py`. It traces whether the requested historical calendar window has selected-trade coverage or a named blocker by month. It is read-only and does not import quotes, mutate evidence stores, overwrite canonical selected-trade artifacts, create trades, or change policy.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Requested window: `{window.get('window_start')}` through `{window.get('window_end')}` as of `{window.get('as_of_date')}`.",
        f"- Requested months: `{window.get('requested_calendar_month_count')}`.",
        f"- Selected-trade covered months: `{coverage.get('calendar_months_covered_count')}`.",
        f"- Selected months with rows: `{coverage.get('selected_entry_months_with_rows_count')}`.",
        f"- Selected rows in window: `{selected.get('selected_rows_in_window')}`.",
        f"- Zero-selection months explicit: `{coverage.get('zero_selection_months_explicit')}`.",
        f"- Candidate generation proven: `{source.get('candidate_generation_proven')}`.",
        f"- Quote-history shared dates: `{source.get('feature_store_shared_quote_date_count')}` through `{source.get('feature_store_latest_shared_quote_date_et')}`.",
        "",
        "## Monthly Diagnostics",
        "",
        "| Month | Covered | Selected | Stage | Reasons |",
        "|---|---:|---:|---|---|",
    ]
    for row in _as_list(report.get("month_diagnostics")):
        row = _as_dict(row)
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(row.get('month'))}`",
                    _cell(row.get("selected_trade_calendar_covered")),
                    _cell(row.get("selected_trade_count")),
                    f"`{_cell(row.get('stage_status'))}`",
                    _cell(", ".join(str(item) for item in _as_list(row.get("stage_reasons")))),
                ]
            )
            + " |"
        )
    blockers = _as_list(report.get("blockers"))
    if blockers:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "A month with quote coverage but no proven point-in-time candidate-generation run is not treated as a safe zero-selection month. The next implementation step after this report is the missing candidate generator for any unproven months.",
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
    parser = argparse.ArgumentParser(description="Build the read-only point-in-time selected-trade depth trace.")
    parser.add_argument("--source-report", type=Path, default=DEFAULT_SOURCE_REPORT)
    parser.add_argument("--feature-store-report", type=Path, default=DEFAULT_FEATURE_STORE_REPORT)
    parser.add_argument("--source-quality-policy", type=Path, default=DEFAULT_SOURCE_QUALITY_POLICY)
    parser.add_argument("--holdout-contract", type=Path, default=DEFAULT_HOLDOUT_CONTRACT)
    parser.add_argument("--window-start", default=DEFAULT_WINDOW_START)
    parser.add_argument("--window-end", default=DEFAULT_WINDOW_END)
    parser.add_argument("--as-of-date", default=DEFAULT_AS_OF_DATE)
    parser.add_argument(
        "--candidate-generation-proven",
        action="store_true",
        help="Treat months with quote/feature coverage and no selected rows as explicit zero-selection months. Use only with a proven point-in-time candidate generator.",
    )
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
        candidate_generation_proven=bool(args.candidate_generation_proven),
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
