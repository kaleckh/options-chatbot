"""
Phase 2: Deribit API client for crypto options.

Fetches option chains, order books, and instrument data.
Uses public endpoints (no auth needed for market data).
Auth required only for order placement (Phase 3).
"""

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx

from .config import DERIBIT_CONFIG


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class OptionInstrument:
    name: str                   # e.g. "BTC-25APR26-80000-C"
    currency: str               # "BTC" or "ETH"
    strike: float
    option_type: str            # "call" or "put"
    expiry: str                 # ISO date
    expiry_timestamp: int       # ms
    tick_size: float
    min_trade_amount: float
    settlement_period: str      # "day", "week", "month"


@dataclass
class OptionQuote:
    instrument: str
    bid: float                  # in BTC/ETH (base currency)
    ask: float
    mark: float
    last: float
    iv: float                   # implied volatility (0-1 scale)
    delta: float
    gamma: float
    theta: float
    vega: float
    open_interest: float
    volume_24h: float
    underlying_price: float


@dataclass
class SpreadCandidate:
    symbol: str                 # "BTC" or "ETH"
    expiry: str
    direction: str              # "call" or "put"
    long_leg: OptionQuote
    short_leg: OptionQuote
    net_debit_base: float       # in BTC/ETH
    net_debit_usd: float
    max_profit_base: float
    max_loss_base: float
    spread_width: float         # strike difference
    risk_reward: float
    dte: int


# ── API client ────────────────────────────────────────────────────────────────

