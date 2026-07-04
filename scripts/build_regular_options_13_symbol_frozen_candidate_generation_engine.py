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
)
from scripts.build_regular_options_robust_search_evaluation import _load_json  # noqa: E402


REPORT_ID = "regular_options_13_symbol_frozen_candidate_generation_engine"
DEFAULT_FEATURE_STORE = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_NO_WRITE_RUNNER = (
    ROOT / "data" / "profitability-lab" / "regular-options-13-symbol-candidate-generation-no-write" / "latest.json"
)
DEFAULT_FROZEN_ENTRYPOINT = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-13-symbol-frozen-candidate-generation-entrypoint"
    / "latest.json"
)
DEFAULT_SOURCE_SURFACE = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-13-symbol-frozen-candidate-generation-source-surface"
    / "latest.json"
)
DEFAULT_DENOMINATOR_V2 = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-13-symbol-frozen-candidate-generation-denominator-v2"
    / "latest.json"
)
DEFAULT_BASE_LEDGER = ROOT / "data" / "profitability-lab" / "regular-options-base-clean-stack-identity-ledger" / "latest.json"
DEFAULT_FORWARD_COHORT = ROOT / "data" / "contracts" / "forward-cohort-preregistration.json"
DEFAULT_FORWARD_HOLDOUT = ROOT / "data" / "contracts" / "forward-holdout-contract.json"
DEFAULT_SOURCE_QUALITY_POLICY = ROOT / "data" / "contracts" / "regular-options-source-quality-scope-policy.json"
DEFAULT_OUTPUT_DIR = (
    ROOT / "data" / "profitability-lab" / "regular-options-13-symbol-frozen-candidate-generation-engine"
)
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-13-symbol-frozen-candidate-generation-engine.md"
LATEST_AUDIT_MONTHS = ("2026-02", "2026-03", "2026-04", "2026-05")

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
    "order_preparation",
    "live_validation",
    "auto_track",
    "production_scanner_release",
    "production_scanner_policy_change",
    "production_strategy_change",
    "stop_change",
    "sizing_change",
    "proof_bar_change",
    "quote_import",
    "options_history_db_mutation",
    "evidence_database_mutation_outside_generated_research_artifacts",
    "forward_cohort_append",
    "protected_holdout_consumption",
    "promotion",
    "historical_rows_as_forward_proof",
    "post_hoc_filtering_broad_59_symbol_source_into_13_symbol_proof",
    "inventing_point_in_time_candidate_generation_decisions",
    "changing_frozen_cohort_membership_or_freeze_date",
    "using_midpoint_stale_eod_display_last_model_manual_synthetic_lookahead_zero_bid_or_untradable_marks_as_proof",
    "reclassifying_zero_bid_or_untradable_rows_as_missing_provider_data",
    "lowering_90pct_executable_quote_quality_floor",
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


def _market_dates(feature_store: dict[str, Any], start: date, end: date) -> list[date]:
    dates: list[date] = []
    for raw in _as_list(feature_store.get("shared_quote_dates")):
        parsed = _parse_date(raw)
        if parsed is not None and start <= parsed <= end:
            dates.append(parsed)
    return sorted(set(dates))


def _cohort_pairs(cohort: dict[str, Any], allowed_universe: Sequence[str]) -> list[dict[str, str]]:
    allowed = set(allowed_universe)
    pairs: list[dict[str, str]] = []
    for lane in _as_list(cohort.get("lanes")):
        lane_data = _as_dict(lane)
        lane_id = str(lane_data.get("lane_id") or "")
        policy_hash = str(lane_data.get("policy_snapshot_sha256") or "")
        for symbol in _as_list(lane_data.get("symbols")):
            ticker = str(symbol).upper()
            if lane_id and ticker in allowed:
                pairs.append({"lane": lane_id, "underlying": ticker, "policy_snapshot_sha256": policy_hash})
    return pairs


