from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
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
from scripts.analyze_trading_desk_profitability_guardrails import canonical_lane, pnl_pct, source
from scripts.audit_trading_desk_negative_trade_decisions import _as_mapping, _review_is_executable, _review_pnl


DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOC = ROOT / "docs" / "trading-desk-exit-policy-replay-2026-05-31.md"
REGULAR_LANES = {
    "short_term",
    "swing",
    "bullish_momentum",
    "bullish_pullback_observation",
    "tracked_winner_primary",
    "tracked_winner_observation",
    "volatility_expansion_observation",
    "range_breakout_observation",
    "legacy_unlabeled",
}
CURRENT_PROFIT_HARVEST_LANES = {
    "bullish_pullback_observation",
    "tracked_winner_primary",
    "tracked_winner_observation",
}
LEGACY_MISSED_CLOSE_IDS = {26, 39, 44}
LOSS_BUCKET_THRESHOLDS = (50.0, 70.0, 80.0, 90.0, 95.0, 99.0)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def safe_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_date(value: Any) -> date | None:
    parsed = _parse_datetime(value)
    if parsed is not None:
        return parsed.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _days_held(position: dict[str, Any], review: dict[str, Any]) -> int:
    filled = _parse_date(position.get("filled_at"))
    reviewed_at = _parse_date(review.get("reviewed_at"))
    if filled is None or reviewed_at is None:
        return 0
    return max((reviewed_at - filled).days, 0)


def _configured_time_exit_day(position: dict[str, Any]) -> int:
    value = safe_float(position.get("time_exit_day"))
    if value is None or value <= 0:
        return 1
    return int(value)


def _configured_profit_target(position: dict[str, Any]) -> float:
    value = safe_float(position.get("profit_target_pct"))
    return value if value is not None and value > 0 else 100.0


def _configured_stop(position: dict[str, Any], cap: float = 90.0) -> float:
    value = safe_float(position.get("stop_loss_pct"))
    if value is None or value <= 0:
        return cap
    return min(value, cap)


@dataclass(frozen=True)
class ExitPolicy:
    policy_id: str
    label: str
    stop_loss_pct: float = 90.0
    profit_target_pct: float | None = None
    profit_harvest_lanes: str = "current"
    profit_harvest_trigger_pct: float | None = None
    giveback_trigger_pct: float | None = None
    giveback_pct: float = 20.0
    min_remaining_profit_pct: float = 15.0
    time_exit_day: int | None = None
    use_stored_sell: bool = False


POLICIES = [
    ExitPolicy("current_policy_replay", "Current stop/target/harvest/time policy"),
    ExitPolicy(
        "profit_harvest_all_lanes_50",
        "Add 50% profit harvest to all regular lanes",
        profit_harvest_lanes="all",
        profit_harvest_trigger_pct=50.0,
    ),
    ExitPolicy(
        "profit_harvest_all_lanes_35",
        "Add 35% profit harvest to all regular lanes",
        profit_harvest_lanes="all",
        profit_harvest_trigger_pct=35.0,
    ),
    ExitPolicy(
        "trailing_giveback_all_lanes_50_20",
        "Add 50% peak / 20pt giveback trailing exit to all regular lanes",
        profit_harvest_lanes="none",
        giveback_trigger_pct=50.0,
        giveback_pct=20.0,
        min_remaining_profit_pct=15.0,
    ),
    ExitPolicy("time_exit_7", "Force first executable time exit at 7 calendar days", time_exit_day=7),
    ExitPolicy("time_exit_10", "Force first executable time exit at 10 calendar days", time_exit_day=10),
    ExitPolicy("stop_90", "Executable stop grid: 90%", stop_loss_pct=90.0),
    ExitPolicy("stop_80", "Executable stop grid: 80%", stop_loss_pct=80.0),
    ExitPolicy("stop_70", "Tighten executable stop to 70%", stop_loss_pct=70.0),
    ExitPolicy("stop_60", "Executable stop grid: 60%", stop_loss_pct=60.0),
    ExitPolicy("stop_50", "Tighten executable stop to 50%", stop_loss_pct=50.0),
    ExitPolicy("stored_sell_recommendation", "Follow stored executable SELL reviews", use_stored_sell=True),
]


