from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_existing_input_surface_atlas"
ATLAS_ID = "existing_repository_point_in_time_input_surface_atlas_v1"
DEFAULT_DB = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-existing-input-surface-atlas"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-existing-input-surface-atlas.md"

CONTROL_ARTIFACTS = {
    "oracle_packet": ROOT / "data" / "forward-tracking" / "options_oracle_profit_loop_packet_latest.json",
    "all_local_quote_atlas": ROOT / "data" / "profitability-lab" / "regular-options-all-local-quote-minute-structure-capability-atlas" / "latest.json",
    "local_quote_matrix": ROOT / "data" / "profitability-lab" / "regular-options-local-quote-structure-capability-matrix" / "latest.json",
    "opening_replay": ROOT / "data" / "profitability-lab" / "regular-options-quote-surface-opening-range-reversal-replay" / "latest.json",
    "synthetic_forward": ROOT / "data" / "profitability-lab" / "regular-options-quote-derived-synthetic-forward-surface" / "latest.json",
    "vix_bucket": ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-vix-bucket" / "latest.json",
    "flow_input": ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-flow-extreme-input" / "latest.json",
    "flow_volume_oi": ROOT / "data" / "profitability-lab" / "regular-options-flow-extreme-volume-oi-source-rows" / "latest.json",
    "macro_event_calendar": ROOT / "data" / "profitability-lab" / "regular-options-macro-event-calendar" / "latest.json",
    "dispersion_proxy": ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-dispersion-concentration-proxy" / "latest.json",
    "pmcc_readiness": ROOT / "data" / "profitability-lab" / "regular-options-pmcc-diagonal-replay-readiness" / "latest.json",
    "base_ledger": ROOT / "data" / "profitability-lab" / "regular-options-base-clean-stack-identity-ledger" / "latest.json",
    "forward_holdout": ROOT / "data" / "contracts" / "forward-holdout-contract.json",
    "forward_cohort": ROOT / "data" / "contracts" / "forward-cohort-preregistration.json",
    "source_quality_policy": ROOT / "data" / "contracts" / "regular-options-source-quality-scope-policy.json",
}

INPUT_FAMILY_ORDER = (
    "underlying_or_opening_bucket",
    "trend_or_regime",
    "direct_vix_or_volatility_regime",
    "option_iv_proxy_volatility_regime",
    "flow_or_liquidity_pressure",
    "volume_open_interest",
    "macro_event_calendar",
    "earnings_event_calendar",
    "term_structure_or_skew",
    "dispersion_or_concentration_proxy",
    "candidate_generation_diagnostics",
    "fresh_forward_collection_readiness",
)

READ_ONLY_FLAGS = {
    "read_only": True,
    "no_write": True,
    "accepted_profitability": False,
    "historical_rows_are_forward_proof": False,
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
    "p_l_replay_performed": False,
    "realized_pnl_used_for_ranking": False,
}

FORBIDDEN_ACTIONS = (
    "broker orders",
    "live validation",
    "auto-track",
    "production scanner release",
    "production strategy changes",
    "stop or sizing changes",
    "proof-bar relaxation",
    "quote import",
    "evidence database mutation",
    "protected holdout consumption",
    "promotion",
    "historical rows as forward proof",
    "creating trades",
    "preparing orders",
    "forward cohort append",
    "P&L replay",
    "ranking source surfaces by realized profitability",
    "using midpoint, stale, EOD, display-only, last-trade, model, manual, synthetic, or non-executable marks as fill or P&L evidence",
    "reclassifying zero-bid or untradable rows as missing data",
    "relabeling proxies as direct VIX, flow, event, or underlying-price proof",
)

TRUSTED_BATCH_SQL = "q.source_batch_id IN (SELECT id FROM import_batches WHERE data_trust = 'trusted')"


@dataclass(frozen=True)
class DateWindow:
    start_date: str
    end_date: str
    latest_four_months: tuple[str, ...]
    requested_dates: tuple[str, ...]
    train_months: tuple[str, ...]


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


