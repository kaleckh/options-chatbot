from __future__ import annotations

import copy
import inspect
import json
import os
import re
import sqlite3
import weakref
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any, Callable, Optional

import pandas as pd
import yfinance as yf

from alpaca_market_data import alpaca_provider_requested, make_alpaca_ticker_factory
from us_equity_market_calendar import is_us_equity_market_day


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
    "earningsDate",
    "earningsTimestamp",
    "earningsTimestampStart",
    "earningsTimestampEnd",
)

_REQUEST_MEMO: ContextVar[Optional[dict[tuple[Any, ...], Any]]] = ContextVar(
    "market_data_request_memo",
    default=None,
)
_MEMORY_CACHE: dict[tuple[Any, ...], tuple[datetime, Any]] = {}
_CACHE_STATS: dict[str, dict[str, int]] = {}
_CACHE_LOCK = threading.RLock()
_THREAD_LOCAL = threading.local()
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
    _close_thread_local_connections()
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


def _close_thread_local_connections(*, keep_path: str | None = None) -> None:
    connections = getattr(_THREAD_LOCAL, "connections", None)
    if not connections:
        return
    keep = os.path.abspath(keep_path) if keep_path else None
    retained: dict[str, sqlite3.Connection] = {}
    for path, conn in list(connections.items()):
        normalized_path = os.path.abspath(str(path))
        if keep and normalized_path == keep:
            retained[path] = conn
            continue
        try:
            conn.close()
        except Exception:
            pass
    if retained:
        _THREAD_LOCAL.connections = retained
    else:
        try:
            delattr(_THREAD_LOCAL, "connections")
        except AttributeError:
            pass


def _close_sqlite_connection(conn: sqlite3.Connection | None) -> None:
    if conn is None:
        return
    try:
        conn.close()
    except Exception:
        pass


