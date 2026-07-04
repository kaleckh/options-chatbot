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
    _candidate_universe,
    _month_range,
    _parse_date,
)
from scripts.build_regular_options_13_symbol_frozen_candidate_generation_engine import (  # noqa: E402
    _cohort_pairs,
    _market_dates,
)
from scripts.build_regular_options_robust_search_evaluation import _load_json  # noqa: E402


REPORT_ID = "regular_options_13_symbol_frozen_candidate_generation_entrypoint"
DEFAULT_SOURCE_CANDIDATE_GENERATION = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-13-symbol-frozen-daily-candidate-decisions"
    / "latest.json"
)
DEFAULT_FEATURE_STORE = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_FORWARD_COHORT = ROOT / "data" / "contracts" / "forward-cohort-preregistration.json"
DEFAULT_OUTPUT_DIR = (
    ROOT / "data" / "profitability-lab" / "regular-options-13-symbol-frozen-candidate-generation-entrypoint"
)
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-13-symbol-frozen-candidate-generation-entrypoint.md"
ACCEPTED_DAILY_STATUSES = {"selected_candidate", "explicit_no_pick"}
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
    "production_scanner_change",
    "production_strategy_change",
    "stop_change",
    "sizing_change",
    "proof_bar_change",
    "quote_import",
    "external_market_data_fetch",
    "options_history_db_mutation",
    "evidence_store_mutation",
    "forward_cohort_append",
    "protected_holdout_consumption",
    "promotion",
    "posthoc_filter_broad_source_as_frozen_13_symbol_proof",
    "inventing_candidate_or_no_pick_rows",
    "historical_rows_as_forward_proof",
]
DEFAULT_CANDIDATE_MATERIALIZATION_BASIS = "deterministic_local_pit_candidate_materializer_v1"


def _source_non_parity(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_materialization_basis": str(
            source.get("candidate_materialization_basis") or DEFAULT_CANDIDATE_MATERIALIZATION_BASIS
        ),
        "scanner_parity": bool(source.get("scanner_parity")) if "scanner_parity" in source else False,
        "production_scanner_replay": bool(source.get("production_scanner_replay"))
        if "production_scanner_replay" in source
        else False,
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


def _parse_universe(value: str | Sequence[str]) -> tuple[str, ...]:
    raw = value.split(",") if isinstance(value, str) else list(value)
    return tuple(str(item).strip().upper() for item in raw if str(item).strip())


def _row_date(row: dict[str, Any]) -> str:
    return str(row.get("date") or row.get("candidate_generation_date") or row.get("entry_date") or "")[:10]


def _row_lane(row: dict[str, Any]) -> str:
    return str(row.get("lane") or row.get("lane_id") or "").strip()


def _row_symbol(row: dict[str, Any]) -> str:
    return str(row.get("underlying") or row.get("ticker") or row.get("symbol") or "").strip().upper()


def _row_status(row: dict[str, Any]) -> str:
    status = str(row.get("status") or row.get("decision") or "").strip()
    if status in {"candidate_generated", "exact_entry_captured"}:
        return "selected_candidate"
    if status in {"no_candidate", "no_pick"}:
        return "explicit_no_pick"
    return status


