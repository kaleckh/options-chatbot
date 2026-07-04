from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_regular_options_filtered_forward_paper_shadow_tracker as tracker  # noqa: E402


REPORT_ID = "regular_options_filtered_forward_exit_evidence_capture"
DEFAULT_MATCHED_ROWS_LOG = tracker.DEFAULT_MATCHED_ROWS_LOG
DEFAULT_EXIT_EVIDENCE = tracker.DEFAULT_OUTPUT_DIR / "exit_evidence.jsonl"
DEFAULT_OPTIONS_HISTORY_DB = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_LATEST_JSON = tracker.DEFAULT_OUTPUT_DIR / "exit_evidence_capture_latest.json"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-filtered-forward-exit-evidence-capture.md"
THETADATA_SOURCE_LABEL = "thetadata_opra_nbbo_1m"
EXIT_WINDOW_START_MINUTE = 15 * 60 + 50
CONTRACT_MULTIPLIER = tracker.CONTRACT_MULTIPLIER
DEFAULT_FEE_PER_CONTRACT_LEG_USD = tracker.DEFAULT_FEE_PER_CONTRACT_LEG_USD


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _norm_lower(value: Any) -> str:
    return _norm(value).lower()


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _file_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.exists():
        return [], {"path": _rel(path), "exists": False, "status": "missing", "row_count": 0, "bad_row_count": 0}
    rows: list[dict[str, Any]] = []
    bad = 0
    for raw in path.read_text(encoding="utf8").splitlines():
        if not raw.strip():
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            bad += 1
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
        else:
            bad += 1
    status = "loaded" if bad == 0 else "malformed"
    return rows, {"path": _rel(path), "exists": True, "status": status, "row_count": len(rows), "bad_row_count": bad}


def _append_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), sort_keys=True, separators=(",", ":")) + "\n")


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(_norm(value)[:10])
    except ValueError:
        return None


def _is_weekday_market_day(value: date) -> bool:
    return value.weekday() < 5


def _latest_completed_market_day(now_utc: str) -> date:
    parsed = datetime.fromisoformat(now_utc.replace("Z", "+00:00")).astimezone(UTC)
    current = parsed.date()
    if parsed.time() < datetime.strptime("21:00:00", "%H:%M:%S").time():
        current = current - timedelta(days=1)
    while not _is_weekday_market_day(current):
        current -= timedelta(days=1)
    return current


def _market_day_on_or_after(target: date, *, latest: date) -> date | None:
    current = target
    while current <= latest:
        if _is_weekday_market_day(current):
            return current
        current += timedelta(days=1)
    return None


def _policy_exit_date(row: dict[str, Any]) -> date | None:
    target = _parse_date(row.get("policy_exit_date")) or _parse_date(tracker._policy_exit_date(row))
    expiry = _parse_date(row.get("expiry"))
    if target is None or expiry is None:
        return None
    return _market_day_on_or_after(target, latest=expiry)


def _current_lifecycle_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return tracker._merge_lifecycle_rows(rows)


def _completed_candidate_ids(rows: Sequence[dict[str, Any]]) -> set[str]:
    return {_norm(row.get("candidate_id")) for row in rows if tracker._is_completed_forward_row(row)}


