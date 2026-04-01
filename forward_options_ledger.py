from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_FORWARD_LEDGER_DB_PATH = ROOT_DIR / "data" / "options-validation" / "forward_tracking.db"

FORWARD_EVENT_OPTIONAL_COLUMNS: dict[str, str] = {
    "cohort_id": "TEXT",
    "cohort_role": "TEXT",
    "policy_state": "TEXT",
    "guardrail_state": "TEXT",
    "candidate_rank": "INTEGER",
    "option_bid": "REAL",
    "option_ask": "REAL",
    "option_mid": "REAL",
    "option_spread_pct": "REAL",
    "option_iv": "REAL",
    "option_delta": "REAL",
    "option_dte": "INTEGER",
    "outcome_state": "TEXT",
}


def _db_path() -> Path:
    override = os.getenv("FORWARD_OPTIONS_LEDGER_DB_PATH")
    return Path(override) if override else DEFAULT_FORWARD_LEDGER_DB_PATH


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
                notes_json TEXT NOT NULL DEFAULT '{}'
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
                candidate_rank INTEGER,
                option_bid REAL,
                option_ask REAL,
                option_mid REAL,
                option_spread_pct REAL,
                option_iv REAL,
                option_delta REAL,
                option_dte INTEGER,
                outcome_state TEXT,
                payload_json TEXT NOT NULL
            );
            """
        )
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


def _tracked_position_matches_pick(
    pick: dict[str, Any],
    tracked_positions: list[dict[str, Any]],
) -> bool:
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
) -> dict[str, Any]:
    cohort_id = str(pick.get("cohort_id") or "").strip() or None
    cohort_role = str(pick.get("cohort_role") or "").strip() or None
    policy_state = str(
        pick.get("policy_decision")
        or pick.get("trade_policy_decision")
        or ""
    ).strip() or None
    guardrail_state = str(pick.get("guardrail_decision") or "").strip() or None
    return {
        "ticker": str(pick.get("ticker") or "").strip().upper() or None,
        "contract_symbol": _pick_contract_symbol(pick),
        "recommendation": policy_state,
        "pricing_source": pick.get("pricing_source"),
        "cohort_id": cohort_id,
        "cohort_role": cohort_role,
        "policy_state": policy_state,
        "guardrail_state": guardrail_state,
        "candidate_rank": _safe_int(pick.get("candidate_rank")) or int(candidate_rank),
        "option_bid": _safe_float(pick.get("bid")),
        "option_ask": _safe_float(pick.get("ask")),
        "option_mid": _safe_float(pick.get("mid") if pick.get("mid") is not None else pick.get("premium")),
        "option_spread_pct": _safe_float(
            pick.get("spread_pct")
            if pick.get("spread_pct") is not None
            else pick.get("spread_percent")
        ),
        "option_iv": _safe_float(
            pick.get("iv_percentile")
            if pick.get("iv_percentile") is not None
            else pick.get("iv_pct")
        ),
        "option_delta": _safe_float(pick.get("delta")),
        "option_dte": _safe_int(pick.get("dte")),
        "outcome_state": _pick_outcome_state(pick, tracked_positions),
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
    candidate_rank: Optional[int] = None,
    option_bid: Optional[float] = None,
    option_ask: Optional[float] = None,
    option_mid: Optional[float] = None,
    option_spread_pct: Optional[float] = None,
    option_iv: Optional[float] = None,
    option_delta: Optional[float] = None,
    option_dte: Optional[int] = None,
    outcome_state: Optional[str] = None,
) -> None:
    cursor.execute(
        """
        INSERT INTO forward_events (
            session_id,
            event_type,
            event_key,
            ticker,
            contract_symbol,
            recommendation,
            pricing_source,
            cohort_id,
            cohort_role,
            policy_state,
            guardrail_state,
            candidate_rank,
            option_bid,
            option_ask,
            option_mid,
            option_spread_pct,
            option_iv,
            option_delta,
            option_dte,
            outcome_state,
            payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
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
            candidate_rank,
            option_bid,
            option_ask,
            option_mid,
            option_spread_pct,
            option_iv,
            option_delta,
            option_dte,
            outcome_state,
            payload_json,
        ),
    )


