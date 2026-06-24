from __future__ import annotations

import json
import sys

from scripts import run_regular_options_59_symbol_thetadata_opra_import_repair as repair


def main(argv: list[str] | None = None) -> int:
    args = repair.parse_args(argv or sys.argv[1:])
    report = repair.build_report(
        db_path=args.db,
        output_dir=args.output_dir or repair.DEFAULT_RESUME_OUTPUT_DIR,
        docs_report=args.docs_report or repair.DEFAULT_RESUME_DOC,
        start_date=args.start_date,
        end_date=args.end_date,
        as_of_date=args.as_of_date,
        source_label=args.source_label,
        universe=repair._parse_symbols(args.universe),
        theta_url=args.theta_url,
        dry_run=args.dry_run,
        resume_missing_only=True,
        provider_recheck=True,
        approval_token=args.approval_token,
        timeout=float(args.timeout),
    )
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else repair.render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
