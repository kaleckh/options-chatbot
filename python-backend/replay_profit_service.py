from __future__ import annotations

import json
from typing import Any

from backend_route_context import BackendRouteContext


def build_backtest_report(
    ctx: BackendRouteContext,
    truth_lane: str | None,
    min_trades: int,
) -> dict[str, Any]:
    return ctx.build_prediction_replay_report(
        result=ctx._cached_preferred_results_by_truth_lane(truth_lane),
        min_trades=min_trades,
    )


def build_metric_truth_report(
    ctx: BackendRouteContext,
    truth_lane: str | None,
    min_trades: int,
    bucket_size: int,
) -> dict[str, Any]:
    result = ctx._cached_preferred_results_by_truth_lane(truth_lane)
    if not result:
        return {"error": "No backtest results found"}
    return ctx.build_metric_truth_report(
        result=result,
        min_trades=min_trades,
        bucket_size=bucket_size,
    )


def build_backtest_experiments(
    ctx: BackendRouteContext,
    body: dict[str, Any],
) -> dict[str, Any]:
    return ctx.build_options_experiment_matrix(
        result=ctx._cached_preferred_results_by_truth_lane(body.get("truth_lane")),
        min_trades=body.get("min_trades", 20),
        score_floors=body.get("score_floors"),
        max_tickers=body.get("max_tickers", 8),
        max_sectors=body.get("max_sectors", 8),
        min_profit_factor=body.get("min_profit_factor", 1.05),
        min_directional_accuracy_pct=body.get("min_directional_accuracy_pct", 50.0),
    )


def build_backtest_profitability_forensics(
    ctx: BackendRouteContext,
    min_trades: int,
    truth_lane: str | None,
) -> dict[str, Any]:
    return ctx.build_options_profitability_forensics(
        result=ctx._cached_preferred_results_by_truth_lane(truth_lane),
        min_trades=min_trades,
    )


def build_backtest_stability(
    ctx: BackendRouteContext,
    min_trades: int,
    min_profit_factor: float,
    truth_lane: str | None,
) -> dict[str, Any]:
    return ctx.build_options_stability_report(
        result=ctx._cached_preferred_results_by_truth_lane(truth_lane),
        min_trades=min_trades,
        min_profit_factor=min_profit_factor,
    )


def build_live_trade_policy_report(
    ctx: BackendRouteContext,
    min_trades: int,
    max_tickers: int,
    max_sectors: int,
    min_profit_factor: float,
    min_directional_accuracy_pct: float,
    truth_lane: str | None,
) -> dict[str, Any]:
    return ctx.build_live_options_trade_policy(
        truth_lane=truth_lane,
        min_trades=min_trades,
        max_tickers=max_tickers,
        max_sectors=max_sectors,
        min_profit_factor=min_profit_factor,
        min_directional_accuracy_pct=min_directional_accuracy_pct,
    )


def build_playbook_exit_audit_report(
    ctx: BackendRouteContext,
    playbook: str,
    min_trades: int,
    max_tickers: int,
    max_sectors: int,
    min_profit_factor: float,
    min_directional_accuracy_pct: float,
    truth_lane: str | None,
) -> dict[str, Any]:
    return ctx.build_playbook_exit_audit(
        playbook=playbook,
        truth_lane=truth_lane,
        min_trades=min_trades,
        max_tickers=max_tickers,
        max_sectors=max_sectors,
        min_profit_factor=min_profit_factor,
        min_directional_accuracy_pct=min_directional_accuracy_pct,
    )


def build_truth_lane_comparison_report(
    ctx: BackendRouteContext,
    truth_lane: str | None,
) -> dict[str, Any]:
    return ctx.build_truth_lane_comparison(truth_lane=truth_lane)


def cached_backtest_report(
    ctx: BackendRouteContext,
    truth_lane: str | None,
    min_trades: int,
) -> dict[str, Any]:
    key = ("backtest_report", ctx._preferred_results_cache_key(truth_lane), int(min_trades))
    return ctx._cached_readonly_report(key, lambda: build_backtest_report(ctx, truth_lane, min_trades))