def _trusted_quote_from_db(
    conn: sqlite3.Connection,
    *,
    contract_symbol: str,
    quote_date: date,
) -> dict[str, Any] | None:
    try:
        row = conn.execute(
            """
            SELECT q.bid, q.ask, q.as_of_utc, q.quote_minute_et, b.source_label
            FROM option_quote_snapshots q
            JOIN import_batches b ON b.id = q.source_batch_id
            WHERE q.contract_symbol = ?
              AND q.quote_date_et = ?
              AND q.snapshot_kind = 'intraday'
              AND q.quote_minute_et >= ?
              AND b.source_label = ?
              AND b.data_trust = 'trusted'
            ORDER BY q.quote_minute_et ASC, q.as_of_utc ASC
            LIMIT 1
            """,
            (contract_symbol, quote_date.isoformat(), EXIT_WINDOW_START_MINUTE, THETADATA_SOURCE_LABEL),
        ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    return {
        "bid": _safe_float(row[0]),
        "ask": _safe_float(row[1]),
        "as_of_utc": row[2],
        "quote_minute_et": row[3],
        "source_label": row[4],
    }


def _evidence_by_candidate(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        candidate_id = _norm(row.get("candidate_id") or row.get("source_candidate_id"))
        if not candidate_id and _norm(row.get("ticker") or row.get("symbol")) and tracker._candidate_date(row):
            candidate_id = tracker._candidate_identity(row)
        if candidate_id and candidate_id not in indexed:
            indexed[candidate_id] = dict(row)
    return indexed


def _trusted_live_evidence(row: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    reasons: list[str] = []
    source = _norm(row.get("exit_quote_source") or row.get("quote_source"))
    if not source:
        reasons.append("missing_exit_quote_source")
    elif _norm_lower(source) not in tracker.TRUSTED_EXECUTABLE_QUOTE_SOURCES:
        reasons.append("untrusted_exit_quote_source")
    timestamp = _norm(row.get("exit_quote_timestamp_utc") or row.get("quote_timestamp_utc") or row.get("captured_at_utc"))
    if not timestamp:
        reasons.append("missing_exit_quote_timestamp")
    long_bid = _safe_float(row.get("long_exit_bid") if row.get("long_exit_bid") is not None else row.get("exit_long_bid"))
    short_ask = _safe_float(row.get("short_exit_ask") if row.get("short_exit_ask") is not None else row.get("exit_short_ask"))
    if long_bid is None:
        reasons.append("missing_long_exit_bid")
    if short_ask is None:
        reasons.append("missing_short_exit_ask")
    text = " ".join(_norm(row.get(key)).lower() for key in ("quote_evidence_class", "exit_price_source", "pnl_basis"))
    if any(token in text for token in ("midpoint", "eod", "display", "last", "manual", "model", "synthetic", "lookahead")):
        reasons.append("non_executable_exit_basis")
    if reasons:
        return None, reasons
    return {
        "source_label": source,
        "timestamp_utc": timestamp,
        "long_bid": long_bid,
        "short_ask": short_ask,
        "long_ask": _safe_float(row.get("long_exit_ask") if row.get("long_exit_ask") is not None else row.get("exit_long_ask")),
        "short_bid": _safe_float(row.get("short_exit_bid") if row.get("short_exit_bid") is not None else row.get("exit_short_bid")),
        "basis": "trusted_live_exit_evidence_jsonl",
    }, []


def _completion_row(entry: dict[str, Any], exit_quote: dict[str, Any], *, exit_date: date) -> dict[str, Any] | None:
    entry_debit = _safe_float(entry.get("entry_debit") if entry.get("entry_debit") is not None else entry.get("net_debit"))
    long_bid = _safe_float(exit_quote.get("long_bid"))
    short_ask = _safe_float(exit_quote.get("short_ask"))
    if entry_debit is None or entry_debit <= 0 or long_bid is None or short_ask is None:
        return None
    raw_exit_value = long_bid - short_ask
    exit_value = max(0.0, raw_exit_value)
    pnl_pct = (exit_value - entry_debit) / entry_debit * 100.0
    total_fees_usd = 4.0 * DEFAULT_FEE_PER_CONTRACT_LEG_USD
    gross_pnl_usd = (exit_value - entry_debit) * CONTRACT_MULTIPLIER
    net_pnl_usd = gross_pnl_usd - total_fees_usd
    net_pnl_pct_after_fees = net_pnl_usd / (entry_debit * CONTRACT_MULTIPLIER) * 100.0
    completed = dict(entry)
    completed.update(
        {
            "record_type": "completion",
            "lifecycle_event": "completed_exact_exit",
            "tracking_state": "forward_paper_shadow_completed",
            "planned_exit_status": "policy_exit_reached",
            "realized_pnl_status": "completed_exact_exit",
            "exit_date": exit_date.isoformat(),
            "exit_reason": "fixed_75pct_dte_time_exit",
            "exit_quote_source": exit_quote.get("source_label"),
            "exit_quote_timestamp_utc": exit_quote.get("timestamp_utc"),
            "long_exit_bid": long_bid,
            "long_exit_ask": exit_quote.get("long_ask"),
            "short_exit_bid": exit_quote.get("short_bid"),
            "short_exit_ask": short_ask,
            "exit_value": round(exit_value, 4),
            "exit_value_floored_at_zero": raw_exit_value < 0.0,
            "gross_pnl_usd": round(gross_pnl_usd, 4),
            "total_fees_usd": round(total_fees_usd, 4),
            "net_pnl_usd": round(net_pnl_usd, 4),
            "net_pnl_pct": round(pnl_pct, 4),
            "net_pnl_pct_after_fees": round(net_pnl_pct_after_fees, 4),
            "exit_capture_basis": exit_quote.get("basis"),
            "append_only_log": True,
        }
    )
    return completed


def build_report(
    *,
    matched_rows_log_path: Path = DEFAULT_MATCHED_ROWS_LOG,
    exit_evidence_path: Path = DEFAULT_EXIT_EVIDENCE,
    options_history_db_path: Path = DEFAULT_OPTIONS_HISTORY_DB,
    latest_json_path: Path = DEFAULT_LATEST_JSON,
    docs_report_path: Path = DEFAULT_DOCS_REPORT,
    no_write: bool = False,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    latest_market_day = _latest_completed_market_day(generated_at)
    log_rows, log_source = _load_jsonl(matched_rows_log_path)
    evidence_rows, evidence_source = _load_jsonl(exit_evidence_path)
    current_rows = _current_lifecycle_rows(log_rows)
    completed_ids = _completed_candidate_ids(log_rows)
    live_evidence = _evidence_by_candidate(evidence_rows)
    reject_counts: Counter[str] = Counter()
    row_results: list[dict[str, Any]] = []
    completions: list[dict[str, Any]] = []
    duplicate_identities = tracker._matched_log_duplicate_daily_signal_identities(log_rows)
    blockers: list[str] = []
    if log_rows and not tracker._matched_log_has_current_identity_schema(log_rows):
        blockers.append("matched_rows_log_nonempty_before_daily_signal_identity_upgrade")
    if duplicate_identities:
        blockers.append("duplicate_ticker_date_direction_matched_rows")
    conn: sqlite3.Connection | None = None
    if options_history_db_path.exists() and not blockers:
        conn = sqlite3.connect(f"file:{options_history_db_path}?mode=ro", uri=True)
    try:
        for row in ([] if blockers else current_rows):
            candidate_id = _norm(row.get("candidate_id"))
            if not candidate_id or candidate_id in completed_ids:
                continue
            exit_date = _policy_exit_date(row)
            if exit_date is None:
                reject_counts["missing_policy_exit_date"] += 1
                row_results.append({"candidate_id": candidate_id, "status": "missing_policy_exit_date"})
                continue
            if exit_date > latest_market_day:
                row_results.append({"candidate_id": candidate_id, "status": "policy_exit_not_due", "policy_exit_date": exit_date.isoformat()})
                continue
            exit_quote: dict[str, Any] | None = None
            if conn is not None:
                long_quote = _trusted_quote_from_db(conn, contract_symbol=_norm(row.get("long_contract_symbol")), quote_date=exit_date)
                short_quote = _trusted_quote_from_db(conn, contract_symbol=_norm(row.get("short_contract_symbol")), quote_date=exit_date)
                if long_quote and short_quote:
                    exit_quote = {
                        "source_label": THETADATA_SOURCE_LABEL,
                        "timestamp_utc": long_quote.get("as_of_utc"),
                        "long_bid": long_quote.get("bid"),
                        "long_ask": long_quote.get("ask"),
                        "short_bid": short_quote.get("bid"),
                        "short_ask": short_quote.get("ask"),
                        "basis": "trusted_thetadata_intraday_options_history_db_read_only",
                    }
            if exit_quote is None and candidate_id in live_evidence:
                exit_quote, reasons = _trusted_live_evidence(live_evidence[candidate_id])
                for reason in reasons:
                    reject_counts[reason] += 1
                if reasons:
                    row_results.append({"candidate_id": candidate_id, "status": "exit_evidence_rejected", "reject_reasons": reasons})
                    continue
            if exit_quote is None:
                status = "exit_window_missed_awaiting_trusted_backfill" if exit_date < latest_market_day else "exit_window_waiting_for_live_capture_or_backfill"
                row_results.append({"candidate_id": candidate_id, "status": status, "policy_exit_date": exit_date.isoformat()})
                continue
            completion = _completion_row(row, exit_quote, exit_date=exit_date)
            if completion is None:
                reject_counts["completion_pnl_inputs_missing"] += 1
                row_results.append({"candidate_id": candidate_id, "status": "completion_pnl_inputs_missing"})
                continue
            completions.append(completion)
            row_results.append({"candidate_id": candidate_id, "status": "completion_appended" if not no_write else "completion_ready_no_write", "policy_exit_date": exit_date.isoformat()})
    finally:
        if conn is not None:
            conn.close()
    if completions and not no_write:
        _append_jsonl(matched_rows_log_path, completions)
    status = "exit_completion_waiting_for_matched_rows"
    if blockers:
        status = "blocked_filtered_forward_exit_capture"
    elif log_source.get("status") == "loaded" and current_rows:
        status = "exit_completion_waiting_for_due_rows"
    if completions:
        status = "exit_completion_appended" if not no_write else "exit_completion_ready_no_write"
    elif reject_counts:
        status = "exit_completion_rows_rejected"
    report = {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "status": status,
        "no_write": no_write,
        "matched_rows_log": {**log_source, "sha256": _file_hash(matched_rows_log_path)},
        "exit_evidence_source": {**evidence_source, "sha256": _file_hash(exit_evidence_path)},
        "options_history_db": {"path": _rel(options_history_db_path), "exists": options_history_db_path.exists(), "read_only": True},
        "latest_completed_market_day": latest_market_day.isoformat(),
        "open_candidate_count": len([row for row in current_rows if not tracker._is_completed_forward_row(row)]),
        "completion_rows_ready": len(completions),
        "completion_rows_appended": 0 if no_write else len(completions),
        "reject_counts": dict(sorted(reject_counts.items())),
        "row_results": row_results,
        "blockers": blockers,
        "duplicate_daily_signal_identities": duplicate_identities,
        "accepted_profitability": False,
        "approval_authority": False,
        "historical_rows_are_forward_proof": False,
        "scanner_policy_changed": False,
        "live_validation_enabled": False,
        "auto_track_enabled": False,
        "broker_order_allowed": False,
        "quotes_imported": False,
        "options_history_db_mutated": False,
        "evidence_stores_mutated": False,
        "protected_holdout_consumed": False,
        "prohibited_actions": [
            "do_not_import_quotes_from_exit_capture",
            "do_not_mutate_options_history_db_from_exit_capture",
            "do_not_submit_broker_orders_from_exit_capture",
            "do_not_enable_live_validation_from_exit_capture",
            "do_not_enable_auto_track_from_exit_capture",
            "do_not_change_scanner_policy_from_exit_capture",
            "do_not_promote_from_exit_capture",
        ],
    }
    if not no_write:
        latest_json_path.parent.mkdir(parents=True, exist_ok=True)
        docs_report_path.parent.mkdir(parents=True, exist_ok=True)
        latest_json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
        docs_report_path.write_text(render_markdown(report) + "\n", encoding="utf8")
    return report


def render_markdown(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Regular Options Filtered Forward Exit Evidence Capture",
            "",
            f"- Status: `{report.get('status')}`.",
            f"- Open candidates: `{report.get('open_candidate_count')}`.",
            f"- Completion rows ready: `{report.get('completion_rows_ready')}`.",
            f"- Completion rows appended: `{report.get('completion_rows_appended')}`.",
            f"- Latest completed market day: `{report.get('latest_completed_market_day')}`.",
            f"- Reject counts: `{json.dumps(report.get('reject_counts') or {}, sort_keys=True)}`.",
            "",
            "This script appends completion events only to the filtered forward matched-row log. It reads trusted quote stores in read-only mode and never imports quotes, submits orders, creates tracked positions, or changes scanner policy.",
            "",
        ]
    )


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture/complete filtered forward paper-shadow exact exits.")
    parser.add_argument("--matched-rows-log", type=Path, default=DEFAULT_MATCHED_ROWS_LOG)
    parser.add_argument("--exit-evidence", type=Path, default=DEFAULT_EXIT_EVIDENCE)
    parser.add_argument("--options-history-db", type=Path, default=DEFAULT_OPTIONS_HISTORY_DB)
    parser.add_argument("--latest-json", type=Path, default=DEFAULT_LATEST_JSON)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(list(argv))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(
        matched_rows_log_path=args.matched_rows_log,
        exit_evidence_path=args.exit_evidence,
        options_history_db_path=args.options_history_db,
        latest_json_path=args.latest_json,
        docs_report_path=args.docs_report,
        no_write=args.no_write,
    )
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
