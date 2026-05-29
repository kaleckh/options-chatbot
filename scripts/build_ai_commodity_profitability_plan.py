from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_commodity_universe import (  # noqa: E402
    ai_commodity_conditional_options_tickers,
    ai_commodity_core_options_tickers,
    ai_commodity_scan_tickers,
)
from lane_research_controls import build_event_macro_concentration_controls  # noqa: E402


DEFAULT_PROGRESS_PATH = ROOT / "data" / "ai-commodity-infra" / "progress" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "ai-commodity-infra" / "profitability-plan"
DEFAULT_LEDGER_DB_PATH = ROOT / "data" / "options-validation" / "forward_tracking_authoritative.db"
DEFAULT_ALPACA_HISTORY_PROBE_PATH = ROOT / "data" / "ai-commodity-infra" / "progress" / "alpaca_options_history_access_probe_latest.json"
DEFAULT_SUPPORTING_HISTORY_PATH = ROOT / "data" / "ai-commodity-infra" / "alpaca-supporting-history" / "latest.json"
DEFAULT_ONCLICKMEDIA_EOD_PATH = ROOT / "data" / "ai-commodity-infra" / "onclickmedia-eod" / "latest.json"
DEFAULT_LIQUIDITY_NEAR_MISS_LOG_PATH = ROOT / "data" / "forward-tracking" / "liquidity_near_misses.jsonl"
DEFAULT_PLAYBOOK = "ai_commodity_infra_observation"

_NEAR_MISS_COST_FIELD_KEYS = (
    "ask",
    "bid",
    "ask_bid",
    "bid_ask",
    "ask_price",
    "bid_price",
    "entry_ask",
    "entry_bid",
    "intended_limit_debit",
    "limit_debit",
    "executable_cost",
    "executable_debit",
    "executable_credit",
    "estimated_executable_cost",
    "estimated_executable_debit",
    "spread_alternatives",
    "top_alternatives",
    "top_spread_alternatives",
    "best_spread_alternative",
    "leg_quotes",
    "legs",
    "quote",
    "intended_ask_bid_debit",
    "quote_age_hours",
    "max_quote_age_hours",
    "quote_age_excess_hours",
    "no_fill_reason",
    "liquidity_reason",
    "reason",
    "distance_to_current_filters",
    "distance_components",
    "worst_leg_spread_excess_pct",
    "spread_slippage_excess_pct",
    "min_leg_volume_shortfall",
    "min_leg_open_interest_shortfall",
)

_NEAR_MISS_RESEARCH_POLICY = {
    "allowed": True,
    "label": "research_only",
    "research_only": True,
    "non_promotable": True,
    "near_miss_diagnostics_promotable": False,
    "scope": "research_only_after_exact_replay_unlock",
    "promotion_policy": "near_miss_diagnostics_can_rank_research_variants_but_cannot_promote_or_relax_production_gates",
    "forbidden_production_changes": [
        "widen_spread_or_slippage_gates",
        "increase_quote_age_limit",
        "lower_open_interest_or_volume_floors",
        "relax_signal_thresholds_for_live_trading",
    ],
}


def _near_miss_missing_log_gap(log_path: Path | None = None) -> dict[str, Any]:
    return {
        "kind": "missing_liquidity_near_misses_jsonl",
        "severity": "evidence_gap",
        "log_path": str(log_path or DEFAULT_LIQUIDITY_NEAR_MISS_LOG_PATH),
        "message": "liquidity_near_misses.jsonl is missing, so near-miss fillability evidence has not been captured yet.",
    }


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _load_json(path)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _symbols(values: Sequence[Any] | None) -> list[str]:
    return sorted({str(value or "").strip().upper() for value in values or [] if str(value or "").strip()})


def _near_miss_cost_fields(source: dict[str, Any]) -> dict[str, Any]:
    fields = {key: source.get(key) for key in _NEAR_MISS_COST_FIELD_KEYS if key in source}
    alternatives = (
        source.get("top_spread_alternatives")
        if source.get("top_spread_alternatives") is not None
        else source.get("top_alternatives")
    )
    if alternatives is None:
        alternatives = source.get("spread_alternatives")
    if alternatives is not None:
        fields["top_spread_alternatives"] = alternatives
        fields["top_alternatives"] = alternatives
    return fields


def _near_miss_research_policy() -> dict[str, Any]:
    return dict(_NEAR_MISS_RESEARCH_POLICY)


