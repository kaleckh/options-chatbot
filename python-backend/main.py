"""
FastAPI backend for the options scanner and research UI.
Exposes tool dispatch plus scanner, replay, and position endpoints.
"""

import asyncio
import copy
import os
import sys
import json
import math
import sqlite3
import contextlib
import threading
from datetime import UTC, datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Any

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BACKEND_DIR)

# Add parent directory to path so we can import existing modules
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, BACKEND_DIR)

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency for local env loading
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(os.path.join(ROOT_DIR, ".env"))
    load_dotenv(os.path.join(ROOT_DIR, ".env.local"))

from options_chatbot import (
    log_prediction,
    TOOL_DISPATCH,
    STRATEGY_PROFILES,
    _load_predictions,
    _save_profile,
    scan_daily_top_trades,
    roll_forward_daily_picks,
    generate_position_recommendations,
    DEFAULT_SCAN_PICKS,
    DEFAULT_WATCHLIST,
    CHANGELOG_FILES,
)
from market_data_service import (
    download_history_batch as _md_download_history_batch,
    get_cache_stats as _md_get_cache_stats,
    request_scope as _market_data_request_scope,
    reset_cache_stats as _md_reset_cache_stats,
)

import wfo_optimizer as wfo_module
from wfo_optimizer import (
    ARCHIVED_FORWARD_SOURCE_LABEL,
    run_historical_backtest,
    run_archived_forward_daily_backtest,
    load_last_results_by_truth_lane,
    load_last_archived_forward_daily_results,
    load_preferred_results_by_truth_lane,
    build_prediction_replay_report,
    build_options_experiment_matrix,
    build_options_stability_report,
    build_live_options_trade_policy,
    build_playbook_exit_audit,
    build_truth_lane_comparison,
)
from metric_truth_audit import build_metric_truth_report
from options_profitability_forensics import build_options_profitability_forensics
from forward_options_ledger import (
    LIVE_PRODUCTION_EVIDENCE_CLASS,
    MANUAL_OBSERVATION_EVIDENCE_CLASS,
    archive_forward_ledger_db_path,
    authoritative_forward_ledger_db_path,
    build_forward_scan_snapshot,
    list_forward_scan_pick_events,
    list_forward_sessions,
    record_forward_snapshot,
    record_position_opened,
)
from positions_repository import create_positions_repository
from positions_service import build_position_payload, review_open_positions
from suggested_trades_repository import create_suggested_trades_repository
from supervised_scan import (
    LIVE_SCAN_TRUTH_LANE,
    run_supervised_scan,
    scan_pick_market_regime,
)
from options_profit_gate import evaluate_claim_readiness, evaluate_measurement_gate
from options_profit_state import build_read_only_profit_status_view, live_profile_entry_for_symbol

app = FastAPI(title="Options Chatbot Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── SQLite session management (shared DB with existing Streamlit app) ──────────

DB_PATH = os.path.join(ROOT_DIR, "chat_history.db")
POSITIONS_REPOSITORY = create_positions_repository(os.getenv("DATABASE_URL"))
SUGGESTED_TRADES_REPOSITORY = create_suggested_trades_repository(DB_PATH)
_REPORT_CACHE_LOCK = threading.Lock()
_PREFERRED_RESULTS_CACHE: dict[tuple[Any, ...], Any] = {}
_LAST_RESULTS_CACHE: dict[tuple[Any, ...], Any] = {}
_FORWARD_EVIDENCE_REPORT_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}
_READONLY_REPORT_OUTPUT_CACHE: dict[tuple[Any, ...], Any] = {}
_OPTIONS_PROFIT_SYMBOLS = ("SPY", "QQQ")


