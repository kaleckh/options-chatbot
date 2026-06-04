from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from historical_options_store import (  # noqa: E402
    DEFAULT_HISTORICAL_OPTIONS_DB_PATH,
    INTRADAY_SNAPSHOT_KIND,
    SQLITE_BUSY_TIMEOUT_MS,
    SQLITE_TIMEOUT_SECONDS,
    TRUSTED_DATA_TRUST,
)
from local_env import load_local_env  # noqa: E402
from scripts.import_thetadata_options_nbbo import _extract_rows  # noqa: E402
from us_equity_market_calendar import is_us_equity_market_day  # noqa: E402

load_local_env(ROOT)

EASTERN_TZ = ZoneInfo("America/New_York")
DEFAULT_THETA_URL = "http://127.0.0.1:25503"
DEFAULT_SOURCE_LABEL = "thetadata_opra_nbbo_1m"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "side-aware-zero-bid"
DEFAULT_RUN_PATH = (
    ROOT
    / "data"
    / "options-validation"
    / "runs"
    / "20260530_191945_lane_a_chain_native_ret20_4_stop200_time75_rerun4_v1_intraday.json"
)

OCC_RE = re.compile(r"^(?P<root>[A-Z.]+)(?P<expiry>\d{6})(?P<right>[CP])(?P<strike>\d{8})$")
ENTRY_START_MINUTE_ET = 10 * 60 + 10
ENTRY_END_MINUTE_ET = 10 * 60 + 25
EXIT_MINUTE_ET = 15 * 60 + 55
COMMISSION_PER_CONTRACT_USD = 0.65


@dataclass(frozen=True)
class ContractParts:
    contract_symbol: str
    root: str
    expiry: date
    option_type: str
    strike: float


@dataclass(frozen=True)
class RawQuote:
    contract_symbol: str
    quote_date_et: str
    quote_minute_et: int
    bid: float
    ask: float
    source: str
    as_of_utc: str | None = None
    underlying_price: float | None = None


def parse_occ(symbol: str) -> ContractParts:
    text = str(symbol or "").strip().upper()
    match = OCC_RE.match(text)
    if not match:
        raise ValueError(f"Unsupported OCC symbol {symbol!r}")
    expiry_raw = match.group("expiry")
    expiry = date(2000 + int(expiry_raw[:2]), int(expiry_raw[2:4]), int(expiry_raw[4:6]))
    option_type = "call" if match.group("right") == "C" else "put"
    return ContractParts(
        contract_symbol=text,
        root=match.group("root"),
        expiry=expiry,
        option_type=option_type,
        strike=int(match.group("strike")) / 1000.0,
    )


def _safe_float(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _minute_from_timestamp(value: Any, trade_date: date) -> tuple[str, int]:
    raw = str(value or "").strip()
    if raw:
        normalized = raw.replace("Z", "+00:00")
        if "T" not in normalized and ":" in normalized:
            normalized = f"{trade_date.isoformat()}T{normalized}"
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=EASTERN_TZ)
    else:
        parsed = datetime.combine(trade_date, time(15, 55), tzinfo=EASTERN_TZ)
    as_et = parsed.astimezone(EASTERN_TZ)
    minute = as_et.hour * 60 + as_et.minute
    as_utc = as_et.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    return as_utc, minute


def _theta_quote_from_row(row: dict[str, Any], *, parts: ContractParts, trade_date: date) -> RawQuote | None:
    bid = _safe_float(row.get("bid"))
    ask = _safe_float(row.get("ask"))
    if bid is None or ask is None or bid < 0 or ask <= 0 or ask < bid:
        return None
    expiration_raw = row.get("expiration") or row.get("exp") or parts.expiry.isoformat()
    right_raw = str(row.get("right") or row.get("option_type") or parts.option_type).strip().lower()
    strike = _safe_float(row.get("strike"))
    expiration = date.fromisoformat(str(expiration_raw)[:10])
    option_type = "call" if right_raw in {"call", "c"} else "put"
    if expiration != parts.expiry or option_type != parts.option_type:
        return None
    if strike is not None and abs(float(strike) - parts.strike) > 0.0001:
        return None
    as_of_utc, minute = _minute_from_timestamp(row.get("timestamp") or row.get("datetime"), trade_date)
    return RawQuote(
        contract_symbol=parts.contract_symbol,
        quote_date_et=trade_date.isoformat(),
        quote_minute_et=minute,
        bid=round(float(bid), 4),
        ask=round(float(ask), 4),
        source="thetadata_raw",
        as_of_utc=as_of_utc,
        underlying_price=_safe_float(row.get("underlying_price")),
    )


