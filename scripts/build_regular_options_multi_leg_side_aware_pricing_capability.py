from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_multi_leg_side_aware_pricing_capability"

DEFAULT_OPTIONS_DB = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_MANIFEST = ROOT / "tests" / "fixtures" / "regular_options_multi_leg_pricing" / "ratio_backspread_bounded_manifest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-multi-leg-side-aware-pricing-capability"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-multi-leg-side-aware-pricing-capability.md"

SUPPORTED_STRUCTURES = ("ratio_backspread_bounded",)
DEFAULT_UNDERLYINGS = ("SPY", "QQQ")
TRUSTED_SOURCE_LABELS = {"thetadata_opra_nbbo_1m"}
CONTRACT_MULTIPLIER = 100
PROTECTED_HOLDOUT_START = "2026-06-01"

READ_ONLY_FLAGS = {
    "read_only": True,
    "research_only": True,
    "accepted_profitability": False,
    "historical_replay_performed": False,
    "historical_rows_are_forward_proof": False,
    "fixture_source_not_proof_eligible": True,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "options_history_db_mutated": False,
    "protected_holdout_consumed": False,
    "production_scanner_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "scanner_strategy_stop_sizing_or_proof_bar_changed": False,
    "promotion_ready": False,
}

DENOMINATOR_STATUSES = (
    "no_candidate",
    "rejected_flow_input_missing",
    "rejected_vix_bucket",
    "rejected_width_or_liquidity",
    "rejected_undefined_risk",
    "missing_leg_quote",
    "zero_bid_or_untradable",
    "crossed_or_invalid_quote",
    "stale_or_untrusted_quote",
    "exact_entry_captured",
    "open_waiting_policy_exit_or_expiry",
    "assignment_or_expiration_blocked",
    "exact_exit_captured",
    "missing_exit",
    "protected_holdout_blocked",
    "malformed_candidate",
)

FORBIDDEN_ACTIONS = (
    "do_not_create_trades",
    "do_not_prepare_or_submit_broker_orders",
    "do_not_enable_live_validation",
    "do_not_enable_auto_track",
    "do_not_run_or_change_production_scanners",
    "do_not_change_scanner_policy",
    "do_not_change_strategy_logic",
    "do_not_change_stops",
    "do_not_change_sizing",
    "do_not_lower_proof_bars",
    "do_not_import_quotes",
    "do_not_fetch_external_market_data",
    "do_not_mutate_options_history_db",
    "do_not_mutate_evidence_stores",
    "do_not_append_forward_cohort_rows",
    "do_not_consume_protected_holdout",
    "do_not_promote_any_lane",
    "do_not_allow_undefined_or_naked_ratio_backspread_risk",
    "do_not_count_fixture_rows_as_profitability_or_forward_proof",
)

