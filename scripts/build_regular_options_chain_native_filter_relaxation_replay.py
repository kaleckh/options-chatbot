from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import wfo_optimizer as wfo

from scripts import audit_zero_pick_days_current_main_lane as single_lane_audit


REPORT_ID = "regular_options_chain_native_filter_relaxation_replay"

DEFAULT_EXACT_CANDIDATE_REPAIR = (
    ROOT / "data" / "forward-tracking" / "regular_options_exact_candidate_selection_repair_latest.json"
)
DEFAULT_ZERO_PICK_AUDIT = ROOT / "data" / "forward-tracking" / "all_lanes_zero_pick_current_algo_audit_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-chain-native-filter-relaxation-replay.md"

PROHIBITED_ACTIONS = (
    "do_not_create_live_row_from_chain_native_filter_relaxation_replay",
    "do_not_submit_broker_order_from_chain_native_filter_relaxation_replay",
    "do_not_mutate_database_from_chain_native_filter_relaxation_replay",
    "do_not_change_scanner_policy_from_chain_native_filter_relaxation_replay",
    "do_not_change_contract_selection_policy_from_chain_native_filter_relaxation_replay",
    "do_not_change_lane_promotion_from_chain_native_filter_relaxation_replay",
    "do_not_change_stop_policy_from_chain_native_filter_relaxation_replay",
    "do_not_change_sizing_from_chain_native_filter_relaxation_replay",
    "do_not_lower_exact_opra_nbbo_proof_bar_from_chain_native_filter_relaxation_replay",
    "do_not_synthesize_pnl_from_relaxed_entry_candidates",
)

