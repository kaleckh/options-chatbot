#!/usr/bin/env
#  python3
"""
Options Trading Chatbot
Powered by Claude Sonnet 4.6 + Yahoo Finance (yfinance)

Specializes in:
- US large-cap stocks and ETFs with high options liquidity
- Single-leg positions: long/short calls and puts
- Short DTE: 0–21 days to expiration

Free enhancements:
- IV Analysis: HV30, HV Rank, IV vs HV comparison
- Earnings calendar: warns when earnings fall within your DTE
- Market context: VIX level, SPY/QQQ trend, market regime
- Put/Call ratio: directional sentiment from live options flow
- Paper trading journal: log trades and track real P&L
- Strategy backtester: simulate how a strategy would have performed historically
- Daily predictions tracker: log directional calls, auto-grade them, track accuracy over time
"""

import os
import re
import json
import math
import glob
import shutil
import subprocess
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf

RISK_FREE_RATE = 0.045  # 4.5% — approximate 3-month T-bill. Update periodically.

DEFAULT_WATCHLIST = [
    "SPY", "QQQ", "AAPL", "NVDA", "TSLA", "MSFT", "META", "AMZN",
    "GOOGL", "AMD", "NFLX", "COIN", "PLTR", "ARM", "SMCI", "MSTR",
    "JPM", "BAC", "XOM", "V", "DIS", "UBER", "BABA", "RIVN",
]

# High-beta names most likely to make the big % moves needed for 2x options gains
HIGH_BETA_WATCHLIST = [
    "NVDA", "TSLA", "AMD", "COIN", "PLTR", "MSTR", "ARM", "SMCI",
    "RIVN", "BABA", "NFLX", "META", "GOOGL", "AMZN", "AAPL", "MSFT",
]

# ─── Risk settings (user can update account_size mid-conversation) ────────────
# Claude will read/write these via the manage_risk_settings tool.
# risk_settings is a live alias for STRATEGY_PROFILE["risk"] — defined after STRATEGY_PROFILE below

PAPER_TRADES_FILE   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trades.json")
PREDICTIONS_FILE    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "predictions.json")

# ─── Strategy Profile ─────────────────────────────────────────────────────────
# This is the canonical strategy definition for the entire system.
# All tools, the chatbot, and the backtest reference these values.
STRATEGY_PROFILE = {
    "name": "OTM Short-Duration Momentum Strategy",
    "philosophy": (
        "Buy OTM calls or puts on high-conviction momentum signals with strict entry filters. "
        "Entry is gated by signal quality, volatility regime, and liquidity. "
        "Position size scales with conviction. Exit rules are fixed and non-negotiable."
    ),
    # Confidence score weights (normalized automatically — optimizer tunes all 4)
    "confidence_weights": {
        "iv_percentile": 0.40,   # IV rank/percentile of the option being purchased
        "delta":         0.30,   # distance from optimal delta (0.30)
        "dte":           0.20,   # distance from optimal DTE (10 days)
        "technical":     0.10,   # RSI + MACD + SMA trend alignment
    },
    # Optimal parameter targets
    "targets": {
        "delta_optimal":      0.30,   # sweet spot for OTM leverage
        "delta_falloff":      0.20,   # score = 0 when |delta - optimal| >= this
        "dte_optimal":        10,     # sweet spot (days)
        "dte_falloff":        20,     # score = 0 when |dte - optimal| >= this
        "iv_percentile_max":  50,     # prefer buying when IV rank < 50th percentile
    },
    # Entry filters
    "filters": {
        "vix_defense_threshold":       25.0,   # VIX above this → Defense Mode
        "atr_expansion_stop_mult":      1.5,   # widen stop-loss when ATR is expanding
        "defense_position_mult":        0.5,   # position size in Defense Mode
        "liquidity_spread_max_pct":     1.5,   # flag as illiquid above this bid-ask spread %
        "illiquid_extra_margin_pct":   10.0,   # extra required profit margin if illiquid
        "iv_crush_z_threshold":         2.0,   # z-scores above 30-day HV mean → IV crush risk
        "iv_crush_confidence_penalty": 20.0,   # subtract this from confidence score
        "min_ev_return_pct":           10.0,   # EV must be ≥ 10% ROC to emit trade signal
    },
    # Exit & position rules (single source of truth — risk_settings is an alias of this)
    "risk": {
        "stop_loss_pct":        50.0,   # exit when option loses this % of premium
        "profit_target_pct":   100.0,   # take profit when option gains this %
        "max_position_pct":    40.0,    # ceiling: highest risk % (confidence=10)
        "min_position_pct":     7.0,    # floor: lowest risk % (confidence=1)
        "account_size":        None,    # set by user via manage_risk_settings
        "max_drawdown_pct":    15.0,    # pause trading after this % portfolio drawdown
        "dte_0_max_pct":        2.0,    # 0DTE trades capped at this % of account
    },
}

# ── Persist / restore STRATEGY_PROFILE across restarts ───────────────────────
PROFILE_FILE    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "strategy_profile.json")
CHANGELOG_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_changelog.json")


def _log_brain_update(source: str, note: str) -> None:
    """Append one timestamped entry to brain_changelog.json."""
    from datetime import timezone
    entry = {
        "ts":     datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source,
        "note":   note,
    }
    try:
        if os.path.exists(CHANGELOG_FILE):
            with open(CHANGELOG_FILE) as f:
                log = json.load(f)
        else:
            log = []
        log.append(entry)
        with open(CHANGELOG_FILE, "w") as f:
            json.dump(log, f, indent=2)
    except Exception:
        pass  # never crash the caller over a changelog write


def _save_profile(note: str = "") -> None:
    """Write STRATEGY_PROFILE to disk. Call after every Apply."""
    with open(PROFILE_FILE, "w") as f:
        json.dump(
            {k: v for k, v in STRATEGY_PROFILE.items() if k not in ("name", "philosophy")},
            f, indent=2,
        )
    _log_brain_update(source="apply", note=note or "Strategy profile updated")


def _load_profile() -> None:
    """Merge saved profile into STRATEGY_PROFILE in-place (runs at import time)."""
    if not os.path.exists(PROFILE_FILE):
        return
    try:
        with open(PROFILE_FILE) as f:
            saved = json.load(f)
        for section in ("confidence_weights", "targets", "filters", "risk"):
            if section in saved and isinstance(saved[section], dict):
                STRATEGY_PROFILE[section].update(saved[section])
    except Exception:
        pass  # corrupt file — fall back to defaults silently


_load_profile()  # restore on every import / app startup

# ── Live alias so all legacy code that reads risk_settings["x"] auto-reflects changes ──
risk_settings = STRATEGY_PROFILE["risk"]


# ─── Black-Scholes Greeks ──────────────────────────────────────────────────────

def _norm_pdf(x: float) -> float:
    return math.exp(-x * x / 2.0) / math.sqrt(2.0 * math.pi)


def _norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _bs_greeks(S, K, T, r, sigma, option_type) -> dict:
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return {}
    try:
        sqrtT = math.sqrt(T)
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrtT)
        d2 = d1 - sigma * sqrtT
        nd1, nd2 = _norm_cdf(d1), _norm_cdf(d2)
        pdf_d1 = _norm_pdf(d1)
        disc = math.exp(-r * T)

        if option_type == "call":
            price = S * nd1 - K * disc * nd2
            delta = nd1
        else:
            price = K * disc * _norm_cdf(-d2) - S * _norm_cdf(-d1)
            delta = nd1 - 1.0

        gamma = pdf_d1 / (S * sigma * sqrtT)
        theta_call = (-S * pdf_d1 * sigma / (2.0 * sqrtT) - r * K * disc * nd2) / 365.0
        theta_put  = (-S * pdf_d1 * sigma / (2.0 * sqrtT) + r * K * disc * _norm_cdf(-d2)) / 365.0
        theta = theta_call if option_type == "call" else theta_put
        vega = S * sqrtT * pdf_d1 / 100.0

        return {
            "bs_price": round(price, 4),
            "delta":    round(delta, 4),
            "gamma":    round(gamma, 6),
            "theta":    round(theta, 4),   # $ per calendar day
            "vega":     round(vega, 4),    # $ per 1% IV move
        }
    except (ValueError, ZeroDivisionError, OverflowError):
        return {}


def _enrich_row(row, S, option_type, exp_str, today) -> dict:
    exp_dt = datetime.strptime(exp_str, "%Y-%m-%d")
    dte = max((exp_dt - today).days, 0)
    T = dte / 365.0
    iv   = row.get("impliedVolatility") or 0.0
    K    = row.get("strike") or 0.0
    vol  = int(row.get("volume") or 0)
    oi   = int(row.get("openInterest") or 0)
    bid  = row.get("bid") or 0.0
    ask  = row.get("ask") or 0.0
    last = row.get("lastPrice") or 0.0
    mid  = round((bid + ask) / 2, 2) if bid and ask else last

    greeks = _bs_greeks(S, K, T, RISK_FREE_RATE, iv, option_type) if iv and T > 0 else {}
    break_even = round(K + mid, 2) if option_type == "call" and mid else (round(K - mid, 2) if mid else None)

    return {
        "type": option_type,
        "strike": K,
        "expiration": exp_str,
        "dte": dte,
        "last": last,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "volume": vol,
        "open_interest": oi,
        "vol_oi_ratio": round(vol / oi, 2) if oi else None,
        "iv_pct": round(iv * 100, 1),
        "in_the_money": bool(row.get("inTheMoney")),
        "break_even": break_even,
        "underlying_price": S,
        **greeks,
    }


def _get_price(ticker_obj) -> float:
    hist = ticker_obj.history(period="1d", interval="5m")
    if not hist.empty:
        return float(hist["Close"].iloc[-1])
    return float((ticker_obj.info or {}).get("currentPrice") or (ticker_obj.info or {}).get("regularMarketPrice") or 0)


# ─── Tool 1: Stock snapshot ────────────────────────────────────────────────────

def get_stock_snapshot(symbol: str) -> str:
    try:
        t = yf.Ticker(symbol.upper())
        hist = t.history(period="5d", interval="5m")
        info = t.info or {}

        if not hist.empty:
            last      = float(hist["Close"].iloc[-1])
            day_open  = float(hist["Open"].resample("D").first().iloc[-1])
            day_high  = float(hist["High"].resample("D").max().iloc[-1])
            day_low   = float(hist["Low"].resample("D").min().iloc[-1])
            day_vol   = int(hist["Volume"].resample("D").sum().iloc[-1])
        else:
            last     = info.get("currentPrice") or info.get("regularMarketPrice") or 0
            day_open = info.get("regularMarketOpen")
            day_high = info.get("dayHigh")
            day_low  = info.get("dayLow")
            day_vol  = info.get("regularMarketVolume")

        prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
        change_pct = round((last / prev_close - 1) * 100, 2) if last and prev_close else None

        return json.dumps({
            "symbol": symbol.upper(),
            "last_price": round(last, 2),
            "open": round(day_open, 2) if day_open else None,
            "high": round(day_high, 2) if day_high else None,
            "low":  round(day_low,  2) if day_low  else None,
            "volume": day_vol,
            "prev_close": round(prev_close, 2) if prev_close else None,
            "change_pct": change_pct,
            "market_cap": info.get("marketCap"),
            "sector": info.get("sector"),
            "source": "Yahoo Finance (~15-min delayed)",
        })
    except Exception as e:
        return json.dumps({"error": str(e), "symbol": symbol.upper()})


# ─── Tool 2: Options chain ─────────────────────────────────────────────────────

