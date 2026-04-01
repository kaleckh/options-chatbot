import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from metric_truth_audit import build_metric_truth_report, load_result


def _top_dense_buckets(items: list[dict], limit: int = 3) -> list[dict]:
    dense = [item for item in items if item["trades"] > 0]
    return dense[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit whether score metrics are actually aligned with profitable outcomes.")
    parser.add_argument("--input", default=str(ROOT / "wfo_results.json"), help="Path to a backtest result JSON file.")
    parser.add_argument("--bucket-size", type=int, default=10, help="Bucket size for metric bands.")
    parser.add_argument("--min-trades", type=int, default=20, help="Minimum trades for dense buckets/floors.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    args = parser.parse_args()

    result = load_result(args.input)
    report = build_metric_truth_report(
        result=result,
        bucket_size=args.bucket_size,
        min_trades=args.min_trades,
    )

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    summary = {
        "source": report["source"],
        "overall": report["overall"],
        "direction_score_bands": _top_dense_buckets(report["metric_buckets"].get("direction_score", []), limit=5),
        "direction_score_best_floor": report["metric_health"].get("direction_score", {}).get("best_floor"),
        "risk_flags": report["risk_flags"],
        "recommendations": report["recommendations"],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
