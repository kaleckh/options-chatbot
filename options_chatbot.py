#!/usr/bin/env python3
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
"""

import os
import re
import json
import math
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
risk_settings = {
    "account_size":       None,    # set by user — e.g. 10000
    "max_drawdown_pct":   15.0,    # max portfolio drawdown before stopping (%)
    "max_per_trade_pct":   5.0,    # max % of account risked on one trade
    "stop_loss_pct":      50.0,    # exit when option loses this % of premium
    "dte_0_max_pct":       2.0,    # 0DTE trades capped at 2% of account (binary)
}

PAPER_TRADES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trades.json")


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
) -> str:
    """
    Calculates safe position sizing for a single options trade.

    Uses risk_settings defaults unless overrides are provided.
    Returns max contracts, total dollar risk, stop-loss levels, and
    a drawdown impact warning.
    """
    acct  = account_size  or risk_settings["account_size"]
    risk_pct = max_risk_pct or (
        risk_settings["dte_0_max_pct"] if dte == 0 else risk_settings["max_per_trade_pct"]
    )

    if not acct:
        return json.dumps({
            "error": "Account size not set.",
            "fix": "Tell me your account size (e.g. 'my account is $10,000') and I'll size the trade for you.",
        })

    max_risk_dollars  = round(acct * risk_pct / 100, 2)
    cost_per_contract = round(option_price * 100, 2)
    max_contracts     = max(1, int(max_risk_dollars / cost_per_contract))
    actual_risk       = round(max_contracts * cost_per_contract, 2)
    pct_of_account    = round(actual_risk / acct * 100, 2)

    stop_loss_pct   = risk_settings["stop_loss_pct"]
    stop_loss_value = round(option_price * (1 - stop_loss_pct / 100), 2)
    stop_loss_loss  = round(actual_risk * stop_loss_pct / 100, 2)

    drawdown_pct    = round(actual_risk / acct * 100, 2)
    max_dd          = risk_settings["max_drawdown_pct"]
    trades_to_limit = int(max_dd / risk_pct) if risk_pct else 0

    warning = None
    if pct_of_account > risk_settings["max_per_trade_pct"] * 1.5:
        warning = f"⚠️  This position exceeds the recommended {risk_settings['max_per_trade_pct']}% per-trade limit."
    if dte == 0:
        warning = (warning or "") + " ⚠️  0DTE is binary — size conservatively, full loss is common."

    return json.dumps({
        "account_size":        acct,
        "option_price":        option_price,
        "cost_per_contract":   cost_per_contract,
        "risk_settings": {
            "max_per_trade_pct": risk_pct,
            "max_drawdown_pct":  max_dd,
            "stop_loss_pct":     stop_loss_pct,
        },
        "sizing": {
            "max_contracts":     max_contracts,
            "total_cost":        actual_risk,
            "pct_of_account":    pct_of_account,
            "max_loss_if_zero":  actual_risk,
        },
        "stop_loss": {
            "exit_at_option_price": stop_loss_value,
            "loss_if_stopped":      stop_loss_loss,
            "pct_of_account_lost":  round(stop_loss_loss / acct * 100, 2),
            "rule": f"Exit if option drops {stop_loss_pct}% from entry",
        },
        "drawdown_context": {
            "this_trade_impact_pct":    drawdown_pct,
            "trades_until_15pct_limit": trades_to_limit,
            "warning": warning,
        },
    }, indent=2)


# ─── Tool 10: Update risk settings ────────────────────────────────────────────

def manage_risk_settings(
    account_size: float = None,
    max_drawdown_pct: float = None,
    max_per_trade_pct: float = None,
    stop_loss_pct: float = None,
    dte_0_max_pct: float = None,
) -> str:
    """
    Update the global risk settings (account size, drawdown limit, per-trade risk, stop-loss).
    Call this whenever the user mentions their account size or wants to change risk limits.
    Returns the current settings after applying any changes.
    """
    if account_size    is not None: risk_settings["account_size"]     = account_size
    if max_drawdown_pct is not None: risk_settings["max_drawdown_pct"] = max_drawdown_pct
    if max_per_trade_pct is not None: risk_settings["max_per_trade_pct"] = max_per_trade_pct
    if stop_loss_pct   is not None: risk_settings["stop_loss_pct"]    = stop_loss_pct
    if dte_0_max_pct   is not None: risk_settings["dte_0_max_pct"]    = dte_0_max_pct

    acct = risk_settings["account_size"]
    result = {"current_risk_settings": risk_settings.copy()}

    if acct:
        max_trade  = round(acct * risk_settings["max_per_trade_pct"] / 100, 2)
        max_0dte   = round(acct * risk_settings["dte_0_max_pct"] / 100, 2)
        dd_limit   = round(acct * risk_settings["max_drawdown_pct"] / 100, 2)
        result["dollar_limits"] = {
            "max_per_trade":        max_trade,
            "max_per_0dte_trade":   max_0dte,
            "max_total_drawdown":   dd_limit,
            "trades_until_dd_limit": int(risk_settings["max_drawdown_pct"] / risk_settings["max_per_trade_pct"]),
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


# ─── Tool 12: Historical strategy backtester ──────────────────────────────────

def backtest_strategy(
    symbol: str,
    option_type: str = "call",
    dte_at_entry: int = 7,
    strike_offset_pct: float = 3.0,
    lookback_days: int = 252,
    stop_loss_pct: float = 50.0,
    profit_target_pct: float = 100.0,
) -> str:
    """
    Simulates buying options at regular intervals over historical price data.

    Every 5 trading days over the lookback period:
      - Entry: buy an option with dte_at_entry days to expiration
      - Strike: stock_price × (1 + offset%) for calls, (1 - offset%) for puts
      - IV proxy: 30-day historical volatility at time of entry
      - Exit: hit profit target, stop loss, or hold to expiration

    Returns win rate, expected value, and sample trade breakdown.

    IMPORTANT LIMITATION: Uses historical volatility as IV proxy. Real option
    prices depend on actual implied vol at the time, which may differ significantly.
    This tests whether the STOCK moved enough — not the actual option P&L.
    """
    try:
        fetch_days = lookback_days + dte_at_entry + 90
        t = yf.Ticker(symbol.upper())
        hist = t.history(period=f"{fetch_days}d")
        if hist.empty or len(hist) < 60:
            return json.dumps({"error": f"Not enough price history for {symbol}"})

        closes = hist["Close"].dropna()
        n = len(closes)
        simulated = []

        # Simulate a trade entry every 5 trading days
        for i in range(30, min(n - dte_at_entry - 1, lookback_days + 30), 5):
            S0 = float(closes.iloc[i])

            # 30-day HV as IV proxy
            log_rets = [math.log(float(closes.iloc[j]) / float(closes.iloc[j-1]))
                        for j in range(i - 30, i) if j > 0]
            if len(log_rets) < 20:
                continue
            hv30 = float(np.std(log_rets) * math.sqrt(252))
            if hv30 <= 0:
                continue

            K = round(S0 * (1 + strike_offset_pct/100), 2) if option_type == "call" \
                else round(S0 * (1 - strike_offset_pct/100), 2)

            entry_g = _bs_greeks(S0, K, dte_at_entry/365.0, RISK_FREE_RATE, hv30, option_type)
            if not entry_g or not entry_g.get("bs_price") or entry_g["bs_price"] < 0.01:
                continue

            entry_px = entry_g["bs_price"]
            stop_px   = entry_px * (1 - stop_loss_pct / 100)
            target_px = entry_px * (1 + profit_target_pct / 100)

            exit_px = None
            exit_reason = "expired"

            for d in range(1, dte_at_entry + 1):
                fi = i + d
                if fi >= n:
                    break
                S_now = float(closes.iloc[fi])
                T_now = max((dte_at_entry - d) / 365.0, 0)

                if T_now <= 0:
                    exit_px = max(0.0, S_now - K) if option_type == "call" else max(0.0, K - S_now)
                    exit_reason = "expired"
                    break

                g = _bs_greeks(S_now, K, T_now, RISK_FREE_RATE, hv30, option_type)
                opt_now = g.get("bs_price", 0.0) if g else 0.0

                if opt_now <= stop_px:
                    exit_px = opt_now
                    exit_reason = f"stop_loss ({stop_loss_pct}%)"
                    break
                if opt_now >= target_px:
                    exit_px = opt_now
                    exit_reason = f"profit_target ({profit_target_pct}%)"
                    break

            if exit_px is None:
                fi = min(i + dte_at_entry, n - 1)
                S_exp = float(closes.iloc[fi])
                exit_px = max(0.0, S_exp - K) if option_type == "call" else max(0.0, K - S_exp)

            pnl_pct = round((exit_px / entry_px - 1) * 100, 1)
            simulated.append({
                "entry_date":       str(closes.index[i])[:10],
                "underlying_entry": round(S0, 2),
                "strike":           K,
                "entry_option_px":  round(entry_px, 4),
                "exit_option_px":   round(exit_px, 4),
                "exit_reason":      exit_reason,
                "pnl_pct":          pnl_pct,
                "hv30_as_iv":       round(hv30 * 100, 1),
            })

        if not simulated:
            return json.dumps({"error": "No valid simulated trades. Try wider parameters."})

        wins    = [t for t in simulated if t["pnl_pct"] > 0]
        losses  = [t for t in simulated if t["pnl_pct"] <= 0]
        doubles = [t for t in simulated if t["pnl_pct"] >= profit_target_pct]
        stopped = [t for t in simulated if "stop_loss" in t["exit_reason"]]

        avg_pnl  = round(sum(t["pnl_pct"] for t in simulated) / len(simulated), 1)
        avg_win  = round(sum(t["pnl_pct"] for t in wins)   / len(wins),   1) if wins   else 0
        avg_loss = round(sum(t["pnl_pct"] for t in losses) / len(losses), 1) if losses else 0
        ev = round((len(wins)/len(simulated)) * avg_win + (len(losses)/len(simulated)) * avg_loss, 1)

        return json.dumps({
            "symbol": symbol.upper(),
            "strategy": {
                "option_type":        option_type,
                "dte_at_entry":       dte_at_entry,
                "strike_offset_pct":  strike_offset_pct,
                "stop_loss_pct":      stop_loss_pct,
                "profit_target_pct":  profit_target_pct,
                "lookback_days":      lookback_days,
                "IMPORTANT_CAVEAT":   (
                    "IV estimated from 30-day HV. Real options used actual implied vol, "
                    "which varies. This simulation shows if the STOCK made the required move, "
                    "not guaranteed option P&L. Use as directional signal, not precise forecast."
                ),
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
            },
            "best_trade":  max(simulated, key=lambda x: x["pnl_pct"]),
            "worst_trade": min(simulated, key=lambda x: x["pnl_pct"]),
            "recent_10_trades": simulated[-10:],
        }, indent=2)

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
            "Given an option price and account size, returns the maximum safe number of contracts, "
            "total dollar risk, stop-loss trigger price, and drawdown impact. "
            "Enforces the 15% max drawdown rule and per-trade risk limits."
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
                "max_risk_pct": {
                    "type": "number",
                    "description": "Override max risk % for this trade. Leave blank to use default.",
                },
                "dte": {
                    "type": "integer",
                    "description": "Days to expiration — 0DTE uses a tighter 2% cap.",
                    "default": 5,
                },
            },
            "required": ["option_price"],
        },
    },
    {
        "name": "manage_risk_settings",
        "description": (
            "Call this whenever the user mentions their account size or wants to change risk limits. "
            "Stores account size, max drawdown %, per-trade risk %, stop-loss %, and 0DTE cap. "
            "Also call to show the user their current risk configuration."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_size":      {"type": "number", "description": "Total trading account size in dollars"},
                "max_drawdown_pct":  {"type": "number", "description": "Max portfolio drawdown before pausing (default 15)"},
                "max_per_trade_pct": {"type": "number", "description": "Max % of account risked per trade (default 5)"},
                "stop_loss_pct":     {"type": "number", "description": "Exit when option loses this % of premium (default 50)"},
                "dte_0_max_pct":     {"type": "number", "description": "Max % of account for 0DTE trades (default 2)"},
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
        "name": "backtest_strategy",
        "description": (
            "Backtests an options buying strategy on historical price data. "
            "Simulates buying an OTM call or put every 5 trading days over the past year (or custom period). "
            "Shows win rate, average P&L, expected value, how often the 2x target was hit, "
            "and how often stop loss was triggered. "
            "Use this when the user asks 'how would this strategy have performed?' or wants to validate "
            "an approach before risking real money. "
            "IMPORTANT: IV is estimated from historical volatility — treat as directional signal, not exact P&L."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol":             {"type": "string", "description": "Ticker to backtest, e.g. NVDA"},
                "option_type":        {"type": "string", "enum": ["call", "put"], "default": "call"},
                "dte_at_entry":       {"type": "integer", "description": "DTE when buying each option (e.g. 7, 14)", "default": 7},
                "strike_offset_pct":  {"type": "number",  "description": "% OTM at entry — 3 means 3% out of the money", "default": 3.0},
                "lookback_days":      {"type": "integer", "description": "Trading days of history to test over (252 = ~1 year)", "default": 252},
                "stop_loss_pct":      {"type": "number",  "description": "Exit if option loses this % (default 50)", "default": 50.0},
                "profit_target_pct":  {"type": "number",  "description": "Take profit at this % gain (default 100 = 2x)", "default": 100.0},
            },
            "required": ["symbol"],
        },
    },
]

TOOL_DISPATCH = {
    "get_stock_snapshot":       get_stock_snapshot,
    "get_options_chain":        get_options_chain,
    "screen_options":           screen_options,
    "find_high_leverage_options": find_high_leverage_options,
    "get_expirations":          get_expirations,
    "get_iv_analysis":     get_iv_analysis,
    "get_earnings_info":   get_earnings_info,
    "get_market_context":  get_market_context,
    "get_put_call_ratio":        get_put_call_ratio,
    "calculate_position_size":   calculate_position_size,
    "manage_risk_settings":      manage_risk_settings,
    "log_paper_trade":           log_paper_trade,
    "backtest_strategy":         backtest_strategy,
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


def _build_prompt(messages: list, system: str) -> str:
    parts = [system, "\n\n---\n\nCONVERSATION:\n"]
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
                    chunks.append(item["text"])
                elif t == "tool_result":
                    result = item.get("content", "")
                    if len(result) > 3000:
                        result = result[:3000] + "...[truncated]"
                    chunks.append(f"<tool_result>{result}</tool_result>")
            if chunks:
                parts.append(f"{role}: {''.join(chunks)}\n\n")
    parts.append("ASSISTANT:")
    return "".join(parts)


def _call_claude_cli(prompt: str) -> str:
    try:
        result = subprocess.run(
            ["claude", "-p"],
            input=prompt, capture_output=True, text=True,
            timeout=120, encoding="utf-8",
        )
        if result.returncode != 0 and result.stderr:
            return f"[CLI Error: {result.stderr[:200]}]"
        return result.stdout.strip()
    except FileNotFoundError:
        return "[Error: 'claude' command not found. Ensure Claude Code is installed and in PATH.]"
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

SYSTEM_PROMPT = """You are an expert options trading advisor specializing in US large-cap equity options.

