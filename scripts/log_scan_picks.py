"""
Log today's scan picks to data/forward-tracking/scan_picks.jsonl

Each line is one pick with entry details and underlying price at scan time.
The daily scan also auto-creates tracked positions for new picks using the
same exact/comparable-contract resolution path as the app UI.

Usage: python scripts/log_scan_picks.py
"""

from __future__ import annotations

import copy
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PYTHON_BACKEND_DIR = ROOT / "python-backend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(PYTHON_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_BACKEND_DIR))

from local_env import load_local_env
from forward_options_ledger import build_forward_scan_snapshot, record_forward_snapshot
from positions_repository import create_positions_repository
from positions_service import build_position_payload, review_open_positions
from supervised_scan import DEFAULT_SCAN_PLAYBOOK_ID, LIVE_SCAN_TRUTH_LANE, run_supervised_scan
from us_equity_market_calendar import is_us_equity_market_day


LOG_DIR = ROOT / "data" / "forward-tracking"
LOG_FILE = LOG_DIR / "scan_picks.jsonl"
FILL_ATTEMPT_LOG_FILE = LOG_DIR / "fill_attempts.jsonl"
LIQUIDITY_NEAR_MISS_LOG_FILE = LOG_DIR / "liquidity_near_misses.jsonl"


def _is_market_closed(run_at: datetime) -> bool:
    return not is_us_equity_market_day(run_at.date())


def _scan_date_value(row: dict[str, Any]) -> str:
    return str(row.get("scan_date") or "")[:10]


def _playbook_value(row: dict[str, Any]) -> str:
    return str(row.get("playbook_id") or "").strip()


def _load_log_rows(*, log_file: Path = LOG_FILE) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not log_file.exists():
        return rows
    for line in log_file.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except Exception:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def _write_log_rows(rows: list[dict[str, Any]], *, log_file: Path = LOG_FILE) -> None:
    os.makedirs(log_file.parent, exist_ok=True)
    with log_file.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _append_log_rows(rows: list[dict[str, Any]], *, log_file: Path) -> None:
    if not rows:
        return
    os.makedirs(log_file.parent, exist_ok=True)
    with log_file.open("a", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _replace_scan_rows(
    scan_date: str,
    records: list[dict[str, Any]],
    *,
    log_file: Path = LOG_FILE,
) -> int:
    existing_rows = _load_log_rows(log_file=log_file)
    record_playbooks = {_playbook_value(record) for record in records if _playbook_value(record)}

    def _matches_replace_scope(row: dict[str, Any]) -> bool:
        if _scan_date_value(row) != scan_date:
            return False
        if not record_playbooks:
            return True
        return _playbook_value(row) in record_playbooks

    replaced = sum(1 for row in existing_rows if _matches_replace_scope(row))
    kept_rows = [row for row in existing_rows if not _matches_replace_scope(row)]
    _write_log_rows(kept_rows + records, log_file=log_file)
    return replaced


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _pick_fill_price(scan_pick: dict[str, Any]) -> float | None:
    strategy_type = str(scan_pick.get("strategy_type") or "").strip().lower()
    fields = ("entry_execution_price", "net_debit", "premium", "est_premium", "mid")
    if strategy_type == "vertical_spread" or scan_pick.get("short_strike") is not None:
        fields = ("entry_execution_price", "net_debit", "premium", "est_premium", "mid")
    for field in fields:
        value = _safe_float(scan_pick.get(field))
        if value is not None and value > 0:
            return round(float(value), 4)
    return None


def _safe_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _top_spread_alternatives(pick: dict[str, Any], *, limit: int = 3) -> list[dict[str, Any]]:
    alternatives = [
        dict(item)
        for item in list(pick.get("spread_alternatives") or [])
        if isinstance(item, dict)
    ]
    return copy.deepcopy(alternatives[: max(int(limit), 0)])


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _top_counts(value: Any, *, limit: int = 5) -> str:
    counts = _safe_dict(value)
    pairs: list[tuple[str, int]] = []
    for key, count in counts.items():
        try:
            normalized_count = int(count or 0)
        except (TypeError, ValueError):
            normalized_count = 0
        if normalized_count > 0:
            pairs.append((str(key), normalized_count))
    pairs.sort(key=lambda item: (-item[1], item[0]))
    return ", ".join(f"{key}={count}" for key, count in pairs[:limit]) or "none"


def _compact_pick_label(pick: dict[str, Any]) -> str:
    ticker = str(pick.get("ticker") or "?").upper()
    direction = str(pick.get("direction") or pick.get("type") or "?").lower()
    strike = pick.get("strike")
    short_strike = pick.get("short_strike")
    expiry = pick.get("expiry") or "?"
    debit = pick.get("net_debit")
    debit_pct = pick.get("debit_pct_of_width")
    spread = f"{strike}/{short_strike}" if short_strike is not None else str(strike or "?")
    parts = [f"{ticker} {direction} {spread}", f"exp={expiry}"]
    if debit is not None:
        try:
            parts.append(f"debit={float(debit):.2f}")
        except (TypeError, ValueError):
            parts.append(f"debit={debit}")
    if debit_pct is not None:
        try:
            parts.append(f"debit_width={float(debit_pct):.1f}%")
        except (TypeError, ValueError):
            parts.append(f"debit_width={debit_pct}")
    return " ".join(parts)


def _print_scan_diagnostics(scan_result: dict[str, Any], *, max_candidates: int = 5) -> None:
    playbook = _safe_dict(scan_result.get("playbook"))
    playbook_id = str(playbook.get("id") or "unknown")
    playbook_label = str(playbook.get("label") or playbook_id)
    scan_funnel = _safe_dict(scan_result.get("scan_funnel"))
    raw_candidates = scan_funnel.get("raw_candidates", scan_result.get("candidate_count", 0))
    returned_picks = scan_funnel.get("returned_picks", scan_result.get("returned_count", 0))

    print(
        "Scan diagnostics: "
        f"playbook={playbook_id} ({playbook_label}) "
        f"raw_candidates={raw_candidates} returned_picks={returned_picks}"
    )
    print(f"  Top scan drops: {_top_counts(scan_funnel.get('drop_counts'))}")
    print(f"  Guardrails: {_top_counts(scan_funnel.get('guardrail_counts'))}")
    print(f"  Policy: {_top_counts(scan_funnel.get('policy_counts'))}")

    audit_picks = [
        dict(pick)
        for pick in list(scan_result.get("candidate_audit_picks") or [])
        if isinstance(pick, dict)
    ]
    if not audit_picks:
        return

    print("  Candidate audit:")
    for pick in audit_picks[: max(int(max_candidates), 0)]:
        decision = str(pick.get("guardrail_decision") or "candidate")
        reasons = list(pick.get("guardrail_reasons") or [])
        if not reasons and pick.get("managed_block_reason"):
            reasons = [str(pick.get("managed_block_reason"))]
        reason_text = "; ".join(str(reason) for reason in reasons if str(reason).strip()) or "no blocker recorded"
        print(f"    - {decision}: {_compact_pick_label(pick)} | {reason_text}")


def _env_flag_enabled(name: str, default: bool = True) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}


