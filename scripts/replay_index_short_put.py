from __future__ import annotations

"""Replay single-leg cash-secured short puts on index ETFs with executable-side fills.

Motivation: every multi-leg single-name structure tested in this repo died on entry
constructibility (post-earnings condors: 13 of 72 OOS events constructible; 285/552 legs
breaching a 25%-of-midpoint spread filter). Measured single-leg index ETF put spreads are
roughly 1% of midpoint - about 20-30x cheaper. This script tests whether that cheaper
execution surface supports a strategy that beats simply holding the underlying.

Read-only against the quote store. Sells at the bid, buys back at the ask, never midpoint.
Fees are frozen numerically here rather than left undefined, which is one of the three
defects that made the post-earnings fallback contract unscoreable as written.
"""

import argparse
import json
import math
import sqlite3
import sys
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB_PATH = ROOT / "data/options-validation/options_history.db"

# ---- frozen strategy parameters -------------------------------------------------
SYMBOLS = ("SPY", "QQQ", "IWM")
# 10:10 ET is the only stratum present in every year of the store (15:55 begins in 2022).
# Measured cost is materially the same: SPY 35-45 DTE puts, bid>=1.00, median spread/midpoint
# 1.062% at 10:10 vs 1.012% at 15:55 over 2022-2024, so nothing is given up by using it.
ENTRY_MINUTE = 610
DTE_MIN, DTE_MAX = 35, 45
TARGET_DELTA = 0.20          # short put delta target
PROFIT_TAKE_FRACTION = 0.50  # close when 50% of credit captured
STOP_LOSS_CREDIT_MULT = 3.0  # buy back at 3x credit => realised loss of 2x credit
TIME_EXIT_DTE = 7
FEE_PER_CONTRACT_SIDE = 0.80  # USD; $1.60 round trip
MIN_ENTRY_BID = 0.30
MAX_ENTRY_SPREAD_FRACTION = 0.10  # reject entries wider than 10% of midpoint
RISK_FREE_RATE = 0.045
# --------------------------------------------------------------------------------


def normal_cdf(value: float) -> float:
    return 0.5 * math.erfc(-value / math.sqrt(2.0))


def black76_price(forward: float, strike: float, years: float, volatility: float, option_type: str) -> float:
    discount = math.exp(-RISK_FREE_RATE * years)
    scale = volatility * math.sqrt(years)
    if scale <= 0.0:
        intrinsic = max(forward - strike, 0.0) if option_type == "call" else max(strike - forward, 0.0)
        return discount * intrinsic
    d1 = (math.log(forward / strike) + 0.5 * volatility * volatility * years) / scale
    d2 = d1 - scale
    if option_type == "call":
        return discount * (forward * normal_cdf(d1) - strike * normal_cdf(d2))
    return discount * (strike * normal_cdf(-d2) - forward * normal_cdf(-d1))


def implied_delta(*, midpoint: float, forward: float, strike: float, years: float) -> float | None:
    """Bisect Black-76 implied vol from the put midpoint, then return put delta."""
    discount = math.exp(-RISK_FREE_RATE * years)
    intrinsic = discount * max(strike - forward, 0.0)
    maximum = discount * strike
    if midpoint < intrinsic - 1e-6 or midpoint >= maximum or midpoint <= 0.0:
        return None
    low, high = 1e-4, 5.0
    if black76_price(forward, strike, years, high, "put") < midpoint:
        return None
    for _ in range(64):
        guess = (low + high) / 2.0
        if black76_price(forward, strike, years, guess, "put") < midpoint:
            low = guess
        else:
            high = guess
    volatility = (low + high) / 2.0
    scale = volatility * math.sqrt(years)
    if scale <= 0.0:
        return None
    d1 = (math.log(forward / strike) + 0.5 * volatility * volatility * years) / scale
    return normal_cdf(-d1)


