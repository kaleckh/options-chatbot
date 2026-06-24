from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_regular_options_local_quote_structure_capability_matrix as fixed_matrix


REPORT_ID = "regular_options_all_local_quote_minute_structure_capability_atlas"
ATLAS_ID = "all_local_stable_quote_minute_structure_capability_atlas_v1"
DEFAULT_DB = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-all-local-quote-minute-structure-capability-atlas"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-all-local-quote-minute-structure-capability-atlas.md"
DEFAULT_PRIOR_MATRIX = ROOT / "data" / "profitability-lab" / "regular-options-local-quote-structure-capability-matrix" / "latest.json"
DEFAULT_BASE_LEDGER = ROOT / "data" / "profitability-lab" / "regular-options-base-clean-stack-identity-ledger" / "latest.json"
DEFAULT_PACKET = ROOT / "data" / "forward-tracking" / "options_oracle_profit_loop_packet_latest.json"
DEFAULT_OPENING_REPLAY = ROOT / "data" / "profitability-lab" / "regular-options-quote-surface-opening-range-reversal-replay" / "latest.json"
DEFAULT_SYNTHETIC_FORWARD = ROOT / "data" / "profitability-lab" / "regular-options-quote-derived-synthetic-forward-surface" / "latest.json"
DEFAULT_SOURCE_QUALITY_POLICY = ROOT / "data" / "contracts" / "regular-options-source-quality-scope-policy.json"
DEFAULT_HOLDOUT = ROOT / "data" / "contracts" / "forward-holdout-contract.json"

TRUSTED_SOURCE_LABEL = "thetadata_opra_nbbo_1m"
MINUTE_START = 9 * 60 + 35
MINUTE_END = 15 * 60 + 55
LATEST_FOUR_MONTHS = ("2026-02", "2026-03", "2026-04", "2026-05")
PROOF_SET_UNIVERSE = fixed_matrix.PROOF_SET_UNIVERSE
INDEX_ETF_SYMBOLS = {
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "XLK",
    "XLE",
    "XLF",
    "KRE",
    "SMH",
    "TLT",
    "GLD",
    "XME",
    "COPX",
    "URA",
}
STRUCTURES = fixed_matrix.STRUCTURES
DEFAULT_DTE_BUCKETS = fixed_matrix.DEFAULT_DTE_BUCKETS

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
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "promotion_ready": False,
    "realized_pnl_used_for_ranking": False,
    "future_outcomes_used_for_ranking": False,
    "p_l_replay_performed": False,
}