SCENARIOS: tuple[dict[str, Any], ...] = (
    {
        "scenario_id": "current_chain_native_filters",
        "description": "Current lane chain-native entry filters.",
        "relaxed_filter_names": [],
        "overrides": {},
    },
    {
        "scenario_id": "relax_debit_cap_only",
        "description": "Remove only the debit-percent-of-width cap.",
        "relaxed_filter_names": ["max_debit_pct_of_width"],
        "overrides": {"max_debit_pct_of_width": None},
    },
    {
        "scenario_id": "relax_width_cap_only",
        "description": "Widen only the max spread-width percent cap.",
        "relaxed_filter_names": ["spread_max_width_pct"],
        "overrides": {"spread_max_width_pct": 20.0},
    },
    {
        "scenario_id": "widen_dte_window_only",
        "description": "Widen only the entry DTE search window.",
        "relaxed_filter_names": ["chain_native_min_dte", "chain_native_max_dte"],
        "overrides": {"chain_native_min_dte": 1, "chain_native_max_dte": 90},
    },
    {
        "scenario_id": "relax_prior_quote_continuity_only",
        "description": "Remove prior quote-continuity requirements only.",
        "relaxed_filter_names": [
            "chain_native_min_prior_quote_days",
            "chain_native_min_long_prior_quote_days",
            "chain_native_min_short_prior_quote_days",
        ],
        "overrides": {
            "chain_native_min_prior_quote_days": 0,
            "chain_native_min_long_prior_quote_days": 0,
            "chain_native_min_short_prior_quote_days": 0,
        },
    },
    {
        "scenario_id": "relax_entry_liquidity_caps_only",
        "description": "Remove entry-leg bid/ask and short-bid caps only.",
        "relaxed_filter_names": ["chain_native_max_entry_leg_bid_ask_pct", "chain_native_min_entry_short_bid"],
        "overrides": {"chain_native_max_entry_leg_bid_ask_pct": None, "chain_native_min_entry_short_bid": None},
    },
    {
        "scenario_id": "combined_broad_entry_relaxation",
        "description": "Broad diagnostic relaxation of debit, width, DTE, prior continuity, and entry-liquidity caps.",
        "relaxed_filter_names": [
            "max_debit_pct_of_width",
            "spread_max_width_pct",
            "chain_native_min_dte",
            "chain_native_max_dte",
            "chain_native_min_prior_quote_days",
            "chain_native_min_long_prior_quote_days",
            "chain_native_min_short_prior_quote_days",
            "chain_native_max_entry_leg_bid_ask_pct",
            "chain_native_min_entry_short_bid",
        ],
        "overrides": {
            "max_debit_pct_of_width": None,
            "spread_max_width_pct": 20.0,
            "chain_native_min_dte": 1,
            "chain_native_max_dte": 90,
            "chain_native_min_prior_quote_days": 0,
            "chain_native_min_long_prior_quote_days": 0,
            "chain_native_min_short_prior_quote_days": 0,
            "chain_native_max_entry_leg_bid_ask_pct": None,
            "chain_native_min_entry_short_bid": None,
        },
    },
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


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _target_rows(exact_candidate_repair: dict[str, Any]) -> list[dict[str, Any]]:
    if exact_candidate_repair.get("status") != "exact_candidate_selection_repair_readback":
        return []
    rows = []
    for row in _as_list(exact_candidate_repair.get("repair_targets")):
        row = _as_dict(row)
        if row.get("next_action") != "build_chain_native_filter_relaxation_replay":
            continue
        target_id = _norm(row.get("target_id")) or f"{_norm(row.get('lane'))}:{_norm(row.get('scan_date'))}"
        rows.append(
            {
                "target_id": target_id,
                "lane": _norm(row.get("lane")),
                "scan_date": _norm(row.get("scan_date")),
                "signal_candidate_count_before": _safe_int(row.get("signal_candidate_count")),
                "exact_candidate_count_before": _safe_int(row.get("exact_candidate_count")),
                "would_track_pick_count_before": _safe_int(row.get("would_track_pick_count")),
                "top_signal_tickers": [_norm(item).upper() for item in _as_list(row.get("top_signal_tickers")) if _norm(item)],
                "primary_reject_reason": _norm(row.get("primary_repair_reason"))
                or "no_chain_native_spread_passed_current_filters",
                "source_exact_reject_reasons": _as_dict(row.get("exact_reject_reasons")),
            }
        )
    rows.sort(key=lambda item: (_norm(item.get("lane")), _norm(item.get("scan_date"))))
    return rows


def _zero_pick_lane_params(zero_pick_audit: dict[str, Any], lane: str) -> dict[str, Any]:
    for row in _as_list(zero_pick_audit.get("lanes")):
        row = _as_dict(row)
        if _norm(row.get("playbook")) == lane:
            return _as_dict(row.get("parameters"))
    return {}


def _scenario_params(engine: single_lane_audit.CurrentMainLaneReplay, candidate: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    p_config = dict(candidate.get("_p_config") or engine._ticker_cfg(_norm(candidate.get("ticker")))[0])
    dte_at_entry = int(p_config.get("dte_at_entry") or engine.replay_playbook.get("target_dte") or 35)
    params = {
        "long_delta_target": float(p_config.get("spread_long_delta", 0.50)),
        "short_delta_target": float(p_config.get("spread_short_delta", 0.20)),
        "target_dte": dte_at_entry,
        "chain_native_min_dte": int(p_config.get("chain_native_min_dte") or max(1, dte_at_entry - 7)),
        "chain_native_max_dte": int(p_config.get("chain_native_max_dte") or dte_at_entry + 10),
        "spread_max_width_pct": float(p_config.get("spread_max_width_pct", 5.0)),
        "max_debit_pct_of_width": engine.replay_playbook.get("max_debit_pct_of_width"),
        "entry_slippage_pct": float(p_config.get("entry_slippage_pct", 0.0) or 0.0),
        "chain_native_min_prior_quote_days": int(p_config.get("chain_native_min_prior_quote_days", 0) or 0),
        "chain_native_min_long_prior_quote_days": p_config.get("chain_native_min_long_prior_quote_days"),
        "chain_native_min_short_prior_quote_days": p_config.get("chain_native_min_short_prior_quote_days"),
        "chain_native_prior_quote_lookback_days": int(p_config.get("chain_native_prior_quote_lookback_days", 14) or 14),
        "chain_native_prior_quote_score_weight": float(p_config.get("chain_native_prior_quote_score_weight", 0.0) or 0.0),
        "chain_native_long_prior_quote_score_weight": p_config.get("chain_native_long_prior_quote_score_weight"),
        "chain_native_short_prior_quote_score_weight": p_config.get("chain_native_short_prior_quote_score_weight"),
        "chain_native_prior_quote_score_cap": int(p_config.get("chain_native_prior_quote_score_cap", 0) or 0),
        "chain_native_max_entry_leg_bid_ask_pct": p_config.get("chain_native_max_entry_leg_bid_ask_pct"),
        "chain_native_min_entry_short_bid": p_config.get("chain_native_min_entry_short_bid"),
        "chain_native_short_inside_steps": int(p_config.get("chain_native_short_inside_steps", 0) or 0),
        "chain_native_short_inside_require_debit_cap": bool(
            p_config.get("chain_native_short_inside_require_debit_cap", True)
        ),
    }
    for key, value in _as_dict(scenario.get("overrides")).items():
        params[key] = value
    return params


def _positive_bid_ask(quote: Any) -> bool:
    bid = _safe_float(getattr(quote, "bid", None))
    ask = _safe_float(getattr(quote, "ask", None))
    return bid is not None and ask is not None and bid > 0 and ask > 0 and ask >= bid


def _entry_contract_coverage(
    *,
    engine: single_lane_audit.CurrentMainLaneReplay,
    candidate: dict[str, Any],
    params: dict[str, Any],
) -> dict[str, Any]:
    entry_date = date.fromisoformat(_norm(candidate.get("date"))[:10])
    min_expiry = entry_date + timedelta(days=max(int(params["chain_native_min_dte"]), 1))
    max_expiry = entry_date + timedelta(
        days=max(int(params["chain_native_max_dte"]), int(params["chain_native_min_dte"]))
    )
    quotes = engine.store.list_entry_contracts(
        underlying=_norm(candidate.get("ticker")).upper(),
        trade_date_et=entry_date,
        option_type=_norm(candidate.get("trade_type") or "call"),
        earliest_minute_et=engine.entry_quote_minute_et,
        window_minutes=engine.entry_window_minutes,
        snapshot_kind=engine.snapshot_kind,
        allow_last_price=False,
        min_expiry=min_expiry,
        max_expiry=max_expiry,
        source_labels=engine.source_labels,
        trusted_only=engine.trusted_only,
    )
    reject_reasons: Counter[str] = Counter()
    valid_quotes = []
    expiries: Counter[str] = Counter()
    for quote in quotes:
        expiries[_norm(getattr(quote, "expiry", ""))[:10]] += 1
        if _positive_bid_ask(quote):
            valid_quotes.append(quote)
        else:
            reject_reasons["non_executable_or_missing_entry_bid_ask"] += 1
    return {
        "entry_contract_quote_count": len(quotes),
        "valid_entry_contract_quote_count": len(valid_quotes),
        "entry_contract_reject_reasons": dict(sorted(reject_reasons.items())),
        "expiry_count": len(expiries),
        "top_expiries": [
            {"expiry": expiry, "contract_count": count} for expiry, count in expiries.most_common(5)
        ],
        "min_expiry": min_expiry.isoformat(),
        "max_expiry": max_expiry.isoformat(),
    }


def _select_for_scenario(
    *,
    engine: single_lane_audit.CurrentMainLaneReplay,
    candidate: dict[str, Any],
    scenario: dict[str, Any],
) -> dict[str, Any]:
    params = _scenario_params(engine, candidate, scenario)
    coverage = _entry_contract_coverage(engine=engine, candidate=candidate, params=params)
    row = {
        "ticker": _norm(candidate.get("ticker")).upper(),
        "scan_date": _norm(candidate.get("date"))[:10],
        "trade_type": _norm(candidate.get("trade_type") or "call"),
        "scenario_id": scenario["scenario_id"],
        "scenario_description": scenario["description"],
        "relaxed_filter_names": list(scenario.get("relaxed_filter_names") or []),
        "filter_thresholds": {
            "max_debit_pct_of_width": params.get("max_debit_pct_of_width"),
            "spread_max_width_pct": params.get("spread_max_width_pct"),
            "chain_native_min_dte": params.get("chain_native_min_dte"),
            "chain_native_max_dte": params.get("chain_native_max_dte"),
            "chain_native_min_prior_quote_days": params.get("chain_native_min_prior_quote_days"),
            "chain_native_min_long_prior_quote_days": params.get("chain_native_min_long_prior_quote_days"),
            "chain_native_min_short_prior_quote_days": params.get("chain_native_min_short_prior_quote_days"),
            "chain_native_max_entry_leg_bid_ask_pct": params.get("chain_native_max_entry_leg_bid_ask_pct"),
            "chain_native_min_entry_short_bid": params.get("chain_native_min_entry_short_bid"),
        },
        "candidate_contracts_available": coverage["entry_contract_quote_count"] > 0,
        "exact_bid_ask_available": coverage["valid_entry_contract_quote_count"] > 0,
        "entry_contract_quote_count": coverage["entry_contract_quote_count"],
        "valid_entry_contract_quote_count": coverage["valid_entry_contract_quote_count"],
        "entry_contract_quote_coverage": coverage,
        "exact_chain_native_spread_count": 0,
        "requires_exact_opra_nbbo_for_pnl": True,
        "production_proof": False,
        "promotion_ready": False,
    }
    if coverage["entry_contract_quote_count"] <= 0:
        row["status"] = "no_entry_contract_quotes"
        row["reject_reason"] = "trusted_entry_contract_quote_coverage_missing"
        return row
    if coverage["valid_entry_contract_quote_count"] <= 0:
        row["status"] = "no_executable_entry_bid_ask_quotes"
        row["reject_reason"] = "trusted_executable_entry_bid_ask_missing"
        return row

    entry_date = date.fromisoformat(_norm(candidate.get("date"))[:10])
    result = wfo._select_chain_native_spread(
        store=engine.store,
        ticker=_norm(candidate.get("ticker")).upper(),
        entry_date=entry_date,
        trade_type=_norm(candidate.get("trade_type") or "call"),
        S0=float(candidate["underlying_price_at_selection"]),
        hv30=float(candidate.get("hv30") or 0.0),
        long_delta_target=float(params["long_delta_target"]),
        short_delta_target=float(params["short_delta_target"]),
        target_dte=int(params["target_dte"]),
        min_dte=int(params["chain_native_min_dte"]),
        max_dte=int(params["chain_native_max_dte"]),
        max_width_pct=float(params["spread_max_width_pct"]),
        max_debit_pct_of_width=params.get("max_debit_pct_of_width"),
        iv_adj=1.20,
        requested_pricing_lane=wfo._normalize_requested_pricing_lane(engine.pricing_lane),
        entry_slippage_pct=float(params["entry_slippage_pct"] or 0.0),
        snapshot_kind=engine.snapshot_kind,
        entry_quote_minute_et=engine.entry_quote_minute_et,
        entry_window_minutes=engine.entry_window_minutes,
        source_labels=engine.source_labels,
        trusted_only=engine.trusted_only,
        min_prior_quote_days=int(params["chain_native_min_prior_quote_days"] or 0),
        prior_quote_lookback_days=int(params["chain_native_prior_quote_lookback_days"] or 14),
        min_long_prior_quote_days=params.get("chain_native_min_long_prior_quote_days"),
        min_short_prior_quote_days=params.get("chain_native_min_short_prior_quote_days"),
        prior_quote_score_weight=float(params["chain_native_prior_quote_score_weight"] or 0.0),
        long_prior_quote_score_weight=params.get("chain_native_long_prior_quote_score_weight"),
        short_prior_quote_score_weight=params.get("chain_native_short_prior_quote_score_weight"),
        prior_quote_score_cap=int(params["chain_native_prior_quote_score_cap"] or 0),
        max_entry_leg_bid_ask_pct=params.get("chain_native_max_entry_leg_bid_ask_pct"),
        min_entry_short_bid=params.get("chain_native_min_entry_short_bid"),
        short_inside_steps=int(params["chain_native_short_inside_steps"] or 0),
        short_inside_require_debit_cap=bool(params["chain_native_short_inside_require_debit_cap"]),
        include_diagnostics=True,
    )
    if isinstance(result, dict) and result.get("diagnostics"):
        diagnostics = _as_dict(result.get("diagnostics"))
        row["status"] = "selected_chain_native_entry_spread"
        row["reject_reason"] = None
        row["exact_chain_native_spread_count"] = 1
        row["selected_spread"] = diagnostics.get("selected_spread")
        row["top_spread_alternatives"] = _as_list(diagnostics.get("top_spread_alternatives"))
        row["entry_spread_mid_debit"] = diagnostics.get("entry_spread_mid_debit")
        row["entry_spread_ask_bid_debit"] = diagnostics.get("entry_spread_ask_bid_debit")
        row["fill_degradation_vs_mid_pct"] = diagnostics.get("fill_degradation_vs_mid_pct")
        return row
    row["status"] = "no_viable_chain_native_spread"
    row["reject_reason"] = "no_chain_native_spread_after_relaxation_scenario"
    return row


def _signal_snapshot(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticker": _norm(candidate.get("ticker")).upper(),
        "scan_date": _norm(candidate.get("date"))[:10],
        "trade_type": _norm(candidate.get("trade_type") or candidate.get("direction")),
        "signal_family": candidate.get("signal_family"),
        "signal_variant": candidate.get("signal_variant"),
        "underlying_price_at_selection": candidate.get("underlying_price_at_selection"),
        "entry_anchor_source": candidate.get("entry_anchor_source"),
        "hv30": candidate.get("hv30"),
        "iv_pct": candidate.get("iv_pct"),
        "direction_score": candidate.get("direction_score"),
        "quality_score": candidate.get("quality_score"),
        "tech_score": candidate.get("tech_score"),
        "ev_pct": candidate.get("ev_pct"),
        "market_regime": candidate.get("market_regime"),
        "sector": candidate.get("sector"),
    }


def _engine_for_target(
    *,
    target: dict[str, Any],
    zero_pick_audit: dict[str, Any],
    cache: dict[tuple[Any, ...], single_lane_audit.CurrentMainLaneReplay],
) -> single_lane_audit.CurrentMainLaneReplay:
    params = _zero_pick_lane_params(zero_pick_audit, _norm(target.get("lane")))
    source_labels = [
        _norm(item)
        for item in _as_list(params.get("source_labels") or ["thetadata_opra_nbbo_1m"])
        if _norm(item)
    ]
    key = (
        _norm(target.get("lane")),
        _norm(params.get("truth_lane") or wfo.IMPORTED_TRUTH_SOURCE),
        _norm(params.get("pricing_lane") or "pessimistic"),
        tuple(source_labels),
        bool(params.get("trusted_only", True)),
        int(params.get("lookback_years") or 2),
    )
    if key not in cache:
        engine = single_lane_audit.CurrentMainLaneReplay(
            playbook_id=key[0],
            truth_lane=key[1],
            pricing_lane=key[2],
            source_labels=list(key[3]),
            trusted_only=bool(key[4]),
            lookback_years=int(key[5]),
            audit_id=REPORT_ID,
        )
        engine.load()
        cache[key] = engine
    return cache[key]


def _run_target_replays(targets: list[dict[str, Any]], zero_pick_audit: dict[str, Any]) -> list[dict[str, Any]]:
    engine_cache: dict[tuple[Any, ...], single_lane_audit.CurrentMainLaneReplay] = {}
    results: list[dict[str, Any]] = []
    for target in targets:
        target_result = {
            **target,
            "replay_status": "not_run",
            "signal_rows": [],
            "scenario_rows": [],
            "scenario_counts": {},
            "entry_quote_demands": [],
        }
        try:
            engine = _engine_for_target(target=target, zero_pick_audit=zero_pick_audit, cache=engine_cache)
            target_date = date.fromisoformat(_norm(target.get("scan_date"))[:10])
            signal_candidates, signal_rejects = engine.signal_candidates_for_date(target_date)
        except Exception as exc:
            target_result["replay_status"] = "blocked_replay_unavailable"
            target_result["error_type"] = type(exc).__name__
            target_result["error"] = str(exc)
            results.append(target_result)
            continue

        tickers = {_norm(ticker).upper() for ticker in _as_list(target.get("top_signal_tickers")) if _norm(ticker)}
        scoped_candidates = [
            candidate
            for candidate in signal_candidates
            if not tickers or _norm(candidate.get("ticker")).upper() in tickers
        ]
        target_result["replay_status"] = "replayed"
        target_result["replay_signal_candidate_count"] = len(scoped_candidates)
        target_result["replay_signal_reject_reason_counts"] = dict(
            Counter(_norm(item.get("reason")) or "unknown" for item in signal_rejects)
        )
        target_result["signal_rows"] = [_signal_snapshot(candidate) for candidate in scoped_candidates]
        scenario_rows: list[dict[str, Any]] = []
        for candidate in scoped_candidates:
            for scenario in SCENARIOS:
                scenario_rows.append(_select_for_scenario(engine=engine, candidate=candidate, scenario=scenario))
        target_result["scenario_rows"] = scenario_rows
        scenario_counts: dict[str, dict[str, Any]] = {}
        for scenario in SCENARIOS:
            rows = [row for row in scenario_rows if row.get("scenario_id") == scenario["scenario_id"]]
            scenario_counts[scenario["scenario_id"]] = {
                "signal_count": len(rows),
                "selected_chain_native_entry_spread_count": sum(
                    1 for row in rows if row.get("status") == "selected_chain_native_entry_spread"
                ),
                "no_entry_contract_quote_count": sum(1 for row in rows if row.get("status") == "no_entry_contract_quotes"),
                "no_executable_entry_bid_ask_quote_count": sum(
                    1 for row in rows if row.get("status") == "no_executable_entry_bid_ask_quotes"
                ),
                "no_viable_chain_native_spread_count": sum(
                    1 for row in rows if row.get("status") == "no_viable_chain_native_spread"
                ),
            }
        target_result["scenario_counts"] = scenario_counts
        broad_rows = [row for row in scenario_rows if row.get("scenario_id") == "combined_broad_entry_relaxation"]
        demands = []
        for row in broad_rows:
            if row.get("status") not in {"no_entry_contract_quotes", "no_executable_entry_bid_ask_quotes"}:
                continue
            coverage = _as_dict(row.get("entry_contract_quote_coverage"))
            demands.append(
                {
                    "target_id": target.get("target_id"),
                    "lane": target.get("lane"),
                    "scan_date": target.get("scan_date"),
                    "ticker": row.get("ticker"),
                    "option_type": row.get("trade_type"),
                    "quote_date": target.get("scan_date"),
                    "entry_quote_minute_et": engine.entry_quote_minute_et,
                    "entry_window_minutes": engine.entry_window_minutes,
                    "snapshot_kind": engine.snapshot_kind,
                    "source_labels": engine.source_labels,
                    "trusted_only": engine.trusted_only,
                    "min_expiry": coverage.get("min_expiry"),
                    "max_expiry": coverage.get("max_expiry"),
                    "missing_reason": row.get("reject_reason"),
                }
            )
        target_result["entry_quote_demands"] = demands
        results.append(target_result)
    return results


def _summarize_results(targets: list[dict[str, Any]], target_results: list[dict[str, Any]]) -> dict[str, Any]:
    all_scenario_rows = [
        row for target in target_results for row in _as_list(target.get("scenario_rows"))
    ]
    current_rows = [row for row in all_scenario_rows if row.get("scenario_id") == "current_chain_native_filters"]
    relaxed_rows = [row for row in all_scenario_rows if row.get("scenario_id") != "current_chain_native_filters"]
    entry_demands = [row for target in target_results for row in _as_list(target.get("entry_quote_demands"))]
    status_counts = Counter(_norm(row.get("status")) or "unknown" for row in all_scenario_rows)
    best_scenario_counts = Counter()
    for row in relaxed_rows:
        if row.get("status") == "selected_chain_native_entry_spread":
            best_scenario_counts[_norm(row.get("scenario_id"))] += 1
    replay_blocked_count = sum(1 for target in target_results if target.get("replay_status") == "blocked_replay_unavailable")
    blockers: list[str] = []
    if replay_blocked_count:
        blockers.append("chain_native_relaxation_replay_unavailable")
    if entry_demands:
        blockers.append("trusted_entry_contract_quote_coverage_missing_for_target_underlyings")
    if not any(row.get("status") == "selected_chain_native_entry_spread" for row in relaxed_rows):
        blockers.append("no_relaxed_exact_chain_native_candidates")
    blockers.extend(
        [
            "single_date_target_overfit_risk",
            "exact_exit_pnl_replay_missing",
            "fresh_paper_holdout_required_before_policy_change",
        ]
    )
    return {
        "target_lane_count": len({_norm(target.get("lane")) for target in targets if _norm(target.get("lane"))}),
        "target_date_count": len(targets),
        "target_signal_candidate_count": sum(_safe_int(target.get("signal_candidate_count_before")) for target in targets),
        "replay_signal_candidate_count": sum(_safe_int(target.get("replay_signal_candidate_count")) for target in target_results),
        "scenario_count": len(SCENARIOS),
        "scenario_row_count": len(all_scenario_rows),
        "current_selected_chain_native_entry_spread_count": sum(
            1 for row in current_rows if row.get("status") == "selected_chain_native_entry_spread"
        ),
        "relaxed_selected_chain_native_entry_spread_count": sum(
            1 for row in relaxed_rows if row.get("status") == "selected_chain_native_entry_spread"
        ),
        "combined_broad_entry_relaxation_selected_count": sum(
            1
            for row in all_scenario_rows
            if row.get("scenario_id") == "combined_broad_entry_relaxation"
            and row.get("status") == "selected_chain_native_entry_spread"
        ),
        "entry_quote_demand_count": len(entry_demands),
        "entry_quote_demand_tickers": sorted({_norm(row.get("ticker")) for row in entry_demands if _norm(row.get("ticker"))}),
        "scenario_status_counts": dict(sorted(status_counts.items())),
        "selected_relaxation_scenario_counts": dict(sorted(best_scenario_counts.items())),
        "replay_blocked_target_count": replay_blocked_count,
        "promotion_ready": False,
        "live_policy_change": False,
        "blockers": sorted(set(blockers)),
    }


def _overall_status(summary: dict[str, Any], missing_required: list[str], live_policy_change: bool) -> str:
    if live_policy_change:
        return "invalid_live_policy_change"
    if missing_required:
        return "blocked_missing_inputs"
    if summary.get("target_date_count", 0) == 0:
        return "chain_native_filter_relaxation_replay_no_targets"
    if int(summary.get("replay_blocked_target_count") or 0) > 0:
        return "chain_native_filter_relaxation_replay_blocked_replay_unavailable"
    if int(summary.get("relaxed_selected_chain_native_entry_spread_count") or 0) > 0:
        return "chain_native_filter_relaxation_replay_candidates_found_diagnostic_only"
    if int(summary.get("entry_quote_demand_count") or 0) > 0:
        return "chain_native_filter_relaxation_replay_entry_quote_gap"
    return "chain_native_filter_relaxation_replay_no_viable_spreads"


def _next_evidence_queue(overall_status: str, target_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if overall_status == "chain_native_filter_relaxation_replay_blocked_replay_unavailable":
        return [
            {
                "priority": 4,
                "action": "repair_chain_native_relaxation_replay_inputs",
                "count": sum(1 for target in target_results if target.get("replay_status") == "blocked_replay_unavailable"),
                "reason": "chain_native_relaxation_replay_unavailable",
                "operator_next_step": "Repair price-history or lane replay inputs before retesting relaxation scenarios.",
            }
        ]
    entry_demands = [row for target in target_results for row in _as_list(target.get("entry_quote_demands"))]
    if entry_demands:
        tickers = sorted({_norm(row.get("ticker")) for row in entry_demands if _norm(row.get("ticker"))})
        return [
            {
                "priority": 4,
                "action": "import_or_query_chain_native_entry_contract_quotes",
                "count": len(entry_demands),
                "reason": "trusted_entry_contract_quote_coverage_missing_for_target_underlyings",
                "operator_next_step": "Import or query trusted OPRA/NBBO entry contract quotes for the listed underlying/date/option-type windows, then rerun the relaxation replay.",
                "target_tickers": tickers,
            }
        ]
    selected_rows = [
        row
        for target in target_results
        for row in _as_list(target.get("scenario_rows"))
        if row.get("scenario_id") != "current_chain_native_filters"
        and row.get("status") == "selected_chain_native_entry_spread"
    ]
    if selected_rows:
        return [
            {
                "priority": 4,
                "action": "build_exact_exit_outcome_replay_for_relaxed_chain_native_candidates",
                "count": len(selected_rows),
                "reason": "relaxed_entry_candidates_have_no_exact_exit_pnl",
                "operator_next_step": "Replay candidate exits with trusted OPRA/NBBO bid/ask before any policy discussion.",
            },
            {
                "priority": 5,
                "action": "validate_chain_native_relaxation_on_later_holdout",
                "count": 1,
                "reason": "single_date_target_overfit_risk",
                "operator_next_step": "Validate the same predeclared relaxation on later dates/fresh paper before policy discussion.",
            },
        ]
    if overall_status == "chain_native_filter_relaxation_replay_no_viable_spreads":
        return [
            {
                "priority": 5,
                "action": "archive_chain_native_relaxation_dead_end",
                "count": len(target_results),
                "reason": "no_relaxation_scenario_found_exact_chain_native_candidates",
                "operator_next_step": "Keep the bearish-put gap as no viable exact entry spread until a new data source or frozen hypothesis changes the target.",
            }
        ]
    return []


def build_report(
    *,
    exact_candidate_repair_path: Path = DEFAULT_EXACT_CANDIDATE_REPAIR,
    zero_pick_audit_path: Path = DEFAULT_ZERO_PICK_AUDIT,
    generated_at_utc: str | None = None,
    replay_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    reports: dict[str, dict[str, Any]] = {}
    inputs: dict[str, dict[str, Any]] = {}
    for key, path in {
        "exact_candidate_selection_repair": exact_candidate_repair_path,
        "all_lanes_zero_pick_audit": zero_pick_audit_path,
    }.items():
        reports[key], inputs[key] = _load_json(path)

    missing_required = [key for key, meta in inputs.items() if meta["status"] != "loaded"]
    live_policy_change = any(_has_live_policy_change(report) for report in reports.values())
    targets = [] if missing_required or live_policy_change else _target_rows(reports["exact_candidate_selection_repair"])
    target_results = replay_results if replay_results is not None else []
    if targets and replay_results is None:
        target_results = _run_target_replays(targets, reports["all_lanes_zero_pick_audit"])
    summary = _summarize_results(targets, target_results)
    summary["missing_required_inputs"] = missing_required
    summary["live_policy_change"] = live_policy_change
    overall_status = _overall_status(summary, missing_required, live_policy_change)
    summary["overall_status"] = overall_status
    next_queue = _next_evidence_queue(overall_status, target_results)
    summary["next_evidence_action_count"] = len(next_queue)
    status = (
        "invalid_live_policy_change"
        if live_policy_change
        else "blocked_missing_inputs"
        if missing_required
        else "chain_native_filter_relaxation_replay_readback"
    )
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_read_only_chain_native_filter_relaxation_replay",
        "schema_version": 1,
        "read_only": True,
        "summary": summary,
        "proof_policy": {
            "readback_is": "read-only diagnostic replay of predeclared chain-native entry-filter relaxation scenarios",
            "readback_is_not": "scanner policy, contract-selection policy, broker recommendation, DB mutation, lane promotion, or P&L proof",
            "trusted_proof_standard": "P&L requires exact OPRA/NBBO entry and exit bid/ask evidence; this report only diagnoses entry-candidate availability",
            "prohibited_actions": list(PROHIBITED_ACTIONS),
        },
        "scenario_grid": [
            {
                "scenario_id": scenario["scenario_id"],
                "description": scenario["description"],
                "relaxed_filter_names": list(scenario.get("relaxed_filter_names") or []),
            }
            for scenario in SCENARIOS
        ],
        "inputs": inputs,
        "targets": targets,
        "target_replays": target_results,
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
        "# Regular Options Chain-Native Filter Relaxation Replay",
        "",
        "This report is generated from `scripts/build_regular_options_chain_native_filter_relaxation_replay.py`. It replays frozen exact-candidate repair targets through predeclared diagnostic chain-native entry-filter relaxation scenarios.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Overall status: `{summary.get('overall_status')}`.",
        f"- Target lanes: `{summary.get('target_lane_count')}`.",
        f"- Target dates: `{summary.get('target_date_count')}`.",
        f"- Target signal candidates: `{summary.get('target_signal_candidate_count')}`.",
        f"- Replay signal candidates: `{summary.get('replay_signal_candidate_count')}`.",
        f"- Scenario rows: `{summary.get('scenario_row_count')}`.",
        f"- Current selected entry spreads: `{summary.get('current_selected_chain_native_entry_spread_count')}`.",
        f"- Relaxed selected entry spreads: `{summary.get('relaxed_selected_chain_native_entry_spread_count')}`.",
        f"- Entry quote demands: `{summary.get('entry_quote_demand_count')}`.",
        f"- Entry quote demand tickers: `{_json_inline(summary.get('entry_quote_demand_tickers') or [])}`.",
        f"- Scenario status counts: `{_json_inline(summary.get('scenario_status_counts') or {})}`.",
        f"- Selected relaxation scenario counts: `{_json_inline(summary.get('selected_relaxation_scenario_counts') or {})}`.",
        f"- Promotion ready: `{summary.get('promotion_ready')}`.",
        f"- Blockers: `{_json_inline(summary.get('blockers') or [])}`.",
        f"- Live policy change: `{str(bool(summary.get('live_policy_change'))).lower()}`.",
        "",
        "## Scenario Grid",
        "",
        "| Scenario | Relaxed Filters | Description |",
        "|---|---|---|",
    ]
    for scenario in _as_list(report.get("scenario_grid")):
        scenario = _as_dict(scenario)
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(scenario.get('scenario_id'))}`",
                    _json_inline(scenario.get("relaxed_filter_names") or []),
                    _cell(scenario.get("description")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Target Replay Summary",
            "",
            "| Target | Signals | Scenario Rows | Current Selected | Relaxed Selected | Entry Quote Demands | Status |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for target in _as_list(report.get("target_replays")):
        target = _as_dict(target)
        scenario_rows = _as_list(target.get("scenario_rows"))
        current_selected = sum(
            1
            for row in scenario_rows
            if row.get("scenario_id") == "current_chain_native_filters"
            and row.get("status") == "selected_chain_native_entry_spread"
        )
        relaxed_selected = sum(
            1
            for row in scenario_rows
            if row.get("scenario_id") != "current_chain_native_filters"
            and row.get("status") == "selected_chain_native_entry_spread"
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(target.get('target_id'))}`",
                    _cell(target.get("replay_signal_candidate_count")),
                    _cell(len(scenario_rows)),
                    _cell(current_selected),
                    _cell(relaxed_selected),
                    _cell(len(_as_list(target.get("entry_quote_demands")))),
                    f"`{_cell(target.get('replay_status'))}`",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Entry Quote Demands",
            "",
            "| Lane | Date | Ticker | Option Type | Minute ET | Expiry Window | Missing Reason |",
            "|---|---|---|---|---:|---|---|",
        ]
    )
    for target in _as_list(report.get("target_replays")):
        target = _as_dict(target)
        for demand in _as_list(target.get("entry_quote_demands")):
            demand = _as_dict(demand)
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(demand.get("lane")),
                        _cell(demand.get("scan_date")),
                        _cell(demand.get("ticker")),
                        _cell(demand.get("option_type")),
                        _cell(demand.get("entry_quote_minute_et")),
                        f"{_cell(demand.get('min_expiry'))} to {_cell(demand.get('max_expiry'))}",
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
            "This chain-native filter relaxation replay is read-only and diagnostic. It does not create trades, submit broker orders, mutate DB state, change scanner or contract-selection policy, change lane promotion, change stops or sizing, lower exact OPRA/NBBO proof bars, or synthesize P&L from relaxed entry candidates.",
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
    parser = argparse.ArgumentParser(description="Build the read-only regular-options chain-native filter relaxation replay.")
    parser.add_argument("--exact-candidate-repair", type=Path, default=DEFAULT_EXACT_CANDIDATE_REPAIR)
    parser.add_argument("--zero-pick-audit", type=Path, default=DEFAULT_ZERO_PICK_AUDIT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(
        exact_candidate_repair_path=args.exact_candidate_repair,
        zero_pick_audit_path=args.zero_pick_audit,
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
