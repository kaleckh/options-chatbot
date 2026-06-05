from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.import_missing_replay_quotes_from_thetadata import _finalized_attempts, _initial_attempts  # noqa: E402
from scripts.regular_options_repair_targets import (  # noqa: E402
    expand_items,
    missing_items_from_run_paths,
    original_target_key,
    target_filters,
)


DEFAULT_IMPORT_OUTPUT_DIR = ROOT / "data" / "options-validation" / "thetadata-nbbo"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-repair-attempts"
DEFAULT_DOC = ROOT / "docs" / "regular-options-repair-attempts.md"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path | str | None) -> str | None:
    if path is None:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    try:
        return str(candidate.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(candidate).replace("\\", "/")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf8"))
    return payload if isinstance(payload, dict) else {}


def _resolve_path(path_value: Any) -> Path | None:
    if not path_value:
        return None
    path = Path(str(path_value))
    if not path.is_absolute():
        path = ROOT / path
    return path


def _default_summary_paths(import_output_dir: Path = DEFAULT_IMPORT_OUTPUT_DIR) -> list[Path]:
    if not import_output_dir.exists():
        return []
    return sorted(import_output_dir.glob("thetadata_exact_missing_intraday_*.json"))


def _key_parts(repair_attempt_key: str) -> dict[str, str]:
    source_artifact, ticker, contract_symbol, missing_quote_date = (repair_attempt_key.split("|", 3) + ["", "", "", ""])[
        :4
    ]
    return {
        "source_artifact": source_artifact,
        "ticker": ticker,
        "contract_symbol": contract_symbol,
        "missing_quote_date": missing_quote_date[:10],
    }


def _flatten_attempts(summary_path: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    generated_at = str(payload.get("generated_at_utc") or "")
    rows: list[dict[str, Any]] = []
    for attempt in payload.get("repair_attempts") or []:
        if not isinstance(attempt, dict):
            continue
        keys = attempt.get("repair_attempt_keys") or [attempt.get("repair_attempt_key")]
        for key in [str(value) for value in keys if value]:
            parts = _key_parts(key)
            row = {
                "repair_attempt_key": key,
                **parts,
                "summary_path": _rel(summary_path),
                "summary_generated_at_utc": generated_at,
                "dry_run": bool(payload.get("dry_run")),
                "plan_only": bool(payload.get("plan_only")),
                "write_artifacts": bool(payload.get("write_artifacts")),
                "source_label": attempt.get("source_label") or payload.get("source"),
                "outcome": attempt.get("outcome"),
                "proof_repair_status": attempt.get("proof_repair_status"),
                "exact_missing_date_status": attempt.get("exact_missing_date_status"),
                "exact_date_row_count": int(attempt.get("exact_date_row_count") or 0),
                "lookahead_row_count": int(attempt.get("lookahead_row_count") or 0),
                "total_row_count": int(attempt.get("total_row_count") or 0),
                "request_dates_attempted": list(attempt.get("request_dates_attempted") or []),
                "available_quote_dates": list(attempt.get("available_quote_dates") or []),
                "first_available_after_missing_date": attempt.get("first_available_after_missing_date"),
                "current_source_exhausted_for_exact_date": bool(
                    attempt.get("current_source_exhausted_for_exact_date")
                ),
                "errors": list(attempt.get("errors") or []),
            }
            rows.append(row)
    return rows


def _csv_counts(csv_path: Path | None) -> dict[tuple[str, str], int]:
    if csv_path is None or not csv_path.exists():
        return {}
    counts: dict[tuple[str, str], int] = Counter()
    try:
        with csv_path.open("r", encoding="utf8", newline="") as handle:
            for row in csv.DictReader(handle):
                contract = str(row.get("contract_symbol") or "").upper()
                as_of = str(row.get("as_of_utc") or "")[:10]
                if contract and as_of:
                    counts[(contract, as_of)] += 1
    except Exception:
        return {}
    return dict(counts)


def _legacy_source_label(payload: dict[str, Any]) -> str:
    import_result = payload.get("import_result") if isinstance(payload.get("import_result"), dict) else {}
    return str(payload.get("source") or import_result.get("source_label") or "thetadata_opra_nbbo_1m")


def _legacy_run_paths(payload: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for value in payload.get("input_run_paths") or []:
        path = _resolve_path(value)
        if path is not None and path.exists():
            paths.append(path)
    return paths


def _legacy_filter_sets(payload: dict[str, Any]) -> dict[str, set[str]]:
    raw = payload.get("target_filters") if isinstance(payload.get("target_filters"), dict) else {}
    filters = target_filters(
        tickers=[str(value) for value in raw.get("tickers") or []],
        contract_symbols=[str(value) for value in raw.get("contract_symbols") or []],
        quote_dates=[str(value) for value in raw.get("quote_dates") or []],
    )
    return {
        "tickers": set(filters["tickers"]),
        "contract_symbols": set(filters["contract_symbols"]),
        "quote_dates": set(filters["quote_dates"]),
    }


def _legacy_request_dates(base_items: list[dict[str, Any]], payload: dict[str, Any]) -> dict[tuple[str, str], list[str]]:
    request_dates: dict[tuple[str, str], set[str]] = {}
    expanded = expand_items(base_items, lookahead_calendar_days=int(payload.get("lookahead_calendar_days") or 0))
    for item in expanded:
        key = original_target_key(item)
        quote_date = item.get("quote_date")
        request_dates.setdefault(key, set()).add(quote_date.isoformat() if hasattr(quote_date, "isoformat") else str(quote_date))
    return {key: sorted(values) for key, values in request_dates.items()}


def _flatten_legacy_attempts(summary_path: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    if payload.get("repair_attempts"):
        return []
    run_paths = _legacy_run_paths(payload)
    if not run_paths:
        return []
    filters = _legacy_filter_sets(payload)
    try:
        base_items = missing_items_from_run_paths(
            run_paths,
            tickers=filters["tickers"],
            contract_symbols=filters["contract_symbols"],
            quote_dates=filters["quote_dates"],
        )
    except Exception:
        return []
    attempts_by_key = _initial_attempts(base_items, source_label=_legacy_source_label(payload))
    request_dates_by_key = _legacy_request_dates(base_items, payload)
    counts = _csv_counts(_resolve_path(payload.get("csv_path")))
    rows_by_contract = {
        str(contract).upper(): int(count or 0)
        for contract, count in (payload.get("rows_by_contract") or {}).items()
    }
    rows_by_date = {str(date)[:10]: int(count or 0) for date, count in (payload.get("rows_by_date") or {}).items()}
    errors = [str(error) for error in payload.get("errors") or []]

    for key, attempt in attempts_by_key.items():
        missing_quote_date, contract_symbol = key
        contract = str(contract_symbol or "").upper()
        attempt["request_dates_attempted"] = request_dates_by_key.get(key, [])
        attempt["errors"] = [error for error in errors if contract in error]
        if counts:
            for (row_contract, row_date), count in counts.items():
                if row_contract != contract:
                    continue
                attempt["total_row_count"] += int(count)
                attempt["available_quote_dates"] = sorted(
                    set([*attempt.get("available_quote_dates", []), row_date])
                )
                if row_date == str(missing_quote_date)[:10]:
                    attempt["exact_date_row_count"] += int(count)
                elif row_date > str(missing_quote_date)[:10]:
                    attempt["lookahead_row_count"] += int(count)
        elif rows_by_contract.get(contract):
            total_count = rows_by_contract.get(contract, 0)
            aggregate_counts_are_contract_scoped = len(attempts_by_key) == 1 and set(rows_by_contract) == {contract}
            if aggregate_counts_are_contract_scoped:
                exact_count = min(rows_by_date.get(str(missing_quote_date)[:10], 0), total_count)
                attempt["exact_date_row_count"] = exact_count
                attempt["lookahead_row_count"] = max(0, total_count - exact_count)
                attempt["available_quote_dates"] = sorted(
                    date for date, count in rows_by_date.items() if int(count or 0) > 0
                )
            else:
                attempt["lookahead_row_count"] = total_count
                attempt["legacy_aggregate_date_counts_unsafe"] = True
            attempt["total_row_count"] = total_count

    finalized = _finalized_attempts(
        attempts_by_key,
        plan_only=bool(payload.get("plan_only")),
        import_performed=bool(payload.get("import_result")),
    )
    rows: list[dict[str, Any]] = []
    for attempt in finalized:
        for key in attempt.get("repair_attempt_keys") or [attempt.get("repair_attempt_key")]:
            if not key:
                continue
            parts = _key_parts(str(key))
            rows.append(
                {
                    "repair_attempt_key": str(key),
                    **parts,
                    "summary_path": _rel(summary_path),
                    "summary_generated_at_utc": str(payload.get("generated_at_utc") or ""),
                    "dry_run": bool(payload.get("dry_run")),
                    "plan_only": bool(payload.get("plan_only")),
                    "write_artifacts": bool(payload.get("write_artifacts", True)),
                    "legacy_inferred": True,
                    "source_label": attempt.get("source_label") or _legacy_source_label(payload),
                    "outcome": attempt.get("outcome"),
                    "proof_repair_status": attempt.get("proof_repair_status"),
                    "exact_missing_date_status": attempt.get("exact_missing_date_status"),
                    "exact_date_row_count": int(attempt.get("exact_date_row_count") or 0),
                    "lookahead_row_count": int(attempt.get("lookahead_row_count") or 0),
                    "total_row_count": int(attempt.get("total_row_count") or 0),
                    "request_dates_attempted": list(attempt.get("request_dates_attempted") or []),
                    "available_quote_dates": list(attempt.get("available_quote_dates") or []),
                    "first_available_after_missing_date": attempt.get("first_available_after_missing_date"),
                    "current_source_exhausted_for_exact_date": bool(
                        attempt.get("current_source_exhausted_for_exact_date")
                    ),
                    "legacy_aggregate_date_counts_unsafe": bool(
                        attempt.get("legacy_aggregate_date_counts_unsafe")
                    ),
                    "errors": list(attempt.get("errors") or []),
                }
            )
    return rows


def _latest_attempts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("repair_attempt_key") or "")
        current = latest.get(key)
        if current is None or (
            str(row.get("summary_generated_at_utc") or ""),
            str(row.get("summary_path") or ""),
        ) >= (
            str(current.get("summary_generated_at_utc") or ""),
            str(current.get("summary_path") or ""),
        ):
            latest[key] = row
    return [latest[key] for key in sorted(latest)]


def _summary(
    rows: list[dict[str, Any]],
    latest_rows: list[dict[str, Any]],
    *,
    input_summary_count: int,
) -> dict[str, Any]:
    outcome_counts = Counter(str(row.get("outcome") or "unknown") for row in latest_rows)
    proof_counts = Counter(str(row.get("proof_repair_status") or "unknown") for row in latest_rows)
    return {
        "attempt_record_count": len(rows),
        "latest_attempt_count": len(latest_rows),
        "input_summary_count": input_summary_count,
        "latest_outcome_counts": dict(sorted(outcome_counts.items())),
        "latest_proof_repair_status_counts": dict(sorted(proof_counts.items())),
        "latest_current_source_exhausted_count": sum(
            1 for row in latest_rows if row.get("current_source_exhausted_for_exact_date")
        ),
        "latest_exact_date_row_count": sum(int(row.get("exact_date_row_count") or 0) for row in latest_rows),
        "latest_lookahead_row_count": sum(int(row.get("lookahead_row_count") or 0) for row in latest_rows),
    }


def build_readback(summary_paths: list[Path] | None = None) -> dict[str, Any]:
    paths = [path.resolve() for path in summary_paths] if summary_paths else _default_summary_paths()
    attempts: list[dict[str, Any]] = []
    inputs: list[dict[str, Any]] = []
    for path in paths:
        entry = {"path": _rel(path), "exists": path.exists(), "status": "missing"}
        if not path.exists():
            inputs.append(entry)
            continue
        try:
            payload = _load_json(path)
        except Exception as exc:
            entry["status"] = f"unreadable:{exc}"
            inputs.append(entry)
            continue
        entry["status"] = "ok"
        entry["generated_at_utc"] = payload.get("generated_at_utc")
        entry["repair_attempt_count"] = len(payload.get("repair_attempts") or [])
        inputs.append(entry)
        flattened = _flatten_attempts(path, payload)
        if flattened:
            attempts.extend(flattened)
        else:
            legacy_attempts = _flatten_legacy_attempts(path, payload)
            if legacy_attempts:
                entry["repair_attempt_count"] = len(legacy_attempts)
                entry["legacy_inferred_attempt_count"] = len(legacy_attempts)
                attempts.extend(legacy_attempts)

    latest_rows = _latest_attempts(attempts)
    return {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "scope": "regular_options_repair_attempt_readback",
        "status": "repair_attempt_readback",
        "proof_policy": {
            "exact_date_rows": "Exact missing-date rows are repair candidates only until the source replay graduates.",
            "lookahead_only_rows": "Lookahead-only rows are diagnostics and do not repair the missing exact proof date.",
            "no_match": "No-match attempts exhaust the current source for that exact date until a new source or rerun changes evidence.",
        },
        "inputs": inputs,
        "summary": _summary(attempts, latest_rows, input_summary_count=len(inputs)),
        "attempts": attempts,
        "latest_attempts": latest_rows,
    }


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    latest = report.get("latest_attempts") or []
    lines = [
        "# Regular Options Repair Attempts",
        "",
        "This report is generated from `scripts/build_regular_options_repair_attempt_readback.py`. It is a repair-memory/readback layer for regular options proof work, not a scanner or broker-action surface.",
        "",
        "## Summary",
        "",
        f"- Latest attempts: `{summary.get('latest_attempt_count')}`.",
        f"- Input summaries scanned: `{summary.get('input_summary_count')}`.",
        f"- Latest outcomes: `{json.dumps(summary.get('latest_outcome_counts') or {}, sort_keys=True)}`.",
        f"- Latest proof repair statuses: `{json.dumps(summary.get('latest_proof_repair_status_counts') or {}, sort_keys=True)}`.",
        f"- Current-source exhausted exact dates: `{summary.get('latest_current_source_exhausted_count')}`.",
        f"- Exact-date rows found: `{summary.get('latest_exact_date_row_count')}`.",
        f"- Lookahead-only rows found: `{summary.get('latest_lookahead_row_count')}`.",
        "",
        "## Outcome Matrix",
        "",
        "| Outcome | Meaning | Proof posture |",
        "|---|---|---|",
        "| `imported_pending_replay` | Exact missing-date rows were imported. | Rerun the source replay before graduation. |",
        "| `exact_date_rows_found` | Exact missing-date rows were found in dry-run. | Candidate only until imported and replayed. |",
        "| `lookahead_only_rows_found` | Later dates had rows, missing date did not. | Diagnostic only; not proof repair. |",
        "| `exact_date_no_match` | Current source returned no exact rows. | Exhausted for this source/date until new evidence exists. |",
        "| `planned_not_requested` | Plan-only target; no provider request. | No proof change. |",
        "",
        "## Latest Attempts",
        "",
        "| Outcome | Proof status | Ticker | Contract | Missing date | Exact rows | Lookahead rows | First later date | Source |",
        "|---|---|---|---|---|---:|---:|---|---|",
    ]
    for row in latest[:80]:
        lines.append(
            "| "
            + " | ".join(
                [
                    _fmt(row.get("outcome")),
                    _fmt(row.get("proof_repair_status")),
                    _fmt(row.get("ticker")),
                    _fmt(row.get("contract_symbol")),
                    _fmt(row.get("missing_quote_date")),
                    _fmt(row.get("exact_date_row_count")),
                    _fmt(row.get("lookahead_row_count")),
                    _fmt(row.get("first_available_after_missing_date")),
                    _fmt(row.get("source_artifact")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Inputs",
            "",
            "| Status | Generated | Attempts | Path |",
            "|---|---|---:|---|",
        ]
    )
    inputs = report.get("inputs") or []
    for entry in inputs[-20:]:
        lines.append(
            "| "
            + " | ".join(
                [
                    _fmt(entry.get("status")),
                    _fmt(entry.get("generated_at_utc")),
                    _fmt(entry.get("repair_attempt_count")),
                    _fmt(entry.get("path")),
                ]
            )
            + " |"
        )
    omitted = max(0, len(inputs) - 20)
    if omitted:
        lines.extend(["", f"Older input summaries omitted from this Markdown table: `{omitted}`."])
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, doc_path: Path = DEFAULT_DOC) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"regular_options_repair_attempts_{stamp}.json"
    latest_json = output_dir / "latest.json"
    markdown_path = output_dir / f"regular_options_repair_attempts_{stamp}.md"
    latest_markdown = output_dir / "latest.md"
    artifacts = {
        "json": str(json_path),
        "latest_json": str(latest_json),
        "markdown": str(markdown_path),
        "latest_markdown": str(latest_markdown),
        "docs_report": str(doc_path),
    }
    report_with_artifacts = dict(report)
    report_with_artifacts["artifacts"] = artifacts
    payload = json.dumps(report_with_artifacts, indent=2, sort_keys=True)
    markdown = render_markdown(report_with_artifacts)
    json_path.write_text(payload + "\n", encoding="utf8")
    latest_json.write_text(payload + "\n", encoding="utf8")
    markdown_path.write_text(markdown, encoding="utf8")
    latest_markdown.write_text(markdown, encoding="utf8")
    doc_path.write_text(markdown, encoding="utf8")
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build regular options exact-repair attempt readback.")
    parser.add_argument("summary_paths", nargs="*", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--doc-path", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_readback(args.summary_paths)
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, doc_path=args.doc_path)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif not args.no_write:
        print(f"wrote {report['artifacts']['latest_json']}")
        print(f"wrote {report['artifacts']['docs_report']}")
    else:
        print(json.dumps({"status": report["status"], "summary": report["summary"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
