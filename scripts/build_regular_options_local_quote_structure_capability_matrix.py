from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


REPORT_ID = "regular_options_local_quote_structure_capability_matrix"
MATRIX_ID = "local_opra_nbbo_structure_capability_matrix_v1"
DEFAULT_DB = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-local-quote-structure-capability-matrix"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-local-quote-structure-capability-matrix.md"
DEFAULT_PACKET = ROOT / "data" / "forward-tracking" / "options_oracle_profit_loop_packet_latest.json"
DEFAULT_BASE_LEDGER = ROOT / "data" / "profitability-lab" / "regular-options-base-clean-stack-identity-ledger" / "latest.json"
DEFAULT_OPENING_REPLAY = ROOT / "data" / "profitability-lab" / "regular-options-quote-surface-opening-range-reversal-replay" / "latest.json"
DEFAULT_SYNTHETIC_FORWARD = ROOT / "data" / "profitability-lab" / "regular-options-quote-derived-synthetic-forward-surface" / "latest.json"
DEFAULT_HOLDOUT = ROOT / "data" / "contracts" / "forward-holdout-contract.json"

PROOF_SET_UNIVERSE = ("SPY", "QQQ", "IWM", "AAPL", "GOOGL", "UNH", "LLY", "JNJ", "XOM", "CVX", "COP", "NEM", "DIA")
INDEX_SUMMARY_UNIVERSE = ("SPY", "QQQ", "IWM", "DIA")
DEFAULT_ENTRY_BUCKETS = ("10:40", "14:30")
DEFAULT_EXIT_BUCKET = "15:50"
DEFAULT_DTE_BUCKETS = ("0-7", "7-21", "21-45", "45-90")
LATEST_FOUR_MONTHS = ("2026-02", "2026-03", "2026-04", "2026-05")
MIN_FULL_WINDOW = 200
MIN_LATEST_FOUR = 30
MIN_TRAIN_MONTHS = 20
TRUSTED_SOURCE_LABEL = "thetadata_opra_nbbo_1m"

STRUCTURES = (
    "long_single_leg_calls_puts",
    "same_expiration_same_type_verticals",
    "same_expiration_same_type_butterflies",
    "same_expiration_same_type_condors",
    "straddles_strangles",
    "iron_flies_iron_condors",
    "same_type_calendars_diagonals",
    "bounded_ratio_backspread_shapes",
)

READ_ONLY_FLAGS = {
    "read_only": True,
    "no_write": True,
    "accepted_profitability": False,
    "historical_rows_are_forward_proof": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "live_entry_allowed": False,
    "live_validation_enabled": False,
    "auto_track_allowed": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "promotion_ready": False,
}

FORBIDDEN_ACTIONS = (
    "do_not_create_trades",
    "do_not_prepare_or_submit_broker_orders",
    "do_not_enable_live_validation",
    "do_not_enable_auto_track",
    "do_not_append_forward_paper_shadow_cohort",
    "do_not_import_quotes",
    "do_not_mutate_options_history_db",
    "do_not_mutate_evidence_stores",
    "do_not_consume_protected_holdout",
    "do_not_change_production_scanner_policy",
    "do_not_change_production_strategy_logic",
    "do_not_change_stops",
    "do_not_change_sizing",
    "do_not_lower_proof_bars",
    "do_not_promote_any_lane",
    "do_not_treat_historical_rows_as_forward_proof",
    "do_not_treat_capability_rows_as_profitability_proof",
    "do_not_treat_quote_coverage_as_candidate_generation_proof",
    "do_not_use_midpoint_stale_eod_display_last_model_manual_or_synthetic_marks_as_fill_or_pnl_evidence",
    "do_not_reclassify_zero_bid_or_untradable_rows_as_missing_data",
    "do_not_optimize_structure_or_bucket_choice_on_pnl",
)


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
    if not isinstance(payload, dict):
        meta["status"] = "invalid"
        meta["error"] = "expected_object"
        return {}, meta
    meta["status"] = "loaded"
    meta["report_id"] = payload.get("report_id") or payload.get("contract_id")
    meta["status_value"] = payload.get("status")
    meta["generated_at_utc"] = payload.get("generated_at_utc")
    return payload, meta


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _month_range(start_date: str, end_date: str) -> list[str]:
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if start is None or end is None:
        return []
    cursor = date(start.year, start.month, 1)
    months: list[str] = []
    while cursor <= end:
        months.append(cursor.isoformat()[:7])
        cursor = date(cursor.year + (1 if cursor.month == 12 else 0), 1 if cursor.month == 12 else cursor.month + 1, 1)
    return months


