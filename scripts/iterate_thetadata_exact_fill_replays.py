from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import wfo_optimizer as wfo  # noqa: E402


DEFAULT_PLAYBOOKS = [
    "tracked_winner_chain_native_qqq_time60_debit60_ret20_watch",
    "tracked_winner_chain_native_spy_qqq_time60_ret20_watch",
    "tracked_winner_chain_native_qqq_time80_research",
]


def _run_replays(playbooks: list[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    os.environ.setdefault("OPTIONS_MARKET_DATA_PROVIDER", "yahoo")
    for playbook in playbooks:
        result = wfo.run_historical_backtest(
            lookback_years=1,
            n_picks=5,
            pricing_lane="pessimistic",
            truth_lane=wfo.IMPORTED_TRUTH_SOURCE,
            playbook=playbook,
            min_imported_calendar_dates=100,
            historical_source_labels="thetadata_opra_nbbo_1m",
            allow_research_imported_data=False,
            save_result=True,
        )
        priced = int(result.get("priced_trade_count") or 0)
        candidates = int(result.get("candidate_trade_count") or 0)
        results.append(
            {
                "playbook": playbook,
                "result_path": result.get("result_path"),
                "total_days": result.get("total_days"),
                "priced_trade_count": priced,
                "unpriced_trade_count": result.get("unpriced_trade_count"),
                "candidate_trade_count": candidates,
                "coverage_pct": round(100.0 * priced / max(1, candidates), 1),
                "profit_factor": result.get("profit_factor"),
                "unpriced_trade_diagnostics": result.get("unpriced_trade_diagnostics"),
            }
        )
    return results


def _run_exact_import(
    result_paths: list[str],
    *,
    start_time: str,
    end_time: str,
    interval: str,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "import_missing_replay_quotes_from_thetadata.py"),
        *result_paths,
        "--start-time",
        str(start_time),
        "--end-time",
        str(end_time),
        "--interval",
        str(interval),
        "--json",
    ]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=True)
    return json.loads(completed.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description="Iteratively fill exact ThetaData replay misses and rerun replays.")
    parser.add_argument("--max-cycles", type=int, default=6)
    parser.add_argument("--min-new-rows", type=int, default=1)
    parser.add_argument("--playbooks", default=",".join(DEFAULT_PLAYBOOKS))
    parser.add_argument("--start-time", default="15:55:00")
    parser.add_argument("--end-time", default="15:55:00")
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    playbooks = [item.strip() for item in args.playbooks.split(",") if item.strip()]
    cycles: list[dict[str, Any]] = []
    replay_results = _run_replays(playbooks)
    for cycle_index in range(1, int(args.max_cycles) + 1):
        result_paths = [str(item["result_path"]) for item in replay_results if item.get("result_path")]
        import_result = _run_exact_import(
            result_paths,
            start_time=str(args.start_time),
            end_time=str(args.end_time),
            interval=str(args.interval),
        )
        imported_rows = int((import_result.get("import_result") or {}).get("imported_rows") or 0)
        replay_results = _run_replays(playbooks)
        cycle = {
            "cycle": cycle_index,
            "exact_import_summary_path": import_result.get("summary_path"),
            "exact_imported_rows": imported_rows,
            "exact_unique_items": import_result.get("unique_items"),
            "exact_errors": len(import_result.get("errors") or []),
            "replays": replay_results,
        }
        cycles.append(cycle)
        if not args.json:
            print(json.dumps(cycle, indent=2))
        if imported_rows < int(args.min_new_rows):
            break

    summary = {
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "playbooks": playbooks,
        "cycles": cycles,
        "final_replays": replay_results,
    }
    out = ROOT / "data" / "profitability-lab" / "thetadata-exact-fill-iteration-summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf8")
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"summary_path {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