def get_options_chain(symbol: str, option_type: str = None,
                      max_dte: int = 21, expiration_date: str = None) -> str:
    try:
        today = datetime.now()
        t = yf.Ticker(symbol.upper())
        all_exps = t.options

        if expiration_date:
            target_exps = [expiration_date] if expiration_date in all_exps else []
        else:
            target_exps = [e for e in all_exps
                           if 0 <= (datetime.strptime(e, "%Y-%m-%d") - today).days <= max_dte]

        if not target_exps:
            return json.dumps({"error": f"No expirations within {max_dte} DTE",
                               "available": list(all_exps[:10])})

        S = _get_price(t)
        options = []
        for exp in target_exps:
            chain = t.option_chain(exp)
            frames = []
            if option_type != "put":  frames.append(("call", chain.calls))
            if option_type != "call": frames.append(("put",  chain.puts))
            for otype, df in frames:
                for _, row in df.iterrows():
                    options.append(_enrich_row(row.to_dict(), S, otype, exp, today))

        options.sort(key=lambda x: x.get("volume") or 0, reverse=True)
        return json.dumps({
            "symbol": symbol.upper(),
            "underlying_price": round(S, 2),
            "expirations_fetched": target_exps,
            "contracts_found": len(options),
            "top_40_by_volume": options[:40],
            "greeks_method": "Black-Scholes",
        }, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


# ─── Tool 3: Multi-ticker screener ────────────────────────────────────────────

def screen_options(symbols: list, option_type: str = "both",
                   max_dte: int = 21, min_volume: int = 100) -> str:
    if isinstance(symbols, str):
        symbols = [symbols]
    today = datetime.now()
    all_opts = []

    for sym in symbols[:6]:
        try:
            t = yf.Ticker(sym.upper())
            target_exps = [e for e in t.options
                           if 0 <= (datetime.strptime(e, "%Y-%m-%d") - today).days <= max_dte]
            if not target_exps:
                continue
            S = _get_price(t)
            for exp in target_exps:
                chain = t.option_chain(exp)
                frames = []
                if option_type != "put":  frames.append(("call", chain.calls))
                if option_type != "call": frames.append(("put",  chain.puts))
                for otype, df in frames:
                    for _, row in df.iterrows():
                        if (row.get("volume") or 0) < min_volume:
                            continue
                        enriched = _enrich_row(row.to_dict(), S, otype, exp, today)
                        enriched["symbol"] = sym.upper()
                        all_opts.append(enriched)
        except Exception:
            continue

    all_opts.sort(key=lambda x: x.get("volume") or 0, reverse=True)
    return json.dumps({
        "tickers_screened": [s.upper() for s in symbols],
        "filters": {"option_type": option_type, "max_dte": max_dte, "min_volume": min_volume},
        "total_qualifying": len(all_opts),
        "top_35_by_volume": all_opts[:35],
        "greeks_method": "Black-Scholes",
    }, indent=2, default=str)


# ─── Tool 4: High-leverage / 2x screener ─────────────────────────────────────

def find_high_leverage_options(
    symbols: list = None,
    option_type: str = "both",
    max_dte: int = 14,
    min_volume: int = 50,
    max_move_needed_pct: float = 12.0,
) -> str:
    """
    Screens for options with the highest probability of a 100%+ gain.

    For each contract, calculates:
    - move_needed_pct: % the underlying must move to approximately double the option price
      Formula: (option_mid / delta) / underlying_price × 100
    - leverage_ratio: how many dollars the option gains per 1% move in underlying
      Formula: delta × underlying_price / 100 × 100  (per contract)
    - gamma_efficiency: gamma per dollar of premium (higher = more explosive)

    Sorted by move_needed_pct ascending — top results need the smallest move to 2x.
    """
    if symbols is None:
        symbols = HIGH_BETA_WATCHLIST
    if isinstance(symbols, str):
        symbols = [symbols]

    today = datetime.now()
    candidates = []

    for sym in symbols[:8]:
        try:
            t = yf.Ticker(sym.upper())
            target_exps = [e for e in t.options
                           if 0 <= (datetime.strptime(e, "%Y-%m-%d") - today).days <= max_dte]
            if not target_exps:
                continue

            S = _get_price(t)
            if not S:
                continue

            for exp in target_exps:
                chain = t.option_chain(exp)
                dte = (datetime.strptime(exp, "%Y-%m-%d") - today).days
                T = max(dte, 1) / 365.0

                frames = []
                if option_type != "put":  frames.append(("call", chain.calls))
                if option_type != "call": frames.append(("put",  chain.puts))

                for otype, df in frames:
                    for _, row in df.iterrows():
                        vol = int(row.get("volume") or 0)
                        if vol < min_volume:
                            continue

                        iv  = row.get("impliedVolatility") or 0.0
                        K   = row.get("strike") or 0.0
                        bid = row.get("bid") or 0.0
                        ask = row.get("ask") or 0.0
                        mid = round((bid + ask) / 2, 2) if bid and ask else (row.get("lastPrice") or 0.0)

                        if mid < 0.05 or not iv:
                            continue

                        greeks = _bs_greeks(S, K, T, RISK_FREE_RATE, iv, otype)
                        if not greeks:
                            continue

                        delta = abs(greeks.get("delta") or 0)
                        gamma = greeks.get("gamma") or 0

                        if delta < 0.05:  # too far OTM — delta unreliable
                            continue

                        # % move in underlying needed to ~double option price
                        move_needed_pct = round((mid / delta) / S * 100, 1)

                        if move_needed_pct > max_move_needed_pct:
                            continue

                        # $ gain per 1% move in underlying (per contract = ×100)
                        leverage_ratio = round(delta * S * 0.01 * 100, 2)

                        # Gamma per dollar of premium — higher = more explosive upside
                        gamma_efficiency = round(gamma / mid, 4) if mid else 0

                        oi = int(row.get("openInterest") or 0)
                        break_even = round(K + mid, 2) if otype == "call" else round(K - mid, 2)

                        candidates.append({
                            "symbol": sym.upper(),
                            "type": otype,
                            "strike": K,
                            "expiration": exp,
                            "dte": dte,
                            "mid": mid,
                            "cost_per_contract": round(mid * 100, 2),
                            "volume": vol,
                            "open_interest": oi,
                            "iv_pct": round(iv * 100, 1),
                            "delta": round(greeks.get("delta") or 0, 3),
                            "gamma": round(gamma, 5),
                            "theta": greeks.get("theta"),
                            "break_even": break_even,
                            "underlying_price": round(S, 2),
                            "move_needed_pct": move_needed_pct,
                            "leverage_per_contract": leverage_ratio,
                            "gamma_efficiency": gamma_efficiency,
                            "in_the_money": bool(row.get("inTheMoney")),
                        })
        except Exception:
            continue

    # Sort by smallest move needed (easiest path to 100% gain)
    candidates.sort(key=lambda x: x["move_needed_pct"])

    return json.dumps({
        "tickers_screened": [s.upper() for s in symbols[:8]],
        "criteria": {
            "max_dte": max_dte,
            "min_volume": min_volume,
            "max_move_needed_pct": max_move_needed_pct,
            "goal": "100% gain (option doubles in value)",
        },
        "candidates_found": len(candidates),
        "top_20_easiest_to_double": candidates[:20],
        "note": (
            "move_needed_pct = approximate % underlying move for option to 2x. "
            "Lower = easier. Based on current delta — actual move needed will differ "
            "as delta changes (gamma effect). Not a guarantee of profit."
        ),
    }, indent=2, default=str)


# ─── Tool 5: Expirations ───────────────────────────────────────────────────────

def get_expirations(symbol: str) -> str:
    try:
        t = yf.Ticker(symbol.upper())
        today = datetime.now()
        results = []
        for exp in t.options:
            try:
                dte = (datetime.strptime(exp, "%Y-%m-%d") - today).days
                if 0 <= dte <= 21:
                    results.append({"date": exp, "dte": dte})
            except ValueError:
                continue
        return json.dumps({"symbol": symbol.upper(), "expirations_within_21_days": results,
                           "all_available": list(t.options)})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─── Tool 5: IV & Volatility Analysis ─────────────────────────────────────────

def get_iv_analysis(symbol: str) -> str:
    """
    Calculates:
    - HV10, HV30, HV60 (realized historical volatility)
    - HV Rank over 1 year (proxy for IV rank — how elevated is vol vs history)
    - Current ATM implied volatility from nearest 14-45 DTE expiration
    - IV vs HV spread (positive = options expensive, negative = options cheap)
    """
    try:
        today = datetime.now()
        t = yf.Ticker(symbol.upper())

        # ── Historical volatility ──────────────────────────────────────────────
        hist = t.history(period="1y")
        if hist.empty or len(hist) < 30:
            return json.dumps({"error": "Not enough price history for vol calculation"})

        closes = hist["Close"].dropna()
        log_ret = np.log(closes / closes.shift(1)).dropna()

        def hv(window):
            return float(log_ret.rolling(window).std().iloc[-1] * np.sqrt(252) * 100)

        hv10 = round(hv(10), 1)
        hv30 = round(hv(30), 1)
        hv60 = round(hv(60), 1)

        # HV rank: where is current 30-day HV relative to its 1-year range?
        rolling_hv30 = log_ret.rolling(30).std() * np.sqrt(252) * 100
        hv30_max = float(rolling_hv30.max())
        hv30_min = float(rolling_hv30.min())
        hv_rank = round((hv30 - hv30_min) / (hv30_max - hv30_min) * 100, 1) if hv30_max != hv30_min else 50.0

        if   hv_rank >= 80: hv_regime = "VERY HIGH — vol near 1-year peak, premium selling favored"
        elif hv_rank >= 60: hv_regime = "ELEVATED — above-average vol, be selective buying"
        elif hv_rank >= 40: hv_regime = "MODERATE — neutral vol environment"
        elif hv_rank >= 20: hv_regime = "LOW — below-average vol, buying cheaper than usual"
        else:               hv_regime = "VERY LOW — vol near 1-year trough, options are cheap"

        # ── Current ATM implied volatility ────────────────────────────────────
        S = _get_price(t)
        atm_iv = None
        atm_exp = None
        for exp in t.options:
            dte = (datetime.strptime(exp, "%Y-%m-%d") - today).days
            if 14 <= dte <= 45:
                chain = t.option_chain(exp)
                calls = chain.calls
                if calls.empty:
                    continue
                idx = (calls["strike"] - S).abs().idxmin()
                iv_val = calls.loc[idx, "impliedVolatility"]
                if iv_val and iv_val > 0:
                    atm_iv = round(float(iv_val) * 100, 1)
                    atm_exp = exp
                break

        iv_hv_spread = round(atm_iv - hv30, 1) if atm_iv else None
        if iv_hv_spread is not None:
            if   iv_hv_spread >  15: iv_assessment = "OPTIONS EXPENSIVE — IV >> HV, elevated risk premium, consider selling"
            elif iv_hv_spread >   5: iv_assessment = "SLIGHTLY EXPENSIVE — IV moderately above HV"
            elif iv_hv_spread > -5:  iv_assessment = "FAIRLY PRICED — IV ≈ HV"
            else:                    iv_assessment = "OPTIONS CHEAP — IV below realized vol, favorable for buyers"
        else:
            iv_assessment = "Could not determine (no ATM IV available)"

        return json.dumps({
            "symbol": symbol.upper(),
            "underlying_price": round(S, 2),
            "realized_volatility": {
                "hv10_pct": hv10,
                "hv30_pct": hv30,
                "hv60_pct": hv60,
            },
            "hv_rank": {
                "rank_pct": hv_rank,
                "1y_low_pct": round(hv30_min, 1),
                "1y_high_pct": round(hv30_max, 1),
                "regime": hv_regime,
            },
            "implied_volatility": {
                "atm_iv_pct": atm_iv,
                "expiration_used": atm_exp,
                "iv_vs_hv30_spread": iv_hv_spread,
                "assessment": iv_assessment,
            },
            "note": "HV Rank uses realized vol as proxy (true IV rank requires paid historical IV data)",
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


# ─── Tool 6: Earnings calendar ────────────────────────────────────────────────

def get_earnings_info(symbol: str) -> str:
    """
    Returns next earnings date, days until earnings, and a warning
    if earnings fall within the next 21 days (major IV event risk).
    """
    try:
        t = yf.Ticker(symbol.upper())
        today = datetime.now()
        next_date = None

        # Try earnings_dates DataFrame first (most reliable)
        try:
            ed = t.earnings_dates
            if ed is not None and not ed.empty:
                future = ed[ed.index.tz_localize(None) >= today] if ed.index.tzinfo else ed[ed.index >= today]
                if not future.empty:
                    next_date = future.index[-1]  # yfinance lists newest first, take last for soonest future
                    # Actually earnings_dates may be sorted descending, get the earliest future date
                    future_sorted = future.sort_index()
                    next_date = future_sorted.index[0]
        except Exception:
            pass

        # Fallback: try calendar
        if next_date is None:
            try:
                cal = t.calendar
                if isinstance(cal, dict):
                    dates = cal.get("Earnings Date", [])
                    if dates:
                        next_date = dates[0] if hasattr(dates[0], "date") else None
            except Exception:
                pass

        if next_date is None:
            return json.dumps({
                "symbol": symbol.upper(),
                "next_earnings": "Not found",
                "warning": "Could not determine earnings date — check manually before trading",
            })

        next_date_dt = next_date.to_pydatetime() if hasattr(next_date, "to_pydatetime") else next_date
        next_date_dt = next_date_dt.replace(tzinfo=None)
        days_until = (next_date_dt - today).days

        warning = None
        if days_until <= 0:
            warning = "EARNINGS IMMINENT or PASSED — check if post-earnings IV crush applies"
        elif days_until <= 7:
            warning = f"⚠️  EARNINGS IN {days_until} DAYS — IV will spike into earnings then CRUSH after. High risk for option buyers."
        elif days_until <= 21:
            warning = f"⚠️  EARNINGS IN {days_until} DAYS — falls within typical 0-21 DTE window. Factor IV crush into your exit plan."

        return json.dumps({
            "symbol": symbol.upper(),
            "next_earnings_date": next_date_dt.strftime("%Y-%m-%d"),
            "days_until_earnings": days_until,
            "warning": warning,
            "advice": (
                "If buying options: exit BEFORE earnings to avoid IV crush. "
                "If selling options: premium is richest just before earnings — sell then let IV crush work for you."
            ) if warning else "Earnings not within 21-day window — standard analysis applies.",
        })
    except Exception as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


# ─── Tool 7: Market context (VIX + SPY/QQQ trend) ────────────────────────────

def get_market_context() -> str:
    """
    Fetches:
    - VIX level and 5-day change (fear gauge)
    - SPY and QQQ 1-month price trend
    - Market regime interpretation
    - Overall options environment (cheap vs expensive)
    """
    try:
        today = datetime.now()

        # VIX
        vix_hist = yf.Ticker("^VIX").history(period="10d")
        vix_now  = round(float(vix_hist["Close"].iloc[-1]), 2)
        vix_5d   = round(float(vix_hist["Close"].iloc[-5]), 2) if len(vix_hist) >= 5 else vix_now
        vix_chg  = round(vix_now - vix_5d, 2)

        if   vix_now < 13: vix_regime = "VERY LOW — market extremely complacent, options are cheap"
        elif vix_now < 17: vix_regime = "LOW — calm market, options cheaply priced"
        elif vix_now < 22: vix_regime = "NORMAL — typical volatility environment"
        elif vix_now < 28: vix_regime = "ELEVATED — fear rising, options getting expensive"
        elif vix_now < 35: vix_regime = "HIGH FEAR — options expensive, premium selling has edge"
        else:              vix_regime = "EXTREME FEAR / CRISIS — very expensive options, huge moves expected"

        vix_trend = "RISING (fear increasing)" if vix_chg > 1 else "FALLING (fear decreasing)" if vix_chg < -1 else "STABLE"

        # SPY trend
        spy_hist = yf.Ticker("SPY").history(period="1mo")
        spy_now  = round(float(spy_hist["Close"].iloc[-1]), 2)
        spy_1w   = round(float(spy_hist["Close"].iloc[-5]), 2)
        spy_1mo  = round(float(spy_hist["Close"].iloc[0]), 2)
        spy_1w_chg  = round((spy_now / spy_1w  - 1) * 100, 2)
        spy_1mo_chg = round((spy_now / spy_1mo - 1) * 100, 2)

        # QQQ trend
        qqq_hist = yf.Ticker("QQQ").history(period="1mo")
        qqq_now  = round(float(qqq_hist["Close"].iloc[-1]), 2)
        qqq_1mo  = round(float(qqq_hist["Close"].iloc[0]), 2)
        qqq_1mo_chg = round((qqq_now / qqq_1mo - 1) * 100, 2)

        if   spy_1mo_chg >  3: market_trend = "BULLISH — strong uptrend over past month"
        elif spy_1mo_chg >  0: market_trend = "MILDLY BULLISH — slight upward drift"
        elif spy_1mo_chg > -3: market_trend = "NEUTRAL/CHOPPY — sideways action"
        elif spy_1mo_chg > -7: market_trend = "BEARISH — moderate downtrend"
        else:                  market_trend = "STRONGLY BEARISH — significant selloff in progress"

        options_env = (
            "BUYER'S MARKET — low VIX, cheap premiums, good time to buy calls/puts"
            if vix_now < 18 else
            "SELLER'S MARKET — elevated VIX, rich premiums, selling premium has edge"
            if vix_now > 25 else
            "NEUTRAL — balanced environment, evaluate each name individually"
        )

        return json.dumps({
            "timestamp": today.strftime("%Y-%m-%d %H:%M"),
            "vix": {
                "current": vix_now,
                "5d_ago": vix_5d,
                "5d_change": vix_chg,
                "trend": vix_trend,
                "regime": vix_regime,
            },
            "spy": {
                "price": spy_now,
                "1w_change_pct": spy_1w_chg,
                "1mo_change_pct": spy_1mo_chg,
            },
            "qqq": {
                "price": qqq_now,
                "1mo_change_pct": qqq_1mo_chg,
            },
            "market_trend": market_trend,
            "options_environment": options_env,
            "recommendation": (
                "Favor CALLS on individual names with bullish setups" if spy_1mo_chg > 2 and vix_now < 22
                else "Favor PUTS or hedges — market in downtrend" if spy_1mo_chg < -3
                else "Be selective — mixed signals, focus on individual stock catalysts"
            ),
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


# ─── Tool 8: Put/Call ratio ────────────────────────────────────────────────────

def get_put_call_ratio(symbol: str, max_dte: int = 21) -> str:
    """
    Calculates the put/call volume ratio across all near-term expirations.

    P/C > 1.2  → bearish sentiment (heavy put buying)
    P/C 0.8–1.2 → neutral
    P/C < 0.8  → bullish sentiment (heavy call buying)

    Also shows P/C by expiration and highlights the most active strikes.
    """
    try:
        today = datetime.now()
        t = yf.Ticker(symbol.upper())
        S = _get_price(t)

        total_call_vol = 0
        total_put_vol  = 0
        total_call_oi  = 0
        total_put_oi   = 0
        by_expiration  = []
        top_strikes    = []

        for exp in t.options:
            dte = (datetime.strptime(exp, "%Y-%m-%d") - today).days
            if not (0 <= dte <= max_dte):
                continue

            chain = t.option_chain(exp)
            c_vol = int(chain.calls["volume"].sum() or 0)
            p_vol = int(chain.puts["volume"].sum()  or 0)
            c_oi  = int(chain.calls["openInterest"].sum() or 0)
            p_oi  = int(chain.puts["openInterest"].sum()  or 0)

            total_call_vol += c_vol
            total_put_vol  += p_vol
            total_call_oi  += c_oi
            total_put_oi   += p_oi

            pc = round(p_vol / c_vol, 2) if c_vol else None
            by_expiration.append({"expiration": exp, "dte": dte,
                                  "call_volume": c_vol, "put_volume": p_vol,
                                  "put_call_ratio": pc})

            # Top call and put strike by volume this expiration
            if not chain.calls.empty:
                top_c = chain.calls.nlargest(1, "volume").iloc[0]
                top_strikes.append({"exp": exp, "type": "call",
                                    "strike": top_c["strike"], "volume": int(top_c["volume"] or 0),
                                    "distance_pct": round((top_c["strike"] - S) / S * 100, 1)})
            if not chain.puts.empty:
                top_p = chain.puts.nlargest(1, "volume").iloc[0]
                top_strikes.append({"exp": exp, "type": "put",
                                    "strike": top_p["strike"], "volume": int(top_p["volume"] or 0),
                                    "distance_pct": round((top_p["strike"] - S) / S * 100, 1)})

        overall_pc = round(total_put_vol / total_call_vol, 2) if total_call_vol else None

        if overall_pc is None:
            sentiment = "No data"
        elif overall_pc > 1.5: sentiment = "VERY BEARISH — heavy put buying, market expects downside"
        elif overall_pc > 1.2: sentiment = "BEARISH — put volume significantly outpaces calls"
        elif overall_pc > 0.9: sentiment = "SLIGHTLY BEARISH / NEUTRAL"
        elif overall_pc > 0.7: sentiment = "NEUTRAL / SLIGHTLY BULLISH"
        elif overall_pc > 0.5: sentiment = "BULLISH — call volume dominates"
        else:                  sentiment = "VERY BULLISH — aggressive call buying"

        top_strikes.sort(key=lambda x: x["volume"], reverse=True)

        return json.dumps({
            "symbol": symbol.upper(),
            "underlying_price": round(S, 2),
            "overall": {
                "total_call_volume": total_call_vol,
                "total_put_volume":  total_put_vol,
                "put_call_ratio":    overall_pc,
                "sentiment":         sentiment,
                "call_oi": total_call_oi,
                "put_oi":  total_put_oi,
                "oi_put_call_ratio": round(total_put_oi / total_call_oi, 2) if total_call_oi else None,
            },
            "by_expiration": by_expiration,
            "most_active_strikes": top_strikes[:10],
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


# ─── Tool 9: Position sizing & risk check ────────────────────────────────────

def calculate_position_size(
    option_price: float,
    account_size: float = None,
    max_risk_pct: float = None,
    dte: int = 5,
    confidence: int = 5,
) -> str:
    """
    Calculates safe position sizing for a single options trade.

    confidence (1–10): scales risk linearly from min_trade_risk_pct (7%) at 1
    up to max_trade_risk_pct (40%) at 10. Use your honest assessment of edge.
    """
    acct = account_size or risk_settings["account_size"]

    if not acct:
        return json.dumps({
            "error": "Account size not set.",
            "fix": "Tell me your account size (e.g. 'my account is $10,000') and I'll size the trade for you.",
        })

    # 0DTE always uses the hard cap regardless of confidence
    if dte == 0:
        risk_pct = risk_settings["dte_0_max_pct"]
        confidence_note = "0DTE hard cap — confidence scaling disabled for binary outcomes."
    elif max_risk_pct is not None:
        risk_pct = max_risk_pct
        confidence_note = f"Manual override: {risk_pct}%"
    else:
        # Linear interpolation: confidence 1 → min, 10 → max
        lo  = risk_settings["min_trade_risk_pct"]
        hi  = risk_settings["max_trade_risk_pct"]
        c   = max(1, min(10, confidence))
        risk_pct = round(lo + (c - 1) / 9.0 * (hi - lo), 2)
        confidence_note = (
            f"Confidence {c}/10 → {risk_pct}% of account "
            f"(scale: {lo}% at 1 → {hi}% at 10)"
        )

    max_risk_dollars  = round(acct * risk_pct / 100, 2)
    cost_per_contract = round(option_price * 100, 2)
    max_contracts     = max(1, int(max_risk_dollars / cost_per_contract))
    actual_risk       = round(max_contracts * cost_per_contract, 2)
    pct_of_account    = round(actual_risk / acct * 100, 2)

    stop_loss_pct   = risk_settings["stop_loss_pct"]
    stop_loss_value = round(option_price * (1 - stop_loss_pct / 100), 2)
    stop_loss_loss  = round(actual_risk * stop_loss_pct / 100, 2)

    max_dd          = risk_settings["max_drawdown_pct"]
    trades_to_limit = int(max_dd / risk_pct) if risk_pct else 0

    warning = None
    if dte == 0:
        warning = "⚠️  0DTE is binary — full loss is common. Size is already capped."

    return json.dumps({
        "account_size":      acct,
        "option_price":      option_price,
        "cost_per_contract": cost_per_contract,
        "confidence_sizing": {
            "confidence_score":  confidence,
            "risk_pct_applied":  risk_pct,
            "note":              confidence_note,
        },
        "sizing": {
            "max_contracts":   max_contracts,
            "total_cost":      actual_risk,
            "pct_of_account":  pct_of_account,
            "max_loss_if_zero": actual_risk,
        },
        "stop_loss": {
            "exit_at_option_price": stop_loss_value,
            "loss_if_stopped":      stop_loss_loss,
            "pct_of_account_lost":  round(stop_loss_loss / acct * 100, 2),
            "rule": f"Exit if option drops {stop_loss_pct}% from entry",
        },
        "drawdown_context": {
            "this_trade_impact_pct":    pct_of_account,
            "trades_until_dd_limit":    trades_to_limit,
            "warning":                  warning,
        },
    }, indent=2)


# ─── Tool 10: Update risk settings ────────────────────────────────────────────

def manage_risk_settings(
    # ── Risk / exit params ────────────────────────────────────────────────────
    account_size: float = None,
    max_drawdown_pct: float = None,
    stop_loss_pct: float = None,
    profit_target_pct: float = None,
    min_position_pct: float = None,
    max_position_pct: float = None,
    dte_0_max_pct: float = None,
    # ── Strategy filter params ────────────────────────────────────────────────
    vix_defense_threshold: float = None,
    defense_position_mult: float = None,
    atr_expansion_stop_mult: float = None,
    min_ev_return_pct: float = None,
    liquidity_spread_max_pct: float = None,
    illiquid_extra_margin_pct: float = None,
    iv_crush_z_threshold: float = None,
    iv_crush_confidence_penalty: float = None,
    # ── Confidence target params ──────────────────────────────────────────────
    delta_target: float = None,
    dte_target: int = None,
) -> str:
    """
    View or update any part of the unified strategy profile (risk rules, entry filters,
    confidence targets). Call with NO arguments to display the full current profile.
    Call with specific arguments to update those values.
    """
    sp  = STRATEGY_PROFILE
    rsk = sp["risk"]
    flt = sp["filters"]
    tgt = sp["targets"]

    # ── Apply updates ─────────────────────────────────────────────────────────
    if account_size               is not None: rsk["account_size"]               = account_size
    if max_drawdown_pct           is not None: rsk["max_drawdown_pct"]           = max_drawdown_pct
    if stop_loss_pct              is not None: rsk["stop_loss_pct"]              = stop_loss_pct
    if profit_target_pct          is not None: rsk["profit_target_pct"]          = profit_target_pct
    if min_position_pct           is not None: rsk["min_position_pct"]           = min_position_pct
    if max_position_pct           is not None: rsk["max_position_pct"]           = max_position_pct
    if dte_0_max_pct              is not None: rsk["dte_0_max_pct"]              = dte_0_max_pct
    if vix_defense_threshold      is not None: flt["vix_defense_threshold"]      = vix_defense_threshold
    if defense_position_mult      is not None: flt["defense_position_mult"]      = defense_position_mult
    if atr_expansion_stop_mult    is not None: flt["atr_expansion_stop_mult"]    = atr_expansion_stop_mult
    if min_ev_return_pct          is not None: flt["min_ev_return_pct"]          = min_ev_return_pct
    if liquidity_spread_max_pct   is not None: flt["liquidity_spread_max_pct"]   = liquidity_spread_max_pct
    if illiquid_extra_margin_pct  is not None: flt["illiquid_extra_margin_pct"]  = illiquid_extra_margin_pct
    if iv_crush_z_threshold       is not None: flt["iv_crush_z_threshold"]       = iv_crush_z_threshold
    if iv_crush_confidence_penalty is not None: flt["iv_crush_confidence_penalty"] = iv_crush_confidence_penalty
    if delta_target               is not None: tgt["delta_optimal"]              = delta_target
    if dte_target                 is not None: tgt["dte_optimal"]                = dte_target

    # ── Build full profile snapshot ───────────────────────────────────────────
    acct = rsk.get("account_size")
    cw   = sp["confidence_weights"]

    result = {
        "strategy_name": sp["name"],
        "confidence_score": {
            "weights": {
                "iv_rank":  f"{round(cw['iv_percentile'] * 100)}%",
                "delta":    f"{round(cw['delta'] * 100)}%",
                "dte":      f"{round(cw['dte'] * 100)}%",
            },
            "targets": {
                "delta_optimal":  tgt["delta_optimal"],
                "delta_falloff":  tgt["delta_falloff"],
                "dte_optimal":    tgt["dte_optimal"],
                "dte_falloff":    tgt["dte_falloff"],
            },
        },
        "entry_filters": {
            "iv_crush_z_threshold":        flt["iv_crush_z_threshold"],
            "iv_crush_confidence_penalty": flt["iv_crush_confidence_penalty"],
            "liquidity_spread_max_pct":    flt["liquidity_spread_max_pct"],
            "illiquid_extra_margin_pct":   flt["illiquid_extra_margin_pct"],
            "min_ev_return_pct":           flt["min_ev_return_pct"],
        },
        "market_regime": {
            "vix_defense_threshold":    flt["vix_defense_threshold"],
            "defense_position_mult":    flt["defense_position_mult"],
            "atr_expansion_stop_mult":  flt["atr_expansion_stop_mult"],
        },
        "risk_and_exits": {
            "account_size":       acct or "not set",
            "stop_loss_pct":      rsk["stop_loss_pct"],
            "profit_target_pct":  rsk["profit_target_pct"],
            "min_position_pct":   rsk["min_position_pct"],
            "max_position_pct":   rsk["max_position_pct"],
            "max_drawdown_pct":   rsk["max_drawdown_pct"],
            "dte_0_max_pct":      rsk["dte_0_max_pct"],
        },
    }

    if acct:
        result["dollar_limits"] = {
            "max_per_trade_$":    round(acct * rsk["max_position_pct"] / 100, 2),
            "min_per_trade_$":    round(acct * rsk["min_position_pct"] / 100, 2),
            "max_0dte_$":         round(acct * rsk["dte_0_max_pct"] / 100, 2),
            "max_drawdown_$":     round(acct * rsk["max_drawdown_pct"] / 100, 2),
        }

    return json.dumps(result, indent=2)


# ─── Tool 11: Paper trading journal ──────────────────────────────────────────

def _load_trades() -> list:
    if os.path.exists(PAPER_TRADES_FILE):
        try:
            with open(PAPER_TRADES_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def _save_trades(trades: list):
    with open(PAPER_TRADES_FILE, "w") as f:
        json.dump(trades, f, indent=2, default=str)


def log_paper_trade(
    action: str = "list",
    symbol: str = None,
    option_type: str = None,
    strike: float = None,
    expiration: str = None,
    entry_price: float = None,
    underlying_entry: float = None,
    contracts: int = 1,
    notes: str = None,
    trade_id: int = None,
    exit_price: float = None,
) -> str:
    """
    Paper trading journal — log, track, and close options trades.

    action="add"   — log a new trade
    action="list"  — show all trades + summary stats (win rate, total P&L)
    action="check" — estimate current P&L for open trades using Black-Scholes
    action="close" — mark a trade closed with a final exit price
    """
    trades = _load_trades()
    today = datetime.now()

    if action == "add":
        if not all([symbol, option_type, strike, expiration, entry_price]):
            return json.dumps({"error": "Required: symbol, option_type, strike, expiration, entry_price"})
        exp_dt = datetime.strptime(expiration, "%Y-%m-%d")
        dte = (exp_dt - today).days
        new_id = max((t["id"] for t in trades), default=0) + 1
        stop_px = round(entry_price * (1 - risk_settings["stop_loss_pct"] / 100), 2)
        trade = {
            "id": new_id,
            "symbol": symbol.upper(),
            "option_type": option_type.lower(),
            "strike": strike,
            "expiration": expiration,
            "dte_at_entry": dte,
            "entry_price": entry_price,
            "cost_per_contract": round(entry_price * 100, 2),
            "contracts": contracts,
            "total_cost": round(entry_price * 100 * contracts, 2),
            "underlying_entry": underlying_entry,
            "entry_date": today.strftime("%Y-%m-%d"),
            "stop_loss_price": stop_px,
            "target_2x_price": round(entry_price * 2, 2),
            "status": "open",
            "exit_price": None,
            "exit_date": None,
            "pnl_pct": None,
            "pnl_dollars": None,
            "notes": notes or "",
        }
        trades.append(trade)
        _save_trades(trades)
        return json.dumps({
            "message": f"Trade #{new_id} logged.",
            "trade": trade,
            "reminders": {
                "stop_loss": f"Exit if option falls to ${stop_px}",
                "target":    f"Take profit at ${trade['target_2x_price']} (100% gain)",
                "expires":   f"{expiration} ({dte} DTE)",
            },
        }, indent=2)

    elif action == "list":
        if not trades:
            return json.dumps({"message": "No paper trades logged yet.", "total": 0})
        closed = [t for t in trades if t["status"] == "closed"]
        open_t  = [t for t in trades if t["status"] == "open"]
        wins    = [t for t in closed if (t.get("pnl_pct") or 0) > 0]
        losses  = [t for t in closed if (t.get("pnl_pct") or 0) <= 0]
        return json.dumps({
            "summary": {
                "total_trades": len(trades),
                "open": len(open_t),
                "closed": len(closed),
                "win_rate": f"{round(len(wins)/len(closed)*100,1)}%" if closed else "N/A",
                "avg_win_pct":  round(sum(t["pnl_pct"] for t in wins)   / len(wins),   1) if wins   else None,
                "avg_loss_pct": round(sum(t["pnl_pct"] for t in losses) / len(losses), 1) if losses else None,
                "total_pnl_dollars": round(sum(t.get("pnl_dollars") or 0 for t in closed), 2),
            },
            "open_trades":   open_t,
            "recent_closed": closed[-10:],
        }, indent=2, default=str)

    elif action == "check":
        open_t = [t for t in trades if t["status"] == "open"]
        if trade_id:
            open_t = [t for t in open_t if t["id"] == trade_id]
        if not open_t:
            return json.dumps({"message": "No open trades to check."})
        results = []
        for t in open_t:
            try:
                ticker = yf.Ticker(t["symbol"])
                S = _get_price(ticker)
                exp_dt = datetime.strptime(t["expiration"], "%Y-%m-%d")
                dte = max((exp_dt - today).days, 0)
                T = dte / 365.0
                # Try to get real IV from chain, fall back to HV30
                iv = None
                try:
                    ch = ticker.option_chain(t["expiration"])
                    df = ch.calls if t["option_type"] == "call" else ch.puts
                    if not df.empty:
                        idx = (df["strike"] - S).abs().idxmin()
                        iv_raw = df.loc[idx, "impliedVolatility"]
                        if iv_raw and iv_raw > 0:
                            iv = float(iv_raw)
                except Exception:
                    pass
                if not iv:
                    h = ticker.history(period="2mo")
                    if len(h) >= 30:
                        lr = np.log(h["Close"] / h["Close"].shift(1)).dropna()
                        iv = float(lr.rolling(30).std().iloc[-1] * np.sqrt(252))
                if T <= 0:
                    cur = max(0.0, S - t["strike"]) if t["option_type"] == "call" else max(0.0, t["strike"] - S)
                elif iv:
                    g = _bs_greeks(S, t["strike"], T, RISK_FREE_RATE, iv, t["option_type"])
                    cur = g.get("bs_price") if g else None
                else:
                    cur = None
                if cur is not None:
                    pct = round((cur / t["entry_price"] - 1) * 100, 1)
                    dlr = round((cur - t["entry_price"]) * 100 * t["contracts"], 2)
                    if pct >= 100:     flag = "🚀 2x TARGET — consider taking profit"
                    elif pct >= 50:    flag = "🟢 BIG WINNER — consider partial exit"
                    elif pct > 0:      flag = "🟢 PROFIT"
                    elif pct > -risk_settings["stop_loss_pct"]: flag = "🔴 LOSS"
                    else:              flag = "⛔ STOP LOSS HIT — exit now"
                else:
                    pct, dlr, flag = None, None, "Cannot price"
                results.append({
                    "id": t["id"],
                    "trade": f"{t['symbol']} {t['option_type'].upper()} ${t['strike']} {t['expiration']}",
                    "entry_price": t["entry_price"],
                    "current_value_est": round(cur, 4) if cur else None,
                    "underlying_now": round(S, 2),
                    "dte_remaining": dte,
                    "pnl_pct": pct,
                    "pnl_dollars": dlr,
                    "status": flag,
                })
            except Exception as e:
                results.append({"id": t["id"], "error": str(e)})
        return json.dumps({"updates": results, "note": "Values estimated via Black-Scholes"}, indent=2)

    elif action == "close":
        if trade_id is None or exit_price is None:
            return json.dumps({"error": "Required: trade_id and exit_price"})
        for t in trades:
            if t["id"] == trade_id:
                if t["status"] == "closed":
                    return json.dumps({"error": f"Trade #{trade_id} already closed."})
                pct = round((exit_price / t["entry_price"] - 1) * 100, 1)
                dlr = round((exit_price - t["entry_price"]) * 100 * t["contracts"], 2)
                t.update({"status": "closed", "exit_price": exit_price,
                           "exit_date": today.strftime("%Y-%m-%d"),
                           "pnl_pct": pct, "pnl_dollars": dlr})
                _save_trades(trades)
                return json.dumps({
                    "message": f"Trade #{trade_id} closed.",
                    "outcome": "WIN 🟢" if pct > 0 else "LOSS 🔴",
                    "pnl_pct": pct, "pnl_dollars": dlr,
                }, indent=2)
        return json.dumps({"error": f"Trade #{trade_id} not found."})

    return json.dumps({"error": f"Unknown action '{action}'. Use: add, list, check, close"})


# ─── Tool 12: Daily predictions tracker ───────────────────────────────────────

def _load_predictions() -> list:
    if os.path.exists(PREDICTIONS_FILE):
        try:
            with open(PREDICTIONS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_predictions(preds: list):
    with open(PREDICTIONS_FILE, "w") as f:
        json.dump(preds, f, indent=2, default=str)


def log_prediction(
    action: str = "log",
    ticker: str = None,
    direction: str = None,
    target_move_pct: float = None,
    target_date: str = None,
    confidence: int = 5,
    reasoning: str = "",
    prediction_id: int = None,
) -> str:
    """
    action="log"    — record a new daily prediction (fetches entry price automatically)
    action="grade"  — grade all ungraded predictions whose target_date has passed
    action="list"   — show all predictions + accuracy stats
    action="delete" — remove a prediction by id
    """
    preds = _load_predictions()
    today = datetime.now()

    # ── list ──────────────────────────────────────────────────────────────────
    if action == "list":
        if not preds:
            return json.dumps({"message": "No predictions recorded yet."})
        total   = len(preds)
        graded  = [p for p in preds if p.get("outcome")]
        hits    = [p for p in graded if p["outcome"] == "hit"]
        dir_ok  = [p for p in graded if p["outcome"] in ("hit", "directional")]
        pending = [p for p in preds if not p.get("outcome")]
        summary = {
            "total_predictions": total,
            "graded": len(graded),
            "pending_grade": len(pending),
            "hit_rate_pct":       round(len(hits) / len(graded) * 100, 1) if graded else None,
            "directional_rate_pct": round(len(dir_ok) / len(graded) * 100, 1) if graded else None,
            "predictions": preds,
        }
        return json.dumps(summary, indent=2, default=str)

    # ── grade ─────────────────────────────────────────────────────────────────
    if action == "grade":
        graded_count = 0
        for p in preds:
            if p.get("outcome"):
                continue
            try:
                target_dt = datetime.strptime(p["target_date"], "%Y-%m-%d")
            except Exception:
                continue
            if today.date() < target_dt.date():
                continue  # not yet due
            try:
                t = yf.Ticker(p["ticker"])
                hist = t.history(start=p["entry_date"], end=(target_dt + timedelta(days=3)).strftime("%Y-%m-%d"))
                if hist.empty:
                    continue
                entry_price  = p["entry_price"]
                # Use the close on or just after target_date
                target_rows = hist[hist.index.date >= target_dt.date()]
                if target_rows.empty:
                    target_rows = hist
                exit_price = float(target_rows["Close"].iloc[0])
                actual_move_pct = round((exit_price / entry_price - 1) * 100, 2)
                direction = p["direction"]
                predicted_move = p.get("target_move_pct", 0)
                # Normalise direction: call/put → bullish/bearish for outcome logic
                is_bullish = direction in ("bullish", "call")
                # Was direction correct?
                dir_correct = (is_bullish and actual_move_pct > 0) or \
                              (not is_bullish and actual_move_pct < 0)
                # Was magnitude within 50% of predicted move (generous)?
                mag_ok = abs(actual_move_pct) >= abs(predicted_move) * 0.5 if predicted_move else dir_correct
                if dir_correct and mag_ok:
                    outcome = "hit"
                elif dir_correct:
                    outcome = "directional"
                else:
                    outcome = "miss"

                # Estimated option P&L for daily_scan picks (delta-approximation)
                est_option_gain_pct = None
                if p.get("type") == "daily_scan":
                    delta   = p.get("delta_est", 0.0)
                    premium = p.get("est_premium", 0.0)
                    if delta > 0 and premium > 0:
                        dir_factor = 1.0 if is_bullish else -1.0
                        raw_gain = dir_factor * delta * (entry_price * actual_move_pct / 100.0) / premium * 100.0
                        stop   = -abs(p.get("stop_loss_pct",   50.0))
                        target =  abs(p.get("profit_target_pct", 100.0))
                        est_option_gain_pct = round(max(stop, min(target, raw_gain)), 1)

                update = {
                    "outcome":            outcome,
                    "exit_price":         round(exit_price, 2),
                    "actual_move_pct":    actual_move_pct,
                    "graded_date":        today.strftime("%Y-%m-%d"),
                }
                if est_option_gain_pct is not None:
                    update["est_option_gain_pct"] = est_option_gain_pct
                p.update(update)
                graded_count += 1
            except Exception as e:
                p["grade_error"] = str(e)
        _save_predictions(preds)
        return json.dumps({"message": f"Graded {graded_count} prediction(s).",
                           "predictions": preds}, indent=2, default=str)

    # ── delete ────────────────────────────────────────────────────────────────
    if action == "delete":
        before = len(preds)
        preds = [p for p in preds if p.get("id") != prediction_id]
        _save_predictions(preds)
        return json.dumps({"message": f"Deleted prediction #{prediction_id}." if len(preds) < before
                           else f"Prediction #{prediction_id} not found."})

    # ── log ───────────────────────────────────────────────────────────────────
    if action == "log":
        if not ticker or not direction:
            return json.dumps({"error": "ticker and direction are required for action='log'"})
        if direction not in ("bullish", "bearish"):
            return json.dumps({"error": "direction must be 'bullish' or 'bearish'"})
        if not target_date:
            # default: 5 calendar days out
            target_date = (today + timedelta(days=5)).strftime("%Y-%m-%d")

        # Fetch current price as entry
        try:
            t = yf.Ticker(ticker.upper())
            entry_price = round(_get_price(t), 2)
        except Exception as e:
            return json.dumps({"error": f"Could not fetch price for {ticker}: {e}"})

        new_id = max((p.get("id", 0) for p in preds), default=0) + 1
        pred = {
            "id":               new_id,
            "ticker":           ticker.upper(),
            "direction":        direction,
            "target_move_pct":  target_move_pct,
            "entry_date":       today.strftime("%Y-%m-%d"),
            "entry_price":      entry_price,
            "target_date":      target_date,
            "confidence":       max(1, min(10, confidence)),
            "reasoning":        reasoning,
            "outcome":          None,
        }
        preds.append(pred)
        _save_predictions(preds)
        return json.dumps({
            "message": f"Prediction #{new_id} logged.",
            "prediction": pred,
        }, indent=2, default=str)

    return json.dumps({"error": f"Unknown action '{action}'. Use: log, grade, list, delete"})


# ─── Tool 13: Retroactive prediction backfill ─────────────────────────────────

def backfill_predictions(
    tickers: list = None,
    lookback_days: int = 90,
    horizon_days: int = 5,
    overwrite: bool = False,
) -> str:
    """
    Retroactively generate and grade predictions for every past trading day.

    Signal logic (using only data available at market open that day):
      - 5-day return  (short momentum)
      - 20-day return (medium trend)
      - Position of close vs 20-day simple moving average

    Direction rules:
      bullish  if  5d_ret >  1.0%  AND  price > SMA20
      bearish  if  5d_ret < -1.0%  AND  price < SMA20

    Confidence scales with signal strength (1–10).
    Skips days where the signal is ambiguous.

    All predictions are graded immediately (target date has already passed).
    """
    if tickers is None:
        tickers = ["SPY", "QQQ", "NVDA", "TSLA", "AAPL", "META", "AMD"]

    preds      = _load_predictions()
    existing   = set()
    if not overwrite:
        existing = {(p["ticker"], p["entry_date"]) for p in preds}

    today       = datetime.now().date()
    fetch_start = (datetime.now() - timedelta(days=lookback_days + 60)).strftime("%Y-%m-%d")
    fetch_end   = today.strftime("%Y-%m-%d")

    added = 0
    skipped_neutral = 0
    next_id = max((p.get("id", 0) for p in preds), default=0) + 1

    for ticker in tickers:
        try:
            t    = yf.Ticker(ticker.upper())
            hist = t.history(start=fetch_start, end=fetch_end, interval="1d")
            if hist.empty or len(hist) < 25:
                continue
            closes = hist["Close"]
            opens  = hist["Open"]
            dates  = [d.date() for d in hist.index]

            for i in range(24, len(dates)):
                pred_date   = dates[i]          # the "today" for this prediction
                target_date = None
                # find the trading day ~horizon_days later
                for j in range(i + 1, min(i + horizon_days + 6, len(dates))):
                    if (dates[j] - pred_date).days >= horizon_days:
                        target_date = dates[j]
                        exit_idx    = j
                        break
                if target_date is None:
                    continue                     # not enough future data
                if (today - target_date).days < 0:
                    continue                     # target not yet reached

                date_str = pred_date.strftime("%Y-%m-%d")
                if (ticker.upper(), date_str) in existing:
                    continue

                # Signal: use data available *before* market open on pred_date
                #   close[i-1]  = yesterday's close (known at open)
                #   close[i-20..i-1] = last 20 closes
                c_now  = float(closes.iloc[i - 1])   # yesterday's close = entry proxy
                c_5    = float(closes.iloc[i - 6])   # 5 trading days ago
                sma20  = float(closes.iloc[i - 20: i].mean())
                ret5   = (c_now / c_5 - 1) * 100

                # Entry price = open on pred_date
                entry_price = round(float(opens.iloc[i]), 2)

                # Direction decision (threshold aligned with live scanner: 0.3%)
                if ret5 > 0.3 and c_now > sma20:
                    direction = "bullish"
                    # confidence: scales 6–9 with strength of signal
                    conf = min(9, 6 + int(min(ret5 - 0.3, 6) / 2))
                elif ret5 < -0.3 and c_now < sma20:
                    direction = "bearish"
                    conf = min(9, 6 + int(min(abs(ret5) - 0.3, 6) / 2))
                else:
                    skipped_neutral += 1
                    continue

                # Expected move = half of recent 5-day absolute move
                target_move_pct = round(abs(ret5) * 0.5, 2)

                # Grade immediately
                exit_price      = round(float(closes.iloc[exit_idx]), 2)
                actual_move_pct = round((exit_price / entry_price - 1) * 100, 2)
                dir_correct = (direction == "bullish" and actual_move_pct > 0) or \
                              (direction == "bearish" and actual_move_pct < 0)
                mag_ok = abs(actual_move_pct) >= target_move_pct * 0.5 if target_move_pct else dir_correct
                if dir_correct and mag_ok:
                    outcome = "hit"
                elif dir_correct:
                    outcome = "directional"
                else:
                    outcome = "miss"

                pred = {
                    "id":               next_id,
                    "ticker":           ticker.upper(),
                    "direction":        direction,
                    "target_move_pct":  target_move_pct,
                    "entry_date":       date_str,
                    "entry_price":      entry_price,
                    "target_date":      target_date.strftime("%Y-%m-%d"),
                    "confidence":       conf,
                    "reasoning":        f"5d_ret={ret5:+.1f}% vs SMA20 ({sma20:.2f})",
                    "outcome":          outcome,
                    "exit_price":       exit_price,
                    "actual_move_pct":  actual_move_pct,
                    "graded_date":      today.strftime("%Y-%m-%d"),
                    "source":           "backfill",
                }
                preds.append(pred)
                existing.add((ticker.upper(), date_str))
                next_id += 1
                added += 1

        except Exception:
            pass

    _save_predictions(preds)

    # Summary stats
    backfill_preds = [p for p in preds if p.get("source") == "backfill"]
    graded  = [p for p in backfill_preds if p.get("outcome")]
    hits    = [p for p in graded if p["outcome"] == "hit"]
    dir_ok  = [p for p in graded if p["outcome"] in ("hit", "directional")]

    return json.dumps({
        "message":          f"Backfilled {added} predictions across {len(tickers)} tickers.",
        "skipped_neutral":  skipped_neutral,
        "total_backfill":   len(backfill_preds),
        "hit_rate_pct":     round(len(hits) / len(graded) * 100, 1) if graded else None,
        "directional_rate_pct": round(len(dir_ok) / len(graded) * 100, 1) if graded else None,
        "tickers":          tickers,
        "lookback_days":    lookback_days,
        "horizon_days":     horizon_days,
    }, indent=2)


# ─── Tool 14: Historical strategy backtester ──────────────────────────────────

def backtest_strategy(
    symbol: str,
    option_type: str = "signal",   # "call" | "put" | "signal" (auto from momentum)
    dte_at_entry: int = 7,
    delta_target: float = None,    # defaults to STRATEGY_PROFILE["targets"]["delta_optimal"]
    lookback_days: int = 252,
    stop_loss_pct: float = None,   # defaults to STRATEGY_PROFILE["risk"]["stop_loss_pct"]
    profit_target_pct: float = None,  # defaults to STRATEGY_PROFILE["risk"]["profit_target_pct"]
    position_size_dollars: float = None,
    # Filters matching the bot's live rules
    vix_max: float = None,         # defaults to STRATEGY_PROFILE["filters"]["vix_defense_threshold"]
    hv_rank_max: float = 80.0,     # skip days estimated HV rank > this
    require_signal: bool = True,   # only trade on momentum+trend signal days (like bot)
) -> str:
    """
    Backtests the bot's ACTUAL methodology over historical data:

    Entry filters (all must pass to take a trade):
      1. Momentum signal: 5-day return direction aligns with option_type
         (or auto-selects direction when option_type='signal')
      2. Trend confirmation: price > SMA20 for calls, price < SMA20 for puts
      3. VIX proxy filter: estimated market vol < vix_max (uses SPY HV as proxy)
      4. HV rank filter: current 30-day HV not in top hv_rank_max% of trailing year
         (avoids buying expensive options — mirrors the bot's IV rank rule)

    Strike selection:
      - Searches for strike with BS delta closest to delta_target
        (bot targets 0.20–0.40 OTM delta range)

    Exit rules (same as live bot):
      - Stop-loss at stop_loss_pct% of premium
      - Profit target at profit_target_pct% gain
      - Hold to expiry otherwise (intrinsic value only)

    Position sizing:
      - Uses confidence-scaled sizing: stronger signal → larger position
        (mirrors the 7–40% linear confidence scale)
    """
    try:
        # Resolve None defaults from STRATEGY_PROFILE — single source of truth
        if delta_target     is None: delta_target     = STRATEGY_PROFILE["targets"]["delta_optimal"]
        if stop_loss_pct    is None: stop_loss_pct    = STRATEGY_PROFILE["risk"]["stop_loss_pct"]
        if profit_target_pct is None: profit_target_pct = STRATEGY_PROFILE["risk"]["profit_target_pct"]
        if vix_max          is None: vix_max          = STRATEGY_PROFILE["filters"]["vix_defense_threshold"]

        # Dollar sizing: explicit param → risk_settings account → fallback $1 000
        if position_size_dollars is None:
            acct = STRATEGY_PROFILE["risk"].get("account_size") or 0
            position_size_dollars = acct * 0.10 if acct else 1_000.0

        fetch_days = lookback_days + dte_at_entry + 120
        t = yf.Ticker(symbol.upper())
        hist = t.history(period=f"{fetch_days}d")
        if hist.empty or len(hist) < 80:
            return json.dumps({"error": f"Not enough price history for {symbol}"})

        # Also fetch SPY as VIX proxy (HV of SPY ≈ market vol regime)
        spy_hist = yf.Ticker("SPY").history(period=f"{fetch_days}d") if symbol.upper() != "SPY" else hist
        spy_closes = spy_hist["Close"].dropna()

        closes = hist["Close"].dropna()
        n = len(closes)

        # Build a lookup: date → SPY HV30 (for VIX proxy filter)
        spy_hv_by_idx = {}
        for si in range(30, len(spy_closes)):
            lr = [math.log(float(spy_closes.iloc[j]) / float(spy_closes.iloc[j-1]))
                  for j in range(si - 30, si) if j > 0]
            if len(lr) >= 20:
                spy_hv_by_idx[si] = float(np.std(lr) * math.sqrt(252)) * 100  # annualised %

        # Build rolling 252-day HV percentile lookup for this ticker (HV rank proxy)
        hv_history = []
        for ci in range(30, n):
            lr = [math.log(float(closes.iloc[j]) / float(closes.iloc[j-1]))
                  for j in range(ci - 30, ci) if j > 0]
            hv_history.append(float(np.std(lr) * math.sqrt(252)) * 100 if len(lr) >= 20 else 0.0)

        simulated  = []
        skipped    = {"no_signal": 0, "vix_filter": 0, "hv_rank_filter": 0, "no_valid_strike": 0}

        for i in range(30, min(n - dte_at_entry - 1, lookback_days + 30)):
            # Only check every trading day (not every 5) — let filters thin the trades naturally
            S0 = float(closes.iloc[i])

            # ── HV calculations ────────────────────────────────────────────────
            log_rets = [math.log(float(closes.iloc[j]) / float(closes.iloc[j-1]))
                        for j in range(i - 30, i) if j > 0]
            if len(log_rets) < 20:
                continue
            hv30 = float(np.std(log_rets) * math.sqrt(252))
            if hv30 <= 0:
                continue

            # ── Filter 1: VIX proxy (SPY HV30 as market vol regime) ────────────
            # Map ticker day to nearest SPY day by position ratio
            spy_idx = min(int(i * len(spy_closes) / n), len(spy_closes) - 1)
            spy_hv  = spy_hv_by_idx.get(spy_idx, 0)
            # SPY HV30 > 35% annualised ≈ VIX > 35 regime
            if spy_hv > vix_max:
                skipped["vix_filter"] += 1
                continue

            # ── Filter 2: HV rank proxy — skip if vol is historically expensive ──
            hv_hist_idx = i - 30
            if hv_hist_idx >= len(hv_history) and hv_hist_idx < 0:
                continue
            trailing = [hv_history[j] for j in range(max(0, hv_hist_idx - 252), hv_hist_idx + 1)
                        if hv_history[j] > 0]
            if trailing:
                hv_rank = sum(1 for v in trailing if v <= hv30 * 100) / len(trailing) * 100
                if hv_rank > hv_rank_max:
                    skipped["hv_rank_filter"] += 1
                    continue

            # ── Filter 3: Momentum + trend signal ─────────────────────────────
            if i < 25:
                continue
            c5   = float(closes.iloc[i - 5])
            sma20 = float(closes.iloc[i - 20: i].mean())
            ret5  = (S0 / c5 - 1) * 100
            ret1  = (S0 / float(closes.iloc[i - 1]) - 1) * 100  # today's move

            if option_type == "signal" or require_signal:
                bullish_signal = ret5 > 0.5 and S0 > sma20
                bearish_signal = ret5 < -0.5 and S0 < sma20
                if not bullish_signal and not bearish_signal:
                    skipped["no_signal"] += 1
                    continue
                if option_type == "signal":
                    trade_type = "call" if bullish_signal else "put"
                else:
                    # Fixed direction — must align with signal
                    if option_type == "call" and not bullish_signal:
                        skipped["no_signal"] += 1
                        continue
                    if option_type == "put" and not bearish_signal:
                        skipped["no_signal"] += 1
                        continue
                    trade_type = option_type
            else:
                trade_type = option_type if option_type != "signal" else "call"

            # Confidence-based position sizing (mirrors 7–40% linear scale)
            signal_strength = min(abs(ret5) / 3.0, 1.0)  # 0–1 scale (3% move = max)
            lo = risk_settings["min_position_pct"] / 100
            hi = risk_settings["max_position_pct"] / 100
            conf_pct = lo + signal_strength * (hi - lo)
            acct = risk_settings.get("account_size") or 0
            if acct:
                trade_dollars = round(acct * conf_pct, 2)
            else:
                trade_dollars = round(position_size_dollars * (0.5 + signal_strength * 0.5), 2)

            # ── Strike selection: find strike closest to delta_target ───────────
            T = dte_at_entry / 365.0
            best_strike = None
            best_delta_diff = 999
            for offset_pct in [x * 0.5 for x in range(-10, 16)]:  # -5% to +7.5% in 0.5% steps
                K_cand = round(S0 * (1 + offset_pct / 100), 2)
                g = _bs_greeks(S0, K_cand, T, RISK_FREE_RATE, hv30, trade_type)
                if not g:
                    continue
                d = abs(g.get("delta", 0))
                diff = abs(d - delta_target)
                if diff < best_delta_diff:
                    best_delta_diff = diff
                    best_strike = K_cand
                    best_entry_g = g

            if best_strike is None or not best_entry_g.get("bs_price") or best_entry_g["bs_price"] < 0.01:
                skipped["no_valid_strike"] += 1
                continue

            K        = best_strike
            entry_px = best_entry_g["bs_price"]
            stop_px  = entry_px * (1 - stop_loss_pct / 100)
            target_px = entry_px * (1 + profit_target_pct / 100)

            # ── Simulate holding through DTE ───────────────────────────────────
            exit_px     = None
            exit_reason = "expired"

            for d in range(1, dte_at_entry + 1):
                fi = i + d
                if fi >= n:
                    break
                S_now = float(closes.iloc[fi])
                T_now = max((dte_at_entry - d) / 365.0, 0)

                if T_now <= 0:
                    exit_px = max(0.0, S_now - K) if trade_type == "call" else max(0.0, K - S_now)
                    exit_reason = "expired"
                    break

                g = _bs_greeks(S_now, K, T_now, RISK_FREE_RATE, hv30, trade_type)
                opt_now = g.get("bs_price", 0.0) if g else 0.0

                if opt_now <= stop_px:
                    exit_px = opt_now
                    exit_reason = f"stop_loss ({stop_loss_pct}%)"
                    break
                if opt_now >= target_px:
                    exit_px = target_px              # cap at limit price, like a real limit order
                    exit_reason = f"profit_target ({profit_target_pct}%)"
                    break

            if exit_px is None:
                fi = min(i + dte_at_entry, n - 1)
                S_exp    = float(closes.iloc[fi])
                intrinsic = max(0.0, S_exp - K) if trade_type == "call" else max(0.0, K - S_exp)
                # Cap at profit target — mirrors live behaviour where a limit order
                # would have filled before expiry if the option reached the target
                exit_px  = min(intrinsic, target_px)

            pnl_pct     = round((exit_px / entry_px - 1) * 100, 1)
            pnl_dollars = round(trade_dollars * pnl_pct / 100, 2)
            simulated.append({
                "entry_date":       str(closes.index[i])[:10],
                "underlying_entry": round(S0, 2),
                "option_type":      trade_type,
                "strike":           K,
                "delta":            round(abs(best_entry_g.get("delta", 0)), 3),
                "entry_option_px":  round(entry_px, 4),
                "exit_option_px":   round(exit_px, 4),
                "exit_reason":      exit_reason,
                "pnl_pct":          pnl_pct,
                "pnl_dollars":      pnl_dollars,
                "position_dollars": trade_dollars,
                "hv30_as_iv":       round(hv30 * 100, 1),
                "signal_5d_ret":    round(ret5, 2),
            })

        if not simulated:
            return json.dumps({
                "error": "No valid simulated trades. Try wider parameters or disable filters.",
                "skipped": skipped,
            })

        wins    = [t for t in simulated if t["pnl_pct"] > 0]
        losses  = [t for t in simulated if t["pnl_pct"] <= 0]
        doubles = [t for t in simulated if t["pnl_pct"] >= profit_target_pct]
        stopped = [t for t in simulated if "stop_loss" in t["exit_reason"]]

        avg_pnl  = round(sum(t["pnl_pct"] for t in simulated) / len(simulated), 1)
        avg_win  = round(sum(t["pnl_pct"] for t in wins)   / len(wins),   1) if wins   else 0
        avg_loss = round(sum(t["pnl_pct"] for t in losses) / len(losses), 1) if losses else 0
        ev = round((len(wins)/len(simulated)) * avg_win + (len(losses)/len(simulated)) * avg_loss, 1)

        total_pnl_dollars        = round(sum(t["pnl_dollars"]      for t in simulated), 2)
        total_capital_deployed   = round(sum(t["position_dollars"]  for t in simulated), 2)
        total_return_pct         = round(
            total_pnl_dollars / total_capital_deployed * 100, 1
        ) if total_capital_deployed else 0

        # Build equity curve: running cumulative P&L + per-trade breakdown
        equity_curve = []
        cumulative_dollars = 0.0
        cumulative_capital = 0.0
        peak_dollars = 0.0
        max_dd_pct   = 0.0
        for trade in simulated:
            cumulative_dollars  = round(cumulative_dollars + trade["pnl_dollars"], 2)
            cumulative_capital += trade["position_dollars"]
            peak_dollars        = max(peak_dollars, cumulative_dollars)
            if peak_dollars > 0:
                dd = (peak_dollars - cumulative_dollars) / peak_dollars * 100
                max_dd_pct = max(max_dd_pct, dd)
            cum_return_pct = round(
                cumulative_dollars / cumulative_capital * 100, 2
            ) if cumulative_capital else 0.0
            equity_curve.append({
                "date":           trade["entry_date"],
                "cumulative_pnl": cumulative_dollars,
                "cum_return_pct": cum_return_pct,
                "trade_pnl_pct":  trade["pnl_pct"],
                "win":            trade["pnl_pct"] > 0,
            })

        return json.dumps({
            "symbol": symbol.upper(),
            "strategy": {
                "option_type":           option_type,
                "dte_at_entry":          dte_at_entry,
                "delta_target":          delta_target,
                "stop_loss_pct":         stop_loss_pct,
                "profit_target_pct":     profit_target_pct,
                "lookback_days":         lookback_days,
                "vix_max":               vix_max,
                "hv_rank_max":           hv_rank_max,
                "require_signal":        require_signal,
                "IMPORTANT_CAVEAT": (
                    "IV estimated from 30-day HV. Real options used actual implied vol, "
                    "which varies. This simulation shows if the STOCK made the required move, "
                    "not guaranteed option P&L. Use as directional signal, not precise forecast."
                ),
            },
            "filters": {
                "days_skipped_no_signal":    skipped["no_signal"],
                "days_skipped_vix_too_high": skipped["vix_filter"],
                "days_skipped_hv_rank_high": skipped["hv_rank_filter"],
                "days_skipped_no_strike":    skipped["no_valid_strike"],
                "days_traded":               len(simulated),
            },
            "results": {
                "trades_simulated":       len(simulated),
                "win_rate_pct":           round(len(wins)/len(simulated)*100, 1),
                "avg_pnl_pct":            avg_pnl,
                "expected_value_pct":     ev,
                "avg_winning_trade_pct":  avg_win,
                "avg_losing_trade_pct":   avg_loss,
                "hit_profit_target_pct":  round(len(doubles)/len(simulated)*100, 1),
                "stopped_out_pct":        round(len(stopped)/len(simulated)*100, 1),
                "expired_worthless_pct":  round(
                    sum(1 for t in simulated if t["exit_reason"]=="expired" and t["pnl_pct"]<-90)
                    / len(simulated) * 100, 1),
                "total_pnl_dollars":      total_pnl_dollars,
                "total_capital_deployed": total_capital_deployed,
                "total_return_pct":       total_return_pct,
                "max_drawdown_pct":       round(max_dd_pct, 1),
            },
            "equity_curve":  equity_curve,
            "best_trade":    max(simulated, key=lambda x: x["pnl_pct"]),
            "worst_trade":   min(simulated, key=lambda x: x["pnl_pct"]),
            "all_trades":    simulated,
        }, indent=2)

    except Exception as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


# ─── Strategy engine helpers (internal, not exposed as standalone tools) ──────

def _compute_tech_score_live(symbol: str, option_type: str = "call") -> float:
    """
    Fetch recent price history and compute a direction-aware technical setup score (0–100).

    Uses the same RSI + MACD + SMA formula as the optimizer's _tech_score():
      40% SMA trend (price / sma20 / sma50 alignment)
      35% RSI 14 positioning (momentum building in the right direction)
      25% MACD histogram direction

    Returns 50.0 (neutral) if data cannot be fetched.
    """
    try:
        hist = yf.Ticker(symbol).history(period="90d")["Close"].dropna()
        if len(hist) < 55:
            return 50.0
        p = hist.values.astype(float)
        n = len(p)
        idx = n - 1   # most recent day

        # SMA20 / SMA50
        sma20 = float(np.mean(p[idx - 20 : idx]))
        sma50 = float(np.mean(p[idx - 50 : idx]))
        price = float(p[idx])

        # RSI 14
        diffs = np.diff(p[idx - 15 : idx + 1])
        avg_up   = float(np.mean(diffs[diffs > 0])) if np.any(diffs > 0) else 0.0
        avg_down = float(np.mean(-diffs[diffs < 0])) if np.any(diffs < 0) else 0.0
        rs   = avg_up / (avg_down + 1e-9)
        rsi14 = 100.0 - 100.0 / (1.0 + rs)

        # MACD (EMA12 − EMA26)
        k12, k26 = 2.0 / 13.0, 2.0 / 27.0
        ema12 = ema26 = float(p[0])
        ema12_prev = ema26_prev = ema12
        for px in p[1:]:
            ema12_prev, ema26_prev = ema12, ema26
            ema12 = float(px) * k12 + ema12 * (1 - k12)
            ema26 = float(px) * k26 + ema26 * (1 - k26)
        macd      = ema12 - ema26
        macd_prev = ema12_prev - ema26_prev
        macd_rising = macd > macd_prev

        trade_type = option_type.lower()
        if trade_type == "call":
            trend  = (50.0 if price > sma20 else 0.0) + (50.0 if sma20 > sma50 else 0.0)
            rsi_s  = max(0.0, 100.0 - abs(rsi14 - 55.0) * (100.0 / 35.0))
            macd_s = 100.0 if macd > 0 and macd_rising else (50.0 if macd > 0 else 0.0)
        else:
            trend  = (50.0 if price < sma20 else 0.0) + (50.0 if sma20 < sma50 else 0.0)
            rsi_s  = max(0.0, 100.0 - abs(rsi14 - 45.0) * (100.0 / 35.0))
            macd_s = 100.0 if macd < 0 and not macd_rising else (50.0 if macd < 0 else 0.0)

        score = trend * 0.40 + rsi_s * 0.35 + macd_s * 0.25
        return round(float(score), 1)
    except Exception:
        return 50.0


def _compute_quality_score(iv_pct: float, delta_val: float, dte: int) -> float:
    """
    Option quality score (0-100): how good is the option to buy if direction is right?
    Components: IV rank (40%) + delta fit (35%) + DTE fit (25%)
    Independent of direction — purely about option economics.
    """
    import math as _math
    sp = STRATEGY_PROFILE

    iv_score    = max(0.0, 100.0 - iv_pct)   # 0th pct = 100, 100th pct = 0

    d_opt   = float(sp["targets"]["delta_optimal"])
    d_fall  = float(sp["targets"]["delta_falloff"])
    delta_score = 100.0 * _math.exp(-((abs(delta_val) - d_opt) ** 2) / (2 * d_fall ** 2))

    t_opt   = float(sp["targets"]["dte_optimal"])
    t_fall  = float(sp["targets"]["dte_falloff"])
    dte_score = max(0.0, 100.0 * (1.0 - abs(dte - t_opt) / max(t_fall, 1.0)))

    quality = iv_score * 0.40 + delta_score * 0.35 + dte_score * 0.25
    return round(min(100.0, max(0.0, quality)), 1)


def _compute_direction_score(
    tech_score: float,
    trade_type: str,     # "call" or "put"
    rsi14: float,
    ret5: float,         # 5-day % return of the underlying
    spy_ret5: float,     # 5-day % return of SPY (market regime)
) -> float:
    """
    Direction Score (0-100): how likely is the stock to move in the intended direction?

    Three weighted components:
      55% tech score        (RSI/MACD/SMA directional alignment)
      30% regime alignment  (SPY moving same direction as trade?)
      15% momentum strength (magnitude of 5-day move in trade direction)

    Minus an RSI overextension penalty (0-15 pts) for mean-reversion risk:
      if bullish and RSI > 72 → -15 pts; RSI > 68 → -8 pts
      if bearish and RSI < 28 → -15 pts; RSI < 32 → -8 pts
    """
    is_bullish = (trade_type == "call")

    # ── Regime alignment (0-100): is SPY moving with the trade? ──────────────
    spy_aligned  = (is_bullish and spy_ret5 > 0) or (not is_bullish and spy_ret5 < 0)
    spy_magnitude = abs(spy_ret5)
    if spy_magnitude < 0.5:
        regime_score = 50.0                              # flat market = neutral
    elif spy_aligned:
        regime_score = min(100.0, 50.0 + spy_magnitude * 16.7)   # 0.5% → 58, 3%+ → 100
    else:
        regime_score = max(0.0, 50.0 - spy_magnitude * 16.7)     # opposing = penalty

    # ── Momentum strength (0-100): how big is the move in the right direction? ─
    abs_ret5   = abs(ret5)
    mom_score  = min(100.0, abs_ret5 / 5.0 * 100.0)    # 5%+ move = full score

    # ── Weighted blend ────────────────────────────────────────────────────────
    raw = tech_score * 0.55 + regime_score * 0.30 + mom_score * 0.15

    # ── RSI overextension penalty ─────────────────────────────────────────────
    if is_bullish:
        penalty = 15.0 if rsi14 > 72 else (8.0 if rsi14 > 68 else 0.0)
    else:
        penalty = 15.0 if rsi14 < 28 else (8.0 if rsi14 < 32 else 0.0)

    return round(max(0.0, min(100.0, raw - penalty)), 1)


def _generate_trade_strategy(
    trade_type: str,
    direction_score: float,
    quality_score: float,
    iv_rank: float,
    rsi14: float,
    spy_ret5: float,
    est_premium: float,
    stop_loss_pct: float,
    profit_target_pct: float,
    stock_price: float,
    delta_est: float,
) -> dict:
    """
    Generate an adaptive TP/SL strategy for a single pick.

    Returns:
      sl_option_px   : option price at stop loss
      tp_option_px   : option price at take profit
      stock_sl       : underlying price where stop triggers
      stock_tp       : underlying price where target triggers
      label          : short table label (≤ 20 chars)
      comment        : 1-sentence strategy note
    """
    is_bullish   = (trade_type == "call")
    sl_option_px = round(est_premium * (1 - stop_loss_pct   / 100), 3)
    tp_option_px = round(est_premium * (1 + profit_target_pct / 100), 3)

    # Approximate underlying move needed to hit TP or SL via delta
    d = max(delta_est, 0.05)
    stock_move_to_tp = (est_premium * profit_target_pct / 100) / d
    stock_move_to_sl = (est_premium * stop_loss_pct    / 100) / d
    if is_bullish:
        stock_tp = round(stock_price + stock_move_to_tp, 2)
        stock_sl = round(stock_price - stock_move_to_sl, 2)
    else:
        stock_tp = round(stock_price - stock_move_to_tp, 2)
        stock_sl = round(stock_price + stock_move_to_sl, 2)

    spy_aligned = (is_bullish and spy_ret5 > 0) or (not is_bullish and spy_ret5 < 0)
    rsi_extreme = (is_bullish and rsi14 > 68) or (not is_bullish and rsi14 < 32)

    # Priority-ordered rule set — first match wins
    if rsi_extreme:
        label   = "⚠ RSI caution"
        comment = (
            f"RSI at {'overbought' if is_bullish else 'oversold'} extreme ({rsi14:.0f}) — "
            "mean-reversion risk is elevated. Exit immediately if momentum stalls; don't hold into expiry."
        )
    elif not spy_aligned and abs(spy_ret5) >= 1.5:
        label   = "⚠ Regime risk"
        comment = (
            f"SPY is moving {'up' if spy_ret5 > 0 else 'down'} {abs(spy_ret5):.1f}% while this trade fades "
            "the market. Reduce to 60% of normal size and take profit at 50–60% of target if reached."
        )
    elif iv_rank >= 65:
        label   = "Exit early"
        comment = (
            f"IV at {iv_rank:.0f}th percentile — options are expensive and IV crush can erode gains "
            "even on a winning move. Target 50–60% of full profit and exit before last 2 days."
        )
    elif direction_score >= 78 and quality_score >= 65 and spy_aligned:
        label   = "Hold to target"
        comment = (
            "High-conviction setup with market regime aligned. Hold to the full profit target; "
            "if the option doubles early, consider activating a trailing stop at 80% of peak value."
        )
    elif direction_score >= 65 and iv_rank <= 20:
        label   = "Let it breathe"
        comment = (
            f"IV very low ({iv_rank:.0f}th pct) — premium is cheap so theta decay is slow. "
            "Hold to the full target without rushing; the trade has time on its side."
        )
    elif direction_score < 60:
        label   = "Lighter size"
        comment = (
            "Direction signal is moderate. Consider half normal size; take profit at 60% of target "
            "and do not average in if the trade moves against you early."
        )
    else:
        label   = "Standard"
        comment = "Follow stop and target as set. No unusual risk factors detected."

    return {
        "sl_option_px": sl_option_px,
        "tp_option_px": tp_option_px,
        "stock_sl":     stock_sl,
        "stock_tp":     stock_tp,
        "label":        label,
        "comment":      comment,
    }


def scan_daily_top_trades(n_picks: int = 5, dte: int = None, min_confidence: float = 35.0, min_tech_score: float = 55.0) -> list:
    """
    Scan DEFAULT_WATCHLIST for the highest-confidence option setups right now.

    For each ticker:
      1. Fetch 90d price history
      2. Compute HV30, IV percentile, technical indicators
      3. Detect bullish (call) or bearish (put) momentum signal
      4. Score with the 4-component confidence formula
      5. Filter by min_confidence and positive EV

    Returns up to n_picks candidates sorted by confidence score descending.
    Each entry is a dict suitable for direct storage as a prediction record.
    """
    if dte is None:
        dte = int(STRATEGY_PROFILE["targets"]["dte_optimal"])

    sp                = STRATEGY_PROFILE
    stop_loss_pct     = float(sp["risk"]["stop_loss_pct"])
    profit_target_pct = float(sp["risk"]["profit_target_pct"])
    delta_target      = float(sp["targets"]["delta_optimal"])
    min_ev            = float(sp["filters"]["min_ev_return_pct"])
    T                 = dte / 365.0

    candidates: list[dict] = []

    # Fetch SPY regime data once for all tickers
    _spy_ret5 = 0.0
    try:
        _spy_hist = yf.Ticker("SPY").history(period="10d")["Close"].dropna()
        if len(_spy_hist) >= 6:
            _spy_ret5 = float((_spy_hist.iloc[-1] / _spy_hist.iloc[-6] - 1) * 100)
    except Exception:
        pass

    for ticker in DEFAULT_WATCHLIST:
        try:
            hist = yf.Ticker(ticker).history(period="90d")["Close"].dropna()
            if len(hist) < 55:
                continue
            prices = hist.values.astype(float)
            n      = len(prices)
            idx    = n - 1
            price  = float(prices[idx])

            # HV30
            log_rets = np.log(prices[1:] / prices[:-1])
            hv30 = float(np.std(log_rets[idx - 30 : idx]) * math.sqrt(252))
            if hv30 <= 0:
                continue

            # IV percentile (rank of today's hv30 vs 90-day rolling hv30 history)
            hv_hist = []
            for i in range(30, n):
                hv_i = float(np.std(log_rets[max(0, i - 30) : i]) * math.sqrt(252))
                if hv_i > 0:
                    hv_hist.append(hv_i)
            iv_pct = float(np.sum(np.array(hv_hist) <= hv30) / max(len(hv_hist), 1) * 100) if hv_hist else 50.0

            # Momentum signal (same logic as backtest)
            ret5  = (price / float(prices[idx - 5]) - 1) * 100
            sma20 = float(np.mean(prices[idx - 20 : idx]))
            sma50 = float(np.mean(prices[idx - 50 : idx]))

            bullish = ret5 >  0.3 and price > sma20
            bearish = ret5 < -0.3 and price < sma20
            if not bullish and not bearish:
                continue
            trade_type = "call" if bullish else "put"

            # RSI 14 (needed for direction score overextension penalty)
            _diffs   = np.diff(prices[max(0, idx - 15) : idx + 1])
            _avg_up  = float(np.mean(_diffs[_diffs > 0])) if np.any(_diffs > 0) else 0.0
            _avg_dn  = float(np.mean(-_diffs[_diffs < 0])) if np.any(_diffs < 0) else 0.0
            rsi14    = round(100.0 - 100.0 / (1.0 + _avg_up / (_avg_dn + 1e-9)), 1)

            # Technical setup score — gate early to avoid expensive strike search on weak setups
            tech = _compute_tech_score_live(ticker, trade_type)
            if tech < min_tech_score:
                continue

            # Find best strike near delta_target
            best_strike: float | None = None
            best_g:      dict  | None = None
            best_diff = 999.0
            for offset in [x * 0.5 for x in range(-10, 16)]:
                K = round(price * (1 + offset / 100), 2)
                g = _bs_greeks(price, K, T, RISK_FREE_RATE, hv30, trade_type)
                if not g:
                    continue
                diff = abs(abs(g.get("delta", 0)) - delta_target)
                if diff < best_diff:
                    best_diff   = diff
                    best_strike = K
                    best_g      = g

            if best_strike is None or not best_g or best_g.get("bs_price", 0) < 0.01:
                continue

            est_premium = float(best_g["bs_price"])
            delta_val   = abs(float(best_g.get("delta", 0)))

            # Direction Score: predicts if stock moves the right way (this is the headline)
            direction_score = _compute_direction_score(tech, trade_type, rsi14, ret5, _spy_ret5)
            if direction_score < min_confidence:
                continue

            # Quality Score: rates the option to buy if direction is right
            quality_score = _compute_quality_score(iv_pct, delta_val, dte)

            # Expected value gate (uses direction score as P(win))
            p_win  = direction_score / 100.0
            ev_pct = p_win * profit_target_pct - (1.0 - p_win) * stop_loss_pct
            if ev_pct < min_ev:
                continue

            # Build human-readable signal reasons
            reasons: list[str] = []
            if bullish:
                if price > sma20:  reasons.append(f"Price ${price:.0f} above SMA20 ${sma20:.0f}")
                if sma20 > sma50:  reasons.append("SMA20 above SMA50 — uptrend confirmed")
                reasons.append(f"+{ret5:.1f}% 5-day momentum")
            else:
                if price < sma20:  reasons.append(f"Price ${price:.0f} below SMA20 ${sma20:.0f}")
                if sma20 < sma50:  reasons.append("SMA20 below SMA50 — downtrend confirmed")
                reasons.append(f"{ret5:.1f}% 5-day momentum")
            if iv_pct < 30:
                reasons.append(f"Low IV rank ({iv_pct:.0f}th pct) — relatively cheap options")
            elif iv_pct > 70:
                reasons.append(f"High IV rank ({iv_pct:.0f}th pct) — options are expensive, consider smaller size")

            # Regime alignment reason
            if abs(_spy_ret5) >= 0.5:
                spy_dir = "rising" if _spy_ret5 > 0 else "falling"
                aligned = (bullish and _spy_ret5 > 0) or (bearish and _spy_ret5 < 0)
                reasons.append(f"SPY {spy_dir} {_spy_ret5:+.1f}% (regime {'aligned ✓' if aligned else 'opposing ✗'})")

            today_str   = datetime.now().strftime("%Y-%m-%d")
            _raw_target = datetime.now() + timedelta(days=dte + 2)
            # Roll forward to next weekday if target lands on weekend
            while _raw_target.weekday() >= 5:
                _raw_target += timedelta(days=1)
            target_str  = _raw_target.strftime("%Y-%m-%d")

            strategy = _generate_trade_strategy(
                trade_type=trade_type,
                direction_score=direction_score,
                quality_score=quality_score,
                iv_rank=iv_pct,
                rsi14=rsi14,
                spy_ret5=_spy_ret5,
                est_premium=est_premium,
                stop_loss_pct=stop_loss_pct,
                profit_target_pct=profit_target_pct,
                stock_price=price,
                delta_est=delta_val,
            )

            candidates.append({
                "ticker":             ticker,
                "direction":          trade_type,
                "confidence":         round(direction_score, 1),
                "direction_score":    round(direction_score, 1),
                "quality_score":      round(quality_score, 1),
                "tech_score":         round(tech, 1),
                "iv_rank":            round(iv_pct, 1),
                "delta_est":          round(delta_val, 2),
                "stock_price":        round(price, 2),
                "strike_est":         round(best_strike, 2),
                "dte":                dte,
                "est_premium":        round(est_premium, 4),
                "stop_loss_pct":      stop_loss_pct,
                "profit_target_pct":  profit_target_pct,
                "ev_pct":             round(ev_pct, 1),
                "ret5":               round(ret5, 2),
                "rsi14":              round(rsi14, 1),
                "spy_ret5":           round(_spy_ret5, 2),
                "entry_date":         today_str,
                "target_date":        target_str,
                "entry_price":        round(price, 2),
                "signal_reasons":     reasons,
                "strategy_label":     strategy["label"],
                "strategy_comment":   strategy["comment"],
                "sl_option_px":       strategy["sl_option_px"],
                "tp_option_px":       strategy["tp_option_px"],
                "stock_sl":           strategy["stock_sl"],
                "stock_tp":           strategy["stock_tp"],
                "type":               "daily_scan",
                "outcome":            None,
            })
        except Exception:
            continue

    candidates.sort(key=lambda x: x["confidence"], reverse=True)
    return candidates[:n_picks]


def _calculate_confidence_score(
    iv_percentile: float,
    delta: float,
    dte: int,
    tech_score: float = 50.0,   # 0–100 directional technical setup score
) -> dict:
    """
    Weighted confidence score 0–100 based on the STRATEGY_PROFILE weights.

    iv_percentile : lower IV rank = cheaper options = higher score
    delta         : peaks at delta_optimal, Gaussian fall-off
    dte           : peaks at dte_optimal, Gaussian fall-off
    tech_score    : RSI + MACD + SMA trend alignment (0-100, 50 = neutral)
                    weight controlled by STRATEGY_PROFILE["confidence_weights"]["technical"]
    """
    sp = STRATEGY_PROFILE
    # IV percentile: 0th → score 1.0, 100th → score 0.0
    iv_norm = max(0.0, 1.0 - iv_percentile / 100.0)

    # Delta: triangle peak at optimal
    d_opt = sp["targets"]["delta_optimal"]
    d_fall = sp["targets"]["delta_falloff"]
    delta_norm = max(0.0, 1.0 - abs(abs(delta) - d_opt) / d_fall)

    # DTE: triangle peak at optimal
    t_opt = sp["targets"]["dte_optimal"]
    t_fall = sp["targets"]["dte_falloff"]
    dte_norm = max(0.0, 1.0 - abs(dte - t_opt) / t_fall)

    # Technical: already 0-100, normalize to 0-1
    tech_norm = tech_score / 100.0

    w = sp["confidence_weights"]
    total_w = sum(w.values()) or 1.0
    raw = (
        w["iv_percentile"]        * iv_norm   * 100
        + w["delta"]              * delta_norm * 100
        + w["dte"]                * dte_norm   * 100
        + w.get("technical", 0.0) * tech_norm  * 100
    ) / total_w

    return {
        "confidence_score":      round(raw, 1),
        "iv_component":          round(iv_norm    * w["iv_percentile"]        / total_w * 100, 1),
        "delta_component":       round(delta_norm * w["delta"]                / total_w * 100, 1),
        "dte_component":         round(dte_norm   * w["dte"]                  / total_w * 100, 1),
        "tech_component":        round(tech_norm  * w.get("technical", 0.0)  / total_w * 100, 1),
        "tech_score_in":         round(tech_score, 1),
        "iv_percentile_in":      iv_percentile,
        "delta_in":              round(abs(delta), 3),
        "dte_in":                dte,
    }


def _check_trade_liquidity(bid: float, ask: float) -> dict:
    """
    Bid-ask spread as % of mid-price.
    If spread > 1.5% flag as illiquid and require 10% extra profit margin.
    """
    f = STRATEGY_PROFILE["filters"]
    if not bid or not ask or ask <= bid:
        return {
            "mid_price": None, "spread_pct": 999.0, "is_illiquid": True,
            "extra_margin_pct": f["illiquid_extra_margin_pct"],
            "flag": "⚠️ ILLIQUID — no valid bid/ask",
        }
    mid = (bid + ask) / 2.0
    spread_pct = (ask - bid) / mid * 100.0
    illiquid = spread_pct > f["liquidity_spread_max_pct"]
    return {
        "mid_price":       round(mid, 4),
        "spread_pct":      round(spread_pct, 2),
        "is_illiquid":     illiquid,
        "extra_margin_pct": f["illiquid_extra_margin_pct"] if illiquid else 0.0,
        "flag": (
            f"⚠️ ILLIQUID — spread {spread_pct:.1f}% > {f['liquidity_spread_max_pct']}%"
            f" — requires {f['illiquid_extra_margin_pct']:.0f}% extra profit margin"
            if illiquid else f"✅ Liquid — spread {spread_pct:.1f}%"
        ),
    }


def _get_market_regime(symbol: str) -> dict:
    """
    VIX + ATR regime detector.
    VIX > 25 → Defense Mode (50% position sizes).
    ATR expanding (14d > 28d avg by 5%) → stop-loss ×1.5.
    """
    sp = STRATEGY_PROFILE
    # VIX
    try:
        vix = float(yf.Ticker("^VIX").history(period="5d")["Close"].iloc[-1])
    except Exception:
        vix = 20.0

    # ATR (14-day vs 28-day to detect expansion)
    atr_14 = atr_28 = 0.0
    atr_expanding = False
    try:
        hist = yf.Ticker(symbol).history(period="45d")
        hi, lo, cl = hist["High"].values, hist["Low"].values, hist["Close"].values
        trs = [max(hi[i] - lo[i], abs(hi[i] - cl[i-1]), abs(lo[i] - cl[i-1]))
               for i in range(1, len(cl))]
        if len(trs) >= 28:
            atr_14 = float(np.mean(trs[-14:]))
            atr_28 = float(np.mean(trs[-28:]))
            atr_expanding = atr_14 > atr_28 * 1.05
        elif len(trs) >= 14:
            atr_14 = atr_28 = float(np.mean(trs[-14:]))
    except Exception:
        pass

    defense = vix > sp["filters"]["vix_defense_threshold"]
    stop_mult = sp["filters"]["atr_expansion_stop_mult"] if atr_expanding else 1.0
    pos_mult  = sp["filters"]["defense_position_mult"] if defense else 1.0

    notes = []
    if defense:
        notes.append(f"VIX {vix:.0f} > {sp['filters']['vix_defense_threshold']:.0f} → Defense Mode: position sizes halved")
    if atr_expanding:
        notes.append(f"ATR expanding ({atr_14:.3f} > {atr_28:.3f}) → stop-loss widened to {stop_mult:.1f}×")

    return {
        "vix":                    round(vix, 2),
        "atr_14d":                round(atr_14, 4),
        "atr_28d":                round(atr_28, 4),
        "atr_expanding":          atr_expanding,
        "defense_mode":           defense,
        "regime":                 "⚠️ DEFENSE" if defense else "✅ NORMAL",
        "position_size_mult":     pos_mult,
        "stop_loss_mult":         round(stop_mult, 1),
        "regime_notes":           notes if notes else ["Normal market conditions"],
    }


def _calculate_iv_skew(symbol: str, target_strike: float, option_type: str, expiry: str) -> dict:
    """
    Vertical skew: (OTM IV − ATM IV) / ATM IV for the target strike.
    Time skew: near-term ATM IV minus next-expiry ATM IV.
    IV crush check: if target IV > HV30_mean + 2σ, apply confidence penalty.
    """
    sp = STRATEGY_PROFILE
    ticker = yf.Ticker(symbol)
    spot = None
    atm_iv = target_iv = None
    vertical_skew = 0.0
    near_iv = far_iv = None
    time_skew = 0.0
    z_score = 0.0
    hv_mean = hv_std = None
    iv_crush_penalty = 0.0
    iv_crush_warning = ""

    # Get spot price
    try:
        spot = float(ticker.history(period="2d")["Close"].iloc[-1])
    except Exception:
        pass

    # Vertical skew from target expiry
    if spot is not None:
        try:
            chain = ticker.option_chain(expiry)
            opts = chain.calls if option_type.lower() == "call" else chain.puts
            opts = opts[opts["impliedVolatility"] > 0]

            atm_row = opts.iloc[(opts["strike"] - spot).abs().argsort()[:1]]
            tgt_row = opts.iloc[(opts["strike"] - target_strike).abs().argsort()[:1]]

            atm_iv    = round(float(atm_row["impliedVolatility"].values[0]) * 100, 2)
            target_iv = round(float(tgt_row["impliedVolatility"].values[0]) * 100, 2)
            vertical_skew = (target_iv - atm_iv) / atm_iv if atm_iv else 0.0
        except Exception:
            pass

    # Time skew: compare near vs next expiry ATM IV
    if spot is not None:
        try:
            exps = ticker.options
            if len(exps) >= 2:
                def _atm_iv(exp):
                    c = ticker.option_chain(exp)
                    o = c.calls if option_type.lower() == "call" else c.puts
                    o = o[o["impliedVolatility"] > 0]
                    r = o.iloc[(o["strike"] - spot).abs().argsort()[:1]]
                    return round(float(r["impliedVolatility"].values[0]) * 100, 2)
                near_iv = _atm_iv(exps[0])
                far_iv  = _atm_iv(exps[1])
                time_skew = near_iv - far_iv
        except Exception:
            pass

    # IV crush check: compare target IV to 30-day HV rolling distribution
    if target_iv is not None:
        try:
            hist90 = ticker.history(period="120d")
            log_rets = np.log(hist90["Close"] / hist90["Close"].shift(1)).dropna().values
            windows = [float(np.std(log_rets[i-30:i]) * math.sqrt(252) * 100)
                       for i in range(30, len(log_rets))]
            if windows:
                hv_mean = float(np.mean(windows))
                hv_std  = float(np.std(windows))
                z_score = (target_iv - hv_mean) / hv_std if hv_std > 0 else 0.0
                thresh  = sp["filters"]["iv_crush_z_threshold"]
                if z_score >= thresh:
                    iv_crush_penalty = sp["filters"]["iv_crush_confidence_penalty"]
                    iv_crush_warning = (
                        f"⚠️ IV CRUSH RISK: strike IV {target_iv:.1f}% is "
                        f"{z_score:.1f}σ above 30-day HV mean ({hv_mean:.1f}%) "
                        f"→ confidence reduced by {iv_crush_penalty:.0f} points"
                    )
        except Exception:
            pass

    v_note = (
        "OTM priced rich vs ATM"   if vertical_skew >  0.10 else
        "OTM priced cheap vs ATM"  if vertical_skew < -0.05 else
        "Normal vertical skew"
    )
    t_note = (
        "Near-term premium elevated"  if time_skew >  5 else
        "Near-term premium depressed" if time_skew < -3 else
        "Normal time structure"
    )

    return {
        "atm_iv":               atm_iv,
        "target_strike_iv":     target_iv,
        "vertical_skew_pct":    round(vertical_skew * 100, 2),
        "vertical_skew_note":   v_note,
        "near_expiry_atm_iv":   near_iv,
        "next_expiry_atm_iv":   far_iv,
        "time_skew":            round(time_skew, 2) if near_iv and far_iv else None,
        "time_skew_note":       t_note,
        "iv_zscore_vs_hv30":    round(z_score, 2),
        "hv30_mean":            round(hv_mean, 2) if hv_mean else None,
        "hv30_std":             round(hv_std,  2) if hv_std  else None,
        "iv_crush_penalty_pts": iv_crush_penalty,
        "iv_crush_warning":     iv_crush_warning,
    }


def _calculate_ev(delta: float, avg_win_pct: float, avg_loss_pct: float,
                  capital_at_risk: float, extra_margin_pct: float = 0.0,
                  confidence: float = None) -> dict:
    """
    EV = (P_profit × avg_win) − (P_loss × avg_loss)
    Uses confidence score (0–100) as P(profit) when available; falls back to
    |delta| only if confidence is not supplied.
    Trade signal fires only when EV ≥ min_ev_return_pct (10%) AND EV > 0.
    Extra margin requirement raised if option is illiquid.
    """
    sp = STRATEGY_PROFILE
    if confidence is not None:
        p_win = min(max(confidence / 100.0, 0.01), 0.99)
    else:
        p_win = min(abs(delta), 0.99)
    p_loss = 1.0 - p_win
    ev_pct    = (p_win * avg_win_pct) - (p_loss * abs(avg_loss_pct))
    ev_dollars = capital_at_risk * ev_pct / 100.0
    threshold = sp["filters"]["min_ev_return_pct"] + extra_margin_pct
    signal = ev_pct > 0 and ev_pct >= threshold
    return {
        "p_profit":           round(p_win, 3),
        "p_loss":             round(p_loss, 3),
        "avg_win_pct":        avg_win_pct,
        "avg_loss_pct":       avg_loss_pct,
        "ev_pct":             round(ev_pct, 2),
        "ev_dollars":         round(ev_dollars, 2),
        "required_ev_pct":    round(threshold, 1),
        "trade_signal":       signal,
        "ev_note": (
            f"✅ EV {ev_pct:.1f}% ≥ {threshold:.0f}% required" if signal
            else f"❌ EV {ev_pct:.1f}% < {threshold:.0f}% required"
        ),
    }


def evaluate_trade_signal(
    symbol: str,
    option_type: str,
    strike: float,
    expiry: str,
    bid: float = None,
    ask: float = None,
    delta: float = None,
    iv_percentile: float = None,
    dte: int = None,
    position_dollars: float = 1000.0,
    avg_win_pct: float = 80.0,
    avg_loss_pct: float = 40.0,
) -> str:
    """
    Master trade evaluator — runs every strategy filter and returns a unified signal.

    Combines:
      1. Confidence score (IV rank, Delta, DTE, Technical setup — weights optimizer-tuned)
      2. IV vertical + time skew; IV crush penalty if OTM IV > HV mean + 2σ
      3. Liquidity check — flags illiquid spreads and adjusts required profit margin
      4. Market regime — VIX + ATR expansion (Defense Mode, stop-loss widening)
      5. EV formula — (P_win × avg_win) − (P_loss × avg_loss) using delta as P_win proxy
    """
    try:
        out: dict = {
            "symbol":      symbol.upper(),
            "option_type": option_type,
            "strike":      strike,
            "expiry":      expiry,
        }

        # ── 1. Confidence score (IV rank + delta + DTE + technical setup) ─────
        confidence_score = None
        if iv_percentile is not None and delta is not None and dte is not None:
            tech = _compute_tech_score_live(symbol, option_type)
            conf = _calculate_confidence_score(iv_percentile, delta, dte, tech_score=tech)
            confidence_score = conf["confidence_score"]
            out["confidence"] = conf

        # ── 2. IV skew + crush check ──────────────────────────────────────────
        iv_crush_penalty = 0.0
        skew = _calculate_iv_skew(symbol, strike, option_type, expiry)
        out["iv_skew"] = skew
        iv_crush_penalty = skew["iv_crush_penalty_pts"]
        if confidence_score is not None and iv_crush_penalty > 0:
            adjusted = max(0.0, confidence_score - iv_crush_penalty)
            out["confidence"]["adjusted_score"]    = round(adjusted, 1)
            out["confidence"]["iv_crush_penalty"]  = -iv_crush_penalty
            confidence_score = adjusted

        # ── 3. Liquidity check ────────────────────────────────────────────────
        extra_margin = 0.0
        if bid is not None and ask is not None:
            liq = _check_trade_liquidity(bid, ask)
            extra_margin = liq["extra_margin_pct"]
            out["liquidity"] = liq

        # ── 4. Market regime ──────────────────────────────────────────────────
        regime = _get_market_regime(symbol)
        out["market_regime"] = regime

        base_stop   = risk_settings["stop_loss_pct"]
        adj_stop    = round(base_stop * regime["stop_loss_mult"], 1)
        adj_dollars = round(position_dollars * regime["position_size_mult"], 2)
        out["adjusted_parameters"] = {
            "position_dollars":  adj_dollars,
            "stop_loss_pct":     adj_stop,
            "profit_target_pct": STRATEGY_PROFILE["risk"]["profit_target_pct"],
            "regime_notes":      regime["regime_notes"],
        }

        # ── 5. EV calculation ─────────────────────────────────────────────────
        ev_signal = False
        if delta is not None:
            ev = _calculate_ev(delta, avg_win_pct, avg_loss_pct, adj_dollars, extra_margin,
                               confidence=confidence_score)
            ev_signal = ev["trade_signal"]
            out["expected_value"] = ev

        # ── 6. Overall recommendation ─────────────────────────────────────────
        blocks   = []
        warnings = []

        if confidence_score is not None and confidence_score < 40:
            blocks.append(f"Confidence too low ({confidence_score:.0f}/100)")
        if skew["iv_crush_warning"]:
            warnings.append(skew["iv_crush_warning"])
        if out.get("liquidity", {}).get("is_illiquid"):
            warnings.append(out["liquidity"]["flag"])
        if regime["defense_mode"]:
            warnings.append(f"⚠️ Defense Mode — VIX {regime['vix']:.0f}")
        if not ev_signal and delta is not None:
            blocks.append(out.get("expected_value", {}).get("ev_note", "EV check failed"))

        if not blocks and ev_signal:
            rec = "✅ PROCEED" if (confidence_score or 0) >= 60 else "⚠️ PROCEED WITH CAUTION"
        else:
            rec = "❌ AVOID" if blocks else "⚠️ CAUTION"

        out["recommendation"] = {
            "signal":   rec,
            "warnings": warnings,
            "blocks":   blocks,
            "summary":  (
                f"{rec} | Confidence {confidence_score:.0f}/100"
                if confidence_score is not None else rec
            ),
        }

        return json.dumps(out, indent=2)

    except Exception as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


# ─── Tool definitions ──────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "get_stock_snapshot",
        "description": (
            "Get current stock price, today's open/high/low, volume, and percent change. "
            "Call this first for any specific ticker to get the underlying price."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string", "description": "Ticker, e.g. 'AAPL'"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "get_options_chain",
        "description": (
            "Fetch the options chain with Black-Scholes Greeks (delta, gamma, theta, vega), "
            "IV, volume, open interest, bid/ask, and break-even. Returns top 40 by volume. "
            "Use for deep analysis of a single ticker."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "option_type": {"type": "string", "enum": ["call", "put"],
                                "description": "Omit for both."},
                "max_dte": {"type": "integer", "default": 21,
                            "description": "Max days to expiration. Use 1 for 0DTE."},
                "expiration_date": {"type": "string",
                                    "description": "Specific date YYYY-MM-DD (optional)."},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "screen_options",
        "description": (
            "Scan options across multiple tickers at once. "
            "Best for finding hottest plays across the market. Max 6 tickers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbols": {"type": "array", "items": {"type": "string"},
                            "description": "List of tickers (max 6)."},
                "option_type": {"type": "string", "enum": ["call", "put", "both"], "default": "both"},
                "max_dte": {"type": "integer", "default": 21},
                "min_volume": {"type": "integer", "default": 100},
            },
            "required": ["symbols"],
        },
    },
    {
        "name": "find_high_leverage_options",
        "description": (
            "PURPOSE-BUILT for 'double my money' / '100% gain' requests. "
            "Screens options across high-beta large-caps and ranks them by "
            "'move_needed_pct' — the smallest % move the underlying needs to make "
            "the option approximately double in value. Lower move_needed_pct = easier path to 2x. "
            "Also shows leverage_per_contract ($ gain per 1% move) and gamma_efficiency. "
            "ALWAYS use this tool when user asks for 100%+ gain potential or wants to double their money."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tickers to scan (max 8). Defaults to high-beta watchlist if omitted.",
                },
                "option_type": {
                    "type": "string",
                    "enum": ["call", "put", "both"],
                    "description": "Use 'call' for bullish plays, 'put' for bearish. Default 'both'.",
                    "default": "both",
                },
                "max_dte": {
                    "type": "integer",
                    "description": "Max days to expiration. Default 14 for 2-week window.",
                    "default": 14,
                },
                "min_volume": {
                    "type": "integer",
                    "description": "Minimum daily volume. Default 50.",
                    "default": 50,
                },
                "max_move_needed_pct": {
                    "type": "number",
                    "description": "Only show options that need less than this % move to double. Default 12.",
                    "default": 12.0,
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_expirations",
        "description": "List available options expiration dates within 21 days for a ticker.",
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "get_iv_analysis",
        "description": (
            "ALWAYS call this before recommending options on a ticker. "
            "Returns: HV10/30/60 (realized vol), HV Rank 0-100 (how elevated vol is vs past year), "
            "current ATM implied volatility, and IV vs HV spread (positive = options expensive). "
            "Tells you whether to favor buying or selling premium."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string", "description": "Stock ticker"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "get_earnings_info",
        "description": (
            "ALWAYS call this before recommending options on a single stock (not ETFs). "
            "Returns next earnings date and days until earnings. "
            "Earnings within your DTE = IV crush risk for buyers, opportunity for sellers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "get_market_context",
        "description": (
            "Get the current market regime: VIX level and trend, SPY/QQQ price trend, "
            "and overall options environment (buyer's vs seller's market). "
            "Call this at the start of any broad market scan or when user asks about overall conditions."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_put_call_ratio",
        "description": (
            "Calculate the put/call volume and OI ratio for a ticker across all near-term expirations. "
            "Shows directional sentiment, most active strikes, and per-expiration breakdown. "
            "P/C > 1.2 = bearish flow. P/C < 0.8 = bullish flow."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "max_dte": {"type": "integer", "default": 21,
                            "description": "Max DTE to include in ratio. Default 21."},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "calculate_position_size",
        "description": (
            "ALWAYS call this after identifying a specific trade to recommend. "
            "Given an option price, account size, and your confidence score (1-10), returns "
            "the number of contracts, total dollar risk, stop-loss price, and drawdown impact. "
            "Confidence scales risk linearly: 1=7% of account, 10=40% of account. "
            "Be honest — only use 8-10 when you have strong conviction from multiple confirming signals."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "option_price": {
                    "type": "number",
                    "description": "Mid price of the option (e.g. 1.45)",
                },
                "account_size": {
                    "type": "number",
                    "description": "User's account size in dollars. Use stored value if already known.",
                },
                "dte": {
                    "type": "integer",
                    "description": "Days to expiration — 0DTE always uses the 2% hard cap regardless of confidence.",
                    "default": 5,
                },
                "confidence": {
                    "type": "integer",
                    "description": (
                        "Your confidence in this trade on a 1–10 scale. "
                        "Maps linearly to position size: 1→7%, 5→~21%, 10→40% of account. "
                        "1-3: weak signal, high uncertainty. "
                        "4-6: moderate edge, decent setup. "
                        "7-8: strong confluence of signals. "
                        "9-10: exceptional setup — multiple strong confirming factors, ideal conditions."
                    ),
                    "default": 5,
                },
                "max_risk_pct": {
                    "type": "number",
                    "description": "Hard override for risk %. Ignores confidence scale. Leave blank normally.",
                },
            },
            "required": ["option_price"],
        },
    },
    {
        "name": "manage_risk_settings",
        "description": (
            "Read or update any part of the strategy profile — confidence weights, entry filters, "
            "market-regime rules, and risk/exit parameters. "
            "Call with no arguments to show the full current configuration. "
            "Call with any subset of arguments to apply only those changes. "
            "Always call this when the user mentions account size, risk tolerance, position sizing, "
            "stop-loss, profit targets, IV thresholds, VIX rules, EV filters, delta targets, or DTE targets."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                # ── Risk / exit ───────────────────────────────────────────────
                "account_size":         {"type": "number",  "description": "Total trading account size in dollars"},
                "max_drawdown_pct":     {"type": "number",  "description": "Pause all trading after this % portfolio drawdown (default 15)"},
                "stop_loss_pct":        {"type": "number",  "description": "Exit when option loses this % of premium paid (default 50)"},
                "profit_target_pct":    {"type": "number",  "description": "Take profit when option gains this % of premium paid (default 100)"},
                "min_position_pct":     {"type": "number",  "description": "Minimum position size as % of account — floor for low-confidence trades (default 7)"},
                "max_position_pct":     {"type": "number",  "description": "Maximum position size as % of account — ceiling for high-confidence trades (default 40)"},
                "dte_0_max_pct":        {"type": "number",  "description": "Cap 0DTE trades to this % of account (default 2)"},
                # ── Market regime / defense ───────────────────────────────────
                "vix_defense_threshold":     {"type": "number",  "description": "VIX level that triggers defense mode — cut position sizes (default 25)"},
                "defense_position_mult":     {"type": "number",  "description": "Multiply all position sizes by this in defense mode, e.g. 0.5 = half size (default 0.5)"},
                "atr_expansion_stop_mult":   {"type": "number",  "description": "Widen stop-loss by this multiplier when ATR expands (default 1.5)"},
                # ── Entry filters ─────────────────────────────────────────────
                "min_ev_return_pct":         {"type": "number",  "description": "Minimum expected-value return on capital to emit a trade signal (default 8)"},
                "liquidity_spread_max_pct":  {"type": "number",  "description": "Max bid/ask spread as % of mid price before the liquidity gate blocks a trade (default 10)"},
                "illiquid_extra_margin_pct": {"type": "number",  "description": "Extra EV margin required when option is near the liquidity boundary (default 5)"},
                "iv_crush_z_threshold":      {"type": "number",  "description": "Z-score above 30-day HV mean at which we penalise for IV-crush risk (default 1.5)"},
                "iv_crush_confidence_penalty": {"type": "number","description": "Confidence points subtracted when IV crush risk is detected (default 15)"},
                # ── Targets (confidence scoring) ──────────────────────────────
                "delta_target":    {"type": "number",  "description": "Optimal delta for peak confidence score, e.g. 0.30 (default 0.30)"},
                "dte_target":      {"type": "integer", "description": "Optimal DTE at entry for peak confidence score, e.g. 7 (default 7)"},
            },
            "required": [],
        },
    },
    {
        "name": "log_paper_trade",
        "description": (
            "Paper trading journal — log, track, and close options trades to measure real performance. "
            "Use action='add' to log a new trade after recommending it. "
            "Use action='list' to show all trades and the win rate / total P&L summary. "
            "Use action='check' to estimate current P&L for open trades using live prices + Black-Scholes. "
            "Use action='close' to record the final exit price and lock in the result. "
            "ALWAYS offer to log a trade after giving a specific recommendation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action":            {"type": "string", "enum": ["add", "list", "check", "close"],
                                      "description": "What to do: add/list/check/close"},
                "symbol":            {"type": "string", "description": "Ticker e.g. NVDA"},
                "option_type":       {"type": "string", "enum": ["call", "put"]},
                "strike":            {"type": "number", "description": "Strike price"},
                "expiration":        {"type": "string", "description": "Expiration date YYYY-MM-DD"},
                "entry_price":       {"type": "number", "description": "Option mid price at entry"},
                "underlying_entry":  {"type": "number", "description": "Stock price at entry"},
                "contracts":         {"type": "integer", "default": 1},
                "notes":             {"type": "string", "description": "Optional trade thesis/notes"},
                "trade_id":          {"type": "integer", "description": "For check/close actions"},
                "exit_price":        {"type": "number", "description": "Option price at exit (for close)"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "log_prediction",
        "description": (
            "Daily market prediction tracker — log directional predictions and grade them automatically when the target date arrives. "
            "action='log': record a new prediction (ticker, direction=bullish/bearish, target_move_pct, target_date, confidence 1-10, reasoning). "
            "Entry price is fetched automatically. "
            "action='grade': fetch actual prices and score all ungraded predictions whose target date has passed. "
            "Outcomes: 'hit' (direction + ~magnitude correct), 'directional' (direction only), 'miss'. "
            "action='list': show all predictions and overall accuracy stats. "
            "action='delete': remove a prediction by prediction_id. "
            "Make a prediction each day and grade previous ones to build a real track record."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action":           {"type": "string", "enum": ["log", "grade", "list", "delete"],
                                     "description": "What to do"},
                "ticker":           {"type": "string", "description": "Stock/ETF ticker e.g. NVDA"},
                "direction":        {"type": "string", "enum": ["bullish", "bearish"],
                                     "description": "Predicted price direction"},
                "target_move_pct":  {"type": "number",
                                     "description": "Expected % move (e.g. 3.5 for +3.5%). Positive = up."},
                "target_date":      {"type": "string",
                                     "description": "Date by which the move should happen YYYY-MM-DD (default: 5 days)"},
                "confidence":       {"type": "integer", "minimum": 1, "maximum": 10,
                                     "description": "Conviction 1-10"},
                "reasoning":        {"type": "string",
                                     "description": "Why you expect this move"},
                "prediction_id":    {"type": "integer",
                                     "description": "For delete action"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "backfill_predictions",
        "description": (
            "Retroactively generates and grades daily directional predictions for every past trading day. "
            "For each day in the lookback window it computes a momentum+trend signal (5-day return vs 20-day SMA), "
            "logs a bullish or bearish prediction at that day's open price, then grades it immediately using the "
            "actual close on the target date. Skips neutral/ambiguous days. "
            "Use this to build a historical track record so the bot can see what its signal is actually good at. "
            "Safe to re-run — won't duplicate entries unless overwrite=True."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tickers":       {"type": "array", "items": {"type": "string"},
                                  "description": "List of tickers to backfill (default: SPY QQQ NVDA TSLA AAPL META AMD)"},
                "lookback_days": {"type": "integer", "default": 90,
                                  "description": "How many calendar days back to generate predictions for"},
                "horizon_days":  {"type": "integer", "default": 5,
                                  "description": "How many trading days forward each prediction targets"},
                "overwrite":     {"type": "boolean", "default": False,
                                  "description": "If true, regenerate predictions even if that date already exists"},
            },
            "required": [],
        },
    },
    {
        "name": "backtest_strategy",
        "description": (
            "Backtests the bot's ACTUAL trading methodology over historical price data. "
            "Applies the same entry filters the bot uses live: momentum+trend signal, VIX proxy filter, "
            "HV rank filter, and delta-targeted strike selection. Position size scales with signal confidence. "
            "Shows win rate, avg P&L, expected value, total dollar P&L, and equity curve. "
            "Use when the user asks 'how would this strategy have performed?' or wants to validate "
            "the bot's approach before risking real money. "
            "IMPORTANT: IV is estimated from 30-day HV — treat as directional signal, not exact P&L."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol":                {"type": "string",  "description": "Ticker to backtest, e.g. NVDA"},
                "option_type":           {"type": "string",  "enum": ["call", "put", "signal"],
                                          "description": "'signal' auto-selects direction from momentum (default)", "default": "signal"},
                "dte_at_entry":          {"type": "integer", "description": "DTE when buying each option (e.g. 7, 14)", "default": 7},
                "delta_target":          {"type": "number",  "description": "Target BS delta for strike selection (0.15–0.45, default 0.30)", "default": 0.30},
                "lookback_days":         {"type": "integer", "description": "Trading days of history to test (252 = ~1 year)", "default": 252},
                "stop_loss_pct":         {"type": "number",  "description": "Exit if option loses this % (default 50)", "default": 50.0},
                "profit_target_pct":     {"type": "number",  "description": "Take profit at this % gain (default 100 = 2x)", "default": 100.0},
                "position_size_dollars": {"type": "number",  "description": "Base dollar size per trade; scales with signal confidence. Default: 10% of account or $1000"},
                "vix_max":               {"type": "number",  "description": "Skip days when estimated market vol > this (default 35)", "default": 35.0},
                "hv_rank_max":           {"type": "number",  "description": "Skip days when HV rank > this percentile (default 80)", "default": 80.0},
                "require_signal":        {"type": "boolean", "description": "Only trade on momentum+trend signal days (default true)", "default": True},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "evaluate_trade_signal",
        "description": (
            "Master trade evaluator — runs ALL strategy filters on a specific option contract "
            "and returns a unified PROCEED / CAUTION / AVOID signal. "
            "Always call this before recommending a specific options contract. "
            "Computes: (1) Confidence score weighted by IV rank 40%, delta 30%, DTE 30%. "
            "(2) IV vertical + time skew; penalises confidence by 20 pts if OTM IV is >2σ above "
            "30-day HV mean (IV crush risk). "
            "(3) Liquidity check — flags bid-ask spread > 1.5% of mid and requires 10% extra profit margin. "
            "(4) Market regime — VIX + ATR; Defense Mode halves position size, expanding ATR widens stop 1.5×. "
            "(5) EV formula: EV = (delta × avg_win) − ((1−delta) × avg_loss); signal only if EV ≥ 10%."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol":          {"type": "string",  "description": "Ticker, e.g. NVDA"},
                "option_type":     {"type": "string",  "enum": ["call", "put"]},
                "strike":          {"type": "number",  "description": "Strike price"},
                "expiry":          {"type": "string",  "description": "Expiration date YYYY-MM-DD"},
                "bid":             {"type": "number",  "description": "Current bid price"},
                "ask":             {"type": "number",  "description": "Current ask price"},
                "delta":           {"type": "number",  "description": "Option delta (positive number, e.g. 0.30)"},
                "iv_percentile":   {"type": "number",  "description": "IV rank/percentile 0-100 (from get_iv_analysis)"},
                "dte":             {"type": "integer", "description": "Days to expiration"},
                "position_dollars":{"type": "number",  "description": "Dollar size before regime adjustments", "default": 1000},
                "avg_win_pct":     {"type": "number",  "description": "Expected % gain when trade wins (default 80 = 0.8x)", "default": 80},
                "avg_loss_pct":    {"type": "number",  "description": "Expected % loss when trade loses (default 40)", "default": 40},
            },
            "required": ["symbol", "option_type", "strike", "expiry"],
        },
    },
]

TOOL_DISPATCH = {
    "get_stock_snapshot":         get_stock_snapshot,
    "get_options_chain":          get_options_chain,
    "screen_options":             screen_options,
    "find_high_leverage_options": find_high_leverage_options,
    "get_expirations":            get_expirations,
    "get_iv_analysis":            get_iv_analysis,
    "get_earnings_info":          get_earnings_info,
    "get_market_context":         get_market_context,
    "get_put_call_ratio":         get_put_call_ratio,
    "calculate_position_size":    calculate_position_size,
    "manage_risk_settings":       manage_risk_settings,
    "log_paper_trade":            log_paper_trade,
    "log_prediction":             log_prediction,
    "backfill_predictions":       backfill_predictions,
    "backtest_strategy":          backtest_strategy,
    "evaluate_trade_signal":      evaluate_trade_signal,
}


def run_tool(name: str, inputs: dict) -> str:
    fn = TOOL_DISPATCH.get(name)
    if not fn:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        return fn(**inputs)
    except Exception as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


# ─── Claude CLI via subprocess ─────────────────────────────────────────────────

def _build_tool_schema_text() -> str:
    lines = [
        "Call tools one at a time using this exact format:\n"
        "<tool_call>{\"tool\": \"name\", \"args\": {...}}</tool_call>\n"
        "\nAvailable tools:"
    ]
    for tool in TOOLS:
        desc = tool["description"].split("\n")[0][:120]
        props = tool["input_schema"].get("properties", {})
        req = tool["input_schema"].get("required", [])
        args = ", ".join(f"{k}{'*' if k in req else ''}" for k in props)
        lines.append(f"\n{tool['name']}({args})\n  {desc}")
    return "\n".join(lines)


def _build_prompt(messages: list) -> str:
    parts = ["CONVERSATION:\n"]
    for msg in messages:
        role = msg["role"].upper()
        content = msg["content"]
        if isinstance(content, str):
            parts.append(f"{role}: {content}\n\n")
        elif isinstance(content, list):
            chunks = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                t = item.get("type", "")
                if t == "text" and item.get("text"):
                    chunks.append(_strip_tool_calls(item["text"]))
                elif t == "tool_result":
                    result = item.get("content", "")
                    if len(result) > 3000:
                        result = result[:3000] + "...[truncated]"
                    chunks.append(f"<tool_result>{result}</tool_result>")
            if chunks:
                parts.append(f"{role}: {''.join(chunks)}\n\n")
    parts.append("ASSISTANT:")
    return "".join(parts)


def _find_claude() -> str:
    """Return the path to the claude executable, searching common Windows locations."""
    # 1. Already on PATH
    found = shutil.which("claude")
    if found:
        return found
    # 2. Windows App (Claude Desktop) install — version number varies, take newest
    pattern = os.path.expanduser(
        "~/AppData/Local/Packages/Claude_*/LocalCache/Roaming/Claude/claude-code/*/claude.exe"
    )
    matches = sorted(glob.glob(pattern))
    if matches:
        return matches[-1]
    # 3. VS Code extension copy — also version-numbered, take newest
    pattern2 = os.path.expanduser(
        "~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude.exe"
    )
    matches2 = sorted(glob.glob(pattern2))
    if matches2:
        return matches2[-1]
    return "claude"  # will raise FileNotFoundError with original message


def _call_claude_cli(prompt: str, system: str = "") -> str:
    try:
        cmd = [_find_claude(), "-p", "--tools", "", "--no-session-persistence"]
        if system:
            cmd += ["--system-prompt", system]
        result = subprocess.run(
            cmd,
            input=prompt, capture_output=True, text=True,
            timeout=120, encoding="utf-8",
        )
        if result.returncode != 0 and result.stderr:
            return f"[CLI Error: {result.stderr[:200]}]"
        return result.stdout.strip()
    except FileNotFoundError:
        return "[Error: 'claude' command not found. Ensure Claude Code is installed.]"
    except subprocess.TimeoutExpired:
        return "[Error: Claude CLI timed out after 120s.]"
    except Exception as e:
        return f"[Error calling Claude CLI: {e}]"


def _parse_tool_calls(response: str) -> list:
    matches = re.findall(r'<tool_call>(.*?)</tool_call>', response, re.DOTALL)
    calls = []
    for i, m in enumerate(matches):
        try:
            data = json.loads(m.strip())
            data["_id"] = f"call_{i}"
            calls.append(data)
        except json.JSONDecodeError:
            pass
    return calls


def _strip_tool_calls(text: str) -> str:
    return re.sub(r'<tool_call>.*?</tool_call>', '', text, flags=re.DOTALL).strip()


# ─── Conversation history trimmer ─────────────────────────────────────────────

MAX_HISTORY = 20  # max messages to keep (10 user/assistant exchanges)


def _trim_history(conversation: list) -> list:
    """Drop oldest messages when history grows long, preserving turn structure."""
    if len(conversation) <= MAX_HISTORY:
        return conversation
    trimmed = conversation[-MAX_HISTORY:]
    # Never start with an assistant turn — drop until we hit a user message
    while trimmed and trimmed[0]["role"] == "assistant":
        trimmed = trimmed[1:]
    return trimmed


# ─── System prompt ─────────────────────────────────────────────────────────────

def _get_system_prompt() -> str:
    """Build the system prompt dynamically from STRATEGY_PROFILE so any slider
    changes in the Risk Engine tab are immediately reflected in Claude's instructions."""
    sp  = STRATEGY_PROFILE
    cw  = sp["confidence_weights"]
    tgt = sp["targets"]
    flt = sp["filters"]
    rsk = sp["risk"]

    iv_w    = round(cw["iv_percentile"] * 100)
    d_w     = round(cw["delta"]         * 100)
    dte_w   = round(cw["dte"]           * 100)

    illiq_total = round(flt["min_ev_return_pct"] + flt["illiquid_extra_margin_pct"])

    return f"""You are an expert options trading advisor specializing in US large-cap equity options.
You operate using a defined strategy called the **OTM Short-Duration Momentum Strategy**.

## Core Strategy
- **Universe**: High-liquidity large-caps and ETFs — SPY, QQQ, AAPL, NVDA, TSLA, META, MSFT, AMZN, GOOGL, AMD, NFLX, COIN, PLTR, and similar
- **Instrument**: Single-leg long calls or puts only (no spreads, no naked shorts)
- **Timeframe**: 5–21 DTE preferred; 0DTE only for high-conviction binary setups capped at {rsk["dte_0_max_pct"]:.0f}%
- **Strike**: Target delta {tgt["delta_optimal"] - tgt["delta_falloff"]:.2f}–{tgt["delta_optimal"] + tgt["delta_falloff"]:.2f} OTM (sweet spot: {tgt["delta_optimal"]:.2f})
- **Entry gate**: All five filters must clear before a trade is recommended (see evaluate_trade_signal)

## Confidence Score (0–100)
Your internal confidence in any trade is computed from three inputs with fixed weights:
- **IV Rank/Percentile** ({iv_w}%): lower IV rank = cheaper options = higher score
- **Delta** ({d_w}%): score peaks at delta {tgt["delta_optimal"]:.2f}, falls off linearly toward {tgt["delta_optimal"] - tgt["delta_falloff"]:.2f} or {tgt["delta_optimal"] + tgt["delta_falloff"]:.2f}
- **DTE** ({dte_w}%): score peaks at {tgt["dte_optimal"]} DTE, falls off toward 0 or {tgt["dte_optimal"] + tgt["dte_falloff"]}+
After computing, apply adjustments:
- **IV Crush Penalty**: if OTM option's IV is >{flt["iv_crush_z_threshold"]:.1f}σ above 30-day HV mean → subtract {flt["iv_crush_confidence_penalty"]:.0f} confidence points
- Final score ≥ 60 → PROCEED; 40–59 → PROCEED WITH CAUTION; < 40 → AVOID

## Liquidity Gate
- Compute bid-ask spread as % of mid-price
- Spread > {flt["liquidity_spread_max_pct"]:.1f}% → flag as ILLIQUID → require {flt["illiquid_extra_margin_pct"]:.0f}% higher profit margin in EV calculation
- Spread > 20% of mid → automatic veto (system prompt rule)

## Market Regime
- VIX > {flt["vix_defense_threshold"]:.0f} → **Defense Mode**: cut all position sizes by {round((1 - flt["defense_position_mult"]) * 100):.0f}%
- ATR (14-day) > ATR (28-day) × 1.05 → **ATR Expanding**: widen stop-loss by {flt["atr_expansion_stop_mult"]:.1f}×
- VIX > 35 → **Do not buy options** (premiums extreme, mean reversion expected)

## EV Filter
EV = (P_profit × avg_win%) − (P_loss × avg_loss%)  where P_profit = |delta|
- Only emit a trade signal if EV ≥ {flt["min_ev_return_pct"]:.0f}% return on capital at risk
- Illiquid options raise the threshold to {illiq_total}% ({flt["min_ev_return_pct"]:.0f}% base + {flt["illiquid_extra_margin_pct"]:.0f}% illiquidity penalty)

## MANDATORY: evaluate_trade_signal Before Any Recommendation
Whenever you are about to recommend a specific options contract, you MUST call
`evaluate_trade_signal` with the contract's delta, IV percentile, DTE, bid, ask,
strike, and expiry. Use the result to:
1. Report the confidence score and its components
2. Flag any IV crush risk, liquidity issues, or regime warnings
3. Show the EV calculation
4. Only recommend the trade if the overall signal is PROCEED or PROCEED WITH CAUTION
   with a clear explanation of any caveats

## Workflow: "100% Gain / Double My Money" Requests
When a user asks for trades that can 100%+ within days, follow this exact sequence:
1. `get_market_context` — confirm market regime (avoid buying in extreme fear/VIX spike)
2. `find_high_leverage_options` — run with `max_dte` matching their window, `option_type` matching their bias
3. For the top 3–5 candidates: call `get_iv_analysis` and `get_earnings_info` to validate
4. For the best 2–3 candidates: call `evaluate_trade_signal` to get full signal check
5. Rank final picks by: highest confidence score + positive EV + liquid + earnings NOT in window
6. Present top 2–3 specific contracts with full breakdown including evaluate_trade_signal output

**Key math for 2x trades:**
- `move_needed_pct` = (option_mid / |delta|) / stock_price × 100
- Lower = easier. A 5% move target is very achievable; 15%+ is a long shot.
- OTM options (delta 0.20–0.35) with 3–7 DTE are the sweet spot: cheap enough to 2x on a moderate move, enough time for the move to happen
- High gamma_efficiency = the option accelerates faster as the stock moves your way

## Standard Analysis Workflow (follow this order)

**For any specific stock recommendation:**
1. `get_market_context` — understand the macro regime (VIX, trend)
2. `get_stock_snapshot` — get current price and daily action
3. `get_iv_analysis` — assess whether options are cheap or expensive (HV rank, IV vs HV)
4. `get_earnings_info` — check for earnings within the DTE window (critical risk)
5. `get_put_call_ratio` — read the flow sentiment
6. `get_options_chain` — pull the actual contracts, filtered by your thesis
7. `evaluate_trade_signal` — **mandatory for any specific contract recommendation**; pass delta, iv_percentile (from get_iv_analysis), DTE, bid, ask, strike, expiry

**For broad market scans:**
1. `get_market_context` first
2. `screen_options` across relevant tickers
3. Drill down with `get_iv_analysis` and `get_earnings_info` on best candidates
4. `evaluate_trade_signal` on the finalist contracts

## Greeks Framework

**Delta**: Directional exposure per $1 underlying move; rough probability of expiring ITM
- 0.70–0.90 (deep ITM): high conviction, behaves like stock, expensive
- 0.45–0.55 (ATM): balanced, ~50% probability ITM, maximum gamma
- 0.20–0.40 (OTM): leveraged, needs meaningful move, cheaper premium
- <0.15 (far OTM): lottery ticket — only for high-conviction fast moves

**Gamma**: Delta acceleration — peaks at ATM, explodes near expiry
- 0DTE gamma is extreme: a 0.5% move can swing delta by 0.20+
- High gamma = explosive upside AND downside

**Theta**: Daily time decay (shown in $ per day, negative for long positions)
- Final 3 days: theta accelerates dramatically — expect to lose value fast even if stock flat
- 0DTE: theta is irrelevant — the option lives or dies by close

**Vega**: Sensitivity to IV change ($ per 1% IV move)
- Pre-earnings: IV rises → long options gain vega value
- Post-earnings: IV crushes 30-60% in hours → devastates long options

## IV Interpretation (from get_iv_analysis)
- **HV Rank > 70**: Vol historically elevated → premium selling favored, buying is expensive
- **HV Rank < 30**: Vol historically depressed → buying is cheap, strong conviction can pay off
- **IV spread > +15%**: Options pricing in more than they've historically moved — sell premium
- **IV spread < -5%**: Options underpriced vs realized moves — favorable for buyers

## Put/Call Ratio Signals (from get_put_call_ratio)
- **P/C > 1.5**: Heavy put buying — market fears downside or bearish speculation
- **P/C 0.8–1.2**: Neutral — no strong directional bias in flow
- **P/C < 0.6**: Heavy call buying — bullish speculation or squeeze potential

## Earnings Risk (from get_earnings_info)
- Earnings within DTE → IV will SPIKE into the event then CRUSH 30-60% after
- Buying pre-earnings: exit BEFORE the print to capture IV expansion, not to hold through
- Selling pre-earnings: richest premium window — sell 1-5 days before, let IV crush pay you
- Post-earnings: IV crush creates opportunity to buy cheap options if stock still has momentum

## VIX Context (from get_market_context)
- VIX < 15: Cheap options broadly, good buying environment
- VIX 15-22: Normal, evaluate each name individually
- VIX > 25: Expensive options — selling premium or being very selective with buys
- VIX rising sharply: Uncertainty increasing, consider protective puts

## For Every Recommendation, Provide
1. **Contract**: TICKER — CALL/PUT — $STRIKE — EXPIRY (X DTE)
2. **Cost**: Mid price × 100 = total premium / max loss for longs
3. **Break-even**: Underlying price needed at expiry to profit
4. **Delta**: Sensitivity + rough ITM probability
5. **Theta**: Daily decay in dollars
6. **Move needed**: % change in underlying required for profitability
7. **Risk**: Max loss (longs = premium paid; naked short calls = UNLIMITED — always flag)
8. **IV context**: Is this option cheap or expensive given HV rank?
9. **Conviction**: Why this contract, what's the edge

## Risk Management Framework

**Every recommendation MUST include position sizing. Always call `calculate_position_size` after selecting a contract — and always pass a `confidence` score.**

### Confidence-Based Position Sizing
Risk scales linearly with your conviction. Be honest — inflating confidence costs the user real money.

| Confidence | Risk % | When to use |
|------------|--------|-------------|
| 1–3 | 7–18% | Weak signal, high uncertainty, mixed indicators |
| 4–6 | 18–29% | Decent setup, moderate edge, most typical trades |
| 7–8 | 29–36% | Strong confluence — trend + IV + earnings all align |
| 9–10 | 36–40% | Exceptional — rare, high-conviction, ideal conditions |

**What raises confidence:** trend confirmed, IV cheap (rank < 30), no earnings risk, strong flow (P/C signal), catalyst present, multiple timeframes aligned.
**What lowers confidence:** mixed signals, elevated VIX, earnings within DTE, wide bid/ask, weak volume, thesis unclear.

### Default Risk Rules (adjustable via `manage_risk_settings`)
| Rule | Current | Purpose |
|------|---------|---------|
| Min per-trade risk | {rsk["min_position_pct"]:.0f}% of account | Floor for lowest-confidence trades |
| Max per-trade risk | {rsk["max_position_pct"]:.0f}% of account | Ceiling for highest-confidence trades |
| Max drawdown | {rsk["max_drawdown_pct"]:.0f}% of account | Pause trading after large cumulative loss |
| Stop-loss | {rsk["stop_loss_pct"]:.0f}% of premium | Exit before full premium loss |
| Profit target | {rsk["profit_target_pct"]:.0f}% of premium | Take profit at this gain |
| 0DTE cap | {rsk["dte_0_max_pct"]:.0f}% of account | 0DTE is binary — confidence scaling disabled |

### Stop-Loss Rules by DTE
- **0DTE**: No stop needed (expires same day) — but size to {rsk["dte_0_max_pct"]:.0f}% max. Accept binary outcome.
- **1–3 DTE**: Hard stop at {rsk["stop_loss_pct"]:.0f}% premium loss. Theta decay is brutal; cut losers fast.
- **4–14 DTE**: Stop at {rsk["stop_loss_pct"]:.0f}% premium loss OR if thesis is invalidated (stock breaks key level).
- **Never average down** on a losing short-DTE option — theta accelerates against you.

### Drawdown Protection Logic
- {rsk["max_drawdown_pct"]:.0f}% max drawdown = stop trading / review after losing {rsk["max_drawdown_pct"]:.0f}% of total account
- After hitting 50% of drawdown limit ({rsk["max_drawdown_pct"] / 2:.1f}% down): reduce position size by 50%

### When to Skip a Trade (Risk Veto)
- VIX > 35: Do NOT buy options — premiums are extreme, mean reversion expected
- Earnings within DTE unless explicitly trading the earnings move
- Option bid/ask spread > 20% of mid price — too illiquid, bad fills
- IV rank > 85: Strongly avoid buying premium — options are historically expensive

### If Account Size Is Unknown
If the user hasn't told you their account size yet, ask before giving position sizing.
Once they tell you, call `manage_risk_settings(account_size=X)` to store it.

## Paper Trading Journal (log_paper_trade)
After giving a specific trade recommendation, ALWAYS offer to log it. Say:
"Want me to log this in your paper trading journal so we can track how it performs?"
- action="add": log a new trade after recommending it
- action="check": estimate current P&L for all open trades
- action="list": show all trades + win rate / P&L summary
- action="close": record exit price and finalize result

## Daily Predictions (log_prediction)
You maintain a running track record of directional market predictions. This is how you learn what you're good at and where you're wrong.

**When to make a prediction:**
- At the start of each trading day (or when asked), scan the watchlist and pick 2–3 high-conviction setups
- Use `get_market_context` + `get_stock_snapshot` + `get_iv_analysis` before predicting
- Be specific: ticker, direction (bullish/bearish), expected % move, target date, confidence score (1–10), and brief reasoning

**Workflow:**
1. `log_prediction(action="grade")` first — grade any predictions whose target date has passed
2. `log_prediction(action="list")` — review your accuracy stats before making new calls
3. Make 2–3 new predictions: `log_prediction(action="log", ticker=..., direction=..., target_move_pct=..., ...)`
4. Present predictions to the user with your reasoning

**Grading:**
- "hit" = direction correct AND magnitude within 50% of target
- "directional" = direction correct but move smaller than expected
- "miss" = direction wrong

**Be honest about your edge.** If your hit rate is below 50%, your directional bias is no better than a coin flip.
Always include win rate and directional accuracy in your report.

## Backtesting (backtest_strategy)
When a user asks "how would this have performed?" or wants to test a strategy:
1. Run `backtest_strategy` with their parameters
2. Explain the win rate, expected value, and how often the 2x target was hit
3. Compare to realistic benchmarks (random 50% would give EV near 0)
4. ALWAYS mention the key caveat: IV is estimated from HV — real option prices
   depend on actual implied vol at the time, which this simulation approximates.
5. Use results to REFINE strategy (adjust DTE, offset, or ticker selection)

Key backtest metrics to highlight:
- `win_rate_pct`: % of trades that were profitable at exit
- `expected_value_pct`: average P&L per trade (positive = edge)
- `hit_profit_target_pct`: % of trades that doubled
- `stopped_out_pct`: % of trades that hit stop loss

## Data Notes
- Market data from Yahoo Finance (~15-min delayed)
- Greeks calculated via Black-Scholes from live IV
- HV Rank uses realized vol as proxy (true IV rank requires paid historical IV data)
- Backtest IV estimated from 30-day historical vol — treat as directional signal
- This is analysis only — not financial advice. Total premium loss is always possible.

## Scan Watchlist (for broad market scans without specific tickers)
{{watchlist}}

Today: {{datetime}}  |  Risk-free rate: {{rfr}}%
"""

# SYSTEM_PROMPT is intentionally removed — use _get_system_prompt() which reads live from STRATEGY_PROFILE


# ─── Main chat loop ─────────────────────────────────────────────────────────────

def chat():
    conversation = []
    system = _get_system_prompt().format(
        watchlist=", ".join(DEFAULT_WATCHLIST),
        datetime=datetime.now().strftime("%A, %Y-%m-%d %H:%M ET"),
        rfr=round(RISK_FREE_RATE * 100, 1),
    ) + "\n\n## Tool Calling\n" + _build_tool_schema_text()

    print()
    print("=" * 66)
    print("  📈  Options Trading Assistant  —  Enhanced Edition")
    print("  Claude Sonnet 4.6  x  Yahoo Finance (free, ~15-min delayed)")
    print("  13 tools: Greeks · IV Rank · Earnings · VIX · P/C Ratio")
    print("    · 2x Screener · Position Sizing · Risk Management")
    print("    · Paper Trading Journal · Strategy Backtester")
    print("  Scope: Large-cap single-leg | 0–21 DTE | 15% max drawdown")
    print("=" * 66)
    print()
    print("  STEP 1 — Tell the bot your account size so it can size every")
    print("           trade safely (required for position sizing):")
    print('    "My account is $10,000"')
    print()
    print("  STEP 2 — Try asking:")
    print()
    print("  [ Market Overview ]")
    print('    "What\'s the market setup right now — should I be buying or selling premium?"')
    print('    "What does the VIX say about options pricing today?"')
    print()
    print("  [ Find Trades ]")
    print('    "Find me the best option trade to double my money within 2 weeks"')
    print('    "Scan the market for the hottest calls right now"')
    print('    "Best NVDA calls this week — are options cheap or expensive?"')
    print()
    print("  [ Specific Analysis ]")
    print('    "Analyze TSLA — I\'m bearish, what put should I buy?"')
    print('    "Show me SPY 0DTE options and the put/call ratio"')
    print('    "Does AAPL have earnings coming up that would affect my trade?"')
    print()
    print("  [ Backtest a Strategy ]")
    print('    "Backtest buying NVDA 5% OTM calls with 7 DTE over the past year"')
    print('    "How would buying weekly SPY puts have performed in the last 6 months?"')
    print('    "Test a TSLA call strategy — 3% OTM, 14 DTE, 50% stop, 2x target"')
    print()
    print("  [ Paper Trading Journal ]")
    print('    "Log this trade in my paper trading journal"')
    print('    "How are my open paper trades doing right now?"')
    print('    "Show me my paper trading win rate and total P&L"')
    print('    "Close trade #3 — I sold it for $2.10"')
    print()
    print("  [ Risk & Sizing ]")
    print('    "How many contracts of the NVDA $X call should I buy?"')
    print('    "What is my max drawdown limit and how many losing trades until I hit it?"')
    print('    "Change my stop-loss to 40% and max trade risk to 3%"')
    print()
    print("  Type 'quit' to exit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye! Trade safe. 📈")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye", "q"):
            print("Goodbye! Trade safe. 📈")
            break

        conversation.append({"role": "user", "content": user_input})
        print()

        while True:
            raw = _call_claude_cli(_build_prompt(_trim_history(conversation)), system=system)

            tool_calls = _parse_tool_calls(raw)
            visible_text = _strip_tool_calls(raw)

            if visible_text:
                print(f"Assistant: {visible_text}")

            if not tool_calls:
                conversation.append({"role": "assistant", "content": visible_text or raw})
                print()
                break

            # Execute each tool call and collect results
            tool_results = []
            for call in tool_calls:
                tool_name = call.get("tool", "")
                tool_args = call.get("args", {})
                arg_str = json.dumps(tool_args)
                preview = arg_str[:72] + ("..." if len(arg_str) > 72 else "")
                print(f"  🔍 {tool_name}({preview})")
                result = run_tool(tool_name, tool_args)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": call["_id"],
                    "content": result,
                })

            # Add assistant turn and tool results to conversation history
            conversation.append({"role": "assistant", "content": [{"type": "text", "text": raw}]})
            conversation.append({"role": "user", "content": tool_results})


if __name__ == "__main__":
    chat()
