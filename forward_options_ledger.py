from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from contextlib import closing
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from historical_options_store import DAILY_SNAPSHOT_KIND, HistoricalOptionsStore
from options_execution import commission_total_usd, executable_option_price, safe_float as execution_safe_float

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "python-backend"
for candidate in (ROOT_DIR, BACKEND_DIR):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from positions_repository import create_positions_repository  # type: ignore  # noqa: E402

DEFAULT_FORWARD_LEDGER_DB_PATH = ROOT_DIR / "data" / "options-validation" / "forward_tracking.db"
DEFAULT_AUTHORITATIVE_FORWARD_LEDGER_DB_PATH = (
    ROOT_DIR / "data" / "options-validation" / "forward_tracking_authoritative.db"
)
FORWARD_LEDGER_DB_ENV = "FORWARD_OPTIONS_LEDGER_DB_PATH"
AUTHORITATIVE_FORWARD_LEDGER_DB_ENV = "FORWARD_OPTIONS_AUTHORITATIVE_LEDGER_DB_PATH"

LIVE_PRODUCTION_EVIDENCE_CLASS = "live_production"
MANUAL_OBSERVATION_EVIDENCE_CLASS = "manual_observation"
FIXTURE_SMOKE_EVIDENCE_CLASS = "fixture_smoke"
UNIT_TEST_EVIDENCE_CLASS = "unit_test"
E2E_TEST_EVIDENCE_CLASS = "e2e_test"
RESEARCH_BACKFILL_EVIDENCE_CLASS = "research_backfill"
ELIGIBLE_STATUS = "eligible"
INELIGIBLE_STATUS = "ineligible"
PENDING_TRUTH_STATUS = "pending_truth"

FORWARD_SESSION_OPTIONAL_COLUMNS: dict[str, str] = {
    "run_id": "TEXT",
    "run_mode": "TEXT",
    "evidence_class": "TEXT",
    "is_fixture": "INTEGER NOT NULL DEFAULT 0",
    "policy_artifact_id": "TEXT",
    "quote_freshness_status": "TEXT",
    "eligibility_status": "TEXT",
    "eligibility_blockers": "TEXT NOT NULL DEFAULT '[]'",
}

FORWARD_EVENT_OPTIONAL_COLUMNS: dict[str, str] = {
    "cohort_id": "TEXT",
    "cohort_role": "TEXT",
    "policy_state": "TEXT",
    "guardrail_state": "TEXT",
    "expiry": "TEXT",
    "strike": "REAL",
    "option_type": "TEXT",
    "quote_time_et": "TEXT",
    "quote_basis": "TEXT",
    "underlying_price_at_selection": "REAL",
    "selection_source": "TEXT",
    "promotion_class": "TEXT",
    "candidate_rank": "INTEGER",
    "option_bid": "REAL",
    "option_ask": "REAL",
    "option_mid": "REAL",
    "option_spread_pct": "REAL",
    "option_iv": "REAL",
    "option_delta": "REAL",
    "option_dte": "INTEGER",
    "entry_execution_price": "REAL",
    "entry_execution_basis": "TEXT",
    "entry_fee_total_usd": "REAL",
    "exit_execution_price": "REAL",
    "exit_execution_basis": "TEXT",
    "gross_pnl_pct": "REAL",
    "net_pnl_pct": "REAL",
    "gross_pnl_usd": "REAL",
    "net_pnl_usd": "REAL",
    "fee_total_usd": "REAL",
    "outcome_state": "TEXT",
    "run_id": "TEXT",
    "run_mode": "TEXT",
    "evidence_class": "TEXT",
    "is_fixture": "INTEGER NOT NULL DEFAULT 0",
    "policy_artifact_id": "TEXT",
    "quote_freshness_status": "TEXT",
    "eligibility_status": "TEXT",
    "eligibility_blockers": "TEXT NOT NULL DEFAULT '[]'",
    "position_id": "INTEGER",
    "contracts": "INTEGER",
    "source_scan_session_id": "INTEGER",
    "source_scan_event_key": "TEXT",
    "source_scan_run_id": "TEXT",
}


def archive_forward_ledger_db_path() -> Path:
    override = os.getenv(FORWARD_LEDGER_DB_ENV)
    return Path(override) if override else DEFAULT_FORWARD_LEDGER_DB_PATH


def authoritative_forward_ledger_db_path() -> Path:
    override = os.getenv(AUTHORITATIVE_FORWARD_LEDGER_DB_ENV)
    if override:
        return Path(override)
    legacy_override = os.getenv(FORWARD_LEDGER_DB_ENV)
    if legacy_override:
        legacy_path = Path(legacy_override)
        stem = legacy_path.stem or "forward_tracking"
        return legacy_path.with_name(f"{stem}_authoritative{legacy_path.suffix or '.db'}")
    return DEFAULT_AUTHORITATIVE_FORWARD_LEDGER_DB_PATH


def _db_path() -> Path:
    return authoritative_forward_ledger_db_path()


def _ensure_table_columns(
    conn: sqlite3.Connection,
    table_name: str,
    columns: dict[str, str],
) -> None:
    existing = {
        str(row[1])
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    for name, ddl in columns.items():
        if name in existing:
            continue
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {name} {ddl}")


def init_forward_ledger(db_path: str | Path | None = None) -> Path:
    path = Path(db_path) if db_path else _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS forward_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recorded_at_utc TEXT NOT NULL,
                source_label TEXT NOT NULL,
                playbook TEXT,
                truth_source TEXT,
                promotion_status TEXT,
                scan_picks_count INTEGER NOT NULL DEFAULT 0,
                reviewed_positions_count INTEGER NOT NULL DEFAULT 0,
                notes_json TEXT NOT NULL DEFAULT '{}',
                run_id TEXT,
                run_mode TEXT,
                evidence_class TEXT,
                is_fixture INTEGER NOT NULL DEFAULT 0,
                policy_artifact_id TEXT,
                quote_freshness_status TEXT,
                eligibility_status TEXT,
                eligibility_blockers TEXT NOT NULL DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS forward_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL REFERENCES forward_sessions(id) ON DELETE CASCADE,
                event_type TEXT NOT NULL,
                event_key TEXT,
                ticker TEXT,
                contract_symbol TEXT,
                recommendation TEXT,
                pricing_source TEXT,
                cohort_id TEXT,
                cohort_role TEXT,
                policy_state TEXT,
                guardrail_state TEXT,
                expiry TEXT,
                strike REAL,
                option_type TEXT,
                quote_time_et TEXT,
                quote_basis TEXT,
                underlying_price_at_selection REAL,
                selection_source TEXT,
                promotion_class TEXT,
                candidate_rank INTEGER,
                option_bid REAL,
                option_ask REAL,
                option_mid REAL,
                option_spread_pct REAL,
                option_iv REAL,
                option_delta REAL,
                option_dte INTEGER,
                entry_execution_price REAL,
                entry_execution_basis TEXT,
                entry_fee_total_usd REAL,
                exit_execution_price REAL,
                exit_execution_basis TEXT,
                gross_pnl_pct REAL,
                net_pnl_pct REAL,
                gross_pnl_usd REAL,
                net_pnl_usd REAL,
                fee_total_usd REAL,
                outcome_state TEXT,
                run_id TEXT,
                run_mode TEXT,
                evidence_class TEXT,
                is_fixture INTEGER NOT NULL DEFAULT 0,
                policy_artifact_id TEXT,
                quote_freshness_status TEXT,
                eligibility_status TEXT,
                eligibility_blockers TEXT NOT NULL DEFAULT '[]',
                payload_json TEXT NOT NULL
            );
            """
        )
        _ensure_table_columns(conn, "forward_sessions", FORWARD_SESSION_OPTIONAL_COLUMNS)
        _ensure_table_columns(conn, "forward_events", FORWARD_EVENT_OPTIONAL_COLUMNS)
        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_forward_sessions_recorded_at
                ON forward_sessions (recorded_at_utc DESC);
            CREATE INDEX IF NOT EXISTS idx_forward_events_session_type
                ON forward_events (session_id, event_type, id);
            CREATE INDEX IF NOT EXISTS idx_forward_events_cohort
                ON forward_events (cohort_id, event_type, id);
            """
        )
        conn.commit()
    return path


