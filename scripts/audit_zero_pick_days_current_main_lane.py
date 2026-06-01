from __future__ import annotations

import argparse
import copy
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
for candidate in (ROOT, BACKEND_DIR):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

import wfo_optimizer as wfo
from forward_options_ledger import build_forward_scan_snapshot, record_forward_snapshot
from historical_options_store import (
    DAILY_QUOTE_MINUTE_ET,
    ENTRY_QUOTE_MINUTE_ET,
    ENTRY_QUOTE_WINDOW_MINUTES,
    HistoricalOptionsStore,
)
from local_env import load_local_env
from supervised_scan import DEFAULT_SCAN_PLAYBOOK_ID, get_scan_playbook
from us_equity_market_calendar import is_us_equity_market_day

from scripts import log_scan_picks


ET = ZoneInfo("America/New_York")
AUDIT_ID = "main_lane_zero_pick_current_algo_v1"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
SCAN_LOG = DEFAULT_OUTPUT_DIR / "scan_picks.jsonl"
FILL_ATTEMPT_LOG = DEFAULT_OUTPUT_DIR / "fill_attempts.jsonl"
FORWARD_LEDGER_DB = ROOT / "data" / "options-validation" / "forward_tracking_authoritative.db"
HISTORICAL_OPTIONS_DB = ROOT / "data" / "options-validation" / "options_history.db"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value in (None, ""):
        return fallback
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return fallback


def _jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        parsed = _safe_json(text, None)
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def _append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _date_text(value: Any) -> str:
    return str(value or "")[:10]


def _parse_date(value: str) -> date:
    return date.fromisoformat(str(value)[:10])


