from __future__ import annotations

import copy
import json
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any, Callable, Optional

import pandas as pd
import yfinance as yf


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MARKET_DATA_DB_PATH = os.path.join(ROOT_DIR, "market_data.db")

_INFO_TTL = timedelta(days=7)
_EARNINGS_TTL = timedelta(hours=24)
_OPTIONS_TTL = timedelta(minutes=5)
_OPTION_CHAIN_TTL = timedelta(minutes=5)
_FAST_INFO_TTL = timedelta(seconds=30)
_INTRADAY_HISTORY_TTL = timedelta(seconds=60)
_RECENT_REFRESH_TRADING_DAYS = 5
_INFO_FIELDS = (
    "sector",
    "marketCap",
    "previousClose",
    "regularMarketPreviousClose",
    "currentPrice",
    "regularMarketPrice",
    "regularMarketOpen",
    "dayHigh",
    "dayLow",
    "regularMarketVolume",
)

_REQUEST_MEMO: ContextVar[Optional[dict[tuple[Any, ...], Any]]] = ContextVar(
    "market_data_request_memo",
    default=None,
)
_MEMORY_CACHE: dict[tuple[Any, ...], tuple[datetime, Any]] = {}
_CACHE_STATS: dict[str, dict[str, int]] = {}
_CACHE_LOCK = threading.RLock()
_SCHEMA_READY: set[str] = set()

_HISTORY_PERIOD_RE = re.compile(r"^(?P<count>\d+)(?P<unit>d|mo|y)$", re.IGNORECASE)


def _clone_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, pd.DataFrame):
        return value.copy(deep=True)
    if isinstance(value, pd.Series):
        return value.copy(deep=True)
    if isinstance(value, SimpleNamespace):
        return SimpleNamespace(
            **{key: _clone_value(val) for key, val in vars(value).items()}
        )
    return copy.deepcopy(value)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _record_stat(namespace: str, event: str, count: int = 1) -> None:
    with _CACHE_LOCK:
        bucket = _CACHE_STATS.setdefault(str(namespace), {})
        bucket[event] = int(bucket.get(event, 0)) + int(count)


