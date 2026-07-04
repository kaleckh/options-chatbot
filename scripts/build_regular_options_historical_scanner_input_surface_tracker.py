from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from contextlib import closing
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
from scripts.build_regular_options_13_symbol_frozen_candidate_generation_engine import _market_dates  # noqa: E402
from scripts.build_regular_options_robust_search_evaluation import _load_json  # noqa: E402


REPORT_ID = "regular_options_historical_scanner_input_surface_tracker"
DEFAULT_FEATURE_STORE = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_MARKET_REGIME_INPUTS = (
    ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-market-regime-inputs" / "latest.json"
)
DEFAULT_VIX_BUCKET = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-vix-bucket" / "latest.json"
DEFAULT_UNDERLYING_DAILY_SOURCE_ROWS = (
    ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-underlying-daily-history" / "source_rows.jsonl"
)
DEFAULT_ALPACA_MINUTE_SOURCE_ROWS = (
    ROOT / "data" / "profitability-lab" / "regular-options-alpaca-underlying-minute-price-surface" / "source_rows.jsonl"
)
DEFAULT_EARNINGS_CALENDAR = (
    ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-earnings-calendar" / "latest.json"
)
DEFAULT_FROZEN_ADAPTER = (
    ROOT / "data" / "profitability-lab" / "regular-options-historical-frozen-scanner-replay-adapter" / "latest.json"
)
DEFAULT_FROZEN_ENGINE = (
    ROOT / "data" / "profitability-lab" / "regular-options-13-symbol-frozen-candidate-generation-engine" / "latest.json"
)
DEFAULT_OPTIONS_HISTORY_DB = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_OUTPUT_DIR = (
    ROOT / "data" / "profitability-lab" / "regular-options-historical-scanner-input-surface-tracker"
)
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-historical-scanner-input-surface-tracker.md"

THETADATA_SOURCE_LABEL = "thetadata_opra_nbbo_1m"
ENTRY_QUOTE_MINUTE_ET = 10 * 60 + 10
ENTRY_QUOTE_WINDOW_MINUTES = 15
ALPACA_ENTRY_MINUTE_START = 9 * 60 + 35
ALPACA_ENTRY_MINUTE_END = 10 * 60 + 45
MIN_DTE = 5
MAX_DTE = 35
ETF_OR_INDEX_SYMBOLS = {"SPY", "QQQ", "IWM", "DIA"}