class DeribitClient:
    """Thin wrapper around Deribit REST API v2."""

    def __init__(self, use_testnet: bool = None):
        cfg = DERIBIT_CONFIG
        if use_testnet is None:
            use_testnet = cfg["use_testnet"]
        self.base_url = cfg["testnet_url"] if use_testnet else cfg["base_url"]
        self.client = httpx.Client(timeout=15.0)
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0

    def _get(self, method: str, params: dict = None) -> dict:
        """Call a public Deribit API method."""
        url = f"{self.base_url}/public/{method}"
        resp = self.client.get(url, params=params or {})
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"Deribit API error: {data['error']}")
        return data.get("result", data)

    def _private_get(self, method: str, params: dict = None) -> dict:
        """Call a private Deribit API method (requires auth)."""
        self._ensure_auth()
        url = f"{self.base_url}/private/{method}"
        headers = {"Authorization": f"Bearer {self._access_token}"}
        resp = self.client.get(url, params=params or {}, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"Deribit API error: {data['error']}")
        return data.get("result", data)

    def _ensure_auth(self):
        """Authenticate with Deribit if needed."""
        if self._access_token and time.time() < self._token_expiry:
            return
        cfg = DERIBIT_CONFIG
        if not cfg["client_id"] or not cfg["client_secret"]:
            raise RuntimeError("Deribit API credentials not configured. Set DERIBIT_CLIENT_ID and DERIBIT_CLIENT_SECRET.")
        result = self._get("auth", {
            "grant_type": "client_credentials",
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
        })
        self._access_token = result["access_token"]
        self._token_expiry = time.time() + result.get("expires_in", 900) - 60

    # ── Public market data ────────────────────────────────────────────────

    def get_index_price(self, currency: str = "BTC") -> float:
        """Get current index (spot) price."""
        result = self._get("get_index_price", {"index_name": f"{currency.lower()}_usd"})
        return float(result["index_price"])

    def get_instruments(self, currency: str = "BTC", kind: str = "option", expired: bool = False) -> list[OptionInstrument]:
        """Get all active option instruments for a currency."""
        result = self._get("get_instruments", {
            "currency": currency.upper(),
            "kind": kind,
            "expired": str(expired).lower(),
        })
        instruments = []
        for inst in result:
            if inst.get("option_type") is None:
                continue
            instruments.append(OptionInstrument(
                name=inst["instrument_name"],
                currency=currency.upper(),
                strike=float(inst["strike"]),
                option_type=inst["option_type"],
                expiry=datetime.fromtimestamp(inst["expiration_timestamp"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
                expiry_timestamp=inst["expiration_timestamp"],
                tick_size=float(inst.get("tick_size", 0.0001)),
                min_trade_amount=float(inst.get("min_trade_amount", 0.1)),
                settlement_period=inst.get("settlement_period", ""),
            ))
        return instruments

    def get_order_book(self, instrument_name: str) -> OptionQuote:
        """Get order book with Greeks for a single instrument."""
        result = self._get("get_order_book", {"instrument_name": instrument_name})
        greeks = result.get("greeks", {})
        return OptionQuote(
            instrument=instrument_name,
            bid=float(result.get("best_bid_price") or 0),
            ask=float(result.get("best_ask_price") or 0),
            mark=float(result.get("mark_price") or 0),
            last=float(result.get("last_price") or 0),
            iv=float(result.get("mark_iv", 0)) / 100.0,  # Deribit returns as percentage
            delta=float(greeks.get("delta", 0)),
            gamma=float(greeks.get("gamma", 0)),
            theta=float(greeks.get("theta", 0)),
            vega=float(greeks.get("vega", 0)),
            open_interest=float(result.get("open_interest", 0)),
            volume_24h=float(result.get("stats", {}).get("volume", 0)),
            underlying_price=float(result.get("underlying_price", 0)),
        )

    def get_option_chain(self, currency: str = "BTC", expiry: str = None) -> list[OptionQuote]:
        """
        Get full option chain for a currency/expiry.

        If expiry is None, returns all active options.
        """
        instruments = self.get_instruments(currency, kind="option")
        if expiry:
            instruments = [i for i in instruments if i.expiry == expiry]

        chain = []
        for inst in instruments:
            try:
                quote = self.get_order_book(inst.name)
                chain.append(quote)
            except Exception:
                continue
            time.sleep(0.05)  # rate limit

        return chain

    def get_available_expiries(self, currency: str = "BTC") -> list[dict]:
        """Get available expiry dates with instrument counts."""
        instruments = self.get_instruments(currency)
        expiries = {}
        now = datetime.now(timezone.utc)
        for inst in instruments:
            exp = inst.expiry
            if exp not in expiries:
                dte = (datetime.strptime(exp, "%Y-%m-%d").replace(tzinfo=timezone.utc) - now).days
                expiries[exp] = {"expiry": exp, "dte": dte, "calls": 0, "puts": 0}
            if inst.option_type == "call":
                expiries[exp]["calls"] += 1
            else:
                expiries[exp]["puts"] += 1
        return sorted(expiries.values(), key=lambda x: x["expiry"])

    # ── Trading (Phase 3) ─────────────────────────────────────────────────

    def place_order(self, instrument: str, side: str, amount: float,
                    price: float = None, order_type: str = "limit") -> dict:
        """Place an order on Deribit. Requires auth."""
        params = {
            "instrument_name": instrument,
            "amount": amount,
            "type": order_type,
        }
        if price is not None:
            params["price"] = price
        method = "buy" if side == "buy" else "sell"
        return self._private_get(method, params)

    def get_positions(self, currency: str = "BTC", kind: str = "option") -> list[dict]:
        """Get open positions. Requires auth."""
        return self._private_get("get_positions", {
            "currency": currency.upper(),
            "kind": kind,
        })

    def cancel_all(self, currency: str = "BTC") -> dict:
        """Cancel all open orders. Requires auth."""
        return self._private_get("cancel_all_by_currency", {
            "currency": currency.upper(),
        })


# ── Spread construction ───────────────────────────────────────────────────────

def find_best_spread(
    client: DeribitClient,
    currency: str,
    direction: str,             # "call" or "put"
    config: dict = None,
) -> Optional[SpreadCandidate]:
    """
    Find the best vertical spread from the live Deribit chain.

    For call spreads: buy lower-strike call, sell higher-strike call.
    For put spreads: buy higher-strike put, sell lower-strike put.
    """
    from .config import SPREAD_CONFIG
    cfg = config or SPREAD_CONFIG

    # Get spot price
    spot = client.get_index_price(currency)

    # Find best expiry
    expiries = client.get_available_expiries(currency)
    valid = [e for e in expiries if cfg["dte_min"] <= e["dte"] <= cfg["dte_max"]]
    if not valid:
        return None
    best_expiry = min(valid, key=lambda e: abs(e["dte"] - cfg["dte_target"]))

    # Get all instruments for this expiry
    instruments = client.get_instruments(currency)
    expiry_instruments = [
        i for i in instruments
        if i.expiry == best_expiry["expiry"] and i.option_type == direction
    ]
    if len(expiry_instruments) < 2:
        return None

    # Fetch quotes for all strikes (rate-limited)
    quotes = []
    for inst in expiry_instruments:
        try:
            q = client.get_order_book(inst.name)
            if q.bid > 0 and q.ask > 0:
                quotes.append(q)
        except Exception:
            continue
        time.sleep(0.05)

    if len(quotes) < 2:
        return None

    # Find legs by delta target
    long_target = cfg["long_delta_target"]
    short_target = cfg["short_delta_target"]

    if direction == "call":
        # Calls: positive delta. Long = higher delta (ATM), short = lower delta (OTM)
        long_leg = min(quotes, key=lambda q: abs(abs(q.delta) - long_target))
        short_leg = min(quotes, key=lambda q: abs(abs(q.delta) - short_target))

        long_strike = float(long_leg.instrument.split("-")[2])
        short_strike = float(short_leg.instrument.split("-")[2])
        if long_strike >= short_strike:
            return None
        spread_width = short_strike - long_strike
    else:
        # Puts: negative delta. Long = higher |delta| (ATM), short = lower |delta| (OTM)
        long_leg = min(quotes, key=lambda q: abs(abs(q.delta) - long_target))
        short_leg = min(quotes, key=lambda q: abs(abs(q.delta) - short_target))

        long_strike = float(long_leg.instrument.split("-")[2])
        short_strike = float(short_leg.instrument.split("-")[2])
        if long_strike <= short_strike:
            return None
        spread_width = long_strike - short_strike

    # Net debit (in base currency — BTC or ETH)
    net_debit = long_leg.ask - short_leg.bid  # worst-case fill
    if net_debit <= 0:
        return None

    net_debit_usd = net_debit * spot
    if net_debit_usd < cfg["min_net_debit_usd"]:
        return None

    # Width check
    width_pct = spread_width / spot * 100
    if width_pct > cfg["max_width_pct"]:
        return None

    # Cost efficiency
    max_profit_base = (spread_width / spot) - net_debit  # spreads are in BTC on Deribit
    if max_profit_base <= 0:
        return None

    debit_pct = net_debit / (spread_width / spot) * 100
    if debit_pct > cfg["max_debit_pct_of_width"]:
        return None

    return SpreadCandidate(
        symbol=currency,
        expiry=best_expiry["expiry"],
        direction=direction,
        long_leg=long_leg,
        short_leg=short_leg,
        net_debit_base=round(net_debit, 6),
        net_debit_usd=round(net_debit_usd, 2),
        max_profit_base=round(max_profit_base, 6),
        max_loss_base=round(net_debit, 6),
        spread_width=spread_width,
        risk_reward=round(max_profit_base / net_debit, 2) if net_debit > 0 else 0,
        dte=best_expiry["dte"],
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    client = DeribitClient(use_testnet="--live" not in sys.argv)
    mode = "LIVE" if "--live" in sys.argv else "TESTNET"
    print(f"Deribit {mode} — {client.base_url}")

    for currency in ["BTC", "ETH"]:
        print(f"\n{'='*50}")
        price = client.get_index_price(currency)
        print(f"{currency}: ${price:,.0f}")

        expiries = client.get_available_expiries(currency)
        print(f"Expiries: {len(expiries)}")
        for e in expiries[:5]:
            print(f"  {e['expiry']} ({e['dte']}d): {e['calls']}C/{e['puts']}P")

        if "--spread" in sys.argv:
            spread = find_best_spread(client, currency, "call")
            if spread:
                print(f"\nBest call spread:")
                print(f"  {spread.long_leg.instrument} / {spread.short_leg.instrument}")
                print(f"  Debit: {spread.net_debit_base:.6f} {currency} (${spread.net_debit_usd:.0f})")
                print(f"  Width: ${spread.spread_width:,.0f}")
                print(f"  R:R = {spread.risk_reward:.1f}")
                print(f"  Expiry: {spread.expiry} ({spread.dte}d)")
            else:
                print(f"\n  No valid call spread found")
