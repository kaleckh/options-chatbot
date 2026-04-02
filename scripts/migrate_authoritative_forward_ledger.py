from __future__ import annotations

import argparse
import json
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
for candidate in (ROOT, BACKEND_DIR):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from forward_options_ledger import migrate_live_production_evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Copy live-production forward-ledger sessions/events into the authoritative ledger."
    )
    parser.add_argument("--source-db-path", default=None, help="Optional source shared/archive ledger path.")
    parser.add_argument("--destination-db-path", default=None, help="Optional authoritative ledger path.")
    parser.add_argument("--json", action="store_true", help="Print the migration summary as JSON.")
    args = parser.parse_args(argv)

    result = migrate_live_production_evidence(
        source_db_path=args.source_db_path,
        destination_db_path=args.destination_db_path,
    )
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