def _source_daily_rows(source: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("daily_candidate_generation", "daily_candidate_decisions", "daily_rows", "daily_selection_diagnostics"):
        rows = [_as_dict(item) for item in _as_list(source.get(key))]
        if rows:
            return rows
    return []


def _normalize_daily_rows(
    *,
    source: dict[str, Any],
    source_meta: dict[str, Any],
    feature: dict[str, Any],
    cohort: dict[str, Any],
    start: date,
    end: date,
    as_of: date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], int]:
    market_dates = _market_dates(feature, start, end)
    pairs = _cohort_pairs(cohort, ALLOWED_UNIVERSE)
    expected = {(day.isoformat(), pair["lane"], pair["underlying"]): pair for day in market_dates for pair in pairs}
    source_rows = _source_daily_rows(source)
    non_parity = _source_non_parity(source)
    source_universe = _candidate_universe(source)
    exact_source = bool(source_universe.get("frozen_universe_exact_13_symbols"))
    outside_rows = [
        row for row in source_rows if _row_symbol(row) and _row_symbol(row) not in set(ALLOWED_UNIVERSE)
    ]
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in source_rows:
        key = (_row_date(row), _row_lane(row), _row_symbol(row))
        if key in expected and key not in by_key:
            by_key[key] = row

    blockers: list[str] = []
    if source_meta.get("status") != "loaded":
        blockers.append("source_candidate_generation_artifact_not_loaded")
    if not exact_source:
        blockers.append("source_artifact_universe_not_13_symbol")
    if not source_rows:
        blockers.append("missing_daily_candidate_generation_diagnostics")
    if outside_rows:
        blockers.append("outside_universe_source_rows_present")
    if not market_dates:
        blockers.append("feature_store_market_dates_missing")
    if not pairs:
        blockers.append("forward_cohort_lane_symbol_pairs_missing")
    blockers.extend(str(item) for item in _as_list(source.get("blockers")))

    daily_rows: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    for key, pair in sorted(expected.items()):
        day, lane, symbol = key
        source_row = by_key.get(key)
        row_blockers: list[str] = []
        if source_row is None:
            row_blockers.append("missing_daily_candidate_generation_diagnostics")
            status = "blocked_missing_daily_candidate_generation_diagnostics"
        else:
            status = _row_status(source_row)
            if status.startswith("blocked_"):
                row_blockers.extend(str(item) for item in _as_list(source_row.get("blockers")))
            elif status not in ACCEPTED_DAILY_STATUSES:
                row_blockers.append("unsupported_daily_candidate_generation_status")
                status = "blocked_unsupported_daily_candidate_generation_status"
            elif _as_list(source_row.get("blockers")):
                row_blockers.extend(str(item) for item in _as_list(source_row.get("blockers")))
                status = "blocked_daily_candidate_generation_integrity"

        row_id = f"{REPORT_ID}:{day}:{lane}:{symbol}"
        daily = dict(source_row) if source_row is not None else {}
        daily.update({
            "row_id": row_id,
            "date": day,
            "candidate_generation_date": day,
            "month": day[:7],
            "lane": lane,
            "lane_id": lane,
            "underlying": symbol,
            "ticker": symbol,
            "policy_snapshot_sha256": pair.get("policy_snapshot_sha256"),
            "status": status,
            "selected_candidate": status == "selected_candidate",
            "explicit_no_pick": status == "explicit_no_pick",
            "known_at": f"{day}T00:00:00Z",
            "tradable_after": f"{day}T13:30:00Z",
            "decision_timestamp_utc": f"{day}T00:00:00Z",
            "as_of_date": as_of.isoformat(),
            "read_only": True,
            "no_write": True,
            **non_parity,
            "source_artifact_path": source_meta.get("path"),
            "blockers": sorted(dict.fromkeys(row_blockers)),
        })
        daily_rows.append(daily)
        if daily["selected_candidate"]:
            selected.append(daily)
    return daily_rows, selected, sorted(dict.fromkeys(blockers)), len(outside_rows)


def _coverage(daily_rows: Sequence[dict[str, Any]], requested_months: Sequence[str]) -> dict[str, Any]:
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in daily_rows:
        by_month[str(row.get("month"))].append(dict(row))
    covered = [
        month
        for month in requested_months
        if by_month.get(month) and all(str(row.get("status")) in ACCEPTED_DAILY_STATUSES for row in by_month[month])
    ]
    zero_months = [
        month
        for month in covered
        if by_month.get(month) and all(str(row.get("status")) == "explicit_no_pick" for row in by_month[month])
    ]
    return {
        "requested_months": list(requested_months),
        "requested_month_count": len(requested_months),
        "candidate_generation_months_covered": covered,
        "candidate_generation_months_covered_count": len(covered),
        "zero_selection_months": zero_months,
        "zero_selection_months_explicit": bool(zero_months),
        "blocked_months": [month for month in requested_months if month not in set(covered)],
    }


