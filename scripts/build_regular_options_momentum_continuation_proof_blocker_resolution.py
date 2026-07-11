from __future__ import annotations

# ruff: noqa: E402

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import (
    build_regular_options_momentum_continuation_research_replay as replay,
)
from scripts.build_regular_options_point_in_time_market_regime_inputs import (
    POINT_IN_TIME_SOURCE_MODE,
)
from scripts.evaluate_regular_options_autoresearch import (
    block_bootstrap_confidence_for_values,
)

REPORT_ID = "regular_options_momentum_continuation_proof_blocker_resolution"
CONCEPT_ID = "breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1"

DEFAULT_SOURCE_REPLAY = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-momentum-continuation-research-replay"
    / "latest.json"
)
DEFAULT_PREREGISTERED_PLAYBOOK = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-preregistered-momentum-continuation-playbook"
    / "latest.json"
)
DEFAULT_POINT_IN_TIME_VIX_BUCKET = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-point-in-time-vix-bucket"
    / "latest.json"
)
DEFAULT_POINT_IN_TIME_MARKET_REGIME_INPUTS = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-point-in-time-market-regime-inputs"
    / "latest.json"
)
DEFAULT_ALL_PLANNED = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-autoresearch"
    / "all-planned-sleeves"
    / "latest.json"
)
DEFAULT_OPTIONS_DB = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_RUNS_DIR = ROOT / "data" / "options-validation" / "runs"
DEFAULT_OUTPUT_DIR = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-momentum-continuation-proof-blocker-resolution"
)
DEFAULT_DOCS_REPORT = (
    ROOT / "docs" / "regular-options-momentum-continuation-proof-blocker-resolution.md"
)

CONTRACT_MULTIPLIER = 100
MIN_STRICT_ROWS = 30
MIN_QUOTE_COVERAGE = 0.90
MIN_PF_LOWER_BOUND = 1.0
MIN_STRESS_PF = 1.0

QUOTE_BLOCKERS = frozenset(
    {
        "entry_missing_leg_quote",
        "entry_zero_or_nonpositive_bid_ask",
        "entry_crossed_quote",
        "entry_debit_nonpositive",
        "exit_missing_leg_quote",
        "exit_zero_or_nonpositive_bid_ask",
        "exit_crossed_quote",
        "exit_value_negative",
    }
)

READ_ONLY_FLAGS = {
    "read_only": True,
    "accepted_profitability": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "promotion_ready": False,
}

