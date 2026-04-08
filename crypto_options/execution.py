"""
Phase 3: Execution and position monitoring for crypto options.

Paper-trade first: logs all decisions to JSONL without placing real orders.
Real execution via Deribit API when ready.
"""

import json
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from .config import (
    RISK_CONFIG, FORWARD_TRACKING_DIR, FORWARD_LOG,
    SYMBOLS, DERIBIT_CURRENCY_MAP,
)
from .signals import scan_crypto_signals, Signal
from .deribit import DeribitClient, find_best_spread, SpreadCandidate


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class Position:
    id: str
    symbol: str                 # "BTC" or "ETH"
    direction: str              # "call" or "put"
    long_instrument: str
    short_instrument: str
    entry_debit_base: float     # in BTC/ETH
    entry_debit_usd: float
    entry_time: str
    expiry: str
    dte_at_entry: int
    spread_width: float
    signal_direction_score: float
    signal_regime: str
    status: str                 # "open", "closed"
    exit_reason: Optional[str] = None
    exit_time: Optional[str] = None
    exit_pnl_base: Optional[float] = None
    exit_pnl_usd: Optional[float] = None
    exit_pnl_pct: Optional[float] = None


# ── Position tracking ─────────────────────────────────────────────────────────

POSITIONS_FILE = FORWARD_TRACKING_DIR / "crypto_options_positions.json"


def _load_positions() -> list[dict]:
    if not POSITIONS_FILE.exists():
        return []
    return json.loads(POSITIONS_FILE.read_text())


def _save_positions(positions: list[dict]):
    os.makedirs(FORWARD_TRACKING_DIR, exist_ok=True)
    POSITIONS_FILE.write_text(json.dumps(positions, indent=2))


