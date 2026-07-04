from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from historical_options_store import INTRADAY_SNAPSHOT_KIND, import_historical_option_snapshots  # noqa: E402
from scripts.import_thetadata_options_nbbo import (  # noqa: E402
    CSV_FIELDNAMES,
    DEFAULT_THETA_URL,
    INTRADAY_DATASET_KIND,
    _business_dates,
    build_thetadata_nbbo_import,
)
from scripts.plan_regular_sector_etf_imports import check_theta_terminal  # noqa: E402


REPORT_ID = "regular_options_13_symbol_out_of_sample_thetadata_opra_import"
APPROVAL_TOKEN = "APPROVE_SCOPED_13_SYMBOL_OOS_THETADATA_OPRA_IMPORT"
DEFAULT_DB = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_CONTRACT = ROOT / "data" / "contracts" / "regular-options-out-of-sample-extension-v1.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-13-symbol-out-of-sample-thetadata-opra-import"
DEFAULT_DOC = ROOT / "docs" / "regular-options-13-symbol-out-of-sample-thetadata-opra-import.md"
DEFAULT_SOURCE_LABEL = "thetadata_opra_nbbo_1m"

IMPORT_INTERVAL = "1m"
IMPORT_START_TIME = "15:55:00"
IMPORT_END_TIME = "15:55:00"
IMPORT_MIN_DTE = 5
IMPORT_MAX_DTE = 60
IMPORT_RIGHT = "both"
IMPORT_MAX_WORKERS = 4

FALLBACK_PROOF_SET = (
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "AAPL",
    "GOOGL",
    "UNH",
    "LLY",
    "JNJ",
    "XOM",
    "CVX",
    "COP",
    "NEM",
)

