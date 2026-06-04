from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from historical_options_store import INTRADAY_SNAPSHOT_KIND, import_historical_option_snapshots  # noqa: E402
from scripts.import_thetadata_options_nbbo import (  # noqa: E402
    CSV_FIELDNAMES,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SOURCE_LABEL,
    DEFAULT_THETA_URL,
    INTRADAY_DATASET_KIND,
    _extract_rows,
    _normalize_theta_quote_row,
)
from scripts.regular_options_repair_targets import (  # noqa: E402
    base_target_key,
    expand_items,
    json_item,
    missing_items_from_run_paths,
    original_target_key,
    repair_attempt_key,
    repair_manifest,
    target_filters,
)


def _theta_rows_for_contract(
    session: requests.Session,
    *,
    theta_url: str,
    item: dict[str, Any],
    start_time: str,
    end_time: str,
    interval: str,
    timeout: float,
) -> list[dict[str, str]]:
    trade_date: date = item["quote_date"]
    params: dict[str, Any] = {
        "symbol": item["root"],
        "expiration": item["expiry"].strftime("%Y%m%d"),
        "date": trade_date.strftime("%Y%m%d"),
        "interval": interval,
        "format": "json",
        "start_time": start_time,
        "end_time": end_time,
        "right": item["right"],
        "strike": item["strike"],
    }
    response = session.get(f"{theta_url.rstrip('/')}/v3/option/history/quote", params=params, timeout=timeout)
    response.raise_for_status()

    matches: list[dict[str, str]] = []
    for raw_row in _extract_rows(response.json()):
        normalized = _normalize_theta_quote_row(raw_row, underlying=item["root"], trade_date=trade_date)
        if not normalized:
            continue
        if normalized["contract_symbol"] == item["contract_symbol"]:
            matches.append(normalized)
    return matches


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _rel(path: Path | str | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    try:
        return str(candidate.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(candidate).replace("\\", "/")


def _source_artifacts_for_item(item: dict[str, Any]) -> list[str]:
    artifacts = {
        normalized
        for row in item.get("source_occurrences") or []
        if row.get("run_path")
        for normalized in [_rel(row.get("run_path"))]
        if normalized
    }
    return sorted(artifacts)


def _tickers_for_item(item: dict[str, Any]) -> list[str]:
    return sorted({str(row.get("ticker") or "").upper() for row in item.get("source_occurrences") or [] if row.get("ticker")})


def _initial_attempts(base_items: list[dict[str, Any]], *, source_label: str) -> dict[tuple[str, str], dict[str, Any]]:
    attempts: dict[tuple[str, str], dict[str, Any]] = {}
    for item in base_items:
        key = base_target_key(item)
        missing_quote_date, contract_symbol = key
        source_artifacts = _source_artifacts_for_item(item)
        tickers = _tickers_for_item(item)
        attempt_keys = [
            repair_attempt_key(
                source_artifact=artifact,
                ticker=ticker if len(tickers) == 1 else "",
                contract_symbol=contract_symbol,
                missing_quote_date=missing_quote_date,
            )
            for artifact in source_artifacts
            for ticker in (tickers or [""])
        ]
        if not attempt_keys:
            attempt_keys = [
                repair_attempt_key(
                    source_artifact="",
                    ticker=tickers[0] if len(tickers) == 1 else "",
                    contract_symbol=contract_symbol,
                    missing_quote_date=missing_quote_date,
                )
            ]
        attempts[key] = {
            "repair_attempt_key": attempt_keys[0],
            "repair_attempt_keys": sorted(set(attempt_keys)),
            "source_label": source_label,
            "source_artifacts": source_artifacts,
            "tickers": tickers,
            "contract_symbol": contract_symbol,
            "missing_quote_date": missing_quote_date,
            "exact_date_row_count": 0,
            "lookahead_row_count": 0,
            "total_row_count": 0,
            "request_dates_attempted": [],
            "available_quote_dates": [],
            "errors": [],
            "source_occurrences": json_item(item).get("source_occurrences") or [],
        }
    return attempts


def _record_request_date(attempt: dict[str, Any], request_date: str) -> None:
    dates = set(attempt.get("request_dates_attempted") or [])
    dates.add(request_date)
    attempt["request_dates_attempted"] = sorted(dates)


def _record_available_date(attempt: dict[str, Any], quote_date: str) -> None:
    dates = set(attempt.get("available_quote_dates") or [])
    dates.add(quote_date)
    attempt["available_quote_dates"] = sorted(dates)


def _finalize_attempt(attempt: dict[str, Any], *, plan_only: bool, import_performed: bool) -> dict[str, Any]:
    exact_count = int(attempt.get("exact_date_row_count") or 0)
    lookahead_count = int(attempt.get("lookahead_row_count") or 0)
    available_dates = sorted(str(value) for value in attempt.get("available_quote_dates") or [])
    missing_quote_date = str(attempt.get("missing_quote_date") or "")[:10]
    first_after = next((value for value in available_dates if value > missing_quote_date), None)
    if plan_only:
        outcome = "planned_not_requested"
        exact_status = "not_requested"
        proof_status = "not_requested"
    elif exact_count > 0 and import_performed:
        outcome = "imported_pending_replay"
        exact_status = "rows_found"
        proof_status = "exact_date_imported_pending_replay"
    elif exact_count > 0:
        outcome = "exact_date_rows_found"
        exact_status = "rows_found"
        proof_status = "exact_date_repair_candidate"
    elif lookahead_count > 0:
        outcome = "lookahead_only_rows_found"
        exact_status = "no_rows_found"
        proof_status = "lookahead_only_not_exact_proof"
    else:
        outcome = "exact_date_no_match"
        exact_status = "no_rows_found"
        proof_status = "current_source_exhausted"
    return {
        **attempt,
        "available_quote_dates": available_dates,
        "first_available_after_missing_date": first_after,
        "outcome": outcome,
        "exact_missing_date_status": exact_status,
        "proof_repair_status": proof_status,
        "current_source_exhausted_for_exact_date": not plan_only and exact_count == 0,
    }


def _finalized_attempts(
    attempts: dict[tuple[str, str], dict[str, Any]],
    *,
    plan_only: bool,
    import_performed: bool,
) -> list[dict[str, Any]]:
    return [
        _finalize_attempt(attempt, plan_only=plan_only, import_performed=import_performed)
        for _, attempt in sorted(attempts.items(), key=lambda item: item[0])
    ]


def _attempt_summary(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "attempt_count": len(attempts),
        "outcome_counts": dict(sorted(Counter(str(item.get("outcome")) for item in attempts).items())),
        "proof_repair_status_counts": dict(
            sorted(Counter(str(item.get("proof_repair_status")) for item in attempts).items())
        ),
        "exact_date_row_count": sum(int(item.get("exact_date_row_count") or 0) for item in attempts),
        "lookahead_row_count": sum(int(item.get("lookahead_row_count") or 0) for item in attempts),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Import exact ThetaData quotes needed by replay unpriced trades.")
    parser.add_argument("run_paths", nargs="+", type=Path)
    parser.add_argument("--theta-url", default=DEFAULT_THETA_URL)
    parser.add_argument("--source", default=DEFAULT_SOURCE_LABEL)
    parser.add_argument("--snapshot-kind", default=INTRADAY_SNAPSHOT_KIND, choices=(INTRADAY_SNAPSHOT_KIND,))
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--start-time", default="15:55:00")
    parser.add_argument("--end-time", default="15:55:00")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--db-path")
    parser.add_argument(
        "--lookahead-calendar-days",
        type=int,
        default=0,
        help="Also request this many calendar days after each missing quote date, capped at expiration.",
    )
    parser.add_argument("--max-requests", type=int, default=0, help="Optional cap on expanded ThetaData requests.")
    parser.add_argument(
        "--ticker",
        action="append",
        default=[],
        help="Limit targets to one or more comma-separated tickers. Can be repeated.",
    )
    parser.add_argument(
        "--contract-symbol",
        action="append",
        default=[],
        help="Limit targets to one or more comma-separated exact OCC contract symbols. Can be repeated.",
    )
    parser.add_argument(
        "--quote-date",
        action="append",
        default=[],
        help="Limit targets to one or more comma-separated missing quote dates in YYYY-MM-DD form. Can be repeated.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Fetch and normalize rows, but do not write summaries, CSVs, or DB imports.")
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Print the de-duplicated repair manifest without requesting ThetaData or writing files.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    run_paths = [path.resolve() for path in args.run_paths]
    filters = target_filters(
        tickers=args.ticker,
        contract_symbols=args.contract_symbol,
        quote_dates=args.quote_date,
    )
    base_items = missing_items_from_run_paths(
        run_paths,
        tickers=set(filters["tickers"]),
        contract_symbols=set(filters["contract_symbols"]),
        quote_dates=set(filters["quote_dates"]),
    )
    items = expand_items(base_items, lookahead_calendar_days=int(args.lookahead_calendar_days))
    expanded_item_count = len(items)
    if int(args.max_requests) > 0:
        items = items[: int(args.max_requests)]
    no_write = bool(args.dry_run or args.plan_only)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    csv_path = Path(args.output_dir) / f"thetadata_opra_nbbo_exact_missing_intraday_{stamp}.csv"
    summary_path = Path(args.output_dir) / f"thetadata_exact_missing_intraday_{stamp}.json"

    rows: list[dict[str, str]] = []
    errors: list[str] = []
    rows_by_contract: Counter[str] = Counter()
    rows_by_date: Counter[str] = Counter()
    request_count = 0
    attempts = _initial_attempts(base_items, source_label=args.source)
    if not args.plan_only:
        with requests.Session() as session:
            for item in items:
                attempt = attempts.get(original_target_key(item))
                request_date = str(item["quote_date"])
                if attempt is not None:
                    _record_request_date(attempt, request_date)
                try:
                    matches = _theta_rows_for_contract(
                        session,
                        theta_url=args.theta_url,
                        item=item,
                        start_time=args.start_time,
                        end_time=args.end_time,
                        interval=args.interval,
                        timeout=float(args.timeout),
                    )
                    request_count += 1
                except Exception as exc:
                    error = f"{item['quote_date']} {item['contract_symbol']}: {exc}"
                    errors.append(error)
                    if attempt is not None:
                        attempt["errors"].append(error)
                    continue
                if not matches:
                    error = f"{item['quote_date']} {item['contract_symbol']}: no matched rows"
                    errors.append(error)
                    if attempt is not None:
                        attempt["errors"].append(error)
                    continue
                for row in matches:
                    rows.append(row)
                    rows_by_contract[row["contract_symbol"]] += 1
                    rows_by_date[row["as_of_utc"][:10]] += 1
                    if attempt is not None:
                        row_date = row["as_of_utc"][:10]
                        _record_available_date(attempt, row_date)
                        attempt["total_row_count"] += 1
                        if row_date == attempt["missing_quote_date"]:
                            attempt["exact_date_row_count"] += 1
                        else:
                            attempt["lookahead_row_count"] += 1

    import_result = None
    if rows and not no_write:
        _write_csv(csv_path, rows)
        import_result = import_historical_option_snapshots(
            csv_path,
            args.source,
            dataset_kind=INTRADAY_DATASET_KIND,
            snapshot_kind=args.snapshot_kind,
            db_path=args.db_path,
        )

    repair_attempts = _finalized_attempts(
        attempts,
        plan_only=bool(args.plan_only),
        import_performed=bool(import_result),
    )
    payload = {
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "input_run_paths": [str(path) for path in run_paths],
        "target_filters": filters,
        "dry_run": bool(args.dry_run),
        "plan_only": bool(args.plan_only),
        "write_artifacts": not no_write,
        "base_unique_items": len(base_items),
        "unique_items": len(items),
        "expanded_unique_items": expanded_item_count,
        "request_count": request_count,
        "lookahead_calendar_days": int(args.lookahead_calendar_days),
        "normalized_rows": len(rows),
        "csv_path": None if no_write or not rows else str(csv_path.resolve()),
        "summary_path": None if no_write else str(summary_path.resolve()),
        "repair_manifest": repair_manifest(
            base_items=base_items,
            request_items=items,
            expanded_item_count=expanded_item_count,
            max_requests=int(args.max_requests),
        ),
        "repair_attempts": repair_attempts,
        "repair_attempt_summary": _attempt_summary(repair_attempts),
        "rows_by_contract": dict(sorted(rows_by_contract.items())),
        "rows_by_date": dict(sorted(rows_by_date.items())),
        "errors": errors,
        "import_result": import_result,
    }
    if not no_write:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf8")
    print(
        json.dumps(
            payload
            if args.json
            else {
                k: payload[k]
                for k in (
                    "dry_run",
                    "plan_only",
                    "unique_items",
                    "request_count",
                    "normalized_rows",
                    "csv_path",
                    "summary_path",
                    "import_result",
                )
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
