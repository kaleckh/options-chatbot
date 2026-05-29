from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import wfo_optimizer as wfo
from exact_contract_accounting import is_exact_contract_resolution


DEFAULT_OUTPUT_ROOT = ROOT / "data" / "profitability-lab" / "tracked-winner-research-sweep"
TRACKED_WINNER_SYMBOLS = ["SPY", "GOOGL", "XLK", "DIA", "NVDA"]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _pnl(trade: dict[str, Any]) -> float:
    return _num(trade.get("net_pnl_pct", trade.get("pnl_pct")))


def _metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    values = [_pnl(trade) for trade in trades]
    count = len(values)
    gross_profit = sum(value for value in values if value > 0)
    gross_loss = -sum(value for value in values if value < 0)
    if gross_loss > 0:
        profit_factor = round(gross_profit / gross_loss, 2)
    elif gross_profit > 0:
        profit_factor = 999.0
    else:
        profit_factor = 0.0
    return {
        "trades": count,
        "avg_pnl_pct": round(sum(values) / count, 2) if count else 0.0,
        "profit_factor": profit_factor,
        "win_rate_pct": round(sum(1 for value in values if value > 0) / count * 100.0, 1) if count else 0.0,
        "gross_profit_pct": round(gross_profit, 2),
        "gross_loss_pct": round(gross_loss, 2),
        "worst_pnl_pct": round(min(values), 2) if values else 0.0,
        "best_pnl_pct": round(max(values), 2) if values else 0.0,
    }


def _exact_trades(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        trade
        for trade in trades
        if is_exact_contract_resolution(trade.get("entry_contract_resolution"))
    ]


def _counter_rows(counter: Counter[str], limit: int = 10) -> list[dict[str, Any]]:
    return [{"key": key, "count": count} for key, count in counter.most_common(limit)]


def _summarize_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("error"):
        return {"error": result.get("error")}
    trades = list(result.get("trades") or [])
    unpriced = list(result.get("unpriced_trades") or [])
    exact = _exact_trades(trades)
    return {
        "total_trades": int(result.get("total_trades") or len(trades)),
        "candidate_trade_count": int(result.get("candidate_trade_count") or 0),
        "unpriced_trade_count": int(result.get("unpriced_trade_count") or len(unpriced)),
        "quote_coverage_pct": result.get("quote_coverage_pct"),
        "directional_accuracy_pct": result.get("directional_accuracy_pct"),
        "all_priced": _metrics(trades),
        "exact": _metrics(exact),
        "exact_contract_match_count": int(result.get("exact_contract_match_count") or len(exact)),
        "nearest_contract_match_count": int(result.get("nearest_contract_match_count") or 0),
        "unpriced_reasons": _counter_rows(
            Counter(
                str(
                    trade.get("pricing_failure_reason")
                    or trade.get("unpriced_reason")
                    or trade.get("entry_contract_resolution")
                    or "unknown"
                )
                for trade in unpriced
            )
        ),
        "ticker_priced": _counter_rows(Counter(str(trade.get("ticker") or "UNKNOWN") for trade in trades)),
        "ticker_exact": _counter_rows(Counter(str(trade.get("ticker") or "UNKNOWN") for trade in exact)),
        "exit_reasons": _counter_rows(Counter(str(trade.get("exit_reason") or "unknown") for trade in trades)),
        "replay_calendar": result.get("replay_calendar"),
    }


BASE_VARIANT: dict[str, Any] = {
    "allowed_tickers": TRACKED_WINNER_SYMBOLS,
    "historical_required_underlyings": TRACKED_WINNER_SYMBOLS,
    "allowed_market_regimes": ["bullish"],
    "allowed_directions": ["call"],
    "target_dte": 35,
    "min_quality_score": 0.0,
}


