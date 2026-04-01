"""
FastAPI backend for the options scanner and research UI.
Exposes tool dispatch plus scanner, replay, and position endpoints.
"""

import os
import sys
import json
import math
import sqlite3
import contextlib
from datetime import datetime
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

from wfo_optimizer import (
    run_historical_backtest,
    load_last_results_by_truth_lane,
    build_prediction_replay_report,
    build_options_experiment_matrix,
    build_options_stability_report,
    build_live_options_trade_policy,
    build_playbook_exit_audit,
    build_truth_lane_comparison,
)
from metric_truth_audit import build_metric_truth_report
from positions_repository import create_positions_repository
from positions_service import build_position_payload, review_open_positions
from suggested_trades_repository import create_suggested_trades_repository
from supervised_scan import (
    LIVE_SCAN_TRUTH_LANE,
    run_supervised_scan,
    scan_pick_market_regime,
)

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
        result = fn(**body)
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
    normalized["contract_symbol"] = pick.get("contract_symbol") or pick.get("contractSymbol")
    normalized["ev"] = pick.get("ev_pct")
    normalized["strike"] = pick.get("strike_est")
    normalized["premium"] = pick.get("est_premium")
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
    return normalized


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
        result = _run_supervised_scan_request(body, n_picks=n_picks, include_policy_flags=True)
        return {
            **{key: value for key, value in result.items() if key not in {"picks", "ranked_picks"}},
            "picks": [_normalize_scan_pick(pick) for pick in result["picks"]],
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
        return {"position": position}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/positions")
async def list_positions_endpoint(status: str = "open"):
    """Return tracked options positions from local Postgres."""
    if not getattr(POSITIONS_REPOSITORY, "is_available", False):
        return _positions_unavailable_response()

    if status not in {"open", "closed", "all"}:
        raise HTTPException(400, "status must be one of: open, closed, all")

    try:
        query_status = None if status == "all" else status
        return {"positions": POSITIONS_REPOSITORY.list_positions(query_status)}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/positions/review")
async def review_positions_endpoint(body: dict[str, Any] = {}):
    """Review open tracked positions and return HOLD/SELL guidance."""
    if not getattr(POSITIONS_REPOSITORY, "is_available", False):
        return _positions_unavailable_response()

    try:
        position_ids = _parse_position_ids(body.get("position_ids"))
        reviewed = review_open_positions(POSITIONS_REPOSITORY, position_ids=position_ids)
        return {"positions": reviewed}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
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
async def list_suggested_trades_endpoint(status: str = "open"):
    """Return hypothetical scanner trades tracked in local SQLite."""
    if not getattr(SUGGESTED_TRADES_REPOSITORY, "is_available", False):
        return _suggested_trades_unavailable_response()

    if status not in {"open", "closed", "all"}:
        raise HTTPException(400, "status must be one of: open, closed, all")

    try:
        query_status = None if status == "all" else status
        return {"trades": SUGGESTED_TRADES_REPOSITORY.list_positions(query_status)}
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
        reviewed = review_open_positions(SUGGESTED_TRADES_REPOSITORY, position_ids=position_ids)
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
    result = generate_position_recommendations(
        pending,
        n_picks=n_picks,
        candidates=supervised["ranked_picks"],
    )
    return {
        **result,
        "policy_applied": supervised["policy_applied"],
        "policy": supervised["policy"],
        "playbook": supervised["playbook"],
        "truth_lane": supervised["truth_lane"],
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
    result = roll_forward_daily_picks(
        pending,
        n_picks=n_picks,
        candidates=supervised["ranked_picks"],
    )
    return {
        **result,
        "policy_applied": supervised["policy_applied"],
        "policy": supervised["policy"],
        "playbook": supervised["playbook"],
        "truth_lane": supervised["truth_lane"],
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
        result = run_historical_backtest(
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


@app.get("/api/backtest/last")
async def get_last_backtest(truth_lane: str | None = None):
    """Return last saved backtest results."""
    result = load_last_results_by_truth_lane(truth_lane)
    if not result:
        return {"error": "No backtest results found"}
    return result


@app.get("/api/backtest/report")
async def get_backtest_report(min_trades: int = 20, truth_lane: str | None = None):
    """Return a grouped replay report from the most recent backtest."""
    result = build_prediction_replay_report(
        result=load_last_results_by_truth_lane(truth_lane),
        min_trades=min_trades,
    )
    if result.get("error"):
        return result
    return result


@app.get("/api/backtest/metric-truth")
async def get_metric_truth_report(min_trades: int = 20, bucket_size: int = 10, truth_lane: str | None = None):
    """Return a calibration and profitability truth report from the most recent backtest."""
    result = load_last_results_by_truth_lane(truth_lane)
    if not result:
        return {"error": "No backtest results found"}
    return build_metric_truth_report(
        result=result,
        min_trades=min_trades,
        bucket_size=bucket_size,
    )


@app.post("/api/backtest/experiments")
async def get_backtest_experiments(body: dict[str, Any] = {}):
    """Return a ranked options-only experiment matrix from the most recent backtest."""
    result = build_options_experiment_matrix(
        result=load_last_results_by_truth_lane(body.get("truth_lane")),
        min_trades=body.get("min_trades", 20),
        score_floors=body.get("score_floors"),
        max_tickers=body.get("max_tickers", 8),
        max_sectors=body.get("max_sectors", 8),
        min_profit_factor=body.get("min_profit_factor", 1.05),
        min_directional_accuracy_pct=body.get("min_directional_accuracy_pct", 50.0),
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
    result = build_options_stability_report(
        result=load_last_results_by_truth_lane(truth_lane),
        min_trades=min_trades,
        min_profit_factor=min_profit_factor,
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
    result = build_live_options_trade_policy(
        truth_lane=truth_lane,
        min_trades=min_trades,
        max_tickers=max_tickers,
        max_sectors=max_sectors,
        min_profit_factor=min_profit_factor,
        min_directional_accuracy_pct=min_directional_accuracy_pct,
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
    result = build_playbook_exit_audit(
        playbook=playbook,
        truth_lane=truth_lane,
        min_trades=min_trades,
        max_tickers=max_tickers,
        max_sectors=max_sectors,
        min_profit_factor=min_profit_factor,
        min_directional_accuracy_pct=min_directional_accuracy_pct,
    )
    if result.get("error"):
        return result
    return result


@app.get("/api/backtest/comparison")
async def get_backtest_truth_lane_comparison(truth_lane: str | None = None):
    """Compare the latest synthetic and imported validation lanes side by side."""
    result = build_truth_lane_comparison(truth_lane=truth_lane)
    if result.get("error"):
        return result
    return result


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
