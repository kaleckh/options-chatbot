from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Sequence
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from historical_options_store import INTRADAY_SNAPSHOT_KIND, import_historical_option_snapshots  # noqa: E402
from scripts.build_regular_options_13_symbol_candidate_generation_surface_audit import ALLOWED_UNIVERSE  # noqa: E402
from scripts.import_thetadata_options_nbbo import (  # noqa: E402
    CSV_FIELDNAMES,
    DEFAULT_THETA_URL,
    INTRADAY_DATASET_KIND,
    _business_dates,
    build_thetadata_nbbo_import,
)
from us_equity_market_calendar import is_us_equity_market_day, previous_market_day  # noqa: E402


REPORT_ID = "regular_options_fresh_window_thetadata_opra_import"
APPROVAL_TOKEN = "APPROVE_FRESH_WINDOW_THETADATA_OPRA_IMPORT"
DEFAULT_DB = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_FORWARD_COHORT = ROOT / "data" / "contracts" / "forward-cohort-preregistration.json"
DEFAULT_FORWARD_HOLDOUT = ROOT / "data" / "contracts" / "forward-holdout-contract.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-fresh-window-thetadata-opra"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-fresh-window-thetadata-opra-import.md"
DEFAULT_LOCK_PATH = ROOT / "data" / "options-validation" / "options_history_import.lock"
DEFAULT_SOURCE_LABEL = "thetadata_opra_nbbo_1m"
MARKET_TZ = ZoneInfo("America/New_York")
IMPORT_INTERVAL = "1m"
IMPORT_START_TIME = "15:55:00"
IMPORT_END_TIME = "15:55:00"
IMPORT_MIN_DTE = 5
IMPORT_MAX_DTE = 60
IMPORT_RIGHT = "both"
IMPORT_MAX_WORKERS = 4
ACTIVE_STORE_WRITER_PATTERNS = (
    "run_regular_options_13_symbol_out_of_sample_thetadata_opra_import.py",
    "run_regular_options_59_symbol_thetadata_opra_import_repair.py",
    "run_regular_options_59_symbol_thetadata_opra_import_resume.py",
    "import_thetadata_options_nbbo.py",
)
FALSE_FLAGS = {
    "accepted_profitability": False,
    "historical_rows_are_forward_proof": False,
    "promotion_ready": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "forward_cohort_appended": False,
    "protected_holdout_consumed": False,
}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Expected YYYY-MM-DD date, got {value!r}") from exc


def _parse_symbols(value: str | Sequence[str]) -> list[str]:
    raw = value.split(",") if isinstance(value, str) else list(value)
    symbols: list[str] = []
    seen: set[str] = set()
    for item in raw:
        symbol = str(item).strip().upper()
        if symbol and symbol not in seen:
            symbols.append(symbol)
            seen.add(symbol)
    if not symbols:
        raise argparse.ArgumentTypeError("At least one symbol is required.")
    return symbols


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def allowed_symbols(forward_cohort_path: Path = DEFAULT_FORWARD_COHORT) -> list[str]:
    symbols = list(ALLOWED_UNIVERSE)
    seen = set(symbols)
    cohort = _load_json(forward_cohort_path)
    for lane in cohort.get("lanes") if isinstance(cohort.get("lanes"), list) else []:
        if not isinstance(lane, dict):
            continue
        for item in lane.get("symbols") if isinstance(lane.get("symbols"), list) else []:
            symbol = str(item).strip().upper()
            if symbol and symbol not in seen:
                symbols.append(symbol)
                seen.add(symbol)
    return symbols


def latest_completed_market_day(now_utc: datetime | None = None) -> date:
    now = now_utc or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    local = now.astimezone(MARKET_TZ)
    current = local.date()
    if is_us_equity_market_day(current) and local.time() >= time(16, 0):
        return current
    return previous_market_day(current)


