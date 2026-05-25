from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_commodity_universe import ai_commodity_scan_tickers
from historical_options_store import DAILY_SNAPSHOT_KIND, TRUSTED_DATA_TRUST
from lane_universe_manifest import lane_universe_symbols


DEFAULT_DB_PATH = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "lane-data-shortfall"
ALPACA_OPRA_DAILY_SOURCE_LABEL = "alpaca_opra_daily_snapshot"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalize_symbols(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(str(value).strip().upper() for value in values if str(value).strip()))


def _lane_symbols(lane_id: str) -> list[str]:
    if lane_id == "ai_commodity_infra_observation":
        return _normalize_symbols(ai_commodity_scan_tickers())
    return _normalize_symbols(lane_universe_symbols(lane_id))


def lane_definitions() -> list[dict[str, Any]]:
    regular_symbols = _lane_symbols("bullish_pullback_observation")
    return [
        {
            "id": "bullish_pullback_observation",
            "label": "Regular Bullish Pullback Primary",
            "lane_family": "regular_options",
            "direction": "call",
            "symbols": regular_symbols,
        },
        {
            "id": "regular_bearish_put_primary",
            "label": "Regular Bearish Put Primary",
            "lane_family": "regular_options",
            "direction": "put",
            "symbols": regular_symbols,
        },
        {
            "id": "ai_commodity_infra_observation",
            "label": "AI Commodity Infra",
            "lane_family": "commodity_options",
            "direction": "call_or_put",
            "symbols": _lane_symbols("ai_commodity_infra_observation"),
        },
    ]


def _sqlite_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _scope_clauses(
    *,
    snapshot_kind: str,
    data_scope: str,
    source_labels: Sequence[str] = (),
    underlyings: Sequence[str] = (),
    quote_date: str | None = None,
) -> tuple[str, list[Any]]:
    clauses = ["q.snapshot_kind = ?"]
    params: list[Any] = [snapshot_kind]
    normalized_scope = str(data_scope or "all").strip().lower()
    if normalized_scope == "trusted":
        clauses.append("b.data_trust = ?")
        params.append(TRUSTED_DATA_TRUST)
    elif normalized_scope == "research_only":
        clauses.append("b.data_trust != ?")
        params.append(TRUSTED_DATA_TRUST)
    elif normalized_scope != "all":
        raise ValueError(f"Unsupported data scope: {data_scope}")

    labels = [str(label).strip() for label in source_labels if str(label).strip()]
    if labels:
        placeholders = ", ".join("?" for _ in labels)
        clauses.append(f"b.source_label IN ({placeholders})")
        params.extend(labels)

    symbols = _normalize_symbols(underlyings)
    if symbols:
        placeholders = ", ".join("?" for _ in symbols)
        clauses.append(f"q.underlying IN ({placeholders})")
        params.extend(symbols)

    if quote_date:
        clauses.append("q.quote_date_et = ?")
        params.append(str(quote_date)[:10])

    return " AND ".join(clauses), params


def _pct(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator) * 100.0, 2) if denominator else 0.0