def _profit_harvest_enabled(policy: ExitPolicy, lane: str) -> bool:
    if policy.profit_harvest_lanes == "all":
        return True
    if policy.profit_harvest_lanes == "none":
        return False
    return lane in CURRENT_PROFIT_HARVEST_LANES


def _sell_reason(
    *,
    position: dict[str, Any],
    review: dict[str, Any],
    policy: ExitPolicy,
    lane: str,
    peak_pnl_pct: float,
) -> str | None:
    pnl = _review_pnl(review)
    if pnl is None:
        return None
    days_held = _days_held(position, review)
    if policy.use_stored_sell and str(review.get("recommendation") or "").upper() == "SELL":
        return "stored_executable_sell_recommendation"
    if pnl <= -_configured_stop(position, cap=policy.stop_loss_pct):
        return "stop_loss"
    target = policy.profit_target_pct if policy.profit_target_pct is not None else _configured_profit_target(position)
    if pnl >= target:
        return "profit_target"
    harvest_trigger = policy.profit_harvest_trigger_pct
    if harvest_trigger is None and policy.policy_id == "current_policy_replay":
        harvest_trigger = 50.0
    if (
        harvest_trigger is not None
        and _profit_harvest_enabled(policy, lane)
        and days_held >= 1
        and pnl >= harvest_trigger
    ):
        return "profit_harvest"
    giveback_trigger = policy.giveback_trigger_pct
    if giveback_trigger is None and policy.policy_id == "current_policy_replay" and lane in CURRENT_PROFIT_HARVEST_LANES:
        giveback_trigger = 50.0
    if (
        giveback_trigger is not None
        and days_held >= 1
        and peak_pnl_pct >= giveback_trigger
        and peak_pnl_pct - pnl >= policy.giveback_pct
        and pnl >= policy.min_remaining_profit_pct
    ):
        return "trailing_giveback"
    time_exit_day = policy.time_exit_day if policy.time_exit_day is not None else _configured_time_exit_day(position)
    if days_held >= time_exit_day:
        return "time_exit"
    return None


