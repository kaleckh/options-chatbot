from __future__ import annotations

import json
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Optional

import pyarrow.parquet as pq

from forward_options_ledger import (
    PENDING_TRUTH_STATUS,
    _measurement_status_for_event,
    authoritative_forward_ledger_db_path,
    list_forward_scan_pick_events,
    list_forward_sessions,
)
from historical_options_store import DAILY_SNAPSHOT_KIND, HistoricalOptionsStore
from options_profit_state import TARGET_SYMBOLS, utc_now_iso
from wfo_optimizer import (
    IMPORTED_DAILY_TRUTH_SOURCE,
    MIN_ARCHIVED_PRIMARY_SYMBOL_TRADES,
    OPTIONS_VALIDATION_DAILY_LATEST_FILE,
    _imported_result_matches_current_store,
    _load_json_file,
)
from local_env import load_local_env


ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "python-backend"
for candidate in (ROOT_DIR, BACKEND_DIR):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

_ENV_FILES_LOADED = load_local_env(ROOT_DIR)

from positions_repository import create_positions_repository  # type: ignore  # noqa: E402


LIVE_EVIDENCE_CLASS = "live_production"
NON_PRODUCTION_EVIDENCE_CLASSES = {
    "manual_observation",
    "fixture_smoke",
    "unit_test",
    "e2e_test",
    "research_backfill",
}
DEFAULT_MIN_IMPORTED_QUOTE_COVERAGE_PCT = 70.0
DEFAULT_MIN_ELIGIBLE_FORWARD_EVENTS = 10
DEFAULT_MIN_ELIGIBLE_EVENTS_PER_SYMBOL = 3
DEFAULT_MIN_CLOSED_TRACKED_POSITIONS = 1
DEFAULT_MAX_TRUSTED_TRUTH_STALENESS_BUSINESS_DAYS = 3
DAILY_TRUTH_IMPORT_MANIFEST_ENV = "OPTIONS_DAILY_TRUTH_IMPORT_MANIFEST"
LEGACY_DAILY_TRUTH_IMPORT_MANIFEST_ENV = "HISTORICAL_OPTIONS_IMPORT_MANIFEST"
DEFAULT_DAILY_TRUTH_IMPORT_MANIFEST = ROOT_DIR / "data" / "options-validation" / "daily_truth_import_manifest.json"


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> Optional[date]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            return None


def _resolve_daily_truth_import_manifest() -> tuple[str | None, str | None]:
    for env_name in (DAILY_TRUTH_IMPORT_MANIFEST_ENV, LEGACY_DAILY_TRUTH_IMPORT_MANIFEST_ENV):
        raw = str(os.getenv(env_name) or "").strip()
        if not raw:
            continue
        if raw.startswith(("http://", "https://")):
            return raw, env_name
        path = Path(raw)
        if not path.is_absolute():
            path = ROOT_DIR / path
        return str(path.resolve()), env_name
    if DEFAULT_DAILY_TRUTH_IMPORT_MANIFEST.exists():
        return str(DEFAULT_DAILY_TRUTH_IMPORT_MANIFEST.resolve()), "default_manifest"
    return None, None


def _load_manifest_entries(manifest_path: str | None) -> list[dict[str, Any]]:
    if not manifest_path:
        return []
    try:
        payload = json.loads(Path(manifest_path).read_text(encoding="utf8"))
    except Exception:
        return []
    if isinstance(payload, list):
        entries = payload
    else:
        entries = payload.get("imports")
    if not isinstance(entries, list):
        return []
    return [dict(entry) for entry in entries if isinstance(entry, dict)]


def _resolve_manifest_entry_path(value: Any) -> Path | None:
    raw = str(value or "").strip()
    if not raw or raw.startswith(("http://", "https://")):
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path.resolve()