def _discover_reusable_entrypoint(no_write_runner: dict[str, Any]) -> dict[str, Any]:
    manifest = _as_dict(no_write_runner.get("support_manifest"))
    explicit = manifest.get("reusable_frozen_candidate_generation_entrypoint")
    if isinstance(explicit, str) and explicit.strip():
        return {"available": True, "entrypoint": explicit.strip(), "basis": "support_manifest"}

    entrypoints: list[str] = []
    for item in _as_list(no_write_runner.get("source_artifact_inventory")):
        entrypoints.extend(str(ep) for ep in _as_list(_as_dict(item).get("runner_entrypoints")) if str(ep).strip())
    frozen = [
        ep
        for ep in entrypoints
        if "frozen" in ep.lower() and ("candidate" in ep.lower() or "selection" in ep.lower())
    ]
    if frozen:
        return {"available": True, "entrypoint": frozen[0], "basis": "source_artifact_inventory"}

    return {
        "available": False,
        "entrypoint": None,
        "basis": "no_reusable_frozen_no_write_entrypoint_advertised",
        "inspected_candidate_commands": _as_list(manifest.get("candidate_commands")),
        "inspected_runner_entrypoints": entrypoints,
    }


def _entrypoint_discovery(no_write_runner: dict[str, Any], frozen_entrypoint: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    if meta.get("status") == "loaded" and frozen_entrypoint.get("report_id") == "regular_options_13_symbol_frozen_candidate_generation_entrypoint":
        return {
            "available": True,
            "entrypoint": "scripts/regular_options_frozen_candidate_generation_entrypoint.py",
            "basis": "frozen_entrypoint_artifact",
            "artifact_status": frozen_entrypoint.get("status"),
            "artifact_path": meta.get("path"),
        }
    discovered = _discover_reusable_entrypoint(no_write_runner)
    discovered["artifact_status"] = meta.get("status")
    discovered["artifact_path"] = meta.get("path")
    return discovered


def _cohort_guard(cohort: dict[str, Any], holdout: dict[str, Any], as_of: date) -> dict[str, Any]:
    cohort_data = _as_dict(cohort.get("cohort"))
    freeze_date = _parse_date(cohort_data.get("freeze_date"))
    eval_date = _parse_date(cohort_data.get("eval_date"))
    holdout_start = _parse_date(holdout.get("protected_holdout_start") or holdout.get("holdout_start"))
    return {
        "forward_cohort_status": cohort.get("status"),
        "freeze_date": freeze_date.isoformat() if freeze_date else None,
        "eval_date": eval_date.isoformat() if eval_date else None,
        "frozen": bool(cohort_data.get("frozen")),
        "as_of_before_protected_holdout": True if holdout_start is None else as_of < holdout_start,
        "protected_holdout_start": holdout_start.isoformat() if holdout_start else None,
    }


def _daily_rows(
    *,
    market_dates: Sequence[date],
    lane_symbol_pairs: Sequence[dict[str, str]],
    entrypoint_available: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    status = "blocked_missing_reusable_candidate_generation_entrypoint" if not entrypoint_available else "blocked_engine_execution_not_implemented"
    blocker = status
    for current_date in market_dates:
        for pair in lane_symbol_pairs:
            row_id = f"{REPORT_ID}:{current_date.isoformat()}:{pair['lane']}:{pair['underlying']}"
            rows.append(
                {
                    "row_id": row_id,
                    "date": current_date.isoformat(),
                    "month": current_date.isoformat()[:7],
                    "lane": pair["lane"],
                    "underlying": pair["underlying"],
                    "policy_snapshot_sha256": pair.get("policy_snapshot_sha256"),
                    "status": status,
                    "candidate_generated": False,
                    "explicit_no_pick": False,
                    "denominator_status": blocker,
                    "known_at": current_date.isoformat(),
                    "tradable_after": current_date.isoformat(),
                    "source_artifact_path": None,
                    "candidate_source_id": None,
                    "planned_entry_timestamp": None,
                    "planned_exit_policy": None,
                    "scanner_hash": None,
                    "opportunity_identity": row_id,
                    "blockers": [blocker],
                }
            )
    return rows


def _daily_rows_from_entrypoint(frozen_entrypoint: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [_as_dict(item) for item in _as_list(frozen_entrypoint.get("daily_candidate_generation"))]
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        item = dict(row)
        item.setdefault("row_id", f"{REPORT_ID}:entrypoint:{index}")
        item.setdefault("date", str(item.get("candidate_generation_date") or "")[:10])
        item.setdefault("month", str(item.get("date") or "")[:7])
        item.setdefault("lane", item.get("lane_id"))
        item.setdefault("underlying", item.get("ticker") or item.get("symbol"))
        item.setdefault("candidate_generated", item.get("status") == "selected_candidate")
        item.setdefault("explicit_no_pick", item.get("status") == "explicit_no_pick")
        item.setdefault("denominator_status", item.get("status"))
        item.setdefault("blockers", _as_list(item.get("blockers")))
        normalized.append(item)
    return normalized


def _coverage(daily_rows: Sequence[dict[str, Any]], requested_months: Sequence[str]) -> dict[str, Any]:
    by_month: dict[str, list[dict[str, Any]]] = {}
    for row in daily_rows:
        by_month.setdefault(str(row.get("month")), []).append(dict(row))
    covered_months = [
        month
        for month in requested_months
        if month in by_month and all(row.get("status") in {"candidate_generated", "selected_candidate", "explicit_no_pick"} for row in by_month[month])
    ]
    blocked_months = [month for month in requested_months if month not in set(covered_months)]
    coverage_proven = not blocked_months and len(covered_months) == len(requested_months)
    latest_audit_rows = [
        row
        for row in daily_rows
        if coverage_proven
        and str(row.get("month")) in set(LATEST_AUDIT_MONTHS)
        and str(row.get("status")) in {"candidate_generated", "selected_candidate"}
    ]
    latest_audit_exact_rows = [
        row
        for row in latest_audit_rows
        if bool(row.get("exact_priced"))
        and str(row.get("proof_grade") or "") == "trusted_intraday_opra_nbbo"
        and str(row.get("fill_basis") or "") == "imported_spread_mark"
    ]
    return {
        "requested_months": list(requested_months),
        "requested_month_count": len(requested_months),
        "candidate_generation_months_covered": covered_months,
        "candidate_generation_months_covered_count": len(covered_months),
        "train_months_covered": len([month for month in requested_months[:20] if month in set(covered_months)]),
        "audit_months_covered": len([month for month in LATEST_AUDIT_MONTHS if month in set(covered_months)]),
        "blocked_months": blocked_months,
        "missing_daily_diagnostics": len(blocked_months),
        "latest_audit_exact_trades": len(latest_audit_exact_rows),
        "latest_audit_exact_trades_scope": "strict_calendar_coverage_only",
        "latest_four_strict_new_candidates": len(latest_audit_rows),
    }


def _partial_audit_summary(source_surface: dict[str, Any]) -> dict[str, Any]:
    rows = [_as_dict(item) for item in _as_list(source_surface.get("selected_trades"))]
    exact_rows = [
        row
        for row in rows
        if bool(row.get("exact_priced"))
        and str(row.get("proof_grade") or "") == "trusted_intraday_opra_nbbo"
        and str(row.get("fill_basis") or "") == "imported_spread_mark"
    ]
    months = sorted({str(row.get("entry_date") or row.get("date") or "")[:7] for row in exact_rows if str(row.get("entry_date") or row.get("date") or "")[:7]})
    partial_rows = [row for row in rows if row.get("partial_audit_candidate")]
    coverage = _as_dict(source_surface.get("calendar_coverage"))
    strict_coverage = coverage.get("status") == "calendar_coverage_proven"
    return {
        "status": "partial_selected_row_audit_available" if exact_rows else "partial_selected_row_audit_unavailable",
        "strict_calendar_coverage_proven": strict_coverage,
        **_source_non_parity(source_surface),
        "selected_rows_exported": len(rows),
        "partial_audit_candidate_rows": len(partial_rows),
        "exact_priced_rows": len(exact_rows),
        "exact_priced_months": months,
        "exact_priced_month_count": len(months),
        "boundary": (
            "selected-row metrics are backed by strict candidate-generation month coverage"
            if strict_coverage
            else "partial selected-row metrics are diagnostic only and do not satisfy strict candidate-generation month coverage"
        ),
    }


def build_report(
    *,
    feature_store_path: Path = DEFAULT_FEATURE_STORE,
    no_write_runner_path: Path = DEFAULT_NO_WRITE_RUNNER,
    source_surface_path: Path = DEFAULT_SOURCE_SURFACE,
    denominator_v2_path: Path = DEFAULT_DENOMINATOR_V2,
    frozen_entrypoint_path: Path = DEFAULT_FROZEN_ENTRYPOINT,
    base_ledger_path: Path = DEFAULT_BASE_LEDGER,
    forward_cohort_path: Path = DEFAULT_FORWARD_COHORT,
    forward_holdout_path: Path = DEFAULT_FORWARD_HOLDOUT,
    source_quality_policy_path: Path = DEFAULT_SOURCE_QUALITY_POLICY,
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

    feature, feature_meta = _load_json(feature_store_path)
    no_write_runner, no_write_runner_meta = _load_json(no_write_runner_path)
    source_surface, source_surface_meta = _load_json(source_surface_path)
    denominator_v2, denominator_v2_meta = _load_json(denominator_v2_path)
    frozen_entrypoint, frozen_entrypoint_meta = _load_json(frozen_entrypoint_path)
    base_ledger, base_ledger_meta = _load_json(base_ledger_path)
    cohort, cohort_meta = _load_json(forward_cohort_path)
    holdout, holdout_meta = _load_json(forward_holdout_path)
    source_quality_policy, source_quality_policy_meta = _load_json(source_quality_policy_path)

    requested_months = _month_range(start, end)
    market_dates = _market_dates(feature, start, end)
    lane_symbol_pairs = _cohort_pairs(cohort, ALLOWED_UNIVERSE)
    entrypoint = _entrypoint_discovery(no_write_runner, frozen_entrypoint, frozen_entrypoint_meta)
    if entrypoint.get("basis") == "frozen_entrypoint_artifact":
        daily_rows = _daily_rows_from_entrypoint(frozen_entrypoint)
    else:
        daily_rows = _daily_rows(
            market_dates=market_dates,
            lane_symbol_pairs=lane_symbol_pairs,
            entrypoint_available=bool(entrypoint.get("available")),
        )
    coverage = _coverage(daily_rows, requested_months)
    status_counts = Counter(str(row.get("status")) for row in daily_rows)
    selected_candidates = [
        row for row in daily_rows if str(row.get("status")) in {"selected_candidate", "candidate_generated"}
    ]

    blockers: list[str] = []
    if feature_meta.get("status") != "loaded" or feature.get("status") != "feature_store_built":
        blockers.append("feature_store_not_loaded")
    if len(market_dates) == 0:
        blockers.append("feature_store_market_dates_missing")
    if no_write_runner_meta.get("status") != "loaded":
        blockers.append("no_write_runner_artifact_not_loaded")
    if not entrypoint.get("available"):
        blockers.append("blocked_missing_reusable_candidate_generation_entrypoint")
    if source_surface_meta.get("status") != "loaded":
        blockers.append("prior_frozen_source_surface_not_loaded")
    if denominator_v2_meta.get("status") != "loaded":
        blockers.append("prior_denominator_v2_not_loaded")
    if frozen_entrypoint_meta.get("status") != "loaded":
        blockers.append("frozen_candidate_generation_entrypoint_not_loaded")
    for blocker in _as_list(frozen_entrypoint.get("blockers")):
        blockers.append(str(blocker))
    if base_ledger_meta.get("status") != "loaded":
        blockers.append("base_clean_stack_identity_ledger_not_loaded")
    if cohort_meta.get("status") != "loaded":
        blockers.append("forward_cohort_contract_not_loaded")
    if holdout_meta.get("status") != "loaded":
        blockers.append("forward_holdout_contract_not_loaded")
    if source_quality_policy_meta.get("status") != "loaded":
        blockers.append("source_quality_policy_not_loaded")
    if coverage["candidate_generation_months_covered_count"] < len(requested_months):
        blockers.append("blocked_daily_candidate_generation_coverage")
    if coverage["train_months_covered"] < 20:
        blockers.append("blocked_train_or_audit_month_coverage")
    if coverage["audit_months_covered"] < 4:
        blockers.append("blocked_train_or_audit_month_coverage")
    if coverage["latest_audit_exact_trades"] < 30:
        blockers.append(f"strict_latest_audit_exact_trades_{coverage['latest_audit_exact_trades']}_below_30")
    blockers = sorted(dict.fromkeys(blockers))

    if not entrypoint.get("available"):
        decision = "blocked_missing_reusable_candidate_generation_entrypoint"
    elif blockers:
        decision = "blocked_frozen_candidate_generation_entrypoint_incomplete"
    else:
        decision = "frozen_13_symbol_candidate_generation_engine_ready"
    report = {
        "report_id": REPORT_ID,
        "status": "blocked_frozen_13_symbol_candidate_generation_engine" if blockers else "frozen_13_symbol_candidate_generation_engine_ready",
        "decision": decision if blockers else "frozen_13_symbol_candidate_generation_engine_ready",
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "schema_version": 1,
        "read_only": True,
        "research_only": True,
        "no_write": True,
        **FALSE_FLAGS,
        "scope": "frozen_13_symbol_candidate_generation_engine_daily_diagnostics_v1",
        "requested_window": {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "as_of_date": as_of.isoformat(),
            "requested_months": requested_months,
            "latest_audit_months": list(LATEST_AUDIT_MONTHS),
        },
        "allowed_universe": list(ALLOWED_UNIVERSE),
        **_source_non_parity(frozen_entrypoint),
        "inputs": {
            "feature_store": feature_meta,
            "no_write_runner": no_write_runner_meta,
            "frozen_entrypoint": frozen_entrypoint_meta,
            "prior_frozen_source_surface": source_surface_meta,
            "prior_denominator_v2": denominator_v2_meta,
            "base_clean_stack_identity_ledger": base_ledger_meta,
            "forward_cohort": cohort_meta,
            "forward_holdout": holdout_meta,
            "source_quality_policy": source_quality_policy_meta,
        },
        "baseline_reproduction": {
            "current_forward_rows": 0,
            "target_forward_rows": 30,
            "base_clean_stack_exact_rows": base_ledger.get("ledger_row_count")
            or base_ledger.get("expected_base_clean_stack_exact_rows"),
            "candidate_generation_13_symbol_quote_months": 24,
            "prior_frozen_source_surface_months_covered": _as_dict(source_surface.get("calendar_coverage")).get(
                "calendar_months_covered_count"
            ),
            "prior_frozen_source_surface_selected_rows": _as_dict(source_surface.get("selected_trade_summary")).get(
                "selected_rows_in_window"
            ),
            "prior_denominator_v2_all_rows_blocked": _as_dict(denominator_v2.get("candidate_generation_denominator")).get(
                "blocked_days"
            )
            == _as_dict(denominator_v2.get("calendar")).get("daily_status_row_count"),
            "prior_latest_four_strict_new_candidates": _as_dict(
                denominator_v2.get("candidate_generation_denominator")
            ).get("latest_four_month_candidate_rows_after_dedupe"),
            "prior_smallest_blocker": denominator_v2.get("smallest_next_blocker_clearing_slice"),
            "accepted_profitability": False,
            "historical_rows_are_forward_proof": False,
        },
        "forward_cohort_guard": _cohort_guard(cohort, holdout, as_of),
        "lane_symbol_pairs": lane_symbol_pairs,
        "reusable_entrypoint_discovery": entrypoint,
        "coverage": coverage,
        "partial_selected_row_audit": _partial_audit_summary(source_surface),
        "daily_candidate_generation_row_count": len(daily_rows),
        "daily_status_counts": dict(sorted(status_counts.items())),
        "selected_candidate_row_count": len(selected_candidates),
        "selected_candidates": selected_candidates,
        "daily_candidate_generation": daily_rows,
        "blockers": blockers,
        "smallest_next_blocker_clearing_slice": blockers[0] if blockers else None,
        "audit_consumed_generated_surface": False,
        "historical_simulated_forward_audit_command": None,
        "proof_policy": {
            "readback_is": "read-only frozen 13-symbol candidate-generation engine/daily diagnostics materializer",
            "readback_is_not": "profitability proof, fresh forward proof, scanner release, quote import, evidence mutation, live validation, broker permission, proof-bar change, protected-holdout consumption, or promotion",
            "fail_closed_rule": "without complete frozen daily selected_candidate or explicit_no_pick rows, daily diagnostics remain blocked and no picks are invented",
            "scanner_parity": _source_non_parity(frozen_entrypoint).get("scanner_parity"),
            "production_scanner_replay": _source_non_parity(frozen_entrypoint).get("production_scanner_replay"),
        },
        "forbidden_actions": FORBIDDEN_ACTIONS,
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    window = _as_dict(report.get("requested_window"))
    coverage = _as_dict(report.get("coverage"))
    baseline = _as_dict(report.get("baseline_reproduction"))
    coverage_proven = (
        int(coverage.get("candidate_generation_months_covered_count") or 0)
        == int(coverage.get("requested_month_count") or -1)
        and not _as_list(report.get("blockers"))
    )
    if coverage_proven:
        boundary = (
            "This artifact proves the requested frozen candidate-generation calendar coverage for the deterministic "
            "local PIT materializer, so downstream historical simulated-forward audit metrics may consume the generated "
            "selected rows. Historical rows remain non-forward proof, and scanner parity remains false."
        )
    else:
        boundary = (
            "This artifact does not run historical simulated-forward audit metrics because candidate-generation coverage "
            "is not proven. Historical rows remain non-forward proof."
        )
    lines = [
        "# Regular Options 13-Symbol Frozen Candidate Generation Engine",
        "",
        "This generated artifact materializes the frozen 13-symbol candidate-generation engine diagnostics. It is read-only and fails closed instead of inventing scanner decisions.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Decision: `{report.get('decision')}`.",
        f"- Window: `{window.get('window_start')}` through `{window.get('window_end')}` as of `{window.get('as_of_date')}`.",
        f"- Daily diagnostics rows: `{report.get('daily_candidate_generation_row_count')}`.",
        f"- Candidate-generation months covered: `{coverage.get('candidate_generation_months_covered_count')}` / `{coverage.get('requested_month_count')}`.",
        f"- Train months covered: `{coverage.get('train_months_covered')}`.",
        f"- Audit months covered: `{coverage.get('audit_months_covered')}`.",
        f"- Latest audit exact trades: `{coverage.get('latest_audit_exact_trades')}`.",
        f"- Latest audit exact-trade scope: `{coverage.get('latest_audit_exact_trades_scope')}`.",
        f"- Partial selected-row exact trades: `{_as_dict(report.get('partial_selected_row_audit')).get('exact_priced_rows')}`.",
        f"- Candidate materialization basis: `{report.get('candidate_materialization_basis')}`.",
        f"- Scanner parity: `{report.get('scanner_parity')}`.",
        f"- Production scanner replay: `{report.get('production_scanner_replay')}`.",
        f"- Prior source-surface months covered: `{baseline.get('prior_frozen_source_surface_months_covered')}`.",
        f"- Prior denominator all rows blocked: `{baseline.get('prior_denominator_v2_all_rows_blocked')}`.",
        f"- Accepted profitability: `{report.get('accepted_profitability')}`.",
        "",
        "## Status Counts",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status, count in _as_dict(report.get("daily_status_counts")).items():
        lines.append(f"| `{status}` | `{count}` |")
    blockers = _as_list(report.get("blockers"))
    if blockers:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            boundary,
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
    parser = argparse.ArgumentParser(description="Build the frozen 13-symbol candidate-generation engine diagnostics.")
    parser.add_argument("--source-feature-store", "--feature-store", type=Path, default=DEFAULT_FEATURE_STORE)
    parser.add_argument("--no-write-runner", type=Path, default=DEFAULT_NO_WRITE_RUNNER)
    parser.add_argument("--prior-source-surface", type=Path, default=DEFAULT_SOURCE_SURFACE)
    parser.add_argument("--prior-denominator-v2", type=Path, default=DEFAULT_DENOMINATOR_V2)
    parser.add_argument("--frozen-entrypoint", type=Path, default=DEFAULT_FROZEN_ENTRYPOINT)
    parser.add_argument("--base-ledger", type=Path, default=DEFAULT_BASE_LEDGER)
    parser.add_argument("--forward-cohort", type=Path, default=DEFAULT_FORWARD_COHORT)
    parser.add_argument("--forward-holdout", type=Path, default=DEFAULT_FORWARD_HOLDOUT)
    parser.add_argument("--source-quality-policy", type=Path, default=DEFAULT_SOURCE_QUALITY_POLICY)
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
        feature_store_path=args.source_feature_store,
        no_write_runner_path=args.no_write_runner,
        source_surface_path=args.prior_source_surface,
        denominator_v2_path=args.prior_denominator_v2,
        frozen_entrypoint_path=args.frozen_entrypoint,
        base_ledger_path=args.base_ledger,
        forward_cohort_path=args.forward_cohort,
        forward_holdout_path=args.forward_holdout,
        source_quality_policy_path=args.source_quality_policy,
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