def _normalize_near_miss_record(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized.update(_near_miss_cost_fields(row))
    normalized["research_only"] = True
    normalized["non_promotable"] = True
    normalized["diagnostic_label"] = "research_only_near_miss"
    normalized["promotion_policy"] = _NEAR_MISS_RESEARCH_POLICY["promotion_policy"]
    return normalized


def _normalize_liquidity_near_miss_log_summary(summary: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(summary)
    nearest_records = normalized.get("nearest_records")
    if isinstance(nearest_records, list):
        normalized["nearest_records"] = [
            _normalize_near_miss_record(record) if isinstance(record, dict) else record
            for record in nearest_records
        ]
    normalized.setdefault("research_policy", _near_miss_research_policy())
    return normalized


def _drop_symbols_by_key(progress: dict[str, Any]) -> dict[str, list[str]]:
    scan = progress.get("scan") if isinstance(progress.get("scan"), dict) else {}
    for source in (
        scan.get("scan_drop_reason_symbols_by_drop"),
        (progress.get("fresh_scan_post_run_evaluation") or {}).get("scan_drop_reason_symbols_by_drop")
        if isinstance(progress.get("fresh_scan_post_run_evaluation"), dict)
        else None,
        (progress.get("live_candidate_recovery_scan_drop_reason_audit") or {}).get("symbols_by_drop")
        if isinstance(progress.get("live_candidate_recovery_scan_drop_reason_audit"), dict)
        else None,
    ):
        if isinstance(source, dict) and source:
            return {str(key): _symbols(value if isinstance(value, list) else []) for key, value in source.items()}
    return {}


def _candidate_symbols(progress: dict[str, Any]) -> list[str]:
    scan = progress.get("scan") if isinstance(progress.get("scan"), dict) else {}
    return _symbols(scan.get("candidate_symbols") or progress.get("scan_candidate_symbols"))


def _scan_funnel(progress: dict[str, Any]) -> dict[str, Any]:
    scan = progress.get("scan") if isinstance(progress.get("scan"), dict) else {}
    funnel = scan.get("scan_funnel") if isinstance(scan.get("scan_funnel"), dict) else {}
    return funnel


def build_forward_session_summary(
    db_path: Path = DEFAULT_LEDGER_DB_PATH,
    *,
    playbook: str = DEFAULT_PLAYBOOK,
) -> dict[str, Any]:
    if not db_path.exists():
        return {
            "available": False,
            "db_path": str(db_path),
            "playbook": playbook,
            "reason": "ledger_db_missing",
        }

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        summary = conn.execute(
            """
            SELECT
                COUNT(*) AS session_count,
                MIN(recorded_at_utc) AS first_session_at_utc,
                MAX(recorded_at_utc) AS latest_session_at_utc,
                COALESCE(SUM(scan_picks_count), 0) AS total_scan_picks,
                COALESCE(SUM(reviewed_positions_count), 0) AS reviewed_positions_count,
                SUM(CASE WHEN eligibility_status = 'eligible' THEN 1 ELSE 0 END) AS eligible_session_count,
                GROUP_CONCAT(DISTINCT quote_freshness_status) AS quote_freshness_statuses,
                GROUP_CONCAT(DISTINCT eligibility_status) AS eligibility_statuses
            FROM forward_sessions
            WHERE playbook = ?
            """,
            (playbook,),
        ).fetchone()
        by_day = [
            dict(row)
            for row in conn.execute(
                """
                SELECT
                    SUBSTR(recorded_at_utc, 1, 10) AS day,
                    COUNT(*) AS session_count,
                    COALESCE(SUM(scan_picks_count), 0) AS scan_picks,
                    GROUP_CONCAT(DISTINCT eligibility_status) AS eligibility_statuses,
                    GROUP_CONCAT(DISTINCT quote_freshness_status) AS quote_freshness_statuses
                FROM forward_sessions
                WHERE playbook = ?
                GROUP BY SUBSTR(recorded_at_utc, 1, 10)
                ORDER BY day
                """,
                (playbook,),
            )
        ]
        true_playbook_pnl = conn.execute(
            """
            SELECT
                COUNT(*) AS review_count,
                AVG(net_pnl_pct) AS avg_net_pnl_pct,
                SUM(net_pnl_usd) AS sum_net_pnl_usd
            FROM forward_events e
            JOIN forward_sessions s ON s.id = e.session_id
            WHERE s.playbook = ?
              AND e.event_type = 'position_review'
              AND e.payload_json LIKE ?
            """,
            (playbook, f'%"playbook_id": "{playbook}"%'),
        ).fetchone()
    finally:
        conn.close()

    session_count = _as_int(summary["session_count"] if summary else 0)
    total_scan_picks = _as_int(summary["total_scan_picks"] if summary else 0)
    return {
        "available": True,
        "db_path": str(db_path),
        "playbook": playbook,
        "session_count": session_count,
        "first_session_at_utc": summary["first_session_at_utc"] if summary else None,
        "latest_session_at_utc": summary["latest_session_at_utc"] if summary else None,
        "total_scan_picks": total_scan_picks,
        "reviewed_positions_count": _as_int(summary["reviewed_positions_count"] if summary else 0),
        "eligible_session_count": _as_int(summary["eligible_session_count"] if summary else 0),
        "quote_freshness_statuses": [
            item for item in str((summary["quote_freshness_statuses"] if summary else "") or "").split(",") if item
        ],
        "eligibility_statuses": [
            item for item in str((summary["eligibility_statuses"] if summary else "") or "").split(",") if item
        ],
        "scan_picks_per_session": round(total_scan_picks / session_count, 4) if session_count else 0.0,
        "by_day": by_day,
        "true_playbook_position_review_pnl": {
            "review_count": _as_int(true_playbook_pnl["review_count"] if true_playbook_pnl else 0),
            "avg_net_pnl_pct": _as_float(true_playbook_pnl["avg_net_pnl_pct"] if true_playbook_pnl else None),
            "sum_net_pnl_usd": _as_float(true_playbook_pnl["sum_net_pnl_usd"] if true_playbook_pnl else None),
            "policy": "only_reviews_whose_payload_source_pick_snapshot_playbook_id_matches_commodity_playbook_count",
        },
    }


def build_liquidity_near_miss_log_summary(
    log_path: Path = DEFAULT_LIQUIDITY_NEAR_MISS_LOG_PATH,
    *,
    playbook: str = DEFAULT_PLAYBOOK,
    tail_limit: int = 500,
) -> dict[str, Any]:
    if not log_path.exists():
        return {
            "available": False,
            "log_path": str(log_path),
            "playbook": playbook,
            "record_count": 0,
            "status": "evidence_gap_missing_liquidity_near_misses_jsonl",
            "evidence_gap": _near_miss_missing_log_gap(log_path),
            "research_policy": _near_miss_research_policy(),
        }
    rows: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf8").splitlines()[-max(int(tail_limit), 1) :]:
        text = line.strip()
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    filtered = [
        row
        for row in rows
        if str(row.get("event_type") or "") == "liquidity_near_miss"
        and str(row.get("playbook_id") or "") == playbook
    ]
    ticker_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    for row in filtered:
        ticker = str(row.get("ticker") or "").strip().upper()
        if ticker:
            ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1
        for reason in row.get("liquidity_reasons") or []:
            reason_text = str(reason or "").strip()
            if reason_text:
                reason_counts[reason_text] = reason_counts.get(reason_text, 0) + 1
    latest = filtered[-1] if filtered else None
    nearest_records = sorted(
        filtered,
        key=lambda row: (
            row.get("distance_to_current_filters") is None,
            float(row.get("distance_to_current_filters") or 999999.0),
            str(row.get("ticker") or ""),
        ),
    )[:8]
    return {
        "available": True,
        "log_path": str(log_path),
        "playbook": playbook,
        "record_count": len(filtered),
        "latest_logged_at": latest.get("logged_at") if latest else None,
        "latest_scan_date": latest.get("scan_date") if latest else None,
        "top_tickers": [
            {"ticker": ticker, "count": count}
            for ticker, count in sorted(ticker_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
        ],
        "top_liquidity_reasons": [
            {"reason": reason, "count": count}
            for reason, count in sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
        ],
        "nearest_records": [_normalize_near_miss_record(row) for row in nearest_records],
        "status": "active" if filtered else "implemented_waiting_for_next_scan_records",
        "research_policy": _near_miss_research_policy(),
    }


def build_cohort_throughput(progress: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = set(_candidate_symbols(progress))
    drops = _drop_symbols_by_key(progress)
    cohorts = [
        ("full_24", ai_commodity_scan_tickers()),
        ("core_options", ai_commodity_core_options_tickers()),
        ("conditional_options", ai_commodity_conditional_options_tickers()),
    ]
    rows: list[dict[str, Any]] = []
    for cohort_id, cohort_symbols in cohorts:
        cohort_set = set(cohort_symbols)
        drop_counts = {
            key: len(cohort_set & set(symbols))
            for key, symbols in sorted(drops.items())
            if cohort_set & set(symbols)
        }
        dominant_drop = max(drop_counts.items(), key=lambda item: item[1])[0] if drop_counts else None
        rows.append(
            {
                "cohort": cohort_id,
                "symbol_count": len(cohort_symbols),
                "symbols": cohort_symbols,
                "candidate_count": len(cohort_set & candidates),
                "candidate_symbols": sorted(cohort_set & candidates),
                "drop_counts": drop_counts,
                "dominant_drop_key": dominant_drop,
                "dropped_symbol_count": sum(drop_counts.values()),
                "unexplained_symbol_count": max(len(cohort_symbols) - len(cohort_set & candidates) - sum(drop_counts.values()), 0),
            }
        )
    return rows


def _near_miss_queue(progress: dict[str, Any]) -> list[dict[str, Any]]:
    scan = progress.get("scan") if isinstance(progress.get("scan"), dict) else {}
    diagnostics = scan.get("drop_diagnostics") if isinstance(scan.get("drop_diagnostics"), list) else []
    queue: list[dict[str, Any]] = []
    for diagnostic in diagnostics:
        if not isinstance(diagnostic, dict):
            continue
        drop_key = str(diagnostic.get("drop_key") or "")
        count = _as_int(diagnostic.get("count"))
        examples = diagnostic.get("nearest_examples") or diagnostic.get("representative_examples") or []
        if not isinstance(examples, list):
            continue
        for example in examples[:3]:
            if not isinstance(example, dict):
                continue
            item = {
                "drop_key": drop_key,
                "drop_count": count,
                "symbol": example.get("symbol"),
                "liquidity_reasons": example.get("liquidity_reasons"),
                "worst_leg_spread_excess_pct": example.get("worst_leg_spread_excess_pct"),
                "spread_slippage_excess_pct": example.get("spread_slippage_excess_pct"),
                "quote_age_excess_hours": example.get("quote_age_excess_hours"),
                "min_leg_open_interest_shortfall": example.get("min_leg_open_interest_shortfall"),
                "tech_score_shortfall": example.get("tech_score_shortfall"),
                "momentum_signal_distance_pct": example.get("momentum_signal_distance_pct"),
                "production_filter_action": diagnostic.get("production_filter_action"),
                "next_diagnostic_action": diagnostic.get("next_diagnostic_action"),
                "research_only": True,
                "non_promotable": True,
                "diagnostic_label": "research_only_near_miss",
                "promotion_policy": _NEAR_MISS_RESEARCH_POLICY["promotion_policy"],
            }
            item.update(_near_miss_cost_fields(example))
            queue.append(item)
    return queue[:12]


def _research_control_records(progress: dict[str, Any]) -> list[dict[str, Any]]:
    for key in (
        "closed_trade_reviews",
        "forward_review_records",
        "paper_review_records",
        "completed_trades",
        "trades",
    ):
        value = progress.get(key)
        if isinstance(value, list):
            return [dict(item) for item in value if isinstance(item, dict)]
    return []


def _ranked_drop_counts(drop_counts: dict[str, Any]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for key, value in sorted(drop_counts.items()):
        count = _as_int(value)
        if count > 0:
            ranked.append({"drop_key": str(key), "count": count})
    ranked.sort(key=lambda item: (-int(item["count"]), str(item["drop_key"])))
    return ranked


def _dominant_drop_action(drop_key: str | None) -> list[str]:
    actions_by_drop = {
        "option_liquidity": [
            "rerun_live_scan_inside_fresh_opra_window_before_filter_changes",
            "compare_top_spread_alternatives_for_structural_width_vs_quote_age",
            "keep_collecting_exact_bid_ask_history_until_replay_and_oos_gates_unlock",
        ],
        "tech_score": [
            "queue_research_only_tech_score_variants_after_exact_replay_unlock",
            "inspect_symbols_nearest_to_the_floor_by_theme_bucket",
        ],
        "momentum": [
            "queue_research_only_momentum_variants_after_exact_replay_unlock",
            "separate_trend_gap_shortfalls_from_one_day_pullback_noise",
        ],
        "ev_floor": [
            "audit_ev_shortfall_against_exact_bid_ask_fillability_after_replay_unlock",
            "do_not_lower_ev_floor_without_oos_exact_contract_survival",
        ],
    }
    return actions_by_drop.get(
        str(drop_key or ""),
        ["inspect_raw_drop_reason_examples_before_any_filter_or_algorithm_change"],
    )


def _opportunity_denominator_diagnostic_packet(lane_b_throughput: dict[str, Any]) -> dict[str, Any]:
    latest_funnel = lane_b_throughput.get("latest_funnel") if isinstance(lane_b_throughput.get("latest_funnel"), dict) else {}
    return {
        "status": lane_b_throughput.get("status"),
        "near_miss_log_status": lane_b_throughput.get("near_miss_log_status"),
        "near_miss_log_record_count": _as_int(lane_b_throughput.get("near_miss_log_record_count")),
        "near_miss_log_evidence_gap": lane_b_throughput.get("near_miss_log_evidence_gap"),
        "dominant_drop_key": lane_b_throughput.get("dominant_drop_key"),
        "drop_counts": latest_funnel.get("drop_counts") or {},
        "drop_rank": lane_b_throughput.get("drop_rank") or [],
        "near_miss_queue": lane_b_throughput.get("near_miss_queue") or [],
        "nearest_near_miss_log_records": lane_b_throughput.get("nearest_near_miss_log_records") or [],
        "research_policy": lane_b_throughput.get("research_policy") or _near_miss_research_policy(),
    }


def build_lane_b_throughput_diagnostics(
    progress: dict[str, Any],
    *,
    liquidity_near_miss_log: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scan = progress.get("scan") if isinstance(progress.get("scan"), dict) else {}
    funnel = _scan_funnel(progress)
    drop_counts = funnel.get("drop_counts") if isinstance(funnel.get("drop_counts"), dict) else {}
    ranked_drops = _ranked_drop_counts(drop_counts)
    dominant_drop = ranked_drops[0]["drop_key"] if ranked_drops else None
    candidate_count = _as_int(scan.get("candidate_count") if scan.get("candidate_count") is not None else scan.get("returned_count"))
    returned_picks = _as_int(funnel.get("returned_picks") if funnel.get("returned_picks") is not None else scan.get("returned_count"))
    raw_candidates = _as_int(funnel.get("raw_candidates"))
    drop_reason_count = _as_int(scan.get("scan_drop_reason_count") or progress.get("scan_drop_reason_count"))
    near_miss_log = (
        _normalize_liquidity_near_miss_log_summary(liquidity_near_miss_log)
        if isinstance(liquidity_near_miss_log, dict)
        else {}
    )

    if returned_picks > 0 or candidate_count > 0:
        status = "has_live_candidate"
    elif drop_reason_count > 0 or ranked_drops:
        status = "zero_returned_with_recorded_drop_reasons"
    elif raw_candidates > 0:
        status = "raw_candidates_filtered_without_symbol_drop_reason_coverage"
    else:
        status = "zero_raw_candidates_waiting_for_next_scan"

    exact_replay_ready = bool(
        ((progress.get("verification_gate") or {}).get("gates") or {}).get("exact_replay_profit_factor_positive")
        if isinstance(progress.get("verification_gate"), dict)
        else False
    )

    return {
        "lane_id": DEFAULT_PLAYBOOK,
        "status": status,
        "production_gate_policy": "diagnostic_only_preserve_production_gates",
        "safe_to_tune_production_filters": False,
        "safe_to_tune_reason": (
            "exact_replay_gate_unlocked"
            if exact_replay_ready
            else "exact_replay_and_oos_gates_not_ready"
        ),
        "latest_funnel": {
            "raw_candidates": raw_candidates,
            "post_policy_visible": _as_int(funnel.get("post_policy_visible")),
            "post_guardrail_visible": _as_int(funnel.get("post_guardrail_visible")),
            "returned_picks": returned_picks,
            "policy_filtered_out": _as_int(funnel.get("policy_filtered_out")),
            "guardrail_filtered_out": _as_int(funnel.get("guardrail_filtered_out")),
            "final_trimmed": _as_int(funnel.get("final_trimmed")),
            "drop_counts": {str(key): _as_int(value) for key, value in sorted(drop_counts.items())},
        },
        "drop_rank": ranked_drops,
        "dominant_drop_key": dominant_drop,
        "drop_reason_count": drop_reason_count,
        "cohort_throughput": build_cohort_throughput(progress),
        "near_miss_queue": _near_miss_queue(progress),
        "near_miss_log_status": near_miss_log.get("status") or "not_loaded",
        "near_miss_log_record_count": _as_int(near_miss_log.get("record_count")) if near_miss_log else 0,
        "near_miss_log_evidence_gap": near_miss_log.get("evidence_gap"),
        "nearest_near_miss_log_records": near_miss_log.get("nearest_records") or [],
        "next_diagnostic_actions": _dominant_drop_action(dominant_drop),
        "research_policy": _near_miss_research_policy(),
    }


def build_profitability_plan(
    progress: dict[str, Any],
    *,
    forward_summary: dict[str, Any] | None = None,
    alpaca_history_probe: dict[str, Any] | None = None,
    supporting_history: dict[str, Any] | None = None,
    onclickmedia_eod: dict[str, Any] | None = None,
    liquidity_near_miss_log: dict[str, Any] | None = None,
) -> dict[str, Any]:
    verification = progress.get("verification_gate") if isinstance(progress.get("verification_gate"), dict) else {}
    scorecard = (
        progress.get("profitability_evidence_scorecard")
        if isinstance(progress.get("profitability_evidence_scorecard"), dict)
        else {}
    )
    scan = progress.get("scan") if isinstance(progress.get("scan"), dict) else {}
    funnel = _scan_funnel(progress)
    proof_window = progress.get("proof_window") if isinstance(progress.get("proof_window"), dict) else {}
    source_quality = progress.get("source_quality") if isinstance(progress.get("source_quality"), dict) else {}
    live_recovery = (
        progress.get("live_candidate_recovery_plan")
        if isinstance(progress.get("live_candidate_recovery_plan"), dict)
        else {}
    )
    current_shared = _as_int(
        scorecard.get("current_shared_quote_dates")
        if scorecard.get("current_shared_quote_dates") is not None
        else proof_window.get("current_shared_quote_dates")
    )
    required_shared = _as_int(
        scorecard.get("required_shared_quote_dates")
        if scorecard.get("required_shared_quote_dates") is not None
        else proof_window.get("required_shared_quote_dates"),
        100,
    )
    candidate_count = _as_int(scan.get("candidate_count") if scan.get("candidate_count") is not None else scan.get("returned_count"))
    raw_candidate_count = _as_int(funnel.get("raw_candidates"))
    drop_counts = funnel.get("drop_counts") if isinstance(funnel.get("drop_counts"), dict) else {}
    dominant_drop = None
    positive_drops = {str(key): _as_int(value) for key, value in drop_counts.items() if _as_int(value) > 0}
    if positive_drops:
        dominant_drop = max(positive_drops.items(), key=lambda item: item[1])[0]

    p_and_l_review = (forward_summary or {}).get("true_playbook_position_review_pnl", {})
    live_candidate_gate = (verification.get("gates") or {}).get("live_scan_has_candidate") is True
    exact_replay_gate = (verification.get("gates") or {}).get("exact_replay_profit_factor_positive") is True
    claim_status = "verified_profitable" if verification.get("verified") is True else "not_verified_unmeasured"
    if p_and_l_review.get("review_count"):
        claim_status = "has_true_playbook_forward_reviews_but_exact_replay_still_required"
    probe_findings = (
        alpaca_history_probe.get("access_findings")
        if isinstance(alpaca_history_probe, dict) and isinstance(alpaca_history_probe.get("access_findings"), dict)
        else {}
    )
    supporting_history = supporting_history if isinstance(supporting_history, dict) else {}
    onclickmedia_eod = onclickmedia_eod if isinstance(onclickmedia_eod, dict) else {}
    liquidity_near_miss_log = (
        _normalize_liquidity_near_miss_log_summary(liquidity_near_miss_log)
        if isinstance(liquidity_near_miss_log, dict)
        else {
            "status": "evidence_gap_missing_liquidity_near_misses_jsonl",
            "record_count": 0,
            "evidence_gap": _near_miss_missing_log_gap(),
            "research_policy": _near_miss_research_policy(),
        }
    )
    near_miss_status = liquidity_near_miss_log.get("status") or "implemented_waiting_for_next_scan_records"
    lane_b_throughput = build_lane_b_throughput_diagnostics(
        progress,
        liquidity_near_miss_log=liquidity_near_miss_log,
    )
    opportunity_denominator_diagnostics = _opportunity_denominator_diagnostic_packet(lane_b_throughput)
    event_macro_concentration_controls = build_event_macro_concentration_controls(
        _research_control_records(progress),
        lane_id=DEFAULT_PLAYBOOK,
    )

    return {
        "generated_at": _utc_now_iso(),
        "source_progress_generated_at": progress.get("generated_at"),
        "playbook": DEFAULT_PLAYBOOK,
        "claim_status": claim_status,
        "profitability_summary": {
            "verified": bool(verification.get("verified")),
            "verification_status": verification.get("status"),
            "replay_total_trades": verification.get("replay_total_trades"),
            "replay_profit_factor": verification.get("replay_profit_factor"),
            "replay_total_return_pct": verification.get("replay_total_return_pct"),
            "forward_true_playbook_review_count": p_and_l_review.get("review_count", 0),
            "forward_true_playbook_sum_net_pnl_usd": p_and_l_review.get("sum_net_pnl_usd"),
            "pnl_policy": p_and_l_review.get("policy"),
        },
        "proof_depth": {
            "provider": progress.get("provider"),
            "proof_source_label": progress.get("proof_source_label"),
            "current_shared_quote_dates": current_shared,
            "required_shared_quote_dates": required_shared,
            "remaining_shared_quote_dates": max(required_shared - current_shared, 0),
            "source_quality_status": source_quality.get("status"),
            "min_executable_quote_pct": source_quality.get("min_executable_quote_pct"),
            "first_shared_quote_date": proof_window.get("first_shared_quote_date"),
            "latest_shared_quote_date": proof_window.get("latest_shared_quote_date"),
            "diagnostic_ready_date": proof_window.get("approx_diagnostic_ready_date_if_one_capture_per_market_day"),
            "full_replay_ready_date": proof_window.get("approx_completion_date_if_one_capture_per_market_day"),
        },
        "opportunity_throughput": {
            "status": "has_live_candidate" if candidate_count > 0 else "zero_candidate_with_recorded_drop_reasons",
            "latest_candidate_count": candidate_count,
            "latest_candidate_symbols": _candidate_symbols(progress),
            "latest_raw_candidate_count": raw_candidate_count,
            "latest_returned_pick_count": _as_int(funnel.get("returned_picks") or scan.get("returned_count")),
            "scan_drop_reason_count": _as_int(scan.get("scan_drop_reason_count") or progress.get("scan_drop_reason_count")),
            "dominant_drop_key": dominant_drop or live_recovery.get("dominant_drop_key"),
            "top_drop_counts": live_recovery.get("top_drop_counts") or [
                {"drop_key": key, "count": value}
                for key, value in sorted(positive_drops.items(), key=lambda item: item[1], reverse=True)
            ],
            "denominator_diagnostics": opportunity_denominator_diagnostics,
            "forward_session_summary": forward_summary or {},
        },
        "opportunity_denominator_diagnostics": opportunity_denominator_diagnostics,
        "pre_registered_cohort_throughput": build_cohort_throughput(progress),
        "near_miss_queue": _near_miss_queue(progress),
        "lane_b_throughput_diagnostics": lane_b_throughput,
        "event_macro_concentration_controls": event_macro_concentration_controls,
        "alpaca_data_surface": {
            "probe_generated_at_utc": alpaca_history_probe.get("generated_at_utc") if isinstance(alpaca_history_probe, dict) else None,
            "historical_option_bars_accessible": bool(probe_findings.get("historical_option_bars_accessible")),
            "historical_option_trades_accessible": bool(probe_findings.get("historical_option_trades_accessible")),
            "historical_option_quotes_accessible": bool(probe_findings.get("historical_option_quotes_accessible")),
            "latest_option_quotes_accessible": bool(probe_findings.get("latest_option_quotes_accessible")),
            "proof_grade_bid_ask_backfill_available_from_alpaca_probe": bool(
                probe_findings.get("proof_grade_bid_ask_backfill_available_from_alpaca_probe")
            ),
            "historical_option_quotes_status_code": probe_findings.get("historical_option_quotes_status_code"),
            "policy": "bars_and_trades_are_supporting_context_only; exact_profitability_requires_bid_ask_quotes",
        },
        "supporting_history": {
            "available": bool(supporting_history),
            "generated_at_utc": supporting_history.get("generated_at_utc"),
            "contract_count": supporting_history.get("contract_count"),
            "bars_row_count": (supporting_history.get("bars") or {}).get("row_count")
            if isinstance(supporting_history.get("bars"), dict)
            else None,
            "trades_row_count": (supporting_history.get("trades") or {}).get("row_count")
            if isinstance(supporting_history.get("trades"), dict)
            else None,
            "proof_grade_bid_ask": supporting_history.get("proof_grade_bid_ask"),
            "proof_blocker": supporting_history.get("proof_blocker"),
            "usage_policy": supporting_history.get("usage_policy"),
            "latest_path": supporting_history.get("latest_path"),
        },
        "research_grade_eod_bidask": {
            "available": bool(onclickmedia_eod),
            "source_label": onclickmedia_eod.get("source_label"),
            "source_grade": onclickmedia_eod.get("source_grade"),
            "proof_grade": onclickmedia_eod.get("proof_grade"),
            "generated_at_utc": onclickmedia_eod.get("generated_at_utc"),
            "selected_shared_dates": onclickmedia_eod.get("selected_shared_dates"),
            "symbol_count": onclickmedia_eod.get("symbol_count"),
            "row_count": onclickmedia_eod.get("row_count"),
            "executable_bid_ask_rows": onclickmedia_eod.get("executable_bid_ask_rows"),
            "executable_bid_ask_pct": onclickmedia_eod.get("executable_bid_ask_pct"),
            "executable_with_volume_oi_rows": onclickmedia_eod.get("executable_with_volume_oi_rows"),
            "executable_with_volume_oi_pct": onclickmedia_eod.get("executable_with_volume_oi_pct"),
            "error_pairs": onclickmedia_eod.get("error_pairs"),
            "usage_policy": onclickmedia_eod.get("usage_policy"),
            "output_dir": onclickmedia_eod.get("output_dir"),
            "data_quality_caveats": onclickmedia_eod.get("data_quality_caveats"),
        },
        "near_miss_fillability_log": liquidity_near_miss_log,
        "debate_resolution": [
            {
                "decision": "do_not_loosen_production_filters",
                "why": "liquidity misses include stale quotes, wide legs, and slippage; loosening before exact replay can create activity while destroying EV.",
            },
            {
                "decision": "separate_external_nbbo_sources_from_alpaca_baseline",
                "why": "historical vendor NBBO can accelerate proof only through source-labeled readiness gates, not by contaminating the Alpaca OPRA proof contract.",
            },
            {
                "decision": "measure_throughput_before_signal_relaxation",
                "why": "the lane currently has zero live candidates, so candidate production and near-miss distance are first-class profitability inputs.",
            },
            {
                "decision": "require_stronger_replay_metrics_after_unlock",
                "why": "positive PF and return are necessary but not enough; trade count, drawdown, expectancy, OOS behavior, and stress fills should gate promotion.",
            },
        ],
        "technical_plan": [
            {
                "priority": 1,
                "workstream": "guarded_fresh_scan_and_capture",
                "status": "blocked_until_next_guarded_window",
                "action": progress.get("guarded_command_decision_next_command_when_allowed")
                or scorecard.get("next_evidence_event_command"),
                "not_before_user_local": progress.get("guarded_command_decision_next_not_before_user_local")
                or scorecard.get("next_evidence_event_not_before_user_local"),
                "done_when": "scorecard shared quote dates advance or fresh scan records verifiable candidates/drop reasons without filter mutation",
            },
            {
                "priority": 2,
                "workstream": "cohort_and_throughput_reporting",
                "status": "implemented_in_this_report",
                "action": "run scripts/build_ai_commodity_profitability_plan.py",
                "done_when": "full/core/conditional cohort throughput and near-miss queues are visible in JSON and markdown",
            },
            {
                "priority": 3,
                "workstream": "near_miss_fillability_logging",
                "status": near_miss_status,
                "action": "persist top spread alternatives for zero-candidate liquidity blockers under the commodity playbook",
                "done_when": "RIO/CCJ/TT-style near misses include top alternatives, intended limit, quote age, and no-fill reason",
            },
            {
                "priority": 4,
                "workstream": "research_grade_eod_bidask_backtest",
                "status": "implemented_waiting_for_import"
                if not onclickmedia_eod
                else "research_dataset_available",
                "action": "run scripts/import_onclickmedia_options_eod.py for the commodity universe, then use it for EOD bid/ask research only",
                "done_when": "OnclickMedia summary reports >=100 shared dates for all lane symbols with row and executable bid/ask coverage",
            },
            {
                "priority": 5,
                "workstream": "external_nbbo_proof_lane",
                "status": "queued_pending_proof_grade_vendor",
                "action": "accept source-labeled exact NBBO imports only when the source is licensed/proof-grade intraday bid/ask",
                "done_when": "external proof source can be compared against Alpaca baseline without mixing proof labels",
            },
            {
                "priority": 6,
                "workstream": "stress_replay_after_unlock",
                "status": "locked_until_exact_replay_has_trades",
                "action": "add worse-fill scenarios and stronger promotion metrics after exact replay is runnable",
                "done_when": "baseline and variants report net PF, expectancy, drawdown, OOS, per-symbol contribution, and stressed-fill survival",
            },
        ],
        "non_goals": [
            "Do not count SPY/QQQ bullish-pullback P&L as commodity-lane profitability.",
            "Do not count bars, trades, mids, or current snapshots as historical executable BBO proof.",
            "Do not promote OnclickMedia EOD chains as OPRA proof-grade intraday NBBO.",
            "Do not widen spread, slippage, quote-age, OI, or volume gates before exact replay can measure the variant.",
        ],
        "gates": {
            "live_candidate_gate": live_candidate_gate,
            "exact_replay_profitability_gate": exact_replay_gate,
            "safe_to_tune_production_filters": bool(live_recovery.get("safe_to_tune_production_filters"))
            and bool(lane_b_throughput.get("safe_to_tune_production_filters")),
        },
    }


def render_markdown(plan: dict[str, Any]) -> str:
    proof = plan["proof_depth"]
    throughput = plan["opportunity_throughput"]
    profitability = plan["profitability_summary"]
    alpaca_surface = plan.get("alpaca_data_surface") or {}
    supporting_history = plan.get("supporting_history") or {}
    research_eod = plan.get("research_grade_eod_bidask") or {}
    fillability_log = plan.get("near_miss_fillability_log") or {}
    lines = [
        "# AI Commodity Profitability Technical Plan",
        "",
        f"- Generated: `{plan.get('generated_at')}`",
        f"- Source progress generated: `{plan.get('source_progress_generated_at')}`",
        f"- Claim status: `{plan.get('claim_status')}`",
        f"- Verified: `{profitability.get('verified')}`",
        f"- Replay trades / PF / return: `{profitability.get('replay_total_trades')}` / `{profitability.get('replay_profit_factor')}` / `{profitability.get('replay_total_return_pct')}`",
        f"- True commodity-playbook forward review count: `{profitability.get('forward_true_playbook_review_count')}`",
        "",
        "## Proof Depth",
        f"- Provider: `{proof.get('provider')}`",
        f"- Proof source: `{proof.get('proof_source_label')}`",
        f"- Shared dates: `{proof.get('current_shared_quote_dates')}` / `{proof.get('required_shared_quote_dates')}`",
        f"- Remaining shared dates: `{proof.get('remaining_shared_quote_dates')}`",
        f"- Source quality: `{proof.get('source_quality_status')}`",
        f"- Diagnostic ready date: `{proof.get('diagnostic_ready_date')}`",
        f"- Full replay ready date: `{proof.get('full_replay_ready_date')}`",
        "",
        "## Alpaca Data Surface",
        f"- Historical bars/trades: `{alpaca_surface.get('historical_option_bars_accessible')}` / `{alpaca_surface.get('historical_option_trades_accessible')}`",
        f"- Historical quotes: `{alpaca_surface.get('historical_option_quotes_accessible')}` status `{alpaca_surface.get('historical_option_quotes_status_code')}`",
        f"- Proof-grade bid/ask backfill from Alpaca probe: `{alpaca_surface.get('proof_grade_bid_ask_backfill_available_from_alpaca_probe')}`",
        f"- Policy: `{alpaca_surface.get('policy')}`",
        "",
        "## Supporting History",
        f"- Available: `{supporting_history.get('available')}`",
        f"- Contracts / bars / trades: `{supporting_history.get('contract_count')}` / `{supporting_history.get('bars_row_count')}` / `{supporting_history.get('trades_row_count')}`",
        f"- Proof-grade bid/ask: `{supporting_history.get('proof_grade_bid_ask')}` blocker `{supporting_history.get('proof_blocker')}`",
        "",
        "## Research Grade EOD Bid/Ask",
        f"- Available: `{research_eod.get('available')}`",
        f"- Source: `{research_eod.get('source_label')}` grade `{research_eod.get('source_grade')}` proof `{research_eod.get('proof_grade')}`",
        f"- Symbols / shared dates: `{research_eod.get('symbol_count')}` / `{(research_eod.get('selected_shared_dates') or {}).get('count')}`",
        f"- Date range: `{(research_eod.get('selected_shared_dates') or {}).get('first')}` to `{(research_eod.get('selected_shared_dates') or {}).get('last')}`",
        f"- Rows / executable bid-ask / volume+OI executable: `{research_eod.get('row_count')}` / `{research_eod.get('executable_bid_ask_rows')}` / `{research_eod.get('executable_with_volume_oi_rows')}`",
        f"- Usage policy: `{research_eod.get('usage_policy')}`",
        "",
        "## Opportunity Throughput",
        f"- Status: `{throughput.get('status')}`",
        f"- Latest candidates: `{throughput.get('latest_candidate_count')}` `{throughput.get('latest_candidate_symbols')}`",
        f"- Latest raw candidates: `{throughput.get('latest_raw_candidate_count')}`",
        f"- Scan drop reason count: `{throughput.get('scan_drop_reason_count')}`",
        f"- Dominant drop key: `{throughput.get('dominant_drop_key')}`",
        f"- Top drop counts: `{throughput.get('top_drop_counts')}`",
        f"- Forward sessions: `{(throughput.get('forward_session_summary') or {}).get('session_count')}`",
        f"- Scan picks per session: `{(throughput.get('forward_session_summary') or {}).get('scan_picks_per_session')}`",
        "",
        "## Cohorts",
    ]
    for cohort in plan.get("pre_registered_cohort_throughput", []):
        lines.extend(
            [
                f"- `{cohort.get('cohort')}`: `{cohort.get('candidate_count')}` candidates / `{cohort.get('symbol_count')}` symbols; dominant drop `{cohort.get('dominant_drop_key')}`; drops `{cohort.get('drop_counts')}`",
            ]
        )
    lines.extend(["", "## Near Miss Queue"])
    for item in plan.get("near_miss_queue", [])[:8]:
        lines.append(
            f"- `{item.get('symbol')}` `{item.get('drop_key')}` reasons `{item.get('liquidity_reasons')}` spread excess `{item.get('worst_leg_spread_excess_pct')}` quote-age excess `{item.get('quote_age_excess_hours')}`"
        )
    diagnostics = plan.get("lane_b_throughput_diagnostics") or {}
    lines.extend(
        [
            "",
            "## Lane B Throughput Diagnostics",
            f"- Status: `{diagnostics.get('status')}`",
            f"- Production gate policy: `{diagnostics.get('production_gate_policy')}`",
            f"- Dominant drop: `{diagnostics.get('dominant_drop_key')}`",
            f"- Drop rank: `{diagnostics.get('drop_rank')}`",
            f"- Next diagnostic actions: `{diagnostics.get('next_diagnostic_actions')}`",
        ]
    )
    controls = plan.get("event_macro_concentration_controls") or {}
    lines.extend(
        [
            "",
            "## Event Macro Concentration Controls",
            f"- Policy: `{controls.get('policy')}`",
            f"- Records: `{controls.get('record_count')}`",
            f"- Promotion allowed: `{controls.get('promotion_allowed')}`",
            f"- Promotion blockers: `{controls.get('promotion_blockers')}`",
            f"- Event controls: `{controls.get('event_controls')}`",
            f"- Macro controls: `{controls.get('macro_controls')}`",
            f"- Concentration controls: `{controls.get('concentration_controls')}`",
        ]
    )
    lines.extend(
        [
            "",
            "## Fillability Log",
            f"- Status: `{fillability_log.get('status')}`",
            f"- Evidence gap: `{fillability_log.get('evidence_gap') or 'none'}`",
            f"- Records: `{fillability_log.get('record_count')}` latest `{fillability_log.get('latest_scan_date')}`",
            f"- Top tickers: `{fillability_log.get('top_tickers')}`",
            f"- Top liquidity reasons: `{fillability_log.get('top_liquidity_reasons')}`",
        ]
    )
    lines.extend(["", "## Debate Resolution"])
    for item in plan.get("debate_resolution", []):
        lines.append(f"- `{item.get('decision')}`: {item.get('why')}")
    lines.extend(["", "## Technical Plan"])
    for item in plan.get("technical_plan", []):
        lines.append(
            f"- P{item.get('priority')} `{item.get('workstream')}` `{item.get('status')}`: {item.get('action')}"
        )
    lines.extend(["", "## Non Goals"])
    for item in plan.get("non_goals", []):
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def write_plan(plan: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "latest.json"
    md_path = output_dir / "latest.md"
    json_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf8")
    md_path.write_text(render_markdown(plan), encoding="utf8")
    timestamp = str(plan.get("generated_at") or _utc_now_iso()).replace(":", "").replace("-", "")
    snapshot_json = output_dir / f"profitability_plan_{timestamp}.json"
    snapshot_md = output_dir / f"profitability_plan_{timestamp}.md"
    snapshot_json.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf8")
    snapshot_md.write_text(render_markdown(plan), encoding="utf8")
    return {
        "json": str(snapshot_json),
        "markdown": str(snapshot_md),
        "latest_json": str(json_path),
        "latest_markdown": str(md_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build an operator-facing technical plan for the AI commodity options profitability lane."
    )
    parser.add_argument("--progress-path", default=str(DEFAULT_PROGRESS_PATH))
    parser.add_argument("--ledger-db-path", default=str(DEFAULT_LEDGER_DB_PATH))
    parser.add_argument("--alpaca-history-probe-path", default=str(DEFAULT_ALPACA_HISTORY_PROBE_PATH))
    parser.add_argument("--supporting-history-path", default=str(DEFAULT_SUPPORTING_HISTORY_PATH))
    parser.add_argument("--onclickmedia-eod-path", default=str(DEFAULT_ONCLICKMEDIA_EOD_PATH))
    parser.add_argument("--liquidity-near-miss-log-path", default=str(DEFAULT_LIQUIDITY_NEAR_MISS_LOG_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--playbook", default=DEFAULT_PLAYBOOK)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of markdown.")
    args = parser.parse_args()

    progress = _load_json(Path(args.progress_path))
    forward_summary = build_forward_session_summary(Path(args.ledger_db_path), playbook=args.playbook)
    plan = build_profitability_plan(
        progress,
        forward_summary=forward_summary,
        alpaca_history_probe=_load_json_if_exists(Path(args.alpaca_history_probe_path)),
        supporting_history=_load_json_if_exists(Path(args.supporting_history_path)),
        onclickmedia_eod=_load_json_if_exists(Path(args.onclickmedia_eod_path)),
        liquidity_near_miss_log=build_liquidity_near_miss_log_summary(
            Path(args.liquidity_near_miss_log_path),
            playbook=args.playbook,
        ),
    )
    if not args.no_write:
        plan["artifacts"] = write_plan(plan, Path(args.output_dir))
    if args.json:
        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        print(render_markdown(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
