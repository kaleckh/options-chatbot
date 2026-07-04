from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from historical_options_store import INTRADAY_SNAPSHOT_KIND, import_historical_option_snapshots
from scripts.import_thetadata_options_nbbo import (
    CSV_FIELDNAMES,
    DEFAULT_THETA_URL,
    INTRADAY_DATASET_KIND,
    _business_dates,
    build_thetadata_nbbo_import,
)
from scripts.plan_regular_sector_etf_imports import check_theta_terminal


REPORT_ID = "regular_options_59_symbol_thetadata_opra_import_repair"
DEFAULT_DB = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-59-symbol-source-repair"
DEFAULT_DOC = ROOT / "docs" / "regular-options-59-symbol-thetadata-opra-import-repair.md"
DEFAULT_RESUME_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-59-symbol-source-repair-resume"
DEFAULT_RESUME_DOC = ROOT / "docs" / "regular-options-59-symbol-thetadata-opra-import-resume.md"
APPROVAL_TOKEN = "APPROVE_SCOPED_59_SYMBOL_THETADATA_OPRA_IMPORT"
DEFAULT_SOURCE_LABEL = "thetadata_opra_nbbo_1m"
PROVIDER_PROBE_SYMBOLS = ("QQQ", "SPY")
PROVIDER_PROBE_DATE = "2026-05-21"
PROVIDER_PROBE_TIME = "10:27:00"
PROVIDER_PROBE_DTE = 28
IMPORT_BATCH_MARKET_DATES = 1
IMPORT_INTERVAL = "1m"
IMPORT_START_TIME = "15:55:00"
IMPORT_END_TIME = "15:55:00"
IMPORT_MIN_DTE = 5
IMPORT_MAX_DTE = 60
IMPORT_RIGHT = "both"
IMPORT_MAX_WORKERS = 4
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


