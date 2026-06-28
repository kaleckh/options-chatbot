from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_regular_options_point_in_time_dispersion_concentration_proxy as proxy


REPORT_ID = "regular_options_dispersion_concentration_proxy_source_import"
APPROVAL_TOKEN = "APPROVE_DISPERSION_CONCENTRATION_PROXY_SOURCE_IMPORT"
SOURCE_FAMILY = "alpaca_sip_underlying_daily_dispersion_concentration_proxy_v1"
DEFAULT_UNDERLYING_DAILY_SOURCE_ROWS = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-point-in-time-underlying-daily-history"
    / "source_rows.jsonl"
)
DEFAULT_SOURCE_ROWS = proxy.DEFAULT_SOURCE_ROWS
DEFAULT_FEATURE_STORE = proxy.DEFAULT_FEATURE_STORE
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-dispersion-concentration-proxy-source-import"
DEFAULT_DOC = ROOT / "docs" / "regular-options-dispersion-concentration-proxy-source-import.md"
DEFAULT_UNIVERSE = proxy.DEFAULT_UNIVERSE
DEFAULT_INDEX_CARRIER = "SPY"
DEFAULT_START_DATE = proxy.DEFAULT_START_DATE
DEFAULT_END_DATE = proxy.DEFAULT_END_DATE
DEFAULT_AS_OF_DATE = proxy.DEFAULT_AS_OF_DATE

SAFETY_FLAGS = {
    "accepted_profitability": False,
    "historical_replay_performed": False,
    "historical_rows_are_forward_proof": False,
    "quotes_imported": False,
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


def _parse_date(value: Any) -> date:
    return date.fromisoformat(str(value)[:10])


def _parse_universe(value: str | Sequence[str]) -> tuple[str, ...]:
    raw = str(value).replace(";", ",").split(",") if isinstance(value, str) else list(value)
    return tuple(str(item).strip().upper() for item in raw if str(item).strip())


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "") or isinstance(value, bool):
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf8"))
    return payload if isinstance(payload, dict) else {}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _feature_dates(path: Path, *, start: date, end: date, as_of: date) -> list[str]:
    payload = _load_json(path)
    dates: list[str] = []
    for value in payload.get("shared_quote_dates", []):
        parsed = _parse_date(value)
        if start <= parsed <= end and parsed <= as_of:
            dates.append(parsed.isoformat())
    return sorted(set(dates))


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + ("\n" if rows else ""), encoding="utf8")


def _validation_source_rows_path(path: Path) -> Path:
    suffix = path.suffix or ".jsonl"
    stem = path.name[: -len(path.suffix)] if path.suffix else path.name
    return path.with_name(f"{stem}.validation_tmp{suffix}")