def build_report(
    *,
    source_candidate_generation_path: Path = DEFAULT_SOURCE_CANDIDATE_GENERATION,
    feature_store_path: Path = DEFAULT_FEATURE_STORE,
    forward_cohort_path: Path = DEFAULT_FORWARD_COHORT,
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
    if not no_write:
        raise ValueError("--no-write is required")

    source, source_meta = _load_json(source_candidate_generation_path)
    feature, feature_meta = _load_json(feature_store_path)
    cohort, cohort_meta = _load_json(forward_cohort_path)
    requested_months = _month_range(start, end)
    daily_rows, selected, integrity_blockers, outside_count = _normalize_daily_rows(
        source=source,
        source_meta=source_meta,
        feature=feature,
        cohort=cohort,
        start=start,
        end=end,
        as_of=as_of,
    )
    coverage = _coverage(daily_rows, requested_months)
    blockers = list(integrity_blockers)
    if feature_meta.get("status") != "loaded":
        blockers.append("feature_store_not_loaded")
    if cohort_meta.get("status") != "loaded":
        blockers.append("forward_cohort_contract_not_loaded")
    if coverage["candidate_generation_months_covered_count"] < len(requested_months):
        blockers.append(
            f"candidate_generation_months_{coverage['candidate_generation_months_covered_count']}_below_requested_{len(requested_months)}"
        )
    blockers = sorted(dict.fromkeys(blockers))
    status_counts = Counter(str(row.get("status")) for row in daily_rows)
    report = {
        "report_id": REPORT_ID,
        "status": "frozen_13_symbol_candidate_generation_entrypoint_ready" if not blockers else "blocked_frozen_13_symbol_candidate_generation_entrypoint",
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "schema_version": 1,
        "read_only": True,
        "research_only": True,
        "no_write": True,
        **FALSE_FLAGS,
        "scope": "read_only_no_write_frozen_13_symbol_candidate_generation_entrypoint",
        "inputs": {
            "source_candidate_generation": source_meta,
            "feature_store": feature_meta,
            "forward_cohort": cohort_meta,
        },
        "requested_window": {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "as_of_date": as_of.isoformat(),
            "requested_months": requested_months,
            "requested_month_count": len(requested_months),
        },
        "frozen_universe": list(ALLOWED_UNIVERSE),
        "allowed_universe": list(ALLOWED_UNIVERSE),
        "outside_universe_row_count": outside_count,
        **_source_non_parity(source),
        "calendar_coverage": {
            "covered_months": coverage["candidate_generation_months_covered"],
            "calendar_months_covered": coverage["candidate_generation_months_covered"],
            "calendar_months_covered_count": coverage["candidate_generation_months_covered_count"],
            "zero_selection_months": coverage["zero_selection_months"],
            "zero_selection_months_explicit": coverage["zero_selection_months_explicit"],
        },
        "coverage": coverage,
        "daily_status_counts": dict(sorted(status_counts.items())),
        "daily_candidate_generation_row_count": len(daily_rows),
        "selected_candidate_row_count": len(selected),
        "selected_trade_summary": {
            "selected_rows_in_window": len(selected),
            "selected_entry_months_with_rows": sorted({str(row.get("month")) for row in selected}),
        },
        "daily_candidate_generation": daily_rows,
        "selected_candidates": selected,
        "selected_trades": selected,
        "blockers": blockers,
        "proof_policy": {
            "readback_is": "read-only reusable frozen 13-symbol daily candidate/no-pick entrypoint",
            "readback_is_not": "profitability proof, fresh forward proof, scanner release, quote import, evidence mutation, live validation, auto-track, broker permission, protected-holdout consumption, proof-bar change, or promotion",
            "pass_condition": "every requested market-date lane/symbol row is selected_candidate or explicit_no_pick from an exact frozen 13-symbol source",
        },
        "forbidden_actions": FORBIDDEN_ACTIONS,
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    window = _as_dict(report.get("requested_window"))
    coverage = _as_dict(report.get("coverage"))
    lines = [
        "# Regular Options 13-Symbol Frozen Candidate Generation Entrypoint",
        "",
        "This generated artifact exposes a reusable read-only daily candidate/no-pick entrypoint for the frozen 13-symbol regular-options universe. It fails closed if the source is broad, missing daily diagnostics, or otherwise not exact.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Window: `{window.get('window_start')}` through `{window.get('window_end')}` as of `{window.get('as_of_date')}`.",
        f"- Daily rows: `{report.get('daily_candidate_generation_row_count')}`.",
        f"- Covered months: `{coverage.get('candidate_generation_months_covered_count')}` / `{coverage.get('requested_month_count')}`.",
        f"- Selected candidates: `{report.get('selected_candidate_row_count')}`.",
        f"- Outside-universe rows: `{report.get('outside_universe_row_count')}`.",
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
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            f"- Candidate materialization basis: `{report.get('candidate_materialization_basis')}`.",
            f"- Scanner parity: `{report.get('scanner_parity')}`.",
            f"- Production scanner replay: `{report.get('production_scanner_replay')}`.",
            "",
            "Historical rows and broad-source rows are not forward proof and are not converted into picks here.",
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
    daily_path = output_dir / "daily_candidate_generation.jsonl"
    selected_path = output_dir / "selected_candidates.jsonl"
    artifacts = {
        "json": _rel(json_path),
        "latest_json": _rel(latest_json),
        "markdown": _rel(md_path),
        "latest_markdown": _rel(latest_md),
        "daily_candidate_generation_jsonl": _rel(daily_path),
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
        for row in _as_list(report.get("daily_candidate_generation")):
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    with selected_path.open("w", encoding="utf8", newline="\n") as handle:
        for row in _as_list(report.get("selected_candidates")):
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return artifacts


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the read-only frozen 13-symbol candidate-generation entrypoint.")
    parser.add_argument("--source-candidate-generation", type=Path, default=DEFAULT_SOURCE_CANDIDATE_GENERATION)
    parser.add_argument("--source-feature-store", "--feature-store", type=Path, default=DEFAULT_FEATURE_STORE)
    parser.add_argument("--forward-cohort", type=Path, default=DEFAULT_FORWARD_COHORT)
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
        feature_store_path=args.source_feature_store,
        forward_cohort_path=args.forward_cohort,
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
