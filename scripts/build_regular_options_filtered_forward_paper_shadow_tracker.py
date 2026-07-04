from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_regular_options_historical_profitability_filter_iteration import (  # noqa: E402
    _as_dict,
    _as_list,
    _filter_rows,
    _load_json,
    _safe_float,
)
from scripts.evaluate_regular_options_autoresearch import block_bootstrap_confidence_for_values  # noqa: E402


REPORT_ID = "regular_options_filtered_forward_paper_shadow_tracker"
POLICY_ID = "historical_filtered_candidate_v1"
MATCHED_ROW_IDENTITY_SCHEMA = "policy_ticker_scan_date_direction_v2"
DEFAULT_FILTERED_AUDIT = (
    ROOT / "data" / "profitability-lab" / "regular-options-historical-filtered-simulated-forward-audit" / "latest.json"
)
DEFAULT_SOURCE_SCAN_PICKS = ROOT / "data" / "forward-tracking" / "scan_picks.jsonl"
DEFAULT_UNDERLYING_DAILY_SOURCE_ROWS = (
    ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-underlying-daily-history" / "source_rows.jsonl"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking" / "regular-options-filtered-forward-paper-shadow"
DEFAULT_CANDIDATES_JSONL = DEFAULT_OUTPUT_DIR / "candidate_rows.jsonl"
DEFAULT_MATCHED_ROWS_LOG = DEFAULT_OUTPUT_DIR / "matched_rows.jsonl"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-filtered-forward-paper-shadow-tracker.md"
DEFAULT_POLICY_CONTRACT = ROOT / "data" / "contracts" / "regular-options-frozen-filtered-policy-v1.json"
DEFAULT_FORWARD_EVIDENCE_BAR_CONTRACT = (
    ROOT / "data" / "contracts" / "regular-options-filtered-forward-evidence-bar-v1.json"
)
DEFAULT_SCAN_TASK_HEALTH = ROOT / "data" / "forward-tracking" / "regular_options_strict_forward_scan_task_health_latest.json"
HISTORICAL_FILTERED_MATERIALIZER_ROW_COUNT = 306
HISTORICAL_FILTERED_MATERIALIZER_MONTH_COUNT = 24

PROHIBITED_ACTIONS = (
    "do_not_submit_broker_order_from_filtered_forward_tracker",
    "do_not_enable_live_validation_from_filtered_forward_tracker",
    "do_not_enable_auto_track_from_filtered_forward_tracker",
    "do_not_mutate_tracked_positions_from_filtered_forward_tracker",
    "do_not_import_quotes_from_filtered_forward_tracker",
    "do_not_change_scanner_policy_from_filtered_forward_tracker",
    "do_not_lower_proof_bars_from_filtered_forward_tracker",
    "do_not_promote_from_filtered_forward_tracker",
)
TRUSTED_EXECUTABLE_QUOTE_SOURCES = {
    "opra_nbbo",
    "trusted_opra_nbbo",
    "trusted_intraday_opra_nbbo",
    "thetadata_opra_nbbo_1m",
    "alpaca_opra",
    "alpaca_opra_daily_snapshot",
}
CONTRACT_MULTIPLIER = 100
DEFAULT_FEE_PER_CONTRACT_LEG_USD = 0.65
TARGET_EXIT_PCT_OF_DTE = 0.75


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _norm_lower(value: Any) -> str:
    return _norm(value).lower()


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
    return rows, {"path": _rel(path), "exists": True, "status": "loaded", "row_count": len(rows), "bad_row_count": bad}


def _file_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _conditions_sha256(conditions: Sequence[Any]) -> str:
    payload = json.dumps(list(conditions), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf8")).hexdigest()


def _load_policy_contract(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if not path.exists():
        return {}, {"path": _rel(path), "exists": False, "status": "missing"}
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        return {}, {"path": _rel(path), "exists": True, "status": "invalid_json", "error": str(exc)}
    if not isinstance(payload, dict):
        return {}, {"path": _rel(path), "exists": True, "status": "invalid_payload"}
    return payload, {"path": _rel(path), "exists": True, "status": "loaded", "sha256": _file_hash(path)}


def _load_optional_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if not path.exists():
        return {}, {"path": _rel(path), "exists": False, "status": "missing"}
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        return {}, {"path": _rel(path), "exists": True, "status": "invalid_json", "error": str(exc)}
    if not isinstance(payload, dict):
        return {}, {"path": _rel(path), "exists": True, "status": "invalid_payload"}
    return payload, {"path": _rel(path), "exists": True, "status": "loaded", "sha256": _file_hash(path)}


def _stable_tracking_start_at(previous_tracker_dir: Path, *, policy_id: str = POLICY_ID) -> str | None:
    if not previous_tracker_dir.exists():
        return None
    candidates: list[str] = []
    for path in sorted(previous_tracker_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("report_id") != REPORT_ID or payload.get("tracking_policy_id") != policy_id:
            continue
        if payload.get("status") != "filtered_forward_paper_shadow_tracking_active":
            continue
        value = _norm(payload.get("tracking_start_at_utc") or payload.get("generated_at_utc"))
        if value:
            candidates.append(value)
    return min(candidates) if candidates else None


def _candidate_date(row: dict[str, Any]) -> str:
    return _norm(
        row.get("selection_date")
        or row.get("scan_date")
        or row.get("candidate_generation_date")
        or row.get("entry_date")
        or row.get("logged_at")
    )[:10]


def _candidate_timestamp(row: dict[str, Any]) -> str:
    return _norm(
        row.get("logged_at")
        or row.get("scan_timestamp_utc")
        or row.get("scan_started_at_utc")
        or row.get("generated_at_utc")
        or row.get("entry_quote_timestamp_utc")
        or row.get("quote_timestamp_utc")
        or row.get("quote_time_utc")
    )


def _field_from_row(row: dict[str, Any], fields: Sequence[str]) -> Any:
    for field in fields:
        value = row
        ok = True
        for part in field.split("."):
            if not isinstance(value, dict) or part not in value:
                ok = False
                break
            value = value[part]
        if ok and value not in (None, ""):
            return value
    return None


def _source_row_index(rows: Sequence[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if row.get("point_in_time_valid") is False:
            continue
        symbol = _norm(row.get("symbol")).upper()
        input_date = _norm(row.get("input_date_et") or row.get("bar_date"))[:10]
        if symbol and input_date:
            indexed[(symbol, input_date)] = dict(row)
    return indexed


def _prior_20_return(row: dict[str, Any], source_index: dict[tuple[str, str], dict[str, Any]]) -> tuple[float | None, str]:
    direct = _safe_float(
        _field_from_row(
            row,
            (
                "signal_evidence.prior_20_trading_day_return_pct",
                "prior_20_trading_day_return_pct",
                "ret20",
                "signal_ret20",
            ),
        )
    )
    if direct is not None:
        return direct, "scan_row"
    symbol = _norm(row.get("ticker") or row.get("symbol") or row.get("underlying")).upper()
    scan_date = _candidate_date(row)
    source = source_index.get((symbol, scan_date))
    if source:
        parsed = _safe_float(source.get("prior_20_trading_day_return_pct"))
        if parsed is not None:
            return parsed, "point_in_time_underlying_daily_source_rows"
    return None, "missing_prior_20_trading_day_return_pct"


def _scan_row_for_filter(row: dict[str, Any], source_index: dict[tuple[str, str], dict[str, Any]]) -> tuple[dict[str, Any], str | None]:
    ticker = _norm(row.get("ticker") or row.get("symbol") or row.get("underlying")).upper()
    scan_date = _candidate_date(row)
    prior_20, prior_source = _prior_20_return(row, source_index)
    if not ticker:
        return dict(row), "missing_ticker"
    if not scan_date:
        return dict(row), "missing_scan_date"
    if prior_20 is None:
        enriched = dict(row)
        enriched["ticker"] = ticker
        enriched["candidate_generation_date"] = scan_date
        return enriched, "missing_prior_20_trading_day_return_pct"
    enriched = dict(row)
    enriched["ticker"] = ticker
    enriched["symbol"] = ticker
    enriched["candidate_generation_date"] = scan_date
    signal = dict(_as_dict(enriched.get("signal_evidence")))
    signal["prior_20_trading_day_return_pct"] = prior_20
    signal["prior_20_trading_day_return_source"] = prior_source
    enriched["signal_evidence"] = signal
    return enriched, None


def _candidate_direction(row: dict[str, Any]) -> str:
    return _norm_lower(row.get("direction") or row.get("option_direction") or row.get("side") or "unknown")


def _candidate_identity_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        _norm(row.get("tracking_policy_id") or row.get("policy_id") or POLICY_ID),
        _norm(row.get("ticker") or row.get("symbol")).upper(),
        _candidate_date(row),
        _candidate_direction(row),
    )


def _candidate_identity(row: dict[str, Any]) -> str:
    parts = [
        _norm(row.get("tracking_policy_id") or row.get("policy_id") or POLICY_ID),
        _norm(row.get("ticker") or row.get("symbol")).upper(),
        _candidate_date(row),
        _candidate_direction(row),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf8")).hexdigest()[:24]


def _candidate_identity_payload(row: dict[str, Any]) -> dict[str, Any]:
    policy_id, ticker, scan_date, direction = _candidate_identity_key(row)
    return {
        "candidate_id": _candidate_identity(row),
        "candidate_identity_schema": MATCHED_ROW_IDENTITY_SCHEMA,
        "candidate_identity_key": {
            "policy_id": policy_id,
            "ticker": ticker,
            "scan_date": scan_date,
            "direction": direction,
        },
        "identity_policy_id": policy_id,
        "identity_ticker": ticker,
        "identity_scan_date": scan_date,
        "identity_direction": direction,
    }


def _sort_key_first_session(row: dict[str, Any], index: int) -> tuple[str, str, int]:
    return (_candidate_date(row), _candidate_timestamp(row), index)


def _first_daily_signal_matches(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    first_by_key: dict[tuple[str, str, str, str], tuple[dict[str, Any], tuple[str, str, int]]] = {}
    duplicate_count = 0
    for index, row in enumerate(rows):
        key = _candidate_identity_key(row)
        sort_key = _sort_key_first_session(row, index)
        current = first_by_key.get(key)
        if current is None:
            first_by_key[key] = (dict(row), sort_key)
            continue
        duplicate_count += 1
        if sort_key < current[1]:
            first_by_key[key] = (dict(row), sort_key)
    return [item[0] for item in sorted(first_by_key.values(), key=lambda item: item[1])], {
        "duplicate_same_day_signal_matches_suppressed": duplicate_count,
    }


def _matched_log_has_current_identity_schema(rows: Sequence[dict[str, Any]]) -> bool:
    if not rows:
        return True
    return all(_norm(row.get("candidate_identity_schema")) == MATCHED_ROW_IDENTITY_SCHEMA for row in rows)


def _matched_log_duplicate_daily_signal_identities(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    matched_entry_rows = [
        row
        for row in rows
        if _norm(row.get("record_type") or "matched_entry") == "matched_entry"
        and not _is_completed_forward_row(dict(row))
    ]
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in matched_entry_rows:
        key_payload = _as_dict(row.get("candidate_identity_key"))
        key = (
            _norm(key_payload.get("policy_id") or row.get("identity_policy_id") or row.get("tracking_policy_id") or POLICY_ID),
            _norm(key_payload.get("ticker") or row.get("identity_ticker") or row.get("ticker")).upper(),
            _norm(key_payload.get("scan_date") or row.get("identity_scan_date") or row.get("scan_date"))[:10],
            _norm_lower(key_payload.get("direction") or row.get("identity_direction") or row.get("direction") or "unknown"),
        )
        if all(key):
            grouped.setdefault(key, []).append(dict(row))
    duplicates: list[dict[str, Any]] = []
    for key, group in sorted(grouped.items()):
        candidate_ids = sorted({_norm(row.get("candidate_id")) for row in group if _norm(row.get("candidate_id"))})
        if len(group) > 1 or len(candidate_ids) > 1:
            duplicates.append(
                {
                    "policy_id": key[0],
                    "ticker": key[1],
                    "scan_date": key[2],
                    "direction": key[3],
                    "matched_entry_row_count": len(group),
                    "candidate_ids": candidate_ids,
                }
            )
    return duplicates


def _candidate_month(row: dict[str, Any]) -> str:
    return _norm(row.get("scan_date") or row.get("entry_date") or row.get("exit_date"))[:7]


def _ticker_week_cluster(row: dict[str, Any]) -> str:
    raw_date = _norm(row.get("scan_date") or row.get("entry_date"))[:10]
    ticker = _norm(row.get("ticker") or row.get("symbol")).upper() or "UNKNOWN"
    try:
        parsed = datetime.fromisoformat(raw_date).date()
        iso = parsed.isocalendar()
        return f"{ticker}:{iso.year}-W{iso.week:02d}"
    except ValueError:
        return f"{ticker}:unknown-week"


def _policy_exit_date(row: dict[str, Any]) -> str | None:
    raw_scan_date = _candidate_date(row)
    raw_expiry = _norm(row.get("expiry") or row.get("expiration") or row.get("resolved_listed_expiry"))[:10]
    dte = _safe_float(row.get("dte"))
    try:
        entry = date.fromisoformat(raw_scan_date)
        expiry = date.fromisoformat(raw_expiry)
    except ValueError:
        return None
    if dte is None:
        dte = max((expiry - entry).days, 1)
    target_days = max(1, int(round(float(dte) * TARGET_EXIT_PCT_OF_DTE)))
    return min(expiry, entry + timedelta(days=target_days)).isoformat()


def _is_completed_forward_row(row: dict[str, Any]) -> bool:
    state = _norm(row.get("tracking_state"))
    realized = _norm(row.get("realized_pnl_status"))
    return state == "forward_paper_shadow_completed" or realized in {
        "realized_pnl_available",
        "closed_realized_pnl",
        "closed_with_realized_pnl",
        "completed_exact_exit",
    }


def _is_fixture_row(row: dict[str, Any]) -> bool:
    source = _as_dict(row.get("source_row"))
    text_values = [
        row.get("source_report"),
        row.get("evidence_bucket"),
        row.get("row_source"),
        source.get("source_report"),
        source.get("row_source"),
        source.get("data_source"),
    ]
    if row.get("is_fixture") is True or source.get("is_fixture") is True:
        return True
    return any("fixture" in _norm(value).lower() for value in text_values)


def _scheduled_session_times(scan_task_health: dict[str, Any]) -> dict[str, Any]:
    expected = _as_dict(scan_task_health.get("expected"))
    tasks = _as_dict(expected.get("tasks"))
    if tasks:
        return {
            str(name): _as_dict(task).get("start_time")
            for name, task in sorted(tasks.items())
            if _as_dict(task).get("start_time")
        }
    task_reports = _as_dict(scan_task_health.get("task_reports"))
    result: dict[str, Any] = {}
    for name, report in sorted(task_reports.items()):
        fields = _as_dict(_as_dict(report).get("runtime_telemetry")).get("fields")
        start_time = _as_dict(fields).get("configured_expected_start_time")
        if start_time:
            result[str(name)] = start_time
    return result


def _forward_evidence_bar_progress(
    rows: Sequence[dict[str, Any]],
    *,
    bar_contract: dict[str, Any],
    bar_meta: dict[str, Any],
) -> dict[str, Any]:
    requirements = _as_dict(bar_contract.get("requirements"))
    min_rows = int(requirements.get("min_completed_forward_paper_shadow_rows") or 30)
    min_clusters = int(requirements.get("min_ticker_week_clusters") or 8)
    min_months = int(requirements.get("min_calendar_months_with_rows") or 3)
    min_pct_lb = float(requirements.get("min_percent_cluster_pf_lb_5pct") or 1.0)
    min_usd_lb = float(requirements.get("min_usd_cluster_pf_lb_5pct") or 1.0)
    min_total_usd = float(requirements.get("min_total_net_pnl_usd_exclusive") or 0.0)
    max_fixture_rows = int(requirements.get("max_fixture_rows") or 0)
    draws = int(requirements.get("bootstrap_draws") or 10000)
    completed = [dict(row) for row in rows if _is_completed_forward_row(dict(row))]
    clusters = sorted({_ticker_week_cluster(row) for row in completed})
    months = sorted({_candidate_month(row) for row in completed if _candidate_month(row)})
    fixture_count = sum(1 for row in completed if _is_fixture_row(row))
    pct_entries: list[tuple[str, float]] = []
    usd_entries: list[tuple[str, float]] = []
    for row in completed:
        cluster = _ticker_week_cluster(row)
        pct = _safe_float(row.get("net_pnl_pct", row.get("pnl_pct")))
        usd = _safe_float(row.get("net_pnl_usd"))
        if pct is not None:
            pct_entries.append((cluster, pct))
        if usd is not None:
            usd_entries.append((cluster, usd))

    evaluation_permitted = len(completed) >= min_rows
    percent_bootstrap = None
    usd_bootstrap = None
    if evaluation_permitted:
        percent_bootstrap = block_bootstrap_confidence_for_values(
            pct_entries,
            branch_id=f"{REPORT_ID}:forward_evidence_bar:percent",
            draws=max(draws, 1),
        )
        usd_bootstrap = block_bootstrap_confidence_for_values(
            usd_entries,
            branch_id=f"{REPORT_ID}:forward_evidence_bar:usd",
            draws=max(draws, 1),
        )

    total_net_pnl_usd = round(sum(value for _cluster, value in usd_entries), 4) if usd_entries else None
    checks = {
        "completed_rows": len(completed) >= min_rows,
        "ticker_week_clusters": len(clusters) >= min_clusters,
        "calendar_months_with_rows": len(months) >= min_months,
        "fixture_rows": fixture_count <= max_fixture_rows,
        "percent_metric_complete": len(pct_entries) == len(completed),
        "usd_metric_complete": len(usd_entries) == len(completed),
        "percent_cluster_pf_lb": bool(
            evaluation_permitted
            and percent_bootstrap
            and _safe_float(percent_bootstrap.get("pf_lb_5pct")) is not None
            and float(percent_bootstrap.get("pf_lb_5pct")) > min_pct_lb
        ),
        "usd_cluster_pf_lb": bool(
            evaluation_permitted
            and usd_bootstrap
            and _safe_float(usd_bootstrap.get("pf_lb_5pct")) is not None
            and float(usd_bootstrap.get("pf_lb_5pct")) > min_usd_lb
        ),
        "total_net_pnl_usd": bool(total_net_pnl_usd is not None and total_net_pnl_usd > min_total_usd),
    }
    criteria_met = bool(evaluation_permitted and all(checks.values()))
    if bar_meta.get("status") != "loaded":
        status = "forward_evidence_bar_contract_missing"
    elif not evaluation_permitted:
        status = "waiting_for_min_completed_forward_rows"
    elif criteria_met:
        status = "forward_evidence_bar_criteria_met_reporting_only"
    else:
        status = "forward_evidence_bar_criteria_not_met"
    return {
        "status": status,
        "bar_contract": bar_meta,
        "bar_id": bar_contract.get("bar_id"),
        "approval_authority": False,
        "accepted_profitability": False,
        "can_change_scanner_policy": False,
        "evaluation_permitted": evaluation_permitted,
        "evaluation_waits_for_min_completed_rows": bool(
            requirements.get("evaluation_may_not_occur_before_min_completed_rows", True)
        ),
        "completed_forward_rows": len(completed),
        "required_completed_forward_rows": min_rows,
        "ticker_week_cluster_count": len(clusters),
        "required_ticker_week_clusters": min_clusters,
        "calendar_month_count": len(months),
        "required_calendar_months": min_months,
        "fixture_row_count": fixture_count,
        "max_fixture_rows": max_fixture_rows,
        "percent_metric_row_count": len(pct_entries),
        "usd_metric_row_count": len(usd_entries),
        "total_net_pnl_usd": total_net_pnl_usd,
        "percent_cluster_bootstrap": percent_bootstrap,
        "usd_cluster_bootstrap": usd_bootstrap,
        "checks": checks,
        "criteria_met_reporting_only": criteria_met,
    }


def _parity_disclosure(scan_task_health: dict[str, Any], scan_task_meta: dict[str, Any]) -> dict[str, Any]:
    monthly_upper_bound = HISTORICAL_FILTERED_MATERIALIZER_ROW_COUNT / HISTORICAL_FILTERED_MATERIALIZER_MONTH_COUNT
    return {
        "historical_materializer_entry_window_et": "10:10-10:25",
        "historical_materializer": "deterministic_local_pit_candidate_materializer_v1",
        "forward_source": "production_scan_sessions",
        "forward_scheduled_session_times": _scheduled_session_times(scan_task_health),
        "scan_task_health": scan_task_meta,
        "additional_forward_scanner_gates": [
            "momentum",
            "tech_score",
            "history_or_liquidity",
            "option_liquidity",
            "portfolio_and_profitability_gates",
        ],
        "forward_results_are_new_distribution": True,
        "not_continuation_of_historical_audit_sample": True,
        "historical_filtered_materializer_rows": HISTORICAL_FILTERED_MATERIALIZER_ROW_COUNT,
        "historical_filtered_materializer_months": HISTORICAL_FILTERED_MATERIALIZER_MONTH_COUNT,
        "expected_match_rate_note": (
            "filtered materializer produced 306 rows / 24 months "
            f"(~{round(monthly_upper_bound)} per month upper bound before production scanner gates), "
            "so months of zero forward matches are expected and are not by themselves a tracker bug"
        ),
    }


def _entry_quote_source(row: dict[str, Any]) -> str:
    return _norm(
        row.get("entry_quote_source")
        or row.get("quote_source")
        or row.get("options_data_source")
        or _as_dict(row.get("entry_quote_snapshot")).get("quote_source")
        or _as_dict(row.get("entry_quote_snapshot")).get("options_data_source")
    )


def _entry_quote_timestamp(row: dict[str, Any]) -> str:
    return _norm(
        row.get("entry_quote_timestamp_utc")
        or row.get("quote_timestamp_utc")
        or row.get("quote_time_utc")
        or _as_dict(row.get("entry_quote_snapshot")).get("quote_timestamp_utc")
        or _as_dict(row.get("entry_quote_snapshot")).get("captured_at_utc")
    )


def _entry_leg_prices(row: dict[str, Any]) -> tuple[float | None, float | None, float | None, float | None]:
    liquidity = _as_dict(row.get("spread_liquidity"))
    snapshot = _as_dict(row.get("entry_quote_snapshot"))
    return (
        _safe_float(_field_from_row(row, ("long_bid", "spread_liquidity.long_bid", "entry_quote_snapshot.long_bid"))),
        _safe_float(_field_from_row(row, ("long_ask", "spread_liquidity.long_ask", "entry_quote_snapshot.long_ask"))),
        _safe_float(_field_from_row(row, ("short_bid", "spread_liquidity.short_bid", "entry_quote_snapshot.short_bid"))),
        _safe_float(_field_from_row(row, ("short_ask", "spread_liquidity.short_ask", "entry_quote_snapshot.short_ask"))),
    )


def _entry_provenance(row: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    reasons: list[str] = []
    long_contract = _norm(row.get("long_contract_symbol") or row.get("contract_symbol"))
    short_contract = _norm(row.get("short_contract_symbol"))
    quote_source = _entry_quote_source(row)
    quote_timestamp = _entry_quote_timestamp(row)
    expiry = _norm(row.get("expiry") or row.get("expiration") or row.get("resolved_listed_expiry"))[:10]
    dte = _safe_float(row.get("dte"))
    long_bid, long_ask, short_bid, short_ask = _entry_leg_prices(row)
    if not long_contract:
        reasons.append("missing_long_contract_symbol")
    if not short_contract:
        reasons.append("missing_short_contract_symbol")
    if not quote_source:
        reasons.append("missing_entry_quote_source")
    elif _norm_lower(quote_source) not in TRUSTED_EXECUTABLE_QUOTE_SOURCES:
        reasons.append("untrusted_entry_quote_source")
    if not quote_timestamp:
        reasons.append("missing_entry_quote_timestamp")
    if not expiry:
        reasons.append("missing_expiry")
    if dte is None:
        reasons.append("missing_dte")
    if long_ask is None:
        reasons.append("missing_entry_long_ask")
    if short_bid is None:
        reasons.append("missing_entry_short_bid")
    entry_debit = round(float(long_ask) - float(short_bid), 4) if long_ask is not None and short_bid is not None else None
    if entry_debit is not None and entry_debit <= 0:
        reasons.append("non_positive_entry_debit")
    return (
        {
            "long_contract_symbol": long_contract,
            "short_contract_symbol": short_contract,
            "entry_quote_source": quote_source,
            "entry_quote_timestamp_utc": quote_timestamp,
            "entry_long_bid": long_bid,
            "entry_long_ask": long_ask,
            "entry_short_bid": short_bid,
            "entry_short_ask": short_ask,
            "entry_debit": entry_debit,
            "entry_debit_basis": "long_ask_minus_short_bid",
            "expiry": expiry,
            "dte": int(dte) if dte is not None else None,
        },
        reasons,
    )


def _paper_shadow_row(row: dict[str, Any], *, tracking_start_date: str, tracking_start_at_utc: str) -> dict[str, Any]:
    signal = _as_dict(row.get("signal_evidence"))
    tracking_state = _norm(row.get("tracking_state")) or "forward_paper_shadow_open"
    if not tracking_state.startswith("forward_paper_shadow_"):
        tracking_state = "forward_paper_shadow_open"
    return {
        **_candidate_identity_payload(row),
        "tracking_policy_id": POLICY_ID,
        "tracking_start_date": tracking_start_date,
        "tracking_start_at_utc": tracking_start_at_utc,
        "tracking_state": tracking_state,
        "evidence_bucket": "forward_paper_shadow",
        "scan_date": _candidate_date(row),
        "policy_exit_date": row.get("policy_exit_date") or _policy_exit_date(row),
        "exit_date": row.get("exit_date"),
        "ticker": _norm(row.get("ticker") or row.get("symbol")).upper(),
        "lane_id": _norm(row.get("lane_id") or row.get("playbook_id") or row.get("lane")),
        "direction": _candidate_direction(row),
        "strategy_type": row.get("strategy_type"),
        "expiry": row.get("expiry") or row.get("expiration") or row.get("resolved_listed_expiry"),
        "dte": row.get("dte"),
        "long_contract_symbol": row.get("long_contract_symbol") or row.get("contract_symbol"),
        "short_contract_symbol": row.get("short_contract_symbol"),
        "long_strike": row.get("long_strike"),
        "short_strike": row.get("short_strike"),
        "spread_width": row.get("spread_width"),
        "net_debit": row.get("net_debit") or row.get("entry_execution_price"),
        "debit_pct_of_width": row.get("debit_pct_of_width"),
        "underlying_price": row.get("underlying_price"),
        "prior_20_trading_day_return_pct": signal.get("prior_20_trading_day_return_pct"),
        "prior_20_trading_day_return_source": signal.get("prior_20_trading_day_return_source"),
        "entry_quote_source": row.get("entry_quote_source") or row.get("quote_source") or row.get("options_data_source"),
        "entry_quote_timestamp_utc": row.get("entry_quote_timestamp_utc") or row.get("quote_timestamp_utc") or row.get("quote_time_utc"),
        "planned_exit_status": row.get("planned_exit_status") or "waiting_policy_exit",
        "realized_pnl_status": row.get("realized_pnl_status") or "open_no_exit_yet",
        "net_pnl_pct": row.get("net_pnl_pct", row.get("pnl_pct")),
        "net_pnl_usd": row.get("net_pnl_usd"),
        "source_scan_run_id": row.get("scanner_run_id") or row.get("scan_run_id"),
        "source_logged_at": row.get("logged_at"),
        "source_row": row,
        "live_trade": False,
        "paper_broker_order": False,
        "broker_order_allowed": False,
        "auto_track_allowed": False,
        "scanner_policy_changed": False,
    }


def _matched_entry_log_row(row: dict[str, Any], *, tracking_start_date: str, tracking_start_at_utc: str) -> tuple[dict[str, Any], list[str]]:
    base = _paper_shadow_row(row, tracking_start_date=tracking_start_date, tracking_start_at_utc=tracking_start_at_utc)
    provenance, reasons = _entry_provenance(row)
    base.update(provenance)
    base.update(
        {
            "schema_version": 1,
            "record_type": "matched_entry",
            "lifecycle_event": "matched_entry",
            "append_only_log": True,
            "candidate_source_mode": "real_market_window_scan_picks",
            "fixture_mode": False,
            "contract_multiplier": CONTRACT_MULTIPLIER,
            "fee_per_contract_leg_usd": DEFAULT_FEE_PER_CONTRACT_LEG_USD,
        }
    )
    return base, reasons


def _merge_lifecycle_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    by_candidate: dict[str, dict[str, Any]] = {}
    for row in rows:
        candidate_id = _norm(row.get("candidate_id"))
        if not candidate_id:
            continue
        current = by_candidate.get(candidate_id)
        if current is None or (_is_completed_forward_row(row) and not _is_completed_forward_row(current)):
            by_candidate[candidate_id] = dict(row)
    return sorted(
        by_candidate.values(),
        key=lambda row: (
            str(row.get("identity_scan_date") or row.get("scan_date")),
            str(row.get("identity_ticker") or row.get("ticker")),
            str(row.get("identity_direction") or row.get("direction")),
            str(row.get("candidate_id")),
        ),
    )


def _append_jsonl_rows(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), sort_keys=True, separators=(",", ":")) + "\n")


def _conditions_text(conditions: Sequence[Any]) -> str:
    chunks = []
    for condition in conditions:
        condition = _as_dict(condition)
        value = condition.get("value")
        if isinstance(value, list):
            value = ",".join(str(item) for item in value)
        chunks.append(f"{condition.get('field')} {condition.get('op')} {value}")
    return "; ".join(chunks) if chunks else "none"


def build_report(
    *,
    policy_contract_path: Path = DEFAULT_POLICY_CONTRACT,
    filtered_audit_path: Path = DEFAULT_FILTERED_AUDIT,
    source_scan_picks_path: Path = DEFAULT_SOURCE_SCAN_PICKS,
    underlying_daily_source_rows_path: Path = DEFAULT_UNDERLYING_DAILY_SOURCE_ROWS,
    matched_rows_log_path: Path = DEFAULT_MATCHED_ROWS_LOG,
    forward_evidence_bar_contract_path: Path = DEFAULT_FORWARD_EVIDENCE_BAR_CONTRACT,
    scan_task_health_path: Path = DEFAULT_SCAN_TASK_HEALTH,
    tracking_start_date: str | None = None,
    tracking_start_at_utc: str | None = None,
    previous_tracker_dir: Path | None = None,
    generated_at_utc: str | None = None,
    append_matched_rows: bool = False,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    policy_contract, policy_contract_meta = _load_policy_contract(policy_contract_path)
    bar_contract, bar_meta = _load_optional_json(forward_evidence_bar_contract_path)
    scan_task_health, scan_task_meta = _load_optional_json(scan_task_health_path)
    filtered_audit, filtered_meta = _load_json(filtered_audit_path)
    scan_rows, scan_meta = _load_jsonl(source_scan_picks_path)
    matched_log_rows, matched_log_meta = _load_jsonl(matched_rows_log_path)
    daily_rows, daily_meta = _load_jsonl(underlying_daily_source_rows_path)
    source_index = _source_row_index(daily_rows)
    filter_source = _as_dict(filtered_audit.get("filter_source"))
    contract_conditions = _as_list(policy_contract.get("conditions"))
    conditions = contract_conditions
    expected_conditions_hash = _norm(policy_contract.get("conditions_sha256"))
    computed_conditions_hash = _conditions_sha256(contract_conditions) if contract_conditions else ""
    latest_audit_conditions = _as_list(filter_source.get("conditions"))
    if filtered_meta.get("status") != "loaded":
        policy_drift_status = "latest_filtered_audit_unavailable"
    elif latest_audit_conditions != contract_conditions:
        policy_drift_status = "latest_filtered_audit_diverged_from_frozen_contract"
    else:
        policy_drift_status = "latest_filtered_audit_matches_frozen_contract"
    prior_start_at = _stable_tracking_start_at(previous_tracker_dir) if previous_tracker_dir else None
    contract_start_at = _norm(policy_contract.get("tracking_start_at_utc"))
    start_at = _norm(
        contract_start_at
        or tracking_start_at_utc
        or prior_start_at
        or filtered_audit.get("generated_at_utc")
        or filtered_audit.get("completed_at_utc")
        or generated_at
    )
    start_source = (
        "frozen_policy_contract"
        if contract_start_at
        else "explicit_tracking_start_at_utc"
        if tracking_start_at_utc
        else "previous_tracker_artifacts"
        if prior_start_at
        else "filtered_audit_timestamp"
    )
    start_date = _norm(start_at if contract_start_at else tracking_start_date or start_at)[:10]

    blockers: list[str] = []
    if policy_contract_meta.get("status") != "loaded":
        blockers.append("frozen_filtered_policy_contract_missing")
    if not conditions:
        blockers.append("frozen_filtered_policy_conditions_missing")
    if expected_conditions_hash and computed_conditions_hash and expected_conditions_hash != computed_conditions_hash:
        blockers.append("frozen_filtered_policy_hash_mismatch")
    elif conditions and not expected_conditions_hash:
        blockers.append("frozen_filtered_policy_hash_missing")
    if scan_meta.get("status") != "loaded":
        blockers.append("scan_picks_not_loaded")
    matched_log_duplicates = _matched_log_duplicate_daily_signal_identities(matched_log_rows)
    matched_log_identity_schema_current = _matched_log_has_current_identity_schema(matched_log_rows)
    if matched_log_rows and not matched_log_identity_schema_current:
        blockers.append("matched_rows_log_nonempty_before_daily_signal_identity_upgrade")
    if matched_log_duplicates:
        blockers.append("duplicate_ticker_date_direction_matched_rows")

    enriched_rows: list[dict[str, Any]] = []
    rejected_counts: Counter[str] = Counter()
    if not blockers:
        for row in scan_rows:
            enriched, reject_reason = _scan_row_for_filter(row, source_index)
            if reject_reason:
                rejected_counts[reject_reason] += 1
                continue
            scan_date = _candidate_date(enriched)
            if start_date and scan_date < start_date:
                rejected_counts["pre_tracking_start_date"] += 1
                continue
            if start_at and scan_date == start_date:
                scan_timestamp = _candidate_timestamp(enriched)
                if not scan_timestamp:
                    rejected_counts["missing_post_tracking_timestamp"] += 1
                    continue
                if scan_timestamp < start_at:
                    rejected_counts["pre_tracking_start_timestamp"] += 1
                    continue
            enriched_rows.append(enriched)
    raw_matched = _filter_rows(enriched_rows, {"conditions": conditions}) if conditions and not blockers else []
    matched, match_dedupe_counts = _first_daily_signal_matches(raw_matched)
    existing_candidate_ids = {_norm(row.get("candidate_id")) for row in matched_log_rows if _norm(row.get("candidate_id"))}
    appendable_entries: list[dict[str, Any]] = []
    unappendable_rows: list[dict[str, Any]] = []
    unappendable_counts: Counter[str] = Counter()
    for row in matched:
        entry, reasons = _matched_entry_log_row(row, tracking_start_date=start_date, tracking_start_at_utc=start_at)
        if reasons:
            for reason in reasons:
                unappendable_counts[reason] += 1
            unappendable_rows.append(
                {
                    "candidate_id": entry.get("candidate_id"),
                    "scan_date": entry.get("scan_date"),
                    "ticker": entry.get("ticker"),
                    "status": "matched_but_unappendable_missing_entry_provenance",
                    "missing_entry_provenance_reasons": reasons,
                }
            )
            continue
        if _norm(entry.get("candidate_id")) not in existing_candidate_ids:
            appendable_entries.append(entry)
    if append_matched_rows:
        matched_rows_log_path.parent.mkdir(parents=True, exist_ok=True)
        matched_rows_log_path.touch(exist_ok=True)
        _append_jsonl_rows(matched_rows_log_path, appendable_entries)
        matched_log_rows = [*matched_log_rows, *appendable_entries]
        matched_log_meta = {
            **matched_log_meta,
            "exists": True,
            "status": "loaded" if matched_log_meta.get("status") in {"loaded", "missing"} else matched_log_meta.get("status"),
            "row_count": int(matched_log_meta.get("row_count") or 0) + len(appendable_entries),
        }
    merged_source_rows = [*matched_log_rows, *([] if append_matched_rows else appendable_entries)]
    paper_shadow_rows = _merge_lifecycle_rows(merged_source_rows)
    by_state = Counter(str(row.get("tracking_state")) for row in paper_shadow_rows)
    by_ticker = Counter(str(row.get("ticker")) for row in paper_shadow_rows)
    by_date = Counter(str(row.get("scan_date")) for row in paper_shadow_rows)
    historical_metrics = _as_dict(filtered_audit.get("metrics"))
    audit_metrics = _as_dict(historical_metrics.get("simulated_forward_audit"))
    audit_bootstrap = _as_dict(audit_metrics.get("bootstrap_cluster") or audit_metrics.get("bootstrap"))
    forward_evidence_bar = _forward_evidence_bar_progress(
        paper_shadow_rows,
        bar_contract=bar_contract,
        bar_meta=bar_meta,
    )
    parity_disclosure = _parity_disclosure(scan_task_health, scan_task_meta)
    status = "filtered_forward_paper_shadow_tracking_active" if not blockers else "blocked_filtered_forward_paper_shadow_tracker"
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at,
        "schema_version": 1,
        "read_only": True,
        "tracking_policy_id": POLICY_ID,
        "tracking_start_date": start_date,
        "tracking_start_at_utc": start_at,
        "tracking_start_source": start_source,
        "tracking_label": "Historical filtered candidate v1 forward paper-shadow tracker",
        "inputs": {
            "policy_contract": policy_contract_meta,
            "forward_evidence_bar_contract": bar_meta,
            "scan_task_health": scan_task_meta,
            "filtered_audit": filtered_meta,
            "source_scan_picks": {**scan_meta, "sha256": _file_hash(source_scan_picks_path)},
            "matched_rows_log": {**matched_log_meta, "sha256": _file_hash(matched_rows_log_path)},
            "underlying_daily_source_rows": daily_meta,
        },
        "frozen_filter": {
            "source": "frozen_policy_contract",
            "contract_path": policy_contract_meta.get("path"),
            "contract_sha256": policy_contract_meta.get("sha256"),
            "policy_id": policy_contract.get("policy_id") or POLICY_ID,
            "filter_id": policy_contract.get("filter_id"),
            "description": policy_contract.get("description"),
            "conditions": conditions,
            "conditions_sha256": expected_conditions_hash,
            "computed_conditions_sha256": computed_conditions_hash,
            "conditions_text": _conditions_text(conditions),
            "freeze_rule": "consume the hash-pinned frozen policy contract exactly; do not retune from filtered audit or forward rows",
        },
        "policy_drift_status": policy_drift_status,
        "latest_filtered_audit_filter": {
            "source_report_id": filter_source.get("source_report_id"),
            "source_status": filter_source.get("source_status"),
            "filter_id": filter_source.get("filter_id"),
            "conditions_sha256": _conditions_sha256(latest_audit_conditions) if latest_audit_conditions else None,
        },
        "historical_audit_context": {
            "status": filtered_audit.get("status"),
            "accepted_historical_filtered_audit": filtered_audit.get("accepted_historical_filtered_audit"),
            "accepted_profitability": filtered_audit.get("accepted_profitability"),
            "audit_exact_trade_count": audit_metrics.get("exact_trade_count"),
            "audit_profit_factor": audit_metrics.get("profit_factor"),
            "audit_avg_pnl_pct": audit_metrics.get("avg_pnl_pct"),
            "audit_pf_lb_5pct": audit_bootstrap.get("pf_lb_5pct"),
            "historical_rows_are_forward_proof": filtered_audit.get("historical_rows_are_forward_proof"),
        },
        "forward_tracking": {
            "tracking_start_date": start_date,
            "tracking_start_at_utc": start_at,
            "tracking_start_source": start_source,
            "source_scan_row_count": len(scan_rows),
            "evaluated_scan_row_count": len(enriched_rows),
            "matched_candidate_count": len(paper_shadow_rows),
            "open_candidate_count": by_state.get("forward_paper_shadow_open", 0),
            "completed_candidate_count": by_state.get("forward_paper_shadow_completed", 0),
            "appendable_entry_count": len(appendable_entries),
            "entry_rows_appended_count": len(appendable_entries) if append_matched_rows else 0,
            "raw_matched_scan_row_count": len(raw_matched),
            "daily_signal_matched_row_count": len(matched),
            "same_day_signal_duplicate_matches_suppressed_count": match_dedupe_counts[
                "duplicate_same_day_signal_matches_suppressed"
            ],
            "matched_but_unappendable_missing_entry_provenance_count": len(unappendable_rows),
            "matched_but_unappendable_counts": dict(sorted(unappendable_counts.items())),
            "matched_rows_log_identity_schema": MATCHED_ROW_IDENTITY_SCHEMA,
            "matched_rows_log_identity_schema_current": matched_log_identity_schema_current,
            "duplicate_daily_signal_identity_count": len(matched_log_duplicates),
            "by_ticker": dict(sorted(by_ticker.items())),
            "by_scan_date": dict(sorted(by_date.items())),
            "rejected_counts": dict(sorted(rejected_counts.items())),
        },
        "forward_evidence_bar": forward_evidence_bar,
        "parity_disclosure": parity_disclosure,
        "candidate_rows": paper_shadow_rows,
        "matched_but_unappendable_rows": unappendable_rows,
        "duplicate_daily_signal_identities": matched_log_duplicates,
        "blockers": blockers,
        "live_trade": False,
        "approval_authority": False,
        "accepted_profitability": False,
        "forward_rows_are_profitability_proof": False,
        "scanner_policy_changed": False,
        "live_validation_enabled": False,
        "auto_track_enabled": False,
        "broker_order_allowed": False,
        "quotes_imported": False,
        "evidence_stores_mutated": False,
        "protected_holdout_consumed": False,
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }


def render_markdown(report: dict[str, Any]) -> str:
    tracking = _as_dict(report.get("forward_tracking"))
    audit = _as_dict(report.get("historical_audit_context"))
    filt = _as_dict(report.get("frozen_filter"))
    bar = _as_dict(report.get("forward_evidence_bar"))
    parity = _as_dict(report.get("parity_disclosure"))
    lines = [
        "# Regular Options Filtered Forward Paper-Shadow Tracker",
        "",
        "This generated readback tracks prospective scan-pick rows that match the frozen historical filtered candidate policy. It is dashboard/reporting evidence, not broker execution.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Tracking policy: `{report.get('tracking_policy_id')}`.",
        f"- Tracking start date: `{tracking.get('tracking_start_date') or report.get('tracking_start_date')}`.",
        f"- Tracking start timestamp: `{tracking.get('tracking_start_at_utc') or report.get('tracking_start_at_utc')}`.",
        f"- Tracking start source: `{tracking.get('tracking_start_source') or report.get('tracking_start_source')}`.",
        f"- Filter: `{filt.get('filter_id')}`.",
        f"- Policy contract: `{filt.get('contract_path')}`.",
        f"- Policy drift status: `{report.get('policy_drift_status')}`.",
        f"- Conditions: {filt.get('conditions_text')}.",
        f"- Source scan rows: `{tracking.get('source_scan_row_count')}`.",
        f"- Evaluated scan rows: `{tracking.get('evaluated_scan_row_count')}`.",
        f"- Matched forward paper-shadow candidates: `{tracking.get('matched_candidate_count')}`.",
        f"- Open candidates: `{tracking.get('open_candidate_count')}`.",
        f"- Completed candidates: `{tracking.get('completed_candidate_count')}`.",
        f"- Entry rows appended: `{tracking.get('entry_rows_appended_count')}`.",
        f"- Matched but unappendable rows: `{tracking.get('matched_but_unappendable_missing_entry_provenance_count')}`.",
        f"- Matched-but-unappendable counts: `{json.dumps(tracking.get('matched_but_unappendable_counts') or {}, sort_keys=True)}`.",
        f"- Rejected counts: `{json.dumps(tracking.get('rejected_counts') or {}, sort_keys=True)}`.",
        f"- Forward evidence bar status: `{bar.get('status')}`.",
        "",
        "## Historical Context",
        "",
        f"- Historical filtered audit status: `{audit.get('status')}`.",
        f"- Latest-four historical audit rows: `{audit.get('audit_exact_trade_count')}`.",
        f"- Latest-four historical audit PF: `{audit.get('audit_profit_factor')}`.",
        f"- Latest-four historical audit PF LB 5%: `{audit.get('audit_pf_lb_5pct')}`.",
        f"- Historical rows are forward proof: `{audit.get('historical_rows_are_forward_proof')}`.",
        "",
        "## Forward Evidence Bar",
        "",
        f"- Bar ID: `{bar.get('bar_id')}`.",
        f"- Completed rows: `{bar.get('completed_forward_rows')}` / `{bar.get('required_completed_forward_rows')}`.",
        f"- Ticker-week clusters: `{bar.get('ticker_week_cluster_count')}` / `{bar.get('required_ticker_week_clusters')}`.",
        f"- Calendar months with rows: `{bar.get('calendar_month_count')}` / `{bar.get('required_calendar_months')}`.",
        f"- Fixture rows: `{bar.get('fixture_row_count')}` / max `{bar.get('max_fixture_rows')}`.",
        f"- Evaluation permitted: `{bar.get('evaluation_permitted')}`.",
        f"- Criteria met reporting-only: `{bar.get('criteria_met_reporting_only')}`.",
        f"- Approval authority: `{bar.get('approval_authority')}`.",
        f"- Percent cluster PF LB 5%: `{_as_dict(bar.get('percent_cluster_bootstrap')).get('pf_lb_5pct')}`.",
        f"- USD cluster PF LB 5%: `{_as_dict(bar.get('usd_cluster_bootstrap')).get('pf_lb_5pct')}`.",
        f"- Total net USD: `{bar.get('total_net_pnl_usd')}`.",
        "",
        "## Parity Disclosure",
        "",
        f"- Historical materializer entry window ET: `{parity.get('historical_materializer_entry_window_et')}`.",
        f"- Historical materializer: `{parity.get('historical_materializer')}`.",
        f"- Forward source: `{parity.get('forward_source')}`.",
        f"- Scheduled session times: `{json.dumps(parity.get('forward_scheduled_session_times') or {}, sort_keys=True)}`.",
        f"- Forward results are a new distribution: `{parity.get('forward_results_are_new_distribution')}`.",
        f"- Expected match-rate note: {parity.get('expected_match_rate_note')}.",
        "",
        "## Candidate Rows",
        "",
        "| Scan Date | Ticker | Lane | Strategy | Expiry | Prior 20% | State |",
        "|---|---|---|---|---|---:|---|",
    ]
    for row in _as_list(report.get("candidate_rows"))[:50]:
        row = _as_dict(row)
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("scan_date") or ""),
                    str(row.get("ticker") or ""),
                    str(row.get("lane_id") or ""),
                    str(row.get("strategy_type") or ""),
                    str(row.get("expiry") or ""),
                    str(row.get("prior_20_trading_day_return_pct") or ""),
                    f"`{row.get('tracking_state')}`",
                ]
            )
            + " |"
        )
    blockers = _as_list(report.get("blockers"))
    if blockers:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "Rows here are forward paper-shadow tracking rows for dashboard/reporting. They are not live trades, Alpaca paper orders, scanner-policy approval, promotion, quote import, evidence mutation, protected-holdout use, or proof-bar changes.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    candidates_jsonl: Path = DEFAULT_CANDIDATES_JSONL,
    matched_rows_log: Path = DEFAULT_MATCHED_ROWS_LOG,
    docs_report: Path = DEFAULT_DOCS_REPORT,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates_jsonl.parent.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    artifacts = {
        "json": _rel(json_path),
        "latest_json": _rel(latest_json),
        "markdown": _rel(md_path),
        "latest_markdown": _rel(latest_md),
        "candidate_rows_jsonl": _rel(candidates_jsonl),
        "matched_rows_log": _rel(matched_rows_log),
        "docs_report": _rel(docs_report),
    }
    report["artifacts"] = artifacts
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(report) + "\n"
    rows = _as_list(report.get("candidate_rows"))
    jsonl = "".join(json.dumps(_as_dict(row), sort_keys=True, separators=(",", ":")) + "\n" for row in rows)
    json_path.write_text(payload, encoding="utf8")
    latest_json.write_text(payload, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    candidates_jsonl.write_text(jsonl, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return artifacts


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Track forward paper-shadow candidates for the frozen filtered policy.")
    parser.add_argument("--policy-contract", type=Path, default=DEFAULT_POLICY_CONTRACT)
    parser.add_argument("--forward-evidence-bar-contract", type=Path, default=DEFAULT_FORWARD_EVIDENCE_BAR_CONTRACT)
    parser.add_argument("--scan-task-health", type=Path, default=DEFAULT_SCAN_TASK_HEALTH)
    parser.add_argument("--filtered-audit", type=Path, default=DEFAULT_FILTERED_AUDIT)
    parser.add_argument("--source-scan-picks", type=Path, default=DEFAULT_SOURCE_SCAN_PICKS)
    parser.add_argument("--underlying-daily-source-rows", type=Path, default=DEFAULT_UNDERLYING_DAILY_SOURCE_ROWS)
    parser.add_argument("--matched-rows-log", type=Path, default=DEFAULT_MATCHED_ROWS_LOG)
    parser.add_argument("--tracking-start-date", default=None)
    parser.add_argument("--tracking-start-at-utc", default=None)
    parser.add_argument("--previous-tracker-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--candidate-rows-jsonl", type=Path, default=DEFAULT_CANDIDATES_JSONL)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(list(argv))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(
        policy_contract_path=args.policy_contract,
        forward_evidence_bar_contract_path=args.forward_evidence_bar_contract,
        scan_task_health_path=args.scan_task_health,
        filtered_audit_path=args.filtered_audit,
        source_scan_picks_path=args.source_scan_picks,
        underlying_daily_source_rows_path=args.underlying_daily_source_rows,
        matched_rows_log_path=args.matched_rows_log,
        tracking_start_date=args.tracking_start_date,
        tracking_start_at_utc=args.tracking_start_at_utc,
        previous_tracker_dir=args.previous_tracker_dir or args.output_dir,
        append_matched_rows=not args.no_write,
    )
    if not args.no_write:
        write_outputs(
            report,
            output_dir=args.output_dir,
            candidates_jsonl=args.candidate_rows_jsonl,
            matched_rows_log=args.matched_rows_log,
            docs_report=args.docs_report,
        )
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
