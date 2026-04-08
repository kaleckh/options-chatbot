from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

from wfo_optimizer import (
    IMPORTED_DAILY_TRUTH_SOURCE,
    _classify_trade_against_live_policy,
    build_live_options_trade_policy,
    build_playbook_exit_audit,
    load_preferred_results_by_truth_lane,
)


_ET = ZoneInfo("America/New_York")
LIVE_SCAN_TRUTH_LANE = IMPORTED_DAILY_TRUTH_SOURCE
SCAN_FUNNEL_DROP_KEYS = (
    "min_history",
    "history_or_liquidity",
    "signal_index",
    "momentum",
    "tech_score",
    "direction_score",
    "direction_filter",
    "stop_cooldown",
    "ticker_regime_filter",
    "ticker_vol_filter",
    "earnings",
    "option_liquidity",
    "iv_crush_penalty",
    "ev_floor",
    "guardrails",
    "exceptions",
)


SCAN_PLAYBOOKS: dict[str, dict[str, Any]] = {
    "short_term": {
        "id": "short_term",
        "label": "Short-Term",
        "description": "Tighter 1-2 week options holds with smaller suggested size.",
        "target_dte": 7,
        "max_new_positions_per_day": 2,
        "max_sector_open_positions": 1,
        "max_regime_open_positions": 2,
        "block_same_ticker": True,
        "calibration_playbook": "broad",
        "max_concurrent_positions": 3,
        "max_correlated_index_positions": 1,
        "daily_loss_limit_pct": 2.0,
        "weekly_loss_limit_pct": 5.0,
    },
    "swing": {
        "id": "swing",
        "label": "Swing",
        "description": "Longer 3-5 week options holds with room for fewer but fuller positions.",
        "target_dte": 21,
        "max_new_positions_per_day": 3,
        "max_sector_open_positions": 2,
        "max_regime_open_positions": 2,
        "block_same_ticker": True,
        "calibration_playbook": "broad",
        "max_concurrent_positions": 3,
        "max_correlated_index_positions": 1,
        "daily_loss_limit_pct": 2.0,
        "weekly_loss_limit_pct": 5.0,
    },
    "bullish_momentum": {
        "id": "bullish_momentum",
        "label": "Bullish Momentum",
        "description": "Bullish equity calls in confirmed bullish tape, kept separate so promotion can depend on replay-backed calibration.",
        "target_dte": 14,
        "max_new_positions_per_day": 2,
        "max_sector_open_positions": 1,
        "max_regime_open_positions": 2,
        "block_same_ticker": True,
        "allowed_asset_classes": ["equity"],
        "allowed_market_regimes": ["bullish"],
        "allowed_directions": ["call"],
        "min_quality_score": 70.0,
        "calibration_playbook": "bullish_momentum",
        "max_concurrent_positions": 3,
        "max_correlated_index_positions": 1,
        "daily_loss_limit_pct": 2.0,
        "weekly_loss_limit_pct": 5.0,
    },
    "bearish_defensive": {
        "id": "bearish_defensive",
        "label": "Bearish Defensive",
        "description": "Selective bearish puts on defensive equities when the broader market regime is already risk-off.",
        "target_dte": 14,
        "max_new_positions_per_day": 1,
        "max_sector_open_positions": 1,
        "max_regime_open_positions": 1,
        "block_same_ticker": True,
        "allowed_asset_classes": ["equity"],
        "allowed_market_regimes": ["bearish"],
        "allowed_sectors": ["Healthcare", "Consumer Defensive"],
        "allowed_directions": ["put"],
        "min_quality_score": 70.0,
        "calibration_playbook": "bearish_defensive",
        "max_concurrent_positions": 3,
        "max_correlated_index_positions": 1,
        "daily_loss_limit_pct": 2.0,
        "weekly_loss_limit_pct": 5.0,
    },
}


def get_scan_playbook(playbook_id: Optional[str]) -> dict[str, Any]:
    key = str(playbook_id or "short_term").strip().lower()
    return dict(SCAN_PLAYBOOKS.get(key) or SCAN_PLAYBOOKS["short_term"])


def scan_pick_market_regime(pick: dict[str, Any]) -> str:
    try:
        spy_ret5 = float(pick.get("spy_ret5", 0.0) or 0.0)
    except (TypeError, ValueError):
        return "unknown"
    if spy_ret5 <= -0.5:
        return "bearish"
    if spy_ret5 >= 0.5:
        return "bullish"
    return "neutral"


def _normalized_label_set(values: list[Any]) -> set[str]:
    labels: set[str] = set()
    for value in values or []:
        text = str(value or "").strip().lower()
        if text:
            labels.add(text)
    return labels


def _normalized_scan_drop_counts(value: Optional[dict[str, Any]]) -> dict[str, int]:
    payload = dict(value or {})
    normalized = {key: 0 for key in SCAN_FUNNEL_DROP_KEYS}
    for key in SCAN_FUNNEL_DROP_KEYS:
        normalized[key] = int(payload.get(key) or 0)
    return normalized


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _et_date(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=_ET)
    return value.astimezone(_ET)