LEAKY_OR_NON_EXECUTABLE_BASIS = {
    "mid",
    "midpoint",
    "source_mark",
    "mark",
    "eod",
    "display",
    "manual",
    "last",
    "last_trade",
    "model",
    "synthetic",
    "lookahead",
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


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _norm(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _safe_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _load_json(path: Path, *, required: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = {"path": _rel(path), "required": required, "exists": path.exists(), "status": "missing", "error": None}
    if not path.exists():
        return {}, meta
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        meta["status"] = "malformed"
        meta["error"] = f"JSONDecodeError:{exc.lineno}:{exc.colno}"
        return {}, meta
    except OSError as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return {}, meta
    if not isinstance(payload, dict):
        meta["status"] = "invalid"
        meta["error"] = "expected_object"
        return {}, meta
    meta["status"] = "loaded"
    meta["report_id"] = payload.get("report_id")
    return payload, meta


def _connect_read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def _db_inventory(path: Path) -> tuple[dict[str, Any], sqlite3.Connection | None]:
    meta = {
        "path": _rel(path),
        "exists": path.exists(),
        "read_only_mode": True,
        "status": "missing",
        "tables": {},
        "trusted_source_labels": [],
        "bid_ask_schema_fields": [],
        "quote_timestamp_fields": [],
        "contract_symbol_fields": [],
        "error": None,
    }
    if not path.exists():
        return meta, None
    try:
        con = _connect_read_only(path)
    except sqlite3.Error as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return meta, None
    try:
        tables = [row[0] for row in con.execute("select name from sqlite_master where type='table' order by name")]
        meta["tables"] = {name: {"columns": [col[1] for col in con.execute(f"pragma table_info({name})")]} for name in tables}
        quote_cols = _as_list(_as_dict(_as_dict(meta["tables"]).get("option_quote_snapshots")).get("columns"))
        batch_cols = _as_list(_as_dict(_as_dict(meta["tables"]).get("import_batches")).get("columns"))
        required_quote_cols = {
            "as_of_utc",
            "quote_date_et",
            "quote_minute_et",
            "snapshot_kind",
            "underlying",
            "contract_symbol",
            "expiry",
            "option_type",
            "strike",
            "bid",
            "ask",
            "source_batch_id",
        }
        required_batch_cols = {"id", "source_label", "data_trust"}
        missing_quote_cols = sorted(required_quote_cols - set(str(col) for col in quote_cols))
        missing_batch_cols = sorted(required_batch_cols - set(str(col) for col in batch_cols))
        meta["bid_ask_schema_fields"] = [col for col in ("bid", "ask") if col in quote_cols]
        meta["quote_timestamp_fields"] = [col for col in ("as_of_utc", "quote_date_et", "quote_minute_et") if col in quote_cols]
        meta["contract_symbol_fields"] = [col for col in ("underlying", "contract_symbol", "expiry", "option_type", "strike") if col in quote_cols]
        if missing_quote_cols or missing_batch_cols:
            meta["status"] = "missing_required_schema"
            meta["missing_quote_columns"] = missing_quote_cols
            meta["missing_import_batch_columns"] = missing_batch_cols
            return meta, con
        labels = [
            row[0]
            for row in con.execute(
                "select distinct source_label from import_batches where data_trust = 'trusted' order by source_label limit 25"
            )
        ]
        meta["trusted_source_labels"] = labels
        meta["status"] = "loaded"
        return meta, con
    except sqlite3.Error as exc:
        meta["status"] = "schema_error"
        meta["error"] = type(exc).__name__
        return meta, con


def _fixture_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(manifest.get("fixtures"), list):
        return [_as_dict(row) for row in manifest["fixtures"]]
    if isinstance(manifest.get("candidates"), list):
        return [_as_dict(row) for row in manifest["candidates"]]
    return []


def _quote_key(contract_symbol: str, quote_date_et: str, quote_minute_et: int) -> tuple[str, str, int]:
    return (contract_symbol, quote_date_et, quote_minute_et)


def _load_needed_quotes(con: sqlite3.Connection | None, fixtures: list[dict[str, Any]]) -> tuple[dict[tuple[str, str, int], dict[str, Any]], dict[str, int]]:
    if con is None:
        return {}, {"query_executed": 0, "row_count": 0}
    contract_symbols: set[str] = set()
    dates: set[str] = set()
    minutes: set[int] = set()
    for fixture in fixtures:
        entry_date = _norm(fixture.get("entry_date"))
        exit_date = _norm(fixture.get("exit_date") or fixture.get("policy_exit_date"))
        entry_minute = _safe_int(fixture.get("entry_minute_et"))
        exit_minute = _safe_int(fixture.get("exit_minute_et") or fixture.get("policy_exit_minute_et"))
        if entry_date and entry_minute is not None:
            dates.add(entry_date)
            minutes.add(entry_minute)
        if exit_date and exit_minute is not None:
            dates.add(exit_date)
            minutes.add(exit_minute)
        for leg in _as_list(fixture.get("legs")):
            symbol = _norm(_as_dict(leg).get("contract_symbol"))
            if symbol:
                contract_symbols.add(symbol)
    if not contract_symbols or not dates or not minutes:
        return {}, {"query_executed": 0, "row_count": 0}
    placeholders_symbols = ",".join("?" for _ in contract_symbols)
    placeholders_dates = ",".join("?" for _ in dates)
    placeholders_minutes = ",".join("?" for _ in minutes)
    params: list[Any] = sorted(contract_symbols) + sorted(dates) + sorted(minutes)
    sql = f"""
        select
            q.as_of_utc,
            q.quote_date_et,
            q.quote_minute_et,
            q.snapshot_kind,
            q.underlying,
            q.contract_symbol,
            q.expiry,
            q.option_type,
            q.strike,
            q.bid,
            q.ask,
            b.source_label,
            b.data_trust
        from option_quote_snapshots q
        join import_batches b on b.id = q.source_batch_id
        where q.contract_symbol in ({placeholders_symbols})
          and q.quote_date_et in ({placeholders_dates})
          and q.quote_minute_et in ({placeholders_minutes})
    """
    rows: dict[tuple[str, str, int], dict[str, Any]] = {}
    for row in con.execute(sql, params):
        payload = {
            "as_of_utc": row[0],
            "quote_date_et": row[1],
            "quote_minute_et": row[2],
            "snapshot_kind": row[3],
            "underlying": row[4],
            "contract_symbol": row[5],
            "expiry": row[6],
            "option_type": row[7],
            "strike": row[8],
            "bid": row[9],
            "ask": row[10],
            "source_label": row[11],
            "data_trust": row[12],
        }
        rows[_quote_key(str(row[5]), str(row[1]), int(row[2]))] = payload
    return rows, {"query_executed": 1, "row_count": len(rows)}


def _leg_side(leg: dict[str, Any]) -> str:
    side = _norm(leg.get("side") or leg.get("position") or leg.get("role")).lower()
    if side in {"long", "buy", "bought"}:
        return "long"
    if side in {"short", "sell", "sold"}:
        return "short"
    return side


def _quote_blocker(quote: dict[str, Any] | None) -> str | None:
    if not quote:
        return "missing_leg_quote"
    bid = _safe_float(quote.get("bid"))
    ask = _safe_float(quote.get("ask"))
    if quote.get("data_trust") != "trusted" or quote.get("source_label") not in TRUSTED_SOURCE_LABELS:
        return "stale_or_untrusted_quote"
    if _norm(quote.get("snapshot_kind")).lower() != "intraday":
        return "stale_or_untrusted_quote"
    if bid is None or ask is None:
        return "missing_leg_quote"
    if bid <= 0 or ask <= 0:
        return "zero_bid_or_untradable"
    if ask < bid:
        return "crossed_or_invalid_quote"
    return None


def _entry_cashflow(side: str, quantity: int, quote: dict[str, Any]) -> float:
    bid = float(quote["bid"])
    ask = float(quote["ask"])
    if side == "long":
        return -ask * quantity
    if side == "short":
        return bid * quantity
    raise ValueError(f"unsupported side {side}")


def _exit_cashflow(side: str, quantity: int, quote: dict[str, Any]) -> float:
    bid = float(quote["bid"])
    ask = float(quote["ask"])
    if side == "long":
        return bid * quantity
    if side == "short":
        return -ask * quantity
    raise ValueError(f"unsupported side {side}")


def _denominator_mapping_valid(mapping: dict[str, Any]) -> tuple[bool, list[str]]:
    present = {str(key) for key in mapping}
    missing = [status for status in DENOMINATOR_STATUSES if status not in present]
    return not missing, missing


def _fixture_static_blockers(fixture: dict[str, Any], *, underlyings: set[str], structures: set[str]) -> list[str]:
    blockers: list[str] = []
    basis_values = [
        _norm(fixture.get("entry_quote_basis")).lower(),
        _norm(fixture.get("exit_quote_basis")).lower(),
        _norm(fixture.get("pricing_basis")).lower(),
    ]
    if any(value in LEAKY_OR_NON_EXECUTABLE_BASIS for value in basis_values if value):
        blockers.append("non_executable_pricing_basis_rejected")
    if _norm(fixture.get("structure")) not in structures:
        blockers.append("unsupported_structure")
    if _norm(fixture.get("underlying")).upper() not in underlyings:
        blockers.append("wrong_underlying")
    if _norm(fixture.get("entry_date")) >= PROTECTED_HOLDOUT_START:
        blockers.append("protected_holdout_blocked")
    if fixture.get("bounded_risk") is not True or fixture.get("undefined_risk_allowed") is not False:
        blockers.append("rejected_undefined_risk")
    if _safe_float(fixture.get("max_loss_usd")) is None or _safe_float(fixture.get("max_loss_usd")) <= 0:
        blockers.append("missing_max_loss_or_collateral")
    if not _norm(fixture.get("collateral_convention")):
        blockers.append("missing_max_loss_or_collateral")
    mapping_valid, missing_statuses = _denominator_mapping_valid(_as_dict(fixture.get("denominator_status_mapping")))
    if not mapping_valid:
        blockers.append("missing_denominator_mapping")
        fixture["_missing_denominator_statuses"] = missing_statuses
    legs = [_as_dict(leg) for leg in _as_list(fixture.get("legs"))]
    if not legs:
        blockers.append("malformed_candidate")
    for leg in legs:
        quantity = _safe_int(leg.get("quantity"))
        if quantity is None or quantity <= 0 or _leg_side(leg) not in {"long", "short"} or not _norm(leg.get("contract_symbol")):
            blockers.append("malformed_candidate")
            break
    if not any(_leg_side(leg) == "long" for leg in legs) or not any(_leg_side(leg) == "short" for leg in legs):
        blockers.append("rejected_undefined_risk")
    return sorted(set(blockers))


def _classify_quote_blocker(blockers: list[str]) -> str:
    priority = [
        "non_executable_pricing_basis_rejected",
        "wrong_underlying",
        "protected_holdout_blocked",
        "rejected_undefined_risk",
        "missing_denominator_mapping",
        "malformed_candidate",
        "missing_leg_quote",
        "zero_bid_or_untradable",
        "crossed_or_invalid_quote",
        "stale_or_untrusted_quote",
        "missing_exit",
    ]
    for item in priority:
        if item in blockers:
            return item
    return blockers[0] if blockers else "exact_exit_captured"


def _price_fixture(
    fixture: dict[str, Any],
    *,
    quotes: dict[tuple[str, str, int], dict[str, Any]],
    underlyings: set[str],
    structures: set[str],
) -> dict[str, Any]:
    blockers = _fixture_static_blockers(fixture, underlyings=underlyings, structures=structures)
    entry_date = _norm(fixture.get("entry_date"))
    exit_date = _norm(fixture.get("exit_date") or fixture.get("policy_exit_date"))
    entry_minute = _safe_int(fixture.get("entry_minute_et"))
    exit_minute = _safe_int(fixture.get("exit_minute_et") or fixture.get("policy_exit_minute_et"))
    if entry_minute is None:
        blockers.append("malformed_candidate")
    if exit_minute is None or not exit_date:
        blockers.append("missing_exit")
    leg_results: list[dict[str, Any]] = []
    entry_cashflow = 0.0
    exit_cashflow = 0.0
    if not blockers:
        for leg in [_as_dict(row) for row in _as_list(fixture.get("legs"))]:
            quantity = int(leg["quantity"])
            side = _leg_side(leg)
            symbol = _norm(leg.get("contract_symbol"))
            entry_quote = quotes.get(_quote_key(symbol, entry_date, int(entry_minute)))
            exit_quote = quotes.get(_quote_key(symbol, exit_date, int(exit_minute)))
            entry_blocker = _quote_blocker(entry_quote)
            exit_blocker = _quote_blocker(exit_quote)
            if entry_blocker:
                blockers.append(entry_blocker)
            if exit_blocker:
                blockers.append("missing_exit" if exit_blocker == "missing_leg_quote" else exit_blocker)
            result = {
                "leg_id": leg.get("leg_id"),
                "side": side,
                "quantity": quantity,
                "contract_symbol": symbol,
                "entry_quote_status": "ready" if entry_blocker is None else entry_blocker,
                "exit_quote_status": "ready" if exit_blocker is None else exit_blocker,
            }
            if entry_blocker is None and entry_quote is not None:
                result["entry_bid"] = entry_quote.get("bid")
                result["entry_ask"] = entry_quote.get("ask")
                entry_cashflow += _entry_cashflow(side, quantity, entry_quote)
            if exit_blocker is None and exit_quote is not None:
                result["exit_bid"] = exit_quote.get("bid")
                result["exit_ask"] = exit_quote.get("ask")
                exit_cashflow += _exit_cashflow(side, quantity, exit_quote)
            leg_results.append(result)
    unique_blockers = sorted(set(blockers))
    status = "exact_exit_captured" if not unique_blockers else _classify_quote_blocker(unique_blockers)
    fees_usd = _safe_float(fixture.get("fees_usd")) or 0.0
    slippage_usd = _safe_float(fixture.get("slippage_usd")) or 0.0
    priced = status == "exact_exit_captured"
    return {
        "fixture_id": fixture.get("fixture_id") or fixture.get("candidate_id"),
        "structure": fixture.get("structure"),
        "underlying": fixture.get("underlying"),
        "status": status,
        "blockers": unique_blockers,
        "missing_denominator_statuses": fixture.get("_missing_denominator_statuses", []),
        "leg_results": leg_results,
        "entry_net_cashflow_per_share": round(entry_cashflow, 4) if priced else None,
        "exit_net_cashflow_per_share": round(exit_cashflow, 4) if priced else None,
        "net_pnl_usd_after_costs": round((entry_cashflow + exit_cashflow) * CONTRACT_MULTIPLIER - fees_usd - slippage_usd, 2) if priced else None,
        "max_loss_usd": _safe_float(fixture.get("max_loss_usd")),
        "collateral_convention": fixture.get("collateral_convention"),
        "denominator_status_mapping_status": "ready" if "missing_denominator_mapping" not in unique_blockers else "blocked",
        "fixture_source_not_proof_eligible": True,
    }


def _count_statuses(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status"))
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _count_blockers(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for blocker in _as_list(row.get("blockers")):
            key = str(blocker)
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _structure_support(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ratio_rows = [row for row in rows if row.get("structure") == "ratio_backspread_bounded"]
    priced = [row for row in ratio_rows if row.get("status") == "exact_exit_captured"]
    denominator_ready = all(row.get("denominator_status_mapping_status") == "ready" for row in priced)
    status = "available" if priced and denominator_ready else "blocked"
    blockers = sorted(
        {
            str(blocker)
            for row in ratio_rows
            for blocker in _as_list(row.get("blockers"))
            if blocker
        }
    )
    return {
        "ratio_backspread_bounded": {
            "status": status,
            "resolved_fixture_count": len(priced),
            "fixture_count": len(ratio_rows),
            "blockers": blockers,
            "denominator_mapping_status": "ready" if denominator_ready and priced else "blocked",
            "undefined_or_naked_ratio_risk_allowed": False,
        }
    }


def build_report(
    *,
    options_db_path: Path = DEFAULT_OPTIONS_DB,
    manifest_path: Path = DEFAULT_MANIFEST,
    as_of_date: str = "2026-06-04",
    structures: tuple[str, ...] | list[str] = SUPPORTED_STRUCTURES,
    underlyings: tuple[str, ...] | list[str] = DEFAULT_UNDERLYINGS,
    no_write_requested: bool = False,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    manifest, manifest_meta = _load_json(manifest_path, required=True)
    fixtures = _fixture_rows(manifest)
    inventory, con = _db_inventory(options_db_path)
    try:
        quotes, query_meta = _load_needed_quotes(con, fixtures)
    finally:
        if con is not None:
            con.close()
    structure_set = {str(item) for item in structures}
    underlying_set = {str(item).upper() for item in underlyings}
    rows = [
        _price_fixture(fixture, quotes=quotes, underlyings=underlying_set, structures=structure_set)
        for fixture in fixtures
    ]
    support = _structure_support(rows)
    ratio = _as_dict(support.get("ratio_backspread_bounded"))
    blockers = set(_count_blockers(rows))
    if manifest_meta["status"] != "loaded":
        blockers.add("missing_fixture_manifest")
    if inventory.get("status") != "loaded":
        blockers.add("missing_or_invalid_options_history_db")
    if not fixtures:
        blockers.add("missing_fixture_manifest_rows")
    if ratio.get("status") != "available":
        blockers.add("missing_side_aware_ratio_backspread_pricing")
    status = (
        "multi_leg_side_aware_pricing_capability_available"
        if not blockers and ratio.get("status") == "available"
        else "blocked_multi_leg_side_aware_pricing_capability"
    )
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": status,
        **READ_ONLY_FLAGS,
        "no_write_requested": no_write_requested,
        "scope": "read_only_multi_leg_side_aware_pricing_capability",
        "as_of_date": as_of_date,
        "protected_holdout_start": PROTECTED_HOLDOUT_START,
        "supported_structures": list(SUPPORTED_STRUCTURES),
        "requested_structures": sorted(structure_set),
        "requested_underlyings": sorted(underlying_set),
        "pricing_formula": {
            "entry": "long/open legs use ask; short/open legs use bid; net_entry_cashflow_per_share = sum(short_bid * qty) - sum(long_ask * qty)",
            "exit": "long/close legs use bid; short/close legs use ask; net_exit_cashflow_per_share = sum(long_bid * qty) - sum(short_ask * qty)",
            "net_pnl_usd_after_costs": "(entry_net_cashflow_per_share + exit_net_cashflow_per_share) * 100 - fees_usd - slippage_usd",
            "forbidden_fallbacks": sorted(LEAKY_OR_NON_EXECUTABLE_BASIS),
        },
        "denominator_status_contract": list(DENOMINATOR_STATUSES),
        "source_inventory": inventory,
        "source_artifacts": {"fixture_manifest": manifest_meta, "options_history_db": inventory},
        "query_meta": query_meta,
        "fixture_manifest_status": manifest_meta["status"],
        "fixture_results": rows,
        "quote_resolution_counts": {
            "fixture_count": len(rows),
            "resolved_fixture_count": len([row for row in rows if row.get("status") == "exact_exit_captured"]),
            "status_counts": _count_statuses(rows),
            "blocker_counts": _count_blockers(rows),
        },
        "missing_quote_counts": {"missing_leg_quote": _count_blockers(rows).get("missing_leg_quote", 0), "missing_exit": _count_blockers(rows).get("missing_exit", 0)},
        "zero_bid_counts": {"zero_bid_or_untradable": _count_blockers(rows).get("zero_bid_or_untradable", 0)},
        "crossed_quote_counts": {"crossed_or_invalid_quote": _count_blockers(rows).get("crossed_or_invalid_quote", 0)},
        "stale_quote_counts": {"stale_or_untrusted_quote": _count_blockers(rows).get("stale_or_untrusted_quote", 0)},
        "structure_support": support,
        "pricing_capability_blockers": sorted(blockers),
        "accepted_profitability_reason": "Capability fixtures are executable-pricing checks only; they are not historical replay, profitability proof, or forward evidence.",
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }
    _validate_report(report)
    return report


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    for status in DENOMINATOR_STATUSES:
        if status not in report.get("denominator_status_contract", []):
            raise ValueError(f"missing denominator status {status}")
    if report.get("accepted_profitability") is not False:
        raise ValueError("capability cannot claim accepted profitability")
    if report.get("fixture_source_not_proof_eligible") is not True:
        raise ValueError("fixture source must be marked not proof eligible")


def _fmt_bool(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Multi-Leg Side-Aware Pricing Capability",
        "",
        "This generated artifact is a read-only, research-only capability check. It resolves fixture legs from the local `options_history.db` using bid/ask only and never treats fixture output as profitability, historical replay, or forward proof.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Accepted profitability: `{_fmt_bool(report['accepted_profitability'])}`.",
        f"- Fixture source proof eligible: `{_fmt_bool(not report['fixture_source_not_proof_eligible'])}`.",
        f"- Options DB read-only: `{_fmt_bool(report['source_inventory']['read_only_mode'])}`.",
        f"- Resolved fixtures: `{report['quote_resolution_counts']['resolved_fixture_count']}` of `{report['quote_resolution_counts']['fixture_count']}`.",
        "",
        "## Structure Support",
        "",
        "| Structure | Status | Resolved | Blockers |",
        "| --- | --- | --- | --- |",
    ]
    for structure, row in _as_dict(report.get("structure_support")).items():
        row = _as_dict(row)
        blockers = ", ".join(f"`{item}`" for item in _as_list(row.get("blockers"))) or "-"
        lines.append(f"| `{structure}` | `{row.get('status')}` | `{row.get('resolved_fixture_count')}` / `{row.get('fixture_count')}` | {blockers} |")
    lines.extend(["", "## Pricing Formula", ""])
    for key, value in _as_dict(report.get("pricing_formula")).items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Denominator Status Contract", ""])
    lines.extend(f"- `{item}`" for item in _as_list(report.get("denominator_status_contract")))
    lines.extend(["", "## Blockers", ""])
    if report.get("pricing_capability_blockers"):
        lines.extend(f"- `{item}`" for item in _as_list(report.get("pricing_capability_blockers")))
    else:
        lines.append("- None.")
    lines.extend(["", "## Forbidden Actions", ""])
    lines.extend(f"- `{item}`" for item in _as_list(report.get("forbidden_actions")))
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
    json_path = output_dir / f"{stamp}.json"
    md_path = output_dir / f"{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    artifacts = {
        "json": _rel(json_path),
        "markdown": _rel(md_path),
        "latest_json": _rel(latest_json),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
    }
    report_with_artifacts = dict(report)
    report_with_artifacts["artifacts"] = artifacts
    markdown = render_markdown(report_with_artifacts)
    for path in (json_path, latest_json):
        path.write_text(json.dumps(report_with_artifacts, indent=2, sort_keys=True) + "\n", encoding="utf8")
    for path in (md_path, latest_md, docs_report):
        path.write_text(markdown, encoding="utf8")
    report["artifacts"] = artifacts
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a read-only multi-leg side-aware pricing capability artifact.")
    parser.add_argument("--options-db", type=Path, default=DEFAULT_OPTIONS_DB)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--as-of-date", default="2026-06-04")
    parser.add_argument("--structures", default=",".join(SUPPORTED_STRUCTURES))
    parser.add_argument("--underlyings", default=",".join(DEFAULT_UNDERLYINGS))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    structures = tuple(item.strip() for item in args.structures.split(",") if item.strip())
    underlyings = tuple(item.strip().upper() for item in args.underlyings.split(",") if item.strip())
    report = build_report(
        options_db_path=args.options_db,
        manifest_path=args.manifest,
        as_of_date=args.as_of_date,
        structures=structures,
        underlyings=underlyings,
        no_write_requested=args.no_write,
    )
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