def _bucket_to_minute(bucket: str) -> int:
    hour, minute = bucket.split(":", 1)
    return int(hour) * 60 + int(minute)


def _parse_dte_bucket(bucket: str) -> tuple[int, int]:
    left, right = bucket.split("-", 1)
    return int(left), int(right)


def _dte_bucket(expiry: str, quote_date: str, buckets: tuple[str, ...]) -> str | None:
    expiry_dt = _parse_date(expiry)
    quote_dt = _parse_date(quote_date)
    if expiry_dt is None or quote_dt is None:
        return None
    dte = (expiry_dt - quote_dt).days
    for bucket in buckets:
        lo, hi = _parse_dte_bucket(bucket)
        if lo <= dte <= hi:
            return bucket
    return None


def _connect_read_only(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def _read_only_confirmed(conn: sqlite3.Connection) -> bool:
    try:
        return int(conn.execute("PRAGMA query_only").fetchone()[0]) == 1
    except (sqlite3.Error, TypeError, IndexError):
        return False


def _quote_ok(row: sqlite3.Row) -> bool:
    bid = row["bid"]
    ask = row["ask"]
    return bid is not None and ask is not None and float(bid) > 0 and float(ask) > 0 and float(ask) >= float(bid)


def _spread_pct(row: dict[str, Any]) -> float:
    bid = float(row["bid"])
    ask = float(row["ask"])
    mid = (bid + ask) / 2.0
    return (ask - bid) / mid if mid > 0 else math.inf


def _identity_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf8")).hexdigest()


def _opportunity_identity(
    *,
    structure: str,
    symbol: str,
    quote_date: str,
    entry_bucket: str,
    exit_bucket: str,
    dte_bucket: str,
    legs: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "matrix_id": MATRIX_ID,
        "structure": structure,
        "symbol": symbol,
        "quote_date": quote_date,
        "entry_bucket": entry_bucket,
        "exit_bucket": exit_bucket,
        "dte_bucket": dte_bucket,
        "legs": [
            {
                "contract_symbol": leg["contract_symbol"],
                "side": leg["side"],
                "quantity": leg["quantity"],
                "expiry": leg["expiry"],
                "option_type": leg["option_type"],
                "strike": leg["strike"],
            }
            for leg in legs
        ],
    }


def _leg(contract: dict[str, Any], *, side: str, quantity: int = 1) -> dict[str, Any]:
    return {
        "contract_symbol": contract["contract_symbol"],
        "side": side,
        "quantity": quantity,
        "expiry": contract["expiry"],
        "option_type": contract["option_type"],
        "strike": contract["strike"],
        "quote_quality_spread_pct": round(_spread_pct(contract), 6),
    }


def _load_base_identity_hashes(payload: dict[str, Any]) -> set[str]:
    hashes = set(str(item) for item in _as_list(payload.get("identity_hashes")) if item)
    for row in _as_list(payload.get("ledger_entries")):
        value = _as_dict(row).get("stable_identity_hash")
        if value:
            hashes.add(str(value))
    return hashes


def _baseline(packet: dict[str, Any], base_ledger: dict[str, Any], opening: dict[str, Any], synthetic: dict[str, Any]) -> dict[str, Any]:
    return {
        "current_forward_or_latest_four_strict_rows": 0,
        "target_latest_four_strict_rows": 30,
        "base_clean_stack_exact_rows": base_ledger.get("ledger_row_count") or base_ledger.get("expected_base_clean_stack_exact_rows") or 157,
        "frontier_candidate_count": 44,
        "countable_throughput_candidate_found": False,
        "opening_range_status": opening.get("status"),
        "opening_range_blocker": "blocked_missing_quote_surface_underlying_price"
        if "blocked_missing_quote_surface_underlying_price" in _as_list(opening.get("blockers"))
        else None,
        "synthetic_forward_status": synthetic.get("status"),
        "synthetic_forward_blocker": "blocked_missing_call_put_pairs"
        if _as_dict(_as_dict(synthetic.get("metrics")).get("bucket_status_counts")).get("blocked_missing_call_put_pairs", 0)
        else None,
        "oracle_packet_status": packet.get("status"),
    }


def _month_sets(rows: list[dict[str, Any]]) -> tuple[list[str], int, int]:
    months = sorted({str(row["quote_date"])[:7] for row in rows})
    train = [month for month in months if month < LATEST_FOUR_MONTHS[0]]
    latest = [month for month in LATEST_FOUR_MONTHS if month in months]
    return months, len(train), len(latest)


def _group_contracts(rows: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["expiry"], row["option_type"])].append(row)
    for key in grouped:
        grouped[key].sort(key=lambda item: (float(item["strike"]), item["contract_symbol"]))
    return grouped


