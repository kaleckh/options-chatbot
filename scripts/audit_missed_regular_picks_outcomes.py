from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
for candidate in (ROOT, BACKEND_DIR):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

from local_env import load_local_env
from positions_repository import create_positions_repository
from scripts.quote_evidence_readback import non_production_research_policy, quote_evidence_readback


DEFAULT_INPUT_CSV = ROOT / "data" / "forward-tracking" / "missed_regular_picks_20260522_20260605_report_only.csv"
DEFAULT_ALL_LANES_REPORT = ROOT / "data" / "forward-tracking" / "all_lanes_zero_pick_current_algo_audit_latest.json"
DEFAULT_OPTIONS_DB = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOC = ROOT / "docs" / "missed-regular-picks-outcome-audit.md"
REPORT_ID = "missed_regular_picks_outcome"

DEBIT_BUCKETS = (
    (25.0, "lt25", 25.0),
    (35.0, "25_35", 35.0),
    (45.0, "35_45", 45.0),
    (55.0, "45_55", 55.0),
    (math.inf, "55_plus", None),
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _safe_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _safe_int(value: Any) -> int:
    parsed = _safe_float(value)
    return int(parsed) if parsed is not None else 0


def _norm_text(value: Any) -> str:
    return str(value or "").strip()


def _rel(path: str | Path | None) -> str | None:
    if path is None:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    try:
        return str(candidate.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(candidate).replace("\\", "/")


def row_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        _norm_text(row.get("scan_date"))[:10],
        _norm_text(row.get("playbook")).lower(),
        _norm_text(row.get("ticker")).upper(),
        _norm_text(row.get("contract_symbol")).upper(),
        _norm_text(row.get("short_contract_symbol")).upper(),
    )


def exact_spread_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        _norm_text(row.get("scan_date"))[:10],
        _norm_text(row.get("ticker")).upper(),
        _norm_text(row.get("contract_symbol")).upper(),
        _norm_text(row.get("short_contract_symbol")).upper(),
    )


def _position_source(position: dict[str, Any]) -> dict[str, Any]:
    source = position.get("source_pick_snapshot")
    if isinstance(source, dict):
        return source
    if isinstance(source, str):
        try:
            parsed = json.loads(source)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def position_key(position: dict[str, Any]) -> tuple[str, str, str, str, str]:
    source = _position_source(position)
    spread = source.get("selected_spread") if isinstance(source.get("selected_spread"), dict) else {}
    return (
        _norm_text(source.get("scan_date") or _norm_text(position.get("filled_at"))[:10])[:10],
        _norm_text(source.get("playbook_id") or source.get("playbook") or source.get("cohort_id")).lower(),
        _norm_text(position.get("ticker") or source.get("ticker")).upper(),
        _norm_text(position.get("contract_symbol") or source.get("contract_symbol") or spread.get("long_contract_symbol")).upper(),
        _norm_text(source.get("short_contract_symbol") or spread.get("short_contract_symbol")).upper(),
    )


def tracked_pnl(position: dict[str, Any]) -> dict[str, Any]:
    latest = position.get("latest_review") if isinstance(position.get("latest_review"), dict) else {}
    for key in ("net_pnl_pct", "gross_pnl_pct", "last_pnl_pct"):
        value = _safe_float(position.get(key))
        if value is not None:
            return {
                "pnl_pct": round(value, 4),
                "basis": key,
                "net_pnl_pct": _safe_float(position.get("net_pnl_pct")),
                "gross_pnl_pct": _safe_float(position.get("gross_pnl_pct")),
                "last_pnl_pct": _safe_float(position.get("last_pnl_pct")),
                "net_pnl_usd": _safe_float(position.get("net_pnl_usd")),
                "gross_pnl_usd": _safe_float(position.get("gross_pnl_usd")),
            }
    for key in ("net_pnl_pct", "gross_pnl_pct", "current_pnl_pct"):
        value = _safe_float(latest.get(key))
        if value is not None:
            return {
                "pnl_pct": round(value, 4),
                "basis": f"latest_review.{key}",
                "net_pnl_pct": _safe_float(latest.get("net_pnl_pct")),
                "gross_pnl_pct": _safe_float(latest.get("gross_pnl_pct")),
                "last_pnl_pct": _safe_float(latest.get("current_pnl_pct")),
                "net_pnl_usd": _safe_float(latest.get("net_pnl_usd")),
                "gross_pnl_usd": _safe_float(latest.get("gross_pnl_usd")),
            }
    return {"pnl_pct": None, "basis": None}


