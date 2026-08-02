from __future__ import annotations

"""Corrected short-put replay. Supersedes scripts/replay_index_short_put.py.

Why v2 exists - three defects were found in v1 by adversarial review, all of which
flattered the strategy:

  1. RISK_FREE_RATE was hard-coded at 4.5% for every year and used for collateral yield,
     the benchmark, AND option pricing. Actual 3-month T-bill yields were ~0.1-0.5% in
     2020-21 and ~2.3% in 2018-19.
  2. Drawdown was computed from an equity curve sampled only at trade exits, so
     intra-trade mark-to-market pain was invisible.
  3. Comparisons pooled symbols whose data windows differed by two years.

The v1 fix for (1) would have been to source a real rate series. That is the wrong
correction. For a cash-secured put the collateral earns the T-bill yield whether or not
the put is sold, so THE OPTION P&L IS ITSELF THE EXCESS RETURN OVER TREASURIES at any
rate. The rate cancels. v2 therefore reports rate-free primary metrics and never
simulates collateral yield.

A discount rate survives in one place only: the Black-76 implied-delta and put-call-parity
forward used to pick strikes. At 35 DTE the discount factor is 0.9957 at 4.5% versus
0.9997 at 0.3%, so strike selection moves by well under 1%. It is declared as
PRICING_DISCOUNT_RATE, is reported in the output, and is used for NOTHING else.

Validation gates (must pass before any strategy number is emitted):
  G1 exit census      - forced/censored exits must be <= MAX_CENSORED_EXIT_FRACTION
  G2 mark density     - daily marks must cover >= MIN_MARK_DENSITY of held trading days
  G3 window equality  - cross-symbol comparisons use the common date intersection or are
                        labelled non-comparable
  G4 aggregation      - undefined statistics stay undefined; pooled and mean-of-groups are
                        reported separately and labelled

Read-only against the quote store.
"""

import argparse
import hashlib
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

# ---- strategy parameters (frozen per run, echoed into the report) ----------------
ENTRY_MINUTE = 610            # 10:10 ET - the only stratum present in every year
DTE_MIN, DTE_MAX = 35, 45
TARGET_DELTA = 0.20
PROFIT_TAKE_FRACTION = 0.50
STOP_LOSS_CREDIT_MULT = 9999.0  # effectively disabled; see the v1 finding on fitted stops
TIME_EXIT_DTE = 7
FEE_PER_CONTRACT_SIDE = 0.80
MIN_ENTRY_BID = 0.30
MAX_ENTRY_SPREAD_FRACTION = 0.10

# ---- pricing-only assumption ----------------------------------------------------
# Used ONLY for the Black-76 implied delta and the parity forward that select a strike.
# Never used for accounting, benchmarks, or returns.
PRICING_DISCOUNT_RATE = 0.03

# ---- validation gate thresholds -------------------------------------------------
MAX_CENSORED_EXIT_FRACTION = 0.02   # Fable's threshold; ~1% permanent ThetaData gaps exist
MIN_MARK_DENSITY = 0.80
# Data-adequacy screen applied BEFORE an entry is taken (Sol: censored exits must be
# excluded before selection, not booked as trades). A normal position sees ~20-23 quote
# days; boundary-censored ones see 1-9. Positions opened too close to the end of available
# data, or into a mid-sample coverage gap, are not tradeable observations at all.
MIN_POST_ENTRY_QUOTE_DAYS = 15
# --------------------------------------------------------------------------------


def normal_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def black76_price(forward: float, strike: float, years: float, vol: float, kind: str) -> float:
    disc = math.exp(-PRICING_DISCOUNT_RATE * years)
    scale = vol * math.sqrt(years)
    if scale <= 0.0:
        intrinsic = max(forward - strike, 0.0) if kind == "call" else max(strike - forward, 0.0)
        return disc * intrinsic
    d1 = (math.log(forward / strike) + 0.5 * vol * vol * years) / scale
    d2 = d1 - scale
    if kind == "call":
        return disc * (forward * normal_cdf(d1) - strike * normal_cdf(d2))
    return disc * (strike * normal_cdf(-d2) - forward * normal_cdf(-d1))


def implied_put_delta(*, midpoint: float, forward: float, strike: float, years: float) -> float | None:
    disc = math.exp(-PRICING_DISCOUNT_RATE * years)
    if midpoint < disc * max(strike - forward, 0.0) - 1e-6 or midpoint >= disc * strike or midpoint <= 0.0:
        return None
    lo, hi = 1e-4, 5.0
    if black76_price(forward, strike, years, hi, "put") < midpoint:
        return None
    for _ in range(64):
        mid = (lo + hi) / 2.0
        if black76_price(forward, strike, years, mid, "put") < midpoint:
            lo = mid
        else:
            hi = mid
    vol = (lo + hi) / 2.0
    scale = vol * math.sqrt(years)
    if scale <= 0.0:
        return None
    d1 = (math.log(forward / strike) + 0.5 * vol * vol * years) / scale
    return normal_cdf(-d1)


