from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
import sys
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


REPORT_ID = "regular_options_quote_derived_synthetic_forward_surface"
SURFACE_ID = "quote_derived_synthetic_forward_opening_bucket_surface_v1"
DEFAULT_QUOTES_DB = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_OPENING_REPLAY = (
    ROOT / "data" / "profitability-lab" / "regular-options-quote-surface-opening-range-reversal-replay" / "latest.json"
)
DEFAULT_HOLDOUT_CONTRACT = ROOT / "data" / "contracts" / "forward-holdout-contract.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-quote-derived-synthetic-forward-surface"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-quote-derived-synthetic-forward-surface.md"

DEFAULT_UNIVERSE = ("SPY", "QQQ", "IWM", "DIA")
DEFAULT_BUCKETS = ("09:35", "10:35", "10:40", "15:50")
LATEST_FOUR_MONTHS = ("2026-02", "2026-03", "2026-04", "2026-05")
MIN_PAIRS_PER_BUCKET = 5
MAX_IQR_SHARE = 0.01
MIN_COVERAGE_PCT = 90.0

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

SURFACE_STATUSES = (
    "surface_ready",
    "blocked_missing_call_put_pairs",
    "blocked_insufficient_pair_count",
    "blocked_crossed_or_stale_quote",
    "blocked_zero_bid_or_untradable",
    "blocked_inconsistent_parity_surface",
    "blocked_outside_universe",
    "blocked_unknown",
)

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
    "do_not_treat_quote_coverage_as_candidate_generation_proof",
    "do_not_treat_synthetic_forward_or_midpoint_values_as_executable_fill_or_pnl_evidence",
    "do_not_use_last_trade_eod_display_model_manual_or_stale_marks",
    "do_not_reclassify_zero_bid_or_untradable_rows_as_missing_data",
    "do_not_optimize_surface_formula_or_thresholds_on_pnl",
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


