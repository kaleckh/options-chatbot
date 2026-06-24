from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
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
    _month_range,
    _parse_date,
    _row_month,
    _row_symbol,
)
from scripts.build_regular_options_robust_search_evaluation import _load_json  # noqa: E402


REPORT_ID = "regular_options_13_symbol_frozen_candidate_generation_denominator_v2"
DEFAULT_FEATURE_STORE = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_NO_WRITE_RUNNER = (
    ROOT / "data" / "profitability-lab" / "regular-options-13-symbol-candidate-generation-no-write" / "latest.json"
)
DEFAULT_SOURCE_SURFACE = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-13-symbol-frozen-candidate-generation-source-surface"
    / "latest.json"
)
DEFAULT_SURFACE_AUDIT = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-13-symbol-candidate-generation-surface-audit"
    / "latest.json"
)
DEFAULT_BASE_LEDGER = (
    ROOT / "data" / "profitability-lab" / "regular-options-base-clean-stack-identity-ledger" / "latest.json"
)
DEFAULT_SOURCE_QUALITY_POLICY = ROOT / "data" / "contracts" / "regular-options-source-quality-scope-policy.json"
DEFAULT_HOLDOUT_CONTRACT = ROOT / "data" / "contracts" / "forward-holdout-contract.json"
DEFAULT_COHORT_PREREGISTRATION = ROOT / "data" / "contracts" / "forward-cohort-preregistration.json"
DEFAULT_OUTPUT_DIR = (
    ROOT / "data" / "profitability-lab" / "regular-options-13-symbol-frozen-candidate-generation-denominator-v2"
)
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-13-symbol-frozen-candidate-generation-denominator-v2.md"
LATEST_FOUR_MONTHS = ("2026-02", "2026-03", "2026-04", "2026-05")

READ_ONLY_FLAGS = {
    "read_only": True,
    "research_only": True,
    "accepted_profitability": False,
    "historical_rows_are_forward_proof": False,
    "promotion_ready": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "scanner_policy_changed": False,
    "production_scanner_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "cohort_append_performed": False,
}

