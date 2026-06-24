from __future__ import annotations

import argparse
import ast
import json
import os
import sqlite3
import sys
import tempfile
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Sequence
from unittest.mock import patch


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
from scripts.build_regular_options_13_symbol_frozen_candidate_generation_engine import (  # noqa: E402
    _cohort_pairs,
    _market_dates,
)
from scripts.build_regular_options_robust_search_evaluation import _load_json  # noqa: E402


REPORT_ID = "regular_options_historical_frozen_scanner_replay_adapter"
DEFAULT_FORWARD_COHORT = ROOT / "data" / "contracts" / "forward-cohort-preregistration.json"
DEFAULT_FEATURE_STORE = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_MARKET_REGIME_INPUTS = (
    ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-market-regime-inputs" / "latest.json"
)
DEFAULT_VIX_BUCKET = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-vix-bucket" / "latest.json"
DEFAULT_OUTPUT_DIR = (
    ROOT / "data" / "profitability-lab" / "regular-options-historical-frozen-scanner-replay-adapter"
)
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-historical-frozen-scanner-replay-adapter.md"

ACCEPTED_STATUSES = {"selected_candidate", "explicit_no_pick"}
ETF_OR_INDEX_SYMBOLS = {"SPY", "QQQ", "IWM", "DIA"}
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
    "external_market_data_fetch",
    "options_history_db_mutation",
    "market_data_db_mutation",
    "evidence_store_mutation",
    "forward_cohort_append",
    "protected_holdout_consumption",
    "promotion",
    "using_current_latest_data_for_historical_candidate_dates",
    "using_pnl_outcomes_winners_or_exits_to_decide_candidates",
    "inventing_selected_or_no_pick_rows",
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


def _function_parameters(path: Path, function_name: str) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf8"))
    except OSError:
        return []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            params = [arg.arg for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs]
            if node.args.vararg:
                params.append("*" + node.args.vararg.arg)
            if node.args.kwarg:
                params.append("**" + node.args.kwarg.arg)
            return params
    return []


def _write_probe_option_rows(db_path: Path) -> None:
    from historical_options_store import init_schema

    init_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        batch_id = conn.execute(
            """
            INSERT INTO import_batches (
                source_label, dataset_kind, data_trust, input_path, file_hash,
                imported_at_utc, total_rows, imported_rows, duplicate_rows, rejected_rows, warnings_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "thetadata_opra_nbbo_1m",
                "intraday_csv",
                "trusted",
                "fixture.csv",
                "abc",
                "2026-06-04T00:00:00Z",
                1,
                1,
                0,
                0,
                "[]",
            ),
        ).lastrowid
        conn.execute(
            """
            INSERT INTO option_quote_snapshots (
                as_of_utc, quote_date_et, quote_minute_et, snapshot_kind, underlying,
                contract_symbol, expiry, option_type, strike, bid, ask, last, iv,
                underlying_price, volume, open_interest, source_batch_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-02-03T15:12:00Z",
                "2026-02-03",
                10 * 60 + 12,
                "intraday",
                "SPY",
                "SPY260220C00500000",
                "2026-02-20",
                "call",
                500.0,
                4.1,
                4.3,
                None,
                None,
                501.0,
                None,
                None,
                batch_id,
            ),
        )
        conn.commit()