FORBIDDEN_ACTIONS = (
    "do_not_submit_broker_orders",
    "do_not_enable_live_validation",
    "do_not_enable_auto_track",
    "do_not_release_scanner",
    "do_not_change_strategy_logic",
    "do_not_change_stops",
    "do_not_change_sizing",
    "do_not_lower_proof_bars",
    "do_not_import_quotes",
    "do_not_mutate_evidence_stores",
    "do_not_append_forward_cohort",
    "do_not_consume_protected_holdout",
    "do_not_promote_any_lane",
    "do_not_count_historical_rows_as_forward_proof",
    "do_not_count_source_marks_midpoints_eod_display_manual_last_synthetic_or_lookahead_as_proof",
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
    try:
        if value in (None, "") or isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _parse_utc(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _load_json(path: Path, *, required: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = {
        "path": _rel(path),
        "required": required,
        "exists": path.exists(),
        "status": "missing",
        "error": None,
    }
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
    meta["generated_at_utc"] = payload.get("generated_at_utc")
    meta["report_id"] = payload.get("report_id")
    return payload, meta


def _source_replay_valid(source: dict[str, Any]) -> bool:
    return (
        source.get("report_id")
        == "regular_options_momentum_continuation_research_replay"
        and source.get("concept_id") == CONCEPT_ID
        and source.get("research_only_replay_harness_implemented") is True
        and source.get("accepted_profitability") is False
        and _as_dict(source.get("proof_qualified")).get("row_count") == 0
    )


def _preregistered_playbook_valid(playbook: dict[str, Any]) -> bool:
    return (
        playbook.get("report_id")
        == "regular_options_preregistered_momentum_continuation_playbook"
        and playbook.get("status") == "preregistered_design_only"
        and playbook.get("concept_id") == CONCEPT_ID
        and playbook.get("accepted_profitability") is False
    )


def _vix_artifact_ready(payload: dict[str, Any]) -> bool:
    return (
        payload.get("status") == "point_in_time_vix_bucket_ready"
        and _as_list(payload.get("blockers")) == []
        and payload.get("point_in_time_vix_low_mid_bucket_available") is True
    )


def _valid_vix_bucket_row(row: dict[str, Any]) -> bool:
    bucket_date = _parse_date(row.get("bucket_date_et"))
    if bucket_date is None:
        return False
    source_ts = _parse_utc(row.get("source_timestamp_utc"))
    known_at = _parse_utc(row.get("known_at_utc"))
    if source_ts is None or known_at is None:
        return False
    if source_ts > known_at or known_at.date() >= bucket_date:
        return False
    return (
        row.get("point_in_time_valid") is True
        and row.get("source_provenance_status") == "trusted_local_or_contract_declared"
        and str(row.get("vix_bucket") or "").lower() in {"low", "mid", "high"}
    )


def _vix_bucket_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not _vix_artifact_ready(payload):
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for item in _as_list(payload.get("bucket_rows")):
        row = _as_dict(item)
        if _valid_vix_bucket_row(row):
            rows[str(row["bucket_date_et"])] = row
    return rows


def _market_regime_artifact_ready(payload: dict[str, Any]) -> bool:
    coverage = _as_dict(payload.get("coverage"))
    source_time_policy = _as_dict(payload.get("source_time_policy"))
    return (
        payload.get("status") == "point_in_time_market_regime_inputs_ready"
        and _as_list(payload.get("blockers")) == []
        and payload.get("point_in_time_market_regime_inputs_available") is True
        and source_time_policy.get("source_time_mode") == POINT_IN_TIME_SOURCE_MODE
        and source_time_policy.get(
            "historical_reconstruction_can_clear_point_in_time_blockers"
        )
        is False
        and _safe_float(coverage.get("date_coverage_pct")) is not None
        and (_safe_float(coverage.get("date_coverage_pct")) or 0.0) >= 90.0
        and int(coverage.get("covered_month_count") or 0)
        >= min(20, int(coverage.get("requested_month_count") or 0))
    )


def _valid_market_regime_row(row: dict[str, Any]) -> bool:
    input_date = _parse_date(row.get("input_date_et"))
    if input_date is None:
        return False
    return (
        row.get("point_in_time_valid") is True
        and row.get("source_time_status") == POINT_IN_TIME_SOURCE_MODE
        and row.get("historical_prior_bar_reconstruction") is False
        and _as_list(row.get("blockers")) == []
        and row.get("proof_eligible") is True
        and isinstance(row.get("spy_momentum_confirmed"), bool)
        and isinstance(row.get("qqq_momentum_confirmed"), bool)
        and isinstance(row.get("breadth_confirmed"), bool)
    )


def _market_regime_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not _market_regime_artifact_ready(payload):
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for item in _as_list(payload.get("input_rows")):
        row = _as_dict(item)
        if _valid_market_regime_row(row):
            rows[str(row["input_date_et"])] = row
    return rows


def _entry_minute_for_run(path: Path) -> int:
    run, _meta = replay._load_json(path, required=False)
    text = str(run.get("entry_quote_time_et") or "")
    if "10:10" in text and "+ 15m" in text:
        return 10 * 60 + 25
    if "10:10" in text:
        return 10 * 60 + 10
    return 10 * 60 + 25


def _reconstruct_denominator(
    all_planned_path: Path, runs_dir: Path, run_paths: list[Path] | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    all_planned, _meta = replay._load_json(all_planned_path, required=True)
    selected_paths = (
        run_paths
        if run_paths is not None
        else replay._candidate_run_paths(all_planned, runs_dir)
    )
    rows, metas = replay._load_run_denominator_rows(selected_paths)
    entry_minutes = {_rel(path): _entry_minute_for_run(path) for path in selected_paths}
    return rows, metas, entry_minutes


def _connect_options_db(path: Path) -> sqlite3.Connection | None:
    if not path.exists():
        return None
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _trusted_quote(
    conn: sqlite3.Connection | None,
    *,
    contract_symbol: str | None,
    quote_date: str | None,
    max_minute: int | None,
) -> dict[str, Any] | None:
    if conn is None or not contract_symbol or not quote_date:
        return None
    minute_clause = ""
    params: list[Any] = [contract_symbol, quote_date]
    if max_minute is not None:
        minute_clause = "and q.quote_minute_et <= ?"
        params.append(max_minute)
    query = f"""
        select q.bid, q.ask, q.quote_minute_et, q.source_batch_id, b.source_label
        from option_quote_snapshots q
        join import_batches b on b.id = q.source_batch_id
        where q.contract_symbol = ?
          and q.snapshot_kind = 'intraday'
          and q.quote_date_et = ?
          and b.data_trust = 'trusted'
          and q.bid is not null
          and q.ask is not null
          {minute_clause}
        order by q.quote_minute_et desc
        limit 1
    """
    row = conn.execute(query, params).fetchone()
    if row is None:
        return None
    return {
        "bid": float(row["bid"]),
        "ask": float(row["ask"]),
        "quote_minute_et": int(row["quote_minute_et"]),
        "source_batch_id": int(row["source_batch_id"]),
        "source_label": row["source_label"],
    }


def _quote_pair_status(
    long_quote: dict[str, Any] | None, short_quote: dict[str, Any] | None
) -> str:
    if not long_quote or not short_quote:
        return "missing_leg_quote"
    if (
        long_quote["bid"] <= 0
        or long_quote["ask"] <= 0
        or short_quote["bid"] <= 0
        or short_quote["ask"] <= 0
    ):
        return "zero_or_nonpositive_bid_ask"
    if long_quote["ask"] < long_quote["bid"] or short_quote["ask"] < short_quote["bid"]:
        return "crossed_quote"
    return "resolved"


def _trusted_synchronized_quote_pair(
    conn: sqlite3.Connection | None,
    *,
    long_contract_symbol: str | None,
    short_contract_symbol: str | None,
    quote_date: str | None,
    max_minute: int | None,
) -> dict[str, Any] | None:
    if (
        conn is None
        or not long_contract_symbol
        or not short_contract_symbol
        or not quote_date
    ):
        return None
    minute_clause = ""
    params: list[Any] = [long_contract_symbol, short_contract_symbol, quote_date]
    if max_minute is not None:
        minute_clause = "and long_quote.quote_minute_et <= ?"
        params.append(max_minute)
    row = conn.execute(
        f"""
        select
            long_quote.bid as long_bid,
            long_quote.ask as long_ask,
            short_quote.bid as short_bid,
            short_quote.ask as short_ask,
            long_quote.quote_minute_et as quote_minute_et,
            long_quote.as_of_utc as as_of_utc,
            long_batch.source_label as source_label
        from option_quote_snapshots long_quote
        join option_quote_snapshots short_quote
          on short_quote.quote_date_et = long_quote.quote_date_et
         and short_quote.quote_minute_et = long_quote.quote_minute_et
         and short_quote.as_of_utc = long_quote.as_of_utc
        join import_batches long_batch on long_batch.id = long_quote.source_batch_id
        join import_batches short_batch on short_batch.id = short_quote.source_batch_id
        where long_quote.contract_symbol = ?
          and short_quote.contract_symbol = ?
          and long_quote.quote_date_et = ?
          and long_quote.snapshot_kind = 'intraday'
          and short_quote.snapshot_kind = 'intraday'
          and long_batch.data_trust = 'trusted'
          and short_batch.data_trust = 'trusted'
          and long_batch.source_label = short_batch.source_label
          and long_quote.bid is not null
          and long_quote.ask is not null
          and short_quote.bid is not null
          and short_quote.ask is not null
          {minute_clause}
        order by long_quote.quote_minute_et desc, long_quote.as_of_utc desc
        limit 1
        """,
        params,
    ).fetchone()
    if row is None:
        return None
    return {
        "long": {"bid": float(row["long_bid"]), "ask": float(row["long_ask"])},
        "short": {
            "bid": float(row["short_bid"]),
            "ask": float(row["short_ask"]),
        },
        "quote_minute_et": int(row["quote_minute_et"]),
        "as_of_utc": str(row["as_of_utc"]),
        "source_label": str(row["source_label"]),
    }


def _resolved_row(
    row: dict[str, Any],
    conn: sqlite3.Connection | None,
    entry_minutes: dict[str, int],
    vix_buckets_by_date: dict[str, dict[str, Any]],
    market_regime_by_date: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    reasons = set(str(item) for item in _as_list(row.get("reason_codes")))
    source_run = str(row.get("source_run") or "")
    entry_minute = entry_minutes.get(source_run, 10 * 60 + 25)
    entry_date = str(row.get("entry_date") or "")
    vix_bucket_row = vix_buckets_by_date.get(entry_date)
    market_regime_row = market_regime_by_date.get(entry_date)
    point_in_time_vix_bucket_resolved = (
        "missing_point_in_time_vix_bucket" in reasons and vix_bucket_row is not None
    )
    point_in_time_breadth_confirmation_resolved = (
        "missing_point_in_time_breadth_confirmation" in reasons
        and market_regime_row is not None
        and market_regime_row.get("breadth_confirmed") is True
    )
    point_in_time_spy_momentum_confirmation_resolved = (
        "missing_point_in_time_spy_momentum_confirmation" in reasons
        and market_regime_row is not None
        and market_regime_row.get("spy_momentum_confirmed") is True
    )
    point_in_time_qqq_momentum_confirmation_resolved = (
        "missing_point_in_time_qqq_momentum_confirmation" in reasons
        and market_regime_row is not None
        and market_regime_row.get("qqq_momentum_confirmed") is True
    )
    long_contract = row.get("long_contract_symbol")
    short_contract = row.get("short_contract_symbol")
    entry_pair = _trusted_synchronized_quote_pair(
        conn,
        long_contract_symbol=long_contract,
        short_contract_symbol=short_contract,
        quote_date=entry_date,
        max_minute=entry_minute,
    )
    exit_pair = _trusted_synchronized_quote_pair(
        conn,
        long_contract_symbol=long_contract,
        short_contract_symbol=short_contract,
        quote_date=row.get("exit_date"),
        max_minute=None,
    )
    entry_long = _as_dict(entry_pair.get("long")) if entry_pair else None
    entry_short = _as_dict(entry_pair.get("short")) if entry_pair else None
    exit_long = _as_dict(exit_pair.get("long")) if exit_pair else None
    exit_short = _as_dict(exit_pair.get("short")) if exit_pair else None
    entry_status = _quote_pair_status(entry_long, entry_short)
    exit_status = _quote_pair_status(exit_long, exit_short)
    resolution_blockers: set[str] = set()

    hard_original_blockers = {
        "protected_holdout_blocked",
        "duplicate_within_research_harness",
        "rejected_outside_preregistered_universe",
        "rejected_not_call_debit_spread",
    }
    resolution_blockers.update(reasons.intersection(hard_original_blockers))

    for point_in_time_blocker in (
        "missing_point_in_time_vix_bucket",
        "missing_point_in_time_breadth_confirmation",
        "missing_point_in_time_spy_momentum_confirmation",
        "missing_point_in_time_qqq_momentum_confirmation",
    ):
        if point_in_time_blocker in reasons:
            if (
                point_in_time_blocker == "missing_point_in_time_vix_bucket"
                and vix_bucket_row is not None
            ):
                continue
            if (
                point_in_time_blocker == "missing_point_in_time_breadth_confirmation"
                and market_regime_row is not None
            ):
                if market_regime_row.get("breadth_confirmed") is True:
                    continue
                resolution_blockers.add("rejected_no_breadth_confirmation")
                continue
            if (
                point_in_time_blocker
                == "missing_point_in_time_spy_momentum_confirmation"
                and market_regime_row is not None
            ):
                if market_regime_row.get("spy_momentum_confirmed") is True:
                    continue
                resolution_blockers.add("rejected_no_spy_momentum_confirmation")
                continue
            if (
                point_in_time_blocker
                == "missing_point_in_time_qqq_momentum_confirmation"
                and market_regime_row is not None
            ):
                if market_regime_row.get("qqq_momentum_confirmed") is True:
                    continue
                resolution_blockers.add("rejected_no_qqq_momentum_confirmation")
                continue
            resolution_blockers.add(point_in_time_blocker)

    if entry_status != "resolved":
        resolution_blockers.add(f"entry_{entry_status}")
    if exit_status != "resolved":
        resolution_blockers.add(f"exit_{exit_status}")

    entry_debit = None
    exit_value = None
    side_aware_net = None
    if entry_status == "resolved":
        entry_debit = entry_long["ask"] - entry_short["bid"]  # type: ignore[index]
        if entry_debit <= 0:
            resolution_blockers.add("entry_debit_nonpositive")
    if exit_status == "resolved":
        exit_value = exit_long["bid"] - exit_short["ask"]  # type: ignore[index]
        if exit_value < 0:
            resolution_blockers.add("exit_value_negative")
    if entry_debit is not None and exit_value is not None:
        diagnostic_fee = 2.6
        side_aware_net = (
            exit_value - entry_debit
        ) * CONTRACT_MULTIPLIER - diagnostic_fee

    proof_qualified = not resolution_blockers
    return {
        "row_id": row.get("row_id"),
        "ticker": row.get("ticker"),
        "entry_date": entry_date,
        "exit_date": row.get("exit_date"),
        "long_contract_symbol": long_contract,
        "short_contract_symbol": short_contract,
        "source_run": source_run,
        "original_denominator_status": row.get("denominator_status"),
        "original_reason_codes": sorted(reasons),
        "resolution_blockers": sorted(resolution_blockers),
        "point_in_time_inputs_resolved": not any(
            item.startswith("missing_point_in_time_") for item in resolution_blockers
        ),
        "point_in_time_vix_bucket_resolved": point_in_time_vix_bucket_resolved,
        "point_in_time_vix_bucket_date_et": vix_bucket_row.get("bucket_date_et")
        if vix_bucket_row
        else None,
        "point_in_time_vix_bucket": vix_bucket_row.get("vix_bucket")
        if vix_bucket_row
        else None,
        "point_in_time_vix_known_at_utc": vix_bucket_row.get("known_at_utc")
        if vix_bucket_row
        else None,
        "point_in_time_market_regime_inputs_resolved": market_regime_row is not None,
        "point_in_time_breadth_confirmation_resolved": point_in_time_breadth_confirmation_resolved,
        "point_in_time_spy_momentum_confirmation_resolved": point_in_time_spy_momentum_confirmation_resolved,
        "point_in_time_qqq_momentum_confirmation_resolved": point_in_time_qqq_momentum_confirmation_resolved,
        "point_in_time_market_regime_input_date_et": market_regime_row.get(
            "input_date_et"
        )
        if market_regime_row
        else None,
        "point_in_time_breadth_confirmed": market_regime_row.get("breadth_confirmed")
        if market_regime_row
        else None,
        "point_in_time_spy_momentum_confirmed": market_regime_row.get(
            "spy_momentum_confirmed"
        )
        if market_regime_row
        else None,
        "point_in_time_qqq_momentum_confirmed": market_regime_row.get(
            "qqq_momentum_confirmed"
        )
        if market_regime_row
        else None,
        "point_in_time_breadth_ratio": market_regime_row.get("breadth_ratio")
        if market_regime_row
        else None,
        "side_aware_entry_quote_status": entry_status,
        "side_aware_exit_quote_status": exit_status,
        "side_aware_quotes_resolved": entry_status == "resolved"
        and exit_status == "resolved",
        "entry_quote_minute_et": entry_pair.get("quote_minute_et")
        if entry_pair
        else None,
        "entry_quote_as_of_utc": entry_pair.get("as_of_utc") if entry_pair else None,
        "entry_quote_pair_synchronized": entry_pair is not None,
        "exit_quote_minute_et": exit_pair.get("quote_minute_et") if exit_pair else None,
        "exit_quote_as_of_utc": exit_pair.get("as_of_utc") if exit_pair else None,
        "exit_quote_pair_synchronized": exit_pair is not None,
        "side_aware_entry_debit": round(entry_debit, 4)
        if entry_debit is not None
        else None,
        "side_aware_exit_value": round(exit_value, 4)
        if exit_value is not None
        else None,
        "side_aware_net_pnl_usd_diagnostic": round(side_aware_net, 2)
        if side_aware_net is not None
        else None,
        "old_mark_net_pnl_usd_diagnostic": row.get("diagnostic_net_pnl_usd"),
        "proof_net_pnl_usd": round(side_aware_net, 2)
        if proof_qualified and side_aware_net is not None
        else None,
        "proof_qualified_after_resolution": proof_qualified,
    }


def _profit_metrics(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    values = [_safe_float(row.get(field)) for row in rows]
    pnl = [value for value in values if value is not None]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = (
        gross_win / gross_loss
        if gross_loss > 0
        else (float("inf") if gross_win > 0 else None)
    )
    dated_values = [
        (row, parsed, value)
        for row in rows
        if (value := _safe_float(row.get(field))) is not None
        and (parsed := _parse_date(row.get("entry_date"))) is not None
    ]
    bootstrap_by_cluster = {
        "ticker_week": block_bootstrap_confidence_for_values(
            [
                (
                    f"{row.get('ticker')}:{parsed.isocalendar().year}-W{parsed.isocalendar().week:02d}",
                    value,
                )
                for row, parsed, value in dated_values
            ],
            branch_id=f"{REPORT_ID}:{field}:ticker_week",
        ),
        "market_week": block_bootstrap_confidence_for_values(
            [
                (
                    f"{parsed.isocalendar().year}-W{parsed.isocalendar().week:02d}",
                    value,
                )
                for _row, parsed, value in dated_values
            ],
            branch_id=f"{REPORT_ID}:{field}:market_week",
        ),
        "entry_date": block_bootstrap_confidence_for_values(
            [(parsed.isoformat(), value) for _row, parsed, value in dated_values],
            branch_id=f"{REPORT_ID}:{field}:entry_date",
        ),
    }
    bootstrap_lbs = [
        value
        for result in bootstrap_by_cluster.values()
        if (value := _safe_float(result.get("pf_lb_5pct"))) is not None
    ]
    conservative_bootstrap_lb = min(bootstrap_lbs) if bootstrap_lbs else None
    return {
        "row_count": len(rows),
        "priced_row_count": len(pnl),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate_pct": round((len(wins) / len(pnl)) * 100.0, 2) if pnl else None,
        "net_pnl_usd": round(sum(pnl), 2) if pnl else None,
        "avg_pnl_usd": round(sum(pnl) / len(pnl), 2) if pnl else None,
        "gross_win_usd": round(gross_win, 2),
        "gross_loss_usd": round(gross_loss, 2),
        "profit_factor": round(pf, 4) if pf not in (None, float("inf")) else pf,
        "bootstrap_pf_lower_bound_5pct": conservative_bootstrap_lb,
        "bootstrap_policy": "minimum_5pct_pf_lower_bound_across_ticker_week_market_week_and_entry_date_clusters",
        "bootstrap_sensitivity": bootstrap_by_cluster,
        "stress_pf": None,
        "stress_test_status": "not_implemented_requires_preregistered_cost_and_liquidity_shocks",
    }


def _status(
    strict_rows: list[dict[str, Any]],
    metrics: dict[str, Any],
    blocker_counts: Counter[str],
    quote_coverage: float,
    artifact_integrity_blockers: list[str],
) -> str:
    if artifact_integrity_blockers:
        return "momentum_continuation_blocked_artifact_integrity_failure"
    if (
        blocker_counts.get("missing_point_in_time_vix_bucket")
        or blocker_counts.get("missing_point_in_time_breadth_confirmation")
        or blocker_counts.get("missing_point_in_time_spy_momentum_confirmation")
        or blocker_counts.get("missing_point_in_time_qqq_momentum_confirmation")
    ):
        return "momentum_continuation_blocked_missing_local_proof_inputs"
    if quote_coverage < MIN_QUOTE_COVERAGE:
        return "momentum_continuation_blocked_incomplete_eligible_quote_coverage"
    if len(strict_rows) < MIN_STRICT_ROWS:
        return "momentum_continuation_rejected_negative_or_underpowered_after_proof_resolution"
    pf = _safe_float(metrics.get("profit_factor"))
    pf_lb = _safe_float(metrics.get("bootstrap_pf_lower_bound_5pct"))
    net = _safe_float(metrics.get("net_pnl_usd"))
    stress = _safe_float(metrics.get("stress_pf"))
    if (
        pf
        and pf > 1.0
        and net
        and net > 0
        and pf_lb
        and pf_lb > MIN_PF_LOWER_BOUND
        and stress
        and stress >= MIN_STRESS_PF
    ):
        return "momentum_continuation_proof_candidate_for_review_not_forward_proof"
    return (
        "momentum_continuation_rejected_negative_or_underpowered_after_proof_resolution"
    )


def build_report(
    *,
    source_replay_path: Path = DEFAULT_SOURCE_REPLAY,
    preregistered_playbook_path: Path = DEFAULT_PREREGISTERED_PLAYBOOK,
    point_in_time_vix_bucket_path: Path = DEFAULT_POINT_IN_TIME_VIX_BUCKET,
    point_in_time_market_regime_inputs_path: Path = DEFAULT_POINT_IN_TIME_MARKET_REGIME_INPUTS,
    all_planned_path: Path = DEFAULT_ALL_PLANNED,
    options_db_path: Path = DEFAULT_OPTIONS_DB,
    runs_dir: Path = DEFAULT_RUNS_DIR,
    run_paths: list[Path] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    source_replay, source_meta = _load_json(source_replay_path, required=True)
    preregistered, preregistered_meta = _load_json(
        preregistered_playbook_path, required=True
    )
    point_in_time_vix_bucket, vix_meta = _load_json(
        point_in_time_vix_bucket_path, required=False
    )
    vix_buckets_by_date = _vix_bucket_index(point_in_time_vix_bucket)
    point_in_time_market_regime_inputs, market_regime_meta = _load_json(
        point_in_time_market_regime_inputs_path,
        required=False,
    )
    market_regime_by_date = _market_regime_index(point_in_time_market_regime_inputs)
    source_valid = _source_replay_valid(source_replay)
    denominator_rows, run_metas, entry_minutes = _reconstruct_denominator(
        all_planned_path, runs_dir, run_paths
    )
    declared_denominator = _as_dict(source_replay.get("denominator")).get("row_count")
    artifact_integrity_blockers: list[str] = []
    if source_meta.get("status") != "loaded" or not source_valid:
        artifact_integrity_blockers.append("invalid_source_replay_artifact")
    if preregistered_meta.get(
        "status"
    ) != "loaded" or not _preregistered_playbook_valid(preregistered):
        artifact_integrity_blockers.append("invalid_preregistered_playbook_artifact")
    if declared_denominator != len(denominator_rows):
        artifact_integrity_blockers.append(
            "source_and_reconstructed_denominator_mismatch"
        )
    if not run_metas or any(meta.get("status") != "loaded" for meta in run_metas):
        artifact_integrity_blockers.append("incomplete_or_invalid_run_artifacts")
    artifact_integrity_blockers = sorted(set(artifact_integrity_blockers))
    conn = _connect_options_db(options_db_path)
    try:
        resolved_rows = [
            _resolved_row(
                row, conn, entry_minutes, vix_buckets_by_date, market_regime_by_date
            )
            for row in denominator_rows
        ]
    finally:
        if conn is not None:
            conn.close()
    strict_rows = [
        row
        for row in resolved_rows
        if row.get("proof_qualified_after_resolution") is True
    ]
    side_aware_rows = [
        row for row in resolved_rows if row.get("side_aware_quotes_resolved") is True
    ]
    point_rows = [
        row for row in resolved_rows if row.get("point_in_time_inputs_resolved") is True
    ]
    vix_resolved_rows = [
        row
        for row in resolved_rows
        if row.get("point_in_time_vix_bucket_resolved") is True
    ]
    market_regime_rows = [
        row
        for row in resolved_rows
        if row.get("point_in_time_market_regime_inputs_resolved") is True
    ]
    breadth_resolved_rows = [
        row
        for row in resolved_rows
        if row.get("point_in_time_breadth_confirmation_resolved") is True
    ]
    spy_resolved_rows = [
        row
        for row in resolved_rows
        if row.get("point_in_time_spy_momentum_confirmation_resolved") is True
    ]
    qqq_resolved_rows = [
        row
        for row in resolved_rows
        if row.get("point_in_time_qqq_momentum_confirmation_resolved") is True
    ]
    blocker_counts: Counter[str] = Counter()
    for row in resolved_rows:
        blocker_counts.update(
            str(item) for item in _as_list(row.get("resolution_blockers"))
        )
    eligible_pre_quote_rows = [
        row
        for row in resolved_rows
        if not (set(_as_list(row.get("resolution_blockers"))) - QUOTE_BLOCKERS)
    ]
    eligible_side_aware_rows = [
        row
        for row in eligible_pre_quote_rows
        if row.get("side_aware_quotes_resolved") is True
    ]
    eligible_quote_coverage = (
        len(eligible_side_aware_rows) / len(eligible_pre_quote_rows)
        if eligible_pre_quote_rows
        else 0.0
    )

    quote_repair_rows = [
        {
            "row_id": row.get("row_id"),
            "ticker": row.get("ticker"),
            "entry_date": row.get("entry_date"),
            "exit_date": row.get("exit_date"),
            "long_contract_symbol": row.get("long_contract_symbol"),
            "short_contract_symbol": row.get("short_contract_symbol"),
            "quote_blockers": sorted(
                set(_as_list(row.get("resolution_blockers"))).intersection(
                    QUOTE_BLOCKERS
                )
            ),
        }
        for row in eligible_pre_quote_rows
        if row.get("side_aware_quotes_resolved") is not True
    ]
    quote_repair_blocker_counts: Counter[str] = Counter()
    for row in quote_repair_rows:
        quote_repair_blocker_counts.update(row["quote_blockers"])
    strict_metrics = _profit_metrics(strict_rows, "proof_net_pnl_usd")
    side_aware_metrics = _profit_metrics(
        side_aware_rows, "side_aware_net_pnl_usd_diagnostic"
    )
    diagnostic_metrics = _as_dict(
        _as_dict(source_replay.get("diagnostic_only_existing_marks")).get("metrics")
    )
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": _status(
            strict_rows,
            strict_metrics,
            blocker_counts,
            eligible_quote_coverage,
            artifact_integrity_blockers,
        ),
        **READ_ONLY_FLAGS,
        "scope": "approved_research_only_momentum_continuation_proof_blocker_resolution",
        "concept_id": CONCEPT_ID,
        "source_denominator_rows": declared_denominator,
        "reconstructed_denominator_rows": len(denominator_rows),
        "proof_qualified_rows_before_resolution": _as_dict(
            source_replay.get("proof_qualified")
        ).get("row_count"),
        "proof_qualified_rows_after_resolution": len(strict_rows),
        "historical_rows_are_forward_proof": False,
        "source_replay_valid": source_valid,
        "artifact_integrity_blockers": artifact_integrity_blockers,
        "source_artifacts": {
            "source_replay": source_meta,
            "preregistered_playbook": preregistered_meta,
            "point_in_time_vix_bucket": vix_meta,
            "point_in_time_market_regime_inputs": market_regime_meta,
            "run_artifacts": run_metas,
            "options_db": {
                "path": _rel(options_db_path),
                "exists": options_db_path.exists(),
                "opened_read_only": options_db_path.exists(),
            },
        },
        "point_in_time_vix_bucket_resolution": {
            "artifact_status": point_in_time_vix_bucket.get("status"),
            "artifact_ready_for_stale_blocker_clear": _vix_artifact_ready(
                point_in_time_vix_bucket
            ),
            "artifact_blockers": _as_list(point_in_time_vix_bucket.get("blockers")),
            "valid_bucket_date_count": len(vix_buckets_by_date),
            "resolved_row_count": len(vix_resolved_rows),
            "join_key": "row.entry_date == point_in_time_vix_bucket.bucket_rows[].bucket_date_et",
            "safe_fields_required": [
                "bucket_date_et",
                "point_in_time_valid",
                "source_provenance_status",
                "source_timestamp_utc",
                "known_at_utc",
                "vix_bucket",
            ],
        },
        "point_in_time_market_regime_input_resolution": {
            "artifact_status": point_in_time_market_regime_inputs.get("status"),
            "artifact_ready_for_stale_blocker_clear": _market_regime_artifact_ready(
                point_in_time_market_regime_inputs
            ),
            "artifact_blockers": _as_list(
                point_in_time_market_regime_inputs.get("blockers")
            ),
            "source_time_policy": _as_dict(
                point_in_time_market_regime_inputs.get("source_time_policy")
            ),
            "historical_reconstruction_can_clear_point_in_time_blockers": _as_dict(
                point_in_time_market_regime_inputs.get("source_time_policy")
            ).get("historical_reconstruction_can_clear_point_in_time_blockers"),
            "valid_input_date_count": len(market_regime_by_date),
            "resolved_row_count": len(market_regime_rows),
            "breadth_confirmation_resolved": len(breadth_resolved_rows),
            "spy_momentum_confirmation_resolved": len(spy_resolved_rows),
            "qqq_momentum_confirmation_resolved": len(qqq_resolved_rows),
            "join_key": "row.entry_date == point_in_time_market_regime_inputs.input_rows[].input_date_et",
            "safe_fields_required": [
                "input_date_et",
                "point_in_time_valid",
                "spy_momentum_confirmed",
                "qqq_momentum_confirmed",
                "breadth_confirmed",
                "source_time_status",
                "historical_prior_bar_reconstruction",
                "proof_eligible",
            ],
        },
        "preregistered_status": preregistered.get("status"),
        "proof_formula": {
            "entry_debit": "long_call_ask - short_call_bid",
            "exit_value": "long_call_bid - short_call_ask",
            "net_pnl_usd": "(exit_value - entry_debit) * 100 - fees/slippage",
        },
        "resolution_counts": {
            "full_denominator_fail_closed": len(resolved_rows),
            "point_in_time_inputs_resolved": len(point_rows),
            "point_in_time_vix_bucket_resolved": len(vix_resolved_rows),
            "point_in_time_market_regime_inputs_resolved": len(market_regime_rows),
            "point_in_time_breadth_confirmation_resolved": len(breadth_resolved_rows),
            "point_in_time_spy_momentum_confirmation_resolved": len(spy_resolved_rows),
            "point_in_time_qqq_momentum_confirmation_resolved": len(qqq_resolved_rows),
            "side_aware_quotes_resolved": len(side_aware_rows),
            "proof_qualified_candidate_rows": len(strict_rows),
            "blocker_counts": dict(sorted(blocker_counts.items())),
        },
        "quote_coverage_resolution": {
            "policy": "synchronized_trusted_bid_ask_pairs_among_rows_passing_all_non_quote_filters",
            "minimum_required": MIN_QUOTE_COVERAGE,
            "eligible_pre_quote_row_count": len(eligible_pre_quote_rows),
            "eligible_side_aware_row_count": len(eligible_side_aware_rows),
            "eligible_quote_coverage": round(eligible_quote_coverage, 4),
            "quote_repair_row_count": len(quote_repair_rows),
            "quote_repair_blocker_counts": dict(
                sorted(quote_repair_blocker_counts.items())
            ),
            "quote_repair_rows": quote_repair_rows,
        },
        "strict_research_metrics": strict_metrics,
        "side_aware_diagnostic_metrics": side_aware_metrics,
        "diagnostic_old_mark_comparison": {
            "source_metrics": diagnostic_metrics,
            "not_counted_as_proof": True,
        },
        "blockers": _blockers(
            strict_rows,
            strict_metrics,
            blocker_counts,
            eligible_quote_coverage,
            artifact_integrity_blockers,
        ),
        "sample_rows": resolved_rows[:50],
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }
    _validate_report(report)
    return report


def _blockers(
    strict_rows: list[dict[str, Any]],
    metrics: dict[str, Any],
    blocker_counts: Counter[str],
    quote_coverage: float,
    artifact_integrity_blockers: list[str],
) -> list[str]:
    blockers = list(artifact_integrity_blockers) + [
        item
        for item in (
            "missing_point_in_time_vix_bucket",
            "missing_point_in_time_breadth_confirmation",
            "missing_point_in_time_spy_momentum_confirmation",
            "missing_point_in_time_qqq_momentum_confirmation",
        )
        if blocker_counts.get(item)
    ]
    if quote_coverage < MIN_QUOTE_COVERAGE:
        blockers.append("eligible_quote_coverage_below_90_pct")
    if len(strict_rows) < MIN_STRICT_ROWS:
        blockers.append("strict_rows_below_30_after_resolution")
    pf_lb = _safe_float(metrics.get("bootstrap_pf_lower_bound_5pct"))
    if pf_lb is None or pf_lb <= MIN_PF_LOWER_BOUND:
        blockers.append("bootstrap_pf_lower_bound_not_above_1_after_resolution")
    net = _safe_float(metrics.get("net_pnl_usd"))
    if net is None or net <= 0:
        blockers.append("net_usd_not_positive_after_resolution")
    if metrics.get("stress_test_status") != "implemented":
        blockers.append("preregistered_stress_test_not_implemented")
    return sorted(set(blockers))


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    if report.get("concept_id") != CONCEPT_ID:
        raise ValueError("wrong concept")
    if report.get("accepted_profitability") is not False:
        raise ValueError(
            "historical proof-blocker resolution cannot accept profitability"
        )
    if report.get("historical_rows_are_forward_proof") is not False:
        raise ValueError("historical rows cannot become forward proof")


def _fmt_bool(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    counts = _as_dict(report.get("resolution_counts"))
    lines = [
        "# Regular Options Momentum Continuation Proof-Blocker Resolution",
        "",
        "This report is generated from `scripts/build_regular_options_momentum_continuation_proof_blocker_resolution.py`. It is a read-only resolver inside the already-approved momentum-continuation research harness. It uses existing local artifacts and read-only trusted quote lookups only; it does not import quotes, mutate evidence stores, append forward rows, change scanner policy, or promote anything.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Concept: `{report['concept_id']}`.",
        f"- Source denominator rows: `{report.get('source_denominator_rows')}`.",
        f"- Reconstructed denominator rows: `{report.get('reconstructed_denominator_rows')}`.",
        f"- Proof rows before resolution: `{report.get('proof_qualified_rows_before_resolution')}`.",
        f"- Proof rows after resolution: `{report.get('proof_qualified_rows_after_resolution')}`.",
        f"- Accepted profitability: `{_fmt_bool(report['accepted_profitability'])}`.",
        f"- Historical rows are forward proof: `{_fmt_bool(report['historical_rows_are_forward_proof'])}`.",
        "",
        "## Resolution Counts",
        "",
        f"- Point-in-time inputs resolved: `{counts.get('point_in_time_inputs_resolved')}`.",
        f"- Point-in-time VIX buckets resolved: `{counts.get('point_in_time_vix_bucket_resolved')}`.",
        f"- Point-in-time market-regime input rows resolved: `{counts.get('point_in_time_market_regime_inputs_resolved')}`.",
        f"- Point-in-time breadth confirmations resolved: `{counts.get('point_in_time_breadth_confirmation_resolved')}`.",
        f"- Point-in-time SPY momentum confirmations resolved: `{counts.get('point_in_time_spy_momentum_confirmation_resolved')}`.",
        f"- Point-in-time QQQ momentum confirmations resolved: `{counts.get('point_in_time_qqq_momentum_confirmation_resolved')}`.",
        f"- Side-aware quotes resolved: `{counts.get('side_aware_quotes_resolved')}`.",
        f"- Proof-qualified candidate rows: `{counts.get('proof_qualified_candidate_rows')}`.",
        f"- Strict research metrics: `{json.dumps(report.get('strict_research_metrics'), sort_keys=True)}`.",
        f"- Side-aware diagnostic metrics: `{json.dumps(report.get('side_aware_diagnostic_metrics'), sort_keys=True)}`.",
        "",
        "## Blocker Counts",
        "",
        "| Blocker | Rows |",
        "| --- | ---: |",
    ]
    for blocker, count in _as_dict(counts.get("blocker_counts")).items():
        lines.append(f"| `{blocker}` | {count} |")
    lines.extend(["", "## Final Blockers", ""])
    lines.extend(f"- `{item}`" for item in _as_list(report.get("blockers")))
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
        path.write_text(
            json.dumps(report_with_artifacts, indent=2, sort_keys=True) + "\n",
            encoding="utf8",
        )
    for path in (md_path, latest_md, docs_report):
        path.write_text(markdown, encoding="utf8")
    report["artifacts"] = artifacts
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a read-only momentum-continuation proof-blocker resolution audit."
    )
    parser.add_argument("--source-replay", type=Path, default=DEFAULT_SOURCE_REPLAY)
    parser.add_argument(
        "--preregistered-playbook", type=Path, default=DEFAULT_PREREGISTERED_PLAYBOOK
    )
    parser.add_argument(
        "--point-in-time-vix-bucket",
        type=Path,
        default=DEFAULT_POINT_IN_TIME_VIX_BUCKET,
    )
    parser.add_argument(
        "--point-in-time-market-regime-inputs",
        type=Path,
        default=DEFAULT_POINT_IN_TIME_MARKET_REGIME_INPUTS,
    )
    parser.add_argument("--all-planned", type=Path, default=DEFAULT_ALL_PLANNED)
    parser.add_argument("--options-db", type=Path, default=DEFAULT_OPTIONS_DB)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument(
        "--run", action="append", type=Path, dest="run_paths", default=None
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = build_report(
        source_replay_path=args.source_replay,
        preregistered_playbook_path=args.preregistered_playbook,
        point_in_time_vix_bucket_path=args.point_in_time_vix_bucket,
        point_in_time_market_regime_inputs_path=args.point_in_time_market_regime_inputs,
        all_planned_path=args.all_planned,
        options_db_path=args.options_db,
        runs_dir=args.runs_dir,
        run_paths=args.run_paths,
    )
    if not args.no_write:
        report["artifacts"] = write_outputs(
            report, output_dir=args.output_dir, docs_report=args.docs_report
        )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