def _sqlite_connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=SQLITE_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    return conn


class QuoteProvider:
    def __init__(
        self,
        *,
        db_path: Path,
        theta_url: str,
        source_labels: list[str],
        timeout: float,
    ) -> None:
        self.db_path = db_path
        self.theta_url = theta_url.rstrip("/")
        self.source_labels = source_labels
        self.timeout = float(timeout)
        self.session = requests.Session()
        self.cache: dict[tuple[str, str, int, int, bool], RawQuote | None] = {}
        self.request_count = 0
        self.db_hit_count = 0
        self.theta_hit_count = 0
        self.theta_error_count = 0
        self.errors: list[str] = []

    def close(self) -> None:
        self.session.close()

    def quote(
        self,
        *,
        contract_symbol: str,
        quote_date: date,
        start_minute: int,
        end_minute: int,
        prefer_latest: bool,
    ) -> RawQuote | None:
        normalized_contract = str(contract_symbol or "").strip().upper()
        key = (normalized_contract, quote_date.isoformat(), int(start_minute), int(end_minute), bool(prefer_latest))
        if key in self.cache:
            return self.cache[key]
        db_quote = self._db_quote(
            contract_symbol=normalized_contract,
            quote_date=quote_date,
            start_minute=start_minute,
            end_minute=end_minute,
            prefer_latest=prefer_latest,
        )
        if db_quote is not None:
            self.db_hit_count += 1
            self.cache[key] = db_quote
            return db_quote
        theta_quote = self._theta_quote(
            contract_symbol=normalized_contract,
            quote_date=quote_date,
            start_minute=start_minute,
            end_minute=end_minute,
            prefer_latest=prefer_latest,
        )
        self.cache[key] = theta_quote
        return theta_quote

    def _db_quote(
        self,
        *,
        contract_symbol: str,
        quote_date: date,
        start_minute: int,
        end_minute: int,
        prefer_latest: bool,
    ) -> RawQuote | None:
        clauses = [
            "q.contract_symbol = ?",
            "q.quote_date_et = ?",
            "q.snapshot_kind = ?",
            "q.quote_minute_et >= ?",
            "q.quote_minute_et <= ?",
            "q.bid IS NOT NULL",
            "q.ask IS NOT NULL",
            "q.bid >= 0",
            "q.ask > 0",
            "q.ask >= q.bid",
            "b.data_trust = ?",
        ]
        params: list[Any] = [
            contract_symbol,
            quote_date.isoformat(),
            INTRADAY_SNAPSHOT_KIND,
            int(start_minute),
            int(end_minute),
            TRUSTED_DATA_TRUST,
        ]
        if self.source_labels:
            placeholders = ", ".join("?" for _ in self.source_labels)
            clauses.append(f"b.source_label IN ({placeholders})")
            params.extend(self.source_labels)
        order = "DESC" if prefer_latest else "ASC"
        with closing(_sqlite_connect(self.db_path)) as conn:
            row = conn.execute(
                f"""
                SELECT q.*
                FROM option_quote_snapshots q
                JOIN import_batches b ON b.id = q.source_batch_id
                WHERE {' AND '.join(clauses)}
                ORDER BY q.quote_minute_et {order}, q.as_of_utc {order}
                LIMIT 1
                """,
                tuple(params),
            ).fetchone()
        if row is None:
            return None
        bid = _safe_float(row["bid"])
        ask = _safe_float(row["ask"])
        if bid is None or ask is None:
            return None
        return RawQuote(
            contract_symbol=contract_symbol,
            quote_date_et=str(row["quote_date_et"]),
            quote_minute_et=int(row["quote_minute_et"]),
            bid=round(float(bid), 4),
            ask=round(float(ask), 4),
            source="trusted_db",
            as_of_utc=str(row["as_of_utc"]),
            underlying_price=_safe_float(row["underlying_price"]),
        )

    def _theta_quote(
        self,
        *,
        contract_symbol: str,
        quote_date: date,
        start_minute: int,
        end_minute: int,
        prefer_latest: bool,
    ) -> RawQuote | None:
        parts = parse_occ(contract_symbol)
        start_time = f"{start_minute // 60:02d}:{start_minute % 60:02d}:00"
        end_time = f"{end_minute // 60:02d}:{end_minute % 60:02d}:00"
        params = {
            "symbol": parts.root,
            "expiration": parts.expiry.strftime("%Y%m%d"),
            "date": quote_date.strftime("%Y%m%d"),
            "interval": "1m",
            "format": "json",
            "start_time": start_time,
            "end_time": end_time,
            "right": "C" if parts.option_type == "call" else "P",
            "strike": parts.strike,
        }
        try:
            response = self.session.get(
                f"{self.theta_url}/v3/option/history/quote",
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            self.request_count += 1
        except Exception as exc:
            self.theta_error_count += 1
            if len(self.errors) < 50:
                self.errors.append(f"{contract_symbol} {quote_date}: {exc}")
            return None
        quotes = [
            quote
            for raw in _extract_rows(response.json())
            if (quote := _theta_quote_from_row(raw, parts=parts, trade_date=quote_date)) is not None
        ]
        if not quotes:
            return None
        quotes.sort(key=lambda item: (item.quote_minute_et, item.as_of_utc or ""))
        self.theta_hit_count += 1
        return quotes[-1] if prefer_latest else quotes[0]


def _market_days(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        if is_us_equity_market_day(current):
            yield current
        current = date.fromordinal(current.toordinal() + 1)


def _entry_leg_price(quote: RawQuote, *, leg: str, mode: str) -> float | None:
    if mode == "midpoint_zero_bid":
        if quote.bid >= 0 and quote.ask > 0 and quote.ask >= quote.bid:
            return round((quote.bid + quote.ask) / 2.0, 4)
        return None
    if mode == "conservative":
        if leg == "long":
            return quote.ask if quote.ask > 0 else None
        if leg == "short":
            return quote.bid if quote.bid > 0 else None
    raise ValueError(f"Unsupported mode {mode!r}")


def _exit_leg_price(quote: RawQuote, *, leg: str, mode: str) -> float | None:
    if mode == "midpoint_zero_bid":
        if quote.bid >= 0 and quote.ask > 0 and quote.ask >= quote.bid:
            return round((quote.bid + quote.ask) / 2.0, 4)
        return None
    if mode == "conservative":
        if leg == "long":
            return quote.bid if quote.bid >= 0 else None
        if leg == "short":
            return quote.ask if quote.ask > 0 else None
    raise ValueError(f"Unsupported mode {mode!r}")


def _stable_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf8")
    return hashlib.sha256(encoded).hexdigest()


def _quote_evidence(quote: RawQuote, *, role: str, side: str, mode: str, purpose: str) -> dict[str, Any]:
    payload = {
        "purpose": purpose,
        "role": role,
        "side": side,
        "mode": mode,
        "contract_symbol": quote.contract_symbol,
        "quote_date_et": quote.quote_date_et,
        "quote_minute_et": int(quote.quote_minute_et),
        "bid": round(float(quote.bid), 4),
        "ask": round(float(quote.ask), 4),
        "source": quote.source,
        "as_of_utc": quote.as_of_utc,
        "underlying_price": quote.underlying_price,
    }
    payload["quote_row_sha256"] = _stable_hash(payload)
    return payload


def _pnl_metrics(pnls: list[float]) -> dict[str, Any]:
    wins = [item for item in pnls if item > 0]
    losses = [item for item in pnls if item < 0]
    gross_win = round(sum(wins), 2)
    gross_loss = round(abs(sum(losses)), 2)
    return {
        "trade_count": len(pnls),
        "win_trade_count": len(wins),
        "loss_trade_count": len(losses),
        "win_rate_pct": round(len(wins) / len(pnls) * 100.0, 1) if pnls else 0.0,
        "avg_pnl_pct": round(sum(pnls) / len(pnls), 2) if pnls else 0.0,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else (gross_win if gross_win > 0 else 0.0),
        "gross_win": gross_win,
        "gross_loss": gross_loss,
    }


def replay_trade(
    trade: dict[str, Any],
    *,
    quote_provider: QuoteProvider,
    mode: str,
    stop_loss_pct: float,
    profit_target_pct: float,
    time_exit_pct: float,
    trailing_profit_pct: float,
    trailing_giveback_pct: float,
) -> dict[str, Any]:
    entry_date = date.fromisoformat(str(trade.get("date"))[:10])
    long_contract = str(trade.get("long_contract_symbol") or trade.get("missing_long_contract_symbol") or "").strip().upper()
    short_contract = str(trade.get("short_contract_symbol") or trade.get("missing_short_contract_symbol") or "").strip().upper()
    base_result = {
        "ticker": trade.get("ticker"),
        "date": entry_date.isoformat(),
        "long_contract_symbol": long_contract,
        "short_contract_symbol": short_contract,
        "original_missing_quote_date": trade.get("missing_quote_date"),
    }
    if not long_contract or not short_contract:
        return {**base_result, "priced": False, "unpriced_reason": "missing_contract_symbol"}
    long_parts = parse_occ(long_contract)
    short_parts = parse_occ(short_contract)
    if long_parts.expiry != short_parts.expiry:
        return {**base_result, "priced": False, "unpriced_reason": "mismatched_expiry"}
    expiry = long_parts.expiry
    long_entry_quote = quote_provider.quote(
        contract_symbol=long_contract,
        quote_date=entry_date,
        start_minute=ENTRY_START_MINUTE_ET,
        end_minute=ENTRY_END_MINUTE_ET,
        prefer_latest=False,
    )
    short_entry_quote = quote_provider.quote(
        contract_symbol=short_contract,
        quote_date=entry_date,
        start_minute=ENTRY_START_MINUTE_ET,
        end_minute=ENTRY_END_MINUTE_ET,
        prefer_latest=False,
    )
    if long_entry_quote is None or short_entry_quote is None:
        return {
            **base_result,
            "priced": False,
            "unpriced_reason": "missing_entry_quote_for_leg",
            "missing_long_contract_symbol": long_contract if long_entry_quote is None else None,
            "missing_short_contract_symbol": short_contract if short_entry_quote is None else None,
        }
    long_entry = _entry_leg_price(long_entry_quote, leg="long", mode=mode)
    short_entry = _entry_leg_price(short_entry_quote, leg="short", mode=mode)
    if long_entry is None or short_entry is None:
        return {**base_result, "priced": False, "unpriced_reason": "non_executable_entry_quote"}
    net_debit = round(long_entry - short_entry, 4)
    if net_debit <= 0.01:
        return {**base_result, "priced": False, "unpriced_reason": "zero_or_negative_net_debit"}
    entry_quote_evidence = [
        _quote_evidence(long_entry_quote, role="long", side="buy_ask" if mode == "conservative" else "midpoint", mode=mode, purpose="entry"),
        _quote_evidence(short_entry_quote, role="short", side="sell_bid" if mode == "conservative" else "midpoint", mode=mode, purpose="entry"),
    ]
    entry_evidence_sha256 = _stable_hash({"entry_quote_evidence": entry_quote_evidence, "entry_px": net_debit})

    spread_width = abs(long_parts.strike - short_parts.strike)
    actual_dte = max((expiry - entry_date).days, 1)
    time_exit_day = max(1, math.ceil(actual_dte * float(time_exit_pct) / 100.0))
    target_value = min(net_debit * (1.0 + float(profit_target_pct) / 100.0), spread_width)
    stop_value = net_debit * (1.0 - float(stop_loss_pct) / 100.0)
    high_watermark = net_debit
    trail_active = False
    trail_stop_value = 0.0

    exit_value: float | None = None
    exit_reason = "unpriced"
    exit_quote_date: date | None = None
    exit_day = 0
    zero_bid_exit_days = 0
    first_zero_bid_quote_date: str | None = None
    missing_after_zero_bid_count = 0
    last_spread_value: float | None = None
    last_quote_date: date | None = None
    last_exit_quote_evidence: list[dict[str, Any]] | None = None
    exit_quote_evidence: list[dict[str, Any]] | None = None

    for exit_day, quote_date in enumerate(_market_days(date.fromordinal(entry_date.toordinal() + 1), expiry), start=1):
        long_quote = quote_provider.quote(
            contract_symbol=long_contract,
            quote_date=quote_date,
            start_minute=EXIT_MINUTE_ET,
            end_minute=EXIT_MINUTE_ET,
            prefer_latest=True,
        )
        short_quote = quote_provider.quote(
            contract_symbol=short_contract,
            quote_date=quote_date,
            start_minute=EXIT_MINUTE_ET,
            end_minute=EXIT_MINUTE_ET,
            prefer_latest=True,
        )
        if long_quote is None or short_quote is None:
            missing_after_zero_bid_count += int(bool(first_zero_bid_quote_date))
            return {
                **base_result,
                "priced": False,
                "unpriced_reason": "missing_exit_quote_for_leg",
                "missing_quote_date": quote_date.isoformat(),
                "missing_long_contract_symbol": long_contract if long_quote is None else None,
                "missing_short_contract_symbol": short_contract if short_quote is None else None,
                "first_zero_bid_quote_date": first_zero_bid_quote_date,
                "missing_after_zero_bid_count": missing_after_zero_bid_count,
            }
        if long_quote.bid == 0 or short_quote.bid == 0:
            zero_bid_exit_days += 1
            first_zero_bid_quote_date = first_zero_bid_quote_date or quote_date.isoformat()
        long_exit = _exit_leg_price(long_quote, leg="long", mode=mode)
        short_exit = _exit_leg_price(short_quote, leg="short", mode=mode)
        if long_exit is None or short_exit is None:
            return {**base_result, "priced": False, "unpriced_reason": "non_executable_exit_quote", "missing_quote_date": quote_date.isoformat()}
        current_exit_quote_evidence = [
            _quote_evidence(long_quote, role="long", side="sell_bid" if mode == "conservative" else "midpoint", mode=mode, purpose="exit"),
            _quote_evidence(short_quote, role="short", side="buy_ask" if mode == "conservative" else "midpoint", mode=mode, purpose="exit"),
        ]
        spread_value = max(0.0, round(long_exit - short_exit, 4))
        last_spread_value = spread_value
        last_quote_date = quote_date
        last_exit_quote_evidence = current_exit_quote_evidence
        if spread_value > high_watermark:
            high_watermark = spread_value
        peak_pnl_pct = ((high_watermark / net_debit) - 1.0) * 100.0 if net_debit > 0 else 0.0
        if not trail_active and peak_pnl_pct >= float(trailing_profit_pct):
            trail_active = True
        if trail_active and peak_pnl_pct > 0.0:
            retained = peak_pnl_pct * max(0.0, 1.0 - float(trailing_giveback_pct) / 100.0)
            trail_stop_value = net_debit * (1.0 + retained / 100.0)
        effective_stop = max(stop_value, trail_stop_value) if trail_active else stop_value

        if spread_value <= effective_stop:
            exit_value = spread_value
            exit_reason = "trailing_stop" if trail_active else "stop"
            exit_quote_date = quote_date
            exit_quote_evidence = current_exit_quote_evidence
            break
        if spread_value >= target_value:
            exit_value = min(spread_value, target_value)
            exit_reason = "target"
            exit_quote_date = quote_date
            exit_quote_evidence = current_exit_quote_evidence
            break
        if exit_day >= time_exit_day:
            exit_value = spread_value
            exit_reason = "time_exit"
            exit_quote_date = quote_date
            exit_quote_evidence = current_exit_quote_evidence
            break

    if exit_value is None or exit_quote_date is None:
        if last_spread_value is not None and last_quote_date is not None:
            exit_value = last_spread_value
            exit_quote_date = last_quote_date
            exit_reason = "expiry_quote_fallback"
            exit_quote_evidence = last_exit_quote_evidence
        else:
            return {
                **base_result,
                "priced": False,
                "unpriced_reason": "insufficient_quote_history",
                "first_zero_bid_quote_date": first_zero_bid_quote_date,
                "zero_bid_exit_days": zero_bid_exit_days,
            }

    if exit_value is None or exit_quote_date is None:
        return {
            **base_result,
            "priced": False,
            "unpriced_reason": "insufficient_quote_history",
            "first_zero_bid_quote_date": first_zero_bid_quote_date,
            "zero_bid_exit_days": zero_bid_exit_days,
        }

    gross_pnl_per_share = exit_value - net_debit
    gross_pnl_usd = gross_pnl_per_share * 100.0
    fee_total = 4.0 * COMMISSION_PER_CONTRACT_USD
    net_pnl_usd = gross_pnl_usd - fee_total
    capital_at_risk = net_debit * 100.0
    gross_pnl_pct = gross_pnl_per_share / net_debit * 100.0
    net_pnl_pct = net_pnl_usd / capital_at_risk * 100.0
    trade_evidence = {
        "mode": mode,
        "entry_quote_evidence": entry_quote_evidence,
        "exit_quote_evidence": exit_quote_evidence or [],
        "entry_px": round(net_debit, 4),
        "exit_px": round(exit_value, 4),
        "exit_date": exit_quote_date.isoformat(),
        "exit_reason": exit_reason,
    }
    return {
        **base_result,
        "priced": True,
        "exit_date": exit_quote_date.isoformat(),
        "exit_reason": exit_reason,
        "mode": mode,
        "entry_px": round(net_debit, 4),
        "exit_px": round(exit_value, 4),
        "gross_pnl_pct": round(gross_pnl_pct, 2),
        "net_pnl_pct": round(net_pnl_pct, 2),
        "pnl_pct": round(net_pnl_pct, 2),
        "gross_pnl_usd": round(gross_pnl_usd, 2),
        "net_pnl_usd": round(net_pnl_usd, 2),
        "fee_total_usd": round(fee_total, 2),
        "spread_width": round(spread_width, 4),
        "time_exit_day": time_exit_day,
        "exit_day": exit_day,
        "zero_bid_exit_days": zero_bid_exit_days,
        "first_zero_bid_quote_date": first_zero_bid_quote_date,
        "used_zero_bid_exit_quote": zero_bid_exit_days > 0,
        "entry_quote_evidence": entry_quote_evidence,
        "exit_quote_evidence": exit_quote_evidence or [],
        "entry_evidence_sha256": entry_evidence_sha256,
        "trade_evidence_sha256": _stable_hash(trade_evidence),
    }


def run_replay(
    run_path: Path,
    *,
    db_path: Path,
    theta_url: str,
    source_labels: list[str],
    timeout: float,
    modes: list[str],
    stop_loss_pct: float = 200.0,
    profit_target_pct: float = 150.0,
    time_exit_pct: float = 75.0,
    trailing_profit_pct: float = 40.0,
    trailing_giveback_pct: float = 50.0,
) -> dict[str, Any]:
    run = json.loads(run_path.read_text(encoding="utf8"))
    candidates = [
        trade
        for trade in run.get("unpriced_trades") or []
        if str(trade.get("unpriced_reason") or "") == "missing_exit_quote_for_leg"
    ]
    existing_pnls = [
        float(trade.get("net_pnl_pct", trade.get("pnl_pct")))
        for trade in run.get("trades") or []
        if trade.get("priced") and _safe_float(trade.get("net_pnl_pct", trade.get("pnl_pct"))) is not None
    ]
    provider = QuoteProvider(
        db_path=db_path,
        theta_url=theta_url,
        source_labels=source_labels,
        timeout=timeout,
    )
    try:
        by_mode: dict[str, Any] = {}
        for mode in modes:
            rows = [
                replay_trade(
                    trade,
                    quote_provider=provider,
                    mode=mode,
                    stop_loss_pct=stop_loss_pct,
                    profit_target_pct=profit_target_pct,
                    time_exit_pct=time_exit_pct,
                    trailing_profit_pct=trailing_profit_pct,
                    trailing_giveback_pct=trailing_giveback_pct,
                )
                for trade in candidates
            ]
            priced = [row for row in rows if row.get("priced")]
            unpriced = [row for row in rows if not row.get("priced")]
            side_pnls = [float(row["net_pnl_pct"]) for row in priced]
            combined_pnls = existing_pnls + side_pnls
            combined_metrics = _pnl_metrics(combined_pnls)
            combined_candidate_count = int(run.get("candidate_trade_count") or 0)
            combined_unpriced_count = max(combined_candidate_count - len(combined_pnls), 0)
            combined_quote_coverage_pct = round(
                len(combined_pnls) / float(combined_candidate_count or 1) * 100.0,
                1,
            )
            by_mode[mode] = {
                "mode": mode,
                "candidate_count": len(candidates),
                "priced_count": len(priced),
                "unpriced_count": len(unpriced),
                "side_aware_metrics": _pnl_metrics(side_pnls),
                "combined_with_existing_metrics": combined_metrics,
                "combined_priced_count": len(combined_pnls),
                "combined_candidate_count": combined_candidate_count,
                "combined_unpriced_count": combined_unpriced_count,
                "combined_quote_coverage_pct": combined_quote_coverage_pct,
                "combined_with_existing_lane_a_metrics": combined_metrics,
                "combined_lane_a_priced_count": len(combined_pnls),
                "combined_lane_a_candidate_count": combined_candidate_count,
                "combined_lane_a_unpriced_count": combined_unpriced_count,
                "combined_lane_a_quote_coverage_pct": combined_quote_coverage_pct,
                "exit_reasons": dict(Counter(str(row.get("exit_reason")) for row in priced)),
                "unpriced_reasons": dict(Counter(str(row.get("unpriced_reason")) for row in unpriced)),
                "zero_bid_priced_count": sum(1 for row in priced if row.get("used_zero_bid_exit_quote")),
                "first_zero_bid_quote_dates": dict(
                    Counter(str(row.get("first_zero_bid_quote_date")) for row in priced if row.get("first_zero_bid_quote_date"))
                ),
                "worst_priced_examples": sorted(
                    priced,
                    key=lambda row: float(row.get("net_pnl_pct") or 0.0),
                )[:10],
                "priced_rows": priced,
                "unpriced_rows": unpriced,
            }
    finally:
        provider.close()
    return {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "run_path": str(run_path),
        "db_path": str(db_path),
        "theta_url": theta_url,
        "source_labels": source_labels,
        "assumptions": {
            "entry_window_et": "10:10-10:25",
            "exit_quote_time_et": "15:55",
            "stop_loss_pct": float(stop_loss_pct),
            "profit_target_pct": float(profit_target_pct),
            "time_exit_pct": float(time_exit_pct),
            "trailing_profit_pct": float(trailing_profit_pct),
            "trailing_giveback_pct": float(trailing_giveback_pct),
            "midpoint_zero_bid": "entry and exit use midpoint while allowing bid=0, ask>0 rows",
            "conservative": "entry buys long at ask and sells short at bid; exit sells long at bid and buys short at ask",
        },
        "original_lane_a": {
            "candidate_trade_count": run.get("candidate_trade_count"),
            "priced_trade_count": run.get("priced_trade_count"),
            "unpriced_trade_count": run.get("unpriced_trade_count"),
            "quote_coverage_pct": run.get("quote_coverage_pct"),
            "profit_factor": (run.get("authoritative_profitability_metrics") or {}).get("profit_factor"),
            "avg_pnl_pct": (run.get("authoritative_profitability_metrics") or {}).get("avg_pnl_pct"),
        },
        "provider_stats": {
            "db_hit_count": provider.db_hit_count,
            "theta_request_count": provider.request_count,
            "theta_hit_count": provider.theta_hit_count,
            "theta_error_count": provider.theta_error_count,
            "errors": provider.errors,
        },
        "modes": by_mode,
    }


def write_outputs(report: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"lane_a_side_aware_zero_bid_{stamp}.json"
    latest = output_dir / "latest_lane_a_side_aware_zero_bid.json"
    payload = json.dumps(report, indent=2, sort_keys=True)
    path.write_text(payload + "\n", encoding="utf8")
    latest.write_text(payload + "\n", encoding="utf8")
    return {"json": str(path), "latest_json": str(latest)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay Lane A unpriced exits with side-aware zero-bid quote handling.")
    parser.add_argument("run_path", nargs="?", type=Path, default=DEFAULT_RUN_PATH)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_HISTORICAL_OPTIONS_DB_PATH)
    parser.add_argument("--theta-url", default=DEFAULT_THETA_URL)
    parser.add_argument("--source-labels", default=DEFAULT_SOURCE_LABEL)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--modes", default="midpoint_zero_bid,conservative")
    parser.add_argument("--stop-loss-pct", type=float, default=200.0)
    parser.add_argument("--profit-target-pct", type=float, default=150.0)
    parser.add_argument("--time-exit-pct", type=float, default=75.0)
    parser.add_argument("--trailing-profit-pct", type=float, default=40.0)
    parser.add_argument("--trailing-giveback-pct", type=float, default=50.0)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    labels = [item.strip() for item in str(args.source_labels).split(",") if item.strip()]
    modes = [item.strip() for item in str(args.modes).split(",") if item.strip()]
    report = run_replay(
        args.run_path.resolve(),
        db_path=args.db_path.resolve(),
        theta_url=str(args.theta_url),
        source_labels=labels,
        timeout=float(args.timeout),
        modes=modes,
        stop_loss_pct=float(args.stop_loss_pct),
        profit_target_pct=float(args.profit_target_pct),
        time_exit_pct=float(args.time_exit_pct),
        trailing_profit_pct=float(args.trailing_profit_pct),
        trailing_giveback_pct=float(args.trailing_giveback_pct),
    )
    if not args.no_write:
        report["artifacts"] = write_outputs(report, args.output_dir)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif not args.no_write:
        print(json.dumps(report["artifacts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
