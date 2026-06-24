from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_regular_options_underlying_daily_source_repair_packet as packet


REPORT_ID = "regular_options_underlying_daily_history_source_import"
APPROVAL_TOKEN = "APPROVE_UNDERLYING_DAILY_HISTORY_SOURCE_IMPORT"
SOURCE_FAMILY = "point_in_time_underlying_daily_ohlcv_adjusted_v1"
DEFAULT_SOURCE_ROWS = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-point-in-time-underlying-daily-history"
    / "source_rows.jsonl"
)
DEFAULT_FEATURE_STORE = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-underlying-daily-source-import"
DEFAULT_DOC = ROOT / "docs" / "regular-options-underlying-daily-source-import.md"

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


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf8"))
    return payload if isinstance(payload, dict) else {}


def _feature_dates(path: Path, *, start: date, end: date, as_of: date) -> list[str]:
    payload = _load_json(path)
    dates: list[str] = []
    for value in payload.get("shared_quote_dates", []):
        parsed = _parse_date(value)
        if start <= parsed <= end and parsed <= as_of:
            dates.append(parsed.isoformat())
    return sorted(set(dates))


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _row_hash(row: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf8")).hexdigest()


def _is_under_tests_fixtures(path: Path) -> bool:
    try:
        resolved = path.resolve()
        fixtures = (ROOT / "tests" / "fixtures").resolve()
        return resolved == fixtures or fixtures in resolved.parents
    except OSError:
        return False


def _is_default_source_rows_path(path: Path) -> bool:
    try:
        return path.resolve() == DEFAULT_SOURCE_ROWS.resolve()
    except OSError:
        return False


def _source_name(row: dict[str, Any]) -> str:
    return str(packet._field_value(row, ("source", "vendor", "source_name")) or "trusted_underlying_daily_history_csv")


def _source_ref(row: dict[str, Any], source_file: Path) -> str:
    value = packet._field_value(row, ("source_ref", "source_url_or_file_name", "provenance_id"))
    return str(value or f"{_rel(source_file)}:{row['symbol']}:{row['bar_date']}")


def _source_timestamp_utc(row: dict[str, Any]) -> str:
    value = packet._field_value(row, ("source_event_time", "source_timestamp_utc", "published_at_utc", "known_at_utc"))
    if value not in (None, ""):
        text = str(value)
        if len(text) == 10:
            return f"{text}T21:00:00Z"
        return packet._parse_utc(text).isoformat(timespec="seconds").replace("+00:00", "Z")
    event_date = packet._field_value(row, ("source_event_date", "bar_date"))
    return f"{str(event_date)[:10]}T21:00:00Z"


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str, tuple[str, ...]]] = set()
    deduped: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: (item["symbol"], item["bar_date"], str(item.get("known_at_utc") or item.get("published_at_utc") or ""))):
        key = (
            row["symbol"],
            row["bar_date"],
            str(row.get("adjustment_mode") or ""),
            str(row.get("corporate_action_basis") or ""),
            tuple(str(row.get(field) or "") for field in ("open", "high", "low", "close", "adjusted_close", "volume")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _index_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        indexed[row["symbol"]].append(row)
    for symbol in indexed:
        indexed[symbol].sort(key=lambda item: (item["bar_date"], packet.known_at_for_row(item)))
    return indexed


def _latest_prior(
    indexed: dict[str, list[dict[str, Any]]],
    *,
    symbol: str,
    input_date: str,
) -> dict[str, Any] | None:
    usable = _usable_prior_rows(indexed, symbol=symbol, input_date=input_date)
    return usable[-1] if usable else None


def _usable_prior_rows(
    indexed: dict[str, list[dict[str, Any]]],
    *,
    symbol: str,
    input_date: str,
) -> list[dict[str, Any]]:
    decision_utc = packet._candidate_decision_utc(input_date)
    return [
        row
        for row in indexed.get(symbol, [])
        if packet.row_usable_for_candidate(row, candidate_date=input_date, candidate_decision_utc=decision_utc)
    ]


def _rolling_metric_close(row: dict[str, Any]) -> float:
    return float(row["close"])


def _rolling_metrics(
    indexed: dict[str, list[dict[str, Any]]],
    *,
    symbol: str,
    input_date: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    usable = _usable_prior_rows(indexed, symbol=symbol, input_date=input_date)
    if len(usable) < 50:
        return None, {
            "input_date_et": input_date,
            "symbol": symbol,
            "reason": "insufficient_prior_50_trading_day_lookback",
            "available_prior_row_count": len(usable),
            "minimum_prior_row_count": 50,
        }
    prior_close = _rolling_metric_close(usable[-1])
    close_20 = _rolling_metric_close(usable[-21])
    if close_20 <= 0:
        return None, {
            "input_date_et": input_date,
            "symbol": symbol,
            "reason": "invalid_20_trading_day_reference_close",
            "reference_bar_date_et": usable[-21]["bar_date"],
        }
    sma_values = [_rolling_metric_close(row) for row in usable[-50:]]
    return {
        "prior_20_trading_day_return_pct": round(((prior_close / close_20) - 1.0) * 100.0, 6),
        "prior_50_trading_day_sma": round(sum(sma_values) / len(sma_values), 6),
        "rolling_metric_prior_row_count": len(usable),
        "rolling_metric_price_basis": "close",
    }, None


def _materialize_rows(
    rows: list[dict[str, Any]],
    *,
    source_file: Path,
    source_file_hash: str,
    requested_dates: list[str],
    universe: tuple[str, ...],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    indexed = _index_rows(rows)
    materialized: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for input_date in requested_dates:
        for symbol in universe:
            row = _latest_prior(indexed, symbol=symbol, input_date=input_date)
            if row is None:
                rejected.append({"input_date_et": input_date, "symbol": symbol, "reason": "missing_prior_underlying_daily_bar"})
                continue
            rolling, rolling_reject = _rolling_metrics(indexed, symbol=symbol, input_date=input_date)
            if rolling_reject is not None:
                rejected.append(rolling_reject)
                continue
            known_at = packet.known_at_for_row(row).isoformat(timespec="seconds").replace("+00:00", "Z")
            output = {
                "input_date_et": input_date,
                "symbol": symbol,
                "prior_bar_date_et": row["bar_date"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "adjusted_close": float(row["adjusted_close"]) if str(row.get("adjusted_close") or "").strip() else None,
                "volume": int(float(row["volume"])),
                "source": _source_name(row),
                "vendor": str(packet._field_value(row, ("vendor", "source", "source_name")) or ""),
                "source_ref": _source_ref(row, source_file),
                "source_timestamp_utc": _source_timestamp_utc(row),
                "known_at_utc": known_at,
                "point_in_time_valid": True,
                "source_provenance_status": str(row.get("source_provenance_status") or "trusted_local_or_contract_declared"),
                "source_family": SOURCE_FAMILY,
                "source_file_hash": source_file_hash,
                "source_row_hash": str(row.get("source_row_hash") or _row_hash(row)),
                "proof_eligible": False,
            }
            assert rolling is not None
            output.update(rolling)
            materialized.append(output)
    return materialized, rejected


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + ("\n" if rows else ""), encoding="utf8")


def build_report(
    *,
    source_file: Path,
    lookback_start_date: str = packet.LOOKBACK_START_DATE,
    target_start_date: str = packet.TARGET_START_DATE,
    target_end_date: str = packet.TARGET_END_DATE,
    as_of_date: str = packet.AS_OF_DATE,
    universe: str | Sequence[str] = packet.TARGET_UNIVERSE,
    source_family: str = SOURCE_FAMILY,
    approval_token: str = "",
    no_replay: bool = True,
    source_rows_path: Path = DEFAULT_SOURCE_ROWS,
    feature_store_path: Path = DEFAULT_FEATURE_STORE,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    symbols = _parse_universe(universe)
    blockers: list[str] = []
    if approval_token != APPROVAL_TOKEN:
        blockers.append("missing_or_invalid_approval_token")
    if source_family != SOURCE_FAMILY:
        blockers.append("unsupported_source_family")
    if not no_replay:
        blockers.append("no_replay_flag_required")
    if not source_file.exists():
        blockers.append("source_file_missing")
    if not symbols:
        blockers.append("empty_universe")
    if _is_under_tests_fixtures(source_file) and _is_default_source_rows_path(source_rows_path):
        blockers.append("fixture_source_file_requires_non_default_source_rows_path")

    requested_dates: list[str] = []
    validation: dict[str, Any] | None = None
    materialized: list[dict[str, Any]] = []
    materialization_rejects: list[dict[str, Any]] = []
    parsed_rows: list[dict[str, Any]] = []
    source_file_hash = _file_sha256(source_file) if source_file.exists() else None

    if not blockers:
        target_start = _parse_date(target_start_date)
        target_end = _parse_date(target_end_date)
        requested_dates = _feature_dates(
            feature_store_path,
            start=target_start,
            end=target_end,
            as_of=_parse_date(as_of_date),
        )
        if not requested_dates:
            blockers.append("feature_store_requested_dates_missing")

    if not blockers:
        try:
            parsed_rows = packet.parse_future_source_csv(source_file)
            validation = packet.validate_future_source_rows(
                parsed_rows,
                target_universe=symbols,
                target_start_date=target_start_date,
                target_end_date=target_end_date,
                requested_dates=requested_dates,
            )
        except (OSError, ValueError) as exc:
            blockers.append("underlying_source_csv_parser_rejected")
            validation = {"error": str(exc)}
        if validation and validation.get("reject_count"):
            blockers.append("underlying_source_csv_rows_rejected")
        if validation and not validation.get("coverage_ready"):
            blockers.append("underlying_source_coverage_not_ready")

    if not blockers:
        assert source_file_hash is not None
        materialized, materialization_rejects = _materialize_rows(
            _dedupe_rows(parsed_rows),
            source_file=source_file,
            source_file_hash=source_file_hash,
            requested_dates=requested_dates,
            universe=symbols,
        )
        if materialization_rejects:
            blockers.append("underlying_source_row_materialization_rejected_dates")
        if not materialized:
            blockers.append("no_underlying_source_rows_materialized")
        if not blockers:
            _write_jsonl(source_rows_path, materialized)

    status = "underlying_daily_history_source_import_materialized" if not blockers else "blocked_underlying_daily_history_source_import"
    return {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": status,
        **SAFETY_FLAGS,
        "source_file": _rel(source_file),
        "source_file_hash": source_file_hash,
        "source_family": source_family,
        "source_family_binding": {
            "expected": SOURCE_FAMILY,
            "provided": source_family,
            "matched": source_family == SOURCE_FAMILY,
        },
        "approval_token_valid": approval_token == APPROVAL_TOKEN,
        "required_approval_token": APPROVAL_TOKEN,
        "no_replay": no_replay,
        "lookback_start_date": lookback_start_date,
        "target_start_date": target_start_date,
        "target_end_date": target_end_date,
        "as_of_date": as_of_date,
        "universe": list(symbols),
        "feature_store_path": _rel(feature_store_path),
        "requested_market_date_count": len(requested_dates),
        "source_rows_path": _rel(source_rows_path),
        "source_rows_path_is_default": _is_default_source_rows_path(source_rows_path),
        "source_file_under_tests_fixtures": _is_under_tests_fixtures(source_file),
        "source_rows_written": status == "underlying_daily_history_source_import_materialized",
        "source_row_count": len(materialized),
        "parser_validation": validation or {},
        "rejected_rows": materialization_rejects[:50],
        "blockers": blockers,
        "downstream_replay_performed": False,
        "downstream_command_to_run_next": "npm run options:research:point-in-time-market-regime-inputs -- --no-write --json",
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Underlying Daily History Source Import",
        "",
        f"- Status: `{report['status']}`.",
        f"- Source family: `{report['source_family']}`.",
        f"- Source family binding matched: `{str(report['source_family_binding']['matched']).lower()}`.",
        f"- Approval token valid: `{str(report['approval_token_valid']).lower()}`.",
        f"- Source rows written: `{str(report['source_rows_written']).lower()}`.",
        f"- Source rows: `{report['source_row_count']}`.",
        f"- Historical replay performed: `{str(report['historical_replay_performed']).lower()}`.",
        f"- Accepted profitability: `{str(report['accepted_profitability']).lower()}`.",
        "",
        "This import writes generated point-in-time underlying daily source rows only after the exact token, source family, parser, validator, coverage, prior-bar, and no-replay gates pass. It does not run replay, import option quotes, mutate trusted evidence stores, create trades, enable live validation, enable auto-track, submit broker orders, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, or promote any lane.",
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
    parser = argparse.ArgumentParser(description="Materialize point-in-time underlying daily source rows from a trusted CSV.")
    parser.add_argument("--source-file", type=Path, required=True)
    parser.add_argument("--lookback-start-date", default=packet.LOOKBACK_START_DATE)
    parser.add_argument("--target-start-date", default=packet.TARGET_START_DATE)
    parser.add_argument("--target-end-date", default=packet.TARGET_END_DATE)
    parser.add_argument("--as-of-date", default=packet.AS_OF_DATE)
    parser.add_argument("--universe", default=",".join(packet.TARGET_UNIVERSE))
    parser.add_argument("--source-family", default=SOURCE_FAMILY)
    parser.add_argument("--approval-token", default="")
    parser.add_argument("--no-replay", action="store_true")
    parser.add_argument("--source-rows", type=Path, default=DEFAULT_SOURCE_ROWS)
    parser.add_argument("--feature-store", type=Path, default=DEFAULT_FEATURE_STORE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--no-write-report", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    report = build_report(
        source_file=args.source_file,
        lookback_start_date=args.lookback_start_date,
        target_start_date=args.target_start_date,
        target_end_date=args.target_end_date,
        as_of_date=args.as_of_date,
        universe=args.universe,
        source_family=args.source_family,
        approval_token=args.approval_token,
        no_replay=args.no_replay,
        source_rows_path=args.source_rows,
        feature_store_path=args.feature_store,
    )
    if not args.no_write_report:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    print(json.dumps(report, indent=2, sort_keys=True) if args.json_output else render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