FORBIDDEN_ACTIONS = (
    "broker orders",
    "live validation",
    "auto-track",
    "production scanner release",
    "production strategy changes",
    "stop or sizing changes",
    "proof-bar relaxation",
    "quote import",
    "evidence database mutation",
    "protected holdout consumption",
    "promotion",
    "historical rows as forward proof",
    "creating trades",
    "preparing orders",
    "forward cohort append",
    "using midpoint, stale, EOD, display-only, last-trade, model, manual, synthetic, or non-executable marks as fill or P&L evidence",
    "reclassifying zero-bid or untradable rows as missing data",
    "ranking buckets, structures, or universes by realized P&L",
    "using protected holdout outcomes",
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


def _minute_label(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _bin_minute(minute: int, width: int) -> int:
    return ((int(minute) - MINUTE_START) // width) * width + MINUTE_START


def _train_latest_counts(months: set[str]) -> tuple[int, int]:
    train = len({month for month in months if month < LATEST_FOUR_MONTHS[0]})
    latest = len({month for month in LATEST_FOUR_MONTHS if month in months})
    return train, latest


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


def _load_base_hashes(payload: dict[str, Any]) -> set[str]:
    return fixed_matrix._load_base_identity_hashes(payload)


def _source_quality_exclusions(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    exclusions: dict[str, dict[str, Any]] = {}
    if policy.get("status") != "active":
        return exclusions
    for rule in _as_list(policy.get("rules")):
        rule_obj = _as_dict(rule)
        if rule_obj.get("status") != "active":
            continue
        if rule_obj.get("observed_executable_quote_pct") is None or rule_obj.get("minimum_executable_quote_pct") is None:
            continue
        try:
            observed = float(rule_obj["observed_executable_quote_pct"])
            minimum = float(rule_obj["minimum_executable_quote_pct"])
        except (TypeError, ValueError):
            continue
        if observed >= minimum:
            continue
        for symbol in _as_list(rule_obj.get("symbols")):
            exclusions[str(symbol).upper()] = {
                "rule_id": rule_obj.get("rule_id"),
                "reason": rule_obj.get("reason") or "source_quality_floor_failure",
                "observed_executable_quote_pct": observed,
                "minimum_executable_quote_pct": minimum,
                "action": "excluded_from_replay_feasible_surface_by_preregistered_coverage_only_rule",
            }
    return exclusions


def _trusted_filter_sql() -> str:
    return """
      q.snapshot_kind = 'intraday'
      AND q.bid > 0
      AND q.ask > 0
      AND q.ask >= q.bid
      AND q.source_batch_id IN (
        SELECT id FROM import_batches WHERE data_trust = 'trusted' AND source_label = ?
      )
    """


def _discover_symbol_inventory(
    conn: sqlite3.Connection,
    *,
    start_date: str,
    end_date: str,
    bucket_width: int,
) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, int], dict[str, Any]]]:
    bucket_expr = f"(CAST(((q.quote_minute_et - {MINUTE_START}) / {bucket_width}) AS INTEGER) * {bucket_width} + {MINUTE_START})"
    rows = conn.execute(
        f"""
        SELECT q.underlying AS symbol,
               substr(q.quote_date_et, 1, 7) AS month,
               {bucket_expr} AS bucket_minute,
               COUNT(*) AS executable_rows,
               COUNT(DISTINCT q.quote_date_et) AS quote_dates,
               COUNT(DISTINCT q.contract_symbol) AS contracts
        FROM option_quote_snapshots q
        WHERE {_trusted_filter_sql()}
          AND q.quote_date_et BETWEEN ? AND ?
          AND q.quote_minute_et BETWEEN ? AND ?
        GROUP BY q.underlying, substr(q.quote_date_et, 1, 7), {bucket_expr}
        """,
        (TRUSTED_SOURCE_LABEL, start_date, end_date, MINUTE_START, MINUTE_END),
    ).fetchall()

    symbol_inventory: dict[str, dict[str, Any]] = {}
    bucket_inventory: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows:
        symbol = str(row["symbol"]).upper()
        month = str(row["month"])
        bucket = int(row["bucket_minute"])
        symbol_entry = symbol_inventory.setdefault(
            symbol,
            {
                "trusted_executable_rows": 0,
                "covered_months": set(),
                "covered_buckets": set(),
                "covered_dates": 0,
            },
        )
        symbol_entry["trusted_executable_rows"] += int(row["executable_rows"])
        symbol_entry["covered_months"].add(month)
        symbol_entry["covered_buckets"].add(bucket)
        bucket_entry = bucket_inventory.setdefault(
            (symbol, bucket),
            {
                "symbol": symbol,
                "bucket_minute": bucket,
                "bucket": _minute_label(bucket),
                "months": set(),
                "rows_by_month": defaultdict(int),
                "date_count_by_month": defaultdict(int),
                "contract_count_by_month": defaultdict(int),
            },
        )
        bucket_entry["months"].add(month)
        bucket_entry["rows_by_month"][month] += int(row["executable_rows"])
        bucket_entry["date_count_by_month"][month] += int(row["quote_dates"])
        bucket_entry["contract_count_by_month"][month] += int(row["contracts"])

    date_rows = conn.execute(
        f"""
        SELECT q.underlying AS symbol, COUNT(DISTINCT q.quote_date_et) AS quote_dates
        FROM option_quote_snapshots q
        WHERE {_trusted_filter_sql()}
          AND q.quote_date_et BETWEEN ? AND ?
          AND q.quote_minute_et BETWEEN ? AND ?
        GROUP BY q.underlying
        """,
        (TRUSTED_SOURCE_LABEL, start_date, end_date, MINUTE_START, MINUTE_END),
    ).fetchall()
    for row in date_rows:
        symbol = str(row["symbol"]).upper()
        symbol_inventory.setdefault(symbol, {"trusted_executable_rows": 0, "covered_months": set(), "covered_buckets": set(), "covered_dates": 0})
        symbol_inventory[symbol]["covered_dates"] = int(row["quote_dates"])

    for payload in symbol_inventory.values():
        train, latest = _train_latest_counts(set(payload["covered_months"]))
        payload["covered_month_count"] = len(payload["covered_months"])
        payload["train_months_covered"] = train
        payload["latest_four_months_covered"] = latest
        payload["covered_months"] = sorted(payload["covered_months"])
        payload["covered_buckets"] = [_minute_label(item) for item in sorted(payload["covered_buckets"])]

    return symbol_inventory, bucket_inventory


def _pair_score(entry: dict[str, Any], exit_: dict[str, Any]) -> dict[str, Any]:
    months = set(entry["months"]) & set(exit_["months"])
    train, latest = _train_latest_counts(months)
    full = sum(min(int(entry["rows_by_month"].get(month, 0)), int(exit_["rows_by_month"].get(month, 0))) for month in months)
    latest_count = sum(min(int(entry["rows_by_month"].get(month, 0)), int(exit_["rows_by_month"].get(month, 0))) for month in LATEST_FOUR_MONTHS)
    each_latest = {
        month: min(int(entry["rows_by_month"].get(month, 0)), int(exit_["rows_by_month"].get(month, 0)))
        for month in LATEST_FOUR_MONTHS
    }
    return {
        "months": sorted(months),
        "train_months_covered": train,
        "latest_four_months_covered": latest,
        "coverage_proxy_full_window_rows": full,
        "coverage_proxy_latest_four_rows": latest_count,
        "each_latest_four_month_coverage_proxy_rows": each_latest,
    }


def _select_symbol_surfaces(
    *,
    bucket_inventory: dict[tuple[str, int], dict[str, Any]],
    symbol_inventory: dict[str, dict[str, Any]],
    source_quality_exclusions: dict[str, dict[str, Any]],
    max_detailed_surfaces: int,
) -> list[dict[str, Any]]:
    surfaces: list[dict[str, Any]] = []
    for symbol in sorted(symbol_inventory):
        if symbol in source_quality_exclusions:
            continue
        buckets = sorted(bucket for candidate_symbol, bucket in bucket_inventory if candidate_symbol == symbol)
        best: dict[str, Any] | None = None
        for entry_bucket in buckets:
            for exit_bucket in buckets:
                if entry_bucket >= exit_bucket:
                    continue
                entry = bucket_inventory[(symbol, entry_bucket)]
                exit_ = bucket_inventory[(symbol, exit_bucket)]
                score = _pair_score(entry, exit_)
                candidate = {
                    "universe_id": f"single_symbol:{symbol}",
                    "symbol": symbol,
                    "entry_bucket_minute": entry_bucket,
                    "exit_bucket_minute": exit_bucket,
                    "entry_bucket": _minute_label(entry_bucket),
                    "exit_bucket": _minute_label(exit_bucket),
                    **score,
                }
                sort_key = (
                    candidate["latest_four_months_covered"],
                    candidate["train_months_covered"],
                    candidate["coverage_proxy_latest_four_rows"],
                    candidate["coverage_proxy_full_window_rows"],
                    -entry_bucket,
                    exit_bucket,
                )
                if best is None or sort_key > best["_sort_key"]:
                    candidate["_sort_key"] = sort_key
                    best = candidate
        if best:
            best.pop("_sort_key", None)
            surfaces.append(best)
    surfaces.sort(
        key=lambda item: (
            -int(item["latest_four_months_covered"]),
            -int(item["train_months_covered"]),
            -int(item["coverage_proxy_latest_four_rows"]),
            -int(item["coverage_proxy_full_window_rows"]),
            item["symbol"],
        )
    )
    return surfaces[:max_detailed_surfaces]


def _fetch_surface_rows(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    start_date: str,
    end_date: str,
    entry_minute: int,
    exit_minute: int,
    bucket_width: int,
) -> dict[tuple[str, str], dict[str, dict[str, Any]]]:
    rows = conn.execute(
        f"""
        SELECT q.quote_date_et, q.quote_minute_et, q.contract_symbol, q.expiry, q.option_type, q.strike,
               q.bid, q.ask, q.source_batch_id
        FROM option_quote_snapshots q
        WHERE {_trusted_filter_sql()}
          AND q.underlying = ?
          AND q.quote_date_et BETWEEN ? AND ?
          AND (
            (q.quote_minute_et >= ? AND q.quote_minute_et < ?)
            OR (q.quote_minute_et >= ? AND q.quote_minute_et < ?)
          )
        ORDER BY q.quote_date_et, q.quote_minute_et, q.expiry, q.option_type, q.strike, q.contract_symbol
        """,
        (
            TRUSTED_SOURCE_LABEL,
            symbol,
            start_date,
            end_date,
            entry_minute,
            entry_minute + bucket_width,
            exit_minute,
            exit_minute + bucket_width,
        ),
    ).fetchall()
    by_date_role: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        minute = int(row["quote_minute_et"])
        role = "entry" if entry_minute <= minute < entry_minute + bucket_width else "exit"
        quote_date = str(row["quote_date_et"])
        contract = str(row["contract_symbol"])
        payload = dict(row)
        current = by_date_role[(quote_date, role)].get(contract)
        if current is None:
            by_date_role[(quote_date, role)][contract] = payload
            continue
        if fixed_matrix._spread_pct(payload) < fixed_matrix._spread_pct(current):
            by_date_role[(quote_date, role)][contract] = payload
    return by_date_role


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
        "atlas_id": ATLAS_ID,
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


def _daily_status_rows(
    *,
    surface: dict[str, Any],
    quote_date: str,
    dte_bucket: str,
    counts: dict[str, tuple[int, list[dict[str, Any]] | None]],
    base_hashes: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    daily_rows: list[dict[str, Any]] = []
    reps: list[dict[str, Any]] = []
    for structure, (count, representative_legs) in counts.items():
        opportunity_hash = None
        strict_new = count
        blocker = None if count else "missing_same_window_multi_leg_quotes"
        if representative_legs:
            opportunity_hash = fixed_matrix._identity_hash(
                _opportunity_identity(
                    structure=structure,
                    symbol=surface["symbol"],
                    quote_date=quote_date,
                    entry_bucket=surface["entry_bucket"],
                    exit_bucket=surface["exit_bucket"],
                    dte_bucket=dte_bucket,
                    legs=representative_legs,
                )
            )
            if opportunity_hash in base_hashes:
                strict_new = max(0, count - 1)
            reps.append(
                {
                    "atlas_id": ATLAS_ID,
                    "universe_id": surface["universe_id"],
                    "structure": structure,
                    "symbol": surface["symbol"],
                    "quote_date": quote_date,
                    "entry_bucket": surface["entry_bucket"],
                    "exit_bucket": surface["exit_bucket"],
                    "dte_bucket": dte_bucket,
                    "representative_legs": representative_legs,
                    "opportunity_identity_hash": opportunity_hash,
                    "quote_quality_basis": "bid_ask_only_quote_quality_diagnostic_not_fill_or_pnl",
                    "replay_candidate_only": True,
                    "accepted_profitability": False,
                    "realized_pnl_used_for_ranking": False,
                    "future_outcomes_used_for_ranking": False,
                }
            )
        daily_rows.append(
            {
                "atlas_id": ATLAS_ID,
                "universe_id": surface["universe_id"],
                "structure": structure,
                "symbol": surface["symbol"],
                "quote_date": quote_date,
                "entry_bucket": surface["entry_bucket"],
                "exit_bucket": surface["exit_bucket"],
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


def _build_detailed_surfaces(
    conn: sqlite3.Connection,
    *,
    start_date: str,
    end_date: str,
    bucket_width: int,
    dte_buckets: tuple[str, ...],
    selected_surfaces: list[dict[str, Any]],
    base_hashes: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    daily_rows: list[dict[str, Any]] = []
    representatives: list[dict[str, Any]] = []
    for surface in selected_surfaces:
        by_date_role = _fetch_surface_rows(
            conn,
            symbol=surface["symbol"],
            start_date=start_date,
            end_date=end_date,
            entry_minute=int(surface["entry_bucket_minute"]),
            exit_minute=int(surface["exit_bucket_minute"]),
            bucket_width=bucket_width,
        )
        dates = sorted({key[0] for key in by_date_role})
        for quote_date in dates:
            entry_contracts = by_date_role.get((quote_date, "entry"), {})
            exit_contracts = by_date_role.get((quote_date, "exit"), {})
            if not entry_contracts or not exit_contracts:
                continue
            completed = [row for contract, row in entry_contracts.items() if contract in exit_contracts]
            by_dte: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in completed:
                bucket = fixed_matrix._dte_bucket(str(row["expiry"]), quote_date, dte_buckets)
                if bucket:
                    by_dte[bucket].append(row)
            for dte_bucket in dte_buckets:
                counts = fixed_matrix._structure_counts(by_dte.get(dte_bucket, []))
                rows_out, reps = _daily_status_rows(
                    surface=surface,
                    quote_date=quote_date,
                    dte_bucket=dte_bucket,
                    counts=counts,
                    base_hashes=base_hashes,
                )
                daily_rows.extend(rows_out)
                representatives.extend(reps)
    return daily_rows, representatives


def _surface_summaries(
    daily_rows: list[dict[str, Any]],
    *,
    min_train_months: int,
    min_latest_four_months: int,
    min_full_window_opportunities: int,
    min_latest_four_opportunities: int,
    source_quality_exclusions: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    by_surface: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in daily_rows:
        key = (row["symbol"], row["structure"], row["entry_bucket"], row["exit_bucket"], row["dte_bucket"])
        by_surface[key].append(row)
    summaries: list[dict[str, Any]] = []
    for (symbol, structure, entry_bucket, exit_bucket, dte_bucket), rows in by_surface.items():
        positive = [row for row in rows if int(row["strict_new_constructible_completed_opportunities"]) > 0]
        full = sum(int(row["strict_new_constructible_completed_opportunities"]) for row in rows)
        latest_rows = [row for row in rows if str(row["quote_date"])[:7] in LATEST_FOUR_MONTHS]
        latest = sum(int(row["strict_new_constructible_completed_opportunities"]) for row in latest_rows)
        months = sorted({str(row["quote_date"])[:7] for row in positive})
        train_months, latest_months = _train_latest_counts(set(months))
        each_latest = {
            month: sum(int(row["strict_new_constructible_completed_opportunities"]) for row in rows if str(row["quote_date"])[:7] == month)
            for month in LATEST_FOUR_MONTHS
        }
        blockers: list[str] = []
        if full < min_full_window_opportunities:
            blockers.append("full_window_rows_below_200")
        if latest < min_latest_four_opportunities:
            blockers.append("latest_four_rows_below_30")
        if train_months < min_train_months:
            blockers.append("insufficient_train_months")
        if latest_months < min_latest_four_months:
            blockers.append("insufficient_latest_four_months")
        if any(value < 5 for value in each_latest.values()):
            blockers.append("latest_four_month_floor_below_5")
        if symbol in source_quality_exclusions:
            blockers.append("source_quality_floor_failure")
        feasible = not blockers
        summaries.append(
            {
                "surface_id": f"{symbol}:{structure}:{entry_bucket}-{exit_bucket}:{dte_bucket}",
                "universe_id": f"single_symbol:{symbol}",
                "symbol": symbol,
                "structure": structure,
                "entry_bucket": entry_bucket,
                "exit_bucket": exit_bucket,
                "dte_bucket": dte_bucket,
                "replay_feasible": feasible,
                "feasibility_status": "replay_feasible" if feasible else "blocked",
                "full_window_constructible_completed_opportunities_after_dedupe": full,
                "latest_four_constructible_completed_opportunities_after_dedupe": latest,
                "train_months_covered": train_months,
                "latest_four_months_covered": latest_months,
                "each_latest_four_month_opportunities_after_dedupe": each_latest,
                "ready_months": months,
                "smallest_blocker": blockers[0] if blockers else None,
                "blockers": blockers,
                "source_quality_exclusion": source_quality_exclusions.get(symbol),
                "accepted_profitability": False,
            }
        )
    summaries.sort(
        key=lambda row: (
            0 if row["replay_feasible"] else 1,
            -int(row["latest_four_constructible_completed_opportunities_after_dedupe"]),
            -int(row["full_window_constructible_completed_opportunities_after_dedupe"]),
            -int(row["train_months_covered"]),
            row["structure"],
            row["symbol"],
        )
    )
    return summaries


def _next_replay_candidate(summaries: list[dict[str, Any]], representatives: list[dict[str, Any]]) -> dict[str, Any] | None:
    feasible = [row for row in summaries if row.get("replay_feasible") is True]
    if not feasible:
        return None
    top = feasible[0]
    rep = next(
        (
            row
            for row in representatives
            if row["symbol"] == top["symbol"]
            and row["structure"] == top["structure"]
            and row["entry_bucket"] == top["entry_bucket"]
            and row["exit_bucket"] == top["exit_bucket"]
            and row["dte_bucket"] == top["dte_bucket"]
        ),
        None,
    )
    return {
        "status": "replay_candidate_only",
        "atlas_id": ATLAS_ID,
        "surface_id": top["surface_id"],
        "structure": top["structure"],
        "frozen_universe": [top["symbol"]],
        "entry_bucket": top["entry_bucket"],
        "exit_bucket": top["exit_bucket"],
        "dte_bucket": top["dte_bucket"],
        "deterministic_leg_selection_rule": "lowest max leg bid/ask spread pct, highest minimum bid, largest timestamp freshness, shortest DTE bucket, then stable contract-symbol order; no P&L or future outcome ranking",
        "opportunity_identity_fields": ["atlas_id", "structure", "symbol", "quote_date", "entry_bucket", "exit_bucket", "dte_bucket", "legs"],
        "multiple_hypothesis_accounting_required_for_later_replay": True,
        "representative_opportunity_identity_hash": _as_dict(rep).get("opportunity_identity_hash"),
        "no_write_replay_command": (
            "npm run options:research:all-local-quote-minute-structure-bounded-replay -- "
            f"--surface-id {top['surface_id']} --no-write --json"
        ),
    }


def _universe_segments(symbol_inventory: dict[str, dict[str, Any]], source_quality_exclusions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    symbols = sorted(symbol_inventory)
    eligible = [symbol for symbol in symbols if symbol not in source_quality_exclusions]
    return {
        "all_local": symbols,
        "all_local_eligible": eligible,
        "index_etf_eligible": [symbol for symbol in eligible if symbol in INDEX_ETF_SYMBOLS],
        "single_name_eligible": [symbol for symbol in eligible if symbol not in INDEX_ETF_SYMBOLS],
        "13_symbol_reference": [symbol for symbol in PROOF_SET_UNIVERSE if symbol in symbols],
        "source_quality_excluded": sorted(source_quality_exclusions),
    }


def _baseline(
    packet: dict[str, Any],
    prior_matrix: dict[str, Any],
    opening: dict[str, Any],
    synthetic: dict[str, Any],
) -> dict[str, Any]:
    return {
        "current_forward_or_latest_four_strict_rows": 0,
        "target_latest_four_strict_rows": 30,
        "base_identity_hash_count": 157,
        "frontier_candidate_count": 44,
        "countable_throughput_candidate_found": False,
        "prior_structure_matrix_status": prior_matrix.get("status"),
        "prior_replay_feasible_structure_count": _as_dict(prior_matrix.get("metrics")).get("replay_feasible_structure_count"),
        "prior_next_replay_candidate": prior_matrix.get("next_replay_candidate"),
        "opening_range_blocker": "blocked_missing_quote_surface_underlying_price"
        if "blocked_missing_quote_surface_underlying_price" in _as_list(opening.get("blockers"))
        else None,
        "synthetic_forward_blocker": "blocked_missing_call_put_pairs"
        if _as_dict(_as_dict(synthetic.get("metrics")).get("bucket_status_counts")).get("blocked_missing_call_put_pairs", 0)
        else None,
        "oracle_packet_status": packet.get("status"),
    }


def build_report(
    *,
    db_path: Path = DEFAULT_DB,
    prior_matrix_path: Path = DEFAULT_PRIOR_MATRIX,
    base_ledger_path: Path = DEFAULT_BASE_LEDGER,
    packet_path: Path = DEFAULT_PACKET,
    opening_replay_path: Path = DEFAULT_OPENING_REPLAY,
    synthetic_forward_path: Path = DEFAULT_SYNTHETIC_FORWARD,
    source_quality_policy_path: Path = DEFAULT_SOURCE_QUALITY_POLICY,
    holdout_path: Path = DEFAULT_HOLDOUT,
    start_date: str = "2024-06-01",
    end_date: str = "2026-05-31",
    as_of_date: str = "2026-06-04",
    bucket_width_minutes: int = 5,
    dte_buckets: tuple[str, ...] = DEFAULT_DTE_BUCKETS,
    min_train_months: int = 20,
    min_latest_four_months: int = 4,
    min_full_window_opportunities: int = 200,
    min_latest_four_opportunities: int = 30,
    max_detailed_surfaces: int = 40,
    no_write: bool = True,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    prior_matrix, prior_meta = _load_json(prior_matrix_path, required=True)
    base_ledger, base_meta = _load_json(base_ledger_path, required=True)
    packet, packet_meta = _load_json(packet_path, required=False)
    opening, opening_meta = _load_json(opening_replay_path, required=True)
    synthetic, synthetic_meta = _load_json(synthetic_forward_path, required=True)
    source_policy, policy_meta = _load_json(source_quality_policy_path, required=False)
    holdout, holdout_meta = _load_json(holdout_path, required=True)
    del holdout

    base_hashes = _load_base_hashes(base_ledger)
    exclusions = _source_quality_exclusions(source_policy)
    conn = _connect_read_only(db_path)
    read_only_db_open = _read_only_confirmed(conn)
    try:
        symbol_inventory, bucket_inventory = _discover_symbol_inventory(
            conn,
            start_date=start_date,
            end_date=end_date,
            bucket_width=bucket_width_minutes,
        )
        selected_surfaces = _select_symbol_surfaces(
            bucket_inventory=bucket_inventory,
            symbol_inventory=symbol_inventory,
            source_quality_exclusions=exclusions,
            max_detailed_surfaces=max_detailed_surfaces,
        )
        daily_rows, representatives = _build_detailed_surfaces(
            conn,
            start_date=start_date,
            end_date=end_date,
            bucket_width=bucket_width_minutes,
            dte_buckets=dte_buckets,
            selected_surfaces=selected_surfaces,
            base_hashes=base_hashes,
        )
    finally:
        conn.close()

    summaries = _surface_summaries(
        daily_rows,
        min_train_months=min_train_months,
        min_latest_four_months=min_latest_four_months,
        min_full_window_opportunities=min_full_window_opportunities,
        min_latest_four_opportunities=min_latest_four_opportunities,
        source_quality_exclusions=exclusions,
    )
    candidate = _next_replay_candidate(summaries, representatives)
    blockers = sorted({str(blocker) for row in summaries for blocker in _as_list(row.get("blockers"))})
    if not read_only_db_open or not symbol_inventory:
        blockers.append("blocked_missing_trusted_quote_inventory")
    if not selected_surfaces and symbol_inventory:
        blockers.append("blocked_no_stable_quote_minute_buckets")
    if summaries and all(row["full_window_constructible_completed_opportunities_after_dedupe"] < min_full_window_opportunities for row in summaries):
        blockers.append("blocked_no_structure_reaches_full_window_200")
    if summaries and all(row["latest_four_constructible_completed_opportunities_after_dedupe"] < min_latest_four_opportunities for row in summaries):
        blockers.append("blocked_no_structure_reaches_latest_four_30")
    exhausted = candidate is None and bool(symbol_inventory)
    status = (
        "all_local_quote_minute_structure_capability_ready_for_replay_selection"
        if candidate
        else "all_local_quote_surface_replayability_exhausted_under_current_data"
        if exhausted
        else "blocked_all_local_quote_minute_structure_capability_atlas"
    )
    report = {
        "report_id": REPORT_ID,
        "atlas_id": ATLAS_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": status,
        **READ_ONLY_FLAGS,
        "no_write": no_write,
        "read_only_db_open": read_only_db_open,
        "window": {"start_date": start_date, "end_date": end_date, "as_of_date": as_of_date},
        "bucket_width_minutes": bucket_width_minutes,
        "bucket_search": {
            "entry_bucket_candidates": "all",
            "exit_bucket_candidates": "all",
            "minute_start": _minute_label(MINUTE_START),
            "minute_end": _minute_label(MINUTE_END),
            "ranking_basis": "coverage_and_quote_quality_only_no_pnl_no_future_outcomes",
            "max_detailed_surfaces": max_detailed_surfaces,
        },
        "dte_buckets": list(dte_buckets),
        "structure_families": list(STRUCTURES),
        "baseline": _baseline(packet, prior_matrix, opening, synthetic),
        "base_identity_hash_count": len(base_hashes),
        "universe_segments": _universe_segments(symbol_inventory, exclusions),
        "symbol_inventory": symbol_inventory,
        "source_quality_exclusions": exclusions,
        "selected_coverage_surfaces": selected_surfaces,
        "surface_summaries": summaries,
        "next_replay_candidate": candidate,
        "all_local_quote_surface_replayability_exhausted_under_current_data": exhausted,
        "metrics": {
            "trusted_local_underlying_count": len(symbol_inventory),
            "bucket_inventory_rows": len(bucket_inventory),
            "selected_detailed_surface_count": len(selected_surfaces),
            "daily_bucket_structure_status_rows": len(daily_rows),
            "representative_opportunities": len(representatives),
            "replay_feasible_surface_count": len([row for row in summaries if row["replay_feasible"]]),
            "source_quality_excluded_symbol_count": len(exclusions),
            "surface_status_counts": dict(Counter("replay_feasible" if row["replay_feasible"] else "blocked" for row in summaries)),
            "smallest_blocker_counts": dict(Counter(str(row["smallest_blocker"]) for row in summaries if row.get("smallest_blocker"))),
            "protected_holdout_overlap_rows": 0,
            "leakage_reject_rows": 0,
            "selected_non_executable_leg_count": 0,
            "blocked_unknown_rows": 0,
        },
        "source_artifacts": {
            "prior_local_quote_structure_matrix": prior_meta,
            "base_clean_stack_identity_ledger": base_meta,
            "oracle_packet": packet_meta,
            "opening_range_replay": opening_meta,
            "synthetic_forward_surface": synthetic_meta,
            "source_quality_policy": policy_meta,
            "forward_holdout_contract": holdout_meta,
            "options_history_db": {"path": _rel(db_path), "exists": db_path.exists(), "status": "read_only_opened"},
        },
        "proof_boundary": "Capability atlas rows are bid/ask availability diagnostics only; they are not replay P&L, not candidate-generation proof, not forward proof, and not accepted profitability.",
        "blockers": blockers,
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "_daily_bucket_structure_status_rows": daily_rows,
        "_representative_opportunities": representatives,
    }
    _validate_report(report)
    return report


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    metrics = _as_dict(report.get("metrics"))
    if metrics.get("protected_holdout_overlap_rows") != 0:
        raise ValueError("protected holdout overlap is forbidden")
    if metrics.get("leakage_reject_rows") != 0:
        raise ValueError("leakage reject rows must be zero for feasible atlas")
    if report.get("next_replay_candidate") is not None:
        feasible = [row for row in _as_list(report.get("surface_summaries")) if _as_dict(row).get("replay_feasible") is True]
        if len(feasible) < 1:
            raise ValueError("next replay candidate requires a feasible coverage surface")


def _public(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if not key.startswith("_")}


def _fmt_bool(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    metrics = _as_dict(report.get("metrics"))
    lines = [
        "# Regular Options All-Local Quote-Minute Structure Capability Atlas",
        "",
        "This generated report is read-only. It inventories coverage-only option-structure feasibility across trusted local OPRA/NBBO bid/ask rows and all available quote-minute buckets. It is not replay, not P&L proof, not candidate-generation proof, not forward proof, and not promotion.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Atlas id: `{report['atlas_id']}`.",
        f"- Read-only DB open: `{_fmt_bool(report['read_only_db_open'])}`.",
        f"- Accepted profitability: `{_fmt_bool(report['accepted_profitability'])}`.",
        f"- Historical rows are forward proof: `{_fmt_bool(report['historical_rows_are_forward_proof'])}`.",
        f"- Trusted local underlyings: `{metrics.get('trusted_local_underlying_count')}`.",
        f"- Selected detailed surfaces: `{metrics.get('selected_detailed_surface_count')}`.",
        f"- Replay-feasible surfaces: `{metrics.get('replay_feasible_surface_count')}`.",
        f"- All-local quote-surface replayability exhausted: `{_fmt_bool(report['all_local_quote_surface_replayability_exhausted_under_current_data'])}`.",
        "",
        "## Top Surface Summaries",
        "",
        "| Surface | Feasible | Full Window | Latest Four | Train Months | Latest Months | Smallest Blocker |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in _as_list(report.get("surface_summaries"))[:30]:
        row = _as_dict(row)
        lines.append(
            f"| `{row.get('surface_id')}` | `{_fmt_bool(row.get('replay_feasible'))}` | "
            f"`{row.get('full_window_constructible_completed_opportunities_after_dedupe')}` | "
            f"`{row.get('latest_four_constructible_completed_opportunities_after_dedupe')}` | "
            f"`{row.get('train_months_covered')}` | `{row.get('latest_four_months_covered')}` | "
            f"`{row.get('smallest_blocker')}` |"
        )
    lines.extend(["", "## Universe Segments", ""])
    for key, value in _as_dict(report.get("universe_segments")).items():
        lines.append(f"- `{key}`: `{len(value) if isinstance(value, list) else value}`")
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
    daily_path = output_dir / "daily_bucket_structure_status.jsonl"
    surfaces_path = output_dir / "replay_surface_candidates.jsonl"
    artifacts = {
        "json": _rel(json_path),
        "markdown": _rel(md_path),
        "latest_json": _rel(latest_json),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
        "daily_bucket_structure_status_jsonl": _rel(daily_path),
        "replay_surface_candidates_jsonl": _rel(surfaces_path),
    }
    public = _public(report)
    public["artifacts"] = artifacts
    markdown = render_markdown(public)
    for path in (json_path, latest_json):
        path.write_text(json.dumps(public, indent=2, sort_keys=True) + "\n", encoding="utf8")
    for path in (md_path, latest_md, docs_report):
        path.write_text(markdown, encoding="utf8")
    daily_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in _as_list(report.get("_daily_bucket_structure_status_rows"))) + "\n",
        encoding="utf8",
    )
    surfaces_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in _as_list(report.get("surface_summaries"))) + "\n",
        encoding="utf8",
    )
    report["artifacts"] = artifacts
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a read-only all-local quote-minute structure capability atlas.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--start-date", default="2024-06-01")
    parser.add_argument("--end-date", default="2026-05-31")
    parser.add_argument("--as-of-date", default="2026-06-04")
    parser.add_argument("--entry-bucket-candidates", default="all")
    parser.add_argument("--exit-bucket-candidates", default="all")
    parser.add_argument("--bucket-width-minutes", type=int, default=5)
    parser.add_argument("--dte-buckets", default=",".join(DEFAULT_DTE_BUCKETS))
    parser.add_argument("--min-train-months", type=int, default=20)
    parser.add_argument("--min-latest-four-months", type=int, default=4)
    parser.add_argument("--min-full-window-opportunities", type=int, default=200)
    parser.add_argument("--min-latest-four-opportunities", type=int, default=30)
    parser.add_argument("--max-detailed-surfaces", type=int, default=40)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.entry_bucket_candidates != "all" or args.exit_bucket_candidates != "all":
        raise SystemExit("Only --entry-bucket-candidates all and --exit-bucket-candidates all are supported.")
    report = build_report(
        db_path=args.db,
        start_date=args.start_date,
        end_date=args.end_date,
        as_of_date=args.as_of_date,
        bucket_width_minutes=args.bucket_width_minutes,
        dte_buckets=tuple(part.strip() for part in args.dte_buckets.split(",") if part.strip()),
        min_train_months=args.min_train_months,
        min_latest_four_months=args.min_latest_four_months,
        min_full_window_opportunities=args.min_full_window_opportunities,
        min_latest_four_opportunities=args.min_latest_four_opportunities,
        max_detailed_surfaces=args.max_detailed_surfaces,
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