def executable_reviews(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = []
    for review in reviews:
        pnl = _review_pnl(review)
        if pnl is None or not _review_is_executable(review):
            continue
        candidates.append(review)
    return sorted(candidates, key=lambda item: str(item.get("reviewed_at") or ""))


def simulate_exit_policy(
    position: dict[str, Any],
    reviews: list[dict[str, Any]],
    policy: ExitPolicy,
) -> dict[str, Any]:
    lane = canonical_lane(position)
    executable = executable_reviews(reviews)
    if not executable:
        return {"status": "unreplayable", "reason": "no_executable_review_timeline"}
    peak_pnl = safe_float(position.get("peak_pnl_pct")) or -999999.0
    for review in executable:
        pnl = _review_pnl(review)
        if pnl is None:
            continue
        peak_pnl = max(peak_pnl, pnl)
        reason = _sell_reason(position=position, review=review, policy=policy, lane=lane, peak_pnl_pct=peak_pnl)
        if reason:
            return {
                "status": "closed",
                "reason": reason,
                "reviewed_at": str(review.get("reviewed_at")),
                "days_held": _days_held(position, review),
                "pnl_pct": round(float(pnl), 4),
                "exit_execution_price": review.get("exit_execution_price"),
                "exit_execution_basis": review.get("exit_execution_basis"),
            }
    last = executable[-1]
    last_pnl = _review_pnl(last)
    return {
        "status": "held_through_reviews",
        "reason": "no_policy_trigger",
        "reviewed_at": str(last.get("reviewed_at")),
        "days_held": _days_held(position, last),
        "pnl_pct": round(float(last_pnl), 4) if last_pnl is not None else None,
        "exit_execution_price": last.get("exit_execution_price"),
        "exit_execution_basis": last.get("exit_execution_basis"),
    }


def _summarize_pnls(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "priced": 0,
            "negative": 0,
            "positive_or_flat": 0,
            "loss_bucket_counts": _loss_bucket_counts(values),
            "avg_pnl_pct": None,
            "median_pnl_pct": None,
            "worst_pnl_pct": None,
            "best_pnl_pct": None,
        }
    negatives = [value for value in values if value < 0]
    return {
        "priced": len(values),
        "negative": len(negatives),
        "positive_or_flat": len(values) - len(negatives),
        "negative_rate_pct": round(len(negatives) / len(values) * 100.0, 1),
        "loss_bucket_counts": _loss_bucket_counts(values),
        "avg_pnl_pct": round(sum(values) / len(values), 2),
        "median_pnl_pct": round(median(values), 2),
        "worst_pnl_pct": round(min(values), 2),
        "best_pnl_pct": round(max(values), 2),
    }


def _loss_bucket_counts(values: list[float]) -> dict[str, int]:
    return {f"loss_le_{int(threshold)}_pct": sum(1 for value in values if value <= -threshold) for threshold in LOSS_BUCKET_THRESHOLDS}


def _loss_bucket_deltas(policy_summary: dict[str, Any], baseline_summary: dict[str, Any]) -> dict[str, int | None]:
    policy_counts = policy_summary.get("loss_bucket_counts") or {}
    baseline_counts = baseline_summary.get("loss_bucket_counts") or {}
    deltas: dict[str, int | None] = {}
    for threshold in LOSS_BUCKET_THRESHOLDS:
        key = f"loss_le_{int(threshold)}_pct"
        policy_value = policy_counts.get(key)
        baseline_value = baseline_counts.get(key)
        deltas[key] = (
            int(policy_value) - int(baseline_value)
            if policy_value is not None and baseline_value is not None
            else None
        )
    return deltas


def _summarize_stop_loss_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "count": 0,
            "avg_policy_pnl_pct": None,
            "avg_baseline_pnl_pct": None,
            "avg_delta_vs_baseline_pct": None,
            "median_delta_vs_baseline_pct": None,
            "improved_count": 0,
            "worse_count": 0,
            "winner_flipped_to_loss_count": 0,
            "loss_bucket_counts": _loss_bucket_counts([]),
        }
    policy_values = [float(row["policy_pnl_pct"]) for row in rows if row.get("policy_pnl_pct") is not None]
    baseline_values = [float(row["baseline_pnl_pct"]) for row in rows if row.get("baseline_pnl_pct") is not None]
    deltas = [float(row["delta_vs_baseline_pct"]) for row in rows if row.get("delta_vs_baseline_pct") is not None]
    winner_flips = sum(
        1
        for row in rows
        if row.get("baseline_pnl_pct") is not None
        and row.get("policy_pnl_pct") is not None
        and float(row["baseline_pnl_pct"]) >= 0
        and float(row["policy_pnl_pct"]) < 0
    )
    return {
        "count": len(rows),
        "avg_policy_pnl_pct": round(sum(policy_values) / len(policy_values), 2) if policy_values else None,
        "avg_baseline_pnl_pct": round(sum(baseline_values) / len(baseline_values), 2) if baseline_values else None,
        "avg_delta_vs_baseline_pct": round(sum(deltas) / len(deltas), 2) if deltas else None,
        "median_delta_vs_baseline_pct": round(median(deltas), 2) if deltas else None,
        "improved_count": sum(1 for value in deltas if value > 0.0001),
        "worse_count": sum(1 for value in deltas if value < -0.0001),
        "winner_flipped_to_loss_count": winner_flips,
        "loss_bucket_counts": _loss_bucket_counts(policy_values),
    }