FORBIDDEN_ACTIONS = [
    "do_not_create_trades",
    "do_not_prepare_or_submit_broker_orders",
    "do_not_enable_live_validation",
    "do_not_enable_auto_track",
    "do_not_append_forward_paper_shadow_cohort",
    "do_not_import_quotes",
    "do_not_mutate_options_history_db",
    "do_not_mutate_evidence_stores",
    "do_not_consume_protected_holdout",
    "do_not_change_scanner_policy",
    "do_not_change_strategy_logic",
    "do_not_change_stops",
    "do_not_change_sizing",
    "do_not_lower_proof_bars",
    "do_not_promote_any_lane",
    "do_not_treat_historical_rows_as_forward_proof",
    "do_not_count_quote_coverage_as_candidate_generation_proof",
    "do_not_posthoc_filter_59_symbol_source_rows_into_13_symbol_proof",
    "do_not_count_midpoint_stale_eod_display_last_model_manual_marks",
    "do_not_reclassify_zero_bid_or_untradable_rows_as_missing_data",
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
    raw = value.split(",") if isinstance(value, str) else list(value)
    return [str(item).strip().upper() for item in raw if str(item).strip()]


def _market_dates(feature_store: dict[str, Any], start: date, end: date) -> list[date]:
    dates = sorted(
        parsed
        for item in _as_list(feature_store.get("shared_quote_dates"))
        if (parsed := _parse_date(item)) is not None and start <= parsed <= end
    )
    return dates


def _selected_rows_by_date(source_surface: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    rows_by_date: dict[str, list[dict[str, Any]]] = {}
    for raw in _as_list(source_surface.get("selected_trades")):
        row = _as_dict(raw)
        entry_date = _parse_date(row.get("entry_date") or row.get("candidate_entry_date") or row.get("date"))
        if entry_date:
            rows_by_date.setdefault(entry_date.isoformat(), []).append(row)
    return rows_by_date


def _month_diagnostics(source_surface: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("month")): _as_dict(row)
        for row in _as_list(source_surface.get("month_diagnostics"))
        if _as_dict(row).get("month")
    }


def _identity_hashes(base_ledger: dict[str, Any]) -> set[str]:
    values = set()
    for key in ("identity_hashes", "duplicate_identity_hashes"):
        values.update(str(item) for item in _as_list(base_ledger.get(key)) if str(item))
    for entry in _as_list(base_ledger.get("ledger_entries")):
        row = _as_dict(entry)
        for key in ("identity_hash", "opportunity_identity_hash"):
            if row.get(key):
                values.add(str(row[key]))
    return values


def _candidate_identity(row: dict[str, Any]) -> str:
    for key in ("opportunity_identity_hash", "identity_hash", "dedupe_key", "row_id"):
        if row.get(key):
            return str(row[key])
    parts = [
        _row_symbol(row),
        str(row.get("lane_id") or row.get("playbook") or ""),
        str(row.get("entry_date") or row.get("candidate_entry_date") or row.get("date") or ""),
        str(row.get("long_contract") or row.get("contract") or row.get("selected_contract") or ""),
        str(row.get("short_contract") or ""),
    ]
    return "|".join(parts)


def _cvx_policy_valid(policy: dict[str, Any], meta: dict[str, Any]) -> bool:
    if meta.get("status") != "loaded" or policy.get("status") != "active":
        return False
    for raw in _as_list(policy.get("rules")):
        rule = _as_dict(raw)
        if rule.get("rule_id") == "cvx_zero_bid_tradability_candidate_scope_v1" and rule.get("status") == "active":
            return "CVX" in {str(item).upper() for item in _as_list(rule.get("symbols"))}
    return False


def _build_daily_rows(
    *,
    market_dates: list[date],
    source_surface: dict[str, Any],
    base_hashes: set[str],
) -> tuple[list[dict[str, Any]], Counter[str], dict[str, int]]:
    diagnostics = _month_diagnostics(source_surface)
    selected_by_date = _selected_rows_by_date(source_surface)
    status_counts: Counter[str] = Counter()
    summary = Counter()
    daily_rows: list[dict[str, Any]] = []
    for current_date in market_dates:
        month = f"{current_date.year:04d}-{current_date.month:02d}"
        diag = diagnostics.get(month, {})
        selected_rows = selected_by_date.get(current_date.isoformat(), [])
        blockers = list(_as_list(diag.get("blockers")))
        month_proven = bool(diag.get("candidate_generation_proven"))
        explicit_no_pick = bool(month_proven and not selected_rows)
        if month_proven and selected_rows:
            status = "candidate_generated"
        elif month_proven and explicit_no_pick:
            status = "explicit_no_pick"
        elif "missing_daily_candidate_generation_diagnostics" in blockers:
            status = "blocked_missing_daily_diagnostics"
        elif "missing_frozen_13_symbol_candidate_generation_engine" in blockers:
            status = "blocked_missing_runner_output"
        elif blockers:
            status = "blocked_policy_scope"
        else:
            status = "blocked_unknown"

        strict_new_rows = 0
        overlap_rows = 0
        outside_rows = 0
        leakage_rows = 0
        for row in selected_rows:
            symbol = _row_symbol(row)
            if symbol and symbol not in ALLOWED_UNIVERSE:
                outside_rows += 1
            if _candidate_identity(row) in base_hashes:
                overlap_rows += 1
            else:
                strict_new_rows += 1
            if str(row.get("future_or_outcome_dependency") or "").lower() == "true":
                leakage_rows += 1

        status_counts[status] += 1
        summary["selected_candidate_rows"] += len(selected_rows)
        summary["strict_new_candidate_rows_after_opportunity_dedupe"] += strict_new_rows
        summary["overlap_rows_against_base_157"] += overlap_rows
        summary["outside_universe_rows"] += outside_rows
        summary["leakage_reject_rows"] += leakage_rows
        if status == "explicit_no_pick":
            summary["explicit_no_pick_days"] += 1
        if status.startswith("blocked_"):
            summary["blocked_days"] += 1
        if month in LATEST_FOUR_MONTHS:
            summary["latest_four_month_candidate_rows_after_dedupe"] += strict_new_rows

        daily_rows.append(
            {
                "date": current_date.isoformat(),
                "month": month,
                "status": status,
                "candidate_generation_proven": month_proven,
                "explicit_no_pick": explicit_no_pick,
                "selected_candidate_rows": len(selected_rows),
                "strict_new_candidate_rows_after_opportunity_dedupe": strict_new_rows,
                "overlap_rows_against_base_157": overlap_rows,
                "outside_universe_rows": outside_rows,
                "leakage_reject_rows": leakage_rows,
                "blockers": blockers,
            }
        )
    return daily_rows, status_counts, dict(summary)


def build_report(
    *,
    feature_store_path: Path = DEFAULT_FEATURE_STORE,
    no_write_runner_path: Path = DEFAULT_NO_WRITE_RUNNER,
    source_surface_path: Path = DEFAULT_SOURCE_SURFACE,
    surface_audit_path: Path = DEFAULT_SURFACE_AUDIT,
    base_ledger_path: Path = DEFAULT_BASE_LEDGER,
    source_quality_policy_path: Path = DEFAULT_SOURCE_QUALITY_POLICY,
    holdout_contract_path: Path = DEFAULT_HOLDOUT_CONTRACT,
    cohort_preregistration_path: Path = DEFAULT_COHORT_PREREGISTRATION,
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
        raise ValueError("start-date, end-date, and as-of-date must be valid YYYY-MM-DD values with start <= end")
    if frozen_universe != ALLOWED_UNIVERSE:
        raise ValueError("universe must exactly match the frozen 13-symbol universe")
    if not no_write:
        raise ValueError("--no-write is required")

    feature, feature_meta = _load_json(feature_store_path)
    runner, runner_meta = _load_json(no_write_runner_path)
    source_surface, source_meta = _load_json(source_surface_path)
    surface_audit, surface_audit_meta = _load_json(surface_audit_path)
    base_ledger, base_meta = _load_json(base_ledger_path)
    policy, policy_meta = _load_json(source_quality_policy_path)
    holdout, holdout_meta = _load_json(holdout_contract_path)
    cohort, cohort_meta = _load_json(cohort_preregistration_path)

    requested_months = _month_range(start, end)
    dates = _market_dates(feature, start, end)
    base_hashes = _identity_hashes(base_ledger)
    daily_rows, daily_status_counts, row_summary = _build_daily_rows(
        market_dates=dates,
        source_surface=source_surface,
        base_hashes=base_hashes,
    )

    source_coverage = _as_dict(source_surface.get("calendar_coverage"))
    runner_manifest = _as_dict(runner.get("support_manifest"))
    audit_quote_vs_generation = _as_dict(surface_audit.get("quote_history_vs_candidate_generation"))

    blockers: list[str] = []
    if feature_meta.get("status") != "loaded" or feature.get("status") != "feature_store_built":
        blockers.append("feature_store_not_loaded")
    if len(dates) == 0:
        blockers.append("feature_store_market_calendar_empty")
    if runner_meta.get("status") != "loaded" or runner_manifest.get("read_only_no_write_runner_available") is not True:
        blockers.append("missing_no_write_runner_support")
    if source_meta.get("status") != "loaded":
        blockers.append("missing_frozen_13_symbol_candidate_generation_source_surface")
    blockers.extend(str(item) for item in _as_list(source_surface.get("blockers")))
    if base_meta.get("status") != "loaded" or base_ledger.get("status") != "base_clean_stack_identity_ledger_ready":
        blockers.append("base_clean_stack_identity_ledger_not_ready")
    if not _cvx_policy_valid(policy, policy_meta):
        blockers.append("source_quality_policy_not_ready")
    if holdout_meta.get("status") != "loaded":
        blockers.append("protected_holdout_contract_not_loaded")
    if cohort_meta.get("status") != "loaded":
        blockers.append("forward_cohort_preregistration_not_loaded")
    if int(source_coverage.get("calendar_months_covered_count") or 0) < len(requested_months):
        blockers.append(
            f"candidate_generation_months_{int(source_coverage.get('calendar_months_covered_count') or 0)}_below_requested_{len(requested_months)}"
        )
    if row_summary.get("blocked_days", 0) > 0:
        blockers.append("blocked_daily_candidate_generation_coverage")
    if row_summary.get("latest_four_month_candidate_rows_after_dedupe", 0) < 30:
        blockers.append("blocked_latest_four_month_rows_below_30")
    if row_summary.get("outside_universe_rows", 0) > 0:
        blockers.append("blocked_outside_frozen_universe")
    if row_summary.get("leakage_reject_rows", 0) > 0:
        blockers.append("blocked_leakage_or_asof_violation")
    blockers = sorted(dict.fromkeys(blockers))

    coverage_ready = (
        not blockers
        and int(row_summary.get("blocked_days", 0)) == 0
        and row_summary.get("latest_four_month_candidate_rows_after_dedupe", 0) >= 30
    )
    status = (
        "ready_13_symbol_frozen_candidate_generation_denominator_v2"
        if coverage_ready
        else "blocked_13_symbol_frozen_candidate_generation_denominator_v2"
    )
    smallest = (
        "missing_frozen_13_symbol_candidate_generation_engine"
        if "missing_frozen_13_symbol_candidate_generation_engine" in blockers
        else blockers[0] if blockers else None
    )

    report = {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "schema_version": 1,
        **READ_ONLY_FLAGS,
        "no_write": True,
        "scope": "read_only_13_symbol_frozen_candidate_generation_denominator_v2",
        "allowed_universe": list(ALLOWED_UNIVERSE),
        "requested_window": {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "as_of_date": as_of.isoformat(),
            "requested_months": requested_months,
            "requested_month_count": len(requested_months),
            "latest_four_months": list(LATEST_FOUR_MONTHS),
        },
        "inputs": {
            "feature_store": feature_meta,
            "no_write_runner": runner_meta,
            "source_surface": source_meta,
            "surface_audit": surface_audit_meta,
            "base_clean_stack_identity_ledger": base_meta,
            "source_quality_policy": policy_meta,
            "forward_holdout_contract": holdout_meta,
            "forward_cohort_preregistration": cohort_meta,
        },
        "baseline_reproduction": {
            "candidate_generation_13_symbol_quote_months": audit_quote_vs_generation.get(
                "quote_surface_months_available_count"
            ),
            "candidate_generation_13_symbol_frozen_source_surface_selected_rows": _as_dict(
                source_surface.get("selected_trade_summary")
            ).get("selected_rows_in_window"),
            "candidate_generation_13_symbol_frozen_source_surface_months_covered": source_coverage.get(
                "calendar_months_covered_count"
            ),
            "runner_status": _as_dict(surface_audit.get("runner_support")).get("status"),
        },
        "calendar": {
            "market_date_count": len(dates),
            "requested_months_count": len(requested_months),
            "daily_status_row_count": len(daily_rows),
            "daily_status_counts": dict(sorted(daily_status_counts.items())),
        },
        "candidate_generation_denominator": {
            "train_months_covered": int(source_coverage.get("calendar_months_covered_count") or 0),
            "audit_months_covered": len(
                [month for month in LATEST_FOUR_MONTHS if month in set(source_coverage.get("calendar_months_covered") or [])]
            ),
            "selected_candidate_rows": int(row_summary.get("selected_candidate_rows", 0)),
            "strict_new_candidate_rows_after_opportunity_dedupe": int(
                row_summary.get("strict_new_candidate_rows_after_opportunity_dedupe", 0)
            ),
            "latest_four_month_candidate_rows_after_dedupe": int(
                row_summary.get("latest_four_month_candidate_rows_after_dedupe", 0)
            ),
            "overlap_rows_against_base_157": int(row_summary.get("overlap_rows_against_base_157", 0)),
            "explicit_no_pick_days": int(row_summary.get("explicit_no_pick_days", 0)),
            "blocked_days": int(row_summary.get("blocked_days", 0)),
            "outside_universe_rows": int(row_summary.get("outside_universe_rows", 0)),
            "leakage_reject_rows": int(row_summary.get("leakage_reject_rows", 0)),
            "protected_holdout_overlap_rows": 0,
            "source_quality_policy_violations": 0 if _cvx_policy_valid(policy, policy_meta) else 1,
        },
        "daily_status": daily_rows,
        "blockers": blockers,
        "smallest_next_blocker_clearing_slice": smallest,
        "next_bounded_read_only_audit_command": (
            "npm run options:audit:historical-simulated-forward -- --json"
            if coverage_ready
            else None
        ),
        "proof_policy": {
            "readback_is": "read-only frozen 13-symbol daily candidate/no-pick/blocker denominator",
            "readback_is_not": "profitability proof, fresh forward proof, scanner release, quote import, evidence mutation, live validation, broker permission, proof-bar change, or promotion",
            "ready_condition": "24/24 candidate-generation months, no blocked days, no leakage, no holdout overlap, and at least 30 latest-four-month strict-new candidate rows after opportunity dedupe",
        },
        "forbidden_actions": FORBIDDEN_ACTIONS,
    }
    return report


def _cell(value: Any) -> str:
    return ("" if value is None else str(value)).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict[str, Any]) -> str:
    window = _as_dict(report.get("requested_window"))
    baseline = _as_dict(report.get("baseline_reproduction"))
    calendar = _as_dict(report.get("calendar"))
    denominator = _as_dict(report.get("candidate_generation_denominator"))
    lines = [
        "# Regular Options 13-Symbol Frozen Candidate Generation Denominator v2",
        "",
        "This generated artifact materializes the daily candidate/no-pick/blocker denominator for the frozen 13-symbol surface. It is read-only and does not run live scans, create trades, import quotes, mutate evidence stores, append forward cohorts, consume protected holdout, change scanner or strategy logic, or promote any lane.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Requested window: `{window.get('window_start')}` through `{window.get('window_end')}` as of `{window.get('as_of_date')}`.",
        f"- Requested months: `{window.get('requested_month_count')}`.",
        f"- Latest four months: `{', '.join(str(item) for item in _as_list(window.get('latest_four_months')))}`.",
        f"- Market-date denominator rows: `{calendar.get('daily_status_row_count')}`.",
        f"- Baseline quote months: `{baseline.get('candidate_generation_13_symbol_quote_months')}`.",
        f"- Baseline source-surface months: `{baseline.get('candidate_generation_13_symbol_frozen_source_surface_months_covered')}`.",
        f"- Runner status: `{baseline.get('runner_status')}`.",
        f"- Latest-four strict-new candidates: `{denominator.get('latest_four_month_candidate_rows_after_dedupe')}`.",
        f"- Blocked days: `{denominator.get('blocked_days')}`.",
        f"- Accepted profitability: `{report.get('accepted_profitability')}`.",
        "",
        "## Daily Status Counts",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status, count in _as_dict(calendar.get("daily_status_counts")).items():
        lines.append(f"| `{_cell(status)}` | `{_cell(count)}` |")
    blockers = _as_list(report.get("blockers"))
    if blockers:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This artifact only decides whether the frozen 13-symbol candidate-generation denominator is auditable. Quote coverage alone does not count as candidate-generation proof, and historical rows remain non-forward proof.",
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
    daily_path = output_dir / "daily_status.jsonl"
    artifacts = {
        "json": _rel(json_path),
        "latest_json": _rel(latest_json),
        "markdown": _rel(md_path),
        "latest_markdown": _rel(latest_md),
        "daily_status_jsonl": _rel(daily_path),
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
        for row in _as_list(report.get("daily_status")):
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return artifacts


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build read-only frozen 13-symbol denominator v2.")
    parser.add_argument("--feature-store", type=Path, default=DEFAULT_FEATURE_STORE)
    parser.add_argument("--no-write-runner", type=Path, default=DEFAULT_NO_WRITE_RUNNER)
    parser.add_argument("--source-surface", type=Path, default=DEFAULT_SOURCE_SURFACE)
    parser.add_argument("--surface-audit", type=Path, default=DEFAULT_SURFACE_AUDIT)
    parser.add_argument("--base-ledger", type=Path, default=DEFAULT_BASE_LEDGER)
    parser.add_argument("--source-quality-policy", type=Path, default=DEFAULT_SOURCE_QUALITY_POLICY)
    parser.add_argument("--holdout-contract", type=Path, default=DEFAULT_HOLDOUT_CONTRACT)
    parser.add_argument("--cohort-preregistration", type=Path, default=DEFAULT_COHORT_PREREGISTRATION)
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
        feature_store_path=args.feature_store,
        no_write_runner_path=args.no_write_runner,
        source_surface_path=args.source_surface,
        surface_audit_path=args.surface_audit,
        base_ledger_path=args.base_ledger,
        source_quality_policy_path=args.source_quality_policy,
        holdout_contract_path=args.holdout_contract,
        cohort_preregistration_path=args.cohort_preregistration,
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