def _connect(path: Path, *, read_only: bool) -> sqlite3.Connection:
    if read_only:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=30.0)
        conn.execute("PRAGMA query_only = ON")
    else:
        conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def max_trusted_intraday_date(db_path: Path, *, source_label: str = DEFAULT_SOURCE_LABEL) -> date | None:
    if not db_path.exists():
        return None
    with closing(_connect(db_path, read_only=True)) as conn:
        row = conn.execute(
            """
            SELECT MAX(q.quote_date_et) AS max_date
            FROM option_quote_snapshots q
            JOIN import_batches b ON b.id = q.source_batch_id
            WHERE b.source_label = ?
              AND b.data_trust = 'trusted'
              AND q.snapshot_kind = 'intraday'
            """,
            (source_label,),
        ).fetchone()
    value = row["max_date"] if row else None
    return date.fromisoformat(value) if value else None


def compute_window(
    *,
    db_path: Path,
    source_label: str,
    date_from: date | None = None,
    date_to: date | None = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    store_max = max_trusted_intraday_date(db_path, source_label=source_label)
    latest_completed = date_to or latest_completed_market_day(now_utc)
    if date_from is not None:
        start = date_from
    elif store_max is not None:
        start = store_max + timedelta(days=1)
    else:
        start = latest_completed + timedelta(days=1)
    market_dates = _business_dates(start, latest_completed) if start <= latest_completed else []
    return {
        "store_max_intraday_date_before": store_max.isoformat() if store_max else None,
        "latest_completed_market_day": latest_completed.isoformat(),
        "date_from": start.isoformat(),
        "date_to": latest_completed.isoformat(),
        "requested_market_dates": [item.isoformat() for item in market_dates],
        "requested_market_date_count": len(market_dates),
        "empty_window": len(market_dates) == 0,
    }


def _trusted_symbol_dates(
    conn: sqlite3.Connection,
    *,
    source_label: str,
    start: str,
    end: str,
    symbols: list[str],
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


def missing_symbol_dates(
    *,
    db_path: Path,
    source_label: str,
    symbols: list[str],
    requested_dates: list[str],
) -> list[dict[str, Any]]:
    if not requested_dates:
        return []
    with closing(_connect(db_path, read_only=True)) as conn:
        coverage = _trusted_symbol_dates(
            conn,
            source_label=source_label,
            start=requested_dates[0],
            end=requested_dates[-1],
            symbols=symbols,
        )
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


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


class ImportLock:
    def __init__(self, path: Path, payload: dict[str, Any]) -> None:
        self.path = path
        self.payload = payload
        self.fd: int | None = None

    def __enter__(self) -> "ImportLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RuntimeError(f"store import lock already exists at {self.path}") from exc
        os.write(self.fd, (json.dumps(self.payload, indent=2, sort_keys=True) + "\n").encode("utf8"))
        os.close(self.fd)
        self.fd = None
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def active_options_history_writer_processes() -> list[dict[str, Any]]:
    if os.name != "nt":
        return []
    patterns = "@(" + ",".join(json.dumps(pattern) for pattern in ACTIVE_STORE_WRITER_PATTERNS) + ")"
    command = f"""
$patterns = {patterns}
$rows = @()
Get-CimInstance Win32_Process | Where-Object {{
  $_.CommandLine -and $_.Name -notmatch 'powershell|pwsh'
}} | ForEach-Object {{
  $proc = $_
  foreach ($pattern in $patterns) {{
    if ($proc.CommandLine -like "*$pattern*") {{
      $rows += $proc
      break
    }}
  }}
}}
$rows | Select-Object ProcessId,Name,CreationDate,CommandLine | ConvertTo-Json -Depth 3
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    rows = payload if isinstance(payload, list) else [payload]
    return [
        {
            "process_id": row.get("ProcessId"),
            "name": row.get("Name"),
            "creation_date": row.get("CreationDate"),
            "command_line": row.get("CommandLine"),
        }
        for row in rows
        if isinstance(row, dict)
    ]


def _group_missing(missing_rows: list[dict[str, Any]]) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for row in missing_rows:
        grouped[str(row["quote_date_et"])].add(str(row["symbol"]).upper())
    return grouped


def run_import(
    *,
    db_path: Path,
    output_dir: Path,
    symbols: list[str],
    missing_rows: list[dict[str, Any]],
    source_label: str,
    theta_url: str,
    timeout: float,
) -> dict[str, Any]:
    missing_by_date = _group_missing(missing_rows)
    symbol_order = {symbol: index for index, symbol in enumerate(symbols)}
    csv_dir = output_dir / "import-csv"
    imported_rows = 0
    duplicate_rows = 0
    rejected_rows = 0
    generated_rows = 0
    request_count = 0
    warning_count = 0
    batch_results: list[dict[str, Any]] = []
    errors: list[str] = []

    for batch_index, quote_date in enumerate(sorted(missing_by_date), start=1):
        trade_date = date.fromisoformat(quote_date)
        batch_symbols = sorted(missing_by_date[quote_date], key=lambda item: symbol_order.get(item, 9999))
        rows: list[dict[str, str]] = []
        batch_errors: list[str] = []
        batch_generated_rows = 0
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
                    fetched = future.result()
                except Exception as exc:
                    batch_errors.append(f"{symbol} {quote_date}: option history quote failed: {exc}")
                    continue
                rows.extend(fetched.get("rows") or [])
                batch_errors.extend(str(item) for item in fetched.get("errors") or [])
                batch_generated_rows += int(fetched.get("generated_rows") or 0)
                batch_request_count += int(fetched.get("request_count") or 0)

        generated_rows += batch_generated_rows
        request_count += batch_request_count
        csv_path: Path | None = None
        import_result: dict[str, Any] | None = None
        if rows:
            csv_path = csv_dir / f"fresh_window_thetadata_opra_{quote_date.replace('-', '')}_{batch_index:04d}.csv"
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
            "quote_date": quote_date,
            "symbols": batch_symbols,
            "request_count": batch_request_count,
            "generated_rows": batch_generated_rows,
            "csv_path": _rel(csv_path),
            "import_result": import_result,
            "errors": batch_errors[:10],
        }
        batch_results.append(batch_record)
        print(
            json.dumps(
                {
                    "event": "fresh_window_thetadata_opra_batch",
                    "batch_index": batch_index,
                    "quote_date": quote_date,
                    "symbols": len(batch_symbols),
                    "request_count": batch_request_count,
                    "generated_rows": batch_generated_rows,
                    "imported_rows": (import_result or {}).get("imported_rows", 0),
                    "duplicate_rows": (import_result or {}).get("duplicate_rows", 0),
                    "rejected_rows": (import_result or {}).get("rejected_rows", 0),
                    "errors": len(batch_errors),
                },
                sort_keys=True,
            ),
            flush=True,
        )
        errors.extend(batch_errors)

    return {
        "import_attempted": bool(missing_rows),
        "imported_rows": imported_rows,
        "duplicate_rows": duplicate_rows,
        "rejected_rows": rejected_rows,
        "generated_rows": generated_rows,
        "request_count": request_count,
        "warning_count": warning_count,
        "errors": errors[:50],
        "batch_results": batch_results,
    }


def _batch_ids(import_result: dict[str, Any]) -> list[int]:
    ids: list[int] = []
    for row in import_result.get("batch_results") or []:
        result = row.get("import_result") if isinstance(row, dict) else None
        if isinstance(result, dict) and result.get("batch_id") is not None:
            ids.append(int(result["batch_id"]))
    return ids


def _outside_universe_rows(db_path: Path, *, batch_ids: list[int], symbols: list[str]) -> int:
    if not batch_ids:
        return 0
    batch_placeholders = ",".join("?" for _ in batch_ids)
    symbol_placeholders = ",".join("?" for _ in symbols)
    with closing(_connect(db_path, read_only=True)) as conn:
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS rows
            FROM option_quote_snapshots
            WHERE source_batch_id IN ({batch_placeholders})
              AND underlying NOT IN ({symbol_placeholders})
            """,
            (*batch_ids, *symbols),
        ).fetchone()
    return int(row["rows"] or 0) if row else 0


def _run_command(command: list[str], *, timeout_seconds: int = 900) -> dict[str, Any]:
    started = _utc_now_iso()
    completed = None
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
    )
    completed = _utc_now_iso()
    return {
        "command": command,
        "started_at_utc": started,
        "completed_at_utc": completed,
        "returncode": result.returncode,
        "status": "pass" if result.returncode == 0 else "fail",
        "stdout_tail": result.stdout.splitlines()[-20:],
        "stderr_tail": result.stderr.splitlines()[-20:],
    }


