from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regime_stratified_replay_report"

DEFAULT_SOURCE = ROOT / "data" / "profitability-lab" / "regular-options-multilane" / "latest.json"
DEFAULT_SOURCE_PATHS = (DEFAULT_SOURCE,)
DEFAULT_MARKET_DATA_DB = Path(os.getenv("MARKET_DATA_DB_PATH", str(ROOT / "market_data.db")))
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regime-stratified-replay"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regime-stratified-replay-report.md"

SPY_SYMBOL = "SPY"
VIX_SYMBOL_CANDIDATES = ("^VIX", "VIX")
MAX_CONTEXT_AGE_DAYS = 7
MAX_PLAUSIBLE_VIX_CLOSE = 100.0

MIN_ROBUST_BUCKET_N = 15
REGIME_DIMENSIONS = ("vix_tercile", "spy_50d_trend_state", "entry_month")

PROHIBITED_ACTIONS = (
    "do_not_create_live_row_from_regime_stratified_replay_report",
    "do_not_submit_broker_order_from_regime_stratified_replay_report",
    "do_not_mutate_database_from_regime_stratified_replay_report",
    "do_not_change_scanner_policy_from_regime_stratified_replay_report",
    "do_not_change_thresholds_from_regime_stratified_replay_report",
    "do_not_lower_exact_opra_nbbo_proof_bar_from_regime_stratified_replay_report",
    "do_not_promote_research_or_backfill_rows_to_production_proof",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _json_inline(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _safe_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _date_only(value: Any) -> date | None:
    raw = _norm(value)[:10]
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


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


def _load_sources(paths: Sequence[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payloads: list[dict[str, Any]] = []
    metas: list[dict[str, Any]] = []
    for path in paths:
        payload, meta = _load_json(path)
        metas.append(meta)
        if meta.get("status") == "loaded":
            payloads.append(payload)
    return payloads, metas


def _sqlite_readonly_connect(path: Path) -> sqlite3.Connection:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def _load_daily_history(
    db_path: Path,
    *,
    symbols: Sequence[str],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    meta = {"path": str(db_path), "exists": db_path.exists(), "status": "missing", "error": None}
    if not db_path.exists():
        meta["error"] = "missing_market_data_db"
        return {}, meta
    try:
        conn = _sqlite_readonly_connect(db_path)
        try:
            placeholders = ", ".join("?" for _ in symbols)
            rows = conn.execute(
                f"""
                SELECT symbol, bar_date, close, source
                FROM daily_history
                WHERE symbol IN ({placeholders})
                  AND close IS NOT NULL
                ORDER BY symbol, bar_date
                """,
                tuple(symbols),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return {}, meta

    history: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in symbols}
    for row in rows:
        parsed_date = _date_only(row["bar_date"])
        close = _safe_float(row["close"])
        symbol = str(row["symbol"])
        if parsed_date is None or close is None:
            continue
        history.setdefault(symbol, []).append(
            {
                "symbol": symbol,
                "bar_date": parsed_date.isoformat(),
                "date": parsed_date,
                "close": close,
                "source": row["source"],
            }
        )
    meta["status"] = "loaded"
    meta["symbols"] = {
        symbol: {
            "rows": len(items),
            "min_date": items[0]["bar_date"] if items else None,
            "max_date": items[-1]["bar_date"] if items else None,
            "sources": dict(Counter(str(item.get("source") or "unknown") for item in items)),
        }
        for symbol, items in history.items()
    }
    return history, meta


def _missed_outcome_row(raw: dict[str, Any]) -> dict[str, Any] | None:
    mark = _as_dict(raw.get("mark"))
    if not bool(mark.get("priced")):
        return None
    if _norm(mark.get("quote_evidence_class")) != "trusted_intraday_opra_nbbo":
        return None
    entry = _date_only(raw.get("scan_date"))
    net_pnl_pct = _safe_float(mark.get("net_pnl_pct"))
    net_pnl_usd = _safe_float(mark.get("net_pnl_usd"))
    if entry is None or net_pnl_pct is None:
        return None
    return {
        "source_schema": "missed_regular_picks_outcome.rows",
        "entry_date": entry.isoformat(),
        "lane": _norm(raw.get("playbook")) or _norm(raw.get("lane_label")) or "unknown_lane",
        "ticker": _norm(raw.get("ticker")) or "UNKNOWN",
        "net_pnl_pct": net_pnl_pct,
        "net_pnl_usd": net_pnl_usd,
        "quote_evidence_class": mark.get("quote_evidence_class"),
        "production_proof": bool(mark.get("production_proof")),
    }


def _lane_month_row(raw: dict[str, Any]) -> dict[str, Any] | None:
    if not bool(raw.get("true_executable_pnl_available")):
        return None
    entry = _date_only(raw.get("entry_date"))
    net_pnl_pct = _safe_float(raw.get("net_pnl_pct"))
    net_pnl_usd = _safe_float(raw.get("net_pnl_usd"))
    if entry is None or net_pnl_pct is None:
        return None
    return {
        "source_schema": "regular_options_monthly_lane_exact_pnl.lane_month_rows",
        "entry_date": entry.isoformat(),
        "lane": _norm(raw.get("lane")) or _norm(raw.get("lane_id")) or "unknown_lane",
        "ticker": _norm(raw.get("ticker")) or "UNKNOWN",
        "net_pnl_pct": net_pnl_pct,
        "net_pnl_usd": net_pnl_usd,
        "quote_evidence_class": "trusted_intraday_opra_nbbo",
        "production_proof": False,
    }


def _selected_trade_row(raw: dict[str, Any]) -> dict[str, Any] | None:
    if not bool(raw.get("priced")) or not bool(raw.get("exact_priced")):
        return None
    if _norm(raw.get("proof_grade")) != "trusted_intraday_opra_nbbo":
        return None
    entry = _date_only(raw.get("entry_date"))
    net_pnl_pct = _safe_float(raw.get("pnl_pct") if raw.get("pnl_pct") is not None else raw.get("net_pnl_pct"))
    if entry is None or net_pnl_pct is None:
        return None
    return {
        "source_schema": "regular_options_multilane.selected_trades",
        "entry_date": entry.isoformat(),
        "lane": _norm(raw.get("lane_id")) or _norm(raw.get("lane_family")) or "unknown_lane",
        "lane_family": _norm(raw.get("lane_family")) or None,
        "ticker": _norm(raw.get("ticker")) or "UNKNOWN",
        "net_pnl_pct": net_pnl_pct,
        "net_pnl_usd": _safe_float(raw.get("net_pnl_usd")),
        "quote_evidence_class": raw.get("proof_grade"),
        "production_proof": False,
    }


def _extract_replay_rows(payloads: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    source_counts: Counter[str] = Counter()
    candidate_count = 0

    for payload in payloads:
        for raw in _as_list(payload.get("rows")):
            if not isinstance(raw, dict):
                continue
            candidate_count += 1
            normalized = _missed_outcome_row(raw)
            if normalized is not None:
                rows.append(normalized)
                source_counts[normalized["source_schema"]] += 1

        for raw in _as_list(payload.get("lane_month_rows")):
            if not isinstance(raw, dict):
                continue
            candidate_count += 1
            normalized = _lane_month_row(raw)
            if normalized is not None:
                rows.append(normalized)
                source_counts[normalized["source_schema"]] += 1

        for raw in _as_list(payload.get("selected_trades")):
            if not isinstance(raw, dict):
                continue
            candidate_count += 1
            normalized = _selected_trade_row(raw)
            if normalized is not None:
                rows.append(normalized)
                source_counts[normalized["source_schema"]] += 1

    return rows, {
        "source_candidate_count": candidate_count,
        "eligible_replay_row_count": len(rows),
        "source_schema_counts": dict(source_counts),
    }


def _choose_vix_symbol(history: dict[str, list[dict[str, Any]]]) -> str | None:
    for symbol in VIX_SYMBOL_CANDIDATES:
        if history.get(symbol):
            return symbol
    return None


def _previous_bar(items: list[dict[str, Any]], entry: date) -> tuple[int, dict[str, Any] | None]:
    previous_index = -1
    for index, item in enumerate(items):
        item_date = item["date"]
        if item_date >= entry:
            break
        previous_index = index
    if previous_index < 0:
        return -1, None
    return previous_index, items[previous_index]


def _context_age_days(entry: date, bar: dict[str, Any] | None) -> int | None:
    if bar is None:
        return None
    return (entry - bar["date"]).days


def _spy_50d_context(items: list[dict[str, Any]], entry: date) -> tuple[dict[str, Any] | None, str | None]:
    index, bar = _previous_bar(items, entry)
    if bar is None:
        return None, "spy_prior_close_missing"
    age = _context_age_days(entry, bar)
    if age is None or age > MAX_CONTEXT_AGE_DAYS:
        return None, "spy_prior_close_stale"
    if index < 49:
        return None, "spy_50d_history_missing"
    closes = [float(item["close"]) for item in items[index - 49 : index + 1]]
    sma50 = sum(closes) / len(closes)
    close = float(bar["close"])
    if close > sma50:
        state = "above_sma50"
    elif close < sma50:
        state = "below_sma50"
    else:
        state = "at_sma50"
    return {
        "spy_asof_date": bar["bar_date"],
        "spy_close": round(close, 4),
        "spy_sma50": round(sma50, 4),
        "spy_50d_trend_state": state,
        "spy_context_age_days": age,
    }, None


def _vix_context(items: list[dict[str, Any]], entry: date) -> tuple[dict[str, Any] | None, str | None]:
    _index, bar = _previous_bar(items, entry)
    if bar is None:
        return None, "vix_prior_close_missing"
    age = _context_age_days(entry, bar)
    if age is None or age > MAX_CONTEXT_AGE_DAYS:
        return None, "vix_prior_close_stale"
    close = _safe_float(bar.get("close"))
    if close is None or close <= 0:
        return None, "vix_close_invalid"
    if close > MAX_PLAUSIBLE_VIX_CLOSE:
        return None, "vix_close_outside_plausible_range"
    return {
        "vix_asof_date": bar["bar_date"],
        "vix_close": round(close, 4),
        "vix_context_age_days": age,
    }, None


def _tercile_thresholds(values: Sequence[float]) -> dict[str, float] | None:
    clean = sorted(float(value) for value in values if math.isfinite(float(value)))
    if len(clean) < 3:
        return None
    low_index = max(0, min(len(clean) - 1, math.ceil(len(clean) / 3) - 1))
    high_index = max(0, min(len(clean) - 1, math.ceil((len(clean) * 2) / 3) - 1))
    return {
        "low_max": round(clean[low_index], 4),
        "mid_max": round(clean[high_index], 4),
    }


def _assign_vix_tercile(value: float | None, thresholds: dict[str, float] | None) -> str:
    if value is None:
        return "vix_missing"
    if thresholds is None:
        return "vix_tercile_unavailable"
    if value <= thresholds["low_max"]:
        return "low"
    if value <= thresholds["mid_max"]:
        return "mid"
    return "high"


def _annotate_rows(
    rows: list[dict[str, Any]],
    history: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    spy_history = history.get(SPY_SYMBOL, [])
    vix_symbol = _choose_vix_symbol(history)
    vix_history = history.get(vix_symbol or "", [])
    reason_counts: Counter[str] = Counter()
    partially_annotated: list[dict[str, Any]] = []
    valid_vix_values: list[float] = []

    for row in rows:
        entry = _date_only(row.get("entry_date"))
        annotated = dict(row)
        annotated["entry_month"] = _norm(row.get("entry_date"))[:7] or "entry_month_missing"
        if entry is None:
            annotated["spy_50d_trend_state"] = "spy50_missing"
            annotated["vix_tercile"] = "vix_missing"
            reason_counts["entry_date_invalid"] += 1
            partially_annotated.append(annotated)
            continue

        spy_context, spy_reason = _spy_50d_context(spy_history, entry)
        if spy_context is None:
            annotated["spy_50d_trend_state"] = "spy50_missing"
            reason_counts[spy_reason or "spy50_missing"] += 1
        else:
            annotated.update(spy_context)

        vix_context, vix_reason = _vix_context(vix_history, entry)
        if vix_context is None:
            annotated["vix_close"] = None
            reason_counts[vix_reason or "vix_missing"] += 1
        else:
            annotated.update(vix_context)
            valid_vix_values.append(float(vix_context["vix_close"]))
        partially_annotated.append(annotated)

    thresholds = _tercile_thresholds(valid_vix_values)
    annotated_rows = []
    for row in partially_annotated:
        annotated = dict(row)
        annotated["vix_tercile"] = _assign_vix_tercile(_safe_float(row.get("vix_close")), thresholds)
        annotated_rows.append(annotated)

    return annotated_rows, {
        "spy_symbol": SPY_SYMBOL,
        "vix_symbol": vix_symbol,
        "vix_tercile_thresholds": thresholds,
        "missing_context_reason_counts": dict(reason_counts),
        "vix_context_available_count": sum(1 for row in annotated_rows if _safe_float(row.get("vix_close")) is not None),
        "spy50_context_available_count": sum(
            1 for row in annotated_rows if _norm(row.get("spy_50d_trend_state")) not in {"", "spy50_missing"}
        ),
    }


def _round_optional(value: float | None, digits: int = 2) -> float | None:
    return round(value, digits) if value is not None and math.isfinite(value) else None


def _bucket_metrics(rows: Iterable[dict[str, Any]], *, dimension: str, bucket: str) -> dict[str, Any]:
    items = list(rows)
    pct_values = [_safe_float(row.get("net_pnl_pct")) for row in items]
    pct_values = [value for value in pct_values if value is not None]
    pf_values = [
        _safe_float(row.get("net_pnl_usd")) if _safe_float(row.get("net_pnl_usd")) is not None else _safe_float(row.get("net_pnl_pct"))
        for row in items
    ]
    pf_values = [value for value in pf_values if value is not None]
    usd_values = [_safe_float(row.get("net_pnl_usd")) for row in items]
    usd_values = [value for value in usd_values if value is not None]
    winners = [value for value in pf_values if value > 0]
    losers = [value for value in pf_values if value < 0]
    gross_profit = sum(winners)
    gross_loss = abs(sum(losers))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
    n_trades = len(pf_values)
    robustness_required = n_trades >= MIN_ROBUST_BUCKET_N
    if not robustness_required:
        robust_pass = None
        robustness_reason = "thin_bucket_ignored"
    elif profit_factor is None:
        robust_pass = False
        robustness_reason = "profit_factor_unavailable_no_loss_sample"
    elif profit_factor >= 1.0:
        robust_pass = True
        robustness_reason = "profit_factor_at_or_above_1_0"
    else:
        robust_pass = False
        robustness_reason = "profit_factor_below_1_0"
    return {
        "dimension": dimension,
        "bucket": bucket,
        "n_trades": n_trades,
        "winner_count": len(winners),
        "loser_count": len(losers),
        "avg_net_pnl_pct": _round_optional(sum(pct_values) / len(pct_values) if pct_values else None),
        "sum_net_pnl_usd": _round_optional(sum(usd_values) if usd_values else None),
        "profit_factor": _round_optional(profit_factor),
        "gross_profit_for_pf": _round_optional(gross_profit),
        "gross_loss_for_pf": _round_optional(gross_loss),
        "pf_basis": "net_pnl_usd_when_available_else_net_pnl_pct",
        "no_loss_sample": bool(pf_values) and gross_loss == 0,
        "robustness_required": robustness_required,
        "robustness_pass": robust_pass,
        "robustness_reason": robustness_reason,
    }


def _bucket_table(rows: list[dict[str, Any]], dimension: str, *, branch: str | None = None) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        bucket = _norm(row.get(dimension)) or f"{dimension}_missing"
        grouped.setdefault(bucket, []).append(row)
    metrics = []
    for bucket, items in grouped.items():
        item = _bucket_metrics(items, dimension=dimension, bucket=bucket)
        if branch is not None:
            item["branch"] = branch
        metrics.append(item)
    return sorted(metrics, key=lambda item: (_norm(item.get("branch")), item["dimension"], item["bucket"]))


def _branch_bucket_tables(rows: list[dict[str, Any]]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    by_branch: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        branch = _norm(row.get("lane")) or "unknown_lane"
        by_branch.setdefault(branch, []).append(row)
    return {
        branch: {dimension: _bucket_table(items, dimension, branch=branch) for dimension in REGIME_DIMENSIONS}
        for branch, items in sorted(by_branch.items())
    }


def _robustness_summary(
    bucket_tables: dict[str, list[dict[str, Any]]],
    context: dict[str, Any],
    *,
    branch_bucket_tables: dict[str, dict[str, list[dict[str, Any]]]] | None = None,
) -> dict[str, Any]:
    all_buckets = [bucket for buckets in bucket_tables.values() for bucket in buckets]
    if branch_bucket_tables:
        all_buckets.extend(
            bucket
            for branch_tables in branch_bucket_tables.values()
            for buckets in branch_tables.values()
            for bucket in buckets
        )
    evaluable = [bucket for bucket in all_buckets if bucket.get("robustness_required")]
    failures = [
        bucket
        for bucket in evaluable
        if bucket.get("robustness_pass") is not True
    ]
    vix_missing = int(context.get("vix_missing_count") or 0)
    spy_missing = int(context.get("spy50_missing_count") or 0)
    coverage_ready = vix_missing == 0 and spy_missing == 0 and context.get("vix_tercile_thresholds") is not None
    regime_robust = bool(evaluable) and coverage_ready and not failures
    return {
        "regime_robust": regime_robust,
        "coverage_ready": coverage_ready,
        "evaluable_bucket_count": len(evaluable),
        "thin_bucket_count": len([bucket for bucket in all_buckets if not bucket.get("robustness_required")]),
        "failing_bucket_count": len(failures),
        "failing_buckets": sorted(
            failures,
            key=lambda item: (_norm(item.get("branch")), _norm(item.get("dimension")), _norm(item.get("bucket"))),
        ),
    }


def _branch_robustness_summary(
    branch_bucket_tables: dict[str, dict[str, list[dict[str, Any]]]],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    coverage_ready = (
        int(context.get("vix_missing_count") or 0) == 0
        and int(context.get("spy50_missing_count") or 0) == 0
        and context.get("vix_tercile_thresholds") is not None
    )
    branch_rows: list[dict[str, Any]] = []
    for branch, dimensions in sorted(branch_bucket_tables.items()):
        buckets = [bucket for rows in dimensions.values() for bucket in rows]
        evaluable = [bucket for bucket in buckets if bucket.get("robustness_required")]
        failures = [bucket for bucket in evaluable if bucket.get("robustness_pass") is not True]
        if not coverage_ready:
            status = "blocked_missing_market_context"
        elif failures:
            status = "regime_not_robust"
        elif evaluable:
            status = "regime_robust"
        else:
            status = "thin_no_evaluable_buckets"
        branch_rows.append(
            {
                "branch": branch,
                "regime_robust": bool(coverage_ready and evaluable and not failures),
                "status": status,
                "coverage_ready": coverage_ready,
                "evaluable_bucket_count": len(evaluable),
                "thin_bucket_count": len([bucket for bucket in buckets if not bucket.get("robustness_required")]),
                "failing_bucket_count": len(failures),
                "failing_buckets": sorted(
                    failures,
                    key=lambda item: (_norm(item.get("dimension")), _norm(item.get("bucket"))),
                ),
            }
        )
    return branch_rows


def build_report(
    *,
    source_path: Path | None = None,
    source_paths: Sequence[Path] | None = None,
    market_data_db_path: Path = DEFAULT_MARKET_DATA_DB,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    if source_paths is None:
        source_paths = (source_path,) if source_path is not None else DEFAULT_SOURCE_PATHS
    source_payloads, source_metas = _load_sources(tuple(source_paths))
    history, market_meta = _load_daily_history(
        market_data_db_path,
        symbols=(SPY_SYMBOL, *VIX_SYMBOL_CANDIDATES),
    )
    missing_required = []
    if not source_metas or any(meta.get("status") != "loaded" for meta in source_metas):
        missing_required.append("source_replay_artifact")
    if market_meta.get("status") != "loaded":
        missing_required.append("market_data_db")

    replay_rows, extraction = _extract_replay_rows(source_payloads) if not missing_required else ([], {})
    annotated_rows, context = _annotate_rows(replay_rows, history) if replay_rows and not missing_required else ([], {})
    vix_missing_count = sum(1 for row in annotated_rows if _norm(row.get("vix_tercile")) in {"vix_missing", "vix_tercile_unavailable"})
    spy_missing_count = sum(1 for row in annotated_rows if _norm(row.get("spy_50d_trend_state")) == "spy50_missing")
    context["vix_missing_count"] = vix_missing_count
    context["spy50_missing_count"] = spy_missing_count

    bucket_tables = {dimension: _bucket_table(annotated_rows, dimension) for dimension in REGIME_DIMENSIONS}
    branch_bucket_tables = _branch_bucket_tables(annotated_rows)
    robustness = _robustness_summary(bucket_tables, context, branch_bucket_tables=branch_bucket_tables)
    branch_robustness = _branch_robustness_summary(branch_bucket_tables, context)

    if missing_required:
        status = "blocked_missing_inputs"
        overall_status = "blocked_missing_inputs"
    elif not replay_rows:
        status = "blocked_no_eligible_replay_rows"
        overall_status = "blocked_no_eligible_exact_replay_rows"
    elif not robustness["coverage_ready"]:
        status = "regime_stratified_replay_readback"
        overall_status = "blocked_missing_market_context"
    elif robustness["regime_robust"]:
        status = "regime_stratified_replay_readback"
        overall_status = "regime_robust"
    else:
        status = "regime_stratified_replay_readback"
        overall_status = "regime_not_robust"

    next_queue = []
    if vix_missing_count:
        next_queue.append(
            {
                "priority": 4,
                "action": "refresh_vix_daily_history_for_regime_report",
                "count": vix_missing_count,
                "reason": "vix_tercile_context_missing_for_entry_rows",
            }
        )
    if spy_missing_count:
        next_queue.append(
            {
                "priority": 4,
                "action": "refresh_spy_daily_history_for_regime_report",
                "count": spy_missing_count,
                "reason": "spy_50d_trend_context_missing_for_entry_rows",
            }
        )
    if robustness["failing_bucket_count"]:
        next_queue.append(
            {
                "priority": 5,
                "action": "review_regime_failure_before_promotion_claim",
                "count": robustness["failing_bucket_count"],
                "reason": "one_or_more_regime_buckets_with_n_ge_15_have_pf_below_1_or_unavailable_pf",
            }
        )

    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_read_only_regime_stratified_replay",
        "schema_version": 1,
        "read_only": True,
        "summary": {
            "overall_status": overall_status,
            "missing_required_inputs": missing_required,
            "eligible_replay_row_count": len(replay_rows),
            "annotated_replay_row_count": len(annotated_rows),
            "vix_context_available_count": context.get("vix_context_available_count", 0),
            "vix_missing_count": vix_missing_count,
            "spy50_context_available_count": context.get("spy50_context_available_count", 0),
            "spy50_missing_count": spy_missing_count,
            "entry_month_count": len({row.get("entry_month") for row in annotated_rows if row.get("entry_month")}),
            "branch_count": len(branch_bucket_tables),
            "branch_bucket_count": sum(
                len(buckets) for branch_tables in branch_bucket_tables.values() for buckets in branch_tables.values()
            ),
            "branch_regime_robust_count": len([row for row in branch_robustness if row.get("regime_robust")]),
            "branch_regime_failure_count": len(
                [row for row in branch_robustness if row.get("status") == "regime_not_robust"]
            ),
            "market_context_status": "complete" if robustness["coverage_ready"] else "missing_or_incomplete",
            "regime_robust": robustness["regime_robust"],
            "coverage_ready": robustness["coverage_ready"],
            "evaluable_bucket_count": robustness["evaluable_bucket_count"],
            "thin_bucket_count": robustness["thin_bucket_count"],
            "failing_bucket_count": robustness["failing_bucket_count"],
            "minimum_bucket_n_for_robustness": MIN_ROBUST_BUCKET_N,
            **extraction,
        },
        "proof_policy": {
            "readback_is": "read-only regime stratification of exact replay P&L rows",
            "readback_is_not": "scanner policy change, live activation, broker order, DB mutation, threshold tuning, or proof-bar change",
            "trusted_proof_standard": "trusted intraday exact-contract OPRA/NBBO rows where available; this report does not promote research/backfill rows",
            "prohibited_actions": list(PROHIBITED_ACTIONS),
        },
        "inputs": {
            "source_replay_artifacts": source_metas,
            "market_data_db": market_meta,
            "spy_symbol": SPY_SYMBOL,
            "vix_symbol_candidates": list(VIX_SYMBOL_CANDIDATES),
            "max_context_age_days": MAX_CONTEXT_AGE_DAYS,
            "max_plausible_vix_close": MAX_PLAUSIBLE_VIX_CLOSE,
        },
        "market_context": context,
        "bucket_tables": bucket_tables,
        "branch_bucket_tables": branch_bucket_tables,
        "branch_robustness": branch_robustness,
        "robustness": robustness,
        "annotated_rows": annotated_rows,
        "next_evidence_queue": next_queue,
        "live_policy_change": False,
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }


def _cell(value: Any) -> str:
    text = _norm(value)
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict[str, Any]) -> str:
    summary = _as_dict(report.get("summary"))
    robustness = _as_dict(report.get("robustness"))
    lines = [
        "# Regime-Stratified Replay Report",
        "",
        "This report is generated by `scripts/build_regime_stratified_replay_report.py`. It is read-only and does not change scanner policy, broker behavior, stops, sizing, thresholds, proof bars, or lane promotion.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}` / `{summary.get('overall_status')}`.",
        f"- Eligible replay rows: `{summary.get('eligible_replay_row_count')}`.",
        f"- Branches: `{summary.get('branch_count')}`; branch buckets `{summary.get('branch_bucket_count')}`.",
        f"- Regime robust: `{summary.get('regime_robust')}`.",
        f"- Branch regime robust count: `{summary.get('branch_regime_robust_count')}`; bucket-failing branches `{summary.get('branch_regime_failure_count')}`.",
        f"- Market context: `{summary.get('market_context_status')}`; VIX missing `{summary.get('vix_missing_count')}`, SPY50 missing `{summary.get('spy50_missing_count')}`.",
        f"- Evaluable / failing buckets: `{summary.get('evaluable_bucket_count')}` / `{summary.get('failing_bucket_count')}`.",
        "",
        "## Market Data Source",
        "",
        f"- Cache: `{_as_dict(_as_dict(report.get('inputs')).get('market_data_db')).get('path')}`.",
        f"- SPY daily history: `{_json_inline(_as_dict(_as_dict(_as_dict(report.get('inputs')).get('market_data_db')).get('symbols')).get('SPY') or {})}`.",
        f"- VIX daily history: `{_json_inline(_as_dict(_as_dict(_as_dict(report.get('inputs')).get('market_data_db')).get('symbols')).get(_as_dict(report.get('market_context')).get('vix_symbol')) or {})}`.",
        "",
        "## Failing Buckets",
        "",
        "| Branch | Dimension | Bucket | N | PF | Avg Net P&L | Reason |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for bucket in _as_list(robustness.get("failing_buckets")):
        bucket = _as_dict(bucket)
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(bucket.get("branch") or "all"),
                    _cell(bucket.get("dimension")),
                    _cell(bucket.get("bucket")),
                    _cell(bucket.get("n_trades")),
                    _cell(bucket.get("profit_factor")),
                    _cell(bucket.get("avg_net_pnl_pct")),
                    _cell(bucket.get("robustness_reason")),
                ]
            )
            + " |"
        )
    for dimension, buckets in _as_dict(report.get("bucket_tables")).items():
        lines.extend(
            [
                "",
                f"## {dimension}",
                "",
                "| Bucket | N | PF | Avg Net P&L | Sum Net USD | Winners | Losers | Robustness |",
                "|---|---:|---:|---:|---:|---:|---:|---|",
            ]
        )
        for bucket in _as_list(buckets):
            bucket = _as_dict(bucket)
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(bucket.get("bucket")),
                        _cell(bucket.get("n_trades")),
                        _cell(bucket.get("profit_factor")),
                        _cell(bucket.get("avg_net_pnl_pct")),
                        _cell(bucket.get("sum_net_pnl_usd")),
                        _cell(bucket.get("winner_count")),
                        _cell(bucket.get("loser_count")),
                        _cell(bucket.get("robustness_reason")),
                    ]
                )
                + " |"
            )
    branch_robustness = _as_list(report.get("branch_robustness"))
    if branch_robustness:
        lines.extend(
            [
                "",
                "## Branch Robustness",
                "",
                "| Branch | Regime Robust | Status | Evaluable | Failing | Coverage Ready |",
                "|---|---:|---|---:|---:|---:|",
            ]
        )
        for row in branch_robustness:
            row = _as_dict(row)
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(row.get("branch")),
                        _cell(row.get("regime_robust")),
                        _cell(row.get("status")),
                        _cell(row.get("evaluable_bucket_count")),
                        _cell(row.get("failing_bucket_count")),
                        _cell(row.get("coverage_ready")),
                    ]
                )
                + " |"
            )
    branch_tables = _as_dict(report.get("branch_bucket_tables"))
    if branch_tables:
        lines.extend(
            [
                "",
                "## Branch Buckets",
                "",
                "| Branch | Dimension | Bucket | N | PF | Avg Net P&L | Sum Net USD | Winners | Losers | Robustness |",
                "|---|---|---|---:|---:|---:|---:|---:|---:|---|",
            ]
        )
        for branch, dimensions in sorted(branch_tables.items()):
            for dimension, buckets in sorted(_as_dict(dimensions).items()):
                for bucket in _as_list(buckets):
                    bucket = _as_dict(bucket)
                    lines.append(
                        "| "
                        + " | ".join(
                            [
                                _cell(branch),
                                _cell(dimension),
                                _cell(bucket.get("bucket")),
                                _cell(bucket.get("n_trades")),
                                _cell(bucket.get("profit_factor")),
                                _cell(bucket.get("avg_net_pnl_pct")),
                                _cell(bucket.get("sum_net_pnl_usd")),
                                _cell(bucket.get("winner_count")),
                                _cell(bucket.get("loser_count")),
                                _cell(bucket.get("robustness_reason")),
                            ]
                        )
                        + " |"
                    )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This report is advisory readback only. It does not create trades, submit broker orders, mutate DB state, change scanner policy, tune thresholds, lower exact OPRA/NBBO proof bars, or convert research/backfill evidence into production proof.",
        ]
    )
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
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
    payload = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    markdown = render_markdown(report) + "\n"
    json_path.write_text(payload, encoding="utf8")
    latest_json.write_text(payload, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return artifacts


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build read-only regime-stratified replay diagnostics.")
    parser.add_argument("--source", type=Path, action="append", help="Replay artifact to consume. Defaults to current regular-options multilane latest.")
    parser.add_argument("--market-data-db", type=Path, default=DEFAULT_MARKET_DATA_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(source_paths=tuple(args.source or DEFAULT_SOURCE_PATHS), market_data_db_path=args.market_data_db)
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