def _query_scope_coverage(
    conn: sqlite3.Connection,
    *,
    symbols: Sequence[str],
    data_scope: str,
    source_labels: Sequence[str] = (),
    snapshot_kind: str = DAILY_SNAPSHOT_KIND,
    min_shared_dates: int,
) -> dict[str, Any]:
    normalized_symbols = _normalize_symbols(symbols)
    if not normalized_symbols:
        return {
            "status": "missing_symbols",
            "symbol_count": 0,
            "available_symbol_count": 0,
            "missing_symbols": [],
            "shared_quote_dates": {"count": 0, "first": None, "last": None, "sample": []},
            "per_symbol": {},
            "sources": [],
        }

    where_sql, params = _scope_clauses(
        snapshot_kind=snapshot_kind,
        data_scope=data_scope,
        source_labels=source_labels,
        underlyings=normalized_symbols,
    )
    rows = conn.execute(
        f"""
        SELECT
            q.underlying,
            COUNT(*) AS quote_rows,
            COUNT(DISTINCT q.contract_symbol) AS contract_count,
            COUNT(DISTINCT q.quote_date_et) AS quote_date_count,
            MIN(q.quote_date_et) AS first_quote_date,
            MAX(q.quote_date_et) AS last_quote_date,
            SUM(
                CASE
                    WHEN q.bid IS NOT NULL
                     AND q.ask IS NOT NULL
                     AND q.bid > 0
                     AND q.ask > 0
                     AND q.ask >= q.bid
                    THEN 1 ELSE 0
                END
            ) AS executable_quote_rows
        FROM option_quote_snapshots q
        JOIN import_batches b ON b.id = q.source_batch_id
        WHERE {where_sql}
        GROUP BY q.underlying
        ORDER BY q.underlying
        """,
        tuple(params),
    ).fetchall()

    per_symbol: dict[str, dict[str, Any]] = {}
    for row in rows:
        quote_rows = int(row["quote_rows"] or 0)
        executable_rows = int(row["executable_quote_rows"] or 0)
        per_symbol[str(row["underlying"]).upper()] = {
            "quote_rows": quote_rows,
            "contract_count": int(row["contract_count"] or 0),
            "quote_date_count": int(row["quote_date_count"] or 0),
            "first_quote_date": str(row["first_quote_date"] or "") or None,
            "last_quote_date": str(row["last_quote_date"] or "") or None,
            "executable_quote_rows": executable_rows,
            "executable_quote_pct": _pct(executable_rows, quote_rows),
        }

    shared_rows = conn.execute(
        f"""
        SELECT q.quote_date_et
        FROM option_quote_snapshots q
        JOIN import_batches b ON b.id = q.source_batch_id
        WHERE {where_sql}
        GROUP BY q.quote_date_et
        HAVING COUNT(DISTINCT q.underlying) = ?
        ORDER BY q.quote_date_et
        """,
        tuple(params + [len(normalized_symbols)]),
    ).fetchall()
    shared_dates = [str(row["quote_date_et"]) for row in shared_rows]

    source_rows = conn.execute(
        f"""
        SELECT
            b.source_label,
            b.data_trust,
            COUNT(*) AS quote_rows,
            COUNT(DISTINCT q.quote_date_et) AS quote_date_count,
            COUNT(DISTINCT q.underlying) AS underlying_count,
            MIN(q.quote_date_et) AS first_quote_date,
            MAX(q.quote_date_et) AS last_quote_date
        FROM option_quote_snapshots q
        JOIN import_batches b ON b.id = q.source_batch_id
        WHERE {where_sql}
        GROUP BY b.source_label, b.data_trust
        ORDER BY b.data_trust, b.source_label
        """,
        tuple(params),
    ).fetchall()

    latest_row = conn.execute(
        f"""
        SELECT MAX(q.quote_date_et) AS latest_quote_date
        FROM option_quote_snapshots q
        JOIN import_batches b ON b.id = q.source_batch_id
        WHERE {where_sql}
        """,
        tuple(params),
    ).fetchone()
    latest_quote_date = str((latest_row["latest_quote_date"] if latest_row else None) or "") or None
    latest_missing_symbols: list[str] = []
    if latest_quote_date:
        latest_where, latest_params = _scope_clauses(
            snapshot_kind=snapshot_kind,
            data_scope=data_scope,
            source_labels=source_labels,
            underlyings=normalized_symbols,
            quote_date=latest_quote_date,
        )
        latest_symbols = {
            str(row["underlying"]).upper()
            for row in conn.execute(
                f"""
                SELECT DISTINCT q.underlying
                FROM option_quote_snapshots q
                JOIN import_batches b ON b.id = q.source_batch_id
                WHERE {latest_where}
                """,
                tuple(latest_params),
            ).fetchall()
        }
        latest_missing_symbols = [symbol for symbol in normalized_symbols if symbol not in latest_symbols]

    missing_symbols = [symbol for symbol in normalized_symbols if symbol not in per_symbol]
    thin_symbols = [
        symbol
        for symbol in normalized_symbols
        if int(per_symbol.get(symbol, {}).get("quote_date_count") or 0) < int(min_shared_dates)
    ]
    if missing_symbols:
        status = "missing_symbols"
    elif len(shared_dates) < int(min_shared_dates):
        status = "thin_shared_calendar"
    else:
        status = "ready_for_research_replay" if data_scope != "trusted" else "ready_for_proof_replay"

    return {
        "status": status,
        "data_scope": data_scope,
        "source_labels": [str(label) for label in source_labels],
        "snapshot_kind": snapshot_kind,
        "symbol_count": len(normalized_symbols),
        "available_symbol_count": len(per_symbol),
        "missing_symbols": missing_symbols,
        "thin_symbols": thin_symbols,
        "latest_quote_date": latest_quote_date,
        "latest_quote_date_missing_symbols": latest_missing_symbols,
        "shared_quote_dates": {
            "count": len(shared_dates),
            "first": shared_dates[0] if shared_dates else None,
            "last": shared_dates[-1] if shared_dates else None,
            "sample": shared_dates[-5:],
            "required": int(min_shared_dates),
        },
        "per_symbol": per_symbol,
        "sources": [
            {
                "source_label": str(row["source_label"]),
                "data_trust": str(row["data_trust"]),
                "quote_rows": int(row["quote_rows"] or 0),
                "quote_date_count": int(row["quote_date_count"] or 0),
                "underlying_count": int(row["underlying_count"] or 0),
                "first_quote_date": str(row["first_quote_date"] or "") or None,
                "last_quote_date": str(row["last_quote_date"] or "") or None,
            }
            for row in source_rows
        ],
    }