def _date_range(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _previous_market_day(anchor: date) -> date:
    current = anchor
    while not is_us_equity_market_day(current):
        current -= timedelta(days=1)
    return current


def _main_lane_sessions(db_path: Path, playbook_id: str) -> dict[str, dict[str, Any]]:
    if not db_path.exists():
        return {}
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, recorded_at_utc, source_label, playbook, scan_picks_count, run_id, notes_json
            FROM forward_sessions
            WHERE COALESCE(playbook, '') = ?
              AND COALESCE(source_label, '') IN ('scheduled_scan', 'api_scan_auto', 'research_backfill')
            ORDER BY recorded_at_utc ASC, id ASC
            """,
            (playbook_id,),
        ).fetchall()
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        session_date = _date_text(row["recorded_at_utc"])
        item = grouped.setdefault(
            session_date,
            {
                "date": session_date,
                "session_ids": [],
                "scan_picks_count": 0,
                "scheduled_or_api_session_count": 0,
                "research_backfill_session_count": 0,
                "funnels": [],
            },
        )
        item["session_ids"].append(int(row["id"]))
        item["scan_picks_count"] += int(row["scan_picks_count"] or 0)
        source = str(row["source_label"] or "")
        if source == "research_backfill":
            item["research_backfill_session_count"] += 1
        else:
            item["scheduled_or_api_session_count"] += 1
        notes = _safe_json(row["notes_json"], {})
        if isinstance(notes, dict) and isinstance(notes.get("scan_funnel"), dict):
            item["funnels"].append(notes["scan_funnel"])
    return grouped


def _discover_audit_dates(
    *,
    playbook_id: str,
    date_from: date | None,
    date_to: date | None,
    scope: str,
) -> tuple[list[date], dict[str, list[str]], dict[str, Any]]:
    scan_rows = _jsonl_rows(SCAN_LOG)
    all_pick_dates = {_date_text(row.get("scan_date") or row.get("logged_at")) for row in scan_rows}
    all_pick_dates = {value for value in all_pick_dates if value}
    main_pick_dates = {
        _date_text(row.get("scan_date") or row.get("logged_at"))
        for row in scan_rows
        if str(row.get("playbook_id") or "").strip() == playbook_id
    }
    main_pick_dates = {value for value in main_pick_dates if value}
    main_sessions = _main_lane_sessions(FORWARD_LEDGER_DB, playbook_id)

    default_start = min((_parse_date(value) for value in all_pick_dates), default=date(2026, 4, 8))
    session_dates = [_parse_date(value) for value in main_sessions if value]
    default_end = max(
        [_parse_date(value) for value in all_pick_dates]
        + session_dates
        + [_previous_market_day(datetime.now(ET).date())],
        default=_previous_market_day(datetime.now(ET).date()),
    )
    start = date_from or default_start
    end = _previous_market_day(date_to or default_end)

    reasons_by_date: dict[str, list[str]] = defaultdict(list)
    market_dates = [day for day in _date_range(start, end) if is_us_equity_market_day(day)]
    first_main_session_date = min((_parse_date(value) for value in main_sessions), default=None)
    for day in market_dates:
        day_text = day.isoformat()
        if day_text not in all_pick_dates:
            reasons_by_date[day_text].append("zero_any_scan_picks")
        if day_text not in main_pick_dates:
            if first_main_session_date is None or day >= first_main_session_date:
                reasons_by_date[day_text].append("zero_main_lane_scan_picks")
        session = main_sessions.get(day_text)
        if session and int(session.get("scheduled_or_api_session_count") or 0) > 0 and int(session.get("scan_picks_count") or 0) == 0:
            reasons_by_date[day_text].append("main_lane_session_zero_picks")

    if scope == "zero_any":
        selected = [day for day in market_dates if "zero_any_scan_picks" in reasons_by_date[day.isoformat()]]
    elif scope == "main_zero":
        selected = [
            day
            for day in market_dates
            if any(
                reason in reasons_by_date[day.isoformat()]
                for reason in ("zero_main_lane_scan_picks", "main_lane_session_zero_picks")
            )
        ]
    else:
        selected = [day for day in market_dates if reasons_by_date[day.isoformat()]]

    discovery = {
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "scope": scope,
        "all_pick_dates": sorted(all_pick_dates),
        "main_pick_dates": sorted(main_pick_dates),
        "main_sessions": main_sessions,
        "market_date_count": len(market_dates),
    }
    return selected, {day.isoformat(): reasons_by_date[day.isoformat()] for day in selected}, discovery


def _copy_playbook_value(value: Any) -> Any:
    if isinstance(value, (list, tuple, set)):
        return list(value)
    if isinstance(value, dict):
        return dict(value)
    return value


def _build_replay_playbook_for_audit(playbook_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    playbook_id = str(playbook_id or "").strip().lower()
    scan_playbook = get_scan_playbook(playbook_id)
    calibration_playbook_id = str(scan_playbook.get("calibration_playbook") or "").strip().lower()
    if playbook_id in wfo.REPLAY_PLAYBOOKS:
        base_playbook_id = playbook_id
        adapter_source = "direct_replay_playbook"
    elif calibration_playbook_id and calibration_playbook_id in wfo.REPLAY_PLAYBOOKS:
        base_playbook_id = calibration_playbook_id
        adapter_source = "calibration_playbook"
    else:
        raise RuntimeError(
            f"Scan playbook '{playbook_id}' has no historical replay adapter. "
            "Add a matching wfo.REPLAY_PLAYBOOKS entry or a calibration_playbook before auditing it."
        )

    replay_playbook = copy.deepcopy(wfo.REPLAY_PLAYBOOKS[base_playbook_id])
    replay_playbook["id"] = playbook_id
    replay_playbook["label"] = scan_playbook.get("label") or replay_playbook.get("label") or playbook_id
    replay_playbook["target_dte"] = scan_playbook.get("target_dte", replay_playbook.get("target_dte", 35))

    scan_tickers = (
        scan_playbook.get("scan_tickers")
        or scan_playbook.get("allowed_tickers")
        or replay_playbook.get("allowed_tickers")
        or replay_playbook.get("historical_required_underlyings")
        or getattr(wfo, "REGULAR_OPTIONS_REPLAY_UNIVERSE", [])
        or getattr(wfo, "IMPORTED_VALIDATION_UNIVERSE", [])
        or []
    )
    replay_playbook["allowed_tickers"] = [str(symbol).strip().upper() for symbol in scan_tickers if str(symbol).strip()]

    scan_directions = (
        scan_playbook.get("scan_allowed_directions")
        or scan_playbook.get("allowed_directions")
        or replay_playbook.get("allowed_directions")
        or ["call"]
    )
    replay_playbook["allowed_directions"] = [str(direction).strip().lower() for direction in scan_directions if str(direction).strip()]

    for key in (
        "allowed_asset_classes",
        "allowed_market_regimes",
        "allowed_sectors",
        "allowed_strategy_types",
        "min_quality_score",
        "max_debit_pct_of_width",
        "max_scan_picks_per_ticker",
    ):
        if scan_playbook.get(key) is not None:
            replay_playbook[key] = _copy_playbook_value(scan_playbook[key])

    if scan_playbook.get("signal_variant") and not replay_playbook.get("entry_signal_id"):
        replay_playbook["entry_signal_id"] = str(scan_playbook["signal_variant"]).strip()

    if str(replay_playbook.get("entry_signal_id") or "").strip().lower() == "pullback_uptrend":
        replay_playbook.setdefault("allowed_signal_families", ["bullish_pullback"])
        replay_playbook.setdefault("pullback_ret5_min", -4.0)
        replay_playbook.setdefault("pullback_ret5_max", 0.25)
        replay_playbook.setdefault("pullback_ret20_min", 2.0)

    adapter = {
        "source": adapter_source,
        "base_playbook_id": base_playbook_id,
        "scan_playbook_id": playbook_id,
        "calibration_playbook_id": calibration_playbook_id or None,
        "entry_signal_id": replay_playbook.get("entry_signal_id") or "momentum_default",
        "allowed_signal_families": replay_playbook.get("allowed_signal_families") or [],
        "uses_default_momentum_entry": not bool(replay_playbook.get("entry_signal_id")),
    }
    return scan_playbook, replay_playbook, adapter


def _entry_dt(entry_date: date, minute_et: int) -> datetime:
    return datetime.combine(entry_date, time(hour=minute_et // 60, minute=minute_et % 60), tzinfo=ET)


def _quote_mid(bid: Any, ask: Any) -> float | None:
    bid_value = _safe_float(bid)
    ask_value = _safe_float(ask)
    if bid_value is None or ask_value is None:
        return None
    return round((bid_value + ask_value) / 2.0, 4)


def _leg_snapshot(quote: Any, role: str) -> dict[str, Any]:
    return {
        "role": role,
        "contract_symbol": quote.contract_symbol,
        "expiry": quote.expiry,
        "option_type": quote.option_type,
        "strike": round(float(quote.strike), 4),
        "bid": quote.bid,
        "ask": quote.ask,
        "last": quote.last,
        "mid": _quote_mid(quote.bid, quote.ask),
        "iv": quote.iv,
        "volume": quote.volume,
        "open_interest": quote.open_interest,
        "quote_time_utc": quote.as_of_utc,
        "quote_minute_et": quote.quote_minute_et,
        "quote_basis": quote.price_basis,
        "snapshot_kind": quote.snapshot_kind,
    }


class CurrentMainLaneReplay:
    def __init__(
        self,
        *,
        playbook_id: str,
        truth_lane: str,
        pricing_lane: str,
        source_labels: list[str],
        trusted_only: bool,
        lookback_years: int,
        audit_id: str = AUDIT_ID,
    ) -> None:
        self.playbook_id = playbook_id
        self.audit_id = audit_id
        self.truth_lane = truth_lane
        self.pricing_lane = pricing_lane
        self.source_labels = source_labels
        self.trusted_only = trusted_only
        self.lookback_years = lookback_years
        self.snapshot_kind = wfo._imported_snapshot_kind(truth_lane)
        self.entry_quote_minute_et = DAILY_QUOTE_MINUTE_ET if truth_lane == wfo.IMPORTED_DAILY_TRUTH_SOURCE else ENTRY_QUOTE_MINUTE_ET
        self.entry_window_minutes = 0 if truth_lane == wfo.IMPORTED_DAILY_TRUTH_SOURCE else ENTRY_QUOTE_WINDOW_MINUTES
        self.store = HistoricalOptionsStore()

        scan_playbook, replay_playbook, replay_adapter_info = _build_replay_playbook_for_audit(playbook_id)
        self.replay_playbook = replay_playbook
        self.replay_adapter_info = replay_adapter_info
        self.scan_playbook = scan_playbook
        self.symbols = [str(symbol).strip().upper() for symbol in replay_playbook.get("allowed_tickers") or [] if str(symbol).strip()]

        eq_sp = wfo.STRATEGY_PROFILES.get("equity", wfo.STRATEGY_PROFILE)
        idx_sp = wfo.STRATEGY_PROFILES.get("index", wfo.STRATEGY_PROFILE)
        eq_config, _ = wfo._build_profile_config(eq_sp)
        idx_config, _ = wfo._build_profile_config(idx_sp)
        self.eq_config = wfo._apply_replay_playbook_config_overrides(eq_config, replay_playbook)
        self.idx_config = wfo._apply_replay_playbook_config_overrides(idx_config, replay_playbook)
        self.eq_sp = eq_sp
        self.idx_sp = idx_sp
        self.underlying_filters = wfo._replay_underlying_filters_for_playbook(replay_playbook)

        self.spy_index: pd.DatetimeIndex | None = None
        self.all_closes: dict[str, pd.Series] = {}
        self.all_opens: dict[str, pd.Series] = {}
        self.precomputed: dict[str, list[Any]] = {}
        self.ticker_arrays: dict[str, dict[str, Any]] = {}
        self.ticker_sectors: dict[str, str] = {}
        self.available_quote_dates_by_symbol: dict[str, set[str]] = {}

    def _ticker_cfg(self, ticker: str) -> tuple[dict[str, Any], dict[str, Any]]:
        return (self.idx_config, self.idx_sp) if ticker.upper() in wfo.INDEX_TICKERS else (self.eq_config, self.eq_sp)

    def load(self) -> None:
        fetch_days = max(int(self.lookback_years) * 365 + 365, 800)
        symbols = list(dict.fromkeys([*self.symbols, "SPY"]))
        histories: dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            try:
                hist = wfo._cached_history(symbol, period=f"{fetch_days}d")
                hist = wfo._sanitize_replay_history_frame(hist)
            except Exception:
                continue
            if hist is None or hist.empty or len(hist) < 100:
                continue
            if not {"Open", "Close", "Volume"}.issubset(hist.columns):
                continue
            normalized = hist[["Open", "Close", "Volume"]].copy()
            normalized.index = wfo._normalize_replay_history_index(normalized.index)
            normalized = normalized[~normalized.index.duplicated(keep="last")]
            histories[symbol] = normalized
        if "SPY" not in histories:
            raise RuntimeError("Could not fetch SPY price history for current-algorithm audit.")

        self.spy_index = histories["SPY"].index
        for symbol, hist in histories.items():
            aligned = hist.reindex(self.spy_index).ffill()
            if aligned["Close"].isna().any() or aligned["Open"].isna().any():
                continue
            aligned["Volume"] = aligned["Volume"].fillna(0.0)
            closes = aligned["Close"].astype(float)
            self.all_closes[symbol] = closes
            self.all_opens[symbol] = aligned["Open"].astype(float)
            # Selection-only audit: do not blank recent dates just because a
            # full exit simulation horizon is unavailable.
            pc = wfo._precompute(closes, 0)
            self.precomputed[symbol] = pc
            prices_arr = closes.values.astype(float)
            volumes_s = aligned["Volume"].astype(float)
            avg_volume_20d = volumes_s.rolling(wfo.UNDERLYING_LIQUIDITY_WINDOW, min_periods=wfo.UNDERLYING_LIQUIDITY_WINDOW).mean().fillna(0.0)
            avg_dollar_volume_20d = (closes * volumes_s).rolling(
                wfo.UNDERLYING_LIQUIDITY_WINDOW,
                min_periods=wfo.UNDERLYING_LIQUIDITY_WINDOW,
            ).mean().fillna(0.0)
            macd_full = pd.Series(prices_arr).ewm(span=12, adjust=False).mean() - pd.Series(prices_arr).ewm(span=26, adjust=False).mean()
            rsi14 = [50.0] * len(prices_arr)
            sma20 = [float("nan")] * len(prices_arr)
            sma50 = [float("nan")] * len(prices_arr)
            for item in pc:
                if item is None:
                    continue
                idx = int(item["idx"])
                rsi14[idx] = item["rsi14"]
                sma20[idx] = item["sma20"]
                sma50[idx] = item["sma50"]
            self.ticker_arrays[symbol] = {
                "prices": prices_arr,
                "opens": self.all_opens[symbol].values.astype(float),
                "_adv20": avg_volume_20d.values.astype(float),
                "_adtv20": avg_dollar_volume_20d.values.astype(float),
                "_macd": macd_full.values.astype(float),
                "_rsi14": rsi14,
                "_sma20": sma20,
                "_sma50": sma50,
            }

        for symbol in self.symbols:
            if symbol in wfo.INDEX_TICKERS:
                self.ticker_sectors[symbol] = "Index ETF"
            else:
                try:
                    self.ticker_sectors[symbol] = wfo._cached_ticker_info(symbol).get("sector") or "Unknown"
                except Exception:
                    self.ticker_sectors[symbol] = "Unknown"

    def _available_quote_dates(self, symbol: str) -> set[str]:
        symbol = symbol.upper()
        if symbol not in self.available_quote_dates_by_symbol:
            try:
                self.available_quote_dates_by_symbol[symbol] = set(
                    self.store.available_quote_dates(
                        symbol,
                        snapshot_kind=self.snapshot_kind,
                        trusted_only=self.trusted_only,
                        source_labels=self.source_labels,
                    )
                )
            except Exception:
                self.available_quote_dates_by_symbol[symbol] = set()
        return self.available_quote_dates_by_symbol[symbol]

    def _date_index(self, audit_date: date) -> int | None:
        if self.spy_index is None:
            raise RuntimeError("Price histories are not loaded.")
        timestamp = pd.Timestamp(audit_date)
        if timestamp not in self.spy_index:
            return None
        return int(self.spy_index.get_loc(timestamp))

    def signal_candidates_for_date(self, audit_date: date) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        day_idx = self._date_index(audit_date)
        if day_idx is None:
            return [], [{"ticker": None, "reason": "date_missing_from_spy_history"}]
        if day_idx < 57:
            return [], [{"ticker": None, "reason": "insufficient_indicator_warmup"}]

        spy_closes = self.all_closes.get("SPY")
        spy_ret5_today = 0.0
        if spy_closes is not None and day_idx >= 6:
            spy_ret5_today = float((spy_closes.iloc[day_idx - 1] / spy_closes.iloc[day_idx - 6] - 1.0) * 100.0)
        market_regime = wfo._market_regime_bucket(spy_ret5_today)

        candidates: list[dict[str, Any]] = []
        rejects: list[dict[str, Any]] = []
        for ticker in self.symbols:
            if ticker not in self.all_closes or ticker not in self.ticker_arrays:
                rejects.append({"ticker": ticker, "reason": "missing_price_history"})
                continue
            pc = self.precomputed.get(ticker)
            t_arr = self.ticker_arrays[ticker]
            if not pc or day_idx >= len(pc):
                rejects.append({"ticker": ticker, "reason": "missing_precomputed_indicators"})
                continue
            day_data = pc[day_idx - 1]
            if day_data is None:
                rejects.append({"ticker": ticker, "reason": "missing_prior_day_indicator"})
                continue
            adv20 = float(t_arr["_adv20"][day_idx - 1]) if day_idx - 1 < len(t_arr["_adv20"]) else 0.0
            adtv20 = float(t_arr["_adtv20"][day_idx - 1]) if day_idx - 1 < len(t_arr["_adtv20"]) else 0.0
            if (
                adv20 < float(self.underlying_filters["avg_volume_20d_min"])
                or adtv20 < float(self.underlying_filters["avg_dollar_volume_20d_min"])
            ):
                rejects.append({"ticker": ticker, "reason": "underlying_liquidity"})
                continue

            t_config, t_sp = self._ticker_cfg(ticker)
            prior_close = float(t_arr["prices"][day_idx - 2]) if day_idx >= 2 else None
            signal = wfo._resolve_replay_entry_signal(day_data, self.replay_playbook, t_config, prior_close=prior_close)
            if signal is None:
                rejects.append({"ticker": ticker, "reason": "signal"})
                continue
            trade_type = str(signal["trade_type"]).lower()
            entry_filters = t_sp.get("entry_filters", {})
            if entry_filters:
                if entry_filters.get("require_bullish_regime") and market_regime != "bullish":
                    rejects.append({"ticker": ticker, "reason": "market_regime"})
                    continue
                if ticker == "QQQ":
                    if entry_filters.get("qqq_require_bullish_regime") and market_regime != "bullish":
                        rejects.append({"ticker": ticker, "reason": "qqq_market_regime"})
                        continue
                    qqq_max_hv = float(entry_filters.get("qqq_max_hv30", 999.0))
                    if float(day_data["hv30"]) > qqq_max_hv:
                        rejects.append({"ticker": ticker, "reason": "qqq_hv30"})
                        continue

            tech = wfo._tech_score(
                rsi14=day_data["rsi14"],
                macd=day_data["macd"],
                macd_prev=day_data["macd_prev"],
                price=day_data["S0"],
                sma20=day_data["sma20"],
                sma50=day_data.get("sma50", day_data["sma20"]),
                trade_type=trade_type,
            )
            if tech < float(t_config["min_tech_score"]):
                rejects.append({"ticker": ticker, "reason": "tech_score"})
                continue
            direction_score = wfo._compute_direction_score(
                tech,
                trade_type,
                day_data["rsi14"],
                day_data["ret5"],
                spy_ret5_today,
                sp=t_sp,
            )
            if signal.get("direction_score_override") is not None:
                direction_score = float(signal["direction_score_override"])
            if direction_score < float(t_config["min_confidence"]):
                rejects.append({"ticker": ticker, "reason": "direction_score"})
                continue
            quality_score = wfo._compute_quality_score(
                day_data["iv_pct"],
                t_config["delta_target"],
                t_config["dte_at_entry"],
                sp=t_sp,
            )
            p_win = float(direction_score) / 100.0
            ev = p_win * float(t_config["profit_target_pct"]) - (1.0 - p_win) * float(t_config["stop_loss_pct"])
            if ev < float(t_config["min_ev_pct"]):
                rejects.append({"ticker": ticker, "reason": "ev_floor"})
                continue
            playbook_candidate = {
                "ticker": ticker,
                "trade_type": trade_type,
                "signal_family": signal.get("signal_family"),
                "signal_variant": signal.get("signal_variant"),
                "signal_ret5": signal.get("signal_ret5", day_data["ret5"]),
                "signal_ret20": signal.get("signal_ret20", day_data.get("ret20")),
                "quality_score": quality_score,
                "tech_score": tech,
                "direction_score": direction_score,
                "hv30": day_data["hv30"],
                "spy_ret5": spy_ret5_today,
                "market_regime": market_regime,
                "sector": self.ticker_sectors.get(ticker, "Unknown"),
            }
            if not wfo._candidate_matches_replay_playbook(playbook_candidate, self.replay_playbook):
                rejects.append({"ticker": ticker, "reason": "playbook_filter"})
                continue
            entry_anchor_price = float(t_arr["opens"][day_idx])
            entry_anchor_source = "open"
            if self.truth_lane == wfo.IMPORTED_DAILY_TRUTH_SOURCE:
                entry_anchor_price = float(t_arr["prices"][day_idx - 1]) if day_idx > 0 else entry_anchor_price
                entry_anchor_source = "prior_close"
            candidates.append(
                {
                    "ticker": ticker,
                    "date": audit_date.isoformat(),
                    "day_idx": day_idx,
                    "trade_type": trade_type,
                    "direction": trade_type,
                    "type": trade_type,
                    "signal_family": signal.get("signal_family"),
                    "signal_variant": signal.get("signal_variant"),
                    "signal_ret5": signal.get("signal_ret5", day_data["ret5"]),
                    "signal_ret20": signal.get("signal_ret20", day_data.get("ret20")),
                    "signal_sma20": signal.get("signal_sma20", day_data.get("sma20")),
                    "signal_sma50": signal.get("signal_sma50", day_data.get("sma50")),
                    "ret5": round(float(day_data["ret5"]), 4),
                    "rsi14": round(float(day_data["rsi14"]), 4),
                    "direction_score": round(float(direction_score), 4),
                    "quality_score": round(float(quality_score), 4),
                    "tech_score": round(float(tech), 4),
                    "ev": round(float(ev), 4),
                    "ev_pct": round(float(ev), 4),
                    "sector": self.ticker_sectors.get(ticker, "Unknown"),
                    "spy_ret5": round(float(spy_ret5_today), 4),
                    "market_regime": market_regime,
                    "selection_source": "bootstrap_heuristic",
                    "hv30": round(float(day_data["hv30"]), 4),
                    "iv_pct": round(float(day_data["iv_pct"]), 4),
                    "stock_price": round(float(entry_anchor_price), 4),
                    "underlying_price_at_selection": round(float(entry_anchor_price), 4),
                    "entry_anchor_source": entry_anchor_source,
                    "avg_volume_20d": round(float(adv20), 0),
                    "avg_dollar_volume_20d": round(float(adtv20), 2),
                    "_p_config": t_config,
                }
            )
        return candidates, rejects

    def exact_spread_pick(self, candidate: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
        ticker = str(candidate.get("ticker") or "").upper()
        entry_date = _parse_date(str(candidate["date"]))
        if entry_date.isoformat() not in self._available_quote_dates(ticker):
            return None, "no_exact_option_quotes_for_date"

        p_config = dict(candidate.get("_p_config") or self._ticker_cfg(ticker)[0])
        selected = wfo._select_chain_native_spread(
            store=self.store,
            ticker=ticker,
            entry_date=entry_date,
            trade_type=str(candidate.get("trade_type") or "call"),
            S0=float(candidate["underlying_price_at_selection"]),
            hv30=float(candidate.get("hv30") or 0.0),
            long_delta_target=float(p_config.get("spread_long_delta", 0.50)),
            short_delta_target=float(p_config.get("spread_short_delta", 0.20)),
            target_dte=int(p_config["dte_at_entry"]),
            min_dte=int(p_config.get("chain_native_min_dte") or max(1, int(p_config["dte_at_entry"]) - 7)),
            max_dte=int(p_config.get("chain_native_max_dte") or int(p_config["dte_at_entry"]) + 10),
            max_width_pct=float(p_config.get("spread_max_width_pct", 5.0)),
            max_debit_pct_of_width=self.replay_playbook.get("max_debit_pct_of_width"),
            iv_adj=1.20,
            requested_pricing_lane=wfo._normalize_requested_pricing_lane(self.pricing_lane),
            entry_slippage_pct=float(p_config.get("entry_slippage_pct", 0.0) or 0.0),
            snapshot_kind=self.snapshot_kind,
            entry_quote_minute_et=self.entry_quote_minute_et,
            entry_window_minutes=self.entry_window_minutes,
            source_labels=self.source_labels,
            trusted_only=self.trusted_only,
            min_prior_quote_days=int(p_config.get("chain_native_min_prior_quote_days", 0) or 0),
            prior_quote_lookback_days=int(p_config.get("chain_native_prior_quote_lookback_days", 14) or 14),
            min_long_prior_quote_days=p_config.get("chain_native_min_long_prior_quote_days"),
            min_short_prior_quote_days=p_config.get("chain_native_min_short_prior_quote_days"),
            prior_quote_score_weight=float(p_config.get("chain_native_prior_quote_score_weight", 0.0) or 0.0),
            long_prior_quote_score_weight=p_config.get("chain_native_long_prior_quote_score_weight"),
            short_prior_quote_score_weight=p_config.get("chain_native_short_prior_quote_score_weight"),
            prior_quote_score_cap=int(p_config.get("chain_native_prior_quote_score_cap", 0) or 0),
            max_entry_leg_bid_ask_pct=p_config.get("chain_native_max_entry_leg_bid_ask_pct"),
            min_entry_short_bid=p_config.get("chain_native_min_entry_short_bid"),
            short_inside_steps=int(p_config.get("chain_native_short_inside_steps", 0) or 0),
            short_inside_require_debit_cap=bool(p_config.get("chain_native_short_inside_require_debit_cap", True)),
        )
        if selected is None:
            return None, "no_chain_native_spread_passed_current_filters"

        long_quote, short_quote, net_debit, spread_width, long_delta, short_delta = selected
        expiry = _parse_date(long_quote.expiry)
        actual_dte = max((expiry - entry_date).days, 1)
        spread_mid_debit = None
        long_mid = _quote_mid(long_quote.bid, long_quote.ask)
        short_mid = _quote_mid(short_quote.bid, short_quote.ask)
        if long_mid is not None and short_mid is not None:
            spread_mid_debit = round(long_mid - short_mid, 4)
        debit_pct = round(float(net_debit) / max(float(spread_width), 0.01) * 100.0, 4)
        quote_dt = _entry_dt(entry_date, int(long_quote.quote_minute_et or self.entry_quote_minute_et))
        fill_basis = "spread_ask_bid" if self.pricing_lane == "pessimistic" else f"historical_spread_{self.pricing_lane}"
        pick = {
            **{key: value for key, value in candidate.items() if not key.startswith("_")},
            "strategy_type": "vertical_spread",
            "option_type": str(candidate.get("trade_type") or "call"),
            "contract_symbol": long_quote.contract_symbol,
            "short_contract_symbol": short_quote.contract_symbol,
            "strike": round(float(long_quote.strike), 4),
            "short_strike": round(float(short_quote.strike), 4),
            "long_strike": round(float(long_quote.strike), 4),
            "expiry": expiry.isoformat(),
            "original_logged_expiry": expiry.isoformat(),
            "resolved_listed_expiry": expiry.isoformat(),
            "target_expiry": (entry_date + timedelta(days=int(p_config["dte_at_entry"]))).isoformat(),
            "dte": actual_dte,
            "spread_width": round(float(spread_width), 4),
            "net_debit": round(float(net_debit), 4),
            "entry_execution_price": round(float(net_debit), 4),
            "entry_execution_basis": fill_basis,
            "entry_fee_total_usd": 1.30,
            "max_profit": round(float(spread_width) - float(net_debit), 4),
            "max_loss": round(float(net_debit), 4),
            "risk_reward_ratio": round((float(spread_width) - float(net_debit)) / max(float(net_debit), 0.01), 4),
            "debit_pct_of_width": debit_pct,
            "spread_entry_debit": round(float(net_debit), 4),
            "spread_bid_ask_pct_of_mid": None,
            "spread_liquidity": {
                "spread_mid_debit": spread_mid_debit,
                "spread_entry_debit": round(float(net_debit), 4),
                "long_bid": long_quote.bid,
                "long_ask": long_quote.ask,
                "short_bid": short_quote.bid,
                "short_ask": short_quote.ask,
                "long_delta": round(float(long_delta), 4),
                "short_delta": round(float(short_delta), 4),
            },
            "delta": round(float(long_delta), 4),
            "short_delta": round(float(short_delta), 4),
            "delta_est": round(float(long_delta), 4),
            "bid": long_quote.bid,
            "ask": long_quote.ask,
            "last": long_quote.last,
            "mid": long_mid,
            "short_bid": short_quote.bid,
            "short_ask": short_quote.ask,
            "short_last": short_quote.last,
            "quote_time_et": quote_dt.isoformat(),
            "quote_time_utc": quote_dt.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "quote_timestamp_et": quote_dt.isoformat(),
            "quote_timestamp_utc": quote_dt.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "quote_timestamp_source": "historical_options_store",
            "quote_basis": "historical_bid_ask",
            "market_data_source": "historical_replay",
            "underlying_data_source": "yfinance_historical_daily",
            "options_data_source": ",".join(self.source_labels) or self.snapshot_kind,
            "quote_source": ",".join(self.source_labels) or self.snapshot_kind,
            "quote_freshness_status": "observed",
            "selection_source": "historical_chain_native_exact_contract",
            "contract_selection_source": "chain_native_listed_spread",
            "promotion_class": "research_backfill_exact_contract",
            "candidate_execution_label": "historical_exact_backfill_candidate",
            "pricing_evidence_class": "research_backfill",
            "profitability_evidence_class": "research_backfill",
            "source_separation": "historical_selection_not_live_production",
            "playbook_id": self.playbook_id,
            "playbook_label": self.scan_playbook.get("label") or self.replay_playbook.get("label"),
            "cohort_id": self.scan_playbook.get("forced_cohort_id") or self.playbook_id,
            "cohort_role": self.scan_playbook.get("forced_cohort_role") or "primary",
            "truth_lane": self.truth_lane,
            "policy_applied": False,
            "stop_loss_pct": p_config.get("spread_stop_loss_pct", p_config.get("stop_loss_pct")),
            "profit_target_pct": p_config.get("spread_profit_target_pct", p_config.get("profit_target_pct")),
            "time_exit_pct": p_config.get("spread_time_exit_pct", p_config.get("time_exit_pct")),
            "time_exit_day": max(1, round(actual_dte * float(p_config.get("spread_time_exit_pct", 65.0)) / 100.0)),
            "long_leg": _leg_snapshot(long_quote, "long"),
            "short_leg": _leg_snapshot(short_quote, "short"),
            "legs": [_leg_snapshot(long_quote, "long"), _leg_snapshot(short_quote, "short")],
            "backfill_audit_id": self.audit_id,
        }
        pick["backfill_signature"] = _pick_signature(pick)
        return pick, None


def _pick_signature(pick: dict[str, Any]) -> str:
    return "|".join(
        [
            _date_text(pick.get("scan_date") or pick.get("date") or pick.get("quote_time_et")),
            str(pick.get("playbook_id") or DEFAULT_SCAN_PLAYBOOK_ID),
            str(pick.get("ticker") or "").upper(),
            str(pick.get("direction") or pick.get("type") or "").lower(),
            str(pick.get("contract_symbol") or "").upper(),
            str(pick.get("short_contract_symbol") or "").upper(),
        ]
    )


def _existing_backfill_signatures() -> set[str]:
    signatures: set[str] = set()
    for row in [*_jsonl_rows(SCAN_LOG), *_jsonl_rows(FILL_ATTEMPT_LOG)]:
        explicit = str(row.get("backfill_signature") or "").strip()
        if explicit:
            signatures.add(explicit)
            continue
        if row.get("contract_symbol"):
            signatures.add(_pick_signature(row))
    return signatures


def _existing_ledger_run_ids(playbook_id: str) -> set[str]:
    if not FORWARD_LEDGER_DB.exists():
        return set()
    with sqlite3.connect(FORWARD_LEDGER_DB) as conn:
        rows = conn.execute(
            """
            SELECT run_id
            FROM forward_sessions
            WHERE COALESCE(source_label, '') = 'research_backfill'
              AND COALESCE(playbook, '') = ?
            """,
            (playbook_id,),
        ).fetchall()
    return {str(row[0]) for row in rows if row and row[0]}


def _research_backfill_run_id(*, audit_id: str, playbook_id: str, scan_date: date) -> str:
    if audit_id == AUDIT_ID and playbook_id == DEFAULT_SCAN_PLAYBOOK_ID:
        return f"{audit_id}:{scan_date.isoformat()}"
    return f"{audit_id}:{playbook_id}:{scan_date.isoformat()}"


def _log_records_for_pick(
    *,
    pick: dict[str, Any],
    run_at: datetime,
    scan_result: dict[str, Any],
    rank: int,
    reasons: list[str],
    audit_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    scan_record = log_scan_picks._build_log_record(pick, run_at=run_at, scan_result=scan_result)
    scan_record.update(
        {
            "event_type": "historical_backfill_scan_pick",
            "status": "backfilled",
            "scan_date": run_at.strftime("%Y-%m-%d"),
            "candidate_rank": rank,
            "backfill_audit_id": audit_id,
            "backfill_signature": _pick_signature(pick),
            "backfill_scope_reasons": list(reasons),
            "research_only": True,
            "non_promotable": True,
            "production_filter_action": "research_backfill_not_live_production",
        }
    )
    fill_record = log_scan_picks._build_fill_attempt_record(
        pick,
        run_at=run_at,
        scan_result=scan_result,
        candidate_rank=rank,
    )
    fill_record.update(
        {
            "event_type": "historical_backfill_candidate_shown",
            "status": "backfilled",
            "fill_status": "backfilled_historical_track",
            "fill_outcome": "paper_fill_recorded",
            "fill_outcome_reason": "zero_pick_current_algorithm_research_backfill",
            "filled": True,
            "filled_price": pick.get("entry_execution_price") or pick.get("net_debit"),
            "filled_at": run_at.isoformat(),
            "auto_track_position_id": None,
            "review_status": "research_backfill",
            "backfill_audit_id": audit_id,
            "backfill_signature": _pick_signature(pick),
            "backfill_scope_reasons": list(reasons),
            "research_only": True,
            "non_promotable": True,
        }
    )
    return scan_record, fill_record


def _record_research_ledger_session(
    *,
    scan_date: date,
    picks: list[dict[str, Any]],
    scan_result: dict[str, Any],
    reasons: list[str],
    dry_run: bool,
    audit_id: str,
    playbook_id: str,
) -> dict[str, Any] | None:
    run_id = _research_backfill_run_id(audit_id=audit_id, playbook_id=playbook_id, scan_date=scan_date)
    if dry_run:
        return {"run_id": run_id, "status": "dry_run"}
    if run_id in _existing_ledger_run_ids(playbook_id):
        return {"run_id": run_id, "status": "duplicate_skipped"}
    snapshot = build_forward_scan_snapshot(
        picks=picks,
        candidate_audit_picks=list(scan_result.get("candidate_audit_picks") or []),
        policy_applied=False,
        policy={"truth_source": scan_result.get("truth_lane"), "promotion_status": "research_backfill"},
        playbook=scan_result.get("playbook"),
        truth_lane=scan_result.get("truth_lane"),
        scan_funnel=scan_result.get("scan_funnel"),
        candidate_count=scan_result.get("candidate_count"),
        returned_count=len(picks),
        cohort_funnels={
            str((scan_result.get("playbook") or {}).get("forced_cohort_id") or playbook_id): scan_result.get("scan_funnel")
        },
        cohort_ids=[str((scan_result.get("playbook") or {}).get("forced_cohort_id") or playbook_id)],
        run_id=run_id,
        run_mode="zero_pick_current_algorithm_backfill",
        evidence_class="research_backfill",
        is_fixture=False,
        policy_artifact_id=audit_id,
        quote_freshness_status="observed",
        symbol_diagnostics={"backfill_scope_reasons": reasons},
    )
    pseudo_positions = [
        {
            "id": f"research_backfill:{_pick_signature(pick)}",
            "status": "research_backfill",
            "ticker": pick.get("ticker"),
            "direction": pick.get("direction"),
            "contract_symbol": pick.get("contract_symbol"),
            "expiry": pick.get("expiry"),
            "strike": pick.get("strike"),
            "source_pick_snapshot": pick,
        }
        for pick in picks
    ]
    return record_forward_snapshot(
        scan_snapshot=snapshot,
        reviewed_positions=[],
        tracked_positions=pseudo_positions,
        source_label="research_backfill",
    )


def build_audit(args: argparse.Namespace) -> dict[str, Any]:
    load_local_env(ROOT)
    playbook_id = str(args.playbook or "").strip().lower()
    audit_id = str(getattr(args, "audit_id", None) or AUDIT_ID)
    historical_options_db = Path(str(args.historical_options_db)).expanduser()
    if historical_options_db:
        os.environ["HISTORICAL_OPTIONS_DB_PATH"] = str(historical_options_db)
    source_labels = [
        item.strip()
        for item in str(args.source_labels or "").replace(";", ",").split(",")
        if item.strip()
    ]
    audit_dates, reasons_by_date, discovery = _discover_audit_dates(
        playbook_id=playbook_id,
        date_from=_parse_date(args.date_from) if args.date_from else None,
        date_to=_parse_date(args.date_to) if args.date_to else None,
        scope=args.scope,
    )
    engine = CurrentMainLaneReplay(
        playbook_id=playbook_id,
        truth_lane=args.truth_lane,
        pricing_lane=args.pricing_lane,
        source_labels=source_labels,
        trusted_only=not bool(args.allow_research_data),
        lookback_years=int(args.lookback_years),
        audit_id=audit_id,
    )
    engine.load()

    existing_signatures = _existing_backfill_signatures()
    scan_rows_to_append: list[dict[str, Any]] = []
    fill_rows_to_append: list[dict[str, Any]] = []
    ledger_results: list[dict[str, Any]] = []
    per_date: list[dict[str, Any]] = []
    duplicate_count = 0
    selected_total = 0
    signal_total = 0
    exact_total = 0
    no_exact_counter: Counter[str] = Counter()
    reject_counter: Counter[str] = Counter()

    for audit_date in audit_dates:
        reasons = reasons_by_date.get(audit_date.isoformat(), [])
        signal_candidates, signal_rejects = engine.signal_candidates_for_date(audit_date)
        signal_total += len(signal_candidates)
        reject_counter.update(str(item.get("reason") or "unknown") for item in signal_rejects)
        exact_candidates: list[dict[str, Any]] = []
        exact_rejects: list[dict[str, Any]] = []
        for candidate in signal_candidates:
            exact_pick, exact_reason = engine.exact_spread_pick(candidate)
            if exact_pick is None:
                reason = exact_reason or "exact_spread_unknown"
                exact_rejects.append({"ticker": candidate.get("ticker"), "reason": reason})
                no_exact_counter[reason] += 1
                continue
            exact_candidates.append(exact_pick)
        exact_total += len(exact_candidates)
        selected = wfo._pick_top_n_daily(exact_candidates, int(args.n_picks)) if exact_candidates else []
        for idx, pick in enumerate(selected, start=1):
            pick["candidate_rank"] = idx
            pick["scan_date"] = audit_date.isoformat()
            pick["backfill_scope_reasons"] = list(reasons)
            pick["backfill_signature"] = _pick_signature(pick)

        scan_result = {
            "picks": selected,
            "candidate_audit_picks": exact_candidates,
            "playbook": engine.scan_playbook,
            "truth_lane": args.truth_lane,
            "policy_applied": False,
            "candidate_count": len(signal_candidates),
            "returned_count": len(selected),
            "scan_funnel": {
                "raw_candidates": len(signal_candidates),
                "post_policy_visible": len(signal_candidates),
                "post_guardrails_visible": len(exact_candidates),
                "returned_picks": len(selected),
                "policy_filtered_out": 0,
                "guardrail_filtered_out": max(len(signal_candidates) - len(exact_candidates), 0),
                "final_trimmed": max(len(exact_candidates) - len(selected), 0),
                "policy_counts": {},
                "guardrail_counts": {"clear": len(exact_candidates), "blocked": max(len(signal_candidates) - len(exact_candidates), 0)},
                "drop_counts": dict(Counter(str(item.get("reason") or "unknown") for item in signal_rejects)),
            },
        }

        selected_for_logs: list[dict[str, Any]] = []
        for rank, pick in enumerate(selected, start=1):
            signature = _pick_signature(pick)
            if signature in existing_signatures:
                duplicate_count += 1
                continue
            run_at = _entry_dt(audit_date, engine.entry_quote_minute_et)
            scan_row, fill_row = _log_records_for_pick(
                pick=pick,
                run_at=run_at,
                scan_result=scan_result,
                rank=rank,
                reasons=reasons,
                audit_id=audit_id,
            )
            scan_rows_to_append.append(scan_row)
            fill_rows_to_append.append(fill_row)
            existing_signatures.add(signature)
            selected_for_logs.append(pick)
        selected_total += len(selected_for_logs)

        if selected_for_logs:
            ledger_result = _record_research_ledger_session(
                scan_date=audit_date,
                picks=selected_for_logs,
                scan_result=scan_result,
                reasons=reasons,
                dry_run=not bool(args.apply),
                audit_id=audit_id,
                playbook_id=playbook_id,
            )
            if ledger_result:
                ledger_results.append(ledger_result)

        per_date.append(
            {
                "scan_date": audit_date.isoformat(),
                "scope_reasons": reasons,
                "signal_candidate_count": len(signal_candidates),
                "exact_candidate_count": len(exact_candidates),
                "selected_count": len(selected),
                "newly_tracked_count": len(selected_for_logs),
                "duplicate_count": len(selected) - len(selected_for_logs),
                "selected": [
                    {
                        "ticker": pick.get("ticker"),
                        "direction": pick.get("direction"),
                        "contract_symbol": pick.get("contract_symbol"),
                        "short_contract_symbol": pick.get("short_contract_symbol"),
                        "expiry": pick.get("expiry"),
                        "strike": pick.get("strike"),
                        "short_strike": pick.get("short_strike"),
                        "net_debit": pick.get("net_debit"),
                        "dte": pick.get("dte"),
                    }
                    for pick in selected
                ],
                "exact_reject_reasons": dict(Counter(str(item.get("reason") or "unknown") for item in exact_rejects)),
                "top_signal_tickers": [str(item.get("ticker") or "") for item in sorted(signal_candidates, key=wfo._candidate_rank_tuple, reverse=True)[:10]],
            }
        )

    if args.apply:
        _append_jsonl(SCAN_LOG, scan_rows_to_append)
        _append_jsonl(FILL_ATTEMPT_LOG, fill_rows_to_append)

    summary = {
        "audit_id": audit_id,
        "playbook": playbook_id,
        "apply": bool(args.apply),
        "date_count": len(audit_dates),
        "signal_candidate_count": signal_total,
        "exact_candidate_count": exact_total,
        "newly_tracked_pick_count": selected_total if args.apply else 0,
        "would_track_pick_count": selected_total,
        "duplicate_pick_count": duplicate_count,
        "scan_rows_appended": len(scan_rows_to_append) if args.apply else 0,
        "fill_attempt_rows_appended": len(fill_rows_to_append) if args.apply else 0,
        "ledger_sessions_recorded": sum(1 for item in ledger_results if item.get("session_id") is not None),
        "no_exact_reason_counts": dict(no_exact_counter),
        "signal_reject_reason_counts": dict(reject_counter),
    }
    return {
        "generated_at_utc": _utc_now_iso(),
        "summary": summary,
        "parameters": {
            "playbook": playbook_id,
            "scope": args.scope,
            "truth_lane": args.truth_lane,
            "pricing_lane": args.pricing_lane,
            "source_labels": source_labels,
            "trusted_only": not bool(args.allow_research_data),
            "n_picks": int(args.n_picks),
            "lookback_years": int(args.lookback_years),
            "historical_options_db": str(historical_options_db),
            "replay_adapter": engine.replay_adapter_info,
        },
        "discovery": discovery,
        "ledger_results": ledger_results,
        "dates": per_date,
    }


def write_report(audit: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"main_lane_zero_pick_current_algo_audit_{stamp}.json"
    latest = output_dir / "main_lane_zero_pick_current_algo_audit_latest.json"
    payload = json.dumps(audit, indent=2, sort_keys=True)
    path.write_text(payload, encoding="utf-8")
    latest.write_text(payload, encoding="utf-8")
    return path, latest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit zero-pick days against one explicitly selected scan lane.")
    parser.add_argument("--playbook", default=DEFAULT_SCAN_PLAYBOOK_ID)
    parser.add_argument("--scope", choices=["zero_any", "main_zero", "zero_any_or_main_zero"], default="zero_any_or_main_zero")
    parser.add_argument("--date-from")
    parser.add_argument("--date-to")
    parser.add_argument("--truth-lane", choices=[wfo.IMPORTED_TRUTH_SOURCE, wfo.IMPORTED_DAILY_TRUTH_SOURCE], default=wfo.IMPORTED_TRUTH_SOURCE)
    parser.add_argument("--pricing-lane", default="pessimistic")
    parser.add_argument("--source-labels", default="thetadata_opra_nbbo_1m")
    parser.add_argument("--historical-options-db", default=str(HISTORICAL_OPTIONS_DB))
    parser.add_argument("--allow-research-data", action="store_true")
    parser.add_argument("--lookback-years", type=int, default=2)
    parser.add_argument("--n-picks", type=int, default=10)
    parser.add_argument("--audit-id", default=AUDIT_ID)
    parser.add_argument("--apply", action="store_true", help="Append backfilled tracking rows and research-backfill ledger sessions.")
    parser.add_argument("--no-write-report", action="store_true")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args(argv)

    audit = build_audit(args)
    if not args.no_write_report:
        path, latest = write_report(audit, Path(args.output_dir))
        print(f"Wrote audit report: {path}")
        print(f"Wrote latest audit report: {latest}")

    summary = audit["summary"]
    print(
        "Zero-pick current-algo audit: "
        f"dates={summary['date_count']} "
        f"signals={summary['signal_candidate_count']} "
        f"exact={summary['exact_candidate_count']} "
        f"would_track={summary['would_track_pick_count']} "
        f"tracked={summary['newly_tracked_pick_count']} "
        f"duplicates={summary['duplicate_pick_count']}"
    )
    if summary.get("no_exact_reason_counts"):
        print(f"No-exact reasons: {summary['no_exact_reason_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