class _SQLiteConnectionProxy:
    def __init__(self, conn: sqlite3.Connection, *, persistent: bool) -> None:
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "_persistent", persistent)
        object.__setattr__(self, "_closed", False)
        object.__setattr__(
            self,
            "_finalizer",
            None if persistent else weakref.finalize(self, _close_sqlite_connection, conn),
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_conn"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in {"_conn", "_persistent", "_closed", "_finalizer"}:
            object.__setattr__(self, name, value)
            return
        setattr(object.__getattribute__(self, "_conn"), name, value)

    def close(self) -> None:
        if object.__getattribute__(self, "_closed"):
            return
        object.__setattr__(self, "_closed", True)
        if object.__getattribute__(self, "_persistent"):
            return
        finalizer = object.__getattribute__(self, "_finalizer")
        if finalizer is not None and finalizer.alive:
            finalizer()

    def __enter__(self) -> "_SQLiteConnectionProxy":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def _unwrap_sqlite_connection(conn: sqlite3.Connection) -> sqlite3.Connection:
    raw_conn = getattr(conn, "_conn", conn)
    return raw_conn if isinstance(raw_conn, sqlite3.Connection) else conn


def _ensure_sqlite_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    existing = {
        str(row[1])
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def _daily_history_pk_columns(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("PRAGMA table_info(daily_history)").fetchall()
    pk_rows = [row for row in rows if int(row[5] or 0) > 0]
    return [
        str(row[1])
        for row in sorted(pk_rows, key=lambda row: int(row[5] or 0))
    ]


def _ensure_daily_history_adjustment_mode_schema(conn: sqlite3.Connection) -> None:
    _ensure_sqlite_column(conn, "daily_history", "adjustment_mode", "TEXT")
    if _daily_history_pk_columns(conn) == ["symbol", "bar_date", "adjustment_mode"]:
        return
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS daily_history_v2 (
            symbol TEXT NOT NULL,
            bar_date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            adj_close REAL,
            volume REAL,
            fetched_at TEXT NOT NULL,
            source TEXT,
            adjustment_mode TEXT NOT NULL DEFAULT 'adjusted',
            PRIMARY KEY (symbol, bar_date, adjustment_mode)
        );
        INSERT OR REPLACE INTO daily_history_v2 (
            symbol, bar_date, open, high, low, close, adj_close, volume, fetched_at, source, adjustment_mode
        )
        SELECT
            symbol, bar_date, open, high, low, close, adj_close, volume, fetched_at, source,
            COALESCE(NULLIF(adjustment_mode, ''), 'adjusted')
        FROM daily_history;
        DROP TABLE daily_history;
        ALTER TABLE daily_history_v2 RENAME TO daily_history;
        """
    )


def _sqlite_connection() -> sqlite3.Connection:
    path = _db_path()
    request_active = _REQUEST_MEMO.get() is not None
    connections = getattr(_THREAD_LOCAL, "connections", None)
    if request_active:
        if connections is None:
            connections = {}
            _THREAD_LOCAL.connections = connections
        else:
            for existing_path in list(connections.keys()):
                if os.path.abspath(str(existing_path)) != os.path.abspath(path):
                    _close_thread_local_connections(keep_path=path)
                    connections = getattr(_THREAD_LOCAL, "connections", {})
                    break
        conn = connections.get(path)
        if conn is None:
            _ensure_schema()
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            connections[path] = conn
        return _SQLiteConnectionProxy(conn, persistent=True)

    _ensure_schema()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return _SQLiteConnectionProxy(conn, persistent=False)


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
                    source TEXT,
                    adjustment_mode TEXT NOT NULL DEFAULT 'adjusted',
                    PRIMARY KEY (symbol, bar_date, adjustment_mode)
                );
                CREATE TABLE IF NOT EXISTS ticker_info_cache (
                    symbol TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    source TEXT
                );
                CREATE TABLE IF NOT EXISTS earnings_dates_cache (
                    symbol TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    source TEXT
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
            _ensure_sqlite_column(conn, "daily_history", "source", "TEXT")
            _ensure_daily_history_adjustment_mode_schema(conn)
            _ensure_sqlite_column(conn, "ticker_info_cache", "source", "TEXT")
            _ensure_sqlite_column(conn, "earnings_dates_cache", "source", "TEXT")
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
        _close_thread_local_connections()


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
    source = _market_data_source_label(frame, "")
    normalized = frame.copy()
    if not isinstance(normalized.index, pd.DatetimeIndex):
        normalized.index = pd.to_datetime(normalized.index)
    normalized = normalized.sort_index()
    normalized = normalized[~normalized.index.duplicated(keep="last")]
    keep = [col for col in ["Open", "High", "Low", "Close", "Adj Close", "Volume"] if col in normalized.columns]
    out = normalized[keep].copy() if keep else normalized.copy()
    if source:
        out.attrs["market_data_source"] = source
    return out


def _ticker_factory_or_default(ticker_factory: Optional[Callable[[str], Any]]) -> Callable[[str], Any]:
    if ticker_factory is not None:
        return ticker_factory
    if alpaca_provider_requested():
        return make_alpaca_ticker_factory(fallback_factory=None)
    return yf.Ticker


def _history_adjustment_mode(auto_adjust: bool) -> str:
    return "adjusted" if bool(auto_adjust) else "raw"


def _callable_accepts_explicit_keyword(func: Callable[..., Any], keyword: str) -> bool:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return True
    for parameter in signature.parameters.values():
        if parameter.name == keyword:
            return True
    return False


def _history_supports_auto_adjust(ticker: Any) -> bool:
    module = str(getattr(ticker.__class__, "__module__", ""))
    if module.startswith("yfinance") or module == "alpaca_market_data":
        return True
    return _callable_accepts_explicit_keyword(ticker.history, "auto_adjust")


def _fetch_history_direct(
    symbol: str,
    *,
    period: Optional[str] = None,
    start: Optional[Any] = None,
    end: Optional[Any] = None,
    interval: str = "1d",
    auto_adjust: Optional[bool] = None,
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
    supports_auto_adjust = auto_adjust is not None and _history_supports_auto_adjust(ticker)
    if supports_auto_adjust:
        kwargs["auto_adjust"] = bool(auto_adjust)
    raw = ticker.history(**kwargs)
    source = _market_data_source_label(raw, _market_data_source_label(ticker, "network"))
    normalized = _normalize_history_frame(raw)
    normalized.attrs["market_data_source"] = source
    if auto_adjust is not None:
        normalized.attrs["adjustment_mode"] = _history_adjustment_mode(bool(auto_adjust))
    required_source = _required_stock_cache_source()
    _require_data_source(source, required_source, symbol=symbol, payload="stock history")
    return normalized


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
        current.isoformat()
        for current in (start_date + timedelta(days=offset) for offset in range((end_date - start_date).days + 1))
        if is_us_equity_market_day(current)
    }


def _history_has_all_business_dates(frame: pd.DataFrame, start_date: date, end_date: date) -> bool:
    if frame.empty:
        return False
    expected = _business_dates(start_date, end_date)
    if not expected:
        return True
    actual = {pd.Timestamp(index).date().isoformat() for index in frame.index}
    return expected.issubset(actual)


def _expected_history_bounds(start_date: date, end_date: date) -> tuple[date, date] | None:
    expected = sorted(_business_dates(start_date, end_date))
    if not expected:
        return None
    return date.fromisoformat(expected[0]), date.fromisoformat(expected[-1])


def _load_daily_history_rows(
    symbol: str,
    start_date: date,
    end_date: date,
    *,
    adjustment_mode: str = "adjusted",
) -> pd.DataFrame:
    required_source = _required_stock_cache_source()
    with _sqlite_connection() as conn:
        raw_conn = _unwrap_sqlite_connection(conn)
        columns = {str(row[1]) for row in raw_conn.execute("PRAGMA table_info(daily_history)").fetchall()}
        source_expr = "source" if "source" in columns else "NULL AS source"
        if "adjustment_mode" in columns:
            adjustment_expr = "adjustment_mode"
            adjustment_clause = "AND adjustment_mode = ?"
            params = (symbol.upper(), start_date.isoformat(), end_date.isoformat(), adjustment_mode)
        else:
            if adjustment_mode != "adjusted":
                return pd.DataFrame()
            adjustment_expr = "'adjusted' AS adjustment_mode"
            adjustment_clause = ""
            params = (symbol.upper(), start_date.isoformat(), end_date.isoformat())
        rows = pd.read_sql_query(
            f"""
            SELECT bar_date, open, high, low, close, adj_close, volume, {source_expr}, {adjustment_expr}
            FROM daily_history
            WHERE symbol = ? AND bar_date >= ? AND bar_date <= ? {adjustment_clause}
            ORDER BY bar_date
            """,
            raw_conn,
            params=params,
        )
    if rows.empty:
        return pd.DataFrame()
    if required_source:
        rows = rows[
            rows["source"].map(lambda source: _source_satisfies_requirement(source, required_source))
        ].copy()
        if rows.empty:
            return pd.DataFrame()
    source = str(rows["source"].dropna().iloc[-1]) if "source" in rows and not rows["source"].dropna().empty else ""
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
    renamed = renamed.drop(columns=["source"], errors="ignore")
    frame = _normalize_history_frame(renamed)
    if source:
        frame.attrs["market_data_source"] = source
    return frame


def _store_daily_history(symbol: str, frame: pd.DataFrame, *, adjustment_mode: str) -> None:
    normalized = _normalize_history_frame(frame)
    if normalized.empty:
        return
    source = _market_data_source_label(frame, _market_data_source_label(normalized, "unknown"))
    required_source = _required_stock_cache_source()
    _require_data_source(source, required_source, symbol=symbol, payload="stock history cache write")
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
                source,
                adjustment_mode,
            )
        )
    conn = _sqlite_connection()
    conn.executemany(
        """
        INSERT INTO daily_history (
            symbol, bar_date, open, high, low, close, adj_close, volume, fetched_at, source, adjustment_mode
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol, bar_date, adjustment_mode) DO UPDATE SET
            open = excluded.open,
            high = excluded.high,
            low = excluded.low,
            close = excluded.close,
            adj_close = excluded.adj_close,
            volume = excluded.volume,
            fetched_at = excluded.fetched_at,
            source = excluded.source
        """,
        rows,
    )
    conn.commit()


def _as_float(value: Any) -> Optional[float]:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def _store_json_cache(
    table: str,
    symbol: str,
    payload: dict[str, Any],
    *,
    ttl: timedelta,
    source: str,
) -> None:
    required_source = _required_stock_cache_source()
    _require_data_source(source, required_source, symbol=symbol, payload=f"{table} cache write")
    conn = _sqlite_connection()
    conn.execute(
        f"""
        INSERT INTO {table} (symbol, payload_json, fetched_at, source)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            payload_json = excluded.payload_json,
            fetched_at = excluded.fetched_at,
            source = excluded.source
        """,
        (symbol.upper(), json.dumps(payload), _utcnow().isoformat(timespec="seconds"), str(source)),
    )
    conn.commit()
    _memory_cache_set(("sqlite_json_cache", table, symbol.upper(), required_source or ""), payload, ttl)


def _load_json_cache(
    table: str,
    symbol: str,
    ttl: timedelta,
    *,
    required_source: str | None = None,
) -> Optional[dict[str, Any]]:
    cache_key = ("sqlite_json_cache", table, symbol.upper(), required_source or "")
    memo_hit = _memory_cache_get(cache_key)
    if memo_hit is not None:
        return memo_hit
    conn = _sqlite_connection()
    row = conn.execute(
        f"SELECT payload_json, fetched_at, source FROM {table} WHERE symbol = ?",
        (symbol.upper(),),
    ).fetchone()
    if row is None:
        return None
    if not _source_satisfies_requirement(row[2], required_source):
        return None
    fetched_at = datetime.fromisoformat(str(row[1]))
    if _utcnow() - fetched_at > ttl:
        return None
    try:
        payload = json.loads(str(row[0]))
    except Exception:
        return None
    normalized = payload if isinstance(payload, dict) else None
    if normalized is not None:
        _memory_cache_set(cache_key, normalized, ttl)
    return normalized


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


def _market_data_source_label(value: Any, default: str = "network") -> str:
    for attr in ("market_data_source", "data_source", "source", "provider_source"):
        try:
            raw = getattr(value, attr)
        except Exception:
            raw = None
        if raw:
            return str(raw)
    try:
        attrs = getattr(value, "attrs", {}) or {}
        raw = attrs.get("market_data_source") or attrs.get("data_source")
        if raw:
            return str(raw)
    except Exception:
        pass
    return str(default)


def _required_options_cache_source() -> str | None:
    try:
        from alpaca_market_data import ALPACA_OPTIONS_SOURCE, alpaca_provider_requested

        if alpaca_provider_requested() and str(os.getenv("ALPACA_OPTIONS_FEED") or "opra").strip().lower() == "opra":
            return ALPACA_OPTIONS_SOURCE
    except Exception:
        return None
    return None


def _required_stock_cache_source() -> str | None:
    try:
        from alpaca_market_data import ALPACA_STOCK_SOURCE, alpaca_provider_requested

        if alpaca_provider_requested() and str(os.getenv("ALPACA_STOCK_FEED") or "sip").strip().lower() == "sip":
            return ALPACA_STOCK_SOURCE
    except Exception:
        return None
    return None


def _source_satisfies_requirement(source: Any, required: str | None) -> bool:
    if not required:
        return True
    source_text = str(source or "").strip().lower()
    required_text = str(required or "").strip().lower()
    if not source_text:
        return False
    if source_text == required_text:
        return True
    if required_text == "alpaca_opra":
        return "alpaca" in source_text and "opra" in source_text
    if required_text == "alpaca_sip":
        return "alpaca" in source_text and "sip" in source_text
    return required_text in source_text


def _record_satisfies_options_requirement(record: Optional[dict[str, Any]], required: str | None) -> bool:
    if not required or record is None:
        return True
    source = record.get("source")
    freshness = record.get("freshness")
    if not source and isinstance(freshness, dict):
        source = freshness.get("source")
    return _source_satisfies_requirement(source, required)


def _require_options_source(source: Any, required: str | None, *, symbol: str, payload: str) -> None:
    _require_data_source(source, required, symbol=symbol, payload=payload)


def _require_data_source(source: Any, required: str | None, *, symbol: str, payload: str) -> None:
    if _source_satisfies_requirement(source, required):
        return
    raise RuntimeError(
        f"{payload} fetch for {symbol.upper()} returned {source or 'unknown'} while {required} is required"
    )


def _store_option_expiries(symbol: str, expiries: list[str], *, source: str, error: Optional[Any] = None) -> None:
    payload = {"expiries": list(expiries)}
    conn = _sqlite_connection()
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
    _memory_cache_set(
        ("option_expiries_record", symbol.upper()),
        {
            "value": list(expiries),
            "freshness": _freshness_payload(
                status="fresh",
                fetched_at=_utcnow(),
                ttl=_OPTIONS_TTL,
                source=str(source),
                error=error,
            ),
            "status": "fresh",
            "source": str(source),
            "fetched_at": _utcnow().isoformat(timespec="seconds"),
            "error": _error_payload(error) if error is not None else None,
        },
        _OPTIONS_TTL,
    )


def _load_option_expiries_record(symbol: str) -> Optional[dict[str, Any]]:
    cache_key = ("option_expiries_record", symbol.upper())
    memo_hit = _memory_cache_get(cache_key)
    if isinstance(memo_hit, dict):
        return memo_hit
    conn = _sqlite_connection()
    row = conn.execute(
        """
        SELECT payload_json, fetched_at, source, error_json
        FROM option_expiries_cache
        WHERE symbol = ?
        """,
        (symbol.upper(),),
    ).fetchone()
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
    record = {
        "value": list(expiries),
        "freshness": freshness,
        "status": freshness["status"],
        "source": freshness["source"],
        "fetched_at": freshness["fetched_at"],
        "error": freshness["error_payload"],
    }
    _memory_cache_set(cache_key, record, _OPTIONS_TTL)
    return record


def _store_option_chain_snapshot(
    symbol: str,
    expiry: str,
    chain: SimpleNamespace,
    *,
    source: str,
    error: Optional[Any] = None,
) -> None:
    payload = {
        "calls": _serialize_frame(getattr(chain, "calls", pd.DataFrame())),
        "puts": _serialize_frame(getattr(chain, "puts", pd.DataFrame())),
    }
    conn = _sqlite_connection()
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
    _memory_cache_set(
        ("option_chain_record", symbol.upper(), str(expiry)),
        {
            "value": SimpleNamespace(
                calls=getattr(chain, "calls", pd.DataFrame()).copy(deep=True),
                puts=getattr(chain, "puts", pd.DataFrame()).copy(deep=True),
            ),
            "freshness": _freshness_payload(
                status="fresh",
                fetched_at=_utcnow(),
                ttl=_OPTION_CHAIN_TTL,
                source=str(source),
                error=error,
            ),
            "status": "fresh",
            "source": str(source),
            "fetched_at": _utcnow().isoformat(timespec="seconds"),
            "error": _error_payload(error) if error is not None else None,
        },
        _OPTION_CHAIN_TTL,
    )


def _load_option_chain_record(symbol: str, expiry: str) -> Optional[dict[str, Any]]:
    cache_key = ("option_chain_record", symbol.upper(), str(expiry))
    memo_hit = _memory_cache_get(cache_key)
    if isinstance(memo_hit, dict):
        return memo_hit
    conn = _sqlite_connection()
    row = conn.execute(
        """
        SELECT payload_json, fetched_at, source, error_json
        FROM option_chain_snapshot_cache
        WHERE symbol = ? AND expiry = ?
        """,
        (symbol.upper(), str(expiry)),
    ).fetchone()
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
    record = {
        "value": SimpleNamespace(
            calls=_deserialize_frame((payload or {}).get("calls")),
            puts=_deserialize_frame((payload or {}).get("puts")),
            source=str(row[2] or "sqlite"),
            market_data_source=str(row[2] or "sqlite"),
        ),
        "freshness": freshness,
        "status": freshness["status"],
        "source": freshness["source"],
        "fetched_at": freshness["fetched_at"],
        "error": freshness["error_payload"],
    }
    _memory_cache_set(cache_key, record, _OPTION_CHAIN_TTL)
    return record


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
    auto_adjust: bool = True,
    ticker_factory: Optional[Callable[[str], Any]] = None,
) -> pd.DataFrame:
    namespace = "history"
    adjustment_mode = _history_adjustment_mode(auto_adjust)
    key = ("history", symbol.upper(), period, str(start), str(end), interval, adjustment_mode)
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
                auto_adjust=auto_adjust,
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
            auto_adjust=auto_adjust,
            ticker_factory=ticker_factory,
        )
        _request_memo_set(key, direct)
        return direct

    start_date, end_date = normalized_window
    try:
        cached = _load_daily_history_rows(
            symbol,
            start_date,
            end_date,
            adjustment_mode=adjustment_mode,
        )
        first_cached: date | None = None
        last_cached: date | None = None
        if cached.empty:
            _record_stat(namespace, "persistent_misses")
            needs_full_refresh = True
        else:
            first_cached = cached.index.min().date()
            last_cached = cached.index.max().date()
            expected_bounds = _expected_history_bounds(start_date, end_date)
            has_all_business_dates = _history_has_all_business_dates(cached, start_date, end_date)
            needs_full_refresh = (
                not has_all_business_dates
                or (
                    expected_bounds is not None
                    and (first_cached > expected_bounds[0] or last_cached < expected_bounds[1])
                )
            )
            if needs_full_refresh:
                _record_stat(namespace, "persistent_partial_hits")
            else:
                _record_stat(namespace, "persistent_hits")
        recent_refresh_start = _recent_refresh_start()
        touches_recent = end_date >= recent_refresh_start
        stale_recent_tail_only = bool(
            not cached.empty
            and first_cached is not None
            and last_cached is not None
            and first_cached <= (start_date + timedelta(days=7))
            and touches_recent
            and last_cached >= (max(start_date, recent_refresh_start) - timedelta(days=1))
        )

        if needs_full_refresh:
            _record_stat(namespace, "full_refreshes")
            _record_stat(namespace, "network_fetches")
            try:
                fetched = _fetch_history_direct(
                    symbol,
                    start=start_date.isoformat(),
                    end=(end_date + timedelta(days=1)).isoformat(),
                    interval="1d",
                    auto_adjust=auto_adjust,
                    ticker_factory=ticker_factory,
                )
                if not fetched.empty:
                    _store_daily_history(symbol, fetched, adjustment_mode=adjustment_mode)
            except Exception:
                if stale_recent_tail_only:
                    _record_stat(namespace, "full_refresh_failures")
                    _record_stat(namespace, "stale_cache_returns")
                    _request_memo_set(key, cached)
                    return _normalize_history_frame(cached)
                raise
        elif touches_recent:
            _record_stat(namespace, "recent_refreshes")
            _record_stat(namespace, "network_fetches")
            refresh_start = max(start_date, recent_refresh_start)
            try:
                fetched = _fetch_history_direct(
                    symbol,
                    start=refresh_start.isoformat(),
                    end=(end_date + timedelta(days=1)).isoformat(),
                    interval="1d",
                    auto_adjust=auto_adjust,
                    ticker_factory=ticker_factory,
                )
                if not fetched.empty:
                    _store_daily_history(symbol, fetched, adjustment_mode=adjustment_mode)
            except Exception:
                if not cached.empty:
                    _record_stat(namespace, "full_refresh_failures")
                    _record_stat(namespace, "recent_refresh_failures")
                    _record_stat(namespace, "stale_cache_returns")
                    _request_memo_set(key, cached)
                    return _normalize_history_frame(cached)
                raise

        frame = _load_daily_history_rows(
            symbol,
            start_date,
            end_date,
            adjustment_mode=adjustment_mode,
        )
        if frame.empty:
            _record_stat(namespace, "fallback_fetches")
            _record_stat(namespace, "network_fetches")
            frame = _fetch_history_direct(
                symbol,
                start=start_date.isoformat(),
                end=(end_date + timedelta(days=1)).isoformat(),
                interval="1d",
                auto_adjust=auto_adjust,
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
            auto_adjust=auto_adjust,
            ticker_factory=ticker_factory,
        )
        _request_memo_set(key, direct)
        return direct


def _coerce_batch_download_frames(downloaded: Any, symbols: list[str]) -> dict[str, pd.DataFrame]:
    if downloaded is None:
        return {}
    frame = _normalize_history_frame(downloaded)
    if frame.empty:
        return {}

    normalized_symbols = [symbol.upper() for symbol in symbols]
    frames: dict[str, pd.DataFrame] = {}
    if isinstance(frame.columns, pd.MultiIndex):
        level_values = [
            {str(value).upper() for value in frame.columns.get_level_values(level)}
            for level in range(frame.columns.nlevels)
        ]
        symbol_level = next(
            (idx for idx, values in enumerate(level_values) if any(symbol in values for symbol in normalized_symbols)),
            None,
        )
        if symbol_level is not None:
            for symbol in normalized_symbols:
                if symbol not in level_values[symbol_level]:
                    continue
                try:
                    symbol_frame = frame.xs(symbol, axis=1, level=symbol_level, drop_level=True)
                except (KeyError, ValueError):
                    continue
                symbol_frame = _normalize_history_frame(symbol_frame)
                if not symbol_frame.empty:
                    frames[symbol] = symbol_frame
            return frames

    if len(normalized_symbols) == 1:
        frames[normalized_symbols[0]] = frame
    return frames


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
    adjustment_mode = _history_adjustment_mode(auto_adjust)
    key = ("download_history_batch", tuple(symbols), period, adjustment_mode)
    memo_hit = _request_memo_get(key)
    if memo_hit is not None:
        _record_stat(namespace, "request_memo_hits")
        return memo_hit
    frames: dict[str, pd.DataFrame] = {}
    missing_symbols: list[str] = []
    daily_cache_events: dict[str, str] = {}
    normalized_window = _normalize_daily_window(period=period)
    try:
        if normalized_window is None:
            missing_symbols = symbols[:]
        else:
            start_date, end_date = normalized_window
            for symbol in symbols:
                cached = _load_daily_history_rows(
                    symbol,
                    start_date,
                    end_date,
                    adjustment_mode=adjustment_mode,
                )
                if cached.empty:
                    daily_cache_events[symbol] = "persistent_misses"
                    missing_symbols.append(symbol)
                    continue
                first_cached = cached.index.min().date()
                last_cached = cached.index.max().date()
                expected_bounds = _expected_history_bounds(start_date, end_date)
                has_all_business_dates = _history_has_all_business_dates(cached, start_date, end_date)
                if (
                    not has_all_business_dates
                    or (
                        expected_bounds is not None
                        and (first_cached > expected_bounds[0] or last_cached < expected_bounds[1])
                    )
                ):
                    daily_cache_events[symbol] = "persistent_partial_hits"
                    missing_symbols.append(symbol)
                    continue
                frames[symbol] = cached
                if end_date >= _recent_refresh_start():
                    daily_cache_events[symbol] = "recent_refreshes"
                    missing_symbols.append(symbol)
                    continue
                daily_cache_events[symbol] = "persistent_hits"
                _record_stat("history", "persistent_hits")
    except Exception:
        _record_stat(namespace, "cache_failures")
        _record_stat("history", "cache_failures")
        frames = {}
        missing_symbols = symbols[:]

    if missing_symbols:
        fetched_symbols: set[str] = set()
        if ticker_factory is None and not alpaca_provider_requested():
            batch_fetch = download_fn or yf.download
            try:
                _record_stat(namespace, "batch_network_fetches")
                downloaded = batch_fetch(
                    " ".join(missing_symbols),
                    period=period,
                    auto_adjust=auto_adjust,
                    progress=False,
                    group_by="column",
                    threads=True,
                )
                batch_frames = _coerce_batch_download_frames(downloaded, missing_symbols)
                for symbol, frame in batch_frames.items():
                    if frame.empty:
                        continue
                    frames[symbol] = frame
                    fetched_symbols.add(symbol)
                    cache_event = daily_cache_events.get(symbol)
                    if cache_event:
                        _record_stat("history", cache_event)
                    _record_stat("history", "full_refreshes")
                    _record_stat("history", "network_fetches")
                    try:
                        _store_daily_history(symbol, frame, adjustment_mode=adjustment_mode)
                    except Exception:
                        _record_stat(namespace, "cache_write_failures")
            except Exception:
                _record_stat(namespace, "batch_network_failures")

        for symbol in missing_symbols:
            if symbol in fetched_symbols:
                continue
            frame = get_history(
                symbol,
                period=period,
                interval="1d",
                auto_adjust=auto_adjust,
                ticker_factory=ticker_factory,
            )
            if frame.empty:
                continue
            frames[symbol] = frame
            try:
                _store_daily_history(symbol, frame, adjustment_mode=adjustment_mode)
            except Exception:
                _record_stat(namespace, "cache_write_failures")

    if not frames:
        _record_stat(namespace, "network_fallbacks")
        result = pd.DataFrame()
        for symbol in symbols:
            frame = _fetch_history_direct(
                symbol,
                period=period,
                interval="1d",
                auto_adjust=auto_adjust,
                ticker_factory=ticker_factory,
            )
            if frame.empty:
                continue
            if symbol in frames:
                continue
            frames[symbol] = frame
            try:
                _store_daily_history(symbol, frame, adjustment_mode=adjustment_mode)
            except Exception:
                _record_stat(namespace, "cache_write_failures")
        if frames:
            combined = pd.concat(frames, axis=1).swaplevel(axis=1).sort_index(axis=1)
            _memory_cache_set(key, combined, _INTRADAY_HISTORY_TTL)
            _request_memo_set(key, combined)
            return combined
        _request_memo_set(key, result)
        return result

    _record_stat(namespace, "cache_hits")
    combined = pd.concat(frames, axis=1).swaplevel(axis=1).sort_index(axis=1)
    _memory_cache_set(key, combined, _INTRADAY_HISTORY_TTL)
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
        cached = _load_json_cache(
            "ticker_info_cache",
            symbol,
            _INFO_TTL,
            required_source=_required_stock_cache_source(),
        )
        if _ticker_info_payload_complete(cached):
            _record_stat(namespace, "persistent_hits")
            _request_memo_set(key, cached)
            return cached
        _record_stat(namespace, "persistent_misses")
    except Exception:
        _record_stat(namespace, "cache_failures")
        pass

    try:
        ticker = _ticker_factory_or_default(ticker_factory)(symbol)
        info = dict(getattr(ticker, "info", {}) or {})
        source = _market_data_source_label(info, _market_data_source_label(ticker, "network"))
        _require_data_source(source, _required_stock_cache_source(), symbol=symbol, payload="ticker info")
        _record_stat(namespace, "network_fetches")
        payload = _ticker_info_payload(info)
        try:
            _store_json_cache("ticker_info_cache", symbol, payload, ttl=_INFO_TTL, source=source)
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
        cached = _load_json_cache(
            "earnings_dates_cache",
            symbol,
            _EARNINGS_TTL,
            required_source=_required_stock_cache_source(),
        )
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
        source = _market_data_source_label(earnings, _market_data_source_label(ticker, "network"))
        _require_data_source(source, _required_stock_cache_source(), symbol=symbol, payload="earnings dates")
        _record_stat(namespace, "network_fetches")
        frame = earnings.copy() if isinstance(earnings, pd.DataFrame) else pd.DataFrame()
        payload = {
            "index": [pd.Timestamp(ts).isoformat() for ts in frame.index]
        } if not frame.empty else {"index": []}
        try:
            _store_json_cache("earnings_dates_cache", symbol, payload, ttl=_EARNINGS_TTL, source=source)
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
    required_source = _required_options_cache_source()
    memo_key = ("options", symbol_up, bool(include_metadata), required_source or "")
    memo_hit = _request_memo_get(memo_key)
    if memo_hit is not None:
        _record_stat(namespace, "request_memo_hits")
        return memo_hit

    def _fresh_record_to_value(record: dict[str, Any]) -> list[str]:
        value = record.get("value") if isinstance(record, dict) else []
        return list(value or [])

    if not include_metadata:
        cache_key = ("options", symbol_up, required_source or "")
        cached = _memory_cache_get(cache_key)
        if cached is not None:
            _record_stat(namespace, "memory_hits")
            value = list(cached or [])
            _request_memo_set(memo_key, value)
            return value
        _record_stat(namespace, "memory_misses")
        record: Optional[dict[str, Any]] = None
        try:
            record = _load_option_expiries_record(symbol_up)
            if (
                record is not None
                and record.get("status") == "fresh"
                and _record_satisfies_options_requirement(record, required_source)
            ):
                _record_stat(namespace, "persistent_hits")
                value = _fresh_record_to_value(record)
                _memory_cache_set(cache_key, value, _OPTIONS_TTL)
                _request_memo_set(memo_key, value)
                return value
            if record is not None:
                if record.get("status") == "fresh" and not _record_satisfies_options_requirement(record, required_source):
                    _record_stat(namespace, "persistent_provider_mismatches")
                else:
                    _record_stat(namespace, "persistent_stale_hits")
            else:
                _record_stat(namespace, "persistent_misses")
        except Exception:
            _record_stat(namespace, "cache_failures")
            record = None
        try:
            ticker = _ticker_factory_or_default(ticker_factory)(symbol)
            expiries = list(getattr(ticker, "options", []) or [])
            source = _market_data_source_label(ticker, "network")
            _require_options_source(source, required_source, symbol=symbol_up, payload="option expiries")
            _record_stat(namespace, "network_fetches")
            try:
                _store_option_expiries(symbol_up, expiries, source=source)
            except Exception:
                _record_stat(namespace, "cache_write_failures")
            _memory_cache_set(cache_key, expiries, _OPTIONS_TTL)
            _request_memo_set(memo_key, expiries)
            return expiries
        except Exception as exc:
            _record_stat(namespace, "fallbacks")
            if record is not None:
                fallback_value = _fresh_record_to_value(record)
                if fallback_value and _record_satisfies_options_requirement(record, required_source):
                    _request_memo_set(memo_key, fallback_value)
                    return fallback_value
            raise RuntimeError(f"option expiries fetch failed for {symbol_up}: {exc}") from exc

    record: Optional[dict[str, Any]] = None
    try:
        record = _load_option_expiries_record(symbol_up)
        if record is not None:
            status = str(record.get("status") or "error")
            source_ok = _record_satisfies_options_requirement(record, required_source)
            if status == "fresh" and source_ok:
                _record_stat(namespace, "persistent_hits")
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
            if status == "fresh" and not source_ok:
                _record_stat(namespace, "persistent_provider_mismatches")
            if status == "stale":
                _record_stat(namespace, "persistent_stale_hits")
            else:
                _record_stat(namespace, "persistent_misses")
        _record_stat(namespace, "persistent_misses")
    except Exception:
        _record_stat(namespace, "cache_failures")
        record = None

    try:
        ticker = _ticker_factory_or_default(ticker_factory)(symbol)
        expiries = list(getattr(ticker, "options", []) or [])
        source = _market_data_source_label(ticker, "network")
        _require_options_source(source, required_source, symbol=symbol_up, payload="option expiries")
        _record_stat(namespace, "network_fetches")
        try:
            _store_option_expiries(symbol_up, expiries, source=source)
        except Exception:
            _record_stat(namespace, "cache_write_failures")
        envelope = _snapshot_envelope(
            expiries,
            _freshness_payload(
                status="fresh",
                fetched_at=_utcnow(),
                ttl=_OPTIONS_TTL,
                source=source,
            ),
        )
        _request_memo_set(memo_key, envelope)
        return envelope
    except Exception as exc:
        _record_stat(namespace, "fallbacks")
        if record is not None and _record_satisfies_options_requirement(record, required_source):
            envelope = _snapshot_envelope(
                record.get("value") or [],
                record.get("freshness") or _freshness_payload(
                    status=str(record.get("status") or "error"),
                    fetched_at=None,
                    ttl=_OPTIONS_TTL,
                    source=str(record.get("source") or "sqlite"),
                    error=exc,
                    stale_reason="network_refresh_failed",
                ),
            )
            _request_memo_set(memo_key, envelope)
            return envelope
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
    required_source = _required_options_cache_source()
    memo_key = ("option_chain", symbol_up, str(expiry), bool(include_metadata), required_source or "")
    memo_hit = _request_memo_get(memo_key)
    if memo_hit is not None:
        _record_stat(namespace, "request_memo_hits")
        return memo_hit

    def _network_fetch() -> SimpleNamespace:
        ticker = _ticker_factory_or_default(ticker_factory)(symbol)
        raw_chain = ticker.option_chain(expiry)
        source = _market_data_source_label(raw_chain, _market_data_source_label(ticker, "network"))
        return SimpleNamespace(
            calls=getattr(raw_chain, "calls", pd.DataFrame()).copy(deep=True),
            puts=getattr(raw_chain, "puts", pd.DataFrame()).copy(deep=True),
            source=source,
            market_data_source=source,
        )

    if not include_metadata:
        cache_key = ("option_chain", symbol_up, str(expiry), required_source or "")
        cached = _memory_cache_get(cache_key)
        if cached is not None:
            _record_stat(namespace, "memory_hits")
            _request_memo_set(memo_key, cached)
            return cached
        _record_stat(namespace, "memory_misses")
        record: Optional[dict[str, Any]] = None
        try:
            record = _load_option_chain_record(symbol_up, expiry)
            if (
                record is not None
                and record.get("status") == "fresh"
                and _record_satisfies_options_requirement(record, required_source)
            ):
                _record_stat(namespace, "persistent_hits")
                value = record["value"]
                _memory_cache_set(cache_key, value, _OPTION_CHAIN_TTL)
                _request_memo_set(memo_key, value)
                return value
            if record is not None:
                if record.get("status") == "fresh" and not _record_satisfies_options_requirement(record, required_source):
                    _record_stat(namespace, "persistent_provider_mismatches")
                else:
                    _record_stat(namespace, "persistent_stale_hits")
            else:
                _record_stat(namespace, "persistent_misses")
        except Exception:
            _record_stat(namespace, "cache_failures")
            record = None
        try:
            value = _network_fetch()
            _require_options_source(
                _market_data_source_label(value, "network"),
                required_source,
                symbol=symbol_up,
                payload="option chain",
            )
            _record_stat(namespace, "network_fetches")
            try:
                _store_option_chain_snapshot(
                    symbol_up,
                    expiry,
                    value,
                    source=_market_data_source_label(value, "network"),
                )
            except Exception:
                _record_stat(namespace, "cache_write_failures")
            _memory_cache_set(cache_key, value, _OPTION_CHAIN_TTL)
            _request_memo_set(memo_key, value)
            return value
        except Exception as exc:
            _record_stat(namespace, "fallbacks")
            if record is not None and _record_satisfies_options_requirement(record, required_source):
                fallback_value = record.get("value")
                if fallback_value is not None and (
                    not getattr(fallback_value.calls, "empty", True)
                    or not getattr(fallback_value.puts, "empty", True)
                ):
                    _request_memo_set(memo_key, fallback_value)
                    return fallback_value
            raise RuntimeError(f"option chain fetch failed for {symbol_up} {expiry}: {exc}") from exc

    record: Optional[dict[str, Any]] = None
    try:
        record = _load_option_chain_record(symbol_up, expiry)
        if record is not None:
            status = str(record.get("status") or "error")
            source_ok = _record_satisfies_options_requirement(record, required_source)
            if status == "fresh" and source_ok:
                _record_stat(namespace, "persistent_hits")
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
            if status == "fresh" and not source_ok:
                _record_stat(namespace, "persistent_provider_mismatches")
            elif status == "stale":
                _record_stat(namespace, "persistent_stale_hits")
            else:
                _record_stat(namespace, "persistent_misses")
        _record_stat(namespace, "persistent_misses")
    except Exception:
        _record_stat(namespace, "cache_failures")
        record = None

    try:
        value = _network_fetch()
        _require_options_source(
            _market_data_source_label(value, "network"),
            required_source,
            symbol=symbol_up,
            payload="option chain",
        )
        _record_stat(namespace, "network_fetches")
        try:
            _store_option_chain_snapshot(
                symbol_up,
                expiry,
                value,
                source=_market_data_source_label(value, "network"),
            )
        except Exception:
            _record_stat(namespace, "cache_write_failures")
        envelope = _snapshot_envelope(
            value,
            _freshness_payload(
                status="fresh",
                fetched_at=_utcnow(),
                ttl=_OPTION_CHAIN_TTL,
                source=_market_data_source_label(value, "network"),
            ),
        )
        _request_memo_set(memo_key, envelope)
        return envelope
    except Exception as exc:
        _record_stat(namespace, "fallbacks")
        if record is not None and _record_satisfies_options_requirement(record, required_source):
            envelope = _snapshot_envelope(
                record["value"],
                record.get("freshness") or _freshness_payload(
                    status=str(record.get("status") or "error"),
                    fetched_at=None,
                    ttl=_OPTION_CHAIN_TTL,
                    source=str(record.get("source") or "sqlite"),
                    error=exc,
                    stale_reason="network_refresh_failed",
                ),
            )
            _request_memo_set(memo_key, envelope)
            return envelope
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