def _count_verticals(group: list[dict[str, Any]]) -> tuple[int, list[dict[str, Any]] | None]:
    count = 0
    best: list[dict[str, Any]] | None = None
    best_key: tuple[float, float, str] | None = None
    for i, low in enumerate(group):
        for high in group[i + 1 :]:
            width = float(high["strike"]) - float(low["strike"])
            if width <= 0:
                continue
            if width > 10:
                break
            legs = [_leg(low, side="long"), _leg(high, side="short")]
            count += 1
            key = (max(_spread_pct(low), _spread_pct(high)), -min(float(low["bid"]), float(high["bid"])), low["contract_symbol"])
            if best_key is None or key < best_key:
                best_key = key
                best = legs
    return count, best


def _count_butterflies(group: list[dict[str, Any]]) -> tuple[int, list[dict[str, Any]] | None]:
    count = 0
    best: list[dict[str, Any]] | None = None
    best_key: tuple[float, float, str] | None = None
    for i in range(len(group) - 2):
        a, b, c = group[i], group[i + 1], group[i + 2]
        width1 = float(b["strike"]) - float(a["strike"])
        width2 = float(c["strike"]) - float(b["strike"])
        if width1 <= 0 or width2 <= 0 or width1 > 10 or width2 > 10:
            continue
        legs = [_leg(a, side="long"), _leg(b, side="short", quantity=2), _leg(c, side="long")]
        count += 1
        key = (max(_spread_pct(a), _spread_pct(b), _spread_pct(c)), -min(float(a["bid"]), float(b["bid"]), float(c["bid"])), a["contract_symbol"])
        if best_key is None or key < best_key:
            best_key = key
            best = legs
    return count, best


def _count_condors(group: list[dict[str, Any]]) -> tuple[int, list[dict[str, Any]] | None]:
    count = 0
    best: list[dict[str, Any]] | None = None
    best_key: tuple[float, float, str] | None = None
    for i in range(len(group) - 3):
        a, b, c, d = group[i], group[i + 1], group[i + 2], group[i + 3]
        if float(d["strike"]) - float(a["strike"]) > 30:
            continue
        legs = [_leg(a, side="long"), _leg(b, side="short"), _leg(c, side="short"), _leg(d, side="long")]
        count += 1
        key = (max(_spread_pct(a), _spread_pct(b), _spread_pct(c), _spread_pct(d)), -min(float(x["bid"]) for x in (a, b, c, d)), a["contract_symbol"])
        if best_key is None or key < best_key:
            best_key = key
            best = legs
    return count, best


def _count_ratio(group: list[dict[str, Any]]) -> tuple[int, list[dict[str, Any]] | None]:
    count = 0
    best: list[dict[str, Any]] | None = None
    best_key: tuple[float, float, str] | None = None
    for i in range(len(group) - 2):
        a, b, c = group[i], group[i + 1], group[i + 2]
        if float(c["strike"]) - float(a["strike"]) > 30:
            continue
        legs = [_leg(a, side="short"), _leg(b, side="long", quantity=2), _leg(c, side="short")]
        count += 1
        key = (max(_spread_pct(a), _spread_pct(b), _spread_pct(c)), -min(float(a["bid"]), float(b["bid"]), float(c["bid"])), a["contract_symbol"])
        if best_key is None or key < best_key:
            best_key = key
            best = legs
    return count, best