def infer_forward(pairs: dict[float, dict[str, float]], years: float) -> float | None:
    """Put-call parity forward from the five strikes with the smallest call-put gap."""
    both = [(k, s["call"], s["put"]) for k, s in pairs.items() if "call" in s and "put" in s]
    if not both:
        return None
    discount = math.exp(-RISK_FREE_RATE * years)
    closest = sorted(both, key=lambda item: (abs(item[1] - item[2]), item[0]))[:5]
    forwards = [k + (c - p) / discount for k, c, p in closest]
    usable = [f for f in forwards if f > 0.0 and math.isfinite(f)]
    return median(usable) if usable else None


def connect() -> sqlite3.Connection:
    uri = f"file:{DB_PATH.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=300)
    conn.execute("PRAGMA query_only=ON")
    return conn


def trading_dates(conn: sqlite3.Connection, symbol: str, start: str, end: str) -> list[str]:
    rows = conn.execute(
        """SELECT DISTINCT quote_date_et FROM option_quote_snapshots
           WHERE underlying=? AND snapshot_kind='intraday' AND quote_minute_et=?
             AND quote_date_et BETWEEN ? AND ?
           ORDER BY quote_date_et""",
        (symbol, ENTRY_MINUTE, start, end),
    ).fetchall()
    return [r[0] for r in rows]


def chain_for_date(conn: sqlite3.Connection, symbol: str, quote_date: str) -> dict[str, dict[float, dict[str, Any]]]:
    """expiry -> strike -> {call:..., put:...} with bid/ask kept per side."""
    rows = conn.execute(
        """SELECT expiry, strike, option_type, bid, ask FROM option_quote_snapshots
           WHERE underlying=? AND snapshot_kind='intraday' AND quote_minute_et=?
             AND quote_date_et=? AND bid>0 AND ask>bid""",
        (symbol, ENTRY_MINUTE, quote_date),
    ).fetchall()
    chain: dict[str, dict[float, dict[str, Any]]] = defaultdict(lambda: defaultdict(dict))
    for expiry, strike, option_type, bid, ask in rows:
        chain[expiry][float(strike)][option_type] = {"bid": float(bid), "ask": float(ask)}
    return chain


def dte(quote_date: str, expiry: str) -> int:
    return (date.fromisoformat(expiry) - date.fromisoformat(quote_date)).days


def select_entry(chain: dict[str, dict[float, dict[str, Any]]], quote_date: str) -> dict[str, Any] | None:
    """Pick the expiry nearest 40 DTE, then the put whose delta is nearest TARGET_DELTA."""
    expiries = [e for e in chain if DTE_MIN <= dte(quote_date, e) <= DTE_MAX]
    if not expiries:
        return None
    expiry = min(expiries, key=lambda e: abs(dte(quote_date, e) - 40))
    days = dte(quote_date, expiry)
    years = max(days, 1) / 365.0

    mids = {
        strike: {side: (v["bid"] + v["ask"]) / 2.0 for side, v in sides.items()}
        for strike, sides in chain[expiry].items()
    }
    forward = infer_forward(mids, years)
    if forward is None:
        return None

    best = None
    for strike, sides in chain[expiry].items():
        put = sides.get("put")
        if put is None or strike >= forward:
            continue  # out-of-the-money puts only
        mid = (put["bid"] + put["ask"]) / 2.0
        delta = implied_delta(midpoint=mid, forward=forward, strike=strike, years=years)
        if delta is None:
            continue
        gap = abs(delta - TARGET_DELTA)
        if best is None or gap < best["delta_gap"]:
            best = {
                "expiry": expiry, "strike": strike, "dte": days, "forward": forward,
                "delta": delta, "delta_gap": gap, "bid": put["bid"], "ask": put["ask"],
                "spread_fraction": (put["ask"] - put["bid"]) / mid if mid > 0 else None,
            }
    if best is None:
        return None
    if best["bid"] < MIN_ENTRY_BID:
        return None
    if best["spread_fraction"] is None or best["spread_fraction"] > MAX_ENTRY_SPREAD_FRACTION:
        return None
    return best