def migrate_live_production_evidence(
    *,
    source_db_path: str | Path | None = None,
    destination_db_path: str | Path | None = None,
) -> dict[str, Any]:
    source_path = init_forward_ledger(source_db_path or archive_forward_ledger_db_path())
    destination_path = init_forward_ledger(destination_db_path or authoritative_forward_ledger_db_path())
    if source_path.resolve() == destination_path.resolve():
        return {
            "status": "skipped_same_path",
            "source_db_path": str(source_path),
            "destination_db_path": str(destination_path),
            "selected_session_count": 0,
            "migrated_session_count": 0,
            "migrated_event_count": 0,
            "skipped_existing_session_count": 0,
        }

    with closing(sqlite3.connect(source_path)) as source_conn, closing(sqlite3.connect(destination_path)) as dest_conn:
        source_conn.row_factory = sqlite3.Row
        dest_conn.row_factory = sqlite3.Row
        session_columns = [
            str(row["name"])
            for row in source_conn.execute("PRAGMA table_info(forward_sessions)").fetchall()
            if str(row["name"]) != "id"
        ]
        event_columns = [
            str(row["name"])
            for row in source_conn.execute("PRAGMA table_info(forward_events)").fetchall()
            if str(row["name"]) not in {"id", "session_id"}
        ]
        selected_sessions = source_conn.execute(
            """
            SELECT *
            FROM forward_sessions
            WHERE COALESCE(evidence_class, '') = ?
              AND COALESCE(is_fixture, 0) = 0
            ORDER BY recorded_at_utc ASC, id ASC
            """,
            (LIVE_PRODUCTION_EVIDENCE_CLASS,),
        ).fetchall()

        migrated_session_count = 0
        migrated_event_count = 0
        skipped_existing_session_count = 0
        for source_session in selected_sessions:
            existing = dest_conn.execute(
                """
                SELECT id
                FROM forward_sessions
                WHERE COALESCE(recorded_at_utc, '') = COALESCE(?, '')
                  AND COALESCE(source_label, '') = COALESCE(?, '')
                  AND COALESCE(run_id, '') = COALESCE(?, '')
                  AND COALESCE(evidence_class, '') = COALESCE(?, '')
                ORDER BY id DESC
                LIMIT 1
                """,
                (
                    source_session["recorded_at_utc"],
                    source_session["source_label"],
                    source_session["run_id"],
                    source_session["evidence_class"],
                ),
            ).fetchone()
            if existing is not None:
                skipped_existing_session_count += 1
                continue

            insert_placeholders = ", ".join("?" for _ in session_columns)
            dest_conn.execute(
                f"""
                INSERT INTO forward_sessions ({", ".join(session_columns)})
                VALUES ({insert_placeholders})
                """,
                tuple(source_session[column] for column in session_columns),
            )
            destination_session_id = int(dest_conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            migrated_session_count += 1

            source_events = source_conn.execute(
                """
                SELECT *
                FROM forward_events
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (int(source_session["id"]),),
            ).fetchall()
            event_placeholders = ", ".join("?" for _ in event_columns)
            for source_event in source_events:
                dest_conn.execute(
                    f"""
                    INSERT INTO forward_events (session_id, {", ".join(event_columns)})
                    VALUES (?, {event_placeholders})
                    """,
                    (destination_session_id, *(source_event[column] for column in event_columns)),
                )
                migrated_event_count += 1

        dest_conn.commit()

    return {
        "status": "migrated",
        "source_db_path": str(source_path),
        "destination_db_path": str(destination_path),
        "selected_session_count": len(selected_sessions),
        "migrated_session_count": migrated_session_count,
        "migrated_event_count": migrated_event_count,
        "skipped_existing_session_count": skipped_existing_session_count,
    }


def _safe_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_text(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _json_array(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if value in (None, ""):
        return []
    try:
        loaded = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return list(loaded) if isinstance(loaded, list) else []


def _normalized_blockers(value: Any) -> list[str]:
    blockers: list[str] = []
    for item in _json_array(value) if not isinstance(value, list) else value:
        text = _safe_text(item)
        if text and text not in blockers:
            blockers.append(text)
    return blockers


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


@lru_cache(maxsize=8)
def _trusted_truth_horizon_for_db(db_path_hint: str) -> Optional[date]:
    try:
        resolved_db_path = str(db_path_hint or "").strip() or None
        latest_quote_at_utc = str(
            HistoricalOptionsStore(resolved_db_path).snapshot_summary(
                DAILY_SNAPSHOT_KIND,
                trusted_only=True,
            ).get("latest_quote_at_utc")
            or ""
        ).strip()
    except Exception:
        return None
    return _parse_date(latest_quote_at_utc)


def _trusted_truth_horizon() -> Optional[date]:
    return _trusted_truth_horizon_for_db(str(os.getenv("HISTORICAL_OPTIONS_DB_PATH") or ""))


def _closed_tracked_positions_snapshot() -> tuple[bool, list[dict[str, Any]]]:
    repo = create_positions_repository(os.getenv("DATABASE_URL"))
    if not getattr(repo, "is_available", False):
        return False, []
    try:
        return True, list(repo.list_positions("closed"))
    except Exception:
        return False, []


def _realized_position_summary(
    positions: list[dict[str, Any]],
    *,
    cohort_id: str | None = None,
) -> dict[str, Any]:
    normalized_cohort = str(cohort_id or "").strip() or None
    gross_realized_pnl_usd = 0.0
    net_realized_pnl_usd = 0.0
    gross_notional_usd = 0.0
    net_notional_usd = 0.0
    closed_position_count = 0
    for position in list(positions or []):
        source = dict(position.get("source_pick_snapshot") or {})
        position_cohort = str(
            position.get("cohort_id")
            or source.get("cohort_id")
            or source.get("profit_candidate_id")
            or ""
        ).strip() or None
        if normalized_cohort is not None and position_cohort != normalized_cohort:
            continue
        entry_execution_price = execution_safe_float(
            position.get("entry_execution_price")
            if position.get("entry_execution_price") is not None
            else position.get("entry_option_price")
        )
        gross_pnl_usd = execution_safe_float(position.get("gross_pnl_usd"))
        net_pnl_usd = execution_safe_float(position.get("net_pnl_usd"))
        contracts = _safe_int(position.get("contracts")) or 0
        if (
            entry_execution_price is None
            or entry_execution_price <= 0
            or contracts <= 0
            or gross_pnl_usd is None
            or net_pnl_usd is None
        ):
            continue
        closed_position_count += 1
        gross_realized_pnl_usd += float(gross_pnl_usd)
        net_realized_pnl_usd += float(net_pnl_usd)
        entry_notional_usd = float(entry_execution_price) * 100.0 * int(contracts)
        gross_notional_usd += entry_notional_usd
        net_notional_usd += entry_notional_usd
    gross_realized_pnl_pct = (
        round((gross_realized_pnl_usd / gross_notional_usd) * 100.0, 4)
        if gross_notional_usd > 0
        else None
    )
    net_realized_pnl_pct = (
        round((net_realized_pnl_usd / net_notional_usd) * 100.0, 4)
        if net_notional_usd > 0
        else None
    )
    return {
        "closed_position_count": closed_position_count,
        "gross_realized_pnl_usd": round(gross_realized_pnl_usd, 4),
        "net_realized_pnl_usd": round(net_realized_pnl_usd, 4),
        "gross_realized_pnl_pct": gross_realized_pnl_pct,
        "net_realized_pnl_pct": net_realized_pnl_pct,
    }


def _measurement_status_for_event(
    event: dict[str, Any],
    *,
    trusted_truth_horizon: date | None,
    base_blockers: list[str] | None = None,
) -> str:
    def _event_value(key: str) -> Any:
        if hasattr(event, "get"):
            return event.get(key)
        try:
            return event[key]
        except Exception:
            return None

    blockers = [str(item or "").strip() for item in list(base_blockers or []) if str(item or "").strip()]
    if blockers:
        return INELIGIBLE_STATUS
    existing_status = str(_event_value("eligibility_status") or "").strip().lower()
    if existing_status == PENDING_TRUTH_STATUS:
        return PENDING_TRUTH_STATUS
    if existing_status and existing_status != ELIGIBLE_STATUS:
        return existing_status
    entry_date = _parse_date(
        _event_value("entry_date")
        or _event_value("quote_time_et")
        or _event_value("recorded_at_utc")
    )
    if trusted_truth_horizon and entry_date and entry_date > trusted_truth_horizon:
        return PENDING_TRUTH_STATUS
    return ELIGIBLE_STATUS if existing_status == ELIGIBLE_STATUS or existing_status == "" else existing_status


def _normalize_evidence_class(
    value: Any,
    *,
    source_label: str | None = None,
) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {
        LIVE_PRODUCTION_EVIDENCE_CLASS,
        MANUAL_OBSERVATION_EVIDENCE_CLASS,
        FIXTURE_SMOKE_EVIDENCE_CLASS,
        UNIT_TEST_EVIDENCE_CLASS,
        E2E_TEST_EVIDENCE_CLASS,
        RESEARCH_BACKFILL_EVIDENCE_CLASS,
    }:
        return normalized
    label = str(source_label or "").strip().lower()
    if "manual" in label or "observation" in label:
        return MANUAL_OBSERVATION_EVIDENCE_CLASS
    if "fixture" in label or "smoke" in label:
        return FIXTURE_SMOKE_EVIDENCE_CLASS
    if "unit_test" in label or "pytest" in label or "unittest" in label:
        return UNIT_TEST_EVIDENCE_CLASS
    if "e2e" in label:
        return E2E_TEST_EVIDENCE_CLASS
    if "research" in label or "backfill" in label:
        return RESEARCH_BACKFILL_EVIDENCE_CLASS
    return LIVE_PRODUCTION_EVIDENCE_CLASS


def _default_run_mode(evidence_class: str) -> str:
    if evidence_class == LIVE_PRODUCTION_EVIDENCE_CLASS:
        return "live"
    if evidence_class == MANUAL_OBSERVATION_EVIDENCE_CLASS:
        return "observation"
    if evidence_class == FIXTURE_SMOKE_EVIDENCE_CLASS:
        return "fixture"
    if evidence_class in {UNIT_TEST_EVIDENCE_CLASS, E2E_TEST_EVIDENCE_CLASS}:
        return "test"
    return "research"


def _normalize_quote_freshness_status(value: Any) -> Optional[str]:
    normalized = str(value or "").strip().lower()
    if normalized in {"fresh", "observed", "stale", "unknown"}:
        return normalized
    if "stale" in normalized:
        return "stale"
    if normalized in {"ok", "ready", "live", "current"} or "fresh" in normalized:
        return "fresh"
    if normalized:
        return "observed"
    return None


def _quote_freshness_status_from_pick(pick: dict[str, Any], fallback: str | None = None) -> str:
    explicit = _normalize_quote_freshness_status(
        pick.get("quote_freshness_status")
        or pick.get("options_snapshot_status")
        or pick.get("option_chain_status")
        or fallback
    )
    if explicit:
        return explicit
    if _safe_text(pick.get("quote_time_et")):
        return "observed"
    return "unknown"


def _session_quote_freshness_status(
    picks: list[dict[str, Any]],
    explicit: Any = None,
) -> str:
    normalized = _normalize_quote_freshness_status(explicit)
    if normalized:
        return normalized
    statuses = {
        _quote_freshness_status_from_pick(pick)
        for pick in list(picks or [])
    }
    if not statuses:
        return "unknown"
    if "stale" in statuses:
        return "stale"
    if statuses == {"fresh"}:
        return "fresh"
    if statuses.issubset({"fresh", "observed"}):
        return "observed"
    return "unknown"


def _provenance_for_snapshot(
    scan_snapshot: dict[str, Any],
    *,
    source_label: str,
    recorded_at_utc: str,
) -> dict[str, Any]:
    evidence_class = _normalize_evidence_class(
        scan_snapshot.get("evidence_class"),
        source_label=source_label,
    )
    run_mode = _safe_text(scan_snapshot.get("run_mode")) or _default_run_mode(evidence_class)
    run_id = _safe_text(scan_snapshot.get("run_id")) or f"{source_label}:{recorded_at_utc}"
    is_fixture = bool(
        scan_snapshot.get("is_fixture")
        if scan_snapshot.get("is_fixture") is not None
        else evidence_class in {
            FIXTURE_SMOKE_EVIDENCE_CLASS,
            UNIT_TEST_EVIDENCE_CLASS,
            E2E_TEST_EVIDENCE_CLASS,
        }
    )
    policy = dict(scan_snapshot.get("policy") or {})
    policy_artifact_id = _safe_text(
        scan_snapshot.get("policy_artifact_id")
        or policy.get("artifact_id")
        or policy.get("policy_artifact_id")
        or scan_snapshot.get("champion_manifest_path")
    )
    return {
        "recorded_at_utc": recorded_at_utc,
        "run_id": run_id,
        "run_mode": run_mode,
        "evidence_class": evidence_class,
        "is_fixture": is_fixture,
        "policy_artifact_id": policy_artifact_id,
        "quote_freshness_status": _session_quote_freshness_status(
            list(scan_snapshot.get("picks") or []),
            scan_snapshot.get("quote_freshness_status"),
        ),
    }


def _db_path_for_provenance(provenance: dict[str, Any]) -> Path:
    if (
        _normalize_evidence_class(provenance.get("evidence_class"))
        == LIVE_PRODUCTION_EVIDENCE_CLASS
        and not bool(provenance.get("is_fixture"))
    ):
        return authoritative_forward_ledger_db_path()
    return archive_forward_ledger_db_path()


def _eligibility_for_pick(
    pick: dict[str, Any],
    *,
    provenance: dict[str, Any],
    policy_applied: bool,
    truth_source: str | None,
    promotion_status: str | None,
    positions_available: bool,
    positions_error: str | None,
) -> tuple[str, list[str], str]:
    blockers: list[str] = []
    quote_freshness_status = _quote_freshness_status_from_pick(
        pick,
        fallback=provenance.get("quote_freshness_status"),
    )
    quote_basis = _safe_text(pick.get("quote_basis"))
    derived_execution = executable_option_price(
        side="entry",
        bid=pick.get("bid"),
        ask=pick.get("ask"),
        last=pick.get("last"),
        model_price=pick.get("premium") if quote_basis == "model" else None,
        slippage_pct=0.0,
    )
    entry_execution_price = execution_safe_float(pick.get("entry_execution_price")) or derived_execution.get("execution_price")
    profitability_blockers = _normalized_blockers(
        pick.get("profitability_blockers")
        if pick.get("profitability_blockers") is not None
        else derived_execution.get("profitability_blockers")
    )
    if provenance.get("evidence_class") != LIVE_PRODUCTION_EVIDENCE_CLASS:
        blockers.append("non_live_evidence_class")
    if provenance.get("is_fixture"):
        blockers.append("fixture_or_test_traffic")
    if not policy_applied:
        blockers.append("policy_not_applied")
    if not truth_source:
        blockers.append("missing_truth_source")
    if not promotion_status:
        blockers.append("missing_promotion_status")
    if not positions_available:
        blockers.append("tracked_positions_unavailable")
    if positions_error:
        blockers.append("positions_error")
    if quote_freshness_status == "stale":
        blockers.append("stale_quote_freshness")
    elif quote_freshness_status == "unknown":
        blockers.append("unknown_quote_freshness")
    if entry_execution_price is None:
        blockers.extend(profitability_blockers or ["missing_executable_entry_quote"])
    if not _safe_text(_pick_contract_symbol(pick)):
        blockers.append("missing_contract_symbol")
    deduped_blockers = _normalized_blockers(blockers)
    if not deduped_blockers:
        trusted_truth_horizon = _trusted_truth_horizon()
        entry_date = _parse_date(
            pick.get("quote_time_et")
            or pick.get("entry_date")
            or provenance.get("recorded_at_utc")
        )
        if trusted_truth_horizon and entry_date and entry_date > trusted_truth_horizon:
            return PENDING_TRUTH_STATUS, ["entry_date_beyond_trusted_truth_horizon"], quote_freshness_status
    return (
        ELIGIBLE_STATUS if not deduped_blockers else INELIGIBLE_STATUS,
        deduped_blockers,
        quote_freshness_status,
    )


def _session_eligibility(
    picks: list[dict[str, Any]],
    *,
    provenance: dict[str, Any],
    policy_applied: bool,
    truth_source: str | None,
    promotion_status: str | None,
    positions_available: bool,
    positions_error: str | None,
) -> tuple[str, list[str]]:
    blockers: list[str] = []
    if provenance.get("evidence_class") != LIVE_PRODUCTION_EVIDENCE_CLASS:
        blockers.append("non_live_evidence_class")
    if provenance.get("is_fixture"):
        blockers.append("fixture_or_test_traffic")
    if not policy_applied:
        blockers.append("policy_not_applied")
    if not truth_source:
        blockers.append("missing_truth_source")
    if not promotion_status:
        blockers.append("missing_promotion_status")
    if not positions_available:
        blockers.append("tracked_positions_unavailable")
    if positions_error:
        blockers.append("positions_error")
    if provenance.get("quote_freshness_status") == "stale":
        blockers.append("stale_quote_freshness")
    elif provenance.get("quote_freshness_status") == "unknown":
        blockers.append("unknown_quote_freshness")
    if not picks:
        blockers.append("no_scan_picks")
    elif not any(_safe_text(_pick_contract_symbol(pick)) for pick in picks):
        blockers.append("missing_contract_symbol")
    deduped_blockers = _normalized_blockers(blockers)
    if not deduped_blockers:
        trusted_truth_horizon = _trusted_truth_horizon()
        pending_dates = [
            _parse_date(
                pick.get("quote_time_et")
                or pick.get("entry_date")
                or provenance.get("recorded_at_utc")
            )
            for pick in list(picks or [])
        ]
        pending_dates = [value for value in pending_dates if value is not None]
        if trusted_truth_horizon and pending_dates and min(pending_dates) > trusted_truth_horizon:
            return PENDING_TRUTH_STATUS, ["entry_date_beyond_trusted_truth_horizon"]
    return ELIGIBLE_STATUS if not deduped_blockers else INELIGIBLE_STATUS, deduped_blockers


def _normalized_scan_funnel(value: Any) -> dict[str, Any]:
    payload = dict(value or {})
    return {
        "raw_candidates": int(payload.get("raw_candidates") or 0),
        "post_policy_visible": int(payload.get("post_policy_visible") or 0),
        "post_guardrails_visible": int(payload.get("post_guardrails_visible") or 0),
        "returned_picks": int(payload.get("returned_picks") or 0),
        "policy_filtered_out": int(payload.get("policy_filtered_out") or 0),
        "guardrail_filtered_out": int(payload.get("guardrail_filtered_out") or 0),
        "final_trimmed": int(payload.get("final_trimmed") or 0),
        "policy_counts": {
            str(key): int(count or 0)
            for key, count in dict(payload.get("policy_counts") or {}).items()
        },
        "guardrail_counts": {
            str(key): int(count or 0)
            for key, count in dict(payload.get("guardrail_counts") or {}).items()
        },
        "policy_applied": bool(payload.get("policy_applied")),
        "policy_fail_closed": bool(payload.get("policy_fail_closed")),
        "include_blocked_policy_picks": bool(payload.get("include_blocked_policy_picks")),
        "include_blocked_guardrail_picks": bool(payload.get("include_blocked_guardrail_picks")),
        "drop_counts": {
            str(key): int(count or 0)
            for key, count in dict(payload.get("drop_counts") or {}).items()
        },
        "symbol_diagnostics": dict(payload.get("symbol_diagnostics") or {}),
    }


def _accumulate_scan_funnel(target: dict[str, Any], value: Any) -> dict[str, Any]:
    current = _normalized_scan_funnel(value)
    for key in (
        "raw_candidates",
        "post_policy_visible",
        "post_guardrails_visible",
        "returned_picks",
        "policy_filtered_out",
        "guardrail_filtered_out",
        "final_trimmed",
    ):
        target[key] = int(target.get(key) or 0) + int(current.get(key) or 0)
    policy_counts = dict(target.get("policy_counts") or {})
    for key, count in dict(current.get("policy_counts") or {}).items():
        policy_counts[str(key)] = policy_counts.get(str(key), 0) + int(count or 0)
    target["policy_counts"] = policy_counts
    guardrail_counts = dict(target.get("guardrail_counts") or {})
    for key, count in dict(current.get("guardrail_counts") or {}).items():
        guardrail_counts[str(key)] = guardrail_counts.get(str(key), 0) + int(count or 0)
    target["guardrail_counts"] = guardrail_counts
    target["policy_applied"] = bool(target.get("policy_applied")) or bool(current.get("policy_applied"))
    target["policy_fail_closed"] = bool(target.get("policy_fail_closed")) or bool(current.get("policy_fail_closed"))
    target["include_blocked_policy_picks"] = bool(target.get("include_blocked_policy_picks")) or bool(current.get("include_blocked_policy_picks"))
    target["include_blocked_guardrail_picks"] = bool(target.get("include_blocked_guardrail_picks")) or bool(current.get("include_blocked_guardrail_picks"))
    drop_counts = dict(target.get("drop_counts") or {})
    for key, count in dict(current.get("drop_counts") or {}).items():
        drop_counts[str(key)] = drop_counts.get(str(key), 0) + int(count or 0)
    target["drop_counts"] = drop_counts
    existing_diag = dict(target.get("symbol_diagnostics") or {})
    current_diag = dict(current.get("symbol_diagnostics") or {})
    for symbol, diag in current_diag.items():
        if symbol not in existing_diag:
            existing_diag[symbol] = diag
    target["symbol_diagnostics"] = existing_diag
    return target


def _session_scan_funnel(notes: dict[str, Any], cohort_id: str | None) -> Optional[dict[str, Any]]:
    if cohort_id:
        cohort_funnels = dict(notes.get("cohort_funnels") or {})
        if cohort_id in cohort_funnels:
            return _normalized_scan_funnel(cohort_funnels.get(cohort_id))
    if notes.get("scan_funnel") is not None:
        return _normalized_scan_funnel(notes.get("scan_funnel"))
    return None


def _infer_starvation_stage(funnel: Optional[dict[str, Any]]) -> Optional[str]:
    current = _normalized_scan_funnel(funnel or {})
    if current.get("policy_fail_closed"):
        return "policy_fail_closed"
    if int(current.get("raw_candidates") or 0) <= 0:
        return "no_raw_candidates"
    if int(current.get("post_policy_visible") or 0) <= 0:
        return "policy_filtered_all"
    if int(current.get("post_guardrails_visible") or 0) <= 0:
        return "guardrails_filtered_all"
    if int(current.get("returned_picks") or 0) <= 0:
        return "final_selection_trim"
    return None


def _pick_contract_symbol(pick: dict[str, Any]) -> Optional[str]:
    return (
        pick.get("contract_symbol")
        or pick.get("contractSymbol")
        or pick.get("option_contract_symbol")
    )


def _pick_option_type(pick: dict[str, Any]) -> Optional[str]:
    option_type = (
        pick.get("option_type")
        or pick.get("direction")
        or pick.get("type")
        or pick.get("prediction_type")
    )
    normalized = str(option_type or "").strip().lower()
    return normalized or None


def _pick_playbook_id(value: Any) -> Optional[str]:
    if isinstance(value, dict):
        return _safe_text(value.get("id") or value.get("playbook_id") or value.get("label"))
    return _safe_text(value)


def build_forward_scan_snapshot(
    *,
    picks: list[dict[str, Any]],
    policy_applied: bool,
    policy: Optional[dict[str, Any]],
    policy_error: Any = None,
    playbook: Any = None,
    truth_lane: Optional[str] = None,
    scan_funnel: Any = None,
    policy_decision_counts: Any = None,
    guardrail_decision_counts: Any = None,
    candidate_count: Any = None,
    returned_count: Any = None,
    playbook_exit_audit: Any = None,
    playbook_exit_audit_error: Any = None,
    exposure_snapshot: Any = None,
    cohort_snapshots: Optional[list[dict[str, Any]]] = None,
    cohort_funnels: Optional[dict[str, Any]] = None,
    cohort_count: Any = None,
    cohort_ids: Optional[list[str]] = None,
    champion_manifest_path: Optional[str] = None,
    positions_error: Optional[str] = None,
    run_id: Optional[str] = None,
    run_mode: Optional[str] = None,
    evidence_class: Optional[str] = None,
    is_fixture: Optional[bool] = None,
    policy_artifact_id: Optional[str] = None,
    quote_freshness_status: Optional[str] = None,
    symbol_diagnostics: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    snapshot = {
        "picks": list(picks or []),
        "policy_applied": bool(policy_applied),
        "policy": dict(policy or {}),
        "policy_error": policy_error,
        "playbook_exit_audit": playbook_exit_audit,
        "playbook_exit_audit_error": playbook_exit_audit_error,
        "policy_decision_counts": dict(policy_decision_counts or {}),
        "guardrail_decision_counts": dict(guardrail_decision_counts or {}),
        "candidate_count": int(candidate_count or len(picks or [])),
        "returned_count": int(returned_count if returned_count is not None else len(picks or [])),
        "scan_funnel": _normalized_scan_funnel(scan_funnel),
        "playbook": playbook,
        "truth_lane": truth_lane,
        "exposure_snapshot": exposure_snapshot,
        "cohort_snapshots": list(cohort_snapshots or []),
        "cohort_funnels": {
            str(key): _normalized_scan_funnel(value)
            for key, value in dict(cohort_funnels or {}).items()
            if str(key).strip()
        },
        "cohort_count": int(cohort_count or len(cohort_snapshots or [])),
        "cohort_ids": [str(item).strip() for item in list(cohort_ids or []) if str(item).strip()],
        "champion_manifest_path": champion_manifest_path,
        "run_id": _safe_text(run_id),
        "run_mode": _safe_text(run_mode),
        "evidence_class": _safe_text(evidence_class),
        "is_fixture": is_fixture if is_fixture is not None else None,
        "policy_artifact_id": _safe_text(policy_artifact_id),
        "quote_freshness_status": _normalize_quote_freshness_status(quote_freshness_status),
        "symbol_diagnostics": dict(symbol_diagnostics or {}),
    }
    if positions_error:
        snapshot["positions_error"] = str(positions_error)
    return snapshot


def _tracked_position_matches_pick(
    pick: dict[str, Any],
    tracked_positions: list[dict[str, Any]],
) -> bool:
    # 1. Prefer explicit scan provenance ids when both pick and position have them
    pick_session_id = pick.get("source_scan_session_id")
    pick_event_key = pick.get("source_scan_event_key")
    if pick_session_id is not None and pick_event_key is not None:
        for position in tracked_positions:
            pos_session_id = position.get("source_scan_session_id")
            pos_event_key = position.get("source_scan_event_key")
            if pos_session_id is not None and pos_event_key is not None:
                if int(pos_session_id) == int(pick_session_id) and str(pos_event_key) == str(pick_event_key):
                    return True

    # 2. Exact contract symbol match
    ticker = str(pick.get("ticker") or "").strip().upper()
    contract_symbol = str(_pick_contract_symbol(pick) or "").strip().upper()
    expiry = str(pick.get("expiry") or "").strip()[:10]
    direction = str(pick.get("direction") or pick.get("type") or "").strip().lower()
    strike = _safe_float(pick.get("strike") if pick.get("strike") is not None else pick.get("strike_est"))
    cohort_id = str(pick.get("cohort_id") or "").strip()

    for position in tracked_positions:
        source = dict(position.get("source_pick_snapshot") or {})
        if cohort_id:
            position_cohort = str(source.get("cohort_id") or position.get("cohort_id") or "").strip()
            if position_cohort != cohort_id:
                continue
        position_contract = str(
            position.get("contract_symbol")
            or source.get("contract_symbol")
            or source.get("contractSymbol")
            or ""
        ).strip().upper()
        if contract_symbol and position_contract and contract_symbol == position_contract:
            return True

    # 3. Fallback heuristic matching
    for position in tracked_positions:
        source = dict(position.get("source_pick_snapshot") or {})
        if cohort_id:
            position_cohort = str(source.get("cohort_id") or position.get("cohort_id") or "").strip()
            if position_cohort != cohort_id:
                continue
        if ticker and str(position.get("ticker") or source.get("ticker") or "").strip().upper() != ticker:
            continue
        position_expiry = str(position.get("expiry") or source.get("expiry") or "").strip()[:10]
        if expiry and position_expiry and expiry != position_expiry:
            continue
        position_direction = str(
            position.get("direction")
            or source.get("direction")
            or source.get("type")
            or ""
        ).strip().lower()
        if direction and position_direction and direction != position_direction:
            continue
        position_strike = _safe_float(
            position.get("strike")
            if position.get("strike") is not None
            else source.get("strike")
            if source.get("strike") is not None
            else source.get("strike_est")
        )
        if strike is not None and position_strike is not None and round(position_strike, 4) != round(strike, 4):
            continue
        return True
    return False


def _pick_outcome_state(
    pick: dict[str, Any],
    tracked_positions: list[dict[str, Any]],
) -> str:
    policy_state = str(pick.get("policy_decision") or pick.get("trade_policy_decision") or "").strip().lower()
    guardrail_state = str(pick.get("guardrail_decision") or "").strip().lower()
    if policy_state == "blocked" or guardrail_state == "blocked":
        return "blocked"
    if tracked_positions and _tracked_position_matches_pick(pick, tracked_positions):
        return "taken"
    return "skipped"


def _event_fields_from_pick(
    pick: dict[str, Any],
    *,
    candidate_rank: int,
    tracked_positions: list[dict[str, Any]],
    provenance: dict[str, Any],
    policy_applied: bool,
    truth_source: str | None,
    promotion_status: str | None,
    positions_available: bool,
    positions_error: str | None,
) -> dict[str, Any]:
    cohort_id = str(pick.get("cohort_id") or "").strip() or None
    cohort_role = str(pick.get("cohort_role") or "").strip() or None
    policy_state = str(
        pick.get("policy_decision")
        or pick.get("trade_policy_decision")
        or ""
    ).strip() or None
    guardrail_state = str(pick.get("guardrail_decision") or "").strip() or None
    quote_basis = _safe_text(pick.get("quote_basis"))
    selection_source = _safe_text(
        pick.get("selection_source") or pick.get("contract_selection_source")
    )
    spread_pct = _safe_float(
        pick.get("spread_pct")
        if pick.get("spread_pct") is not None
        else pick.get("spread_percent")
    )
    option_mid = _safe_float(
        pick.get("mid")
        if pick.get("mid") is not None
        else pick.get("premium")
    )
    derived_execution = executable_option_price(
        side="entry",
        bid=pick.get("bid"),
        ask=pick.get("ask"),
        last=pick.get("last"),
        model_price=pick.get("premium") if quote_basis == "model" else None,
        slippage_pct=0.0,
    )
    entry_execution_price = execution_safe_float(pick.get("entry_execution_price")) or derived_execution.get("execution_price")
    entry_execution_basis = _safe_text(pick.get("entry_execution_basis")) or _safe_text(derived_execution.get("execution_basis"))
    entry_fee_total_usd = execution_safe_float(pick.get("entry_fee_total_usd"))
    if entry_fee_total_usd is None and entry_execution_price is not None:
        entry_fee_total_usd = commission_total_usd(contracts=1)
    eligibility_status, eligibility_blockers, quote_freshness_status = _eligibility_for_pick(
        pick,
        provenance=provenance,
        policy_applied=policy_applied,
        truth_source=truth_source,
        promotion_status=promotion_status,
        positions_available=positions_available,
        positions_error=positions_error,
    )
    return {
        "ticker": str(pick.get("ticker") or "").strip().upper() or None,
        "contract_symbol": _pick_contract_symbol(pick),
        "recommendation": policy_state,
        "pricing_source": pick.get("pricing_source") or quote_basis,
        "cohort_id": cohort_id,
        "cohort_role": cohort_role,
        "policy_state": policy_state,
        "guardrail_state": guardrail_state,
        "expiry": _safe_text(pick.get("expiry")),
        "strike": _safe_float(
            pick.get("strike") if pick.get("strike") is not None else pick.get("strike_est")
        ),
        "option_type": _pick_option_type(pick),
        "quote_time_et": _safe_text(pick.get("quote_time_et")),
        "quote_basis": quote_basis,
        "underlying_price_at_selection": _safe_float(
            pick.get("underlying_price_at_selection")
            if pick.get("underlying_price_at_selection") is not None
            else (
                pick.get("stock_price")
                if pick.get("stock_price") is not None
                else pick.get("entry_price")
            )
        ),
        "selection_source": selection_source,
        "promotion_class": _safe_text(pick.get("promotion_class")),
        "candidate_rank": _safe_int(pick.get("candidate_rank")) or int(candidate_rank),
        "option_bid": _safe_float(pick.get("bid")),
        "option_ask": _safe_float(pick.get("ask")),
        "option_mid": option_mid,
        "option_spread_pct": spread_pct,
        "option_iv": _safe_float(
            pick.get("iv_percentile")
            if pick.get("iv_percentile") is not None
            else (
                pick.get("iv_pct")
                if pick.get("iv_pct") is not None
                else pick.get("iv_rank")
            )
        ),
        "option_delta": _safe_float(
            pick.get("delta")
            if pick.get("delta") is not None
            else pick.get("delta_est")
        ),
        "option_dte": _safe_int(pick.get("dte")),
        "entry_execution_price": entry_execution_price,
        "entry_execution_basis": entry_execution_basis,
        "entry_fee_total_usd": entry_fee_total_usd,
        "exit_execution_price": None,
        "exit_execution_basis": None,
        "gross_pnl_pct": None,
        "net_pnl_pct": None,
        "gross_pnl_usd": None,
        "net_pnl_usd": None,
        "fee_total_usd": entry_fee_total_usd,
        "outcome_state": _pick_outcome_state(pick, tracked_positions),
        "run_id": provenance.get("run_id"),
        "run_mode": provenance.get("run_mode"),
        "evidence_class": provenance.get("evidence_class"),
        "is_fixture": bool(provenance.get("is_fixture")),
        "policy_artifact_id": provenance.get("policy_artifact_id"),
        "quote_freshness_status": quote_freshness_status,
        "eligibility_status": eligibility_status,
        "eligibility_blockers": json.dumps(eligibility_blockers),
        "payload_json": json.dumps(pick),
    }


def _insert_forward_event(
    cursor: sqlite3.Cursor,
    *,
    session_id: int,
    event_type: str,
    event_key: Optional[str],
    payload_json: str,
    ticker: Optional[str] = None,
    contract_symbol: Optional[str] = None,
    recommendation: Optional[str] = None,
    pricing_source: Optional[str] = None,
    cohort_id: Optional[str] = None,
    cohort_role: Optional[str] = None,
    policy_state: Optional[str] = None,
    guardrail_state: Optional[str] = None,
    expiry: Optional[str] = None,
    strike: Optional[float] = None,
    option_type: Optional[str] = None,
    quote_time_et: Optional[str] = None,
    quote_basis: Optional[str] = None,
    underlying_price_at_selection: Optional[float] = None,
    selection_source: Optional[str] = None,
    promotion_class: Optional[str] = None,
    candidate_rank: Optional[int] = None,
    option_bid: Optional[float] = None,
    option_ask: Optional[float] = None,
    option_mid: Optional[float] = None,
    option_spread_pct: Optional[float] = None,
    option_iv: Optional[float] = None,
    option_delta: Optional[float] = None,
    option_dte: Optional[int] = None,
    entry_execution_price: Optional[float] = None,
    entry_execution_basis: Optional[str] = None,
    entry_fee_total_usd: Optional[float] = None,
    exit_execution_price: Optional[float] = None,
    exit_execution_basis: Optional[str] = None,
    gross_pnl_pct: Optional[float] = None,
    net_pnl_pct: Optional[float] = None,
    gross_pnl_usd: Optional[float] = None,
    net_pnl_usd: Optional[float] = None,
    fee_total_usd: Optional[float] = None,
    outcome_state: Optional[str] = None,
    run_id: Optional[str] = None,
    run_mode: Optional[str] = None,
    evidence_class: Optional[str] = None,
    is_fixture: Optional[bool] = None,
    policy_artifact_id: Optional[str] = None,
    quote_freshness_status: Optional[str] = None,
    eligibility_status: Optional[str] = None,
    eligibility_blockers: Optional[str] = None,
    position_id: Optional[int] = None,
    contracts: Optional[int] = None,
    source_scan_session_id: Optional[int] = None,
    source_scan_event_key: Optional[str] = None,
    source_scan_run_id: Optional[str] = None,
) -> None:
    columns = [
        "session_id",
        "event_type",
        "event_key",
        "ticker",
        "contract_symbol",
        "recommendation",
        "pricing_source",
        "cohort_id",
        "cohort_role",
        "policy_state",
        "guardrail_state",
        "expiry",
        "strike",
        "option_type",
        "quote_time_et",
        "quote_basis",
        "underlying_price_at_selection",
        "selection_source",
        "promotion_class",
        "candidate_rank",
        "option_bid",
        "option_ask",
        "option_mid",
        "option_spread_pct",
        "option_iv",
        "option_delta",
        "option_dte",
        "entry_execution_price",
        "entry_execution_basis",
        "entry_fee_total_usd",
        "exit_execution_price",
        "exit_execution_basis",
        "gross_pnl_pct",
        "net_pnl_pct",
        "gross_pnl_usd",
        "net_pnl_usd",
        "fee_total_usd",
        "outcome_state",
        "run_id",
        "run_mode",
        "evidence_class",
        "is_fixture",
        "policy_artifact_id",
        "quote_freshness_status",
        "eligibility_status",
        "eligibility_blockers",
        "position_id",
        "contracts",
        "source_scan_session_id",
        "source_scan_event_key",
        "source_scan_run_id",
        "payload_json",
    ]
    values = (
        int(session_id),
        str(event_type),
        event_key,
        ticker,
        contract_symbol,
        recommendation,
        pricing_source,
        cohort_id,
        cohort_role,
        policy_state,
        guardrail_state,
        expiry,
        strike,
        option_type,
        quote_time_et,
        quote_basis,
        underlying_price_at_selection,
        selection_source,
        promotion_class,
        candidate_rank,
        option_bid,
        option_ask,
        option_mid,
        option_spread_pct,
        option_iv,
        option_delta,
        option_dte,
        entry_execution_price,
        entry_execution_basis,
        entry_fee_total_usd,
        exit_execution_price,
        exit_execution_basis,
        gross_pnl_pct,
        net_pnl_pct,
        gross_pnl_usd,
        net_pnl_usd,
        fee_total_usd,
        outcome_state,
        run_id,
        run_mode,
        evidence_class,
        int(bool(is_fixture)),
        policy_artifact_id,
        quote_freshness_status,
        eligibility_status,
        eligibility_blockers or "[]",
        position_id,
        contracts,
        source_scan_session_id,
        source_scan_event_key,
        source_scan_run_id,
        payload_json,
    )
    placeholders = ", ".join("?" for _ in columns)
    cursor.execute(
        f"INSERT INTO forward_events ({', '.join(columns)}) VALUES ({placeholders})",
        values,
    )


def _position_review_event_fields(position: dict[str, Any], *, provenance: dict[str, Any]) -> dict[str, Any]:
    latest_review = dict(position.get("latest_review") or {})
    source = dict(position.get("source_pick_snapshot") or {})
    return {
        "ticker": str(position.get("ticker") or source.get("ticker") or "").upper() or None,
        "contract_symbol": (
            position.get("contract_symbol")
            or source.get("contract_symbol")
            or source.get("contractSymbol")
        ),
        "recommendation": latest_review.get("recommendation"),
        "pricing_source": latest_review.get("pricing_source") or source.get("quote_basis"),
        "cohort_id": _safe_text(source.get("cohort_id")),
        "cohort_role": _safe_text(source.get("cohort_role")),
        "policy_state": _safe_text(source.get("policy_decision") or source.get("trade_policy_decision")),
        "guardrail_state": _safe_text(source.get("guardrail_decision")),
        "expiry": _safe_text(source.get("expiry")),
        "strike": _safe_float(
            source.get("strike") if source.get("strike") is not None else source.get("strike_est")
        ),
        "option_type": _pick_option_type(source),
        "quote_time_et": _safe_text(source.get("quote_time_et")),
        "quote_basis": _safe_text(source.get("quote_basis")),
        "underlying_price_at_selection": _safe_float(
            source.get("underlying_price_at_selection")
            if source.get("underlying_price_at_selection") is not None
            else (
                source.get("stock_price")
                if source.get("stock_price") is not None
                else source.get("entry_price")
            )
        ),
        "selection_source": _safe_text(
            source.get("selection_source") or source.get("contract_selection_source")
        ),
        "promotion_class": _safe_text(source.get("promotion_class")),
        "candidate_rank": _safe_int(source.get("candidate_rank")),
        "option_bid": _safe_float(source.get("bid")),
        "option_ask": _safe_float(source.get("ask")),
        "option_mid": _safe_float(
            source.get("mid") if source.get("mid") is not None else source.get("premium")
        ),
        "option_spread_pct": _safe_float(
            source.get("spread_pct")
            if source.get("spread_pct") is not None
            else source.get("spread_percent")
        ),
        "option_iv": _safe_float(
            source.get("iv_percentile")
            if source.get("iv_percentile") is not None
            else (
                source.get("iv_pct")
                if source.get("iv_pct") is not None
                else source.get("iv_rank")
            )
        ),
        "option_delta": _safe_float(
            source.get("delta")
            if source.get("delta") is not None
            else source.get("delta_est")
        ),
        "option_dte": _safe_int(source.get("dte")),
        "entry_execution_price": execution_safe_float(
            latest_review.get("entry_execution_price")
            if latest_review.get("entry_execution_price") is not None
            else position.get("entry_execution_price")
        ),
        "entry_execution_basis": _safe_text(
            latest_review.get("entry_execution_basis")
            or position.get("entry_execution_basis")
        ),
        "entry_fee_total_usd": execution_safe_float(position.get("entry_fee_total_usd")),
        "exit_execution_price": execution_safe_float(
            latest_review.get("exit_execution_price")
            if latest_review.get("exit_execution_price") is not None
            else position.get("exit_execution_price")
        ),
        "exit_execution_basis": _safe_text(
            latest_review.get("exit_execution_basis")
            or position.get("exit_execution_basis")
        ),
        "gross_pnl_pct": execution_safe_float(
            latest_review.get("gross_pnl_pct")
            if latest_review.get("gross_pnl_pct") is not None
            else position.get("gross_pnl_pct")
        ),
        "net_pnl_pct": execution_safe_float(
            latest_review.get("net_pnl_pct")
            if latest_review.get("net_pnl_pct") is not None
            else position.get("net_pnl_pct")
        ),
        "gross_pnl_usd": execution_safe_float(
            latest_review.get("gross_pnl_usd")
            if latest_review.get("gross_pnl_usd") is not None
            else position.get("gross_pnl_usd")
        ),
        "net_pnl_usd": execution_safe_float(
            latest_review.get("net_pnl_usd")
            if latest_review.get("net_pnl_usd") is not None
            else position.get("net_pnl_usd")
        ),
        "fee_total_usd": execution_safe_float(
            latest_review.get("fee_total_usd")
            if latest_review.get("fee_total_usd") is not None
            else position.get("fee_total_usd")
        ),
        "outcome_state": _safe_text(position.get("status")),
        "run_id": provenance.get("run_id"),
        "run_mode": provenance.get("run_mode"),
        "evidence_class": provenance.get("evidence_class"),
        "is_fixture": bool(provenance.get("is_fixture")),
        "policy_artifact_id": provenance.get("policy_artifact_id"),
        "quote_freshness_status": _quote_freshness_status_from_pick(source, fallback=provenance.get("quote_freshness_status")),
        "eligibility_status": provenance.get("eligibility_status"),
        "eligibility_blockers": json.dumps(_normalized_blockers(provenance.get("eligibility_blockers"))),
        "payload_json": json.dumps(position),
    }


def record_forward_snapshot(
    *,
    scan_snapshot: dict[str, Any],
    reviewed_positions: list[dict[str, Any]],
    tracked_positions: Optional[list[dict[str, Any]]] = None,
    source_label: str = "manual_snapshot",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    recorded_at_utc = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    normalized_source_label = str(source_label or "manual_snapshot").strip() or "manual_snapshot"

    picks = list(scan_snapshot.get("picks") or [])
    policy = dict(scan_snapshot.get("policy") or {})
    playbook = str((scan_snapshot.get("playbook") or {}).get("id") or scan_snapshot.get("playbook") or "")
    tracked = list(tracked_positions or [])
    provenance = _provenance_for_snapshot(
        scan_snapshot,
        source_label=normalized_source_label,
        recorded_at_utc=recorded_at_utc,
    )
    path = init_forward_ledger(db_path or _db_path_for_provenance(provenance))
    positions_available = tracked_positions is not None
    truth_source = _safe_text(policy.get("truth_source"))
    promotion_status = _safe_text(policy.get("promotion_status"))
    session_eligibility_status, session_eligibility_blockers = _session_eligibility(
        picks,
        provenance=provenance,
        policy_applied=bool(scan_snapshot.get("policy_applied")),
        truth_source=truth_source,
        promotion_status=promotion_status,
        positions_available=positions_available,
        positions_error=_safe_text(scan_snapshot.get("positions_error")),
    )
    provenance["eligibility_status"] = session_eligibility_status
    provenance["eligibility_blockers"] = session_eligibility_blockers
    notes = {
        "policy_applied": bool(scan_snapshot.get("policy_applied")),
        "policy_error": scan_snapshot.get("policy_error"),
        "truth_source": truth_source,
        "promotion_status": promotion_status,
        "truth_lane": scan_snapshot.get("truth_lane"),
        "candidate_count": scan_snapshot.get("candidate_count"),
        "returned_count": scan_snapshot.get("returned_count"),
        "guardrail_decision_counts": scan_snapshot.get("guardrail_decision_counts"),
        "policy_decision_counts": scan_snapshot.get("policy_decision_counts"),
        "positions_available": positions_available,
        "champion_manifest_path": scan_snapshot.get("champion_manifest_path"),
        "cohort_count": scan_snapshot.get("cohort_count"),
        "requested_cohort_ids": list(scan_snapshot.get("cohort_ids") or []),
        "scan_funnel": _normalized_scan_funnel(scan_snapshot.get("scan_funnel")),
        "cohort_funnels": {
            str(key): _normalized_scan_funnel(value)
            for key, value in dict(scan_snapshot.get("cohort_funnels") or {}).items()
            if str(key).strip()
        },
        "positions_error": scan_snapshot.get("positions_error"),
        "symbol_diagnostics": dict(scan_snapshot.get("symbol_diagnostics") or {}),
        "run_id": provenance["run_id"],
        "run_mode": provenance["run_mode"],
        "evidence_class": provenance["evidence_class"],
        "is_fixture": provenance["is_fixture"],
        "policy_artifact_id": provenance["policy_artifact_id"],
        "quote_freshness_status": provenance["quote_freshness_status"],
        "eligibility_status": provenance["eligibility_status"],
        "eligibility_blockers": list(provenance["eligibility_blockers"]),
    }

    taken_count = 0
    skipped_count = 0
    blocked_count = 0
    cohort_ids: set[str] = set()

    with closing(sqlite3.connect(path)) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO forward_sessions (
                recorded_at_utc,
                source_label,
                playbook,
                truth_source,
                promotion_status,
                scan_picks_count,
                reviewed_positions_count,
                notes_json,
                run_id,
                run_mode,
                evidence_class,
                is_fixture,
                policy_artifact_id,
                quote_freshness_status,
                eligibility_status,
                eligibility_blockers
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                recorded_at_utc,
                normalized_source_label,
                playbook or None,
                truth_source,
                promotion_status,
                len(picks),
                len(reviewed_positions),
                json.dumps(notes),
                provenance["run_id"],
                provenance["run_mode"],
                provenance["evidence_class"],
                int(bool(provenance["is_fixture"])),
                provenance["policy_artifact_id"],
                provenance["quote_freshness_status"],
                provenance["eligibility_status"],
                json.dumps(provenance["eligibility_blockers"]),
            ),
        )
        session_id = int(cursor.lastrowid)

        _insert_forward_event(
            cursor,
            session_id=session_id,
            event_type="scan_snapshot",
            event_key=playbook or "scan",
            run_id=provenance["run_id"],
            run_mode=provenance["run_mode"],
            evidence_class=provenance["evidence_class"],
            is_fixture=provenance["is_fixture"],
            policy_artifact_id=provenance["policy_artifact_id"],
            quote_freshness_status=provenance["quote_freshness_status"],
            eligibility_status=provenance["eligibility_status"],
            eligibility_blockers=json.dumps(provenance["eligibility_blockers"]),
            payload_json=json.dumps(scan_snapshot),
        )

        for idx, pick in enumerate(picks, start=1):
            fields = _event_fields_from_pick(
                pick,
                candidate_rank=idx,
                tracked_positions=tracked,
                provenance=provenance,
                policy_applied=bool(scan_snapshot.get("policy_applied")),
                truth_source=truth_source,
                promotion_status=promotion_status,
                positions_available=positions_available,
                positions_error=_safe_text(scan_snapshot.get("positions_error")),
            )
            if fields["cohort_id"]:
                cohort_ids.add(str(fields["cohort_id"]))
            if fields["outcome_state"] == "taken":
                taken_count += 1
            elif fields["outcome_state"] == "blocked":
                blocked_count += 1
            else:
                skipped_count += 1
            event_key = f"rank_{idx}"
            if fields["cohort_id"]:
                event_key = f"{fields['cohort_id']}:{event_key}"
            _insert_forward_event(
                cursor,
                session_id=session_id,
                event_type="scan_pick",
                event_key=event_key,
                **fields,
            )

        if tracked_positions is not None:
            _insert_forward_event(
                cursor,
                session_id=session_id,
                event_type="tracked_positions_snapshot",
                event_key="open_positions",
                run_id=provenance["run_id"],
                run_mode=provenance["run_mode"],
                evidence_class=provenance["evidence_class"],
                is_fixture=provenance["is_fixture"],
                policy_artifact_id=provenance["policy_artifact_id"],
                quote_freshness_status=provenance["quote_freshness_status"],
                eligibility_status=provenance["eligibility_status"],
                eligibility_blockers=json.dumps(provenance["eligibility_blockers"]),
                payload_json=json.dumps(tracked_positions),
            )

        for position in reviewed_positions:
            fields = _position_review_event_fields(position, provenance=provenance)
            _insert_forward_event(
                cursor,
                session_id=session_id,
                event_type="position_review",
                event_key=str(position.get("id") or ""),
                **fields,
            )

        conn.commit()

    return {
        "db_path": str(path),
        "session_id": session_id,
        "recorded_at_utc": recorded_at_utc,
        "source_label": source_label,
        "scan_picks_count": len(picks),
        "reviewed_positions_count": len(reviewed_positions),
        "truth_source": truth_source,
        "promotion_status": promotion_status,
        "taken_pick_count": taken_count,
        "skipped_pick_count": skipped_count,
        "blocked_pick_count": blocked_count,
        "cohort_ids_recorded": sorted(cohort_ids),
        "requested_cohort_ids": list(notes.get("requested_cohort_ids") or []),
        "scan_funnel": notes["scan_funnel"],
        "run_id": provenance["run_id"],
        "run_mode": provenance["run_mode"],
        "evidence_class": provenance["evidence_class"],
        "is_fixture": bool(provenance["is_fixture"]),
        "policy_artifact_id": provenance["policy_artifact_id"],
        "quote_freshness_status": provenance["quote_freshness_status"],
        "eligibility_status": provenance["eligibility_status"],
        "eligibility_blockers": list(provenance["eligibility_blockers"]),
    }


def record_position_opened(
    *,
    position: dict[str, Any],
    source_label: str = "position_opened",
    db_path: str | Path | None = None,
    evidence_class: str | None = None,
    run_id: str | None = None,
    run_mode: str | None = None,
    is_fixture: bool | None = None,
) -> dict[str, Any]:
    """Record a position_opened forward event when the user takes a scan pick."""
    recorded_at_utc = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    source = dict(position.get("source_pick_snapshot") or {})

    resolved_evidence_class = _normalize_evidence_class(
        evidence_class,
        source_label=source_label,
    )
    resolved_run_mode = _safe_text(run_mode) or _default_run_mode(resolved_evidence_class)
    resolved_run_id = _safe_text(run_id) or f"{source_label}:{recorded_at_utc}"
    resolved_is_fixture = is_fixture if is_fixture is not None else resolved_evidence_class in {
        FIXTURE_SMOKE_EVIDENCE_CLASS, UNIT_TEST_EVIDENCE_CLASS, E2E_TEST_EVIDENCE_CLASS,
    }

    provenance = {
        "recorded_at_utc": recorded_at_utc,
        "run_id": resolved_run_id,
        "run_mode": resolved_run_mode,
        "evidence_class": resolved_evidence_class,
        "is_fixture": resolved_is_fixture,
        "policy_artifact_id": None,
        "quote_freshness_status": _quote_freshness_status_from_pick(source),
        "eligibility_status": ELIGIBLE_STATUS if resolved_evidence_class == LIVE_PRODUCTION_EVIDENCE_CLASS and not resolved_is_fixture else INELIGIBLE_STATUS,
        "eligibility_blockers": [] if resolved_evidence_class == LIVE_PRODUCTION_EVIDENCE_CLASS and not resolved_is_fixture else ["non_live_evidence_class"],
    }

    path = init_forward_ledger(db_path or _db_path_for_provenance(provenance))

    ticker = str(position.get("ticker") or "").strip().upper()
    contract_symbol = str(position.get("contract_symbol") or "").strip().upper() or None
    direction = str(position.get("direction") or "").strip().lower()
    expiry = str(position.get("expiry") or "").strip()[:10]
    strike = _safe_float(position.get("strike"))
    position_id = position.get("id")
    contracts = _safe_int(position.get("contracts"))
    cohort_id = _safe_text(source.get("cohort_id"))
    cohort_role = _safe_text(source.get("cohort_role"))
    selection_source = _safe_text(source.get("selection_source") or source.get("contract_selection_source"))
    promotion_class = _safe_text(source.get("promotion_class"))

    notes = {
        "event_type": "position_opened",
        "position_id": position_id,
        "ticker": ticker,
        "contract_symbol": contract_symbol,
        "direction": direction,
        "run_id": provenance["run_id"],
        "run_mode": provenance["run_mode"],
        "evidence_class": provenance["evidence_class"],
        "is_fixture": provenance["is_fixture"],
    }

    with closing(sqlite3.connect(path)) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO forward_sessions (
                recorded_at_utc, source_label, playbook, truth_source, promotion_status,
                scan_picks_count, reviewed_positions_count, notes_json,
                run_id, run_mode, evidence_class, is_fixture,
                policy_artifact_id, quote_freshness_status,
                eligibility_status, eligibility_blockers
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                recorded_at_utc,
                source_label,
                "position_opened",
                None,
                None,
                0,
                0,
                json.dumps(notes),
                provenance["run_id"],
                provenance["run_mode"],
                provenance["evidence_class"],
                int(bool(provenance["is_fixture"])),
                provenance["policy_artifact_id"],
                provenance["quote_freshness_status"],
                provenance["eligibility_status"],
                json.dumps(provenance["eligibility_blockers"]),
            ),
        )
        session_id = int(cursor.lastrowid)

        _insert_forward_event(
            cursor,
            session_id=session_id,
            event_type="position_opened",
            event_key=str(position_id or ""),
            ticker=ticker or None,
            contract_symbol=contract_symbol,
            cohort_id=cohort_id,
            cohort_role=cohort_role,
            expiry=expiry or None,
            strike=strike,
            option_type=direction or None,
            quote_time_et=_safe_text(source.get("quote_time_et")),
            quote_basis=_safe_text(source.get("quote_basis")),
            underlying_price_at_selection=_safe_float(
                source.get("underlying_price_at_selection") or source.get("stock_price")
            ),
            selection_source=selection_source,
            promotion_class=promotion_class,
            entry_execution_price=_safe_float(position.get("entry_execution_price")),
            entry_execution_basis=_safe_text(position.get("entry_execution_basis")),
            entry_fee_total_usd=_safe_float(position.get("entry_fee_total_usd")),
            outcome_state="taken",
            position_id=_safe_int(position_id),
            contracts=contracts,
            source_scan_session_id=_safe_int(position.get("source_scan_session_id")),
            source_scan_event_key=_safe_text(position.get("source_scan_event_key")),
            source_scan_run_id=_safe_text(position.get("source_scan_run_id")),
            run_id=provenance["run_id"],
            run_mode=provenance["run_mode"],
            evidence_class=provenance["evidence_class"],
            is_fixture=provenance["is_fixture"],
            policy_artifact_id=provenance["policy_artifact_id"],
            quote_freshness_status=provenance["quote_freshness_status"],
            eligibility_status=provenance["eligibility_status"],
            eligibility_blockers=json.dumps(provenance["eligibility_blockers"]),
            payload_json=json.dumps(position, default=str),
        )
        conn.commit()

    return {
        "db_path": str(path),
        "session_id": session_id,
        "recorded_at_utc": recorded_at_utc,
        "event_type": "position_opened",
        "position_id": position_id,
        "ticker": ticker,
        "contract_symbol": contract_symbol,
        "evidence_class": provenance["evidence_class"],
    }


def list_forward_sessions(
    limit: int = 20,
    *,
    source_label: str | None = None,
    evidence_class: str | None = None,
    eligibility_status: str | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = init_forward_ledger(db_path)
    normalized_evidence_class = (
        _normalize_evidence_class(evidence_class)
        if _safe_text(evidence_class)
        else None
    )
    normalized_eligibility_status = _safe_text(eligibility_status)
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT *
            FROM forward_sessions
            WHERE (? IS NULL OR source_label = ?)
              AND (? IS NULL OR evidence_class = ?)
              AND (? IS NULL OR eligibility_status = ?)
            ORDER BY recorded_at_utc DESC, id DESC
            LIMIT ?
            """,
            (
                _safe_text(source_label),
                _safe_text(source_label),
                normalized_evidence_class,
                normalized_evidence_class,
                normalized_eligibility_status,
                normalized_eligibility_status,
                int(limit),
            ),
        ).fetchall()
    sessions: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["notes"] = json.loads(item.pop("notes_json") or "{}")
        item["is_fixture"] = bool(item.get("is_fixture"))
        item["eligibility_blockers"] = _normalized_blockers(item.get("eligibility_blockers"))
        sessions.append(item)
    return sessions


def list_forward_scan_pick_events(
    *,
    recorded_after_utc: str | None = None,
    recorded_before_utc: str | None = None,
    source_label: str | None = None,
    eligible_only: bool = False,
    evidence_class: str | None = None,
    eligibility_status: str | None = None,
    cohort_id: str | None = None,
    tickers: Optional[list[str]] = None,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = init_forward_ledger(db_path)
    normalized_evidence_class = (
        LIVE_PRODUCTION_EVIDENCE_CLASS if eligible_only and not _safe_text(evidence_class)
        else _normalize_evidence_class(evidence_class) if _safe_text(evidence_class) else None
    )
    normalized_eligibility_status = (
        ELIGIBLE_STATUS if eligible_only and not _safe_text(eligibility_status)
        else _safe_text(eligibility_status)
    )
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                fs.id AS session_id,
                fs.recorded_at_utc,
                fs.source_label,
                fs.playbook AS session_playbook,
                fs.truth_source AS session_truth_source,
                fs.promotion_status AS session_promotion_status,
                fe.*
            FROM forward_events fe
            JOIN forward_sessions fs
                ON fs.id = fe.session_id
            WHERE fe.event_type = 'scan_pick'
              AND (? IS NULL OR fs.source_label = ?)
              AND (? IS NULL OR fs.recorded_at_utc >= ?)
              AND (? IS NULL OR fs.recorded_at_utc < ?)
              AND (? IS NULL OR COALESCE(fe.evidence_class, fs.evidence_class) = ?)
              AND (? IS NULL OR COALESCE(fe.eligibility_status, fs.eligibility_status) = ?)
              AND (? = 0 OR COALESCE(fe.is_fixture, fs.is_fixture, 0) = 0)
            ORDER BY fs.recorded_at_utc ASC, fe.id ASC
            """,
            (
                _safe_text(source_label),
                _safe_text(source_label),
                _safe_text(recorded_after_utc),
                _safe_text(recorded_after_utc),
                _safe_text(recorded_before_utc),
                _safe_text(recorded_before_utc),
                normalized_evidence_class,
                normalized_evidence_class,
                normalized_eligibility_status,
                normalized_eligibility_status,
                int(bool(eligible_only)),
            ),
        ).fetchall()
        events: list[dict[str, Any]] = []
    normalized_cohort_id = _safe_text(cohort_id)
    normalized_tickers = {
        str(item).strip().upper()
        for item in list(tickers or [])
        if str(item).strip()
    }
    for row in rows:
        payload = json.loads(str(row["payload_json"] or "{}"))
        event = {
            **payload,
            "session_id": int(row["session_id"]),
            "recorded_at_utc": row["recorded_at_utc"],
            "source_label": row["source_label"],
            "session_playbook": row["session_playbook"],
            "session_truth_source": row["session_truth_source"],
            "session_promotion_status": row["session_promotion_status"],
            "event_key": row["event_key"],
            "event_id": int(row["id"]),
            "candidate_rank": _safe_int(payload.get("candidate_rank")) or _safe_int(row["candidate_rank"]),
            "ticker": str(payload.get("ticker") or row["ticker"] or "").upper() or None,
            "contract_symbol": payload.get("contract_symbol") or row["contract_symbol"],
            "expiry": payload.get("expiry") or row["expiry"],
            "strike": payload.get("strike") if payload.get("strike") is not None else row["strike"],
            "option_type": payload.get("option_type") or row["option_type"],
            "quote_time_et": payload.get("quote_time_et") or row["quote_time_et"],
            "quote_basis": payload.get("quote_basis") or row["quote_basis"],
            "underlying_price_at_selection": (
                payload.get("underlying_price_at_selection")
                if payload.get("underlying_price_at_selection") is not None
                else row["underlying_price_at_selection"]
            ),
            "selection_source": payload.get("selection_source") or row["selection_source"],
            "promotion_class": payload.get("promotion_class") or row["promotion_class"],
            "entry_execution_price": (
                payload.get("entry_execution_price")
                if payload.get("entry_execution_price") is not None
                else row["entry_execution_price"]
            ),
            "entry_execution_basis": payload.get("entry_execution_basis") or row["entry_execution_basis"],
            "entry_fee_total_usd": (
                payload.get("entry_fee_total_usd")
                if payload.get("entry_fee_total_usd") is not None
                else row["entry_fee_total_usd"]
            ),
            "exit_execution_price": (
                payload.get("exit_execution_price")
                if payload.get("exit_execution_price") is not None
                else row["exit_execution_price"]
            ),
            "exit_execution_basis": payload.get("exit_execution_basis") or row["exit_execution_basis"],
            "gross_pnl_pct": payload.get("gross_pnl_pct") if payload.get("gross_pnl_pct") is not None else row["gross_pnl_pct"],
            "net_pnl_pct": payload.get("net_pnl_pct") if payload.get("net_pnl_pct") is not None else row["net_pnl_pct"],
            "gross_pnl_usd": payload.get("gross_pnl_usd") if payload.get("gross_pnl_usd") is not None else row["gross_pnl_usd"],
            "net_pnl_usd": payload.get("net_pnl_usd") if payload.get("net_pnl_usd") is not None else row["net_pnl_usd"],
            "fee_total_usd": payload.get("fee_total_usd") if payload.get("fee_total_usd") is not None else row["fee_total_usd"],
            "run_id": payload.get("run_id") or row["run_id"],
            "run_mode": payload.get("run_mode") or row["run_mode"],
            "evidence_class": payload.get("evidence_class") or row["evidence_class"],
            "is_fixture": bool(payload.get("is_fixture")) if payload.get("is_fixture") is not None else bool(row["is_fixture"]),
            "policy_artifact_id": payload.get("policy_artifact_id") or row["policy_artifact_id"],
            "quote_freshness_status": payload.get("quote_freshness_status") or row["quote_freshness_status"],
            "eligibility_status": payload.get("eligibility_status") or row["eligibility_status"],
            "eligibility_blockers": _normalized_blockers(
                payload.get("eligibility_blockers")
                if payload.get("eligibility_blockers") is not None
                else row["eligibility_blockers"]
            ),
        }
        if not event.get("entry_date"):
            recorded_at_utc = str(row["recorded_at_utc"] or "").strip()
            if recorded_at_utc:
                try:
                    event["entry_date"] = datetime.fromisoformat(
                        recorded_at_utc.replace("Z", "+00:00")
                    ).date().isoformat()
                except ValueError:
                    pass
        if normalized_cohort_id is not None and str(event.get("cohort_id") or "").strip() != normalized_cohort_id:
            continue
        if normalized_tickers and str(event.get("ticker") or "").strip().upper() not in normalized_tickers:
            continue
        events.append(event)
    return events


def summarize_forward_holdout(
    *,
    cohort_id: str | None = None,
    source_label: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    path = init_forward_ledger(db_path)
    normalized_cohort = str(cohort_id or "").strip() or None
    normalized_source_label = _safe_text(source_label)

    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        session_rows = conn.execute(
            """
            SELECT *
            FROM forward_sessions
            WHERE (? IS NULL OR source_label = ?)
            ORDER BY recorded_at_utc ASC, id ASC
            """,
            (normalized_source_label, normalized_source_label),
        ).fetchall()
        rows = conn.execute(
            """
            SELECT
                fe.session_id,
                fs.recorded_at_utc,
                fs.playbook,
                fs.truth_source,
                fs.promotion_status,
                fe.event_type,
                fe.ticker,
                fe.contract_symbol,
                fe.recommendation,
                fe.outcome_state,
                fe.cohort_id,
                fe.eligibility_status,
                fe.quote_time_et,
                fe.gross_pnl_pct,
                fe.net_pnl_pct,
                fe.gross_pnl_usd,
                fe.net_pnl_usd
            FROM forward_events fe
            JOIN forward_sessions fs
                ON fs.id = fe.session_id
            WHERE fe.event_type IN ('scan_pick', 'position_review')
              AND (? IS NULL OR fs.source_label = ?)
              AND (? IS NULL OR fe.cohort_id = ?)
            ORDER BY fs.recorded_at_utc ASC, fe.id ASC
            """,
            (
                normalized_source_label,
                normalized_source_label,
                normalized_cohort,
                normalized_cohort,
            ),
        ).fetchall()

    filtered_sessions: list[sqlite3.Row] = []
    aggregate_scan_funnel = _normalized_scan_funnel({})
    latest_scan_funnel: Optional[dict[str, Any]] = None
    latest_starvation_stage: Optional[str] = None
    sessions_with_zero_scan_picks = 0
    for row in session_rows:
        notes = json.loads(str(row["notes_json"] or "{}"))
        requested_ids = {
            str(item).strip()
            for item in list(notes.get("requested_cohort_ids") or [])
            if str(item).strip()
        }
        if normalized_cohort is None or normalized_cohort in requested_ids:
            filtered_sessions.append(row)
            session_funnel = _session_scan_funnel(notes, normalized_cohort)
            if session_funnel is not None:
                _accumulate_scan_funnel(aggregate_scan_funnel, session_funnel)
                latest_scan_funnel = session_funnel
                if int(session_funnel.get("returned_picks") or 0) <= 0:
                    sessions_with_zero_scan_picks += 1
                    latest_starvation_stage = _infer_starvation_stage(session_funnel)

    positions_available = _closed_tracked_positions_snapshot()[0]

    if not rows and not filtered_sessions:
        return {
            "available": False,
            "cohort_id": normalized_cohort,
            "source_label": normalized_source_label,
            "db_path": str(path),
            "session_count": 0,
            "scan_pick_count": 0,
            "eligible_event_count": 0,
            "pending_truth_event_count": 0,
            "taken_pick_count": 0,
            "blocked_pick_count": 0,
            "skipped_pick_count": 0,
            "review_count": 0,
            "closed_review_count": 0,
            "tracked_positions_available": positions_available,
            "gross_realized_pnl_usd": 0.0,
            "net_realized_pnl_usd": 0.0,
            "gross_realized_pnl_pct": None,
            "net_realized_pnl_pct": None,
            "days_elapsed": 0,
            "unique_recording_days": 0,
            "recommendation_counts": {},
            "status_counts": {},
            "truth_sources_seen": [],
            "promotion_statuses_seen": [],
            "scan_funnel_totals": _normalized_scan_funnel({}),
            "latest_scan_funnel": None,
            "sessions_with_zero_scan_picks": 0,
            "latest_starvation_stage": None,
            "by_symbol": {},
            "by_playbook": {},
            "exact_contract_coverage": {
                "scan_pick": {"with_contract_count": 0, "missing_contract_count": 0},
                "taken_pick": {"with_contract_count": 0, "missing_contract_count": 0},
                "position_review": {"with_contract_count": 0, "missing_contract_count": 0},
            },
            "session_contract_coverage": [],
        }

    if not rows:
        recorded_values: list[datetime] = []
        truth_sources: set[str] = set()
        promotion_statuses: set[str] = set()
        for row in filtered_sessions:
            raw_recorded = str(row["recorded_at_utc"] or "").strip()
            if raw_recorded:
                try:
                    recorded_values.append(datetime.fromisoformat(raw_recorded.replace("Z", "+00:00")))
                except ValueError:
                    pass
            truth_source = str(row["truth_source"] or "").strip()
            if truth_source:
                truth_sources.add(truth_source)
            promotion_status = str(row["promotion_status"] or "").strip().lower()
            if promotion_status:
                promotion_statuses.add(promotion_status)
        earliest = min(recorded_values) if recorded_values else None
        latest = max(recorded_values) if recorded_values else None
        unique_days = {
            value.astimezone(UTC).date().isoformat()
            for value in recorded_values
        }
        days_elapsed = 0
        if earliest is not None and latest is not None:
            days_elapsed = max((latest.date() - earliest.date()).days, 0)
        return {
            "available": True,
            "cohort_id": normalized_cohort,
            "source_label": normalized_source_label,
            "db_path": str(path),
            "session_count": len(filtered_sessions),
            "earliest_recorded_at_utc": earliest.astimezone(UTC).isoformat().replace("+00:00", "Z") if earliest else None,
            "latest_recorded_at_utc": latest.astimezone(UTC).isoformat().replace("+00:00", "Z") if latest else None,
            "days_elapsed": days_elapsed,
            "unique_recording_days": len(unique_days),
            "scan_pick_count": 0,
            "eligible_event_count": 0,
            "pending_truth_event_count": 0,
            "taken_pick_count": 0,
            "blocked_pick_count": 0,
            "skipped_pick_count": 0,
            "review_count": 0,
            "closed_review_count": 0,
            "tracked_positions_available": positions_available,
            "gross_realized_pnl_usd": 0.0,
            "net_realized_pnl_usd": 0.0,
            "gross_realized_pnl_pct": None,
            "net_realized_pnl_pct": None,
            "recommendation_counts": {},
            "status_counts": {},
            "truth_sources_seen": sorted(truth_sources),
            "promotion_statuses_seen": sorted(promotion_statuses),
            "scan_funnel_totals": aggregate_scan_funnel,
            "latest_scan_funnel": latest_scan_funnel,
            "sessions_with_zero_scan_picks": sessions_with_zero_scan_picks,
            "latest_starvation_stage": latest_starvation_stage,
            "by_symbol": {},
            "by_playbook": {},
            "exact_contract_coverage": {
                "scan_pick": {"with_contract_count": 0, "missing_contract_count": 0},
                "taken_pick": {"with_contract_count": 0, "missing_contract_count": 0},
                "position_review": {"with_contract_count": 0, "missing_contract_count": 0},
            },
            "session_contract_coverage": [],
        }

    session_ids: set[int] = set()
    recorded_values: list[datetime] = []
    truth_sources: set[str] = set()
    promotion_statuses: set[str] = set()
    scan_pick_count = 0
    eligible_event_count = 0
    pending_truth_event_count = 0
    taken_pick_count = 0
    blocked_pick_count = 0
    skipped_pick_count = 0
    review_count = 0
    closed_review_count = 0
    recommendation_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    by_symbol: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_playbook: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    session_contract_coverage: dict[int, dict[str, Any]] = defaultdict(
        lambda: {
            "scan_pick_with_contract_count": 0,
            "scan_pick_missing_contract_count": 0,
            "taken_pick_with_contract_count": 0,
            "taken_pick_missing_contract_count": 0,
            "review_with_contract_count": 0,
            "review_missing_contract_count": 0,
        }
    )
    exact_contract_coverage = {
        "scan_pick": {"with_contract_count": 0, "missing_contract_count": 0},
        "taken_pick": {"with_contract_count": 0, "missing_contract_count": 0},
        "position_review": {"with_contract_count": 0, "missing_contract_count": 0},
    }
    trusted_truth_horizon = _trusted_truth_horizon()
    positions_available, closed_positions = _closed_tracked_positions_snapshot()
    gross_realized_pnl_usd = 0.0
    net_realized_pnl_usd = 0.0
    gross_realized_pnl_pct_values: list[float] = []
    net_realized_pnl_pct_values: list[float] = []

    for row in rows:
        session_ids.add(int(row["session_id"]))
        raw_recorded = str(row["recorded_at_utc"] or "").strip()
        if raw_recorded:
            try:
                recorded_values.append(datetime.fromisoformat(raw_recorded.replace("Z", "+00:00")))
            except ValueError:
                pass
        truth_source = str(row["truth_source"] or "").strip()
        if truth_source:
            truth_sources.add(truth_source)
        promotion_status = str(row["promotion_status"] or "").strip().lower()
        if promotion_status:
            promotion_statuses.add(promotion_status)

        event_type = str(row["event_type"] or "").strip().lower()
        recommendation = str(row["recommendation"] or "").strip().upper()
        outcome_state = str(row["outcome_state"] or "").strip().lower()
        eligibility_status = str(row["eligibility_status"] or "").strip().lower()
        ticker = str(row["ticker"] or "").strip().upper() or "UNKNOWN"
        playbook = _pick_playbook_id(row["playbook"]) or "unknown"
        has_contract = bool(str(row["contract_symbol"] or "").strip())
        if recommendation:
            recommendation_counts[recommendation] += 1
        if outcome_state:
            status_counts[outcome_state] += 1

        if event_type == "scan_pick":
            scan_pick_count += 1
            effective_eligibility_status = _measurement_status_for_event(
                row,
                trusted_truth_horizon=trusted_truth_horizon,
            )
            if effective_eligibility_status == ELIGIBLE_STATUS:
                eligible_event_count += 1
                by_symbol[ticker]["eligible_event_count"] += 1
                by_playbook[playbook]["eligible_event_count"] += 1
            elif effective_eligibility_status == PENDING_TRUTH_STATUS:
                pending_truth_event_count += 1
                by_symbol[ticker]["pending_truth_event_count"] += 1
                by_playbook[playbook]["pending_truth_event_count"] += 1
            by_symbol[ticker]["scan_pick_count"] += 1
            by_playbook[playbook]["scan_pick_count"] += 1
            if has_contract:
                exact_contract_coverage["scan_pick"]["with_contract_count"] += 1
                session_contract_coverage[int(row["session_id"])]["scan_pick_with_contract_count"] += 1
            else:
                exact_contract_coverage["scan_pick"]["missing_contract_count"] += 1
                session_contract_coverage[int(row["session_id"])]["scan_pick_missing_contract_count"] += 1
            if outcome_state == "taken":
                taken_pick_count += 1
                by_symbol[ticker]["taken_pick_count"] += 1
                by_playbook[playbook]["taken_pick_count"] += 1
                if has_contract:
                    exact_contract_coverage["taken_pick"]["with_contract_count"] += 1
                    session_contract_coverage[int(row["session_id"])]["taken_pick_with_contract_count"] += 1
                else:
                    exact_contract_coverage["taken_pick"]["missing_contract_count"] += 1
                    session_contract_coverage[int(row["session_id"])]["taken_pick_missing_contract_count"] += 1
            elif outcome_state == "blocked":
                blocked_pick_count += 1
                by_symbol[ticker]["blocked_pick_count"] += 1
                by_playbook[playbook]["blocked_pick_count"] += 1
            else:
                skipped_pick_count += 1
                by_symbol[ticker]["skipped_pick_count"] += 1
                by_playbook[playbook]["skipped_pick_count"] += 1
        elif event_type == "position_review":
            review_count += 1
            by_symbol[ticker]["review_count"] += 1
            by_playbook[playbook]["review_count"] += 1
            if has_contract:
                exact_contract_coverage["position_review"]["with_contract_count"] += 1
                session_contract_coverage[int(row["session_id"])]["review_with_contract_count"] += 1
            else:
                exact_contract_coverage["position_review"]["missing_contract_count"] += 1
                session_contract_coverage[int(row["session_id"])]["review_missing_contract_count"] += 1
            if outcome_state == "closed":
                closed_review_count += 1
                by_symbol[ticker]["closed_review_count"] += 1
                by_playbook[playbook]["closed_review_count"] += 1
                gross_realized_usd = execution_safe_float(row["gross_pnl_usd"])
                net_realized_usd = execution_safe_float(row["net_pnl_usd"])
                gross_realized_pct = execution_safe_float(row["gross_pnl_pct"])
                net_realized_pct = execution_safe_float(row["net_pnl_pct"])
                if gross_realized_usd is not None:
                    gross_realized_pnl_usd += gross_realized_usd
                if net_realized_usd is not None:
                    net_realized_pnl_usd += net_realized_usd
                if gross_realized_pct is not None:
                    gross_realized_pnl_pct_values.append(gross_realized_pct)
                if net_realized_pct is not None:
                    net_realized_pnl_pct_values.append(net_realized_pct)

    for session_row in filtered_sessions:
        session_id = int(session_row["id"])
        if session_id in session_ids:
            continue
        raw_recorded = str(session_row["recorded_at_utc"] or "").strip()
        if raw_recorded:
            try:
                recorded_values.append(datetime.fromisoformat(raw_recorded.replace("Z", "+00:00")))
            except ValueError:
                pass
        truth_source = str(session_row["truth_source"] or "").strip()
        if truth_source:
            truth_sources.add(truth_source)
        promotion_status = str(session_row["promotion_status"] or "").strip().lower()
        if promotion_status:
            promotion_statuses.add(promotion_status)

    earliest = min(recorded_values) if recorded_values else None
    latest = max(recorded_values) if recorded_values else None
    unique_days = {
        value.astimezone(UTC).date().isoformat()
        for value in recorded_values
    }
    days_elapsed = 0
    if earliest is not None and latest is not None:
        days_elapsed = max((latest.date() - earliest.date()).days, 0)

    realized_position_summary = _realized_position_summary(
        closed_positions,
        cohort_id=normalized_cohort,
    )
    if int(realized_position_summary.get("closed_position_count") or 0) > 0:
        closed_review_count = max(
            closed_review_count,
            int(realized_position_summary["closed_position_count"]),
        )
        gross_realized_pnl_usd = float(realized_position_summary["gross_realized_pnl_usd"])
        net_realized_pnl_usd = float(realized_position_summary["net_realized_pnl_usd"])
        gross_realized_pnl_pct_values = []
        net_realized_pnl_pct_values = []

    return {
        "available": True,
        "cohort_id": normalized_cohort,
        "source_label": normalized_source_label,
        "db_path": str(path),
        "session_count": len(filtered_sessions) if filtered_sessions else len(session_ids),
        "earliest_recorded_at_utc": earliest.astimezone(UTC).isoformat().replace("+00:00", "Z") if earliest else None,
        "latest_recorded_at_utc": latest.astimezone(UTC).isoformat().replace("+00:00", "Z") if latest else None,
        "days_elapsed": days_elapsed,
        "unique_recording_days": len(unique_days),
        "scan_pick_count": scan_pick_count,
        "eligible_event_count": eligible_event_count,
        "pending_truth_event_count": pending_truth_event_count,
        "taken_pick_count": taken_pick_count,
        "blocked_pick_count": blocked_pick_count,
        "skipped_pick_count": skipped_pick_count,
        "review_count": review_count,
        "closed_review_count": closed_review_count,
        "tracked_positions_available": positions_available,
        "gross_realized_pnl_usd": round(gross_realized_pnl_usd, 2),
        "net_realized_pnl_usd": round(net_realized_pnl_usd, 2),
        "gross_realized_pnl_pct": (
            round(float(realized_position_summary["gross_realized_pnl_pct"]), 2)
            if realized_position_summary.get("gross_realized_pnl_pct") is not None
            else round(sum(gross_realized_pnl_pct_values) / len(gross_realized_pnl_pct_values), 2)
            if gross_realized_pnl_pct_values
            else None
        ),
        "net_realized_pnl_pct": (
            round(float(realized_position_summary["net_realized_pnl_pct"]), 2)
            if realized_position_summary.get("net_realized_pnl_pct") is not None
            else round(sum(net_realized_pnl_pct_values) / len(net_realized_pnl_pct_values), 2)
            if net_realized_pnl_pct_values
            else None
        ),
        "recommendation_counts": dict(sorted(recommendation_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "truth_sources_seen": sorted(truth_sources),
        "promotion_statuses_seen": sorted(promotion_statuses),
        "scan_funnel_totals": aggregate_scan_funnel,
        "latest_scan_funnel": latest_scan_funnel,
        "sessions_with_zero_scan_picks": sessions_with_zero_scan_picks,
        "latest_starvation_stage": latest_starvation_stage,
        "by_symbol": {
            key: {metric: int(value) for metric, value in sorted(metrics.items())}
            for key, metrics in sorted(by_symbol.items())
        },
        "by_playbook": {
            key: {metric: int(value) for metric, value in sorted(metrics.items())}
            for key, metrics in sorted(by_playbook.items())
        },
        "exact_contract_coverage": exact_contract_coverage,
        "session_contract_coverage": [
            {"session_id": int(session_id), **coverage}
            for session_id, coverage in sorted(session_contract_coverage.items())
        ],
    }