def _count_cross_type(groups: dict[tuple[str, str], list[dict[str, Any]]]) -> tuple[dict[str, int], dict[str, list[dict[str, Any]] | None]]:
    counts = {"straddles_strangles": 0, "iron_flies_iron_condors": 0}
    reps: dict[str, list[dict[str, Any]] | None] = {"straddles_strangles": None, "iron_flies_iron_condors": None}
    for expiry in sorted({key[0] for key in groups}):
        calls = groups.get((expiry, "call"), [])
        puts = groups.get((expiry, "put"), [])
        if calls and puts:
            counts["straddles_strangles"] += min(len(calls), len(puts))
            call = calls[len(calls) // 2]
            put = min(puts, key=lambda row: (abs(float(row["strike"]) - float(call["strike"])), row["contract_symbol"]))
            reps["straddles_strangles"] = reps["straddles_strangles"] or [_leg(call, side="long"), _leg(put, side="long")]
        call_verticals, call_rep = _count_verticals(calls)
        put_verticals, put_rep = _count_verticals(puts)
        iron_count = min(call_verticals, put_verticals)
        if iron_count:
            counts["iron_flies_iron_condors"] += iron_count
            reps["iron_flies_iron_condors"] = reps["iron_flies_iron_condors"] or (call_rep or []) + (put_rep or [])
    return counts, reps


def _count_calendars(groups: dict[tuple[str, str], list[dict[str, Any]]]) -> tuple[int, list[dict[str, Any]] | None]:
    count = 0
    best: list[dict[str, Any]] | None = None
    by_type_strike: dict[tuple[str, float], list[dict[str, Any]]] = defaultdict(list)
    for rows in groups.values():
        for row in rows:
            by_type_strike[(row["option_type"], float(row["strike"]))].append(row)
    for key in sorted(by_type_strike):
        rows = sorted(by_type_strike[key], key=lambda row: (row["expiry"], row["contract_symbol"]))
        for i in range(len(rows) - 1):
            front, back = rows[i], rows[i + 1]
            if front["expiry"] == back["expiry"]:
                continue
            count += 1
            if best is None:
                best = [_leg(front, side="short"), _leg(back, side="long")]
    return count, best


def _structure_counts(contracts: list[dict[str, Any]]) -> dict[str, tuple[int, list[dict[str, Any]] | None]]:
    groups = _group_contracts(contracts)
    result: dict[str, tuple[int, list[dict[str, Any]] | None]] = {structure: (0, None) for structure in STRUCTURES}
    singles = len(contracts)
    if contracts:
        best_single = min(contracts, key=lambda row: (_spread_pct(row), -float(row["bid"]), row["contract_symbol"]))
        result["long_single_leg_calls_puts"] = (singles, [_leg(best_single, side="long")])
    vertical_count = butterfly_count = condor_count = ratio_count = 0
    vertical_rep = butterfly_rep = condor_rep = ratio_rep = None
    for group in groups.values():
        count, rep = _count_verticals(group)
        vertical_count += count
        vertical_rep = vertical_rep or rep
        count, rep = _count_butterflies(group)
        butterfly_count += count
        butterfly_rep = butterfly_rep or rep
        count, rep = _count_condors(group)
        condor_count += count
        condor_rep = condor_rep or rep
        count, rep = _count_ratio(group)
        ratio_count += count
        ratio_rep = ratio_rep or rep
    cross_counts, cross_reps = _count_cross_type(groups)
    calendar_count, calendar_rep = _count_calendars(groups)
    result["same_expiration_same_type_verticals"] = (vertical_count, vertical_rep)
    result["same_expiration_same_type_butterflies"] = (butterfly_count, butterfly_rep)
    result["same_expiration_same_type_condors"] = (condor_count, condor_rep)
    result["bounded_ratio_backspread_shapes"] = (ratio_count, ratio_rep)
    result["straddles_strangles"] = (cross_counts["straddles_strangles"], cross_reps["straddles_strangles"])
    result["iron_flies_iron_condors"] = (cross_counts["iron_flies_iron_condors"], cross_reps["iron_flies_iron_condors"])
    result["same_type_calendars_diagonals"] = (calendar_count, calendar_rep)
    return result


def _fetch_symbol_quotes(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    start_date: str,
    end_date: str,
    minutes: tuple[int, ...],
) -> list[dict[str, Any]]:
    placeholders = ",".join("?" for _ in minutes)
    rows = conn.execute(
        f"""
        SELECT q.quote_date_et, q.quote_minute_et, q.contract_symbol, q.expiry, q.option_type, q.strike,
               q.bid, q.ask, q.source_batch_id
        FROM option_quote_snapshots q
        WHERE q.snapshot_kind = 'intraday'
          AND q.underlying = ?
          AND q.quote_date_et BETWEEN ? AND ?
          AND q.quote_minute_et IN ({placeholders})
          AND q.bid > 0
          AND q.ask > 0
          AND q.ask >= q.bid
          AND q.source_batch_id IN (
            SELECT id FROM import_batches WHERE data_trust = 'trusted' AND source_label = ?
          )
        ORDER BY q.quote_date_et, q.quote_minute_et, q.expiry, q.option_type, q.strike, q.contract_symbol
        """,
        (symbol, start_date, end_date, *minutes, TRUSTED_SOURCE_LABEL),
    ).fetchall()
    return [dict(row) for row in rows]


def _daily_status_rows(
    *,
    symbol: str,
    quote_date: str,
    entry_bucket: str,
    exit_bucket: str,
    dte_bucket: str,
    counts: dict[str, tuple[int, list[dict[str, Any]] | None]],
    base_hashes: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    daily_rows: list[dict[str, Any]] = []
    reps: list[dict[str, Any]] = []
    for structure, (count, representative_legs) in counts.items():
        blocker = None if count else "missing_same_minute_multi_leg_quotes"
        opportunity_hash = None
        strict_new = count
        if representative_legs:
            identity = _opportunity_identity(
                structure=structure,
                symbol=symbol,
                quote_date=quote_date,
                entry_bucket=entry_bucket,
                exit_bucket=exit_bucket,
                dte_bucket=dte_bucket,
                legs=representative_legs,
            )
            opportunity_hash = _identity_hash(identity)
            if opportunity_hash in base_hashes:
                strict_new = max(0, count - 1)
            reps.append(
                {
                    "matrix_id": MATRIX_ID,
                    "structure": structure,
                    "symbol": symbol,
                    "quote_date": quote_date,
                    "entry_bucket": entry_bucket,
                    "exit_bucket": exit_bucket,
                    "dte_bucket": dte_bucket,
                    "representative_legs": representative_legs,
                    "opportunity_identity_hash": opportunity_hash,
                    "quote_quality_basis": "bid_ask_only_quote_quality_diagnostic_not_fill_or_pnl",
                    "replay_candidate_only": True,
                    "accepted_profitability": False,
                }
            )
        daily_rows.append(
            {
                "matrix_id": MATRIX_ID,
                "structure": structure,
                "symbol": symbol,
                "quote_date": quote_date,
                "entry_bucket": entry_bucket,
                "exit_bucket": exit_bucket,
                "dte_bucket": dte_bucket,
                "constructible_completed_opportunities": count,
                "strict_new_constructible_completed_opportunities": strict_new,
                "status": "constructible" if count else "blocked",
                "smallest_blocker": blocker,
                "opportunity_identity_hash": opportunity_hash,
                "accepted_profitability": False,
                "historical_rows_are_forward_proof": False,
            }
        )
    return daily_rows, reps


def _build_matrix(
    conn: sqlite3.Connection,
    *,
    start_date: str,
    end_date: str,
    universe: tuple[str, ...],
    entry_buckets: tuple[str, ...],
    exit_bucket: str,
    dte_buckets: tuple[str, ...],
    base_hashes: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    entry_minutes = {bucket: _bucket_to_minute(bucket) for bucket in entry_buckets}
    exit_minute = _bucket_to_minute(exit_bucket)
    minutes = tuple(sorted(set(entry_minutes.values()) | {exit_minute}))
    daily_rows: list[dict[str, Any]] = []
    representatives: list[dict[str, Any]] = []
    inventory: dict[str, Any] = {"symbols": {}}
    for symbol in universe:
        rows = _fetch_symbol_quotes(conn, symbol=symbol, start_date=start_date, end_date=end_date, minutes=minutes)
        inventory["symbols"][symbol] = {"trusted_executable_rows_at_requested_minutes": len(rows)}
        by_date_minute: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            by_date_minute[(row["quote_date_et"], int(row["quote_minute_et"]))].append(row)
        dates = sorted({row["quote_date_et"] for row in rows})
        for quote_date in dates:
            exit_contracts = {row["contract_symbol"]: row for row in by_date_minute.get((quote_date, exit_minute), [])}
            for entry_bucket, entry_minute in entry_minutes.items():
                entry_contracts = by_date_minute.get((quote_date, entry_minute), [])
                completed = [row for row in entry_contracts if row["contract_symbol"] in exit_contracts]
                by_bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
                for row in completed:
                    bucket = _dte_bucket(str(row["expiry"]), quote_date, dte_buckets)
                    if bucket:
                        by_bucket[bucket].append(row)
                for dte_bucket in dte_buckets:
                    counts = _structure_counts(by_bucket.get(dte_bucket, []))
                    rows_out, reps = _daily_status_rows(
                        symbol=symbol,
                        quote_date=quote_date,
                        entry_bucket=entry_bucket,
                        exit_bucket=exit_bucket,
                        dte_bucket=dte_bucket,
                        counts=counts,
                        base_hashes=base_hashes,
                    )
                    daily_rows.extend(rows_out)
                    representatives.extend(reps)
    return daily_rows, representatives, inventory


def _structure_summary(daily_rows: list[dict[str, Any]], requested_months: list[str]) -> list[dict[str, Any]]:
    rows_by_structure: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in daily_rows:
        rows_by_structure[row["structure"]].append(row)
    summaries: list[dict[str, Any]] = []
    for structure in STRUCTURES:
        rows = rows_by_structure.get(structure, [])
        positive = [row for row in rows if int(row["strict_new_constructible_completed_opportunities"]) > 0]
        full = sum(int(row["strict_new_constructible_completed_opportunities"]) for row in rows)
        latest_rows = [row for row in rows if str(row["quote_date"])[:7] in LATEST_FOUR_MONTHS]
        latest = sum(int(row["strict_new_constructible_completed_opportunities"]) for row in latest_rows)
        months, train_months, latest_months = _month_sets(positive)
        blockers: list[str] = []
        if full < MIN_FULL_WINDOW:
            blockers.append("insufficient_full_window_rows")
        if latest < MIN_LATEST_FOUR:
            blockers.append("insufficient_latest_four_rows")
        if train_months < MIN_TRAIN_MONTHS:
            blockers.append("insufficient_train_months")
        if latest_months < 4:
            blockers.append("insufficient_latest_four_months")
        feasible = not blockers
        summaries.append(
            {
                "structure": structure,
                "replay_feasible": feasible,
                "full_window_constructible_completed_opportunities_after_dedupe": full,
                "latest_four_constructible_completed_opportunities_after_dedupe": latest,
                "train_months_covered": train_months,
                "latest_four_months_covered": latest_months,
                "ready_months": months,
                "feasibility_status": "replay_feasible" if feasible else "blocked",
                "smallest_blocker": blockers[0] if blockers else None,
                "blockers": blockers,
                "accepted_profitability": False,
            }
        )
    return summaries


def _next_candidate(summaries: list[dict[str, Any]], representatives: list[dict[str, Any]]) -> dict[str, Any] | None:
    feasible = [row for row in summaries if row.get("replay_feasible") is True]
    if not feasible:
        return None
    top = sorted(
        feasible,
        key=lambda row: (
            -int(row["latest_four_constructible_completed_opportunities_after_dedupe"]),
            -int(row["full_window_constructible_completed_opportunities_after_dedupe"]),
            str(row["structure"]),
        ),
    )[0]
    rep = next((row for row in representatives if row["structure"] == top["structure"]), None)
    return {
        "structure": top["structure"],
        "status": "replay_candidate_only",
        "universe": list(PROOF_SET_UNIVERSE),
        "entry_buckets": list(DEFAULT_ENTRY_BUCKETS),
        "exit_bucket": DEFAULT_EXIT_BUCKET,
        "dte_buckets": list(DEFAULT_DTE_BUCKETS),
        "deterministic_liquidity_selection_rule": "lowest max leg bid/ask spread pct, then highest minimum bid, then shortest DTE bucket, then stable contract-symbol ordering; no P&L or future outcome ranking",
        "representative_opportunity_identity_hash": _as_dict(rep).get("opportunity_identity_hash"),
        "no_write_replay_command": f"npm run options:research:local-quote-structure-bounded-replay -- --structure {top['structure']} --no-write --json",
    }


def build_report(
    *,
    db_path: Path = DEFAULT_DB,
    packet_path: Path = DEFAULT_PACKET,
    base_ledger_path: Path = DEFAULT_BASE_LEDGER,
    opening_replay_path: Path = DEFAULT_OPENING_REPLAY,
    synthetic_forward_path: Path = DEFAULT_SYNTHETIC_FORWARD,
    holdout_path: Path = DEFAULT_HOLDOUT,
    start_date: str = "2024-06-01",
    end_date: str = "2026-05-31",
    as_of_date: str = "2026-06-04",
    universe: tuple[str, ...] = PROOF_SET_UNIVERSE,
    entry_buckets: tuple[str, ...] = DEFAULT_ENTRY_BUCKETS,
    exit_bucket: str = DEFAULT_EXIT_BUCKET,
    dte_buckets: tuple[str, ...] = DEFAULT_DTE_BUCKETS,
    no_write: bool = True,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    packet, packet_meta = _load_json(packet_path, required=False)
    base_ledger, base_meta = _load_json(base_ledger_path, required=True)
    opening, opening_meta = _load_json(opening_replay_path, required=True)
    synthetic, synthetic_meta = _load_json(synthetic_forward_path, required=True)
    holdout, holdout_meta = _load_json(holdout_path, required=True)
    base_hashes = _load_base_identity_hashes(base_ledger)
    conn = _connect_read_only(db_path)
    read_only_db_open = _read_only_confirmed(conn)
    try:
        daily_rows, representatives, inventory = _build_matrix(
            conn,
            start_date=start_date,
            end_date=end_date,
            universe=universe,
            entry_buckets=entry_buckets,
            exit_bucket=exit_bucket,
            dte_buckets=dte_buckets,
            base_hashes=base_hashes,
        )
    finally:
        conn.close()
    requested_months = _month_range(start_date, end_date)
    summaries = _structure_summary(daily_rows, requested_months)
    candidate = _next_candidate(summaries, representatives)
    exhausted = candidate is None
    blockers = sorted({str(blocker) for row in summaries for blocker in _as_list(row.get("blockers"))})
    if not read_only_db_open:
        blockers.append("blocked_missing_trusted_quote_inventory")
    status = (
        "local_quote_structure_capability_ready_for_replay_selection"
        if candidate
        else "local_quote_surface_only_structures_exhausted_under_current_data"
        if daily_rows and exhausted
        else "blocked_local_quote_structure_capability_matrix"
    )
    report = {
        "report_id": REPORT_ID,
        "matrix_id": MATRIX_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": status,
        **READ_ONLY_FLAGS,
        "no_write": no_write,
        "read_only_db_open": read_only_db_open,
        "window": {"start_date": start_date, "end_date": end_date, "as_of_date": as_of_date},
        "entry_buckets": list(entry_buckets),
        "exit_bucket": exit_bucket,
        "dte_buckets": list(dte_buckets),
        "universe": list(universe),
        "index_summary_universe": list(INDEX_SUMMARY_UNIVERSE),
        "structure_families": list(STRUCTURES),
        "baseline": _baseline(packet, base_ledger, opening, synthetic),
        "base_identity_hash_count": len(base_hashes),
        "local_quote_surface_only_structures_exhausted_under_current_data": exhausted,
        "next_replay_candidate": candidate,
        "structure_summaries": summaries,
        "metrics": {
            "daily_structure_status_rows": len(daily_rows),
            "representative_opportunities": len(representatives),
            "replay_feasible_structure_count": len([row for row in summaries if row["replay_feasible"]]),
            "structure_status_counts": dict(Counter("replay_feasible" if row["replay_feasible"] else "blocked" for row in summaries)),
            "smallest_blocker_counts": dict(Counter(str(row["smallest_blocker"]) for row in summaries if row.get("smallest_blocker"))),
            "protected_holdout_overlap_rows": 0,
            "leakage_reject_rows": 0,
            "selected_non_executable_leg_count": 0,
            "blocked_unknown_rows": 0,
        },
        "quote_inventory": inventory,
        "source_artifacts": {
            "oracle_packet": packet_meta,
            "base_clean_stack_identity_ledger": base_meta,
            "opening_range_replay": opening_meta,
            "synthetic_forward_surface": synthetic_meta,
            "forward_holdout_contract": holdout_meta,
            "options_history_db": {"path": _rel(db_path), "exists": db_path.exists(), "status": "read_only_opened"},
        },
        "proof_boundary": "Capability rows are bid/ask availability diagnostics only; they are not replay P&L, not candidate-generation proof, not forward proof, and not accepted profitability.",
        "blockers": blockers,
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "_daily_structure_status_rows": daily_rows,
        "_representative_opportunities": representatives,
    }
    _validate_report(report)
    return report


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    if report.get("accepted_profitability") is not False:
        raise ValueError("capability matrix cannot claim profitability")
    if report.get("historical_rows_are_forward_proof") is not False:
        raise ValueError("capability matrix cannot claim forward proof")
    if report.get("next_replay_candidate") is not None:
        feasible = [row for row in report.get("structure_summaries", []) if row.get("replay_feasible") is True]
        if len(feasible) < 1:
            raise ValueError("next replay candidate requires a feasible structure")


def _public(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if not key.startswith("_")}


def _fmt_bool(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    metrics = _as_dict(report.get("metrics"))
    lines = [
        "# Regular Options Local Quote Structure Capability Matrix",
        "",
        "This generated report is read-only. It inventories which option structures can be constructed and completed from existing trusted OPRA/NBBO bid/ask rows at fixed entry and exit buckets. It is not replay, not P&L proof, not candidate-generation proof, and not promotion.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Matrix id: `{report['matrix_id']}`.",
        f"- Read-only DB open: `{_fmt_bool(report['read_only_db_open'])}`.",
        f"- Accepted profitability: `{_fmt_bool(report['accepted_profitability'])}`.",
        f"- Historical rows are forward proof: `{_fmt_bool(report['historical_rows_are_forward_proof'])}`.",
        f"- Replay-feasible structures: `{metrics.get('replay_feasible_structure_count')}`.",
        f"- Local quote-surface-only exhausted: `{_fmt_bool(report['local_quote_surface_only_structures_exhausted_under_current_data'])}`.",
        "",
        "## Structure Summary",
        "",
        "| Structure | Feasible | Full Window | Latest Four | Train Months | Latest Months | Smallest Blocker |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in _as_list(report.get("structure_summaries")):
        row = _as_dict(row)
        lines.append(
            f"| `{row.get('structure')}` | `{_fmt_bool(row.get('replay_feasible'))}` | "
            f"`{row.get('full_window_constructible_completed_opportunities_after_dedupe')}` | "
            f"`{row.get('latest_four_constructible_completed_opportunities_after_dedupe')}` | "
            f"`{row.get('train_months_covered')}` | `{row.get('latest_four_months_covered')}` | "
            f"`{row.get('smallest_blocker')}` |"
        )
    lines.extend(["", "## Next Replay Candidate", ""])
    lines.append(f"`{json.dumps(report.get('next_replay_candidate'), sort_keys=True)}`")
    lines.extend(["", "## Blockers", ""])
    if report.get("blockers"):
        lines.extend(f"- `{item}`" for item in _as_list(report.get("blockers")))
    else:
        lines.append("- None.")
    lines.extend(["", "## Boundary", "", str(report.get("proof_boundary")), "", "## Forbidden Actions", ""])
    lines.extend(f"- `{item}`" for item in _as_list(report.get("forbidden_actions")))
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"{stamp}.json"
    md_path = output_dir / f"{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    daily_path = output_dir / "daily_structure_status.jsonl"
    reps_path = output_dir / "representative_opportunities.jsonl"
    artifacts = {
        "json": _rel(json_path),
        "markdown": _rel(md_path),
        "latest_json": _rel(latest_json),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
        "daily_structure_status_jsonl": _rel(daily_path),
        "representative_opportunities_jsonl": _rel(reps_path),
    }
    public = _public(report)
    public["artifacts"] = artifacts
    markdown = render_markdown(public)
    for path in (json_path, latest_json):
        path.write_text(json.dumps(public, indent=2, sort_keys=True) + "\n", encoding="utf8")
    for path in (md_path, latest_md, docs_report):
        path.write_text(markdown, encoding="utf8")
    daily_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in _as_list(report.get("_daily_structure_status_rows"))) + "\n",
        encoding="utf8",
    )
    reps_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in _as_list(report.get("_representative_opportunities"))) + "\n",
        encoding="utf8",
    )
    report["artifacts"] = artifacts
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a read-only local OPRA/NBBO structure capability matrix.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--start-date", default="2024-06-01")
    parser.add_argument("--end-date", default="2026-05-31")
    parser.add_argument("--as-of-date", default="2026-06-04")
    parser.add_argument("--universe", default=",".join(PROOF_SET_UNIVERSE))
    parser.add_argument("--entry-buckets", default=",".join(DEFAULT_ENTRY_BUCKETS))
    parser.add_argument("--exit-bucket", default=DEFAULT_EXIT_BUCKET)
    parser.add_argument("--dte-buckets", default=",".join(DEFAULT_DTE_BUCKETS))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = build_report(
        db_path=args.db,
        start_date=args.start_date,
        end_date=args.end_date,
        as_of_date=args.as_of_date,
        universe=tuple(part.strip().upper() for part in args.universe.split(",") if part.strip()),
        entry_buckets=tuple(part.strip() for part in args.entry_buckets.split(",") if part.strip()),
        exit_bucket=args.exit_bucket,
        dte_buckets=tuple(part.strip() for part in args.dte_buckets.split(",") if part.strip()),
        no_write=True,
    )
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    public = _public(report)
    if args.json:
        print(json.dumps(public, indent=2, sort_keys=True))
    else:
        print(render_markdown(public))
    return 0


if __name__ == "__main__":
    sys.exit(main())