async def _run_in_worker(fn, /, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


def _options_profit_state_dir() -> Path:
    override = os.getenv("OPTIONS_PROFIT_STATE_DIR")
    if override:
        return Path(override).resolve()
    return Path(ROOT_DIR) / "data" / "options-profit"


def _read_json_artifact(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _default_profit_side_entry(symbol: str, direction: str) -> dict[str, Any]:
    normalized_symbol = str(symbol).strip().upper()
    normalized_direction = str(direction).strip().lower()
    return {
        "symbol": normalized_symbol,
        "direction": normalized_direction,
        "candidate_id": f"{normalized_symbol}__{normalized_direction}__baseline_broad_control",
        "cohort_id": "baseline_broad_control",
        "base_profile": "index",
        "overrides": {},
        "manifest_source": None,
        "source": "read_only_default",
        "mode": "incumbent",
        "status": "incumbent",
        "applied_at": None,
    }


def _default_options_profit_status() -> dict[str, Any]:
    active_incumbents = {
        symbol: {
            direction: _default_profit_side_entry(symbol, direction)
            for direction in ("call", "put")
        }
        for symbol in _OPTIONS_PROFIT_SYMBOLS
    }
    current_canary = {
        symbol: {
            direction: None
            for direction in ("call", "put")
        }
        for symbol in _OPTIONS_PROFIT_SYMBOLS
    }
    blocker = "Options profit cycle has not run yet."
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "daily_truth_refresh": None,
        "measurement_gate": {
            "state": "blocked",
            "blockers": [blocker],
            "warnings": [],
        },
        "active_incumbents": active_incumbents,
        "current_canary": current_canary,
        "last_decision": {
            "action": "not_started",
            "summary": blocker,
        },
        "blockers": [blocker],
    }


def _read_latest_options_profit_decision(state_dir: Path) -> dict[str, Any] | None:
    decisions_dir = state_dir / "decisions"
    if not decisions_dir.is_dir():
        return None
    try:
        decision_paths = sorted(
            (
                path
                for path in decisions_dir.iterdir()
                if path.is_file() and path.suffix.lower() == ".json"
            ),
            key=lambda path: path.name,
            reverse=True,
        )
    except Exception:
        return None
    for path in decision_paths:
        payload = _read_json_artifact(path)
        if payload:
            return payload
    return None


def _read_only_options_profit_status() -> dict[str, Any]:
    state_dir = _options_profit_state_dir()
    status_payload = _read_json_artifact(state_dir / "status.json") or {}
    live_profile = _read_json_artifact(state_dir / "live_profile.json") or {}
    incumbents_payload = _read_json_artifact(state_dir / "incumbents.json") or {}
    decision_payload = _read_latest_options_profit_decision(state_dir) or {}
    return build_read_only_profit_status_view(
        status_payload=status_payload,
        incumbents_payload=incumbents_payload,
        live_profile_payload=live_profile,
        decision_payload=decision_payload,
    )


@contextlib.contextmanager
def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Tool dispatch endpoint ────────────────────────────────────────────────────


@app.post("/api/tools/{tool_name}")
async def call_tool_endpoint(tool_name: str, body: dict[str, Any] = {}):
    """Execute any of the 16 tool functions by name."""
    fn = TOOL_DISPATCH.get(tool_name)
    if not fn:
        raise HTTPException(404, f"Unknown tool: {tool_name}")
    try:
        result = await _run_in_worker(fn, **body)
        return {"result": result}
    except Exception as e:
        return {"result": json.dumps({"error": type(e).__name__, "message": str(e)})}


# ── Profile endpoints ────────────────────────────────────────────────────────


@app.get("/api/profile")
async def get_profile(type: str = "equity"):
    """Return one strategy profile."""
    if type not in STRATEGY_PROFILES:
        raise HTTPException(400, f"Unknown profile type: {type}")
    return STRATEGY_PROFILES[type]


@app.get("/api/profiles")
async def get_profiles():
    """Return both strategy profiles."""
    return STRATEGY_PROFILES


@app.put("/api/profile")
async def update_profile(body: dict[str, Any]):
    """Update a strategy profile section."""
    profile_type = body.get("type", "equity")
    updates = body.get("updates", {})
    note = body.get("note", "")

    if profile_type not in STRATEGY_PROFILES:
        raise HTTPException(400, f"Unknown profile type: {profile_type}")

    sp = STRATEGY_PROFILES[profile_type]
    for section_key, section_val in updates.items():
        if section_key in sp and isinstance(sp[section_key], dict) and isinstance(section_val, dict):
            sp[section_key].update(section_val)

    _save_profile(note=note or f"{profile_type} profile updated", profile=profile_type)
    return {"ok": True}


# ── Predictions endpoints ────────────────────────────────────────────────────


@app.get("/api/predictions")
async def get_predictions():
    """Return all predictions."""
    return _load_predictions()


@app.post("/api/predictions/grade")
async def grade_predictions(body: dict[str, Any] = {}):
    """Grade predictions."""
    scan_date = body.get("scan_date")
    kwargs = {}
    if scan_date:
        kwargs["scan_date"] = scan_date
    result = log_prediction(action="grade", **kwargs)
    return json.loads(result)


@app.delete("/api/predictions/{pred_id}")
async def delete_prediction(pred_id: int):
    """Delete a prediction by ID."""
    result = log_prediction(action="delete", prediction_id=pred_id)
    return json.loads(result)


# ── Scan endpoints ────────────────────────────────────────────────────────────


def _normalize_scan_pick(pick: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(pick)
    normalized["prediction_type"] = pick.get("type")
    normalized["type"] = pick.get("direction")
    normalized["direction"] = pick.get("direction") or pick.get("type")
    normalized["option_type"] = pick.get("option_type") or pick.get("direction") or pick.get("type")
    normalized["contract_symbol"] = pick.get("contract_symbol") or pick.get("contractSymbol")
    normalized["ev"] = pick.get("ev_pct")
    normalized["strike"] = pick.get("strike") if pick.get("strike") is not None else pick.get("strike_est")
    normalized["premium"] = pick.get("premium") if pick.get("premium") is not None else pick.get("est_premium")
    normalized["mid"] = pick.get("mid") if pick.get("mid") is not None else normalized["premium"]
    normalized["delta"] = pick.get("delta") if pick.get("delta") is not None else pick.get("delta_est")
    normalized["iv_percentile"] = (
        pick.get("iv_percentile")
        if pick.get("iv_percentile") is not None
        else (
            pick.get("iv_pct")
            if pick.get("iv_pct") is not None
            else pick.get("iv_rank")
        )
    )
    normalized["iv_pct"] = (
        pick.get("iv_pct")
        if pick.get("iv_pct") is not None
        else normalized["iv_percentile"]
    )
    normalized["sector"] = pick.get("sector")
    normalized["market_regime"] = pick.get("market_regime") or scan_pick_market_regime(pick)
    normalized["policy_decision"] = pick.get("trade_policy_decision")
    normalized["policy_fit_score"] = pick.get("policy_fit_score")
    normalized["policy_fit_reasons"] = pick.get("policy_fit_reasons")
    normalized["playbook"] = pick.get("playbook_id")
    normalized["playbook_label"] = pick.get("playbook_label")
    normalized["guardrail_decision"] = pick.get("guardrail_decision")
    normalized["guardrail_reasons"] = pick.get("guardrail_reasons")
    normalized["suggested_size_tier"] = pick.get("suggested_size_tier")
    normalized["suggested_size_reason"] = pick.get("suggested_size_reason")
    normalized["quote_time_et"] = pick.get("quote_time_et")
    normalized["quote_basis"] = pick.get("quote_basis")
    normalized["quote_freshness_status"] = pick.get("quote_freshness_status")
    normalized["expectancy_selection_source"] = pick.get("expectancy_selection_source")
    normalized["underlying_price_at_selection"] = (
        pick.get("underlying_price_at_selection")
        if pick.get("underlying_price_at_selection") is not None
        else (pick.get("current_spot") if pick.get("current_spot") is not None else pick.get("stock_price"))
    )
    normalized["selection_source"] = (
        pick.get("selection_source")
        or pick.get("contract_selection_source")
    )
    normalized["promotion_class"] = pick.get("promotion_class")
    normalized["promotable"] = bool(pick.get("promotable"))
    normalized["options_snapshot_status"] = pick.get("options_snapshot_status")
    normalized["option_chain_status"] = pick.get("option_chain_status")
    normalized["managed_eligible"] = bool(pick.get("managed_eligible"))
    normalized["managed_block_reason"] = pick.get("managed_block_reason")
    normalized["bid"] = pick.get("bid")
    normalized["ask"] = pick.get("ask")
    normalized["last"] = pick.get("last")
    normalized["mid"] = pick.get("mid")
    normalized["entry_execution_price"] = pick.get("entry_execution_price")
    normalized["entry_execution_basis"] = pick.get("entry_execution_basis")
    normalized["entry_fee_total_usd"] = pick.get("entry_fee_total_usd")
    normalized["profitability_eligibility"] = pick.get("profitability_eligibility")
    normalized["profitability_blockers"] = pick.get("profitability_blockers")
    normalized["candidate_rank"] = pick.get("candidate_rank")
    live_profit_entry = live_profile_entry_for_symbol(
        str(normalized.get("ticker") or ""),
        str(normalized.get("direction") or ""),
    )
    if live_profit_entry:
        normalized["profit_candidate_id"] = (
            pick.get("profit_candidate_id")
            or live_profit_entry.get("candidate_id")
        )
        normalized["policy_artifact_id"] = (
            pick.get("policy_artifact_id")
            or live_profit_entry.get("candidate_id")
        )
        normalized["cohort_id"] = (
            pick.get("cohort_id")
            or live_profit_entry.get("cohort_id")
        )
        normalized["cohort_role"] = (
            pick.get("cohort_role")
            or live_profit_entry.get("mode")
            or live_profit_entry.get("status")
        )
    return normalized


def _normalize_scan_picks(picks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_picks: list[dict[str, Any]] = []
    for idx, pick in enumerate(list(picks or []), start=1):
        normalized = _normalize_scan_pick(pick)
        normalized["candidate_rank"] = int(normalized.get("candidate_rank") or idx)
        normalized_picks.append(normalized)
    return normalized_picks


def _scan_run_id() -> str:
    override = str(os.getenv("OPTIONS_RUN_ID") or "").strip()
    if override:
        return override
    return f"api_scan_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"


def _scan_run_mode() -> str:
    return str(os.getenv("OPTIONS_RUN_MODE") or "api_scan").strip() or "api_scan"


def _scan_evidence_class() -> str:
    explicit = str(os.getenv("OPTIONS_EVIDENCE_CLASS") or "").strip().lower()
    if explicit:
        return explicit
    if str(os.getenv("PYTEST_CURRENT_TEST") or "").strip():
        return "e2e_test"
    return LIVE_PRODUCTION_EVIDENCE_CLASS


def _scan_is_fixture() -> bool:
    value = str(os.getenv("OPTIONS_IS_FIXTURE") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _scan_policy_artifact_id(result: dict[str, Any]) -> str | None:
    policy = dict(result.get("policy") or {})
    for key in ("policy_artifact_id", "run_id", "generated_at", "source_run_at"):
        value = str(policy.get(key) or "").strip()
        if value:
            return value
    return None


def _artifact_mtime(path: str) -> tuple[str, float | None]:
    if not os.path.exists(path):
        return (path, None)
    return (path, os.path.getmtime(path))


def _preferred_results_cache_key(truth_lane: str | None) -> tuple[Any, ...]:
    return (
        str(truth_lane or "").strip() or None,
        _artifact_mtime(wfo_module.OPTIONS_VALIDATION_LATEST_FILE),
        _artifact_mtime(wfo_module.OPTIONS_VALIDATION_DAILY_LATEST_FILE),
        _artifact_mtime(wfo_module.OPTIONS_VALIDATION_DAILY_FORWARD_LATEST_FILE),
    )


def _forward_evidence_cache_key() -> tuple[Any, ...]:
    authoritative_path = str(authoritative_forward_ledger_db_path())
    archive_path = str(archive_forward_ledger_db_path())
    evidence_path = os.path.join(
        os.path.dirname(os.path.abspath(authoritative_path)),
        "forward_evidence_events.jsonl",
    )
    return (
        _artifact_mtime(authoritative_path),
        _artifact_mtime(archive_path),
        _artifact_mtime(evidence_path),
        _artifact_mtime(wfo_module.OPTIONS_VALIDATION_DAILY_FORWARD_LATEST_FILE),
    )


def _cached_preferred_results_by_truth_lane(truth_lane: str | None) -> Any:
    key = _preferred_results_cache_key(truth_lane)
    with _REPORT_CACHE_LOCK:
        if key in _PREFERRED_RESULTS_CACHE:
            return _PREFERRED_RESULTS_CACHE[key]
    result = load_preferred_results_by_truth_lane(truth_lane)
    with _REPORT_CACHE_LOCK:
        _PREFERRED_RESULTS_CACHE[key] = copy.deepcopy(result)
        return copy.deepcopy(_PREFERRED_RESULTS_CACHE[key])


def _cached_last_results_by_truth_lane(truth_lane: str | None) -> Any:
    key = ("last",) + _preferred_results_cache_key(truth_lane)
    with _REPORT_CACHE_LOCK:
        if key in _LAST_RESULTS_CACHE:
            return _LAST_RESULTS_CACHE[key]
    result = load_last_results_by_truth_lane(truth_lane)
    with _REPORT_CACHE_LOCK:
        _LAST_RESULTS_CACHE[key] = copy.deepcopy(result)
        return copy.deepcopy(_LAST_RESULTS_CACHE[key])


def _cached_forward_evidence_report() -> dict[str, Any]:
    key = _forward_evidence_cache_key()
    with _REPORT_CACHE_LOCK:
        if key in _FORWARD_EVIDENCE_REPORT_CACHE:
            return _FORWARD_EVIDENCE_REPORT_CACHE[key]
    report = _build_forward_evidence_report()
    with _REPORT_CACHE_LOCK:
        _FORWARD_EVIDENCE_REPORT_CACHE[key] = copy.deepcopy(report)
        return copy.deepcopy(_FORWARD_EVIDENCE_REPORT_CACHE[key])


def _cached_readonly_report(key: tuple[Any, ...], builder) -> Any:
    with _REPORT_CACHE_LOCK:
        if key in _READONLY_REPORT_OUTPUT_CACHE:
            return copy.deepcopy(_READONLY_REPORT_OUTPUT_CACHE[key])
    report = builder()
    with _REPORT_CACHE_LOCK:
        _READONLY_REPORT_OUTPUT_CACHE[key] = copy.deepcopy(report)
        return copy.deepcopy(_READONLY_REPORT_OUTPUT_CACHE[key])


def _record_forward_truth_for_scan(
    *,
    result: dict[str, Any],
    normalized_picks: list[dict[str, Any]],
) -> dict[str, Any]:
    tracked_positions = None
    positions_error = None
    if getattr(POSITIONS_REPOSITORY, "is_available", False):
        try:
            tracked_positions = POSITIONS_REPOSITORY.list_positions("open")
        except Exception as exc:
            tracked_positions = []
            positions_error = f"tracked_positions_snapshot_failed: {exc}"
    else:
        positions_error = getattr(POSITIONS_REPOSITORY, "error_message", None)

    evidence_class = _scan_evidence_class()
    scan_snapshot = build_forward_scan_snapshot(
        picks=normalized_picks,
        policy_applied=bool(result.get("policy_applied")),
        policy=result.get("policy"),
        policy_error=result.get("policy_error"),
        playbook=result.get("playbook"),
        truth_lane=result.get("truth_lane"),
        scan_funnel=result.get("scan_funnel"),
        policy_decision_counts=result.get("policy_decision_counts"),
        guardrail_decision_counts=result.get("guardrail_decision_counts"),
        candidate_count=result.get("candidate_count"),
        returned_count=result.get("returned_count"),
        playbook_exit_audit=result.get("playbook_exit_audit"),
        playbook_exit_audit_error=result.get("playbook_exit_audit_error"),
        exposure_snapshot=result.get("exposure_snapshot"),
        positions_error=positions_error,
        run_id=_scan_run_id(),
        run_mode=_scan_run_mode(),
        evidence_class=evidence_class,
        is_fixture=_scan_is_fixture(),
        policy_artifact_id=_scan_policy_artifact_id(result),
    )
    recorded = record_forward_snapshot(
        scan_snapshot=scan_snapshot,
        reviewed_positions=[],
        tracked_positions=tracked_positions,
        source_label=ARCHIVED_FORWARD_SOURCE_LABEL,
    )
    return {
        "forward_truth_recorded": True,
        "forward_truth_session_id": recorded.get("session_id"),
        "forward_truth_error": None,
        "forward_truth_evidence_class": evidence_class,
        "forward_truth_authoritative": evidence_class == LIVE_PRODUCTION_EVIDENCE_CLASS,
    }


def _position_event_payload(position: dict[str, Any], *, reason: str) -> dict[str, Any]:
    payload = copy.deepcopy(position)
    latest_review = dict(payload.get("latest_review") or {})
    if not latest_review:
        latest_review = {
            "reviewed_at": payload.get("closed_at") or payload.get("last_reviewed_at") or datetime.now().isoformat(),
            "pricing_source": payload.get("exit_execution_basis") or reason,
            "current_option_price": payload.get("exit_option_price") or payload.get("last_option_price"),
            "current_pnl_pct": payload.get("gross_pnl_pct") or payload.get("last_pnl_pct"),
            "gross_pnl_pct": payload.get("gross_pnl_pct"),
            "net_pnl_pct": payload.get("net_pnl_pct"),
            "gross_pnl_usd": payload.get("gross_pnl_usd"),
            "net_pnl_usd": payload.get("net_pnl_usd"),
            "entry_execution_price": payload.get("entry_execution_price"),
            "exit_execution_price": payload.get("exit_execution_price"),
            "entry_execution_basis": payload.get("entry_execution_basis"),
            "exit_execution_basis": payload.get("exit_execution_basis") or reason,
            "fee_total_usd": payload.get("fee_total_usd"),
            "recommendation": "SELL" if str(payload.get("status") or "").strip().lower() == "closed" else payload.get("last_recommendation"),
            "reason": reason,
            "warnings": [],
            "metrics_snapshot": {},
        }
    payload["latest_review"] = latest_review
    return payload


def _record_forward_truth_for_position_events(
    *,
    reviewed_positions: list[dict[str, Any]],
    run_mode: str,
    reason: str,
) -> None:
    if not reviewed_positions:
        return
    tracked_positions = None
    positions_error = None
    if getattr(POSITIONS_REPOSITORY, "is_available", False):
        try:
            tracked_positions = POSITIONS_REPOSITORY.list_positions("all")
        except Exception as exc:
            tracked_positions = []
            positions_error = f"tracked_positions_snapshot_failed: {exc}"
    else:
        positions_error = getattr(POSITIONS_REPOSITORY, "error_message", None)
    evidence_class = _scan_evidence_class()
    scan_snapshot = build_forward_scan_snapshot(
        picks=[],
        policy_applied=True,
        policy={"truth_source": LIVE_SCAN_TRUTH_LANE, "promotion_status": "observed"},
        playbook={"id": "tracked_positions"},
        truth_lane=LIVE_SCAN_TRUTH_LANE,
        positions_error=positions_error,
        run_id=_scan_run_id(),
        run_mode=run_mode,
        evidence_class=evidence_class,
        is_fixture=_scan_is_fixture(),
        policy_artifact_id=reason,
    )
    record_forward_snapshot(
        scan_snapshot=scan_snapshot,
        reviewed_positions=[_position_event_payload(position, reason=reason) for position in reviewed_positions],
        tracked_positions=tracked_positions,
        source_label=ARCHIVED_FORWARD_SOURCE_LABEL,
    )


def _forward_evidence_log_path() -> str:
    ledger_path = str(authoritative_forward_ledger_db_path())
    return os.path.join(os.path.dirname(os.path.abspath(ledger_path)), "forward_evidence_events.jsonl")


def _append_forward_evidence_event(
    *,
    recorded: bool,
    session_id: int | None,
    error: str | None,
    picks: list[dict[str, Any]],
    evidence_class: str | None = None,
) -> None:
    normalized_evidence_class = str(evidence_class or MANUAL_OBSERVATION_EVIDENCE_CLASS).strip().lower()
    payload = {
        "recorded_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source_label": ARCHIVED_FORWARD_SOURCE_LABEL,
        "forward_truth_recorded": bool(recorded),
        "forward_truth_session_id": session_id,
        "forward_truth_error": str(error) if error else None,
        "evidence_class": normalized_evidence_class,
        "forward_truth_authoritative": bool(recorded) and normalized_evidence_class == LIVE_PRODUCTION_EVIDENCE_CLASS,
        "scan_pick_count": len(list(picks or [])),
        "exact_contract_capture_count": sum(
            1 for pick in list(picks or []) if str(pick.get("contract_symbol") or "").strip()
        ),
    }
    path = _forward_evidence_log_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf8") as handle:
        handle.write(json.dumps(payload) + "\n")


def _read_forward_evidence_events(limit: int = 200) -> list[dict[str, Any]]:
    path = _forward_evidence_log_path()
    if not os.path.exists(path):
        return []
    events: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw:
                continue
            try:
                events.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    if limit > 0:
        return events[-int(limit):]
    return events


def _latest_artifact_timestamp(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    return datetime.fromtimestamp(os.path.getmtime(path)).isoformat(timespec="seconds")


def _build_forward_evidence_report() -> dict[str, Any]:
    authoritative_db_path = authoritative_forward_ledger_db_path()
    archive_db_path = archive_forward_ledger_db_path()
    authoritative_events = list_forward_scan_pick_events(
        source_label=ARCHIVED_FORWARD_SOURCE_LABEL,
        eligible_only=True,
        db_path=authoritative_db_path,
    )
    authoritative_all_events = list_forward_scan_pick_events(
        source_label=ARCHIVED_FORWARD_SOURCE_LABEL,
        db_path=authoritative_db_path,
    )
    observation_events = list_forward_scan_pick_events(
        source_label=ARCHIVED_FORWARD_SOURCE_LABEL,
        db_path=archive_db_path,
    ) if archive_db_path.resolve() != authoritative_db_path.resolve() else list(authoritative_all_events)
    recent_sessions = list_forward_sessions(
        limit=25,
        source_label=ARCHIVED_FORWARD_SOURCE_LABEL,
        db_path=authoritative_db_path,
    )
    authoritative_sessions = list_forward_sessions(
        limit=25,
        source_label=ARCHIVED_FORWARD_SOURCE_LABEL,
        evidence_class=LIVE_PRODUCTION_EVIDENCE_CLASS,
        eligibility_status="eligible",
        db_path=authoritative_db_path,
    )
    authoritative_exact_contract_count = sum(
        1 for event in authoritative_all_events if str(event.get("contract_symbol") or "").strip()
    )
    events = _read_forward_evidence_events()
    latest_event = events[-1] if events else None
    failure_events = [event for event in events if not bool(event.get("forward_truth_recorded"))]
    latest_failure = failure_events[-1] if failure_events else None
    authoritative_log_events = [
        event for event in events
        if bool(event.get("forward_truth_authoritative"))
    ]
    latest_authoritative_event = authoritative_log_events[-1] if authoritative_log_events else None
    latest_artifact = load_last_archived_forward_daily_results()
    latest_artifact_path = wfo_module.OPTIONS_VALIDATION_DAILY_FORWARD_LATEST_FILE
    latest_artifact_timestamp = _latest_artifact_timestamp(latest_artifact_path)
    historical_evidence_available = len(authoritative_all_events) > 0
    latest_capture_created_picks = bool(latest_authoritative_event) and int(latest_authoritative_event.get("scan_pick_count") or 0) > 0
    if latest_capture_created_picks:
        activation_status = "active"
        activation_message = "The latest eligible live-production capture created authoritative archived scan_pick evidence."
    elif latest_event and str(latest_event.get("evidence_class") or "").strip().lower() != LIVE_PRODUCTION_EVIDENCE_CLASS:
        activation_status = "observation_only_latest_scan"
        activation_message = "The latest /api/scan was recorded as observation-only and did not enter the authoritative forward lane."
    elif historical_evidence_available:
        activation_status = "historical_evidence_only_latest_scan_empty"
        activation_message = "Authoritative archived forward evidence exists, but the latest eligible live-production capture did not add new scan_pick rows."
    else:
        activation_status = "archived_forward_unavailable"
        activation_message = "No eligible live-production scan_pick events are archived yet, so archived-forward profitability remains unavailable."
    artifact_available = bool(latest_artifact) and not bool(latest_artifact.get("insufficient_archived_evidence"))

    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source_label": ARCHIVED_FORWARD_SOURCE_LABEL,
        "recent_session_count": len(recent_sessions),
        "authoritative_session_count": len(authoritative_sessions),
        "scan_pick_count": len(authoritative_all_events),
        "eligible_scan_pick_count": len(authoritative_events),
        "exact_contract_capture_counts": {
            "with_contract_count": authoritative_exact_contract_count,
            "without_contract_count": max(len(authoritative_all_events) - authoritative_exact_contract_count, 0),
        },
        "forward_truth_recording_failure_count": len(failure_events),
        "latest_archived_forward_artifact_timestamp": latest_artifact_timestamp,
        "activation_check": {
            "active": latest_capture_created_picks,
            "status": activation_status,
            "message": activation_message,
            "historical_evidence_available": historical_evidence_available,
            "latest_recorded_scan_pick_count": int(latest_authoritative_event.get("scan_pick_count") or 0) if latest_authoritative_event else 0,
        },
        "recording_health": {
            "events_logged": len(events),
            "recorded_success_count": sum(1 for event in events if bool(event.get("forward_truth_recorded"))),
            "recorded_failure_count": len(failure_events),
            "latest_event": latest_event,
            "latest_failure": latest_failure,
            "latest_authoritative_event": latest_authoritative_event,
        },
        "ledger_summary": {
            "available": historical_evidence_available,
            "authoritative_db_path": str(authoritative_db_path),
            "archive_db_path": str(archive_db_path),
            "scan_pick_count": len(authoritative_all_events),
            "eligible_scan_pick_count": len(authoritative_events),
            "observation_scan_pick_count": len(observation_events),
            "recent_session_count": len(recent_sessions),
            "authoritative_session_count": len(authoritative_sessions),
        },
        "archived_forward_artifact": {
            "available": artifact_available,
            "path": latest_artifact_path,
            "run_at": latest_artifact.get("run_at") if latest_artifact else None,
            "evidence_status": latest_artifact.get("evidence_status") if latest_artifact else None,
            "primary_judge_trade_count": int(latest_artifact.get("primary_judge_trade_count") or 0) if latest_artifact else 0,
            "primary_judge_fallback_used": bool(latest_artifact.get("primary_judge_fallback_used")) if latest_artifact else False,
            "primary_judge_fallback_reason": latest_artifact.get("primary_judge_fallback_reason") if latest_artifact else None,
            "pending_truth_horizon_count": int(latest_artifact.get("pending_truth_horizon_count") or 0) if latest_artifact else 0,
            "contract_resolution_overview": dict(latest_artifact.get("contract_resolution_overview") or {}) if latest_artifact else {},
            "archived_sample_date_coverage": dict(latest_artifact.get("archived_sample_date_coverage") or {}) if latest_artifact else {},
        },
    }


def _build_backtest_report(truth_lane: str | None, min_trades: int) -> dict[str, Any]:
    return build_prediction_replay_report(
        result=_cached_preferred_results_by_truth_lane(truth_lane),
        min_trades=min_trades,
    )


def _build_metric_truth_report(truth_lane: str | None, min_trades: int, bucket_size: int) -> dict[str, Any]:
    result = _cached_preferred_results_by_truth_lane(truth_lane)
    if not result:
        return {"error": "No backtest results found"}
    return build_metric_truth_report(
        result=result,
        min_trades=min_trades,
        bucket_size=bucket_size,
    )


def _build_backtest_experiments(body: dict[str, Any]) -> dict[str, Any]:
    return build_options_experiment_matrix(
        result=_cached_preferred_results_by_truth_lane(body.get("truth_lane")),
        min_trades=body.get("min_trades", 20),
        score_floors=body.get("score_floors"),
        max_tickers=body.get("max_tickers", 8),
        max_sectors=body.get("max_sectors", 8),
        min_profit_factor=body.get("min_profit_factor", 1.05),
        min_directional_accuracy_pct=body.get("min_directional_accuracy_pct", 50.0),
    )


def _build_backtest_profitability_forensics(
    min_trades: int,
    truth_lane: str | None,
) -> dict[str, Any]:
    return build_options_profitability_forensics(
        result=_cached_preferred_results_by_truth_lane(truth_lane),
        min_trades=min_trades,
    )


def _build_backtest_stability(
    min_trades: int,
    min_profit_factor: float,
    truth_lane: str | None,
) -> dict[str, Any]:
    return build_options_stability_report(
        result=_cached_preferred_results_by_truth_lane(truth_lane),
        min_trades=min_trades,
        min_profit_factor=min_profit_factor,
    )


def _build_live_trade_policy_report(
    min_trades: int,
    max_tickers: int,
    max_sectors: int,
    min_profit_factor: float,
    min_directional_accuracy_pct: float,
    truth_lane: str | None,
) -> dict[str, Any]:
    return build_live_options_trade_policy(
        truth_lane=truth_lane,
        min_trades=min_trades,
        max_tickers=max_tickers,
        max_sectors=max_sectors,
        min_profit_factor=min_profit_factor,
        min_directional_accuracy_pct=min_directional_accuracy_pct,
    )


def _build_playbook_exit_audit_report(
    playbook: str,
    min_trades: int,
    max_tickers: int,
    max_sectors: int,
    min_profit_factor: float,
    min_directional_accuracy_pct: float,
    truth_lane: str | None,
) -> dict[str, Any]:
    return build_playbook_exit_audit(
        playbook=playbook,
        truth_lane=truth_lane,
        min_trades=min_trades,
        max_tickers=max_tickers,
        max_sectors=max_sectors,
        min_profit_factor=min_profit_factor,
        min_directional_accuracy_pct=min_directional_accuracy_pct,
    )


def _build_truth_lane_comparison_report(truth_lane: str | None) -> dict[str, Any]:
    return build_truth_lane_comparison(truth_lane=truth_lane)


def _cached_backtest_report(truth_lane: str | None, min_trades: int) -> dict[str, Any]:
    key = ("backtest_report", _preferred_results_cache_key(truth_lane), int(min_trades))
    return _cached_readonly_report(key, lambda: _build_backtest_report(truth_lane, min_trades))


def _cached_metric_truth_report(truth_lane: str | None, min_trades: int, bucket_size: int) -> dict[str, Any]:
    key = (
        "metric_truth_report",
        _preferred_results_cache_key(truth_lane),
        int(min_trades),
        int(bucket_size),
    )
    return _cached_readonly_report(
        key,
        lambda: _build_metric_truth_report(truth_lane, min_trades, bucket_size),
    )


def _cached_backtest_experiments(body: dict[str, Any]) -> dict[str, Any]:
    key = (
        "backtest_experiments",
        _preferred_results_cache_key(body.get("truth_lane")),
        json.dumps(body, sort_keys=True, default=str),
    )
    return _cached_readonly_report(key, lambda: _build_backtest_experiments(body))


def _cached_backtest_profitability_forensics(
    min_trades: int,
    truth_lane: str | None,
) -> dict[str, Any]:
    key = (
        "backtest_profitability_forensics",
        _preferred_results_cache_key(truth_lane),
        int(min_trades),
    )
    return _cached_readonly_report(
        key,
        lambda: _build_backtest_profitability_forensics(min_trades, truth_lane),
    )


def _cached_backtest_stability(
    min_trades: int,
    min_profit_factor: float,
    truth_lane: str | None,
) -> dict[str, Any]:
    key = (
        "backtest_stability",
        _preferred_results_cache_key(truth_lane),
        int(min_trades),
        float(min_profit_factor),
    )
    return _cached_readonly_report(
        key,
        lambda: _build_backtest_stability(min_trades, min_profit_factor, truth_lane),
    )


def _cached_live_trade_policy_report(
    min_trades: int,
    max_tickers: int,
    max_sectors: int,
    min_profit_factor: float,
    min_directional_accuracy_pct: float,
    truth_lane: str | None,
) -> dict[str, Any]:
    key = (
        "live_trade_policy",
        _preferred_results_cache_key(truth_lane),
        int(min_trades),
        int(max_tickers),
        int(max_sectors),
        float(min_profit_factor),
        float(min_directional_accuracy_pct),
    )
    return _cached_readonly_report(
        key,
        lambda: _build_live_trade_policy_report(
            min_trades,
            max_tickers,
            max_sectors,
            min_profit_factor,
            min_directional_accuracy_pct,
            truth_lane,
        ),
    )


def _cached_playbook_exit_audit_report(
    playbook: str,
    min_trades: int,
    max_tickers: int,
    max_sectors: int,
    min_profit_factor: float,
    min_directional_accuracy_pct: float,
    truth_lane: str | None,
) -> dict[str, Any]:
    key = (
        "playbook_exit_audit",
        _preferred_results_cache_key(truth_lane),
        str(playbook),
        int(min_trades),
        int(max_tickers),
        int(max_sectors),
        float(min_profit_factor),
        float(min_directional_accuracy_pct),
    )
    return _cached_readonly_report(
        key,
        lambda: _build_playbook_exit_audit_report(
            playbook,
            min_trades,
            max_tickers,
            max_sectors,
            min_profit_factor,
            min_directional_accuracy_pct,
            truth_lane,
        ),
    )


def _cached_truth_lane_comparison_report(truth_lane: str | None) -> dict[str, Any]:
    key = ("truth_lane_comparison", _preferred_results_cache_key(truth_lane))
    return _cached_readonly_report(key, lambda: _build_truth_lane_comparison_report(truth_lane))


def _build_backtest_summary(
    truth_lane: str | None,
    min_trades: int,
    bucket_size: int,
) -> dict[str, Any]:
    return {
        "last": _cached_last_results_by_truth_lane(truth_lane) or {"error": "No backtest results found"},
        "report": _cached_backtest_report(truth_lane, min_trades),
        "metricTruth": _cached_metric_truth_report(truth_lane, min_trades, bucket_size),
        "profitabilityForensics": _cached_backtest_profitability_forensics(min_trades, truth_lane),
        "comparison": _cached_truth_lane_comparison_report(truth_lane),
    }


def _positions_unavailable_response():
    message = getattr(POSITIONS_REPOSITORY, "error_message", None) or (
        "Tracked positions storage is unavailable."
    )
    return {"error": message}


def _suggested_trades_unavailable_response():
    message = getattr(SUGGESTED_TRADES_REPOSITORY, "error_message", None) or (
        "Suggested trades storage is unavailable."
    )
    return {"error": message}


def _parse_position_ids(raw_ids: Any) -> list[int] | None:
    if raw_ids in (None, "", []):
        return None
    if not isinstance(raw_ids, list):
        raise ValueError("position_ids must be a list of positive integers.")

    parsed: list[int] = []
    seen: set[int] = set()
    for value in raw_ids:
        if isinstance(value, bool):
            raise ValueError("position_ids must be a list of positive integers.")
        if isinstance(value, int):
            parsed_id = value
        elif isinstance(value, str) and value.strip().isdigit():
            parsed_id = int(value.strip())
        else:
            raise ValueError("position_ids must be a list of positive integers.")

        if parsed_id <= 0:
            raise ValueError("position_ids must be a list of positive integers.")
        if parsed_id not in seen:
            seen.add(parsed_id)
            parsed.append(parsed_id)
    return parsed


def _group_rows_by_status(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    open_rows: list[dict[str, Any]] = []
    closed_rows: list[dict[str, Any]] = []
    for row in list(rows or []):
        status = str(row.get("status") or "").strip().lower()
        if status == "closed" or row.get("closed_at"):
            closed_rows.append(row)
        else:
            open_rows.append(row)
    return {"open": open_rows, "closed": closed_rows}


def _parse_positive_price(value: Any, field_name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a finite number greater than 0.")
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError(f"{field_name} must be a finite number greater than 0.")
    return parsed


def _run_supervised_scan_request(
    body: dict[str, Any],
    *,
    n_picks: int,
    include_policy_flags: bool = False,
) -> dict[str, Any]:
    return run_supervised_scan(
        scan_func=scan_daily_top_trades,
        positions_repository=POSITIONS_REPOSITORY,
        n_picks=n_picks,
        watchlist_size=len(DEFAULT_WATCHLIST),
        playbook_id=body.get("playbook"),
        use_recommended_policy=bool(body.get("use_recommended_policy", True)),
        include_blocked_policy_picks=bool(body.get("include_blocked_policy_picks"))
        if include_policy_flags
        else False,
        include_blocked_guardrail_picks=bool(body.get("include_blocked_guardrail_picks"))
        if include_policy_flags
        else False,
        truth_lane=body.get("truth_lane") or LIVE_SCAN_TRUTH_LANE,
        min_trades=int(body.get("min_trades", 20)),
        max_tickers=int(body.get("max_tickers", 8)),
        max_sectors=int(body.get("max_sectors", 8)),
        min_profit_factor=float(body.get("min_profit_factor", 1.05)),
        min_directional_accuracy_pct=float(body.get("min_directional_accuracy_pct", 50.0)),
    )


@app.post("/api/scan")
async def run_scan_endpoint(body: dict[str, Any] = {}):
    """Run daily top trades scan."""
    n_picks = int(body.get("n_picks", DEFAULT_SCAN_PICKS))
    try:
        result = await _run_in_worker(
            _run_supervised_scan_request,
            body,
            n_picks=n_picks,
            include_policy_flags=True,
        )
        normalized_picks = _normalize_scan_picks(result["picks"])
        normalized_watch_picks = _normalize_scan_picks(result.get("watch_picks") or [])
        forward_truth_meta = {
            "forward_truth_recorded": False,
            "forward_truth_session_id": None,
            "forward_truth_error": None,
            "forward_truth_evidence_class": _scan_evidence_class(),
            "forward_truth_authoritative": False,
        }
        try:
            forward_truth_meta = await _run_in_worker(
                _record_forward_truth_for_scan,
                result=result,
                normalized_picks=normalized_picks,
            )
        except Exception as exc:
            forward_truth_meta = {
                "forward_truth_recorded": False,
                "forward_truth_session_id": None,
                "forward_truth_error": str(exc),
                "forward_truth_evidence_class": _scan_evidence_class(),
                "forward_truth_authoritative": False,
        }
        try:
            await _run_in_worker(
                _append_forward_evidence_event,
                recorded=bool(forward_truth_meta.get("forward_truth_recorded")),
                session_id=forward_truth_meta.get("forward_truth_session_id"),
                error=forward_truth_meta.get("forward_truth_error"),
                picks=normalized_picks,
                evidence_class=forward_truth_meta.get("forward_truth_evidence_class"),
            )
        except Exception:
            pass
        return {
            **{key: value for key, value in result.items() if key not in {"picks", "ranked_picks", "watch_picks"}},
            "picks": normalized_picks,
            "watch_picks": normalized_watch_picks,
            **forward_truth_meta,
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/positions")
async def create_position_endpoint(body: dict[str, Any]):
    """Track a user-confirmed options position from a live scan pick."""
    if not getattr(POSITIONS_REPOSITORY, "is_available", False):
        return _positions_unavailable_response()

    try:
        payload = build_position_payload(
            scan_pick=body.get("scan_pick") or {},
            fill_price=float(body.get("fill_price") or 0.0),
            contracts=int(body.get("contracts") or 0),
            filled_at=body.get("filled_at"),
            notes=body.get("notes"),
        )
        position = POSITIONS_REPOSITORY.create_position(payload)
        try:
            await _run_in_worker(
                record_position_opened,
                position=position,
                source_label="position_opened",
                evidence_class=_scan_evidence_class(),
                run_id=_scan_run_id(),
                run_mode="position_opened",
                is_fixture=_scan_is_fixture(),
            )
        except Exception:
            pass
        return {"position": position}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/positions")
async def list_positions_endpoint(status: str = "open", grouped: bool = False):
    """Return tracked options positions from local Postgres."""
    if not getattr(POSITIONS_REPOSITORY, "is_available", False):
        return _positions_unavailable_response()

    if status not in {"open", "closed", "all"}:
        raise HTTPException(400, "status must be one of: open, closed, all")

    try:
        query_status = None if status == "all" else status
        positions = POSITIONS_REPOSITORY.list_positions(query_status)
        if grouped:
            return _group_rows_by_status(positions)
        return {"positions": positions}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/positions/review")
async def review_positions_endpoint(body: dict[str, Any] = {}):
    """Review open tracked positions and return HOLD/SELL guidance."""
    if not getattr(POSITIONS_REPOSITORY, "is_available", False):
        return _positions_unavailable_response()

    try:
        position_ids = _parse_position_ids(body.get("position_ids"))
        reviewed = await _run_in_worker(review_open_positions, POSITIONS_REPOSITORY, position_ids=position_ids)
        try:
            await _run_in_worker(
                _record_forward_truth_for_position_events,
                reviewed_positions=reviewed,
                run_mode="positions_review",
                reason="tracked_positions_review",
            )
        except Exception:
            pass
        return {"positions": reviewed}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/positions/{position_id}/close-prefill")
async def close_prefill_endpoint(position_id: int):
    """Return prefilled exit data from the latest review for a tracked position."""
    if not getattr(POSITIONS_REPOSITORY, "is_available", False):
        return _positions_unavailable_response()

    try:
        position = POSITIONS_REPOSITORY.get_position(position_id)
        if position is None:
            raise HTTPException(404, f"Tracked position {position_id} was not found")
        if str(position.get("status") or "").strip().lower() != "open":
            raise HTTPException(409, f"Tracked position {position_id} is already closed")

        latest_review = position.get("latest_review") or {}
        metrics = latest_review.get("metrics_snapshot") or {}
        exit_execution_price = (
            latest_review.get("exit_execution_price")
            or position.get("exit_execution_price")
        )
        exit_execution_basis = (
            latest_review.get("exit_execution_basis")
            or position.get("exit_execution_basis")
        )
        pricing_state = metrics.get("pricing_state")

        return {
            "position_id": position_id,
            "ticker": position.get("ticker"),
            "contract_symbol": position.get("contract_symbol"),
            "prefill_available": exit_execution_price is not None,
            "exit_execution_price": exit_execution_price,
            "exit_execution_basis": exit_execution_basis,
            "pricing_state": pricing_state,
            "current_option_price": latest_review.get("current_option_price"),
            "recommendation": latest_review.get("recommendation"),
            "reason": latest_review.get("reason"),
            "reviewed_at": latest_review.get("reviewed_at"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/positions/{position_id}/close")
async def close_position_endpoint(position_id: int, body: dict[str, Any]):
    """Mark a tracked position closed after the user exits it."""
    if not getattr(POSITIONS_REPOSITORY, "is_available", False):
        return _positions_unavailable_response()

    if body.get("exit_price") is None:
        raise HTTPException(400, "exit_price is required")

    try:
        closed_at_raw = body.get("closed_at")
        closed_at = datetime.fromisoformat(closed_at_raw.replace("Z", "+00:00")) if closed_at_raw else datetime.now()
        position = POSITIONS_REPOSITORY.close_position(
            position_id=position_id,
            exit_price=_parse_positive_price(body.get("exit_price"), "exit_price"),
            closed_at=closed_at,
            exit_reason="manual_close",
            notes=body.get("notes"),
        )
        if position is None:
            raise HTTPException(404, f"Tracked position {position_id} was not found")
        try:
            await _run_in_worker(
                _record_forward_truth_for_position_events,
                reviewed_positions=[position],
                run_mode="positions_close",
                reason="manual_close",
            )
        except Exception:
            pass
        return {"position": position}
    except HTTPException:
        raise
    except ValueError as exc:
        message = str(exc)
        status = 409 if "already closed" in message.lower() or "not open" in message.lower() else 400
        raise HTTPException(status, message)
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/suggested-trades")
async def create_suggested_trade_endpoint(body: dict[str, Any]):
    """Save a hypothetical scanner trade for later mark-to-market review."""
    if not getattr(SUGGESTED_TRADES_REPOSITORY, "is_available", False):
        return _suggested_trades_unavailable_response()

    try:
        payload = build_position_payload(
            scan_pick=body.get("scan_pick") or {},
            fill_price=float(body.get("fill_price") or 0.0),
            contracts=int(body.get("contracts") or 1),
            filled_at=body.get("filled_at"),
            notes=body.get("notes"),
        )
        trade = SUGGESTED_TRADES_REPOSITORY.create_position(payload)
        return {"trade": trade}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/suggested-trades")
async def list_suggested_trades_endpoint(status: str = "open", grouped: bool = False):
    """Return hypothetical scanner trades tracked in local SQLite."""
    if not getattr(SUGGESTED_TRADES_REPOSITORY, "is_available", False):
        return _suggested_trades_unavailable_response()

    if status not in {"open", "closed", "all"}:
        raise HTTPException(400, "status must be one of: open, closed, all")

    try:
        query_status = None if status == "all" else status
        trades = SUGGESTED_TRADES_REPOSITORY.list_positions(query_status)
        if grouped:
            return _group_rows_by_status(trades)
        return {"trades": trades}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/suggested-trades/review")
async def review_suggested_trades_endpoint(body: dict[str, Any] = {}):
    """Review open suggested trades and refresh their hypothetical P/L."""
    if not getattr(SUGGESTED_TRADES_REPOSITORY, "is_available", False):
        return _suggested_trades_unavailable_response()

    try:
        raw_ids = body.get("position_ids") or []
        position_ids = [int(position_id) for position_id in raw_ids] if raw_ids else None
        reviewed = await _run_in_worker(review_open_positions, SUGGESTED_TRADES_REPOSITORY, position_ids=position_ids)
        return {"trades": reviewed}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/suggested-trades/{position_id}/close")
async def close_suggested_trade_endpoint(position_id: int, body: dict[str, Any]):
    """Mark a suggested trade closed using a hypothetical or observed exit price."""
    if not getattr(SUGGESTED_TRADES_REPOSITORY, "is_available", False):
        return _suggested_trades_unavailable_response()

    exit_price = body.get("exit_price")
    if exit_price is None:
        raise HTTPException(400, "exit_price is required")

    try:
        closed_at_raw = body.get("closed_at")
        closed_at = datetime.fromisoformat(closed_at_raw.replace("Z", "+00:00")) if closed_at_raw else datetime.now()
        trade = SUGGESTED_TRADES_REPOSITORY.close_position(
            position_id=position_id,
            exit_price=float(exit_price),
            closed_at=closed_at,
            exit_reason="manual_hypothetical_close",
            notes=body.get("notes"),
        )
        if trade is None:
            raise HTTPException(404, f"Suggested trade {position_id} was not found")
        return {"trade": trade}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/scan/recommendations")
async def get_recommendations(body: dict[str, Any] = {}):
    """Generate position recommendations for pending picks."""
    preds = _load_predictions()
    pending = [p for p in preds if not p.get("outcome") and p.get("type") == "daily_scan"]
    n_picks = int(body.get("n_picks", DEFAULT_SCAN_PICKS))
    supervised = _run_supervised_scan_request(body, n_picks=n_picks)
    if supervised.get("policy_fail_closed"):
        return supervised
    candidates = supervised["picks"] if supervised.get("policy_applied") else supervised["ranked_picks"]
    result = generate_position_recommendations(
        pending,
        n_picks=n_picks,
        candidates=candidates,
    )
    return {
        **result,
        "policy_applied": supervised["policy_applied"],
        "policy": supervised["policy"],
        "playbook": supervised["playbook"],
        "truth_lane": supervised["truth_lane"],
        "watch_picks": _normalize_scan_picks(supervised.get("watch_picks") or []),
        "managed_lane_status": supervised.get("managed_lane_status"),
        "truth_window_status": supervised.get("truth_window_status"),
        "authoritative_evidence_source": supervised.get("authoritative_evidence_source"),
        "authoritative_evidence_status": supervised.get("authoritative_evidence_status"),
        "watch_priority_symbols": supervised.get("watch_priority_symbols"),
        "watch_deprioritized_symbols": supervised.get("watch_deprioritized_symbols"),
    }


@app.post("/api/scan/roll")
async def roll_picks(body: dict[str, Any] = {}):
    """Roll forward daily picks."""
    preds = _load_predictions()
    pending = [p for p in preds if not p.get("outcome") and p.get("type") == "daily_scan"]
    n_picks = int(body.get("n_picks", DEFAULT_SCAN_PICKS))
    supervised = _run_supervised_scan_request(body, n_picks=n_picks)
    if supervised.get("policy_fail_closed"):
        return supervised
    candidates = supervised["picks"] if supervised.get("policy_applied") else supervised["ranked_picks"]
    result = roll_forward_daily_picks(
        pending,
        n_picks=n_picks,
        candidates=candidates,
    )
    return {
        **result,
        "policy_applied": supervised["policy_applied"],
        "policy": supervised["policy"],
        "playbook": supervised["playbook"],
        "truth_lane": supervised["truth_lane"],
        "watch_picks": _normalize_scan_picks(supervised.get("watch_picks") or []),
        "managed_lane_status": supervised.get("managed_lane_status"),
        "truth_window_status": supervised.get("truth_window_status"),
        "authoritative_evidence_source": supervised.get("authoritative_evidence_source"),
        "authoritative_evidence_status": supervised.get("authoritative_evidence_status"),
        "watch_priority_symbols": supervised.get("watch_priority_symbols"),
        "watch_deprioritized_symbols": supervised.get("watch_deprioritized_symbols"),
    }


# ── Sector sentiment ──────────────────────────────────────────────────────────


@app.get("/api/sectors")
async def get_sector_sentiments():
    """Fetch sector sentiments (11 sectors, 3 timeframes)."""
    import numpy as np

    SECTORS = [
        ("Technology", "XLK"), ("Healthcare", "XLV"), ("Financials", "XLF"),
        ("Energy", "XLE"), ("Consumer Discretionary", "XLY"), ("Consumer Staples", "XLP"),
        ("Industrials", "XLI"), ("Materials", "XLB"), ("Real Estate", "XLRE"),
        ("Utilities", "XLU"), ("Communication Services", "XLC"),
    ]

    def score_to_sentiment(score: float) -> str:
        if score >= 2.0: return "Very Bullish"
        if score >= 0.8: return "Bullish"
        if score > -0.8: return "Neutral"
        if score > -2.0: return "Bearish"
        return "Very Bearish"

    def sentiment_for_window(closes, window):
        if len(closes) < window + 5:
            return "Neutral", 0.0
        recent = float(closes.iloc[-1])
        start = float(closes.iloc[-window])
        ret_pct = (recent / start - 1) * 100
        sma = float(closes.iloc[-window:].mean())
        above_sma = recent > sma

        x = np.arange(min(window, len(closes)))
        y = closes.iloc[-min(window, len(closes)):].values.astype(float)
        slope = float(np.polyfit(x, y, 1)[0]) / (float(y.mean()) + 1e-9) * 100

        score = 0.0
        if ret_pct > 15: score += 2.0
        elif ret_pct > 5: score += 1.0
        elif ret_pct > -5: score += 0.0
        elif ret_pct > -15: score -= 1.0
        else: score -= 2.0

        score += 0.5 if above_sma else -0.5
        score += 0.5 if slope > 0.05 else (-0.5 if slope < -0.05 else 0.0)

        return score_to_sentiment(score), round(ret_pct, 1)

    tickers = [etf for _, etf in SECTORS]
    with _market_data_request_scope():
        hist = _md_download_history_batch(tickers, period="760d", auto_adjust=True)["Close"]

    rows = []
    for sector, etf in SECTORS:
        try:
            closes = hist[etf].dropna()
            if len(closes) < 30:
                raise ValueError("insufficient data")
            nt_sent, nt_ret = sentiment_for_window(closes, 21)
            mt_sent, mt_ret = sentiment_for_window(closes, 126)
            lt_sent, lt_ret = sentiment_for_window(closes, 252)
            rows.append({
                "sector": sector, "etf": etf,
                "near_sent": nt_sent, "near_ret": nt_ret,
                "med_sent": mt_sent, "med_ret": mt_ret,
                "long_sent": lt_sent, "long_ret": lt_ret,
            })
        except Exception:
            rows.append({
                "sector": sector, "etf": etf,
                "near_sent": "Neutral", "near_ret": 0.0,
                "med_sent": "Neutral", "med_ret": 0.0,
                "long_sent": "Neutral", "long_ret": 0.0,
            })
    return rows


@app.get("/api/market-data/cache-stats")
async def get_market_data_cache_stats():
    """Expose cache observability for the market data service."""
    return _md_get_cache_stats()


@app.post("/api/market-data/cache-stats/reset")
async def reset_market_data_cache_stats():
    """Reset in-memory cache observability counters."""
    return _md_reset_cache_stats()


# ── Backtest endpoint ─────────────────────────────────────────────────────────


@app.post("/api/backtest")
async def run_backtest_endpoint(body: dict[str, Any]):
    """Run historical backtest."""
    try:
        lookback_years = body.get("lookback_years", 5)
        iv_adj = body.get("iv_adj", 1.20)
        n_picks = body.get("n_picks", DEFAULT_SCAN_PICKS)
        pricing_lane = body.get("pricing_lane", "pessimistic")
        truth_lane = body.get("truth_lane")
        playbook = body.get("playbook")
        result = await _run_in_worker(
            run_historical_backtest,
            lookback_years=lookback_years,
            iv_adj=iv_adj,
            n_picks=n_picks,
            pricing_lane=pricing_lane,
            truth_lane=str(truth_lane) if truth_lane else None,
            playbook=playbook,
        )
        return result
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/backtest/archived-forward")
async def run_archived_forward_backtest_endpoint(body: dict[str, Any] = {}):
    """Run archived-forward exact-contract imported-daily replay over /api/scan picks."""
    try:
        result = await _run_in_worker(
            run_archived_forward_daily_backtest,
            source_label=str(body.get("source_label") or ARCHIVED_FORWARD_SOURCE_LABEL),
        )
        return result
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/backtest/last")
async def get_last_backtest(truth_lane: str | None = None):
    """Return last saved backtest results."""
    result = await _run_in_worker(_cached_last_results_by_truth_lane, truth_lane)
    if not result:
        return {"error": "No backtest results found"}
    return result


@app.get("/api/backtest/forward-evidence")
async def get_forward_evidence_report():
    """Return evidence-health for archived /api/scan exact-contract validation."""
    try:
        return await _run_in_worker(_cached_forward_evidence_report)
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/backtest/report")
async def get_backtest_report(min_trades: int = 20, truth_lane: str | None = None):
    """Return a grouped replay report from the most recent backtest."""
    result = await _run_in_worker(_cached_backtest_report, truth_lane, min_trades)
    if result.get("error"):
        return result
    return result


@app.get("/api/backtest/metric-truth")
async def get_metric_truth_report(min_trades: int = 20, bucket_size: int = 10, truth_lane: str | None = None):
    """Return a calibration and profitability truth report from the most recent backtest."""
    return await _run_in_worker(_cached_metric_truth_report, truth_lane, min_trades, bucket_size)


@app.post("/api/backtest/experiments")
async def get_backtest_experiments(body: dict[str, Any] = {}):
    """Return a ranked options-only experiment matrix from the most recent backtest."""
    result = await _run_in_worker(_cached_backtest_experiments, body)
    if result.get("error"):
        return result
    return result


@app.get("/api/backtest/profitability-forensics")
async def get_backtest_profitability_forensics(min_trades: int = 20, truth_lane: str | None = None):
    """Return slice-based profitability forensics from the most recent backtest."""
    result = await _run_in_worker(_cached_backtest_profitability_forensics, min_trades, truth_lane)
    if result.get("error"):
        return result
    return result


@app.get("/api/backtest/stability")
async def get_backtest_stability(
    min_trades: int = 20,
    min_profit_factor: float = 1.05,
    truth_lane: str | None = None,
):
    """Return fixed-window and rolling-window stability results for the latest backtest."""
    result = await _run_in_worker(_cached_backtest_stability, min_trades, min_profit_factor, truth_lane)
    if result.get("error"):
        return result
    return result


@app.get("/api/backtest/live-policy")
async def get_live_trade_policy(
    min_trades: int = 20,
    max_tickers: int = 8,
    max_sectors: int = 8,
    min_profit_factor: float = 1.05,
    min_directional_accuracy_pct: float = 50.0,
    truth_lane: str | None = None,
):
    """Return a replay-backed live trade policy for the supervised options scanner."""
    result = await _run_in_worker(
        _cached_live_trade_policy_report,
        min_trades,
        max_tickers,
        max_sectors,
        min_profit_factor,
        min_directional_accuracy_pct,
        truth_lane,
    )
    if result.get("error"):
        return result
    return result


@app.get("/api/backtest/exit-audit")
async def get_playbook_exit_audit(
    playbook: str = "short_term",
    min_trades: int = 20,
    max_tickers: int = 8,
    max_sectors: int = 8,
    min_profit_factor: float = 1.05,
    min_directional_accuracy_pct: float = 50.0,
    truth_lane: str | None = None,
):
    """Return a replay exit audit for the approved/watch/blocked cohorts in a playbook window."""
    result = await _run_in_worker(
        _cached_playbook_exit_audit_report,
        playbook,
        min_trades,
        max_tickers,
        max_sectors,
        min_profit_factor,
        min_directional_accuracy_pct,
        truth_lane,
    )
    if result.get("error"):
        return result
    return result


@app.get("/api/backtest/comparison")
async def get_backtest_truth_lane_comparison(truth_lane: str | None = None):
    """Compare the latest synthetic and imported validation lanes side by side."""
    result = await _run_in_worker(_cached_truth_lane_comparison_report, truth_lane)
    if result.get("error"):
        return result
    return result


@app.get("/api/backtest/summary")
async def get_backtest_summary(
    min_trades: int = 20,
    bucket_size: int = 10,
    truth_lane: str | None = None,
):
    """Return the current optimizer artifact bundle in one cached response."""
    try:
        return await _run_in_worker(_build_backtest_summary, truth_lane, min_trades, bucket_size)
    except Exception as exc:
        raise HTTPException(500, str(exc))


# ── Changelog endpoint ────────────────────────────────────────────────────────


@app.get("/api/changelog")
async def get_changelog(profile: str = "equity"):
    """Return brain changelog for a profile."""
    cfile = CHANGELOG_FILES.get(profile)
    if not cfile or not os.path.exists(cfile):
        return []
    try:
        with open(cfile) as f:
            return json.load(f)
    except Exception:
        return []


# ── Daily performance endpoint ────────────────────────────────────────────────


@app.get("/api/daily-performance")
async def get_daily_performance():
    """Return daily performance snapshots."""
    perf_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "daily_performance.json",
    )
    if not os.path.exists(perf_file):
        return []
    try:
        with open(perf_file) as f:
            return json.load(f)
    except Exception:
        return []


# ── Risk settings shortcut ────────────────────────────────────────────────────


@app.get("/api/risk")
async def get_risk_settings():
    """Return current risk settings for sidebar display."""
    return {
        "equity": STRATEGY_PROFILES["equity"]["risk"],
        "index": STRATEGY_PROFILES["index"]["risk"],
    }


# ── Health check ───────────────────────────────────��──────────────────────────


@app.get("/api/health")
async def health():
    return {"status": "ok", "tools": list(TOOL_DISPATCH.keys())}


@app.get("/api/options-profit/status")
async def get_options_profit_status():
    """Return the read-only bounded options profit-cycle status artifact."""
    try:
        return await _run_in_worker(_read_only_options_profit_status)
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/proof-summary")
async def get_proof_summary():
    """Return the canonical proof-lane summary: loop-health and claim-readiness verdicts."""
    try:
        def _build_proof_summary() -> dict[str, Any]:
            loop_health = evaluate_measurement_gate()
            claim_readiness = evaluate_claim_readiness()

            # Count positions
            positions_available = False
            open_count = 0
            closed_count = 0
            exact_contract_closed = 0
            if getattr(POSITIONS_REPOSITORY, "is_available", False):
                positions_available = True
                try:
                    open_positions = POSITIONS_REPOSITORY.list_positions("open")
                    closed_positions = POSITIONS_REPOSITORY.list_positions("closed")
                    open_count = len(open_positions)
                    closed_count = len(closed_positions)
                    exact_contract_closed = sum(
                        1 for p in closed_positions
                        if str(p.get("contract_symbol") or "").strip()
                    )
                except Exception:
                    pass

            # Forward evidence counts
            forward_evidence = _cached_forward_evidence_report()
            forward_events = list(forward_evidence.get("authoritative_events") or [])
            scan_pick_events = [e for e in forward_events if str(e.get("event_type") or "") == "scan_pick"]
            position_opened_events = [e for e in forward_events if str(e.get("event_type") or "") == "position_opened"]
            review_events = [e for e in forward_events if str(e.get("event_type") or "") == "position_review"]

            return {
                "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "loop_health": {
                    "state": loop_health["state"],
                    "blocker_count": len(loop_health["blockers"]),
                    "blockers": loop_health["blockers"],
                },
                "claim_readiness": {
                    "state": claim_readiness["state"],
                    "claim_ready": claim_readiness["claim_ready"],
                    "blocker_count": claim_readiness["blocker_count"],
                    "blockers": claim_readiness["blockers"],
                },
                "evidence_counts": {
                    "forward_event_count": len(forward_events),
                    "scan_pick_event_count": len(scan_pick_events),
                    "position_opened_event_count": len(position_opened_events),
                    "review_event_count": len(review_events),
                    "eligible_event_count": claim_readiness.get("eligible_event_count", 0),
                    "pending_truth_event_count": claim_readiness.get("pending_truth_event_count", 0),
                    "by_symbol": claim_readiness.get("by_symbol", {}),
                },
                "tracked_positions": {
                    "available": positions_available,
                    "open_count": open_count,
                    "closed_count": closed_count,
                    "exact_contract_closed_count": exact_contract_closed,
                },
                "realized_metrics": claim_readiness.get("tracked_realized_metrics", {}),
            }

        return await _run_in_worker(_build_proof_summary)
    except Exception as exc:
        raise HTTPException(500, str(exc))
