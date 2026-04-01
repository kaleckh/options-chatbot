import argparse
import json
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wfo_optimizer import (
    build_options_experiment_matrix,
    load_last_results_by_truth_lane,
    run_historical_backtest,
)


def _parse_score_floors(text: str) -> list[int]:
    floors: list[int] = []
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        floors.append(int(part))
    return floors or [40, 50, 60, 70, 80]


def main() -> int:
    parser = argparse.ArgumentParser(description="Rank options replay slices from the historical backtest.")
    parser.add_argument("--run-backtest", action="store_true", help="Run a fresh historical backtest before scoring slices.")
    parser.add_argument("--lookback-years", type=int, default=1, help="Lookback window to use when --run-backtest is enabled.")
    parser.add_argument("--iv-adj", type=float, default=1.2, help="IV adjustment to use when --run-backtest is enabled.")
    parser.add_argument(
        "--truth-lane",
        default="synthetic",
        choices=["synthetic", "historical_imported", "historical_imported_daily"],
        help="Which truth lane to inspect. Synthetic stays the default research loop.",
    )
    parser.add_argument("--min-trades", type=int, default=20, help="Minimum trades required to clear the quality bar.")
    parser.add_argument("--score-floors", default="40,50,60,70,80", help="Comma-separated score floors to test.")
    parser.add_argument("--max-tickers", type=int, default=8, help="How many high-volume ticker slices to include.")
    parser.add_argument("--max-sectors", type=int, default=8, help="How many high-volume sector slices to include.")
    parser.add_argument("--min-profit-factor", type=float, default=1.05, help="Profit-factor bar for passing slices.")
    parser.add_argument(
        "--min-directional-accuracy",
        type=float,
        default=50.0,
        help="Directional-accuracy bar for passing slices.",
    )
    parser.add_argument("--json", action="store_true", help="Print the full experiment matrix JSON.")
    args = parser.parse_args()

    result = (
        run_historical_backtest(
            lookback_years=args.lookback_years,
            iv_adj=args.iv_adj,
            truth_lane=args.truth_lane,
        )
        if args.run_backtest
        else load_last_results_by_truth_lane(args.truth_lane)
    )
    if not result:
        raise SystemExit("No backtest results found. Run /api/backtest or re-run with --run-backtest.")
    if result.get("error"):
        raise SystemExit(result["error"])

    matrix = build_options_experiment_matrix(
        result=result,
        min_trades=args.min_trades,
        score_floors=_parse_score_floors(args.score_floors),
        max_tickers=args.max_tickers,
        max_sectors=args.max_sectors,
        min_profit_factor=args.min_profit_factor,
        min_directional_accuracy_pct=args.min_directional_accuracy,
    )
    if matrix.get("error"):
        raise SystemExit(matrix["error"])

    if args.json:
        print(json.dumps(matrix, indent=2))
        return 0

    summary = {
        "source": matrix["source"],
        "strategy_domain": matrix["strategy_domain"],
        "trade_types": matrix["trade_types"],
        "overall": {
            "trades": matrix["overall"]["trades"],
            "profit_factor": matrix["overall"]["profit_factor"],
            "avg_pnl_pct": matrix["overall"]["avg_pnl_pct"],
            "directional_accuracy_pct": matrix["overall"]["directional_accuracy_pct"],
        },
        "top_experiments": [
            {
                "label": item["label"],
                "category": item["category"],
                "trades": item["trades"],
                "profit_factor": item["profit_factor"],
                "avg_pnl_pct": item["avg_pnl_pct"],
                "directional_accuracy_pct": item["directional_accuracy_pct"],
                "passes_quality_bar": item["passes_quality_bar"],
            }
            for item in matrix["experiments"][:5]
        ],
        "passing_experiments": [
            {
                "label": item["label"],
                "category": item["category"],
                "trades": item["trades"],
                "profit_factor": item["profit_factor"],
                "avg_pnl_pct": item["avg_pnl_pct"],
                "directional_accuracy_pct": item["directional_accuracy_pct"],
            }
            for item in matrix["passing_experiments"][:5]
        ],
        "recommendations": matrix["recommendations"],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