def _normalize_source_horizon_date(value: Any) -> date | None:
    if value is None:
        return None
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _parquet_source_horizon(path: Path, *, date_column: str = "date") -> date | None:
    try:
        parquet = pq.ParquetFile(path)
    except Exception:
        return None
    names = list(parquet.schema_arrow.names)
    if date_column not in names:
        return None
    column_index = names.index(date_column)
    latest: date | None = None
    try:
        for row_group_index in range(parquet.metadata.num_row_groups):
            stats = parquet.metadata.row_group(row_group_index).column(column_index).statistics
            candidate = _normalize_source_horizon_date(getattr(stats, "max", None))
            if candidate is None:
                latest = None
                break
            if latest is None or candidate > latest:
                latest = candidate
        if latest is not None:
            return latest
    except Exception:
        latest = None
    try:
        table = pq.read_table(path, columns=[date_column], use_threads=False)
    except Exception:
        return None
    values = [
        _normalize_source_horizon_date(item)
        for item in table.column(date_column).to_pylist()
    ]
    values = [item for item in values if item is not None]
    return max(values) if values else None


def _daily_truth_source_freshness(
    *,
    current_date: date,
    max_trusted_truth_staleness_business_days: int,
) -> dict[str, Any]:
    manifest_path, manifest_source = _resolve_daily_truth_import_manifest()
    entries = _load_manifest_entries(manifest_path)
    requested_manifest_inputs: list[str] = []
    latest_input_mtime_utc: datetime | None = None
    latest_source_horizon: date | None = None
    for entry in entries:
        for key in ("input", "underlying_input"):
            candidate = _resolve_manifest_entry_path(entry.get(key))
            if candidate is None:
                continue
            requested_manifest_inputs.append(str(candidate))
            if not candidate.exists():
                continue
            modified = datetime.fromtimestamp(candidate.stat().st_mtime, tz=UTC)
            if latest_input_mtime_utc is None or modified > latest_input_mtime_utc:
                latest_input_mtime_utc = modified
            if candidate.suffix.lower() == ".parquet":
                source_horizon = _parquet_source_horizon(candidate)
                if source_horizon is not None and (latest_source_horizon is None or source_horizon > latest_source_horizon):
                    latest_source_horizon = source_horizon
    source_staleness = _business_days_stale(
        latest_input_mtime_utc.date() if latest_input_mtime_utc is not None else None,
        current_date,
    )
    source_horizon_staleness = _business_days_stale(latest_source_horizon, current_date)
    effective_source_staleness = source_horizon_staleness if latest_source_horizon is not None else source_staleness
    return {
        "manifest_path": manifest_path,
        "manifest_source": manifest_source,
        "requested_manifest_inputs": requested_manifest_inputs,
        "daily_truth_source_latest_mtime_utc": (
            latest_input_mtime_utc.isoformat().replace("+00:00", "Z")
            if latest_input_mtime_utc is not None
            else None
        ),
        "daily_truth_source_horizon": latest_source_horizon.isoformat() if latest_source_horizon else None,
        "daily_truth_source_stale": (
            effective_source_staleness is not None
            and effective_source_staleness > int(max_trusted_truth_staleness_business_days)
        ),
        "source_horizon_staleness_business_days": source_horizon_staleness,
    }


def _normalize_evidence_class(value: Any, *, source_label: str = "") -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {LIVE_EVIDENCE_CLASS, *NON_PRODUCTION_EVIDENCE_CLASSES}:
        return normalized
    source = str(source_label or "").strip().lower()
    if any(token in source for token in ("manual", "observation")):
        return "manual_observation"
    if any(token in source for token in ("fixture", "smoke")):
        return "fixture_smoke"
    if "e2e" in source:
        return "e2e_test"
    if "test" in source:
        return "unit_test"
    if any(token in source for token in ("research", "backfill")):
        return "research_backfill"
    return LIVE_EVIDENCE_CLASS