def _candidate_rank_tuple(pick: dict[str, Any]) -> tuple[float, float, float, float, float, float]:
    calibrated = pick.get("calibrated_expectancy_pct")
    promotable_exact = str(pick.get("promotion_class") or "").strip().lower() == "promotable_exact_contract"
    calibrated_value = (
        float(calibrated or 0.0)
        if calibrated is not None and promotable_exact and bool(pick.get("calibration_is_dense"))
        else -9999.0
    )
    return (
        1 if promotable_exact else 0,
        1 if bool(pick.get("calibration_is_dense")) else 0,
        calibrated_value,
        float(pick.get("direction_score", 0.0) or 0.0),
        float(pick.get("quality_score", 0.0) or 0.0),
        float(pick.get("tech_score", 0.0) or 0.0),
    )


def _watch_symbol_rank(pick: dict[str, Any], policy: Optional[dict[str, Any]]) -> int:
    if not policy:
        return 0
    decision = str(
        pick.get("managed_lane_decision")
        or pick.get("trade_policy_decision")
        or "watch"
    ).strip().lower()
    if decision != "watch":
        return 0
    ticker = str(pick.get("ticker") or "").strip().upper()
    priority = {
        str(symbol or "").strip().upper()
        for symbol in policy.get("watch_priority_symbols")
        or (policy.get("scan_policy") or {}).get("watch_priority_symbols")
        or []
        if str(symbol or "").strip()
    }
    deprioritized = {
        str(symbol or "").strip().upper()
        for symbol in policy.get("watch_deprioritized_symbols")
        or (policy.get("scan_policy") or {}).get("watch_deprioritized_symbols")
        or []
        if str(symbol or "").strip()
    }
    if ticker in priority:
        return 1
    if ticker in deprioritized:
        return -1
    return 0


