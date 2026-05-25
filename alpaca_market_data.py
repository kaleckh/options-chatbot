from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, Callable, Iterable

import pandas as pd
import requests


ALPACA_STOCK_SOURCE = "alpaca_sip"
ALPACA_OPTIONS_SOURCE = "alpaca_opra"
YAHOO_FALLBACK_SOURCE = "yahoo_fallback_delayed"

_PERIOD_RE = re.compile(r"^(?P<count>\d+)(?P<unit>d|mo|y)$", re.IGNORECASE)
_OCC_RE = re.compile(
    r"^(?P<root>[A-Z0-9]+?)(?P<expiry>\d{6})(?P<right>[CP])(?P<strike>\d{8})$",
    re.IGNORECASE,
)


class AlpacaMarketDataError(RuntimeError):
    """Raised when an Alpaca market-data request cannot be completed."""


def _clean_url(value: str | None, default: str) -> str:
    return str(value or default).strip().rstrip("/")


def _data_v2_base() -> str:
    endpoint = _clean_url(os.getenv("ALPACA_DATA_ENDPOINT"), "https://data.alpaca.markets/v2")
    if endpoint.endswith("/v2"):
        return endpoint
    return f"{endpoint}/v2"


def _data_root() -> str:
    endpoint = _clean_url(os.getenv("ALPACA_DATA_ENDPOINT"), "https://data.alpaca.markets/v2")
    if endpoint.endswith("/v2"):
        return endpoint[: -len("/v2")]
    return endpoint


def _trading_v2_base() -> str:
    return _clean_url(
        os.getenv("ALPACA_TRADING_ENDPOINT") or os.getenv("APCA_API_BASE_URL"),
        "https://paper-api.alpaca.markets/v2",
    )


def _stock_feed() -> str:
    return str(os.getenv("ALPACA_STOCK_FEED") or "sip").strip().lower()


def _options_feed() -> str:
    return str(os.getenv("ALPACA_OPTIONS_FEED") or "opra").strip().lower()


def configured_for_alpaca() -> bool:
    return bool(os.getenv("APCA_API_KEY_ID") and os.getenv("APCA_API_SECRET_KEY"))


