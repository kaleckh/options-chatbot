from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from statistics import median, pstdev
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_point_in_time_dispersion_concentration_proxy"
DEFAULT_SOURCE_ROWS = (
    ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-dispersion-concentration-proxy" / "source_rows.jsonl"
)
DEFAULT_FEATURE_STORE = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-dispersion-concentration-proxy"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-point-in-time-dispersion-concentration-proxy.md"

DEFAULT_START_DATE = "2024-06-01"
DEFAULT_END_DATE = "2026-05-31"
DEFAULT_AS_OF_DATE = "2026-06-04"
DEFAULT_UNIVERSE = "SPY,QQQ,IWM,AAPL,GOOGL,UNH,LLY,JNJ,XOM,CVX,COP,NEM,DIA"
INDEX_CARRIERS = {"SPY", "QQQ", "IWM", "DIA"}
MIN_COVERED_MONTHS = 20
MIN_DATE_COVERAGE_PCT = 90.0
MIN_CONSTITUENTS_PER_DATE = 5

REQUIRED_ROW_FIELDS = (
    "proxy_date_et",
    "symbol",
    "index_carrier",
    "return_pct",
    "source_name",
    "source_ref",
    "source_timestamp_utc",
    "known_at_utc",
    "point_in_time_valid",
    "source_provenance_status",
)
LEAKAGE_KEYS = {
    "future_return",
    "future_returns",
    "future_realized_vol",
    "future_iv",
    "realized_pnl",
    "realized_vol",
    "net_pnl",
    "net_pnl_usd",
    "option_pnl",
    "option_return",
    "trade_outcome",
    "winner",
    "label",
    "post_entry_return",
}
READ_ONLY_FLAGS = {
    "read_only": True,
    "research_only": True,
    "no_write": True,
    "accepted_profitability": False,
    "historical_replay_performed": False,
    "historical_rows_are_forward_proof": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "production_scanner_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "promotion_ready": False,
}
FORBIDDEN_ACTIONS = (
    "broker_orders",
    "broker_order_preparation",
    "live_validation",
    "auto_track",
    "production_scanner_changes",
    "strategy_logic_changes",
    "stop_changes",
    "sizing_changes",
    "proof_bar_changes",
    "quote_import",
    "external_market_data_fetch",
    "options_history_db_mutation",
    "canonical_evidence_store_mutation",
    "forward_cohort_append",
    "protected_holdout_consumption",
    "promotion",
    "using_realized_pnl_or_selected_winners_to_define_thresholds",
)

EASTERN = ZoneInfo("America/New_York")


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


def _parse_dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "") or isinstance(value, bool):
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _load_json(path: Path, *, required: bool) -> tuple[Any, dict[str, Any]]:
    meta = {"path": _rel(path), "required": required, "exists": path.exists(), "status": "missing", "error": None}
    if not path.exists():
        return {}, meta
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        meta["status"] = "malformed"
        meta["error"] = f"JSONDecodeError:{exc.lineno}:{exc.colno}"
        return {}, meta
    except OSError as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return {}, meta
    if isinstance(payload, dict):
        meta["generated_at_utc"] = payload.get("generated_at_utc")
        meta["report_id"] = payload.get("report_id") or payload.get("contract_id")
        meta["status_value"] = payload.get("status")
    meta["status"] = "loaded"
    return payload, meta


