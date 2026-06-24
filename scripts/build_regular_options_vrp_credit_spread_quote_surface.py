from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_vrp_credit_spread_quote_surface"
SURFACE_ID = "vrp_put_credit_spread_trusted_quote_surface_v1"
DEFAULT_QUOTES_DB = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-vrp-credit-spread-quote-surface"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-vrp-credit-spread-quote-surface.md"

DEFAULT_UNIVERSE = ("SPY", "QQQ", "IWM", "DIA")
DEFAULT_SOURCE_LABELS = ("thetadata_opra_nbbo_1m",)
DEFAULT_START_DATE = "2024-06-01"
DEFAULT_END_DATE = "2026-05-31"
DEFAULT_LATEST_FOUR_MONTHS = ("2026-02", "2026-03", "2026-04", "2026-05")
DEFAULT_DTE_MIN = 21
DEFAULT_DTE_MAX = 45
REQUIRED_MONTHS = 24
REQUIRED_LATEST_FOUR_MONTHS = 4

READ_ONLY_FLAGS = {
    "read_only": True,
    "no_write": True,
    "accepted_profitability": False,
    "historical_replay_performed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "promotion_ready": False,
}

FORBIDDEN_ACTIONS = (
    "do_not_create_trades",
    "do_not_run_replay",
    "do_not_import_quotes",
    "do_not_mutate_options_history_db",
    "do_not_mutate_evidence_stores",
    "do_not_append_forward_cohort_rows",
    "do_not_consume_protected_holdout",
    "do_not_enable_live_validation",
    "do_not_enable_auto_track",
    "do_not_submit_broker_orders",
    "do_not_change_scanner_policy",
    "do_not_change_strategy_logic",
    "do_not_change_stops",
    "do_not_change_sizing",
    "do_not_lower_proof_bars",
    "do_not_promote_any_lane",
    "do_not_claim_accepted_profitability",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _sqlite_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("select 1 from sqlite_master where type='table' and name=?", (table,)).fetchone()
    return row is not None


def _month_range(start_date: str, end_date: str) -> list[str]:
    start = date.fromisoformat(start_date[:10])
    end = date.fromisoformat(end_date[:10])
    months: list[str] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year += 1
            month = 1
    return months


def _surface_rows(
    conn: sqlite3.Connection,
    *,
    universe: Sequence[str],
    source_labels: Sequence[str],
    start_date: str,
    end_date: str,
    latest_four_months: Sequence[str],
    dte_min: int,
    dte_max: int,
) -> dict[str, dict[str, Any]]:
    placeholders_symbols = ",".join("?" for _ in universe)
    placeholders_sources = ",".join("?" for _ in source_labels)
    placeholders_latest = ",".join("?" for _ in latest_four_months)
    params: list[Any] = [
        *source_labels,
        *universe,
        start_date,
        end_date,
        dte_min,
        dte_max,
        *latest_four_months,
    ]
    query = f"""
        with trusted_batches as (
            select id
            from import_batches
            where source_label in ({placeholders_sources})
              and data_trust = 'trusted'
        ),
        spread_groups as (
            select
                q.underlying,
                q.quote_date_et,
                q.quote_minute_et,
                q.expiry,
                count(distinct q.strike) as strike_count
            from option_quote_snapshots q
            where q.source_batch_id in trusted_batches
              and q.underlying in ({placeholders_symbols})
              and q.quote_date_et between ? and ?
              and q.option_type = 'put'
              and q.bid is not null
              and q.ask is not null
              and q.bid >= 0
              and q.ask >= q.bid
              and (julianday(q.expiry) - julianday(q.quote_date_et)) between ? and ?
            group by q.underlying, q.quote_date_et, q.quote_minute_et, q.expiry
            having strike_count >= 2
        ),
        covered_dates as (
            select distinct underlying, quote_date_et
            from spread_groups
        )
        select
            sg.underlying,
            count(distinct sg.quote_date_et) as covered_dates,
            count(distinct substr(sg.quote_date_et, 1, 7)) as covered_months,
            count(distinct case when substr(sg.quote_date_et, 1, 7) in ({placeholders_latest}) then substr(sg.quote_date_et, 1, 7) end) as latest_four_months_covered,
            count(*) as spread_groups,
            min(sg.quote_date_et) as first_covered_date,
            max(sg.quote_date_et) as last_covered_date
        from spread_groups sg
        group by sg.underlying
    """
    return {str(row["underlying"]): dict(row) for row in conn.execute(query, params)}


def _symbol_status(
    *,
    symbol: str,
    row: dict[str, Any] | None,
    requested_months: list[str],
    latest_four_months: Sequence[str],
    required_months: int,
    required_latest_four_months: int,
) -> dict[str, Any]:
    row = row or {}
    covered_months = int(row.get("covered_months") or 0)
    latest_covered = int(row.get("latest_four_months_covered") or 0)
    blockers: list[str] = []
    if not row:
        blockers.append("missing_symbol_quote_surface")
    if covered_months < required_months:
        blockers.append("insufficient_month_coverage")
    if latest_covered < required_latest_four_months:
        blockers.append("insufficient_latest_four_month_coverage")
    return {
        "symbol": symbol,
        "status": "ready" if not blockers else "blocked",
        "blockers": blockers,
        "covered_dates": int(row.get("covered_dates") or 0),
        "covered_months": covered_months,
        "required_months": required_months,
        "latest_four_months_covered": latest_covered,
        "required_latest_four_months": required_latest_four_months,
        "requested_months": requested_months,
        "latest_four_months": list(latest_four_months),
        "spread_groups": int(row.get("spread_groups") or 0),
        "first_covered_date": row.get("first_covered_date"),
        "last_covered_date": row.get("last_covered_date"),
    }


def build_report(
    *,
    quotes_db_path: Path = DEFAULT_QUOTES_DB,
    universe: Sequence[str] = DEFAULT_UNIVERSE,
    source_labels: Sequence[str] = DEFAULT_SOURCE_LABELS,
    start_date: str = DEFAULT_START_DATE,
    end_date: str = DEFAULT_END_DATE,
    latest_four_months: Sequence[str] = DEFAULT_LATEST_FOUR_MONTHS,
    dte_min: int = DEFAULT_DTE_MIN,
    dte_max: int = DEFAULT_DTE_MAX,
    required_months: int = REQUIRED_MONTHS,
    required_latest_four_months: int = REQUIRED_LATEST_FOUR_MONTHS,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    db_meta = {"path": _rel(quotes_db_path), "exists": quotes_db_path.exists(), "status": "missing"}
    requested_months = _month_range(start_date, end_date)
    raw_rows: dict[str, dict[str, Any]] = {}
    if quotes_db_path.exists():
        try:
            with _sqlite_readonly(quotes_db_path) as conn:
                if not _table_exists(conn, "option_quote_snapshots") or not _table_exists(conn, "import_batches"):
                    db_meta["status"] = "missing_required_tables"
                else:
                    db_meta["status"] = "loaded_read_only"
                    raw_rows = _surface_rows(
                        conn,
                        universe=universe,
                        source_labels=source_labels,
                        start_date=start_date,
                        end_date=end_date,
                        latest_four_months=latest_four_months,
                        dte_min=dte_min,
                        dte_max=dte_max,
                    )
        except sqlite3.Error as exc:
            db_meta["status"] = "unreadable"
            db_meta["error"] = str(exc)

    symbol_rows = [
        _symbol_status(
            symbol=symbol,
            row=raw_rows.get(symbol),
            requested_months=requested_months,
            latest_four_months=latest_four_months,
            required_months=required_months,
            required_latest_four_months=required_latest_four_months,
        )
        for symbol in universe
    ]
    symbols_ready = [row["symbol"] for row in symbol_rows if row["status"] == "ready"]
    blockers = [] if len(symbols_ready) == len(tuple(universe)) else ["missing_index_credit_spread_quote_surface"]
    report = {
        "report_id": REPORT_ID,
        "surface_id": SURFACE_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": "credit_spread_quote_surface_ready" if not blockers else "blocked_vrp_credit_spread_quote_surface",
        **READ_ONLY_FLAGS,
        "scope": "read_only_vrp_credit_spread_quote_surface_proof",
        "credit_spread_quote_surface_ready": not blockers,
        "symbols_ready": symbols_ready,
        "research_universe": list(universe),
        "source_labels": list(source_labels),
        "geometry_filter": {
            "option_type": "put",
            "dte_min": dte_min,
            "dte_max": dte_max,
            "same_minute_same_expiry_min_distinct_strikes": 2,
            "trusted_bid_ask_required": True,
        },
        "window": {
            "start_date": start_date,
            "end_date": end_date,
            "requested_months": requested_months,
            "latest_four_months": list(latest_four_months),
        },
        "symbol_rows": symbol_rows,
        "blockers": blockers,
        "source_artifacts": {"options_history_db": db_meta},
        "proof_boundary": "quote-surface coverage is input readiness only; it is not replay, P&L, forward proof, or accepted profitability",
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }
    _validate_report(report)
    return report


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    if report.get("accepted_profitability") is not False or report.get("promotion_ready") is not False:
        raise ValueError("quote-surface proof cannot mark profitability or promotion")


def _fmt_bool(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options VRP Credit Spread Quote Surface",
        "",
        "This generated report is read-only. It checks whether existing trusted local OPRA/NBBO rows contain same-minute, same-expiry put quote surfaces for the preregistered VRP credit-spread geometry. It does not run replay, compute P&L, import quotes, mutate evidence, consume holdout, or promote any lane.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Surface ready: `{_fmt_bool(report['credit_spread_quote_surface_ready'])}`.",
        f"- Accepted profitability: `{_fmt_bool(report['accepted_profitability'])}`.",
        f"- Symbols ready: `{', '.join(_as_list(report.get('symbols_ready'))) or '-'}`.",
        "",
        "## Blockers",
        "",
    ]
    if report.get("blockers"):
        lines.extend(f"- `{item}`" for item in _as_list(report.get("blockers")))
    else:
        lines.append("- None.")
    lines.extend(["", "## Symbol Coverage", "", "| Symbol | Status | Covered Months | Latest-Four Months | Covered Dates | Spread Groups | Blockers |", "| --- | --- | ---: | ---: | ---: | ---: | --- |"])
    for row in _as_list(report.get("symbol_rows")):
        blockers = ", ".join(_as_list(row.get("blockers"))) or "-"
        lines.append(
            f"| `{row.get('symbol')}` | `{row.get('status')}` | {row.get('covered_months')} / {row.get('required_months')} | "
            f"{row.get('latest_four_months_covered')} / {row.get('required_latest_four_months')} | {row.get('covered_dates')} | {row.get('spread_groups')} | {blockers} |"
        )
    lines.extend(["", "## Forbidden Actions", ""])
    lines.extend(f"- `{item}`" for item in _as_list(report.get("forbidden_actions")))
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"{stamp}.json"
    md_path = output_dir / f"{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    artifacts = {
        "json": _rel(json_path),
        "markdown": _rel(md_path),
        "latest_json": _rel(latest_json),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
    }
    report_with_artifacts = dict(report)
    report_with_artifacts["artifacts"] = artifacts
    payload = json.dumps(report_with_artifacts, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(report_with_artifacts)
    json_path.write_text(payload, encoding="utf8")
    latest_json.write_text(payload, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a read-only VRP credit-spread quote-surface proof.")
    parser.add_argument("--quotes-db", type=Path, default=DEFAULT_QUOTES_DB)
    parser.add_argument("--universe", default=",".join(DEFAULT_UNIVERSE))
    parser.add_argument("--source-labels", default=",".join(DEFAULT_SOURCE_LABELS))
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=DEFAULT_END_DATE)
    parser.add_argument("--latest-four-months", default=",".join(DEFAULT_LATEST_FOUR_MONTHS))
    parser.add_argument("--dte-min", type=int, default=DEFAULT_DTE_MIN)
    parser.add_argument("--dte-max", type=int, default=DEFAULT_DTE_MAX)
    parser.add_argument("--required-months", type=int, default=REQUIRED_MONTHS)
    parser.add_argument("--required-latest-four-months", type=int, default=REQUIRED_LATEST_FOUR_MONTHS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(
        quotes_db_path=args.quotes_db,
        universe=tuple(item.strip().upper() for item in args.universe.split(",") if item.strip()),
        source_labels=tuple(item.strip() for item in args.source_labels.split(",") if item.strip()),
        start_date=args.start_date,
        end_date=args.end_date,
        latest_four_months=tuple(item.strip() for item in args.latest_four_months.split(",") if item.strip()),
        dte_min=args.dte_min,
        dte_max=args.dte_max,
        required_months=args.required_months,
        required_latest_four_months=args.required_latest_four_months,
    )
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