VARIANTS: tuple[dict[str, Any], ...] = (
    {
        "id": "tw_base_debit40_width5",
        "label": "Old winners base debit 40 width 5",
        "max_debit_pct_of_width": 40.0,
        "spread_max_width_pct": 5.0,
    },
    {
        "id": "tw_debit55_width10",
        "label": "Old winners debit 55 width 10",
        "max_debit_pct_of_width": 55.0,
        "spread_max_width_pct": 10.0,
    },
    {
        "id": "tw_debit60_width15",
        "label": "Old winners debit 60 width 15",
        "max_debit_pct_of_width": 60.0,
        "spread_max_width_pct": 15.0,
    },
    {
        "id": "tw_loose_exit_debit55_width10",
        "label": "Old winners loose exits debit 55 width 10",
        "max_debit_pct_of_width": 55.0,
        "spread_max_width_pct": 10.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 80.0,
    },
    {
        "id": "tw_loose_exit_debit60_width15",
        "label": "Old winners loose exits debit 60 width 15",
        "max_debit_pct_of_width": 60.0,
        "spread_max_width_pct": 15.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 80.0,
    },
    {
        "id": "tw_loose_exit_debit60_width15_no_xlk",
        "label": "Old winners loose exits debit 60 width 15 no XLK",
        "allowed_tickers": ["SPY", "GOOGL", "DIA", "NVDA"],
        "historical_required_underlyings": ["SPY", "GOOGL", "DIA", "NVDA"],
        "max_debit_pct_of_width": 60.0,
        "spread_max_width_pct": 15.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 80.0,
    },
    {
        "id": "tw_loose_exit_debit60_width15_time70",
        "label": "Old winners loose exits debit 60 width 15 time 70",
        "max_debit_pct_of_width": 60.0,
        "spread_max_width_pct": 15.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 70.0,
    },
    {
        "id": "tw_loose_exit_debit60_width15_time75",
        "label": "Old winners loose exits debit 60 width 15 time 75",
        "max_debit_pct_of_width": 60.0,
        "spread_max_width_pct": 15.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 75.0,
    },
    {
        "id": "tw_loose_exit_debit60_width15_time85",
        "label": "Old winners loose exits debit 60 width 15 time 85",
        "max_debit_pct_of_width": 60.0,
        "spread_max_width_pct": 15.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 85.0,
    },
    {
        "id": "tw_loose_exit_debit60_width15_target125",
        "label": "Old winners loose exits debit 60 width 15 target 125",
        "max_debit_pct_of_width": 60.0,
        "spread_max_width_pct": 15.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 125.0,
        "spread_time_exit_pct": 80.0,
    },
    {
        "id": "tw_loose_exit_debit60_width15_target175",
        "label": "Old winners loose exits debit 60 width 15 target 175",
        "max_debit_pct_of_width": 60.0,
        "spread_max_width_pct": 15.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 175.0,
        "spread_time_exit_pct": 80.0,
    },
    {
        "id": "tw_loose_exit_debit60_width15_ret5_1_5_to_3",
        "label": "Old winners loose exits debit 60 width 15 ret5 1.5-3",
        "max_debit_pct_of_width": 60.0,
        "spread_max_width_pct": 15.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 80.0,
        "min_signal_ret5": 1.5,
        "max_signal_ret5": 3.0,
        "min_signal_ret20": 1.0,
    },
    {
        "id": "tw_loose_exit_debit60_width15_ret5_1_to_3_5",
        "label": "Old winners loose exits debit 60 width 15 ret5 1-3.5",
        "max_debit_pct_of_width": 60.0,
        "spread_max_width_pct": 15.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 80.0,
        "min_signal_ret5": 1.0,
        "max_signal_ret5": 3.5,
        "min_signal_ret20": 1.0,
    },
    {
        "id": "tw_chain_native_no_xlk_time80_debit70_width20",
        "label": "Chain-native no XLK time 80 debit 70 width 20",
        "allowed_tickers": ["SPY", "GOOGL", "DIA", "NVDA"],
        "historical_required_underlyings": ["SPY", "GOOGL", "DIA", "NVDA"],
        "max_debit_pct_of_width": 70.0,
        "spread_max_width_pct": 20.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 80.0,
        "chain_native_spread_selection": True,
        "chain_native_min_dte": 28,
        "chain_native_max_dte": 45,
    },
    {
        "id": "tw_chain_native_no_xlk_time65_debit70_width20",
        "label": "Chain-native no XLK time 65 debit 70 width 20",
        "allowed_tickers": ["SPY", "GOOGL", "DIA", "NVDA"],
        "historical_required_underlyings": ["SPY", "GOOGL", "DIA", "NVDA"],
        "max_debit_pct_of_width": 70.0,
        "spread_max_width_pct": 20.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 65.0,
        "chain_native_spread_selection": True,
        "chain_native_min_dte": 28,
        "chain_native_max_dte": 45,
    },
    {
        "id": "tw_chain_native_no_xlk_time65_target125",
        "label": "Chain-native no XLK time 65 target 125",
        "allowed_tickers": ["SPY", "GOOGL", "DIA", "NVDA"],
        "historical_required_underlyings": ["SPY", "GOOGL", "DIA", "NVDA"],
        "max_debit_pct_of_width": 70.0,
        "spread_max_width_pct": 20.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 125.0,
        "spread_time_exit_pct": 65.0,
        "chain_native_spread_selection": True,
        "chain_native_min_dte": 28,
        "chain_native_max_dte": 45,
    },
    {
        "id": "tw_chain_native_with_qqq_time80",
        "label": "Chain-native with QQQ time 80",
        "allowed_tickers": ["SPY", "QQQ", "GOOGL", "DIA", "NVDA"],
        "historical_required_underlyings": ["SPY", "QQQ", "GOOGL", "DIA", "NVDA"],
        "max_debit_pct_of_width": 70.0,
        "spread_max_width_pct": 20.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 80.0,
        "chain_native_spread_selection": True,
        "chain_native_min_dte": 28,
        "chain_native_max_dte": 45,
    },
    {
        "id": "tw_chain_native_with_qqq_time65",
        "label": "Chain-native with QQQ time 65",
        "allowed_tickers": ["SPY", "QQQ", "GOOGL", "DIA", "NVDA"],
        "historical_required_underlyings": ["SPY", "QQQ", "GOOGL", "DIA", "NVDA"],
        "max_debit_pct_of_width": 70.0,
        "spread_max_width_pct": 20.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 65.0,
        "chain_native_spread_selection": True,
        "chain_native_min_dte": 28,
        "chain_native_max_dte": 45,
    },
    {
        "id": "tw_chain_native_spy_qqq_time60_ret5_band",
        "label": "Chain-native SPY+QQQ time 60 ret5 0.5-3",
        "allowed_tickers": ["SPY", "QQQ"],
        "historical_required_underlyings": ["SPY", "QQQ"],
        "max_debit_pct_of_width": 70.0,
        "spread_max_width_pct": 20.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 60.0,
        "min_signal_ret5": 0.5,
        "max_signal_ret5": 3.0,
        "chain_native_spread_selection": True,
        "chain_native_min_dte": 28,
        "chain_native_max_dte": 45,
    },
    {
        "id": "tw_chain_native_spy_qqq_time60_ret20_watch",
        "label": "Chain-native SPY+QQQ time 60 ret20 watch",
        "allowed_tickers": ["SPY", "QQQ"],
        "historical_required_underlyings": ["SPY", "QQQ"],
        "max_debit_pct_of_width": 70.0,
        "spread_max_width_pct": 20.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 60.0,
        "min_signal_ret5": 0.5,
        "max_signal_ret5": 3.0,
        "min_signal_ret20": 2.0,
        "chain_native_spread_selection": True,
        "chain_native_min_dte": 28,
        "chain_native_max_dte": 45,
    },
    {
        "id": "tw_chain_native_qqq_time60_debit60_ret20_watch",
        "label": "Chain-native QQQ time 60 debit60 ret20 watch",
        "allowed_tickers": ["QQQ"],
        "historical_required_underlyings": ["QQQ"],
        "max_debit_pct_of_width": 60.0,
        "spread_max_width_pct": 20.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 60.0,
        "min_signal_ret5": 0.5,
        "max_signal_ret5": 3.0,
        "min_signal_ret20": 2.0,
        "chain_native_spread_selection": True,
        "chain_native_min_dte": 28,
        "chain_native_max_dte": 45,
    },
    {
        "id": "tw_balanced_exit_debit60_width15",
        "label": "Old winners balanced exits debit 60 width 15",
        "max_debit_pct_of_width": 60.0,
        "spread_max_width_pct": 15.0,
        "spread_stop_loss_pct": 80.0,
        "spread_profit_target_pct": 125.0,
        "spread_time_exit_pct": 65.0,
    },
    {
        "id": "tw_time_exit55_stop100_debit60_width15",
        "label": "Old winners stop100 time55 debit 60 width 15",
        "max_debit_pct_of_width": 60.0,
        "spread_max_width_pct": 15.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 55.0,
    },
    {
        "id": "tw_loose_exit_debit70_width20",
        "label": "Old winners loose exits debit 70 width 20",
        "max_debit_pct_of_width": 70.0,
        "spread_max_width_pct": 20.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 80.0,
    },
    {
        "id": "tw_momentum_1_5_to_3",
        "label": "Old winners ret5 1.5-3 debit 55 width 10",
        "max_debit_pct_of_width": 55.0,
        "spread_max_width_pct": 10.0,
        "min_signal_ret5": 1.5,
        "max_signal_ret5": 3.0,
        "min_signal_ret20": 1.0,
    },
    {
        "id": "tw_momentum_0_5_to_2_5",
        "label": "Old winners ret5 0.5-2.5 debit 55 width 10",
        "max_debit_pct_of_width": 55.0,
        "spread_max_width_pct": 10.0,
        "min_signal_ret5": 0.5,
        "max_signal_ret5": 2.5,
        "min_signal_ret20": 2.0,
    },
    {
        "id": "tw_momentum_loose_exit",
        "label": "Old winners ret5 1.5-3 loose exits",
        "max_debit_pct_of_width": 55.0,
        "spread_max_width_pct": 10.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 80.0,
        "min_signal_ret5": 1.5,
        "max_signal_ret5": 3.0,
        "min_signal_ret20": 1.0,
    },
    {
        "id": "tw_pullback_ret5_neg4_to_0_25",
        "label": "Old winners pullback shape",
        "max_debit_pct_of_width": 55.0,
        "spread_max_width_pct": 10.0,
        "min_signal_ret20": 2.0,
        "min_signal_ret5": -4.0,
        "max_signal_ret5": 0.25,
    },
)