def _load_source_rows(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta = {"path": _rel(path), "required": False, "exists": path.exists(), "status": "missing", "error": None, "row_count": 0}
    if not path.exists():
        return [], meta
    rows: list[dict[str, Any]] = []
    try:
        if path.suffix.lower() == ".jsonl":
            for line_number, line in enumerate(path.read_text(encoding="utf8").splitlines(), start=1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
                else:
                    meta.setdefault("non_object_lines", []).append(line_number)
        else:
            payload = json.loads(path.read_text(encoding="utf8"))
            if isinstance(payload, list):
                rows = [row for row in payload if isinstance(row, dict)]
            elif isinstance(payload, dict):
                for key in ("source_rows", "proxy_source_rows", "rows"):
                    if isinstance(payload.get(key), list):
                        rows = [row for row in payload[key] if isinstance(row, dict)]
                        break
    except json.JSONDecodeError as exc:
        meta["status"] = "malformed"
        meta["error"] = f"JSONDecodeError:{exc.lineno}:{exc.colno}"
        return [], meta
    except OSError as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return [], meta
    meta["status"] = "loaded"
    meta["row_count"] = len(rows)
    return rows, meta


def _feature_store_dates(feature_store: Any, *, start: date, end: date) -> list[str]:
    dates: list[str] = []
    for value in _as_list(_as_dict(feature_store).get("shared_quote_dates")):
        parsed = _parse_date(value)
        if parsed and start <= parsed <= end:
            dates.append(parsed.isoformat())
    return sorted(set(dates))


def _months_between(start: date, end: date) -> list[str]:
    months: list[str] = []
    year = start.year
    month = start.month
    while (year, month) <= (end.year, end.month):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def _find_leakage_keys(row: dict[str, Any]) -> list[str]:
    hits: list[str] = []

    def walk(value: Any, prefix: str = "") -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                path = f"{prefix}.{key}" if prefix else str(key)
                if str(key).lower() in LEAKAGE_KEYS:
                    hits.append(path)
                walk(nested, path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{prefix}[{index}]")

    walk(row)
    return hits


def _known_before_proxy_date(row: dict[str, Any], known_at: datetime) -> bool:
    source_frequency = str(row.get("source_frequency") or "daily_close").lower()
    candidate_entry = _parse_dt(row.get("candidate_entry_timestamp_utc"))
    if candidate_entry:
        return known_at <= candidate_entry
    if source_frequency == "intraday":
        return True
    proxy_date = _parse_date(row.get("proxy_date_et"))
    return bool(proxy_date and known_at.astimezone(EASTERN).date() < proxy_date)


def _validate_row(
    row: dict[str, Any],
    index: int,
    *,
    start: date,
    end: date,
    as_of_date: date,
    universe: set[str],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    reasons: list[str] = []
    missing = [field for field in REQUIRED_ROW_FIELDS if row.get(field) in (None, "")]
    if missing:
        reasons.append("missing_required_fields")
    symbol = str(row.get("symbol") or "").upper()
    index_carrier = str(row.get("index_carrier") or "").upper()
    proxy_date = _parse_date(row.get("proxy_date_et"))
    source_ts = _parse_dt(row.get("source_timestamp_utc"))
    known_at = _parse_dt(row.get("known_at_utc"))
    return_pct = _safe_float(row.get("return_pct"))
    leakage = _find_leakage_keys(row)
    if symbol not in universe:
        reasons.append("symbol_outside_requested_universe")
    if index_carrier not in INDEX_CARRIERS:
        reasons.append("invalid_index_carrier")
    if proxy_date is None or not (start <= proxy_date <= end):
        reasons.append("proxy_date_outside_requested_window")
    elif proxy_date > as_of_date:
        reasons.append("proxy_date_after_as_of_date")
    if row.get("point_in_time_valid") is not True:
        reasons.append("point_in_time_valid_not_true")
    if row.get("source_provenance_status") != "trusted_local_or_contract_declared":
        reasons.append("source_provenance_status_not_trusted_local_or_contract_declared")
    if source_ts is None or known_at is None:
        reasons.append("missing_or_invalid_source_or_known_at_timestamp")
    elif known_at < source_ts:
        reasons.append("known_at_before_source_timestamp")
    elif not _known_before_proxy_date(row, known_at):
        reasons.append("known_at_after_candidate_join_cutoff")
    if return_pct is None:
        reasons.append("missing_or_invalid_return_pct")
    if leakage:
        reasons.append("leakage_fields_present")
    if reasons:
        return None, {
            "index": index,
            "proxy_date_et": row.get("proxy_date_et"),
            "symbol": row.get("symbol"),
            "reasons": reasons,
            "missing_fields": missing,
            "leakage_keys": leakage,
        }
    assert proxy_date is not None and return_pct is not None
    return (
        {
            "proxy_date_et": proxy_date.isoformat(),
            "symbol": symbol,
            "index_carrier": index_carrier,
            "return_pct": return_pct,
            "source_name": str(row["source_name"]),
            "source_ref": str(row["source_ref"]),
            "source_timestamp_utc": str(row["source_timestamp_utc"]),
            "known_at_utc": str(row["known_at_utc"]),
            "point_in_time_valid": True,
            "source_provenance_status": "trusted_local_or_contract_declared",
            "source_frequency": str(row.get("source_frequency") or "daily_close"),
            "proof_eligible": False,
        },
        None,
    )


def _source_inventory(
    *,
    source_meta: dict[str, Any],
    feature_store: Any,
    feature_meta: dict[str, Any],
    universe: set[str],
    requested_dates: list[str],
) -> dict[str, Any]:
    feature = _as_dict(feature_store)
    rows = [_as_dict(row) for row in _as_list(feature.get("symbol_surface_rows"))]
    available_symbols = {str(row.get("symbol") or "").upper() for row in rows if row.get("symbol")}
    missing_symbols = sorted(universe - available_symbols)
    underlying_price_rows = sum(int(row.get("underlying_price_row_count") or 0) for row in rows if str(row.get("symbol") or "").upper() in universe)
    return_fields_available = underlying_price_rows > 0
    status = "ready" if source_meta.get("status") == "loaded" and source_meta.get("row_count", 0) > 0 else "missing_proxy_source_rows"
    if feature_meta.get("status") != "loaded":
        feature_status = "missing_feature_store"
    elif missing_symbols:
        feature_status = "feature_store_universe_mismatch"
    elif not return_fields_available:
        feature_status = "feature_store_missing_underlying_return_fields"
    else:
        feature_status = "feature_store_return_fields_present"
    return {
        "status": status,
        "source_rows": source_meta,
        "feature_store": {
            **feature_meta,
            "requested_date_count": len(requested_dates),
            "available_symbols": sorted(available_symbols & universe),
            "missing_symbols": missing_symbols,
            "underlying_price_row_count": underlying_price_rows,
            "return_fields_available": return_fields_available,
            "inventory_status": feature_status,
        },
    }


def _compute_proxy_rows(clean_rows: list[dict[str, Any]], *, requested_dates: set[str], universe: set[str]) -> list[dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in clean_rows:
        by_date[str(row["proxy_date_et"])].append(row)
    proxy_rows: list[dict[str, Any]] = []
    for proxy_date in sorted(by_date):
        if requested_dates and proxy_date not in requested_dates:
            continue
        rows = by_date[proxy_date]
        constituent_rows = [row for row in rows if row["symbol"] not in INDEX_CARRIERS]
        index_rows = [row for row in rows if row["symbol"] in INDEX_CARRIERS]
        returns = [float(row["return_pct"]) for row in constituent_rows]
        index_carrier = str(rows[0]["index_carrier"])
        index_return_row = next((row for row in index_rows if row["symbol"] == index_carrier), None)
        missing_symbols = sorted(universe - {str(row["symbol"]) for row in rows})
        blockers: list[str] = []
        if len(returns) < MIN_CONSTITUENTS_PER_DATE:
            blockers.append("insufficient_constituent_return_rows")
        if index_return_row is None:
            blockers.append("missing_index_carrier_return_row")
        dispersion = round(pstdev(returns), 6) if len(returns) >= 2 else None
        abs_sum = sum(abs(value) for value in returns)
        concentration = round(max((abs(value) for value in returns), default=0.0) / abs_sum, 6) if abs_sum else None
        median_return = median(returns) if returns else None
        index_return = float(index_return_row["return_pct"]) if index_return_row else None
        leadership_skew = round(index_return - median_return, 6) if index_return is not None and median_return is not None else None
        broadening_state = "blocked"
        if not blockers and concentration is not None and leadership_skew is not None:
            broadening_state = "concentrated_leadership" if concentration >= 0.35 and leadership_skew > 0 else "broad_or_mixed"
        proxy_rows.append(
            {
                "proxy_date_et": proxy_date,
                "index_carrier": index_carrier,
                "constituent_count_available": len(returns),
                "missing_symbol_count": len(missing_symbols),
                "missing_symbols": missing_symbols,
                "stale_or_untrusted_symbol_count": 0,
                "cross_section_return_dispersion": dispersion,
                "concentration_proxy": concentration,
                "leadership_skew_proxy": leadership_skew,
                "broadening_or_narrowing_state": broadening_state,
                "blockers": blockers,
                "proof_eligible": False,
            }
        )
    return proxy_rows


def _coverage(proxy_rows: list[dict[str, Any]], requested_dates: list[str], requested_months: list[str]) -> dict[str, Any]:
    clean_dates = sorted(row["proxy_date_et"] for row in proxy_rows if not row.get("blockers"))
    covered_months = sorted({item[:7] for item in clean_dates})
    missing_months = sorted(set(requested_months) - set(covered_months))
    requested_date_set = set(requested_dates)
    covered_dates = sorted(set(clean_dates) & requested_date_set) if requested_date_set else clean_dates
    date_coverage_pct = 100.0 if not requested_dates else round(len(covered_dates) / len(requested_dates) * 100.0, 4)
    return {
        "requested_months": requested_months,
        "requested_month_count": len(requested_months),
        "covered_months": covered_months,
        "covered_month_count": len(covered_months),
        "missing_months": missing_months,
        "requested_date_count": len(requested_dates),
        "covered_date_count": len(covered_dates),
        "date_coverage_pct": date_coverage_pct,
        "minimum_covered_months": min(MIN_COVERED_MONTHS, len(requested_months)),
        "minimum_date_coverage_pct": MIN_DATE_COVERAGE_PCT,
    }


def _status(blockers: list[str]) -> str:
    if blockers:
        return "blocked_point_in_time_dispersion_concentration_proxy"
    return "point_in_time_dispersion_concentration_proxy_available"


def build_report(
    *,
    source_rows_path: Path = DEFAULT_SOURCE_ROWS,
    feature_store_path: Path = DEFAULT_FEATURE_STORE,
    start_date: str = DEFAULT_START_DATE,
    end_date: str = DEFAULT_END_DATE,
    as_of_date: str = DEFAULT_AS_OF_DATE,
    universe: str = DEFAULT_UNIVERSE,
    no_write: bool = True,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    as_of = _parse_date(as_of_date)
    if start is None or end is None or as_of is None or start > end:
        raise ValueError("invalid start/end/as-of date")
    requested_universe = {item.strip().upper() for item in universe.split(",") if item.strip()}
    if not requested_universe:
        raise ValueError("universe must not be empty")
    if not no_write:
        raise ValueError("--no-write is required for this materializer")

    source_rows, source_meta = _load_source_rows(source_rows_path)
    feature_store, feature_meta = _load_json(feature_store_path, required=True)
    requested_dates = _feature_store_dates(feature_store, start=start, end=end)
    requested_months = _months_between(start, end)
    inventory = _source_inventory(
        source_meta=source_meta,
        feature_store=feature_store,
        feature_meta=feature_meta,
        universe=requested_universe,
        requested_dates=requested_dates,
    )

    clean_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    for index, row in enumerate(source_rows):
        clean, reject = _validate_row(row, index, start=start, end=end, as_of_date=as_of, universe=requested_universe)
        if clean:
            clean_rows.append(clean)
        if reject:
            rejected_rows.append(reject)
    proxy_rows = _compute_proxy_rows(clean_rows, requested_dates=set(requested_dates), universe=requested_universe)
    coverage = _coverage(proxy_rows, requested_dates, requested_months)

    blockers: list[str] = []
    if source_meta.get("status") == "missing" or source_meta.get("row_count", 0) == 0:
        blockers.append("missing_point_in_time_dispersion_proxy_source")
    if feature_meta.get("status") != "loaded":
        blockers.append("missing_trusted_feature_store")
    if _as_dict(inventory.get("feature_store")).get("missing_symbols"):
        blockers.append("source_universe_mismatch")
    if _as_dict(inventory.get("feature_store")).get("return_fields_available") is False:
        blockers.append("missing_required_return_fields")
    if not requested_dates:
        blockers.append("missing_requested_feature_store_dates")
    if rejected_rows:
        blockers.append("point_in_time_dispersion_proxy_row_validation_failed")
    if any(row.get("blockers") for row in proxy_rows):
        blockers.append("insufficient_daily_proxy_row_completeness")
    if coverage["covered_month_count"] < coverage["minimum_covered_months"]:
        blockers.append("insufficient_month_coverage")
    if coverage["date_coverage_pct"] < MIN_DATE_COVERAGE_PCT:
        blockers.append("insufficient_date_coverage")
    blockers = list(dict.fromkeys(blockers))

    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": _status(blockers),
        **READ_ONLY_FLAGS,
        "scope": "read_only_point_in_time_dispersion_concentration_proxy_materializer",
        "research_window": {"start_date": start.isoformat(), "end_date": end.isoformat(), "as_of_date": as_of.isoformat()},
        "requested_universe": sorted(requested_universe),
        "index_carriers": sorted(INDEX_CARRIERS & requested_universe),
        "source_inventory": inventory,
        "formula_policy": {
            "cross_section_return_dispersion": "population standard deviation of same-known-at constituent return_pct values for the proxy date",
            "concentration_proxy": "max(abs(constituent_return_pct)) / sum(abs(constituent_return_pct))",
            "leadership_skew_proxy": "index_carrier_return_pct - median(constituent_return_pct)",
            "broadening_or_narrowing_state": "concentrated_leadership when concentration_proxy >= 0.35 and leadership_skew_proxy > 0, else broad_or_mixed; blocked rows stay blocked",
            "thresholds_outcome_tuned": False,
        },
        "coverage": coverage,
        "proxy_rows": proxy_rows,
        "accepted_source_row_count": len(clean_rows),
        "rejected_source_rows": rejected_rows,
        "blockers": blockers,
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }
    _validate_report(report)
    return report


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    if report["status"] == "point_in_time_dispersion_concentration_proxy_available" and report["blockers"]:
        raise ValueError("proxy cannot be available while blockers are present")
    for row in _as_list(report.get("proxy_rows")):
        if _as_dict(row).get("proof_eligible") is not False:
            raise ValueError("proxy rows cannot be proof eligible")


def render_markdown(report: dict[str, Any]) -> str:
    coverage = _as_dict(report.get("coverage"))
    lines = [
        "# Regular Options Point-in-Time Dispersion/Concentration Proxy",
        "",
        "This report is generated from `scripts/build_regular_options_point_in_time_dispersion_concentration_proxy.py`. It is a read-only input materializer for future dispersion-proxy hybrid research. It does not run replay, create trades, import quotes, mutate evidence stores, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, enable live validation or auto-track, submit broker orders, or promote any lane.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Accepted profitability: `{str(report['accepted_profitability']).lower()}`.",
        f"- Covered months: `{coverage.get('covered_month_count')}` / `{coverage.get('requested_month_count')}`.",
        f"- Date coverage: `{coverage.get('date_coverage_pct')}`.",
        f"- Accepted source rows: `{report.get('accepted_source_row_count')}`.",
        f"- Proxy rows: `{len(_as_list(report.get('proxy_rows')))}`.",
        "",
        "## Source Inventory",
        "",
        "```json",
        json.dumps(report.get("source_inventory"), indent=2, sort_keys=True),
        "```",
        "",
        "## Formula Policy",
        "",
        "```json",
        json.dumps(report.get("formula_policy"), indent=2, sort_keys=True),
        "```",
        "",
        "## Blockers",
        "",
    ]
    if report.get("blockers"):
        lines.extend(f"- `{item}`" for item in _as_list(report.get("blockers")))
    else:
        lines.append("- None.")
    lines.extend(["", "## Forbidden Actions", ""])
    lines.extend(f"- `{item}`" for item in _as_list(report.get("forbidden_actions")))
    lines.append("")
    return "\n".join(lines)


def write_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOCS_REPORT,
) -> dict[str, str]:
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
    markdown = render_markdown(report_with_artifacts)
    for path in (json_path, latest_json):
        path.write_text(json.dumps(report_with_artifacts, indent=2, sort_keys=True) + "\n", encoding="utf8")
    for path in (md_path, latest_md, docs_report):
        path.write_text(markdown, encoding="utf8")
    report["artifacts"] = artifacts
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a read-only point-in-time dispersion/concentration proxy artifact.")
    parser.add_argument("--source-rows", type=Path, default=DEFAULT_SOURCE_ROWS)
    parser.add_argument("--feature-store", type=Path, default=DEFAULT_FEATURE_STORE)
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=DEFAULT_END_DATE)
    parser.add_argument("--as-of-date", default=DEFAULT_AS_OF_DATE)
    parser.add_argument("--universe", default=DEFAULT_UNIVERSE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    report = build_report(
        source_rows_path=args.source_rows,
        feature_store_path=args.feature_store,
        start_date=args.start_date,
        end_date=args.end_date,
        as_of_date=args.as_of_date,
        universe=args.universe,
        no_write=args.no_write,
    )
    report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
