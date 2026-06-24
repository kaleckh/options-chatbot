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


REPORT_ID = "regular_options_13_symbol_candidate_generation_no_write"
DEFAULT_CANDIDATE_GENERATION = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-13-symbol-frozen-candidate-generation-source-surface"
    / "latest.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-13-symbol-candidate-generation-no-write"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-13-symbol-candidate-generation-no-write.md"
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
    "counting_quote_history_only_months_as_no_pick_proof",
    "counting_historical_rows_as_forward_proof",
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


def _month_key_to_date(month: str) -> date | None:
    return _parse_date(f"{month}-01")


def build_report(
    *,
    candidate_generation_path: Path = DEFAULT_CANDIDATE_GENERATION,
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
    if tuple(frozen_universe) != ALLOWED_UNIVERSE:
        raise ValueError("universe must exactly match the frozen 13-symbol universe")
    if not no_write:
        raise ValueError("--no-write is required")

    candidate_generation, candidate_meta = _load_json(candidate_generation_path)
    requested_months = _month_range(start, end)
    candidate_months = _candidate_months(candidate_generation)
    candidate_universe = _candidate_universe(candidate_generation)
    allowed_set = set(ALLOWED_UNIVERSE)
    selected_by_month = {
        month: [row for row in rows if _row_symbol(row) in allowed_set]
        for month, rows in _as_dict(candidate_months.get("selected_by_month")).items()
    }
    outside_by_month: dict[str, int] = defaultdict(int)
    for row in _candidate_selected_rows(candidate_generation):
        month = _row_month(row)
        if month and _row_symbol(row) and _row_symbol(row) not in allowed_set:
            outside_by_month[month] += 1

    month_diagnostics: list[dict[str, Any]] = []
    for month in requested_months:
        covered = month in set(candidate_months.get("covered_months") or [])
        zero_explicit = month in set(candidate_months.get("zero_selection_months") or [])
        source_surface_exact = bool(candidate_universe.get("frozen_universe_exact_13_symbols"))
        outside_count = int(outside_by_month.get(month, 0))
        selected_rows = _as_list(selected_by_month.get(month))
        blockers: list[str] = []
        if not covered:
            blockers.append("candidate_generation_diagnostics_missing_for_month")
        if not source_surface_exact:
            blockers.append("source_artifact_universe_not_13_symbol")
        if outside_count:
            blockers.append("outside_universe_source_rows_present")
        proven = bool(covered and source_surface_exact and not outside_count)
        month_diagnostics.append(
            {
                "month": month,
                "candidate_generation_attempted": covered,
                "candidate_generation_proven": proven,
                "explicit_no_pick_proof": bool(proven and zero_explicit and not selected_rows),
                "selected_trade_count": len(selected_rows) if proven else 0,
                "outside_universe_source_row_count": outside_count,
                "audit_coverable": bool(proven and (selected_rows or zero_explicit)),
                "blockers": blockers,
            }
        )

    status_counts = Counter(
        "audit_coverable" if row["audit_coverable"] else "blocked" for row in month_diagnostics
    )
    covered_months = [row["month"] for row in month_diagnostics if row["audit_coverable"]]
    blockers = sorted({blocker for row in month_diagnostics for blocker in row["blockers"]})
    if candidate_meta.get("status") != "loaded":
        blockers.append("candidate_generation_artifact_not_loaded")
    if len(covered_months) < len(requested_months):
        blockers.append(f"audit_coverable_months_{len(covered_months)}_below_requested_{len(requested_months)}")
    blockers = sorted(dict.fromkeys(blockers))

    invocation = (
        "uv run --locked python scripts/run_regular_options_13_symbol_no_write_candidate_generation.py "
        f"--start-date {start.isoformat()} --end-date {end.isoformat()} --as-of-date {as_of.isoformat()} "
        f"--universe {','.join(ALLOWED_UNIVERSE)} --no-write --json"
    )
    report = {
        "report_id": REPORT_ID,
        "status": "candidate_generation_no_write_runner_ready_with_blockers" if blockers else "candidate_generation_no_write_runner_ready",
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "read_only": True,
        "research_only": True,
        "no_write": True,
        **READ_ONLY_FALSE_FLAGS,
        "scope": "read_only_no_write_13_symbol_candidate_generation_runner_support",
        "inputs": {"candidate_generation": candidate_meta},
        "requested_window": {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "as_of_date": as_of.isoformat(),
            "requested_months": requested_months,
            "requested_month_count": len(requested_months),
        },
        "frozen_universe": list(ALLOWED_UNIVERSE),
        "support_manifest": {
            "read_only_no_write_runner_available": True,
            "read_only": True,
            "research_only": True,
            "no_write": True,
            "mutating": False,
            "as_of_date": as_of.isoformat(),
            "as_of_gated": True,
            "pre_holdout_as_of": as_of < date(2026, 6, 5),
            "universe_filter": True,
            "frozen_universe_exact_13_symbols": tuple(frozen_universe) == ALLOWED_UNIVERSE,
            "candidate_commands": [invocation],
            "quotes_imported": False,
            "evidence_stores_mutated": False,
            "protected_holdout_consumed": False,
            "production_scanner_changed": False,
            "strategy_logic_changed": False,
            "stops_changed": False,
            "sizing_changed": False,
            "proof_bars_changed": False,
        },
        "source_surface": candidate_universe,
        "month_diagnostics": month_diagnostics,
        "coverage": {
            "audit_coverable_months": covered_months,
            "audit_coverable_month_count": len(covered_months),
            "blocked_months": [row["month"] for row in month_diagnostics if not row["audit_coverable"]],
            "blocked_month_count": len([row for row in month_diagnostics if not row["audit_coverable"]]),
            "status_counts": dict(sorted(status_counts.items())),
        },
        "blockers": blockers,
        "forbidden_actions": FORBIDDEN_ACTIONS,
        "proof_policy": {
            "readback_is": "read-only no-write runner support and diagnostics for the frozen 13-symbol research surface",
            "readback_is_not": "profitability proof, fresh forward proof, scanner release, strategy change, quote import, evidence mutation, live validation, broker permission, or promotion",
        },
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    window = _as_dict(report.get("requested_window"))
    manifest = _as_dict(report.get("support_manifest"))
    coverage = _as_dict(report.get("coverage"))
    lines = [
        "# Regular Options 13-Symbol No-Write Candidate Generation",
        "",
        "This artifact proves the research-only runner controls for the frozen 13-symbol candidate-generation surface. It is not a replay, profitability proof, scanner release, quote import, evidence mutation, live validation, broker permission, or promotion.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Requested window: `{window.get('window_start')}` through `{window.get('window_end')}` as of `{window.get('as_of_date')}`.",
        f"- Runner available: `{manifest.get('read_only_no_write_runner_available')}`.",
        f"- No-write: `{manifest.get('no_write')}`.",
        f"- As-of gated: `{manifest.get('as_of_gated')}`.",
        f"- Universe filter: `{manifest.get('universe_filter')}`.",
        f"- Audit-coverable months: `{coverage.get('audit_coverable_month_count')}` / `{window.get('requested_month_count')}`.",
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
    blockers = _as_list(report.get("blockers"))
    if blockers:
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
    parser = argparse.ArgumentParser(description="Build read-only 13-symbol candidate-generation no-write support.")
    parser.add_argument("--candidate-generation", type=Path, default=DEFAULT_CANDIDATE_GENERATION)
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
        candidate_generation_path=args.candidate_generation,
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
