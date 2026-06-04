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
import secrets
import threading
import time
from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
from proof_contract import (
    row_counts_as_production_proof as _row_counts_as_production_proof,
    row_counts_as_proof_grade_exact_closed as _row_counts_as_proof_grade_exact_closed,
    row_has_raw_exact_contract as _row_has_raw_exact_contract,
    row_has_research_backfill_marker as _row_has_research_backfill_marker,
)
from backend_route_context import BackendRouteContext
from predictions_routes import create_predictions_router
from profile_routes import create_profile_router
import replay_profit_service
from tools_routes import create_tools_router
from suggested_trades_repository import create_suggested_trades_repository
from supervised_scan import (
    LIVE_SCAN_TRUTH_LANE,
    SCAN_PLAYBOOK_FALLBACK_ID,
    apply_playbook_guardrails,
    get_scan_playbook,
    run_supervised_scan,
    scan_pick_market_regime,
)
from options_profit_gate import (
    DEFAULT_MIN_CLOSED_TRACKED_POSITIONS,
    DEFAULT_MIN_REALIZED_AVG_NET_PNL_PCT,
    DEFAULT_MIN_REALIZED_PROFIT_FACTOR,
    _realized_position_metrics,
    evaluate_claim_readiness,
    evaluate_measurement_gate,
)
from options_profit_state import build_read_only_profit_status_view, live_profile_entry_for_symbol
from proof_summary_service import build_proof_summary
from trading_desk_api_models import (
    parse_close_trading_desk_record_body,
    parse_create_trading_desk_record_body,
    parse_review_trading_desk_records_body,
)

app = FastAPI(title="Options Chatbot Backend")

BACKEND_API_TOKEN_HEADER = "x-options-backend-token"


def _backend_api_token() -> str:
    return str(os.getenv("OPTIONS_BACKEND_API_TOKEN") or "").strip()