def refresh_materializer_chain(*, end_date: str, as_of_date: str) -> list[dict[str, Any]]:
    window_args = ["--end-date", end_date, "--as-of-date", as_of_date]
    steps = [
        [sys.executable, "scripts/build_regular_options_feature_store.py"],
        [sys.executable, "scripts/build_regular_options_historical_scanner_input_surface_tracker.py", *window_args],
        [sys.executable, "scripts/build_regular_options_historical_frozen_scanner_replay_adapter.py", *window_args],
        [sys.executable, "scripts/build_regular_options_13_symbol_frozen_daily_candidate_decisions.py", *window_args],
        [sys.executable, "scripts/regular_options_frozen_candidate_generation_entrypoint.py", "--no-write", *window_args],
        [sys.executable, "scripts/build_regular_options_13_symbol_frozen_candidate_generation_source_surface.py", "--no-write", *window_args],
        [sys.executable, "scripts/build_regular_options_13_symbol_frozen_candidate_generation_engine.py", "--no-write", *window_args],
        [sys.executable, "scripts/build_regular_options_scanner_materializer_parity_diff.py", "--end-date", end_date],
    ]
    return [_run_command(step) for step in steps]


def _holdout_start(path: Path) -> str | None:
    payload = _load_json(path)
    protected = payload.get("protected_range") if isinstance(payload.get("protected_range"), dict) else {}
    value = protected.get("start_date") or payload.get("protected_holdout_start") or payload.get("holdout_start")
    return str(value)[:10] if value else None


