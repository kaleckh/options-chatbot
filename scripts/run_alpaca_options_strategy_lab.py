from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_commodity_universe import ai_commodity_scan_tickers  # noqa: E402
from alpaca_market_data import AlpacaMarketDataClient, AlpacaMarketDataError  # noqa: E402
from historical_options_store import DAILY_SNAPSHOT_KIND, HistoricalOptionsStore  # noqa: E402
from options_chatbot import DEFAULT_WATCHLIST  # noqa: E402


DEFAULT_OUTPUT_DIR = ROOT / "data" / "alpaca-options-strategy-lab"
DEFAULT_CACHE_DIR = ROOT / "data" / "alpaca-cache" / "historical-option-bars"
DEFAULT_DATE_FROM = "2024-02-01"
DEFAULT_MIN_TOTAL_TRADES = 50
DEFAULT_MIN_OOS_TRADES = 20
DEFAULT_MIN_PROFIT_FACTOR = 1.15
DEFAULT_PREFERRED_PROFIT_FACTOR = 1.25
DEFAULT_FEE_PER_CONTRACT_USD = 0.65
DEFAULT_BAR_SLIPPAGE_PCT = 0.08
DEFAULT_TARGET_DTE = 35
DEFAULT_MIN_DTE = 21
DEFAULT_MAX_DTE = 49
DEFAULT_HOLD_TRADING_DAYS = 10
DEFAULT_WIDTH_PCT = 0.025
DEFAULT_CONDOR_RANGE_PCT = 0.035
DEFAULT_CONDOR_WING_PCT = 0.02

LANE_PRESETS: dict[str, dict[str, dict[str, Any]]] = {
    "baseline": {},
    "spy_qqq_exact": {
        "bullish": {
            "variant": "pullback_uptrend",
            "hold_days": 15,
            "width_pct": 0.06,
            "max_per_week": 2,
        },
        "bearish": {
            "variant": "overbought_downtrend",
            "hold_days": 3,
            "width_pct": 0.08,
            "max_per_week": 3,
        },
        "sideways": {
            "variant": "calm_uptrend_condor",
            "hold_days": 20,
            "condor_range_pct": 0.05,
            "condor_wing_pct": 0.02,
            "max_per_week": 3,
        },
    },
}


@dataclass(frozen=True)
class LabCandidate:
    lane: str
    symbol: str
    entry_date: date
    score: float
    signal: dict[str, Any]


@dataclass(frozen=True)
class LegQuote:
    symbol: str
    option_type: str
    strike: float
    expiry: date
    bid: float | None
    ask: float | None
    last: float | None
    source: str
    price_basis: str


@dataclass
class SimulatedTrade:
    lane: str
    structure: str
    symbol: str
    entry_date: str
    exit_date: str
    expiry: str
    pnl_pct: float
    pnl_usd: float
    risk_usd: float
    entry_value: float
    exit_value: float
    gross_pnl_usd: float
    fees_usd: float
    evidence_level: str
    data_source: str
    exact_bid_ask: bool
    option_bar_fallback: bool
    legs: list[dict[str, Any]]
    signal: dict[str, Any]
    exit_reason: str


def _load_dotenv_local(path: Path = ROOT / ".env.local") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _parse_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])


def _date_to_utc_end(value: date) -> str:
    return datetime.combine(value, datetime.max.time(), tzinfo=UTC).replace(microsecond=0).isoformat()


def _date_to_utc_start(value: date) -> str:
    return datetime.combine(value, datetime.min.time(), tzinfo=UTC).isoformat()