def _variant_playbook(variant: dict[str, Any]) -> dict[str, Any]:
    playbook = copy.deepcopy(BASE_VARIANT)
    playbook.update(copy.deepcopy(variant))
    return playbook


def run_sweep(
    *,
    lookback_years: int,
    n_picks: int,
    min_imported_calendar_dates: int,
    variant_ids: set[str] | None = None,
) -> dict[str, Any]:
    os.environ.setdefault("OPTIONS_MARKET_DATA_PROVIDER", "yahoo")
    os.environ.setdefault("ALPACA_ALLOW_YAHOO_FALLBACK", "1")
    started_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    original_playbooks = copy.deepcopy(wfo.REPLAY_PLAYBOOKS)
    rows: list[dict[str, Any]] = []
    try:
        for variant in VARIANTS:
            if variant_ids and str(variant["id"]) not in variant_ids:
                continue
            playbook = _variant_playbook(variant)
            wfo.REPLAY_PLAYBOOKS[playbook["id"]] = playbook
            result = wfo.run_historical_backtest(
                playbook=playbook["id"],
                n_picks=int(n_picks),
                lookback_years=int(lookback_years),
                pricing_lane="pessimistic",
                truth_lane=wfo.IMPORTED_DAILY_TRUTH_SOURCE,
                min_imported_calendar_dates=int(min_imported_calendar_dates),
                historical_source_labels="",
                allow_research_imported_data=True,
                save_result=False,
            )
            rows.append(
                {
                    "variant": playbook["id"],
                    "label": playbook["label"],
                    "config": {
                        key: playbook.get(key)
                        for key in (
                            "max_debit_pct_of_width",
                            "spread_max_width_pct",
                            "spread_stop_loss_pct",
                            "spread_profit_target_pct",
                            "spread_time_exit_pct",
                            "chain_native_spread_selection",
                            "chain_native_min_dte",
                            "chain_native_max_dte",
                            "min_signal_ret5",
                            "max_signal_ret5",
                            "min_signal_ret20",
                        )
                        if key in playbook
                    },
                    "summary": _summarize_result(result),
                }
            )
    finally:
        wfo.REPLAY_PLAYBOOKS.clear()
        wfo.REPLAY_PLAYBOOKS.update(original_playbooks)
    ranked = sorted(
        rows,
        key=lambda row: (
            _num((row["summary"].get("exact") or {}).get("profit_factor")),
            _num((row["summary"].get("exact") or {}).get("avg_pnl_pct")),
            int((row["summary"].get("exact") or {}).get("trades") or 0),
            _num((row["summary"].get("all_priced") or {}).get("profit_factor")),
        ),
        reverse=True,
    )
    return {
        "started_at": started_at,
        "completed_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "lookback_years": int(lookback_years),
        "n_picks": int(n_picks),
        "min_imported_calendar_dates": int(min_imported_calendar_dates),
        "symbols": TRACKED_WINNER_SYMBOLS,
        "variant_count": len(rows),
        "results": rows,
        "ranked": ranked,
        "best": ranked[0] if ranked else None,
        "acceptance_target": {
            "min_exact_trades": 100,
            "min_profit_factor": 1.0,
            "min_avg_pnl_pct": 0.0,
            "data_scope": "research_included_imported_daily",
        },
    }