def _business_days_stale(truth_horizon: date | None, current_date: date | None) -> Optional[int]:
    if truth_horizon is None or current_date is None:
        return None
    if truth_horizon >= current_date:
        return 0
    day = truth_horizon
    business_days = 0
    while day < current_date:
        day = day.fromordinal(day.toordinal() + 1)
        if day.weekday() < 5:
            business_days += 1
    return business_days


def _normalize_quote_freshness_status(event: dict[str, Any]) -> str:
    explicit = str(
        event.get("quote_freshness_status")
        or event.get("options_snapshot_status")
        or event.get("option_chain_status")
        or ""
    ).strip().lower()
    if explicit:
        if any(token in explicit for token in ("stale", "error", "missing", "expired", "unavailable")):
            return "stale"
        return explicit
    quote_basis = str(event.get("quote_basis") or "").strip().lower()
    if "stale" in quote_basis:
        return "stale"
    return "fresh"


def _load_positions_snapshot() -> dict[str, Any]:
    database_url = str(os.getenv("DATABASE_URL") or "").strip()
    repo = create_positions_repository(database_url or None)
    available = bool(getattr(repo, "is_available", False))
    closed_positions: list[dict[str, Any]] = []
    error_message = getattr(repo, "error_message", None)
    if available:
        try:
            closed_positions = list(repo.list_positions("closed"))
        except Exception as exc:
            available = False
            error_message = str(exc)
    return {
        "available": available,
        "error_message": error_message,
        "closed_positions": closed_positions,
        "database_url_configured": bool(database_url),
    }


def _realized_position_metrics(positions: list[dict[str, Any]]) -> dict[str, Any]:
    net_pnls: list[float] = []
    gross_pnls: list[float] = []
    net_realized_pnl_usd = 0.0
    gross_realized_pnl_usd = 0.0
    exact_contract_count = 0
    for position in positions:
        net_pnl_pct = _safe_float(position.get("net_pnl_pct"))
        gross_pnl_pct = _safe_float(position.get("gross_pnl_pct"))
        if net_pnl_pct is None or gross_pnl_pct is None:
            entry = _safe_float(position.get("entry_execution_price"))
            if entry is None:
                entry = _safe_float(position.get("entry_option_price"))
            exit_price = _safe_float(position.get("exit_execution_price"))
            if exit_price is None:
                exit_price = _safe_float(position.get("exit_option_price"))
            if entry is None or entry <= 0 or exit_price is None:
                continue
            gross_pnl_pct = (exit_price / entry - 1.0) * 100.0
            net_pnl_pct = gross_pnl_pct
        if str(position.get("contract_symbol") or "").strip():
            exact_contract_count += 1
        net_pnls.append(net_pnl_pct)
        gross_pnls.append(gross_pnl_pct)
        net_realized_pnl_usd += float(_safe_float(position.get("net_pnl_usd")) or 0.0)
        gross_realized_pnl_usd += float(_safe_float(position.get("gross_pnl_usd")) or 0.0)
    positive = sum(value for value in net_pnls if value > 0)
    negative = abs(sum(value for value in net_pnls if value < 0))
    profit_factor = round(positive / negative, 3) if negative > 0 else (999.0 if positive > 0 else None)
    return {
        "closed_position_count": len(net_pnls),
        "exact_contract_closed_count": exact_contract_count,
        "avg_pnl_pct": round(sum(net_pnls) / len(net_pnls), 3) if net_pnls else None,
        "avg_net_pnl_pct": round(sum(net_pnls) / len(net_pnls), 3) if net_pnls else None,
        "avg_gross_pnl_pct": round(sum(gross_pnls) / len(gross_pnls), 3) if gross_pnls else None,
        "profit_factor": profit_factor,
        "net_profit_factor": profit_factor,
        "positive_sum_pct": round(positive, 3),
        "negative_sum_pct": round(negative, 3),
        "net_realized_pnl_usd": round(net_realized_pnl_usd, 2),
        "gross_realized_pnl_usd": round(gross_realized_pnl_usd, 2),
    }


