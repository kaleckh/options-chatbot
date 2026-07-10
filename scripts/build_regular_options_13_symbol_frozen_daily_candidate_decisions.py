from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Sequence
from zoneinfo import ZoneInfo


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
    "unavailable end-to-end no-write production scanner replay: signatures and historical provider support exist, "
    "but candidate_generation_date, as_of_date, lane_id, symbol decisions are not emitted by the production scanner"
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
DEFAULT_CANDIDATE_MATERIALIZATION_BASIS = "deterministic_local_pit_candidate_materializer_v1"
ENTRY_START_MINUTE = 10 * 60 + 10
EASTERN = ZoneInfo("America/New_York")


def _source_non_parity(source: dict[str, Any] | None) -> dict[str, Any]:
    source_data = _as_dict(source)
    return {
        "candidate_materialization_basis": str(
            source_data.get("candidate_materialization_basis") or DEFAULT_CANDIDATE_MATERIALIZATION_BASIS
        ),
        "scanner_parity": bool(source_data.get("scanner_parity")) if "scanner_parity" in source_data else False,
        "production_scanner_replay": bool(source_data.get("production_scanner_replay"))
        if "production_scanner_replay" in source_data
        else False,
    }


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _et_minute_to_utc_iso(day: date, minute_et: int = ENTRY_START_MINUTE) -> str:
    hour, minute = divmod(int(minute_et), 60)
    localized = datetime(day.year, day.month, day.day, hour, minute, tzinfo=EASTERN)
    return localized.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _latest_utc_timestamp(*values: Any) -> str | None:
    parsed: list[datetime] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        try:
            item = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            continue
        if item.tzinfo is None:
            item = item.replace(tzinfo=UTC)
        parsed.append(item.astimezone(UTC))
    if not parsed:
        return None
    return max(parsed).isoformat(timespec="seconds").replace("+00:00", "Z")


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
    signature_support_available = bool(run_has_date and scan_has_date)
    try:
        scanner_source = (ROOT / "options_chatbot.py").read_text(encoding="utf8")
    except OSError:
        scanner_source = ""
    observed_no_write_empty_short_circuit = bool(
        "no_write_scan_blocks_provider_fetches" in scanner_source and "return []" in scanner_source
    )
    adapter_available = False
    return {
        "adapter_available": adapter_available,
        "signature_support_available": signature_support_available,
        "end_to_end_no_write_scanner_replay_available": False,
        "observed_no_write_empty_short_circuit": observed_no_write_empty_short_circuit,
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
        "decision": "end_to_end_no_write_scanner_replay_unavailable",
        "missing_command": MISSING_COMMAND,
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
    non_parity = _source_non_parity(source)
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
                source_research_materializer_safe = bool(
                    source_proof_safe or source_row.get("research_materializer_safe") is True
                )
                if source_integrity_blockers:
                    status = "blocked_source_artifact_not_exact_frozen_daily_decision_source"
                    source_proof_safe = False
                    source_research_materializer_safe = False
                elif status not in ACCEPTED_STATUSES and not status.startswith("blocked_"):
                    status = "blocked_unsupported_daily_candidate_decision_status"
                    row_blockers.append("unsupported_daily_candidate_decision_status")
                elif status in ACCEPTED_STATUSES and not source_research_materializer_safe:
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
                source_research_materializer_safe = False

            fallback_timestamp = _et_minute_to_utc_iso(current_date)
            source_signal = _as_dict(source_row.get("signal_evidence")) if source_row else {}
            entry_quote_timestamp = _latest_utc_timestamp(
                source_row.get("entry_quote_timestamp_utc") if source_row else None,
                source_row.get("entry_quote_as_of_utc") if source_row else None,
                source_row.get("long_entry_quote_timestamp_utc") if source_row else None,
                source_row.get("long_entry_quote_as_of_utc") if source_row else None,
                source_row.get("short_entry_quote_timestamp_utc") if source_row else None,
                source_row.get("short_entry_quote_as_of_utc") if source_row else None,
            )
            known_at = (
                str(source_row.get("known_at") or source_signal.get("known_at_utc") or "")
                if source_row
                else ""
            ) or fallback_timestamp
            tradable_after = (
                str(source_row.get("tradable_after") or "") if source_row else ""
            ) or entry_quote_timestamp or fallback_timestamp
            decision_timestamp = (
                str(source_row.get("decision_timestamp_utc") or "") if source_row else ""
            ) or tradable_after
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
                "research_materializer_safe": bool(
                    status in ACCEPTED_STATUSES and source_research_materializer_safe
                ),
                "known_at": known_at,
                "tradable_after": tradable_after,
                "decision_timestamp_utc": decision_timestamp,
                "as_of_date": as_of.isoformat(),
                "read_only": True,
                "no_write": True,
                "accepted_profitability": False,
                "historical_rows_are_forward_proof": False,
                **non_parity,
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
                    "research_materializer_safe": bool(
                        status in ACCEPTED_STATUSES and source_research_materializer_safe
                    ),
                    **non_parity,
                },
                "blockers": sorted(dict.fromkeys(row_blockers)),
            }
            if source_row and status in ACCEPTED_STATUSES:
                for payload_key in (
                    "entry_date",
                    "exit_date",
                    "ticker",
                    "symbol",
                    "lane_family",
                    "direction",
                    "strategy_type",
                    "entry_contract_resolution",
                    "fill_basis",
                    "proof_grade",
                    "quote_source",
                    "exact_priced",
                    "pnl_pct",
                    "gross_pnl_pct",
                    "net_pnl_pct",
                    "contract_multiplier",
                    "fee_per_contract_leg_usd",
                    "total_fees_usd",
                    "gross_pnl_usd",
                    "net_pnl_usd",
                    "net_pnl_pct_after_fees",
                    "exit_value_floored_at_zero",
                    "dedupe_key",
                    "portfolio_eligible",
                    "source_result_path",
                    "long_contract_symbol",
                    "short_contract_symbol",
                    "expiry",
                    "dte",
                    "spread_width",
                    "entry_debit",
                    "net_debit",
                    "debit_pct_of_width",
                    "exit_reason",
                    "exit_value",
                    "exit_px",
                    "exit_pricing_status",
                    "long_entry_bid",
                    "long_entry_ask",
                    "short_entry_bid",
                    "short_entry_ask",
                    "entry_quote_minute_et",
                    "entry_quote_as_of_utc",
                    "entry_quote_timestamp_utc",
                    "long_entry_quote_minute_et",
                    "short_entry_quote_minute_et",
                    "long_entry_quote_as_of_utc",
                    "short_entry_quote_as_of_utc",
                    "long_entry_quote_timestamp_utc",
                    "short_entry_quote_timestamp_utc",
                    "long_exit_bid",
                    "long_exit_ask",
                    "short_exit_bid",
                    "short_exit_ask",
                    "exit_quote_minute_et",
                    "exit_quote_as_of_utc",
                    "exit_quote_timestamp_utc",
                    "long_exit_quote_minute_et",
                    "short_exit_quote_minute_et",
                    "long_exit_quote_as_of_utc",
                    "short_exit_quote_as_of_utc",
                    "long_exit_quote_timestamp_utc",
                    "short_exit_quote_timestamp_utc",
                    "policy_exit_target_date",
                    "exit_calendar_observable_through_date",
                    "exit_calendar_latest_available_date",
                    "exit_right_censored",
                    "exit_right_censor_reason",
                    "exit_evidence_blocker",
                    "exit_price_lineage_status",
                    "exit_price_lineage",
                    "signal_evidence",
                    "no_pick_reason",
                ):
                    if payload_key in source_row:
                        row[payload_key] = source_row.get(payload_key)
                row.update(
                    {
                        "row_id": f"{REPORT_ID}:{current_date.isoformat()}:{lane}:{symbol}",
                        "date": current_date.isoformat(),
                        "candidate_generation_date": current_date.isoformat(),
                        "month": current_date.isoformat()[:7],
                        "lane": lane,
                        "lane_id": lane,
                        "underlying": symbol,
                        "ticker": symbol,
                        "status": status,
                        "selected_candidate": status == "selected_candidate",
                        "explicit_no_pick": status == "explicit_no_pick",
                        "proof_safe": bool(status in ACCEPTED_STATUSES and source_proof_safe),
                        "research_materializer_safe": bool(
                            status in ACCEPTED_STATUSES and source_research_materializer_safe
                        ),
                        "blockers": sorted(dict.fromkeys(row_blockers)),
                    }
                )
                if row.get("net_pnl_pct_after_fees") not in (None, ""):
                    if row.get("net_pnl_pct") != row.get("net_pnl_pct_after_fees"):
                        row["legacy_net_pnl_pct"] = row.get("net_pnl_pct")
                    row["net_pnl_pct"] = row.get("net_pnl_pct_after_fees")
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
    daily_rows, selected, materializer_blockers = _build_rows(
        market_dates=dates,
        pairs=pairs,
        as_of=as_of,
        scanner_surface=scanner_surface,
        source=source,
        source_meta=source_meta,
        source_integrity=source_integrity,
    )
    if cohort_meta.get("status") != "loaded":
        materializer_blockers.append("forward_cohort_preregistration_not_loaded")
    if feature_meta.get("status") != "loaded":
        materializer_blockers.append("feature_store_not_loaded")
    if not dates:
        materializer_blockers.append("market_date_denominator_missing")
    if not pairs:
        materializer_blockers.append("forward_cohort_lane_symbol_pairs_missing")
    requested_months = _month_range(start, end)
    coverage = _coverage(daily_rows, requested_months)
    if coverage["calendar_months_covered_count"] < len(requested_months):
        materializer_blockers.append(
            f"candidate_generation_months_{coverage['calendar_months_covered_count']}_below_requested_{len(requested_months)}"
        )
    materializer_blockers = sorted(dict.fromkeys(materializer_blockers))
    source_blockers = [str(item) for item in _as_list(_as_dict(source).get("blockers"))]
    proof_or_nomination_blockers = [
        str(item) for item in _as_list(_as_dict(source).get("proof_or_nomination_blockers"))
    ]
    blockers = sorted(dict.fromkeys([*materializer_blockers, *source_blockers, *proof_or_nomination_blockers]))
    research_materializer_ready = not materializer_blockers
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
        "no_write": bool(no_write),
        "source_data_no_write": True,
        "report_artifact_write_requested": not bool(no_write),
        "report_artifact_write_performed": False,
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
        "candidate_materialization_basis": _source_non_parity(source).get("candidate_materialization_basis"),
        "research_materializer_status": (
            "research_materializer_ready" if research_materializer_ready else "blocked_research_materializer"
        ),
        "research_materializer_ready": research_materializer_ready,
        "research_materializer_blockers": materializer_blockers,
        "scanner_parity": _source_non_parity(source).get("scanner_parity"),
        "production_scanner_replay": _source_non_parity(source).get("production_scanner_replay"),
        "production_parity_mismatches": _as_list(_as_dict(source).get("production_parity_mismatches")),
        "historical_selection_conditioning": _as_dict(
            _as_dict(source).get("historical_selection_conditioning")
        ),
        "proof_or_nomination_blockers": sorted(dict.fromkeys(proof_or_nomination_blockers)),
        "source_artifact_inventory": [
            {
                "artifact": "existing_scanner_surface",
                "proof_safe": False,
                "reason": scanner_surface.get("decision"),
                "missing_command": scanner_surface.get("missing_command"),
                "inspected_callables": scanner_surface.get("inspected_callables"),
                **_source_non_parity(source),
            }
        ],
        "calendar_coverage": {
            "status": (
                "research_materializer_calendar_coverage_proven"
                if research_materializer_ready
                else "research_materializer_calendar_coverage_blocked"
            ),
            "coverage_basis": "research_materializer_safe_daily_selected_or_explicit_no_pick_rows_only",
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
        if materializer_blockers
        else [],
        "proof_policy": {
            "readback_is": "read-only frozen daily candidate/no-pick/blocker source materializer",
            "readback_is_not": "profitability proof, fresh forward proof, quote import, evidence mutation, live validation, auto-track, broker permission, proof-bar change, scanner policy change, or promotion",
            "pass_condition": "each frozen market-date/lane/symbol row is selected_candidate or explicit_no_pick from a research-materializer-safe point-in-time source",
            "proof_separation": "research rows may flow while proof_safe and production_scanner_replay remain false and nomination blockers remain global",
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
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            f"- Candidate materialization basis: `{report.get('candidate_materialization_basis')}`.",
            f"- Scanner parity: `{report.get('scanner_parity')}`.",
            f"- Production scanner replay: `{report.get('production_scanner_replay')}`.",
            "",
            "No rows are fabricated, broad-source rows are not post-hoc filtered into proof, and scanner policy is unchanged.",
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
    report["no_write"] = False
    report["report_artifact_write_requested"] = True
    report["report_artifact_write_performed"] = True
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