def _chunked(items: Sequence[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(items), size):
        yield list(items[index : index + size])


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        number = float(value)
        if math.isnan(number):
            return default
        return number
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    number = _safe_float(value)
    return default if number is None else int(number)


def _normal_symbols(scope: str, symbols: str | None) -> list[str]:
    if symbols:
        values = [item.strip().upper() for item in symbols.split(",") if item.strip()]
        return sorted(dict.fromkeys(values))
    normalized_scope = str(scope or "normal").strip().lower()
    if normalized_scope == "commodity":
        return list(ai_commodity_scan_tickers())
    if normalized_scope == "both":
        return sorted(dict.fromkeys([*DEFAULT_WATCHLIST, *ai_commodity_scan_tickers()]))
    return list(DEFAULT_WATCHLIST)


def _stock_frame(client: AlpacaMarketDataClient, symbol: str, start: date, end: date) -> pd.DataFrame:
    warmup = start - timedelta(days=90)
    frame = client.stock_bars(symbol, start=_date_to_utc_start(warmup), end=_date_to_utc_end(end), interval="1d")
    if frame.empty:
        return pd.DataFrame()
    out = frame.copy()
    out.index = pd.to_datetime(out.index, utc=True).date
    out = out[~pd.Index(out.index).duplicated(keep="last")]
    out = out.sort_index()
    for column in ("Open", "High", "Low", "Close", "Volume"):
        if column in out:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    close = out["Close"]
    out["sma20"] = close.rolling(20).mean()
    out["sma50"] = close.rolling(50).mean()
    out["ret5"] = close.pct_change(5) * 100.0
    out["ret10"] = close.pct_change(10) * 100.0
    out["ret20"] = close.pct_change(20) * 100.0
    out["vol20"] = close.pct_change().rolling(20).std() * math.sqrt(252)
    high_low = (out["High"] - out["Low"]).abs() if {"High", "Low"}.issubset(out.columns) else close * 0
    out["range_pct20"] = (high_low / close).rolling(20).mean() * 100.0
    return out


def _candidate_date_index(frame: pd.DataFrame, start: date, end: date) -> list[date]:
    dates: list[date] = []
    for value in frame.index:
        current = _parse_date(value)
        if start <= current <= end:
            row = frame.loc[current]
            if not pd.isna(row.get("sma50")) and not pd.isna(row.get("ret5")):
                dates.append(current)
    return dates


def _build_candidates(
    histories: dict[str, pd.DataFrame],
    *,
    lane: str,
    variant: str,
    start: date,
    end: date,
    max_per_week: int,
) -> tuple[list[LabCandidate], Counter[str]]:
    normalized_variant = str(variant or "baseline").strip().lower()
    grouped: dict[tuple[int, int], list[LabCandidate]] = defaultdict(list)
    rejected: Counter[str] = Counter()
    for symbol, frame in histories.items():
        if frame.empty:
            rejected["missing_stock_history"] += 1
            continue
        for current in _candidate_date_index(frame, start, end):
            row = frame.loc[current]
            close = float(row["Close"])
            sma20 = float(row["sma20"])
            sma50 = float(row["sma50"])
            ret5 = float(row["ret5"])
            ret10 = float(row["ret10"])
            ret20 = float(row["ret20"])
            vol20 = float(row["vol20"]) if not pd.isna(row.get("vol20")) else 0.0
            range_pct20 = float(row["range_pct20"]) if not pd.isna(row.get("range_pct20")) else 0.0
            signal = {
                "close": round(close, 4),
                "sma20": round(sma20, 4),
                "sma50": round(sma50, 4),
                "ret5_pct": round(ret5, 3),
                "ret10_pct": round(ret10, 3),
                "ret20_pct": round(ret20, 3),
                "vol20": round(vol20, 4),
                "range_pct20": round(range_pct20, 3),
                "variant": normalized_variant,
            }
            if lane == "bullish":
                if normalized_variant == "pullback_uptrend":
                    is_match = close > sma50 and ret20 > 2.0 and -4.0 < ret5 < 0.25
                    score = ret20 - abs(ret5) * 0.5
                elif normalized_variant == "sma_reclaim":
                    is_match = close > sma20 and close > sma50 and ret5 > 0.0 and ret10 < 3.5 and ret20 > 0.0
                    score = ((close / sma20) - 1.0) * 100.0 + ret5
                elif normalized_variant == "trend_strict":
                    is_match = close > sma20 > sma50 and ret5 > 1.0 and ret20 > 2.0
                    score = ret5 + ret20 * 0.4
                elif normalized_variant == "oversold_index_uptrend":
                    is_match = close > sma50 and ret5 < -1.0 and ret20 > -2.0
                    score = abs(ret5) + max(ret20, 0.0)
                else:
                    is_match = close > sma20 > sma50 and ret5 > 0.35 and ret20 > 0.0
                    score = ret5 + max(ret20, 0.0) * 0.3 + ((close / sma50) - 1.0) * 100.0
                if not is_match:
                    rejected["bullish_signal_filter"] += 1
                    continue
            elif lane == "bearish":
                if normalized_variant == "overbought_downtrend":
                    is_match = close < sma50 and ret5 > 1.0 and ret20 < 2.0
                    score = ret5 + abs(min(ret20, 0.0))
                elif normalized_variant == "failed_reclaim":
                    is_match = close < sma50 and close > sma20 and ret20 < -3.0 and ret5 > 0.0
                    score = abs(ret20) + ret5 * 0.2
                elif normalized_variant == "panic_followthrough":
                    is_match = close < sma20 and ret5 < -2.5 and ret10 < -3.0
                    score = abs(ret5) + abs(ret10) * 0.4
                elif normalized_variant == "breakdown_strict":
                    is_match = close < sma20 < sma50 and ret5 < -1.0 and ret20 < -2.0
                    score = abs(ret5) + abs(ret20) * 0.4
                else:
                    is_match = close < sma20 < sma50 and ret5 < -0.35 and ret20 < 0.0
                    score = abs(ret5) + abs(min(ret20, 0.0)) * 0.3 + ((sma50 / close) - 1.0) * 100.0
                if not is_match:
                    rejected["bearish_signal_filter"] += 1
                    continue
            else:
                distance_to_sma20 = abs(close / sma20 - 1.0) * 100.0 if sma20 > 0 else 999.0
                if normalized_variant == "calm_uptrend_condor":
                    is_match = close > sma50 and abs(ret5) <= 1.5 and ret20 > 0.0 and 0 < vol20 < 0.22 and distance_to_sma20 <= 3.0
                    score = ret20 * 0.2 + (0.22 - vol20) * 20.0 + 3.0 - abs(ret5)
                elif normalized_variant == "wide_range":
                    is_match = abs(ret10) <= 3.0 and abs(ret20) <= 5.0 and distance_to_sma20 <= 3.0
                    score = 5.0 - abs(ret20) + range_pct20
                elif normalized_variant == "low_vol_flat":
                    is_match = abs(ret20) <= 4.0 and 0 < vol20 < 0.20 and distance_to_sma20 <= 2.5
                    score = (0.20 - vol20) * 20.0 + 5.0 - abs(ret20)
                elif normalized_variant == "tight_range":
                    is_match = abs(ret10) <= 1.5 and abs(ret20) <= 3.0 and distance_to_sma20 <= 1.5
                    score = 5.0 - abs(ret20) + range_pct20
                elif normalized_variant == "post_move_pause":
                    is_match = abs(ret5) <= 1.0 and abs(ret10) <= 2.0 and ret20 > 0.0 and distance_to_sma20 <= 2.5
                    score = 4.0 - abs(ret10) + ret20 * 0.2
                else:
                    is_match = abs(ret10) <= 2.0 and abs(ret20) <= 4.0 and distance_to_sma20 <= 2.0 and vol20 > 0
                    score = max(0.0, 5.0 - abs(ret20)) + max(0.0, 3.0 - distance_to_sma20) + range_pct20
                if not is_match:
                    rejected["sideways_range_filter"] += 1
                    continue
            iso = current.isocalendar()
            grouped[(int(iso.year), int(iso.week))].append(
                LabCandidate(lane=lane, symbol=symbol, entry_date=current, score=round(float(score), 4), signal=signal)
            )
    selected: list[LabCandidate] = []
    for key in sorted(grouped):
        selected.extend(sorted(grouped[key], key=lambda item: item.score, reverse=True)[:max_per_week])
    return selected, rejected


class OptionEvidenceProvider:
    def __init__(
        self,
        *,
        client: AlpacaMarketDataClient,
        store: HistoricalOptionsStore,
        cache_dir: Path,
        allow_alpaca_bars: bool,
    ) -> None:
        self.client = client
        self.store = store
        self.cache_dir = Path(cache_dir)
        self.allow_alpaca_bars = bool(allow_alpaca_bars)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._contract_cache: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = {}
        self._bar_memory: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        self._store_chain_cache: dict[tuple[str, str, str, str, str], list[sqlite3.Row]] = {}
        self._store_closing_cache: dict[tuple[str, str], LegQuote | None] = {}

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.store.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _store_chain_rows(
        self,
        *,
        symbol: str,
        quote_date: date,
        option_type: str,
        min_expiry: date,
        max_expiry: date,
    ) -> list[sqlite3.Row]:
        cache_key = (
            symbol.upper(),
            quote_date.isoformat(),
            option_type,
            min_expiry.isoformat(),
            max_expiry.isoformat(),
        )
        if cache_key in self._store_chain_cache:
            return self._store_chain_cache[cache_key]
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT q.*
                FROM option_quote_snapshots q
                JOIN import_batches b ON b.id = q.source_batch_id
                WHERE q.underlying = ?
                  AND q.snapshot_kind = ?
                  AND q.quote_date_et = ?
                  AND q.option_type = ?
                  AND q.expiry >= ?
                  AND q.expiry <= ?
                  AND b.data_trust = 'trusted'
                  AND q.bid IS NOT NULL
                  AND q.ask IS NOT NULL
                  AND q.bid >= 0
                  AND q.ask > 0
                ORDER BY q.expiry ASC, q.strike ASC
                """,
                (
                    symbol.upper(),
                    DAILY_SNAPSHOT_KIND,
                    quote_date.isoformat(),
                    option_type,
                    min_expiry.isoformat(),
                    max_expiry.isoformat(),
                ),
            ).fetchall()
        self._store_chain_cache[cache_key] = list(rows)
        return self._store_chain_cache[cache_key]

    def _row_to_leg(self, row: sqlite3.Row) -> LegQuote:
        return LegQuote(
            symbol=str(row["contract_symbol"]),
            option_type=str(row["option_type"]),
            strike=float(row["strike"]),
            expiry=_parse_date(row["expiry"]),
            bid=_safe_float(row["bid"]),
            ask=_safe_float(row["ask"]),
            last=_safe_float(row["last"]),
            source="local_daily_exact_bid_ask",
            price_basis="bid_ask",
        )

    @staticmethod
    def _nearest(rows: Sequence[sqlite3.Row], target: float, *, above: bool | None = None) -> sqlite3.Row | None:
        filtered: list[sqlite3.Row] = []
        for row in rows:
            strike = float(row["strike"])
            if above is True and strike <= target:
                continue
            if above is False and strike >= target:
                continue
            filtered.append(row)
        if not filtered:
            filtered = list(rows)
        return min(filtered, key=lambda row: abs(float(row["strike"]) - target), default=None)

    def _select_store_vertical(
        self,
        *,
        symbol: str,
        entry_date: date,
        option_type: str,
        spot: float,
        target_dte: int,
        min_dte: int,
        max_dte: int,
        width_pct: float,
    ) -> list[LegQuote] | None:
        min_expiry = entry_date + timedelta(days=min_dte)
        max_expiry = entry_date + timedelta(days=max_dte)
        rows = self._store_chain_rows(
            symbol=symbol,
            quote_date=entry_date,
            option_type=option_type,
            min_expiry=min_expiry,
            max_expiry=max_expiry,
        )
        if not rows:
            return None
        by_expiry: dict[date, list[sqlite3.Row]] = defaultdict(list)
        for row in rows:
            by_expiry[_parse_date(row["expiry"])].append(row)
        target_expiry = entry_date + timedelta(days=target_dte)
        expiries = sorted(by_expiry, key=lambda item: abs((item - target_expiry).days))
        for expiry in expiries:
            expiry_rows = by_expiry[expiry]
            long_row = self._nearest(expiry_rows, spot)
            if long_row is None:
                continue
            long_strike = float(long_row["strike"])
            if option_type == "call":
                short_target = max(spot * (1.0 + width_pct), long_strike + 0.5)
                short_row = self._nearest(expiry_rows, short_target, above=True)
                valid = short_row is not None and float(short_row["strike"]) > long_strike
            else:
                short_target = min(spot * (1.0 - width_pct), long_strike - 0.5)
                short_row = self._nearest(expiry_rows, short_target, above=False)
                valid = short_row is not None and float(short_row["strike"]) < long_strike
            if not valid or short_row is None:
                continue
            return [self._row_to_leg(long_row), self._row_to_leg(short_row)]
        return None

    def _select_store_condor(
        self,
        *,
        symbol: str,
        entry_date: date,
        spot: float,
        target_dte: int,
        min_dte: int,
        max_dte: int,
        range_pct: float,
        wing_pct: float,
    ) -> list[LegQuote] | None:
        min_expiry = entry_date + timedelta(days=min_dte)
        max_expiry = entry_date + timedelta(days=max_dte)
        call_rows = self._store_chain_rows(
            symbol=symbol,
            quote_date=entry_date,
            option_type="call",
            min_expiry=min_expiry,
            max_expiry=max_expiry,
        )
        put_rows = self._store_chain_rows(
            symbol=symbol,
            quote_date=entry_date,
            option_type="put",
            min_expiry=min_expiry,
            max_expiry=max_expiry,
        )
        if not call_rows or not put_rows:
            return None
        by_expiry_calls: dict[date, list[sqlite3.Row]] = defaultdict(list)
        by_expiry_puts: dict[date, list[sqlite3.Row]] = defaultdict(list)
        for row in call_rows:
            by_expiry_calls[_parse_date(row["expiry"])].append(row)
        for row in put_rows:
            by_expiry_puts[_parse_date(row["expiry"])].append(row)
        target_expiry = entry_date + timedelta(days=target_dte)
        common_expiries = sorted(
            set(by_expiry_calls).intersection(by_expiry_puts),
            key=lambda item: abs((item - target_expiry).days),
        )
        for expiry in common_expiries:
            calls = by_expiry_calls[expiry]
            puts = by_expiry_puts[expiry]
            short_call = self._nearest(calls, spot * (1.0 + range_pct), above=True)
            long_call = self._nearest(calls, spot * (1.0 + range_pct + wing_pct), above=True)
            short_put = self._nearest(puts, spot * (1.0 - range_pct), above=False)
            long_put = self._nearest(puts, spot * (1.0 - range_pct - wing_pct), above=False)
            if not (short_call and long_call and short_put and long_put):
                continue
            if not (float(long_call["strike"]) > float(short_call["strike"])):
                continue
            if not (float(long_put["strike"]) < float(short_put["strike"])):
                continue
            return [
                self._row_to_leg(short_put),
                self._row_to_leg(long_put),
                self._row_to_leg(short_call),
                self._row_to_leg(long_call),
            ]
        return None

    def _contracts(
        self,
        *,
        symbol: str,
        option_type: str,
        min_expiry: date,
        max_expiry: date,
    ) -> list[dict[str, Any]]:
        today = datetime.now(UTC).date()
        status = "inactive" if max_expiry < today else "active"
        cache_key = (symbol.upper(), option_type, min_expiry.isoformat(), max_expiry.isoformat(), status)
        if cache_key in self._contract_cache:
            return self._contract_cache[cache_key]
        rows = self.client.option_contracts(
            symbol,
            status=status,
            expiration_date_gte=min_expiry.isoformat(),
            expiration_date_lte=max_expiry.isoformat(),
            option_type=option_type,
        )
        self._contract_cache[cache_key] = rows
        return rows

    @staticmethod
    def _contract_leg(contract: dict[str, Any]) -> LegQuote:
        return LegQuote(
            symbol=str(contract.get("symbol") or "").upper(),
            option_type=str(contract.get("type") or "").lower(),
            strike=float(contract.get("strike_price") or 0.0),
            expiry=_parse_date(contract.get("expiration_date")),
            bid=None,
            ask=None,
            last=None,
            source="alpaca_opra_historical_bars",
            price_basis="bar_close",
        )

    @staticmethod
    def _nearest_contract(
        contracts: Sequence[dict[str, Any]],
        *,
        target_expiry: date,
        target_strike: float,
        above: bool | None = None,
    ) -> dict[str, Any] | None:
        filtered: list[dict[str, Any]] = []
        for contract in contracts:
            strike = _safe_float(contract.get("strike_price"))
            expiry_raw = contract.get("expiration_date")
            if strike is None or not expiry_raw:
                continue
            if above is True and strike <= target_strike:
                continue
            if above is False and strike >= target_strike:
                continue
            filtered.append(contract)
        if not filtered:
            return None
        return min(
            filtered,
            key=lambda contract: (
                abs((_parse_date(contract.get("expiration_date")) - target_expiry).days),
                abs(float(contract.get("strike_price") or 0.0) - target_strike),
            ),
        )

    def _select_alpaca_vertical(
        self,
        *,
        symbol: str,
        entry_date: date,
        option_type: str,
        spot: float,
        target_dte: int,
        min_dte: int,
        max_dte: int,
        width_pct: float,
    ) -> list[LegQuote] | None:
        if not self.allow_alpaca_bars:
            return None
        min_expiry = entry_date + timedelta(days=min_dte)
        max_expiry = entry_date + timedelta(days=max_dte)
        target_expiry = entry_date + timedelta(days=target_dte)
        contracts = self._contracts(symbol=symbol, option_type=option_type, min_expiry=min_expiry, max_expiry=max_expiry)
        if not contracts:
            return None
        long_contract = self._nearest_contract(contracts, target_expiry=target_expiry, target_strike=spot)
        if long_contract is None:
            return None
        long_strike = float(long_contract.get("strike_price") or 0.0)
        if option_type == "call":
            short_target = max(spot * (1.0 + width_pct), long_strike + 0.5)
            short_contract = self._nearest_contract(
                contracts, target_expiry=_parse_date(long_contract.get("expiration_date")), target_strike=short_target, above=True
            )
            valid = short_contract is not None and float(short_contract.get("strike_price") or 0.0) > long_strike
        else:
            short_target = min(spot * (1.0 - width_pct), long_strike - 0.5)
            short_contract = self._nearest_contract(
                contracts, target_expiry=_parse_date(long_contract.get("expiration_date")), target_strike=short_target, above=False
            )
            valid = short_contract is not None and float(short_contract.get("strike_price") or 0.0) < long_strike
        if not valid or short_contract is None:
            return None
        return [self._contract_leg(long_contract), self._contract_leg(short_contract)]

    def _select_alpaca_condor(
        self,
        *,
        symbol: str,
        entry_date: date,
        spot: float,
        target_dte: int,
        min_dte: int,
        max_dte: int,
        range_pct: float,
        wing_pct: float,
    ) -> list[LegQuote] | None:
        if not self.allow_alpaca_bars:
            return None
        min_expiry = entry_date + timedelta(days=min_dte)
        max_expiry = entry_date + timedelta(days=max_dte)
        target_expiry = entry_date + timedelta(days=target_dte)
        calls = self._contracts(symbol=symbol, option_type="call", min_expiry=min_expiry, max_expiry=max_expiry)
        puts = self._contracts(symbol=symbol, option_type="put", min_expiry=min_expiry, max_expiry=max_expiry)
        short_put = self._nearest_contract(puts, target_expiry=target_expiry, target_strike=spot * (1 - range_pct), above=False)
        if not short_put:
            return None
        expiry = _parse_date(short_put.get("expiration_date"))
        short_call = self._nearest_contract(calls, target_expiry=expiry, target_strike=spot * (1 + range_pct), above=True)
        long_put = self._nearest_contract(puts, target_expiry=expiry, target_strike=spot * (1 - range_pct - wing_pct), above=False)
        long_call = self._nearest_contract(calls, target_expiry=expiry, target_strike=spot * (1 + range_pct + wing_pct), above=True)
        if not (short_call and long_put and long_call):
            return None
        if _parse_date(short_call.get("expiration_date")) != expiry or _parse_date(long_put.get("expiration_date")) != expiry or _parse_date(long_call.get("expiration_date")) != expiry:
            return None
        return [
            self._contract_leg(short_put),
            self._contract_leg(long_put),
            self._contract_leg(short_call),
            self._contract_leg(long_call),
        ]

    def select_legs(
        self,
        *,
        candidate: LabCandidate,
        spot: float,
        target_dte: int,
        min_dte: int,
        max_dte: int,
        width_pct: float,
        condor_range_pct: float,
        condor_wing_pct: float,
    ) -> tuple[list[LegQuote] | None, str]:
        if candidate.lane == "bullish":
            legs = self._select_store_vertical(
                symbol=candidate.symbol,
                entry_date=candidate.entry_date,
                option_type="call",
                spot=spot,
                target_dte=target_dte,
                min_dte=min_dte,
                max_dte=max_dte,
                width_pct=width_pct,
            )
            if legs:
                return legs, "local_daily_exact_bid_ask"
            legs = self._select_alpaca_vertical(
                symbol=candidate.symbol,
                entry_date=candidate.entry_date,
                option_type="call",
                spot=spot,
                target_dte=target_dte,
                min_dte=min_dte,
                max_dte=max_dte,
                width_pct=width_pct,
            )
            return legs, "alpaca_opra_historical_bars" if legs else "no_contracts"
        if candidate.lane == "bearish":
            legs = self._select_store_vertical(
                symbol=candidate.symbol,
                entry_date=candidate.entry_date,
                option_type="put",
                spot=spot,
                target_dte=target_dte,
                min_dte=min_dte,
                max_dte=max_dte,
                width_pct=width_pct,
            )
            if legs:
                return legs, "local_daily_exact_bid_ask"
            legs = self._select_alpaca_vertical(
                symbol=candidate.symbol,
                entry_date=candidate.entry_date,
                option_type="put",
                spot=spot,
                target_dte=target_dte,
                min_dte=min_dte,
                max_dte=max_dte,
                width_pct=width_pct,
            )
            return legs, "alpaca_opra_historical_bars" if legs else "no_contracts"
        legs = self._select_store_condor(
            symbol=candidate.symbol,
            entry_date=candidate.entry_date,
            spot=spot,
            target_dte=target_dte,
            min_dte=min_dte,
            max_dte=max_dte,
            range_pct=condor_range_pct,
            wing_pct=condor_wing_pct,
        )
        if legs:
            return legs, "local_daily_exact_bid_ask"
        legs = self._select_alpaca_condor(
            symbol=candidate.symbol,
            entry_date=candidate.entry_date,
            spot=spot,
            target_dte=target_dte,
            min_dte=min_dte,
            max_dte=max_dte,
            range_pct=condor_range_pct,
            wing_pct=condor_wing_pct,
        )
        return legs, "alpaca_opra_historical_bars" if legs else "no_contracts"

    def _cache_path(self, symbol: str, start: date, end: date) -> Path:
        safe = f"{symbol}_{start.isoformat()}_{end.isoformat()}.json".replace(":", "")
        return self.cache_dir / safe

    def _bars_for_symbols(self, symbols: Sequence[str], start: date, end: date) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        missing: list[str] = []
        for symbol in symbols:
            cache_key = (symbol, start.isoformat(), end.isoformat())
            if cache_key in self._bar_memory:
                result[symbol] = self._bar_memory[cache_key]
                continue
            cache_path = self._cache_path(symbol, start, end)
            if cache_path.exists():
                rows = json.loads(cache_path.read_text(encoding="utf8"))
                self._bar_memory[cache_key] = rows if isinstance(rows, list) else []
                result[symbol] = self._bar_memory[cache_key]
                continue
            missing.append(symbol)
        for chunk in _chunked(missing, 100):
            payload = self.client.historical_option_bars(
                chunk,
                start=_date_to_utc_start(start),
                end=_date_to_utc_end(end),
                timeframe="1Day",
            )
            for symbol in chunk:
                rows = list(payload.get(symbol) or [])
                cache_key = (symbol, start.isoformat(), end.isoformat())
                self._bar_memory[cache_key] = rows
                result[symbol] = rows
                self._cache_path(symbol, start, end).write_text(json.dumps(rows, separators=(",", ":")), encoding="utf8")
        return result

    @staticmethod
    def _bar_close_on_or_after(rows: Sequence[dict[str, Any]], target: date) -> tuple[float | None, date | None]:
        candidates: list[tuple[date, float]] = []
        for row in rows:
            row_date = _parse_date(row.get("t"))
            close = _safe_float(row.get("c"))
            if close is None:
                continue
            if row_date >= target:
                candidates.append((row_date, close))
        if not candidates:
            return None, None
        row_date, close = min(candidates, key=lambda item: item[0])
        return close, row_date

    @staticmethod
    def _bar_close_on_or_before(rows: Sequence[dict[str, Any]], target: date) -> tuple[float | None, date | None]:
        candidates: list[tuple[date, float]] = []
        for row in rows:
            row_date = _parse_date(row.get("t"))
            close = _safe_float(row.get("c"))
            if close is None:
                continue
            if row_date <= target:
                candidates.append((row_date, close))
        if not candidates:
            return None, None
        row_date, close = max(candidates, key=lambda item: item[0])
        return close, row_date

    def fill_bar_prices(self, legs: list[LegQuote], entry_date: date, exit_date: date) -> tuple[list[LegQuote] | None, list[LegQuote] | None]:
        symbols = [leg.symbol for leg in legs]
        bars = self._bars_for_symbols(symbols, entry_date, exit_date)
        entry_legs: list[LegQuote] = []
        exit_legs: list[LegQuote] = []
        for leg in legs:
            rows = bars.get(leg.symbol) or []
            entry_close, _entry_bar_date = self._bar_close_on_or_after(rows, entry_date)
            exit_close, _exit_bar_date = self._bar_close_on_or_before(rows, exit_date)
            if entry_close is None or exit_close is None:
                return None, None
            entry_legs.append(
                LegQuote(**{**asdict(leg), "last": entry_close, "source": "alpaca_opra_historical_bars", "price_basis": "bar_close"})
            )
            exit_legs.append(
                LegQuote(**{**asdict(leg), "last": exit_close, "source": "alpaca_opra_historical_bars", "price_basis": "bar_close"})
            )
        return entry_legs, exit_legs

    def closing_quotes_for_store_legs(self, legs: list[LegQuote], exit_date: date) -> list[LegQuote] | None:
        exit_legs: list[LegQuote] = []
        for leg in legs:
            cache_key = (leg.symbol, exit_date.isoformat())
            if cache_key not in self._store_closing_cache:
                quote = self.store.get_closing_quote(
                    contract_symbol=leg.symbol,
                    quote_date_et=exit_date,
                    snapshot_kind=DAILY_SNAPSHOT_KIND,
                    allow_last_price=False,
                )
                if quote is None or quote.bid is None or quote.ask is None:
                    self._store_closing_cache[cache_key] = None
                else:
                    self._store_closing_cache[cache_key] = LegQuote(
                        symbol=quote.contract_symbol,
                        option_type=quote.option_type,
                        strike=quote.strike,
                        expiry=_parse_date(quote.expiry),
                        bid=quote.bid,
                        ask=quote.ask,
                        last=quote.last,
                        source="local_daily_exact_bid_ask",
                        price_basis="bid_ask",
                    )
            cached = self._store_closing_cache[cache_key]
            if cached is None:
                return None
            exit_legs.append(cached)
        return exit_legs


def _exit_date_for_trade(frame: pd.DataFrame, entry: date, expiry: date, hold_days: int) -> date | None:
    trade_dates = [_parse_date(item) for item in frame.index if entry < _parse_date(item) <= expiry]
    if not trade_dates:
        return None
    target_index = min(max(int(hold_days), 1) - 1, len(trade_dates) - 1)
    return trade_dates[target_index]


def _debit_vertical_value(legs: Sequence[LegQuote], *, side: str, slippage_pct: float) -> float | None:
    long_leg, short_leg = legs[0], legs[1]
    exact = long_leg.bid is not None and long_leg.ask is not None and short_leg.bid is not None and short_leg.ask is not None
    if exact:
        if side == "entry":
            return float(long_leg.ask or 0.0) - float(short_leg.bid or 0.0)
        return float(long_leg.bid or 0.0) - float(short_leg.ask or 0.0)
    if long_leg.last is None or short_leg.last is None:
        return None
    if side == "entry":
        return float(long_leg.last) * (1.0 + slippage_pct) - float(short_leg.last) * (1.0 - slippage_pct)
    return float(long_leg.last) * (1.0 - slippage_pct) - float(short_leg.last) * (1.0 + slippage_pct)


def _leg_payload(leg: LegQuote) -> dict[str, Any]:
    payload = asdict(leg)
    payload["expiry"] = leg.expiry.isoformat()
    return payload


def _condor_value(legs: Sequence[LegQuote], *, side: str, slippage_pct: float) -> float | None:
    short_put, long_put, short_call, long_call = legs
    exact = all(leg.bid is not None and leg.ask is not None for leg in legs)
    if exact:
        if side == "entry":
            return (
                float(short_put.bid or 0.0)
                - float(long_put.ask or 0.0)
                + float(short_call.bid or 0.0)
                - float(long_call.ask or 0.0)
            )
        return (
            float(short_put.ask or 0.0)
            - float(long_put.bid or 0.0)
            + float(short_call.ask or 0.0)
            - float(long_call.bid or 0.0)
        )
    if any(leg.last is None for leg in legs):
        return None
    if side == "entry":
        return (
            float(short_put.last) * (1.0 - slippage_pct)
            - float(long_put.last) * (1.0 + slippage_pct)
            + float(short_call.last) * (1.0 - slippage_pct)
            - float(long_call.last) * (1.0 + slippage_pct)
        )
    return (
        float(short_put.last) * (1.0 + slippage_pct)
        - float(long_put.last) * (1.0 - slippage_pct)
        + float(short_call.last) * (1.0 + slippage_pct)
        - float(long_call.last) * (1.0 - slippage_pct)
    )


def _simulate_candidate(
    candidate: LabCandidate,
    *,
    provider: OptionEvidenceProvider,
    histories: dict[str, pd.DataFrame],
    target_dte: int,
    min_dte: int,
    max_dte: int,
    hold_days: int,
    width_pct: float,
    condor_range_pct: float,
    condor_wing_pct: float,
    fee_per_contract: float,
    bar_slippage_pct: float,
) -> tuple[SimulatedTrade | None, str | None]:
    frame = histories.get(candidate.symbol)
    if frame is None or frame.empty or candidate.entry_date not in frame.index:
        return None, "missing_underlying_entry"
    spot = float(frame.loc[candidate.entry_date]["Close"])
    legs, selection_source = provider.select_legs(
        candidate=candidate,
        spot=spot,
        target_dte=target_dte,
        min_dte=min_dte,
        max_dte=max_dte,
        width_pct=width_pct,
        condor_range_pct=condor_range_pct,
        condor_wing_pct=condor_wing_pct,
    )
    if not legs:
        return None, selection_source
    expiry = min(leg.expiry for leg in legs)
    exit_date = _exit_date_for_trade(frame, candidate.entry_date, expiry, hold_days)
    if exit_date is None:
        return None, "missing_exit_date"
    exact_entry = all(leg.source == "local_daily_exact_bid_ask" and leg.bid is not None and leg.ask is not None for leg in legs)
    if exact_entry:
        exit_legs = provider.closing_quotes_for_store_legs(legs, exit_date)
        if exit_legs is None:
            if not provider.allow_alpaca_bars:
                return None, "missing_exact_exit_quotes"
            entry_legs, exit_legs = provider.fill_bar_prices(legs, candidate.entry_date, exit_date)
            if entry_legs is None or exit_legs is None:
                return None, "missing_alpaca_bar_exit"
            legs = entry_legs
    else:
        entry_legs, exit_legs = provider.fill_bar_prices(legs, candidate.entry_date, exit_date)
        if entry_legs is None or exit_legs is None:
            return None, "missing_alpaca_bar_entry_or_exit"
        legs = entry_legs
    exact_bid_ask = (
        all(leg.source == "local_daily_exact_bid_ask" and leg.bid is not None and leg.ask is not None for leg in legs)
        and all(leg.source == "local_daily_exact_bid_ask" and leg.bid is not None and leg.ask is not None for leg in exit_legs)
    )
    option_bar_fallback = not exact_bid_ask

    if candidate.lane in {"bullish", "bearish"}:
        entry_value = _debit_vertical_value(legs, side="entry", slippage_pct=bar_slippage_pct)
        exit_value = _debit_vertical_value(exit_legs, side="exit", slippage_pct=bar_slippage_pct)
        if entry_value is None or exit_value is None:
            return None, "missing_vertical_value"
        width = abs(float(legs[0].strike) - float(legs[1].strike))
        if entry_value <= 0.01 or width <= 0 or entry_value >= width:
            return None, "invalid_vertical_debit"
        gross_pnl_usd = (exit_value - entry_value) * 100.0
        risk_usd = entry_value * 100.0
        fees = 4.0 * fee_per_contract
        pnl_usd = gross_pnl_usd - fees
        structure = "call_debit_spread" if candidate.lane == "bullish" else "put_debit_spread"
    else:
        entry_value = _condor_value(legs, side="entry", slippage_pct=bar_slippage_pct)
        exit_value = _condor_value(exit_legs, side="exit", slippage_pct=bar_slippage_pct)
        if entry_value is None or exit_value is None:
            return None, "missing_condor_value"
        put_width = abs(float(legs[0].strike) - float(legs[1].strike))
        call_width = abs(float(legs[3].strike) - float(legs[2].strike))
        width = max(put_width, call_width)
        if entry_value <= 0.01 or width <= 0 or entry_value >= width:
            return None, "invalid_condor_credit"
        gross_pnl_usd = (entry_value - exit_value) * 100.0
        risk_usd = max((width - entry_value) * 100.0, 1.0)
        fees = 8.0 * fee_per_contract
        pnl_usd = gross_pnl_usd - fees
        structure = "defined_risk_iron_condor"
    if risk_usd <= 0:
        return None, "invalid_risk"
    pnl_pct = pnl_usd / risk_usd * 100.0
    evidence_level = "exact_bid_ask" if exact_bid_ask else "alpaca_opra_historical_bars_no_bidask"
    data_source = "local_daily_exact_bid_ask" if exact_bid_ask else "alpaca_opra_historical_bars"
    trade = SimulatedTrade(
        lane=candidate.lane,
        structure=structure,
        symbol=candidate.symbol,
        entry_date=candidate.entry_date.isoformat(),
        exit_date=exit_date.isoformat(),
        expiry=expiry.isoformat(),
        pnl_pct=round(pnl_pct, 2),
        pnl_usd=round(pnl_usd, 2),
        risk_usd=round(risk_usd, 2),
        entry_value=round(entry_value, 4),
        exit_value=round(exit_value, 4),
        gross_pnl_usd=round(gross_pnl_usd, 2),
        fees_usd=round(fees, 2),
        evidence_level=evidence_level,
        data_source=data_source,
        exact_bid_ask=exact_bid_ask,
        option_bar_fallback=option_bar_fallback,
        legs=[_leg_payload(leg) for leg in legs],
        signal={**candidate.signal, "candidate_score": candidate.score},
        exit_reason=f"{hold_days}_trading_day_hold",
    )
    return trade, None


def _profit_factor(values: Sequence[float]) -> float:
    gross_profit = sum(value for value in values if value > 0)
    gross_loss = -sum(value for value in values if value < 0)
    if gross_loss > 0:
        return gross_profit / gross_loss
    if gross_profit > 0:
        return 999.0
    return 0.0


def _max_drawdown(values: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        equity += float(value)
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return max_dd


def _summarize_trades(trades: Sequence[SimulatedTrade]) -> dict[str, Any]:
    values = [float(trade.pnl_pct) for trade in trades]
    months = sorted({trade.entry_date[:7] for trade in trades})
    expiries = sorted({trade.expiry for trade in trades})
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    return {
        "trade_count": len(trades),
        "win_rate_pct": round(len(wins) / len(values) * 100.0, 2) if values else 0.0,
        "profit_factor": round(_profit_factor(values), 4),
        "avg_pnl_pct": round(sum(values) / len(values), 4) if values else 0.0,
        "median_pnl_pct": round(float(pd.Series(values).median()), 4) if values else 0.0,
        "gross_profit_pct": round(sum(wins), 4),
        "gross_loss_pct": round(sum(losses), 4),
        "max_drawdown_pct_points": round(_max_drawdown(values), 4),
        "best_pnl_pct": round(max(values), 4) if values else None,
        "worst_pnl_pct": round(min(values), 4) if values else None,
        "month_count": len(months),
        "months": months,
        "expiration_cycle_count": len(expiries),
        "exact_bid_ask_count": sum(1 for trade in trades if trade.exact_bid_ask),
        "bar_fallback_count": sum(1 for trade in trades if trade.option_bar_fallback),
    }


def _window_key(value: str) -> str:
    parsed = _parse_date(value)
    half = "H1" if parsed.month <= 6 else "H2"
    return f"{parsed.year}-{half}"


def _walk_forward(trades: Sequence[SimulatedTrade]) -> list[dict[str, Any]]:
    groups: dict[str, list[SimulatedTrade]] = defaultdict(list)
    for trade in trades:
        groups[_window_key(trade.entry_date)].append(trade)
    return [
        {"window": key, **_summarize_trades(sorted(groups[key], key=lambda item: item.entry_date))}
        for key in sorted(groups)
    ]


def _lane_report(
    lane: str,
    trades: Sequence[SimulatedTrade],
    *,
    rejected: Counter[str],
    oos_start: date,
    min_total_trades: int,
    min_oos_trades: int,
    min_profit_factor: float,
    preferred_profit_factor: float,
) -> dict[str, Any]:
    ordered = sorted(trades, key=lambda item: (item.entry_date, item.symbol))
    proof = [trade for trade in ordered if trade.exact_bid_ask]
    oos = [trade for trade in proof if _parse_date(trade.entry_date) >= oos_start]
    walk = _walk_forward(proof)
    all_summary = _summarize_trades(ordered)
    proof_summary = _summarize_trades(proof)
    oos_summary = _summarize_trades(oos)
    walk_good = bool(walk) and all(
        item["trade_count"] < 5 or (item["avg_pnl_pct"] > 0 and item["profit_factor"] >= 1.0)
        for item in walk
    )
    gates = {
        "min_50_exact_trades": len(proof) >= min_total_trades,
        "min_oos_exact_trades": len(oos) >= min_oos_trades,
        "multi_month_distribution": proof_summary["month_count"] >= 4 and proof_summary["expiration_cycle_count"] >= 4,
        "profit_factor_min": proof_summary["profit_factor"] >= min_profit_factor,
        "profit_factor_preferred": proof_summary["profit_factor"] >= preferred_profit_factor,
        "positive_expectancy_after_slippage_fees": proof_summary["avg_pnl_pct"] > 0,
        "oos_positive": oos_summary["trade_count"] >= min_oos_trades and oos_summary["avg_pnl_pct"] > 0 and oos_summary["profit_factor"] >= 1.0,
        "walk_forward_holds": walk_good,
        "bid_ask_proof_only": len(ordered) == len(proof),
    }
    viable = all(
        gates[key]
        for key in (
            "min_50_exact_trades",
            "min_oos_exact_trades",
            "multi_month_distribution",
            "profit_factor_min",
            "positive_expectancy_after_slippage_fees",
            "oos_positive",
            "walk_forward_holds",
        )
    )
    return {
        "lane": lane,
        "status": "viable_for_paper_promotion" if viable else "research_only",
        "promotion_allowed": viable,
        "strategy": {
            "bullish": "call debit spreads",
            "bearish": "put debit spreads",
            "sideways": "defined-risk iron condors",
        }[lane],
        "all_trade_summary": all_summary,
        "exact_bid_ask_proof_summary": proof_summary,
        "out_of_sample_start": oos_start.isoformat(),
        "out_of_sample_exact_summary": oos_summary,
        "walk_forward_windows": walk,
        "gates": gates,
        "rejected_candidate_reasons": (
            dict(rejected.most_common()) if hasattr(rejected, "most_common") else dict(rejected)
        ),
        "trades": [asdict(trade) for trade in ordered],
        "sample_trades": [asdict(trade) for trade in ordered[:5]],
    }


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Alpaca Options Strategy Evidence Lab",
        "",
        f"- Run at: `{report['run_at_utc']}`",
        f"- Requested window: `{report['date_from']}` through `{report['date_to']}`",
        f"- Symbols: `{', '.join(report['symbols'])}`",
        f"- Option evidence: exact bid/ask store first; Alpaca OPRA historical bars are research fallback where exact BBO is missing.",
        "",
        "## Lane Results",
        "",
    ]
    for lane in report["lanes"]:
        proof = lane["exact_bid_ask_proof_summary"]
        oos = lane["out_of_sample_exact_summary"]
        lines.extend(
            [
                f"### {lane['lane'].title()} - {lane['status']}",
                "",
                f"- Variant: `{lane.get('variant')}`; parameters: `{lane.get('lane_parameters')}`",
                f"- Exact trades: `{proof['trade_count']}`; OOS exact trades: `{oos['trade_count']}`",
                f"- PF: `{proof['profit_factor']}`; avg P&L: `{proof['avg_pnl_pct']}%`; win rate: `{proof['win_rate_pct']}%`",
                f"- OOS PF: `{oos['profit_factor']}`; OOS avg P&L: `{oos['avg_pnl_pct']}%`",
                f"- Months: `{proof['month_count']}`; expiration cycles: `{proof['expiration_cycle_count']}`",
                f"- Max drawdown: `{proof['max_drawdown_pct_points']} pct-points`",
                f"- Top rejects: `{dict(list(lane['rejected_candidate_reasons'].items())[:5])}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Promotion Rule",
            "",
            "Only exact bid/ask trades count toward promotion. Alpaca historical option bars preserve exact contract identity and OPRA OHLCV, but they do not provide historical bid/ask BBO, so those trades remain research-only unless exact quotes are available from the local store.",
            "",
        ]
    )
    return "\n".join(lines)


def _lane_arg(args: argparse.Namespace, lane: str, key: str, default: Any) -> Any:
    preset = LANE_PRESETS.get(str(args.preset or "baseline"), {})
    lane_config = preset.get(lane, {})
    if key in lane_config:
        return lane_config[key]
    return getattr(args, key, default)


def run_lab(args: argparse.Namespace) -> dict[str, Any]:
    _load_dotenv_local()
    date_from = _parse_date(args.date_from)
    date_to = _parse_date(args.date_to or datetime.now(UTC).date())
    oos_start = _parse_date(args.oos_start)
    symbols = _normal_symbols(args.scope, args.symbols)
    client = AlpacaMarketDataClient()
    store = HistoricalOptionsStore(args.db_path)
    provider = OptionEvidenceProvider(
        client=client,
        store=store,
        cache_dir=Path(args.cache_dir),
        allow_alpaca_bars=bool(args.allow_alpaca_bars),
    )
    histories: dict[str, pd.DataFrame] = {}
    stock_errors: dict[str, str] = {}
    for symbol in symbols:
        try:
            frame = _stock_frame(client, symbol, date_from, date_to)
        except Exception as exc:
            stock_errors[symbol] = exc.__class__.__name__
            frame = pd.DataFrame()
        if not frame.empty:
            histories[symbol] = frame

    lane_reports: list[dict[str, Any]] = []
    for lane in ("bullish", "bearish", "sideways"):
        lane_variant = str(_lane_arg(args, lane, "variant", "baseline"))
        lane_hold_days = int(_lane_arg(args, lane, "hold_days", args.hold_days))
        lane_width_pct = float(_lane_arg(args, lane, "width_pct", args.width_pct))
        lane_range_pct = float(_lane_arg(args, lane, "condor_range_pct", args.condor_range_pct))
        lane_wing_pct = float(_lane_arg(args, lane, "condor_wing_pct", args.condor_wing_pct))
        lane_max_per_week = int(_lane_arg(args, lane, "max_per_week", args.max_per_week))
        candidates, rejected = _build_candidates(
            histories,
            lane=lane,
            variant=lane_variant,
            start=date_from,
            end=date_to,
            max_per_week=lane_max_per_week,
        )
        trades: list[SimulatedTrade] = []
        for candidate in candidates:
            if int(args.max_candidates_per_lane) > 0 and len(trades) >= int(args.max_candidates_per_lane):
                break
            try:
                trade, reject_reason = _simulate_candidate(
                    candidate,
                    provider=provider,
                    histories=histories,
                    target_dte=int(args.target_dte),
                    min_dte=int(args.min_dte),
                    max_dte=int(args.max_dte),
                    hold_days=lane_hold_days,
                    width_pct=lane_width_pct,
                    condor_range_pct=lane_range_pct,
                    condor_wing_pct=lane_wing_pct,
                    fee_per_contract=float(args.fee_per_contract),
                    bar_slippage_pct=float(args.bar_slippage_pct),
                )
            except (AlpacaMarketDataError, OSError, ValueError) as exc:
                trade = None
                reject_reason = exc.__class__.__name__
            if trade is None:
                rejected[str(reject_reason or "unpriced")] += 1
            else:
                trades.append(trade)
        lane_reports.append(
            _lane_report(
                lane,
                trades,
                rejected=rejected,
                oos_start=oos_start,
                min_total_trades=int(args.min_total_trades),
                min_oos_trades=int(args.min_oos_trades),
                min_profit_factor=float(args.min_profit_factor),
                preferred_profit_factor=float(args.preferred_profit_factor),
            )
        )
        lane_reports[-1]["variant"] = lane_variant
        lane_reports[-1]["lane_parameters"] = {
            "hold_days": lane_hold_days,
            "width_pct": lane_width_pct,
            "condor_range_pct": lane_range_pct,
            "condor_wing_pct": lane_wing_pct,
            "max_per_week": lane_max_per_week,
        }

    report = {
        "run_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "oos_start": oos_start.isoformat(),
        "scope": args.scope,
        "preset": args.preset,
        "symbols": symbols,
        "histories_loaded": sorted(histories),
        "stock_history_errors": stock_errors,
        "data_policy": {
            "stock_source": "alpaca_sip",
            "option_primary": "local exact bid/ask historical store when present",
            "option_research_fallback": "alpaca_opra_historical_bars_no_bidask" if args.allow_alpaca_bars else None,
            "promotion_trade_basis": "exact_bid_ask only",
        },
        "parameters": {
            "preset": args.preset,
            "target_dte": int(args.target_dte),
            "min_dte": int(args.min_dte),
            "max_dte": int(args.max_dte),
            "hold_days": int(args.hold_days),
            "max_per_week": int(args.max_per_week),
            "fee_per_contract": float(args.fee_per_contract),
            "bar_slippage_pct": float(args.bar_slippage_pct),
            "min_total_trades": int(args.min_total_trades),
            "min_oos_trades": int(args.min_oos_trades),
            "min_profit_factor": float(args.min_profit_factor),
            "preferred_profit_factor": float(args.preferred_profit_factor),
        },
        "lanes": lane_reports,
    }
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = report["run_at_utc"].replace(":", "").replace("-", "").replace("Z", "Z")
    json_path = output_dir / f"alpaca_options_strategy_lab_{stamp}.json"
    md_path = output_dir / f"alpaca_options_strategy_lab_{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    report["artifact_paths"] = {
        "json": str(json_path),
        "markdown": str(md_path),
        "latest_json": str(latest_json),
        "latest_markdown": str(latest_md),
    }
    json_path.write_text(json.dumps(report, indent=2), encoding="utf8")
    md_path.write_text(_render_markdown(report), encoding="utf8")
    latest_json.write_text(json.dumps(report, indent=2), encoding="utf8")
    latest_md.write_text(_render_markdown(report), encoding="utf8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Alpaca SIP/OPRA evidence lab for bullish, bearish, and sideways options lanes.")
    parser.add_argument("--preset", default="baseline", choices=sorted(LANE_PRESETS))
    parser.add_argument("--scope", default="normal", choices=["normal", "commodity", "both"])
    parser.add_argument("--symbols", help="Comma-separated symbol override.")
    parser.add_argument("--date-from", default=DEFAULT_DATE_FROM)
    parser.add_argument("--date-to", default=datetime.now(UTC).date().isoformat())
    parser.add_argument("--oos-start", default="2025-07-01")
    parser.add_argument("--target-dte", type=int, default=DEFAULT_TARGET_DTE)
    parser.add_argument("--min-dte", type=int, default=DEFAULT_MIN_DTE)
    parser.add_argument("--max-dte", type=int, default=DEFAULT_MAX_DTE)
    parser.add_argument("--hold-days", type=int, default=DEFAULT_HOLD_TRADING_DAYS)
    parser.add_argument("--width-pct", type=float, default=DEFAULT_WIDTH_PCT)
    parser.add_argument("--condor-range-pct", type=float, default=DEFAULT_CONDOR_RANGE_PCT)
    parser.add_argument("--condor-wing-pct", type=float, default=DEFAULT_CONDOR_WING_PCT)
    parser.add_argument("--max-per-week", type=int, default=3)
    parser.add_argument("--max-candidates-per-lane", type=int, default=0, help="0 means no cap.")
    parser.add_argument("--min-total-trades", type=int, default=DEFAULT_MIN_TOTAL_TRADES)
    parser.add_argument("--min-oos-trades", type=int, default=DEFAULT_MIN_OOS_TRADES)
    parser.add_argument("--min-profit-factor", type=float, default=DEFAULT_MIN_PROFIT_FACTOR)
    parser.add_argument("--preferred-profit-factor", type=float, default=DEFAULT_PREFERRED_PROFIT_FACTOR)
    parser.add_argument("--fee-per-contract", type=float, default=DEFAULT_FEE_PER_CONTRACT_USD)
    parser.add_argument("--bar-slippage-pct", type=float, default=DEFAULT_BAR_SLIPPAGE_PCT)
    parser.add_argument("--allow-alpaca-bars", action="store_true")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = run_lab(args)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        compact = {
            "artifact_paths": report["artifact_paths"],
            "lanes": [
                {
                    "lane": lane["lane"],
                    "variant": lane.get("variant"),
                    "status": lane["status"],
                    "exact_trades": lane["exact_bid_ask_proof_summary"]["trade_count"],
                    "oos_exact_trades": lane["out_of_sample_exact_summary"]["trade_count"],
                    "profit_factor": lane["exact_bid_ask_proof_summary"]["profit_factor"],
                    "avg_pnl_pct": lane["exact_bid_ask_proof_summary"]["avg_pnl_pct"],
                    "promotion_allowed": lane["promotion_allowed"],
                }
                for lane in report["lanes"]
            ],
        }
        print(json.dumps(compact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
