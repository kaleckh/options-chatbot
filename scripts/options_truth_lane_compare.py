import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wfo_optimizer import build_truth_lane_comparison


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare the latest synthetic and imported historical options validation lanes."
    )
    parser.add_argument("--json", action="store_true", help="Print the full comparison JSON.")
    args = parser.parse_args()

    result = build_truth_lane_comparison()
    if result.get("error"):
        raise SystemExit(result["error"])

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    summary = {
        "synthetic": result["synthetic"],
        "imported": result["imported"],
        "deltas": result["deltas"],
        "matching_priced_trade_count": result["matching_priced_trade_count"],
        "unsupported_by_import_count": result["unsupported_by_import_count"],
        "warnings": result["warnings"],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
