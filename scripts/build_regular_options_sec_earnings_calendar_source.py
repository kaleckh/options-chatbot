from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_regular_options_point_in_time_earnings_calendar as earnings_calendar  # noqa: E402
from scripts.import_regular_options_earnings_calendar import CSV_FIELDS  # noqa: E402


REPORT_ID = "regular_options_sec_earnings_calendar_source"
DEFAULT_OUTPUT_CSV = ROOT / "data" / "import-staging" / "earnings" / "point_in_time_equity_earnings_calendar.csv"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-sec-earnings-calendar-source"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-sec-earnings-calendar-source.md"
DEFAULT_USER_AGENT = "options-chatbot research contact kaleckh@gmail.com"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _parse_symbols(value: str | Sequence[str]) -> tuple[str, ...]:
    raw = value.split(",") if isinstance(value, str) else list(value)
    return tuple(str(item).strip().upper() for item in raw if str(item).strip())


def _request_json(url: str, *, user_agent: str, timeout: int = 30) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept-Encoding": "identity",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read().decode("utf8")
    data = json.loads(payload)
    return data if isinstance(data, dict) else {}


def _ticker_ciks(*, user_agent: str) -> dict[str, str]:
    data = _request_json(SEC_TICKERS_URL, user_agent=user_agent)
    mapping: dict[str, str] = {}
    for item in data.values():
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker") or "").strip().upper()
        cik = str(item.get("cik_str") or "").strip()
        if ticker and cik:
            mapping[ticker] = cik.zfill(10)
    return mapping


def _recent_filings(submissions: dict[str, Any]) -> list[dict[str, Any]]:
    recent = submissions.get("filings", {}).get("recent", {})
    if not isinstance(recent, dict):
        return []
    keys = [key for key, value in recent.items() if isinstance(value, list)]
    row_count = max((len(recent[key]) for key in keys), default=0)
    rows: list[dict[str, Any]] = []
    for index in range(row_count):
        row: dict[str, Any] = {}
        for key in keys:
            values = recent.get(key) or []
            row[key] = values[index] if index < len(values) else None
        rows.append(row)
    return rows


def _acceptance_to_utc(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=UTC)
        except ValueError:
            return None
    return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")


def _filing_url(cik10: str, accession: str, primary_document: str | None) -> str:
    cik_plain = str(int(cik10))
    accession_no_dashes = accession.replace("-", "")
    if primary_document:
        return f"https://www.sec.gov/Archives/edgar/data/{cik_plain}/{accession_no_dashes}/{primary_document}"
    return f"https://www.sec.gov/Archives/edgar/data/{cik_plain}/{accession_no_dashes}/"


