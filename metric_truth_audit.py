from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import median
from typing import Iterable


DEFAULT_RESULT_PATH = Path(__file__).resolve().parent / "wfo_results.json"


def _safe_number(value, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number) or math.isinf(number):
        return default
    return number


def _pct(part: int, whole: int) -> float:
    if whole <= 0:
        return 0.0
    return round(part / whole * 100.0, 1)


def _round(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _profit_factor(pnl_values: Iterable[float]) -> float:
    wins = [value for value in pnl_values if value > 0]
    losses = [value for value in pnl_values if value <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    if gross_loss <= 0:
        return round(gross_win, 2) if gross_win > 0 else 0.0
    return round(gross_win / gross_loss, 2)


def _metric_present(trades: list[dict], metric_key: str) -> bool:
    return any(metric_key in trade and trade.get(metric_key) is not None for trade in trades)


def load_result(path: str | Path | None = None) -> dict:
    result_path = Path(path or DEFAULT_RESULT_PATH)
    if not result_path.exists():
        raise FileNotFoundError(f"No result file found at {result_path}")
    with result_path.open("r", encoding="utf8") as handle:
        return json.load(handle)


def summarize_trade_subset(label: str, trades: list[dict], total_trades: int) -> dict:
    pnl_values = [_safe_number(trade.get("pnl_pct")) for trade in trades]
    profitable = [value for value in pnl_values if value > 0]
    directionally_correct = [trade for trade in trades if bool(trade.get("directional_correct"))]
    full_hits = [trade for trade in trades if str(trade.get("prediction_outcome") or "").lower() == "hit"]
    avg_direction_score = (
        sum(_safe_number(trade.get("direction_score")) for trade in trades) / len(trades)
        if trades and _metric_present(trades, "direction_score")
        else None
    )

    return {
        "label": label,
        "trades": len(trades),
        "share_of_total_pct": _pct(len(trades), total_trades),
        "win_rate_pct": _pct(len(profitable), len(trades)),
        "directional_accuracy_pct": _pct(len(directionally_correct), len(trades)),
        "full_hit_rate_pct": _pct(len(full_hits), len(trades)),
        "profit_factor": _profit_factor(pnl_values),
        "avg_pnl_pct": _round(sum(pnl_values) / len(pnl_values), 2) if pnl_values else 0.0,
        "median_pnl_pct": _round(median(pnl_values), 2) if pnl_values else 0.0,
        "avg_direction_score": _round(avg_direction_score, 1) if avg_direction_score is not None else None,
    }


def _bucket_bounds(lower: int, upper: int) -> str:
    return f"{lower:02d}-{upper:02d}"


def build_metric_buckets(
    trades: list[dict],
    metric_key: str,
    bucket_size: int = 10,
    min_trades: int = 20,
) -> list[dict]:
    if bucket_size <= 0:
        raise ValueError("bucket_size must be positive")

    buckets: dict[str, list[dict]] = {}
    for trade in trades:
        if trade.get(metric_key) is None:
            continue
        value = max(0.0, min(100.0, _safe_number(trade.get(metric_key))))
        lower = int(value // bucket_size) * bucket_size
        upper = min(99, lower + bucket_size - 1)
        label = _bucket_bounds(lower, upper)
        buckets.setdefault(label, []).append(trade)

    ordered_labels = []
    for lower in range(0, 100, bucket_size):
        upper = min(99, lower + bucket_size - 1)
        ordered_labels.append(_bucket_bounds(lower, upper))

    summarized = []
    for label in ordered_labels:
        summary = summarize_trade_subset(label, buckets.get(label, []), len(trades))
        summary["sparse"] = summary["trades"] < min_trades
        if summary["avg_direction_score"] is not None:
            realized = (summary["directional_accuracy_pct"] or 0.0) / 100.0
            predicted = summary["avg_direction_score"] / 100.0
            summary["calibration_gap_pct"] = _round((realized - predicted) * 100.0, 1)
        summarized.append(summary)
    return summarized


def build_metric_floor_analysis(
    trades: list[dict],
    metric_key: str,
    floors: Iterable[int],
    min_trades: int = 20,
) -> list[dict]:
    summaries = []
    for floor in sorted({int(floor) for floor in floors}):
        subset = [trade for trade in trades if _safe_number(trade.get(metric_key), default=-1) >= floor]
        summary = summarize_trade_subset(f"{metric_key}>={floor}", subset, len(trades))
        summary["floor"] = floor
        summary["metric"] = metric_key
        summary["sparse"] = summary["trades"] < min_trades
        summaries.append(summary)
    return summaries


def _sequence_signal(bucket_summaries: list[dict], value_key: str, min_trades: int) -> dict:
    dense = [item for item in bucket_summaries if item["trades"] >= min_trades]
    if len(dense) < 2:
        return {"dense_buckets": len(dense), "improving_steps": 0, "regressing_steps": 0}

    improving = 0
    regressing = 0
    for previous, current in zip(dense, dense[1:]):
        prev_value = _safe_number(previous.get(value_key))
        cur_value = _safe_number(current.get(value_key))
        if cur_value > prev_value:
            improving += 1
        elif cur_value < prev_value:
            regressing += 1
    return {
        "dense_buckets": len(dense),
        "improving_steps": improving,
        "regressing_steps": regressing,
    }


def _best_floor(floors: list[dict], baseline: dict, min_trades: int) -> dict | None:
    dense = [
        item for item in floors
        if item["trades"] >= min_trades
        and item["profit_factor"] >= baseline["profit_factor"]
        and item["avg_pnl_pct"] >= baseline["avg_pnl_pct"]
        and (
            item["profit_factor"] > baseline["profit_factor"]
            or item["avg_pnl_pct"] > baseline["avg_pnl_pct"]
            or item["win_rate_pct"] > baseline["win_rate_pct"]
        )
    ]
    if not dense:
        return None
    return sorted(
        dense,
        key=lambda item: (
            _safe_number(item["profit_factor"]),
            _safe_number(item["avg_pnl_pct"]),
            _safe_number(item["win_rate_pct"]),
            -item["floor"],
        ),
        reverse=True,
    )[0]


def build_metric_truth_report(
    result: dict,
    bucket_size: int = 10,
    min_trades: int = 20,
    score_floors: Iterable[int] = (40, 50, 60, 70, 80),
    quality_floors: Iterable[int] = (40, 50, 60, 70),
    tech_floors: Iterable[int] = (50, 60, 70, 80),
    ev_floors: Iterable[int] = (0, 5, 10, 20, 30, 40),
) -> dict:
    trades = list(result.get("trades") or [])
    truth_source = str(result.get("truth_source") or "synthetic_research")
    overall = summarize_trade_subset("overall", trades, len(trades))

    metric_buckets = {}
    metric_floors = {}
    for metric_key, floors in (
        ("direction_score", score_floors),
        ("quality_score", quality_floors),
        ("tech_score", tech_floors),
        ("ev", ev_floors),
    ):
        if _metric_present(trades, metric_key):
            metric_buckets[metric_key] = build_metric_buckets(
                trades=trades,
                metric_key=metric_key,
                bucket_size=bucket_size,
                min_trades=min_trades,
            )
            metric_floors[metric_key] = build_metric_floor_analysis(
                trades=trades,
                metric_key=metric_key,
                floors=floors,
                min_trades=min_trades,
            )

    metric_health = {}
    for metric_key, buckets in metric_buckets.items():
        metric_health[metric_key] = {
            "avg_pnl_trend": _sequence_signal(buckets, "avg_pnl_pct", min_trades),
            "win_rate_trend": _sequence_signal(buckets, "directional_accuracy_pct", min_trades),
            "best_floor": _best_floor(metric_floors.get(metric_key, []), overall, min_trades),
        }

    risk_flags: list[str] = []
    recommendations: list[str] = []

    if overall["profit_factor"] < 1.0:
        risk_flags.append("Overall profit factor is below 1.0, so the current replay is not profitable after losses.")
    if overall["avg_pnl_pct"] <= 0:
        risk_flags.append("Average trade P&L is not positive, so the current metric stack is not producing positive expectancy.")
    if overall["directional_accuracy_pct"] < 50.0:
        risk_flags.append("Directional accuracy is below 50%, so the signal does not beat a naive coin-flip bar yet.")

    direction_buckets = metric_buckets.get("direction_score", [])
    dense_direction_buckets = [item for item in direction_buckets if item["trades"] >= min_trades]
    if len(dense_direction_buckets) >= 2:
        low_band = dense_direction_buckets[0]
        high_band = dense_direction_buckets[-1]
        if _safe_number(high_band["avg_pnl_pct"]) <= _safe_number(low_band["avg_pnl_pct"]):
            risk_flags.append("Higher direction-score bands are not outperforming lower-score bands on average P&L.")
        if _safe_number(high_band["directional_accuracy_pct"]) <= _safe_number(low_band["directional_accuracy_pct"]):
            risk_flags.append("Higher direction-score bands are not improving realized directional accuracy.")

        calibration_gaps = [
            abs(_safe_number(item.get("calibration_gap_pct")))
            for item in dense_direction_buckets
            if item.get("calibration_gap_pct") is not None
        ]
        if calibration_gaps:
            avg_gap = sum(calibration_gaps) / len(calibration_gaps)
            if avg_gap >= 10.0:
                risk_flags.append(
                    "Direction score is materially miscalibrated versus realized directional accuracy, so it should not be treated as a direct probability."
                )

    for metric_key, health in metric_health.items():
        best_floor = health.get("best_floor")
        if best_floor:
            recommendations.append(
                f"Best current threshold candidate is {metric_key}>={best_floor['floor']} "
                f"(PF {best_floor['profit_factor']}, avg P&L {best_floor['avg_pnl_pct']}%)."
            )

    if not recommendations:
        recommendations.append(
            "No metric floor currently improves both profit factor and average P&L with enough sample size."
        )

    return {
        "generated_at": result.get("run_at"),
        "source": {
            "run_at": result.get("run_at"),
            "mode": result.get("mode"),
            "lookback_years": result.get("lookback_years"),
            "pricing_lane": result.get("pricing_lane"),
            "playbook": result.get("playbook"),
            "truth_source": truth_source,
            "quote_coverage_pct": result.get("quote_coverage_pct"),
            "priced_trade_count": result.get("priced_trade_count"),
            "unpriced_trade_count": result.get("unpriced_trade_count"),
            "entry_quote_time_et": result.get("entry_quote_time_et"),
            "exit_quote_time_et": result.get("exit_quote_time_et"),
            "total_days": result.get("total_days"),
            "total_trades": len(trades),
        },
        "quality_bar": {
            "min_trades": int(min_trades),
            "bucket_size": int(bucket_size),
        },
        "overall": overall,
        "metric_buckets": metric_buckets,
        "metric_floors": metric_floors,
        "metric_health": metric_health,
        "risk_flags": risk_flags,
        "recommendations": recommendations,
    }