FALSE_FLAGS = {
    "read_only": True,
    "research_only": True,
    "accepted_profitability": False,
    "historical_replay_performed": False,
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
    "external_market_data_fetch",
    "options_history_db_mutation",
    "market_data_db_mutation",
    "evidence_store_mutation",
    "forward_cohort_append",
    "protected_holdout_consumption",
    "promotion",
    "using_current_latest_data_for_historical_candidate_dates",
    "using_pnl_outcomes_winners_or_exits_to_decide_candidates",
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


def _requested_pairs(market_dates: Sequence[date], symbols: Sequence[str]) -> set[tuple[str, str]]:
    return {(day.isoformat(), str(symbol).upper()) for day in market_dates for symbol in symbols}


def _coverage_summary(
    *,
    requested_pairs: set[tuple[str, str]],
    covered_pairs: set[tuple[str, str]],
    requested_months: Sequence[str],
    symbols: Sequence[str],
) -> dict[str, Any]:
    covered = requested_pairs & covered_pairs
    missing = sorted(requested_pairs - covered_pairs)
    missing_by_symbol = Counter(symbol for _day, symbol in missing)
    covered_months: list[str] = []
    for month in requested_months:
        month_pairs = {pair for pair in requested_pairs if pair[0].startswith(f"{month}-")}
        if month_pairs and month_pairs <= covered_pairs:
            covered_months.append(month)
    pct = round((len(covered) / len(requested_pairs) * 100.0), 4) if requested_pairs else 0.0
    return {
        "requested_symbol_date_count": len(requested_pairs),
        "covered_symbol_date_count": len(covered),
        "coverage_pct": pct,
        "requested_symbols": list(symbols),
        "covered_months": covered_months,
        "covered_month_count": len(covered_months),
        "requested_months": list(requested_months),
        "requested_month_count": len(requested_months),
        "missing_symbol_date_count": len(missing),
        "missing_symbol_date_examples": [f"{day}:{symbol}" for day, symbol in missing[:20]],
        "missing_by_symbol": dict(sorted(missing_by_symbol.items())),
        "ready": bool(requested_pairs and requested_pairs <= covered_pairs),
    }


def _jsonl_pair_coverage(
    path: Path,
    *,
    date_field: str,
    symbol_field: str,
    requested_pairs: set[tuple[str, str]],
    minute_field: str | None = None,
    minute_start: int | None = None,
    minute_end: int | None = None,
) -> tuple[set[tuple[str, str]], dict[str, Any]]:
    meta = {"path": _rel(path), "exists": path.exists(), "status": "missing", "rows_read": 0, "malformed_rows": 0}
    if not path.exists():
        return set(), meta
    covered: set[tuple[str, str]] = set()
    try:
        with path.open("r", encoding="utf8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                meta["rows_read"] += 1
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    meta["malformed_rows"] += 1
                    continue
                if not isinstance(row, dict):
                    continue
                if row.get("point_in_time_valid") is not True:
                    continue
                if minute_field:
                    try:
                        minute = int(row.get(minute_field))
                    except (TypeError, ValueError):
                        continue
                    if minute_start is not None and minute < minute_start:
                        continue
                    if minute_end is not None and minute > minute_end:
                        continue
                pair = (str(row.get(date_field) or "")[:10], str(row.get(symbol_field) or "").upper())
                if pair in requested_pairs:
                    covered.add(pair)
    except OSError as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return covered, meta
    meta["status"] = "loaded"
    return covered, meta


def _option_chain_pair_coverage(
    db_path: Path,
    *,
    requested_pairs: set[tuple[str, str]],
    symbols: Sequence[str],
    start: date,
    end: date,
    source_label: str,
    min_dte: int,
    max_dte: int,
    quote_minute: int,
    quote_window_minutes: int,
) -> tuple[set[tuple[str, str]], dict[str, Any]]:
    meta: dict[str, Any] = {
        "path": _rel(db_path),
        "exists": db_path.exists(),
        "status": "missing",
        "source_label": source_label,
        "data_trust": "trusted",
        "snapshot_kind": "intraday",
        "quote_minute_window_et": {
            "start": int(quote_minute - quote_window_minutes),
            "end": int(quote_minute + quote_window_minutes),
        },
        "dte_window": {"min": int(min_dte), "max": int(max_dte)},
    }
    if not db_path.exists():
        return set(), meta
    if not symbols:
        meta["status"] = "empty_universe"
        return set(), meta
    placeholders = ", ".join("?" for _ in symbols)
    params: list[Any] = [
        *[str(symbol).upper() for symbol in symbols],
        start.isoformat(),
        end.isoformat(),
        int(quote_minute - quote_window_minutes),
        int(quote_minute + quote_window_minutes),
        source_label,
        int(min_dte),
        int(max_dte),
    ]
    query = f"""
        SELECT
            q.quote_date_et AS quote_date_et,
            q.underlying AS underlying,
            COUNT(*) AS row_count,
            COUNT(DISTINCT q.expiry) AS expiry_count,
            SUM(CASE WHEN LOWER(q.option_type) = 'call' THEN 1 ELSE 0 END) AS call_rows,
            SUM(CASE WHEN LOWER(q.option_type) = 'put' THEN 1 ELSE 0 END) AS put_rows,
            SUM(CASE WHEN q.bid IS NOT NULL AND q.ask IS NOT NULL THEN 1 ELSE 0 END) AS bidask_rows,
            SUM(CASE WHEN q.underlying_price IS NOT NULL THEN 1 ELSE 0 END) AS underlying_price_rows,
            MIN(q.quote_minute_et) AS min_quote_minute_et,
            MAX(q.quote_minute_et) AS max_quote_minute_et
        FROM option_quote_snapshots q INDEXED BY idx_option_quotes_underlying_date
        JOIN import_batches b ON b.id = q.source_batch_id
        WHERE q.underlying IN ({placeholders})
          AND q.snapshot_kind = 'intraday'
          AND q.quote_date_et BETWEEN ? AND ?
          AND q.quote_minute_et BETWEEN ? AND ?
          AND b.source_label = ?
          AND b.data_trust = 'trusted'
          AND (julianday(q.expiry) - julianday(q.quote_date_et)) BETWEEN ? AND ?
        GROUP BY q.quote_date_et, q.underlying
    """
    covered: set[tuple[str, str]] = set()
    underlying_price_pairs: set[tuple[str, str]] = set()
    row_count = 0
    try:
        with closing(sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True, timeout=30.0)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
    except sqlite3.Error as exc:
        meta["status"] = "sqlite_error"
        meta["error"] = f"{type(exc).__name__}: {exc}"
        return covered, meta
    for row in rows:
        pair = (str(row["quote_date_et"]), str(row["underlying"]).upper())
        if pair not in requested_pairs:
            continue
        row_count += int(row["row_count"] or 0)
        if int(row["bidask_rows"] or 0) > 0 and int(row["call_rows"] or 0) > 0 and int(row["expiry_count"] or 0) > 0:
            covered.add(pair)
        if int(row["underlying_price_rows"] or 0) > 0:
            underlying_price_pairs.add(pair)
    meta["status"] = "loaded"
    meta["aggregated_symbol_date_rows"] = len(rows)
    meta["trusted_quote_rows_in_scope"] = row_count
    meta["underlying_price_symbol_date_count"] = len(underlying_price_pairs)
    return covered, meta


def _artifact_ready(payload: dict[str, Any], meta: dict[str, Any], *, expected_status: str | None = None, flag: str | None = None) -> bool:
    if meta.get("status") != "loaded":
        return False
    if expected_status and payload.get("status") != expected_status:
        return False
    if flag and payload.get(flag) is not True:
        return False
    return not _as_list(payload.get("blockers"))


def build_report(
    *,
    feature_store_path: Path = DEFAULT_FEATURE_STORE,
    market_regime_inputs_path: Path = DEFAULT_MARKET_REGIME_INPUTS,
    vix_bucket_path: Path = DEFAULT_VIX_BUCKET,
    underlying_daily_source_rows_path: Path = DEFAULT_UNDERLYING_DAILY_SOURCE_ROWS,
    alpaca_minute_source_rows_path: Path = DEFAULT_ALPACA_MINUTE_SOURCE_ROWS,
    earnings_calendar_path: Path = DEFAULT_EARNINGS_CALENDAR,
    frozen_adapter_path: Path = DEFAULT_FROZEN_ADAPTER,
    frozen_engine_path: Path = DEFAULT_FROZEN_ENGINE,
    options_history_db_path: Path = DEFAULT_OPTIONS_HISTORY_DB,
    window_start: str = DEFAULT_WINDOW_START,
    window_end: str = DEFAULT_WINDOW_END,
    as_of_date: str = DEFAULT_AS_OF_DATE,
    universe: Sequence[str] = ALLOWED_UNIVERSE,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    start = _parse_date(window_start)
    end = _parse_date(window_end)
    as_of = _parse_date(as_of_date)
    symbols = _parse_universe(universe)
    if start is None or end is None or as_of is None or end < start:
        raise ValueError("start-date, end-date, and as-of-date must be valid YYYY-MM-DD values with start <= end")
    if symbols != ALLOWED_UNIVERSE:
        raise ValueError("universe must exactly match the frozen 13-symbol universe")

    feature_store, feature_meta = _load_json(feature_store_path)
    market_regime, market_regime_meta = _load_json(market_regime_inputs_path)
    vix_bucket, vix_meta = _load_json(vix_bucket_path)
    earnings_calendar, earnings_calendar_meta = _load_json(earnings_calendar_path)
    frozen_adapter, frozen_adapter_meta = _load_json(frozen_adapter_path)
    frozen_engine, frozen_engine_meta = _load_json(frozen_engine_path)
    market_dates = _market_dates(feature_store, start, end)
    requested_months = _month_range(start, end)
    pairs = _requested_pairs(market_dates, symbols)

    daily_pairs, daily_meta = _jsonl_pair_coverage(
        underlying_daily_source_rows_path,
        date_field="input_date_et",
        symbol_field="symbol",
        requested_pairs=pairs,
    )
    minute_pairs, minute_meta = _jsonl_pair_coverage(
        alpaca_minute_source_rows_path,
        date_field="price_date_et",
        symbol_field="underlying",
        requested_pairs=pairs,
        minute_field="price_minute_et",
        minute_start=ALPACA_ENTRY_MINUTE_START,
        minute_end=ALPACA_ENTRY_MINUTE_END,
    )
    chain_pairs, chain_meta = _option_chain_pair_coverage(
        options_history_db_path,
        requested_pairs=pairs,
        symbols=symbols,
        start=start,
        end=end,
        source_label=THETADATA_SOURCE_LABEL,
        min_dte=MIN_DTE,
        max_dte=MAX_DTE,
        quote_minute=ENTRY_QUOTE_MINUTE_ET,
        quote_window_minutes=ENTRY_QUOTE_WINDOW_MINUTES,
    )

    market_regime_ready = _artifact_ready(
        market_regime,
        market_regime_meta,
        expected_status="point_in_time_market_regime_inputs_ready",
        flag="point_in_time_market_regime_inputs_available",
    )
    vix_ready = _artifact_ready(vix_bucket, vix_meta, expected_status="point_in_time_vix_bucket_ready")
    earnings_window = _as_dict(earnings_calendar.get("requested_window"))
    earnings_ready = bool(
        earnings_calendar_meta.get("status") == "loaded"
        and earnings_calendar.get("status") == "point_in_time_earnings_calendar_ready"
        and not _as_list(earnings_calendar.get("blockers"))
        and earnings_window.get("window_start") == start.isoformat()
        and earnings_window.get("window_end") == end.isoformat()
    )
    deterministic_materializer_ready = bool(
        frozen_adapter_meta.get("status") == "loaded"
        and frozen_adapter.get("status") == "historical_frozen_scanner_replay_adapter_ready"
        and not _as_list(frozen_adapter.get("blockers"))
        and frozen_engine_meta.get("status") == "loaded"
        and frozen_engine.get("status") == "frozen_13_symbol_candidate_generation_engine_ready"
        and not _as_list(frozen_engine.get("blockers"))
        and frozen_adapter.get("candidate_materialization_basis") == "deterministic_local_pit_candidate_materializer_v1"
        and frozen_engine.get("candidate_materialization_basis") == "deterministic_local_pit_candidate_materializer_v1"
        and frozen_adapter.get("scanner_parity") is False
        and frozen_engine.get("scanner_parity") is False
    )
    daily_summary = _coverage_summary(
        requested_pairs=pairs,
        covered_pairs=daily_pairs,
        requested_months=requested_months,
        symbols=symbols,
    )
    minute_summary = _coverage_summary(
        requested_pairs=pairs,
        covered_pairs=minute_pairs,
        requested_months=requested_months,
        symbols=symbols,
    )
    chain_summary = _coverage_summary(
        requested_pairs=pairs,
        covered_pairs=chain_pairs,
        requested_months=requested_months,
        symbols=symbols,
    )
    equity_pairs = {(day, symbol) for day, symbol in pairs if symbol not in ETF_OR_INDEX_SYMBOLS}

    blockers: list[str] = []
    if feature_meta.get("status") != "loaded":
        blockers.append("feature_store_not_loaded")
    if not market_dates:
        blockers.append("market_date_denominator_missing")
    if not market_regime_ready:
        blockers.append("missing_point_in_time_market_regime_inputs")
    if not daily_summary["ready"]:
        blockers.append("missing_point_in_time_underlying_daily_feature_source_rows")
    if not vix_ready:
        blockers.append("missing_point_in_time_vix_source")
    if not minute_summary["ready"]:
        blockers.append("missing_historical_entry_underlying_price_surface")
    if not chain_summary["ready"]:
        blockers.append("missing_historical_option_chain_selection_surface")
    if equity_pairs and not earnings_ready:
        blockers.append("missing_point_in_time_earnings_calendar_source")
    if not deterministic_materializer_ready:
        blockers.extend(
            [
                "missing_lane_specific_point_in_time_feature_inputs",
                "missing_daily_candidate_generation_diagnostics",
                "missing_historical_candidate_decision_replay_execution",
            ]
        )
    blockers = sorted(dict.fromkeys(blockers))

    surface_readiness = {
        "feature_store_denominator": {
            "available": feature_meta.get("status") == "loaded" and bool(market_dates),
            "meta": feature_meta,
            "requested_market_date_count": len(market_dates),
        },
        "market_regime_inputs": {
            "available": market_regime_ready,
            "meta": market_regime_meta,
            "status": market_regime.get("status"),
            "blockers": _as_list(market_regime.get("blockers")),
        },
        "underlying_daily_feature_source_rows": {
            "available": bool(daily_summary["ready"]),
            "meta": daily_meta,
            **daily_summary,
        },
        "vix_bucket": {
            "available": vix_ready,
            "meta": vix_meta,
            "status": vix_bucket.get("status"),
            "blockers": _as_list(vix_bucket.get("blockers")),
        },
        "entry_underlying_price_surface": {
            "available": bool(minute_summary["ready"]),
            "source": "alpaca_sip_underlying_minute_price_v1",
            "minute_window_et": {"start": ALPACA_ENTRY_MINUTE_START, "end": ALPACA_ENTRY_MINUTE_END},
            "meta": minute_meta,
            **minute_summary,
        },
        "option_chain_selection_surface": {
            "available": bool(chain_summary["ready"]),
            "source": THETADATA_SOURCE_LABEL,
            "selection_rule": "trusted intraday bid/ask call rows in the scanner entry quote window with 5-35 DTE",
            "meta": chain_meta,
            **chain_summary,
        },
        "earnings_calendar": {
            "available": earnings_ready,
            "required_equity_symbol_date_count": len(equity_pairs),
            "status": earnings_calendar.get("status") or "missing_point_in_time_earnings_calendar_source",
            "meta": earnings_calendar_meta,
            "covered_equity_symbols": _as_list(earnings_calendar.get("covered_equity_symbols")),
            "missing_equity_symbols": _as_list(earnings_calendar.get("missing_equity_symbols")),
        },
        "lane_specific_feature_inputs": {
            "available": deterministic_materializer_ready,
            "status": "deterministic_materializer_inputs_ready" if deterministic_materializer_ready else "missing_lane_specific_point_in_time_feature_inputs",
            "availability_basis": "deterministic_local_pit_candidate_materializer_v1" if deterministic_materializer_ready else None,
            "production_scanner_parity": False,
            "required": [
                "scanner RSI/tech score inputs",
                "scanner liquidity snapshot inputs",
                "lane-specific momentum/breadth/regime gates beyond base market regime",
            ],
        },
        "candidate_decision_replay_execution": {
            "available": deterministic_materializer_ready,
            "status": "deterministic_candidate_decision_materialization_ready" if deterministic_materializer_ready else "missing_historical_candidate_decision_replay_execution",
            "required": "a no-write replay that consumes these point-in-time surfaces and emits selected_candidate or explicit_no_pick rows",
            "adapter": frozen_adapter_meta,
            "engine": frozen_engine_meta,
            "candidate_materialization_basis": frozen_engine.get("candidate_materialization_basis"),
            "production_scanner_parity": bool(frozen_engine.get("production_scanner_replay")),
        },
    }

    paid_source_summary = {
        "alpaca_daily_underlying_source_rows_ready": bool(daily_summary["ready"]),
        "alpaca_entry_minute_surface_ready": bool(minute_summary["ready"]),
        "thetadata_entry_window_option_chain_surface_ready": bool(chain_summary["ready"]),
        "direct_vix_ready": vix_ready,
        "earnings_calendar_ready": earnings_ready,
        "deterministic_materializer_ready": deterministic_materializer_ready,
        "paid_sources_can_clear_all_current_historical_scanner_input_blockers": bool(
            daily_summary["ready"]
            and minute_summary["ready"]
            and chain_summary["ready"]
            and vix_ready
            and earnings_ready
            and deterministic_materializer_ready
        ),
    }
    status = "historical_scanner_input_surfaces_ready" if not blockers else "blocked_historical_scanner_input_surfaces"
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "schema_version": 1,
        **FALSE_FLAGS,
        "scope": "daily_read_only_historical_scanner_input_surface_tracking_for_frozen_13_symbol_audit",
        "requested_window": {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "as_of_date": as_of.isoformat(),
            "requested_months": requested_months,
            "requested_month_count": len(requested_months),
            "market_date_count": len(market_dates),
            "symbol_count": len(symbols),
            "symbol_date_count": len(pairs),
        },
        "universe": list(symbols),
        "inputs": {
            "feature_store": feature_meta,
            "market_regime_inputs": market_regime_meta,
            "vix_bucket": vix_meta,
            "earnings_calendar": earnings_calendar_meta,
            "frozen_adapter": frozen_adapter_meta,
            "frozen_engine": frozen_engine_meta,
            "underlying_daily_source_rows": daily_meta,
            "alpaca_minute_source_rows": minute_meta,
            "options_history_db": chain_meta,
        },
        "surface_readiness": surface_readiness,
        "paid_source_summary": paid_source_summary,
        "daily_tracking": {
            "wired_into_daily_ops": True,
            "daily_ops_step_id": "historical_scanner_input_surface_tracker",
            "recommended_command": "npm run options:research:historical-scanner-input-surface-tracker -- --json",
            "read_only_safe": True,
        },
        "blockers": blockers,
        "smallest_next_blocker_clearing_slice": blockers[0] if blockers else None,
        "forbidden_actions": FORBIDDEN_ACTIONS,
    }


def render_markdown(report: dict[str, Any]) -> str:
    window = _as_dict(report.get("requested_window"))
    surfaces = _as_dict(report.get("surface_readiness"))
    lines = [
        "# Regular Options Historical Scanner Input Surface Tracker",
        "",
        "This generated artifact tracks whether the paid/local source surfaces needed for the frozen 13-symbol historical candidate replay are materialized. It is read-only and does not replay candidates.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Window: `{window.get('window_start')}` through `{window.get('window_end')}` as of `{window.get('as_of_date')}`.",
        f"- Symbol-dates: `{window.get('symbol_date_count')}`.",
        f"- Smallest next blocker: `{report.get('smallest_next_blocker_clearing_slice')}`.",
        "",
        "## Surfaces",
        "",
        "| Surface | Available | Coverage |",
        "|---|---:|---:|",
    ]
    for key, surface in surfaces.items():
        data = _as_dict(surface)
        coverage = data.get("coverage_pct")
        coverage_text = "" if coverage is None else f"`{coverage}%`"
        lines.append(f"| `{key}` | `{str(bool(data.get('available'))).lower()}` | {coverage_text} |")
    if blockers := _as_list(report.get("blockers")):
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "The tracker reads generated source rows and trusted local ThetaData rows. It does not fetch market data, import quotes, mutate evidence stores, call the scanner, append cohorts, enable live validation, enable auto-track, submit broker orders, lower proof bars, consume protected holdout, or promote any lane.",
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
    parser = argparse.ArgumentParser(description="Track historical scanner input surface coverage for the frozen 13-symbol audit.")
    parser.add_argument("--source-feature-store", "--feature-store", type=Path, default=DEFAULT_FEATURE_STORE)
    parser.add_argument("--market-regime-inputs", type=Path, default=DEFAULT_MARKET_REGIME_INPUTS)
    parser.add_argument("--vix-bucket", type=Path, default=DEFAULT_VIX_BUCKET)
    parser.add_argument("--underlying-daily-source-rows", type=Path, default=DEFAULT_UNDERLYING_DAILY_SOURCE_ROWS)
    parser.add_argument("--alpaca-minute-source-rows", type=Path, default=DEFAULT_ALPACA_MINUTE_SOURCE_ROWS)
    parser.add_argument("--earnings-calendar", type=Path, default=DEFAULT_EARNINGS_CALENDAR)
    parser.add_argument("--frozen-adapter", type=Path, default=DEFAULT_FROZEN_ADAPTER)
    parser.add_argument("--frozen-engine", type=Path, default=DEFAULT_FROZEN_ENGINE)
    parser.add_argument("--options-history-db", type=Path, default=DEFAULT_OPTIONS_HISTORY_DB)
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
        market_regime_inputs_path=args.market_regime_inputs,
        vix_bucket_path=args.vix_bucket,
        underlying_daily_source_rows_path=args.underlying_daily_source_rows,
        alpaca_minute_source_rows_path=args.alpaca_minute_source_rows,
        earnings_calendar_path=args.earnings_calendar,
        frozen_adapter_path=args.frozen_adapter,
        frozen_engine_path=args.frozen_engine,
        options_history_db_path=args.options_history_db,
        window_start=args.start_date,
        window_end=args.end_date,
        as_of_date=args.as_of_date,
        universe=_parse_universe(args.universe),
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