def cached_metric_truth_report(
    ctx: BackendRouteContext,
    truth_lane: str | None,
    min_trades: int,
    bucket_size: int,
) -> dict[str, Any]:
    key = (
        "metric_truth_report",
        ctx._preferred_results_cache_key(truth_lane),
        int(min_trades),
        int(bucket_size),
    )
    return ctx._cached_readonly_report(
        key,
        lambda: build_metric_truth_report(ctx, truth_lane, min_trades, bucket_size),
    )


def cached_backtest_experiments(
    ctx: BackendRouteContext,
    body: dict[str, Any],
) -> dict[str, Any]:
    key = (
        "backtest_experiments",
        ctx._preferred_results_cache_key(body.get("truth_lane")),
        json.dumps(body, sort_keys=True, default=str),
    )
    return ctx._cached_readonly_report(key, lambda: build_backtest_experiments(ctx, body))


def cached_backtest_profitability_forensics(
    ctx: BackendRouteContext,
    min_trades: int,
    truth_lane: str | None,
) -> dict[str, Any]:
    key = (
        "backtest_profitability_forensics",
        ctx._preferred_results_cache_key(truth_lane),
        int(min_trades),
    )
    return ctx._cached_readonly_report(
        key,
        lambda: build_backtest_profitability_forensics(ctx, min_trades, truth_lane),
    )


def cached_backtest_stability(
    ctx: BackendRouteContext,
    min_trades: int,
    min_profit_factor: float,
    truth_lane: str | None,
) -> dict[str, Any]:
    key = (
        "backtest_stability",
        ctx._preferred_results_cache_key(truth_lane),
        int(min_trades),
        float(min_profit_factor),
    )
    return ctx._cached_readonly_report(
        key,
        lambda: build_backtest_stability(ctx, min_trades, min_profit_factor, truth_lane),
    )


def cached_live_trade_policy_report(
    ctx: BackendRouteContext,
    min_trades: int,
    max_tickers: int,
    max_sectors: int,
    min_profit_factor: float,
    min_directional_accuracy_pct: float,
    truth_lane: str | None,
) -> dict[str, Any]:
    key = (
        "live_trade_policy",
        ctx._preferred_results_cache_key(truth_lane),
        int(min_trades),
        int(max_tickers),
        int(max_sectors),
        float(min_profit_factor),
        float(min_directional_accuracy_pct),
    )
    return ctx._cached_readonly_report(
        key,
        lambda: build_live_trade_policy_report(
            ctx,
            min_trades,
            max_tickers,
            max_sectors,
            min_profit_factor,
            min_directional_accuracy_pct,
            truth_lane,
        ),
    )


def cached_playbook_exit_audit_report(
    ctx: BackendRouteContext,
    playbook: str,
    min_trades: int,
    max_tickers: int,
    max_sectors: int,
    min_profit_factor: float,
    min_directional_accuracy_pct: float,
    truth_lane: str | None,
) -> dict[str, Any]:
    key = (
        "playbook_exit_audit",
        ctx._preferred_results_cache_key(truth_lane),
        str(playbook),
        int(min_trades),
        int(max_tickers),
        int(max_sectors),
        float(min_profit_factor),
        float(min_directional_accuracy_pct),
    )
    return ctx._cached_readonly_report(
        key,
        lambda: build_playbook_exit_audit_report(
            ctx,
            playbook,
            min_trades,
            max_tickers,
            max_sectors,
            min_profit_factor,
            min_directional_accuracy_pct,
            truth_lane,
        ),
    )


def cached_truth_lane_comparison_report(
    ctx: BackendRouteContext,
    truth_lane: str | None,
) -> dict[str, Any]:
    key = ("truth_lane_comparison", ctx._preferred_results_cache_key(truth_lane))
    return ctx._cached_readonly_report(key, lambda: build_truth_lane_comparison_report(ctx, truth_lane))


def build_backtest_summary(
    ctx: BackendRouteContext,
    truth_lane: str | None,
    min_trades: int,
    bucket_size: int,
) -> dict[str, Any]:
    return {
        "last": ctx._cached_last_results_by_truth_lane(truth_lane) or {"error": "No backtest results found"},
        "report": cached_backtest_report(ctx, truth_lane, min_trades),
        "metricTruth": cached_metric_truth_report(ctx, truth_lane, min_trades, bucket_size),
        "profitabilityForensics": cached_backtest_profitability_forensics(ctx, min_trades, truth_lane),
        "comparison": cached_truth_lane_comparison_report(ctx, truth_lane),
    }