def _load_forward_evidence(
    *,
    forward_db_path: str | Path | None = None,
    recorded_before_utc: str | None = None,
) -> dict[str, Any]:
    resolved_forward_db_path = Path(forward_db_path) if forward_db_path else authoritative_forward_ledger_db_path()
    session_map = {
        int(session["id"]): session
        for session in list_forward_sessions(limit=5000, db_path=resolved_forward_db_path)
    }
    store = HistoricalOptionsStore()
    latest_quote_at_utc = str(
        store.snapshot_summary(DAILY_SNAPSHOT_KIND, trusted_only=True).get("latest_quote_at_utc") or ""
    ).strip()
    trusted_truth_horizon = _parse_date(latest_quote_at_utc)

    eligible_events: list[dict[str, Any]] = []
    pending_truth_events: list[dict[str, Any]] = []
    all_events: list[dict[str, Any]] = []
    contamination_findings: list[dict[str, Any]] = []
    stale_metadata_events: list[dict[str, Any]] = []
    by_symbol: dict[str, dict[str, int]] = {
        symbol: {"eligible": 0, "pending_truth": 0, "ineligible": 0}
        for symbol in TARGET_SYMBOLS
    }

    for event in list_forward_scan_pick_events(
        db_path=resolved_forward_db_path,
        recorded_before_utc=recorded_before_utc,
    ):
        session = session_map.get(int(event.get("session_id") or 0), {})
        notes = dict(session.get("notes") or {})
        source_label = str(event.get("source_label") or session.get("source_label") or "").strip()
        evidence_class = _normalize_evidence_class(
            event.get("evidence_class")
            or notes.get("evidence_class")
            or event.get("run_mode")
            or notes.get("run_mode"),
            source_label=source_label,
        )
        quote_freshness_status = _normalize_quote_freshness_status(event)
        truth_source = str(
            event.get("session_truth_source")
            or session.get("truth_source")
            or notes.get("truth_source")
            or ""
        ).strip()
        promotion_status = str(
            event.get("session_promotion_status")
            or session.get("promotion_status")
            or notes.get("promotion_status")
            or ""
        ).strip()
        eligibility_blockers = [
            str(item or "").strip()
            for item in list(event.get("eligibility_blockers") or [])
            if str(item or "").strip()
        ]
        if evidence_class != LIVE_EVIDENCE_CLASS:
            blocker = f"evidence_class:{evidence_class}"
            if blocker not in eligibility_blockers:
                eligibility_blockers.append(blocker)
        if not bool(notes.get("policy_applied")):
            if "policy_not_applied" not in eligibility_blockers:
                eligibility_blockers.append("policy_not_applied")
        if not truth_source:
            if "missing_truth_source" not in eligibility_blockers:
                eligibility_blockers.append("missing_truth_source")
        if not promotion_status:
            if "missing_promotion_status" not in eligibility_blockers:
                eligibility_blockers.append("missing_promotion_status")
        if str(notes.get("positions_error") or "").strip():
            if "positions_error" not in eligibility_blockers:
                eligibility_blockers.append("positions_error")
        if quote_freshness_status == "stale":
            if "stale_quote_metadata" not in eligibility_blockers:
                eligibility_blockers.append("stale_quote_metadata")
        if not str(event.get("contract_symbol") or "").strip():
            if "missing_exact_contract" not in eligibility_blockers:
                eligibility_blockers.append("missing_exact_contract")
        if _safe_float(event.get("entry_execution_price")) is None:
            if "missing_executable_entry_quote" not in eligibility_blockers:
                eligibility_blockers.append("missing_executable_entry_quote")
        effective_status = _measurement_status_for_event(
            event,
            trusted_truth_horizon=trusted_truth_horizon,
            base_blockers=eligibility_blockers,
        )
        if effective_status == PENDING_TRUTH_STATUS:
            effective_blockers = ["entry_date_beyond_trusted_truth_horizon"]
        elif effective_status == "eligible":
            effective_blockers = []
        else:
            effective_blockers = list(eligibility_blockers)

        normalized_event = dict(event)
        normalized_event["evidence_class"] = evidence_class
        normalized_event["quote_freshness_status"] = quote_freshness_status
        normalized_event["truth_source"] = truth_source or None
        normalized_event["promotion_status"] = promotion_status or None
        normalized_event["eligibility_blockers"] = list(effective_blockers)
        normalized_event["eligibility_status"] = effective_status
        all_events.append(normalized_event)

        symbol = str(event.get("ticker") or "").strip().upper()
        if symbol in by_symbol:
            bucket = effective_status if effective_status in {"eligible", PENDING_TRUTH_STATUS} else "ineligible"
            by_symbol[symbol][bucket] += 1

        if evidence_class != LIVE_EVIDENCE_CLASS and source_label:
            contamination_findings.append(
                {
                    "event_id": normalized_event.get("event_id"),
                    "session_id": normalized_event.get("session_id"),
                    "source_label": source_label,
                    "evidence_class": evidence_class,
                }
            )
        if quote_freshness_status == "stale":
            stale_metadata_events.append(
                {
                    "event_id": normalized_event.get("event_id"),
                    "ticker": symbol or None,
                    "source_label": source_label,
                    "quote_time_et": normalized_event.get("quote_time_et"),
                }
            )
        if effective_status == "eligible":
            eligible_events.append(normalized_event)
        elif effective_status == PENDING_TRUTH_STATUS:
            pending_truth_events.append(normalized_event)

    return {
        "db_path": str(resolved_forward_db_path),
        "trusted_truth_horizon": trusted_truth_horizon.isoformat() if trusted_truth_horizon else None,
        "all_events": all_events,
        "eligible_events": eligible_events,
        "eligible_event_count": len(eligible_events),
        "pending_truth_events": pending_truth_events,
        "pending_truth_event_count": len(pending_truth_events),
        "contamination_findings": contamination_findings,
        "stale_metadata_events": stale_metadata_events,
        "by_symbol": by_symbol,
    }