def _summarize_stop_loss_groups(
    rows: list[dict[str, Any]],
    *,
    group_key: str,
    limit: int | None = None,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(group_key) or "unknown")].append(row)
    ordered = sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))
    if limit is not None:
        ordered = ordered[:limit]
    return {key: _summarize_stop_loss_rows(group_rows) for key, group_rows in ordered}


def _baseline_value(position: dict[str, Any], reviews: list[dict[str, Any]]) -> float | None:
    value = pnl_pct(position)
    if value is not None:
        return value
    executable = executable_reviews(reviews)
    if executable:
        return _review_pnl(executable[-1])
    return None


def _regular_position(position: dict[str, Any]) -> bool:
    lane = canonical_lane(position)
    return lane in REGULAR_LANES


def build_report(
    positions: list[dict[str, Any]],
    *,
    reviews_by_position: dict[int, list[dict[str, Any]]],
    policies: list[ExitPolicy] | None = None,
) -> dict[str, Any]:
    policies = policies or POLICIES
    regular_positions = [position for position in positions if _regular_position(position)]
    replayable = [
        position
        for position in regular_positions
        if executable_reviews(reviews_by_position.get(int(position.get("id") or 0), []))
    ]
    baseline_values: dict[int, float] = {}
    for position in replayable:
        position_id = int(position.get("id") or 0)
        baseline = _baseline_value(position, reviews_by_position.get(position_id, []))
        if baseline is not None:
            baseline_values[position_id] = float(baseline)

    baseline_summary = _summarize_pnls(list(baseline_values.values()))
    policy_results = []
    row_results = []
    for policy in policies:
        pnls: list[float] = []
        closed_count = 0
        reasons: Counter[str] = Counter()
        improvements: list[float] = []
        worse_count = 0
        winner_loss_count = 0
        legacy_hits = []
        policy_rows: list[dict[str, Any]] = []
        for position in replayable:
            position_id = int(position.get("id") or 0)
            result = simulate_exit_policy(position, reviews_by_position.get(position_id, []), policy)
            value = safe_float(result.get("pnl_pct"))
            if value is None:
                continue
            pnls.append(value)
            if result["status"] == "closed":
                closed_count += 1
            reasons[str(result.get("reason") or result["status"])] += 1
            baseline = baseline_values.get(position_id)
            delta = None
            if baseline is not None:
                delta = value - baseline
                improvements.append(delta)
                if delta < -0.0001:
                    worse_count += 1
                if baseline >= 0 and value < 0:
                    winner_loss_count += 1
            row = {
                "policy_id": policy.policy_id,
                "trade_id": position_id,
                "ticker": position.get("ticker"),
                "lane": canonical_lane(position),
                "baseline_pnl_pct": round(baseline, 4) if baseline is not None else None,
                "policy_pnl_pct": round(value, 4),
                "delta_vs_baseline_pct": round(delta, 4) if delta is not None else None,
                "status": result["status"],
                "reason": result.get("reason"),
                "reviewed_at": result.get("reviewed_at"),
                "days_held": result.get("days_held"),
                "legacy_missed_close_target": position_id in LEGACY_MISSED_CLOSE_IDS,
            }
            row_results.append(row)
            policy_rows.append(row)
            if position_id in LEGACY_MISSED_CLOSE_IDS:
                legacy_hits.append(row)
        summary = _summarize_pnls(pnls)
        avg_delta = round(sum(improvements) / len(improvements), 2) if improvements else None
        median_delta = round(median(improvements), 2) if improvements else None
        stop_loss_rows = [row for row in policy_rows if row.get("reason") == "stop_loss"]
        policy_results.append(
            {
                "policy_id": policy.policy_id,
                "label": policy.label,
                "summary": summary,
                "loss_bucket_delta_vs_baseline": _loss_bucket_deltas(summary, baseline_summary),
                "closed_count": closed_count,
                "reason_counts": dict(reasons.most_common()),
                "avg_delta_vs_baseline_pct": avg_delta,
                "median_delta_vs_baseline_pct": median_delta,
                "improved_count": sum(1 for value in improvements if value > 0.0001),
                "worse_count": worse_count,
                "winner_flipped_to_loss_count": winner_loss_count,
                "stop_loss_trigger_summary": _summarize_stop_loss_rows(stop_loss_rows),
                "stop_loss_trigger_by_lane": _summarize_stop_loss_groups(stop_loss_rows, group_key="lane"),
                "stop_loss_trigger_by_ticker": _summarize_stop_loss_groups(stop_loss_rows, group_key="ticker", limit=12),
                "legacy_targets": legacy_hits,
                "recommendation": _policy_recommendation(
                    summary,
                    baseline_summary,
                    avg_delta,
                    winner_loss_count,
                    diagnostic_only=policy.use_stored_sell,
                ),
            }
        )
    return {
        "generated_at_utc": _utc_now_iso(),
        "scope": "regular_supervised_trading_desk_exit_policy_replay",
        "evidence_standard": "stored executable review rows only; non-executable marks, last trades, midpoint-only rows, and unpriced rows are excluded",
        "inventory": {
            "regular_positions": len(regular_positions),
            "replayable_positions_with_executable_reviews": len(replayable),
            "baseline_positions_with_pnl": len(baseline_values),
            "legacy_missed_close_ids": sorted(LEGACY_MISSED_CLOSE_IDS),
        },
        "baseline": baseline_summary,
        "policies": sorted(
            policy_results,
            key=lambda row: (
                row["recommendation"]["rank"],
                -(row["avg_delta_vs_baseline_pct"] if row["avg_delta_vs_baseline_pct"] is not None else -999999),
            ),
        ),
        "rows": row_results,
    }


