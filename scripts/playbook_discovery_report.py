import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from metric_truth_audit import load_result
from wfo_optimizer import build_playbook_discovery_report


def _discover_cached_result_paths(root: Path) -> list[Path]:
    patterns = (
        "wfo_results*.json",
        "data/**/*wfo*.json",
        "data/**/*replay*.json",
    )
    seen: set[Path] = set()
    paths: list[Path] = []
    for pattern in patterns:
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            if any(part in {"node_modules", ".next", "__pycache__"} for part in path.parts):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            paths.append(resolved)
    return sorted(paths)


def _candidate_summary(items: list[dict], limit: int) -> list[dict]:
    summary: list[dict] = []
    for item in items[:limit]:
        overall = dict(item.get("overall") or {})
        summary.append(
            {
                "label": item.get("label"),
                "filters": item.get("filters"),
                "status": item.get("status"),
                "trades": overall.get("trades"),
                "profit_factor": overall.get("profit_factor"),
                "avg_pnl_pct": overall.get("avg_pnl_pct"),
                "directional_accuracy_pct": overall.get("directional_accuracy_pct"),
                "top_ticker_share_pct": overall.get("top_ticker_share_pct"),
                "reasons": list(item.get("reasons") or [])[:3],
                "blockers": list(item.get("blockers") or [])[:3],
            }
        )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mine cached replay outputs for stable regime/sector/direction-first playbook candidates."
    )
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        help="Path to a cached replay JSON file. Repeat to compare multiple cached runs.",
    )
    parser.add_argument("--min-trades", type=int, default=20, help="Minimum trades required for a dense slice.")
    parser.add_argument("--min-profit-factor", type=float, default=1.05, help="Profit-factor bar for passing slices.")
    parser.add_argument(
        "--min-directional-accuracy",
        type=float,
        default=50.0,
        help="Directional-accuracy bar for passing slices.",
    )
    parser.add_argument("--rolling-window-days", type=int, default=182, help="Rolling stability window size.")
    parser.add_argument("--rolling-step-days", type=int, default=91, help="Rolling stability step size.")
    parser.add_argument("--top", type=int, default=5, help="How many candidates per status bucket to print in summary mode.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    args = parser.parse_args()

    input_paths = [Path(path).expanduser().resolve() for path in args.input]
    if not input_paths:
        input_paths = _discover_cached_result_paths(ROOT)
    if not input_paths:
        raise SystemExit("No cached replay JSON files found. Pass --input with one or more result files.")

    results: list[dict] = []
    for path in input_paths:
        result = load_result(path)
        if not result.get("lookback_years") and not result.get("pricing_lane") and not result.get("playbook"):
            result["_playbook_discovery_label"] = path.stem
        results.append(result)

    report = build_playbook_discovery_report(
        result=results[0],
        comparison_results=results[1:],
        min_trades=args.min_trades,
        min_profit_factor=args.min_profit_factor,
        min_directional_accuracy_pct=args.min_directional_accuracy,
        rolling_window_days=args.rolling_window_days,
        rolling_step_days=args.rolling_step_days,
    )
    if report.get("error"):
        raise SystemExit(report["error"])

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    summary = {
        "source_catalog": report.get("source_catalog"),
        "quality_bar": report.get("quality_bar"),
        "promote_candidates": _candidate_summary(report.get("promote_candidates") or [], args.top),
        "watch_candidates": _candidate_summary(report.get("watch_candidates") or [], args.top),
        "block_candidates": _candidate_summary(report.get("block_candidates") or [], args.top),
        "recommendations": report.get("recommendations"),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