def record_forward_snapshot(
    *,
    scan_snapshot: dict[str, Any],
    reviewed_positions: list[dict[str, Any]],
    tracked_positions: Optional[list[dict[str, Any]]] = None,
    source_label: str = "manual_snapshot",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    path = init_forward_ledger(db_path)
    recorded_at_utc = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    picks = list(scan_snapshot.get("picks") or [])
    policy = dict(scan_snapshot.get("policy") or {})
    playbook = str((scan_snapshot.get("playbook") or {}).get("id") or scan_snapshot.get("playbook") or "")
    tracked = list(tracked_positions or [])
    notes = {
        "policy_applied": bool(scan_snapshot.get("policy_applied")),
        "policy_error": scan_snapshot.get("policy_error"),
        "truth_source": policy.get("truth_source"),
        "promotion_status": policy.get("promotion_status"),
        "candidate_count": scan_snapshot.get("candidate_count"),
        "returned_count": scan_snapshot.get("returned_count"),
        "guardrail_decision_counts": scan_snapshot.get("guardrail_decision_counts"),
        "policy_decision_counts": scan_snapshot.get("policy_decision_counts"),
        "positions_available": tracked_positions is not None,
        "champion_manifest_path": scan_snapshot.get("champion_manifest_path"),
        "cohort_count": scan_snapshot.get("cohort_count"),
        "requested_cohort_ids": list(scan_snapshot.get("cohort_ids") or []),
        "scan_funnel": _normalized_scan_funnel(scan_snapshot.get("scan_funnel")),
        "cohort_funnels": {
            str(key): _normalized_scan_funnel(value)
            for key, value in dict(scan_snapshot.get("cohort_funnels") or {}).items()
            if str(key).strip()
        },
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
                notes_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                recorded_at_utc,
                str(source_label or "manual_snapshot").strip() or "manual_snapshot",
                playbook or None,
                policy.get("truth_source"),
                policy.get("promotion_status"),
                len(picks),
                len(reviewed_positions),
                json.dumps(notes),
            ),
        )
        session_id = int(cursor.lastrowid)

        _insert_forward_event(
            cursor,
            session_id=session_id,
            event_type="scan_snapshot",
            event_key=playbook or "scan",
            payload_json=json.dumps(scan_snapshot),
        )

        for idx, pick in enumerate(picks, start=1):
            fields = _event_fields_from_pick(
                pick,
                candidate_rank=idx,
                tracked_positions=tracked,
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
                payload_json=json.dumps(tracked_positions),
            )

        for position in reviewed_positions:
            latest_review = dict(position.get("latest_review") or {})
            source = dict(position.get("source_pick_snapshot") or {})
            _insert_forward_event(
                cursor,
                session_id=session_id,
                event_type="position_review",
                event_key=str(position.get("id") or ""),
                ticker=str(position.get("ticker") or "").upper() or None,
                contract_symbol=position.get("contract_symbol") or source.get("contract_symbol") or source.get("contractSymbol"),
                recommendation=latest_review.get("recommendation"),
                pricing_source=latest_review.get("pricing_source"),
                cohort_id=source.get("cohort_id"),
                cohort_role=source.get("cohort_role"),
                policy_state=source.get("policy_decision") or source.get("trade_policy_decision"),
                guardrail_state=source.get("guardrail_decision"),
                candidate_rank=_safe_int(source.get("candidate_rank")),
                option_bid=_safe_float(source.get("bid")),
                option_ask=_safe_float(source.get("ask")),
                option_mid=_safe_float(source.get("mid") if source.get("mid") is not None else source.get("premium")),
                option_spread_pct=_safe_float(source.get("spread_pct")),
                option_iv=_safe_float(
                    source.get("iv_percentile")
                    if source.get("iv_percentile") is not None
                    else source.get("iv_pct")
                ),
                option_delta=_safe_float(source.get("delta")),
                option_dte=_safe_int(source.get("dte")),
                outcome_state=str(position.get("status") or "").strip() or None,
                payload_json=json.dumps(position),
            )

        conn.commit()

    return {
        "db_path": str(path),
        "session_id": session_id,
        "recorded_at_utc": recorded_at_utc,
        "source_label": source_label,
        "scan_picks_count": len(picks),
        "reviewed_positions_count": len(reviewed_positions),
        "truth_source": policy.get("truth_source"),
        "promotion_status": policy.get("promotion_status"),
        "taken_pick_count": taken_count,
        "skipped_pick_count": skipped_count,
        "blocked_pick_count": blocked_count,
        "cohort_ids_recorded": sorted(cohort_ids),
        "scan_funnel": notes["scan_funnel"],
    }