def _lane_next_action(lane: dict[str, Any]) -> str:
    trusted = lane["coverage"]["trusted_alpaca"]
    research = lane["coverage"]["all_research_and_trusted"]
    if trusted["status"] == "ready_for_proof_replay":
        return "Run proof-grade exact replay and promotion checks against Alpaca OPRA."
    if research["status"] == "ready_for_research_replay":
        return "Run research replay now, then keep forward-capturing Alpaca OPRA until proof shared-date bars are met."
    if research["missing_symbols"]:
        return "Backfill research EOD chains for missing symbols before replaying this full lane."
    return "Keep importing/capturing more shared quote dates before treating the lane result as stable."


def build_lane_data_shortfall_report(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    min_trusted_shared_dates: int = 120,
    min_research_shared_dates: int = 15,
) -> dict[str, Any]:
    path = Path(db_path)
    lanes = lane_definitions()
    report_lanes: list[dict[str, Any]] = []
    if not path.exists():
        return {
            "generated_at": _utc_now(),
            "db_path": str(path),
            "status": "missing_database",
            "lanes": [],
            "next_actions": [f"Create or import option quote history into {path}."],
        }

    with _sqlite_readonly(path) as conn:
        coverage_cache: dict[tuple[tuple[str, ...], str, tuple[str, ...], int], dict[str, Any]] = {}

        def _coverage(
            *,
            symbols: Sequence[str],
            data_scope: str,
            source_labels: Sequence[str] = (),
            min_shared_dates: int,
        ) -> dict[str, Any]:
            key = (
                tuple(_normalize_symbols(symbols)),
                str(data_scope),
                tuple(str(label).strip() for label in source_labels if str(label).strip()),
                int(min_shared_dates),
            )
            if key not in coverage_cache:
                coverage_cache[key] = _query_scope_coverage(
                    conn,
                    symbols=symbols,
                    data_scope=data_scope,
                    source_labels=source_labels,
                    min_shared_dates=min_shared_dates,
                )
            return dict(coverage_cache[key])

        for lane in lanes:
            symbols = _normalize_symbols(lane["symbols"])
            lane_report = {
                "id": lane["id"],
                "label": lane["label"],
                "lane_family": lane["lane_family"],
                "direction": lane["direction"],
                "symbols": symbols,
                "symbol_count": len(symbols),
                "coverage": {
                    "trusted_alpaca": _coverage(
                        symbols=symbols,
                        data_scope="trusted",
                        source_labels=[ALPACA_OPRA_DAILY_SOURCE_LABEL],
                        min_shared_dates=min_trusted_shared_dates,
                    ),
                    "all_research_and_trusted": _coverage(
                        symbols=symbols,
                        data_scope="all",
                        min_shared_dates=min_research_shared_dates,
                    ),
                    "research_only": _coverage(
                        symbols=symbols,
                        data_scope="research_only",
                        min_shared_dates=min_research_shared_dates,
                    ),
                },
            }
            lane_report["next_action"] = _lane_next_action(lane_report)
            report_lanes.append(lane_report)

    proof_ready = [
        lane["id"]
        for lane in report_lanes
        if lane["coverage"]["trusted_alpaca"]["status"] == "ready_for_proof_replay"
    ]
    research_ready = [
        lane["id"]
        for lane in report_lanes
        if lane["coverage"]["all_research_and_trusted"]["status"] == "ready_for_research_replay"
    ]
    next_actions = [
        "Use all-research coverage for strategy selection and bearish/bullish lane comparisons.",
        "Use Alpaca OPRA trusted coverage only for forward proof, promotion, and live-stack accountability.",
    ]
    if not proof_ready:
        next_actions.append("Keep daily Alpaca OPRA capture running until each lane reaches the trusted shared-date bar.")
    if research_ready:
        next_actions.append("Run imported daily walk-forward research replay for research-ready lanes.")

    return {
        "generated_at": _utc_now(),
        "db_path": str(path),
        "status": "summarized",
        "minimums": {
            "trusted_shared_dates_for_proof": int(min_trusted_shared_dates),
            "research_shared_dates_for_smoke_replay": int(min_research_shared_dates),
        },
        "proof_ready_lanes": proof_ready,
        "research_ready_lanes": research_ready,
        "lanes": report_lanes,
        "next_actions": next_actions,
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Lane Data Shortfall Report",
        "",
        f"Generated: {report.get('generated_at')}",
        f"Database: {report.get('db_path')}",
        "",
    ]
    for lane in report.get("lanes") or []:
        trusted = lane["coverage"]["trusted_alpaca"]
        research = lane["coverage"]["all_research_and_trusted"]
        lines.extend(
            [
                f"## {lane['label']}",
                "",
                f"- Symbols: {lane['symbol_count']}",
                (
                    "- Trusted Alpaca shared dates: "
                    f"{trusted['shared_quote_dates']['count']} "
                    f"({trusted['shared_quote_dates']['first']} to {trusted['shared_quote_dates']['last']})"
                ),
                (
                    "- Research/all shared dates: "
                    f"{research['shared_quote_dates']['count']} "
                    f"({research['shared_quote_dates']['first']} to {research['shared_quote_dates']['last']})"
                ),
                f"- Latest all-data date: {research.get('latest_quote_date')}",
                (
                    "- Missing on latest all-data date: "
                    + (", ".join(research.get("latest_quote_date_missing_symbols") or []) or "none")
                ),
                f"- Next action: {lane['next_action']}",
                "",
            ]
        )
    if report.get("next_actions"):
        lines.extend(["## Next Actions", ""])
        lines.extend(f"- {item}" for item in report["next_actions"])
        lines.append("")
    return "\n".join(lines)