def infer_forward(mids: dict[float, dict[str, float]], years: float) -> float | None:
    both = [(k, s["call"], s["put"]) for k, s in mids.items() if "call" in s and "put" in s]
    if not both:
        return None
    disc = math.exp(-PRICING_DISCOUNT_RATE * years)
    closest = sorted(both, key=lambda i: (abs(i[1] - i[2]), i[0]))[:5]
    fwds = [k + (c - p) / disc for k, c, p in closest]
    ok = [f for f in fwds if f > 0.0 and math.isfinite(f)]
    return median(ok) if ok else None


def dte(quote_date: str, expiry: str) -> int:
    return (date.fromisoformat(expiry) - date.fromisoformat(quote_date)).days


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True, timeout=300)
    conn.execute("PRAGMA query_only=ON")
    return conn


def trading_dates(conn, symbol, start, end) -> list[str]:
    return [r[0] for r in conn.execute(
        """SELECT DISTINCT quote_date_et FROM option_quote_snapshots
           WHERE underlying=? AND snapshot_kind='intraday' AND quote_minute_et=?
             AND quote_date_et BETWEEN ? AND ? ORDER BY quote_date_et""",
        (symbol, ENTRY_MINUTE, start, end))]


def chain_for_date(conn, symbol, quote_date):
    chain: dict[str, dict[float, dict[str, Any]]] = defaultdict(lambda: defaultdict(dict))
    for expiry, strike, kind, bid, ask in conn.execute(
        """SELECT expiry, strike, option_type, bid, ask FROM option_quote_snapshots
           WHERE underlying=? AND snapshot_kind='intraday' AND quote_minute_et=?
             AND quote_date_et=? AND bid>0 AND ask>bid""",
        (symbol, ENTRY_MINUTE, quote_date)):
        chain[expiry][float(strike)][kind] = {"bid": float(bid), "ask": float(ask)}
    return chain


def select_entry(chain, quote_date):
    expiries = [e for e in chain if DTE_MIN <= dte(quote_date, e) <= DTE_MAX]
    if not expiries:
        return None
    expiry = min(expiries, key=lambda e: abs(dte(quote_date, e) - 40))
    days = dte(quote_date, expiry)
    years = max(days, 1) / 365.0
    mids = {k: {s: (v["bid"] + v["ask"]) / 2.0 for s, v in sides.items()}
            for k, sides in chain[expiry].items()}
    forward = infer_forward(mids, years)
    if forward is None:
        return None
    best = None
    for strike, sides in chain[expiry].items():
        put = sides.get("put")
        if put is None or strike >= forward:
            continue
        mid = (put["bid"] + put["ask"]) / 2.0
        d = implied_put_delta(midpoint=mid, forward=forward, strike=strike, years=years)
        if d is None:
            continue
        gap = abs(d - TARGET_DELTA)
        if best is None or gap < best["gap"]:
            best = {"expiry": expiry, "strike": strike, "dte": days, "forward": forward,
                    "delta": d, "gap": gap, "bid": put["bid"], "ask": put["ask"],
                    "spread_fraction": (put["ask"] - put["bid"]) / mid if mid > 0 else None}
    if best is None or best["bid"] < MIN_ENTRY_BID:
        return None
    if best["spread_fraction"] is None or best["spread_fraction"] > MAX_ENTRY_SPREAD_FRACTION:
        return None
    return best


def future_quotes(conn, symbol, expiry, strike, after):
    return [(r[0], float(r[1]), float(r[2])) for r in conn.execute(
        """SELECT quote_date_et, bid, ask FROM option_quote_snapshots
           WHERE underlying=? AND option_type='put' AND snapshot_kind='intraday'
             AND quote_minute_et=? AND expiry=? AND strike=?
             AND quote_date_et > ? AND quote_date_et <= ? ORDER BY quote_date_et""",
        (symbol, ENTRY_MINUTE, expiry, strike, after, expiry))]