def list_forward_sessions(
    limit: int = 20,
    *,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = init_forward_ledger(db_path)
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT *
            FROM forward_sessions
            ORDER BY recorded_at_utc DESC, id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    sessions: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["notes"] = json.loads(item.pop("notes_json") or "{}")
        sessions.append(item)
    return sessions


def summarize_forward_holdout(
    *,
    cohort_id: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    path = init_forward_ledger(db_path)
    normalized_cohort = str(cohort_id or "").strip() or None

    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        session_rows = conn.execute(
            """
            SELECT *
            FROM forward_sessions
            ORDER BY recorded_at_utc ASC, id ASC
            """
        ).fetchall()
        rows = conn.execute(
            """
            SELECT
                fe.session_id,
                fs.recorded_at_utc,
                fs.truth_source,
                fs.promotion_status,
                fe.event_type,
                fe.recommendation,
                fe.outcome_state,
                fe.cohort_id
            FROM forward_events fe
            JOIN forward_sessions fs
                ON fs.id = fe.session_id
            WHERE fe.event_type IN ('scan_pick', 'position_review')
              AND (? IS NULL OR fe.cohort_id = ?)
            ORDER BY fs.recorded_at_utc ASC, fe.id ASC
            """,
            (normalized_cohort, normalized_cohort),
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

    if not rows and not filtered_sessions:
        return {
            "available": False,
            "cohort_id": normalized_cohort,
            "db_path": str(path),
            "session_count": 0,
            "scan_pick_count": 0,
            "taken_pick_count": 0,
            "blocked_pick_count": 0,
            "skipped_pick_count": 0,
            "review_count": 0,
            "closed_review_count": 0,
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
            "db_path": str(path),
            "session_count": len(filtered_sessions),
            "earliest_recorded_at_utc": earliest.astimezone(UTC).isoformat().replace("+00:00", "Z") if earliest else None,
            "latest_recorded_at_utc": latest.astimezone(UTC).isoformat().replace("+00:00", "Z") if latest else None,
            "days_elapsed": days_elapsed,
            "unique_recording_days": len(unique_days),
            "scan_pick_count": 0,
            "taken_pick_count": 0,
            "blocked_pick_count": 0,
            "skipped_pick_count": 0,
            "review_count": 0,
            "closed_review_count": 0,
            "recommendation_counts": {},
            "status_counts": {},
            "truth_sources_seen": sorted(truth_sources),
            "promotion_statuses_seen": sorted(promotion_statuses),
            "scan_funnel_totals": aggregate_scan_funnel,
            "latest_scan_funnel": latest_scan_funnel,
            "sessions_with_zero_scan_picks": sessions_with_zero_scan_picks,
            "latest_starvation_stage": latest_starvation_stage,
        }

    session_ids: set[int] = set()
    recorded_values: list[datetime] = []
    truth_sources: set[str] = set()
    promotion_statuses: set[str] = set()
    scan_pick_count = 0
    taken_pick_count = 0
    blocked_pick_count = 0
    skipped_pick_count = 0
    review_count = 0
    closed_review_count = 0
    recommendation_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()

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
        if recommendation:
            recommendation_counts[recommendation] += 1
        if outcome_state:
            status_counts[outcome_state] += 1

        if event_type == "scan_pick":
            scan_pick_count += 1
            if outcome_state == "taken":
                taken_pick_count += 1
            elif outcome_state == "blocked":
                blocked_pick_count += 1
            else:
                skipped_pick_count += 1
        elif event_type == "position_review":
            review_count += 1
            if outcome_state == "closed":
                closed_review_count += 1

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

    return {
        "available": True,
        "cohort_id": normalized_cohort,
        "db_path": str(path),
        "session_count": len(filtered_sessions) if filtered_sessions else len(session_ids),
        "earliest_recorded_at_utc": earliest.astimezone(UTC).isoformat().replace("+00:00", "Z") if earliest else None,
        "latest_recorded_at_utc": latest.astimezone(UTC).isoformat().replace("+00:00", "Z") if latest else None,
        "days_elapsed": days_elapsed,
        "unique_recording_days": len(unique_days),
        "scan_pick_count": scan_pick_count,
        "taken_pick_count": taken_pick_count,
        "blocked_pick_count": blocked_pick_count,
        "skipped_pick_count": skipped_pick_count,
        "review_count": review_count,
        "closed_review_count": closed_review_count,
        "recommendation_counts": dict(sorted(recommendation_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "truth_sources_seen": sorted(truth_sources),
        "promotion_statuses_seen": sorted(promotion_statuses),
        "scan_funnel_totals": aggregate_scan_funnel,
        "latest_scan_funnel": latest_scan_funnel,
        "sessions_with_zero_scan_picks": sessions_with_zero_scan_picks,
        "latest_starvation_stage": latest_starvation_stage,
    }