## Your Focus
- **Universe**: High-liquidity large-caps and ETFs — SPY, QQQ, AAPL, NVDA, TSLA, META, MSFT, AMZN, GOOGL, AMD, NFLX, COIN, PLTR, and similar
- **Strategies**: Single-leg positions ONLY — long calls, long puts, short calls, short puts
- **Timeframe**: 0 DTE to 21 DTE, with full understanding of the difference between each horizon
- **Edge**: Volume, liquidity, Greeks, IV context, earnings risk, and market regime

## Workflow: "100% Gain / Double My Money" Requests
When a user asks for trades that can 100%+ within days, follow this exact sequence:
1. `get_market_context` — confirm market regime (avoid buying in extreme fear/VIX spike)
2. `find_high_leverage_options` — run with `max_dte` matching their window, `option_type` matching their bias
3. For the top 3–5 candidates: call `get_iv_analysis` and `get_earnings_info` to validate
4. Rank final picks by: lowest `move_needed_pct` + liquid (vol > 200) + earnings NOT in window
5. Present top 2–3 specific contracts with full breakdown

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

**For broad market scans:**
1. `get_market_context` first
2. `screen_options` across relevant tickers
3. Drill down with `get_iv_analysis` and `get_earnings_info` on best candidates

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

**Every recommendation MUST include position sizing. Always call `calculate_position_size` after selecting a contract.**

