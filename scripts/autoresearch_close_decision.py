from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from scripts.autoresearch_governance import record_decision_closure


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record the final human decision for an autoresearch run and refresh generated state."
    )
    parser.add_argument("--run-dir", required=True, help="Research run directory to close.")
    parser.add_argument(
        "--verdict",
        required=True,
        choices=("promote", "hold", "reject"),
        help="Final human verdict for the run.",
    )
    parser.add_argument("--approver", required=True, help="Human approver label.")
    parser.add_argument("--rationale", required=True, help="Short human rationale.")
    parser.add_argument(
        "--advance-queue-state",
        action="store_true",
        help="Move the matching queue item into the historical section when present.",
    )
    parser.add_argument("--phase-manifest", help="Optional phase manifest override.")
    parser.add_argument("--queue-json", help="Optional queue JSON override.")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir

    record_decision_closure(
        root_dir=ROOT,
        run_dir=run_dir,
        final_verdict=args.verdict,
        approver=args.approver,
        rationale=args.rationale,
        advance_queue_state=bool(args.advance_queue_state),
        phase_manifest_path=args.phase_manifest,
        queue_json_path=args.queue_json,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