def future_quotes(conn: sqlite3.Connection, symbol: str, expiry: str, strike: float, after: str) -> list[tuple[str, float, float]]:
    rows = conn.execute(
        """SELECT quote_date_et, bid, ask FROM option_quote_snapshots
           WHERE underlying=? AND option_type='put' AND snapshot_kind='intraday'
             AND quote_minute_et=? AND expiry=? AND strike=?
             AND quote_date_et > ? AND quote_date_et <= ?
           ORDER BY quote_date_et""",
        (symbol, ENTRY_MINUTE, expiry, strike, after, expiry),
    ).fetchall()
    return [(r[0], float(r[1]), float(r[2])) for r in rows]


def run_symbol(conn: sqlite3.Connection, symbol: str, start: str, end: str) -> list[dict[str, Any]]:
    dates = trading_dates(conn, symbol, start, end)
    trades: list[dict[str, Any]] = []
    blocked_until = ""  # sequential: one open position at a time

    for quote_date in dates:
        if quote_date <= blocked_until:
            continue
        chain = chain_for_date(conn, symbol, quote_date)
        if not chain:
            continue
        pick = select_entry(chain, quote_date)
        if pick is None:
            continue

        credit = pick["bid"]                       # sell to open at the bid
        stop_price = credit * STOP_LOSS_CREDIT_MULT
        take_price = credit * (1.0 - PROFIT_TAKE_FRACTION)

        series = future_quotes(conn, symbol, pick["expiry"], pick["strike"], quote_date)
        exit_row = None
        for qd, bid, ask in series:
            remaining = dte(qd, pick["expiry"])
            if ask <= take_price:
                exit_row = (qd, ask, "profit_target"); break
            if ask >= stop_price:
                exit_row = (qd, ask, "stop_loss"); break
            if remaining <= TIME_EXIT_DTE:
                exit_row = (qd, ask, "time_exit"); break
        if exit_row is None:
            if not series:
                continue  # no post-entry coverage at all; not tradeable, skip
            qd, _bid, ask = series[-1]
            exit_row = (qd, ask, "last_available_quote")

        exit_date, exit_ask, reason = exit_row
        gross = (credit - exit_ask) * 100.0
        fees = FEE_PER_CONTRACT_SIDE * 2.0
        net = gross - fees
        capital = pick["strike"] * 100.0

        trades.append({
            "symbol": symbol, "entry_date": quote_date, "exit_date": exit_date,
            "expiry": pick["expiry"], "strike": pick["strike"], "dte": pick["dte"],
            "delta": round(pick["delta"], 4), "forward": round(pick["forward"], 2),
            "entry_spread_fraction": round(pick["spread_fraction"], 5),
            "credit": credit, "exit_ask": exit_ask, "exit_reason": reason,
            "gross_usd": round(gross, 2), "fees_usd": round(fees, 2), "net_usd": round(net, 2),
            "capital_usd": round(capital, 2), "return_on_capital": net / capital,
            "held_days": (date.fromisoformat(exit_date) - date.fromisoformat(quote_date)).days,
            "post_entry_quote_days": len(series),
        })
        blocked_until = exit_date

    return trades


def forward_series(conn: sqlite3.Connection, symbol: str, start: str, end: str) -> list[tuple[str, float]]:
    """Underlying proxy for the benchmark: parity-inferred forward, nearest expiry >= 25 DTE."""
    out = []
    for quote_date in trading_dates(conn, symbol, start, end):
        chain = chain_for_date(conn, symbol, quote_date)
        cands = [e for e in chain if 25 <= dte(quote_date, e) <= 60]
        if not cands:
            continue
        expiry = min(cands, key=lambda e: dte(quote_date, e))
        years = max(dte(quote_date, expiry), 1) / 365.0
        mids = {s: {k: (v["bid"] + v["ask"]) / 2.0 for k, v in sides.items()} for s, sides in chain[expiry].items()}
        fwd = infer_forward(mids, years)
        if fwd:
            out.append((quote_date, fwd))
    return out