def _log_pick(record: dict):
    os.makedirs(FORWARD_TRACKING_DIR, exist_ok=True)
    with open(FORWARD_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


# ── Risk checks ───────────────────────────────────────────────────────────────

def check_position_risk(
    client: DeribitClient,
    position: dict,
) -> Optional[str]:
    """
    Check if a position should be closed.

    Returns exit_reason if position should close, None otherwise.
    """
    cfg = RISK_CONFIG

    # Time exit — close before expiry
    expiry_dt = datetime.strptime(position["expiry"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    dte_remaining = (expiry_dt - now).total_seconds() / 86400
    if dte_remaining <= cfg["time_exit_dte"]:
        return "time_exit"

    # Check current spread value
    try:
        long_book = client.get_order_book(position["long_instrument"])
        short_book = client.get_order_book(position["short_instrument"])

        # Current spread value = long bid - short ask (what we'd get closing)
        current_value = long_book.bid - short_book.ask
        entry_debit = position["entry_debit_base"]

        if entry_debit > 0:
            pnl_pct = (current_value - entry_debit) / entry_debit * 100

            # Stop loss
            if pnl_pct <= -cfg["stop_loss_pct"]:
                return "stop"

            # Profit target
            if pnl_pct >= cfg["profit_target_pct"]:
                return "target"
    except Exception:
        pass  # can't get quotes, hold position

    return None


def has_recent_stop(positions: list[dict], symbol: str) -> bool:
    """Check if there's been a stop within cooldown period."""
    cfg = RISK_CONFIG
    cooldown_hours = cfg["stop_cooldown_hours"]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=cooldown_hours)

    for pos in positions:
        if pos.get("symbol") != symbol:
            continue
        if pos.get("exit_reason") not in ("stop", "trailing_stop"):
            continue
        exit_time = pos.get("exit_time")
        if not exit_time:
            continue
        try:
            exit_dt = datetime.fromisoformat(exit_time.replace("Z", "+00:00"))
            if exit_dt.tzinfo is None:
                exit_dt = exit_dt.replace(tzinfo=timezone.utc)
            if exit_dt >= cutoff:
                return True
        except (ValueError, TypeError):
            continue
    return False


# ── Main scan + trade loop ────────────────────────────────────────────────────

def run_scan_cycle(
    client: DeribitClient = None,
    paper_trade: bool = True,
    max_positions: int = None,
) -> dict:
    """
    Run one scan cycle: check signals, manage positions, log results.

    Returns summary of actions taken.
    """
    cfg = RISK_CONFIG
    max_pos = max_positions or cfg["max_concurrent_positions"]
    positions = _load_positions()
    open_positions = [p for p in positions if p.get("status") == "open"]
    actions = []

    # ── Check existing positions for exits ────────────────────────────────
    if client:
        for pos in open_positions:
            exit_reason = check_position_risk(client, pos)
            if exit_reason:
                pos["status"] = "closed"
                pos["exit_reason"] = exit_reason
                pos["exit_time"] = datetime.now(timezone.utc).isoformat()
                actions.append(f"CLOSE {pos['symbol']} {pos['direction']} ({exit_reason})")

    # ── Scan for new signals ──────────────────────────────────────────────
    open_symbols = {p["symbol"] for p in open_positions if p.get("status") == "open"}
    open_count = len([p for p in positions if p.get("status") == "open"])

    signals = scan_crypto_signals()

    for sig in signals:
        currency = DERIBIT_CURRENCY_MAP.get(sig.symbol, sig.symbol.replace("USDT", ""))

        # Skip if already have position in this symbol
        if currency in open_symbols:
            continue

        # Skip if at max positions
        if open_count >= max_pos:
            break

        # Skip if in cooldown
        if has_recent_stop(positions, currency):
            actions.append(f"SKIP {currency} {sig.direction} (stop cooldown)")
            continue

        # Try to build a spread
        spread = None
        if client:
            try:
                spread = find_best_spread(client, currency, sig.direction)
            except Exception as e:
                actions.append(f"SKIP {currency} {sig.direction} (spread error: {e})")
                continue

        # Log the pick
        pick_record = {
            "logged_at": datetime.now(timezone.utc).isoformat(),
            "symbol": currency,
            "direction": sig.direction,
            "direction_score": sig.direction_score,
            "tech_score": sig.tech_score,
            "signal_strength": sig.signal_strength,
            "regime": sig.regime,
            "htf_trend": sig.htf_trend,
            "price": sig.price,
            "rsi": sig.rsi,
            "rationale": sig.rationale,
            "paper_trade": paper_trade,
        }

        if spread:
            pick_record.update({
                "long_instrument": spread.long_leg.instrument,
                "short_instrument": spread.short_leg.instrument,
                "net_debit_base": spread.net_debit_base,
                "net_debit_usd": spread.net_debit_usd,
                "spread_width": spread.spread_width,
                "risk_reward": spread.risk_reward,
                "expiry": spread.expiry,
                "dte": spread.dte,
            })

            # Create position record
            pos_id = f"{currency}-{sig.direction}-{datetime.now().strftime('%Y%m%d%H%M')}"
            new_pos = {
                "id": pos_id,
                "symbol": currency,
                "direction": sig.direction,
                "long_instrument": spread.long_leg.instrument,
                "short_instrument": spread.short_leg.instrument,
                "entry_debit_base": spread.net_debit_base,
                "entry_debit_usd": spread.net_debit_usd,
                "entry_time": datetime.now(timezone.utc).isoformat(),
                "expiry": spread.expiry,
                "dte_at_entry": spread.dte,
                "spread_width": spread.spread_width,
                "signal_direction_score": sig.direction_score,
                "signal_regime": sig.regime,
                "status": "open",
            }
            positions.append(new_pos)
            open_count += 1
            open_symbols.add(currency)
            actions.append(
                f"OPEN {currency} {sig.direction} spread "
                f"${spread.net_debit_usd:.0f} R:R={spread.risk_reward:.1f} "
                f"exp={spread.expiry}"
            )

            if not paper_trade and client:
                try:
                    client.place_order(spread.long_leg.instrument, "buy", spread.long_leg.ask)
                    client.place_order(spread.short_leg.instrument, "sell", spread.short_leg.bid)
                except Exception as e:
                    actions.append(f"  ORDER FAILED: {e}")
        else:
            pick_record["spread_available"] = False
            actions.append(f"SIGNAL {currency} {sig.direction} dir={sig.direction_score:.0f} (no spread available)")

        _log_pick(pick_record)

    _save_positions(positions)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actions": actions,
        "open_positions": len([p for p in positions if p["status"] == "open"]),
        "total_signals": len(signals),
    }


# ── Continuous monitoring loop ────────────────────────────────────────────────

def run_monitor_loop(
    poll_seconds: int = 300,    # 5 minutes
    paper_trade: bool = True,
    use_testnet: bool = True,
):
    """
    Continuous monitoring loop for crypto options.

    Scans for signals and monitors positions every poll_seconds.
    """
    client = DeribitClient(use_testnet=use_testnet)
    print(f"Crypto options monitor started ({'paper' if paper_trade else 'LIVE'})")
    print(f"  Deribit: {client.base_url}")
    print(f"  Poll interval: {poll_seconds}s")
    print(f"  Symbols: {list(DERIBIT_CURRENCY_MAP.values())}")
    print()

    while True:
        try:
            result = run_scan_cycle(client=client, paper_trade=paper_trade)
            ts = datetime.now().strftime("%H:%M:%S")
            if result["actions"]:
                for action in result["actions"]:
                    print(f"[{ts}] {action}")
            else:
                print(f"[{ts}] No actions. {result['total_signals']} signals, {result['open_positions']} positions.")
        except KeyboardInterrupt:
            print("\nMonitor stopped.")
            break
        except Exception as e:
            print(f"[ERROR] {e}")

        time.sleep(poll_seconds)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if "--loop" in sys.argv:
        poll = 300
        for i, arg in enumerate(sys.argv):
            if arg == "--poll" and i + 1 < len(sys.argv):
                poll = int(sys.argv[i + 1])
        run_monitor_loop(
            poll_seconds=poll,
            paper_trade="--live-orders" not in sys.argv,
            use_testnet="--live" not in sys.argv,
        )
    else:
        # Single scan cycle
        try:
            client = DeribitClient(use_testnet="--live" not in sys.argv)
            result = run_scan_cycle(client=client, paper_trade=True)
        except Exception:
            # Run without Deribit (signal-only mode)
            result = run_scan_cycle(client=None, paper_trade=True)

        print(f"Signals: {result['total_signals']}")
        print(f"Open positions: {result['open_positions']}")
        for action in result["actions"]:
            print(f"  {action}")