def _source_rows_for_symbol(
    *,
    symbol: str,
    cik10: str,
    user_agent: str,
    coverage_start: str,
    coverage_end: str,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    submissions = _request_json(SEC_SUBMISSIONS_URL.format(cik10=cik10), user_agent=user_agent)
    rows: list[dict[str, str]] = []
    inspected_8k = 0
    matched_202 = 0
    out_of_window_202 = 0
    for filing in _recent_filings(submissions):
        form = str(filing.get("form") or "").upper()
        if form not in {"8-K", "8-K/A"}:
            continue
        inspected_8k += 1
        items = str(filing.get("items") or "")
        if "2.02" not in items:
            continue
        filing_date = str(filing.get("filingDate") or "")[:10]
        if filing_date < coverage_start or filing_date > coverage_end:
            out_of_window_202 += 1
            continue
        acceptance = _acceptance_to_utc(filing.get("acceptanceDateTime"))
        accession = str(filing.get("accessionNumber") or "")
        if not (filing_date and acceptance and accession):
            continue
        matched_202 += 1
        rows.append(
            {
                "symbol": symbol,
                "earnings_date_et": filing_date,
                "earnings_time": "unknown",
                "source_name": "sec_edgar_8k_item_2_02",
                "source_url_or_file_name": _filing_url(cik10, accession, str(filing.get("primaryDocument") or "")),
                "source_published_at_utc": acceptance,
                "known_at_utc": acceptance,
                "revision_status": f"sec_{form.lower().replace('/', '_')}_item_2_02",
                "source_calendar_coverage_start_date_et": coverage_start,
                "source_calendar_coverage_end_date_et": coverage_end,
            }
        )
    rows.sort(key=lambda row: (row["earnings_date_et"], row["known_at_utc"]))
    diagnostics = {
        "symbol": symbol,
        "cik": cik10,
        "company_name": submissions.get("name"),
        "inspected_8k_count": inspected_8k,
        "matched_item_2_02_count": matched_202,
        "out_of_window_item_2_02_count": out_of_window_202,
        "latest_filing_date": rows[-1]["earnings_date_et"] if rows else None,
        "earliest_filing_date": rows[0]["earnings_date_et"] if rows else None,
    }
    return rows, diagnostics


def build_report(
    *,
    symbols: Sequence[str] = earnings_calendar.DEFAULT_EQUITY_SYMBOLS,
    output_csv: Path = DEFAULT_OUTPUT_CSV,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOCS_REPORT,
    coverage_start: str = earnings_calendar.DEFAULT_WINDOW_START,
    coverage_end: str = "2026-07-15",
    user_agent: str = DEFAULT_USER_AGENT,
    sleep_seconds: float = 0.12,
    write_outputs: bool = True,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    normalized_symbols = tuple(sorted(_parse_symbols(symbols)))
    blockers: list[str] = []
    source_rows: list[dict[str, str]] = []
    diagnostics: list[dict[str, Any]] = []
    try:
        cik_by_ticker = _ticker_ciks(user_agent=user_agent)
        for symbol in normalized_symbols:
            cik = cik_by_ticker.get(symbol)
            if not cik:
                blockers.append(f"missing_sec_cik_for_{symbol}")
                continue
            rows, diag = _source_rows_for_symbol(
                symbol=symbol,
                cik10=cik,
                user_agent=user_agent,
                coverage_start=coverage_start,
                coverage_end=coverage_end,
            )
            if not rows:
                blockers.append(f"missing_sec_item_2_02_rows_for_{symbol}")
            source_rows.extend(rows)
            diagnostics.append(diag)
            time.sleep(max(float(sleep_seconds), 0.0))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        blockers.append(f"sec_source_fetch_failed:{type(exc).__name__}")
    if not source_rows:
        blockers.append("no_sec_earnings_rows_materialized")

    status = "sec_earnings_calendar_source_ready" if not blockers else "blocked_sec_earnings_calendar_source"
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": status,
        "source_kind": "sec_edgar_8k_item_2_02_observed_earnings_release_dates",
        "source_limitation": (
            "SEC Item 2.02 filings are official point-in-time observed earnings-release filings. "
            "They are not vendor scheduled future earnings-calendar snapshots."
        ),
        "symbols": list(normalized_symbols),
        "coverage_start_date_et": coverage_start,
        "coverage_end_date_et": coverage_end,
        "source_row_count": len(source_rows),
        "source_rows_by_symbol": {symbol: sum(1 for row in source_rows if row["symbol"] == symbol) for symbol in normalized_symbols},
        "diagnostics": diagnostics,
        "output_csv": _rel(output_csv),
        "csv_fields": list(CSV_FIELDS),
        "blockers": blockers,
        "read_only": True,
        "historical_replay_performed": False,
        "quotes_imported": False,
        "evidence_stores_mutated": False,
        "broker_order_allowed": False,
        "promotion_ready": False,
    }
    if write_outputs and status == "sec_earnings_calendar_source_ready":
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        with output_csv.open("w", encoding="utf8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(source_rows)
    if write_outputs:
        write_report(report, output_dir=output_dir, docs_report=docs_report)
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options SEC Earnings Calendar Source",
        "",
        f"- Status: `{report['status']}`.",
        f"- Source rows: `{report['source_row_count']}`.",
        f"- Output CSV: `{report['output_csv']}`.",
        "",
        report["source_limitation"],
        "",
        "## Rows By Symbol",
        "",
        "| Symbol | Rows |",
        "|---|---:|",
    ]
    for symbol, count in report["source_rows_by_symbol"].items():
        lines.append(f"| `{symbol}` | `{count}` |")
    if report["blockers"]:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{blocker}`" for blocker in report["blockers"])
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict[str, Any], *, output_dir: Path, docs_report: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    artifacts = {
        "json": _rel(output_dir / f"{REPORT_ID}_{stamp}.json"),
        "markdown": _rel(output_dir / f"{REPORT_ID}_{stamp}.md"),
        "latest_json": _rel(output_dir / "latest.json"),
        "latest_markdown": _rel(output_dir / "latest.md"),
        "docs_report": _rel(docs_report),
    }
    payload = dict(report)
    payload["artifacts"] = artifacts
    markdown = render_markdown(payload)
    for path in (output_dir / f"{REPORT_ID}_{stamp}.json", output_dir / "latest.json"):
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")
    for path in (output_dir / f"{REPORT_ID}_{stamp}.md", output_dir / "latest.md", docs_report):
        path.write_text(markdown, encoding="utf8")
    report["artifacts"] = artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a staged SEC EDGAR Item 2.02 earnings calendar CSV.")
    parser.add_argument("--symbols", default=",".join(sorted(earnings_calendar.DEFAULT_EQUITY_SYMBOLS)))
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--coverage-start", default=earnings_calendar.DEFAULT_WINDOW_START)
    parser.add_argument("--coverage-end", default="2026-07-15")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--sleep-seconds", type=float, default=0.12)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    report = build_report(
        symbols=_parse_symbols(args.symbols),
        output_csv=args.output_csv,
        output_dir=args.output_dir,
        docs_report=args.docs_report,
        coverage_start=args.coverage_start,
        coverage_end=args.coverage_end,
        user_agent=args.user_agent,
        sleep_seconds=args.sleep_seconds,
        write_outputs=not args.no_write,
    )
    print(json.dumps(report, indent=2, sort_keys=True) if args.json_output else render_markdown(report))
    return 0 if report["status"] == "sec_earnings_calendar_source_ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
