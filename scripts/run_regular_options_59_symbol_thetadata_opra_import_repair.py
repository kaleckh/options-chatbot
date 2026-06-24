from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.import_thetadata_options_nbbo import DEFAULT_THETA_URL, _business_dates
from scripts.plan_regular_sector_etf_imports import check_theta_terminal


REPORT_ID = "regular_options_59_symbol_thetadata_opra_import_repair"
DEFAULT_DB = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-59-symbol-source-repair"
DEFAULT_DOC = ROOT / "docs" / "regular-options-59-symbol-thetadata-opra-import-repair.md"
DEFAULT_RESUME_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-59-symbol-source-repair-resume"
DEFAULT_RESUME_DOC = ROOT / "docs" / "regular-options-59-symbol-thetadata-opra-import-resume.md"
APPROVAL_TOKEN = "APPROVE_SCOPED_59_SYMBOL_THETADATA_OPRA_IMPORT"
DEFAULT_SOURCE_LABEL = "thetadata_opra_nbbo_1m"
CANONICAL_UNIVERSE = (
    "SPY", "QQQ", "IWM", "AAPL", "GOOGL", "UNH", "LLY", "JNJ", "XOM", "CVX", "COP", "NEM", "DIA",
    "AA", "ABBV", "AMD", "AMT", "AMZN", "ARM", "BA", "BAC", "C", "CAT", "CLF", "COIN", "COST",
    "DE", "DIS", "EQR", "FCX", "GS", "JPM", "KO", "LIN", "LMT", "MCD", "META", "MSFT", "MSTR",
    "NFLX", "NKE", "NVDA", "OXY", "PFE", "PG", "PLD", "PLTR", "PM", "RTX", "SBUX", "SLB",
    "SMCI", "SPG", "T", "TSLA", "V", "WELL", "WMT", "XLK",
)
READ_ONLY_FLAGS = {
    "accepted_profitability": False,
    "historical_rows_are_forward_proof": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "promotion_ready": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "protected_holdout_consumed": False,
    "forward_cohort_appended": False,
}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _parse_symbols(value: str) -> list[str]:
    symbols = [item.strip().upper() for item in value.replace(";", ",").split(",") if item.strip()]
    seen: set[str] = set()
    unique = [symbol for symbol in symbols if not (symbol in seen or seen.add(symbol))]
    return unique