def _connect_read_only(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def _read_only_confirmed(conn: sqlite3.Connection) -> bool:
    try:
        return int(conn.execute("PRAGMA query_only").fetchone()[0]) == 1
    except (sqlite3.Error, TypeError, IndexError):
        return False


def _load_json(path: Path, *, required: bool) -> tuple[dict[str, Any], dict[str, Any]]:
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
    if not isinstance(payload, dict):
        meta["status"] = "invalid"
        meta["error"] = "expected_json_object"
        return {}, meta
    meta["status"] = "loaded"
    meta["report_id"] = payload.get("report_id") or payload.get("contract_id") or payload.get("policy_id")
    meta["status_value"] = payload.get("status")
    meta["generated_at_utc"] = payload.get("generated_at_utc")
    return payload, meta


def _month_iter(start_month: str, end_month: str) -> list[str]:
    year, month = [int(part) for part in start_month.split("-")]
    end_year, end_m = [int(part) for part in end_month.split("-")]
    months: list[str] = []
    while (year, month) <= (end_year, end_m):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year += 1
            month = 1
    return months


def _business_dates(start: str, end: str) -> list[str]:
    current = date.fromisoformat(start)
    final = date.fromisoformat(end)
    dates: list[str] = []
    while current <= final:
        if current.weekday() < 5:
            dates.append(current.isoformat())
        current += timedelta(days=1)
    return dates


def _window(start_date: str, end_date: str, latest_four_months: tuple[str, ...]) -> DateWindow:
    requested_dates = tuple(_business_dates(start_date, end_date))
    all_months = _month_iter(start_date[:7], end_date[:7])
    train_months = tuple(month for month in all_months if month not in set(latest_four_months))
    return DateWindow(start_date, end_date, latest_four_months, requested_dates, train_months)


def _coverage(covered_dates: set[str], window: DateWindow) -> dict[str, Any]:
    requested = set(window.requested_dates)
    latest_dates = {day for day in requested if day[:7] in set(window.latest_four_months)}
    in_range = {day for day in covered_dates if day in requested}
    latest = {day for day in in_range if day[:7] in set(window.latest_four_months)}
    months = sorted({day[:7] for day in in_range})
    return {
        "covered_months": months,
        "train_months_covered": len({month for month in months if month in set(window.train_months)}),
        "latest_four_months_covered": len({month for month in months if month in set(window.latest_four_months)}),
        "covered_date_count": len(in_range),
        "latest_four_covered_date_count": len(latest),
        "date_coverage_pct": round((len(in_range) / len(requested) * 100.0) if requested else 0.0, 2),
        "latest_four_date_coverage_pct": round((len(latest) / len(latest_dates) * 100.0) if latest_dates else 0.0, 2),
    }


def _known_at_safe(row: dict[str, Any]) -> bool:
    known = row.get("known_at_utc") or row.get("as_of_utc") or row.get("tradable_after_utc") or row.get("source_timestamp_utc")
    event_time = row.get("event_timestamp_utc") or row.get("candidate_entry_timestamp_utc")
    if not known:
        return False
    try:
        known_dt = datetime.fromisoformat(str(known).replace("Z", "+00:00"))
    except ValueError:
        return False
    if event_time:
        try:
            event_dt = datetime.fromisoformat(str(event_time).replace("Z", "+00:00"))
        except ValueError:
            return False
        if known_dt > event_dt:
            return False
    return True


def _source_type_for_path(path: Path) -> str:
    lowered = _rel(path).lower()
    if lowered.startswith("docs/") or "/docs/" in lowered:
        return "docs_only"
    if any(token in lowered for token in ("import", "repair", "mutation")):
        return "approval_required_import"
    if any(token in lowered for token in ("vix", "macro-event", "earnings", "event-calendar")):
        return "direct_market_source"
    if any(token in lowered for token in ("iv", "proxy", "dispersion", "term-structure", "skew")):
        return "derived_point_in_time_proxy"
    if any(token in lowered for token in ("diagnostic", "readiness", "audit", "packet", "contract")):
        return "diagnostic_only"
    return "diagnostic_only"


def _candidate_ready(row: dict[str, Any]) -> bool:
    if row.get("approval_required"):
        return False
    if row.get("input_family") == "fresh_forward_collection_readiness":
        return False
    if row.get("source_type") not in {"direct_market_source", "derived_point_in_time_proxy"}:
        return False
    if row.get("source_type") == "derived_point_in_time_proxy":
        direct_blockers = {"direct_vix_or_volatility_regime", "flow_or_liquidity_pressure", "macro_event_calendar", "earnings_event_calendar"}
        if row.get("input_family") in direct_blockers:
            return False
    gates = (
        row.get("required_fields_present") is True,
        row.get("known_at_safe") is True,
        int(row.get("leakage_reject_count") or 0) == 0,
        int(row.get("protected_holdout_overlap_rows") or 0) == 0,
        int(row.get("train_months_covered") or 0) >= 20,
        int(row.get("latest_four_months_covered") or 0) == 4,
        float(row.get("date_coverage_pct") or 0.0) >= 90.0,
        float(row.get("latest_four_date_coverage_pct") or 0.0) >= 90.0,
    )
    if not all(gates):
        return False
    return "already_parked_quote_surface_only" not in _as_list(row.get("remaining_blockers"))


def _row_blockers(row: dict[str, Any]) -> list[str]:
    blockers = list(_as_list(row.get("remaining_blockers")))
    if row.get("approval_required"):
        blockers.append("approval_required")
    if row.get("required_fields_present") is not True:
        blockers.append("missing_required_fields")
    if row.get("known_at_safe") is not True:
        blockers.append("missing_or_unsafe_known_at")
    if int(row.get("leakage_reject_count") or 0) > 0:
        blockers.append("leakage_rejects_present")
    if int(row.get("protected_holdout_overlap_rows") or 0) > 0:
        blockers.append("protected_holdout_overlap")
    if int(row.get("train_months_covered") or 0) < 20:
        blockers.append("train_months_below_20")
    if int(row.get("latest_four_months_covered") or 0) < 4:
        blockers.append("latest_four_months_below_4")
    if float(row.get("date_coverage_pct") or 0.0) < 90.0:
        blockers.append("date_coverage_below_90")
    if float(row.get("latest_four_date_coverage_pct") or 0.0) < 90.0:
        blockers.append("latest_four_date_coverage_below_90")
    if row.get("source_type") == "docs_only":
        blockers.append("docs_only_evidence")
    if row.get("source_type") == "missing":
        blockers.append("source_missing")
    if row.get("source_type") == "derived_point_in_time_proxy" and row.get("input_family") in {
        "direct_vix_or_volatility_regime",
        "flow_or_liquidity_pressure",
        "macro_event_calendar",
        "earnings_event_calendar",
    }:
        blockers.append("proxy_cannot_clear_direct_source_blocker")
    return sorted(set(str(blocker) for blocker in blockers if blocker))


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except sqlite3.Error:
        return set()


def _db_field_candidate(
    conn: sqlite3.Connection,
    *,
    input_family: str,
    field_names: tuple[str, ...],
    source_type: str,
    surface_id: str,
    source_path: str,
    window: DateWindow,
    extra_blockers: tuple[str, ...] = (),
    next_safe_branch: str | None = None,
) -> dict[str, Any]:
    columns = _table_columns(conn, "option_quote_snapshots")
    required = {"quote_date_et", "as_of_utc", "underlying", *field_names}
    required_present = required.issubset(columns)
    covered_dates: set[str] = set()
    usable_rows = 0
    if required_present:
        predicates = " AND ".join([f"q.{field} IS NOT NULL" for field in field_names])
        try:
            rows = conn.execute(
                f"""
                SELECT q.quote_date_et AS quote_date, COUNT(*) AS rows
                FROM option_quote_snapshots q
                WHERE q.quote_date_et BETWEEN ? AND ?
                  AND {TRUSTED_BATCH_SQL}
                  AND {predicates}
                GROUP BY q.quote_date_et
                """,
                (window.start_date, window.end_date),
            ).fetchall()
            for row in rows:
                covered_dates.add(str(row["quote_date"]))
                usable_rows += int(row["rows"] or 0)
        except sqlite3.Error:
            required_present = False
    cov = _coverage(covered_dates, window)
    row = {
        "surface_id": surface_id,
        "input_family": input_family,
        "source_type": source_type if usable_rows else "missing",
        "source_path": source_path,
        "required_fields_present": bool(required_present and usable_rows),
        "known_at_safe": bool(required_present and "as_of_utc" in columns and usable_rows),
        "leakage_reject_count": 0,
        "protected_holdout_overlap_rows": 0,
        "usable_row_count": usable_rows,
        "approval_required": False,
        "clears_blockers": [],
        "remaining_blockers": list(extra_blockers),
        "next_safe_branch": next_safe_branch,
        **cov,
    }
    row["remaining_blockers"] = _row_blockers(row)
    return row


def _artifact_candidate(
    *,
    input_family: str,
    surface_id: str,
    path: Path,
    payload: dict[str, Any],
    window: DateWindow,
    source_type: str | None = None,
    blockers: tuple[str, ...] = (),
    approval_required: bool = False,
) -> dict[str, Any]:
    coverage_obj = _as_dict(payload.get("coverage"))
    covered_months = {str(month) for month in _as_list(coverage_obj.get("covered_months"))}
    covered_dates = {str(day) for day in _as_list(coverage_obj.get("covered_dates")) if str(day) in set(window.requested_dates)}
    if not covered_dates and covered_months:
        for day in window.requested_dates:
            if day[:7] in covered_months:
                covered_dates.add(day)
    cov = _coverage(covered_dates, window)
    required_fields_present = bool(coverage_obj) and not _as_list(payload.get("blockers"))
    source = source_type or _source_type_for_path(path)
    if not path.exists():
        source = "missing"
    row = {
        "surface_id": surface_id,
        "input_family": input_family,
        "source_type": source,
        "source_path": _rel(path),
        "required_fields_present": required_fields_present,
        "known_at_safe": required_fields_present and bool(payload.get("point_in_time_valid") or "point_in_time" in str(payload.get("status", ""))),
        "leakage_reject_count": int(payload.get("leakage_reject_count") or 0),
        "protected_holdout_overlap_rows": int(payload.get("protected_holdout_overlap_rows") or payload.get("holdout_overlap_count") or 0),
        "usable_row_count": int(coverage_obj.get("covered_date_count") or payload.get("source_row_count") or payload.get("row_count") or 0),
        "approval_required": approval_required,
        "clears_blockers": [],
        "remaining_blockers": list(blockers) + [str(value) for value in _as_list(payload.get("blockers"))],
        "next_safe_branch": None,
        **cov,
    }
    row["remaining_blockers"] = _row_blockers(row)
    return row


def _fresh_forward_candidate(path: Path, payload: dict[str, Any], window: DateWindow) -> dict[str, Any]:
    row = {
        "surface_id": "fresh_forward_collection_readiness_from_existing_contracts",
        "input_family": "fresh_forward_collection_readiness",
        "source_type": "approval_required_import",
        "source_path": _rel(path),
        "required_fields_present": path.exists(),
        "known_at_safe": path.exists(),
        "leakage_reject_count": 0,
        "protected_holdout_overlap_rows": 0,
        "covered_months": [],
        "train_months_covered": 0,
        "latest_four_months_covered": 0,
        "covered_date_count": 0,
        "latest_four_covered_date_count": 0,
        "date_coverage_pct": 0.0,
        "latest_four_date_coverage_pct": 0.0,
        "usable_row_count": int(payload.get("cohort_row_count") or 0),
        "approval_required": True,
        "clears_blockers": ["fresh_forward_rows_can_become_proof_only_after_approved_append"],
        "remaining_blockers": ["forward_cohort_append_forbidden_in_this_slice", "valid_market_window_required"],
        "next_safe_branch": None,
    }
    row["remaining_blockers"] = _row_blockers(row)
    return row


def _scan_data_sources(data_root: Path, *, max_files: int = 2000) -> list[dict[str, Any]]:
    if not data_root.exists():
        return []
    skip_parts = {"node_modules", ".cache", "build", "dist", "__pycache__"}
    rows: list[dict[str, Any]] = []
    for path in data_root.rglob("*"):
        if len(rows) >= max_files:
            break
        if not path.is_file() or any(part in skip_parts for part in path.parts):
            continue
        if path.suffix.lower() not in {".json", ".jsonl", ".csv", ".parquet"}:
            continue
        rows.append({"path": _rel(path), "suffix": path.suffix.lower(), "size_bytes": path.stat().st_size, "source_type_guess": _source_type_for_path(path)})
    return rows


def _db_inventory(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for table_row in conn.execute("SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view') ORDER BY name").fetchall():
        name = str(table_row["name"])
        try:
            count = int(conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
        except sqlite3.Error:
            count = None
        rows.append({"name": name, "type": table_row["type"], "row_count": count, "columns": sorted(_table_columns(conn, name))})
    return rows


def _normalize_synthetic_candidate(row: dict[str, Any], window: DateWindow) -> dict[str, Any]:
    normalized = {
        "surface_id": row.get("surface_id", "synthetic_existing_source_fixture"),
        "input_family": row.get("input_family", "trend_or_regime"),
        "source_type": row.get("source_type", "direct_market_source"),
        "source_path": row.get("source_path", "fixture://existing-source"),
        "required_fields_present": bool(row.get("required_fields_present", True)),
        "known_at_safe": bool(row.get("known_at_safe", True)),
        "leakage_reject_count": int(row.get("leakage_reject_count", 0)),
        "protected_holdout_overlap_rows": int(row.get("protected_holdout_overlap_rows", 0)),
        "usable_row_count": int(row.get("usable_row_count", len(window.requested_dates))),
        "approval_required": bool(row.get("approval_required", False)),
        "clears_blockers": _as_list(row.get("clears_blockers")),
        "remaining_blockers": _as_list(row.get("remaining_blockers")),
        "next_safe_branch": row.get("next_safe_branch", "fixture_no_write_research_branch"),
    }
    normalized.update(
        {
            "covered_months": _as_list(row.get("covered_months")) or _month_iter(window.start_date[:7], window.end_date[:7]),
            "train_months_covered": int(row.get("train_months_covered", 20)),
            "latest_four_months_covered": int(row.get("latest_four_months_covered", 4)),
            "covered_date_count": int(row.get("covered_date_count", len(window.requested_dates))),
            "latest_four_covered_date_count": int(row.get("latest_four_covered_date_count", 80)),
            "date_coverage_pct": float(row.get("date_coverage_pct", 100.0)),
            "latest_four_date_coverage_pct": float(row.get("latest_four_date_coverage_pct", 100.0)),
        }
    )
    normalized["remaining_blockers"] = _row_blockers(normalized)
    return normalized


def _rank_ready(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    direct_rank = {"direct_market_source": 0, "derived_point_in_time_proxy": 1}
    family_rank = {family: index for index, family in enumerate(INPUT_FAMILY_ORDER)}
    ready = [row for row in rows if _candidate_ready(row)]
    return sorted(
        ready,
        key=lambda row: (
            direct_rank.get(str(row.get("source_type")), 9),
            -float(row.get("latest_four_date_coverage_pct") or 0.0),
            -float(row.get("date_coverage_pct") or 0.0),
            -int(row.get("train_months_covered") or 0),
            family_rank.get(str(row.get("input_family")), 99),
            str(row.get("surface_id")),
        ),
    )


def _baseline(artifacts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    base_ledger = _as_dict(artifacts.get("base_ledger"))
    all_local = _as_dict(artifacts.get("all_local_quote_atlas"))
    local_matrix = _as_dict(artifacts.get("local_quote_matrix"))
    opening = _as_dict(artifacts.get("opening_replay"))
    synthetic = _as_dict(artifacts.get("synthetic_forward"))
    return {
        "accepted_profitability": False,
        "current_forward_or_latest_four_strict_rows": 0,
        "target_latest_four_strict_rows": 30,
        "historical_rows_are_forward_proof": False,
        "frontier_candidate_count": 44,
        "countable_throughput_candidate_found": False,
        "base_identity_hash_count": int(base_ledger.get("ledger_row_count") or all_local.get("base_identity_hash_count") or 157),
        "all_local_quote_surface_replayability_exhausted_under_current_data": bool(
            all_local.get("all_local_quote_surface_replayability_exhausted_under_current_data")
            or all_local.get("status") == "all_local_quote_surface_replayability_exhausted_under_current_data"
        ),
        "local_quote_matrix_status": local_matrix.get("status"),
        "opening_range_blocker": next(iter(_as_list(opening.get("blockers"))), "blocked_missing_quote_surface_underlying_price"),
        "synthetic_forward_blocker": next(iter(_as_list(synthetic.get("blockers"))), "blocked_missing_call_put_pairs"),
    }


def build_report(
    *,
    db_path: Path = DEFAULT_DB,
    data_root: Path = ROOT / "data",
    start_date: str = "2024-06-01",
    end_date: str = "2026-05-31",
    as_of_date: str = "2026-06-04",
    latest_four_months: tuple[str, ...] = ("2026-02", "2026-03", "2026-04", "2026-05"),
    generated_at_utc: str | None = None,
    control_artifacts: dict[str, Path] | None = None,
    synthetic_candidate_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    generated_at_utc = generated_at_utc or _utc_now_iso()
    control_paths = control_artifacts or CONTROL_ARTIFACTS
    window = _window(start_date, end_date, latest_four_months)

    artifacts: dict[str, dict[str, Any]] = {}
    artifact_meta: dict[str, dict[str, Any]] = {}
    for name, path in control_paths.items():
        payload, meta = _load_json(path, required=name in {"oracle_packet", "all_local_quote_atlas", "base_ledger"})
        artifacts[name] = payload
        artifact_meta[name] = meta

    conn = _connect_read_only(db_path)
    try:
        read_only_open = _read_only_confirmed(conn)
        db_tables = _db_inventory(conn)
        candidates = [
            _db_field_candidate(
                conn,
                input_family="underlying_or_opening_bucket",
                field_names=("underlying_price",),
                source_type="direct_market_source",
                surface_id="option_quote_snapshots_underlying_price_opening_bucket",
                source_path="data/options-validation/options_history.db:option_quote_snapshots.underlying_price",
                window=window,
                extra_blockers=("blocked_missing_quote_surface_underlying_price",),
                next_safe_branch="opening_bucket_underlying_price_readiness_no_write",
            ),
            _db_field_candidate(
                conn,
                input_family="trend_or_regime",
                field_names=("underlying_price",),
                source_type="derived_point_in_time_proxy",
                surface_id="option_quote_snapshots_underlying_price_trend_proxy",
                source_path="data/options-validation/options_history.db:option_quote_snapshots.underlying_price",
                window=window,
                extra_blockers=("insufficient_underlying_price_history_for_trend_proxy",),
                next_safe_branch="point_in_time_trend_regime_proxy_design_no_write",
            ),
            _artifact_candidate(
                input_family="direct_vix_or_volatility_regime",
                surface_id="point_in_time_vix_bucket_artifact",
                path=control_paths["vix_bucket"],
                payload=artifacts["vix_bucket"],
                window=window,
                source_type="direct_market_source",
                blockers=("direct_vix_source_not_present",),
            ),
            _db_field_candidate(
                conn,
                input_family="option_iv_proxy_volatility_regime",
                field_names=("iv",),
                source_type="derived_point_in_time_proxy",
                surface_id="option_quote_snapshots_iv_proxy_volatility_regime",
                source_path="data/options-validation/options_history.db:option_quote_snapshots.iv",
                window=window,
                extra_blockers=("proxy_may_not_clear_direct_vix_blocker",),
                next_safe_branch="option_iv_proxy_volatility_regime_playbook_no_write",
            ),
            _artifact_candidate(
                input_family="flow_or_liquidity_pressure",
                surface_id="point_in_time_flow_extreme_input_artifact",
                path=control_paths["flow_input"],
                payload=artifacts["flow_input"],
                window=window,
                source_type="missing",
                blockers=("plain_bid_ask_availability_is_not_flow_input",),
            ),
            _db_field_candidate(
                conn,
                input_family="volume_open_interest",
                field_names=("volume", "open_interest"),
                source_type="direct_market_source",
                surface_id="option_quote_snapshots_volume_open_interest",
                source_path="data/options-validation/options_history.db:option_quote_snapshots.volume/open_interest",
                window=window,
                extra_blockers=("insufficient_volume_open_interest_history",),
                next_safe_branch="volume_open_interest_pressure_readiness_no_write",
            ),
            _artifact_candidate(
                input_family="macro_event_calendar",
                surface_id="macro_event_calendar_artifact",
                path=control_paths["macro_event_calendar"],
                payload=artifacts["macro_event_calendar"],
                window=window,
                source_type="direct_market_source",
                blockers=("macro_event_calendar_source_missing",),
            ),
            _artifact_candidate(
                input_family="earnings_event_calendar",
                surface_id="earnings_event_calendar_existing_artifact_search",
                path=ROOT / "data" / "profitability-lab" / "regular-options-earnings-event-calendar" / "latest.json",
                payload={},
                window=window,
                source_type="missing",
                blockers=("earnings_event_calendar_source_missing",),
            ),
            _db_field_candidate(
                conn,
                input_family="term_structure_or_skew",
                field_names=("bid", "ask", "expiry", "strike", "option_type"),
                source_type="derived_point_in_time_proxy",
                surface_id="option_quote_snapshots_term_structure_skew_quote_proxy",
                source_path="data/options-validation/options_history.db:option_quote_snapshots.bid/ask/expiry/strike/option_type",
                window=window,
                extra_blockers=("already_parked_quote_surface_only",),
                next_safe_branch=None,
            ),
            _artifact_candidate(
                input_family="dispersion_or_concentration_proxy",
                surface_id="dispersion_concentration_proxy_artifact",
                path=control_paths["dispersion_proxy"],
                payload=artifacts["dispersion_proxy"],
                window=window,
                source_type="derived_point_in_time_proxy",
                blockers=("missing_point_in_time_dispersion_proxy_source",),
            ),
            _artifact_candidate(
                input_family="candidate_generation_diagnostics",
                surface_id="candidate_generation_diagnostics_from_oracle_packet",
                path=control_paths["oracle_packet"],
                payload=artifacts["oracle_packet"],
                window=window,
                source_type="diagnostic_only",
                blockers=("missing_daily_candidate_generation_diagnostics",),
            ),
            _fresh_forward_candidate(control_paths["forward_cohort"], artifacts["forward_cohort"], window),
        ]
    finally:
        conn.close()

    for row in synthetic_candidate_rows or []:
        candidates.append(_normalize_synthetic_candidate(row, window))

    for row in candidates:
        row["ready_for_branch_selection"] = _candidate_ready(row)

    ready_rows = _rank_ready(candidates)
    selected = ready_rows[0] if ready_rows else None
    if selected:
        status = "existing_input_surface_ready_for_branch_selection"
        stop_exception_candidate = False
        no_upgrade_remaining = False
        next_research_branch = {
            "input_family": selected["input_family"],
            "source_path": selected["source_path"],
            "surface_id": selected["surface_id"],
            "coverage_metrics": {
                "train_months_covered": selected["train_months_covered"],
                "latest_four_months_covered": selected["latest_four_months_covered"],
                "date_coverage_pct": selected["date_coverage_pct"],
                "latest_four_date_coverage_pct": selected["latest_four_date_coverage_pct"],
                "usable_row_count": selected["usable_row_count"],
            },
            "cleared_blockers": selected["clears_blockers"],
            "remaining_blockers": selected["remaining_blockers"],
            "bounded_no_write_command": f"npm run options:research:existing-input-surface-atlas -- --start-date {start_date} --end-date {end_date} --as-of-date {as_of_date} --no-write --json",
        }
    else:
        status = "research_only_input_surfaces_exhausted_under_current_repository"
        stop_exception_candidate = True
        no_upgrade_remaining = True
        next_research_branch = None

    baseline = _baseline(artifacts)
    blocked_reason_counts: dict[str, int] = {}
    for row in candidates:
        for blocker in _as_list(row.get("remaining_blockers")):
            blocked_reason_counts[str(blocker)] = blocked_reason_counts.get(str(blocker), 0) + 1

    return {
        "report_id": REPORT_ID,
        "atlas_id": ATLAS_ID,
        "status": status,
        "generated_at_utc": generated_at_utc,
        "as_of_date": as_of_date,
        "window": {
            "start_date": start_date,
            "end_date": end_date,
            "latest_four_months": list(latest_four_months),
            "requested_business_date_count": len(window.requested_dates),
            "train_months": list(window.train_months),
        },
        **READ_ONLY_FLAGS,
        "read_only_db_open": read_only_open,
        "baseline": baseline,
        "current_forward_or_latest_four_strict_rows": baseline["current_forward_or_latest_four_strict_rows"],
        "target_latest_four_strict_rows": baseline["target_latest_four_strict_rows"],
        "frontier_candidate_count": baseline["frontier_candidate_count"],
        "countable_throughput_candidate_found": baseline["countable_throughput_candidate_found"],
        "base_identity_hash_count": baseline["base_identity_hash_count"],
        "all_local_quote_surface_replayability_exhausted_under_current_data": baseline[
            "all_local_quote_surface_replayability_exhausted_under_current_data"
        ],
        "opening_range_blocker": baseline["opening_range_blocker"],
        "synthetic_forward_blocker": baseline["synthetic_forward_blocker"],
        "input_families_required": list(INPUT_FAMILY_ORDER),
        "source_surface_candidates": candidates,
        "source_surface_candidate_count": len(candidates),
        "ready_source_surface_count": len(ready_rows),
        "next_research_branch": next_research_branch,
        "no_research_only_input_surface_upgrade_remaining": no_upgrade_remaining,
        "stop_exception_candidate": stop_exception_candidate,
        "approval_required_next_gates": [
            "fresh_forward_cohort_append_during_valid_market_window",
            "scoped_source_repair_or_replay",
            "quote_import_or_new_data_surface",
            "protected_holdout_decision",
            "promotion_review",
        ],
        "blocked_reason_counts": blocked_reason_counts,
        "control_artifacts": artifact_meta,
        "source_inventory": {"db_tables": db_tables, "data_files_sample": _scan_data_sources(data_root)},
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "artifacts": {
            "docs_report": _rel(DEFAULT_DOCS_REPORT),
            "latest_json": _rel(DEFAULT_OUTPUT_DIR / "latest.json"),
            "latest_markdown": _rel(DEFAULT_OUTPUT_DIR / "latest.md"),
            "source_surface_candidates_jsonl": _rel(DEFAULT_OUTPUT_DIR / "source_surface_candidates.jsonl"),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Existing Input Surface Atlas",
        "",
        f"- Status: `{report['status']}`",
        f"- Generated: `{report['generated_at_utc']}`",
        f"- Read-only DB open: `{report['read_only_db_open']}`",
        f"- Accepted profitability: `{report['accepted_profitability']}`",
        f"- Strict latest-four/forward rows: `{report['current_forward_or_latest_four_strict_rows']}/{report['target_latest_four_strict_rows']}`",
        f"- Ready source surfaces: `{report['ready_source_surface_count']}`",
        f"- Stop exception candidate: `{report['stop_exception_candidate']}`",
        "",
        "This is a source/input inventory only. It does not run P&L replay, generate trades, import quotes, mutate evidence, consume protected holdout, change strategy logic, or promote a lane.",
        "",
        "## Baseline",
        "",
    ]
    for key, value in report["baseline"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Candidate Surfaces", ""])
    for row in report["source_surface_candidates"]:
        blockers = ", ".join(row.get("remaining_blockers") or ["none"])
        lines.append(
            f"- `{row['surface_id']}` ({row['input_family']}, {row['source_type']}): "
            f"ready=`{row['ready_for_branch_selection']}`, train_months=`{row['train_months_covered']}`, "
            f"latest_four_months=`{row['latest_four_months_covered']}`, date_coverage=`{row['date_coverage_pct']}%`, "
            f"latest_four_date_coverage=`{row['latest_four_date_coverage_pct']}%`, blockers={blockers}"
        )
    if report["next_research_branch"]:
        lines.extend(["", "## Next Research Branch", "", "```json", json.dumps(report["next_research_branch"], indent=2, sort_keys=True), "```"])
    else:
        lines.extend(["", "## Next Gates", ""])
        for gate in report["approval_required_next_gates"]:
            lines.append(f"- `{gate}`")
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path, docs_report: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    markdown = render_markdown(report)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    for path in (output_dir / "latest.json", output_dir / f"{stamp}.json"):
        path.write_text(payload, encoding="utf8")
    for path in (output_dir / "latest.md", output_dir / f"{stamp}.md", docs_report):
        path.write_text(markdown, encoding="utf8")
    with (output_dir / "source_surface_candidates.jsonl").open("w", encoding="utf8", newline="\n") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "surface_id",
                "input_family",
                "source_type",
                "source_path",
                "required_fields_present",
                "known_at_safe",
                "leakage_reject_count",
                "covered_months",
                "train_months_covered",
                "latest_four_months_covered",
                "date_coverage_pct",
                "latest_four_date_coverage_pct",
                "usable_row_count",
                "approval_required",
                "clears_blockers",
                "remaining_blockers",
                "next_safe_branch",
                "ready_for_branch_selection",
            ],
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in report["source_surface_candidates"]:
            writer.writerow({key: json.dumps(value, sort_keys=True) if isinstance(value, (list, dict)) else value for key, value in row.items()})


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the read-only existing input surface atlas.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--data-root", type=Path, default=ROOT / "data")
    parser.add_argument("--start-date", default="2024-06-01")
    parser.add_argument("--end-date", default="2026-05-31")
    parser.add_argument("--as-of-date", default="2026-06-04")
    parser.add_argument("--latest-four-months", default="2026-02,2026-03,2026-04,2026-05")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    latest_months = tuple(part.strip() for part in str(args.latest_four_months).split(",") if part.strip())
    report = build_report(
        db_path=args.db,
        data_root=args.data_root,
        start_date=args.start_date,
        end_date=args.end_date,
        as_of_date=args.as_of_date,
        latest_four_months=latest_months,
    )
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