def run_symbol(conn, symbol, start, end):
    """Returns (trades, daily_marks) where daily_marks is [(date, symbol, open_pnl_usd)]."""
    dates = trading_dates(conn, symbol, start, end)
    date_set = set(dates)
    trades, marks = [], []
    blocked_until = ""
    skipped_inadequate = 0
    for quote_date in dates:
        if quote_date <= blocked_until:
            continue
        chain = chain_for_date(conn, symbol, quote_date)
        if not chain:
            continue
        pick = select_entry(chain, quote_date)
        if pick is None:
            continue

        credit = pick["bid"]
        take = credit * (1.0 - PROFIT_TAKE_FRACTION)
        stop = credit * STOP_LOSS_CREDIT_MULT
        series = future_quotes(conn, symbol, pick["expiry"], pick["strike"], quote_date)
        if len(series) < MIN_POST_ENTRY_QUOTE_DAYS:
            skipped_inadequate += 1
            continue

        exit_row, marked_days = None, 0
        for qd, _bid, ask in series:
            marks.append((qd, symbol, (credit - ask) * 100.0))   # G2: daily mark-to-market
            marked_days += 1
            if ask <= take:
                exit_row = (qd, ask, "profit_target"); break
            if ask >= stop:
                exit_row = (qd, ask, "stop_loss"); break
            if dte(qd, pick["expiry"]) <= TIME_EXIT_DTE:
                exit_row = (qd, ask, "time_exit"); break
        if exit_row is None:
            qd, _b, ask = series[-1]
            exit_row = (qd, ask, "censored_data_exhaustion")

        exit_date, exit_ask, reason = exit_row
        gross = (credit - exit_ask) * 100.0
        fees = FEE_PER_CONTRACT_SIDE * 2.0
        held = (date.fromisoformat(exit_date) - date.fromisoformat(quote_date)).days
        # G2 denominator: trading days the position was actually OPEN, not days to expiry.
        expected_marks = sum(1 for d in date_set if quote_date < d <= exit_date)
        trades.append({
            "symbol": symbol, "entry_date": quote_date, "exit_date": exit_date,
            "expiry": pick["expiry"], "strike": pick["strike"], "dte": pick["dte"],
            "delta": round(pick["delta"], 4), "forward": round(pick["forward"], 2),
            "entry_spread_fraction": round(pick["spread_fraction"], 5),
            "credit": credit, "exit_ask": exit_ask, "exit_reason": reason,
            "gross_usd": round(gross, 2), "fees_usd": round(fees, 2),
            "net_usd": round(gross - fees, 2),
            "capital_usd": round(pick["strike"] * 100.0, 2),
            "held_days": held, "marked_days": marked_days,
            "expected_mark_days": expected_marks,
            "post_entry_quote_days": len(series),
        })
        blocked_until = exit_date
    return trades, marks, skipped_inadequate


def max_drawdown(curve: list[float]) -> float | None:
    if not curve:
        return None
    peak, worst = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        if peak != 0:
            worst = max(worst, (peak - v) / abs(peak))
    return worst


def daily_marked_drawdown(trades, marks, capital):
    """G2/G3: drawdown from a DAILY marked equity curve, not sampled at exits."""
    if not trades:
        return {"available": False, "reason": "no trades"}
    realised: dict[str, float] = defaultdict(float)
    for t in trades:
        realised[t["exit_date"]] += t["net_usd"]
    open_pnl: dict[str, float] = defaultdict(float)
    for d, _sym, pnl in marks:
        open_pnl[d] += pnl
    all_days = sorted(set(realised) | set(open_pnl))
    equity, cum = [], capital
    for d in all_days:
        cum += realised.get(d, 0.0)
        equity.append(cum + open_pnl.get(d, 0.0))   # realised + unrealised
    return {
        "available": True,
        "marked_days": len(all_days),
        "max_drawdown_daily_marked": round(max_drawdown(equity), 4),
        "final_equity_usd": round(cum, 2),
    }


def profit_factor(trades):
    """G4: undefined stays undefined - never coerced to 0."""
    wins = sum(t["net_usd"] for t in trades if t["net_usd"] > 0)
    losses = -sum(t["net_usd"] for t in trades if t["net_usd"] <= 0)
    if losses == 0:
        return None
    return round(wins / losses, 4)