def _stats_totals_snapshot(stats: dict[str, dict[str, int]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for bucket in stats.values():
        for event, count in bucket.items():
            totals[event] = totals.get(event, 0) + int(count)
    return totals


def _memory_cache_family_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    with _CACHE_LOCK:
        keys = list(_MEMORY_CACHE.keys())
    for key in keys:
        family = str(key[0]) if key else "unknown"
        counts[family] = counts.get(family, 0) + 1
    return counts


def get_cache_stats() -> dict[str, Any]:
    path = _db_path()
    memo = _REQUEST_MEMO.get()
    with _CACHE_LOCK:
        stats = copy.deepcopy(_CACHE_STATS)
        memory_cache_entries = len(_MEMORY_CACHE)
        schema_initialized = path in _SCHEMA_READY
    return {
        "generated_at": _utcnow().isoformat(timespec="seconds"),
        "status": "ok" if os.path.exists(path) or schema_initialized else "cold",
        "db_path": path,
        "db_exists": os.path.exists(path),
        "memory_cache_entries": memory_cache_entries,
        "memory_cache_families": _memory_cache_family_counts(),
        "request_scope_active": memo is not None,
        "request_scope_entries": len(memo or {}),
        "schema_initialized": schema_initialized,
        "policy": {
            "info_ttl_seconds": int(_INFO_TTL.total_seconds()),
            "earnings_ttl_seconds": int(_EARNINGS_TTL.total_seconds()),
            "options_ttl_seconds": int(_OPTIONS_TTL.total_seconds()),
            "option_chain_ttl_seconds": int(_OPTION_CHAIN_TTL.total_seconds()),
            "fast_info_ttl_seconds": int(_FAST_INFO_TTL.total_seconds()),
            "intraday_history_ttl_seconds": int(_INTRADAY_HISTORY_TTL.total_seconds()),
            "recent_refresh_trading_days": int(_RECENT_REFRESH_TRADING_DAYS),
        },
        "stats": stats,
        "totals": _stats_totals_snapshot(stats),
    }


def reset_cache_stats() -> dict[str, Any]:
    before = get_cache_stats()
    with _CACHE_LOCK:
        _CACHE_STATS.clear()
    after = get_cache_stats()
    return {
        "message": "market-data cache stats reset",
        "before": before,
        "after": after,
    }


def _db_path() -> str:
    return os.getenv("MARKET_DATA_DB_PATH") or DEFAULT_MARKET_DATA_DB_PATH


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _ensure_schema() -> None:
    path = _db_path()
    with _CACHE_LOCK:
        if path in _SCHEMA_READY:
            return
        _ensure_parent_dir(path)
        conn = sqlite3.connect(path)
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS daily_history (
                    symbol TEXT NOT NULL,
                    bar_date TEXT NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    adj_close REAL,
                    volume REAL,
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY (symbol, bar_date)
                );
                CREATE TABLE IF NOT EXISTS ticker_info_cache (
                    symbol TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS earnings_dates_cache (
                    symbol TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS option_expiries_cache (
                    symbol TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    error_json TEXT
                );
                CREATE TABLE IF NOT EXISTS option_chain_snapshot_cache (
                    symbol TEXT NOT NULL,
                    expiry TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    error_json TEXT,
                    PRIMARY KEY (symbol, expiry)
                );
                """
            )
            conn.commit()
            _SCHEMA_READY.add(path)
        finally:
            conn.close()


@contextmanager
def request_scope():
    memo = _REQUEST_MEMO.get()
    if memo is not None:
        yield memo
        return
    token = _REQUEST_MEMO.set({})
    try:
        yield _REQUEST_MEMO.get()
    finally:
        _REQUEST_MEMO.reset(token)


def _request_memo_get(key: tuple[Any, ...]) -> Any:
    memo = _REQUEST_MEMO.get()
    if memo is None or key not in memo:
        return None
    return _clone_value(memo[key])


def _request_memo_set(key: tuple[Any, ...], value: Any) -> None:
    memo = _REQUEST_MEMO.get()
    if memo is None:
        return
    memo[key] = _clone_value(value)


def _memory_cache_get(key: tuple[Any, ...]) -> Any:
    now = _utcnow()
    with _CACHE_LOCK:
        hit = _MEMORY_CACHE.get(key)
        if hit is None:
            return None
        expires_at, value = hit
        if expires_at <= now:
            _MEMORY_CACHE.pop(key, None)
            return None
        return _clone_value(value)


def _memory_cache_set(key: tuple[Any, ...], value: Any, ttl: timedelta) -> None:
    with _CACHE_LOCK:
        _MEMORY_CACHE[key] = (_utcnow() + ttl, _clone_value(value))


def _read_through_memory_cache(
    key: tuple[Any, ...],
    ttl: timedelta,
    fetcher: Callable[[], Any],
    namespace: str,
) -> Any:
    memo_hit = _request_memo_get(key)
    if memo_hit is not None:
        _record_stat(namespace, "request_memo_hits")
        return memo_hit
    cached = _memory_cache_get(key)
    if cached is not None:
        _record_stat(namespace, "memory_hits")
        _request_memo_set(key, cached)
        return cached
    _record_stat(namespace, "memory_misses")
    value = fetcher()
    _record_stat(namespace, "network_fetches")
    _memory_cache_set(key, value, ttl)
    _request_memo_set(key, value)
    return _clone_value(value)


def _normalize_history_frame(frame: Optional[pd.DataFrame]) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    normalized = frame.copy()
    if not isinstance(normalized.index, pd.DatetimeIndex):
        normalized.index = pd.to_datetime(normalized.index)
    normalized = normalized.sort_index()
    normalized = normalized[~normalized.index.duplicated(keep="last")]
    keep = [col for col in ["Open", "High", "Low", "Close", "Adj Close", "Volume"] if col in normalized.columns]
    return normalized[keep].copy() if keep else normalized.copy()


def _ticker_factory_or_default(ticker_factory: Optional[Callable[[str], Any]]) -> Callable[[str], Any]:
    return ticker_factory or yf.Ticker


def _download_fn_or_default(download_fn: Optional[Callable[..., Any]]) -> Callable[..., Any]:
    return download_fn or yf.download


def _fetch_history_direct(
    symbol: str,
    *,
    period: Optional[str] = None,
    start: Optional[Any] = None,
    end: Optional[Any] = None,
    interval: str = "1d",
    ticker_factory: Optional[Callable[[str], Any]] = None,
) -> pd.DataFrame:
    ticker = _ticker_factory_or_default(ticker_factory)(symbol)
    kwargs: dict[str, Any] = {"interval": interval}
    if period is not None:
        kwargs["period"] = period
    if start is not None:
        kwargs["start"] = start
    if end is not None:
        kwargs["end"] = end
    return _normalize_history_frame(ticker.history(**kwargs))


def _parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.Timestamp(value).date()


def _normalize_daily_window(
    *,
    period: Optional[str] = None,
    start: Optional[Any] = None,
    end: Optional[Any] = None,
) -> Optional[tuple[date, date]]:
    today = datetime.now().date()
    if start is not None:
        start_date = _parse_date(start)
    elif period:
        match = _HISTORY_PERIOD_RE.match(str(period).strip())
        if not match:
            return None
        count = int(match.group("count"))
        unit = match.group("unit").lower()
        if unit == "d":
            start_date = (pd.Timestamp(today) - pd.Timedelta(days=count)).date()
        elif unit == "mo":
            start_date = (pd.Timestamp(today) - pd.DateOffset(months=count)).date()
        elif unit == "y":
            start_date = (pd.Timestamp(today) - pd.DateOffset(years=count)).date()
        else:
            return None
    else:
        return None

    if end is not None:
        end_date = _parse_date(end) - timedelta(days=1)
    else:
        end_date = today
    if start_date > end_date:
        return None
    return start_date, end_date


def _recent_refresh_start(anchor: Optional[date] = None) -> date:
    today = anchor or datetime.now().date()
    return (pd.Timestamp(today) - pd.offsets.BDay(_RECENT_REFRESH_TRADING_DAYS)).date()


def _business_dates(start_date: date, end_date: date) -> set[str]:
    if start_date > end_date:
        return set()
    return {
        ts.date().isoformat()
        for ts in pd.bdate_range(start=start_date, end=end_date)
    }


def _load_daily_history_rows(symbol: str, start_date: date, end_date: date) -> pd.DataFrame:
    _ensure_schema()
    conn = sqlite3.connect(_db_path())
    try:
        rows = pd.read_sql_query(
            """
            SELECT bar_date, open, high, low, close, adj_close, volume
            FROM daily_history
            WHERE symbol = ? AND bar_date >= ? AND bar_date <= ?
            ORDER BY bar_date
            """,
            conn,
            params=(symbol.upper(), start_date.isoformat(), end_date.isoformat()),
        )
    finally:
        conn.close()
    if rows.empty:
        return pd.DataFrame()
    rows["bar_date"] = pd.to_datetime(rows["bar_date"])
    rows = rows.set_index("bar_date")
    renamed = rows.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "adj_close": "Adj Close",
            "volume": "Volume",
        }
    )
    return _normalize_history_frame(renamed)


def _store_daily_history(symbol: str, frame: pd.DataFrame) -> None:
    normalized = _normalize_history_frame(frame)
    if normalized.empty:
        return
    _ensure_schema()
    fetched_at = _utcnow().isoformat(timespec="seconds")
    rows: list[tuple[Any, ...]] = []
    for ts, row in normalized.iterrows():
        rows.append(
            (
                symbol.upper(),
                pd.Timestamp(ts).date().isoformat(),
                _as_float(row.get("Open")),
                _as_float(row.get("High")),
                _as_float(row.get("Low")),
                _as_float(row.get("Close")),
                _as_float(row.get("Adj Close")),
                _as_float(row.get("Volume")),
                fetched_at,
            )
        )
    conn = sqlite3.connect(_db_path())
    try:
        conn.executemany(
            """
            INSERT INTO daily_history (
                symbol, bar_date, open, high, low, close, adj_close, volume, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, bar_date) DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                adj_close = excluded.adj_close,
                volume = excluded.volume,
                fetched_at = excluded.fetched_at
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def _as_float(value: Any) -> Optional[float]:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def _store_json_cache(table: str, symbol: str, payload: dict[str, Any]) -> None:
    _ensure_schema()
    conn = sqlite3.connect(_db_path())
    try:
        conn.execute(
            f"""
            INSERT INTO {table} (symbol, payload_json, fetched_at)
            VALUES (?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                payload_json = excluded.payload_json,
                fetched_at = excluded.fetched_at
            """,
            (symbol.upper(), json.dumps(payload), _utcnow().isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()


def _load_json_cache(table: str, symbol: str, ttl: timedelta) -> Optional[dict[str, Any]]:
    _ensure_schema()
    conn = sqlite3.connect(_db_path())
    try:
        row = conn.execute(
            f"SELECT payload_json, fetched_at FROM {table} WHERE symbol = ?",
            (symbol.upper(),),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    fetched_at = datetime.fromisoformat(str(row[1]))
    if _utcnow() - fetched_at > ttl:
        return None
    try:
        payload = json.loads(str(row[0]))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, pd.DataFrame):
        return _json_safe(value.to_dict(orient="records"))
    if isinstance(value, pd.Series):
        return _json_safe(value.to_list())
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return pd.Timestamp(value).isoformat()
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        try:
            if pd.isna(value):
                return None
        except Exception:
            pass
        return value
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        extracted = value.item()
    except Exception:
        extracted = None
    if extracted is not None:
        return _json_safe(extracted)
    return str(value)


def _serialize_frame(frame: pd.DataFrame) -> dict[str, Any]:
    normalized = frame.copy(deep=True) if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    if normalized.empty:
        return {"columns": list(normalized.columns), "records": []}
    return {
        "columns": list(normalized.columns),
        "records": _json_safe(normalized.to_dict(orient="records")),
    }


def _deserialize_frame(payload: Any) -> pd.DataFrame:
    if not isinstance(payload, dict):
        return pd.DataFrame()
    columns = payload.get("columns") or []
    records = payload.get("records") or []
    if not isinstance(records, list):
        return pd.DataFrame()
    if not records:
        return pd.DataFrame(columns=list(columns))
    frame = pd.DataFrame.from_records(records)
    if columns:
        ordered = [column for column in columns if column in frame.columns]
        remainder = [column for column in frame.columns if column not in ordered]
        frame = frame[ordered + remainder]
    return frame.copy(deep=True)


def _error_payload(error: Any) -> dict[str, Any]:
    if isinstance(error, dict):
        return _json_safe(error)
    if error is None:
        return {}
    return {
        "type": error.__class__.__name__,
        "message": str(error),
    }


def _fetched_at_to_iso(fetched_at: Optional[datetime]) -> Optional[str]:
    if fetched_at is None:
        return None
    return fetched_at.replace(microsecond=0).isoformat(timespec="seconds")


def _freshness_payload(
    *,
    status: str,
    fetched_at: Optional[datetime],
    ttl: timedelta,
    source: str,
    stale_reason: Optional[str] = None,
    error: Optional[Any] = None,
) -> dict[str, Any]:
    age_seconds: Optional[float] = None
    if fetched_at is not None:
        age_seconds = max((_utcnow() - fetched_at).total_seconds(), 0.0)
    if status == "fresh" and age_seconds is not None and age_seconds > ttl.total_seconds():
        status = "stale"
        stale_reason = stale_reason or "ttl_expired"
    payload = {
        "status": status,
        "fresh": status == "fresh",
        "stale": status == "stale",
        "error": status == "error",
        "source": source,
        "fetched_at": _fetched_at_to_iso(fetched_at),
        "age_seconds": round(age_seconds, 3) if age_seconds is not None else None,
        "ttl_seconds": int(ttl.total_seconds()),
        "stale_reason": stale_reason,
        "error_payload": _error_payload(error) if error is not None else None,
    }
    return payload


def _snapshot_envelope(value: Any, freshness: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        value=_clone_value(value),
        status=freshness.get("status"),
        source=freshness.get("source"),
        fetched_at=freshness.get("fetched_at"),
        age_seconds=freshness.get("age_seconds"),
        freshness=SimpleNamespace(**freshness),
        stale_reason=freshness.get("stale_reason"),
        error=freshness.get("error_payload"),
    )


def _store_option_expiries(symbol: str, expiries: list[str], *, source: str, error: Optional[Any] = None) -> None:
    _ensure_schema()
    payload = {"expiries": list(expiries)}
    conn = sqlite3.connect(_db_path())
    try:
        conn.execute(
            """
            INSERT INTO option_expiries_cache (symbol, payload_json, fetched_at, source, error_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                payload_json = excluded.payload_json,
                fetched_at = excluded.fetched_at,
                source = excluded.source,
                error_json = excluded.error_json
            """,
            (
                symbol.upper(),
                json.dumps(_json_safe(payload)),
                _utcnow().isoformat(timespec="seconds"),
                str(source),
                json.dumps(_json_safe(_error_payload(error))) if error is not None else None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _load_option_expiries_record(symbol: str) -> Optional[dict[str, Any]]:
    _ensure_schema()
    conn = sqlite3.connect(_db_path())
    try:
        row = conn.execute(
            """
            SELECT payload_json, fetched_at, source, error_json
            FROM option_expiries_cache
            WHERE symbol = ?
            """,
            (symbol.upper(),),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    try:
        payload = json.loads(str(row[0]))
    except Exception:
        return None
    expiries = payload.get("expiries") if isinstance(payload, dict) else []
    if not isinstance(expiries, list):
        expiries = []
    try:
        fetched_at = datetime.fromisoformat(str(row[1]))
    except Exception:
        fetched_at = None
    error: Optional[dict[str, Any]] = None
    if row[3]:
        try:
            error = json.loads(str(row[3]))
        except Exception:
            error = {"type": "CacheError", "message": str(row[3])}
    freshness = _freshness_payload(
        status="fresh" if fetched_at is not None else "error",
        fetched_at=fetched_at,
        ttl=_OPTIONS_TTL,
        source=str(row[2] or "sqlite"),
        error=error,
    )
    return {
        "value": list(expiries),
        "freshness": freshness,
        "status": freshness["status"],
        "source": freshness["source"],
        "fetched_at": freshness["fetched_at"],
        "error": freshness["error_payload"],
    }


def _store_option_chain_snapshot(
    symbol: str,
    expiry: str,
    chain: SimpleNamespace,
    *,
    source: str,
    error: Optional[Any] = None,
) -> None:
    _ensure_schema()
    payload = {
        "calls": _serialize_frame(getattr(chain, "calls", pd.DataFrame())),
        "puts": _serialize_frame(getattr(chain, "puts", pd.DataFrame())),
    }
    conn = sqlite3.connect(_db_path())
    try:
        conn.execute(
            """
            INSERT INTO option_chain_snapshot_cache (symbol, expiry, payload_json, fetched_at, source, error_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, expiry) DO UPDATE SET
                payload_json = excluded.payload_json,
                fetched_at = excluded.fetched_at,
                source = excluded.source,
                error_json = excluded.error_json
            """,
            (
                symbol.upper(),
                str(expiry),
                json.dumps(_json_safe(payload)),
                _utcnow().isoformat(timespec="seconds"),
                str(source),
                json.dumps(_json_safe(_error_payload(error))) if error is not None else None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _load_option_chain_record(symbol: str, expiry: str) -> Optional[dict[str, Any]]:
    _ensure_schema()
    conn = sqlite3.connect(_db_path())
    try:
        row = conn.execute(
            """
            SELECT payload_json, fetched_at, source, error_json
            FROM option_chain_snapshot_cache
            WHERE symbol = ? AND expiry = ?
            """,
            (symbol.upper(), str(expiry)),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    try:
        payload = json.loads(str(row[0]))
    except Exception:
        return None
    try:
        fetched_at = datetime.fromisoformat(str(row[1]))
    except Exception:
        fetched_at = None
    error: Optional[dict[str, Any]] = None
    if row[3]:
        try:
            error = json.loads(str(row[3]))
        except Exception:
            error = {"type": "CacheError", "message": str(row[3])}
    freshness = _freshness_payload(
        status="fresh" if fetched_at is not None else "error",
        fetched_at=fetched_at,
        ttl=_OPTION_CHAIN_TTL,
        source=str(row[2] or "sqlite"),
        error=error,
    )
    return {
        "value": SimpleNamespace(
            calls=_deserialize_frame((payload or {}).get("calls")),
            puts=_deserialize_frame((payload or {}).get("puts")),
        ),
        "freshness": freshness,
        "status": freshness["status"],
        "source": freshness["source"],
        "fetched_at": freshness["fetched_at"],
        "error": freshness["error_payload"],
    }


def _ticker_info_payload(info: Optional[dict[str, Any]]) -> dict[str, Any]:
    source = info or {}
    return {field: source.get(field) for field in _INFO_FIELDS}


def _ticker_info_payload_complete(payload: Optional[dict[str, Any]]) -> bool:
    if not isinstance(payload, dict):
        return False
    return all(field in payload for field in _INFO_FIELDS)


def get_history(
    symbol: str,
    *,
    period: Optional[str] = None,
    start: Optional[Any] = None,
    end: Optional[Any] = None,
    interval: str = "1d",
    ticker_factory: Optional[Callable[[str], Any]] = None,
) -> pd.DataFrame:
    namespace = "history"
    key = ("history", symbol.upper(), period, str(start), str(end), interval)
    memo_hit = _request_memo_get(key)
    if memo_hit is not None:
        _record_stat(namespace, "request_memo_hits")
        return memo_hit

    if str(interval).lower() != "1d":
        def _fetch_intraday() -> pd.DataFrame:
            return _fetch_history_direct(
                symbol,
                period=period,
                start=start,
                end=end,
                interval=interval,
                ticker_factory=ticker_factory,
            )

        value = _read_through_memory_cache(key, _INTRADAY_HISTORY_TTL, _fetch_intraday, "history_intraday")
        return _normalize_history_frame(value)

    normalized_window = _normalize_daily_window(period=period, start=start, end=end)
    if normalized_window is None:
        _record_stat(namespace, "network_fetches")
        direct = _fetch_history_direct(
            symbol,
            period=period,
            start=start,
            end=end,
            interval=interval,
            ticker_factory=ticker_factory,
        )
        _request_memo_set(key, direct)
        return direct

    start_date, end_date = normalized_window
    try:
        cached = _load_daily_history_rows(symbol, start_date, end_date)
        if cached.empty:
            _record_stat(namespace, "persistent_misses")
            needs_full_refresh = True
        else:
            first_cached = cached.index.min().date()
            last_cached = cached.index.max().date()
            needs_full_refresh = first_cached > start_date or last_cached < end_date
            if needs_full_refresh:
                _record_stat(namespace, "persistent_partial_hits")
            else:
                _record_stat(namespace, "persistent_hits")
        touches_recent = end_date >= _recent_refresh_start()

        if needs_full_refresh:
            _record_stat(namespace, "full_refreshes")
            _record_stat(namespace, "network_fetches")
            fetched = _fetch_history_direct(
                symbol,
                start=start_date.isoformat(),
                end=(end_date + timedelta(days=1)).isoformat(),
                interval="1d",
                ticker_factory=ticker_factory,
            )
            if not fetched.empty:
                _store_daily_history(symbol, fetched)
        elif touches_recent:
            _record_stat(namespace, "recent_refreshes")
            _record_stat(namespace, "network_fetches")
            refresh_start = max(start_date, _recent_refresh_start())
            fetched = _fetch_history_direct(
                symbol,
                start=refresh_start.isoformat(),
                end=(end_date + timedelta(days=1)).isoformat(),
                interval="1d",
                ticker_factory=ticker_factory,
            )
            if not fetched.empty:
                _store_daily_history(symbol, fetched)

        frame = _load_daily_history_rows(symbol, start_date, end_date)
        if frame.empty:
            _record_stat(namespace, "fallback_fetches")
            _record_stat(namespace, "network_fetches")
            frame = _fetch_history_direct(
                symbol,
                start=start_date.isoformat(),
                end=(end_date + timedelta(days=1)).isoformat(),
                interval="1d",
                ticker_factory=ticker_factory,
            )
        _request_memo_set(key, frame)
        return _normalize_history_frame(frame)
    except Exception:
        _record_stat(namespace, "cache_failures")
        _record_stat(namespace, "fallback_fetches")
        _record_stat(namespace, "network_fetches")
        direct = _fetch_history_direct(
            symbol,
            period=period,
            start=start,
            end=end,
            interval=interval,
            ticker_factory=ticker_factory,
        )
        _request_memo_set(key, direct)
        return direct


def download_history_batch(
    tickers: list[str],
    *,
    period: str,
    auto_adjust: bool = True,
    ticker_factory: Optional[Callable[[str], Any]] = None,
    download_fn: Optional[Callable[..., Any]] = None,
) -> pd.DataFrame:
    namespace = "download_history_batch"
    symbols = [str(t).upper() for t in tickers if str(t).strip()]
    key = ("download_history_batch", tuple(symbols), period, bool(auto_adjust))
    memo_hit = _request_memo_get(key)
    if memo_hit is not None:
        _record_stat(namespace, "request_memo_hits")
        return memo_hit
    frames: dict[str, pd.DataFrame] = {}
    try:
        for symbol in symbols:
            frame = get_history(
                symbol,
                period=period,
                interval="1d",
                ticker_factory=ticker_factory,
            )
            if not frame.empty:
                frames[symbol] = frame
    except Exception:
        _record_stat(namespace, "cache_failures")
        frames = {}

    if not frames:
        _record_stat(namespace, "network_fallbacks")
        _record_stat(namespace, "network_fetches")
        download = _download_fn_or_default(download_fn)
        raw = download(symbols, period=period, progress=False, auto_adjust=auto_adjust)
        result = raw.copy() if isinstance(raw, pd.DataFrame) else pd.DataFrame()
        _request_memo_set(key, result)
        return result

    _record_stat(namespace, "cache_hits")
    combined = pd.concat(frames, axis=1).swaplevel(axis=1).sort_index(axis=1)
    _request_memo_set(key, combined)
    return combined


def get_ticker_info(
    symbol: str,
    *,
    ticker_factory: Optional[Callable[[str], Any]] = None,
) -> dict[str, Any]:
    namespace = "ticker_info"
    key = ("ticker_info", symbol.upper())
    memo_hit = _request_memo_get(key)
    if memo_hit is not None:
        _record_stat(namespace, "request_memo_hits")
        return memo_hit
    try:
        cached = _load_json_cache("ticker_info_cache", symbol, _INFO_TTL)
        if _ticker_info_payload_complete(cached):
            _record_stat(namespace, "persistent_hits")
            _request_memo_set(key, cached)
            return cached
        _record_stat(namespace, "persistent_misses")
    except Exception:
        _record_stat(namespace, "cache_failures")
        pass

    try:
        info = dict(getattr(_ticker_factory_or_default(ticker_factory)(symbol), "info", {}) or {})
        _record_stat(namespace, "network_fetches")
        payload = _ticker_info_payload(info)
        try:
            _store_json_cache("ticker_info_cache", symbol, payload)
        except Exception:
            _record_stat(namespace, "cache_write_failures")
            pass
        _request_memo_set(key, payload)
        return payload
    except Exception:
        _record_stat(namespace, "fallbacks")
        fallback: dict[str, Any] = {}
        _request_memo_set(key, fallback)
        return fallback


def _earnings_df_from_payload(payload: Optional[dict[str, Any]]) -> pd.DataFrame:
    if not payload:
        return pd.DataFrame()
    values = payload.get("index") or []
    if not values:
        return pd.DataFrame()
    return pd.DataFrame(index=pd.to_datetime(values))


def get_earnings_dates(
    symbol: str,
    *,
    ticker_factory: Optional[Callable[[str], Any]] = None,
) -> pd.DataFrame:
    namespace = "earnings_dates"
    key = ("earnings_dates", symbol.upper())
    memo_hit = _request_memo_get(key)
    if memo_hit is not None:
        _record_stat(namespace, "request_memo_hits")
        return memo_hit
    try:
        cached = _load_json_cache("earnings_dates_cache", symbol, _EARNINGS_TTL)
        if cached is not None:
            _record_stat(namespace, "persistent_hits")
            frame = _earnings_df_from_payload(cached)
            _request_memo_set(key, frame)
            return frame
        _record_stat(namespace, "persistent_misses")
    except Exception:
        _record_stat(namespace, "cache_failures")
        pass

    try:
        ticker = _ticker_factory_or_default(ticker_factory)(symbol)
        earnings = getattr(ticker, "earnings_dates", None)
        _record_stat(namespace, "network_fetches")
        frame = earnings.copy() if isinstance(earnings, pd.DataFrame) else pd.DataFrame()
        payload = {
            "index": [pd.Timestamp(ts).isoformat() for ts in frame.index]
        } if not frame.empty else {"index": []}
        try:
            _store_json_cache("earnings_dates_cache", symbol, payload)
        except Exception:
            _record_stat(namespace, "cache_write_failures")
            pass
        _request_memo_set(key, frame)
        return frame
    except Exception:
        _record_stat(namespace, "fallbacks")
        empty = pd.DataFrame()
        _request_memo_set(key, empty)
        return empty


def get_options(
    symbol: str,
    *,
    ticker_factory: Optional[Callable[[str], Any]] = None,
    include_metadata: bool = False,
) -> list[str] | SimpleNamespace:
    namespace = "options"
    symbol_up = symbol.upper()
    memo_key = ("options", symbol_up, bool(include_metadata))
    memo_hit = _request_memo_get(memo_key)
    if memo_hit is not None:
        _record_stat(namespace, "request_memo_hits")
        return memo_hit

    def _fresh_record_to_value(record: dict[str, Any]) -> list[str]:
        value = record.get("value") if isinstance(record, dict) else []
        return list(value or [])

    if not include_metadata:
        cache_key = ("options", symbol_up)
        cached = _memory_cache_get(cache_key)
        if cached is not None:
            _record_stat(namespace, "memory_hits")
            value = list(cached or [])
            _request_memo_set(memo_key, value)
            return value
        _record_stat(namespace, "memory_misses")
        try:
            record = _load_option_expiries_record(symbol_up)
            if record is not None and record.get("status") == "fresh":
                _record_stat(namespace, "persistent_hits")
                value = _fresh_record_to_value(record)
                _memory_cache_set(cache_key, value, _OPTIONS_TTL)
                _request_memo_set(memo_key, value)
                return value
            if record is not None:
                _record_stat(namespace, "persistent_stale_hits")
            else:
                _record_stat(namespace, "persistent_misses")
        except Exception:
            _record_stat(namespace, "cache_failures")
        try:
            ticker = _ticker_factory_or_default(ticker_factory)(symbol)
            expiries = list(getattr(ticker, "options", []) or [])
            _record_stat(namespace, "network_fetches")
            try:
                _store_option_expiries(symbol_up, expiries, source="network")
            except Exception:
                _record_stat(namespace, "cache_write_failures")
            _memory_cache_set(cache_key, expiries, _OPTIONS_TTL)
            _request_memo_set(memo_key, expiries)
            return expiries
        except Exception as exc:
            _record_stat(namespace, "fallbacks")
            empty: list[str] = []
            _request_memo_set(memo_key, empty)
            return empty

    record: Optional[dict[str, Any]] = None
    try:
        record = _load_option_expiries_record(symbol_up)
        if record is not None:
            status = str(record.get("status") or "error")
            if status == "fresh":
                _record_stat(namespace, "persistent_hits")
            elif status == "stale":
                _record_stat(namespace, "persistent_stale_hits")
            else:
                _record_stat(namespace, "persistent_misses")
            envelope = _snapshot_envelope(
                record.get("value") or [],
                record.get("freshness") or _freshness_payload(
                    status=status,
                    fetched_at=None,
                    ttl=_OPTIONS_TTL,
                    source="sqlite",
                ),
            )
            _request_memo_set(memo_key, envelope)
            return envelope
        _record_stat(namespace, "persistent_misses")
    except Exception as exc:
        _record_stat(namespace, "cache_failures")
        record = None

    try:
        ticker = _ticker_factory_or_default(ticker_factory)(symbol)
        expiries = list(getattr(ticker, "options", []) or [])
        _record_stat(namespace, "network_fetches")
        try:
            _store_option_expiries(symbol_up, expiries, source="network")
        except Exception:
            _record_stat(namespace, "cache_write_failures")
        envelope = _snapshot_envelope(
            expiries,
            _freshness_payload(
                status="fresh",
                fetched_at=_utcnow(),
                ttl=_OPTIONS_TTL,
                source="network",
            ),
        )
        _request_memo_set(memo_key, envelope)
        return envelope
    except Exception as exc:
        _record_stat(namespace, "fallbacks")
        envelope = _snapshot_envelope(
            [],
            _freshness_payload(
                status="error",
                fetched_at=None,
                ttl=_OPTIONS_TTL,
                source="error",
                error=exc,
                stale_reason="network_fetch_failed",
            ),
        )
        _request_memo_set(memo_key, envelope)
        return envelope


def get_option_chain(
    symbol: str,
    expiry: str,
    *,
    ticker_factory: Optional[Callable[[str], Any]] = None,
    include_metadata: bool = False,
) -> SimpleNamespace:
    namespace = "option_chain"
    symbol_up = symbol.upper()
    memo_key = ("option_chain", symbol_up, str(expiry), bool(include_metadata))
    memo_hit = _request_memo_get(memo_key)
    if memo_hit is not None:
        _record_stat(namespace, "request_memo_hits")
        return memo_hit

    def _network_fetch() -> SimpleNamespace:
        chain = _ticker_factory_or_default(ticker_factory)(symbol).option_chain(expiry)
        return SimpleNamespace(
            calls=getattr(chain, "calls", pd.DataFrame()).copy(deep=True),
            puts=getattr(chain, "puts", pd.DataFrame()).copy(deep=True),
        )

    if not include_metadata:
        cache_key = ("option_chain", symbol_up, str(expiry))
        cached = _memory_cache_get(cache_key)
        if cached is not None:
            _record_stat(namespace, "memory_hits")
            _request_memo_set(memo_key, cached)
            return cached
        _record_stat(namespace, "memory_misses")
        try:
            record = _load_option_chain_record(symbol_up, expiry)
            if record is not None and record.get("status") == "fresh":
                _record_stat(namespace, "persistent_hits")
                value = record["value"]
                _memory_cache_set(cache_key, value, _OPTION_CHAIN_TTL)
                _request_memo_set(memo_key, value)
                return value
            if record is not None:
                _record_stat(namespace, "persistent_stale_hits")
            else:
                _record_stat(namespace, "persistent_misses")
        except Exception:
            _record_stat(namespace, "cache_failures")
        try:
            value = _network_fetch()
            _record_stat(namespace, "network_fetches")
            try:
                _store_option_chain_snapshot(symbol_up, expiry, value, source="network")
            except Exception:
                _record_stat(namespace, "cache_write_failures")
            _memory_cache_set(cache_key, value, _OPTION_CHAIN_TTL)
            _request_memo_set(memo_key, value)
            return value
        except Exception as exc:
            _record_stat(namespace, "fallbacks")
            empty = SimpleNamespace(calls=pd.DataFrame(), puts=pd.DataFrame())
            _request_memo_set(memo_key, empty)
            return empty

    try:
        record = _load_option_chain_record(symbol_up, expiry)
        if record is not None:
            status = str(record.get("status") or "error")
            if status == "fresh":
                _record_stat(namespace, "persistent_hits")
            elif status == "stale":
                _record_stat(namespace, "persistent_stale_hits")
            else:
                _record_stat(namespace, "persistent_misses")
            envelope = _snapshot_envelope(
                record["value"],
                record.get("freshness") or _freshness_payload(
                    status=status,
                    fetched_at=None,
                    ttl=_OPTION_CHAIN_TTL,
                    source="sqlite",
                ),
            )
            _request_memo_set(memo_key, envelope)
            return envelope
        _record_stat(namespace, "persistent_misses")
    except Exception:
        _record_stat(namespace, "cache_failures")

    try:
        value = _network_fetch()
        _record_stat(namespace, "network_fetches")
        try:
            _store_option_chain_snapshot(symbol_up, expiry, value, source="network")
        except Exception:
            _record_stat(namespace, "cache_write_failures")
        envelope = _snapshot_envelope(
            value,
            _freshness_payload(
                status="fresh",
                fetched_at=_utcnow(),
                ttl=_OPTION_CHAIN_TTL,
                source="network",
            ),
        )
        _request_memo_set(memo_key, envelope)
        return envelope
    except Exception as exc:
        _record_stat(namespace, "fallbacks")
        empty = _snapshot_envelope(
            SimpleNamespace(calls=pd.DataFrame(), puts=pd.DataFrame()),
            _freshness_payload(
                status="error",
                fetched_at=None,
                ttl=_OPTION_CHAIN_TTL,
                source="error",
                error=exc,
                stale_reason="network_fetch_failed",
            ),
        )
        _request_memo_set(memo_key, empty)
        return empty


def get_fast_info(
    symbol: str,
    *,
    ticker_factory: Optional[Callable[[str], Any]] = None,
) -> SimpleNamespace:
    key = ("fast_info", symbol.upper())

    def _fetch() -> SimpleNamespace:
        raw = getattr(_ticker_factory_or_default(ticker_factory)(symbol), "fast_info", None)
        if raw is None:
            return SimpleNamespace()
        if isinstance(raw, dict):
            return SimpleNamespace(**dict(raw))
        try:
            return SimpleNamespace(**dict(raw))
        except Exception:
            return SimpleNamespace(
                last_price=getattr(raw, "last_price", None),
                regular_market_price=getattr(raw, "regular_market_price", None),
                lastPrice=getattr(raw, "lastPrice", None),
                regularMarketPrice=getattr(raw, "regularMarketPrice", None),
            )

    return _read_through_memory_cache(key, _FAST_INFO_TTL, _fetch, "fast_info")