def _build_missing_rows(
    *,
    coverage: dict[str, set[str]],
    requested_dates: list[str],
    symbols: list[str],
    source_label: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        covered = coverage.get(symbol, set())
        for quote_date in requested_dates:
            if quote_date not in covered:
                rows.append(
                    {
                        "symbol": symbol,
                        "quote_date_et": quote_date,
                        "reason": "trusted_intraday_symbol_date_missing",
                        "source_label": source_label,
                        "snapshot_kind": "intraday",
                    }
                )
    return rows


def _shared_dates(*, coverage: dict[str, set[str]], requested_dates: list[str], symbols: list[str]) -> set[str]:
    shared = set(requested_dates)
    for symbol in symbols:
        shared &= coverage.get(symbol, set())
    return shared


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _run_scoped_missing_import(
    *,
    db_path: Path,
    output_dir: Path,
    missing_rows: list[dict[str, Any]],
    symbols: list[str],
    source_label: str,
    theta_url: str,
    timeout: float,
) -> dict[str, Any]:
    missing_by_date: dict[str, set[str]] = defaultdict(set)
    for row in missing_rows:
        missing_by_date[str(row["quote_date_et"])].add(str(row["symbol"]).upper())

    symbol_order = {symbol: index for index, symbol in enumerate(symbols)}
    date_keys = sorted(missing_by_date)
    batch_results: list[dict[str, Any]] = []
    imported_rows = 0
    duplicate_rows = 0
    rejected_rows = 0
    generated_rows = 0
    request_count = 0
    warning_count = 0
    errors: list[str] = []

    csv_dir = output_dir / "import-csv"
    for batch_index, start in enumerate(range(0, len(date_keys), IMPORT_BATCH_MARKET_DATES), start=1):
        batch_date_keys = date_keys[start : start + IMPORT_BATCH_MARKET_DATES]
        batch_dates = [date.fromisoformat(item) for item in batch_date_keys]
        batch_symbols = sorted(
            {symbol for quote_date in batch_date_keys for symbol in missing_by_date[quote_date]},
            key=lambda item: symbol_order.get(item, 9999),
        )
        rows: list[dict[str, str]] = []
        batch_errors: list[str] = []
        batch_generated_rows = 0
        batch_request_count = 0

        def fetch_one(symbol: str, trade_date: date) -> dict[str, Any]:
            return build_thetadata_nbbo_import(
                symbols=[symbol],
                dates=[trade_date],
                theta_url=theta_url,
                interval=IMPORT_INTERVAL,
                start_time=IMPORT_START_TIME,
                end_time=IMPORT_END_TIME,
                min_dte=IMPORT_MIN_DTE,
                max_dte=IMPORT_MAX_DTE,
                right=IMPORT_RIGHT,
                timeout=float(timeout),
            )

        with ThreadPoolExecutor(max_workers=IMPORT_MAX_WORKERS) as executor:
            futures = {
                executor.submit(fetch_one, symbol, trade_date): (symbol, trade_date)
                for symbol in batch_symbols
                for trade_date in batch_dates
            }
            for future in as_completed(futures):
                symbol, trade_date = futures[future]
                try:
                    fetch_result = future.result()
                except Exception as exc:
                    batch_errors.append(f"{symbol} {trade_date.isoformat()}: option history quote failed: {exc}")
                    continue
                rows.extend(fetch_result.get("rows") or [])
                batch_errors.extend(str(item) for item in fetch_result.get("errors") or [])
                batch_generated_rows += int(fetch_result.get("generated_rows") or 0)
                batch_request_count += int(fetch_result.get("request_count") or 0)

        generated_rows += batch_generated_rows
        request_count += batch_request_count
        import_result: dict[str, Any] | None = None
        csv_path: Path | None = None
        if rows:
            csv_path = csv_dir / (
                f"thetadata_59_symbol_resume_{batch_date_keys[0].replace('-', '')}_"
                f"{batch_date_keys[-1].replace('-', '')}_{batch_index:04d}.csv"
            )
            _write_csv(csv_path, rows)
            import_result = import_historical_option_snapshots(
                csv_path,
                source_label,
                dataset_kind=INTRADAY_DATASET_KIND,
                snapshot_kind=INTRADAY_SNAPSHOT_KIND,
                db_path=db_path,
            )
            imported_rows += int(import_result.get("imported_rows") or 0)
            duplicate_rows += int(import_result.get("duplicate_rows") or 0)
            rejected_rows += int(import_result.get("rejected_rows") or 0)
            warning_count += len(import_result.get("warnings") or [])

        batch_record = {
            "batch_index": batch_index,
            "symbols": batch_symbols,
            "date_from": batch_date_keys[0],
            "date_to": batch_date_keys[-1],
            "request_count": batch_request_count,
            "generated_rows": batch_generated_rows,
            "csv_path": _rel(csv_path) if csv_path else None,
            "import_result": import_result,
            "errors": batch_errors[:5],
        }
        batch_results.append(batch_record)
        print(
            json.dumps(
                {
                    "event": "thetadata_59_symbol_resume_batch",
                    "batch_index": batch_index,
                    "date_from": batch_record["date_from"],
                    "date_to": batch_record["date_to"],
                    "symbols": len(batch_symbols),
                    "request_count": batch_record["request_count"],
                    "generated_rows": batch_record["generated_rows"],
                    "imported_rows": (import_result or {}).get("imported_rows", 0),
                    "duplicate_rows": (import_result or {}).get("duplicate_rows", 0),
                    "rejected_rows": (import_result or {}).get("rejected_rows", 0),
                    "errors": len(batch_errors),
                },
                sort_keys=True,
            ),
            flush=True,
        )
        if batch_errors:
            errors.extend(batch_errors)
            break

    return {
        "import_attempted": bool(date_keys),
        "imported_rows": imported_rows,
        "duplicate_rows": duplicate_rows,
        "rejected_rows": rejected_rows,
        "warning_count": warning_count,
        "generated_rows": generated_rows,
        "request_count": request_count,
        "batch_results": batch_results,
        "errors": errors[:20],
    }


def _provider_option_probe(
    *,
    theta_url: str,
    timeout: float,
    theta_status: dict[str, Any],
    provider_recheck: bool,
) -> dict[str, Any]:
    if not provider_recheck:
        return {
            "status": "not_checked",
            "available": None,
            "reason": "provider_recheck_not_requested",
        }
    if not theta_status.get("available"):
        return {
            "status": "skipped_theta_unavailable",
            "available": False,
            "reason": "theta_terminal_not_available",
        }
    probe_date = date.fromisoformat(PROVIDER_PROBE_DATE)
    try:
        result = build_thetadata_nbbo_import(
            symbols=list(PROVIDER_PROBE_SYMBOLS),
            dates=[probe_date],
            theta_url=theta_url,
            interval="1m",
            start_time=PROVIDER_PROBE_TIME,
            end_time=PROVIDER_PROBE_TIME,
            min_dte=PROVIDER_PROBE_DTE,
            max_dte=PROVIDER_PROBE_DTE,
            right="call",
            timeout=float(timeout),
        )
    except Exception as exc:
        return {
            "status": "probe_exception",
            "available": False,
            "reason": type(exc).__name__,
            "error": str(exc)[:500],
            "symbols": list(PROVIDER_PROBE_SYMBOLS),
            "date": PROVIDER_PROBE_DATE,
        }
    errors = [str(item) for item in result.get("errors") or []]
    error_text = "\n".join(errors)
    if "403" in error_text or "Forbidden" in error_text or "FREE subscription" in error_text:
        status = "blocked_thetadata_options_entitlement"
        available = False
    elif errors:
        status = "probe_errors"
        available = False
    elif int(result.get("generated_rows") or 0) <= 0:
        status = "probe_no_rows"
        available = False
    else:
        status = "options_history_quote_probe_ready"
        available = True
    return {
        "status": status,
        "available": available,
        "symbols": list(PROVIDER_PROBE_SYMBOLS),
        "date": PROVIDER_PROBE_DATE,
        "time_et": PROVIDER_PROBE_TIME,
        "dte": PROVIDER_PROBE_DTE,
        "request_count": result.get("request_count"),
        "generated_rows": result.get("generated_rows"),
        "errors": errors[:5],
    }


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

    pre_import_coverage = coverage
    pre_import_missing_rows = _build_missing_rows(
        coverage=pre_import_coverage,
        requested_dates=requested_dates,
        symbols=symbols,
        source_label=source_label,
    )
    pre_import_shared_dates = _shared_dates(coverage=pre_import_coverage, requested_dates=requested_dates, symbols=symbols)

    theta_status = check_theta_terminal(theta_url, timeout=timeout)
    if not theta_status.get("available"):
        blockers.append("thetaterminal_source_unavailable")
    provider_probe = _provider_option_probe(
        theta_url=theta_url,
        timeout=timeout,
        theta_status=theta_status,
        provider_recheck=provider_recheck,
    )
    if provider_probe.get("status") == "blocked_thetadata_options_entitlement":
        blockers.append("thetadata_options_entitlement_blocked")
    elif provider_recheck and provider_probe.get("available") is False and provider_probe.get("status") != "skipped_theta_unavailable":
        blockers.append("thetadata_option_history_probe_failed")

    import_summary = {
        "import_attempted": False,
        "imported_rows": 0,
        "duplicate_rows": 0,
        "rejected_rows": 0,
        "warning_count": 0,
        "generated_rows": 0,
        "request_count": 0,
        "batch_results": [],
        "errors": [],
    }
    if not blockers and not dry_run:
        import_summary = _run_scoped_missing_import(
            db_path=db_path,
            output_dir=output_dir,
            missing_rows=pre_import_missing_rows,
            symbols=symbols,
            source_label=source_label,
            theta_url=theta_url,
            timeout=timeout,
        )
        if import_summary["errors"]:
            blockers.append("bulk_import_chunk_errors")

    if import_summary["import_attempted"]:
        conn = _connect(db_path, read_only=True)
        try:
            post_import_coverage = _trusted_symbol_dates(conn, source_label=source_label, start=start_date, end=end_date, symbols=symbols)
        finally:
            conn.close()
    else:
        post_import_coverage = pre_import_coverage
    post_import_missing_rows = _build_missing_rows(
        coverage=post_import_coverage,
        requested_dates=requested_dates,
        symbols=symbols,
        source_label=source_label,
    )
    post_import_shared_dates = _shared_dates(coverage=post_import_coverage, requested_dates=requested_dates, symbols=symbols)

    if "thetaterminal_source_unavailable" in blockers:
        status = "blocked_thetaterminal_source_unavailable_retry" if resume_missing_only else "blocked_thetaterminal_source_unavailable"
    elif "canonical_59_symbol_universe_mismatch" in blockers:
        status = "blocked_canonical_universe_mismatch"
    elif "approval_token_missing_or_invalid" in blockers:
        status = "blocked_import_approval_token_missing"
    elif "provider_recheck_required_for_resume" in blockers:
        status = "blocked_provider_recheck_required_for_resume"
    elif "thetadata_options_entitlement_blocked" in blockers:
        status = "blocked_thetadata_options_entitlement"
    elif "thetadata_option_history_probe_failed" in blockers:
        status = "blocked_thetadata_option_history_probe_failed"
    elif dry_run:
        status = "dry_run_ready_for_scoped_import_resume" if resume_missing_only else "dry_run_ready_for_scoped_import"
    elif "bulk_import_chunk_errors" in blockers:
        status = "blocked_59_symbol_import_repair_partial_import"
    elif blockers:
        status = "blocked_59_symbol_import_repair"
    elif import_summary["import_attempted"]:
        status = "import_performed"
    else:
        status = "no_missing_rows_to_import"

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
        "theta_option_history_probe": provider_probe,
        "dry_run": dry_run,
        "resume_missing_only": resume_missing_only,
        "provider_recheck": provider_recheck,
        "approval_token_valid": approval_token == APPROVAL_TOKEN,
        "import_attempted": import_summary["import_attempted"],
        "imported_rows": import_summary["imported_rows"],
        "duplicate_rows": import_summary["duplicate_rows"],
        "rejected_rows": import_summary["rejected_rows"],
        "warning_count": import_summary["warning_count"],
        "generated_rows": import_summary["generated_rows"],
        "request_count": import_summary["request_count"],
        "import_batch_results": import_summary["batch_results"],
        "import_errors": import_summary["errors"],
        "canonical_universe": symbols,
        "canonical_universe_exact": symbols == expected,
        "requested_market_dates": len(requested_dates),
        "shared_trusted_imported_quote_dates": {
            "count": len(pre_import_shared_dates),
            "first": min(pre_import_shared_dates) if pre_import_shared_dates else None,
            "last": max(pre_import_shared_dates) if pre_import_shared_dates else None,
        },
        "pre_import_missing_symbol_date_count": len(pre_import_missing_rows),
        "missing_symbol_date_count": len(post_import_missing_rows),
        "missing_symbol_date_manifest_row_count": len(post_import_missing_rows),
        "outside_universe_import_rows": 0,
        "protected_holdout_overlap_rows": 0,
        "source_quality_floor_lowered": False,
        "post_import_shared_trusted_imported_quote_dates": {
            "count": len(post_import_shared_dates),
            "first": min(post_import_shared_dates) if post_import_shared_dates else None,
            "last": max(post_import_shared_dates) if post_import_shared_dates else None,
        },
        "post_import_symbol_coverage": {
            symbol: {
                "trusted_intraday_dates": len(post_import_coverage.get(symbol, set())),
                "first": min(post_import_coverage.get(symbol, set())) if post_import_coverage.get(symbol) else None,
                "last": max(post_import_coverage.get(symbol, set())) if post_import_coverage.get(symbol) else None,
            }
            for symbol in symbols
        },
        "pre_import_symbol_coverage": {
            symbol: {
                "trusted_intraday_dates": len(pre_import_coverage.get(symbol, set())),
                "first": min(pre_import_coverage.get(symbol, set())) if pre_import_coverage.get(symbol) else None,
                "last": max(pre_import_coverage.get(symbol, set())) if pre_import_coverage.get(symbol) else None,
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
        "quotes_imported": import_summary["imported_rows"] > 0,
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
        write_report(report, post_import_missing_rows, output_dir=output_dir, docs_report=docs_report)
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
        f"- Theta option-history probe: `{report.get('theta_option_history_probe', {}).get('status')}`",
        f"- Pre-import shared trusted quote dates: `{report['shared_trusted_imported_quote_dates']['count']}`",
        f"- Post-import shared trusted quote dates: `{report.get('post_import_shared_trusted_imported_quote_dates', report['shared_trusted_imported_quote_dates'])['count']}`",
        f"- Pre-import missing symbol-date rows: `{report.get('pre_import_missing_symbol_date_count', report['missing_symbol_date_count'])}`",
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
    return "\n".join(lines).rstrip() + "\n"


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
    with (output_dir / "import_batch_manifest.jsonl").open("w", encoding="utf8", newline="\n") as handle:
        for row in report.get("import_batch_results") or []:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    coverage = {
        "shared_trusted_imported_quote_dates": report["shared_trusted_imported_quote_dates"],
        "post_import_shared_trusted_imported_quote_dates": report["post_import_shared_trusted_imported_quote_dates"],
        "pre_import_symbol_coverage": report["pre_import_symbol_coverage"],
        "post_import_symbol_coverage": report.get("post_import_symbol_coverage"),
        "protected_holdout_overlap_rows": report["protected_holdout_overlap_rows"],
        "outside_universe_import_rows": report["outside_universe_import_rows"],
        "source_quality_floor_lowered": report["source_quality_floor_lowered"],
        "post_import_note": "Coverage recomputed after scoped import attempt." if report.get("import_attempted") else "No post-import change because import was not attempted.",
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