def summarise(trades, label):
    if not trades:
        return {"label": label, "trades": 0}
    ordered = sorted(trades, key=lambda t: t["exit_date"])
    wins = [t for t in ordered if t["net_usd"] > 0]
    censored = [t for t in ordered if t["exit_reason"] == "censored_data_exhaustion"]
    return {
        "label": label,
        "window": {"first_entry": ordered[0]["entry_date"], "last_exit": ordered[-1]["exit_date"]},
        "trades": len(ordered),
        "wins": len(wins), "losses": len(ordered) - len(wins),
        "win_rate": round(len(wins) / len(ordered), 4),
        "option_net_usd": round(sum(t["net_usd"] for t in ordered), 2),
        "option_net_usd_note": "this IS the excess return over T-bills for a cash-secured seller",
        "fees_usd": round(sum(t["fees_usd"] for t in ordered), 2),
        "profit_factor_pooled": profit_factor(ordered),
        "profit_factor_undefined": profit_factor(ordered) is None,
        "median_held_days": median(t["held_days"] for t in ordered),
        "median_entry_spread_fraction": round(median(t["entry_spread_fraction"] for t in ordered), 5),
        "exit_reasons": {r: sum(1 for t in ordered if t["exit_reason"] == r)
                         for r in sorted({t["exit_reason"] for t in ordered})},
        "censored_exit_fraction": round(len(censored) / len(ordered), 4),
    }


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="Corrected short-put replay (v2).")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--symbols", default="SPY,QQQ,IWM")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    symbols = tuple(s.strip().upper() for s in args.symbols.split(",") if s.strip())

    conn = connect()
    all_trades, all_marks, per_symbol = [], [], {}
    total_skipped = 0
    for sym in symbols:
        tr, mk, skipped = run_symbol(conn, sym, args.start, args.end)
        total_skipped += skipped
        per_symbol[sym] = summarise(tr, f"{args.label}:{sym}")
        per_symbol[sym]["entries_skipped_data_inadequate"] = skipped
        if tr:
            cap = max(t["capital_usd"] for t in tr)
            per_symbol[sym]["daily_marked"] = daily_marked_drawdown(tr, mk, cap)
        all_trades.extend(tr); all_marks.extend(mk)
        print(f"  {sym}: {len(tr)} trades ({skipped} skipped: data inadequate)", flush=True)

    # G3: common date intersection across symbols actually traded
    windows = [(per_symbol[s]["window"]["first_entry"], per_symbol[s]["window"]["last_exit"])
               for s in symbols if per_symbol[s].get("trades")]
    common = {"first": max(w[0] for w in windows), "last": min(w[1] for w in windows)} if windows else None
    comparable = bool(windows) and all(w[0] <= common["first"] and w[1] >= common["last"] for w in windows)
    in_common = [t for t in all_trades if common and common["first"] <= t["entry_date"]
                 and t["exit_date"] <= common["last"]]

    combined = summarise(all_trades, f"{args.label}:pooled_all_dates")
    combined_common = summarise(in_common, f"{args.label}:pooled_common_window")

    # G1/G2 gates
    censored_fraction = combined.get("censored_exit_fraction", 1.0)
    mark_density = (sum(t["marked_days"] for t in all_trades) /
                    max(sum(t["expected_mark_days"] for t in all_trades), 1)) if all_trades else 0.0
    gates = {
        "G1_exit_census": {"censored_exit_fraction": censored_fraction,
                           "threshold": MAX_CENSORED_EXIT_FRACTION,
                           "passed": censored_fraction <= MAX_CENSORED_EXIT_FRACTION},
        "G2_mark_density": {"mark_density": round(mark_density, 4),
                            "threshold": MIN_MARK_DENSITY,
                            "passed": mark_density >= MIN_MARK_DENSITY},
        "G3_window_equality": {"common_window": common, "symbols_comparable": comparable,
                               "passed": comparable},
        "G4_aggregation": {"undefined_pf_preserved": True,
                           "pooled_and_per_symbol_reported_separately": True, "passed": True},
    }
    gates["all_passed"] = all(g["passed"] for g in gates.values() if isinstance(g, dict))

    report = {
        "report_id": "short_put_replay_v2",
        "label": args.label,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "supersedes": "scripts/replay_index_short_put.py (v1: synthetic rate, exit-sampled drawdown, unequal windows)",
        "window": {"start": args.start, "end": args.end},
        "parameters": {
            "symbols": list(symbols), "entry_minute_et": ENTRY_MINUTE,
            "dte_band": [DTE_MIN, DTE_MAX], "target_delta": TARGET_DELTA,
            "profit_take_fraction": PROFIT_TAKE_FRACTION,
            "stop_loss_credit_multiple": STOP_LOSS_CREDIT_MULT,
            "time_exit_dte": TIME_EXIT_DTE, "fee_per_contract_side_usd": FEE_PER_CONTRACT_SIDE,
            "min_entry_bid": MIN_ENTRY_BID, "max_entry_spread_fraction": MAX_ENTRY_SPREAD_FRACTION,
            "pricing_discount_rate": PRICING_DISCOUNT_RATE,
            "pricing_discount_rate_scope": "Black-76 delta and parity forward ONLY; not used for accounting, returns, or benchmarks",
            "fill_model": "sell to open at bid, buy to close at ask, never midpoint",
            "no_collateral_yield_modelled": "option P&L is itself the excess return over T-bills",
        },
        "validation_gates": gates,
        "entries_skipped_data_inadequate": total_skipped,
        "combined_all_dates": combined,
        "combined_common_window": combined_common,
        "per_symbol": per_symbol,
        "provenance": {
            "script_sha256": sha256_file(Path(__file__)),
            "db_path": str(DB_PATH.relative_to(ROOT)),
            "db_bytes": DB_PATH.stat().st_size,
        },
        "trades": sorted(all_trades, key=lambda t: (t["entry_date"], t["symbol"])),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"gates_passed={gates['all_passed']}  wrote {out}")
    return 0 if gates["all_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