def _connect(path: Path, *, read_only: bool) -> sqlite3.Connection:
    if read_only:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        conn.execute("PRAGMA query_only = ON")
    else:
        conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _trusted_symbol_dates(conn: sqlite3.Connection, *, source_label: str, start: str, end: str, symbols: list[str]) -> dict[str, set[str]]:
    placeholders = ",".join("?" for _ in symbols)
    rows = conn.execute(
        f"""
        SELECT q.underlying AS symbol, q.quote_date_et AS quote_date, COUNT(*) AS rows
        FROM option_quote_snapshots q
        JOIN import_batches b ON b.id = q.source_batch_id
        WHERE b.source_label = ?
          AND b.data_trust = 'trusted'
          AND q.snapshot_kind = 'intraday'
          AND q.quote_date_et BETWEEN ? AND ?
          AND q.underlying IN ({placeholders})
          AND q.bid IS NOT NULL
          AND q.ask IS NOT NULL
          AND q.ask >= q.bid
        GROUP BY q.underlying, q.quote_date_et
        """,
        (source_label, start, end, *symbols),
    ).fetchall()
    coverage: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        coverage[str(row["symbol"]).upper()].add(str(row["quote_date"]))
    return coverage


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_report(
    *,
    db_path: Path = DEFAULT_DB,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOC,
    start_date: str = "2024-05-22",
    end_date: str = "2026-06-04",
    as_of_date: str = "2026-06-04",
    universe: list[str] | None = None,
    source_label: str = DEFAULT_SOURCE_LABEL,
    theta_url: str = DEFAULT_THETA_URL,
    dry_run: bool = False,
    resume_missing_only: bool = False,
    provider_recheck: bool = False,
    approval_token: str | None = None,
    timeout: float = 5.0,
    write_outputs: bool = True,
) -> dict[str, Any]:
    symbols = universe or list(CANONICAL_UNIVERSE)
    expected = list(CANONICAL_UNIVERSE)
    generated_at = _utc_now_iso()
    requested_dates = [item.isoformat() for item in _business_dates(date.fromisoformat(start_date), date.fromisoformat(end_date))]
    blockers: list[str] = []
    if symbols != expected:
        blockers.append("canonical_59_symbol_universe_mismatch")
    if end_date > as_of_date or end_date > "2026-06-04":
        blockers.append("date_window_exceeds_as_of_or_pre_holdout_boundary")
    if not dry_run and approval_token != APPROVAL_TOKEN:
        blockers.append("approval_token_missing_or_invalid")
    if provider_recheck is False and resume_missing_only:
        blockers.append("provider_recheck_required_for_resume")

    conn = _connect(db_path, read_only=True)
    try:
        coverage = _trusted_symbol_dates(conn, source_label=source_label, start=start_date, end=end_date, symbols=symbols)
    finally:
        conn.close()

    missing_rows: list[dict[str, Any]] = []
    for symbol in symbols:
        covered = coverage.get(symbol, set())
        for quote_date in requested_dates:
            if quote_date not in covered:
                missing_rows.append(
                    {
                        "symbol": symbol,
                        "quote_date_et": quote_date,
                        "reason": "trusted_intraday_symbol_date_missing",
                        "source_label": source_label,
                        "snapshot_kind": "intraday",
                    }
                )
    shared_dates = set(requested_dates)
    for symbol in symbols:
        shared_dates &= coverage.get(symbol, set())

    theta_status = check_theta_terminal(theta_url, timeout=timeout)
    if not theta_status.get("available"):
        blockers.append("thetaterminal_source_unavailable")

    imported_rows = 0
    import_attempted = False
    if not blockers and not dry_run:
        # The actual bulk import intentionally remains behind the existing importer and this preflight.
        # It is not reached unless the terminal is available and all guards pass.
        blockers.append("bulk_import_execution_not_started_by_preflight_wrapper")

    if "thetaterminal_source_unavailable" in blockers:
        status = "blocked_thetaterminal_source_unavailable_retry" if resume_missing_only else "blocked_thetaterminal_source_unavailable"
    elif "canonical_59_symbol_universe_mismatch" in blockers:
        status = "blocked_canonical_universe_mismatch"
    elif "approval_token_missing_or_invalid" in blockers:
        status = "blocked_import_approval_token_missing"
    elif "provider_recheck_required_for_resume" in blockers:
        status = "blocked_provider_recheck_required_for_resume"
    elif dry_run:
        status = "dry_run_ready_for_scoped_import_resume" if resume_missing_only else "dry_run_ready_for_scoped_import"
    elif blockers:
        status = "blocked_59_symbol_import_repair"
    else:
        status = "import_performed"

    report = {
        "report_id": f"{REPORT_ID}_resume" if resume_missing_only else REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at,
        "start_date": start_date,
        "end_date": end_date,
        "as_of_date": as_of_date,
        "source_label": source_label,
        "data_trust": "trusted",
        "snapshot_kind": "intraday",
        "db_path": _rel(db_path),
        "theta_terminal": theta_status,
        "dry_run": dry_run,
        "resume_missing_only": resume_missing_only,
        "provider_recheck": provider_recheck,
        "approval_token_valid": approval_token == APPROVAL_TOKEN,
        "import_attempted": import_attempted,
        "imported_rows": imported_rows,
        "duplicate_rows": 0,
        "rejected_rows": 0,
        "warning_count": 0,
        "canonical_universe": symbols,
        "canonical_universe_exact": symbols == expected,
        "requested_market_dates": len(requested_dates),
        "shared_trusted_imported_quote_dates": {
            "count": len(shared_dates),
            "first": min(shared_dates) if shared_dates else None,
            "last": max(shared_dates) if shared_dates else None,
        },
        "missing_symbol_date_count": len(missing_rows),
        "missing_symbol_date_manifest_row_count": len(missing_rows),
        "outside_universe_import_rows": 0,
        "protected_holdout_overlap_rows": 0,
        "source_quality_floor_lowered": False,
        "post_import_shared_trusted_imported_quote_dates": {
            "count": len(shared_dates),
            "first": min(shared_dates) if shared_dates else None,
            "last": max(shared_dates) if shared_dates else None,
        },
        "pre_import_symbol_coverage": {
            symbol: {
                "trusted_intraday_dates": len(coverage.get(symbol, set())),
                "first": min(coverage.get(symbol, set())) if coverage.get(symbol) else None,
                "last": max(coverage.get(symbol, set())) if coverage.get(symbol) else None,
            }
            for symbol in symbols
        },
        "blockers": sorted(set(blockers)),
        "pre_import_baseline": {
            "forward_rows": 0,
            "minimum_required": 30,
            "historical_rows_are_forward_proof": False,
            "accepted_profitability": False,
            "prior_status": _load_json(DEFAULT_OUTPUT_DIR / "latest.json").get("status"),
            "prior_approval_token_valid": _load_json(DEFAULT_OUTPUT_DIR / "latest.json").get("approval_token_valid"),
            "prior_import_attempted": _load_json(DEFAULT_OUTPUT_DIR / "latest.json").get("import_attempted"),
            "prior_imported_rows": _load_json(DEFAULT_OUTPUT_DIR / "latest.json").get("imported_rows"),
            "prior_shared_trusted_imported_quote_dates": _load_json(DEFAULT_OUTPUT_DIR / "latest.json").get(
                "shared_trusted_imported_quote_dates"
            ),
            "prior_missing_symbol_date_count": _load_json(DEFAULT_OUTPUT_DIR / "latest.json").get(
                "missing_symbol_date_count"
            ),
        },
        "historical_simulated_forward_status": _load_json(
            ROOT / "data" / "profitability-lab" / "regular-options-historical-simulated-forward-audit" / "latest.json"
        ).get("status"),
        "robust_search_status": _load_json(ROOT / "data" / "profitability-lab" / "regular-options-robust-search-evaluation" / "latest.json").get("status"),
        **READ_ONLY_FLAGS,
        "quotes_imported": imported_rows > 0,
        "split_audit_gate": {
            "train_months_covered": 0,
            "audit_months_covered": 0,
            "latest_audit_exact_trades": 0,
            "cleared": False,
            "reason": "not_run_until_import_clears_shared_date_coverage",
        },
        "artifacts": {
            "docs_report": _rel(docs_report),
            "latest_json": _rel(output_dir / "latest.json"),
            "latest_markdown": _rel(output_dir / "latest.md"),
            "universe_json": _rel(output_dir / "universe.json"),
            "missing_symbol_date_manifest_jsonl": _rel(output_dir / "missing_symbol_date_manifest.jsonl"),
            "import_batch_manifest_jsonl": _rel(output_dir / "import_batch_manifest.jsonl"),
            "post_import_coverage_json": _rel(output_dir / "post_import_coverage.json"),
        },
    }
    if write_outputs:
        write_report(report, missing_rows, output_dir=output_dir, docs_report=docs_report)
    return report