def _backend_api_token_required(path: str) -> bool:
    return bool(_backend_api_token()) and str(path or "").startswith("/api/")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_backend_timing_header(request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000.0
    response.headers["x-python-backend-duration-ms"] = f"{duration_ms:.1f}"
    return response


@app.middleware("http")
async def require_backend_api_token(request, call_next):
    expected_token = _backend_api_token()
    if expected_token and _backend_api_token_required(request.url.path):
        actual_token = str(request.headers.get(BACKEND_API_TOKEN_HEADER) or "").strip()
        if not secrets.compare_digest(actual_token, expected_token):
            return JSONResponse(
                {"detail": "Backend API token is required."},
                status_code=401,
            )
    return await call_next(request)


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
_SHARE_SAFE_REVIEW_MAX_AGE = timedelta(minutes=15)
_ROUTE_CONTEXT = BackendRouteContext(globals())

app.include_router(
    create_profile_router(
        strategy_profiles=STRATEGY_PROFILES,
        save_profile=_save_profile,
        changelog_files=CHANGELOG_FILES,
    )
)
app.include_router(create_tools_router(_ROUTE_CONTEXT))
app.include_router(create_predictions_router(_ROUTE_CONTEXT))


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
    status_view = build_read_only_profit_status_view(
        status_payload=status_payload,
        incumbents_payload=incumbents_payload,
        live_profile_payload=live_profile,
        decision_payload=decision_payload,
    )
    return _with_current_tracked_positions_health(status_view)


def _runtime_database_url_configured(repository: Any) -> bool:
    env_url = str(os.getenv("DATABASE_URL") or "").strip()
    repository_url = str(getattr(repository, "database_url", "") or "").strip()
    return bool(env_url or repository_url)


def _safe_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _current_tracked_positions_health_check(base_check: dict[str, Any] | None = None) -> dict[str, Any]:
    check = copy.deepcopy(dict(base_check or {}))
    check["runtime_source"] = "positions_repository"
    check["runtime_checked_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    check["database_url_configured"] = _runtime_database_url_configured(POSITIONS_REPOSITORY)
    required_closed = check.get("required_closed_position_count")
    try:
        required_closed_int = int(required_closed)
    except (TypeError, ValueError):
        required_closed_int = DEFAULT_MIN_CLOSED_TRACKED_POSITIONS
    required_profit_factor = _safe_float(check.get("required_net_profit_factor"))
    if required_profit_factor is None:
        required_profit_factor = DEFAULT_MIN_REALIZED_PROFIT_FACTOR
    required_avg_net_pnl = _safe_float(check.get("required_avg_net_pnl_pct_gt"))
    if required_avg_net_pnl is None:
        required_avg_net_pnl = DEFAULT_MIN_REALIZED_AVG_NET_PNL_PCT

    if not bool(getattr(POSITIONS_REPOSITORY, "is_available", False)):
        check.update(
            {
                "available": False,
                "error_message": getattr(POSITIONS_REPOSITORY, "error_message", None)
                or "Tracked positions storage is unavailable.",
                "open_position_count": 0,
                "total_closed_position_count": 0,
                "closed_position_count": 0,
                "required_closed_position_count": required_closed_int,
                "tracking_required": required_closed_int > 0,
                "realized_profitability_ready": None if required_closed_int <= 0 else False,
            }
        )
        return check

    try:
        profit_status_snapshot = getattr(POSITIONS_REPOSITORY, "profit_status_snapshot", None)
        if callable(profit_status_snapshot):
            snapshot = profit_status_snapshot()
            open_position_count = int(snapshot.get("open_position_count") or 0)
            closed_positions = list(snapshot.get("closed_positions") or [])
            total_closed_position_count = int(
                snapshot.get("total_closed_position_count")
                if snapshot.get("total_closed_position_count") is not None
                else len(closed_positions)
            )
            snapshot_source = "positions_repository_profit_status_snapshot"
        else:
            open_positions = POSITIONS_REPOSITORY.list_positions("open")
            closed_positions = POSITIONS_REPOSITORY.list_positions("closed")
            open_position_count = len(open_positions)
            total_closed_position_count = len(closed_positions)
            snapshot_source = "positions_repository"
    except Exception as exc:
        check.update(
            {
                "available": False,
                "error_message": str(exc),
                "open_position_count": 0,
                "total_closed_position_count": 0,
                "closed_position_count": 0,
                "required_closed_position_count": required_closed_int,
                "tracking_required": required_closed_int > 0,
                "realized_profitability_ready": None if required_closed_int <= 0 else False,
            }
        )
        return check

    realized_metrics = _realized_position_metrics(list(closed_positions))
    closed_position_count = int(realized_metrics.get("closed_position_count") or 0)
    realized_profit_factor = _safe_float(realized_metrics.get("net_profit_factor"))
    realized_avg_net_pnl_pct = _safe_float(realized_metrics.get("avg_net_pnl_pct"))
    realized_profitability_ready = (
        realized_profit_factor is not None
        and realized_profit_factor >= float(required_profit_factor)
        and realized_avg_net_pnl_pct is not None
        and realized_avg_net_pnl_pct > float(required_avg_net_pnl)
    )
    check.update(
        {
            "available": True,
            "error_message": None,
            "open_position_count": open_position_count,
            "total_closed_position_count": total_closed_position_count,
            "closed_position_count": closed_position_count,
            "required_closed_position_count": required_closed_int,
            "tracking_required": required_closed_int > 0,
            "runtime_snapshot_source": snapshot_source,
            "exact_contract_closed_count": realized_metrics.get("exact_contract_closed_count"),
            "non_proof_closed_position_count": realized_metrics.get("non_proof_closed_position_count"),
            "net_profit_factor": realized_profit_factor,
            "required_net_profit_factor": float(required_profit_factor),
            "avg_net_pnl_pct": realized_avg_net_pnl_pct,
            "required_avg_net_pnl_pct_gt": float(required_avg_net_pnl),
            "realized_profitability_ready": (
                realized_profitability_ready if required_closed_int > 0 else None
            ),
        }
    )
    return check


def _with_current_tracked_positions_health(status_view: dict[str, Any]) -> dict[str, Any]:
    current = copy.deepcopy(dict(status_view or {}))
    measurement_gate = copy.deepcopy(dict(current.get("measurement_gate") or {}))
    checks = copy.deepcopy(dict(measurement_gate.get("checks") or {}))
    base_tracked_check = checks.get("tracked_positions")
    checks["tracked_positions"] = _current_tracked_positions_health_check(
        base_tracked_check if isinstance(base_tracked_check, dict) else None
    )
    measurement_gate["checks"] = checks
    current["measurement_gate"] = measurement_gate
    return current


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


# ── Profile endpoints ────────────────────────────────────────────────────────


# ── Predictions endpoints ────────────────────────────────────────────────────


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
    normalized["short_strike"] = pick.get("short_strike")
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
    normalized["portfolio_caps_enforced"] = bool(pick.get("portfolio_caps_enforced")) if pick.get("portfolio_caps_enforced") is not None else None
    normalized["creation_eligible"] = bool(pick.get("creation_eligible")) if pick.get("creation_eligible") is not None else None
    normalized["creation_blockers"] = list(pick.get("creation_blockers") or []) if isinstance(pick.get("creation_blockers"), list) else []
    normalized["position_tracking_mode"] = pick.get("position_tracking_mode")
    normalized["suggested_size_tier"] = pick.get("suggested_size_tier")
    normalized["suggested_size_reason"] = pick.get("suggested_size_reason")
    normalized["risk_tier"] = pick.get("risk_tier")
    normalized["upside_tier"] = pick.get("upside_tier")
    normalized["speculative_flag"] = bool(pick.get("speculative_flag"))
    normalized["speculative_reason"] = pick.get("speculative_reason")
    normalized["convexity_class"] = pick.get("convexity_class")
    normalized["historical_data_ready"] = pick.get("historical_data_ready")
    normalized["historical_data_source"] = pick.get("historical_data_source")
    normalized["historical_data_readiness_status"] = pick.get("historical_data_readiness_status")
    normalized["ai_commodity_bucket"] = pick.get("ai_commodity_bucket")
    normalized["quote_time_et"] = pick.get("quote_time_et")
    normalized["quote_time_utc"] = pick.get("quote_time_utc")
    normalized["quote_basis"] = pick.get("quote_basis")
    normalized["market_data_provider"] = pick.get("market_data_provider")
    normalized["market_data_source"] = pick.get("market_data_source")
    normalized["underlying_data_source"] = pick.get("underlying_data_source")
    normalized["options_data_source"] = pick.get("options_data_source")
    normalized["quote_source"] = pick.get("quote_source")
    normalized["quote_freshness_status"] = pick.get("quote_freshness_status")
    normalized["original_logged_expiry"] = pick.get("original_logged_expiry")
    normalized["resolved_listed_expiry"] = pick.get("resolved_listed_expiry")
    entry_quote_snapshot = pick.get("entry_quote_snapshot")
    if isinstance(entry_quote_snapshot, dict):
        entry_quote_snapshot = dict(entry_quote_snapshot)
        if normalized.get("quote_time_et"):
            entry_quote_snapshot["captured_at_et"] = normalized.get("quote_time_et")
        if normalized.get("quote_time_utc"):
            entry_quote_snapshot["captured_at_utc"] = normalized.get("quote_time_utc")
    normalized["entry_quote_snapshot"] = entry_quote_snapshot
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
    normalized["mid"] = pick.get("mid") if pick.get("mid") is not None else normalized.get("mid")
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


def _scan_pick_event_key(pick: dict[str, Any], candidate_rank: int) -> str:
    event_key = f"rank_{int(candidate_rank)}"
    cohort_id = str(pick.get("cohort_id") or "").strip()
    return f"{cohort_id}:{event_key}" if cohort_id else event_key


def _annotate_scan_picks_with_forward_provenance(
    picks: list[dict[str, Any]],
    *,
    forward_truth_meta: dict[str, Any],
) -> list[dict[str, Any]]:
    if not bool(forward_truth_meta.get("forward_truth_recorded")):
        return picks
    session_id = forward_truth_meta.get("forward_truth_session_id")
    run_id = str(forward_truth_meta.get("forward_truth_run_id") or "").strip()
    recorded_at_utc = str(forward_truth_meta.get("forward_truth_recorded_at_utc") or "").strip()
    if session_id is None or not run_id or not recorded_at_utc:
        return picks

    annotated: list[dict[str, Any]] = []
    for idx, pick in enumerate(list(picks or []), start=1):
        next_pick = dict(pick)
        next_pick["source_scan_session_id"] = int(session_id)
        next_pick["source_scan_event_key"] = _scan_pick_event_key(next_pick, idx)
        next_pick["source_scan_run_id"] = run_id
        next_pick["source_scan_recorded_at_utc"] = recorded_at_utc
        annotated.append(next_pick)
    return annotated


def _normalize_lineage_text(value: Any) -> str:
    return str(value or "").strip()


def _same_lineage_text(left: Any, right: Any) -> bool:
    left_text = _normalize_lineage_text(left)
    right_text = _normalize_lineage_text(right)
    return bool(left_text) and left_text == right_text


def _same_lineage_int(left: Any, right: Any) -> bool:
    try:
        return int(left) == int(right)
    except (TypeError, ValueError):
        return False


def _same_lineage_float(left: Any, right: Any, *, tolerance: float = 0.0001) -> bool:
    try:
        left_value = float(left)
        right_value = float(right)
    except (TypeError, ValueError):
        return False
    return math.isfinite(left_value) and math.isfinite(right_value) and abs(left_value - right_value) <= tolerance


def _same_optional_lineage_text(scan_pick: dict[str, Any], event: dict[str, Any], *fields: str) -> bool:
    for field in fields:
        scan_value = scan_pick.get(field)
        event_value = event.get(field)
        if scan_value or event_value:
            if not _same_lineage_text(scan_value, event_value):
                return False
    return True


def _same_optional_lineage_float(scan_pick: dict[str, Any], event: dict[str, Any], *fields: str) -> bool:
    for field in fields:
        scan_value = scan_pick.get(field)
        event_value = event.get(field)
        if scan_value is not None or event_value is not None:
            if not _same_lineage_float(scan_value, event_value):
                return False
    return True


def _scan_pick_matches_forward_event(scan_pick: dict[str, Any], event: dict[str, Any]) -> bool:
    if not _same_lineage_text(scan_pick.get("ticker"), event.get("ticker")):
        return False

    scan_direction = scan_pick.get("direction") or scan_pick.get("type") or scan_pick.get("option_type")
    event_direction = event.get("direction") or event.get("type") or event.get("option_type")
    if not _same_lineage_text(scan_direction, event_direction):
        return False

    scan_contract = scan_pick.get("contract_symbol") or scan_pick.get("contractSymbol")
    event_contract = event.get("contract_symbol") or event.get("contractSymbol")
    if scan_contract or event_contract:
        if not _same_lineage_text(scan_contract, event_contract):
            return False

    scan_short_contract = scan_pick.get("short_contract_symbol") or scan_pick.get("shortContractSymbol")
    event_short_contract = event.get("short_contract_symbol") or event.get("shortContractSymbol")
    if scan_short_contract or event_short_contract:
        if not _same_lineage_text(scan_short_contract, event_short_contract):
            return False

    scan_expiry = str(scan_pick.get("expiry") or "")[:10]
    event_expiry = str(event.get("expiry") or "")[:10]
    if scan_expiry or event_expiry:
        if scan_expiry != event_expiry:
            return False

    if not _same_optional_lineage_text(
        scan_pick,
        event,
        "strategy_type",
        "entry_execution_basis",
        "quote_time_et",
        "selection_source",
        "contract_selection_source",
        "promotion_class",
        "candidate_execution_label",
        "options_data_source",
        "market_data_source",
        "quote_source",
        "quote_basis",
        "playbook_id",
        "cohort_id",
        "guardrail_decision",
        "portfolio_caps_enforced",
        "creation_eligible",
        "creation_blockers",
    ):
        return False
    if not _same_optional_lineage_float(
        scan_pick,
        event,
        "strike",
        "short_strike",
        "entry_execution_price",
    ):
        return False

    return True


def _verify_source_scan_lineage(scan_pick: dict[str, Any]) -> bool:
    if not isinstance(scan_pick, dict):
        return False
    session_id = scan_pick.get("source_scan_session_id")
    event_key = _normalize_lineage_text(scan_pick.get("source_scan_event_key"))
    run_id = _normalize_lineage_text(scan_pick.get("source_scan_run_id"))
    recorded_at_utc = _normalize_lineage_text(scan_pick.get("source_scan_recorded_at_utc"))
    if session_id in (None, "") or not event_key or not run_id or not recorded_at_utc:
        return False

    try:
        events = list_forward_scan_pick_events(
            source_label=ARCHIVED_FORWARD_SOURCE_LABEL,
            tickers=[str(scan_pick.get("ticker") or "").upper()],
            db_path=authoritative_forward_ledger_db_path(),
        )
    except Exception:
        return False

    for event in events:
        if not _same_lineage_int(event.get("session_id"), session_id):
            continue
        if not _same_lineage_text(event.get("event_key"), event_key):
            continue
        if not _same_lineage_text(event.get("run_id"), run_id):
            continue
        if not _same_lineage_text(event.get("recorded_at_utc"), recorded_at_utc):
            continue
        if _scan_pick_matches_forward_event(scan_pick, event):
            return True
    return False


def _normalize_scan_pick_payload_fields(payload: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    normalized = dict(payload)
    for field in fields:
        value = normalized.get(field)
        if isinstance(value, list):
            normalized_items: list[Any] = []
            rank = 1
            for item in value:
                if not isinstance(item, dict):
                    normalized_items.append(item)
                    continue
                normalized_pick = _normalize_scan_pick(item)
                normalized_pick["candidate_rank"] = int(normalized_pick.get("candidate_rank") or rank)
                normalized_items.append(normalized_pick)
                rank += 1
            normalized[field] = normalized_items
    return normalized


def _normalize_recommendation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_scan_pick_payload_fields(payload, ("new_opportunities",))
    active_positions = []
    for item in list(normalized.get("active_positions") or []):
        if not isinstance(item, dict):
            active_positions.append(item)
            continue
        active = dict(item)
        replacement = active.get("replace_with")
        if isinstance(replacement, dict):
            active["replace_with"] = _normalize_scan_pick(replacement)
        active_positions.append(active)
    normalized["active_positions"] = active_positions
    return normalized


def _normalize_roll_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return _normalize_scan_pick_payload_fields(payload, ("rolled", "new", "dropped"))


def _position_contract_signature(record: dict[str, Any]) -> tuple[Any, ...]:
    source = _safe_dict_payload(record.get("source_pick_snapshot"))

    def _norm_float(value: Any) -> float | None:
        try:
            return round(float(value), 4)
        except (TypeError, ValueError):
            return None

    strike = record.get("strike")
    if strike is None:
        strike = source.get("strike")
    if strike is None:
        strike = source.get("strike_est")

    expiry = record.get("expiry")
    if expiry is None:
        expiry = source.get("expiry")

    direction = record.get("direction")
    if direction is None:
        direction = source.get("direction") or source.get("type")

    contract_symbol = record.get("contract_symbol")
    if contract_symbol is None:
        contract_symbol = source.get("contract_symbol") or source.get("contractSymbol")

    return (
        str(record.get("ticker") or source.get("ticker") or "").strip().upper() or None,
        str(direction or "").strip().lower() or None,
        str(expiry or "").strip()[:10] or None,
        str(source.get("strategy_type") or "single_leg").strip().lower() or None,
        _norm_float(strike),
        _norm_float(source.get("short_strike")),
        str(contract_symbol or "").strip().upper() or None,
        str(source.get("short_contract_symbol") or "").strip().upper() or None,
    )


def _find_existing_open_contract(repository: Any, payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        open_positions = list(repository.list_positions("open") or [])
    except Exception:
        return None
    target_signature = _position_contract_signature(payload)
    for position in open_positions:
        if _position_contract_signature(dict(position)) == target_signature:
            return dict(position)
    return None


def _safe_dict_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        if isinstance(parsed, str):
            try:
                parsed = json.loads(parsed)
            except Exception:
                return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _scan_pick_has_scanner_markers(scan_pick: dict[str, Any]) -> bool:
    if not isinstance(scan_pick, dict):
        return False
    marker_fields = (
        "source_scan_session_id",
        "source_scan_event_key",
        "source_scan_run_id",
        "source_scan_recorded_at_utc",
        "guardrail_decision",
        "portfolio_caps_enforced",
        "creation_eligible",
        "candidate_execution_label",
        "execution_candidate_label",
    )
    return any(scan_pick.get(field) not in (None, "") for field in marker_fields)


def _creation_mode(body: dict[str, Any], scan_pick: dict[str, Any]) -> str:
    raw = str(body.get("creation_mode") or "").strip().lower()
    if not raw:
        return "scanner" if _scan_pick_has_scanner_markers(scan_pick) else "manual_paper"
    if raw not in {"scanner", "manual_paper", "manual_broker"}:
        raise HTTPException(400, "creation_mode must be scanner, manual_paper, or manual_broker.")
    return raw


def _pick_playbook_id(scan_pick: dict[str, Any]) -> str:
    return str(
        scan_pick.get("playbook_id")
        or scan_pick.get("playbook")
        or SCAN_PLAYBOOK_FALLBACK_ID
    ).strip().lower()


def _blocked_create(detail: str, *, reasons: list[str] | None = None) -> None:
    payload: dict[str, Any] = {"message": detail}
    if reasons:
        payload["reasons"] = reasons
    raise HTTPException(409, payload)


def _creation_blockers_from_pick(scan_pick: dict[str, Any]) -> list[str]:
    return list(
        dict.fromkeys(
            str(item).strip()
            for item in list(scan_pick.get("creation_blockers") or [])
            if str(item).strip()
        )
    )


def _require_scanner_creation_flags(scan_pick: dict[str, Any], *, stage: str) -> None:
    reason_prefix = "source" if stage == "source" else "current"
    if scan_pick.get("portfolio_caps_enforced") is not True:
        _blocked_create(
            "Scanner-origin position creation requires a caps-enforced scan.",
            reasons=[f"{reason_prefix}_portfolio_caps_not_enforced"],
        )
    creation_blockers = _creation_blockers_from_pick(scan_pick)
    if creation_blockers:
        _blocked_create(
            "Scanner-origin position creation is not eligible from the current scan."
            if stage == "current"
            else "Scanner-origin position creation is not eligible from the source scan.",
            reasons=creation_blockers,
        )
    if scan_pick.get("creation_eligible") is not True:
        _blocked_create(
            "Scanner-origin position creation requires current scan creation_eligible=true."
            if stage == "current"
            else "Scanner-origin position creation requires source scan creation_eligible=true.",
            reasons=[f"{reason_prefix}_creation_eligible_not_true"],
        )


def _validate_scanner_origin_create(
    scan_pick: dict[str, Any],
    *,
    positions_repository: Any,
) -> tuple[dict[str, Any], bool]:
    lineage_verified = _verify_source_scan_lineage(scan_pick)
    if not lineage_verified:
        _blocked_create(
            "Scanner-origin position creation requires verified archived forward scan lineage.",
            reasons=["source_scan_lineage_unverified"],
        )
    original_guardrail = str(scan_pick.get("guardrail_decision") or "clear").strip().lower()
    if original_guardrail == "blocked":
        _blocked_create(
            "Scanner-origin position creation is blocked by the source scan guardrails.",
            reasons=list(scan_pick.get("guardrail_reasons") or ["guardrail_blocked"]),
        )
    _require_scanner_creation_flags(scan_pick, stage="source")

    playbook = get_scan_playbook(_pick_playbook_id(scan_pick))
    guardrail_result = apply_playbook_guardrails(
        [scan_pick],
        playbook=playbook,
        positions_repository=positions_repository,
        include_blocked=True,
        enforce_portfolio_caps=True,
    )
    rerun_picks = list(guardrail_result.get("ranked_picks") or guardrail_result.get("all_ranked_picks") or [])
    rerun_pick = dict(rerun_picks[0]) if rerun_picks else dict(scan_pick)
    if str(rerun_pick.get("guardrail_decision") or "clear").strip().lower() == "blocked":
        _blocked_create(
            "Current portfolio guardrails block this scanner-origin position.",
            reasons=list(rerun_pick.get("guardrail_reasons") or ["guardrail_blocked"]),
        )
    _require_scanner_creation_flags(rerun_pick, stage="current")
    return rerun_pick, lineage_verified


def _parse_iso_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _annotate_share_safety(row: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(row)
    source_pick = _safe_dict_payload(payload.get("source_pick_snapshot"))
    latest_review = _safe_dict_payload(payload.get("latest_review"))
    contract_symbol = (
        payload.get("contract_symbol")
        or source_pick.get("contract_symbol")
        or source_pick.get("contractSymbol")
    )
    pricing_source = str(latest_review.get("pricing_source") or "").strip().lower() or None
    current_option_price = latest_review.get("current_option_price")
    reviewed_at = latest_review.get("reviewed_at") or payload.get("last_reviewed_at")
    reviewed_dt = _parse_iso_datetime(reviewed_at)
    review_age_minutes = None
    if reviewed_dt is not None:
        review_age_minutes = max(int((datetime.now(UTC) - reviewed_dt).total_seconds() // 60), 0)

    share_safe = False
    share_safe_reason = "Exact live review pending."
    if source_pick.get("approximation_only"):
        share_safe_reason = "Estimated from proxy contract pricing."
    elif not str(contract_symbol or "").strip():
        share_safe_reason = "Missing exact contract symbol."
    elif not latest_review:
        share_safe_reason = "Live review pending."
    elif current_option_price is None:
        share_safe_reason = "No live market option price is saved yet."
    elif pricing_source not in {"mid", "last_price", "spread_mid_exact", "spread_bid_ask_exact"}:
        if pricing_source == "spread_mid_approx":
            share_safe_reason = "Estimated from proxy contract pricing."
        elif pricing_source == "expired":
            share_safe_reason = "Contract is expired."
        else:
            share_safe_reason = "Pricing is not from an exact live option quote."
    elif reviewed_dt is None:
        share_safe_reason = "Missing live review timestamp."
    elif datetime.now(UTC) - reviewed_dt > _SHARE_SAFE_REVIEW_MAX_AGE:
        share_safe_reason = "Live review is stale for share-safe reporting."
    else:
        share_safe = True
        share_safe_reason = (
            "Comparable exact contract live-priced and freshly reviewed."
            if source_pick.get("comparable_contract")
            else "Exact contract live-priced and freshly reviewed."
        )

    payload["share_safe_exact_live"] = share_safe
    payload["share_safe_reason"] = share_safe_reason
    payload["share_review_age_minutes"] = review_age_minutes
    payload["share_reviewed_at"] = reviewed_at
    payload["exact_contract_symbol"] = str(contract_symbol or "").strip().upper() or None
    return payload


def _annotate_share_safety_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_annotate_share_safety(dict(row)) for row in list(rows or [])]


_SOURCE_PICK_LIST_KEYS = {
    "ai_commodity_bucket",
    "approximation_only",
    "cohort_id",
    "comparable_contract",
    "contract_symbol",
    "date",
    "direction",
    "entry_execution_basis",
    "entry_execution_price",
    "expiry",
    "original_logged_expiry",
    "playbook",
    "playbook_id",
    "playbook_label",
    "promotion_class",
    "quote_basis",
    "quote_freshness_status",
    "quote_time_et",
    "quote_time_utc",
    "research_only",
    "resolved_listed_expiry",
    "scan_date",
    "selection_source",
    "short_contract_symbol",
    "short_strike",
    "signal_date",
    "strategy_comment",
    "strategy_label",
    "strategy_type",
    "strike",
    "strike_est",
    "ticker",
    "trade_date",
}
_CLOSED_SOURCE_PICK_LIST_KEYS = {
    "ai_commodity_bucket",
    "cohort_id",
    "date",
    "debit_pct_of_width",
    "direction",
    "fill_degradation_vs_mid_pct",
    "net_debit",
    "playbook",
    "playbook_id",
    "playbook_label",
    "ret5",
    "scan_date",
    "signal_date",
    "spread_width",
    "strategy_comment",
    "strategy_label",
    "trade_date",
    "quote_time_et",
    "quote_time_utc",
    "worst_leg_bid_ask_spread_pct",
    "worst_leg_spread_pct",
}
_CLOSED_SOURCE_LIQUIDITY_DERIVED_KEYS = {
    "fill_degradation_vs_mid_pct",
    "worst_leg_bid_ask_spread_pct",
}
_ENTRY_QUOTE_LIST_KEYS = {
    "captured_at_et",
    "captured_at_utc",
    "resolved_listed_expiry",
}
_LATEST_REVIEW_LIST_KEYS = {
    "current_option_price",
    "current_pnl_pct",
    "exit_execution_basis",
    "exit_execution_price",
    "fee_total_usd",
    "gross_pnl_pct",
    "net_pnl_pct",
    "pricing_source",
    "recommendation",
    "reviewed_at",
    "warnings",
}
_COMPACT_LIST_NOTES_MAX_CHARS = 240
_COMPACT_CLOSED_LIST_NOTES_MAX_CHARS = 96
_COMPACT_LIST_DROP_KEYS = {
    "created_at",
    "share_review_age_minutes",
    "share_reviewed_at",
    "source_scan_event_key",
    "source_scan_recorded_at_utc",
    "source_scan_run_id",
    "updated_at",
}
_COMPACT_CLOSED_LIST_DROP_KEYS = {
    "exact_contract_symbol",
    "last_recommendation_reason",
    "share_review_age_minutes",
    "share_reviewed_at",
    "share_safe_exact_live",
    "share_safe_reason",
}


def _compact_source_pick_snapshot(
    source: dict[str, Any],
    *,
    include_entry_quote: bool = True,
    closed_row: bool = False,
) -> dict[str, Any]:
    list_keys = _CLOSED_SOURCE_PICK_LIST_KEYS if closed_row else _SOURCE_PICK_LIST_KEYS
    compact = {
        key: copy.deepcopy(value)
        for key, value in source.items()
        if key in list_keys
    }
    if closed_row:
        liquidity = source.get("spread_liquidity")
        if isinstance(liquidity, dict):
            for key in _CLOSED_SOURCE_LIQUIDITY_DERIVED_KEYS:
                if compact.get(key) is None and liquidity.get(key) is not None:
                    compact[key] = copy.deepcopy(liquidity.get(key))
            if compact.get("fill_degradation_vs_mid_pct") is None:
                entry_debit = _safe_float(liquidity.get("spread_entry_debit"))
                mid_debit = _safe_float(liquidity.get("spread_mid_debit"))
                if entry_debit is not None and mid_debit is not None and mid_debit > 0:
                    compact["fill_degradation_vs_mid_pct"] = max((entry_debit / mid_debit - 1) * 100, 0)
            if compact.get("worst_leg_bid_ask_spread_pct") is None:
                values: list[float] = []
                for prefix in ("long", "short"):
                    bid = _safe_float(liquidity.get(f"{prefix}_bid"))
                    ask = _safe_float(liquidity.get(f"{prefix}_ask"))
                    if bid is None or ask is None:
                        continue
                    mid = (bid + ask) / 2
                    if mid > 0:
                        values.append(max(((ask - bid) / mid) * 100, 0))
                if values:
                    compact["worst_leg_bid_ask_spread_pct"] = max(values)
    entry_quote = source.get("entry_quote_snapshot")
    if include_entry_quote and isinstance(entry_quote, dict):
        compact["entry_quote_snapshot"] = {
            key: copy.deepcopy(value)
            for key, value in entry_quote.items()
            if key in _ENTRY_QUOTE_LIST_KEYS
        }
    return compact


def _compact_position_evidence(row: dict[str, Any], source: dict[str, Any]) -> dict[str, bool]:
    raw_values = [
        row.get("proof_class"),
        row.get("proof_class_reason"),
        row.get("proof_ineligibility_reason"),
        row.get("notes"),
        source.get("pricing_evidence_class"),
        source.get("profitability_evidence_class"),
        source.get("production_filter_action"),
        source.get("source_separation"),
        source.get("promotion_class"),
        source.get("selection_source"),
        source.get("event_type"),
        source.get("candidate_execution_label"),
        source.get("backfill_audit_id"),
        source.get("position_migration_id"),
        source.get("market_data_source"),
        source.get("status"),
    ]
    evidence_values = [str(value).strip().lower() for value in raw_values if str(value or "").strip()]
    compact = {
        "migrated_paper": bool(source.get("position_migration_id") or source.get("position_migrated_at_utc")),
        "research_backfill": bool(source.get("research_only")) or any(
            any(token in value for token in ("backfill", "research", "historical_replay", "historical_selection"))
            for value in evidence_values
        ),
        "comparable_contract": bool(source.get("comparable_contract")),
        "approximation_only": bool(source.get("approximation_only")),
    }
    return {key: value for key, value in compact.items() if value}


def _compact_latest_review(review: dict[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in review.items()
        if key in _LATEST_REVIEW_LIST_KEYS
    }


def _compact_position_list_row(row: dict[str, Any]) -> dict[str, Any]:
    compact = dict(row)
    is_closed = str(compact.get("status") or "").strip().lower() == "closed"
    for key in _COMPACT_LIST_DROP_KEYS:
        compact.pop(key, None)
    if is_closed:
        for key in _COMPACT_CLOSED_LIST_DROP_KEYS:
            compact.pop(key, None)
        compact.pop("latest_review", None)
    notes = compact.get("notes")
    max_notes = _COMPACT_CLOSED_LIST_NOTES_MAX_CHARS if is_closed else _COMPACT_LIST_NOTES_MAX_CHARS
    if isinstance(notes, str) and len(notes) > max_notes:
        compact["notes"] = notes[:max_notes]
    source = compact.get("source_pick_snapshot")
    if isinstance(source, dict):
        compact_evidence = _compact_position_evidence(compact, source)
        if compact_evidence:
            compact["compact_evidence"] = compact_evidence
        compact["source_pick_snapshot"] = _compact_source_pick_snapshot(
            source,
            include_entry_quote=not is_closed,
            closed_row=is_closed,
        )
    review = compact.get("latest_review")
    if isinstance(review, dict):
        compact["latest_review"] = _compact_latest_review(review)
    return compact


def _compact_position_list_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_compact_position_list_row(row) for row in list(rows or [])]


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
    candidate_audit_picks = result.get("candidate_audit_picks")
    normalized_candidate_audit_picks = (
        _normalize_scan_picks(list(candidate_audit_picks or []))
        if candidate_audit_picks is not None
        else []
    )
    scan_snapshot = build_forward_scan_snapshot(
        picks=normalized_picks,
        candidate_audit_picks=normalized_candidate_audit_picks,
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
        "forward_truth_run_id": recorded.get("run_id"),
        "forward_truth_recorded_at_utc": recorded.get("recorded_at_utc"),
        "forward_truth_error": None,
        "forward_truth_evidence_class": evidence_class,
        "forward_truth_authoritative": evidence_class == LIVE_PRODUCTION_EVIDENCE_CLASS,
    }


def _position_event_payload(position: dict[str, Any], *, reason: str) -> dict[str, Any]:
    payload = copy.deepcopy(position)
    latest_review = dict(payload.get("latest_review") or {})
    is_closed = str(payload.get("status") or "").strip().lower() == "closed" or payload.get("closed_at") is not None

    def _first_present(*values: Any) -> Any:
        for value in values:
            if value is not None:
                return value
        return None

    if is_closed:
        latest_review = {
            "reviewed_at": _first_present(payload.get("closed_at"), payload.get("last_reviewed_at"), latest_review.get("reviewed_at"), datetime.now().isoformat()),
            "pricing_source": _first_present(payload.get("exit_execution_basis"), payload.get("exit_reason"), reason, latest_review.get("pricing_source")),
            "current_option_price": _first_present(payload.get("exit_option_price"), payload.get("last_option_price"), latest_review.get("current_option_price")),
            "current_pnl_pct": _first_present(payload.get("gross_pnl_pct"), payload.get("last_pnl_pct"), latest_review.get("current_pnl_pct")),
            "gross_pnl_pct": _first_present(payload.get("gross_pnl_pct"), latest_review.get("gross_pnl_pct")),
            "net_pnl_pct": _first_present(payload.get("net_pnl_pct"), latest_review.get("net_pnl_pct")),
            "gross_pnl_usd": _first_present(payload.get("gross_pnl_usd"), latest_review.get("gross_pnl_usd")),
            "net_pnl_usd": _first_present(payload.get("net_pnl_usd"), latest_review.get("net_pnl_usd")),
            "entry_execution_price": _first_present(payload.get("entry_execution_price"), latest_review.get("entry_execution_price")),
            "exit_execution_price": _first_present(payload.get("exit_execution_price"), latest_review.get("exit_execution_price")),
            "entry_execution_basis": _first_present(payload.get("entry_execution_basis"), latest_review.get("entry_execution_basis")),
            "exit_execution_basis": _first_present(payload.get("exit_execution_basis"), reason, latest_review.get("exit_execution_basis")),
            "fee_total_usd": _first_present(payload.get("fee_total_usd"), latest_review.get("fee_total_usd")),
            "recommendation": "SELL",
            "reason": _first_present(payload.get("exit_reason"), reason, latest_review.get("reason")),
            "warnings": [],
            "metrics_snapshot": dict(latest_review.get("metrics_snapshot") or {}),
        }
    elif not latest_review:
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
) -> dict[str, Any]:
    if not reviewed_positions:
        return {
            "recorded": False,
            "skipped": True,
            "skip_reason": "no_positions",
            "run_mode": run_mode,
            "reason": reason,
        }
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
    return record_forward_snapshot(
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
    recording_event_type: str = "scan_capture",
    recording_operation: str | None = None,
    run_mode: str | None = None,
    reason: str | None = None,
    position_event_count: int = 0,
    position_ids: list[int] | None = None,
) -> None:
    normalized_evidence_class = str(evidence_class or MANUAL_OBSERVATION_EVIDENCE_CLASS).strip().lower()
    payload = {
        "recorded_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source_label": ARCHIVED_FORWARD_SOURCE_LABEL,
        "recording_event_type": str(recording_event_type or "scan_capture"),
        "recording_operation": str(recording_operation).strip() if recording_operation else None,
        "run_mode": str(run_mode).strip() if run_mode else None,
        "reason": str(reason).strip() if reason else None,
        "forward_truth_recorded": bool(recorded),
        "forward_truth_session_id": session_id,
        "forward_truth_error": str(error) if error else None,
        "evidence_class": normalized_evidence_class,
        "forward_truth_authoritative": bool(recorded) and normalized_evidence_class == LIVE_PRODUCTION_EVIDENCE_CLASS,
        "scan_pick_count": len(list(picks or [])),
        "exact_contract_capture_count": sum(
            1 for pick in list(picks or []) if str(pick.get("contract_symbol") or "").strip()
        ),
        "position_event_count": int(position_event_count or 0),
        "position_ids": list(position_ids or []),
    }
    path = _forward_evidence_log_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf8") as handle:
        handle.write(json.dumps(payload) + "\n")


def _position_ids_from_rows(rows: list[dict[str, Any]]) -> list[int]:
    ids: list[int] = []
    for row in list(rows or []):
        try:
            position_id = int(row.get("id"))
        except (TypeError, ValueError):
            continue
        ids.append(position_id)
    return ids


def _position_event_recording_success(
    result: dict[str, Any] | None,
    *,
    operation: str,
    positions: list[dict[str, Any]],
) -> dict[str, Any]:
    if not result or result.get("skipped"):
        return {
            "status": "skipped",
            "recorded": False,
            "skipped": True,
            "skip_reason": (result or {}).get("skip_reason") or "no_result",
            "operation": operation,
            "error": None,
            "error_type": None,
            "health_event_logged": None,
            "health_event_error": None,
            "session_id": None,
            "run_id": None,
            "recorded_at_utc": None,
            "position_event_count": len(list(positions or [])),
            "position_ids": _position_ids_from_rows(positions),
        }
    return {
        "status": "recorded",
        "recorded": True,
        "skipped": False,
        "skip_reason": None,
        "operation": operation,
        "error": None,
        "error_type": None,
        "health_event_logged": None,
        "health_event_error": None,
        "session_id": result.get("session_id"),
        "run_id": result.get("run_id"),
        "recorded_at_utc": result.get("recorded_at_utc"),
        "event_type": result.get("event_type"),
        "position_event_count": len(list(positions or [])),
        "position_ids": _position_ids_from_rows(positions),
    }


async def _position_event_recording_failure(
    *,
    operation: str,
    error: Exception,
    positions: list[dict[str, Any]],
    run_mode: str,
    reason: str,
) -> dict[str, Any]:
    position_ids = _position_ids_from_rows(positions)
    meta = {
        "status": "failed",
        "recorded": False,
        "skipped": False,
        "skip_reason": None,
        "operation": operation,
        "error": str(error),
        "error_type": type(error).__name__,
        "health_event_logged": False,
        "health_event_error": None,
        "session_id": None,
        "run_id": None,
        "recorded_at_utc": None,
        "position_event_count": len(list(positions or [])),
        "position_ids": position_ids,
    }
    try:
        await _run_in_worker(
            _append_forward_evidence_event,
            recorded=False,
            session_id=None,
            error=str(error),
            picks=[],
            evidence_class=_scan_evidence_class(),
            recording_event_type="position_event",
            recording_operation=operation,
            run_mode=run_mode,
            reason=reason,
            position_event_count=len(list(positions or [])),
            position_ids=position_ids,
        )
        meta["health_event_logged"] = True
    except Exception as log_exc:
        meta["health_event_error"] = str(log_exc)
    return meta


def _read_forward_evidence_events(limit: int = 200) -> list[dict[str, Any]]:
    path = _forward_evidence_log_path()
    if not os.path.exists(path):
        return []
    events = deque(maxlen=int(limit)) if limit > 0 else []
    with open(path, "r", encoding="utf8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw:
                continue
            try:
                events.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    return list(events)


def _forward_event_counts_by_type(db_path: Path) -> dict[str, int]:
    counts = {
        "scan_pick": 0,
        "position_opened": 0,
        "position_review": 0,
        "tracked_positions_snapshot": 0,
    }
    try:
        with contextlib.closing(sqlite3.connect(str(db_path))) as conn:
            rows = conn.execute(
                """
                SELECT event_type, COUNT(*) AS count
                FROM forward_events
                GROUP BY event_type
                """
            ).fetchall()
    except Exception:
        return counts
    for event_type, count in rows:
        key = str(event_type or "").strip()
        if not key:
            continue
        try:
            counts[key] = int(count)
        except (TypeError, ValueError):
            counts[key] = 0
    return counts


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
        1 for event in authoritative_events if str(event.get("contract_symbol") or "").strip()
    )
    all_exact_contract_count = sum(
        1 for event in authoritative_all_events if str(event.get("contract_symbol") or "").strip()
    )
    events = _read_forward_evidence_events()
    latest_event = events[-1] if events else None
    failure_events = [event for event in events if not bool(event.get("forward_truth_recorded"))]
    latest_failure = failure_events[-1] if failure_events else None
    failure_events_by_operation: dict[str, int] = {}
    for event in failure_events:
        operation = str(
            event.get("recording_operation")
            or event.get("recording_event_type")
            or "unknown"
        ).strip() or "unknown"
        failure_events_by_operation[operation] = failure_events_by_operation.get(operation, 0) + 1
    authoritative_log_events = [
        event for event in events
        if bool(event.get("forward_truth_authoritative"))
    ]
    latest_authoritative_event = authoritative_log_events[-1] if authoritative_log_events else None
    event_type_counts = _forward_event_counts_by_type(authoritative_db_path)
    position_opened_event_count = int(event_type_counts.get("position_opened") or 0)
    position_review_event_count = int(event_type_counts.get("position_review") or 0)
    latest_artifact = load_last_archived_forward_daily_results()
    latest_artifact_path = wfo_module.OPTIONS_VALIDATION_DAILY_FORWARD_LATEST_FILE
    latest_artifact_timestamp = _latest_artifact_timestamp(latest_artifact_path)
    historical_evidence_available = len(authoritative_events) > 0
    latest_eligible_session = authoritative_sessions[0] if authoritative_sessions else None

    def _session_id(value: Any) -> int | None:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    latest_recorded_session_id = _session_id(latest_authoritative_event.get("forward_truth_session_id")) if latest_authoritative_event else None
    latest_eligible_session_id = _session_id(latest_eligible_session.get("id")) if latest_eligible_session else None
    latest_capture_created_picks = (
        bool(latest_authoritative_event)
        and latest_recorded_session_id is not None
        and latest_recorded_session_id == latest_eligible_session_id
        and int(latest_eligible_session.get("scan_picks_count") or 0) > 0
    ) if latest_eligible_session else False
    if latest_capture_created_picks:
        activation_status = "active"
        activation_message = "The latest eligible live-production capture created authoritative archived scan_pick evidence."
    elif latest_event and str(latest_event.get("evidence_class") or "").strip().lower() != LIVE_PRODUCTION_EVIDENCE_CLASS:
        activation_status = "non_authoritative_latest_scan"
        activation_message = "The latest /api/scan was not recorded as eligible live-production evidence."
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
            "without_contract_count": max(len(authoritative_events) - authoritative_exact_contract_count, 0),
            "all_with_contract_count": all_exact_contract_count,
            "all_without_contract_count": max(len(authoritative_all_events) - all_exact_contract_count, 0),
        },
        "forward_truth_recording_failure_count": len(failure_events),
        "position_event_recording_failure_count": sum(
            count
            for operation, count in failure_events_by_operation.items()
            if operation in {"position_opened", "positions_review", "positions_close", "position_event"}
        ),
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
            "recorded_failure_count_by_operation": failure_events_by_operation,
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
            "position_opened_event_count": position_opened_event_count,
            "position_review_event_count": position_review_event_count,
            "review_event_count": position_review_event_count,
            "position_event_count": position_opened_event_count + position_review_event_count,
            "event_type_counts": event_type_counts,
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


def _parse_result_window(limit: int | None, offset: int) -> tuple[int | None, int]:
    if isinstance(limit, bool) or isinstance(offset, bool):
        raise ValueError("limit and offset must be integers.")
    if limit is None:
        if offset:
            raise ValueError("offset requires limit.")
        return None, 0
    if limit <= 0 or limit > 1000:
        raise ValueError("limit must be between 1 and 1000.")
    if offset < 0:
        raise ValueError("offset must be greater than or equal to 0.")
    return limit, offset


def _page_metadata(rows: list[dict[str, Any]], limit: int | None, offset: int) -> dict[str, int] | None:
    if limit is None:
        return None
    return {"limit": limit, "offset": offset, "returned": len(rows)}


def _summary_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        parsed = float(value)
        if math.isnan(parsed) or math.isinf(parsed):
            return None
        return parsed
    except (TypeError, ValueError):
        return None


def _row_net_pnl_usd(row: dict[str, Any]) -> float | None:
    latest_review = row.get("latest_review") if isinstance(row.get("latest_review"), dict) else {}
    for value in (
        row.get("net_pnl_usd"),
        latest_review.get("net_pnl_usd"),
        row.get("gross_pnl_usd"),
        latest_review.get("gross_pnl_usd"),
    ):
        parsed = _summary_float(value)
        if parsed is not None:
            return parsed
    return None


def _row_net_pnl_pct(row: dict[str, Any]) -> float | None:
    latest_review = row.get("latest_review") if isinstance(row.get("latest_review"), dict) else {}
    for value in (
        row.get("net_pnl_pct"),
        latest_review.get("net_pnl_pct"),
        row.get("gross_pnl_pct"),
        latest_review.get("gross_pnl_pct"),
        row.get("last_pnl_pct"),
    ):
        parsed = _summary_float(value)
        if parsed is not None:
            return parsed
    return None


def _pnl_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    priced_rows: list[tuple[float | None, float | None]] = []
    for row in list(rows or []):
        pnl_usd = _row_net_pnl_usd(row)
        pnl_pct = _row_net_pnl_pct(row)
        if pnl_usd is not None or pnl_pct is not None:
            priced_rows.append((pnl_usd, pnl_pct))

    directional_values = [
        pnl_usd if pnl_usd is not None else pnl_pct
        for pnl_usd, pnl_pct in priced_rows
        if (pnl_usd if pnl_usd is not None else pnl_pct) is not None
    ]
    pct_values = [pnl_pct for _, pnl_pct in priced_rows if pnl_pct is not None]
    usd_values = [pnl_usd for pnl_usd, _ in priced_rows if pnl_usd is not None]
    return {
        "count": len(rows or []),
        "priced_count": len(priced_rows),
        "wins": sum(1 for value in directional_values if value > 0),
        "losses": sum(1 for value in directional_values if value < 0),
        "flat": sum(1 for value in directional_values if value == 0),
        "net_pnl_usd": round(sum(usd_values), 2) if usd_values else None,
        "avg_pnl_pct": round(sum(pct_values) / len(pct_values), 2) if pct_values else None,
    }


def _tracked_vs_proof_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    all_rows = list(rows or [])
    proof_rows = [row for row in all_rows if _row_counts_as_production_proof(row)]
    return {
        "tracked": _pnl_summary(all_rows),
        "proof": _pnl_summary(proof_rows),
    }


def _group_rows_by_status(rows: list[dict[str, Any]]) -> dict[str, Any]:
    open_rows: list[dict[str, Any]] = []
    closed_rows: list[dict[str, Any]] = []
    for row in list(rows or []):
        status = str(row.get("status") or "").strip().lower()
        if status == "closed" or row.get("closed_at"):
            closed_rows.append(row)
        else:
            open_rows.append(row)
    return {
        "open": open_rows,
        "closed": closed_rows,
        "summary": {
            "open": _tracked_vs_proof_summary(open_rows),
            "closed": _tracked_vs_proof_summary(closed_rows),
            "all": _tracked_vs_proof_summary(open_rows + closed_rows),
        },
    }


def _parse_positive_price(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite number greater than 0.")
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a finite number greater than 0.")
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError(f"{field_name} must be a finite number greater than 0.")
    return parsed


def _parse_positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer.")
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a positive integer.")
    if not math.isfinite(parsed) or parsed <= 0 or not parsed.is_integer():
        raise ValueError(f"{field_name} must be a positive integer.")
    return int(parsed)


def _parse_positive_int_or_default(value: Any, field_name: str, default: int) -> int:
    if value in (None, ""):
        return default
    return _parse_positive_int(value, field_name)


def _parse_nonnegative_price(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite number greater than or equal to 0.")
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a finite number greater than or equal to 0.")
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"{field_name} must be a finite number greater than or equal to 0.")
    return parsed


def _parse_positive_price_or_default(value: Any, field_name: str, default: float) -> float:
    if value in (None, ""):
        return default
    return _parse_positive_price(value, field_name)


def _parse_nonnegative_price_or_default(value: Any, field_name: str, default: float) -> float:
    if value in (None, ""):
        return default
    return _parse_nonnegative_price(value, field_name)


def _parse_bool_param(value: Any, field_name: str, default: bool = False) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"{field_name} must be a boolean.")


def _parse_optional_string(value: Any, field_name: str) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool) or not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string.")
    normalized = value.strip()
    return normalized or None


def _parse_optional_iso_datetime(value: Any, field_name: str) -> datetime:
    if value in (None, ""):
        return datetime.now()
    if isinstance(value, datetime):
        return value
    if isinstance(value, bool) or not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO timestamp.")
    raw = value.strip()
    if not raw:
        return datetime.now()
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO timestamp.") from exc


def _run_supervised_scan_request(
    body: dict[str, Any],
    *,
    n_picks: int,
    include_policy_flags: bool = False,
) -> dict[str, Any]:
    scan_mode = str(_parse_optional_string(body.get("scan_mode"), "scan_mode") or "production").strip().lower()
    if scan_mode not in {"production", "diagnostic"}:
        raise ValueError("scan_mode must be production or diagnostic.")
    enforce_portfolio_caps = _parse_bool_param(
        body.get("enforce_portfolio_caps"),
        "enforce_portfolio_caps",
        default=True,
    )
    allow_caps_off = _parse_bool_param(body.get("allow_caps_off"), "allow_caps_off", default=False)
    if not enforce_portfolio_caps and scan_mode != "diagnostic" and not allow_caps_off:
        raise ValueError("Caps-off scans require scan_mode='diagnostic' or allow_caps_off=true.")
    result = run_supervised_scan(
        scan_func=scan_daily_top_trades,
        positions_repository=POSITIONS_REPOSITORY,
        n_picks=n_picks,
        watchlist_size=len(DEFAULT_WATCHLIST),
        playbook_id=_parse_optional_string(body.get("playbook"), "playbook") or SCAN_PLAYBOOK_FALLBACK_ID,
        use_recommended_policy=_parse_bool_param(body.get("use_recommended_policy"), "use_recommended_policy"),
        include_blocked_policy_picks=_parse_bool_param(body.get("include_blocked_policy_picks"), "include_blocked_policy_picks")
        if include_policy_flags
        else False,
        include_blocked_guardrail_picks=_parse_bool_param(body.get("include_blocked_guardrail_picks"), "include_blocked_guardrail_picks")
        if include_policy_flags
        else False,
        enforce_portfolio_caps=enforce_portfolio_caps,
        truth_lane=_parse_optional_string(body.get("truth_lane"), "truth_lane") or LIVE_SCAN_TRUTH_LANE,
        min_trades=_parse_positive_int_or_default(body.get("min_trades"), "min_trades", 20),
        max_tickers=_parse_positive_int_or_default(body.get("max_tickers"), "max_tickers", 8),
        max_sectors=_parse_positive_int_or_default(body.get("max_sectors"), "max_sectors", 8),
        min_profit_factor=_parse_positive_price_or_default(body.get("min_profit_factor"), "min_profit_factor", 1.05),
        min_directional_accuracy_pct=_parse_nonnegative_price_or_default(
            body.get("min_directional_accuracy_pct"),
            "min_directional_accuracy_pct",
            50.0,
        ),
    )
    result["scan_mode"] = scan_mode
    result["allow_caps_off"] = allow_caps_off
    return result


@app.post("/api/scan")
async def run_scan_endpoint(body: dict[str, Any] | None = None):
    """Run daily top trades scan."""
    body = body or {}
    try:
        n_picks = _parse_positive_int_or_default(body.get("n_picks"), "n_picks", DEFAULT_SCAN_PICKS)
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
            "forward_truth_run_id": None,
            "forward_truth_recorded_at_utc": None,
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
                "forward_truth_run_id": None,
                "forward_truth_recorded_at_utc": None,
                "forward_truth_error": str(exc),
                "forward_truth_evidence_class": _scan_evidence_class(),
                "forward_truth_authoritative": False,
        }
        normalized_picks = _annotate_scan_picks_with_forward_provenance(
            normalized_picks,
            forward_truth_meta=forward_truth_meta,
        )
        forward_truth_event_log_error = None
        try:
            await _run_in_worker(
                _append_forward_evidence_event,
                recorded=bool(forward_truth_meta.get("forward_truth_recorded")),
                session_id=forward_truth_meta.get("forward_truth_session_id"),
                error=forward_truth_meta.get("forward_truth_error"),
                picks=normalized_picks,
                evidence_class=forward_truth_meta.get("forward_truth_evidence_class"),
            )
        except Exception as exc:
            forward_truth_event_log_error = str(exc)
        return {
            **{key: value for key, value in result.items() if key not in {"picks", "ranked_picks", "watch_picks", "candidate_audit_picks"}},
            "picks": normalized_picks,
            "watch_picks": normalized_watch_picks,
            "forward_truth_event_log_error": forward_truth_event_log_error,
            **forward_truth_meta,
        }
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/positions")
async def create_position_endpoint(body: dict[str, Any]):
    """Track a user-confirmed options position from a live scan pick."""
    if not getattr(POSITIONS_REPOSITORY, "is_available", False):
        return _positions_unavailable_response()

    try:
        body = parse_create_trading_desk_record_body(body)
        scan_pick = body.get("scan_pick") or {}
        mode = _creation_mode(body, scan_pick)
        source_scan_lineage_verified = _verify_source_scan_lineage(scan_pick)
        if mode == "scanner":
            scan_pick, source_scan_lineage_verified = _validate_scanner_origin_create(
                scan_pick,
                positions_repository=POSITIONS_REPOSITORY,
            )
        payload = build_position_payload(
            scan_pick=scan_pick,
            fill_price=_parse_positive_price(body.get("fill_price"), "fill_price"),
            contracts=_parse_positive_int(body.get("contracts"), "contracts"),
            filled_at=body.get("filled_at"),
            notes=_parse_optional_string(body.get("notes"), "notes"),
            require_proof_eligible=mode == "scanner",
            require_resolved_contract=True,
            preserve_fill_price=True,
            source_scan_lineage_verified=source_scan_lineage_verified,
        )
        existing_position = _find_existing_open_contract(POSITIONS_REPOSITORY, payload)
        if existing_position is not None:
            return {
                "position": existing_position,
                "duplicate": True,
                "position_event_persistence": _position_event_recording_success(
                    {"skipped": True, "skip_reason": "duplicate_open_contract"},
                    operation="position_opened",
                    positions=[existing_position],
                ),
            }
        position = POSITIONS_REPOSITORY.create_position(payload)
        position_event_persistence: dict[str, Any]
        try:
            recording_result = await _run_in_worker(
                record_position_opened,
                position=position,
                source_label="position_opened",
                evidence_class=_scan_evidence_class(),
                run_id=_scan_run_id(),
                run_mode="position_opened",
                is_fixture=_scan_is_fixture(),
            )
            position_event_persistence = _position_event_recording_success(
                recording_result,
                operation="position_opened",
                positions=[position],
            )
        except Exception as exc:
            position_event_persistence = await _position_event_recording_failure(
                operation="position_opened",
                error=exc,
                positions=[position],
                run_mode="position_opened",
                reason="position_opened",
            )
        return {"position": position, "position_event_persistence": position_event_persistence}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/positions")
async def list_positions_endpoint(
    status: str = "open",
    grouped: bool = False,
    limit: int | None = None,
    offset: int = 0,
    compact: bool = False,
):
    """Return tracked options positions from local Postgres."""
    if not getattr(POSITIONS_REPOSITORY, "is_available", False):
        return _positions_unavailable_response()

    if status not in {"open", "closed", "all"}:
        raise HTTPException(400, "status must be one of: open, closed, all")

    try:
        limit, offset = _parse_result_window(limit, offset)
        query_status = None if status == "all" else status
        compact_closed_list = compact and not grouped and query_status == "closed"
        if compact_closed_list and callable(getattr(POSITIONS_REPOSITORY, "list_compact_positions", None)):
            positions = POSITIONS_REPOSITORY.list_compact_positions(query_status, limit=limit, offset=offset)
        else:
            positions = _annotate_share_safety_rows(
                POSITIONS_REPOSITORY.list_positions(query_status, limit=limit, offset=offset)
            )
        if compact:
            positions = _compact_position_list_rows(positions)
        page = _page_metadata(positions, limit, offset)
        if grouped:
            payload = _group_rows_by_status(positions)
            if page is not None:
                payload["page"] = page
            return payload
        payload = {"positions": positions}
        if page is not None:
            payload["page"] = page
        return payload
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/positions/review")
async def review_positions_endpoint(body: dict[str, Any] | None = None):
    """Review open tracked positions and return HOLD/SELL guidance."""
    if not getattr(POSITIONS_REPOSITORY, "is_available", False):
        return _positions_unavailable_response()

    try:
        body = parse_review_trading_desk_records_body(body)
        position_ids = _parse_position_ids(body.get("position_ids"))
        reviewed = await _run_in_worker(review_open_positions, POSITIONS_REPOSITORY, position_ids=position_ids)
        reviewed = _annotate_share_safety_rows(reviewed)
        position_event_persistence: dict[str, Any]
        try:
            recording_result = await _run_in_worker(
                _record_forward_truth_for_position_events,
                reviewed_positions=reviewed,
                run_mode="positions_review",
                reason="tracked_positions_review",
            )
            position_event_persistence = _position_event_recording_success(
                recording_result,
                operation="positions_review",
                positions=reviewed,
            )
        except Exception as exc:
            position_event_persistence = await _position_event_recording_failure(
                operation="positions_review",
                error=exc,
                positions=reviewed,
                run_mode="positions_review",
                reason="tracked_positions_review",
            )
        return {"positions": reviewed, "position_event_persistence": position_event_persistence}
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

    try:
        body = parse_close_trading_desk_record_body(body)
        if body.get("exit_price") is None:
            raise HTTPException(400, "exit_price is required")
        closed_at = _parse_optional_iso_datetime(body.get("closed_at"), "closed_at")
        position = POSITIONS_REPOSITORY.close_position(
            position_id=position_id,
            exit_price=_parse_nonnegative_price(body.get("exit_price"), "exit_price"),
            closed_at=closed_at,
            exit_reason="manual_close",
            notes=_parse_optional_string(body.get("notes"), "notes"),
            allow_zero_exit_price=True,
        )
        if position is None:
            raise HTTPException(404, f"Tracked position {position_id} was not found")
        position_event_persistence: dict[str, Any]
        try:
            recording_result = await _run_in_worker(
                _record_forward_truth_for_position_events,
                reviewed_positions=[position],
                run_mode="positions_close",
                reason="manual_close",
            )
            position_event_persistence = _position_event_recording_success(
                recording_result,
                operation="positions_close",
                positions=[position],
            )
        except Exception as exc:
            position_event_persistence = await _position_event_recording_failure(
                operation="positions_close",
                error=exc,
                positions=[position],
                run_mode="positions_close",
                reason="manual_close",
            )
        return {"position": position, "position_event_persistence": position_event_persistence}
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
        body = parse_create_trading_desk_record_body(body)
        scan_pick = body.get("scan_pick") or {}
        mode = _creation_mode(body, scan_pick)
        source_scan_lineage_verified = _verify_source_scan_lineage(scan_pick)
        if mode == "scanner":
            scan_pick, source_scan_lineage_verified = _validate_scanner_origin_create(
                scan_pick,
                positions_repository=POSITIONS_REPOSITORY,
            )
        payload = build_position_payload(
            scan_pick=scan_pick,
            fill_price=_parse_positive_price(body.get("fill_price"), "fill_price"),
            contracts=_parse_positive_int(body.get("contracts", 1), "contracts"),
            filled_at=body.get("filled_at"),
            notes=_parse_optional_string(body.get("notes"), "notes"),
            require_proof_eligible=mode == "scanner",
            require_resolved_contract=True,
            preserve_fill_price=True,
            source_scan_lineage_verified=source_scan_lineage_verified,
        )
        existing_trade = _find_existing_open_contract(SUGGESTED_TRADES_REPOSITORY, payload)
        if existing_trade is not None:
            return {"trade": existing_trade, "duplicate": True}
        trade = SUGGESTED_TRADES_REPOSITORY.create_position(payload)
        return {"trade": trade}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/suggested-trades")
async def list_suggested_trades_endpoint(
    status: str = "open",
    grouped: bool = False,
    limit: int | None = None,
    offset: int = 0,
    compact: bool = False,
):
    """Return hypothetical scanner trades tracked in local SQLite."""
    if not getattr(SUGGESTED_TRADES_REPOSITORY, "is_available", False):
        return _suggested_trades_unavailable_response()

    if status not in {"open", "closed", "all"}:
        raise HTTPException(400, "status must be one of: open, closed, all")

    try:
        limit, offset = _parse_result_window(limit, offset)
        query_status = None if status == "all" else status
        trades = _annotate_share_safety_rows(
            SUGGESTED_TRADES_REPOSITORY.list_positions(query_status, limit=limit, offset=offset)
        )
        if compact:
            trades = _compact_position_list_rows(trades)
        page = _page_metadata(trades, limit, offset)
        if grouped:
            payload = _group_rows_by_status(trades)
            if page is not None:
                payload["page"] = page
            return payload
        payload = {"trades": trades}
        if page is not None:
            payload["page"] = page
        return payload
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/suggested-trades/review")
async def review_suggested_trades_endpoint(body: dict[str, Any] | None = None):
    """Review open suggested trades and refresh their hypothetical P/L."""
    if not getattr(SUGGESTED_TRADES_REPOSITORY, "is_available", False):
        return _suggested_trades_unavailable_response()

    try:
        body = parse_review_trading_desk_records_body(body)
        position_ids = _parse_position_ids(body.get("position_ids"))
        reviewed = await _run_in_worker(review_open_positions, SUGGESTED_TRADES_REPOSITORY, position_ids=position_ids)
        reviewed = _annotate_share_safety_rows(reviewed)
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

    try:
        body = parse_close_trading_desk_record_body(body)
        exit_price = body.get("exit_price")
        if exit_price is None:
            raise HTTPException(400, "exit_price is required")
        closed_at = _parse_optional_iso_datetime(body.get("closed_at"), "closed_at")
        trade = SUGGESTED_TRADES_REPOSITORY.close_position(
            position_id=position_id,
            exit_price=_parse_nonnegative_price(exit_price, "exit_price"),
            closed_at=closed_at,
            exit_reason="manual_hypothetical_close",
            notes=_parse_optional_string(body.get("notes"), "notes"),
            allow_zero_exit_price=True,
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
async def get_recommendations(body: dict[str, Any] | None = None):
    """Generate position recommendations for pending picks."""
    body = body or {}
    preds = _load_predictions()
    pending = [p for p in preds if not p.get("outcome") and p.get("type") == "daily_scan"]
    try:
        n_picks = _parse_positive_int_or_default(body.get("n_picks"), "n_picks", DEFAULT_SCAN_PICKS)
        supervised = _run_supervised_scan_request(body, n_picks=n_picks)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if supervised.get("policy_fail_closed"):
        return supervised
    candidates = supervised["picks"] if supervised.get("policy_applied") else supervised["ranked_picks"]
    result = generate_position_recommendations(
        pending,
        n_picks=n_picks,
        candidates=candidates,
    )
    result = _normalize_recommendation_payload(result)
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
async def roll_picks(body: dict[str, Any] | None = None):
    """Roll forward daily picks."""
    body = body or {}
    preds = _load_predictions()
    pending = [p for p in preds if not p.get("outcome") and p.get("type") == "daily_scan"]
    try:
        n_picks = _parse_positive_int_or_default(body.get("n_picks"), "n_picks", DEFAULT_SCAN_PICKS)
        supervised = _run_supervised_scan_request(body, n_picks=n_picks)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if supervised.get("policy_fail_closed"):
        return supervised
    candidates = supervised["picks"] if supervised.get("policy_applied") else supervised["ranked_picks"]
    result = roll_forward_daily_picks(
        pending,
        n_picks=n_picks,
        candidates=candidates,
    )
    result = _normalize_roll_payload(result)
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
            return "Unavailable", None, "unavailable"
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

        return score_to_sentiment(score), round(ret_pct, 1), "available"

    tickers = [etf for _, etf in SECTORS]
    with _market_data_request_scope():
        hist = _md_download_history_batch(tickers, period="760d", auto_adjust=True)["Close"]

    rows = []
    for sector, etf in SECTORS:
        try:
            closes = hist[etf].dropna()
            if len(closes) < 30:
                raise ValueError("insufficient data")
            nt_sent, nt_ret, nt_status = sentiment_for_window(closes, 21)
            mt_sent, mt_ret, mt_status = sentiment_for_window(closes, 126)
            lt_sent, lt_ret, lt_status = sentiment_for_window(closes, 252)
            window_statuses = {nt_status, mt_status, lt_status}
            data_status = (
                "available"
                if window_statuses == {"available"}
                else "partial"
                if "available" in window_statuses
                else "unavailable"
            )
            rows.append({
                "sector": sector, "etf": etf,
                "near_sent": nt_sent, "near_ret": nt_ret,
                "med_sent": mt_sent, "med_ret": mt_ret,
                "long_sent": lt_sent, "long_ret": lt_ret,
                "data_status": data_status,
            })
        except Exception:
            rows.append({
                "sector": sector, "etf": etf,
                "near_sent": "Unavailable", "near_ret": None,
                "med_sent": "Unavailable", "med_ret": None,
                "long_sent": "Unavailable", "long_ret": None,
                "data_status": "unavailable",
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
async def run_backtest_endpoint(body: dict[str, Any] | None = None):
    """Run historical backtest."""
    body = body or {}
    try:
        lookback_years = _parse_positive_int_or_default(body.get("lookback_years"), "lookback_years", 5)
        iv_adj = _parse_positive_price_or_default(body.get("iv_adj"), "iv_adj", 1.20)
        n_picks = _parse_positive_int_or_default(body.get("n_picks"), "n_picks", DEFAULT_SCAN_PICKS)
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
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/backtest/archived-forward")
async def run_archived_forward_backtest_endpoint(body: dict[str, Any] | None = None):
    """Run archived-forward exact-contract imported-daily replay over /api/scan picks."""
    body = body or {}
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
    result = await _run_in_worker(
        replay_profit_service.cached_backtest_report,
        _ROUTE_CONTEXT,
        truth_lane,
        min_trades,
    )
    if result.get("error"):
        return result
    return result


@app.get("/api/backtest/metric-truth")
async def get_metric_truth_report(min_trades: int = 20, bucket_size: int = 10, truth_lane: str | None = None):
    """Return a calibration and profitability truth report from the most recent backtest."""
    return await _run_in_worker(
        replay_profit_service.cached_metric_truth_report,
        _ROUTE_CONTEXT,
        truth_lane,
        min_trades,
        bucket_size,
    )


@app.post("/api/backtest/experiments")
async def get_backtest_experiments(body: dict[str, Any] | None = None):
    """Return a ranked options-only experiment matrix from the most recent backtest."""
    body = body or {}
    result = await _run_in_worker(
        replay_profit_service.cached_backtest_experiments,
        _ROUTE_CONTEXT,
        body,
    )
    if result.get("error"):
        return result
    return result


@app.get("/api/backtest/profitability-forensics")
async def get_backtest_profitability_forensics(min_trades: int = 20, truth_lane: str | None = None):
    """Return slice-based profitability forensics from the most recent backtest."""
    result = await _run_in_worker(
        replay_profit_service.cached_backtest_profitability_forensics,
        _ROUTE_CONTEXT,
        min_trades,
        truth_lane,
    )
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
    result = await _run_in_worker(
        replay_profit_service.cached_backtest_stability,
        _ROUTE_CONTEXT,
        min_trades,
        min_profit_factor,
        truth_lane,
    )
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
        replay_profit_service.cached_live_trade_policy_report,
        _ROUTE_CONTEXT,
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
    playbook: str = SCAN_PLAYBOOK_FALLBACK_ID,
    min_trades: int = 20,
    max_tickers: int = 8,
    max_sectors: int = 8,
    min_profit_factor: float = 1.05,
    min_directional_accuracy_pct: float = 50.0,
    truth_lane: str | None = None,
):
    """Return a replay exit audit for the approved/watch/blocked cohorts in a playbook window."""
    result = await _run_in_worker(
        replay_profit_service.cached_playbook_exit_audit_report,
        _ROUTE_CONTEXT,
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
    result = await _run_in_worker(
        replay_profit_service.cached_truth_lane_comparison_report,
        _ROUTE_CONTEXT,
        truth_lane,
    )
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
        return await _run_in_worker(
            replay_profit_service.build_backtest_summary,
            _ROUTE_CONTEXT,
            truth_lane,
            min_trades,
            bucket_size,
        )
    except Exception as exc:
        raise HTTPException(500, str(exc))


# ── Changelog endpoint ────────────────────────────────────────────────────────


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


# -- Risk settings shortcut --


# -- Health check --


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
        return await _run_in_worker(build_proof_summary, _ROUTE_CONTEXT)
    except Exception as exc:
        raise HTTPException(500, str(exc))
