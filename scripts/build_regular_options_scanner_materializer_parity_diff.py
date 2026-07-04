from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Sequence
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_regular_options_historical_profitability_filter_iteration import (  # noqa: E402
    _as_dict,
    _as_list,
    _filter_rows,
)
from us_equity_market_calendar import is_us_equity_market_day, previous_market_day  # noqa: E402


REPORT_ID = "regular_options_scanner_materializer_parity_diff"
DEFAULT_MATERIALIZER_DECISIONS = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-13-symbol-frozen-daily-candidate-decisions"
    / "daily_candidate_decisions.jsonl"
)
DEFAULT_MATERIALIZER_LATEST = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-13-symbol-frozen-daily-candidate-decisions"
    / "latest.json"
)
DEFAULT_SCAN_PICKS = ROOT / "data" / "forward-tracking" / "scan_picks.jsonl"
DEFAULT_LEDGER_DB = ROOT / "data" / "options-validation" / "forward_tracking_authoritative.db"
DEFAULT_POLICY_CONTRACT = ROOT / "data" / "contracts" / "regular-options-frozen-filtered-policy-v1.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking" / "regular-options-scanner-materializer-parity-diff"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-scanner-materializer-parity-diff.md"
DEFAULT_START_DATE = "2026-06-14"
MATERIALIZER_ENTRY_WINDOW_ET = "10:10-10:25"
MARKET_TZ = ZoneInfo("America/New_York")
FALSE_FLAGS = {
    "accepted_profitability": False,
    "historical_rows_are_forward_proof": False,
    "promotion_ready": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "cohort_append_performed": False,
}
FORBIDDEN_ACTIONS = [
    "scanner_policy_change",
    "scanner_execution_from_parity_diff",
    "strategy_logic_change",
    "stop_change",
    "sizing_change",
    "proof_bar_change",
    "live_validation",
    "auto_track",
    "broker_order",
    "quote_import",
    "options_history_db_mutation",
    "chat_history_db_mutation",
    "postgres_mutation",
    "evidence_store_mutation",
    "protected_forward_holdout_consumption",
    "promotion",
]


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