def _scan_allows_auto_track(scan_result: dict[str, Any]) -> bool:
    return _env_flag_enabled("OPTIONS_SCAN_AUTO_TRACK", True)


def _position_contract_signature(record: dict[str, Any]) -> tuple[Any, ...]:
    source = _safe_dict(record.get("source_pick_snapshot"))

    def _norm_float(value: Any) -> float | None:
        try:
            return round(float(value), 4)
        except (TypeError, ValueError):
            return None

    strike = record.get("strike")
    if strike is None:
        strike = source.get("strike")
    if strike is None:
        strike = source.get("strike_est")

    expiry = record.get("expiry")
    if expiry is None:
        expiry = source.get("expiry")

    direction = record.get("direction")
    if direction is None:
        direction = source.get("direction") or source.get("type")

    contract_symbol = record.get("contract_symbol")
    if contract_symbol is None:
        contract_symbol = source.get("contract_symbol") or source.get("contractSymbol")

    strategy_type = (
        source.get("strategy_type")
        or record.get("strategy_type")
        or ("vertical_spread" if source.get("short_strike") is not None else "single_leg")
    )

    return (
        str(record.get("ticker") or source.get("ticker") or "").strip().upper() or None,
        str(direction or "").strip().lower() or None,
        str(expiry or "").strip()[:10] or None,
        str(strategy_type or "").strip().lower() or None,
        _norm_float(strike),
        _norm_float(source.get("short_strike") if source else record.get("short_strike")),
        str(contract_symbol or "").strip().upper() or None,
        str(source.get("short_contract_symbol") or record.get("short_contract_symbol") or "").strip().upper() or None,
    )