def _materialize_proxy_rows(
    rows: list[dict[str, Any]],
    *,
    requested_dates: Sequence[str],
    universe: tuple[str, ...],
    index_carrier: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    requested_set = set(requested_dates)
    universe_set = set(universe)
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    rejected: list[dict[str, Any]] = []
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        input_date = str(row.get("input_date_et") or "")[:10]
        return_pct = _safe_float(row.get("prior_20_trading_day_return_pct"))
        reasons: list[str] = []
        if symbol not in universe_set:
            reasons.append("symbol_outside_requested_universe")
        if input_date not in requested_set:
            reasons.append("input_date_outside_requested_dates")
        if row.get("point_in_time_valid") is not True:
            reasons.append("point_in_time_valid_not_true")
        if row.get("source_provenance_status") != "trusted_local_or_contract_declared":
            reasons.append("source_provenance_status_not_trusted_local_or_contract_declared")
        if str(row.get("source_family") or "") != "point_in_time_underlying_daily_ohlcv_adjusted_v1":
            reasons.append("unsupported_underlying_source_family")
        if return_pct is None:
            reasons.append("missing_prior_20_trading_day_return_pct")
        if reasons:
            if symbol in universe_set and input_date in requested_set:
                rejected.append({"input_date_et": input_date, "symbol": symbol, "reasons": reasons})
            continue
        key = (input_date, symbol)
        if key in by_key:
            continue
        by_key[key] = row

    materialized: list[dict[str, Any]] = []
    for input_date in requested_dates:
        for symbol in universe:
            row = by_key.get((input_date, symbol))
            if row is None:
                rejected.append({"input_date_et": input_date, "symbol": symbol, "reasons": ["missing_underlying_daily_source_row"]})
                continue
            materialized.append(
                {
                    "proxy_date_et": input_date,
                    "symbol": symbol,
                    "index_carrier": index_carrier,
                    "return_pct": float(row["prior_20_trading_day_return_pct"]),
                    "source_name": "alpaca_sip_underlying_daily_prior_20d_return",
                    "source_ref": str(row.get("source_ref") or ""),
                    "source_timestamp_utc": str(row.get("source_timestamp_utc") or ""),
                    "known_at_utc": str(row.get("known_at_utc") or ""),
                    "point_in_time_valid": True,
                    "source_provenance_status": "trusted_local_or_contract_declared",
                    "source_frequency": "daily_close",
                    "source_family": SOURCE_FAMILY,
                    "return_basis": "prior_20_trading_day_return_pct",
                    "upstream_source_family": str(row.get("source_family") or ""),
                    "upstream_source_row_hash": str(row.get("source_row_hash") or ""),
                    "proof_eligible": False,
                }
            )
    return materialized, rejected


def build_report(
    *,
    underlying_daily_source_rows: Path = DEFAULT_UNDERLYING_DAILY_SOURCE_ROWS,
    source_rows_path: Path = DEFAULT_SOURCE_ROWS,
    feature_store_path: Path = DEFAULT_FEATURE_STORE,
    target_start_date: str = DEFAULT_START_DATE,
    target_end_date: str = DEFAULT_END_DATE,
    as_of_date: str = DEFAULT_AS_OF_DATE,
    universe: str | Sequence[str] = DEFAULT_UNIVERSE,
    index_carrier: str = DEFAULT_INDEX_CARRIER,
    approval_token: str = "",
    no_replay: bool = True,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    symbols = _parse_universe(universe)
    index_carrier = str(index_carrier).strip().upper()
    blockers: list[str] = []
    if approval_token != APPROVAL_TOKEN:
        blockers.append("missing_or_invalid_approval_token")
    if not no_replay:
        blockers.append("no_replay_flag_required")
    if not underlying_daily_source_rows.exists():
        blockers.append("underlying_daily_source_rows_missing")
    if not symbols:
        blockers.append("empty_universe")
    if index_carrier not in set(symbols):
        blockers.append("index_carrier_not_in_universe")

    requested_dates: list[str] = []
    materialized: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    downstream: dict[str, Any] | None = None
    upstream_count = 0

    if not blockers:
        requested_dates = _feature_dates(
            feature_store_path,
            start=_parse_date(target_start_date),
            end=_parse_date(target_end_date),
            as_of=_parse_date(as_of_date),
        )
        if not requested_dates:
            blockers.append("feature_store_requested_dates_missing")

    if not blockers:
        try:
            upstream_rows = _load_jsonl(underlying_daily_source_rows)
            upstream_count = len(upstream_rows)
            materialized, rejected_rows = _materialize_proxy_rows(
                upstream_rows,
                requested_dates=requested_dates,
                universe=symbols,
                index_carrier=index_carrier,
            )
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            blockers.append("underlying_daily_source_rows_unreadable_or_malformed")
            rejected_rows.append({"reason": type(exc).__name__, "detail": str(exc)})
        if rejected_rows:
            blockers.append("dispersion_proxy_source_row_materialization_rejected_dates")
        if not materialized:
            blockers.append("no_dispersion_proxy_source_rows_materialized")

    wrote_source_rows = False

    if not blockers:
        validation_source_rows_path = _validation_source_rows_path(source_rows_path)
        _write_jsonl(validation_source_rows_path, materialized)
        downstream = proxy.build_report(
            source_rows_path=validation_source_rows_path,
            feature_store_path=feature_store_path,
            start_date=target_start_date,
            end_date=target_end_date,
            as_of_date=as_of_date,
            universe=",".join(symbols),
            no_write=True,
            generated_at_utc=generated_at_utc,
        )
        if downstream.get("status") != "point_in_time_dispersion_concentration_proxy_available":
            blockers.append("downstream_dispersion_concentration_proxy_validation_failed")
            try:
                validation_source_rows_path.unlink()
            except FileNotFoundError:
                pass
        else:
            source_rows_path.parent.mkdir(parents=True, exist_ok=True)
            validation_source_rows_path.replace(source_rows_path)
            wrote_source_rows = True

    status = (
        "dispersion_concentration_proxy_source_import_materialized"
        if not blockers
        else "blocked_dispersion_concentration_proxy_source_import"
    )
    return {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": status,
        **SAFETY_FLAGS,
        "source_family": SOURCE_FAMILY,
        "approval_token_valid": approval_token == APPROVAL_TOKEN,
        "required_approval_token": APPROVAL_TOKEN,
        "no_replay": no_replay,
        "underlying_daily_source_rows": _rel(underlying_daily_source_rows),
        "underlying_daily_source_row_count": upstream_count,
        "target_start_date": target_start_date,
        "target_end_date": target_end_date,
        "as_of_date": as_of_date,
        "universe": list(symbols),
        "index_carrier": index_carrier,
        "feature_store_path": _rel(feature_store_path),
        "requested_market_date_count": len(requested_dates),
        "source_rows_path": _rel(source_rows_path),
        "source_rows_written": wrote_source_rows,
        "source_row_count": len(materialized),
        "rejected_rows": rejected_rows[:100],
        "downstream_dispersion_concentration_proxy_status": downstream.get("status") if downstream else None,
        "downstream_dispersion_concentration_proxy_coverage": downstream.get("coverage") if downstream else None,
        "blockers": blockers,
        "downstream_replay_performed": False,
        "downstream_command_to_run_next": "npm run options:research:dispersion-proxy-hybrid-replay-readiness -- --json",
    }


def render_markdown(report: dict[str, Any]) -> str:
    coverage = report.get("downstream_dispersion_concentration_proxy_coverage") or {}
    lines = [
        "# Regular Options Dispersion/Concentration Proxy Source Import",
        "",
        f"- Status: `{report['status']}`.",
        f"- Source family: `{report['source_family']}`.",
        f"- Approval token valid: `{str(report['approval_token_valid']).lower()}`.",
        f"- Source rows written: `{str(report['source_rows_written']).lower()}`.",
        f"- Source rows: `{report['source_row_count']}`.",
        f"- Requested market dates: `{report['requested_market_date_count']}`.",
        f"- Downstream proxy status: `{report.get('downstream_dispersion_concentration_proxy_status')}`.",
        f"- Covered months: `{coverage.get('covered_month_count')}` / `{coverage.get('requested_month_count')}`.",
        f"- Date coverage: `{coverage.get('date_coverage_pct')}`.",
        f"- Historical replay performed: `{str(report['historical_replay_performed']).lower()}`.",
        f"- Accepted profitability: `{str(report['accepted_profitability']).lower()}`.",
        "",
        "This import writes generated point-in-time dispersion/concentration proxy source rows from the already-materialized Alpaca SIP underlying daily source rows. It does not run replay, import option quotes, mutate trusted evidence stores, create trades, enable live validation, enable auto-track, submit broker orders, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, or promote any lane.",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- `{item}`" for item in report.get("blockers", [])) if report.get("blockers") else lines.append("- None.")
    lines.extend(
        [
            "",
            "## Next Command",
            "",
            "```powershell",
            str(report.get("downstream_command_to_run_next") or ""),
            "```",
            "",
        ]
    )
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
    parser = argparse.ArgumentParser(description="Materialize point-in-time dispersion/concentration proxy source rows from Alpaca daily source rows.")
    parser.add_argument("--underlying-daily-source-rows", type=Path, default=DEFAULT_UNDERLYING_DAILY_SOURCE_ROWS)
    parser.add_argument("--source-rows", type=Path, default=DEFAULT_SOURCE_ROWS)
    parser.add_argument("--feature-store", type=Path, default=DEFAULT_FEATURE_STORE)
    parser.add_argument("--target-start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--target-end-date", default=DEFAULT_END_DATE)
    parser.add_argument("--as-of-date", default=DEFAULT_AS_OF_DATE)
    parser.add_argument("--universe", default=DEFAULT_UNIVERSE)
    parser.add_argument("--index-carrier", default=DEFAULT_INDEX_CARRIER)
    parser.add_argument("--approval-token", default="")
    parser.add_argument("--no-replay", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--no-write-report", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    report = build_report(
        underlying_daily_source_rows=args.underlying_daily_source_rows,
        source_rows_path=args.source_rows,
        feature_store_path=args.feature_store,
        target_start_date=args.target_start_date,
        target_end_date=args.target_end_date,
        as_of_date=args.as_of_date,
        universe=args.universe,
        index_carrier=args.index_carrier,
        approval_token=args.approval_token,
        no_replay=args.no_replay,
    )
    if not args.no_write_report:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    print(json.dumps(report, indent=2, sort_keys=True) if args.json_output else render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