def evaluate_measurement_gate(
    *,
    forward_db_path: str | Path | None = None,
    recorded_before_utc: str | None = None,
    min_imported_quote_coverage_pct: float = DEFAULT_MIN_IMPORTED_QUOTE_COVERAGE_PCT,
    min_eligible_forward_events: int = DEFAULT_MIN_ELIGIBLE_FORWARD_EVENTS,
    min_eligible_events_per_symbol: int = DEFAULT_MIN_ELIGIBLE_EVENTS_PER_SYMBOL,
    min_closed_tracked_positions: int = DEFAULT_MIN_CLOSED_TRACKED_POSITIONS,
    max_trusted_truth_staleness_business_days: int = DEFAULT_MAX_TRUSTED_TRUTH_STALENESS_BUSINESS_DAYS,
) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    current_truth_date = _parse_date(recorded_before_utc) or datetime.now(UTC).date()
    source_freshness = _daily_truth_source_freshness(
        current_date=current_truth_date,
        max_trusted_truth_staleness_business_days=int(max_trusted_truth_staleness_business_days),
    )

    raw_imported_daily = _load_json_file(OPTIONS_VALIDATION_DAILY_LATEST_FILE)
    imported_daily_matches_store = _imported_result_matches_current_store(
        raw_imported_daily,
        IMPORTED_DAILY_TRUTH_SOURCE,
    )
    if not raw_imported_daily or not imported_daily_matches_store:
        blockers.append(
            {
                "code": "imported_daily_store_mismatch",
                "severity": "blocked",
                "message": (
                    "The imported-daily validation artifact is missing or no longer matches the trusted "
                    "historical truth store."
                ),
                "path": OPTIONS_VALIDATION_DAILY_LATEST_FILE,
            }
        )

    quote_coverage_pct = _safe_float((raw_imported_daily or {}).get("quote_coverage_pct"))
    if quote_coverage_pct is None or quote_coverage_pct < float(min_imported_quote_coverage_pct):
        blockers.append(
            {
                "code": "imported_daily_quote_coverage_below_floor",
                "severity": "blocked",
                "message": "Imported-daily quote coverage is below the current options gate floor.",
                "quote_coverage_pct": quote_coverage_pct,
                "required_quote_coverage_pct": float(min_imported_quote_coverage_pct),
            }
        )

    forward_evidence = _load_forward_evidence(
        forward_db_path=forward_db_path,
        recorded_before_utc=recorded_before_utc,
    )
    trusted_truth_horizon = _parse_date(forward_evidence.get("trusted_truth_horizon"))
    trusted_truth_staleness = _business_days_stale(trusted_truth_horizon, current_truth_date)
    if forward_evidence["contamination_findings"]:
        blockers.append(
            {
                "code": "forward_ledger_contamination",
                "severity": "blocked",
                "message": "Fixture, test, or research evidence is present in the authoritative forward ledger.",
                "finding_count": len(forward_evidence["contamination_findings"]),
            }
        )

    if trusted_truth_horizon is None:
        blockers.append(
            {
                "code": "trusted_truth_horizon_missing",
                "severity": "blocked",
                "message": "Trusted options truth horizon is missing, so the optimizer must remain read-only.",
            }
        )
    elif trusted_truth_staleness is not None and trusted_truth_staleness > int(max_trusted_truth_staleness_business_days):
        blockers.append(
            {
                "code": "trusted_truth_stale",
                "severity": "blocked",
                "message": "Trusted options truth is too stale for bounded auto-optimization.",
                "trusted_truth_horizon": trusted_truth_horizon.isoformat(),
                "truth_staleness_business_days": int(trusted_truth_staleness),
                "allowed_truth_staleness_business_days": int(max_trusted_truth_staleness_business_days),
            }
        )

    if forward_evidence["stale_metadata_events"]:
        blockers.append(
            {
                "code": "stale_option_metadata",
                "severity": "degraded-watch",
                "message": "Recorded live picks include stale or error-like quote metadata.",
                "finding_count": len(forward_evidence["stale_metadata_events"]),
            }
        )

    if int(forward_evidence.get("pending_truth_event_count") or 0) > 0:
        blockers.append(
            {
                "code": "pending_truth_horizon",
                "severity": "pending_truth",
                "message": "Live forward evidence exists beyond the trusted imported-daily truth horizon and is waiting to mature.",
                "pending_truth_event_count": int(forward_evidence["pending_truth_event_count"]),
                "trusted_truth_horizon": forward_evidence.get("trusted_truth_horizon"),
            }
        )

    if int(forward_evidence["eligible_event_count"]) < int(min_eligible_forward_events):
        blockers.append(
            {
                "code": "insufficient_eligible_forward_truth",
                "severity": "degraded-watch",
                "message": "Not enough matured eligible live-production forward evidence is available.",
                "eligible_event_count": int(forward_evidence["eligible_event_count"]),
                "required_event_count": int(min_eligible_forward_events),
            }
        )

    for symbol, counts in sorted(forward_evidence["by_symbol"].items()):
        if int(counts.get("eligible") or 0) < int(min_eligible_events_per_symbol):
            blockers.append(
                {
                    "code": f"insufficient_symbol_forward_truth_{symbol.lower()}",
                    "severity": "degraded-watch",
                    "message": f"{symbol} does not yet have enough eligible live-production forward evidence.",
                    "symbol": symbol,
                    "eligible_event_count": int(counts.get("eligible") or 0),
                    "required_event_count": int(min_eligible_events_per_symbol),
                }
            )

    positions_snapshot = _load_positions_snapshot()
    if not positions_snapshot["available"]:
        blockers.append(
            {
                "code": "tracked_positions_unavailable",
                "severity": "blocked",
                "message": (
                    positions_snapshot["error_message"]
                    or "Tracked positions storage is unavailable."
                ),
                "database_url_configured": bool(positions_snapshot.get("database_url_configured")),
            }
        )

    realized_metrics = _realized_position_metrics(positions_snapshot["closed_positions"])
    if int(realized_metrics["closed_position_count"] or 0) < int(min_closed_tracked_positions):
        blockers.append(
            {
                "code": "insufficient_closed_tracked_positions",
                "severity": "degraded-watch",
                "message": "Not enough closed tracked positions are available for optimizer supervision.",
                "closed_position_count": int(realized_metrics["closed_position_count"] or 0),
                "required_closed_position_count": int(min_closed_tracked_positions),
            }
        )

    if any(blocker["severity"] == "blocked" for blocker in blockers):
        state = "blocked"
    elif any(blocker["severity"] == "pending_truth" for blocker in blockers):
        state = "pending_truth"
    elif blockers:
        state = "degraded-watch"
    else:
        state = "healthy"

    return {
        "generated_at": utc_now_iso(),
        "state": state,
        "blockers": blockers,
        "checks": {
            "imported_daily_artifact": {
                "path": OPTIONS_VALIDATION_DAILY_LATEST_FILE,
                "present": raw_imported_daily is not None,
                "matches_store": imported_daily_matches_store,
                "quote_coverage_pct": quote_coverage_pct,
                "required_quote_coverage_pct": float(min_imported_quote_coverage_pct),
                "manifest_path": source_freshness.get("manifest_path"),
                "manifest_source": source_freshness.get("manifest_source"),
                "requested_manifest_inputs": list(source_freshness.get("requested_manifest_inputs") or []),
                "daily_truth_source_latest_mtime_utc": source_freshness.get("daily_truth_source_latest_mtime_utc"),
                "daily_truth_source_stale": bool(source_freshness.get("daily_truth_source_stale")),
            },
            "forward_evidence": {
                "db_path": forward_evidence.get("db_path"),
                "eligible_event_count": int(forward_evidence["eligible_event_count"]),
                "pending_truth_event_count": int(forward_evidence.get("pending_truth_event_count") or 0),
                "required_event_count": int(min_eligible_forward_events),
                "trusted_truth_horizon": forward_evidence["trusted_truth_horizon"],
                "truth_staleness_business_days": trusted_truth_staleness,
                "requested_manifest_inputs": list(source_freshness.get("requested_manifest_inputs") or []),
                "daily_truth_source_latest_mtime_utc": source_freshness.get("daily_truth_source_latest_mtime_utc"),
                "daily_truth_source_stale": bool(source_freshness.get("daily_truth_source_stale")),
                "by_symbol": forward_evidence["by_symbol"],
                "contamination_finding_count": len(forward_evidence["contamination_findings"]),
                "stale_metadata_finding_count": len(forward_evidence["stale_metadata_events"]),
                "existing_symbol_floor": int(MIN_ARCHIVED_PRIMARY_SYMBOL_TRADES),
            },
            "tracked_positions": {
                "available": bool(positions_snapshot["available"]),
                "database_url_configured": bool(positions_snapshot.get("database_url_configured")),
                "error_message": positions_snapshot.get("error_message"),
                "closed_position_count": int(realized_metrics["closed_position_count"] or 0),
                "required_closed_position_count": int(min_closed_tracked_positions),
            },
        },
        "eligible_forward_evidence": forward_evidence["eligible_events"],
        "forward_evidence_summary": {
            key: value
            for key, value in forward_evidence.items()
            if key != "all_events"
        },
        "tracked_realized_metrics": realized_metrics,
    }