def write_report(report: dict[str, Any], *, output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("lane_data_shortfall_%Y%m%dT%H%M%SZ")
    json_path = output_path / f"{stamp}.json"
    md_path = output_path / f"{stamp}.md"
    latest_json = output_path / "latest.json"
    latest_md = output_path / "latest.md"
    serialized = json.dumps(report, indent=2)
    markdown = _markdown(report)
    json_path.write_text(serialized, encoding="utf8")
    latest_json.write_text(serialized, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    return {
        "json": str(json_path),
        "markdown": str(md_path),
        "latest_json": str(latest_json),
        "latest_markdown": str(latest_md),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize regular and commodity lane option-data shortfalls.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--min-trusted-shared-dates", type=int, default=120)
    parser.add_argument("--min-research-shared-dates", type=int, default=15)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_lane_data_shortfall_report(
        db_path=args.db_path,
        min_trusted_shared_dates=args.min_trusted_shared_dates,
        min_research_shared_dates=args.min_research_shared_dates,
    )
    artifacts = write_report(report, output_dir=args.output_dir)
    payload = {"artifacts": artifacts, "report": report}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        compact = {
            "artifacts": artifacts,
            "status": report.get("status"),
            "proof_ready_lanes": report.get("proof_ready_lanes", []),
            "research_ready_lanes": report.get("research_ready_lanes", []),
            "next_actions": report.get("next_actions", []),
        }
        print(json.dumps(compact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
