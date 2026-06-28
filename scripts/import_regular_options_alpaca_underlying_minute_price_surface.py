from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alpaca_market_data import AlpacaMarketDataClient, primary_provider_label  # noqa: E402
from scripts.capture_alpaca_opra_daily_snapshots import load_env_file  # noqa: E402


REPORT_ID = "regular_options_alpaca_underlying_minute_price_surface_import"
SOURCE_FAMILY = "alpaca_sip_underlying_minute_price_v1"
APPROVAL_TOKEN = "APPROVE_ALPACA_SIP_UNDERLYING_MINUTE_PRICE_SOURCE_IMPORT"
DEFAULT_QUOTES_DB = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_SOURCE_ROWS = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-alpaca-underlying-minute-price-surface"
    / "source_rows.jsonl"
)
DEFAULT_OUTPUT_DIR = (
    ROOT / "data" / "profitability-lab" / "regular-options-alpaca-underlying-minute-price-surface-import"
)
DEFAULT_DOC = ROOT / "docs" / "regular-options-alpaca-underlying-minute-price-surface-import.md"
DEFAULT_UNIVERSE = ("SPY", "QQQ", "IWM", "DIA")
NY = ZoneInfo("America/New_York")

READ_ONLY_FLAGS = {
    "accepted_profitability": False,
    "historical_replay_performed": False,
    "historical_rows_are_forward_proof": False,
    "quotes_imported": False,
    "options_history_db_mutated": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "promotion_ready": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _parse_universe(value: str) -> tuple[str, ...]:
    return tuple(item.strip().upper() for item in str(value).replace(";", ",").split(",") if item.strip())


def _parse_date(value: Any) -> date:
    return date.fromisoformat(str(value)[:10])


def _market_minutes(start_minute: int, end_minute: int) -> set[int]:
    return set(range(int(start_minute), int(end_minute) + 1))


def _date_to_utc(day: date, local_time: time) -> str:
    return datetime.combine(day, local_time, tzinfo=NY).astimezone(UTC).isoformat()


def _source_row(symbol: str, ts: Any, row: Any) -> dict[str, Any]:
    timestamp = ts.to_pydatetime().astimezone(UTC)
    timestamp_et = timestamp.astimezone(NY)
    minute = timestamp_et.hour * 60 + timestamp_et.minute
    close = float(row["Close"])
    return {
        "source_family": SOURCE_FAMILY,
        "provider": primary_provider_label(),
        "source_name": "alpaca_sip_stock_bars_1min",
        "source_ref": f"alpaca://stocks/bars/{symbol}/{timestamp_et.date().isoformat()}/{minute}",
        "underlying": symbol,
        "price_date_et": timestamp_et.date().isoformat(),
        "price_minute_et": minute,
        "price_timestamp_utc": timestamp.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "open": float(row["Open"]),
        "high": float(row["High"]),
        "low": float(row["Low"]),
        "close": close,
        "volume": int(row["Volume"]),
        "known_at_utc": timestamp.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "point_in_time_valid": True,
        "proof_eligible": False,
        "source_provenance_status": "alpaca_sip_paid_provider",
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + ("\n" if rows else ""), encoding="utf8")


def build_report(
    *,
    target_start_date: str = "2024-06-01",
    target_end_date: str = "2026-05-31",
    universe: str = ",".join(DEFAULT_UNIVERSE),
    minute_start: int = 9 * 60 + 35,
    minute_end: int = 10 * 60 + 45,
    approval_token: str = "",
    no_replay: bool = True,
    env_file: Path = ROOT / ".env.local",
    source_rows_path: Path = DEFAULT_SOURCE_ROWS,
    client: AlpacaMarketDataClient | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    symbols = _parse_universe(universe)
    blockers: list[str] = []
    if symbols != DEFAULT_UNIVERSE:
        blockers.append("unsupported_universe")
    if approval_token != APPROVAL_TOKEN:
        blockers.append("missing_or_invalid_approval_token")
    if not no_replay:
        blockers.append("no_replay_flag_required")
    if int(minute_start) > int(minute_end):
        blockers.append("invalid_minute_window")

    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    loaded_env_keys: list[str] = []
    if not blockers:
        loaded_env_keys = sorted(load_env_file(env_file).keys())
        active_client = client or AlpacaMarketDataClient()
        start = _parse_date(target_start_date)
        end = _parse_date(target_end_date)
        requested_minutes = _market_minutes(minute_start, minute_end)
        for symbol in symbols:
            try:
                frame = active_client.stock_bars(
                    symbol,
                    start=_date_to_utc(start, time(9, 30)),
                    end=_date_to_utc(end, time(16, 0)),
                    interval="1m",
                )
            except Exception as exc:
                errors.append({"symbol": symbol, "type": exc.__class__.__name__, "error": str(exc)})
                continue
            for ts, row in frame.iterrows():
                timestamp_et = ts.to_pydatetime().astimezone(NY)
                day = timestamp_et.date()
                minute = timestamp_et.hour * 60 + timestamp_et.minute
                if start <= day <= end and minute in requested_minutes:
                    rows.append(_source_row(symbol, ts, row))
        if errors:
            blockers.append("alpaca_underlying_minute_requests_failed")
        if not rows:
            blockers.append("no_underlying_minute_source_rows_materialized")
        if not blockers:
            rows.sort(key=lambda item: (item["price_date_et"], item["underlying"], item["price_minute_et"]))
            _write_jsonl(source_rows_path, rows)

    status = "alpaca_underlying_minute_price_surface_source_import_materialized" if not blockers else "blocked_alpaca_underlying_minute_price_surface_source_import"
    return {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": status,
        **READ_ONLY_FLAGS,
        "source_family": SOURCE_FAMILY,
        "provider": primary_provider_label(),
        "approval_token_valid": approval_token == APPROVAL_TOKEN,
        "no_replay": no_replay,
        "target_start_date": target_start_date,
        "target_end_date": target_end_date,
        "universe": list(symbols),
        "minute_window_et": {"start": int(minute_start), "end": int(minute_end)},
        "source_rows_path": _rel(source_rows_path),
        "source_rows_written": status == "alpaca_underlying_minute_price_surface_source_import_materialized",
        "source_row_count": len(rows),
        "covered_symbol_dates": len({(row["underlying"], row["price_date_et"]) for row in rows}),
        "loaded_env_keys": loaded_env_keys,
        "errors": errors[:20],
        "blockers": blockers,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Alpaca Underlying Minute Price Surface Import",
        "",
        f"- Status: `{report['status']}`.",
        f"- Source rows written: `{str(report['source_rows_written']).lower()}`.",
        f"- Source rows: `{report['source_row_count']}`.",
        f"- Covered symbol-dates: `{report['covered_symbol_dates']}`.",
        "",
        "This import writes generated Alpaca SIP underlying minute source rows only. It does not import option quotes, mutate `options_history.db`, mutate evidence stores, create trades, enable live validation, enable auto-track, submit broker orders, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, or promote any lane.",
        "",
        "## Blockers",
        "",
    ]
    if report.get("blockers"):
        lines.extend(f"- `{item}`" for item in report["blockers"])
    else:
        lines.append("- None.")
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOC) -> dict[str, str]:
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
    payload = dict(report)
    payload["artifacts"] = artifacts
    markdown = render_markdown(payload)
    for path in (json_path, latest_json):
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")
    for path in (md_path, latest_md, docs_report):
        path.write_text(markdown, encoding="utf8")
    report["artifacts"] = artifacts
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize Alpaca SIP underlying minute source rows for opening-range surfaces.")
    parser.add_argument("--target-start-date", default="2024-06-01")
    parser.add_argument("--target-end-date", default="2026-05-31")
    parser.add_argument("--universe", default=",".join(DEFAULT_UNIVERSE))
    parser.add_argument("--minute-start", type=int, default=9 * 60 + 35)
    parser.add_argument("--minute-end", type=int, default=10 * 60 + 45)
    parser.add_argument("--approval-token", default="")
    parser.add_argument("--no-replay", action="store_true")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env.local")
    parser.add_argument("--source-rows", type=Path, default=DEFAULT_SOURCE_ROWS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--no-write-report", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    report = build_report(
        target_start_date=args.target_start_date,
        target_end_date=args.target_end_date,
        universe=args.universe,
        minute_start=args.minute_start,
        minute_end=args.minute_end,
        approval_token=args.approval_token,
        no_replay=args.no_replay,
        env_file=args.env_file,
        source_rows_path=args.source_rows,
    )
    if not args.no_write_report:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0 if report["status"] == "alpaca_underlying_minute_price_surface_source_import_materialized" else 1


if __name__ == "__main__":
    raise SystemExit(main())