def alpaca_provider_requested() -> bool:
    if os.getenv("PYTEST_CURRENT_TEST") and str(os.getenv("ALPACA_ENABLE_DURING_TESTS") or "").strip().lower() not in {"1", "true", "yes", "on"}:
        return False
    if str(os.getenv("OPTIONS_IS_FIXTURE") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return False
    if str(os.getenv("OPTIONS_RUN_MODE") or "").strip().lower() in {"test", "test_harness", "fixture", "fixture_smoke"}:
        return False
    provider = str(os.getenv("OPTIONS_MARKET_DATA_PROVIDER") or "alpaca").strip().lower()
    return provider in {"alpaca", "alpaca_plus", "alpaca_algo_trader_plus"}


def alpaca_enabled() -> bool:
    return alpaca_provider_requested() and configured_for_alpaca()


def yahoo_fallback_enabled() -> bool:
    raw = str(os.getenv("ALPACA_ALLOW_YAHOO_FALLBACK") or "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def primary_provider_label() -> str:
    if alpaca_enabled():
        return f"alpaca:{_stock_feed()}:{_options_feed()}"
    return YAHOO_FALLBACK_SOURCE


def _headers() -> dict[str, str]:
    key = os.getenv("APCA_API_KEY_ID")
    secret = os.getenv("APCA_API_SECRET_KEY")
    if not key or not secret:
        raise AlpacaMarketDataError("Alpaca API credentials are not configured")
    return {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json",
    }


def _to_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def _to_int(value: Any) -> int | None:
    number = _to_float(value)
    if number is None:
        return None
    try:
        return int(number)
    except Exception:
        return None


def _first_present(mapping: dict[str, Any] | None, *keys: str) -> Any:
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def _parse_occ_symbol(symbol: str) -> dict[str, Any]:
    match = _OCC_RE.match(str(symbol or "").strip().upper())
    if not match:
        return {}
    expiry = match.group("expiry")
    return {
        "root_symbol": match.group("root").upper(),
        "expiration_date": f"20{expiry[0:2]}-{expiry[2:4]}-{expiry[4:6]}",
        "type": "call" if match.group("right").upper() == "C" else "put",
        "strike_price": int(match.group("strike")) / 1000.0,
    }


def _timestamp(value: Any) -> pd.Timestamp | None:
    if value in (None, ""):
        return None
    try:
        ts = pd.Timestamp(value)
        if pd.isna(ts):
            return None
        return ts
    except Exception:
        return None


def _normalize_history_frame(frame: pd.DataFrame, *, source: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        out = pd.DataFrame()
        out.attrs["market_data_source"] = source
        return out
    normalized = frame.copy()
    if not isinstance(normalized.index, pd.DatetimeIndex):
        normalized.index = pd.to_datetime(normalized.index)
    normalized = normalized.sort_index()
    normalized = normalized[~normalized.index.duplicated(keep="last")]
    normalized.attrs["market_data_source"] = source
    return normalized


def _period_start(period: str | None, *, interval: str) -> datetime:
    now = datetime.now(UTC)
    if not period:
        return now - timedelta(days=90)
    match = _PERIOD_RE.match(str(period).strip())
    if not match:
        return now - timedelta(days=90)
    count = int(match.group("count"))
    unit = match.group("unit").lower()
    if unit == "d":
        return now - timedelta(days=max(count, 1))
    if unit == "mo":
        return now - timedelta(days=max(count, 1) * 31)
    if unit == "y":
        return now - timedelta(days=max(count, 1) * 366)
    return now - timedelta(days=90)


def _alpaca_rfc3339(value: Any) -> str:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize(UTC)
    else:
        ts = ts.tz_convert(UTC)
    return ts.isoformat()


def _timeframe(interval: str) -> str:
    value = str(interval or "1d").strip().lower()
    mapping = {
        "1d": "1Day",
        "1day": "1Day",
        "1wk": "1Week",
        "1w": "1Week",
        "1h": "1Hour",
        "60m": "1Hour",
        "5m": "5Min",
        "5min": "5Min",
        "15m": "15Min",
        "15min": "15Min",
        "30m": "30Min",
        "30min": "30Min",
        "1m": "1Min",
        "1min": "1Min",
    }
    return mapping.get(value, value.replace("d", "Day").replace("m", "Min").replace("h", "Hour"))


def _fallback_source(frame_or_obj: Any) -> Any:
    try:
        if hasattr(frame_or_obj, "attrs"):
            frame_or_obj.attrs["market_data_source"] = YAHOO_FALLBACK_SOURCE
        else:
            setattr(frame_or_obj, "market_data_source", YAHOO_FALLBACK_SOURCE)
    except Exception:
        pass
    return frame_or_obj


@dataclass
class AlpacaMarketDataClient:
    session: requests.Session | None = None

    def __post_init__(self) -> None:
        if self.session is None:
            self.session = requests.Session()

    def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        assert self.session is not None
        response = self.session.get(url, headers=_headers(), params=params, timeout=20)
        if response.status_code >= 400:
            message = ""
            try:
                body = response.json()
                message = str(body.get("message") or body.get("error") or "")
            except Exception:
                message = response.text[:240]
            raise AlpacaMarketDataError(f"Alpaca request failed ({response.status_code}): {message}")
        try:
            payload = response.json()
        except Exception as exc:
            raise AlpacaMarketDataError("Alpaca response was not JSON") from exc
        if not isinstance(payload, dict):
            raise AlpacaMarketDataError("Alpaca response was not an object")
        return payload

    def stock_bars(
        self,
        symbol: str,
        *,
        period: str | None = None,
        start: Any = None,
        end: Any = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        symbol_up = str(symbol).strip().upper()
        if symbol_up.startswith("^"):
            raise AlpacaMarketDataError(f"Alpaca stock bars do not support index symbol {symbol_up}")

        start_ts = start if start is not None else _period_start(period, interval=interval)
        end_ts = end if end is not None else datetime.now(UTC)
        params: dict[str, Any] = {
            "symbols": symbol_up,
            "timeframe": _timeframe(interval),
            "start": _alpaca_rfc3339(start_ts),
            "end": _alpaca_rfc3339(end_ts),
            "limit": 10000,
            "feed": _stock_feed(),
            "adjustment": "raw",
        }
        rows: list[dict[str, Any]] = []
        url = f"{_data_v2_base()}/stocks/bars"
        while True:
            payload = self._get(url, params)
            symbol_bars = (payload.get("bars") or {}).get(symbol_up) or []
            rows.extend(row for row in symbol_bars if isinstance(row, dict))
            token = payload.get("next_page_token")
            if not token:
                break
            params["page_token"] = token
        if not rows:
            return _normalize_history_frame(pd.DataFrame(), source=ALPACA_STOCK_SOURCE)
        frame = pd.DataFrame.from_records(rows)
        index = pd.to_datetime(frame.get("t"), utc=True, errors="coerce")
        out = pd.DataFrame(
            {
                "Open": pd.to_numeric(frame.get("o"), errors="coerce").to_numpy(),
                "High": pd.to_numeric(frame.get("h"), errors="coerce").to_numpy(),
                "Low": pd.to_numeric(frame.get("l"), errors="coerce").to_numpy(),
                "Close": pd.to_numeric(frame.get("c"), errors="coerce").to_numpy(),
                "Volume": pd.to_numeric(frame.get("v"), errors="coerce").to_numpy(),
            },
            index=index,
        ).dropna(subset=["Close"])
        return _normalize_history_frame(out, source=ALPACA_STOCK_SOURCE)

    def latest_stock_bar(self, symbol: str) -> dict[str, Any]:
        symbol_up = str(symbol).strip().upper()
        if symbol_up.startswith("^"):
            raise AlpacaMarketDataError(f"Alpaca latest bars do not support index symbol {symbol_up}")
        payload = self._get(
            f"{_data_v2_base()}/stocks/bars/latest",
            {"symbols": symbol_up, "feed": _stock_feed()},
        )
        bar = (payload.get("bars") or {}).get(symbol_up) or {}
        return dict(bar) if isinstance(bar, dict) else {}

    def option_contracts(
        self,
        symbol: str,
        *,
        status: str = "active",
        expiration_date: str | None = None,
        expiration_date_gte: str | None = None,
        expiration_date_lte: str | None = None,
        option_type: str | None = None,
        root_symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "underlying_symbols": str(symbol).strip().upper(),
            "status": str(status or "active").strip().lower(),
            "limit": 10000,
        }
        if expiration_date:
            params["expiration_date"] = expiration_date
        if expiration_date_gte:
            params["expiration_date_gte"] = expiration_date_gte
        if expiration_date_lte:
            params["expiration_date_lte"] = expiration_date_lte
        if option_type:
            params["type"] = option_type
        if root_symbol:
            params["root_symbol"] = root_symbol

        rows: list[dict[str, Any]] = []
        url = f"{_trading_v2_base()}/options/contracts"
        while True:
            payload = self._get(url, params)
            rows.extend(row for row in (payload.get("option_contracts") or []) if isinstance(row, dict))
            token = payload.get("next_page_token")
            if not token:
                break
            params["page_token"] = token
        return rows

    def historical_option_bars(
        self,
        symbols: Iterable[str] | str,
        *,
        start: Any,
        end: Any,
        timeframe: str = "1Day",
        limit: int = 10000,
    ) -> dict[str, list[dict[str, Any]]]:
        if isinstance(symbols, str):
            normalized_symbols = [item.strip().upper() for item in symbols.split(",") if item.strip()]
        else:
            normalized_symbols = [str(item).strip().upper() for item in symbols if str(item).strip()]
        if not normalized_symbols:
            return {}
        if len(normalized_symbols) > 100:
            raise AlpacaMarketDataError("Alpaca historical option bars accept at most 100 symbols per request")

        params: dict[str, Any] = {
            "symbols": ",".join(normalized_symbols),
            "timeframe": _timeframe(timeframe),
            "start": _alpaca_rfc3339(start),
            "end": _alpaca_rfc3339(end),
            "limit": max(1, min(int(limit), 10000)),
            "sort": "asc",
        }
        # The historical options bars endpoint does not expose a feed query param.
        # OPRA entitlement is controlled by the account subscription behind the key.
        url = f"{_data_root()}/v1beta1/options/bars"
        bars: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in normalized_symbols}
        while True:
            payload = self._get(url, params)
            raw = payload.get("bars") or {}
            if isinstance(raw, dict):
                for symbol, rows in raw.items():
                    symbol_up = str(symbol).strip().upper()
                    if isinstance(rows, list):
                        bars.setdefault(symbol_up, []).extend(row for row in rows if isinstance(row, dict))
            token = payload.get("next_page_token")
            if not token:
                break
            params["page_token"] = token
        return bars

    def historical_option_trades(
        self,
        symbols: Iterable[str] | str,
        *,
        start: Any,
        end: Any,
        limit: int = 10000,
    ) -> dict[str, list[dict[str, Any]]]:
        if isinstance(symbols, str):
            normalized_symbols = [item.strip().upper() for item in symbols.split(",") if item.strip()]
        else:
            normalized_symbols = [str(item).strip().upper() for item in symbols if str(item).strip()]
        if not normalized_symbols:
            return {}
        if len(normalized_symbols) > 100:
            raise AlpacaMarketDataError("Alpaca historical option trades accept at most 100 symbols per request")

        params: dict[str, Any] = {
            "symbols": ",".join(normalized_symbols),
            "start": _alpaca_rfc3339(start),
            "end": _alpaca_rfc3339(end),
            "limit": max(1, min(int(limit), 10000)),
            "sort": "asc",
        }
        # Like historical option bars, trades are entitlement-controlled by the key.
        url = f"{_data_root()}/v1beta1/options/trades"
        trades: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in normalized_symbols}
        while True:
            payload = self._get(url, params)
            raw = payload.get("trades") or {}
            if isinstance(raw, dict):
                for symbol, rows in raw.items():
                    symbol_up = str(symbol).strip().upper()
                    if isinstance(rows, list):
                        trades.setdefault(symbol_up, []).extend(row for row in rows if isinstance(row, dict))
            token = payload.get("next_page_token")
            if not token:
                break
            params["page_token"] = token
        return trades

    def option_chain_snapshots(
        self,
        symbol: str,
        *,
        expiration_date: str,
        option_type: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        params: dict[str, Any] = {
            "feed": _options_feed(),
            "expiration_date": expiration_date,
            "limit": 1000,
        }
        if option_type:
            params["type"] = option_type
        snapshots: dict[str, dict[str, Any]] = {}
        url = f"{_data_root()}/v1beta1/options/snapshots/{str(symbol).strip().upper()}"
        while True:
            payload = self._get(url, params)
            raw = payload.get("snapshots") or {}
            if isinstance(raw, dict):
                snapshots.update({str(key).upper(): value for key, value in raw.items() if isinstance(value, dict)})
            token = payload.get("next_page_token")
            if not token:
                break
            params["page_token"] = token
        return snapshots


class AlpacaTicker:
    """Small yfinance-compatible wrapper for the scanner's market-data cache."""

    def __init__(
        self,
        symbol: str,
        *,
        client: AlpacaMarketDataClient | None = None,
        fallback_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self.symbol = str(symbol).strip().upper()
        self._client = client or AlpacaMarketDataClient()
        self._fallback_factory = fallback_factory
        self.market_data_source = primary_provider_label()
        self.fallback_reason: str | None = None

    def _fallback(self) -> Any:
        if not yahoo_fallback_enabled() or self._fallback_factory is None:
            raise AlpacaMarketDataError("Yahoo fallback is disabled")
        ticker = self._fallback_factory(self.symbol)
        self.market_data_source = YAHOO_FALLBACK_SOURCE
        return ticker

    @property
    def info(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        try:
            bar = self._client.latest_stock_bar(self.symbol)
            close = _to_float(bar.get("c"))
            if close is not None:
                payload.update(
                    {
                        "currentPrice": close,
                        "regularMarketPrice": close,
                        "previousClose": close,
                        "regularMarketPreviousClose": close,
                        "regularMarketVolume": _to_float(bar.get("v")),
                    }
                )
        except Exception as exc:
            self.fallback_reason = exc.__class__.__name__
        if payload:
            payload["market_data_source"] = ALPACA_STOCK_SOURCE
            return payload
        if self._fallback_factory is not None and yahoo_fallback_enabled():
            try:
                fallback_info = dict(getattr(self._fallback_factory(self.symbol), "info", {}) or {})
                fallback_info["market_data_source"] = YAHOO_FALLBACK_SOURCE
                return fallback_info
            except Exception:
                pass
        raise AlpacaMarketDataError("Alpaca latest stock bar did not return ticker info")

    @property
    def fast_info(self) -> SimpleNamespace:
        try:
            bar = self._client.latest_stock_bar(self.symbol)
            close = _to_float(bar.get("c"))
            if close is None:
                raise AlpacaMarketDataError("latest Alpaca bar did not include a close")
            self.market_data_source = ALPACA_STOCK_SOURCE
            return SimpleNamespace(
                last_price=close,
                regular_market_price=close,
                lastPrice=close,
                regularMarketPrice=close,
                market_data_source=ALPACA_STOCK_SOURCE,
            )
        except Exception as exc:
            self.fallback_reason = exc.__class__.__name__
            if self._fallback_factory is not None and yahoo_fallback_enabled():
                return _fallback_source(getattr(self._fallback_factory(self.symbol), "fast_info", SimpleNamespace()))
            raise

    def history(self, *args: Any, **kwargs: Any) -> pd.DataFrame:
        try:
            frame = self._client.stock_bars(
                self.symbol,
                period=kwargs.get("period"),
                start=kwargs.get("start"),
                end=kwargs.get("end"),
                interval=kwargs.get("interval") or "1d",
            )
            if frame.empty:
                raise AlpacaMarketDataError("Alpaca returned no stock bars")
            self.market_data_source = ALPACA_STOCK_SOURCE
            return frame
        except Exception as exc:
            self.fallback_reason = exc.__class__.__name__
            if self._fallback_factory is not None and yahoo_fallback_enabled():
                fallback = self._fallback_factory(self.symbol).history(*args, **kwargs)
                return _fallback_source(_normalize_history_frame(fallback, source=YAHOO_FALLBACK_SOURCE))
            raise

    @property
    def options(self) -> list[str]:
        try:
            today = datetime.now(UTC).date()
            lookahead_days = int(os.getenv("ALPACA_OPTIONS_LOOKAHEAD_DAYS") or "60")
            rows = self._client.option_contracts(
                self.symbol,
                expiration_date_gte=today.isoformat(),
                expiration_date_lte=(today + timedelta(days=max(lookahead_days, 1))).isoformat(),
            )
            expiries = sorted(
                {
                    str(row.get("expiration_date"))
                    for row in rows
                    if row.get("expiration_date")
                }
            )
            self.market_data_source = ALPACA_OPTIONS_SOURCE if _options_feed() == "opra" else "alpaca_indicative_options"
            return expiries
        except Exception as exc:
            self.fallback_reason = exc.__class__.__name__
            if self._fallback_factory is not None and yahoo_fallback_enabled():
                expiries = list(getattr(self._fallback_factory(self.symbol), "options", []) or [])
                self.market_data_source = YAHOO_FALLBACK_SOURCE
                return expiries
            raise

    def option_chain(self, expiry: str) -> SimpleNamespace:
        try:
            contracts = self._client.option_contracts(self.symbol, expiration_date=str(expiry))
            snapshots: dict[str, dict[str, Any]] = {}
            for option_type in ("call", "put"):
                snapshots.update(
                    self._client.option_chain_snapshots(
                        self.symbol,
                        expiration_date=str(expiry),
                        option_type=option_type,
                    )
                )
            chain = _chain_from_alpaca(self.symbol, str(expiry), contracts, snapshots)
            self.market_data_source = ALPACA_OPTIONS_SOURCE if _options_feed() == "opra" else "alpaca_indicative_options"
            return chain
        except Exception as exc:
            self.fallback_reason = exc.__class__.__name__
            if self._fallback_factory is not None and yahoo_fallback_enabled():
                raw = self._fallback_factory(self.symbol).option_chain(expiry)
                calls = getattr(raw, "calls", pd.DataFrame()).copy(deep=True)
                puts = getattr(raw, "puts", pd.DataFrame()).copy(deep=True)
                for frame in (calls, puts):
                    if isinstance(frame, pd.DataFrame):
                        frame["data_source"] = YAHOO_FALLBACK_SOURCE
                        frame["quote_source"] = YAHOO_FALLBACK_SOURCE
                        frame["source_feed"] = "yfinance_delayed"
                        frame.attrs["market_data_source"] = YAHOO_FALLBACK_SOURCE
                chain = SimpleNamespace(
                    calls=calls,
                    puts=puts,
                    source=YAHOO_FALLBACK_SOURCE,
                    market_data_source=YAHOO_FALLBACK_SOURCE,
                    fallback_reason=self.fallback_reason,
                )
                return chain
            raise


def _chain_from_alpaca(
    symbol: str,
    expiry: str,
    contracts: Iterable[dict[str, Any]],
    snapshots: dict[str, dict[str, Any]],
) -> SimpleNamespace:
    source = ALPACA_OPTIONS_SOURCE if _options_feed() == "opra" else "alpaca_indicative_options"
    calls: list[dict[str, Any]] = []
    puts: list[dict[str, Any]] = []
    for contract in contracts:
        contract_symbol = str(contract.get("symbol") or "").strip().upper()
        if not contract_symbol:
            continue
        parsed = _parse_occ_symbol(contract_symbol)
        option_type = str(contract.get("type") or parsed.get("type") or "").strip().lower()
        if option_type not in {"call", "put"}:
            continue
        if str(contract.get("expiration_date") or parsed.get("expiration_date") or "") != str(expiry):
            continue
        row = _option_row_from_alpaca(symbol, expiry, contract, snapshots.get(contract_symbol) or {}, source=source)
        if option_type == "call":
            calls.append(row)
        else:
            puts.append(row)

    call_frame = pd.DataFrame.from_records(calls)
    put_frame = pd.DataFrame.from_records(puts)
    for frame in (call_frame, put_frame):
        if not frame.empty and "strike" in frame:
            frame.sort_values("strike", inplace=True)
            frame.reset_index(drop=True, inplace=True)
        frame.attrs["market_data_source"] = source
    return SimpleNamespace(
        calls=call_frame,
        puts=put_frame,
        source=source,
        market_data_source=source,
        feed=_options_feed(),
    )


def _option_row_from_alpaca(
    symbol: str,
    expiry: str,
    contract: dict[str, Any],
    snapshot: dict[str, Any],
    *,
    source: str,
) -> dict[str, Any]:
    contract_symbol = str(contract.get("symbol") or "").strip().upper()
    parsed = _parse_occ_symbol(contract_symbol)
    latest_quote = snapshot.get("latestQuote") or snapshot.get("latest_quote") or {}
    latest_trade = snapshot.get("latestTrade") or snapshot.get("latest_trade") or {}
    daily_bar = snapshot.get("dailyBar") or snapshot.get("daily_bar") or {}
    greeks = snapshot.get("greeks") or {}

    bid = _to_float(_first_present(latest_quote, "bp", "bid_price", "bidPrice", "bid"))
    ask = _to_float(_first_present(latest_quote, "ap", "ask_price", "askPrice", "ask"))
    last = (
        _to_float(_first_present(latest_trade, "p", "price"))
        or _to_float(_first_present(daily_bar, "c", "close"))
        or _to_float(contract.get("close_price"))
    )
    volume = _to_int(_first_present(daily_bar, "v", "volume")) or 0
    open_interest = _to_int(contract.get("open_interest")) or 0
    iv = (
        _to_float(snapshot.get("impliedVolatility"))
        or _to_float(snapshot.get("implied_volatility"))
        or _to_float(_first_present(greeks, "iv", "impliedVolatility", "implied_volatility"))
        or 0.0
    )
    delta = _to_float(_first_present(greeks, "delta", "d"))
    quote_ts = _timestamp(_first_present(latest_quote, "t", "timestamp"))
    trade_ts = _timestamp(_first_present(latest_trade, "t", "timestamp"))
    freshness_ts = quote_ts or trade_ts

    return {
        "contractSymbol": contract_symbol,
        "strike": _to_float(contract.get("strike_price")) or _to_float(parsed.get("strike_price")) or 0.0,
        "bid": bid or 0.0,
        "ask": ask or 0.0,
        "lastPrice": last or 0.0,
        "impliedVolatility": iv,
        "delta": delta,
        "volume": volume,
        "openInterest": open_interest,
        "lastTradeDate": freshness_ts.isoformat() if freshness_ts is not None else None,
        "latestQuoteTime": quote_ts.isoformat() if quote_ts is not None else None,
        "latestTradeDate": trade_ts.isoformat() if trade_ts is not None else None,
        "expiration": expiry,
        "optionType": str(contract.get("type") or parsed.get("type") or "").strip().lower(),
        "underlyingSymbol": str(contract.get("underlying_symbol") or symbol).strip().upper(),
        "data_source": source,
        "quote_source": source,
        "source_feed": _options_feed(),
        "snapshot_source": source,
        "tradable": bool(contract.get("tradable", True)),
        "openInterestDate": contract.get("open_interest_date"),
        "quote_bid_size": _to_int(_first_present(latest_quote, "bs", "bid_size")),
        "quote_ask_size": _to_int(_first_present(latest_quote, "as", "ask_size")),
    }


def make_alpaca_ticker_factory(
    *,
    fallback_factory: Callable[[str], Any] | None = None,
    client: AlpacaMarketDataClient | None = None,
) -> Callable[[str], AlpacaTicker]:
    shared_client = client or AlpacaMarketDataClient()

    def _factory(symbol: str) -> AlpacaTicker:
        return AlpacaTicker(symbol, client=shared_client, fallback_factory=fallback_factory)

    return _factory