def write_report(report: dict[str, Any], output_root: Path) -> dict[str, str]:
    output_root.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("tracked_winner_sweep_%Y%m%dT%H%M%SZ")
    json_path = output_root / f"{run_id}.json"
    latest_path = output_root / "latest.json"
    text = json.dumps(report, indent=2, sort_keys=True)
    json_path.write_text(text + "\n", encoding="utf8")
    latest_path.write_text(text + "\n", encoding="utf8")
    return {"json": str(json_path), "latest_json": str(latest_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run research-grade sweeps against the tracked-winner playbook.")
    parser.add_argument("--lookback-years", type=int, default=3)
    parser.add_argument("--n-picks", type=int, default=5)
    parser.add_argument("--min-imported-calendar-dates", type=int, default=200)
    parser.add_argument("--variants", help="Comma-separated variant ids to run. Defaults to all.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    variant_ids = None
    if args.variants:
        variant_ids = {item.strip() for item in args.variants.split(",") if item.strip()}
    report = run_sweep(
        lookback_years=args.lookback_years,
        n_picks=args.n_picks,
        min_imported_calendar_dates=args.min_imported_calendar_dates,
        variant_ids=variant_ids,
    )
    artifacts = write_report(report, Path(args.output_root))
    payload = {"artifacts": artifacts, "best": report.get("best")}
    if args.json:
        payload["report"] = report
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