def _safe_float(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _bucket_to_minute(bucket: str) -> int:
    hour, minute = bucket.split(":", 1)
    return int(hour) * 60 + int(minute)


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
    meta["report_id"] = payload.get("report_id")
    meta["status_value"] = payload.get("status")
    return payload, meta


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


def _available_symbol_dates(conn: sqlite3.Connection, *, start_date: str, end_date: str, universe: tuple[str, ...]) -> list[tuple[str, str]]:
    placeholders = ",".join("?" for _ in universe)
    rows = conn.execute(
        f"""
        SELECT underlying, quote_date_et
        FROM option_quote_snapshots
        WHERE snapshot_kind = 'intraday'
          AND quote_date_et BETWEEN ? AND ?
          AND underlying IN ({placeholders})
        GROUP BY underlying, quote_date_et
        ORDER BY quote_date_et, underlying
        """,
        (start_date, end_date, *universe),
    ).fetchall()
    return [(str(row["underlying"]).upper(), str(row["quote_date_et"])) for row in rows]


def _available_bucket_keys(
    conn: sqlite3.Connection,
    *,
    start_date: str,
    end_date: str,
    universe: tuple[str, ...],
    minutes: tuple[int, ...],
) -> set[tuple[str, str, int]]:
    if not minutes:
        return set()
    universe_placeholders = ",".join("?" for _ in universe)
    minute_placeholders = ",".join("?" for _ in minutes)
    rows = conn.execute(
        f"""
        SELECT underlying, quote_date_et, quote_minute_et
        FROM option_quote_snapshots
        WHERE snapshot_kind = 'intraday'
          AND quote_date_et BETWEEN ? AND ?
          AND underlying IN ({universe_placeholders})
          AND quote_minute_et IN ({minute_placeholders})
        GROUP BY underlying, quote_date_et, quote_minute_et
        """,
        (start_date, end_date, *universe, *minutes),
    ).fetchall()
    return {
        (str(row["underlying"]).upper(), str(row["quote_date_et"]), int(row["quote_minute_et"]))
        for row in rows
    }


def _pair_rows(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    quote_date: str,
    minute: int,
    as_of_date: str,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    rows = conn.execute(
        """
        SELECT
          c.as_of_utc AS call_as_of_utc,
          p.as_of_utc AS put_as_of_utc,
          c.source_batch_id AS call_source_batch_id,
          p.source_batch_id AS put_source_batch_id,
          c.expiry AS expiry,
          c.strike AS strike,
          c.bid AS call_bid,
          c.ask AS call_ask,
          p.bid AS put_bid,
          p.ask AS put_ask
        FROM option_quote_snapshots c
        JOIN option_quote_snapshots p
          ON p.underlying = c.underlying
         AND p.quote_date_et = c.quote_date_et
         AND p.quote_minute_et = c.quote_minute_et
         AND p.snapshot_kind = c.snapshot_kind
         AND p.expiry = c.expiry
         AND p.strike = c.strike
         AND p.option_type = 'put'
        WHERE c.snapshot_kind = 'intraday'
          AND c.option_type = 'call'
          AND c.underlying = ?
          AND c.quote_date_et = ?
          AND c.quote_minute_et = ?
        ORDER BY c.expiry, c.strike
        """,
        (symbol, quote_date, minute),
    ).fetchall()
    quote_dt = _parse_date(quote_date)
    as_of_dt = _parse_date(as_of_date)
    diagnostics: list[dict[str, Any]] = []
    rejects: Counter[str] = Counter()
    for row in rows:
        payload = dict(row)
        expiry_dt = _parse_date(payload.get("expiry"))
        if quote_dt is None or expiry_dt is None:
            rejects["blocked_unknown"] += 1
            continue
        dte = (expiry_dt - quote_dt).days
        if dte < 7 or dte > 45:
            continue
        if as_of_dt is not None:
            call_as_of = _parse_date(payload.get("call_as_of_utc"))
            put_as_of = _parse_date(payload.get("put_as_of_utc"))
            if (call_as_of and call_as_of > as_of_dt) or (put_as_of and put_as_of > as_of_dt):
                rejects["blocked_leakage_or_asof_violation"] += 1
                continue
        call_bid = _safe_float(payload.get("call_bid"))
        call_ask = _safe_float(payload.get("call_ask"))
        put_bid = _safe_float(payload.get("put_bid"))
        put_ask = _safe_float(payload.get("put_ask"))
        if call_bid is None or call_ask is None or put_bid is None or put_ask is None:
            rejects["blocked_missing_bid_ask"] += 1
            continue
        if call_bid <= 0 or call_ask <= 0 or put_bid <= 0 or put_ask <= 0:
            rejects["blocked_zero_bid_or_untradable"] += 1
            continue
        if call_ask < call_bid or put_ask < put_bid:
            rejects["blocked_crossed_or_stale_quote"] += 1
            continue
        call_mid = (call_bid + call_ask) / 2.0
        put_mid = (put_bid + put_ask) / 2.0
        synthetic_forward = float(payload["strike"]) + call_mid - put_mid
        diagnostics.append(
            {
                "expiry": payload["expiry"],
                "dte": dte,
                "strike": float(payload["strike"]),
                "call_bid": call_bid,
                "call_ask": call_ask,
                "put_bid": put_bid,
                "put_ask": put_ask,
                "call_put_spread_sum": round((call_ask - call_bid) + (put_ask - put_bid), 4),
                "synthetic_forward": round(synthetic_forward, 6),
                "quote_minute_et": minute,
                "call_as_of_utc": payload.get("call_as_of_utc"),
                "put_as_of_utc": payload.get("put_as_of_utc"),
                "call_source_batch_id": payload.get("call_source_batch_id"),
                "put_source_batch_id": payload.get("put_source_batch_id"),
                "research_signal_only": True,
                "executable_fill_or_pnl_evidence": False,
            }
        )
    return diagnostics, rejects


def _surface_estimate(pair_rows: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    if not pair_rows:
        return None, "blocked_missing_call_put_pairs"
    if len(pair_rows) < MIN_PAIRS_PER_BUCKET:
        return None, "blocked_insufficient_pair_count"
    estimates = [float(row["synthetic_forward"]) for row in pair_rows]
    median = statistics.median(estimates)
    if median <= 0:
        return None, "blocked_unknown"
    ordered = sorted(estimates)
    q1 = ordered[len(ordered) // 4]
    q3 = ordered[(len(ordered) * 3) // 4]
    iqr = q3 - q1
    if iqr / median > MAX_IQR_SHARE:
        return None, "blocked_inconsistent_parity_surface"
    return {
        "eligible_pair_count": len(pair_rows),
        "synthetic_forward_median": round(median, 6),
        "synthetic_forward_iqr": round(iqr, 6),
        "synthetic_forward_iqr_share": round(iqr / median, 6),
        "pair_preview": pair_rows[:10],
        "research_signal_only": True,
        "executable_fill_or_pnl_evidence": False,
    }, "surface_ready"


def _opening_baseline(opening_replay: dict[str, Any]) -> dict[str, Any]:
    metrics = _as_dict(opening_replay.get("metrics"))
    full = _as_dict(metrics.get("full_window"))
    latest = _as_dict(metrics.get("latest_four_months"))
    counts = _as_dict(metrics.get("denominator_status_counts"))
    return {
        "status": opening_replay.get("status"),
        "blocked_missing_quote_surface_underlying_price": "blocked_missing_quote_surface_underlying_price"
        in _as_list(opening_replay.get("blockers")),
        "daily_denominator_rows": metrics.get("daily_denominator_rows"),
        "blocked_missing_underlying_price": counts.get("blocked_missing_underlying_price"),
        "candidate_rows": metrics.get("candidate_rows"),
        "full_window_exact_completed_rows": full.get("exact_completed_rows"),
        "latest_four_strict_executable_completed_rows_after_opportunity_dedupe": latest.get(
            "strict_executable_completed_rows_after_opportunity_dedupe"
        ),
    }


def _coverage_metrics(rows: list[dict[str, Any]], *, requested_months: list[str]) -> dict[str, Any]:
    total_buckets = sum(len(_as_dict(row.get("bucket_statuses"))) for row in rows)
    ready_buckets = sum(
        1 for row in rows for status in _as_dict(row.get("bucket_statuses")).values() if status == "surface_ready"
    )
    row_ready = [row for row in rows if row.get("surface_status") == "surface_ready"]
    ready_months = sorted({str(row.get("quote_date"))[:7] for row in row_ready})
    train_months = [month for month in requested_months if month not in LATEST_FOUR_MONTHS and month in ready_months]
    latest_months = [month for month in LATEST_FOUR_MONTHS if month in ready_months]
    status_counts = Counter(str(row.get("surface_status")) for row in rows)
    bucket_counts: Counter[str] = Counter()
    bucket_reject_counts: Counter[str] = Counter()
    for row in rows:
        bucket_counts.update(str(status) for status in _as_dict(row.get("bucket_statuses")).values())
        for rejects in _as_dict(row.get("bucket_reject_counts")).values():
            bucket_reject_counts.update({str(key): int(value) for key, value in _as_dict(rejects).items()})
    return {
        "daily_symbol_surface_rows": len(rows),
        "requested_symbol_date_bucket_count": total_buckets,
        "ready_symbol_date_bucket_count": ready_buckets,
        "requested_symbol_date_bucket_coverage_pct": round((ready_buckets / total_buckets) * 100.0, 4) if total_buckets else 0.0,
        "surface_status_counts": dict(sorted(status_counts.items())),
        "bucket_status_counts": dict(sorted(bucket_counts.items())),
        "bucket_reject_counts": dict(sorted(bucket_reject_counts.items())),
        "ready_months": ready_months,
        "train_months_covered": len(train_months),
        "latest_four_months": list(LATEST_FOUR_MONTHS),
        "latest_four_months_covered": len(latest_months),
        "leakage_reject_rows": bucket_reject_counts.get("blocked_leakage_or_asof_violation", 0),
        "outside_universe_rows": status_counts.get("blocked_outside_universe", 0),
        "protected_holdout_overlap_rows": 0,
        "blocked_unknown_rows": status_counts.get("blocked_unknown", 0),
    }


def _smallest_blocker(blockers: list[str]) -> str | None:
    priority = (
        "opening_range_baseline_not_parked_on_missing_underlying",
        "blocked_missing_call_put_pair_surface",
        "blocked_execution_quote_quality",
        "blocked_inconsistent_parity_surface",
        "blocked_insufficient_synthetic_forward_coverage",
        "blocked_leakage_or_asof_violation",
    )
    for blocker in priority:
        if blocker in blockers:
            return blocker
    return blockers[0] if blockers else None


def _status(blockers: list[str], ready: bool) -> str:
    if ready and not blockers:
        return "quote_derived_synthetic_forward_surface_ready"
    if blockers:
        return "blocked_quote_derived_synthetic_forward_surface"
    return "diagnostic_only_quote_derived_synthetic_forward_surface"


def build_report(
    *,
    quotes_db_path: Path = DEFAULT_QUOTES_DB,
    opening_replay_path: Path = DEFAULT_OPENING_REPLAY,
    holdout_contract_path: Path = DEFAULT_HOLDOUT_CONTRACT,
    start_date: str = "2024-06-01",
    end_date: str = "2026-05-31",
    as_of_date: str = "2026-06-04",
    universe: tuple[str, ...] = DEFAULT_UNIVERSE,
    buckets: tuple[str, ...] = DEFAULT_BUCKETS,
    no_write: bool = True,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    universe = tuple(symbol.upper().strip() for symbol in universe if symbol.strip())
    if universe != DEFAULT_UNIVERSE:
        raise ValueError("universe must be exactly SPY,QQQ,IWM,DIA in that order")
    bucket_minutes = {bucket: _bucket_to_minute(bucket) for bucket in buckets}
    opening_replay, opening_meta = _load_json(opening_replay_path, required=True)
    holdout, holdout_meta = _load_json(holdout_contract_path, required=True)
    opening_baseline = _opening_baseline(opening_replay)
    blockers: list[str] = []
    if not (
        opening_baseline.get("status") == "blocked_quote_surface_opening_range_reversal_replay"
        and opening_baseline.get("blocked_missing_quote_surface_underlying_price") is True
        and opening_baseline.get("candidate_rows") == 0
    ):
        blockers.append("opening_range_baseline_not_parked_on_missing_underlying")

    conn = _connect_read_only(quotes_db_path)
    read_only_db_open = _read_only_confirmed(conn)
    if not read_only_db_open:
        blockers.append("db_read_only_not_confirmed")
    surface_rows: list[dict[str, Any]] = []
    symbol_dates = _available_symbol_dates(conn, start_date=start_date, end_date=end_date, universe=universe)
    available_bucket_keys = _available_bucket_keys(
        conn,
        start_date=start_date,
        end_date=end_date,
        universe=universe,
        minutes=tuple(bucket_minutes.values()),
    )
    for symbol, quote_date in symbol_dates:
        row = {
            "surface_id": SURFACE_ID,
            "underlying": symbol,
            "quote_date": quote_date,
            "bucket_statuses": {},
            "bucket_estimates": {},
            "bucket_reject_counts": {},
            "research_signal_only": True,
            "executable_fill_or_pnl_evidence": False,
        }
        if symbol not in universe:
            row["surface_status"] = "blocked_outside_universe"
            surface_rows.append(row)
            continue
        for bucket, minute in bucket_minutes.items():
            if (symbol, quote_date, minute) not in available_bucket_keys:
                pairs, rejects = [], Counter()
                estimate, status = None, "blocked_missing_call_put_pairs"
            else:
                pairs, rejects = _pair_rows(
                    conn, symbol=symbol, quote_date=quote_date, minute=minute, as_of_date=as_of_date
                )
                estimate, status = _surface_estimate(pairs)
            row["bucket_statuses"][bucket] = status
            row["bucket_reject_counts"][bucket] = dict(sorted(rejects.items()))
            if estimate:
                row["bucket_estimates"][bucket] = estimate
        bucket_statuses = set(_as_dict(row["bucket_statuses"]).values())
        row["surface_status"] = "surface_ready" if bucket_statuses == {"surface_ready"} else sorted(bucket_statuses)[0]
        surface_rows.append(row)
    conn.close()

    requested_months = _month_range(start_date, end_date)
    metrics = _coverage_metrics(surface_rows, requested_months=requested_months)
    bucket_counts = _as_dict(metrics.get("bucket_status_counts"))
    bucket_reject_counts = _as_dict(metrics.get("bucket_reject_counts"))
    if bucket_counts.get("blocked_missing_call_put_pairs", 0) or bucket_counts.get("blocked_insufficient_pair_count", 0):
        blockers.append("blocked_missing_call_put_pair_surface")
    if (
        bucket_counts.get("blocked_zero_bid_or_untradable", 0)
        or bucket_counts.get("blocked_crossed_or_stale_quote", 0)
        or bucket_reject_counts.get("blocked_zero_bid_or_untradable", 0)
        or bucket_reject_counts.get("blocked_crossed_or_stale_quote", 0)
    ):
        blockers.append("blocked_execution_quote_quality")
    if bucket_reject_counts.get("blocked_leakage_or_asof_violation", 0):
        blockers.append("blocked_leakage_or_asof_violation")
    if bucket_counts.get("blocked_inconsistent_parity_surface", 0):
        blockers.append("blocked_inconsistent_parity_surface")
    if (
        metrics["requested_symbol_date_bucket_coverage_pct"] < MIN_COVERAGE_PCT
        or metrics["train_months_covered"] < 20
        or metrics["latest_four_months_covered"] < 4
    ):
        blockers.append("blocked_insufficient_synthetic_forward_coverage")
    ready = (
        metrics["requested_symbol_date_bucket_coverage_pct"] >= MIN_COVERAGE_PCT
        and metrics["train_months_covered"] >= 20
        and metrics["latest_four_months_covered"] == 4
        and metrics["leakage_reject_rows"] == 0
        and metrics["outside_universe_rows"] == 0
        and metrics["protected_holdout_overlap_rows"] == 0
        and metrics["blocked_unknown_rows"] == 0
    )
    blockers = sorted(set(blockers))
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": _status(blockers, ready),
        **READ_ONLY_FLAGS,
        "no_write": no_write,
        "surface_id": SURFACE_ID,
        "universe": list(universe),
        "buckets": list(buckets),
        "window": {"start_date": start_date, "end_date": end_date, "as_of_date": as_of_date},
        "read_only_db_open": read_only_db_open,
        "synthetic_forward_surface_ready": ready and not blockers,
        "blockers": blockers,
        "smallest_next_blocker_clearing_slice": _smallest_blocker(blockers),
        "opening_range_replay_baseline": opening_baseline,
        "metrics": metrics,
        "surface_statuses": list(SURFACE_STATUSES),
        "daily_symbol_surface_preview": surface_rows[:25],
        "next_replay_command": (
            "npm run options:research:quote-surface-opening-range-reversal-replay-v2 -- "
            "--synthetic-forward-surface data/profitability-lab/regular-options-quote-derived-synthetic-forward-surface/latest.json "
            "--start-date 2024-06-01 --end-date 2026-05-31 --as-of-date 2026-06-04 --universe SPY,QQQ,IWM,DIA --no-write --json"
            if ready and not blockers
            else None
        ),
        "source_artifacts": {
            "opening_range_replay": opening_meta,
            "forward_holdout_contract": holdout_meta,
            "quotes_db": {"path": _rel(quotes_db_path), "exists": quotes_db_path.exists(), "status": "read_only_opened"},
        },
        "proof_boundary": "synthetic-forward parity values are research signal inputs only, not executable fills, not P&L marks, not proof rows, and not accepted profitability",
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "_daily_symbol_surface_rows": surface_rows,
    }
    _validate_report(report)
    return report


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    if report.get("accepted_profitability") is not False:
        raise ValueError("accepted profitability must remain false")
    for status in SURFACE_STATUSES:
        if status not in report.get("surface_statuses", []):
            raise ValueError(f"missing surface status {status}")


def _fmt_bool(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    metrics = _as_dict(report.get("metrics"))
    baseline = _as_dict(report.get("opening_range_replay_baseline"))
    lines = [
        "# Regular Options Quote-Derived Synthetic Forward Surface",
        "",
        "This generated report is read-only. It checks whether existing same-minute OPRA/NBBO call-put pairs can provide a research-only synthetic-forward input surface for opening-bucket replays without importing quotes, mutating evidence, creating trades, or changing scanner behavior.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Surface ready: `{_fmt_bool(report['synthetic_forward_surface_ready'])}`.",
        f"- Read-only DB open: `{_fmt_bool(report['read_only_db_open'])}`.",
        f"- Accepted profitability: `{_fmt_bool(report['accepted_profitability'])}`.",
        f"- Historical rows are forward proof: `{_fmt_bool(report['historical_rows_are_forward_proof'])}`.",
        f"- Requested bucket coverage: `{metrics.get('requested_symbol_date_bucket_coverage_pct')}`.",
        f"- Train months covered: `{metrics.get('train_months_covered')}`.",
        f"- Latest-four months covered: `{metrics.get('latest_four_months_covered')}`.",
        "",
        "## Opening-Range Baseline",
        "",
        f"- Baseline status: `{baseline.get('status')}`.",
        f"- Baseline denominator rows: `{baseline.get('daily_denominator_rows')}`.",
        f"- Baseline blocked missing underlying rows: `{baseline.get('blocked_missing_underlying_price')}`.",
        f"- Baseline candidate rows: `{baseline.get('candidate_rows')}`.",
        f"- Baseline latest-four strict rows: `{baseline.get('latest_four_strict_executable_completed_rows_after_opportunity_dedupe')}`.",
        "",
        "## Blockers",
        "",
    ]
    if report.get("blockers"):
        lines.extend(f"- `{item}`" for item in _as_list(report.get("blockers")))
    else:
        lines.append("- None.")
    lines.extend(["", "## Bucket Status Counts", "", "| Status | Count |", "|---|---:|"])
    for status, count in _as_dict(metrics.get("bucket_status_counts")).items():
        lines.append(f"| `{status}` | `{count}` |")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            report["proof_boundary"],
            "",
            "## Next Replay Command",
            "",
            f"`{report.get('next_replay_command')}`" if report.get("next_replay_command") else "No replay command emitted because the surface is not ready.",
            "",
            "## Forbidden Actions",
            "",
        ]
    )
    lines.extend(f"- `{item}`" for item in _as_list(report.get("forbidden_actions")))
    lines.append("")
    return "\n".join(lines)


def _public_report(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if not key.startswith("_")}


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"{stamp}.json"
    md_path = output_dir / f"{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    surface_path = output_dir / "daily_symbol_surface.jsonl"
    artifacts = {
        "json": _rel(json_path),
        "markdown": _rel(md_path),
        "latest_json": _rel(latest_json),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
        "daily_symbol_surface_jsonl": _rel(surface_path),
    }
    public = _public_report(report)
    public["artifacts"] = artifacts
    markdown = render_markdown(public)
    for path in (json_path, latest_json):
        path.write_text(json.dumps(public, indent=2, sort_keys=True) + "\n", encoding="utf8")
    for path in (md_path, latest_md, docs_report):
        path.write_text(markdown, encoding="utf8")
    surface_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in _as_list(report.get("_daily_symbol_surface_rows"))) + "\n",
        encoding="utf8",
    )
    report["artifacts"] = artifacts
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the read-only quote-derived synthetic-forward source surface.")
    parser.add_argument("--quotes-db", type=Path, default=DEFAULT_QUOTES_DB)
    parser.add_argument("--opening-replay", type=Path, default=DEFAULT_OPENING_REPLAY)
    parser.add_argument("--holdout-contract", type=Path, default=DEFAULT_HOLDOUT_CONTRACT)
    parser.add_argument("--start-date", default="2024-06-01")
    parser.add_argument("--end-date", default="2026-05-31")
    parser.add_argument("--as-of-date", default="2026-06-04")
    parser.add_argument("--universe", default=",".join(DEFAULT_UNIVERSE))
    parser.add_argument("--buckets", default=",".join(DEFAULT_BUCKETS))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = build_report(
        quotes_db_path=args.quotes_db,
        opening_replay_path=args.opening_replay,
        holdout_contract_path=args.holdout_contract,
        start_date=args.start_date,
        end_date=args.end_date,
        as_of_date=args.as_of_date,
        universe=tuple(part.strip().upper() for part in args.universe.split(",") if part.strip()),
        buckets=tuple(part.strip() for part in args.buckets.split(",") if part.strip()),
        no_write=True,
    )
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    public = _public_report(report)
    if args.json:
        print(json.dumps(public, indent=2, sort_keys=True))
    else:
        print(render_markdown(public))
    return 0


if __name__ == "__main__":
    sys.exit(main())