def _find_existing_open_contract(repository: Any, payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        open_positions = list(repository.list_positions("open") or [])
    except Exception:
        return None
    target_signature = _position_contract_signature(payload)
    for position in open_positions:
        if _position_contract_signature(dict(position)) == target_signature:
            return dict(position)
    return None


def _scan_pick_event_key(pick: dict[str, Any], candidate_rank: int) -> str:
    event_key = f"rank_{int(candidate_rank)}"
    cohort_id = str(pick.get("cohort_id") or "").strip()
    return f"{cohort_id}:{event_key}" if cohort_id else event_key


def _auto_track_scan_picks(
    *,
    repository: Any,
    picks: list[dict[str, Any]],
    filled_at: str,
    scan_date: str,
    tracked_links: list[tuple[int, int]] | None = None,
) -> tuple[int, int, int]:
    created_ids: list[int] = []
    created = 0
    duplicates = 0
    skipped = 0

    for idx, pick in enumerate(picks, start=1):
        fill_price = _pick_fill_price(pick)
        if fill_price is None:
            skipped += 1
            print(f"  Skipped auto-track: {pick.get('ticker')} missing fill price")
            continue

        try:
            payload = build_position_payload(
                scan_pick=copy.deepcopy(pick),
                fill_price=fill_price,
                contracts=1,
                filled_at=filled_at,
                notes=f"Auto-created from scheduled daily scan {scan_date}.",
                require_proof_eligible=True,
                require_resolved_contract=True,
                preserve_fill_price=True,
            )
        except Exception as exc:
            skipped += 1
            print(f"  Skipped auto-track: {pick.get('ticker')} ({exc})")
            continue

        existing_position = _find_existing_open_contract(repository, payload)
        if existing_position is not None:
            duplicates += 1
            if tracked_links is not None and existing_position.get("id") is not None:
                tracked_links.append((int(existing_position["id"]), idx))
            print(f"  Already open: {pick.get('ticker')} {payload.get('expiry')}")
            continue

        created_position = repository.create_position(payload)
        created += 1
        if created_position.get("id") is not None:
            created_ids.append(int(created_position["id"]))
            if tracked_links is not None:
                tracked_links.append((int(created_position["id"]), idx))
        print(
            "  Auto-tracked: "
            f"{created_position.get('ticker')} {created_position.get('direction')} "
            f"${created_position.get('entry_option_price'):.2f} exp={created_position.get('expiry')}"
        )

    if created_ids:
        try:
            review_open_positions(repository, position_ids=created_ids)
        except Exception as exc:
            print(f"  Review after auto-track failed: {exc}")

    return created, duplicates, skipped


def _review_positions_before_scan(repository: Any) -> list[dict[str, Any]]:
    if not getattr(repository, "is_available", False):
        return []
    try:
        reviewed_positions = list(review_open_positions(repository) or [])
    except Exception as exc:
        print(f"Pre-scan open position review failed: {exc}")
        return []

    expired_auto_closed = sum(
        1
        for position in reviewed_positions
        if position.get("status") == "closed" and position.get("exit_reason") == "expired_auto_close"
    )
    sell_auto_closed = sum(
        1
        for position in reviewed_positions
        if position.get("status") == "closed" and position.get("exit_reason") == "auto_sell_recommendation"
    )
    if reviewed_positions:
        print(
            "Pre-scan open position review summary: "
            f"reviewed={len(reviewed_positions)}, "
            f"auto_sell_closed={sell_auto_closed}, "
            f"expired_auto_closed={expired_auto_closed}"
        )
    return reviewed_positions


def _build_log_record(
    pick: dict[str, Any],
    *,
    run_at: datetime,
    scan_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scan_result = scan_result or {}
    playbook = _safe_dict(scan_result.get("playbook"))
    return {
        "logged_at": run_at.isoformat(),
        "scan_date": run_at.strftime("%Y-%m-%d"),
        "ticker": pick.get("ticker"),
        "direction": pick.get("direction"),
        "type": pick.get("type"),
        "strategy_type": pick.get("strategy_type"),
        "contract_symbol": pick.get("contract_symbol"),
        "short_contract_symbol": pick.get("short_contract_symbol"),
        "long_strike": pick.get("strike"),
        "short_strike": pick.get("short_strike"),
        "spread_width": pick.get("spread_width"),
        "net_debit": pick.get("net_debit"),
        "entry_execution_price": pick.get("entry_execution_price"),
        "entry_execution_basis": pick.get("entry_execution_basis"),
        "max_profit": pick.get("max_profit"),
        "max_loss": pick.get("max_loss"),
        "risk_reward_ratio": pick.get("risk_reward_ratio"),
        "debit_pct_of_width": pick.get("debit_pct_of_width"),
        "spread_entry_debit": pick.get("spread_entry_debit"),
        "spread_bid_ask_pct_of_mid": pick.get("spread_bid_ask_pct_of_mid"),
        "spread_liquidity": pick.get("spread_liquidity"),
        "spread_alternatives": _top_spread_alternatives(pick),
        "liquidity_first_score": pick.get("liquidity_first_score"),
        "expiry": pick.get("expiry"),
        "original_logged_expiry": pick.get("original_logged_expiry"),
        "resolved_listed_expiry": pick.get("resolved_listed_expiry"),
        "dte": pick.get("dte"),
        "underlying_price": pick.get("underlying_price_at_selection") or pick.get("stock_price"),
        "direction_score": pick.get("direction_score"),
        "tech_score": pick.get("tech_score"),
        "quality_score": pick.get("quality_score"),
        "ev_pct": pick.get("ev_pct"),
        "rsi14": pick.get("rsi14"),
        "ret5": pick.get("ret5"),
        "hv30": pick.get("iv_pct"),
        "market_regime": pick.get("market_regime"),
        "spy_ret5": pick.get("spy_ret5"),
        "sector": pick.get("sector"),
        "signal_reasons": pick.get("signal_reasons"),
        "quote_time_et": pick.get("quote_time_et"),
        "quote_time_utc": pick.get("quote_time_utc"),
        "quote_basis": pick.get("quote_basis"),
        "market_data_provider": pick.get("market_data_provider"),
        "market_data_source": pick.get("market_data_source"),
        "underlying_data_source": pick.get("underlying_data_source"),
        "options_data_source": pick.get("options_data_source"),
        "quote_source": pick.get("quote_source"),
        "quote_freshness_status": pick.get("quote_freshness_status"),
        "quote_timestamp_utc": pick.get("quote_timestamp_utc"),
        "quote_timestamp_et": pick.get("quote_timestamp_et"),
        "quote_timestamp_source": pick.get("quote_timestamp_source"),
        "iv_rank_source": pick.get("iv_rank_source"),
        "iv_rank_proof_grade": pick.get("iv_rank_proof_grade"),
        "iv_rank_quality_flag": pick.get("iv_rank_quality_flag"),
        "data_quality_status": pick.get("data_quality_status"),
        "data_quality_flags": pick.get("data_quality_flags"),
        "pricing_evidence_class": pick.get("pricing_evidence_class"),
        "profitability_evidence_class": pick.get("profitability_evidence_class"),
        "source_separation": pick.get("source_separation"),
        "selection_source": pick.get("selection_source"),
        "promotion_class": pick.get("promotion_class"),
        "candidate_execution_label": pick.get("candidate_execution_label") or pick.get("execution_candidate_label"),
        "trade_policy_decision": pick.get("trade_policy_decision") or pick.get("policy_decision"),
        "policy_fit_score": pick.get("policy_fit_score"),
        "policy_fit_reasons": pick.get("policy_fit_reasons"),
        "winner_profile_fit_score": pick.get("winner_profile_fit_score"),
        "winner_profile_fit_reasons": pick.get("winner_profile_fit_reasons"),
        "policy_promotion_status": pick.get("policy_promotion_status"),
        "guardrail_decision": pick.get("guardrail_decision"),
        "guardrail_reasons": pick.get("guardrail_reasons"),
        "suggested_size_tier": pick.get("suggested_size_tier"),
        "suggested_size_reason": pick.get("suggested_size_reason"),
        "managed_eligible": pick.get("managed_eligible"),
        "managed_lane_decision": pick.get("managed_lane_decision"),
        "managed_block_reason": pick.get("managed_block_reason"),
        "playbook_id": pick.get("playbook_id") or playbook.get("id"),
        "playbook_label": pick.get("playbook_label") or playbook.get("label"),
        "truth_lane": scan_result.get("truth_lane"),
        "policy_applied": scan_result.get("policy_applied"),
        "approximation_only": pick.get("approximation_only"),
        "comparable_contract": pick.get("comparable_contract"),
        "comparable_contract_basis": pick.get("comparable_contract_basis"),
        "comparable_contract_label": pick.get("comparable_contract_label"),
        "resolution_notes": pick.get("resolution_notes"),
        "entry_quote_snapshot": pick.get("entry_quote_snapshot"),
        "stop_loss_pct": pick.get("stop_loss_pct"),
        "profit_target_pct": pick.get("profit_target_pct"),
        "time_exit_pct": pick.get("time_exit_pct"),
        "time_exit_day": pick.get("time_exit_day"),
        # For tracking outcome later
        "outcome": None,
        "exit_date": None,
        "exit_price": None,
        "pnl_pct": None,
    }


def _spread_fill_snapshot(pick: dict[str, Any]) -> dict[str, Any]:
    liquidity = _safe_dict(pick.get("spread_liquidity"))
    return {
        "ticker": pick.get("ticker"),
        "direction": pick.get("direction"),
        "strategy_type": pick.get("strategy_type"),
        "expiry": pick.get("expiry"),
        "long_contract_symbol": pick.get("contract_symbol"),
        "short_contract_symbol": pick.get("short_contract_symbol"),
        "long_strike": pick.get("strike"),
        "short_strike": pick.get("short_strike"),
        "spread_width": pick.get("spread_width"),
        "net_debit": pick.get("net_debit"),
        "entry_execution_price": pick.get("entry_execution_price"),
        "entry_execution_basis": pick.get("entry_execution_basis"),
        "spread_mid_debit": liquidity.get("spread_mid_debit"),
        "spread_entry_debit": liquidity.get("spread_entry_debit"),
        "spread_bid_ask_pct_of_mid": pick.get("spread_bid_ask_pct_of_mid"),
        "debit_pct_of_width": pick.get("debit_pct_of_width"),
        "legs": copy.deepcopy(pick.get("legs") or []),
    }


def _build_fill_attempt_record(
    pick: dict[str, Any],
    *,
    run_at: datetime,
    scan_result: dict[str, Any] | None = None,
    candidate_rank: int = 1,
) -> dict[str, Any]:
    scan_result = scan_result or {}
    playbook = _safe_dict(scan_result.get("playbook"))
    liquidity = _safe_dict(pick.get("spread_liquidity"))
    intended_limit_price = _pick_fill_price(pick)
    spread_mid = _safe_float(liquidity.get("spread_mid_debit") or pick.get("mid"))
    fill_degradation_vs_mid = None
    fill_degradation_vs_mid_pct = None
    if intended_limit_price is not None and spread_mid is not None and spread_mid > 0:
        fill_degradation_vs_mid = round(float(intended_limit_price) - float(spread_mid), 4)
        fill_degradation_vs_mid_pct = round(fill_degradation_vs_mid / float(spread_mid) * 100.0, 4)
    alternatives = _top_spread_alternatives(pick)
    return {
        "logged_at": run_at.isoformat(),
        "scan_date": run_at.strftime("%Y-%m-%d"),
        "event_type": "candidate_shown",
        "status": "shown",
        "fill_status": "pending_auto_track",
        "candidate_rank": int(candidate_rank),
        "playbook_id": pick.get("playbook_id") or playbook.get("id"),
        "playbook_label": pick.get("playbook_label") or playbook.get("label"),
        "cohort_id": pick.get("cohort_id") or playbook.get("forced_cohort_id"),
        "ticker": pick.get("ticker"),
        "direction": pick.get("direction"),
        "strategy_type": pick.get("strategy_type"),
        "signal_variant": pick.get("signal_variant"),
        "signal_family": pick.get("signal_family"),
        "candidate_execution_label": pick.get("candidate_execution_label") or pick.get("execution_candidate_label"),
        "selected_spread": _spread_fill_snapshot(pick),
        "top_alternatives": alternatives,
        "top_spread_alternatives": copy.deepcopy(alternatives),
        "intended_limit_price": intended_limit_price,
        "intended_limit_basis": pick.get("entry_execution_basis"),
        "attempted_limit_price": intended_limit_price,
        "attempted_limit_basis": pick.get("entry_execution_basis"),
        "attempted_limit_quote_time_et": pick.get("quote_time_et"),
        "attempted_limit_quote_time_utc": pick.get("quote_time_utc"),
        "fill_degradation_vs_mid": fill_degradation_vs_mid,
        "fill_degradation_vs_mid_pct": fill_degradation_vs_mid_pct,
        "fill_outcome": "pending",
        "fill_outcome_reason": None,
        "auto_track_position_id": None,
        "filled": None,
        "filled_price": None,
        "filled_at": None,
        "canceled_at": None,
        "exit_result": None,
        "review_status": None,
        "reviewed_at": None,
        "close_review_status": None,
        "close_marked_at": None,
        "quote_time_et": pick.get("quote_time_et"),
        "quote_time_utc": pick.get("quote_time_utc"),
        "quote_timestamp_utc": pick.get("quote_timestamp_utc"),
        "quote_timestamp_et": pick.get("quote_timestamp_et"),
        "quote_timestamp_source": pick.get("quote_timestamp_source"),
        "quote_freshness_status": pick.get("quote_freshness_status"),
        "options_data_source": pick.get("options_data_source"),
        "iv_rank_source": pick.get("iv_rank_source"),
        "iv_rank_proof_grade": pick.get("iv_rank_proof_grade"),
        "iv_rank_quality_flag": pick.get("iv_rank_quality_flag"),
        "data_quality_status": pick.get("data_quality_status"),
        "data_quality_flags": pick.get("data_quality_flags"),
        "pricing_evidence_class": pick.get("pricing_evidence_class"),
        "profitability_evidence_class": pick.get("profitability_evidence_class"),
        "source_separation": pick.get("source_separation"),
        "selection_source": pick.get("selection_source") or pick.get("contract_selection_source"),
        "promotion_class": pick.get("promotion_class"),
    }


def _annotate_fill_attempt_outcomes(
    records: list[dict[str, Any]],
    *,
    tracked_links: list[tuple[int, int]],
    auto_track_allowed: bool,
    repository_available: bool,
    reviewed_positions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    position_by_rank = {int(rank): int(position_id) for position_id, rank in tracked_links}
    reviews_by_id = {
        int(position.get("id")): dict(position)
        for position in list(reviewed_positions or [])
        if position.get("id") is not None
    }
    for record in records:
        rank = int(record.get("candidate_rank") or 0)
        position_id = position_by_rank.get(rank)
        if not auto_track_allowed:
            record.update(
                {
                    "fill_status": "not_submitted_auto_track_disabled",
                    "fill_outcome": "not_submitted",
                    "fill_outcome_reason": "auto_track_disabled",
                    "filled": False,
                }
            )
            continue
        if not repository_available:
            record.update(
                {
                    "fill_status": "not_submitted_repository_unavailable",
                    "fill_outcome": "not_submitted",
                    "fill_outcome_reason": "position_repository_unavailable",
                    "filled": False,
                }
            )
            continue
        if position_id is None:
            record.update(
                {
                    "fill_status": "not_filled_auto_track_skipped",
                    "fill_outcome": "no_fill",
                    "fill_outcome_reason": "auto_track_skipped_or_missing_fill_price",
                    "filled": False,
                }
            )
            continue

        review = reviews_by_id.get(position_id, {})
        record.update(
            {
                "fill_status": "auto_tracked",
                "fill_outcome": "paper_fill_recorded",
                "fill_outcome_reason": "auto_track_position_created_or_existing",
                "auto_track_position_id": position_id,
                "filled": True,
                "filled_price": record.get("attempted_limit_price"),
                "filled_at": record.get("logged_at"),
                "review_status": review.get("status") or "open",
                "reviewed_at": review.get("reviewed_at") or review.get("updated_at"),
                "close_review_status": review.get("exit_reason") if review.get("status") == "closed" else None,
                "close_marked_at": review.get("closed_at") or review.get("exit_marked_at"),
            }
        )
    return records


def _append_fill_attempt_records(
    records: list[dict[str, Any]],
    *,
    log_file: Path | None = None,
) -> None:
    _append_log_rows(records, log_file=log_file or (LOG_DIR / "fill_attempts.jsonl"))


def _liquidity_distance(details: dict[str, Any]) -> dict[str, Any]:
    liquidity = _safe_dict(details.get("liquidity"))
    filters = _safe_dict(details.get("liquidity_filters"))

    def _excess(actual_key: str, limit_key: str) -> float | None:
        actual = _safe_float(liquidity.get(actual_key))
        limit = _safe_float(filters.get(limit_key))
        if actual is None or limit is None:
            return None
        return round(max(actual - limit, 0.0), 4)

    def _shortfall(actual_key: str, floor_key: str) -> float | None:
        actual = _safe_float(liquidity.get(actual_key))
        floor = _safe_float(filters.get(floor_key))
        if actual is None or floor is None:
            return None
        return round(max(floor - actual, 0.0), 4)

    components = {
        "worst_leg_spread_excess_pct": _excess("worst_leg_bid_ask_spread_pct", "liquidity_spread_max_pct"),
        "spread_slippage_excess_pct": _excess("spread_bid_ask_pct_of_mid", "spread_liquidity_slippage_max_pct"),
        "quote_age_excess_hours": _excess("max_quote_age_hours", "max_option_quote_age_hours"),
        "min_leg_volume_shortfall": _shortfall("min_leg_volume", "min_option_volume"),
        "min_leg_open_interest_shortfall": _shortfall("min_leg_open_interest", "min_option_open_interest"),
    }
    numeric = [float(value) for value in components.values() if value is not None]
    return {
        "distance_to_current_filters": round(sum(numeric), 4) if numeric else None,
        "components": components,
    }


def _build_liquidity_near_miss_records(
    *,
    scan_result: dict[str, Any],
    run_at: datetime,
    max_records: int = 12,
) -> list[dict[str, Any]]:
    scan_drop_reasons = _safe_dict(scan_result.get("scan_drop_reasons"))
    if not scan_drop_reasons:
        return []
    playbook = _safe_dict(scan_result.get("playbook"))
    scan_funnel = _safe_dict(scan_result.get("scan_funnel"))
    records: list[dict[str, Any]] = []
    for symbol, reason in sorted(scan_drop_reasons.items(), key=lambda item: str(item[0]).upper()):
        reason = _safe_dict(reason)
        if str(reason.get("drop_key") or "").strip() != "option_liquidity":
            continue
        details = _safe_dict(reason.get("details"))
        liquidity = _safe_dict(details.get("liquidity"))
        selected_spread = _safe_dict(details.get("selected_spread"))
        distance = _liquidity_distance(details)
        distance_components = distance["components"]
        alternatives = copy.deepcopy(
            details.get("top_spread_alternatives")
            or details.get("top_alternatives")
            or details.get("spread_alternatives")
            or []
        )
        executable_debit = _first_present(
            details.get("executable_debit"),
            details.get("executable_cost"),
            details.get("estimated_executable_debit"),
            selected_spread.get("executable_debit"),
            selected_spread.get("entry_debit"),
            selected_spread.get("spread_entry_debit"),
            liquidity.get("spread_entry_debit"),
        )
        intended_ask_bid_debit = _first_present(
            details.get("intended_ask_bid_debit"),
            details.get("intended_limit_debit"),
            details.get("limit_debit"),
            selected_spread.get("intended_ask_bid_debit"),
            selected_spread.get("entry_debit"),
            selected_spread.get("spread_entry_debit"),
            liquidity.get("spread_entry_debit"),
            executable_debit,
        )
        ask_bid = _first_present(
            details.get("ask_bid"),
            details.get("bid_ask"),
            selected_spread.get("ask_bid"),
            selected_spread.get("bid_ask"),
        )
        max_quote_age_hours = _first_present(
            details.get("max_quote_age_hours"),
            details.get("quote_age_hours"),
            selected_spread.get("max_quote_age_hours"),
            selected_spread.get("quote_age_hours"),
            liquidity.get("max_quote_age_hours"),
        )
        no_fill_reason = _first_present(
            details.get("no_fill_reason"),
            details.get("fill_outcome_reason"),
            details.get("reason"),
            liquidity.get("reason"),
        )
        records.append(
            {
                "logged_at": run_at.isoformat(),
                "scan_date": run_at.strftime("%Y-%m-%d"),
                "event_type": "liquidity_near_miss",
                "status": "blocked",
                "playbook_id": playbook.get("id"),
                "playbook_label": playbook.get("label"),
                "cohort_id": playbook.get("forced_cohort_id"),
                "ticker": str(symbol or "").strip().upper(),
                "drop_key": "option_liquidity",
                "reason": details.get("reason"),
                "liquidity_reasons": copy.deepcopy(liquidity.get("reasons") or []),
                "liquidity": copy.deepcopy(liquidity),
                "liquidity_filters": copy.deepcopy(details.get("liquidity_filters") or {}),
                "distance_to_current_filters": distance["distance_to_current_filters"],
                "distance_components": distance_components,
                "worst_leg_spread_excess_pct": distance_components.get("worst_leg_spread_excess_pct"),
                "spread_slippage_excess_pct": distance_components.get("spread_slippage_excess_pct"),
                "quote_age_excess_hours": distance_components.get("quote_age_excess_hours"),
                "min_leg_volume_shortfall": distance_components.get("min_leg_volume_shortfall"),
                "min_leg_open_interest_shortfall": distance_components.get("min_leg_open_interest_shortfall"),
                "max_quote_age_hours": max_quote_age_hours,
                "quote_age_hours": max_quote_age_hours,
                "ask_bid": copy.deepcopy(ask_bid),
                "intended_ask_bid_debit": intended_ask_bid_debit,
                "intended_limit_debit": intended_ask_bid_debit,
                "executable_debit": executable_debit,
                "no_fill_reason": no_fill_reason,
                "liquidity_reason": details.get("reason"),
                "selected_spread": copy.deepcopy(selected_spread),
                "top_alternatives": copy.deepcopy(alternatives),
                "top_spread_alternatives": copy.deepcopy(alternatives),
                "candidate_execution_label": details.get("candidate_execution_label"),
                "signal_variant": details.get("signal_variant"),
                "research_only": True,
                "non_promotable": True,
                "diagnostic_label": "research_only_near_miss",
                "raw_candidates": scan_funnel.get("raw_candidates", scan_result.get("candidate_count", 0)),
                "returned_picks": scan_funnel.get("returned_picks", scan_result.get("returned_count", 0)),
                "production_filter_action": "preserve_filters_until_exact_replay_unlock",
                "next_diagnostic_action": "recheck_with_fresh_opra_quote_then_compare_spread_alternatives",
            }
        )
    records.sort(
        key=lambda record: (
            record["distance_to_current_filters"] is None,
            float(record["distance_to_current_filters"] or 999999.0),
            str(record["ticker"]),
        )
    )
    return records[: max(int(max_records), 0)]


def _append_liquidity_near_miss_records(
    records: list[dict[str, Any]],
    *,
    log_file: Path | None = None,
) -> None:
    _append_log_rows(records, log_file=log_file or (LOG_DIR / "liquidity_near_misses.jsonl"))


def _record_forward_ledger_snapshot(
    *,
    scan_result: dict[str, Any],
    repository: Any,
    reviewed_positions: list[dict[str, Any]],
    scan_date: str,
) -> dict[str, Any] | None:
    tracked_positions = None
    if getattr(repository, "is_available", False):
        try:
            tracked_positions = repository.list_positions("open")
        except Exception as exc:
            print(f"Forward ledger tracked-position snapshot unavailable: {exc}")
    playbook = _safe_dict(scan_result.get("playbook"))
    requested_cohort_ids = {
        str(playbook.get("forced_cohort_id") or "").strip(),
        *[
            str(pick.get("cohort_id") or "").strip()
            for pick in list(scan_result.get("picks") or [])
            if str(pick.get("cohort_id") or "").strip()
        ],
    }
    requested_cohort_ids = {cohort_id for cohort_id in requested_cohort_ids if cohort_id}
    scan_funnel = scan_result.get("scan_funnel")
    cohort_funnels = {
        cohort_id: scan_funnel
        for cohort_id in requested_cohort_ids
        if scan_funnel is not None
    }

    snapshot = build_forward_scan_snapshot(
        picks=list(scan_result.get("picks") or []),
        candidate_audit_picks=list(scan_result.get("candidate_audit_picks") or []),
        policy_applied=bool(scan_result.get("policy_applied")),
        policy=scan_result.get("policy"),
        policy_error=scan_result.get("policy_error"),
        playbook=scan_result.get("playbook"),
        truth_lane=scan_result.get("truth_lane"),
        scan_funnel=scan_result.get("scan_funnel"),
        policy_decision_counts=scan_result.get("policy_decision_counts"),
        guardrail_decision_counts=scan_result.get("guardrail_decision_counts"),
        candidate_count=scan_result.get("candidate_count"),
        returned_count=scan_result.get("returned_count"),
        playbook_exit_audit=scan_result.get("playbook_exit_audit"),
        playbook_exit_audit_error=scan_result.get("playbook_exit_audit_error"),
        exposure_snapshot=scan_result.get("exposure_snapshot"),
        cohort_funnels=cohort_funnels,
        cohort_ids=sorted(requested_cohort_ids),
        run_id=f"scheduled_scan:{scan_date}:{datetime.now().isoformat()}",
        run_mode="scheduled_scan",
        evidence_class="live_production",
        is_fixture=False,
        policy_artifact_id="scheduled_scan",
    )
    try:
        result = record_forward_snapshot(
            scan_snapshot=snapshot,
            reviewed_positions=reviewed_positions,
            tracked_positions=tracked_positions,
            source_label="scheduled_scan",
        )
        print(
            "Forward ledger snapshot: "
            f"session={result.get('session_id')} picks={result.get('scan_picks_count')} "
            f"eligibility={result.get('eligibility_status')}"
        )
        return result
    except Exception as exc:
        print(f"Forward ledger snapshot failed: {exc}")
        return None


def _backfill_position_scan_provenance(
    *,
    repository: Any,
    picks: list[dict[str, Any]],
    tracked_links: list[tuple[int, int]],
    ledger_result: dict[str, Any] | None,
) -> int:
    if not ledger_result or not tracked_links or not getattr(repository, "is_available", False):
        return 0
    session_id = ledger_result.get("session_id")
    run_id = ledger_result.get("run_id")
    recorded_at_utc = ledger_result.get("recorded_at_utc")
    if session_id is None or not run_id:
        return 0

    updated = 0
    for position_id, candidate_rank in tracked_links:
        if candidate_rank <= 0 or candidate_rank > len(picks):
            continue
        try:
            position = repository.get_position(int(position_id))
        except Exception:
            position = None
        if not position:
            continue

        pick = dict(picks[candidate_rank - 1])
        event_key = _scan_pick_event_key(pick, candidate_rank)
        source = _safe_dict(position.get("source_pick_snapshot"))
        source.update(
            {
                "source_scan_session_id": int(session_id),
                "source_scan_event_key": event_key,
                "source_scan_run_id": run_id,
                "source_scan_recorded_at_utc": recorded_at_utc,
            }
        )
        try:
            repository.update_position(
                int(position_id),
                {
                    "source_scan_session_id": int(session_id),
                    "source_scan_event_key": event_key,
                    "source_scan_run_id": run_id,
                    "source_scan_recorded_at_utc": recorded_at_utc,
                    "source_pick_snapshot": source,
                },
            )
            updated += 1
        except Exception as exc:
            print(f"  Scan provenance backfill failed for position {position_id}: {exc}")
    if updated:
        print(f"Scan provenance backfill: updated_positions={updated}")
    return updated


def main() -> int:
    run_at = datetime.now()
    scan_date = run_at.strftime("%Y-%m-%d")
    if _is_market_closed(run_at):
        print(f"Market closed for {scan_date}; skipping scan logging.")
        return 0

    load_local_env(ROOT)

    import market_data_service as mds
    mds._MEMORY_CACHE.clear()
    import options_chatbot as oc

    os.makedirs(LOG_DIR, exist_ok=True)

    repository = create_positions_repository(os.getenv("DATABASE_URL"))
    reviewed_positions: list[dict[str, Any]] = _review_positions_before_scan(repository)
    scan_result = run_supervised_scan(
        scan_func=oc.scan_daily_top_trades,
        positions_repository=repository,
        n_picks=10,
        watchlist_size=len(oc.DEFAULT_WATCHLIST),
        playbook_id=os.getenv("OPTIONS_SCAN_PLAYBOOK") or DEFAULT_SCAN_PLAYBOOK_ID,
        use_recommended_policy=_env_flag_enabled("OPTIONS_SCAN_USE_RECOMMENDED_POLICY", False),
        enforce_portfolio_caps=_env_flag_enabled("OPTIONS_SCAN_ENFORCE_PORTFOLIO_CAPS", False),
        truth_lane=os.getenv("OPTIONS_SCAN_TRUTH_LANE") or LIVE_SCAN_TRUTH_LANE,
        min_trades=int(os.getenv("OPTIONS_SCAN_MIN_TRADES", "20")),
    )
    if scan_result.get("policy_fail_closed"):
        print(f"Supervised scan failed closed: {scan_result.get('policy_error') or 'unknown policy error'}")
        return 1

    picks = list(scan_result.get("picks") or [])
    if not picks:
        print("No picks today.")
        _print_scan_diagnostics(scan_result)
        near_miss_records = _build_liquidity_near_miss_records(
            scan_result=scan_result,
            run_at=run_at,
        )
        _append_liquidity_near_miss_records(near_miss_records)
        if near_miss_records:
            print(f"{len(near_miss_records)} liquidity near-miss record(s) logged to {LOG_DIR / 'liquidity_near_misses.jsonl'}")
        ledger_result = _record_forward_ledger_snapshot(
            scan_result=scan_result,
            repository=repository,
            reviewed_positions=reviewed_positions,
            scan_date=scan_date,
        )
        if ledger_result is None:
            return 1
        return 0

    records = [_build_log_record(pick, run_at=run_at, scan_result=scan_result) for pick in picks]
    replaced = _replace_scan_rows(scan_date, records, log_file=LOG_FILE)
    if replaced:
        print(f"Replaced {replaced} existing log row(s) for {scan_date} before writing the current run.")

    logged = 0
    for record in records:
        logged += 1
        print(
            f"  Logged: {record['ticker']} {record['direction']} "
            f"{record['long_strike']}/{record['short_strike']} "
            f"${(record.get('net_debit') or record.get('entry_execution_price') or 0.0):.2f} exp={record['expiry']}"
        )

    print(f"\n{logged} picks logged to {LOG_FILE}")
    fill_attempt_records = [
        _build_fill_attempt_record(
            pick,
            run_at=run_at,
            scan_result=scan_result,
            candidate_rank=idx,
        )
        for idx, pick in enumerate(picks, start=1)
    ]
    near_miss_records = _build_liquidity_near_miss_records(
        scan_result=scan_result,
        run_at=run_at,
    )
    _append_liquidity_near_miss_records(near_miss_records)
    if near_miss_records:
        print(f"{len(near_miss_records)} liquidity near-miss record(s) logged to {LOG_DIR / 'liquidity_near_misses.jsonl'}")

    tracked_links: list[tuple[int, int]] = []
    auto_track_allowed = _scan_allows_auto_track(scan_result)
    repository_available = bool(getattr(repository, "is_available", False))
    if repository_available and auto_track_allowed:
        created, duplicates, skipped = _auto_track_scan_picks(
            repository=repository,
            picks=picks,
            filled_at=run_at.isoformat(),
            scan_date=scan_date,
            tracked_links=tracked_links,
        )
        print(
            f"Auto-track summary: created={created}, duplicate_open={duplicates}, skipped={skipped}"
        )
        try:
            post_track_review = list(review_open_positions(repository) or [])
            reviewed_positions.extend(post_track_review)
            expired_auto_closed = sum(
                1
                for position in post_track_review
                if position.get("status") == "closed" and position.get("exit_reason") == "expired_auto_close"
            )
            sell_auto_closed = sum(
                1
                for position in post_track_review
                if position.get("status") == "closed" and position.get("exit_reason") == "auto_sell_recommendation"
            )
            print(
                "Open position review summary: "
                f"reviewed={len(post_track_review)}, "
                f"auto_sell_closed={sell_auto_closed}, "
                f"expired_auto_closed={expired_auto_closed}"
            )
        except Exception as exc:
            print(f"Open position review failed: {exc}")
    elif repository_available:
        print("Auto-track disabled by OPTIONS_SCAN_AUTO_TRACK; position review skipped.")
    else:
        print("Tracked positions repository unavailable; auto-track skipped.")

    _annotate_fill_attempt_outcomes(
        fill_attempt_records,
        tracked_links=tracked_links,
        auto_track_allowed=auto_track_allowed,
        repository_available=repository_available,
        reviewed_positions=reviewed_positions,
    )
    _append_fill_attempt_records(fill_attempt_records)
    if fill_attempt_records:
        print(f"{len(fill_attempt_records)} fill-attempt record(s) logged to {LOG_DIR / 'fill_attempts.jsonl'}")

    ledger_result = _record_forward_ledger_snapshot(
        scan_result=scan_result,
        repository=repository,
        reviewed_positions=reviewed_positions,
        scan_date=scan_date,
    )
    if ledger_result is None:
        return 1
    _backfill_position_scan_provenance(
        repository=repository,
        picks=picks,
        tracked_links=tracked_links,
        ledger_result=ledger_result,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