def _policy_recommendation(
    summary: dict[str, Any],
    baseline: dict[str, Any],
    avg_delta: float | None,
    winner_loss_count: int,
    *,
    diagnostic_only: bool = False,
) -> dict[str, Any]:
    baseline_avg = safe_float(baseline.get("avg_pnl_pct"))
    avg = safe_float(summary.get("avg_pnl_pct"))
    baseline_median = safe_float(baseline.get("median_pnl_pct"))
    med = safe_float(summary.get("median_pnl_pct"))
    baseline_negative = safe_float(baseline.get("negative_rate_pct"))
    negative = safe_float(summary.get("negative_rate_pct"))
    if diagnostic_only and avg_delta is not None and avg_delta > 0:
        return {"status": "research_candidate", "rank": 1}
    if (
        avg_delta is not None
        and avg_delta > 2.0
        and avg is not None
        and baseline_avg is not None
        and avg > baseline_avg
        and med is not None
        and baseline_median is not None
        and med >= baseline_median
        and (baseline_negative is None or negative is None or negative <= baseline_negative)
        and winner_loss_count == 0
    ):
        return {"status": "promote_candidate", "rank": 0}
    if avg_delta is not None and avg_delta > 0 and winner_loss_count <= 2:
        return {"status": "research_candidate", "rank": 1}
    return {"status": "reject_current_shape", "rank": 2}


def _load_reviews(repository: Any) -> dict[int, list[dict[str, Any]]]:
    if not hasattr(repository, "_connect"):
        return {}
    query = """
        SELECT
            position_id,
            reviewed_at,
            pricing_source,
            current_option_price,
            current_pnl_pct,
            gross_pnl_pct,
            net_pnl_pct,
            exit_execution_price,
            exit_execution_basis,
            recommendation,
            reason,
            metrics_snapshot
        FROM position_reviews
        ORDER BY position_id, reviewed_at, id
    """
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    with repository._connect() as conn:  # type: ignore[attr-defined]
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    for row in rows:
        item = dict(row)
        item["metrics_snapshot"] = _as_mapping(item.get("metrics_snapshot"))
        grouped[int(item["position_id"])].append(item)
    return dict(grouped)