### Default Risk Rules (adjustable via `manage_risk_settings`)
| Rule | Default | Purpose |
|------|---------|---------|
| Max per-trade risk | 5% of account | Limits single-trade loss |
| Max drawdown | 15% of account | Stops trading after 3 max-sized losing trades |
| Stop-loss | 50% of premium | Exit before full premium loss |
| 0DTE cap | 2% of account | 0DTE is binary — size very small |

### Stop-Loss Rules by DTE
- **0DTE**: No stop needed (expires same day) — but size to 2% max. Accept binary outcome.
- **1–3 DTE**: Hard stop at 50% premium loss. Theta decay is brutal; cut losers fast.
- **4–14 DTE**: Stop at 50% premium loss OR if thesis is invalidated (stock breaks key level).
- **Never average down** on a losing short-DTE option — theta accelerates against you.

### Drawdown Protection Logic
- 15% max drawdown = stop trading / review after losing 15% of total account
- At 5% risk per trade: 3 consecutive max-sized losses = 15% drawdown → pause and review
- After hitting 50% of drawdown limit (7.5% down): reduce position size by 50%

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
{watchlist}

Today: {datetime}  |  Risk-free rate: {rfr}%
"""


# ─── Main chat loop ─────────────────────────────────────────────────────────────

def chat():
    conversation = []
    system = SYSTEM_PROMPT.format(
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
            raw = _call_claude_cli(_build_prompt(_trim_history(conversation), system))

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
