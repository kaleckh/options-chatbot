from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
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
    _month_range,
    _parse_date,
)
from scripts.build_regular_options_13_symbol_frozen_candidate_generation_engine import _cohort_pairs  # noqa: E402
from scripts.build_regular_options_robust_search_evaluation import _load_json  # noqa: E402
from us_equity_market_calendar import is_us_equity_market_day  # noqa: E402


REPORT_ID = "regular_options_13_symbol_frozen_daily_candidate_decisions"
DEFAULT_FORWARD_COHORT = ROOT / "data" / "contracts" / "forward-cohort-preregistration.json"
DEFAULT_FEATURE_STORE = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_OUTPUT_DIR = (
    ROOT / "data" / "profitability-lab" / "regular-options-13-symbol-frozen-daily-candidate-decisions"
)
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-13-symbol-frozen-daily-candidate-decisions.md"
DEFAULT_HISTORICAL_SCANNER_REPLAY_ADAPTER = (
    ROOT / "data" / "profitability-lab" / "regular-options-historical-frozen-scanner-replay-adapter" / "latest.json"
)
BLOCKER = "missing_historical_scanner_replay_adapter"
INPUT_BLOCKER = "missing_historical_scanner_point_in_time_inputs"
MISSING_COMMAND = (
    "missing local read-only command: historical frozen scanner replay adapter accepting "
    "candidate_generation_date, as_of_date, lane_id, symbol, and no_write"
)
ACCEPTED_STATUSES = {"selected_candidate", "explicit_no_pick"}
FALSE_FLAGS = {
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
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "cohort_append_performed": False,
}
FORBIDDEN_ACTIONS = [
    "broker_orders",
    "live_validation",
    "auto_track",
    "production_scanner_policy_change",
    "production_strategy_change",
    "stop_change",
    "sizing_change",
    "proof_bar_change",
    "quote_import",
    "options_history_db_mutation",
    "evidence_store_mutation",
    "forward_cohort_append",
    "protected_holdout_consumption",
    "promotion",
    "posthoc_filter_broad_source_rows_into_proof",
    "invent_selected_or_no_pick_rows",
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


def _parse_universe(value: str | Sequence[str]) -> tuple[str, ...]:
    raw = value.split(",") if isinstance(value, str) else list(value)
    return tuple(str(item).strip().upper() for item in raw if str(item).strip())


def _market_dates(start: date, end: date, feature_store: dict[str, Any]) -> list[date]:
    shared = [
        parsed
        for item in _as_list(feature_store.get("shared_quote_dates"))
        if (parsed := _parse_date(item)) is not None and start <= parsed <= end
    ]
    if shared:
        return sorted(set(shared))

    dates: list[date] = []
    current = start
    while current <= end:
        if is_us_equity_market_day(current):
            dates.append(current)
        current += timedelta(days=1)
    return dates


def _function_parameters(path: Path, function_name: str) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf8"))
    except OSError:
        return []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            args = [arg.arg for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs]
            if node.args.vararg:
                args.append("*" + node.args.vararg.arg)
            if node.args.kwarg:
                args.append("**" + node.args.kwarg.arg)
            return args
    return []


def _scanner_surface() -> dict[str, Any]:
    run_params = _function_parameters(ROOT / "supervised_scan.py", "run_supervised_scan")
    scan_params = _function_parameters(ROOT / "options_chatbot.py", "scan_daily_top_trades")
    historical_param_names = {
        "as_of_date",
        "candidate_generation_date",
        "historical_date",
        "market_date",
        "scan_date",
        "target_date",
    }
    run_has_date = bool(historical_param_names.intersection(run_params))
    scan_has_date = bool(historical_param_names.intersection(scan_params))
    adapter_available = bool(run_has_date and scan_has_date)
    return {
        "adapter_available": adapter_available,
        "inspected_callables": [
            {
                "path": "supervised_scan.py",
                "function": "run_supervised_scan",
                "parameters": run_params,
                "historical_date_parameter_available": run_has_date,
            },
            {
                "path": "options_chatbot.py",
                "function": "scan_daily_top_trades",
                "parameters": scan_params,
                "historical_date_parameter_available": scan_has_date,
            },
        ],
        "decision": "historical_replay_adapter_available" if adapter_available else BLOCKER,
        "missing_command": None if adapter_available else MISSING_COMMAND,
    }


def _row_date(row: dict[str, Any]) -> str:
    return str(row.get("date") or row.get("candidate_generation_date") or row.get("entry_date") or "")[:10]


def _row_lane(row: dict[str, Any]) -> str:
    return str(row.get("lane") or row.get("lane_id") or "").strip()


def _row_symbol(row: dict[str, Any]) -> str:
    return str(row.get("underlying") or row.get("ticker") or row.get("symbol") or "").strip().upper()


def _daily_source_rows(source: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("daily_candidate_generation", "daily_candidate_decisions", "daily_rows"):
        rows = [_as_dict(item) for item in _as_list(source.get(key))]
        if rows:
            return rows
    return []


def _source_declared_universe(source: dict[str, Any]) -> tuple[str, ...]:
    explicit = (
        source.get("allowed_universe")
        or source.get("frozen_universe")
        or source.get("research_universe")
        or _as_dict(source.get("candidate_surface")).get("allowed_universe")
    )
    return _parse_universe(explicit or [])


def _normalize_status(value: Any) -> str:
    status = str(value or "").strip()
    if status in {"candidate_generated", "exact_entry_captured"}:
        return "selected_candidate"
    if status in {"no_candidate", "no_pick"}:
        return "explicit_no_pick"
    return status


def _source_integrity(
    *,
    source: dict[str, Any] | None,
    source_meta: dict[str, Any] | None,
    pairs: Sequence[dict[str, str]],
) -> dict[str, Any]:
    if source is None:
        return {
            "source_loaded": False,
            "source_exact_frozen_daily_decisions": False,
            "declared_universe": [],
            "outside_universe_row_count": 0,
            "outside_frozen_pair_row_count": 0,
            "malformed_daily_decision_row_count": 0,
            "blockers": [],
        }

    rows = _daily_source_rows(source)
    declared_universe = _source_declared_universe(source)
    allowed = set(ALLOWED_UNIVERSE)
    expected_pairs = {(str(pair["lane"]), str(pair["underlying"]).upper()) for pair in pairs}
    outside_universe_rows = [row for row in rows if _row_symbol(row) and _row_symbol(row) not in allowed]
    outside_pair_rows = [
        row
        for row in rows
        if _row_lane(row)
        and _row_symbol(row)
        and _row_symbol(row) in allowed
        and (_row_lane(row), _row_symbol(row)) not in expected_pairs
    ]
    malformed_rows = [row for row in rows if not (_row_date(row) and _row_lane(row) and _row_symbol(row))]
    blockers: list[str] = []
    if _as_dict(source_meta).get("status") != "loaded":
        blockers.append("daily_decision_source_not_loaded")
    if not declared_universe or sorted(declared_universe) != sorted(ALLOWED_UNIVERSE):
        blockers.append("source_artifact_universe_not_13_symbol")
    if outside_universe_rows:
        blockers.append("outside_universe_source_rows_present")
    if outside_pair_rows:
        blockers.append("source_artifact_frozen_pairs_not_exact")
    if malformed_rows:
        blockers.append("malformed_daily_candidate_decision_source_rows_present")
    if not rows:
        blockers.append("missing_daily_candidate_generation_diagnostics")
    return {
        "source_loaded": _as_dict(source_meta).get("status") == "loaded",
        "source_exact_frozen_daily_decisions": not blockers,
        "declared_universe": list(declared_universe),
        "outside_universe_row_count": len(outside_universe_rows),
        "outside_frozen_pair_row_count": len(outside_pair_rows),
        "malformed_daily_decision_row_count": len(malformed_rows),
        "blockers": sorted(dict.fromkeys(blockers)),
    }


def _source_index(source: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in _daily_source_rows(source):
        key = (_row_date(row), _row_lane(row), _row_symbol(row))
        if all(key) and key not in indexed:
            indexed[key] = row
    return indexed


def _build_rows(
    *,
    market_dates: Sequence[date],
    pairs: Sequence[dict[str, str]],
    as_of: date,
    scanner_surface: dict[str, Any],
    source: dict[str, Any] | None = None,
    source_meta: dict[str, Any] | None = None,
    source_integrity: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    indexed = _source_index(source or {})
    source_integrity_blockers = [str(item) for item in _as_list(_as_dict(source_integrity).get("blockers"))]
    rows: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    blockers: list[str] = []
    if not scanner_surface.get("adapter_available") and not indexed:
        blockers.extend([BLOCKER, INPUT_BLOCKER])
    blockers.extend(source_integrity_blockers)

    for current_date in market_dates:
        for pair in pairs:
            lane = pair["lane"]
            symbol = pair["underlying"]
            key = (current_date.isoformat(), lane, symbol)
            source_row = indexed.get(key)
            row_blockers: list[str] = []
            if source_row:
                row_blockers.extend(source_integrity_blockers)
                status = _normalize_status(source_row.get("status") or source_row.get("decision"))
                row_blockers.extend(str(item) for item in _as_list(source_row.get("blockers")))
                source_proof_safe = source_row.get("proof_safe") is True
                if source_integrity_blockers:
                    status = "blocked_source_artifact_not_exact_frozen_daily_decision_source"
                    source_proof_safe = False
                elif status not in ACCEPTED_STATUSES and not status.startswith("blocked_"):
                    status = "blocked_unsupported_daily_candidate_decision_status"
                    row_blockers.append("unsupported_daily_candidate_decision_status")
                elif status in ACCEPTED_STATUSES and not source_proof_safe:
                    status = "blocked_daily_candidate_decision_not_proof_safe"
                    row_blockers.append("daily_candidate_decision_not_proof_safe")
            else:
                if source is not None and source_integrity_blockers:
                    status = "blocked_source_artifact_not_exact_frozen_daily_decision_source"
                    row_blockers.extend(source_integrity_blockers)
                    row_blockers.append("missing_daily_candidate_generation_diagnostics")
                elif source is not None:
                    status = "blocked_missing_daily_candidate_generation_diagnostics"
                    row_blockers.append("missing_daily_candidate_generation_diagnostics")
                else:
                    status = f"blocked_{BLOCKER}"
                    row_blockers.extend([BLOCKER, INPUT_BLOCKER])
                source_proof_safe = False

            row = {
                "row_id": f"{REPORT_ID}:{current_date.isoformat()}:{lane}:{symbol}",
                "date": current_date.isoformat(),
                "candidate_generation_date": current_date.isoformat(),
                "month": current_date.isoformat()[:7],
                "lane": lane,
                "lane_id": lane,
                "underlying": symbol,
                "ticker": symbol,
                "policy_snapshot_sha256": pair.get("policy_snapshot_sha256"),
                "status": status,
                "selected_candidate": status == "selected_candidate",
                "explicit_no_pick": status == "explicit_no_pick",
                "proof_safe": bool(status in ACCEPTED_STATUSES and source_proof_safe),
                "known_at": f"{current_date.isoformat()}T00:00:00Z",
                "tradable_after": f"{current_date.isoformat()}T13:30:00Z",
                "decision_timestamp_utc": f"{current_date.isoformat()}T00:00:00Z",
                "as_of_date": as_of.isoformat(),
                "read_only": True,
                "no_write": True,
                "accepted_profitability": False,
                "historical_rows_are_forward_proof": False,
                "source_artifact_path": _as_dict(source_meta).get("path"),
                "decision_source": (
                    "provided_exact_daily_decision_source"
                    if source_row
                    else "inspected_existing_scanner_surface_no_historical_adapter"
                ),
                "source_lineage": {
                    "scanner_surface_decision": scanner_surface.get("decision"),
                    "missing_command": scanner_surface.get("missing_command"),
                    "source_row_present": bool(source_row),
                    "proof_safe": bool(status in ACCEPTED_STATUSES and source_proof_safe),
                },
                "blockers": sorted(dict.fromkeys(row_blockers)),
            }
            rows.append(row)
            blockers.extend(row_blockers)
            if row["selected_candidate"]:
                selected.append(row)
    return rows, selected, sorted(dict.fromkeys(blockers))


def _coverage(rows: Sequence[dict[str, Any]], requested_months: Sequence[str]) -> dict[str, Any]:
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_month[str(row.get("month"))].append(dict(row))
    covered = [
        month
        for month in requested_months
        if by_month.get(month) and all(str(row.get("status")) in ACCEPTED_STATUSES for row in by_month[month])
    ]
    zero = [
        month
        for month in covered
        if by_month.get(month) and all(str(row.get("status")) == "explicit_no_pick" for row in by_month[month])
    ]
    return {
        "requested_months": list(requested_months),
        "requested_month_count": len(requested_months),
        "covered_months": covered,
        "calendar_months_covered": covered,
        "calendar_months_covered_count": len(covered),
        "zero_selection_months": zero,
        "zero_selection_months_explicit": bool(zero),
        "blocked_months": [month for month in requested_months if month not in set(covered)],
    }


def build_report(
    *,
    forward_cohort_path: Path = DEFAULT_FORWARD_COHORT,
    feature_store_path: Path = DEFAULT_FEATURE_STORE,
    source_daily_decisions_path: Path | None = None,
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
    frozen_universe = _parse_universe(universe)
    if start is None or end is None or as_of is None or end < start:
        raise ValueError("start-date, end-date, and as-of-date must be valid YYYY-MM-DD values with start <= end")
    if frozen_universe != ALLOWED_UNIVERSE:
        raise ValueError("universe must exactly match the frozen 13-symbol universe")
    no_write = True

    cohort, cohort_meta = _load_json(forward_cohort_path)
    feature, feature_meta = _load_json(feature_store_path)
    source: dict[str, Any] | None = None
    source_meta: dict[str, Any] | None = None
    if source_daily_decisions_path:
        source, source_meta = _load_json(source_daily_decisions_path)

    dates = _market_dates(start, end, feature)
    pairs = _cohort_pairs(cohort, ALLOWED_UNIVERSE)
    scanner_surface = _scanner_surface()
    source_integrity = _source_integrity(source=source, source_meta=source_meta, pairs=pairs)
    daily_rows, selected, blockers = _build_rows(
        market_dates=dates,
        pairs=pairs,
        as_of=as_of,
        scanner_surface=scanner_surface,
        source=source,
        source_meta=source_meta,
        source_integrity=source_integrity,
    )
    if cohort_meta.get("status") != "loaded":
        blockers.append("forward_cohort_preregistration_not_loaded")
    if feature_meta.get("status") != "loaded":
        blockers.append("feature_store_not_loaded")
    if not dates:
        blockers.append("market_date_denominator_missing")
    if not pairs:
        blockers.append("forward_cohort_lane_symbol_pairs_missing")
    requested_months = _month_range(start, end)
    coverage = _coverage(daily_rows, requested_months)
    if coverage["calendar_months_covered_count"] < len(requested_months):
        blockers.append(
            f"candidate_generation_months_{coverage['calendar_months_covered_count']}_below_requested_{len(requested_months)}"
        )
    blockers = sorted(dict.fromkeys(blockers))
    status_counts = Counter(str(row.get("status")) for row in daily_rows)
    month_diagnostics = [
        {
            "month": month,
            "candidate_generation_proven": month in set(coverage["covered_months"]),
            "explicit_no_pick_proof": month in set(coverage["zero_selection_months"]),
            "selected_trade_count": len([row for row in selected if str(row.get("month")) == month]),
            "blocked_row_count": len(
                [row for row in daily_rows if str(row.get("month")) == month and str(row.get("status")).startswith("blocked_")]
            ),
            "blockers": sorted(
                {
                    blocker
                    for row in daily_rows
                    if str(row.get("month")) == month
                    for blocker in _as_list(row.get("blockers"))
                }
            ),
        }
        for month in requested_months
    ]
    report = {
        "report_id": REPORT_ID,
        "status": "frozen_daily_candidate_decisions_ready" if not blockers else "blocked_frozen_daily_candidate_decisions",
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "schema_version": 1,
        "read_only": True,
        "research_only": True,
        "no_write": True,
        **FALSE_FLAGS,
        "scope": "read_only_frozen_daily_candidate_no_pick_blocker_materializer",
        "allowed_universe": list(ALLOWED_UNIVERSE),
        "frozen_universe": list(ALLOWED_UNIVERSE),
        "requested_window": {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "as_of_date": as_of.isoformat(),
            "requested_months": requested_months,
            "requested_month_count": len(requested_months),
        },
        "inputs": {
            "forward_cohort": cohort_meta,
            "feature_store": feature_meta,
            "source_daily_decisions": source_meta,
        },
        "scanner_replay_surface": scanner_surface,
        "source_integrity": source_integrity,
        "source_artifact_inventory": [
            {
                "artifact": "existing_scanner_surface",
                "proof_safe": False,
                "reason": scanner_surface.get("decision"),
                "missing_command": scanner_surface.get("missing_command"),
                "inspected_callables": scanner_surface.get("inspected_callables"),
            }
        ],
        "calendar_coverage": {
            "status": "calendar_coverage_proven" if not blockers else "calendar_coverage_not_proven",
            "coverage_basis": "daily_selected_or_explicit_no_pick_rows_only",
            **coverage,
        },
        "coverage": coverage,
        "daily_status_counts": dict(sorted(status_counts.items())),
        "daily_candidate_generation_row_count": len(daily_rows),
        "daily_candidate_decision_row_count": len(daily_rows),
        "selected_candidate_row_count": len(selected),
        "selected_trade_summary": {
            "selected_rows_in_window": len(selected),
            "selected_entry_months_with_rows": sorted({str(row.get("month")) for row in selected}),
        },
        "daily_candidate_generation": daily_rows,
        "daily_candidate_decisions": daily_rows,
        "selected_candidates": selected,
        "selected_trades": selected,
        "month_diagnostics": month_diagnostics,
        "blockers": blockers,
        "missing_inputs": [
            {
                "blocker": BLOCKER,
                "required": "read-only historical scanner replay adapter for frozen lane/symbol/date decisions",
                "observed": scanner_surface.get("inspected_callables"),
                "missing_command": scanner_surface.get("missing_command"),
            },
            {
                "blocker": INPUT_BLOCKER,
                "required": "point-in-time scanner inputs for each historical candidate_generation_date",
                "observed": "current scanner fetches current/latest histories and current market regime without candidate_generation_date/as_of_date contract",
            },
        ]
        if blockers
        else [],
        "proof_policy": {
            "readback_is": "read-only frozen daily candidate/no-pick/blocker source materializer",
            "readback_is_not": "profitability proof, fresh forward proof, quote import, evidence mutation, live validation, auto-track, broker permission, proof-bar change, scanner policy change, or promotion",
            "pass_condition": "each frozen market-date/lane/symbol row is selected_candidate or explicit_no_pick from a proof-safe point-in-time daily scanner replay source",
        },
        "forbidden_actions": FORBIDDEN_ACTIONS,
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    window = _as_dict(report.get("requested_window"))
    coverage = _as_dict(report.get("coverage"))
    lines = [
        "# Regular Options 13-Symbol Frozen Daily Candidate Decisions",
        "",
        "This generated artifact materializes one frozen daily candidate/no-pick/blocker row per market date, lane, and symbol. It is read-only and fails closed when historical scanner replay inputs are unavailable.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Window: `{window.get('window_start')}` through `{window.get('window_end')}` as of `{window.get('as_of_date')}`.",
        f"- Daily rows: `{report.get('daily_candidate_decision_row_count')}`.",
        f"- Covered months: `{coverage.get('calendar_months_covered_count')}` / `{coverage.get('requested_month_count')}`.",
        f"- Selected candidates: `{report.get('selected_candidate_row_count')}`.",
        "",
        "## Status Counts",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status, count in _as_dict(report.get("daily_status_counts")).items():
        lines.append(f"| `{status}` | `{count}` |")
    if blockers := _as_list(report.get("blockers")):
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    lines.extend(["", "## Boundary", "", "No rows are fabricated, broad-source rows are not post-hoc filtered into proof, and scanner policy is unchanged.", ""])
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
    daily_path = output_dir / "daily_candidate_decisions.jsonl"
    selected_path = output_dir / "selected_candidates.jsonl"
    artifacts = {
        "json": _rel(json_path),
        "latest_json": _rel(latest_json),
        "markdown": _rel(md_path),
        "latest_markdown": _rel(latest_md),
        "daily_candidate_decisions_jsonl": _rel(daily_path),
        "selected_candidates_jsonl": _rel(selected_path),
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
    with daily_path.open("w", encoding="utf8", newline="\n") as handle:
        for row in _as_list(report.get("daily_candidate_decisions")):
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    with selected_path.open("w", encoding="utf8", newline="\n") as handle:
        for row in _as_list(report.get("selected_candidates")):
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return artifacts


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build frozen daily candidate/no-pick/blocker decisions.")
    parser.add_argument("--forward-cohort", type=Path, default=DEFAULT_FORWARD_COHORT)
    parser.add_argument("--source-feature-store", "--feature-store", type=Path, default=DEFAULT_FEATURE_STORE)
    parser.add_argument("--source-daily-decisions", type=Path, default=DEFAULT_HISTORICAL_SCANNER_REPLAY_ADAPTER)
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
        forward_cohort_path=args.forward_cohort,
        feature_store_path=args.source_feature_store,
        source_daily_decisions_path=args.source_daily_decisions,
        window_start=args.start_date,
        window_end=args.end_date,
        as_of_date=args.as_of_date,
        universe=_parse_universe(args.universe),
        no_write=args.no_write,
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