def load_current_report() -> dict[str, Any]:
    load_local_env(ROOT)
    repository = create_positions_repository(os.getenv("DATABASE_URL"))
    if not getattr(repository, "is_available", False):
        raise RuntimeError(getattr(repository, "error_message", "Tracked positions repository is unavailable."))
    return build_report(repository.list_positions("all"), reviews_by_position=_load_reviews(repository))


def _fmt_pct(value: Any) -> str:
    number = safe_float(value)
    return "" if number is None else f"{number}%"


def markdown_report(report: dict[str, Any]) -> str:
    baseline_buckets = report["baseline"].get("loss_bucket_counts") or {}
    lines = [
        "# Trading Desk Exit Policy Replay - 2026-05-31",
        "",
        "This is a read-only replay of Trading Desk exit policies over stored executable review rows. It excludes unpriced reviews, last-trade/display-only marks, midpoint-only rows, and rows without executable exit evidence.",
        "",
        "## Inventory",
        "",
        f"- Regular positions: `{report['inventory']['regular_positions']}`",
        f"- Replayable positions with executable review timelines: `{report['inventory']['replayable_positions_with_executable_reviews']}`",
        f"- Baseline positions with P&L: `{report['inventory']['baseline_positions_with_pnl']}`",
        "",
        "## Baseline",
        "",
        "| Priced | Negative | Positive/Flat | Avg P&L | Median P&L | Negative Rate |",
        "|---:|---:|---:|---:|---:|---:|",
        (
            f"| {report['baseline']['priced']} | {report['baseline']['negative']} | "
            f"{report['baseline']['positive_or_flat']} | {report['baseline']['avg_pnl_pct']}% | "
            f"{report['baseline']['median_pnl_pct']}% | {report['baseline'].get('negative_rate_pct')}% |"
        ),
        "",
        "## Deep-Loss Buckets",
        "",
        "| Scope | <= -50% | <= -70% | <= -80% | <= -90% | <= -95% | <= -99% |",
        "|---|---:|---:|---:|---:|---:|---:|",
        (
            f"| Baseline | {baseline_buckets.get('loss_le_50_pct', 0)} | "
            f"{baseline_buckets.get('loss_le_70_pct', 0)} | {baseline_buckets.get('loss_le_80_pct', 0)} | "
            f"{baseline_buckets.get('loss_le_90_pct', 0)} | {baseline_buckets.get('loss_le_95_pct', 0)} | "
            f"{baseline_buckets.get('loss_le_99_pct', 0)} |"
        ),
        "",
        "## Policy Results",
        "",
        "| Policy | Recommendation | Avg Delta | Avg P&L | Negatives | <= -90% | <= -95% | <= -99% | Stop Rows | Stop Avg Delta | Winner Losses | Top Reasons |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for policy in report["policies"]:
        reasons = ", ".join(f"{key}:{value}" for key, value in list(policy["reason_counts"].items())[:4])
        buckets = policy["summary"].get("loss_bucket_counts") or {}
        stop_summary = policy.get("stop_loss_trigger_summary") or {}
        lines.append(
            f"| `{policy['policy_id']}` | {policy['recommendation']['status']} | "
            f"{_fmt_pct(policy['avg_delta_vs_baseline_pct'])} | {_fmt_pct(policy['summary']['avg_pnl_pct'])} | "
            f"{policy['summary']['negative']} | {buckets.get('loss_le_90_pct', 0)} | "
            f"{buckets.get('loss_le_95_pct', 0)} | {buckets.get('loss_le_99_pct', 0)} | "
            f"{stop_summary.get('count', 0)} | {_fmt_pct(stop_summary.get('avg_delta_vs_baseline_pct'))} | "
            f"{policy['winner_flipped_to_loss_count']} | {reasons} |"
        )
    lines.extend(
        [
            "",
            "## Stop-Loss Trigger Detail",
            "",
            "| Policy | Stop Rows | Stop Avg P&L | Stop Avg Baseline | Stop Avg Delta | Stop <= -90% | Stop Winner Losses | Top Stop Lanes |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for policy in report["policies"]:
        stop_summary = policy.get("stop_loss_trigger_summary") or {}
        if not stop_summary.get("count"):
            continue
        stop_buckets = stop_summary.get("loss_bucket_counts") or {}
        lane_bits = []
        for lane, lane_summary in list((policy.get("stop_loss_trigger_by_lane") or {}).items())[:4]:
            lane_bits.append(f"{lane}:{lane_summary.get('count')}")
        lines.append(
            f"| `{policy['policy_id']}` | {stop_summary.get('count')} | "
            f"{_fmt_pct(stop_summary.get('avg_policy_pnl_pct'))} | {_fmt_pct(stop_summary.get('avg_baseline_pnl_pct'))} | "
            f"{_fmt_pct(stop_summary.get('avg_delta_vs_baseline_pct'))} | {stop_buckets.get('loss_le_90_pct', 0)} | "
            f"{stop_summary.get('winner_flipped_to_loss_count', 0)} | {', '.join(lane_bits)} |"
        )
    lines.extend(
        [
            "",
            "## Legacy Rows 26, 39, 44",
            "",
            "| Policy | Trade | Ticker | Lane | Baseline | Replay P&L | Delta | Reason | Reviewed At |",
            "|---|---:|---|---|---:|---:|---:|---|---|",
        ]
    )
    for policy in report["policies"]:
        for row in policy["legacy_targets"]:
            lines.append(
                f"| `{policy['policy_id']}` | {row['trade_id']} | {row['ticker']} | `{row['lane']}` | "
                f"{row['baseline_pnl_pct']}% | {row['policy_pnl_pct']}% | {row['delta_vs_baseline_pct']}% | "
                f"{row['reason']} | {row['reviewed_at']} |"
            )
    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            "Do not promote an exit rule unless it improves average and median executable P&L, reduces or holds the deep-loss buckets, does not increase the negative rate, and does not convert stored winners into losses. Treat legacy missed-auto-close rows as a separate diagnostic unless the same rule improves the broader executable-review universe.",
            "",
            "This stored-review replay cannot answer whether tighter stops would have saved current-policy historical-paper rows that have no executable review timeline. Those rows need a separate exact OPRA/NBBO historical stop replay before live review stops are changed.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], output_dir: Path, doc_path: Path) -> tuple[Path, Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"trading_desk_exit_policy_replay_{stamp}.json"
    latest_json_path = output_dir / "trading_desk_exit_policy_replay_latest.json"
    csv_path = output_dir / f"trading_desk_exit_policy_replay_{stamp}.csv"
    latest_csv_path = output_dir / "trading_desk_exit_policy_replay_latest.csv"
    payload = json.dumps(report, indent=2, sort_keys=True, default=str)
    json_path.write_text(payload, encoding="utf-8")
    latest_json_path.write_text(payload, encoding="utf-8")
    fieldnames = [
        "policy_id",
        "trade_id",
        "ticker",
        "lane",
        "baseline_pnl_pct",
        "policy_pnl_pct",
        "delta_vs_baseline_pct",
        "status",
        "reason",
        "reviewed_at",
        "days_held",
        "legacy_missed_close_target",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in report["rows"]:
            writer.writerow({key: row.get(key) for key in fieldnames})
    latest_csv_path.write_text(csv_path.read_text(encoding="utf-8"), encoding="utf-8")
    doc_path.write_text(markdown_report(report), encoding="utf-8")
    return json_path, latest_json_path, csv_path, doc_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay Trading Desk exit policies over executable review timelines.")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--doc-path", default=str(DEFAULT_DOC))
    args = parser.parse_args(argv)
    report = load_current_report()
    if not args.no_write:
        paths = write_outputs(report, Path(args.output_dir), Path(args.doc_path))
        print("Wrote exit replay artifacts:")
        for path in paths:
            print(path)
    print(json.dumps({"inventory": report["inventory"], "baseline": report["baseline"], "policies": report["policies"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