def load_positions(*, skip_position_store: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if skip_position_store:
        return [], {"status": "skipped"}
    load_local_env(ROOT)
    try:
        repository = create_positions_repository(os.getenv("DATABASE_URL"))
        positions = repository.list_positions("all")
    except Exception as exc:
        return [], {"status": "unavailable", "error": str(exc)}
    return list(positions or []), {"status": "loaded", "repository_class": type(repository).__name__, "position_count": len(positions or [])}


def load_rows_from_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def load_rows_from_all_lanes_report(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for lane in payload.get("lanes") or []:
        if not isinstance(lane, dict):
            continue
        playbook = _norm_text(lane.get("playbook")).lower()
        label = lane.get("label") or playbook
        for day in lane.get("dates") or []:
            if not isinstance(day, dict):
                continue
            scan_date = _norm_text(day.get("scan_date"))[:10]
            for pick in day.get("selected") or []:
                if not isinstance(pick, dict):
                    continue
                row = dict(pick)
                row.setdefault("scan_date", scan_date)
                row.setdefault("playbook", playbook)
                row.setdefault("lane_label", label)
                rows.append(row)
    return rows


def load_input_rows(input_csv: Path | None, all_lanes_report: Path | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if input_csv and input_csv.exists():
        rows = load_rows_from_csv(input_csv)
        return rows, {"source": "csv", "path": _rel(input_csv), "row_count": len(rows)}
    if all_lanes_report and all_lanes_report.exists():
        rows = load_rows_from_all_lanes_report(all_lanes_report)
        return rows, {"source": "all_lanes_report", "path": _rel(all_lanes_report), "row_count": len(rows)}
    raise FileNotFoundError("No missed-pick CSV or all-lanes report was available.")


def _latest_intraday_date(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT MAX(quote_date_et) FROM option_quote_snapshots WHERE snapshot_kind = 'intraday'"
    ).fetchone()
    return str(row[0]) if row and row[0] else None


def _source_filter_sql(source_labels: list[str], alias: str) -> tuple[str, list[Any]]:
    if not source_labels:
        return "", []
    placeholders = ",".join("?" for _ in source_labels)
    return f" AND {alias}.source_label IN ({placeholders})", list(source_labels)


def latest_exit_quote(
    conn: sqlite3.Connection,
    *,
    long_contract: str,
    short_contract: str,
    start_date: str,
    expiry: str,
    latest_quote_date: str,
    source_labels: list[str],
    trusted_only: bool,
) -> dict[str, Any] | None:
    end_date = min(_norm_text(expiry)[:10], latest_quote_date)
    long_source_sql, long_source_params = _source_filter_sql(source_labels, "lb")
    short_source_sql, short_source_params = _source_filter_sql(source_labels, "sb")
    trust_sql = " AND lb.data_trust = 'trusted' AND sb.data_trust = 'trusted'" if trusted_only else ""
    query = f"""
        SELECT l.quote_date_et,
               l.quote_minute_et,
               l.bid AS long_bid,
               l.ask AS long_ask,
               s.bid AS short_bid,
               s.ask AS short_ask,
               l.as_of_utc AS long_as_of_utc,
               s.as_of_utc AS short_as_of_utc
        FROM option_quote_snapshots l
        JOIN import_batches lb ON lb.id = l.source_batch_id
        JOIN option_quote_snapshots s
          ON s.quote_date_et = l.quote_date_et
         AND s.quote_minute_et = l.quote_minute_et
         AND s.snapshot_kind = l.snapshot_kind
        JOIN import_batches sb ON sb.id = s.source_batch_id
        WHERE l.contract_symbol = ?
          AND s.contract_symbol = ?
          AND l.snapshot_kind = 'intraday'
          AND l.quote_date_et >= ?
          AND l.quote_date_et <= ?
          AND l.bid IS NOT NULL
          AND s.ask IS NOT NULL
          {trust_sql}
          {long_source_sql}
          {short_source_sql}
        ORDER BY l.quote_date_et DESC, l.quote_minute_et DESC
        LIMIT 1
    """
    params: list[Any] = [long_contract, short_contract, start_date, end_date, *long_source_params, *short_source_params]
    row = conn.execute(query, params).fetchone()
    return dict(row) if row else None


def conservative_mark(
    row: dict[str, Any],
    *,
    conn: sqlite3.Connection,
    latest_quote_date: str,
    source_labels: list[str],
    trusted_only: bool,
    fee_total_usd: float,
    quote_evidence: dict[str, Any],
) -> dict[str, Any]:
    entry = _safe_float(row.get("net_debit") or row.get("entry_execution_price"))
    if entry is None or entry <= 0:
        return {"priced": False, "reason": "missing_or_invalid_entry_debit"}
    quote = latest_exit_quote(
        conn,
        long_contract=_norm_text(row.get("contract_symbol")).upper(),
        short_contract=_norm_text(row.get("short_contract_symbol")).upper(),
        start_date=_norm_text(row.get("scan_date"))[:10],
        expiry=_norm_text(row.get("expiry"))[:10],
        latest_quote_date=latest_quote_date,
        source_labels=source_labels,
        trusted_only=trusted_only,
    )
    if not quote:
        return {"priced": False, "reason": "no_common_trusted_exit_quote"}
    long_bid = _safe_float(quote.get("long_bid")) or 0.0
    short_ask = _safe_float(quote.get("short_ask")) or 0.0
    exit_credit = max(long_bid - short_ask, 0.0)
    gross_pnl_usd = (exit_credit - entry) * 100.0
    net_pnl_usd = gross_pnl_usd - fee_total_usd
    return {
        "priced": True,
        "production_proof": False,
        "evidence_group": "research_backfill",
        "quote_evidence_class": quote_evidence.get("quote_evidence_class"),
        "quote_evidence_label": quote_evidence.get("quote_evidence_label"),
        "production_proof_source_eligible": quote_evidence.get("production_proof_source_eligible"),
        "entry_debit": round(entry, 4),
        "exit_credit": round(exit_credit, 4),
        "quote_date": quote.get("quote_date_et"),
        "quote_minute_et": quote.get("quote_minute_et"),
        "long_bid": long_bid,
        "short_ask": short_ask,
        "gross_pnl_pct": round((exit_credit - entry) / entry * 100.0, 4),
        "net_pnl_pct": round(net_pnl_usd / (entry * 100.0) * 100.0, 4),
        "gross_pnl_usd": round(gross_pnl_usd, 2),
        "net_pnl_usd": round(net_pnl_usd, 2),
        "fee_total_usd": round(fee_total_usd, 2),
        "basis": "conservative_long_bid_minus_short_ask_latest_available_intraday",
    }


def debit_pct_of_width(row: dict[str, Any]) -> float | None:
    explicit = _safe_float(row.get("debit_pct_of_width"))
    if explicit is not None:
        return explicit
    debit = _safe_float(row.get("net_debit") or row.get("entry_execution_price"))
    long_strike = _safe_float(row.get("long_strike") if row.get("long_strike") is not None else row.get("strike"))
    short_strike = _safe_float(row.get("short_strike"))
    if debit is None or long_strike is None or short_strike is None:
        return None
    width = abs(short_strike - long_strike)
    if width <= 0:
        return None
    return debit / width * 100.0


def debit_bucket(row: dict[str, Any]) -> tuple[str, float | None]:
    pct = debit_pct_of_width(row)
    if pct is None:
        return "missing", None
    for upper, label, guardrail_upper in DEBIT_BUCKETS:
        if pct < upper:
            return label, guardrail_upper
    return "missing", None


def metrics(values: list[float], usd_values: list[float] | None = None, *, row_count: int | None = None) -> dict[str, Any]:
    usd = usd_values or []
    winners = [value for value in values if value > 0]
    losers = [value for value in values if value < 0]
    gross_profit = sum(winners)
    gross_loss = -sum(losers)
    if gross_loss > 0:
        profit_factor: float | None = round(gross_profit / gross_loss, 2)
    elif gross_profit > 0:
        profit_factor = 999.0
    else:
        profit_factor = None
    priced = len(values)
    return {
        "rows": row_count if row_count is not None else priced,
        "priced": priced,
        "unpriced": max((row_count if row_count is not None else priced) - priced, 0),
        "winner_count": len(winners),
        "loser_count": len(losers),
        "flat_count": sum(1 for value in values if value == 0),
        "win_rate_pct": round(len(winners) / priced * 100.0, 1) if priced else 0.0,
        "avg_net_pnl_pct": round(sum(values) / priced, 2) if priced else None,
        "median_net_pnl_pct": round(median(values), 2) if priced else None,
        "min_net_pnl_pct": round(min(values), 2) if priced else None,
        "max_net_pnl_pct": round(max(values), 2) if priced else None,
        "net_pnl_pct_points": round(sum(values), 2) if priced else 0.0,
        "profit_factor": profit_factor,
        "gross_profit_pct_sum": round(gross_profit, 2),
        "gross_loss_pct_sum": round(gross_loss, 2),
        "sum_net_pnl_usd": round(sum(usd), 2) if usd else None,
        "avg_net_pnl_usd": round(sum(usd) / len(usd), 2) if usd else None,
    }


def _marked_values(rows: list[dict[str, Any]]) -> tuple[list[float], list[float]]:
    values: list[float] = []
    usd_values: list[float] = []
    for row in rows:
        mark = row.get("mark") if isinstance(row.get("mark"), dict) else {}
        if mark.get("priced") and mark.get("net_pnl_pct") is not None:
            values.append(float(mark["net_pnl_pct"]))
            if mark.get("net_pnl_usd") is not None:
                usd_values.append(float(mark["net_pnl_usd"]))
    return values, usd_values


def _group_metrics(rows: list[dict[str, Any]], group_key: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_norm_text(row.get(group_key)) or "unknown"].append(row)
    output = {}
    for key, items in grouped.items():
        values, usd_values = _marked_values(items)
        output[key] = metrics(values, usd_values, row_count=len(items))
    return dict(sorted(output.items()))


def _cluster_rows(rows: list[dict[str, Any]], key_func: Any) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[key_func(row)].append(row)
    clusters = []
    for key, items in grouped.items():
        values, usd_values = _marked_values(items)
        if not values:
            continue
        summary = metrics(values, usd_values, row_count=len(items))
        clusters.append({"key": key, **summary})
    clusters.sort(
        key=lambda item: (
            float(item.get("avg_net_pnl_pct") if item.get("avg_net_pnl_pct") is not None else 999.0),
            -int(item.get("rows") or 0),
        )
    )
    return clusters


def build_self_guardrails(
    lane_rows: list[dict[str, Any]],
    *,
    min_cluster_rows: int,
    min_profit_factor: float,
) -> dict[str, Any]:
    ticker_clusters = _cluster_rows(lane_rows, lambda row: _norm_text(row.get("ticker")).upper() or "UNKNOWN")
    blocked_tickers = [
        {
            "ticker": item["key"],
            "rows": item["rows"],
            "winner_count": item["winner_count"],
            "loser_count": item["loser_count"],
            "avg_net_pnl_pct": item["avg_net_pnl_pct"],
            "profit_factor": item["profit_factor"],
        }
        for item in ticker_clusters
        if int(item.get("rows") or 0) >= min_cluster_rows
        and float(item.get("avg_net_pnl_pct") or 0.0) < 0.0
        and float(item.get("winner_count") or 0) <= float(item.get("loser_count") or 0)
    ]

    debit_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    debit_upper: dict[str, float | None] = {}
    for row in lane_rows:
        bucket, upper = debit_bucket(row)
        debit_groups[bucket].append(row)
        debit_upper[bucket] = upper
    profitable_debit_uppers: list[float] = []
    debit_bucket_metrics = []
    for bucket, items in sorted(debit_groups.items()):
        values, usd_values = _marked_values(items)
        item_metrics = metrics(values, usd_values, row_count=len(items))
        debit_bucket_metrics.append({"bucket": bucket, "upper_bound_pct": debit_upper.get(bucket), **item_metrics})
        pf = item_metrics.get("profit_factor")
        avg = item_metrics.get("avg_net_pnl_pct")
        upper = debit_upper.get(bucket)
        if (
            upper is not None
            and int(item_metrics.get("priced") or 0) >= min_cluster_rows
            and _safe_float(pf) is not None
            and float(pf) >= min_profit_factor
            and _safe_float(avg) is not None
            and float(avg) > 0.0
        ):
            profitable_debit_uppers.append(float(upper))

    max_debit_pct = max(profitable_debit_uppers) if profitable_debit_uppers else None
    return {
        "blocked_tickers": blocked_tickers,
        "max_debit_pct_of_width": max_debit_pct,
        "debit_bucket_metrics": debit_bucket_metrics,
        "negative_ticker_clusters": ticker_clusters[:10],
    }


def build_lane_gate(
    *,
    playbook: str,
    lane_rows: list[dict[str, Any]],
    min_priced_rows: int,
    min_profit_factor: float,
    min_avg_net_pnl_pct: float,
    min_cluster_rows: int,
) -> dict[str, Any]:
    values, usd_values = _marked_values(lane_rows)
    summary = metrics(values, usd_values, row_count=len(lane_rows))
    blockers: list[str] = []
    if int(summary["priced"]) < min_priced_rows:
        blockers.append("insufficient_priced_exact_outcomes")
    pf = _safe_float(summary.get("profit_factor"))
    if pf is None or pf < min_profit_factor:
        blockers.append("profit_factor_below_lane_gate")
    avg = _safe_float(summary.get("avg_net_pnl_pct"))
    if avg is None or avg <= min_avg_net_pnl_pct:
        blockers.append("average_net_pnl_not_positive")
    auto_track_allowed = not blockers
    return {
        "playbook": playbook,
        "status": "candidate_flow_allowed_with_self_guardrails" if auto_track_allowed else "diagnostic_only_unprofitable_lane",
        "auto_track_allowed": auto_track_allowed,
        "basis": "untracked_missed_rows_conservative_exact_contract_mark",
        "blockers": blockers,
        "thresholds": {
            "min_priced_rows": min_priced_rows,
            "min_profit_factor": min_profit_factor,
            "min_avg_net_pnl_pct": min_avg_net_pnl_pct,
            "min_cluster_rows": min_cluster_rows,
        },
        "metrics": summary,
        "self_guardrails": build_self_guardrails(
            lane_rows,
            min_cluster_rows=min_cluster_rows,
            min_profit_factor=min_profit_factor,
        )
        if auto_track_allowed
        else {},
    }


def build_report(
    *,
    input_rows: list[dict[str, Any]],
    positions: list[dict[str, Any]],
    options_db: Path,
    source_labels: list[str],
    trusted_only: bool,
    fee_total_usd: float,
    min_priced_rows: int,
    min_profit_factor: float,
    min_avg_net_pnl_pct: float,
    min_cluster_rows: int,
    input_info: dict[str, Any],
    position_store: dict[str, Any],
) -> dict[str, Any]:
    position_index: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for position in positions:
        position_index[position_key(position)].append(position)

    conn = sqlite3.connect(options_db)
    conn.row_factory = sqlite3.Row
    try:
        latest_quote_date = _latest_intraday_date(conn)
        if not latest_quote_date:
            raise RuntimeError("No intraday quotes found in options history DB.")
        quote_evidence = quote_evidence_readback(
            snapshot_kind="intraday",
            source_labels=source_labels,
            trusted_only=trusted_only,
        )
        evidence_policy = non_production_research_policy(
            record_class="missed_regular_pick_research_mark",
            quote_evidence=quote_evidence,
        )
        outcome_rows: list[dict[str, Any]] = []
        for row in input_rows:
            row = dict(row)
            row.setdefault("playbook", _norm_text(row.get("playbook")).lower())
            row.setdefault("scan_date", _norm_text(row.get("scan_date"))[:10])
            matches = position_index.get(row_key(row), [])
            mark = conservative_mark(
                row,
                conn=conn,
                latest_quote_date=latest_quote_date,
                source_labels=source_labels,
                trusted_only=trusted_only,
                fee_total_usd=fee_total_usd,
                quote_evidence=quote_evidence,
            )
            tracked = []
            for position in matches:
                tracked.append(
                    {
                        "position_id": position.get("id"),
                        "status": position.get("status"),
                        "closed_at": position.get("closed_at"),
                        "last_reviewed_at": position.get("last_reviewed_at"),
                        "entry_execution_price": position.get("entry_execution_price"),
                        "exit_execution_price": position.get("exit_execution_price"),
                        "exit_execution_basis": position.get("exit_execution_basis"),
                        **tracked_pnl(position),
                    }
                )
            outcome_rows.append(
                {
                    "scan_date": row.get("scan_date"),
                    "playbook": row.get("playbook"),
                    "lane_label": row.get("lane_label"),
                    "ticker": _norm_text(row.get("ticker")).upper(),
                    "direction": row.get("direction") or row.get("option_type") or row.get("type"),
                    "contract_symbol": _norm_text(row.get("contract_symbol")).upper(),
                    "short_contract_symbol": _norm_text(row.get("short_contract_symbol")).upper(),
                    "expiry": row.get("expiry"),
                    "strike": _safe_float(row.get("strike") if row.get("strike") is not None else row.get("long_strike")),
                    "short_strike": _safe_float(row.get("short_strike")),
                    "dte": _safe_int(row.get("dte")),
                    "net_debit": _safe_float(row.get("net_debit") or row.get("entry_execution_price")),
                    "debit_pct_of_width": debit_pct_of_width(row),
                    "tracked_match_count": len(matches),
                    "tracked_positions": tracked,
                    "mark": mark,
                }
            )
    finally:
        conn.close()

    tracked_rows = [row for row in outcome_rows if int(row.get("tracked_match_count") or 0) > 0]
    untracked_rows = [row for row in outcome_rows if int(row.get("tracked_match_count") or 0) == 0]
    all_values, all_usd = _marked_values(outcome_rows)
    untracked_values, untracked_usd = _marked_values(untracked_rows)
    tracked_values, tracked_usd = _marked_values(tracked_rows)

    exact_counts = Counter(exact_spread_key(row) for row in outcome_rows)
    duplicate_groups = [key for key, count in exact_counts.items() if count > 1]
    by_playbook_untracked = _group_metrics(untracked_rows, "playbook")
    lane_gates = {
        playbook: build_lane_gate(
            playbook=playbook,
            lane_rows=[row for row in untracked_rows if row.get("playbook") == playbook],
            min_priced_rows=min_priced_rows,
            min_profit_factor=min_profit_factor,
            min_avg_net_pnl_pct=min_avg_net_pnl_pct,
            min_cluster_rows=min_cluster_rows,
        )
        for playbook in sorted({str(row.get("playbook") or "") for row in untracked_rows if row.get("playbook")})
    }
    lane_gate_rows = sorted(lane_gates.values(), key=lambda item: str(item.get("playbook") or ""))

    return {
        "report_id": REPORT_ID,
        "generated_at_utc": _utc_now_iso(),
        "scope": "regular_missed_pick_outcome_audit",
        "inputs": {
            "input": input_info,
            "options_db": _rel(options_db),
            "source_labels": source_labels,
            "trusted_only": trusted_only,
            "quote_evidence": quote_evidence,
            "evidence_policy": evidence_policy,
            "latest_intraday_quote_date": latest_quote_date,
            "position_store": position_store,
            "fee_total_usd": fee_total_usd,
        },
        "summary": {
            "raw_row_count": len(outcome_rows),
            "tracked_row_count": len(tracked_rows),
            "untracked_row_count": len(untracked_rows),
            "tracked_rows_with_stored_pnl": sum(
                1
                for row in tracked_rows
                for position in row.get("tracked_positions") or []
                if position.get("pnl_pct") is not None
            ),
            "mark_coverage_count": len(all_values),
            "mark_unpriced_count": len(outcome_rows) - len(all_values),
            "same_exact_spread_duplicate_group_count": len(duplicate_groups),
            "same_exact_spread_duplicate_extra_rows": len(outcome_rows) - len(exact_counts),
            "lane_gate_allowed_count": sum(1 for gate in lane_gate_rows if gate.get("auto_track_allowed")),
            "lane_gate_blocked_count": sum(1 for gate in lane_gate_rows if not gate.get("auto_track_allowed")),
        },
        "metrics": {
            "all_rows_conservative_mark": metrics(all_values, all_usd, row_count=len(outcome_rows)),
            "untracked_rows_conservative_mark": metrics(untracked_values, untracked_usd, row_count=len(untracked_rows)),
            "tracked_rows_conservative_mark": metrics(tracked_values, tracked_usd, row_count=len(tracked_rows)),
            "untracked_by_playbook": by_playbook_untracked,
        },
        "lane_gates": lane_gates,
        "lane_gate_rows": lane_gate_rows,
        "top_untracked_winners": _top_rows(untracked_rows, reverse=True),
        "top_untracked_losers": _top_rows(untracked_rows, reverse=False),
        "rows": outcome_rows,
    }


def _top_rows(rows: list[dict[str, Any]], *, reverse: bool, limit: int = 15) -> list[dict[str, Any]]:
    priced = [row for row in rows if isinstance(row.get("mark"), dict) and row["mark"].get("priced")]
    priced.sort(key=lambda row: float(row["mark"].get("net_pnl_pct") or 0.0), reverse=reverse)
    output = []
    for row in priced[:limit]:
        output.append(
            {
                "scan_date": row.get("scan_date"),
                "playbook": row.get("playbook"),
                "ticker": row.get("ticker"),
                "contract_symbol": row.get("contract_symbol"),
                "short_contract_symbol": row.get("short_contract_symbol"),
                "entry_debit": row.get("mark", {}).get("entry_debit"),
                "exit_credit": row.get("mark", {}).get("exit_credit"),
                "net_pnl_pct": row.get("mark", {}).get("net_pnl_pct"),
                "net_pnl_usd": row.get("mark", {}).get("net_pnl_usd"),
                "quote_date": row.get("mark", {}).get("quote_date"),
                "quote_evidence_class": row.get("mark", {}).get("quote_evidence_class"),
            }
        )
    return output


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    untracked = (report.get("metrics") or {}).get("untracked_rows_conservative_mark") or {}
    lines = [
        "# Missed Regular Picks Outcome Audit",
        "",
        f"- Generated: `{report.get('generated_at_utc')}`",
        f"- Raw rows: `{summary.get('raw_row_count')}`",
        f"- Already tracked rows: `{summary.get('tracked_row_count')}`",
        f"- Untracked missed rows: `{summary.get('untracked_row_count')}`",
        f"- Conservative mark coverage: `{summary.get('mark_coverage_count')}` rows",
        f"- Mark quote evidence class: `{((report.get('inputs') or {}).get('quote_evidence') or {}).get('quote_evidence_class')}`",
        f"- Row evidence group: `{((report.get('inputs') or {}).get('evidence_policy') or {}).get('evidence_group')}`",
        f"- Latest intraday quote date: `{(report.get('inputs') or {}).get('latest_intraday_quote_date')}`",
        "",
        "## Untracked Mark",
        "",
        f"- Winners / losers: `{untracked.get('winner_count')}` / `{untracked.get('loser_count')}`",
        f"- Win rate: `{untracked.get('win_rate_pct')}%`",
        f"- Avg net P&L: `{untracked.get('avg_net_pnl_pct')}%`",
        f"- Median net P&L: `{untracked.get('median_net_pnl_pct')}%`",
        f"- Profit factor: `{untracked.get('profit_factor')}`",
        f"- 1-spread net dollars: `${untracked.get('sum_net_pnl_usd')}`",
        "",
        "## Lane Gates",
        "",
        "| Lane | Status | Rows | PF | Avg Net P&L | Winners | Losers | Self Guardrails |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for gate in report.get("lane_gate_rows") or []:
        metric = gate.get("metrics") or {}
        guardrails = gate.get("self_guardrails") or {}
        blocked_tickers = [item.get("ticker") for item in guardrails.get("blocked_tickers") or []]
        max_debit = guardrails.get("max_debit_pct_of_width")
        guardrail_text = []
        if blocked_tickers:
            guardrail_text.append("blocked tickers: " + ",".join(str(item) for item in blocked_tickers))
        if max_debit is not None:
            guardrail_text.append(f"max debit {max_debit}%")
        lines.append(
            "| "
            + " | ".join(
                [
                    str(gate.get("playbook") or ""),
                    str(gate.get("status") or ""),
                    str(metric.get("priced")),
                    str(metric.get("profit_factor")),
                    str(metric.get("avg_net_pnl_pct")),
                    str(metric.get("winner_count")),
                    str(metric.get("loser_count")),
                    "; ".join(guardrail_text) or "none",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- This is historical/research mark evidence, not broker fills.",
            "- `quote_evidence_class` describes the quote source used for the mark; it does not make the historical missed-pick row production proof.",
            "- Lane gates are allowed to route candidates into validation only when the lane has enough exact rows, positive average net P&L, and profit factor above threshold.",
            "- Profitable lanes still carry self-guardrails learned from negative clusters.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path, doc_path: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    latest_json = output_dir / f"{REPORT_ID}_latest.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_md = output_dir / f"{REPORT_ID}_latest.md"
    artifacts = {
        "json": str(json_path),
        "latest_json": str(latest_json),
        "markdown": str(md_path),
        "latest_markdown": str(latest_md),
        "docs_report": str(doc_path),
    }
    report_with_artifacts = dict(report)
    report_with_artifacts["artifacts"] = artifacts
    payload = json.dumps(report_with_artifacts, indent=2, sort_keys=True)
    markdown = render_markdown(report_with_artifacts)
    json_path.write_text(payload + "\n", encoding="utf-8")
    latest_json.write_text(payload + "\n", encoding="utf-8")
    md_path.write_text(markdown + "\n", encoding="utf-8")
    latest_md.write_text(markdown + "\n", encoding="utf-8")
    doc_path.write_text(markdown + "\n", encoding="utf-8")
    return artifacts


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit tracked status and exact-contract outcomes for missed regular picks.")
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--all-lanes-report", type=Path, default=DEFAULT_ALL_LANES_REPORT)
    parser.add_argument("--options-db", type=Path, default=DEFAULT_OPTIONS_DB)
    parser.add_argument("--source-labels", default="thetadata_opra_nbbo_1m")
    parser.add_argument("--allow-research-data", action="store_true")
    parser.add_argument("--fee-total-usd", type=float, default=2.60)
    parser.add_argument("--min-priced-rows", type=int, default=10)
    parser.add_argument("--min-profit-factor", type=float, default=1.10)
    parser.add_argument("--min-avg-net-pnl-pct", type=float, default=0.0)
    parser.add_argument("--min-cluster-rows", type=int, default=2)
    parser.add_argument("--skip-position-store", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--doc-path", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source_labels = [
        item.strip()
        for item in str(args.source_labels or "").replace(";", ",").split(",")
        if item.strip()
    ]
    rows, input_info = load_input_rows(args.input_csv, args.all_lanes_report)
    positions, position_store = load_positions(skip_position_store=bool(args.skip_position_store))
    report = build_report(
        input_rows=rows,
        positions=positions,
        options_db=args.options_db,
        source_labels=source_labels,
        trusted_only=not bool(args.allow_research_data),
        fee_total_usd=float(args.fee_total_usd),
        min_priced_rows=max(int(args.min_priced_rows), 1),
        min_profit_factor=float(args.min_profit_factor),
        min_avg_net_pnl_pct=float(args.min_avg_net_pnl_pct),
        min_cluster_rows=max(int(args.min_cluster_rows), 1),
        input_info=input_info,
        position_store=position_store,
    )
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, doc_path=args.doc_path)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        payload = {
            "summary": report["summary"],
            "quote_evidence": report["inputs"]["quote_evidence"],
            "evidence_policy": report["inputs"]["evidence_policy"],
            "untracked_rows_conservative_mark": report["metrics"]["untracked_rows_conservative_mark"],
            "lane_gate_rows": [
                {
                    "playbook": gate["playbook"],
                    "status": gate["status"],
                    "auto_track_allowed": gate["auto_track_allowed"],
                    "blockers": gate["blockers"],
                    "metrics": gate["metrics"],
                    "self_guardrails": gate.get("self_guardrails"),
                }
                for gate in report["lane_gate_rows"]
            ],
            "artifacts": report.get("artifacts"),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
