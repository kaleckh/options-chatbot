"""
Sweep spread stop-loss levels and compare backtest results.

Temporarily patches the index strategy profile's spread.stop_loss_pct,
runs the historical backtest (calls only, imported-daily, pessimistic),
and collects metrics for each level. Results are printed as a table
and saved to data/stop_loss_sweep_results.json.
"""

import json
import os
import sys
import copy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import options_chatbot as oc
import wfo_optimizer as wfo


STOP_LEVELS = [30, 40, 50, 60, 70, 80, 90]
RESULTS_FILE = ROOT / "data" / "stop_loss_sweep_results.json"


def run_sweep():
    # Save original profile so we can restore it
    original_index_profile = copy.deepcopy(oc.STRATEGY_PROFILES["index"])

    all_results = []

    for stop_pct in STOP_LEVELS:
        print(f"\n{'='*60}")
        print(f"  Running backtest with spread stop_loss_pct = {stop_pct}%")
        print(f"{'='*60}\n")

        # Patch the in-memory profile
        oc.STRATEGY_PROFILES["index"]["spread"]["stop_loss_pct"] = float(stop_pct)
        # Also patch equity profile in case it's used
        oc.STRATEGY_PROFILES["equity"]["spread"]["stop_loss_pct"] = float(stop_pct)

        try:
            result = wfo.run_historical_backtest(
                lookback_years=2,
                n_picks=1,
                iv_adj=1.20,
                pricing_lane="pessimistic",
                truth_lane="historical_imported_daily",
                allowed_directions=["call"],
            )

            if "error" in result:
                print(f"  ERROR: {result['error']}")
                all_results.append({"stop_loss_pct": stop_pct, "error": result["error"]})
                continue

            # Extract key metrics
            summary = {
                "stop_loss_pct": stop_pct,
                "total_trades": result.get("total_trades", 0),
                "win_rate_pct": result.get("win_rate_pct", 0),
                "profit_factor": result.get("profit_factor", 0),
                "avg_pnl_pct": result.get("avg_pnl_pct", 0),
                "directional_accuracy_pct": result.get("directional_accuracy_pct", 0),
                "max_drawdown_pct": result.get("max_drawdown_pct", 0),
                "sharpe": result.get("sharpe", 0),
            }

            # Per-symbol breakdown
            by_symbol = result.get("by_symbol", {})
            for sym in ["SPY", "QQQ"]:
                sym_data = by_symbol.get(sym, {})
                overall = sym_data.get("overall_metrics", sym_data.get("research_only_metrics", {}))
                summary[f"{sym}_trades"] = overall.get("trade_count", 0)
                summary[f"{sym}_pf"] = overall.get("profit_factor", 0)
                summary[f"{sym}_avg_pnl"] = overall.get("avg_pnl_pct", 0)
                summary[f"{sym}_wr"] = overall.get("win_rate_pct",
                    round(overall.get("directional_accuracy_pct", 0), 1))

            # Exit reason breakdown
            exit_reasons = result.get("promotion_metrics", {}).get("research_only_metrics", {}).get("exit_reasons", [])
            for er in exit_reasons:
                reason = er.get("exit_reason", "unknown")
                summary[f"exit_{reason}_count"] = er.get("trades", 0)
                summary[f"exit_{reason}_pnl"] = er.get("avg_pnl_pct", 0)

            all_results.append(summary)

            print(f"  Trades: {summary['total_trades']}")
            print(f"  Win Rate: {summary['win_rate_pct']}%")
            print(f"  PF: {summary['profit_factor']}")
            print(f"  Avg P&L: {summary['avg_pnl_pct']}%")
            print(f"  Sharpe: {summary['sharpe']}")

        except Exception as e:
            print(f"  EXCEPTION: {e}")
            all_results.append({"stop_loss_pct": stop_pct, "error": str(e)})

    # Restore original profile
    oc.STRATEGY_PROFILES["index"] = original_index_profile

    # Save results
    os.makedirs(RESULTS_FILE.parent, exist_ok=True)
    with open(RESULTS_FILE, "w") as f:
        json.dump(all_results, f, indent=2)

    # Print comparison table
    print(f"\n\n{'='*80}")
    print("  STOP LOSS SWEEP RESULTS")
    print(f"{'='*80}")
    print(f"{'Stop%':>6} {'Trades':>7} {'WR%':>6} {'PF':>6} {'AvgP&L':>8} {'Sharpe':>7} {'SPY PF':>7} {'QQQ PF':>7}")
    print(f"{'-'*6} {'-'*7} {'-'*6} {'-'*6} {'-'*8} {'-'*7} {'-'*7} {'-'*7}")

    for r in all_results:
        if "error" in r:
            print(f"{r['stop_loss_pct']:>5}%  ERROR: {r['error'][:50]}")
            continue
        print(
            f"{r['stop_loss_pct']:>5}% "
            f"{r['total_trades']:>7} "
            f"{r['win_rate_pct']:>5.1f}% "
            f"{r['profit_factor']:>6.2f} "
            f"{r['avg_pnl_pct']:>+7.2f}% "
            f"{r['sharpe']:>7.2f} "
            f"{r.get('SPY_pf', 0):>7.2f} "
            f"{r.get('QQQ_pf', 0):>7.2f}"
        )

    print(f"\nResults saved to {RESULTS_FILE}")


if __name__ == "__main__":
    run_sweep()