def render_markdown(report: dict[str, Any]) -> str:
    title = (
        "# Regular Options 59-Symbol ThetaData OPRA Import Resume"
        if report.get("resume_missing_only")
        else "# Regular Options 59-Symbol ThetaData OPRA Import Repair"
    )
    lines = [
        title,
        "",
        f"- Status: `{report['status']}`",
        f"- Dry run: `{str(report['dry_run']).lower()}`",
        f"- Resume missing only: `{str(report.get('resume_missing_only')).lower()}`",
        f"- Provider recheck: `{str(report.get('provider_recheck')).lower()}`",
        f"- ThetaTerminal: `{report['theta_terminal'].get('status')}`",
        f"- Shared trusted imported quote dates: `{report['shared_trusted_imported_quote_dates']['count']}`",
        f"- Missing symbol-date rows: `{report['missing_symbol_date_count']}`",
        f"- Protected holdout overlap rows: `{report.get('protected_holdout_overlap_rows')}`",
        f"- Outside-universe import rows: `{report.get('outside_universe_import_rows')}`",
        f"- Import attempted: `{str(report['import_attempted']).lower()}`",
        f"- Imported rows: `{report['imported_rows']}`",
        f"- Accepted profitability: `{str(report['accepted_profitability']).lower()}`",
        "",
        "This is a scoped source-repair preflight. It does not create trades, prepare orders, enable live validation, enable auto-track, promote a lane, consume protected holdout, or treat historical rows as forward proof.",
        "",
        "## Blockers",
        "",
    ]
    for blocker in report["blockers"]:
        lines.append(f"- `{blocker}`")
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict[str, Any], missing_rows: list[dict[str, Any]], *, output_dir: Path, docs_report: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    (output_dir / "latest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    (output_dir / "latest.md").write_text(render_markdown(report), encoding="utf8")
    docs_report.write_text(render_markdown(report), encoding="utf8")
    (output_dir / "universe.json").write_text(json.dumps({"symbols": report["canonical_universe"]}, indent=2) + "\n", encoding="utf8")
    with (output_dir / "missing_symbol_date_manifest.jsonl").open("w", encoding="utf8", newline="\n") as handle:
        for row in missing_rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    (output_dir / "import_batch_manifest.jsonl").write_text("", encoding="utf8")
    coverage = {
        "shared_trusted_imported_quote_dates": report["shared_trusted_imported_quote_dates"],
        "post_import_shared_trusted_imported_quote_dates": report["post_import_shared_trusted_imported_quote_dates"],
        "pre_import_symbol_coverage": report["pre_import_symbol_coverage"],
        "protected_holdout_overlap_rows": report["protected_holdout_overlap_rows"],
        "outside_universe_import_rows": report["outside_universe_import_rows"],
        "source_quality_floor_lowered": report["source_quality_floor_lowered"],
        "post_import_note": "No post-import change because import was not attempted.",
    }
    (output_dir / "post_import_coverage.json").write_text(json.dumps(coverage, indent=2, sort_keys=True) + "\n", encoding="utf8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scoped 59-symbol ThetaData OPRA/NBBO import repair preflight.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--start-date", default="2024-05-22")
    parser.add_argument("--end-date", default="2026-06-04")
    parser.add_argument("--as-of-date", default="2026-06-04")
    parser.add_argument("--source-label", default=DEFAULT_SOURCE_LABEL)
    parser.add_argument("--universe", default=",".join(CANONICAL_UNIVERSE))
    parser.add_argument("--theta-url", default=DEFAULT_THETA_URL)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--approval-token")
    parser.add_argument("--resume-missing-only", action="store_true")
    parser.add_argument("--provider-recheck", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--docs-report", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    output_dir = args.output_dir or (DEFAULT_RESUME_OUTPUT_DIR if args.resume_missing_only else DEFAULT_OUTPUT_DIR)
    docs_report = args.docs_report or (DEFAULT_RESUME_DOC if args.resume_missing_only else DEFAULT_DOC)
    report = build_report(
        db_path=args.db,
        output_dir=output_dir,
        docs_report=docs_report,
        start_date=args.start_date,
        end_date=args.end_date,
        as_of_date=args.as_of_date,
        source_label=args.source_label,
        universe=_parse_symbols(args.universe),
        theta_url=args.theta_url,
        dry_run=args.dry_run,
        resume_missing_only=args.resume_missing_only,
        provider_recheck=args.provider_recheck,
        approval_token=args.approval_token,
        timeout=float(args.timeout),
    )
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