def build_report(
    *,
    db_path: Path = DEFAULT_DB,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOCS_REPORT,
    forward_cohort_path: Path = DEFAULT_FORWARD_COHORT,
    forward_holdout_path: Path = DEFAULT_FORWARD_HOLDOUT,
    source_label: str = DEFAULT_SOURCE_LABEL,
    theta_url: str = DEFAULT_THETA_URL,
    symbols: Sequence[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    timeout: float = 20.0,
    approval_token: str | None = None,
    dry_run: bool = False,
    refresh_after_import: bool = False,
    generated_at_utc: str | None = None,
    lock_path: Path = DEFAULT_LOCK_PATH,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    allowed = allowed_symbols(forward_cohort_path)
    selected_symbols = _parse_symbols(symbols or allowed)
    outside_requested = [symbol for symbol in selected_symbols if symbol not in set(allowed)]
    approval_valid = approval_token == APPROVAL_TOKEN
    window = compute_window(
        db_path=db_path,
        source_label=source_label,
        date_from=date_from,
        date_to=date_to,
        now_utc=datetime.fromisoformat(generated_at.replace("Z", "+00:00")),
    )
    requested_dates = list(window["requested_market_dates"])
    missing_rows = (
        missing_symbol_dates(
            db_path=db_path,
            source_label=source_label,
            symbols=selected_symbols,
            requested_dates=requested_dates,
        )
        if requested_dates and not outside_requested
        else []
    )
    blockers: list[str] = []
    if outside_requested:
        blockers.append("requested_symbols_outside_allowed_fresh_window_universe")
    if not dry_run and not approval_valid:
        blockers.append("approval_token_missing_or_invalid")
    active_store_writers = active_options_history_writer_processes()
    if not dry_run and missing_rows and active_store_writers:
        blockers.append("active_options_history_writer_process")

    import_result = {
        "import_attempted": False,
        "imported_rows": 0,
        "duplicate_rows": 0,
        "rejected_rows": 0,
        "generated_rows": 0,
        "request_count": 0,
        "warning_count": 0,
        "errors": [],
        "batch_results": [],
    }
    refresh_results: list[dict[str, Any]] = []
    lock_status = "not_requested"
    if not blockers and not dry_run and missing_rows:
        lock_payload = {
            "report_id": REPORT_ID,
            "pid": os.getpid(),
            "created_at_utc": generated_at,
            "window": window,
            "symbols": selected_symbols,
        }
        try:
            with ImportLock(lock_path, lock_payload):
                lock_status = "acquired"
                import_result = run_import(
                    db_path=db_path,
                    output_dir=output_dir,
                    symbols=selected_symbols,
                    missing_rows=missing_rows,
                    source_label=source_label,
                    theta_url=theta_url,
                    timeout=timeout,
                )
        except RuntimeError as exc:
            blockers.append("store_import_lock_present")
            import_result["errors"] = [str(exc)]
            lock_status = "blocked"
    elif missing_rows:
        lock_status = "skipped"

    batch_ids = _batch_ids(import_result)
    outside_universe_rows = _outside_universe_rows(db_path, batch_ids=batch_ids, symbols=selected_symbols)
    store_max_after = max_trusted_intraday_date(db_path, source_label=source_label)
    if outside_universe_rows:
        blockers.append("outside_universe_rows_detected")
    if import_result.get("errors"):
        blockers.append("provider_or_import_errors")
    if int(import_result.get("rejected_rows") or 0) > 0:
        blockers.append("rejected_rows_detected")

    if refresh_after_import and not dry_run and not blockers:
        refresh_results = refresh_materializer_chain(
            end_date=window["latest_completed_market_day"],
            as_of_date=window["latest_completed_market_day"],
        )
        if any(step.get("returncode") != 0 for step in refresh_results):
            blockers.append("post_import_materializer_refresh_failed")

    if dry_run:
        status = "dry_run_ready" if not blockers else "dry_run_blocked"
    elif blockers:
        status = "blocked_fresh_window_thetadata_opra_import"
    elif not missing_rows:
        status = "fresh_window_thetadata_opra_up_to_date"
    else:
        status = "fresh_window_thetadata_opra_imported"

    report = {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "status": status,
        "blockers": sorted(dict.fromkeys(blockers)),
        "dry_run": dry_run,
        "approval_token_valid": approval_valid,
        "source_label": source_label,
        "theta_url": theta_url,
        "allowed_universe": allowed,
        "symbols": selected_symbols,
        "outside_requested_symbols": outside_requested,
        "active_store_writer_processes": active_store_writers,
        "window": window,
        "missing_symbol_date_count": len(missing_rows),
        "requested_symbol_date_count": len(requested_dates) * len(selected_symbols),
        "lock_status": lock_status,
        "lock_path": _rel(lock_path),
        "store_max_intraday_date_before": window["store_max_intraday_date_before"],
        "store_max_intraday_date_after": store_max_after.isoformat() if store_max_after else None,
        "import_attempted": bool(import_result.get("import_attempted")),
        "quotes_imported": int(import_result.get("imported_rows") or 0) > 0,
        "imported_rows": int(import_result.get("imported_rows") or 0),
        "duplicate_rows": int(import_result.get("duplicate_rows") or 0),
        "rejected_rows": int(import_result.get("rejected_rows") or 0),
        "generated_rows": int(import_result.get("generated_rows") or 0),
        "request_count": int(import_result.get("request_count") or 0),
        "warning_count": int(import_result.get("warning_count") or 0),
        "import_errors": import_result.get("errors") or [],
        "import_batch_results": import_result.get("batch_results") or [],
        "outside_universe_import_rows": outside_universe_rows,
        "protected_holdout_overlap_rows": 0,
        "protected_holdout_measurement": {
            "protected_holdout_start_date": _holdout_start(forward_holdout_path),
            "basis": "quote_import_only_no_candidate_entry_rows_replay_rows_or_holdout_consumption",
            "candidate_or_replay_rows_created": 0,
        },
        "refresh_after_import": refresh_after_import,
        "refresh_results": refresh_results,
        **FALSE_FLAGS,
        "evidence_stores_mutated": bool(import_result.get("import_attempted")),
        "proof_policy": {
            "readback_is": "tokened fresh-window trusted ThetaData OPRA/NBBO source import plus optional materializer/parity refresh",
            "readback_is_not": "scanner policy change, filter selection, proof-bar change, live validation, auto-track, broker permission, protected-holdout consumption, or promotion",
        },
        "artifacts": {},
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    window = report.get("window") if isinstance(report.get("window"), dict) else {}
    lines = [
        "# Regular Options Fresh-Window ThetaData OPRA Import",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Dry run: `{str(report.get('dry_run')).lower()}`.",
        f"- Approval token valid: `{str(report.get('approval_token_valid')).lower()}`.",
        f"- Window: `{window.get('date_from')}` through `{window.get('date_to')}`.",
        f"- Latest completed market day: `{window.get('latest_completed_market_day')}`.",
        f"- Store max before: `{report.get('store_max_intraday_date_before')}`.",
        f"- Store max after: `{report.get('store_max_intraday_date_after')}`.",
        f"- Symbols: `{len(report.get('symbols') or [])}`.",
        f"- Missing symbol-dates: `{report.get('missing_symbol_date_count')}`.",
        f"- Active store writer processes: `{len(report.get('active_store_writer_processes') or [])}`.",
        f"- Import attempted: `{str(report.get('import_attempted')).lower()}`.",
        f"- Imported rows: `{report.get('imported_rows')}`.",
        f"- Rejected rows: `{report.get('rejected_rows')}`.",
        f"- Outside-universe import rows: `{report.get('outside_universe_import_rows')}`.",
        f"- Protected holdout overlap rows: `{report.get('protected_holdout_overlap_rows')}`.",
        f"- Refresh after import: `{str(report.get('refresh_after_import')).lower()}`.",
        "",
        "This tokened import only refreshes trusted quote/source coverage through the guarded importer. It does not change scanner policy, filters, proof bars, stops, sizing, live validation, auto-track, broker behavior, holdout policy, or promotion.",
        "",
    ]
    blockers = report.get("blockers") if isinstance(report.get("blockers"), list) else []
    if blockers:
        lines.extend(["## Blockers", ""])
        lines.extend(f"- `{item}`" for item in blockers)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_outputs(report: dict[str, Any], *, output_dir: Path, docs_report: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    artifacts = {
        "json": _rel(json_path),
        "markdown": _rel(md_path),
        "latest_json": _rel(latest_json),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
    }
    payload = dict(report)
    payload["artifacts"] = artifacts
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    text = render_markdown(payload)
    json_path.write_text(serialized, encoding="utf8")
    latest_json.write_text(serialized, encoding="utf8")
    md_path.write_text(text, encoding="utf8")
    latest_md.write_text(text, encoding="utf8")
    docs_report.write_text(text, encoding="utf8")
    return artifacts


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import fresh-window trusted ThetaData OPRA/NBBO rows.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--forward-cohort", type=Path, default=DEFAULT_FORWARD_COHORT)
    parser.add_argument("--forward-holdout", type=Path, default=DEFAULT_FORWARD_HOLDOUT)
    parser.add_argument("--source-label", default=DEFAULT_SOURCE_LABEL)
    parser.add_argument("--theta-url", default=DEFAULT_THETA_URL)
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--date-from", type=_parse_date, default=None)
    parser.add_argument("--date-to", type=_parse_date, default=None)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--approval-token", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--refresh-after-import", action="store_true")
    parser.add_argument("--lock-path", type=Path, default=DEFAULT_LOCK_PATH)
    parser.add_argument("--no-write-report", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_report(
        db_path=args.db,
        output_dir=args.output_dir,
        docs_report=args.docs_report,
        forward_cohort_path=args.forward_cohort,
        forward_holdout_path=args.forward_holdout,
        source_label=args.source_label,
        theta_url=args.theta_url,
        symbols=args.symbols,
        date_from=args.date_from,
        date_to=args.date_to,
        timeout=args.timeout,
        approval_token=args.approval_token,
        dry_run=args.dry_run,
        refresh_after_import=args.refresh_after_import,
        lock_path=args.lock_path,
    )
    if not args.no_write_report:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0 if report["status"] in {"dry_run_ready", "fresh_window_thetadata_opra_up_to_date", "fresh_window_thetadata_opra_imported"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