def account_simulation(trades: list[dict[str, Any]], start_capital: float) -> dict[str, Any]:
    """Single cash-secured account. Collateral earns the risk-free rate continuously;
    option P&L is booked at exit. Contracts sized to whole multiples of strike*100.

    This replaces naive per-trade return compounding, which (a) double counts when several
    symbols hold positions at once and (b) gives the collateral no yield even though a real
    cash-secured seller earns it.
    """
    if not trades:
        return {"available": False}
    ordered = sorted(trades, key=lambda t: (t["exit_date"], t["symbol"]))
    account = start_capital
    cursor = date.fromisoformat(ordered[0]["entry_date"])
    curve = [account]
    skipped = 0
    for t in ordered:
        exit_day = date.fromisoformat(t["exit_date"])
        elapsed = max((exit_day - cursor).days, 0)
        account *= (1.0 + RISK_FREE_RATE) ** (elapsed / 365.25)  # collateral yield
        contracts = int(account // t["capital_usd"])
        if contracts < 1:
            skipped += 1
        else:
            account += contracts * t["net_usd"]
        curve.append(account)
        cursor = exit_day
    first = date.fromisoformat(ordered[0]["entry_date"])
    last = date.fromisoformat(ordered[-1]["exit_date"])
    years = max((last - first).days / 365.25, 1e-9)
    total = account / start_capital - 1.0
    dd = max_drawdown(curve)
    return {
        "available": True,
        "start_capital_usd": start_capital,
        "end_capital_usd": round(account, 2),
        "total_return": round(total, 4),
        "cagr": round((account / start_capital) ** (1.0 / years) - 1.0, 4),
        "max_drawdown": round(dd, 4),
        "return_over_maxdd": round(total / dd, 3) if dd > 0 else None,
        "trades_skipped_insufficient_capital": skipped,
        "note": "collateral earns risk-free; contracts sized whole; one position per symbol at a time",
    }


def max_drawdown(curve: list[float]) -> float:
    peak, worst = curve[0] if curve else 1.0, 0.0
    for value in curve:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, (peak - value) / peak)
    return worst


def summarise(trades: list[dict[str, Any]], bench: list[tuple[str, float]], label: str) -> dict[str, Any]:
    if not trades:
        return {"label": label, "trades": 0}
    ordered = sorted(trades, key=lambda t: t["exit_date"])
    equity, level = [], 1.0
    for t in ordered:
        level *= (1.0 + t["return_on_capital"])
        equity.append(level)
    wins = [t for t in ordered if t["net_usd"] > 0]
    losses = [t for t in ordered if t["net_usd"] <= 0]
    gross_win = sum(t["net_usd"] for t in wins)
    gross_loss = -sum(t["net_usd"] for t in losses)

    first, last = ordered[0]["entry_date"], ordered[-1]["exit_date"]
    years = max((date.fromisoformat(last) - date.fromisoformat(first)).days / 365.25, 1e-9)
    strat_total = equity[-1] - 1.0
    strat_cagr = equity[-1] ** (1.0 / years) - 1.0
    strat_dd = max_drawdown(equity)

    bench_block: dict[str, Any] = {"available": False}
    if len(bench) >= 2:
        window = [(d, f) for d, f in bench if first <= d <= last]
        if len(window) >= 2:
            bh_curve = [f / window[0][1] for _, f in window]
            bh_total = bh_curve[-1] - 1.0
            bh_dd = max_drawdown(bh_curve)
            bench_block = {
                "available": True,
                "buy_hold_total_return": round(bh_total, 4),
                "buy_hold_cagr": round(bh_curve[-1] ** (1.0 / years) - 1.0, 4),
                "buy_hold_max_drawdown": round(bh_dd, 4),
                "buy_hold_return_over_maxdd": round(bh_total / bh_dd, 3) if bh_dd > 0 else None,
                "risk_free_total_return": round((1 + RISK_FREE_RATE) ** years - 1.0, 4),
            }

    return {
        "label": label,
        "window": {"first_entry": first, "last_exit": last, "years": round(years, 2)},
        "trades": len(ordered),
        "wins": len(wins), "losses": len(losses),
        "win_rate": round(len(wins) / len(ordered), 4),
        "net_usd_total": round(sum(t["net_usd"] for t in ordered), 2),
        "fees_usd_total": round(sum(t["fees_usd"] for t in ordered), 2),
        "profit_factor": round(gross_win / gross_loss, 3) if gross_loss > 0 else None,
        "avg_return_on_capital": round(sum(t["return_on_capital"] for t in ordered) / len(ordered), 5),
        "median_held_days": median(t["held_days"] for t in ordered),
        "exit_reasons": {r: sum(1 for t in ordered if t["exit_reason"] == r)
                         for r in sorted({t["exit_reason"] for t in ordered})},
        "median_entry_spread_fraction": round(median(t["entry_spread_fraction"] for t in ordered), 5),
        "strategy_total_return": round(strat_total, 4),
        "strategy_cagr": round(strat_cagr, 4),
        "strategy_max_drawdown": round(strat_dd, 4),
        "strategy_return_over_maxdd": round(strat_total / strat_dd, 3) if strat_dd > 0 else None,
        "benchmark": bench_block,
    }


