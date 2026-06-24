from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_regular_options_robust_search_evaluation import _load_json  # noqa: E402


REPORT_ID = "regular_options_13_symbol_candidate_generation_surface_audit"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-13-symbol-candidate-generation-surface-audit"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-13-symbol-candidate-generation-surface-audit.md"
DEFAULT_FEATURE_STORE_REPORT = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_SELECTED_TRADE_DEPTH = (
    ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-selected-trade-depth" / "latest.json"
)
DEFAULT_CANDIDATE_GENERATION = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-13-symbol-frozen-candidate-generation-source-surface"
    / "latest.json"
)
DEFAULT_NO_WRITE_CANDIDATE_GENERATION = (
    ROOT / "data" / "profitability-lab" / "regular-options-13-symbol-candidate-generation-no-write" / "latest.json"
)
DEFAULT_SOURCE_QUALITY_POLICY = ROOT / "data" / "contracts" / "regular-options-source-quality-scope-policy.json"
DEFAULT_HOLDOUT_CONTRACT = ROOT / "data" / "contracts" / "forward-holdout-contract.json"
DEFAULT_WINDOW_START = "2024-06-01"
DEFAULT_WINDOW_END = "2026-05-31"
DEFAULT_AS_OF_DATE = "2026-06-04"
EXPECTED_SOURCE_LABEL = "thetadata_opra_nbbo_1m"
EXPECTED_SNAPSHOT_KIND = "intraday"
EXPECTED_DATA_TRUST = "trusted"
ALLOWED_UNIVERSE = (
    "SPY",
    "QQQ",
    "IWM",
    "AAPL",
    "GOOGL",
    "UNH",
    "LLY",
    "JNJ",
    "XOM",
    "CVX",
    "COP",
    "NEM",
    "DIA",
)
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
    "production_scanner_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
}
FORBIDDEN_ACTIONS = (
    "broker_orders",
    "order_preparation",
    "live_validation",
    "auto_track",
    "production_scanner_change",
    "strategy_logic_change",
    "stop_or_sizing_change",
    "proof_bar_relaxation",
    "quote_import",
    "evidence_database_mutation",
    "protected_holdout_consumption",
    "promotion",
    "count_quote_depth_as_zero_selection_proof",
)
MUTATING_COMMAND_TOKENS = (
    "--write",
    "--apply",
    "--import",
    "import_quotes",
    "append_",
    "broker",
    "live-validation",
    "auto-track",
    "promotion",
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
            month = 1
            year += 1
    return months


def _safe_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _symbols(values: Any) -> list[str]:
    return sorted({str(item).strip().upper() for item in _as_list(values) if str(item).strip()})


def _row_symbol(row: dict[str, Any]) -> str:
    return str(row.get("ticker") or row.get("symbol") or row.get("underlying") or "").strip().upper()


def _row_month(row: dict[str, Any]) -> str | None:
    return _month_key(row.get("entry_date") or row.get("candidate_entry_date") or row.get("date"))


def _shared_quote_months(feature: dict[str, Any]) -> set[str]:
    months = {_month_key(item) for item in _as_list(feature.get("shared_quote_dates"))}
    summary = _as_dict(feature.get("summary"))
    first = _parse_date(summary.get("first_shared_quote_date_et"))
    latest = _parse_date(summary.get("latest_shared_quote_date_et"))
    if first and latest:
        months.update(_month_range(first, latest))
    months.discard(None)
    return {str(month) for month in months if month}


def _holdout_start(contract: dict[str, Any]) -> date | None:
    protected = _as_dict(contract.get("protected_range"))
    return _parse_date(protected.get("start_date"))


def _feature_surface(feature: dict[str, Any], feature_meta: dict[str, Any]) -> dict[str, Any]:
    rows = [_as_dict(item) for item in _as_list(feature.get("symbol_surface_rows"))]
    row_symbols = _symbols([row.get("symbol") for row in rows])
    inputs = _as_dict(feature.get("inputs"))
    summary = _as_dict(feature.get("summary"))
    contract = _as_dict(feature.get("feature_contract"))
    trusted_filter = _as_dict(contract.get("trusted_source_filter"))
    source_labels = sorted({str(row.get("source_label") or "") for row in rows if row.get("source_label")})
    snapshot_kinds = sorted({str(row.get("snapshot_kind") or "") for row in rows if row.get("snapshot_kind")})
    data_trust = sorted({str(row.get("data_trust") or "") for row in rows if row.get("data_trust")})
    blockers: list[str] = []
    if feature_meta.get("status") != "loaded":
        blockers.append("feature_store_not_loaded")
    if row_symbols != sorted(ALLOWED_UNIVERSE):
        blockers.append("feature_store_universe_not_exact_13_symbol")
    if inputs.get("source_label") != EXPECTED_SOURCE_LABEL or source_labels != [EXPECTED_SOURCE_LABEL]:
        blockers.append("feature_store_source_label_not_trusted_thetadata_opra_nbbo_1m")
    if inputs.get("snapshot_kind") != EXPECTED_SNAPSHOT_KIND or snapshot_kinds != [EXPECTED_SNAPSHOT_KIND]:
        blockers.append("feature_store_snapshot_kind_not_intraday")
    if data_trust != [EXPECTED_DATA_TRUST]:
        blockers.append("feature_store_data_trust_not_trusted")
    join_rule = str(contract.get("point_in_time_join_rule") or "")
    if "tradable_after_time <= candidate_entry_time" not in join_rule:
        blockers.append("feature_store_point_in_time_join_rule_missing")
    return {
        "status": "valid_13_symbol_point_in_time_quote_surface" if not blockers else "blocked_feature_surface",
        "blockers": blockers,
        "expected_universe": list(ALLOWED_UNIVERSE),
        "symbol_surface_symbols": row_symbols,
        "source_labels": source_labels,
        "snapshot_kinds": snapshot_kinds,
        "data_trust": data_trust,
        "shared_quote_date_count": summary.get("shared_quote_date_count"),
        "first_shared_quote_date_et": summary.get("first_shared_quote_date_et"),
        "latest_shared_quote_date_et": summary.get("latest_shared_quote_date_et"),
        "point_in_time_join_rule": join_rule,
        "trusted_source_filter": trusted_filter,
    }


def _candidate_selected_rows(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [_as_dict(item) for item in _as_list(candidate.get("selected_trades"))]
    if rows:
        return rows
    return [_as_dict(item) for item in _as_list(_as_dict(candidate.get("selected_trade_summary")).get("selected_trades"))]


def _candidate_universe(candidate: dict[str, Any]) -> dict[str, Any]:
    explicit = (
        candidate.get("allowed_universe")
        or candidate.get("frozen_universe")
        or candidate.get("research_universe")
        or _as_dict(candidate.get("candidate_surface")).get("allowed_universe")
    )
    explicit_symbols = _symbols(explicit)
    source_underlyings: set[str] = set()
    for artifact in _as_list(candidate.get("source_artifact_inventory")):
        replay_calendar = _as_dict(_as_dict(artifact).get("replay_calendar"))
        source_underlyings.update(_symbols(replay_calendar.get("underlyings")))
    selected_symbols = _symbols([_row_symbol(row) for row in _candidate_selected_rows(candidate)])
    union = sorted(set(explicit_symbols) | source_underlyings | set(selected_symbols))
    outside = sorted(set(union) - set(ALLOWED_UNIVERSE))
    exact = (explicit_symbols or sorted(source_underlyings)) == sorted(ALLOWED_UNIVERSE) and not outside
    return {
        "explicit_universe": explicit_symbols,
        "source_artifact_underlyings": sorted(source_underlyings),
        "selected_trade_symbols": selected_symbols,
        "observed_union": union,
        "outside_allowed_universe": outside,
        "frozen_universe_exact_13_symbols": exact,
    }


def _candidate_months(candidate: dict[str, Any]) -> dict[str, Any]:
    coverage = _as_dict(candidate.get("calendar_coverage"))
    covered = _symbols(coverage.get("covered_months") or coverage.get("calendar_months_covered"))
    zero_months = _symbols(coverage.get("zero_selection_months"))
    zero_explicit_global = bool(coverage.get("zero_selection_months_explicit"))
    selected_by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _candidate_selected_rows(candidate):
        if month := _row_month(row):
            selected_by_month[month].append(row)
    diag_by_month: dict[str, dict[str, Any]] = {}
    for raw in _as_list(candidate.get("month_diagnostics")):
        row = _as_dict(raw)
        month = str(row.get("month") or "")
        if not month:
            continue
        diag_by_month[month] = row
        if row.get("candidate_generation_proven"):
            covered.append(month)
        if row.get("zero_selection_month_explicit"):
            zero_months.append(month)
    return {
        "covered_months": sorted(set(covered)),
        "zero_selection_months": sorted(set(zero_months)),
        "zero_selection_months_explicit_global": zero_explicit_global,
        "selected_by_month": dict(selected_by_month),
        "month_diagnostics_by_month": diag_by_month,
    }


def _selected_trade_depth_months(selected_trade_depth: dict[str, Any]) -> dict[str, Any]:
    coverage = _as_dict(selected_trade_depth.get("calendar_coverage"))
    return {
        "status": selected_trade_depth.get("status"),
        "covered_months": _symbols(coverage.get("covered_months") or coverage.get("calendar_months_covered")),
        "zero_selection_months": _symbols(coverage.get("zero_selection_months")),
        "zero_selection_months_explicit": bool(coverage.get("zero_selection_months_explicit")),
        "blockers": _as_list(selected_trade_depth.get("blockers")),
    }


def _cvx_scope(policy: dict[str, Any], policy_meta: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    rules = [_as_dict(rule) for rule in _as_list(policy.get("rules"))]
    rule = next((item for item in rules if item.get("rule_id") == "cvx_zero_bid_tradability_candidate_scope_v1"), {})
    exclusions = [
        _as_dict(item)
        for item in _as_list(candidate.get("source_quality_exclusions"))
        if _as_dict(item).get("rule_id") == "cvx_zero_bid_tradability_candidate_scope_v1"
    ]
    enforced = (
        policy_meta.get("status") == "loaded"
        and policy.get("status") == "active"
        and rule.get("status") == "active"
        and "CVX" in _symbols(rule.get("symbols"))
        and _safe_float(rule.get("minimum_executable_quote_pct")) is not None
        and (_safe_float(rule.get("minimum_executable_quote_pct")) or 0.0) >= 90.0
    )
    return {
        "policy_loaded": policy_meta.get("status") == "loaded",
        "rule_id": rule.get("rule_id"),
        "rule_status": rule.get("status"),
        "cvx_scope_enforced": enforced,
        "minimum_executable_quote_pct": rule.get("minimum_executable_quote_pct"),
        "observed_executable_quote_pct": rule.get("observed_executable_quote_pct"),
        "excluded_trade_count": len(exclusions),
        "excluded_months": sorted({str(_row_month(row)) for row in exclusions if _row_month(row)}),
        "policy_blocker": None if enforced else "cvx_scope_policy_missing_or_inactive",
    }


def _runner_support(candidate: dict[str, Any]) -> dict[str, Any]:
    support = _as_dict(candidate.get("runner_support") or candidate.get("no_write_runner_support"))
    commands = [
        str(item)
        for item in _as_list(candidate.get("candidate_runner_commands") or support.get("candidate_commands"))
        if str(item).strip()
    ]
    for artifact in _as_list(candidate.get("source_artifact_inventory")):
        for entrypoint in _as_list(_as_dict(artifact).get("runner_entrypoints")):
            text = str(entrypoint)
            if text and text not in commands:
                commands.append(text)
    rejected = []
    candidate_commands = []
    for command in commands:
        lowered = command.lower()
        mutating = any(token in lowered for token in MUTATING_COMMAND_TOKENS)
        no_write = "--no-write" in lowered or bool(support.get("no_write"))
        as_of = "--as-of-date" in lowered or bool(support.get("as_of_date"))
        universe = any(token in lowered for token in ("--symbols", "--underlyings", "--only", "--required-underlyings")) or bool(
            support.get("universe_filter")
        )
        pre_holdout = "--as-of-date 2026-06-04" in lowered or "--as-of-date=2026-06-04" in lowered or bool(
            support.get("pre_holdout_as_of")
        )
        if mutating or not (no_write and as_of and universe and pre_holdout):
            rejected.append(
                {
                    "command": command,
                    "mutating": mutating,
                    "no_write": no_write,
                    "as_of_gated": as_of,
                    "universe_filter": universe,
                    "pre_holdout_as_of": pre_holdout,
                }
            )
        else:
            candidate_commands.append(command)
    explicit_ready = all(
        bool(support.get(key))
        for key in ("no_write", "read_only", "as_of_date", "universe_filter", "pre_holdout_as_of")
    )
    ready = explicit_ready and not rejected
    if commands and not candidate_commands:
        ready = False
    return {
        "status": "read_only_no_write_runner_available" if ready else "missing_no_write_runner_support",
        "read_only_no_write_runner_available": ready,
        "candidate_commands": candidate_commands,
        "rejected_commands": rejected,
        "support_manifest": support,
    }


def _no_write_runner_support(report: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any] | None:
    if meta.get("status") != "loaded":
        return None
    manifest = _as_dict(report.get("support_manifest"))
    required_true = (
        "read_only_no_write_runner_available",
        "read_only",
        "research_only",
        "no_write",
        "as_of_gated",
        "pre_holdout_as_of",
        "universe_filter",
        "frozen_universe_exact_13_symbols",
    )
    required_false = (
        "mutating",
        "quotes_imported",
        "evidence_stores_mutated",
        "protected_holdout_consumed",
        "production_scanner_changed",
        "strategy_logic_changed",
        "stops_changed",
        "sizing_changed",
        "proof_bars_changed",
    )
    reason_codes: list[str] = []
    if report.get("report_id") != "regular_options_13_symbol_candidate_generation_no_write":
        reason_codes.append("wrong_report_id")
    for key in required_true:
        if manifest.get(key) is not True:
            reason_codes.append(f"{key}_not_true")
    for key in required_false:
        if manifest.get(key) is not False:
            reason_codes.append(f"{key}_not_false")
    commands = [str(item) for item in _as_list(manifest.get("candidate_commands")) if str(item).strip()]
    if not commands:
        reason_codes.append("candidate_commands_missing")
    return {
        "status": "read_only_no_write_runner_available" if not reason_codes else "invalid_no_write_runner_support",
        "read_only_no_write_runner_available": not reason_codes,
        "candidate_commands": commands if not reason_codes else [],
        "rejected_commands": [],
        "support_manifest": manifest,
        "source_artifact_status": report.get("status"),
        "validation_reason_codes": reason_codes,
    }


def _month_is_holdout_overlap(month: str, protected_start: date | None) -> bool:
    month_start = _parse_date(f"{month}-01")
    if month_start is None or protected_start is None:
        return False
    return month_start >= protected_start.replace(day=1)


def build_report(
    *,
    feature_store_report_path: Path = DEFAULT_FEATURE_STORE_REPORT,
    selected_trade_depth_path: Path = DEFAULT_SELECTED_TRADE_DEPTH,
    candidate_generation_path: Path = DEFAULT_CANDIDATE_GENERATION,
    no_write_candidate_generation_path: Path | None = DEFAULT_NO_WRITE_CANDIDATE_GENERATION,
    source_quality_policy_path: Path = DEFAULT_SOURCE_QUALITY_POLICY,
    holdout_contract_path: Path = DEFAULT_HOLDOUT_CONTRACT,
    window_start: str = DEFAULT_WINDOW_START,
    window_end: str = DEFAULT_WINDOW_END,
    as_of_date: str = DEFAULT_AS_OF_DATE,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    feature, feature_meta = _load_json(feature_store_report_path)
    selected_trade_depth, selected_trade_depth_meta = _load_json(selected_trade_depth_path)
    candidate_generation, candidate_generation_meta = _load_json(candidate_generation_path)
    no_write_candidate_generation, no_write_candidate_generation_meta = (
        _load_json(no_write_candidate_generation_path)
        if no_write_candidate_generation_path is not None
        else ({}, {"status": "not_configured", "path": None, "exists": False})
    )
    policy, policy_meta = _load_json(source_quality_policy_path)
    holdout, holdout_meta = _load_json(holdout_contract_path)
    start = _parse_date(window_start)
    end = _parse_date(window_end)
    as_of = _parse_date(as_of_date)
    if start is None or end is None or as_of is None or end < start:
        raise ValueError("window-start, window-end, and as-of-date must be valid YYYY-MM-DD values with start <= end")

    requested_months = _month_range(start, end)
    quote_months = _shared_quote_months(feature)
    feature_surface = _feature_surface(feature, feature_meta)
    candidate_universe = _candidate_universe(candidate_generation)
    candidate_months = _candidate_months(candidate_generation)
    selected_depth_months = _selected_trade_depth_months(selected_trade_depth)
    cvx_scope = _cvx_scope(policy, policy_meta, candidate_generation)
    runner_support = _no_write_runner_support(no_write_candidate_generation, no_write_candidate_generation_meta)
    if runner_support is None:
        runner_support = _runner_support(candidate_generation)
    protected_start = _holdout_start(holdout)
    allowed_set = set(ALLOWED_UNIVERSE)
    non_13_rows = [
        {
            "ticker": _row_symbol(row),
            "entry_date": row.get("entry_date") or row.get("candidate_entry_date") or row.get("date"),
            "lane_id": row.get("lane_id"),
            "source_result_path": row.get("source_result_path"),
        }
        for row in _candidate_selected_rows(candidate_generation)
        if _row_symbol(row) and _row_symbol(row) not in allowed_set
    ]
    candidate_surface_ok = (
        candidate_generation_meta.get("status") == "loaded"
        and candidate_universe["frozen_universe_exact_13_symbols"]
        and not non_13_rows
        and bool(candidate_months["covered_months"])
    )

    month_diagnostics: list[dict[str, Any]] = []
    for month in requested_months:
        quote_surface_available = month in quote_months
        selected_rows = _as_list(candidate_months["selected_by_month"].get(month))
        selected_depth_rows_available = month in selected_depth_months["covered_months"]
        candidate_covered = month in candidate_months["covered_months"]
        zero_explicit = month in candidate_months["zero_selection_months"] or (
            candidate_months["zero_selection_months_explicit_global"] and candidate_covered and not selected_rows
        )
        holdout_overlap = _month_is_holdout_overlap(month, protected_start)
        statuses: list[str] = []
        if quote_surface_available:
            statuses.append("quote_surface_available")
        if candidate_covered and candidate_surface_ok and not holdout_overlap:
            statuses.append("candidate_generation_proven")
        if zero_explicit and candidate_covered and candidate_surface_ok and not holdout_overlap:
            statuses.append("explicit_zero_selection_month")
        if holdout_overlap:
            statuses.append("protected_holdout_overlap")
        if month in cvx_scope["excluded_months"]:
            statuses.append("cvx_scope_blocked")
        if runner_support["status"] != "read_only_no_write_runner_available":
            statuses.append("source_runner_unavailable")
        if not (candidate_covered and candidate_surface_ok):
            statuses.append("candidate_generation_missing")
        if quote_surface_available and not (candidate_covered and candidate_surface_ok) and not selected_rows:
            statuses.append("cannot_count_zero_selection_month")
        month_counted = bool(
            quote_surface_available
            and candidate_surface_ok
            and candidate_covered
            and not holdout_overlap
            and (selected_rows or zero_explicit or selected_depth_rows_available)
        )
        month_diagnostics.append(
            {
                "month": month,
                "quote_surface_available": quote_surface_available,
                "candidate_generation_covered": candidate_covered,
                "candidate_generation_proven": "candidate_generation_proven" in statuses,
                "explicit_zero_selection_month": "explicit_zero_selection_month" in statuses,
                "selected_trade_count": len(selected_rows),
                "selected_trade_depth_covered": selected_depth_rows_available,
                "protected_holdout_overlap": holdout_overlap,
                "month_counted_for_bounded_13_symbol_replay": month_counted,
                "statuses": statuses,
            }
        )

    blockers: list[str] = []
    blockers.extend(feature_surface["blockers"])
    if selected_trade_depth_meta.get("status") != "loaded":
        blockers.append("selected_trade_depth_artifact_not_loaded")
    if candidate_generation_meta.get("status") != "loaded":
        blockers.append("candidate_generation_artifact_not_loaded")
    if holdout_meta.get("status") != "loaded" or protected_start is None:
        blockers.append("protected_holdout_contract_not_loaded")
    if not candidate_months["covered_months"]:
        blockers.append("missing_candidate_generation_diagnostics")
    if len(candidate_months["covered_months"]) < len(requested_months):
        blockers.append(
            f"candidate_generation_months_{len(candidate_months['covered_months'])}_below_requested_{len(requested_months)}"
        )
    if not candidate_universe["frozen_universe_exact_13_symbols"]:
        blockers.append("existing_candidate_generation_surface_not_frozen_13_symbol")
    if candidate_universe["outside_allowed_universe"]:
        blockers.append("source_artifact_universe_not_13_symbol")
    if non_13_rows:
        blockers.append("non_13_symbol_selected_rows_present")
    if runner_support["status"] == "invalid_no_write_runner_support":
        blockers.append("invalid_no_write_runner_support")
    elif runner_support["status"] != "read_only_no_write_runner_available":
        blockers.append("missing_no_write_runner_support")
    if runner_support["rejected_commands"]:
        blockers.append("mutating_runner_command_rejected")
    if cvx_scope["policy_blocker"]:
        blockers.append(str(cvx_scope["policy_blocker"]))
    if any(row["protected_holdout_overlap"] for row in month_diagnostics):
        blockers.append("protected_holdout_overlap")
    if any("cannot_count_zero_selection_month" in row["statuses"] for row in month_diagnostics):
        blockers.append("quote_depth_only_months_cannot_count")
    if any(not row["month_counted_for_bounded_13_symbol_replay"] for row in month_diagnostics):
        blockers.append("not_every_requested_month_has_candidate_generation_or_explicit_no_pick_proof")
    blockers = sorted(dict.fromkeys(blockers))
    status = "ready_for_bounded_13_symbol_no_write_replay" if not blockers else "blocked_13_symbol_candidate_generation_surface_audit"
    stage_counts = Counter(status for row in month_diagnostics for status in row["statuses"])

    report: dict[str, Any] = {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "schema_version": 1,
        **READ_ONLY_FLAGS,
        "scope": "regular_options_13_symbol_candidate_generation_surface_audit",
        "inputs": {
            "feature_store_report": feature_meta,
            "selected_trade_depth": selected_trade_depth_meta,
            "candidate_generation": candidate_generation_meta,
            "no_write_candidate_generation": no_write_candidate_generation_meta,
            "source_quality_policy": policy_meta,
            "holdout_contract": holdout_meta,
        },
        "requested_window": {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "as_of_date": as_of.isoformat(),
            "requested_months": requested_months,
            "requested_month_count": len(requested_months),
        },
        "allowed_universe": list(ALLOWED_UNIVERSE),
        "feature_surface": feature_surface,
        "quote_history_vs_candidate_generation": {
            "quote_surface_months_available": sorted(month for month in requested_months if month in quote_months),
            "quote_surface_months_available_count": len([month for month in requested_months if month in quote_months]),
            "candidate_generation_months_covered": candidate_months["covered_months"],
            "candidate_generation_months_covered_count": len(candidate_months["covered_months"]),
            "selected_trade_depth_months_covered": selected_depth_months["covered_months"],
            "selected_trade_depth_months_covered_count": len(selected_depth_months["covered_months"]),
            "distinction": "quote-history coverage does not prove pick/no-pick candidate-generation coverage",
        },
        "candidate_generation_surface": {
            **candidate_universe,
            "non_13_symbol_selected_row_count": len(non_13_rows),
            "non_13_symbol_selected_rows": non_13_rows[:50],
            "candidate_surface_ok": candidate_surface_ok,
            "source_artifact_inventory": _as_list(candidate_generation.get("source_artifact_inventory")),
        },
        "cvx_scope": cvx_scope,
        "runner_support": runner_support,
        "month_diagnostics": month_diagnostics,
        "stage_status_counts": dict(sorted(stage_counts.items())),
        "blockers": blockers,
        "candidate_commands": runner_support["candidate_commands"],
        "proof_policy": {
            "readback_is": "read-only feasibility audit for a bounded 13-symbol no-write candidate-generation replay",
            "readback_is_not": "historical profitability proof, fresh forward proof, scanner implementation, quote import, evidence mutation, live validation, broker authorization, proof-bar change, or promotion",
            "minimum_ready_condition": "every requested month has point-in-time candidate-generation coverage or explicit no-pick proof on the frozen 13-symbol universe, with no holdout overlap and read-only runner hooks",
        },
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }
    return report


def _cell(value: Any) -> str:
    return ("" if value is None else str(value)).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict[str, Any]) -> str:
    window = _as_dict(report.get("requested_window"))
    comparison = _as_dict(report.get("quote_history_vs_candidate_generation"))
    feature = _as_dict(report.get("feature_surface"))
    candidate = _as_dict(report.get("candidate_generation_surface"))
    cvx = _as_dict(report.get("cvx_scope"))
    runner = _as_dict(report.get("runner_support"))
    lines = [
        "# Regular Options 13-Symbol Candidate-Generation Surface Audit",
        "",
        "This report is generated from `scripts/build_regular_options_13_symbol_candidate_generation_surface_audit.py`. It audits whether the trusted 13-symbol quote surface can honestly support a bounded no-write candidate-generation replay over the requested historical window.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Requested window: `{window.get('window_start')}` through `{window.get('window_end')}` as of `{window.get('as_of_date')}`.",
        f"- Frozen universe: `{', '.join(str(item) for item in _as_list(report.get('allowed_universe')))}`.",
        f"- Quote-surface months available: `{comparison.get('quote_surface_months_available_count')}`.",
        f"- Candidate-generation months covered: `{comparison.get('candidate_generation_months_covered_count')}`.",
        f"- Feature surface: `{feature.get('status')}`.",
        f"- Candidate surface frozen 13-symbol: `{candidate.get('frozen_universe_exact_13_symbols')}`.",
        f"- Non-13 selected rows: `{candidate.get('non_13_symbol_selected_row_count')}`.",
        f"- CVX scope enforced: `{cvx.get('cvx_scope_enforced')}` via `{cvx.get('rule_id')}`.",
        f"- Runner support: `{runner.get('status')}`.",
        "",
        "## Month Diagnostics",
        "",
        "| Month | Quote Surface | Candidate Proven | Explicit Zero | Selected | Counted | Statuses |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in _as_list(report.get("month_diagnostics")):
        row = _as_dict(row)
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(row.get('month'))}`",
                    _cell(row.get("quote_surface_available")),
                    _cell(row.get("candidate_generation_proven")),
                    _cell(row.get("explicit_zero_selection_month")),
                    _cell(row.get("selected_trade_count")),
                    _cell(row.get("month_counted_for_bounded_13_symbol_replay")),
                    _cell(", ".join(str(item) for item in _as_list(row.get("statuses")))),
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
            "A month is countable only when candidate generation, explicit no-pick proof, or selected rows are proven on the frozen 13-symbol surface. Quote-history depth alone is not a zero-selection month and cannot satisfy the 20-train plus latest-4 audit question.",
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


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the read-only 13-symbol candidate-generation surface audit.")
    parser.add_argument("--feature-store-report", type=Path, default=DEFAULT_FEATURE_STORE_REPORT)
    parser.add_argument("--selected-trade-depth", type=Path, default=DEFAULT_SELECTED_TRADE_DEPTH)
    parser.add_argument("--candidate-generation", type=Path, default=DEFAULT_CANDIDATE_GENERATION)
    parser.add_argument("--no-write-candidate-generation", type=Path, default=DEFAULT_NO_WRITE_CANDIDATE_GENERATION)
    parser.add_argument("--source-quality-policy", type=Path, default=DEFAULT_SOURCE_QUALITY_POLICY)
    parser.add_argument("--holdout-contract", type=Path, default=DEFAULT_HOLDOUT_CONTRACT)
    parser.add_argument("--window-start", default=DEFAULT_WINDOW_START)
    parser.add_argument("--window-end", default=DEFAULT_WINDOW_END)
    parser.add_argument("--as-of-date", default=DEFAULT_AS_OF_DATE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(list(argv))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(
        feature_store_report_path=args.feature_store_report,
        selected_trade_depth_path=args.selected_trade_depth,
        candidate_generation_path=args.candidate_generation,
        no_write_candidate_generation_path=args.no_write_candidate_generation,
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
