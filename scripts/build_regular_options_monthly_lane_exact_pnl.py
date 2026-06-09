from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_monthly_lane_exact_pnl"

DEFAULT_MULTILANE = ROOT / "data" / "profitability-lab" / "regular-options-multilane" / "latest.json"
DEFAULT_DB_PATH = Path(os.getenv("HISTORICAL_OPTIONS_DB_PATH", str(ROOT / "data" / "options-validation" / "options_history.db")))
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_SOURCE_LABELS = ("thetadata_opra_nbbo_1m",)

INTRADAY_SNAPSHOT_KIND = "intraday"
TRUSTED_DATA_TRUST = "trusted"
ENTRY_START_MINUTE_ET = 10 * 60 + 10
ENTRY_END_MINUTE_ET = 10 * 60 + 25
EXIT_MINUTE_ET = 15 * 60 + 55
COMMISSION_PER_CONTRACT_USD = 0.65
CONTRACT_MULTIPLIER = 100.0

PROHIBITED_ACTIONS = (
    "do_not_create_live_row_from_monthly_lane_exact_pnl",
    "do_not_submit_broker_order_from_monthly_lane_exact_pnl",
    "do_not_mutate_database_from_monthly_lane_exact_pnl",
    "do_not_change_scanner_policy_from_monthly_lane_exact_pnl",
    "do_not_change_contract_selection_from_monthly_lane_exact_pnl",
    "do_not_change_stop_policy_from_monthly_lane_exact_pnl",
    "do_not_change_sizing_from_monthly_lane_exact_pnl",
    "do_not_lower_exact_opra_nbbo_proof_bar_from_monthly_lane_exact_pnl",
    "do_not_promote_research_or_backfill_rows_to_production_proof",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _norm(value: Any) -> str:
    return str(value or "").strip()


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
    meta = {"path": str(path), "exists": path.exists(), "status": "missing", "error": None}
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


def _sqlite_readonly_connect(path: Path) -> sqlite3.Connection:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def _source_labels_clause(source_labels: Sequence[str]) -> tuple[str, list[Any]]:
    labels = [str(label).strip() for label in source_labels if str(label).strip()]
    if not labels:
        return "", []
    placeholders = ", ".join("?" for _ in labels)
    return f" AND b.source_label IN ({placeholders})", labels


def _quote_lookup(
    conn: sqlite3.Connection,
    *,
    contract_symbol: str,
    quote_date_et: str,
    start_minute_et: int,
    end_minute_et: int,
    prefer_latest: bool,
    source_labels: Sequence[str],
) -> dict[str, Any] | None:
    source_clause, source_params = _source_labels_clause(source_labels)
    order = "DESC" if prefer_latest else "ASC"
    row = conn.execute(
        f"""
        SELECT
            q.contract_symbol,
            q.quote_date_et,
            q.quote_minute_et,
            q.as_of_utc,
            q.bid,
            q.ask,
            q.underlying_price,
            b.source_label,
            b.data_trust
        FROM option_quote_snapshots q
        JOIN import_batches b ON b.id = q.source_batch_id
        WHERE q.contract_symbol = ?
          AND q.snapshot_kind = ?
          AND q.quote_date_et = ?
          AND q.quote_minute_et >= ?
          AND q.quote_minute_et <= ?
          AND q.bid IS NOT NULL
          AND q.ask IS NOT NULL
          AND q.bid >= 0
          AND q.ask > 0
          AND q.ask >= q.bid
          AND b.data_trust = ?
          {source_clause}
        ORDER BY q.quote_minute_et {order}, q.as_of_utc {order}
        LIMIT 1
        """,
        (
            contract_symbol,
            INTRADAY_SNAPSHOT_KIND,
            quote_date_et,
            int(start_minute_et),
            int(end_minute_et),
            TRUSTED_DATA_TRUST,
            *source_params,
        ),
    ).fetchone()
    if row is None:
        return None
    bid = _safe_float(row["bid"])
    ask = _safe_float(row["ask"])
    if bid is None or ask is None:
        return None
    return {
        "contract_symbol": str(row["contract_symbol"]),
        "quote_date_et": str(row["quote_date_et"]),
        "quote_minute_et": int(row["quote_minute_et"]),
        "as_of_utc": str(row["as_of_utc"]),
        "bid": round(float(bid), 4),
        "ask": round(float(ask), 4),
        "underlying_price": _safe_float(row["underlying_price"]),
        "source_label": str(row["source_label"]),
        "data_trust": str(row["data_trust"]),
        "quote_evidence_class": "trusted_intraday_opra_nbbo",
    }


def _entry_debit(long_quote: dict[str, Any], short_quote: dict[str, Any]) -> float | None:
    long_ask = _safe_float(long_quote.get("ask"))
    short_bid = _safe_float(short_quote.get("bid"))
    if long_ask is None or short_bid is None:
        return None
    debit = round(long_ask - short_bid, 4)
    return debit if debit > 0 else None


def _exit_value(long_quote: dict[str, Any], short_quote: dict[str, Any]) -> float | None:
    long_bid = _safe_float(long_quote.get("bid"))
    short_ask = _safe_float(short_quote.get("ask"))
    if long_bid is None or short_ask is None:
        return None
    return round(long_bid - short_ask, 4)


def _direction_from_contract(symbol: str) -> str | None:
    text = _norm(symbol).upper()
    if len(text) < 9:
        return None
    marker = text[-9:-8]
    if marker == "C":
        return "call"
    if marker == "P":
        return "put"
    return None


def _selected_spread(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _run_truth_is_exact_intraday(run: dict[str, Any]) -> bool:
    basis = _norm(run.get("authoritative_profitability_basis")).lower()
    truth = _norm(run.get("truth_source")).lower()
    realism = _norm(run.get("execution_realism")).lower()
    truth_store = run.get("truth_store") if isinstance(run.get("truth_store"), dict) else {}
    return (
        basis == "exact_contract_only"
        and truth == "historical_imported"
        and realism == "quote_backed_intraday_replay"
        and _norm(truth_store.get("snapshot_kind")).lower() == INTRADAY_SNAPSHOT_KIND
        and _norm(truth_store.get("data_trust")).lower() == TRUSTED_DATA_TRUST
    )


def _normalize_run_trade(raw: dict[str, Any], *, run: dict[str, Any], target_lane: str | None, source_row_kind: str) -> dict[str, Any]:
    selected = _selected_spread(raw.get("selected_spread"))
    long_contract = (
        _norm(raw.get("contract_symbol"))
        or _norm(raw.get("long_contract_symbol"))
        or _norm(raw.get("missing_long_contract_symbol"))
        or _norm(selected.get("long_contract_symbol"))
    ).upper()
    short_contract = (
        _norm(raw.get("short_contract_symbol"))
        or _norm(raw.get("missing_short_contract_symbol"))
        or _norm(selected.get("short_contract_symbol"))
    ).upper()
    entry_date = _norm(raw.get("entry_date")) or _norm(raw.get("date")) or _norm(selected.get("entry_date"))
    unpriced_reason = _norm(raw.get("unpriced_reason"))
    missing_quote_date = _norm(raw.get("missing_quote_date"))
    exit_date = _norm(raw.get("exit_date"))
    if not exit_date and source_row_kind == "run_unpriced_trade" and "exit" in unpriced_reason:
        exit_date = missing_quote_date
    lane_id = _norm(raw.get("sleeve_id")) or _norm(raw.get("tier_id")) or _norm(run.get("playbook"))
    lane = _norm(target_lane) or lane_id
    return {
        "entry_date": entry_date,
        "exit_date": exit_date,
        "exact_priced": bool(raw.get("priced")) and source_row_kind == "run_trade",
        "priced": bool(raw.get("priced")) and source_row_kind == "run_trade",
        "proof_grade": "trusted_intraday_opra_nbbo",
        "lane_family": lane,
        "lane_id": lane_id,
        "ticker": raw.get("ticker"),
        "direction": raw.get("direction") or _direction_from_contract(long_contract),
        "strategy_type": raw.get("strategy_type"),
        "long_contract_symbol": long_contract,
        "short_contract_symbol": short_contract,
        "source_playbook": run.get("playbook"),
        "source_result_path": run.get("result_path"),
        "source_row_kind": source_row_kind,
        "source_unpriced_reason": raw.get("unpriced_reason"),
        "pnl_pct": raw.get("net_pnl_pct", raw.get("pnl_pct")),
    }


def _regular_source_rows(multilane: dict[str, Any], *, target_lane: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in multilane.get("selected_trades") or []:
        if not isinstance(raw, dict):
            continue
        if not bool(raw.get("priced")) or not bool(raw.get("exact_priced")):
            continue
        if _norm(raw.get("proof_grade")) != "trusted_intraday_opra_nbbo":
            continue
        if not _norm(raw.get("entry_date")) or not _norm(raw.get("exit_date")):
            continue
        if not _norm(raw.get("long_contract_symbol")) or not _norm(raw.get("short_contract_symbol")):
            continue
        rows.append(raw)
    if _run_truth_is_exact_intraday(multilane):
        for raw in multilane.get("trades") or []:
            if not isinstance(raw, dict):
                continue
            if not bool(raw.get("priced")):
                continue
            rows.append(_normalize_run_trade(raw, run=multilane, target_lane=target_lane, source_row_kind="run_trade"))
        for raw in multilane.get("unpriced_trades") or []:
            if not isinstance(raw, dict):
                continue
            rows.append(
                _normalize_run_trade(raw, run=multilane, target_lane=target_lane, source_row_kind="run_unpriced_trade")
            )
    return rows


def _select_target(rows: list[dict[str, Any]], *, target_month: str | None, target_lane: str | None) -> tuple[str | None, str | None]:
    if target_month and target_lane:
        return target_month, target_lane
    grouped: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        month = _norm(row.get("entry_date"))[:7]
        lane = _norm(row.get("lane_family")) or _norm(row.get("lane_id"))
        if not month or not lane:
            continue
        if target_month and month != target_month:
            continue
        if target_lane and lane != target_lane:
            continue
        grouped[(month, lane)] += 1
    if not grouped:
        return target_month, target_lane
    earliest_month = min(month for month, _lane in grouped)
    month_rows = [(lane, count) for (month, lane), count in grouped.items() if month == earliest_month]
    selected_lane = sorted(month_rows, key=lambda item: (-item[1], item[0]))[0][0]
    return target_month or earliest_month, target_lane or selected_lane


def _evaluate_row(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    *,
    source_labels: Sequence[str],
) -> dict[str, Any]:
    long_symbol = _norm(row.get("long_contract_symbol")).upper()
    short_symbol = _norm(row.get("short_contract_symbol")).upper()
    entry_date = _norm(row.get("entry_date"))[:10]
    exit_date = _norm(row.get("exit_date"))[:10]
    result: dict[str, Any] = {
        "lane_month": entry_date[:7],
        "lane": _norm(row.get("lane_family")) or _norm(row.get("lane_id")),
        "lane_id": row.get("lane_id"),
        "ticker": row.get("ticker"),
        "direction": row.get("direction"),
        "strategy_type": row.get("strategy_type"),
        "entry_date": entry_date,
        "exit_date": exit_date,
        "long_contract_symbol": long_symbol,
        "short_contract_symbol": short_symbol,
        "source_playbook": row.get("source_playbook"),
        "source_result_path": row.get("source_result_path"),
        "source_summary_pnl_pct": row.get("pnl_pct"),
        "contract_quantity": 1,
        "fees_slippage_assumption": {
            "gross_pnl": "no extra fees or slippage beyond executable bid/ask side pricing",
            "net_pnl": "0.65 USD per contract for 2 legs on entry and 2 legs on exit; no additional slippage",
            "commission_per_contract_usd": COMMISSION_PER_CONTRACT_USD,
        },
        "true_executable_pnl_available": False,
        "decision": "reject_missing_exact_lane_month_pnl",
        "blockers": [],
    }
    blockers: list[str] = []
    if not long_symbol:
        blockers.append("missing_long_contract_symbol")
    if not short_symbol:
        blockers.append("missing_short_contract_symbol")
    if not entry_date:
        blockers.append("missing_entry_date")
    if not exit_date:
        blockers.append("missing_exit_date")
    if blockers:
        result["blockers"] = blockers
        return result

    entry_long = _quote_lookup(
        conn,
        contract_symbol=long_symbol,
        quote_date_et=entry_date,
        start_minute_et=ENTRY_START_MINUTE_ET,
        end_minute_et=ENTRY_END_MINUTE_ET,
        prefer_latest=False,
        source_labels=source_labels,
    )
    entry_short = _quote_lookup(
        conn,
        contract_symbol=short_symbol,
        quote_date_et=entry_date,
        start_minute_et=ENTRY_START_MINUTE_ET,
        end_minute_et=ENTRY_END_MINUTE_ET,
        prefer_latest=False,
        source_labels=source_labels,
    )
    exit_long = _quote_lookup(
        conn,
        contract_symbol=long_symbol,
        quote_date_et=exit_date,
        start_minute_et=EXIT_MINUTE_ET,
        end_minute_et=EXIT_MINUTE_ET,
        prefer_latest=True,
        source_labels=source_labels,
    )
    exit_short = _quote_lookup(
        conn,
        contract_symbol=short_symbol,
        quote_date_et=exit_date,
        start_minute_et=EXIT_MINUTE_ET,
        end_minute_et=EXIT_MINUTE_ET,
        prefer_latest=True,
        source_labels=source_labels,
    )
    result.update(
        {
            "entry_long_quote": entry_long,
            "entry_short_quote": entry_short,
            "exit_long_quote": exit_long,
            "exit_short_quote": exit_short,
        }
    )
    if entry_long is None:
        blockers.append("missing_entry_long_quote")
    if entry_short is None:
        blockers.append("missing_entry_short_quote")
    if exit_long is None:
        blockers.append("missing_exit_long_quote")
    if exit_short is None:
        blockers.append("missing_exit_short_quote")
    result["entry_pair_complete"] = entry_long is not None and entry_short is not None
    result["exit_pair_complete"] = exit_long is not None and exit_short is not None
    if result["entry_pair_complete"] and result["exit_pair_complete"]:
        entry_debit = _entry_debit(entry_long, entry_short)  # type: ignore[arg-type]
        exit_side_value = _exit_value(exit_long, exit_short)  # type: ignore[arg-type]
        if entry_debit is not None and exit_side_value is not None:
            gross_pnl_per_spread = round(exit_side_value - entry_debit, 4)
            gross_pnl_usd = round(gross_pnl_per_spread * CONTRACT_MULTIPLIER, 2)
            fee_total = round(COMMISSION_PER_CONTRACT_USD * 4, 2)
            net_pnl_usd = round(gross_pnl_usd - fee_total, 2)
            capital_at_risk = entry_debit * CONTRACT_MULTIPLIER
            result.update(
                {
                    "entry_side_aware_debit": entry_debit,
                    "exit_side_aware_value": exit_side_value,
                    "gross_pnl_per_spread": gross_pnl_per_spread,
                    "gross_pnl_usd": gross_pnl_usd,
                    "gross_pnl_pct": round((gross_pnl_per_spread / entry_debit) * 100.0, 2),
                    "fee_total_usd": fee_total,
                    "net_pnl_usd": net_pnl_usd,
                    "net_pnl_pct": round((net_pnl_usd / capital_at_risk) * 100.0, 2),
                    "true_executable_pnl_available": True,
                    "decision": "count_as_read_only_lane_month_exact_pnl",
                }
            )
        else:
            blockers.append("non_positive_entry_side_aware_debit")
    result["blockers"] = blockers
    return result


def _pnl_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [_safe_float(row.get("net_pnl_pct")) for row in rows]
    values = [value for value in values if value is not None]
    usd_values = [_safe_float(row.get("net_pnl_usd")) for row in rows]
    usd_values = [value for value in usd_values if value is not None]
    winners = [value for value in values if value > 0]
    losers = [value for value in values if value < 0]
    gross_profit = round(sum(winners), 2)
    gross_loss = round(abs(sum(losers)), 2)
    return {
        "rows": len(rows),
        "true_executable_pnl_rows": len(values),
        "winner_count": len(winners),
        "loser_count": len(losers),
        "win_rate_pct": round(len(winners) / len(values) * 100.0, 2) if values else None,
        "avg_net_pnl_pct": round(sum(values) / len(values), 2) if values else None,
        "sum_net_pnl_usd": round(sum(usd_values), 2) if usd_values else None,
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss else (gross_profit if gross_profit > 0 else None),
        "gross_profit_pct_sum": gross_profit,
        "gross_loss_pct_sum": gross_loss,
    }


def _month_counts(rows: list[dict[str, Any]], lane: str) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        if (_norm(row.get("lane_family")) or _norm(row.get("lane_id"))) != lane:
            continue
        month = _norm(row.get("entry_date"))[:7]
        if month:
            counts[month] += 1
    return dict(sorted(counts.items()))


def build_report(
    *,
    multilane_path: Path = DEFAULT_MULTILANE,
    db_path: Path = DEFAULT_DB_PATH,
    target_month: str | None = None,
    target_lane: str | None = None,
    source_labels: Sequence[str] = DEFAULT_SOURCE_LABELS,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    multilane, multilane_meta = _load_json(multilane_path)
    missing_required: list[str] = []
    if multilane_meta.get("status") != "loaded":
        missing_required.append("regular_options_multilane")
    if not db_path.exists():
        missing_required.append("options_history_db")
    source_rows = _regular_source_rows(multilane, target_lane=target_lane) if not missing_required else []
    selected_month, selected_lane = _select_target(source_rows, target_month=target_month, target_lane=target_lane)
    target_rows = [
        row
        for row in source_rows
        if _norm(row.get("entry_date"))[:7] == _norm(selected_month)
        and (_norm(row.get("lane_family")) or _norm(row.get("lane_id"))) == _norm(selected_lane)
    ]
    replay_rows: list[dict[str, Any]] = []
    quote_store_error: str | None = None
    if not missing_required and target_rows:
        try:
            with closing(_sqlite_readonly_connect(db_path)) as conn:
                replay_rows = [_evaluate_row(conn, row, source_labels=source_labels) for row in target_rows]
        except sqlite3.Error as exc:
            quote_store_error = f"{type(exc).__name__}: {exc}"

    true_rows = [row for row in replay_rows if row.get("true_executable_pnl_available")]
    missing_proof_rows = [row for row in replay_rows if not row.get("true_executable_pnl_available")]
    status = "blocked_missing_inputs" if missing_required else "lane_month_exact_pnl_available"
    if not missing_required and not target_rows:
        status = "blocked_no_lane_month_source_rows"
    if quote_store_error:
        status = "blocked_quote_store_error"
    elif not missing_required and target_rows and missing_proof_rows:
        status = "lane_month_exact_pnl_partial"

    all_month_counts = _month_counts(source_rows, selected_lane or "") if selected_lane else {}
    later_months = {month: count for month, count in all_month_counts.items() if selected_month and month > selected_month}
    summary = {
        "overall_status": status,
        "readback_status": "monthly_lane_exact_pnl_readback",
        "target_month": selected_month,
        "target_lane": selected_lane,
        "earliest_available_month": min(all_month_counts) if all_month_counts else None,
        "source_candidate_count": len(target_rows),
        "true_executable_lane_month_pnl_rows": len(true_rows),
        "missing_proof_count": len(missing_proof_rows),
        "source_label_count": len([label for label in source_labels if str(label).strip()]),
        "quote_store_error": quote_store_error,
        "missing_required_inputs": missing_required,
        "metrics": _pnl_metrics(true_rows),
        "later_month_holdout_status": "pending_exact_quote_attachment" if later_months else "no_later_month_rows_available",
        "later_month_source_counts": later_months,
        "decision": (
            "freeze_proof_only_until_later_month_exact_holdout"
            if true_rows and later_months
            else "repair_missing_exact_lane_month_quotes"
            if missing_proof_rows
            else "blocked"
        ),
    }
    return {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_read_only_monthly_lane_exact_pnl",
        "read_only": True,
        "live_policy_change": False,
        "status": status,
        "inputs": {
            "regular_options_multilane": multilane_meta,
            "options_history_db": {"path": str(db_path), "exists": db_path.exists()},
            "source_labels": list(source_labels),
            "entry_window_minutes_et": [ENTRY_START_MINUTE_ET, ENTRY_END_MINUTE_ET],
            "exit_minute_et": EXIT_MINUTE_ET,
        },
        "summary": summary,
        "lane_month_rows": replay_rows,
        "prohibited_actions": list(PROHIBITED_ACTIONS),
        "proof_policy": {
            "trusted_proof_standard": "exact contract intraday OPRA/NBBO bid/ask rows with side-aware executable entry and exit pricing",
            "readback_is": "read-only lane-month executable P&L evidence",
            "readback_is_not": "scanner policy, live activation, broker order, DB mutation, threshold tuning, or production proof promotion",
        },
    }


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    latest_json = output_dir / f"{REPORT_ID}_latest.json"
    payload = json.dumps(report, indent=2, sort_keys=True)
    json_path.write_text(payload + "\n", encoding="utf8")
    latest_json.write_text(payload + "\n", encoding="utf8")
    return {"json": str(json_path), "latest_json": str(latest_json)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build read-only exact OPRA/NBBO lane-month executable P&L.")
    parser.add_argument("--multilane", type=Path, default=DEFAULT_MULTILANE)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--target-month", default=None)
    parser.add_argument("--target-lane", default=None)
    parser.add_argument("--source-labels", default=",".join(DEFAULT_SOURCE_LABELS))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)
    source_labels = [item.strip() for item in str(args.source_labels).split(",") if item.strip()]
    report = build_report(
        multilane_path=args.multilane,
        db_path=args.db_path,
        target_month=args.target_month,
        target_lane=args.target_lane,
        source_labels=source_labels,
    )
    artifacts = None if args.no_write else write_outputs(report, output_dir=args.output_dir)
    if args.json:
        payload: dict[str, Any] = {"report": report}
        if artifacts:
            payload["artifacts"] = artifacts
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(json.dumps({"summary": report["summary"], "artifacts": artifacts}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