def main() -> int:
    global TARGET_DELTA, PROFIT_TAKE_FRACTION, STOP_LOSS_CREDIT_MULT, TIME_EXIT_DTE

    ap = argparse.ArgumentParser(description="Replay single-leg short index puts.")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--target-delta", type=float, default=TARGET_DELTA)
    ap.add_argument("--profit-take", type=float, default=PROFIT_TAKE_FRACTION)
    ap.add_argument("--stop-mult", type=float, default=STOP_LOSS_CREDIT_MULT,
                    help="buy-to-close at this multiple of credit; use a large value to disable the stop")
    ap.add_argument("--time-exit-dte", type=int, default=TIME_EXIT_DTE)
    args = ap.parse_args()

    TARGET_DELTA = args.target_delta
    PROFIT_TAKE_FRACTION = args.profit_take
    STOP_LOSS_CREDIT_MULT = args.stop_mult
    TIME_EXIT_DTE = args.time_exit_dte

    conn = connect()
    all_trades: list[dict[str, Any]] = []
    per_symbol: dict[str, Any] = {}
    for symbol in SYMBOLS:
        trades = run_symbol(conn, symbol, args.start, args.end)
        bench = forward_series(conn, symbol, args.start, args.end)
        per_symbol[symbol] = summarise(trades, bench, f"{args.label}:{symbol}")
        all_trades.extend(trades)
        print(f"  {symbol}: {len(trades)} trades", flush=True)

    spy_bench = forward_series(conn, "SPY", args.start, args.end)

    # Account simulations. Per-symbol uses capital sized to that symbol's largest strike so
    # every trade is takeable; the 3-symbol portfolio needs enough for concurrent positions.
    accounts: dict[str, Any] = {}
    for symbol in SYMBOLS:
        sym_trades = [t for t in all_trades if t["symbol"] == symbol]
        if sym_trades:
            cap = max(t["capital_usd"] for t in sym_trades)
            accounts[symbol] = account_simulation(sym_trades, cap)
    if all_trades:
        portfolio_cap = sum(
            max((t["capital_usd"] for t in all_trades if t["symbol"] == s), default=0.0)
            for s in SYMBOLS
        )
        accounts["portfolio_3_symbol"] = account_simulation(all_trades, portfolio_cap)

    report = {
        "report_id": "index_short_put_replay",
        "label": args.label,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "window": {"start": args.start, "end": args.end},
        "parameters": {
            "symbols": list(SYMBOLS), "entry_minute_et": ENTRY_MINUTE,
            "dte_band": [DTE_MIN, DTE_MAX], "target_delta": TARGET_DELTA,
            "profit_take_fraction": PROFIT_TAKE_FRACTION,
            "stop_loss_credit_multiple": STOP_LOSS_CREDIT_MULT,
            "time_exit_dte": TIME_EXIT_DTE,
            "fee_per_contract_side_usd": FEE_PER_CONTRACT_SIDE,
            "min_entry_bid": MIN_ENTRY_BID,
            "max_entry_spread_fraction": MAX_ENTRY_SPREAD_FRACTION,
            "fill_model": "sell_to_open_at_bid, buy_to_close_at_ask, never midpoint",
        },
        "combined": summarise(all_trades, spy_bench, f"{args.label}:combined_vs_SPY"),
        "accounts": accounts,
        "per_symbol": per_symbol,
        "trades": sorted(all_trades, key=lambda t: (t["entry_date"], t["symbol"])),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