FALSE_FLAGS = {
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


def _rel(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _parse_symbols(value: str | Sequence[str]) -> list[str]:
    raw = value.replace(";", ",").split(",") if isinstance(value, str) else list(value)
    seen: set[str] = set()
    result: list[str] = []
    for item in raw:
        symbol = str(item).strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            result.append(symbol)
    return result


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf8"))
    return payload if isinstance(payload, dict) else {}


def _contract_symbols(contract: dict[str, Any]) -> list[str]:
    proof_set = contract.get("proof_set") if isinstance(contract.get("proof_set"), dict) else {}
    return _parse_symbols(proof_set.get("symbols") or FALLBACK_PROOF_SET)


def _target_window(contract: dict[str, Any]) -> tuple[str, str]:
    window = contract.get("target_window") if isinstance(contract.get("target_window"), dict) else {}
    return (
        str(window.get("requested_start_date") or "2022-01-01"),
        str(window.get("requested_end_date") or "2024-05-31"),
    )


def _connect(path: Path, *, read_only: bool) -> sqlite3.Connection:
    if read_only:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        conn.execute("PRAGMA query_only = ON")
    else:
        conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _trusted_symbol_dates(
    conn: sqlite3.Connection,
    *,
    source_label: str,
    start: str,
    end: str,
    symbols: Sequence[str],
) -> dict[str, set[str]]:
    placeholders = ",".join("?" for _ in symbols)
    rows = conn.execute(
        f"""
        SELECT q.underlying AS symbol, q.quote_date_et AS quote_date
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


def _missing_rows(*, coverage: dict[str, set[str]], requested_dates: Sequence[str], symbols: Sequence[str], source_label: str) -> list[dict[str, Any]]:
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


def _shared_dates(*, coverage: dict[str, set[str]], requested_dates: Sequence[str], symbols: Sequence[str]) -> set[str]:
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


def _run_scoped_import(
    *,
    db_path: Path,
    output_dir: Path,
    missing_rows: list[dict[str, Any]],
    symbols: list[str],
    source_label: str,
    theta_url: str,
    timeout: float,
    continue_on_errors: bool = False,
) -> dict[str, Any]:
    missing_by_date: dict[str, set[str]] = defaultdict(set)
    for row in missing_rows:
        missing_by_date[str(row["quote_date_et"])].add(str(row["symbol"]).upper())

    symbol_order = {symbol: index for index, symbol in enumerate(symbols)}
    csv_dir = output_dir / "import-csv"
    batch_results: list[dict[str, Any]] = []
    totals = Counter()
    errors: list[str] = []
    batch_ids: list[int] = []

    for batch_index, quote_date in enumerate(sorted(missing_by_date), start=1):
        trade_date = date.fromisoformat(quote_date)
        batch_symbols = sorted(missing_by_date[quote_date], key=lambda item: symbol_order.get(item, 9999))
        rows: list[dict[str, str]] = []
        batch_errors: list[str] = []
        batch_request_count = 0

        def fetch_one(symbol: str) -> dict[str, Any]:
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
            futures = {executor.submit(fetch_one, symbol): symbol for symbol in batch_symbols}
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    batch_errors.append(f"{symbol} {quote_date}: option history quote failed: {exc}")
                    continue
                rows.extend(result.get("rows") or [])
                batch_errors.extend(str(item) for item in result.get("errors") or [])
                batch_request_count += int(result.get("request_count") or 0)

        import_result: dict[str, Any] | None = None
        csv_path: Path | None = None
        if rows:
            csv_path = csv_dir / f"thetadata_13_symbol_oos_{quote_date.replace('-', '')}_{batch_index:04d}.csv"
            _write_csv(csv_path, rows)
            import_result = import_historical_option_snapshots(
                csv_path,
                source_label,
                dataset_kind=INTRADAY_DATASET_KIND,
                snapshot_kind=INTRADAY_SNAPSHOT_KIND,
                db_path=db_path,
            )
            if import_result.get("batch_id") is not None:
                batch_ids.append(int(import_result["batch_id"]))
            for key in ("imported_rows", "duplicate_rows", "rejected_rows", "total_rows"):
                totals[key] += int(import_result.get(key) or 0)
            totals["warning_count"] += len(import_result.get("warnings") or [])
        totals["generated_rows"] += len(rows)
        totals["request_count"] += batch_request_count
        batch_results.append(
            {
                "batch_index": batch_index,
                "date": quote_date,
                "symbols": batch_symbols,
                "request_count": batch_request_count,
                "generated_rows": len(rows),
                "csv_path": _rel(csv_path),
                "import_result": import_result,
                "errors": batch_errors[:5],
            }
        )
        print(
            json.dumps(
                {
                    "event": "thetadata_13_symbol_oos_batch",
                    "batch_index": batch_index,
                    "date": quote_date,
                    "symbols": len(batch_symbols),
                    "request_count": batch_request_count,
                    "generated_rows": len(rows),
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
            if not continue_on_errors:
                break

    return {
        "import_attempted": bool(missing_by_date),
        "batch_ids": batch_ids,
        "batch_results": batch_results,
        "errors": errors[:20],
        **{key: int(totals[key]) for key in ("imported_rows", "duplicate_rows", "rejected_rows", "total_rows", "warning_count", "generated_rows", "request_count")},
    }


def _scope_counts(
    conn: sqlite3.Connection,
    *,
    batch_ids: Sequence[int],
    symbols: Sequence[str],
    start_date: str,
    end_date: str,
) -> dict[str, int]:
    if not batch_ids:
        return {"outside_universe_import_rows": 0, "outside_requested_window_import_rows": 0, "protected_holdout_overlap_rows": 0}
    batch_placeholders = ",".join("?" for _ in batch_ids)
    symbol_placeholders = ",".join("?" for _ in symbols)
    outside_universe = conn.execute(
        f"SELECT COUNT(*) FROM option_quote_snapshots WHERE source_batch_id IN ({batch_placeholders}) AND underlying NOT IN ({symbol_placeholders})",
        (*batch_ids, *symbols),
    ).fetchone()[0]
    outside_window = conn.execute(
        f"SELECT COUNT(*) FROM option_quote_snapshots WHERE source_batch_id IN ({batch_placeholders}) AND (quote_date_et < ? OR quote_date_et > ?)",
        (*batch_ids, start_date, end_date),
    ).fetchone()[0]
    holdout_overlap = conn.execute(
        f"SELECT COUNT(*) FROM option_quote_snapshots WHERE source_batch_id IN ({batch_placeholders}) AND quote_date_et > ?",
        (*batch_ids, end_date),
    ).fetchone()[0]
    return {
        "outside_universe_import_rows": int(outside_universe or 0),
        "outside_requested_window_import_rows": int(outside_window or 0),
        "protected_holdout_overlap_rows": int(holdout_overlap or 0),
    }


def _phase_batch_summary(conn: sqlite3.Connection, *, output_dir: Path, source_label: str) -> dict[str, Any]:
    csv_root = str((output_dir / "import-csv").resolve())
    rows = conn.execute(
        """
        SELECT id, total_rows, imported_rows, duplicate_rows, rejected_rows
        FROM import_batches
        WHERE source_label = ?
          AND data_trust = 'trusted'
          AND replace(input_path, '/', '\\') LIKE ?
        ORDER BY id
        """,
        (source_label, f"{csv_root}%"),
    ).fetchall()
    batch_ids = [int(row["id"]) for row in rows]
    return {
        "batch_ids": batch_ids,
        "batch_count": len(batch_ids),
        "total_rows": sum(int(row["total_rows"] or 0) for row in rows),
        "imported_rows": sum(int(row["imported_rows"] or 0) for row in rows),
        "duplicate_rows": sum(int(row["duplicate_rows"] or 0) for row in rows),
        "rejected_rows": sum(int(row["rejected_rows"] or 0) for row in rows),
        "input_path_prefix": _rel(output_dir / "import-csv"),
    }


def _coverage_payload(
    *,
    requested_dates: Sequence[str],
    requested_symbols: Sequence[str],
    pre_coverage: dict[str, set[str]],
    post_coverage: dict[str, set[str]],
) -> dict[str, Any]:
    requested_symbol_dates = len(requested_dates) * len(requested_symbols)
    pre_missing = _missing_rows(coverage=pre_coverage, requested_dates=requested_dates, symbols=requested_symbols, source_label=DEFAULT_SOURCE_LABEL)
    post_missing = _missing_rows(coverage=post_coverage, requested_dates=requested_dates, symbols=requested_symbols, source_label=DEFAULT_SOURCE_LABEL)
    shared_pre = _shared_dates(coverage=pre_coverage, requested_dates=requested_dates, symbols=requested_symbols)
    shared_post = _shared_dates(coverage=post_coverage, requested_dates=requested_dates, symbols=requested_symbols)
    all_post_dates = sorted({day for symbol in requested_symbols for day in post_coverage.get(symbol, set())})
    covered_symbol_dates = sum(len(post_coverage.get(symbol, set()) & set(requested_dates)) for symbol in requested_symbols)
    return {
        "requested_market_date_count": len(requested_dates),
        "requested_symbol_date_count": requested_symbol_dates,
        "received_symbol_date_count": covered_symbol_dates,
        "received_coverage_pct": round((covered_symbol_dates / requested_symbol_dates) * 100.0, 4) if requested_symbol_dates else 0.0,
        "pre_import_missing_symbol_date_count": len(pre_missing),
        "missing_symbol_date_count": len(post_missing),
        "pre_import_shared_trusted_dates": {"count": len(shared_pre), "first": min(shared_pre) if shared_pre else None, "last": max(shared_pre) if shared_pre else None},
        "post_import_shared_trusted_dates": {"count": len(shared_post), "first": min(shared_post) if shared_post else None, "last": max(shared_post) if shared_post else None},
        "provider_received_start_month": all_post_dates[0][:7] if all_post_dates else None,
        "provider_received_end_month": all_post_dates[-1][:7] if all_post_dates else None,
        "deepest_provider_window_observed": {"first_quote_date_et": all_post_dates[0] if all_post_dates else None, "last_quote_date_et": all_post_dates[-1] if all_post_dates else None},
        "post_import_symbol_coverage": {
            symbol: {
                "trusted_intraday_dates": len(post_coverage.get(symbol, set())),
                "first": min(post_coverage.get(symbol, set())) if post_coverage.get(symbol) else None,
                "last": max(post_coverage.get(symbol, set())) if post_coverage.get(symbol) else None,
            }
            for symbol in requested_symbols
        },
    }


def build_report(
    *,
    db_path: Path = DEFAULT_DB,
    contract_path: Path = DEFAULT_CONTRACT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOC,
    start_date: str | None = None,
    end_date: str | None = None,
    as_of_date: str = "2024-05-31",
    universe: Sequence[str] | None = None,
    source_label: str = DEFAULT_SOURCE_LABEL,
    theta_url: str = DEFAULT_THETA_URL,
    approval_token: str | None = None,
    timeout: float = 5.0,
    dry_run: bool = False,
    continue_on_errors: bool = False,
    write_outputs: bool = True,
) -> dict[str, Any]:
    contract = _load_json(contract_path)
    contract_start, contract_end = _target_window(contract)
    start_date = start_date or contract_start
    end_date = end_date or contract_end
    symbols = list(universe or _contract_symbols(contract))
    requested_dates = [item.isoformat() for item in _business_dates(date.fromisoformat(start_date), date.fromisoformat(end_date))]
    contract_symbols = _contract_symbols(contract)
    blockers: list[str] = []
    if contract.get("contract_id") != "regular_options_out_of_sample_extension_v1":
        blockers.append("out_of_sample_contract_missing_or_unexpected")
    if symbols != contract_symbols:
        blockers.append("proof_set_universe_mismatch")
    if start_date != contract_start or end_date != contract_end:
        blockers.append("target_window_mismatch_contract")
    if end_date > as_of_date:
        blockers.append("date_window_exceeds_as_of")
    if not dry_run and approval_token != APPROVAL_TOKEN:
        blockers.append("approval_token_missing_or_invalid")

    with _connect(db_path, read_only=True) as conn:
        pre_coverage = _trusted_symbol_dates(conn, source_label=source_label, start=start_date, end=end_date, symbols=symbols)
    pre_missing = _missing_rows(coverage=pre_coverage, requested_dates=requested_dates, symbols=symbols, source_label=source_label)
    theta_status = check_theta_terminal(theta_url, timeout=timeout)
    if not theta_status.get("available"):
        blockers.append("thetaterminal_source_unavailable")

    import_summary = {
        "import_attempted": False,
        "batch_ids": [],
        "batch_results": [],
        "errors": [],
        "imported_rows": 0,
        "duplicate_rows": 0,
        "rejected_rows": 0,
        "total_rows": 0,
        "warning_count": 0,
        "generated_rows": 0,
        "request_count": 0,
    }
    if not blockers and not dry_run:
        import_summary = _run_scoped_import(
            db_path=db_path,
            output_dir=output_dir,
            missing_rows=pre_missing,
            symbols=symbols,
            source_label=source_label,
            theta_url=theta_url,
            timeout=timeout,
            continue_on_errors=continue_on_errors,
        )
        if import_summary["errors"]:
            blockers.append("bulk_import_chunk_errors")

    with _connect(db_path, read_only=True) as conn:
        post_coverage = _trusted_symbol_dates(conn, source_label=source_label, start=start_date, end=end_date, symbols=symbols)
        phase_batches = _phase_batch_summary(conn, output_dir=output_dir, source_label=source_label)
        scope_counts = _scope_counts(
            conn,
            batch_ids=phase_batches["batch_ids"],
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
        )
    coverage = _coverage_payload(
        requested_dates=requested_dates,
        requested_symbols=symbols,
        pre_coverage=pre_coverage,
        post_coverage=post_coverage,
    )
    if scope_counts["outside_universe_import_rows"]:
        blockers.append("outside_universe_rows_imported")
    if scope_counts["protected_holdout_overlap_rows"]:
        blockers.append("protected_holdout_overlap_rows_imported")

    if dry_run:
        status = "dry_run_ready_for_13_symbol_out_of_sample_import" if not blockers else "blocked_13_symbol_out_of_sample_import"
    elif import_summary["errors"]:
        status = "blocked_13_symbol_out_of_sample_import_partial"
    elif blockers:
        status = "blocked_13_symbol_out_of_sample_import"
    elif import_summary["import_attempted"]:
        status = "import_performed"
    else:
        status = "no_missing_rows_to_import"

    report = {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": _utc_now_iso(),
        "contract_path": _rel(contract_path),
        "contract_id": contract.get("contract_id"),
        "start_date": start_date,
        "end_date": end_date,
        "as_of_date": as_of_date,
        "source_label": source_label,
        "data_trust": "trusted",
        "snapshot_kind": "intraday",
        "db_path": _rel(db_path),
        "theta_terminal": theta_status,
        "dry_run": dry_run,
        "approval_token_valid": approval_token == APPROVAL_TOKEN,
        "continue_on_errors": continue_on_errors,
        "canonical_universe": symbols,
        "proof_set_contract_matched": symbols == contract_symbols,
        "requested_vs_received_coverage": coverage,
        "import_attempted": import_summary["import_attempted"],
        "imported_rows": import_summary["imported_rows"],
        "duplicate_rows": import_summary["duplicate_rows"],
        "rejected_rows": import_summary["rejected_rows"],
        "warning_count": import_summary["warning_count"],
        "generated_rows": import_summary["generated_rows"],
        "request_count": import_summary["request_count"],
        "import_batch_ids": import_summary["batch_ids"],
        "phase_import_batch_summary": phase_batches,
        "phase_imported_rows_cumulative": phase_batches["imported_rows"],
        "phase_duplicate_rows_cumulative": phase_batches["duplicate_rows"],
        "phase_rejected_rows_cumulative": phase_batches["rejected_rows"],
        "import_batch_results": import_summary["batch_results"],
        "import_errors": import_summary["errors"],
        **scope_counts,
        "source_quality_floor_lowered": False,
        "blockers": sorted(set(blockers)),
        **FALSE_FLAGS,
        "quotes_imported": import_summary["imported_rows"] > 0,
        "artifacts": {
            "docs_report": _rel(docs_report),
            "latest_json": _rel(output_dir / "latest.json"),
            "latest_markdown": _rel(output_dir / "latest.md"),
            "missing_symbol_date_manifest_jsonl": _rel(output_dir / "missing_symbol_date_manifest.jsonl"),
            "import_batch_manifest_jsonl": _rel(output_dir / "import_batch_manifest.jsonl"),
            "post_import_coverage_json": _rel(output_dir / "post_import_coverage.json"),
        },
    }
    if write_outputs:
        write_report(report, _missing_rows(coverage=post_coverage, requested_dates=requested_dates, symbols=symbols, source_label=source_label), output_dir=output_dir, docs_report=docs_report)
    return report


def render_markdown(report: dict[str, Any]) -> str:
    coverage = report.get("requested_vs_received_coverage") if isinstance(report.get("requested_vs_received_coverage"), dict) else {}
    lines = [
        "# Regular Options 13-Symbol Out-of-Sample ThetaData OPRA Import",
        "",
        f"- Status: `{report['status']}`",
        f"- Imported rows: `{report['imported_rows']}`",
        f"- Requested symbol-dates: `{coverage.get('requested_symbol_date_count')}`",
        f"- Received symbol-dates: `{coverage.get('received_symbol_date_count')}`",
        f"- Received coverage: `{coverage.get('received_coverage_pct')}`",
        f"- Pre-import shared trusted dates: `{coverage.get('pre_import_shared_trusted_dates', {}).get('count')}`",
        f"- Post-import shared trusted dates: `{coverage.get('post_import_shared_trusted_dates', {}).get('count')}`",
        f"- Remaining missing symbol-dates: `{coverage.get('missing_symbol_date_count')}`",
        f"- Protected holdout overlap rows: `{report.get('protected_holdout_overlap_rows')}`",
        f"- Outside-universe import rows: `{report.get('outside_universe_import_rows')}`",
        "",
        "This is the Phase 15.2 scoped import for the pre-registered 13-symbol proof set. It does not change filters, thresholds, scanner policy, stops, sizing, proof bars, live validation, auto-track, broker behavior, or lane promotion.",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- `{item}`" for item in report.get("blockers", [])) if report.get("blockers") else lines.append("- None.")
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict[str, Any], missing_rows: list[dict[str, Any]], *, output_dir: Path, docs_report: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    (output_dir / "latest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    (output_dir / "latest.md").write_text(render_markdown(report), encoding="utf8")
    docs_report.write_text(render_markdown(report), encoding="utf8")
    with (output_dir / "missing_symbol_date_manifest.jsonl").open("w", encoding="utf8", newline="\n") as handle:
        for row in missing_rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    with (output_dir / "import_batch_manifest.jsonl").open("w", encoding="utf8", newline="\n") as handle:
        for row in report.get("import_batch_results") or []:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    (output_dir / "post_import_coverage.json").write_text(
        json.dumps(
            {
                "requested_vs_received_coverage": report.get("requested_vs_received_coverage"),
                "protected_holdout_overlap_rows": report.get("protected_holdout_overlap_rows"),
                "outside_universe_import_rows": report.get("outside_universe_import_rows"),
                "outside_requested_window_import_rows": report.get("outside_requested_window_import_rows"),
                "source_quality_floor_lowered": report.get("source_quality_floor_lowered"),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf8",
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scoped Phase 15.2 13-symbol out-of-sample ThetaData OPRA import.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--as-of-date", default="2024-05-31")
    parser.add_argument("--source-label", default=DEFAULT_SOURCE_LABEL)
    parser.add_argument("--universe")
    parser.add_argument("--theta-url", default=DEFAULT_THETA_URL)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--approval-token")
    parser.add_argument("--continue-on-errors", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    contract = _load_json(args.contract)
    universe = _parse_symbols(args.universe) if args.universe else _contract_symbols(contract)
    report = build_report(
        db_path=args.db,
        contract_path=args.contract,
        output_dir=args.output_dir,
        docs_report=args.docs_report,
        start_date=args.start_date,
        end_date=args.end_date,
        as_of_date=args.as_of_date,
        universe=universe,
        source_label=args.source_label,
        theta_url=args.theta_url,
        timeout=args.timeout,
        approval_token=args.approval_token,
        continue_on_errors=args.continue_on_errors,
        dry_run=args.dry_run,
    )
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
