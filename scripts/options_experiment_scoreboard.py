import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiment_scoreboard import build_replay_scoreboard


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rank cached options replay variants on conservative profitability and trust metrics."
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="Optional result files, directories, or glob patterns. Defaults to the latest cached options backtest.",
    )
    parser.add_argument("--min-trades", type=int, default=20, help="Minimum anchor-lane trades required to avoid a block.")
    parser.add_argument("--min-profit-factor", type=float, default=1.05, help="Profit-factor bar used by stability checks.")
    parser.add_argument(
        "--catastrophic-pf-floor",
        type=float,
        default=0.85,
        help="Worst rolling-window PF floor used by stability checks.",
    )
    parser.add_argument(
        "--bootstrap-watch-share-pct",
        type=float,
        default=40.0,
        help="Bootstrap share that caps promote-level confidence.",
    )
    parser.add_argument(
        "--bootstrap-block-share-pct",
        type=float,
        default=80.0,
        help="Bootstrap share that blocks a variant outright.",
    )
    parser.add_argument("--json", action="store_true", help="Print the full scoreboard JSON.")
    parser.add_argument("--output", help="Optional file path for writing the full scoreboard JSON.")
    args = parser.parse_args()

    report = build_replay_scoreboard(
        result_paths=args.inputs or None,
        min_trades=args.min_trades,
        min_profit_factor=args.min_profit_factor,
        catastrophic_pf_floor=args.catastrophic_pf_floor,
        bootstrap_watch_share_pct=args.bootstrap_watch_share_pct,
        bootstrap_block_share_pct=args.bootstrap_block_share_pct,
    )
    if report.get("error"):
        raise SystemExit(report["error"])

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2), encoding="utf8")

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    summary = {
        "summary": report["summary"],
        "top_candidates": [
            {
                "rank": item["rank"],
                "label": item["label"],
                "status": item["scoreboard_status"],
                "source_run_at": item["lanes"][item["anchor_lane"]].get("run_at"),
                "lookback_years": item.get("lookback_years"),
                "pricing_lane": item["lanes"][item["anchor_lane"]].get("pricing_lane"),
                "playbook": item.get("playbook"),
                "anchor_lane": item["anchor_lane"],
                "score": item["scoreboard_score"],
                "anchor_profit_factor": item["lanes"][item["anchor_lane"]]["profit_factor"],
                "anchor_avg_pnl_pct": item["lanes"][item["anchor_lane"]]["avg_pnl_pct"],
                "anchor_bootstrap_share_pct": item["lanes"][item["anchor_lane"]]["bootstrap_share_pct"],
                "rolling_pass_rate_pct": item["lanes"][item["anchor_lane"]]["rolling_pass_rate_pct"],
                "verdict_reasons": item["verdict_reasons"][:2],
            }
            for item in report["candidates"][:10]
        ],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