def _parse_date(value: Any) -> date | None:
    text = _norm(value)[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _load_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if not path.exists():
        return {}, {"path": _rel(path), "exists": False, "status": "missing"}
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        return {}, {"path": _rel(path), "exists": True, "status": "invalid_json", "error": str(exc)}
    if not isinstance(payload, dict):
        return {}, {"path": _rel(path), "exists": True, "status": "invalid_payload"}
    return payload, {"path": _rel(path), "exists": True, "status": "loaded"}


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.exists():
        return [], {"path": _rel(path), "exists": False, "status": "missing", "row_count": 0, "bad_row_count": 0}
    rows: list[dict[str, Any]] = []
    bad = 0
    for raw in path.read_text(encoding="utf8").splitlines():
        text = raw.strip().lstrip("\ufeff")
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            bad += 1
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
        else:
            bad += 1
    return rows, {"path": _rel(path), "exists": True, "status": "loaded", "row_count": len(rows), "bad_row_count": bad}


def _row_date(row: dict[str, Any]) -> str:
    return _norm(
        row.get("candidate_generation_date")
        or row.get("selection_date")
        or row.get("scan_date")
        or row.get("date")
        or row.get("entry_date")
        or row.get("logged_at")
    )[:10]


def _row_lane(row: dict[str, Any]) -> str:
    return _norm(row.get("lane_id") or row.get("lane") or row.get("playbook_id") or row.get("cohort_id"))


def _row_symbol(row: dict[str, Any]) -> str:
    return _norm(row.get("ticker") or row.get("symbol") or row.get("underlying")).upper()


def _row_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (_row_date(row), _row_lane(row), _row_symbol(row))


def _scan_pick_date(row: dict[str, Any]) -> str:
    explicit = _norm(row.get("selection_date") or row.get("scan_date"))
    if explicit:
        return explicit[:10]
    return _timestamp_market_date(row.get("selection_timestamp_utc") or row.get("logged_at"))


def _timestamp_market_date(value: Any) -> str:
    text = _norm(value)
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text[:10]
    if parsed.tzinfo is None:
        return parsed.date().isoformat()
    return parsed.astimezone(MARKET_TZ).date().isoformat()


def _scan_pick_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (_scan_pick_date(row), _row_lane(row), _row_symbol(row))


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def _market_dates(start: date, end: date) -> list[date]:
    dates: list[date] = []
    current = start
    while current <= end:
        if is_us_equity_market_day(current):
            dates.append(current)
        current += timedelta(days=1)
    return dates


def _default_end_date(generated_at_utc: str) -> str:
    try:
        parsed = datetime.fromisoformat(generated_at_utc.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.now(UTC)
    local = parsed.astimezone(MARKET_TZ)
    current = local.date()
    if is_us_equity_market_day(current) and local.time() >= time(16, 0):
        return current.isoformat()
    return previous_market_day(current).isoformat()


def _load_materializer_rows(path: Path, latest_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows, meta = _load_jsonl(path)
    if rows or meta.get("exists"):
        return rows, meta
    latest, latest_meta = _load_json(latest_path)
    embedded = [_as_dict(item) for item in _as_list(latest.get("daily_candidate_decisions") or latest.get("daily_candidate_generation"))]
    latest_meta.update({"row_count": len(embedded), "embedded_source": True})
    return embedded, latest_meta


def _session_time_et(value: Any) -> str:
    text = _norm(value)
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(MARKET_TZ).time().isoformat(timespec="seconds")


def _parse_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    text = _norm(value)
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_norm(item) for item in value if _norm(item)]
    text = _norm(value)
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return [text]
    if isinstance(parsed, list):
        return [_norm(item) for item in parsed if _norm(item)]
    return [text]


def _load_scheduled_sessions(
    ledger_db_path: Path,
    *,
    start_date: str,
    end_date: str,
    playbooks: Sequence[str],
) -> tuple[list[dict[str, Any]], str | None]:
    if not ledger_db_path.exists():
        return [], "ledger_db_missing"
    playbooks = [item for item in playbooks if item]
    if not playbooks:
        return [], None
    placeholders = ",".join("?" for _ in playbooks)
    conn: sqlite3.Connection | None = None
    try:
        uri = f"file:{ledger_db_path.resolve().as_posix()}?mode=ro&immutable=1"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT id, recorded_at_utc, playbook, scan_picks_count, eligibility_status,
                   eligibility_blockers, notes_json, run_id, source_label
            FROM forward_sessions
            WHERE source_label = 'scheduled_scan'
              AND substr(run_id, 16, 10) >= ?
              AND substr(run_id, 16, 10) <= ?
              AND playbook IN ({placeholders})
            ORDER BY substr(run_id, 16, 10), playbook, recorded_at_utc DESC, id DESC
            """,
            (start_date, end_date, *playbooks),
        ).fetchall()
    except sqlite3.Error as exc:
        return [], f"ledger_query_failed:{exc}"
    finally:
        if conn is not None:
            conn.close()

    sessions: list[dict[str, Any]] = []
    for row in rows:
        payload = dict(row)
        notes = _parse_json_dict(payload.get("notes_json"))
        scan_funnel = _as_dict(notes.get("scan_funnel"))
        symbol_diagnostics = _as_dict(notes.get("symbol_diagnostics"))
        drop_reasons = _as_dict(symbol_diagnostics.get("scan_drop_reasons") or notes.get("scan_drop_reasons"))
        drop_counts: dict[str, int] = {}
        for key, value in _as_dict(scan_funnel.get("drop_counts")).items():
            try:
                drop_counts[str(key)] = int(value or 0)
            except (TypeError, ValueError):
                drop_counts[str(key)] = 0
        payload["selection_date"] = _run_id_selection_date(payload.get("run_id"))
        payload["recorded_time_et"] = _session_time_et(payload.get("recorded_at_utc"))
        payload["scan_funnel_returned_picks"] = int(scan_funnel.get("returned_picks") or notes.get("returned_count") or 0)
        payload["scan_funnel_drop_counts"] = {key: drop_counts[key] for key in sorted(drop_counts)}
        payload["scan_drop_reasons"] = drop_reasons
        payload["scan_drop_reason_count"] = len(drop_reasons)
        payload["eligibility_blockers"] = _parse_json_list(payload.get("eligibility_blockers"))
        payload.pop("notes_json", None)
        sessions.append(payload)
    return sessions, None


def _run_id_selection_date(value: Any) -> str:
    text = _norm(value)
    parts = text.split(":")
    if len(parts) >= 2:
        return parts[1][:10]
    return ""


def _session_index(sessions: Sequence[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    indexed: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for session in sessions:
        date_key = _norm(session.get("selection_date"))
        lane = _norm(session.get("playbook"))
        if date_key and lane:
            indexed[(date_key, lane)].append(dict(session))
    return indexed


def _scan_pick_index(rows: Sequence[dict[str, Any]], *, start_date: str, end_date: str) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    indexed: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = _scan_pick_key(row)
        if not all(key):
            continue
        if start_date <= key[0] <= end_date:
            indexed[key].append(dict(row))
    return indexed


def _allowed_lane_symbol_pairs(rows: Sequence[dict[str, Any]]) -> set[tuple[str, str]]:
    return {(_row_lane(row), _row_symbol(row)) for row in rows if _row_lane(row) and _row_symbol(row)}


def _materializer_decision_index(
    rows: Sequence[dict[str, Any]],
    *,
    start_date: str,
    end_date: str,
) -> dict[tuple[str, str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = _row_key(row)
        if not all(key):
            continue
        if start_date <= key[0] <= end_date:
            indexed.setdefault(key, dict(row))
    return indexed


def _filtered_materializer_selected_rows(rows: Sequence[dict[str, Any]], policy: dict[str, Any]) -> list[dict[str, Any]]:
    selected = [dict(row) for row in rows if bool(row.get("selected_candidate"))]
    return _filter_rows(selected, {"conditions": _as_list(policy.get("conditions"))})


def _drop_reason_for_symbol(sessions: Sequence[dict[str, Any]], symbol: str) -> tuple[str | None, dict[str, Any] | None]:
    symbol = symbol.upper()
    for session in sessions:
        reasons = _as_dict(session.get("scan_drop_reasons"))
        reason = _as_dict(reasons.get(symbol))
        if reason:
            drop_key = _norm(reason.get("drop_key")) or "unknown"
            return drop_key, reason
    return None, None


def _sessions_have_aggregate_drops(sessions: Sequence[dict[str, Any]]) -> bool:
    for session in sessions:
        for value in _as_dict(session.get("scan_funnel_drop_counts")).values():
            try:
                if int(value or 0) > 0:
                    return True
            except (TypeError, ValueError):
                continue
    return False


def _sessions_time_basis_differs(sessions: Sequence[dict[str, Any]]) -> bool:
    for session in sessions:
        time_text = _norm(session.get("recorded_time_et"))
        if not time_text:
            continue
        if not ("10:10:00" <= time_text <= "10:25:59"):
            return True
    return False


def _classify_materializer_selected_row(
    row: dict[str, Any],
    *,
    sessions: Sequence[dict[str, Any]],
    scan_picks: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    date_key, lane, symbol = _row_key(row)
    if scan_picks:
        divergence = "entry_time_basis_differs" if _sessions_time_basis_differs(sessions) else "matching_pick"
        return {
            "date": date_key,
            "lane": lane,
            "symbol": symbol,
            "materializer_decision": "selected_candidate",
            "scanner_observation": "matching_pick",
            "divergence_class": divergence,
            "scanner_pick_matched": True,
            "scheduled_session_count": len(sessions),
            "scheduled_session_times_et": sorted({_norm(item.get("recorded_time_et")) for item in sessions if _norm(item.get("recorded_time_et"))}),
            "materializer_entry_window_et": MATERIALIZER_ENTRY_WINDOW_ET,
            "drop_reason": None,
            "drop_details": None,
        }
    if not sessions:
        divergence = "no_scheduled_session"
        scanner_observation = "no_scheduled_session"
        drop_key = None
        drop_details = None
    else:
        drop_key, drop_details = _drop_reason_for_symbol(sessions, symbol)
        if drop_key:
            divergence = f"scanner_gate_drop:{drop_key}"
            scanner_observation = "symbol_drop_reason"
        else:
            divergence = "insufficient_drop_reason_data"
            scanner_observation = (
                "aggregate_drops_without_symbol_reason" if _sessions_have_aggregate_drops(sessions) else "scheduled_no_pick_without_reason"
            )
    return {
        "date": date_key,
        "lane": lane,
        "symbol": symbol,
        "materializer_decision": "selected_candidate",
        "scanner_observation": scanner_observation,
        "divergence_class": divergence,
        "scanner_pick_matched": False,
        "scheduled_session_count": len(sessions),
        "scheduled_session_times_et": sorted({_norm(item.get("recorded_time_et")) for item in sessions if _norm(item.get("recorded_time_et"))}),
        "materializer_entry_window_et": MATERIALIZER_ENTRY_WINDOW_ET,
        "drop_reason": drop_key,
        "drop_details": drop_details,
    }


def _classify_scanner_only_pick(
    pick: dict[str, Any],
    *,
    materializer_row: dict[str, Any] | None,
    sessions: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    date_key, lane, symbol = _scan_pick_key(pick)
    decision = "missing_materializer_row"
    if materializer_row:
        decision = "explicit_no_pick" if bool(materializer_row.get("explicit_no_pick")) else "not_selected"
    return {
        "date": date_key,
        "lane": lane,
        "symbol": symbol,
        "materializer_decision": decision,
        "scanner_observation": "scanner_pick",
        "divergence_class": "materializer_no_pick_scanner_pick",
        "scanner_pick_matched": False,
        "scheduled_session_count": len(sessions),
        "scheduled_session_times_et": sorted({_norm(item.get("recorded_time_et")) for item in sessions if _norm(item.get("recorded_time_et"))}),
        "materializer_entry_window_et": MATERIALIZER_ENTRY_WINDOW_ET,
        "drop_reason": None,
        "drop_details": None,
    }


def _top_starvation_gate(counter: Counter[str]) -> dict[str, Any]:
    gate_counts = Counter()
    insufficient = counter.get("insufficient_drop_reason_data", 0)
    for key, value in counter.items():
        if key.startswith("scanner_gate_drop:"):
            gate_counts[key.split(":", 1)[1]] += value
    if gate_counts:
        gate, count = sorted(gate_counts.items(), key=lambda item: (-item[1], item[0]))[0]
        return {"status": "top_scanner_gate_identified", "gate": gate, "day_count": count}
    if insufficient:
        return {"status": "insufficient_drop_reason_data_dominates", "gate": "insufficient_drop_reason_data", "day_count": insufficient}
    return {"status": "no_starvation_gate_observed", "gate": None, "day_count": 0}


def build_report(
    *,
    materializer_decisions_path: Path = DEFAULT_MATERIALIZER_DECISIONS,
    materializer_latest_path: Path = DEFAULT_MATERIALIZER_LATEST,
    scan_picks_path: Path = DEFAULT_SCAN_PICKS,
    ledger_db_path: Path = DEFAULT_LEDGER_DB,
    policy_contract_path: Path = DEFAULT_POLICY_CONTRACT,
    start_date: str = DEFAULT_START_DATE,
    end_date: str | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    end = end_date or _default_end_date(generated_at)
    start_parsed = _parse_date(start_date)
    end_parsed = _parse_date(end)
    if start_parsed is None or end_parsed is None or start_parsed > end_parsed:
        raise ValueError(f"invalid date window: {start_date}..{end}")

    materializer_rows, materializer_meta = _load_materializer_rows(materializer_decisions_path, materializer_latest_path)
    scan_rows, scan_meta = _load_jsonl(scan_picks_path)
    policy, policy_meta = _load_json(policy_contract_path)
    lanes = sorted({_row_lane(row) for row in materializer_rows if _row_lane(row)})
    allowed_pairs = _allowed_lane_symbol_pairs(materializer_rows)
    sessions, session_error = _load_scheduled_sessions(
        ledger_db_path,
        start_date=start_date,
        end_date=end,
        playbooks=lanes,
    )
    session_by_lane_day = _session_index(sessions)
    scan_by_key = {
        key: value
        for key, value in _scan_pick_index(scan_rows, start_date=start_date, end_date=end).items()
        if (key[1], key[2]) in allowed_pairs
    }
    materializer_by_key = _materializer_decision_index(materializer_rows, start_date=start_date, end_date=end)
    filtered_selected_rows = _filtered_materializer_selected_rows(
        [row for row in materializer_rows if start_date <= _row_date(row) <= end],
        policy,
    )

    divergence_rows: list[dict[str, Any]] = []
    matched_scan_keys: set[tuple[str, str, str]] = set()
    for row in filtered_selected_rows:
        key = _row_key(row)
        sessions_for_lane = session_by_lane_day.get((key[0], key[1]), [])
        matching_scan_picks = scan_by_key.get(key, [])
        if matching_scan_picks:
            matched_scan_keys.add(key)
        divergence_rows.append(
            _classify_materializer_selected_row(
                row,
                sessions=sessions_for_lane,
                scan_picks=matching_scan_picks,
            )
        )

    for key, picks in sorted(scan_by_key.items()):
        if key in matched_scan_keys:
            continue
        materializer_row = materializer_by_key.get(key)
        if materializer_row is None or bool(materializer_row.get("selected_candidate")):
            continue
        divergence_rows.append(
            _classify_scanner_only_pick(
                picks[0],
                materializer_row=materializer_row,
                sessions=session_by_lane_day.get((key[0], key[1]), []),
            )
        )

    divergence_counts = Counter(str(row.get("divergence_class")) for row in divergence_rows)
    day_counts: dict[str, Counter[str]] = defaultdict(Counter)
    lane_symbol_counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for row in divergence_rows:
        cls = str(row.get("divergence_class"))
        day_counts[str(row.get("date"))][cls] += 1
        lane_symbol_counts[(str(row.get("lane")), str(row.get("symbol")))][cls] += 1

    dates = [item.isoformat() for item in _market_dates(start_parsed, end_parsed)]
    materializer_rows_in_window = [row for row in materializer_rows if start_date <= _row_date(row) <= end]
    materializer_date_range = sorted({_row_date(row) for row in materializer_rows if _row_date(row)})
    daily_table = []
    for day in dates:
        day_rows = [row for row in materializer_rows_in_window if _row_date(row) == day]
        day_filtered = [row for row in filtered_selected_rows if _row_date(row) == day]
        day_sessions = [session for session in sessions if session.get("selection_date") == day]
        daily_table.append(
            {
                "date": day,
                "materializer_decision_rows": len(day_rows),
                "materializer_selected_rows": sum(1 for row in day_rows if bool(row.get("selected_candidate"))),
                "materializer_filter_matched_selected_rows": len(day_filtered),
                "scheduled_session_count": len(day_sessions),
                "scheduled_scan_pick_count": sum(int(session.get("scan_picks_count") or 0) for session in day_sessions),
                "divergence_counts": _counter_dict(day_counts.get(day, Counter())),
            }
        )

    per_lane_symbol_summary = [
        {
            "lane": lane,
            "symbol": symbol,
            "divergence_counts": _counter_dict(counter),
            "total_divergences": sum(counter.values()),
        }
        for (lane, symbol), counter in sorted(lane_symbol_counts.items())
    ]
    filtered_matched_count = len(filtered_selected_rows)
    matching_pick_count = sum(1 for row in divergence_rows if row.get("materializer_decision") == "selected_candidate" and row.get("scanner_pick_matched"))
    if materializer_rows_in_window:
        status = "scanner_materializer_parity_diff_ready"
    else:
        status = "materializer_window_has_no_rows"
    if session_error:
        status = "blocked_scheduled_scan_session_source_unavailable"

    report = {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "scope": "track_c_phase_13_scanner_vs_materializer_parity_diff",
        "status": status,
        "window": {
            "start_date": start_date,
            "end_date": end,
            "market_day_count": len(dates),
            "default_start_basis": "2026-06-14_forward_freeze",
        },
        "inputs": {
            "materializer_decisions": materializer_meta,
            "materializer_latest": {"path": _rel(materializer_latest_path), "exists": materializer_latest_path.exists()},
            "scan_picks": scan_meta,
            "ledger_db": {"path": _rel(ledger_db_path), "exists": ledger_db_path.exists(), "status": "loaded" if not session_error else session_error},
            "policy_contract": policy_meta,
        },
        "materializer_coverage": {
            "row_count_total": len(materializer_rows),
            "row_count_in_window": len(materializer_rows_in_window),
            "selected_rows_in_window": sum(1 for row in materializer_rows_in_window if bool(row.get("selected_candidate"))),
            "filter_matched_selected_rows_in_window": filtered_matched_count,
            "earliest_materializer_date": materializer_date_range[0] if materializer_date_range else None,
            "latest_materializer_date": materializer_date_range[-1] if materializer_date_range else None,
            "current_default_window_note": (
                "Current materializer artifact ends before the default post-freeze window; no rows are invented."
                if not materializer_rows_in_window
                else None
            ),
        },
        "scheduled_scan_coverage": {
            "session_error": session_error,
            "session_count": len(sessions),
            "scan_pick_rows_in_window": sum(len(value) for value in scan_by_key.values()),
            "session_times_et": sorted({_norm(session.get("recorded_time_et")) for session in sessions if _norm(session.get("recorded_time_et"))}),
        },
        "summary": {
            "filtered_materializer_candidate_rows": filtered_matched_count,
            "matching_scheduled_scan_pick_rows": matching_pick_count,
            "matching_scheduled_scan_pick_rate_pct": round((matching_pick_count / filtered_matched_count) * 100.0, 2)
            if filtered_matched_count
            else None,
            "divergence_counts": _counter_dict(divergence_counts),
            "top_starvation_gate": _top_starvation_gate(divergence_counts),
        },
        "daily_table": daily_table,
        "divergence_rows": divergence_rows,
        "per_lane_symbol_summary": per_lane_symbol_summary,
        "boundary": {
            "diagnostic_only": True,
            "scan_config_changes_forbidden_until_refreeze": True,
            "refreeze_requires_explicit_operator_decision": True,
            "materializer_entry_window_et": MATERIALIZER_ENTRY_WINDOW_ET,
            "scheduled_sessions_are_production_scanner_distribution": True,
            "does_not_change_scanner": True,
        },
        "forbidden_actions": FORBIDDEN_ACTIONS,
        "read_only": True,
        "research_only": True,
        **FALSE_FLAGS,
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    summary = _as_dict(report.get("summary"))
    coverage = _as_dict(report.get("materializer_coverage"))
    scheduled = _as_dict(report.get("scheduled_scan_coverage"))
    top_gate = _as_dict(summary.get("top_starvation_gate"))
    session_times = _as_list(scheduled.get("session_times_et"))
    session_time_sample = session_times[:20]
    lines = [
        "# Regular Options Scanner Materializer Parity Diff",
        "",
        "This generated readback compares the deterministic materializer chain with scheduled scan-session output. It is diagnostic only and does not run or change the scanner.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Window: `{_as_dict(report.get('window')).get('start_date')}` to `{_as_dict(report.get('window')).get('end_date')}`.",
        f"- Materializer rows in window: `{coverage.get('row_count_in_window')}`.",
        f"- Filter-matched materializer selected rows: `{summary.get('filtered_materializer_candidate_rows')}`.",
        f"- Matching scheduled scan-pick rows: `{summary.get('matching_scheduled_scan_pick_rows')}`.",
        f"- Matching scheduled scan-pick rate: `{summary.get('matching_scheduled_scan_pick_rate_pct')}`.",
        f"- Scheduled sessions loaded: `{scheduled.get('session_count')}`.",
        f"- Top starvation gate: `{top_gate.get('gate')}` (`{top_gate.get('status')}`, `{top_gate.get('day_count')}` rows).",
        f"- Divergence counts: `{json.dumps(summary.get('divergence_counts') or {}, sort_keys=True)}`.",
        "",
        "## Boundary",
        "",
        "- Diagnostic only; scan config changes remain forbidden until the frozen-cohort evaluation/refreeze decision.",
        "- Any refreeze or scanner-policy change requires an explicit operator decision.",
        "- This script writes only its own generated report/artifacts and does not import quotes, mutate evidence stores, append cohorts, enable live validation, enable auto-track, submit broker orders, change proof bars, or consume protected holdout.",
        f"- Materializer entry window ET: `{_as_dict(report.get('boundary')).get('materializer_entry_window_et')}`.",
        f"- Scheduled session times ET observed: `{len(session_times)}` distinct times; sample `{json.dumps(session_time_sample)}`.",
        "",
        "## Materializer Coverage",
        "",
        f"- Total materializer rows loaded: `{coverage.get('row_count_total')}`.",
        f"- Earliest materializer date: `{coverage.get('earliest_materializer_date')}`.",
        f"- Latest materializer date: `{coverage.get('latest_materializer_date')}`.",
        f"- Current default-window note: {coverage.get('current_default_window_note') or 'n/a'}.",
        "",
        "## Daily Divergence Table",
        "",
        "| Date | Materializer Rows | Filter-Matched Selected | Scheduled Sessions | Scheduled Picks | Divergences |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in _as_list(report.get("daily_table"))[:80]:
        row = _as_dict(row)
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("date") or ""),
                    str(row.get("materializer_decision_rows") or 0),
                    str(row.get("materializer_filter_matched_selected_rows") or 0),
                    str(row.get("scheduled_session_count") or 0),
                    str(row.get("scheduled_scan_pick_count") or 0),
                    "`" + json.dumps(row.get("divergence_counts") or {}, sort_keys=True) + "`",
                ]
            )
            + " |"
        )
    lines.extend(["", "## Divergence Rows", ""])
    if not _as_list(report.get("divergence_rows")):
        lines.append("No divergence rows were classifiable in this window.")
    else:
        lines.extend(
            [
                "| Date | Lane | Symbol | Materializer | Scanner | Class |",
                "|---|---|---|---|---|---|",
            ]
        )
        for row in _as_list(report.get("divergence_rows"))[:100]:
            row = _as_dict(row)
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row.get("date") or ""),
                        str(row.get("lane") or ""),
                        str(row.get("symbol") or ""),
                        str(row.get("materializer_decision") or ""),
                        str(row.get("scanner_observation") or ""),
                        "`" + str(row.get("divergence_class") or "") + "`",
                    ]
                )
                + " |"
            )
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
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    artifacts = {
        "json": _rel(json_path),
        "latest_json": _rel(latest_json),
        "markdown": _rel(md_path),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
    }
    report["artifacts"] = artifacts
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(report) + "\n"
    json_path.write_text(payload, encoding="utf8")
    latest_json.write_text(payload, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return artifacts


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a read-only scanner-vs-materializer parity diff.")
    parser.add_argument("--materializer-decisions", type=Path, default=DEFAULT_MATERIALIZER_DECISIONS)
    parser.add_argument("--materializer-latest", type=Path, default=DEFAULT_MATERIALIZER_LATEST)
    parser.add_argument("--scan-picks", type=Path, default=DEFAULT_SCAN_PICKS)
    parser.add_argument("--ledger-db", type=Path, default=DEFAULT_LEDGER_DB)
    parser.add_argument("--policy-contract", type=Path, default=DEFAULT_POLICY_CONTRACT)
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(list(argv))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(
        materializer_decisions_path=args.materializer_decisions,
        materializer_latest_path=args.materializer_latest,
        scan_picks_path=args.scan_picks,
        ledger_db_path=args.ledger_db,
        policy_contract_path=args.policy_contract,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