def _historical_option_provider_behavior_probe() -> dict[str, Any]:
    try:
        import options_chatbot as oc
        from historical_options_store import init_schema

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_path = Path(tmp) / "options_history.db"
            _write_probe_option_rows(db_path)
            with patch.dict(os.environ, {"HISTORICAL_OPTIONS_DB_PATH": str(db_path)}, clear=False), patch.object(
                oc,
                "_cached_options_metadata",
                side_effect=AssertionError("latest chain fallback called"),
            ):
                option = oc._fetch_best_option(
                    "SPY",
                    "call",
                    0.50,
                    17,
                    stock_price=501.0,
                    hv30_fallback=0.25,
                    candidate_generation_date="2026-02-03",
                    as_of_date="2026-06-04",
                )
            reads_trusted_row = bool(
                option
                and option.get("contract_symbol") == "SPY260220C00500000"
                and option.get("premium") == 4.3
                and option.get("quote_basis") == "ask"
                and option.get("iv") is None
                and option.get("volume") is None
                and option.get("open_interest") is None
                and option.get("historical_chain") is True
            )
            empty_db = Path(tmp) / "empty_options_history.db"
            init_schema(empty_db)
            with patch.dict(os.environ, {"HISTORICAL_OPTIONS_DB_PATH": str(empty_db)}, clear=False), patch.object(
                oc,
                "_cached_options_metadata",
                side_effect=AssertionError("latest chain fallback called"),
            ), patch.object(
                oc,
                "_cached_option_chain_metadata",
                side_effect=AssertionError("latest chain fallback called"),
            ):
                missing = oc._fetch_best_option(
                    "SPY",
                    "call",
                    0.50,
                    17,
                    stock_price=501.0,
                    hv30_fallback=0.25,
                    candidate_generation_date="2026-02-03",
                    as_of_date="2026-06-04",
                )
        fail_closed_without_fallback = missing is None
        return {
            "proven": bool(reads_trusted_row and fail_closed_without_fallback),
            "reads_trusted_historical_rows": reads_trusted_row,
            "fails_closed_without_latest_chain_fallback": fail_closed_without_fallback,
            "error": None,
        }
    except Exception as exc:
        return {
            "proven": False,
            "reads_trusted_historical_rows": False,
            "fails_closed_without_latest_chain_fallback": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _scanner_contract() -> dict[str, Any]:
    run_params = _function_parameters(ROOT / "supervised_scan.py", "run_supervised_scan")
    scan_params = _function_parameters(ROOT / "options_chatbot.py", "scan_daily_top_trades")
    option_params = _function_parameters(ROOT / "options_chatbot.py", "_fetch_best_option")
    spread_params = _function_parameters(ROOT / "options_chatbot.py", "_fetch_best_spread")
    required = {"candidate_generation_date", "as_of_date", "no_write"}
    run_missing = sorted(required - set(run_params))
    scan_missing = sorted(required - set(scan_params))
    option_missing = sorted({"candidate_generation_date", "as_of_date"} - set(option_params))
    spread_missing = sorted({"candidate_generation_date", "as_of_date"} - set(spread_params))
    blockers: list[str] = []
    if run_missing or scan_missing:
        blockers.append("scanner_api_missing_historical_no_write_contract")
    if option_missing or spread_missing:
        blockers.append("scanner_option_selection_missing_historical_as_of_contract")
    provider_behavior = _historical_option_provider_behavior_probe() if not blockers else {
        "proven": False,
        "reads_trusted_historical_rows": False,
        "fails_closed_without_latest_chain_fallback": False,
        "error": "signature_contract_missing",
    }
    if not provider_behavior.get("proven"):
        blockers.append("scanner_option_selection_missing_historical_as_of_contract")
    blockers = sorted(dict.fromkeys(blockers))
    return {
        "proof_safe_contract_available": not blockers,
        "required_parameters": sorted(required),
        "inspected_callables": [
            {
                "path": "supervised_scan.py",
                "function": "run_supervised_scan",
                "parameters": run_params,
                "missing_required_parameters": run_missing,
            },
            {
                "path": "options_chatbot.py",
                "function": "scan_daily_top_trades",
                "parameters": scan_params,
                "missing_required_parameters": scan_missing,
            },
            {
                "path": "options_chatbot.py",
                "function": "_fetch_best_option",
                "parameters": option_params,
                "missing_historical_parameters": option_missing,
            },
            {
                "path": "options_chatbot.py",
                "function": "_fetch_best_spread",
                "parameters": spread_params,
                "missing_historical_parameters": spread_missing,
            },
        ],
        "historical_option_provider_behavior": provider_behavior,
        "blockers": blockers,
    }


def _surface_inventory(market_regime: dict[str, Any], market_meta: dict[str, Any], vix: dict[str, Any], vix_meta: dict[str, Any]) -> dict[str, Any]:
    market_row_blockers = Counter(
        {str(key): int(value or 0) for key, value in _as_dict(market_regime.get("row_blocker_counts")).items()}
    )
    market_regime_ready = bool(
        market_meta.get("status") == "loaded"
        and market_regime.get("point_in_time_market_regime_inputs_available") is True
        and not _as_list(market_regime.get("blockers"))
    )
    vix_ready = bool(
        vix_meta.get("status") == "loaded"
        and vix.get("status") == "point_in_time_vix_bucket_ready"
        and not _as_list(vix.get("blockers"))
    )
    blockers: list[str] = []
    if not market_regime_ready:
        blockers.append("missing_point_in_time_market_regime_inputs")
        if market_row_blockers.get("market_regime_source_time_not_point_in_time"):
            blockers.append("underlying_daily_history_source_not_point_in_time")
    if not vix_ready:
        blockers.append("missing_point_in_time_vix_source")
    blockers.extend(
        [
            "missing_lane_specific_point_in_time_feature_inputs",
            "missing_historical_entry_underlying_price_surface",
            "missing_historical_option_chain_selection_surface",
            "missing_point_in_time_earnings_calendar_source",
        ]
    )
    return {
        "point_in_time_inputs_ready": False,
        "market_regime": {
            "path": market_meta.get("path"),
            "loaded": market_meta.get("status") == "loaded",
            "status": market_regime.get("status"),
            "available": market_regime_ready,
            "row_blocker_counts": dict(sorted(market_row_blockers.items())),
            "source_time_policy": market_regime.get("source_time_policy"),
        },
        "vix_bucket": {
            "path": vix_meta.get("path"),
            "loaded": vix_meta.get("status") == "loaded",
            "status": vix.get("status"),
            "available": vix_ready,
        },
        "underlying_feature_inputs": {
            "available": False,
            "required_fields": [
                "historical close/high/low/volume windows",
                "ret5",
                "ret20",
                "sma20",
                "sma50",
                "hv30",
                "hv30 rank history",
                "RSI/tech score inputs",
                "liquidity snapshot inputs",
            ],
            "blocker": "missing_lane_specific_point_in_time_feature_inputs",
        },
        "entry_underlying_price_surface": {
            "available": False,
            "required": "candidate-date entry underlying price used for contract selection, known before or at the candidate decision time",
            "blocker": "missing_historical_entry_underlying_price_surface",
        },
        "option_chain_selection_surface": {
            "available": False,
            "required": "historical option expirations, bid/ask, volume, open interest, IV/delta inputs with known-at proof for candidate-date contract selection",
            "blocker": "missing_historical_option_chain_selection_surface",
        },
        "earnings_calendar": {
            "available": False,
            "required": "point-in-time next-earnings dates for equity symbols in the frozen cohort",
            "blocker": "missing_point_in_time_earnings_calendar_source",
        },
        "blockers": sorted(dict.fromkeys(blockers)),
    }


def _row_blockers(symbol: str, contract: dict[str, Any], surfaces: dict[str, Any]) -> list[str]:
    blockers = ["missing_historical_scanner_point_in_time_inputs"]
    blockers.extend(str(item) for item in _as_list(contract.get("blockers")))
    blockers.extend(str(item) for item in _as_list(surfaces.get("blockers")))
    if symbol in ETF_OR_INDEX_SYMBOLS:
        blockers = [item for item in blockers if item != "missing_point_in_time_earnings_calendar_source"]
    return sorted(dict.fromkeys(blockers))


def _build_rows(
    *,
    market_dates: Sequence[date],
    pairs: Sequence[dict[str, str]],
    as_of: date,
    scanner_contract: dict[str, Any],
    surface_inventory: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for current_date in market_dates:
        for pair in pairs:
            lane = str(pair["lane"])
            symbol = str(pair["underlying"]).upper()
            blockers = _row_blockers(symbol, scanner_contract, surface_inventory)
            rows.append(
                {
                    "row_id": f"{REPORT_ID}:{current_date.isoformat()}:{lane}:{symbol}",
                    "date": current_date.isoformat(),
                    "candidate_generation_date": current_date.isoformat(),
                    "month": current_date.isoformat()[:7],
                    "lane": lane,
                    "lane_id": lane,
                    "underlying": symbol,
                    "ticker": symbol,
                    "symbol": symbol,
                    "policy_snapshot_sha256": pair.get("policy_snapshot_sha256"),
                    "status": "blocked_missing_historical_scanner_point_in_time_inputs",
                    "selected_candidate": False,
                    "explicit_no_pick": False,
                    "proof_safe": False,
                    "as_of_date": as_of.isoformat(),
                    "known_at": None,
                    "tradable_after": None,
                    "decision_timestamp_utc": None,
                    "read_only": True,
                    "no_write": True,
                    "decision_source": "historical_frozen_scanner_replay_adapter",
                    "blockers": blockers,
                    "missing_inputs": blockers,
                }
            )
    return rows


def _coverage(rows: Sequence[dict[str, Any]], requested_months: Sequence[str]) -> dict[str, Any]:
    by_month: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_month.setdefault(str(row.get("month")), []).append(dict(row))
    covered = [
        month
        for month in requested_months
        if by_month.get(month) and all(str(row.get("status")) in ACCEPTED_STATUSES for row in by_month[month])
    ]
    return {
        "requested_months": list(requested_months),
        "requested_month_count": len(requested_months),
        "covered_months": covered,
        "covered_month_count": len(covered),
        "blocked_months": [month for month in requested_months if month not in set(covered)],
    }


def build_report(
    *,
    forward_cohort_path: Path = DEFAULT_FORWARD_COHORT,
    feature_store_path: Path = DEFAULT_FEATURE_STORE,
    market_regime_inputs_path: Path = DEFAULT_MARKET_REGIME_INPUTS,
    vix_bucket_path: Path = DEFAULT_VIX_BUCKET,
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
    market_regime, market_regime_meta = _load_json(market_regime_inputs_path)
    vix, vix_meta = _load_json(vix_bucket_path)
    market_dates = _market_dates(feature, start, end)
    pairs = _cohort_pairs(cohort, ALLOWED_UNIVERSE)
    scanner_contract = _scanner_contract()
    surface_inventory = _surface_inventory(market_regime, market_regime_meta, vix, vix_meta)
    daily_rows = _build_rows(
        market_dates=market_dates,
        pairs=pairs,
        as_of=as_of,
        scanner_contract=scanner_contract,
        surface_inventory=surface_inventory,
    )
    requested_months = _month_range(start, end)
    coverage = _coverage(daily_rows, requested_months)
    status_counts = Counter(str(row.get("status")) for row in daily_rows)
    blocker_counts = Counter(
        str(blocker)
        for row in daily_rows
        for blocker in _as_list(row.get("blockers"))
    )
    blockers = sorted(dict.fromkeys(blocker_counts))
    if cohort_meta.get("status") != "loaded":
        blockers.append("forward_cohort_preregistration_not_loaded")
    if feature_meta.get("status") != "loaded":
        blockers.append("feature_store_not_loaded")
    if not market_dates:
        blockers.append("market_date_denominator_missing")
    if not pairs:
        blockers.append("forward_cohort_lane_symbol_pairs_missing")
    if coverage["covered_month_count"] < len(requested_months):
        blockers.append(f"candidate_generation_months_{coverage['covered_month_count']}_below_requested_{len(requested_months)}")
    blockers = sorted(dict.fromkeys(blockers))
    selected_rows = [row for row in daily_rows if row.get("selected_candidate")]
    report = {
        "report_id": REPORT_ID,
        "status": "blocked_historical_frozen_scanner_replay_adapter" if blockers else "historical_frozen_scanner_replay_adapter_ready",
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "schema_version": 1,
        "read_only": True,
        "research_only": True,
        "no_write": no_write,
        **FALSE_FLAGS,
        "scope": "bounded_read_only_historical_frozen_scanner_replay_adapter",
        "allowed_universe": list(ALLOWED_UNIVERSE),
        "frozen_universe": list(ALLOWED_UNIVERSE),
        "requested_window": {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "as_of_date": as_of.isoformat(),
            "requested_months": requested_months,
            "requested_month_count": len(requested_months),
        },
        "adapter_contract": {
            "accepted_fields": ["candidate_generation_date", "as_of_date", "lane_id", "symbol", "no_write"],
            "emitted_fields": ["candidate_generation_date", "as_of_date", "lane_id", "symbol", "no_write", "proof_safe"],
            "default_no_write": True,
            "proof_safe_success_rule": "selected_candidate or explicit_no_pick rows require all scanner inputs known at or before candidate_generation_date and no current/latest provider calls",
        },
        "inputs": {
            "forward_cohort": cohort_meta,
            "feature_store": feature_meta,
            "market_regime_inputs": market_regime_meta,
            "vix_bucket": vix_meta,
        },
        "scanner_contract": scanner_contract,
        "point_in_time_input_inventory": surface_inventory,
        "coverage": coverage,
        "calendar_coverage": {
            "status": "calendar_coverage_not_proven" if blockers else "calendar_coverage_proven",
            "coverage_basis": "proof_safe_selected_or_explicit_no_pick_rows_only",
            "calendar_months_covered": coverage["covered_months"],
            "calendar_months_covered_count": coverage["covered_month_count"],
            "blocked_months": coverage["blocked_months"],
        },
        "daily_status_counts": dict(sorted(status_counts.items())),
        "blocker_counts": dict(sorted(blocker_counts.items())),
        "daily_candidate_generation_row_count": len(daily_rows),
        "daily_candidate_decision_row_count": len(daily_rows),
        "selected_candidate_row_count": len(selected_rows),
        "daily_candidate_generation": daily_rows,
        "daily_candidate_decisions": daily_rows,
        "selected_candidates": selected_rows,
        "selected_trades": selected_rows,
        "blockers": blockers,
        "smallest_next_blocker_clearing_slice": "underlying_daily_history_source_not_point_in_time"
        if "underlying_daily_history_source_not_point_in_time" in blockers
        else (blockers[0] if blockers else None),
        "proof_policy": {
            "readback_is": "read-only historical frozen scanner replay adapter blocker proof",
            "readback_is_not": "profitability proof, fresh forward proof, scanner release, quote import, evidence mutation, live validation, auto-track, broker permission, protected-holdout consumption, proof-bar change, or promotion",
            "fail_closed_rule": "blocked rows are emitted instead of selected/no-pick rows until every scanner input has point-in-time known-at proof",
        },
        "forbidden_actions": FORBIDDEN_ACTIONS,
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    window = _as_dict(report.get("requested_window"))
    coverage = _as_dict(report.get("coverage"))
    lines = [
        "# Regular Options Historical Frozen Scanner Replay Adapter",
        "",
        "This generated artifact is a bounded read-only adapter for the frozen Phase 2 lane/symbol/date denominator. It fails closed when the scanner inputs needed for point-in-time replay are unavailable.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Window: `{window.get('window_start')}` through `{window.get('window_end')}` as of `{window.get('as_of_date')}`.",
        f"- Daily rows: `{report.get('daily_candidate_decision_row_count')}`.",
        f"- Covered months: `{coverage.get('covered_month_count')}` / `{coverage.get('requested_month_count')}`.",
        f"- Selected candidates: `{report.get('selected_candidate_row_count')}`.",
        f"- Smallest next blocker: `{report.get('smallest_next_blocker_clearing_slice')}`.",
        "",
        "## Status Counts",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status, count in _as_dict(report.get("daily_status_counts")).items():
        lines.append(f"| `{status}` | `{count}` |")
    lines.extend(["", "## Blocker Counts", "", "| Blocker | Count |", "|---|---:|"])
    for blocker, count in _as_dict(report.get("blocker_counts")).items():
        lines.append(f"| `{blocker}` | `{count}` |")
    if blockers := _as_list(report.get("blockers")):
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    lines.extend(["", "## Boundary", "", "The adapter did not call the scanner, fetch market data, import quotes, mutate evidence stores, or infer candidates from outcomes.", ""])
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
    parser = argparse.ArgumentParser(description="Build the read-only historical frozen scanner replay adapter.")
    parser.add_argument("--forward-cohort", type=Path, default=DEFAULT_FORWARD_COHORT)
    parser.add_argument("--source-feature-store", "--feature-store", type=Path, default=DEFAULT_FEATURE_STORE)
    parser.add_argument("--market-regime-inputs", type=Path, default=DEFAULT_MARKET_REGIME_INPUTS)
    parser.add_argument("--vix-bucket", type=Path, default=DEFAULT_VIX_BUCKET)
    parser.add_argument("--start-date", default=DEFAULT_WINDOW_START)
    parser.add_argument("--end-date", default=DEFAULT_WINDOW_END)
    parser.add_argument("--as-of-date", default=DEFAULT_AS_OF_DATE)
    parser.add_argument("--candidate-generation-date", default=None)
    parser.add_argument("--lane-id", default=None)
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--universe", default=",".join(ALLOWED_UNIVERSE))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(list(argv))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    start_date = args.candidate_generation_date or args.start_date
    end_date = args.candidate_generation_date or args.end_date
    report = build_report(
        forward_cohort_path=args.forward_cohort,
        feature_store_path=args.source_feature_store,
        market_regime_inputs_path=args.market_regime_inputs,
        vix_bucket_path=args.vix_bucket,
        window_start=start_date,
        window_end=end_date,
        as_of_date=args.as_of_date,
        universe=_parse_universe(args.universe),
        no_write=True,
    )
    if args.lane_id or args.symbol:
        lane = str(args.lane_id or "").strip()
        symbol = str(args.symbol or "").strip().upper()
        rows = [
            row
            for row in _as_list(report.get("daily_candidate_decisions"))
            if (not lane or row.get("lane_id") == lane) and (not symbol or row.get("symbol") == symbol)
        ]
        report["daily_candidate_generation"] = rows
        report["daily_candidate_decisions"] = rows
        report["selected_candidates"] = [row for row in rows if _as_dict(row).get("selected_candidate")]
        report["selected_trades"] = list(report["selected_candidates"])
        report["daily_candidate_generation_row_count"] = len(rows)
        report["daily_candidate_decision_row_count"] = len(rows)
        report["selected_candidate_row_count"] = len(report["selected_candidates"])
        report["daily_status_counts"] = dict(sorted(Counter(str(row.get("status")) for row in rows).items()))
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