def _normalized_snapshot_status(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text or "unknown"


def _managed_pick_block_reason(pick: dict[str, Any], policy: Optional[dict[str, Any]]) -> Optional[str]:
    if not policy:
        return "policy_not_applied"
    if str(policy.get("truth_window_status") or "unknown").strip().lower() == "stale":
        return "truth_window_stale"
    promotion_class = str(pick.get("promotion_class") or "").strip().lower()
    if promotion_class != "promotable_exact_contract":
        return f"promotion_class:{promotion_class or 'unknown'}"
    selection_source = str(
        pick.get("selection_source")
        or pick.get("contract_selection_source")
        or ""
    ).strip().lower()
    if selection_source != "live_chain_exact_contract":
        return f"selection_source:{selection_source or 'unknown'}"
    options_snapshot_status = _normalized_snapshot_status(pick.get("options_snapshot_status"))
    if options_snapshot_status != "fresh":
        return f"options_snapshot_status:{options_snapshot_status}"
    option_chain_status = _normalized_snapshot_status(pick.get("option_chain_status"))
    if option_chain_status != "fresh":
        return f"option_chain_status:{option_chain_status}"
    if str(pick.get("guardrail_decision") or "clear").strip().lower() == "blocked":
        return "guardrail_decision:blocked"
    approved_tickers = {
        str(symbol or "").strip().upper()
        for symbol in ((policy.get("scan_policy") or {}).get("hard_filters") or {}).get("approved_tickers") or []
        if str(symbol or "").strip()
    }
    ticker = str(pick.get("ticker") or "").strip().upper()
    if approved_tickers and ticker not in approved_tickers:
        return "approved_symbol_scope"
    trade_policy_decision = str(pick.get("trade_policy_decision") or "watch").strip().lower()
    if trade_policy_decision != "approved":
        return f"trade_policy_decision:{trade_policy_decision or 'unknown'}"
    return None


def _annotate_managed_pick(pick: dict[str, Any], policy: Optional[dict[str, Any]]) -> dict[str, Any]:
    annotated = dict(pick)
    annotated["options_snapshot_status"] = _normalized_snapshot_status(
        annotated.get("options_snapshot_status")
    )
    annotated["option_chain_status"] = _normalized_snapshot_status(
        annotated.get("option_chain_status")
    )
    block_reason = _managed_pick_block_reason(annotated, policy)
    guardrail_decision = str(annotated.get("guardrail_decision") or "clear").strip().lower()
    managed_eligible = block_reason is None
    if managed_eligible:
        managed_lane_decision = "approved"
    elif guardrail_decision == "blocked":
        managed_lane_decision = "blocked"
    else:
        managed_lane_decision = "watch"
    annotated["managed_eligible"] = managed_eligible
    annotated["managed_block_reason"] = block_reason
    annotated["managed_lane_decision"] = managed_lane_decision
    return annotated


CORRELATED_INDEXES = {"SPY", "QQQ", "IWM", "DIA"}


def load_open_position_context(positions_repository: Any) -> dict[str, Any]:
    context: dict[str, Any] = {
        "available": True,
        "open_positions": 0,
        "opened_today": 0,
        "ticker_counts": {},
        "sector_counts": {},
        "regime_counts": {},
        "warnings": [],
        "daily_realized_pnl_usd": 0.0,
        "weekly_realized_pnl_usd": 0.0,
        "correlated_index_count": 0,
    }
    if not getattr(positions_repository, "is_available", False):
        context["available"] = False
        context["warnings"].append("Tracked positions storage is unavailable, so portfolio guardrails cannot see live open exposure yet.")
        return context

    try:
        open_positions = positions_repository.list_positions("open")
    except Exception as exc:
        context["available"] = False
        context["warnings"].append(f"Could not load tracked positions for guardrails: {exc}")
        return context

    ticker_counts: dict[str, int] = {}
    sector_counts: dict[str, int] = {}
    regime_counts: dict[str, int] = {}
    sector_direction_counts: dict[str, int] = {}
    opened_today = 0
    correlated_index_count = 0
    today_et = datetime.now(_ET).date()

    for position in open_positions:
        source_pick = dict(position.get("source_pick_snapshot") or {})
        ticker = str(position.get("ticker") or source_pick.get("ticker") or "").upper()
        sector = str(source_pick.get("sector") or "").strip()
        market_regime = str(source_pick.get("market_regime") or scan_pick_market_regime(source_pick)).strip().lower()
        pos_direction = str(source_pick.get("direction") or source_pick.get("type") or "").strip().lower()
        filled_at = _et_date(_parse_iso_datetime(position.get("filled_at")))

        if ticker:
            ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1
            if ticker in CORRELATED_INDEXES:
                correlated_index_count += 1
        if sector:
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
        if market_regime and market_regime != "unknown":
            regime_counts[market_regime] = regime_counts.get(market_regime, 0) + 1
        if sector and pos_direction in {"call", "put"}:
            sd_key = f"{sector}|{pos_direction}"
            sector_direction_counts[sd_key] = sector_direction_counts.get(sd_key, 0) + 1
        if filled_at and filled_at.date() == today_et:
            opened_today += 1

    # Query realized P&L for daily/weekly loss limits
    daily_realized_pnl_usd = 0.0
    weekly_realized_pnl_usd = 0.0
    try:
        now_et = datetime.now(_ET)
        today_open = now_et.replace(hour=0, minute=0, second=0, microsecond=0)
        weekday = today_open.weekday()
        monday_open = today_open if weekday == 0 else today_open.replace(day=today_open.day - weekday)
        if hasattr(positions_repository, "get_realized_pnl_since"):
            daily_realized_pnl_usd = positions_repository.get_realized_pnl_since(today_open)
            weekly_realized_pnl_usd = positions_repository.get_realized_pnl_since(monday_open)
    except Exception:
        pass

    context.update(
        {
            "open_positions": len(open_positions),
            "opened_today": opened_today,
            "ticker_counts": ticker_counts,
            "sector_counts": sector_counts,
            "regime_counts": regime_counts,
            "sector_direction_counts": sector_direction_counts,
            "daily_realized_pnl_usd": daily_realized_pnl_usd,
            "weekly_realized_pnl_usd": weekly_realized_pnl_usd,
            "correlated_index_count": correlated_index_count,
        }
    )
    return context


def annotate_pick_with_trade_policy(pick: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    annotated = dict(pick)
    scan_policy = dict(policy.get("scan_policy") or {})
    preferred_filters = dict(scan_policy.get("preferred_filters") or {})
    hard_filters = dict(scan_policy.get("hard_filters") or {})
    classified = _classify_trade_against_live_policy(annotated, scan_policy)

    ticker = str(annotated.get("ticker") or "").upper()
    sector = str(annotated.get("sector") or "").strip()
    market_regime = str(classified.get("market_regime") or scan_pick_market_regime(annotated)).strip().lower()
    asset_class = str(classified.get("asset_class") or annotated.get("asset_class") or "").strip().lower()
    direction_score = float(annotated.get("direction_score", 0.0) or 0.0)
    promotion_status = str(scan_policy.get("promotion_status") or "watch").strip().lower()

    fit_reasons: list[str] = []
    direction_score_min = hard_filters.get("direction_score_min")
    direction_score_max = hard_filters.get("direction_score_max")
    if direction_score_min is not None and direction_score < float(direction_score_min):
        fit_reasons.append(f"Direction score {direction_score:.1f} is below the replay-backed floor of {float(direction_score_min):.1f}.")
    if direction_score_max is not None and direction_score > float(direction_score_max):
        fit_reasons.append(f"Direction score {direction_score:.1f} is above the replay-backed band cap of {float(direction_score_max):.1f}.")

    preferred_asset_class = str(preferred_filters.get("asset_class") or "").strip().lower()
    if preferred_asset_class and asset_class == preferred_asset_class:
        fit_reasons.append(f"Matches preferred asset class: {preferred_asset_class}.")

    preferred_market_regimes = _normalized_label_set(preferred_filters.get("market_regimes") or [])
    if preferred_market_regimes and market_regime in preferred_market_regimes:
        fit_reasons.append(f"Matches preferred market regime: {market_regime}.")

    preferred_sectors = _normalized_label_set(preferred_filters.get("sectors") or [])
    if preferred_sectors and sector.lower() in preferred_sectors:
        fit_reasons.append(f"Matches preferred sector: {sector}.")

    highlighted_tickers = _normalized_label_set(scan_policy.get("highlighted_tickers") or [])
    if ticker.lower() in highlighted_tickers:
        fit_reasons.append(f"{ticker} stood out in the replay, but single-name hits are treated as context rather than a hard filter.")

    promotion_class = str(classified.get("promotion_class") or annotated.get("promotion_class") or "").strip().lower()
    if promotion_class == "research_nearest_listed":
        fit_reasons.insert(0, "Research-only: replay profitability for this setup depends on nearest-listed contract substitution.")
    elif promotion_class == "research_sparse_calibration":
        fit_reasons.insert(0, "Research-only: replay calibration for this setup is still sparse and cannot approve trades.")
    elif promotion_class == "research_bootstrap":
        fit_reasons.insert(0, "Research-only: replay expectancy for this setup is still heuristic rather than dense empirical calibration.")

    if classified["decision"] == "watch" and promotion_status != "promote":
        fit_reasons.insert(0, f"Replay policy is still {promotion_status}-only, so qualifying trades stay on watch until stability improves.")
    elif classified["decision"] == "watch" and not fit_reasons:
        fit_reasons.append("Passes the replay-backed hard gate, but does not match the strongest preference slices.")

    annotated["market_regime"] = market_regime
    annotated["trade_policy_decision"] = classified["decision"]
    annotated["policy_fit_score"] = classified["fit_score"]
    annotated["policy_fit_reasons"] = fit_reasons
    annotated["policy_promotion_status"] = promotion_status
    return annotated


def apply_trade_policy_to_scan(
    picks: list[dict[str, Any]],
    *,
    policy: dict[str, Any],
    include_blocked: bool = False,
) -> dict[str, Any]:
    decision_rank = {"approved": 2, "watch": 1, "blocked": 0}
    annotated = [annotate_pick_with_trade_policy(pick, policy) for pick in picks]
    counts = {"approved": 0, "watch": 0, "blocked": 0}
    for pick in annotated:
        decision = str(pick.get("trade_policy_decision") or "watch")
        counts[decision] = counts.get(decision, 0) + 1

    ranked = sorted(
        annotated,
        key=lambda pick: (
            decision_rank.get(str(pick.get("trade_policy_decision") or "watch"), 0),
            *_candidate_rank_tuple(pick),
            _watch_symbol_rank(pick, policy),
            float(pick.get("policy_fit_score", 0.0) or 0.0),
        ),
        reverse=True,
    )
    if not include_blocked:
        ranked = [pick for pick in ranked if pick.get("trade_policy_decision") != "blocked"]

    approved_picks = [pick for pick in ranked if pick.get("trade_policy_decision") == "approved"]
    watch_picks = [pick for pick in ranked if pick.get("trade_policy_decision") == "watch"]
    blocked_picks = [pick for pick in ranked if pick.get("trade_policy_decision") == "blocked"]

    return {
        "ranked_picks": ranked,
        "approved_picks": approved_picks,
        "watch_picks": watch_picks,
        "blocked_picks": blocked_picks,
        "candidate_count": len(annotated),
        "decision_counts": counts,
    }


def annotate_pick_with_guardrails(
    pick: dict[str, Any],
    *,
    playbook: dict[str, Any],
    exposure: dict[str, Any],
) -> dict[str, Any]:
    annotated = dict(pick)
    ticker = str(annotated.get("ticker") or "").upper()
    sector = str(annotated.get("sector") or "").strip()
    market_regime = str(annotated.get("market_regime") or scan_pick_market_regime(annotated)).strip().lower()
    asset_class = str(annotated.get("asset_class") or "").strip().lower()
    direction = str(annotated.get("direction") or annotated.get("type") or "").strip().lower()
    quality_score = float(annotated.get("quality_score", 0.0) or 0.0)
    opened_today = int(exposure.get("opened_today", 0) or 0)
    ticker_counts = dict(exposure.get("ticker_counts") or {})
    sector_counts = dict(exposure.get("sector_counts") or {})
    regime_counts = dict(exposure.get("regime_counts") or {})

    blocked: list[str] = []
    cautions: list[str] = []

    if not bool(exposure.get("available", True)):
        blocked.append("Portfolio guardrails failed closed because tracked-position storage is unavailable.")

    allowed_asset_classes = _normalized_label_set(playbook.get("allowed_asset_classes") or [])
    if allowed_asset_classes and asset_class not in allowed_asset_classes:
        blocked.append(f"{playbook['label']} only allows asset classes: {', '.join(sorted(allowed_asset_classes))}.")

    allowed_market_regimes = _normalized_label_set(playbook.get("allowed_market_regimes") or [])
    if allowed_market_regimes and market_regime not in allowed_market_regimes:
        blocked.append(f"{playbook['label']} only runs in {', '.join(sorted(allowed_market_regimes))} regimes.")

    allowed_sectors = _normalized_label_set(playbook.get("allowed_sectors") or [])
    if allowed_sectors and sector.lower() not in allowed_sectors:
        blocked.append(f"{playbook['label']} is restricted to sectors: {', '.join(sorted(playbook.get('allowed_sectors') or []))}.")

    allowed_directions = _normalized_label_set(playbook.get("allowed_directions") or [])
    if allowed_directions and direction not in allowed_directions:
        blocked.append(f"{playbook['label']} only allows directions: {', '.join(sorted(allowed_directions))}.")

    min_quality_score = playbook.get("min_quality_score")
    if min_quality_score is not None and quality_score < float(min_quality_score):
        blocked.append(f"Quality score {quality_score:.1f} is below the {playbook['label']} minimum of {float(min_quality_score):.1f}.")

    if playbook.get("block_same_ticker") and ticker and int(ticker_counts.get(ticker, 0) or 0) > 0:
        blocked.append(f"An open tracked position already exists in {ticker}.")

    max_new_positions_per_day = int(playbook.get("max_new_positions_per_day", 2) or 2)
    if opened_today >= max_new_positions_per_day:
        blocked.append(
            f"Playbook daily cap reached: {opened_today} new position(s) already opened today against a {max_new_positions_per_day}-position limit."
        )
    elif opened_today == max_new_positions_per_day - 1 and max_new_positions_per_day > 1:
        cautions.append("This trade would fill the last new-position slot for today in the current playbook.")

    max_sector_open_positions = int(playbook.get("max_sector_open_positions", 1) or 1)
    current_sector_count = int(sector_counts.get(sector, 0) or 0) if sector else 0
    if sector and current_sector_count >= max_sector_open_positions:
        blocked.append(f"Sector cap reached for {sector}: {current_sector_count} open position(s) against a {max_sector_open_positions}-position limit.")
    elif sector and current_sector_count == max_sector_open_positions - 1 and max_sector_open_positions > 1:
        cautions.append(f"{sector} is one trade away from the current sector cap.")

    max_regime_open_positions = int(playbook.get("max_regime_open_positions", 2) or 2)
    current_regime_count = int(regime_counts.get(market_regime, 0) or 0) if market_regime else 0
    if market_regime and market_regime != "unknown" and current_regime_count >= max_regime_open_positions:
        blocked.append(
            f"Regime cap reached for {market_regime}: {current_regime_count} open position(s) against a {max_regime_open_positions}-position limit."
        )
    elif (
        market_regime
        and market_regime != "unknown"
        and current_regime_count == max_regime_open_positions - 1
        and max_regime_open_positions > 1
    ):
        cautions.append(f"{market_regime.title()} regime exposure is near the current cap.")

    # --- Daily / weekly loss limits ---
    account_size = float(playbook.get("account_size") or 10_000)
    daily_loss_limit_pct = float(playbook.get("daily_loss_limit_pct", 2.0) or 2.0)
    weekly_loss_limit_pct = float(playbook.get("weekly_loss_limit_pct", 5.0) or 5.0)
    daily_realized_pnl = float(exposure.get("daily_realized_pnl_usd", 0.0) or 0.0)
    weekly_realized_pnl = float(exposure.get("weekly_realized_pnl_usd", 0.0) or 0.0)
    daily_limit_usd = account_size * daily_loss_limit_pct / 100.0
    weekly_limit_usd = account_size * weekly_loss_limit_pct / 100.0
    if daily_realized_pnl < 0 and abs(daily_realized_pnl) >= daily_limit_usd:
        blocked.append(f"Daily loss limit reached: ${abs(daily_realized_pnl):.2f} lost today against ${daily_limit_usd:.2f} cap ({daily_loss_limit_pct}%).")
    if weekly_realized_pnl < 0 and abs(weekly_realized_pnl) >= weekly_limit_usd:
        blocked.append(f"Weekly loss limit reached: ${abs(weekly_realized_pnl):.2f} lost this week against ${weekly_limit_usd:.2f} cap ({weekly_loss_limit_pct}%).")

    # --- Max concurrent positions ---
    max_concurrent = int(playbook.get("max_concurrent_positions", 3) or 3)
    total_open = int(exposure.get("open_positions", 0) or 0)
    if total_open >= max_concurrent:
        blocked.append(f"Max concurrent positions ({max_concurrent}) reached: {total_open} position(s) currently open.")

    # --- Correlated index positions ---
    max_correlated = int(playbook.get("max_correlated_index_positions", 1) or 1)
    correlated_count = int(exposure.get("correlated_index_count", 0) or 0)
    if ticker in CORRELATED_INDEXES and correlated_count >= max_correlated:
        blocked.append(f"Correlated index limit ({max_correlated}) reached: {correlated_count} index position(s) already open across {', '.join(sorted(CORRELATED_INDEXES))}.")

    # Correlation guard: reduce size when same sector + same direction is already concentrated
    correlation_size_mult = 1.0
    sector_direction_counts = dict(exposure.get("sector_direction_counts") or {})
    if sector and direction in {"call", "put"}:
        sd_key = f"{sector}|{direction}"
        same_sector_direction_count = int(sector_direction_counts.get(sd_key, 0) or 0)
        if same_sector_direction_count >= 2:
            correlation_size_mult = 0.5
            cautions.append(
                f"Correlated exposure: {same_sector_direction_count} open {direction}(s) already in {sector}. "
                f"Suggested size reduced by 50%."
            )
    annotated["correlation_size_mult"] = correlation_size_mult
    # Apply correlation adjustment to position size recommendation
    if correlation_size_mult < 1.0 and "position_size_mult" in annotated:
        annotated["position_size_mult"] = round(
            float(annotated.get("position_size_mult", 1.0)) * correlation_size_mult, 3
        )

    guardrail_decision = "blocked" if blocked else ("caution" if cautions else "clear")
    policy_decision = str(annotated.get("trade_policy_decision") or "watch")
    if guardrail_decision == "blocked":
        suggested_size_tier = "blocked"
        suggested_size_reason = "Do not add this trade while the current playbook guardrails are blocking it."
    elif policy_decision == "watch":
        suggested_size_tier = "starter"
        suggested_size_reason = "Watch-tier trades default to starter size until the cohort proves itself further."
    elif guardrail_decision == "caution":
        suggested_size_tier = "starter" if playbook["id"] == "short_term" else "half"
        suggested_size_reason = "Existing exposure is close to a playbook cap, so keep the new trade smaller."
    else:
        suggested_size_tier = "half" if playbook["id"] == "short_term" else "full"
        suggested_size_reason = "The trade cleared the current playbook and portfolio guardrails."

    annotated["playbook_id"] = playbook["id"]
    annotated["playbook_label"] = playbook["label"]
    annotated["guardrail_decision"] = guardrail_decision
    annotated["guardrail_reasons"] = blocked if blocked else cautions
    annotated["suggested_size_tier"] = suggested_size_tier
    annotated["suggested_size_reason"] = suggested_size_reason
    return annotated


def apply_playbook_guardrails(
    picks: list[dict[str, Any]],
    *,
    playbook: dict[str, Any],
    positions_repository: Any,
    policy: Optional[dict[str, Any]] = None,
    include_blocked: bool = False,
) -> dict[str, Any]:
    exposure = load_open_position_context(positions_repository)
    annotated = [annotate_pick_with_guardrails(pick, playbook=playbook, exposure=exposure) for pick in picks]
    counts = {"clear": 0, "caution": 0, "blocked": 0}
    for pick in annotated:
        decision = str(pick.get("guardrail_decision") or "clear")
        counts[decision] = counts.get(decision, 0) + 1

    rank = {"clear": 2, "caution": 1, "blocked": 0}
    size_rank = {"full": 3, "half": 2, "starter": 1, "blocked": 0}
    ranked = sorted(
        annotated,
        key=lambda pick: (
            rank.get(str(pick.get("guardrail_decision") or "clear"), 0),
            size_rank.get(str(pick.get("suggested_size_tier") or "starter"), 0),
            *_candidate_rank_tuple(pick),
            _watch_symbol_rank(pick, policy),
            float(pick.get("policy_fit_score", 0.0) or 0.0),
        ),
        reverse=True,
    )
    if not include_blocked:
        ranked = [pick for pick in ranked if pick.get("guardrail_decision") != "blocked"]

    exposure_snapshot = {
        "available": bool(exposure.get("available", True)),
        "open_positions": exposure["open_positions"],
        "opened_today": exposure["opened_today"],
        "ticker_counts": exposure["ticker_counts"],
        "sector_counts": exposure["sector_counts"],
        "regime_counts": exposure["regime_counts"],
        "sector_direction_counts": exposure.get("sector_direction_counts", {}),
        "warnings": exposure["warnings"],
    }

    return {
        "ranked_picks": ranked,
        "guardrail_counts": counts,
        "exposure_snapshot": exposure_snapshot,
    }


def _build_scan_funnel(
    *,
    raw_candidate_count: int,
    post_policy_visible_count: int,
    post_guardrail_visible_count: int,
    returned_count: int,
    policy_counts: Optional[dict[str, Any]] = None,
    guardrail_counts: Optional[dict[str, Any]] = None,
    policy_applied: bool,
    policy_fail_closed: bool,
    include_blocked_policy_picks: bool,
    include_blocked_guardrail_picks: bool,
    drop_counts: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    normalized_policy_counts = {
        "approved": int((policy_counts or {}).get("approved") or 0),
        "watch": int((policy_counts or {}).get("watch") or 0),
        "blocked": int((policy_counts or {}).get("blocked") or 0),
    }
    normalized_guardrail_counts = {
        "clear": int((guardrail_counts or {}).get("clear") or 0),
        "caution": int((guardrail_counts or {}).get("caution") or 0),
        "blocked": int((guardrail_counts or {}).get("blocked") or 0),
    }
    raw_candidates = max(int(raw_candidate_count or 0), 0)
    post_policy_visible = max(int(post_policy_visible_count or 0), 0)
    post_guardrails_visible = max(int(post_guardrail_visible_count or 0), 0)
    returned_picks = max(int(returned_count or 0), 0)
    normalized_drop_counts = _normalized_scan_drop_counts(drop_counts)
    normalized_drop_counts["guardrails"] += max(post_policy_visible - post_guardrails_visible, 0)
    return {
        "raw_candidates": raw_candidates,
        "post_policy_visible": post_policy_visible,
        "post_guardrails_visible": post_guardrails_visible,
        "returned_picks": returned_picks,
        "policy_filtered_out": max(raw_candidates - post_policy_visible, 0),
        "guardrail_filtered_out": max(post_policy_visible - post_guardrails_visible, 0),
        "final_trimmed": max(post_guardrails_visible - returned_picks, 0),
        "policy_counts": normalized_policy_counts,
        "guardrail_counts": normalized_guardrail_counts,
        "policy_applied": bool(policy_applied),
        "policy_fail_closed": bool(policy_fail_closed),
        "include_blocked_policy_picks": bool(include_blocked_policy_picks),
        "include_blocked_guardrail_picks": bool(include_blocked_guardrail_picks),
        "drop_counts": normalized_drop_counts,
    }


def run_supervised_scan(
    *,
    scan_func: Callable[..., list[dict[str, Any]]],
    positions_repository: Any,
    n_picks: int,
    watchlist_size: int,
    playbook_id: Optional[str] = None,
    use_recommended_policy: bool = False,
    include_blocked_policy_picks: bool = False,
    include_blocked_guardrail_picks: bool = False,
    truth_lane: Optional[str] = None,
    min_trades: int = 20,
    max_tickers: int = 8,
    max_sectors: int = 8,
    min_profit_factor: float = 1.05,
    min_directional_accuracy_pct: float = 50.0,
) -> dict[str, Any]:
    playbook = get_scan_playbook(playbook_id)
    scan_dte = int(playbook["target_dte"])
    scan_pool_size = max(int(n_picks), int(watchlist_size))
    raw_picks = list(
        scan_func(
            n_picks=scan_pool_size,
            dte=scan_dte,
            calibration_playbook=str(playbook.get("calibration_playbook") or "broad"),
            positions_repository=positions_repository,
        )
    )
    scan_drop_counts = _normalized_scan_drop_counts(getattr(scan_func, "_last_scan_drop_counts", None))
    candidate_count = len(raw_picks)

    policy = None
    policy_error = None
    policy_result = None
    ranked_for_guardrails = list(raw_picks)
    exit_audit = None
    exit_audit_error = None

    if use_recommended_policy:
        preferred_result = load_preferred_results_by_truth_lane(truth_lane or LIVE_SCAN_TRUTH_LANE)
        policy = build_live_options_trade_policy(
            result=preferred_result,
            truth_lane=truth_lane or LIVE_SCAN_TRUTH_LANE,
            min_trades=int(min_trades),
            max_tickers=int(max_tickers),
            max_sectors=int(max_sectors),
            min_profit_factor=float(min_profit_factor),
            min_directional_accuracy_pct=float(min_directional_accuracy_pct),
        )
        exit_audit = build_playbook_exit_audit(
            result=preferred_result,
            policy_bundle=policy,
            playbook=str(playbook.get("id") or "short_term"),
            truth_lane=truth_lane or LIVE_SCAN_TRUTH_LANE,
            min_trades=int(min_trades),
            max_tickers=int(max_tickers),
            max_sectors=int(max_sectors),
            min_profit_factor=float(min_profit_factor),
            min_directional_accuracy_pct=float(min_directional_accuracy_pct),
        )
        if exit_audit.get("error"):
            exit_audit_error = exit_audit.get("error")
            exit_audit = None
            scan_funnel = _build_scan_funnel(
                raw_candidate_count=candidate_count,
                post_policy_visible_count=0,
                post_guardrail_visible_count=0,
                returned_count=0,
                policy_counts={"approved": 0, "watch": 0, "blocked": candidate_count},
                guardrail_counts={"clear": 0, "caution": 0, "blocked": 0},
                policy_applied=False,
                policy_fail_closed=True,
                include_blocked_policy_picks=include_blocked_policy_picks,
                include_blocked_guardrail_picks=include_blocked_guardrail_picks,
                drop_counts=scan_drop_counts,
            )
            return {
                "picks": [],
                "watch_picks": [],
                "ranked_picks": [],
                "policy_applied": False,
                "policy_error": str(exit_audit_error),
                "policy_fail_closed": True,
                "policy": None,
                "playbook_exit_audit": None,
                "playbook_exit_audit_error": exit_audit_error,
                "policy_decision_counts": {"approved": 0, "watch": 0, "blocked": 0},
                "guardrail_decision_counts": {"clear": 0, "caution": 0, "blocked": 0},
                "exposure_snapshot": load_open_position_context(positions_repository),
                "candidate_count": candidate_count,
                "returned_count": 0,
                "scan_funnel": scan_funnel,
                "playbook": playbook,
                "playbooks": list(SCAN_PLAYBOOKS.values()),
                "truth_lane": truth_lane or LIVE_SCAN_TRUTH_LANE,
                "truth_window_status": "unknown",
                "managed_lane_status": None,
                "authoritative_evidence_source": None,
                "authoritative_evidence_status": None,
                "watch_priority_symbols": [],
                "watch_deprioritized_symbols": [],
            }
        if policy.get("error"):
            policy_error = str(policy.get("error"))
            scan_funnel = _build_scan_funnel(
                raw_candidate_count=candidate_count,
                post_policy_visible_count=0,
                post_guardrail_visible_count=0,
                returned_count=0,
                policy_counts={"approved": 0, "watch": 0, "blocked": candidate_count},
                guardrail_counts={"clear": 0, "caution": 0, "blocked": 0},
                policy_applied=False,
                policy_fail_closed=True,
                include_blocked_policy_picks=include_blocked_policy_picks,
                include_blocked_guardrail_picks=include_blocked_guardrail_picks,
                drop_counts=scan_drop_counts,
            )
            return {
                "picks": [],
                "watch_picks": [],
                "ranked_picks": [],
                "policy_applied": False,
                "policy_error": policy_error,
                "policy_fail_closed": True,
                "policy": None,
                "playbook_exit_audit": exit_audit,
                "playbook_exit_audit_error": exit_audit_error,
                "policy_decision_counts": {"approved": 0, "watch": 0, "blocked": 0},
                "guardrail_decision_counts": {"clear": 0, "caution": 0, "blocked": 0},
                "exposure_snapshot": load_open_position_context(positions_repository),
                "candidate_count": candidate_count,
                "returned_count": 0,
                "scan_funnel": scan_funnel,
                "playbook": playbook,
                "playbooks": list(SCAN_PLAYBOOKS.values()),
                "truth_lane": truth_lane or LIVE_SCAN_TRUTH_LANE,
                "truth_window_status": "unknown",
                "managed_lane_status": None,
                "authoritative_evidence_source": None,
                "authoritative_evidence_status": None,
                "watch_priority_symbols": [],
                "watch_deprioritized_symbols": [],
            }

        policy_result = apply_trade_policy_to_scan(
            raw_picks,
            policy=policy,
            include_blocked=include_blocked_policy_picks,
        )
        ranked_for_guardrails = list(policy_result["ranked_picks"])

    guardrail_result = apply_playbook_guardrails(
        ranked_for_guardrails,
        playbook=playbook,
        positions_repository=positions_repository,
        policy=policy,
        include_blocked=include_blocked_guardrail_picks,
    )
    ranked_picks = list(guardrail_result["ranked_picks"])
    truth_window_status = str((policy or {}).get("truth_window_status") or "unknown").strip().lower() or "unknown"
    managed_lane_status = (policy or {}).get("managed_lane_status")
    authoritative_evidence_source = (policy or {}).get("authoritative_evidence_source")
    authoritative_evidence_status = (policy or {}).get("authoritative_evidence_status")
    watch_priority_symbols = list((policy or {}).get("watch_priority_symbols") or [])
    watch_deprioritized_symbols = list((policy or {}).get("watch_deprioritized_symbols") or [])

    if use_recommended_policy and policy is not None:
        ranked_picks = [_annotate_managed_pick(pick, policy) for pick in ranked_picks]
        approved_picks = [
            pick for pick in ranked_picks
            if pick.get("managed_lane_decision") == "approved"
        ][: max(int(n_picks), 0)]
        watch_picks = sorted(
            [
                pick for pick in ranked_picks
                if pick.get("managed_lane_decision") == "watch"
            ],
            key=lambda pick: (
                _watch_symbol_rank(pick, policy),
                *_candidate_rank_tuple(pick),
                float(pick.get("policy_fit_score", 0.0) or 0.0),
            ),
            reverse=True,
        )
        final_picks = approved_picks
    else:
        ranked_picks = [_annotate_managed_pick(pick, None) for pick in ranked_picks]
        final_picks = ranked_picks[: max(int(n_picks), 0)]
        watch_picks = []
    scan_funnel = _build_scan_funnel(
        raw_candidate_count=candidate_count,
        post_policy_visible_count=len(ranked_for_guardrails),
        post_guardrail_visible_count=len(ranked_picks),
        returned_count=len(final_picks),
        policy_counts=(policy_result or {}).get("decision_counts"),
        guardrail_counts=guardrail_result["guardrail_counts"],
        policy_applied=bool(use_recommended_policy and policy is not None),
        policy_fail_closed=False,
        include_blocked_policy_picks=include_blocked_policy_picks,
        include_blocked_guardrail_picks=include_blocked_guardrail_picks,
        drop_counts=scan_drop_counts,
    )

    return {
        "picks": final_picks,
        "watch_picks": watch_picks,
        "ranked_picks": ranked_picks,
        "policy_applied": bool(use_recommended_policy and policy is not None),
        "policy_error": policy_error,
        "policy_fail_closed": False,
        "policy": policy,
        "playbook_exit_audit": exit_audit,
        "playbook_exit_audit_error": exit_audit_error,
        "policy_decision_counts": (policy_result or {}).get("decision_counts"),
        "guardrail_decision_counts": guardrail_result["guardrail_counts"],
        "exposure_snapshot": guardrail_result["exposure_snapshot"],
        "candidate_count": candidate_count,
        "returned_count": len(final_picks),
        "scan_funnel": scan_funnel,
        "playbook": playbook,
        "playbooks": list(SCAN_PLAYBOOKS.values()),
        "truth_lane": truth_lane or LIVE_SCAN_TRUTH_LANE,
        "truth_window_status": truth_window_status,
        "managed_lane_status": managed_lane_status,
        "authoritative_evidence_source": authoritative_evidence_source,
        "authoritative_evidence_status": authoritative_evidence_status,
        "watch_priority_symbols": watch_priority_symbols,
        "watch_deprioritized_symbols": watch_deprioritized_symbols,
    }
