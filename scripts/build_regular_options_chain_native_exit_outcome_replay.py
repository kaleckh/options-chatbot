from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from local_env import load_local_env
except Exception:  # pragma: no cover - minimal test contexts
    load_local_env = None  # type: ignore[assignment]

if load_local_env is not None:
    load_local_env(ROOT)


REPORT_ID = "regular_options_chain_native_exit_outcome_replay"
DEFAULT_CHAIN_NATIVE_REPLAY = (
    ROOT / "data" / "forward-tracking" / "regular_options_chain_native_filter_relaxation_replay_latest.json"
)
DEFAULT_DB_PATH = Path(os.getenv("HISTORICAL_OPTIONS_DB_PATH", str(ROOT / "data" / "options-validation" / "options_history.db")))
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-chain-native-exit-outcome-replay.md"

DEFAULT_SOURCE_LABELS = ("thetadata_opra_nbbo_1m",)
TRUSTED_DATA_TRUST = "trusted"
INTRADAY_SNAPSHOT_KIND = "intraday"
DEFAULT_FEE_TOTAL_USD = 2.60

PROHIBITED_ACTIONS = (
    "do_not_create_live_row_from_chain_native_exit_outcome_replay",
    "do_not_submit_broker_order_from_chain_native_exit_outcome_replay",
    "do_not_mutate_database_from_chain_native_exit_outcome_replay",
    "do_not_change_scanner_policy_from_chain_native_exit_outcome_replay",
    "do_not_change_contract_selection_policy_from_chain_native_exit_outcome_replay",
    "do_not_change_lane_promotion_from_chain_native_exit_outcome_replay",
    "do_not_change_stop_policy_from_chain_native_exit_outcome_replay",
    "do_not_change_sizing_from_chain_native_exit_outcome_replay",
    "do_not_lower_exact_opra_nbbo_proof_bar_from_chain_native_exit_outcome_replay",
    "do_not_promote_single_date_replay_to_production_proof",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _norm(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _load_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = {
        "path": str(path),
        "exists": path.exists(),
        "status": "missing",
        "generated_at_utc": None,
        "error": None,
    }
    if not path.exists():
        meta["error"] = "missing_artifact"
        return {}, meta
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return {}, meta
    if not isinstance(payload, dict):
        meta["status"] = "invalid"
        meta["error"] = "json_root_not_object"
        return {}, meta
    meta["status"] = "loaded"
    meta["generated_at_utc"] = payload.get("generated_at_utc") or payload.get("generated_at")
    return payload, meta


def _has_live_policy_change(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "live_policy_change" and bool(item):
                return True
            if _has_live_policy_change(item):
                return True
    if isinstance(value, list):
        return any(_has_live_policy_change(item) for item in value)
    return False


def _sqlite_readonly_connect(path: Path) -> sqlite3.Connection:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def _latest_intraday_date(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT MAX(quote_date_et) FROM option_quote_snapshots WHERE snapshot_kind = ?",
        (INTRADAY_SNAPSHOT_KIND,),
    ).fetchone()
    return str(row[0]) if row and row[0] else None


def _db_meta(path: Path) -> dict[str, Any]:
    meta = {"path": str(path), "exists": path.exists(), "status": "missing", "error": None}
    if not path.exists():
        meta["error"] = "missing_artifact"
        return meta
    try:
        with closing(_sqlite_readonly_connect(path)) as conn:
            meta["status"] = "loaded"
            meta["latest_intraday_quote_date"] = _latest_intraday_date(conn)
            row = conn.execute("SELECT COUNT(*) FROM option_quote_snapshots WHERE snapshot_kind = ?", (INTRADAY_SNAPSHOT_KIND,)).fetchone()
            meta["intraday_quote_row_count"] = int(row[0] or 0)
    except sqlite3.Error as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
    return meta


def _source_filter_sql(source_labels: Sequence[str], alias: str) -> tuple[str, list[Any]]:
    labels = [str(label).strip() for label in source_labels if str(label).strip()]
    if not labels:
        return "", []
    placeholders = ",".join("?" for _ in labels)
    return f" AND {alias}.source_label IN ({placeholders})", labels


def _latest_exit_quote(
    conn: sqlite3.Connection,
    *,
    long_contract: str,
    short_contract: str,
    start_date: str,
    expiry: str,
    latest_quote_date: str,
    source_labels: Sequence[str],
    trusted_only: bool,
) -> dict[str, Any] | None:
    end_date = min(_norm(expiry)[:10], latest_quote_date)
    long_source_sql, long_source_params = _source_filter_sql(source_labels, "lb")
    short_source_sql, short_source_params = _source_filter_sql(source_labels, "sb")
    trust_sql = " AND lb.data_trust = ? AND sb.data_trust = ?" if trusted_only else ""
    trust_params: list[Any] = [TRUSTED_DATA_TRUST, TRUSTED_DATA_TRUST] if trusted_only else []
    row = conn.execute(
        f"""
        SELECT
            l.quote_date_et,
            l.quote_minute_et,
            l.as_of_utc AS long_as_of_utc,
            s.as_of_utc AS short_as_of_utc,
            l.bid AS long_bid,
            l.ask AS long_ask,
            s.bid AS short_bid,
            s.ask AS short_ask,
            lb.source_label AS long_source_label,
            sb.source_label AS short_source_label,
            lb.data_trust AS long_data_trust,
            sb.data_trust AS short_data_trust
        FROM option_quote_snapshots l
        JOIN import_batches lb ON lb.id = l.source_batch_id
        JOIN option_quote_snapshots s
          ON s.quote_date_et = l.quote_date_et
         AND s.quote_minute_et = l.quote_minute_et
         AND s.snapshot_kind = l.snapshot_kind
        JOIN import_batches sb ON sb.id = s.source_batch_id
        WHERE l.contract_symbol = ?
          AND s.contract_symbol = ?
          AND l.snapshot_kind = ?
          AND l.quote_date_et >= ?
          AND l.quote_date_et <= ?
          AND l.bid IS NOT NULL
          AND s.ask IS NOT NULL
          AND l.bid >= 0
          AND s.ask > 0
          {trust_sql}
          {long_source_sql}
          {short_source_sql}
        ORDER BY l.quote_date_et DESC, l.quote_minute_et DESC, l.as_of_utc DESC
        LIMIT 1
        """,
        (
            long_contract,
            short_contract,
            INTRADAY_SNAPSHOT_KIND,
            start_date,
            end_date,
            *trust_params,
            *long_source_params,
            *short_source_params,
        ),
    ).fetchone()
    return dict(row) if row else None


def _selected_candidate_rows(chain_native_replay: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for target in _as_list(chain_native_replay.get("target_replays")):
        target = _as_dict(target)
        for scenario_row in _as_list(target.get("scenario_rows")):
            scenario_row = _as_dict(scenario_row)
            if scenario_row.get("status") != "selected_chain_native_entry_spread":
                continue
            selected = _as_dict(scenario_row.get("selected_spread"))
            long_symbol = _norm(selected.get("long_contract_symbol")).upper()
            short_symbol = _norm(selected.get("short_contract_symbol")).upper()
            if not long_symbol or not short_symbol:
                continue
            scenario_id = _norm(scenario_row.get("scenario_id"))
            rows.append(
                {
                    "target_id": _norm(target.get("target_id")),
                    "lane": _norm(target.get("lane")),
                    "scan_date": _norm(scenario_row.get("scan_date") or target.get("scan_date"))[:10],
                    "ticker": _norm(scenario_row.get("ticker")).upper(),
                    "trade_type": _norm(scenario_row.get("trade_type")),
                    "scenario_id": scenario_id,
                    "scenario_description": _norm(scenario_row.get("scenario_description")),
                    "relaxation_kind": "current" if scenario_id == "current_chain_native_filters" else "relaxed",
                    "relaxed_filter_names": list(_as_list(scenario_row.get("relaxed_filter_names"))),
                    "selected_spread": selected,
                    "long_contract_symbol": long_symbol,
                    "short_contract_symbol": short_symbol,
                    "expiry": _norm(selected.get("expiry") or scenario_row.get("expiry"))[:10],
                    "entry_debit": _safe_float(selected.get("net_debit"))
                    or _safe_float(selected.get("ask_bid_debit"))
                    or _safe_float(scenario_row.get("entry_spread_ask_bid_debit")),
                    "entry_mid_debit": _safe_float(selected.get("mid_debit")) or _safe_float(scenario_row.get("entry_spread_mid_debit")),
                    "entry_ask_bid_debit": _safe_float(selected.get("ask_bid_debit"))
                    or _safe_float(scenario_row.get("entry_spread_ask_bid_debit")),
                    "spread_width": _safe_float(selected.get("spread_width")),
                    "debit_pct_of_width": _safe_float(selected.get("debit_pct_of_width")),
                    "fill_degradation_vs_mid_pct": _safe_float(selected.get("fill_degradation_vs_mid_pct"))
                    or _safe_float(scenario_row.get("fill_degradation_vs_mid_pct")),
                }
            )
    rows.sort(key=lambda item: (_norm(item.get("target_id")), _norm(item.get("scenario_id")), _norm(item.get("ticker"))))
    return rows


def _quote_public(quote: dict[str, Any]) -> dict[str, Any]:
    return {
        "quote_date_et": quote.get("quote_date_et"),
        "quote_minute_et": quote.get("quote_minute_et"),
        "long_as_of_utc": quote.get("long_as_of_utc"),
        "short_as_of_utc": quote.get("short_as_of_utc"),
        "long_bid": round(float(quote.get("long_bid") or 0.0), 4),
        "long_ask": _safe_float(quote.get("long_ask")),
        "short_bid": _safe_float(quote.get("short_bid")),
        "short_ask": round(float(quote.get("short_ask") or 0.0), 4),
        "long_source_label": quote.get("long_source_label"),
        "short_source_label": quote.get("short_source_label"),
        "long_data_trust": quote.get("long_data_trust"),
        "short_data_trust": quote.get("short_data_trust"),
        "quote_evidence_class": "trusted_intraday_opra_nbbo",
    }


def _price_candidate(
    candidate: dict[str, Any],
    *,
    conn: sqlite3.Connection,
    latest_quote_date: str,
    source_labels: Sequence[str],
    trusted_only: bool,
    fee_total_usd: float,
) -> dict[str, Any]:
    row = dict(candidate)
    blockers: list[str] = []
    entry_debit = _safe_float(row.get("entry_debit"))
    if entry_debit is None or entry_debit <= 0:
        blockers.append("missing_or_invalid_entry_debit")
    if not _norm(row.get("expiry")):
        blockers.append("missing_expiry")
    if not _norm(row.get("scan_date")):
        blockers.append("missing_scan_date")
    if blockers:
        row.update({"exact_exit_pnl_available": False, "blockers": blockers})
        return row

    quote = _latest_exit_quote(
        conn,
        long_contract=_norm(row.get("long_contract_symbol")).upper(),
        short_contract=_norm(row.get("short_contract_symbol")).upper(),
        start_date=_norm(row.get("scan_date"))[:10],
        expiry=_norm(row.get("expiry"))[:10],
        latest_quote_date=latest_quote_date,
        source_labels=source_labels,
        trusted_only=trusted_only,
    )
    if quote is None:
        row.update(
            {
                "exact_exit_pnl_available": False,
                "blockers": ["no_common_trusted_exit_quote"],
                "exit_quote_demand": {
                    "target_id": row.get("target_id"),
                    "lane": row.get("lane"),
                    "scan_date": row.get("scan_date"),
                    "ticker": row.get("ticker"),
                    "scenario_id": row.get("scenario_id"),
                    "long_contract_symbol": row.get("long_contract_symbol"),
                    "short_contract_symbol": row.get("short_contract_symbol"),
                    "quote_date_from": row.get("scan_date"),
                    "quote_date_to": min(_norm(row.get("expiry"))[:10], latest_quote_date),
                    "missing_reason": "no_common_trusted_exit_quote",
                    "source_labels": list(source_labels),
                },
            }
        )
        return row

    long_bid = _safe_float(quote.get("long_bid")) or 0.0
    short_ask = _safe_float(quote.get("short_ask")) or 0.0
    exit_credit = max(round(long_bid - short_ask, 4), 0.0)
    gross_pnl_usd = (exit_credit - entry_debit) * 100.0
    net_pnl_usd = gross_pnl_usd - float(fee_total_usd)
    row.update(
        {
            "exact_exit_pnl_available": True,
            "production_proof": False,
            "promotion_ready": False,
            "evidence_group": "research_backfill",
            "quote_evidence_class": "trusted_intraday_opra_nbbo",
            "entry_side_aware_debit": round(entry_debit, 4),
            "exit_side_aware_credit": round(exit_credit, 4),
            "exit_quote": _quote_public(quote),
            "gross_pnl_pct": round((exit_credit - entry_debit) / entry_debit * 100.0, 4),
            "net_pnl_pct": round(net_pnl_usd / (entry_debit * 100.0) * 100.0, 4),
            "gross_pnl_usd": round(gross_pnl_usd, 2),
            "net_pnl_usd": round(net_pnl_usd, 2),
            "fee_total_usd": round(float(fee_total_usd), 2),
            "basis": "conservative_long_bid_minus_short_ask_latest_available_intraday",
            "blockers": ["single_date_target_overfit_risk", "fresh_paper_holdout_required_before_policy_change"],
        }
    )
    return row


def _metric_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    priced = [
        row
        for row in rows
        if row.get("exact_exit_pnl_available") and _safe_float(row.get("net_pnl_pct")) is not None
    ]
    values = [float(row["net_pnl_pct"]) for row in priced]
    usd = [float(row["net_pnl_usd"]) for row in priced if _safe_float(row.get("net_pnl_usd")) is not None]
    gains = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    return {
        "rows": len(rows),
        "priced": len(priced),
        "unpriced": len(rows) - len(priced),
        "profit_factor": round(gains / losses, 2) if losses else (999.0 if gains > 0 else 0.0 if priced else None),
        "avg_net_pnl_pct": round(sum(values) / len(values), 2) if values else None,
        "median_net_pnl_pct": round(median(values), 2) if values else None,
        "min_net_pnl_pct": round(min(values), 2) if values else None,
        "max_net_pnl_pct": round(max(values), 2) if values else None,
        "win_rate_pct": round(sum(1 for value in values if value > 0) / len(values) * 100.0, 1) if values else None,
        "winner_count": sum(1 for value in values if value > 0),
        "loser_count": sum(1 for value in values if value < 0),
        "sum_net_pnl_usd": round(sum(usd), 2) if usd else None,
        "avg_net_pnl_usd": round(sum(usd) / len(usd), 2) if usd else None,
    }


def _scenario_metrics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_norm(row.get("scenario_id"))].append(row)
    metrics = []
    for scenario_id, scenario_rows in grouped.items():
        metric = _metric_rows(scenario_rows)
        metric.update(
            {
                "scenario_id": scenario_id,
                "relaxation_kind": "current" if scenario_id == "current_chain_native_filters" else "relaxed",
            }
        )
        metrics.append(metric)
    metrics.sort(
        key=lambda item: (
            0 if item.get("scenario_id") == "current_chain_native_filters" else 1,
            -float(item.get("avg_net_pnl_pct") if item.get("avg_net_pnl_pct") is not None else -999999),
            _norm(item.get("scenario_id")),
        )
    )
    return metrics


def _best_relaxed_scenario(scenario_metrics: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        item
        for item in scenario_metrics
        if item.get("relaxation_kind") == "relaxed" and _safe_int(item.get("priced")) > 0
    ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            float(item.get("avg_net_pnl_pct") if item.get("avg_net_pnl_pct") is not None else -999999),
            float(item.get("sum_net_pnl_usd") if item.get("sum_net_pnl_usd") is not None else -999999),
        ),
        reverse=True,
    )
    return candidates[0]


def _dedupe_demands(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str, str]] = set()
    demands = []
    for row in rows:
        demand = _as_dict(row.get("exit_quote_demand"))
        if not demand:
            continue
        key = (
            _norm(demand.get("target_id")),
            _norm(demand.get("scenario_id")),
            _norm(demand.get("ticker")),
            _norm(demand.get("long_contract_symbol")),
            _norm(demand.get("short_contract_symbol")),
        )
        if key in seen:
            continue
        seen.add(key)
        demands.append(demand)
    demands.sort(key=lambda item: (_norm(item.get("scenario_id")), _norm(item.get("ticker"))))
    return demands


def _overall_status(summary: dict[str, Any], missing_required: list[str], live_policy_change: bool, db_status: str) -> str:
    if live_policy_change:
        return "invalid_live_policy_change"
    if missing_required:
        return "blocked_missing_inputs"
    if db_status == "unreadable":
        return "blocked_quote_store_unreadable"
    if _safe_int(summary.get("selected_scenario_row_count")) == 0:
        return "chain_native_exit_outcome_replay_no_selected_candidates"
    priced = _safe_int(summary.get("priced_scenario_row_count"))
    rows = _safe_int(summary.get("selected_scenario_row_count"))
    if priced == 0:
        return "chain_native_exit_outcome_replay_exit_quote_gap"
    if priced < rows:
        return "chain_native_exit_outcome_replay_partial_exact_pnl_diagnostic_only"
    return "chain_native_exit_outcome_replay_exact_pnl_available_diagnostic_only"


def _next_evidence_queue(summary: dict[str, Any], scenario_metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    if _safe_int(summary.get("missing_exit_quote_demand_count")):
        queue.append(
            {
                "priority": 4,
                "action": "import_or_query_chain_native_exit_contract_quotes",
                "count": summary.get("missing_exit_quote_demand_count"),
                "reason": "trusted_exit_contract_quote_coverage_missing_for_selected_chain_native_candidates",
                "operator_next_step": "Import or query trusted OPRA/NBBO exit quotes for the listed long/short contract pairs, then rerun this replay.",
            }
        )
    best = _as_dict(summary.get("best_relaxed_scenario"))
    if _safe_int(summary.get("priced_relaxed_scenario_row_count")):
        avg = _safe_float(best.get("avg_net_pnl_pct"))
        pf = _safe_float(best.get("profit_factor"))
        if avg is not None and avg > 0 and (pf is None or pf >= 1.0):
            queue.append(
                {
                    "priority": 5,
                    "action": "validate_chain_native_relaxation_on_later_holdout",
                    "count": 1,
                    "reason": "single_date_positive_diagnostic_exit_outcome_requires_holdout",
                    "operator_next_step": "Validate the same predeclared relaxation on later dates or fresh paper before any policy discussion.",
                }
            )
        else:
            queue.append(
                {
                    "priority": 5,
                    "action": "archive_negative_chain_native_relaxation_branch",
                    "count": 1,
                    "reason": "relaxed_chain_native_exit_outcome_not_profitable_on_exact_replay",
                    "operator_next_step": "Record this frozen relaxation target as a diagnostic dead end unless a new predeclared hypothesis changes the evidence.",
                }
            )
    elif not scenario_metrics:
        queue.append(
            {
                "priority": 4,
                "action": "repair_chain_native_exit_outcome_inputs",
                "count": 1,
                "reason": "no_selected_chain_native_candidates_for_exit_replay",
                "operator_next_step": "Repair the chain-native filter relaxation replay before exit-outcome replay.",
            }
        )
    queue.sort(key=lambda item: (_safe_int(item.get("priority")), _norm(item.get("action"))))
    return queue


def build_report(
    *,
    chain_native_replay_path: Path = DEFAULT_CHAIN_NATIVE_REPLAY,
    db_path: Path = DEFAULT_DB_PATH,
    generated_at_utc: str | None = None,
    source_labels: Sequence[str] = DEFAULT_SOURCE_LABELS,
    trusted_only: bool = True,
    fee_total_usd: float = DEFAULT_FEE_TOTAL_USD,
) -> dict[str, Any]:
    chain_native_replay, chain_meta = _load_json(chain_native_replay_path)
    db_meta = _db_meta(db_path)
    inputs = {
        "chain_native_filter_relaxation_replay": chain_meta,
        "options_history_db": db_meta,
    }
    missing_required = [key for key, meta in inputs.items() if meta["status"] == "missing"]
    live_policy_change = _has_live_policy_change(chain_native_replay)
    selected_rows: list[dict[str, Any]] = []
    outcome_rows: list[dict[str, Any]] = []
    latest_quote_date = _norm(db_meta.get("latest_intraday_quote_date"))
    if not missing_required and not live_policy_change and db_meta.get("status") == "loaded":
        selected_rows = _selected_candidate_rows(chain_native_replay)
        with closing(_sqlite_readonly_connect(db_path)) as conn:
            for row in selected_rows:
                outcome_rows.append(
                    _price_candidate(
                        row,
                        conn=conn,
                        latest_quote_date=latest_quote_date,
                        source_labels=source_labels,
                        trusted_only=trusted_only,
                        fee_total_usd=fee_total_usd,
                    )
                )
    scenario_metrics = _scenario_metrics(outcome_rows)
    all_metrics = _metric_rows(outcome_rows)
    relaxed_rows = [row for row in outcome_rows if row.get("relaxation_kind") == "relaxed"]
    current_rows = [row for row in outcome_rows if row.get("relaxation_kind") == "current"]
    missing_demands = _dedupe_demands(outcome_rows)
    best_relaxed = _best_relaxed_scenario(scenario_metrics)
    pair_count = len(
        {
            (_norm(row.get("ticker")), _norm(row.get("long_contract_symbol")), _norm(row.get("short_contract_symbol")))
            for row in outcome_rows
        }
    )
    summary: dict[str, Any] = {
        "missing_required_inputs": missing_required,
        "live_policy_change": live_policy_change,
        "db_status": db_meta.get("status"),
        "latest_intraday_quote_date": latest_quote_date or None,
        "selected_scenario_row_count": len(outcome_rows),
        "current_selected_scenario_row_count": len(current_rows),
        "relaxed_selected_scenario_row_count": len(relaxed_rows),
        "unique_contract_pair_count": pair_count,
        "priced_scenario_row_count": all_metrics.get("priced"),
        "priced_current_scenario_row_count": _metric_rows(current_rows).get("priced"),
        "priced_relaxed_scenario_row_count": _metric_rows(relaxed_rows).get("priced"),
        "missing_exit_quote_demand_count": len(missing_demands),
        "scenario_count": len(scenario_metrics),
        "best_relaxed_scenario": best_relaxed,
        "all_scenario_metrics": all_metrics,
        "blockers": [],
        "promotion_ready": False,
    }
    blockers: list[str] = []
    if missing_required:
        blockers.extend(f"missing_{key}" for key in missing_required)
    if db_meta.get("status") == "unreadable":
        blockers.append("quote_store_unreadable")
    if not outcome_rows and not missing_required:
        blockers.append("no_selected_chain_native_candidates")
    if missing_demands:
        blockers.append("exit_quote_coverage_incomplete")
    if _safe_int(summary.get("priced_scenario_row_count")) == 0 and outcome_rows:
        blockers.append("no_exact_exit_pnl_rows")
    if _safe_int(summary.get("priced_scenario_row_count")):
        blockers.extend(["single_date_target_overfit_risk", "fresh_paper_holdout_required_before_policy_change"])
    summary["blockers"] = sorted(set(blockers))
    summary["overall_status"] = _overall_status(summary, missing_required, live_policy_change, _norm(db_meta.get("status")))
    next_queue = _next_evidence_queue(summary, scenario_metrics)
    summary["next_evidence_action_count"] = len(next_queue)
    status = (
        "invalid_live_policy_change"
        if live_policy_change
        else "blocked_missing_inputs"
        if missing_required
        else "blocked_quote_store_unreadable"
        if db_meta.get("status") == "unreadable"
        else "chain_native_exit_outcome_replay_readback"
    )
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_read_only_chain_native_exit_outcome_replay",
        "schema_version": 1,
        "read_only": True,
        "summary": summary,
        "proof_policy": {
            "readback_is": "read-only exact-exit outcome replay for selected chain-native diagnostic candidates",
            "readback_is_not": "scanner policy, contract-selection policy, broker recommendation, DB mutation, lane promotion, or live proof",
            "trusted_proof_standard": "P&L is emitted only from trusted intraday exact-contract OPRA/NBBO entry debit and exit long-bid/short-ask evidence",
            "prohibited_actions": list(PROHIBITED_ACTIONS),
        },
        "inputs": inputs,
        "scenario_metrics": scenario_metrics,
        "outcome_rows": outcome_rows,
        "exit_quote_demands": missing_demands,
        "next_evidence_queue": next_queue,
        "live_policy_change": live_policy_change,
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }


def _cell(value: Any) -> str:
    return _norm(value).replace("|", "\\|").replace("\n", " ")


def _json_inline(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def render_markdown(report: dict[str, Any]) -> str:
    summary = _as_dict(report.get("summary"))
    lines = [
        "# Regular Options Chain-Native Exit Outcome Replay",
        "",
        "This report is generated from `scripts/build_regular_options_chain_native_exit_outcome_replay.py`. It prices selected chain-native diagnostic candidates with trusted intraday OPRA/NBBO exit quotes and remains read-only.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Overall status: `{summary.get('overall_status')}`.",
        f"- Latest intraday quote date: `{summary.get('latest_intraday_quote_date')}`.",
        f"- Selected scenario rows: `{summary.get('selected_scenario_row_count')}`.",
        f"- Current / relaxed selected rows: `{summary.get('current_selected_scenario_row_count')}` / `{summary.get('relaxed_selected_scenario_row_count')}`.",
        f"- Priced scenario rows: `{summary.get('priced_scenario_row_count')}`.",
        f"- Missing exit quote demands: `{summary.get('missing_exit_quote_demand_count')}`.",
        f"- Best relaxed scenario: `{_json_inline(summary.get('best_relaxed_scenario') or {})}`.",
        f"- All-row metrics: `{_json_inline(summary.get('all_scenario_metrics') or {})}`.",
        f"- Promotion ready: `{summary.get('promotion_ready')}`.",
        f"- Blockers: `{_json_inline(summary.get('blockers') or [])}`.",
        f"- Live policy change: `{str(bool(summary.get('live_policy_change'))).lower()}`.",
        "",
        "## Scenario Metrics",
        "",
        "| Scenario | Kind | Rows | Priced | PF | Avg Net | Median | Win Rate | Net USD |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for metric in _as_list(report.get("scenario_metrics")):
        metric = _as_dict(metric)
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(metric.get('scenario_id'))}`",
                    _cell(metric.get("relaxation_kind")),
                    _cell(metric.get("rows")),
                    _cell(metric.get("priced")),
                    _cell(metric.get("profit_factor")),
                    _cell(metric.get("avg_net_pnl_pct")),
                    _cell(metric.get("median_net_pnl_pct")),
                    _cell(metric.get("win_rate_pct")),
                    _cell(metric.get("sum_net_pnl_usd")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Outcome Rows",
            "",
            "| Scenario | Ticker | Long | Short | Entry Debit | Exit Credit | Net P&L % | Net USD | Quote Date | Blockers |",
            "|---|---|---|---|---:|---:|---:|---:|---|---|",
        ]
    )
    for row in _as_list(report.get("outcome_rows"))[:80]:
        row = _as_dict(row)
        quote = _as_dict(row.get("exit_quote"))
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(row.get('scenario_id'))}`",
                    _cell(row.get("ticker")),
                    f"`{_cell(row.get('long_contract_symbol'))}`",
                    f"`{_cell(row.get('short_contract_symbol'))}`",
                    _cell(row.get("entry_side_aware_debit") or row.get("entry_debit")),
                    _cell(row.get("exit_side_aware_credit")),
                    _cell(row.get("net_pnl_pct")),
                    _cell(row.get("net_pnl_usd")),
                    _cell(quote.get("quote_date_et")),
                    _cell(", ".join(str(item) for item in _as_list(row.get("blockers"))) or "none"),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Exit Quote Demands",
            "",
            "| Scenario | Ticker | Long | Short | Date Window | Missing Reason |",
            "|---|---|---|---|---|---|",
        ]
    )
    for demand in _as_list(report.get("exit_quote_demands")):
        demand = _as_dict(demand)
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(demand.get('scenario_id'))}`",
                    _cell(demand.get("ticker")),
                    f"`{_cell(demand.get('long_contract_symbol'))}`",
                    f"`{_cell(demand.get('short_contract_symbol'))}`",
                    f"{_cell(demand.get('quote_date_from'))} to {_cell(demand.get('quote_date_to'))}",
                    _cell(demand.get("missing_reason")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Next Evidence Queue",
            "",
            "| Priority | Action | Count | Reason |",
            "|---:|---|---:|---|",
        ]
    )
    for item in _as_list(report.get("next_evidence_queue")):
        item = _as_dict(item)
        lines.append(
            f"| {_cell(item.get('priority'))} | `{_cell(item.get('action'))}` | {_cell(item.get('count'))} | {_cell(item.get('reason'))} |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This chain-native exit outcome replay is read-only and diagnostic. It does not create trades, submit broker orders, mutate DB state, change scanner or contract-selection policy, change lane promotion, change stops or sizing, lower exact OPRA/NBBO proof bars, or promote a single-date replay into production proof.",
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
    latest_json = output_dir / f"{REPORT_ID}_latest.json"
    latest_md = output_dir / f"{REPORT_ID}_latest.md"
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


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the read-only chain-native exact-exit outcome replay.")
    parser.add_argument("--chain-native-replay", type=Path, default=DEFAULT_CHAIN_NATIVE_REPLAY)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--fee-total-usd", type=float, default=DEFAULT_FEE_TOTAL_USD)
    parser.add_argument("--source-label", action="append", dest="source_labels", default=None)
    parser.add_argument("--allow-untrusted", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(
        chain_native_replay_path=args.chain_native_replay,
        db_path=args.db_path,
        source_labels=tuple(args.source_labels or DEFAULT_SOURCE_LABELS),
        trusted_only=not args.allow_untrusted,
        fee_total_usd=float(args.fee_total_usd),
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
