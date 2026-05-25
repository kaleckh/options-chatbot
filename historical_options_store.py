from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow.parquet as pq


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_HISTORICAL_OPTIONS_DB_PATH = ROOT_DIR / "data" / "options-validation" / "options_history.db"
EASTERN_TZ = ZoneInfo("America/New_York")
ENTRY_QUOTE_MINUTE_ET = 10 * 60 + 10
ENTRY_QUOTE_WINDOW_MINUTES = 15
DAILY_QUOTE_MINUTE_ET = 15 * 60 + 55
INTRADAY_SNAPSHOT_KIND = "intraday"
DAILY_SNAPSHOT_KIND = "daily_eod"
TRUSTED_DATA_TRUST = "trusted"
FIXTURE_DATA_TRUST = "fixture"
RESEARCH_DATA_TRUST = "research"
SQLITE_TIMEOUT_SECONDS = 30.0
SQLITE_BUSY_TIMEOUT_MS = 30_000
QUOTE_INSERT_CHUNK_SIZE = 5_000
QUOTE_LOOKUP_CACHE_MAX_ENTRIES = 100_000

_QUOTE_CACHE_MISS = object()

_OPTION_QUOTE_INSERT_SQL = """
    INSERT OR IGNORE INTO option_quote_snapshots (
        as_of_utc,
        quote_date_et,
        quote_minute_et,
        snapshot_kind,
        underlying,
        contract_symbol,
        expiry,
        option_type,
        strike,
        bid,
        ask,
        last,
        iv,
        underlying_price,
        volume,
        open_interest,
        source_batch_id
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _sqlite_connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=SQLITE_TIMEOUT_SECONDS)
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _db_path() -> Path:
    override = os.getenv("HISTORICAL_OPTIONS_DB_PATH")
    return Path(override) if override else DEFAULT_HISTORICAL_OPTIONS_DB_PATH


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, column_sql: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    existing = {str(row[1]) for row in rows}
    if column_name not in existing:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")


def _normalize_data_trust(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw == FIXTURE_DATA_TRUST:
        return FIXTURE_DATA_TRUST
    if raw == RESEARCH_DATA_TRUST:
        return RESEARCH_DATA_TRUST
    return TRUSTED_DATA_TRUST


def _infer_data_trust(source_label: Any, input_path: Any, dataset_kind: Any) -> str:
    values = [
        str(source_label or "").strip().lower(),
        str(dataset_kind or "").strip().lower(),
    ]
    fixture_tokens = ("fixture", "sample", "demo")
    if any(token in value for value in values for token in fixture_tokens):
        return FIXTURE_DATA_TRUST
    research_tokens = (
        "research",
        "external",
        "free",
        "marketdata_free",
        "thetadata_free",
        "theta_data_free",
        "philippdubach",
        "onclickmedia",
        "yahoo",
        "yfinance",
    )
    if any(token in value for value in values for token in research_tokens):
        return RESEARCH_DATA_TRUST
    return TRUSTED_DATA_TRUST


def _dataset_kind_for_snapshot_kind(snapshot_kind: str | None) -> str | None:
    normalized = str(snapshot_kind or "").strip().lower()
    if not normalized:
        return None
    if normalized == str(DAILY_SNAPSHOT_KIND).lower():
        return "daily_parquet"
    if normalized == str(INTRADAY_SNAPSHOT_KIND).lower():
        return "intraday_csv"
    return None


def _index_columns(conn: sqlite3.Connection, index_name: str) -> list[str]:
    rows = conn.execute(f"PRAGMA index_info('{index_name}')").fetchall()
    return [str(row[2]) for row in rows]


def _has_snapshot_kind_unique_index(conn: sqlite3.Connection) -> bool:
    rows = conn.execute("PRAGMA index_list(option_quote_snapshots)").fetchall()
    for row in rows:
        index_name = str(row[1])
        is_unique = int(row[2]) == 1
        if not is_unique:
            continue
        if _index_columns(conn, index_name) == ["as_of_utc", "contract_symbol", "snapshot_kind"]:
            return True
    return False


def _rebuild_option_quote_snapshots_table(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        ALTER TABLE option_quote_snapshots RENAME TO option_quote_snapshots_legacy;

        CREATE TABLE option_quote_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            as_of_utc TEXT NOT NULL,
            quote_date_et TEXT NOT NULL,
            quote_minute_et INTEGER NOT NULL,
            snapshot_kind TEXT NOT NULL DEFAULT 'intraday',
            underlying TEXT NOT NULL,
            contract_symbol TEXT NOT NULL,
            expiry TEXT NOT NULL,
            option_type TEXT NOT NULL,
            strike REAL NOT NULL,
            bid REAL,
            ask REAL,
            last REAL,
            iv REAL,
            underlying_price REAL,
            volume INTEGER,
            open_interest INTEGER,
            source_batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE RESTRICT,
            UNIQUE(as_of_utc, contract_symbol, snapshot_kind)
        );

        INSERT OR IGNORE INTO option_quote_snapshots (
            id,
            as_of_utc,
            quote_date_et,
            quote_minute_et,
            snapshot_kind,
            underlying,
            contract_symbol,
            expiry,
            option_type,
            strike,
            bid,
            ask,
            last,
            iv,
            underlying_price,
            volume,
            open_interest,
            source_batch_id
        )
        SELECT
            id,
            as_of_utc,
            quote_date_et,
            quote_minute_et,
            COALESCE(snapshot_kind, 'intraday'),
            underlying,
            contract_symbol,
            expiry,
            option_type,
            strike,
            bid,
            ask,
            last,
            iv,
            underlying_price,
            volume,
            open_interest,
            source_batch_id
        FROM option_quote_snapshots_legacy;

        DROP TABLE option_quote_snapshots_legacy;

        CREATE INDEX IF NOT EXISTS idx_option_quotes_underlying_date
            ON option_quote_snapshots (underlying, snapshot_kind, quote_date_et, option_type, quote_minute_et);
        CREATE INDEX IF NOT EXISTS idx_option_quotes_contract_date
            ON option_quote_snapshots (contract_symbol, snapshot_kind, quote_date_et, quote_minute_et DESC);
        CREATE INDEX IF NOT EXISTS idx_option_quotes_tuple_date
            ON option_quote_snapshots (underlying, snapshot_kind, expiry, option_type, strike, quote_date_et, quote_minute_et DESC);
        CREATE INDEX IF NOT EXISTS idx_option_quotes_snapshot_underlying
            ON option_quote_snapshots (snapshot_kind, underlying);
        CREATE INDEX IF NOT EXISTS idx_option_quotes_snapshot_asof
            ON option_quote_snapshots (snapshot_kind, as_of_utc);
        CREATE INDEX IF NOT EXISTS idx_option_quotes_snapshot_quote_date
            ON option_quote_snapshots (snapshot_kind, quote_date_et, underlying);
        """
    )


def _backfill_import_batch_trust(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT id, source_label, input_path, dataset_kind, data_trust
        FROM import_batches
        """
    ).fetchall()
    for row in rows:
        inferred = _infer_data_trust(row[1], row[2], row[3])
        current = _normalize_data_trust(row[4])
        if current != inferred:
            conn.execute(
                "UPDATE import_batches SET data_trust = ? WHERE id = ?",
                (inferred, int(row[0])),
            )


def _normalize_contract_symbol(value: Any) -> str:
    raw = str(value or "").strip().upper()
    if not raw:
        raise ValueError("contract_symbol is required")
    return raw


def _normalize_underlying(value: Any) -> str:
    raw = str(value or "").strip().upper()
    if not raw:
        raise ValueError("underlying is required")
    return raw


def _normalize_option_type(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"c", "call"}:
        return "call"
    if raw in {"p", "put"}:
        return "put"
    raise ValueError("option_type must be call/c or put/p")


def _normalize_source_labels(source_labels: Sequence[str] | None) -> list[str]:
    return [
        str(source_label).strip()
        for source_label in (source_labels or [])
        if str(source_label).strip()
    ]


def _parse_date(value: Any, field_name: str) -> date:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"{field_name} is required")
    return date.fromisoformat(raw[:10])


def _parse_float(value: Any, *, field_name: str, required: bool = False) -> Optional[float]:
    if value is None or str(value).strip() == "":
        if required:
            raise ValueError(f"{field_name} is required")
        return None
    parsed = float(value)
    return parsed


def _parse_int(value: Any, *, field_name: str) -> Optional[int]:
    if value is None or str(value).strip() == "":
        return None
    return int(float(value))


def _parse_as_of_utc(value: Any) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("as_of_utc is required")
    normalized = raw.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=EASTERN_TZ)
    return parsed.astimezone(UTC)


def _build_as_of_utc_for_quote_date(trade_date: date, minute_et: int) -> datetime:
    hour = int(minute_et // 60)
    minute = int(minute_et % 60)
    local_stamp = datetime.combine(trade_date, time(hour=hour, minute=minute), tzinfo=EASTERN_TZ)
    return local_stamp.astimezone(UTC)


def _quote_date_et(as_of_utc: datetime) -> tuple[str, int]:
    as_of_et = as_of_utc.astimezone(EASTERN_TZ)
    minute = as_of_et.hour * 60 + as_of_et.minute
    return as_of_et.date().isoformat(), minute


def _quote_price_with_mode(row: dict[str, Any], *, allow_last_price: bool) -> tuple[Optional[float], Optional[str]]:
    bid = row.get("bid")
    ask = row.get("ask")
    last = row.get("last")
    if bid is not None and ask is not None and bid > 0 and ask > 0 and ask >= bid:
        return round((bid + ask) / 2.0, 4), "mid"
    if allow_last_price and last is not None and last > 0:
        return round(last, 4), "last"
    return None, None


def _valid_quote_sql_clause(alias: str = "q", *, allow_last_price: bool = True) -> str:
    prefix = f"{alias}." if alias else ""
    bid_ask_clause = (
        f"({prefix}bid IS NOT NULL AND {prefix}ask IS NOT NULL "
        f"AND {prefix}bid > 0 AND {prefix}ask > 0 AND {prefix}ask >= {prefix}bid)"
    )
    if allow_last_price:
        return f"({bid_ask_clause} OR ({prefix}last IS NOT NULL AND {prefix}last > 0))"
    return bid_ask_clause


def _quote_insert_values(normalized: dict[str, Any], batch_id: int) -> tuple[Any, ...]:
    return (
        normalized["as_of_utc"],
        normalized["quote_date_et"],
        normalized["quote_minute_et"],
        normalized["snapshot_kind"],
        normalized["underlying"],
        normalized["contract_symbol"],
        normalized["expiry"],
        normalized["option_type"],
        normalized["strike"],
        normalized["bid"],
        normalized["ask"],
        normalized["last"],
        normalized["iv"],
        normalized["underlying_price"],
        normalized["volume"],
        normalized["open_interest"],
        batch_id,
    )


def _insert_option_quote_batch(
    conn: sqlite3.Connection,
    cursor: sqlite3.Cursor,
    values: list[tuple[Any, ...]],
) -> tuple[int, int]:
    if not values:
        return 0, 0
    before_changes = int(conn.total_changes)
    cursor.executemany(_OPTION_QUOTE_INSERT_SQL, values)
    inserted = max(int(conn.total_changes) - before_changes, 0)
    duplicate = max(len(values) - inserted, 0)
    values.clear()
    return inserted, duplicate


@dataclass(frozen=True)
class HistoricalQuote:
    as_of_utc: str
    quote_date_et: str
    quote_minute_et: int
    underlying: str
    contract_symbol: str
    expiry: str
    option_type: str
    strike: float
    price: float
    price_basis: str
    underlying_price: Optional[float]
    bid: Optional[float]
    ask: Optional[float]
    last: Optional[float]
    iv: Optional[float]
    volume: Optional[int]
    open_interest: Optional[int]
    snapshot_kind: str


def init_schema(db_path: str | Path | None = None) -> Path:
    path = Path(db_path) if db_path else _db_path()
    _ensure_parent_dir(path)
    with closing(_sqlite_connect(path)) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS import_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_label TEXT NOT NULL,
                dataset_kind TEXT NOT NULL DEFAULT 'intraday_csv',
                data_trust TEXT NOT NULL DEFAULT 'trusted',
                input_path TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                imported_at_utc TEXT NOT NULL,
                total_rows INTEGER NOT NULL,
                imported_rows INTEGER NOT NULL,
                duplicate_rows INTEGER NOT NULL,
                rejected_rows INTEGER NOT NULL,
                warnings_json TEXT NOT NULL DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS option_quote_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                as_of_utc TEXT NOT NULL,
                quote_date_et TEXT NOT NULL,
                quote_minute_et INTEGER NOT NULL,
                snapshot_kind TEXT NOT NULL DEFAULT 'intraday',
                underlying TEXT NOT NULL,
                contract_symbol TEXT NOT NULL,
                expiry TEXT NOT NULL,
                option_type TEXT NOT NULL,
                strike REAL NOT NULL,
                bid REAL,
                ask REAL,
                last REAL,
                iv REAL,
                underlying_price REAL,
                volume INTEGER,
                open_interest INTEGER,
                source_batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE RESTRICT,
                UNIQUE(as_of_utc, contract_symbol, snapshot_kind)
            );

            CREATE INDEX IF NOT EXISTS idx_option_quotes_underlying_date
                ON option_quote_snapshots (underlying, snapshot_kind, quote_date_et, option_type, quote_minute_et);
            CREATE INDEX IF NOT EXISTS idx_option_quotes_contract_date
                ON option_quote_snapshots (contract_symbol, snapshot_kind, quote_date_et, quote_minute_et DESC);
            CREATE INDEX IF NOT EXISTS idx_option_quotes_tuple_date
                ON option_quote_snapshots (underlying, snapshot_kind, expiry, option_type, strike, quote_date_et, quote_minute_et DESC);
            CREATE INDEX IF NOT EXISTS idx_option_quotes_snapshot_underlying
                ON option_quote_snapshots (snapshot_kind, underlying);
            CREATE INDEX IF NOT EXISTS idx_option_quotes_snapshot_asof
                ON option_quote_snapshots (snapshot_kind, as_of_utc);
            CREATE INDEX IF NOT EXISTS idx_option_quotes_snapshot_quote_date
                ON option_quote_snapshots (snapshot_kind, quote_date_et, underlying);
            """
        )
        _ensure_column(conn, "import_batches", "dataset_kind", "TEXT NOT NULL DEFAULT 'intraday_csv'")
        _ensure_column(conn, "import_batches", "data_trust", "TEXT NOT NULL DEFAULT 'trusted'")
        _ensure_column(conn, "option_quote_snapshots", "snapshot_kind", "TEXT NOT NULL DEFAULT 'intraday'")
        if not _has_snapshot_kind_unique_index(conn):
            _rebuild_option_quote_snapshots_table(conn)
        _backfill_import_batch_trust(conn)
        conn.commit()
    return path


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_csv_row(row: dict[str, Any], *, snapshot_kind: str = INTRADAY_SNAPSHOT_KIND) -> dict[str, Any]:
    as_of_utc = _parse_as_of_utc(row.get("as_of_utc") or row.get("as_of"))
    quote_date_et, quote_minute_et = _quote_date_et(as_of_utc)
    normalized = {
        "as_of_utc": as_of_utc.isoformat().replace("+00:00", "Z"),
        "quote_date_et": quote_date_et,
        "quote_minute_et": quote_minute_et,
        "snapshot_kind": str(snapshot_kind or INTRADAY_SNAPSHOT_KIND),
        "underlying": _normalize_underlying(row.get("underlying")),
        "contract_symbol": _normalize_contract_symbol(row.get("contract_symbol")),
        "expiry": _parse_date(row.get("expiry"), "expiry").isoformat(),
        "option_type": _normalize_option_type(row.get("option_type")),
        "strike": _parse_float(row.get("strike"), field_name="strike", required=True),
        "bid": _parse_float(row.get("bid"), field_name="bid"),
        "ask": _parse_float(row.get("ask"), field_name="ask"),
        "last": _parse_float(row.get("last"), field_name="last"),
        "iv": _parse_float(row.get("iv"), field_name="iv"),
        "underlying_price": _parse_float(row.get("underlying_price"), field_name="underlying_price"),
        "volume": _parse_int(row.get("volume"), field_name="volume"),
        "open_interest": _parse_int(row.get("open_interest"), field_name="open_interest"),
    }
    return normalized


def import_historical_option_snapshots(
    input_path: str | Path,
    source_label: str,
    *,
    dataset_kind: str = "intraday_csv",
    snapshot_kind: str = INTRADAY_SNAPSHOT_KIND,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    csv_path = Path(input_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"No snapshot CSV found at {csv_path}")

    path = init_schema(db_path)
    file_hash = _file_sha256(csv_path)
    imported_at_utc = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    data_trust = _infer_data_trust(source_label, csv_path, dataset_kind)
    total_rows = 0
    imported_rows = 0
    duplicate_rows = 0
    rejected_rows = 0
    warnings: list[str] = []

    with closing(_sqlite_connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO import_batches (
                source_label,
                dataset_kind,
                data_trust,
                input_path,
                file_hash,
                imported_at_utc,
                total_rows,
                imported_rows,
                duplicate_rows,
                rejected_rows,
                warnings_json
            ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, 0, '[]')
            """,
            (
                str(source_label or "").strip() or "manual_import",
                str(dataset_kind or "intraday_csv").strip() or "intraday_csv",
                data_trust,
                str(csv_path),
                file_hash,
                imported_at_utc,
            ),
        )
        batch_id = int(cursor.lastrowid)
        pending_values: list[tuple[Any, ...]] = []

        with csv_path.open("r", encoding="utf8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row_index, row in enumerate(reader, start=2):
                total_rows += 1
                try:
                    normalized = _normalize_csv_row(row, snapshot_kind=snapshot_kind)
                except Exception as exc:
                    rejected_rows += 1
                    if len(warnings) < 20:
                        warnings.append(f"Row {row_index}: {exc}")
                    continue

                pending_values.append(_quote_insert_values(normalized, batch_id))
                if len(pending_values) >= QUOTE_INSERT_CHUNK_SIZE:
                    inserted, duplicate = _insert_option_quote_batch(conn, cursor, pending_values)
                    imported_rows += inserted
                    duplicate_rows += duplicate

        inserted, duplicate = _insert_option_quote_batch(conn, cursor, pending_values)
        imported_rows += inserted
        duplicate_rows += duplicate

        cursor.execute(
            """
            UPDATE import_batches
            SET total_rows = ?,
                imported_rows = ?,
                duplicate_rows = ?,
                rejected_rows = ?,
                warnings_json = ?
            WHERE id = ?
            """,
            (
                total_rows,
                imported_rows,
                duplicate_rows,
                rejected_rows,
                json.dumps(warnings),
                batch_id,
            ),
        )
        conn.commit()

    return {
        "db_path": str(path),
        "batch_id": batch_id,
        "source_label": source_label,
        "input_path": str(csv_path),
        "file_hash": file_hash,
        "imported_at_utc": imported_at_utc,
        "dataset_kind": dataset_kind,
        "data_trust": data_trust,
        "snapshot_kind": snapshot_kind,
        "total_rows": total_rows,
        "imported_rows": imported_rows,
        "duplicate_rows": duplicate_rows,
        "rejected_rows": rejected_rows,
        "warnings": warnings,
    }


def _maybe_read_underlying_prices(
    input_path: str | Path | None,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, float]:
    if not input_path:
        return {}
    frame = pd.read_parquet(input_path)
    if frame.empty:
        return {}

    date_column = None
    for candidate in ("date", "Date", "timestamp"):
        if candidate in frame.columns:
            date_column = candidate
            break
    close_column = None
    for candidate in ("close", "Close", "adj_close", "adjusted_close"):
        if candidate in frame.columns:
            close_column = candidate
            break
    if date_column is None or close_column is None:
        return {}

    frame = frame[[date_column, close_column]].copy()
    frame["quote_date_et"] = pd.to_datetime(frame[date_column], utc=False, errors="coerce").dt.date.astype(str)
    frame["underlying_price"] = pd.to_numeric(frame[close_column], errors="coerce")
    frame = frame.dropna(subset=["quote_date_et", "underlying_price"])
    if date_from is not None:
        frame = frame.loc[frame["quote_date_et"] >= date_from.isoformat()]
    if date_to is not None:
        frame = frame.loc[frame["quote_date_et"] <= date_to.isoformat()]
    if frame.empty:
        return {}
    return {
        str(row["quote_date_et"]): float(row["underlying_price"])
        for _, row in frame.iterrows()
    }


def _iter_daily_parquet_records(
    parquet_path: Path,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    batch_size: int = 50_000,
) -> Iterable[dict[str, Any]]:
    parquet_file = pq.ParquetFile(parquet_path)
    preferred_columns = [
        "contract_id",
        "contract_symbol",
        "contractSymbol",
        "symbol",
        "underlying",
        "expiration",
        "expiry",
        "strike",
        "type",
        "option_type",
        "date",
        "bid",
        "ask",
        "last",
        "mark",
        "volume",
        "open_interest",
        "implied_volatility",
        "iv",
    ]
    columns = [column for column in preferred_columns if column in parquet_file.schema.names]
    for batch in parquet_file.iter_batches(batch_size=batch_size, columns=columns):
        frame = batch.to_pandas()
        if frame.empty:
            continue
        if "date" not in frame.columns:
            if "Date" in frame.columns:
                frame["date"] = frame["Date"]
            elif "timestamp" in frame.columns:
                frame["date"] = frame["timestamp"]
        if "date" not in frame.columns:
            for row in frame.to_dict(orient="records"):
                yield row
            continue
        parsed_dates = pd.to_datetime(frame["date"], utc=False, errors="coerce").dt.date
        frame = frame.assign(_parsed_date=parsed_dates)
        frame = frame.dropna(subset=["_parsed_date"])
        if date_from is not None:
            frame = frame.loc[frame["_parsed_date"] >= date_from]
        if date_to is not None:
            frame = frame.loc[frame["_parsed_date"] <= date_to]
        if frame.empty:
            continue
        frame = frame.drop(columns=["_parsed_date"])
        for row in frame.to_dict(orient="records"):
            yield row


def import_daily_option_parquet(
    input_path: str | Path,
    source_label: str,
    *,
    underlying: str | None = None,
    underlying_input: str | Path | None = None,
    dataset_kind: str = "daily_parquet",
    date_from: date | None = None,
    date_to: date | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    parquet_path = Path(input_path)
    if not parquet_path.exists():
        raise FileNotFoundError(f"No daily options parquet found at {parquet_path}")

    path = init_schema(db_path)
    file_hash = _file_sha256(parquet_path)
    imported_at_utc = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    data_trust = _infer_data_trust(source_label, parquet_path, dataset_kind)
    total_rows = 0
    imported_rows = 0
    duplicate_rows = 0
    rejected_rows = 0
    warnings: list[str] = []

    underlying_prices = _maybe_read_underlying_prices(
        underlying_input,
        date_from=date_from,
        date_to=date_to,
    )

    with closing(_sqlite_connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO import_batches (
                source_label,
                dataset_kind,
                data_trust,
                input_path,
                file_hash,
                imported_at_utc,
                total_rows,
                imported_rows,
                duplicate_rows,
                rejected_rows,
                warnings_json
            ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, 0, '[]')
            """,
            (
                str(source_label or "").strip() or "daily_parquet_import",
                str(dataset_kind or "daily_parquet").strip() or "daily_parquet",
                data_trust,
                str(parquet_path),
                file_hash,
                imported_at_utc,
            ),
        )
        batch_id = int(cursor.lastrowid)

        row_index = 1
        saw_rows = False
        pending_values: list[tuple[Any, ...]] = []
        for raw_row in _iter_daily_parquet_records(
            parquet_path,
            date_from=date_from,
            date_to=date_to,
        ):
            row_index += 1
            saw_rows = True
            total_rows += 1
            try:
                row_underlying = _normalize_underlying(raw_row.get("symbol") or raw_row.get("underlying") or underlying)
                trade_date = _parse_date(raw_row.get("date"), "date")
                expiry = _parse_date(raw_row.get("expiration") or raw_row.get("expiry"), "expiration")
                option_type = _normalize_option_type(raw_row.get("type") or raw_row.get("option_type"))
                strike = _parse_float(raw_row.get("strike"), field_name="strike", required=True)
                contract_symbol = _normalize_contract_symbol(
                    raw_row.get("contract_id")
                    or raw_row.get("contract_symbol")
                    or raw_row.get("contractSymbol")
                )
                as_of_utc = _build_as_of_utc_for_quote_date(trade_date, DAILY_QUOTE_MINUTE_ET)
                normalized = {
                    "as_of_utc": as_of_utc.isoformat().replace("+00:00", "Z"),
                    "quote_date_et": trade_date.isoformat(),
                    "quote_minute_et": DAILY_QUOTE_MINUTE_ET,
                    "snapshot_kind": DAILY_SNAPSHOT_KIND,
                    "underlying": row_underlying,
                    "contract_symbol": contract_symbol,
                    "expiry": expiry.isoformat(),
                    "option_type": option_type,
                    "strike": strike,
                    "bid": _parse_float(raw_row.get("bid"), field_name="bid"),
                    "ask": _parse_float(raw_row.get("ask"), field_name="ask"),
                    "last": _parse_float(raw_row.get("last"), field_name="last"),
                    "iv": _parse_float(raw_row.get("implied_volatility") or raw_row.get("iv"), field_name="iv"),
                    "underlying_price": underlying_prices.get(trade_date.isoformat()),
                    "volume": _parse_int(raw_row.get("volume"), field_name="volume"),
                    "open_interest": _parse_int(raw_row.get("open_interest"), field_name="open_interest"),
                }
            except Exception as exc:
                rejected_rows += 1
                if len(warnings) < 20:
                    warnings.append(f"Row {row_index}: {exc}")
                continue

            pending_values.append(_quote_insert_values(normalized, batch_id))
            if len(pending_values) >= QUOTE_INSERT_CHUNK_SIZE:
                inserted, duplicate = _insert_option_quote_batch(conn, cursor, pending_values)
                imported_rows += inserted
                duplicate_rows += duplicate

        if not saw_rows:
            raise ValueError("The parquet file contained no option rows for the selected date range.")

        inserted, duplicate = _insert_option_quote_batch(conn, cursor, pending_values)
        imported_rows += inserted
        duplicate_rows += duplicate

        cursor.execute(
            """
            UPDATE import_batches
            SET total_rows = ?,
                imported_rows = ?,
                duplicate_rows = ?,
                rejected_rows = ?,
                warnings_json = ?
            WHERE id = ?
            """,
            (
                total_rows,
                imported_rows,
                duplicate_rows,
                rejected_rows,
                json.dumps(warnings),
                batch_id,
            ),
        )
        conn.commit()

    return {
        "db_path": str(path),
        "batch_id": batch_id,
        "source_label": source_label,
        "input_path": str(parquet_path),
        "file_hash": file_hash,
        "imported_at_utc": imported_at_utc,
        "dataset_kind": dataset_kind,
        "data_trust": data_trust,
        "snapshot_kind": DAILY_SNAPSHOT_KIND,
        "date_from": date_from.isoformat() if isinstance(date_from, date) else None,
        "date_to": date_to.isoformat() if isinstance(date_to, date) else None,
        "total_rows": total_rows,
        "imported_rows": imported_rows,
        "duplicate_rows": duplicate_rows,
        "rejected_rows": rejected_rows,
        "warnings": warnings,
    }


class HistoricalOptionsStore:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else _db_path()
        init_schema(self.db_path)
        self._quote_lookup_cache: dict[tuple[Any, ...], Optional[HistoricalQuote]] = {}

    def _connect(self) -> sqlite3.Connection:
        conn = _sqlite_connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _quote_cache_get(self, key: tuple[Any, ...]) -> object:
        return self._quote_lookup_cache.get(key, _QUOTE_CACHE_MISS)

    def _quote_cache_set(self, key: tuple[Any, ...], value: Optional[HistoricalQuote]) -> Optional[HistoricalQuote]:
        if len(self._quote_lookup_cache) >= QUOTE_LOOKUP_CACHE_MAX_ENTRIES:
            self._quote_lookup_cache.clear()
        self._quote_lookup_cache[key] = value
        return value

    def has_quotes(
        self,
        snapshot_kind: str | None = None,
        *,
        trusted_only: bool = False,
        source_labels: Sequence[str] | None = None,
    ) -> bool:
        with closing(self._connect()) as conn:
            query = """
                SELECT 1
                FROM option_quote_snapshots q
                JOIN import_batches b ON b.id = q.source_batch_id
            """
            clauses: list[str] = []
            params: list[Any] = []
            if snapshot_kind:
                clauses.append("q.snapshot_kind = ?")
                params.append(str(snapshot_kind))
            if trusted_only:
                clauses.append("b.data_trust = ?")
                params.append(TRUSTED_DATA_TRUST)
            normalized_source_labels = _normalize_source_labels(source_labels)
            if normalized_source_labels:
                placeholders = ", ".join("?" for _ in normalized_source_labels)
                clauses.append(f"b.source_label IN ({placeholders})")
                params.extend(normalized_source_labels)
            if clauses:
                query += f" WHERE {' AND '.join(clauses)}"
            query += " LIMIT 1"
            row = conn.execute(query, tuple(params)).fetchone()
        return row is not None

    def list_available_underlyings(
        self,
        snapshot_kind: str | None = None,
        *,
        trusted_only: bool = False,
        source_labels: Sequence[str] | None = None,
    ) -> list[str]:
        normalized_source_labels = _normalize_source_labels(source_labels)
        with closing(self._connect()) as conn:
            if not trusted_only and not normalized_source_labels:
                query = "SELECT DISTINCT underlying FROM option_quote_snapshots"
                clauses: list[str] = []
                params: list[Any] = []
                if snapshot_kind:
                    clauses.append("snapshot_kind = ?")
                    params.append(str(snapshot_kind))
                if clauses:
                    query += f" WHERE {' AND '.join(clauses)}"
                query += " ORDER BY underlying"
                rows = conn.execute(query, tuple(params)).fetchall()
                return [str(row["underlying"]) for row in rows]

            query = """
                SELECT DISTINCT q.underlying
                FROM option_quote_snapshots q
                JOIN import_batches b ON b.id = q.source_batch_id
            """
            clauses = []
            params = []
            if snapshot_kind:
                clauses.append("q.snapshot_kind = ?")
                params.append(str(snapshot_kind))
            if trusted_only:
                clauses.append("b.data_trust = ?")
                params.append(TRUSTED_DATA_TRUST)
            if normalized_source_labels:
                placeholders = ", ".join("?" for _ in normalized_source_labels)
                clauses.append(f"b.source_label IN ({placeholders})")
                params.extend(normalized_source_labels)
            query += f" WHERE {' AND '.join(clauses)}"
            query += " ORDER BY q.underlying"
            rows = conn.execute(query, tuple(params)).fetchall()
        return [str(row["underlying"]) for row in rows]

    def available_quote_dates(
        self,
        underlying: str,
        *,
        snapshot_kind: str | None = None,
        trusted_only: bool = False,
        source_labels: Sequence[str] | None = None,
    ) -> list[str]:
        with closing(self._connect()) as conn:
            query = """
                SELECT DISTINCT q.quote_date_et
                FROM option_quote_snapshots q
                JOIN import_batches b ON b.id = q.source_batch_id
            """
            clauses: list[str] = ["q.underlying = ?"]
            params: list[Any] = [_normalize_underlying(underlying)]
            if snapshot_kind:
                clauses.append("q.snapshot_kind = ?")
                params.append(str(snapshot_kind))
            if trusted_only:
                clauses.append("b.data_trust = ?")
                params.append(TRUSTED_DATA_TRUST)
            normalized_source_labels = _normalize_source_labels(source_labels)
            if normalized_source_labels:
                placeholders = ", ".join("?" for _ in normalized_source_labels)
                clauses.append(f"b.source_label IN ({placeholders})")
                params.extend(normalized_source_labels)
            query += f" WHERE {' AND '.join(clauses)}"
            query += " ORDER BY q.quote_date_et"
            rows = conn.execute(query, tuple(params)).fetchall()
        return [str(row["quote_date_et"]) for row in rows]

    def shared_quote_dates(
        self,
        underlyings: Sequence[str],
        *,
        snapshot_kind: str | None = None,
        trusted_only: bool = False,
        source_labels: Sequence[str] | None = None,
    ) -> list[str]:
        normalized_underlyings = sorted(
            {
                _normalize_underlying(underlying)
                for underlying in underlyings
                if str(underlying or "").strip()
            }
        )
        if not normalized_underlyings:
            return []
        if len(normalized_underlyings) == 1:
            return self.available_quote_dates(
                normalized_underlyings[0],
                snapshot_kind=snapshot_kind,
                trusted_only=trusted_only,
                source_labels=source_labels,
            )

        placeholders = ", ".join("?" for _ in normalized_underlyings)
        with closing(self._connect()) as conn:
            query = f"""
                SELECT q.quote_date_et
                FROM option_quote_snapshots q
                JOIN import_batches b ON b.id = q.source_batch_id
                WHERE q.underlying IN ({placeholders})
            """
            params: list[Any] = list(normalized_underlyings)
            if snapshot_kind:
                query += " AND q.snapshot_kind = ?"
                params.append(str(snapshot_kind))
            if trusted_only:
                query += " AND b.data_trust = ?"
                params.append(TRUSTED_DATA_TRUST)
            normalized_source_labels = _normalize_source_labels(source_labels)
            if normalized_source_labels:
                source_placeholders = ", ".join("?" for _ in normalized_source_labels)
                query += f" AND b.source_label IN ({source_placeholders})"
                params.extend(normalized_source_labels)
            query += """
                GROUP BY q.quote_date_et
                HAVING COUNT(DISTINCT q.underlying) = ?
                ORDER BY q.quote_date_et
            """
            params.append(len(normalized_underlyings))
            rows = conn.execute(query, tuple(params)).fetchall()
        return [str(row["quote_date_et"]) for row in rows]

    def summarize_imports(self, snapshot_kind: str | None = None, *, trusted_only: bool = False) -> dict[str, Any]:
        with closing(self._connect()) as conn:
            clauses: list[str] = []
            params: list[Any] = []
            if snapshot_kind:
                clauses.append("q.snapshot_kind = ?")
                params.append(str(snapshot_kind))
            if trusted_only:
                clauses.append("b.data_trust = ?")
                params.append(TRUSTED_DATA_TRUST)
            where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            row = conn.execute(
                f"""
                SELECT
                    COUNT(*) AS quote_rows,
                    COUNT(DISTINCT b.id) AS batch_count,
                    GROUP_CONCAT(DISTINCT b.source_label) AS source_labels,
                    GROUP_CONCAT(DISTINCT b.dataset_kind) AS dataset_kinds,
                    GROUP_CONCAT(DISTINCT b.data_trust) AS trust_levels
                FROM option_quote_snapshots q
                JOIN import_batches b ON b.id = q.source_batch_id
                {where_sql}
                """,
                tuple(params),
            ).fetchone()
        source_labels = [item for item in str(row["source_labels"] if row else "").split(",") if item]
        dataset_kinds = [item for item in str(row["dataset_kinds"] if row else "").split(",") if item]
        trust_levels = [item for item in str(row["trust_levels"] if row else "").split(",") if item]
        return {
            "quote_rows": int(row["quote_rows"] if row else 0),
            "batch_count": int(row["batch_count"] if row else 0),
            "source_labels": source_labels,
            "dataset_kinds": dataset_kinds,
            "trust_levels": trust_levels,
            "trusted_only": trusted_only,
            "snapshot_kind": snapshot_kind,
        }

    def source_inventory(
        self,
        snapshot_kind: str | None = None,
        *,
        trusted_only: bool = False,
        source_labels: Sequence[str] | None = None,
        underlyings: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        normalized_source_labels = _normalize_source_labels(source_labels)
        normalized_underlyings = sorted(
            {
                _normalize_underlying(underlying)
                for underlying in (underlyings or [])
                if str(underlying or "").strip()
            }
        )
        dataset_kind = _dataset_kind_for_snapshot_kind(snapshot_kind)

        batch_clauses: list[str] = []
        batch_params: list[Any] = []
        if dataset_kind:
            batch_clauses.append("dataset_kind = ?")
            batch_params.append(dataset_kind)
        if trusted_only:
            batch_clauses.append("data_trust = ?")
            batch_params.append(TRUSTED_DATA_TRUST)
        if normalized_source_labels:
            placeholders = ", ".join("?" for _ in normalized_source_labels)
            batch_clauses.append(f"source_label IN ({placeholders})")
            batch_params.extend(normalized_source_labels)
        batch_where = f"WHERE {' AND '.join(batch_clauses)}" if batch_clauses else ""

        quote_clauses: list[str] = []
        quote_params: list[Any] = []
        if snapshot_kind:
            quote_clauses.append("q.snapshot_kind = ?")
            quote_params.append(str(snapshot_kind))
        if trusted_only:
            quote_clauses.append("b.data_trust = ?")
            quote_params.append(TRUSTED_DATA_TRUST)
        if normalized_source_labels:
            placeholders = ", ".join("?" for _ in normalized_source_labels)
            quote_clauses.append(f"b.source_label IN ({placeholders})")
            quote_params.extend(normalized_source_labels)
        if normalized_underlyings:
            placeholders = ", ".join("?" for _ in normalized_underlyings)
            quote_clauses.append(f"q.underlying IN ({placeholders})")
            quote_params.extend(normalized_underlyings)
        quote_where = f"WHERE {' AND '.join(quote_clauses)}" if quote_clauses else ""

        with closing(self._connect()) as conn:
            batch_rows = conn.execute(
                f"""
                SELECT
                    source_label,
                    COUNT(*) AS batch_count,
                    COALESCE(SUM(total_rows), 0) AS batch_total_rows,
                    COALESCE(SUM(imported_rows), 0) AS batch_imported_rows,
                    COALESCE(SUM(duplicate_rows), 0) AS batch_duplicate_rows,
                    COALESCE(SUM(rejected_rows), 0) AS batch_rejected_rows,
                    MIN(imported_at_utc) AS first_imported_at_utc,
                    MAX(imported_at_utc) AS latest_imported_at_utc,
                    GROUP_CONCAT(DISTINCT dataset_kind) AS dataset_kinds,
                    GROUP_CONCAT(DISTINCT data_trust) AS trust_levels
                FROM import_batches
                {batch_where}
                GROUP BY source_label
                """,
                tuple(batch_params),
            ).fetchall()
            quote_rows = conn.execute(
                f"""
                SELECT
                    b.source_label AS source_label,
                    COUNT(*) AS quote_rows,
                    COUNT(DISTINCT q.quote_date_et) AS quote_date_count,
                    MIN(q.quote_date_et) AS first_quote_date,
                    MAX(q.quote_date_et) AS last_quote_date,
                    COUNT(DISTINCT q.underlying) AS underlying_count,
                    GROUP_CONCAT(DISTINCT q.underlying) AS underlyings
                FROM option_quote_snapshots q
                JOIN import_batches b ON b.id = q.source_batch_id
                {quote_where}
                GROUP BY b.source_label
                """,
                tuple(quote_params),
            ).fetchall()

        def _split_csv(value: Any) -> list[str]:
            return sorted(item for item in str(value or "").split(",") if item)

        batch_by_source = {str(row["source_label"]): row for row in batch_rows}
        quote_by_source = {str(row["source_label"]): row for row in quote_rows}
        source_names = sorted(set(batch_by_source) | set(quote_by_source))
        sources: list[dict[str, Any]] = []
        for source_label in source_names:
            batch_row = batch_by_source.get(source_label)
            quote_row = quote_by_source.get(source_label)
            quote_date_count = int((quote_row["quote_date_count"] if quote_row else 0) or 0)
            sources.append(
                {
                    "source_label": source_label,
                    "batch_count": int((batch_row["batch_count"] if batch_row else 0) or 0),
                    "batch_total_rows": int((batch_row["batch_total_rows"] if batch_row else 0) or 0),
                    "batch_imported_rows": int((batch_row["batch_imported_rows"] if batch_row else 0) or 0),
                    "batch_duplicate_rows": int((batch_row["batch_duplicate_rows"] if batch_row else 0) or 0),
                    "batch_rejected_rows": int((batch_row["batch_rejected_rows"] if batch_row else 0) or 0),
                    "first_imported_at_utc": (
                        str((batch_row["first_imported_at_utc"] if batch_row else None) or "") or None
                    ),
                    "latest_imported_at_utc": (
                        str((batch_row["latest_imported_at_utc"] if batch_row else None) or "") or None
                    ),
                    "dataset_kinds": _split_csv(batch_row["dataset_kinds"] if batch_row else None),
                    "trust_levels": _split_csv(batch_row["trust_levels"] if batch_row else None),
                    "quote_rows_in_scope": int((quote_row["quote_rows"] if quote_row else 0) or 0),
                    "quote_dates": {
                        "count": quote_date_count,
                        "first": str((quote_row["first_quote_date"] if quote_row else None) or "") or None,
                        "last": str((quote_row["last_quote_date"] if quote_row else None) or "") or None,
                    },
                    "underlying_count_in_scope": int((quote_row["underlying_count"] if quote_row else 0) or 0),
                    "underlyings_in_scope": _split_csv(quote_row["underlyings"] if quote_row else None),
                    "requested_underlying_count": len(normalized_underlyings),
                }
            )

        return {
            "status": "summarized",
            "db_path": str(self.db_path),
            "snapshot_kind": snapshot_kind,
            "trusted_only": trusted_only,
            "source_labels_requested": normalized_source_labels,
            "underlyings_requested": normalized_underlyings,
            "underlyings_requested_count": len(normalized_underlyings),
            "source_labels_seen": source_names,
            "source_labels_with_batches": sorted(batch_by_source),
            "source_labels_with_quotes_in_scope": sorted(quote_by_source),
            "sources": sources,
        }

    def snapshot_summary(
        self,
        snapshot_kind: str,
        *,
        trusted_only: bool = False,
        include_available_underlyings: bool = True,
        source_labels: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        normalized_snapshot_kind = str(snapshot_kind)
        normalized_source_labels = _normalize_source_labels(source_labels)
        with closing(self._connect()) as conn:
            dataset_kind = _dataset_kind_for_snapshot_kind(normalized_snapshot_kind)
            batch_clauses = ["imported_rows > 0"]
            batch_params: list[Any] = []
            if dataset_kind:
                batch_clauses.append("dataset_kind = ?")
                batch_params.append(dataset_kind)
            if trusted_only:
                batch_clauses.append("data_trust = ?")
                batch_params.append(TRUSTED_DATA_TRUST)
            if normalized_source_labels:
                placeholders = ", ".join("?" for _ in normalized_source_labels)
                batch_clauses.append(f"source_label IN ({placeholders})")
                batch_params.extend(normalized_source_labels)
            batch_row = conn.execute(
                f"""
                SELECT
                    COALESCE(SUM(imported_rows), 0) AS quote_count,
                    COUNT(*) AS batch_count,
                    MAX(imported_at_utc) AS latest_imported_at_utc,
                    GROUP_CONCAT(DISTINCT source_label) AS source_labels,
                    GROUP_CONCAT(DISTINCT dataset_kind) AS dataset_kinds,
                    GROUP_CONCAT(DISTINCT data_trust) AS trust_levels
                FROM import_batches
                WHERE {' AND '.join(batch_clauses)}
                """,
                tuple(batch_params),
            ).fetchone()

            quote_count = int((batch_row["quote_count"] if batch_row else 0) or 0)
            if quote_count <= 0:
                return {
                    "db_path": str(self.db_path),
                    "snapshot_kind": normalized_snapshot_kind,
                    "quote_count": 0,
                    "batch_count": 0,
                    "earliest_quote_at_utc": None,
                    "latest_quote_at_utc": None,
                    "latest_imported_at_utc": None,
                    "available_underlyings": [] if include_available_underlyings else None,
                    "source_labels": [],
                    "dataset_kinds": [],
                    "trust_levels": [TRUSTED_DATA_TRUST] if trusted_only else [],
                    "trusted_only": trusted_only,
                }

            trust_filter_redundant = True
            if trusted_only and dataset_kind:
                untrusted_count_row = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM import_batches
                    WHERE imported_rows > 0
                      AND dataset_kind = ?
                      AND data_trust != ?
                    """,
                    (dataset_kind, TRUSTED_DATA_TRUST),
                ).fetchone()
                trust_filter_redundant = int((untrusted_count_row[0] if untrusted_count_row else 0) or 0) == 0

            if trust_filter_redundant and not normalized_source_labels:
                earliest_row = conn.execute(
                    """
                    SELECT as_of_utc
                    FROM option_quote_snapshots
                    WHERE snapshot_kind = ?
                    ORDER BY as_of_utc ASC
                    LIMIT 1
                    """,
                    (normalized_snapshot_kind,),
                ).fetchone()
                latest_row = conn.execute(
                    """
                    SELECT as_of_utc
                    FROM option_quote_snapshots
                    WHERE snapshot_kind = ?
                    ORDER BY as_of_utc DESC
                    LIMIT 1
                    """,
                    (normalized_snapshot_kind,),
                ).fetchone()
                earliest_quote_at_utc = str((earliest_row["as_of_utc"] if earliest_row else None) or "") or None
                latest_quote_at_utc = str((latest_row["as_of_utc"] if latest_row else None) or "") or None
            else:
                quote_clauses = ["q.snapshot_kind = ?"]
                params: list[Any] = [normalized_snapshot_kind]
                if trusted_only:
                    quote_clauses.append("b.data_trust = ?")
                    params.append(TRUSTED_DATA_TRUST)
                if normalized_source_labels:
                    placeholders = ", ".join("?" for _ in normalized_source_labels)
                    quote_clauses.append(f"b.source_label IN ({placeholders})")
                    params.extend(normalized_source_labels)
                row = conn.execute(
                    f"""
                    SELECT
                        MIN(q.as_of_utc) AS earliest_quote_at_utc,
                        MAX(q.as_of_utc) AS latest_quote_at_utc
                    FROM option_quote_snapshots q
                    JOIN import_batches b
                      ON b.id = q.source_batch_id
                    WHERE {' AND '.join(quote_clauses)}
                    """,
                    tuple(params),
                ).fetchone()
                earliest_quote_at_utc = str((row["earliest_quote_at_utc"] if row else None) or "") or None
                latest_quote_at_utc = str((row["latest_quote_at_utc"] if row else None) or "") or None

        return {
            "db_path": str(self.db_path),
            "snapshot_kind": normalized_snapshot_kind,
            "quote_count": quote_count,
            "batch_count": int((batch_row["batch_count"] if batch_row else 0) or 0),
            "earliest_quote_at_utc": earliest_quote_at_utc,
            "latest_quote_at_utc": latest_quote_at_utc,
            "latest_imported_at_utc": str((batch_row["latest_imported_at_utc"] if batch_row else None) or "") or None,
            "available_underlyings": (
                self.list_available_underlyings(
                    snapshot_kind=normalized_snapshot_kind,
                    trusted_only=(trusted_only if normalized_source_labels else (trusted_only and not trust_filter_redundant)),
                    source_labels=normalized_source_labels,
                )
                if include_available_underlyings
                else None
            ),
            "source_labels": [item for item in str((batch_row["source_labels"] if batch_row else "") or "").split(",") if item],
            "dataset_kinds": [item for item in str((batch_row["dataset_kinds"] if batch_row else "") or "").split(",") if item],
            "trust_levels": [item for item in str((batch_row["trust_levels"] if batch_row else "") or "").split(",") if item],
            "trusted_only": trusted_only,
            "source_labels_requested": normalized_source_labels,
        }

    def get_exact_quote(
        self,
        *,
        quote_date_et: str | date,
        contract_symbol: str | None = None,
        underlying: str | None = None,
        expiry: str | date | None = None,
        option_type: str | None = None,
        strike: float | None = None,
        prefer_latest: bool = True,
        snapshot_kind: str | None = None,
        allow_last_price: bool = True,
        source_labels: Sequence[str] | None = None,
    ) -> Optional[HistoricalQuote]:
        quote_date_text = quote_date_et.isoformat() if isinstance(quote_date_et, date) else str(quote_date_et)[:10]
        clauses = ["q.quote_date_et = ?"]
        params: list[Any] = [quote_date_text]
        normalized_snapshot_kind = str(snapshot_kind) if snapshot_kind else None
        if snapshot_kind:
            clauses.append("q.snapshot_kind = ?")
            params.append(normalized_snapshot_kind)
        normalized_contract_symbol = None
        if contract_symbol:
            normalized_contract_symbol = _normalize_contract_symbol(contract_symbol)
            clauses.append("q.contract_symbol = ?")
            params.append(normalized_contract_symbol)
            normalized_tuple = None
        else:
            if not (underlying and expiry and option_type and strike is not None):
                raise ValueError("Exact tuple match requires underlying, expiry, option_type, and strike.")
            normalized_tuple = (
                _normalize_underlying(underlying),
                expiry.isoformat() if isinstance(expiry, date) else str(expiry)[:10],
                _normalize_option_type(option_type),
                float(strike),
            )
            clauses.extend(
                [
                    "q.underlying = ?",
                    "q.expiry = ?",
                    "q.option_type = ?",
                    "ABS(q.strike - ?) <= 0.0001",
                ]
            )
            params.extend(normalized_tuple)
        normalized_source_labels = _normalize_source_labels(source_labels)
        normalized_source_label_tuple = tuple(normalized_source_labels)
        if normalized_source_labels:
            placeholders = ", ".join("?" for _ in normalized_source_labels)
            clauses.append(f"b.source_label IN ({placeholders})")
            params.extend(normalized_source_labels)
        clauses.append(_valid_quote_sql_clause("q", allow_last_price=allow_last_price))

        cache_key = (
            "exact",
            quote_date_text,
            normalized_snapshot_kind,
            normalized_contract_symbol,
            normalized_tuple,
            bool(prefer_latest),
            bool(allow_last_price),
            normalized_source_label_tuple,
        )
        cached = self._quote_cache_get(cache_key)
        if cached is not _QUOTE_CACHE_MISS:
            return cached  # type: ignore[return-value]

        order = "DESC" if prefer_latest else "ASC"
        with closing(self._connect()) as conn:
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
        candidate = self._row_to_quote(row, allow_last_price=allow_last_price) if row is not None else None
        return self._quote_cache_set(cache_key, candidate)

    def find_entry_contract(
        self,
        *,
        underlying: str,
        trade_date_et: str | date,
        option_type: str,
        target_expiry: str | date,
        target_strike: float,
        earliest_minute_et: int = ENTRY_QUOTE_MINUTE_ET,
        window_minutes: int = ENTRY_QUOTE_WINDOW_MINUTES,
        snapshot_kind: str = INTRADAY_SNAPSHOT_KIND,
        allow_last_price: bool = True,
        source_labels: Sequence[str] | None = None,
    ) -> Optional[HistoricalQuote]:
        quote_date_text = trade_date_et.isoformat() if isinstance(trade_date_et, date) else str(trade_date_et)[:10]
        target_expiry_date = target_expiry if isinstance(target_expiry, date) else date.fromisoformat(str(target_expiry)[:10])
        target_expiry_text = target_expiry_date.isoformat()
        normalized_underlying = _normalize_underlying(underlying)
        normalized_option_type = _normalize_option_type(option_type)
        normalized_snapshot_kind = str(snapshot_kind)
        end_minute_et = int(earliest_minute_et + window_minutes)
        clauses = [
            "q.underlying = ?",
            "q.snapshot_kind = ?",
            "q.option_type = ?",
            "q.quote_date_et = ?",
            "q.quote_minute_et >= ?",
            "q.quote_minute_et <= ?",
        ]
        params: list[Any] = [
            normalized_underlying,
            normalized_snapshot_kind,
            normalized_option_type,
            quote_date_text,
            int(earliest_minute_et),
            end_minute_et,
        ]
        normalized_source_labels = _normalize_source_labels(source_labels)
        normalized_source_label_tuple = tuple(normalized_source_labels)
        if normalized_source_labels:
            placeholders = ", ".join("?" for _ in normalized_source_labels)
            clauses.append(f"b.source_label IN ({placeholders})")
            params.extend(normalized_source_labels)
        clauses.append(_valid_quote_sql_clause("q", allow_last_price=allow_last_price))

        cache_key = (
            "entry_contract",
            normalized_underlying,
            quote_date_text,
            normalized_option_type,
            target_expiry_text,
            float(target_strike),
            int(earliest_minute_et),
            end_minute_et,
            normalized_snapshot_kind,
            bool(allow_last_price),
            normalized_source_label_tuple,
        )
        cached = self._quote_cache_get(cache_key)
        if cached is not _QUOTE_CACHE_MISS:
            return cached  # type: ignore[return-value]

        with closing(self._connect()) as conn:
            row = conn.execute(
                f"""
                WITH first_valid_quotes AS (
                    SELECT
                        q.*,
                        ROW_NUMBER() OVER (
                            PARTITION BY q.contract_symbol
                            ORDER BY q.quote_minute_et ASC, q.as_of_utc ASC
                        ) AS quote_rank
                    FROM option_quote_snapshots q
                    JOIN import_batches b ON b.id = q.source_batch_id
                    WHERE {' AND '.join(clauses)}
                )
                SELECT *
                FROM first_valid_quotes
                WHERE quote_rank = 1
                ORDER BY
                    ABS(julianday(expiry) - julianday(?)) ASC,
                    ABS(strike - ?) ASC,
                    quote_minute_et ASC,
                    contract_symbol ASC
                LIMIT 1
                """,
                tuple(params + [target_expiry_text, float(target_strike)]),
            ).fetchone()

        candidate = self._row_to_quote(row, allow_last_price=allow_last_price) if row is not None else None
        return self._quote_cache_set(cache_key, candidate)

    def list_entry_contracts(
        self,
        *,
        underlying: str,
        trade_date_et: str | date,
        option_type: str,
        earliest_minute_et: int = ENTRY_QUOTE_MINUTE_ET,
        window_minutes: int = ENTRY_QUOTE_WINDOW_MINUTES,
        snapshot_kind: str = INTRADAY_SNAPSHOT_KIND,
        allow_last_price: bool = True,
        min_expiry: str | date | None = None,
        max_expiry: str | date | None = None,
        source_labels: Sequence[str] | None = None,
    ) -> list[HistoricalQuote]:
        quote_date_text = trade_date_et.isoformat() if isinstance(trade_date_et, date) else str(trade_date_et)[:10]
        normalized_underlying = _normalize_underlying(underlying)
        normalized_option_type = _normalize_option_type(option_type)
        normalized_snapshot_kind = str(snapshot_kind)
        end_minute_et = int(earliest_minute_et + window_minutes)
        clauses = [
            "q.underlying = ?",
            "q.snapshot_kind = ?",
            "q.option_type = ?",
            "q.quote_date_et = ?",
            "q.quote_minute_et >= ?",
            "q.quote_minute_et <= ?",
        ]
        params: list[Any] = [
            normalized_underlying,
            normalized_snapshot_kind,
            normalized_option_type,
            quote_date_text,
            int(earliest_minute_et),
            end_minute_et,
        ]
        if min_expiry is not None:
            min_expiry_text = min_expiry.isoformat() if isinstance(min_expiry, date) else str(min_expiry)[:10]
            clauses.append("q.expiry >= ?")
            params.append(min_expiry_text)
        if max_expiry is not None:
            max_expiry_text = max_expiry.isoformat() if isinstance(max_expiry, date) else str(max_expiry)[:10]
            clauses.append("q.expiry <= ?")
            params.append(max_expiry_text)
        normalized_source_labels = _normalize_source_labels(source_labels)
        if normalized_source_labels:
            placeholders = ", ".join("?" for _ in normalized_source_labels)
            clauses.append(f"b.source_label IN ({placeholders})")
            params.extend(normalized_source_labels)
        clauses.append(_valid_quote_sql_clause("q", allow_last_price=allow_last_price))

        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"""
                WITH first_valid_quotes AS (
                    SELECT
                        q.*,
                        ROW_NUMBER() OVER (
                            PARTITION BY q.contract_symbol
                            ORDER BY q.quote_minute_et ASC, q.as_of_utc ASC
                        ) AS quote_rank
                    FROM option_quote_snapshots q
                    JOIN import_batches b ON b.id = q.source_batch_id
                    WHERE {' AND '.join(clauses)}
                )
                SELECT *
                FROM first_valid_quotes
                WHERE quote_rank = 1
                ORDER BY expiry ASC, strike ASC, contract_symbol ASC
                """,
                tuple(params),
            ).fetchall()
        quotes: list[HistoricalQuote] = []
        for row in rows:
            quote = self._row_to_quote(row, allow_last_price=allow_last_price)
            if quote is not None:
                quotes.append(quote)
        return quotes

    def find_entry_quote_for_contract(
        self,
        *,
        contract_symbol: str,
        trade_date_et: str | date,
        earliest_minute_et: int = ENTRY_QUOTE_MINUTE_ET,
        window_minutes: int = ENTRY_QUOTE_WINDOW_MINUTES,
        snapshot_kind: str = INTRADAY_SNAPSHOT_KIND,
        allow_last_price: bool = True,
        source_labels: Sequence[str] | None = None,
    ) -> Optional[HistoricalQuote]:
        quote_date_text = trade_date_et.isoformat() if isinstance(trade_date_et, date) else str(trade_date_et)[:10]
        normalized_contract_symbol = _normalize_contract_symbol(contract_symbol)
        normalized_snapshot_kind = str(snapshot_kind)
        end_minute_et = int(earliest_minute_et + window_minutes)
        clauses = [
            "q.contract_symbol = ?",
            "q.snapshot_kind = ?",
            "q.quote_date_et = ?",
        ]
        params: list[Any] = [
            normalized_contract_symbol,
            normalized_snapshot_kind,
            quote_date_text,
        ]
        if normalized_snapshot_kind != DAILY_SNAPSHOT_KIND:
            clauses.extend(
                [
                    "q.quote_minute_et >= ?",
                    "q.quote_minute_et <= ?",
                ]
            )
            params.extend(
                [
                    int(earliest_minute_et),
                    end_minute_et,
                ]
            )
        normalized_source_labels = _normalize_source_labels(source_labels)
        normalized_source_label_tuple = tuple(normalized_source_labels)
        if normalized_source_labels:
            placeholders = ", ".join("?" for _ in normalized_source_labels)
            clauses.append(f"b.source_label IN ({placeholders})")
            params.extend(normalized_source_labels)
        clauses.append(_valid_quote_sql_clause("q", allow_last_price=allow_last_price))

        cache_key = (
            "entry_quote_contract",
            normalized_contract_symbol,
            quote_date_text,
            int(earliest_minute_et),
            end_minute_et,
            normalized_snapshot_kind,
            bool(allow_last_price),
            normalized_source_label_tuple,
        )
        cached = self._quote_cache_get(cache_key)
        if cached is not _QUOTE_CACHE_MISS:
            return cached  # type: ignore[return-value]

        with closing(self._connect()) as conn:
            row = conn.execute(
                f"""
                SELECT q.*
                FROM option_quote_snapshots q
                JOIN import_batches b ON b.id = q.source_batch_id
                WHERE {' AND '.join(clauses)}
                ORDER BY q.quote_minute_et ASC, q.as_of_utc ASC
                LIMIT 1
                """,
                tuple(params),
            ).fetchone()

        candidate = self._row_to_quote(row, allow_last_price=allow_last_price) if row is not None else None
        return self._quote_cache_set(cache_key, candidate)

    def get_closing_quote(
        self,
        *,
        contract_symbol: str,
        quote_date_et: str | date,
        snapshot_kind: str | None = None,
        allow_last_price: bool = True,
        source_labels: Sequence[str] | None = None,
    ) -> Optional[HistoricalQuote]:
        return self.get_exact_quote(
            quote_date_et=quote_date_et,
            contract_symbol=contract_symbol,
            prefer_latest=True,
            snapshot_kind=snapshot_kind,
            allow_last_price=allow_last_price,
            source_labels=source_labels,
        )

    def _row_to_quote(self, row: sqlite3.Row, *, allow_last_price: bool = True) -> Optional[HistoricalQuote]:
        raw = dict(row)
        normalized = {
            "bid": _parse_float(raw.get("bid"), field_name="bid"),
            "ask": _parse_float(raw.get("ask"), field_name="ask"),
            "last": _parse_float(raw.get("last"), field_name="last"),
        }
        price, basis = _quote_price_with_mode(normalized, allow_last_price=allow_last_price)
        if price is None or basis is None:
            return None
        return HistoricalQuote(
            as_of_utc=str(raw["as_of_utc"]),
            quote_date_et=str(raw["quote_date_et"]),
            quote_minute_et=int(raw["quote_minute_et"]),
            underlying=str(raw["underlying"]),
            contract_symbol=str(raw["contract_symbol"]),
            expiry=str(raw["expiry"]),
            option_type=str(raw["option_type"]),
            strike=float(raw["strike"]),
            price=price,
            price_basis=basis,
            underlying_price=_parse_float(raw.get("underlying_price"), field_name="underlying_price"),
            bid=normalized["bid"],
            ask=normalized["ask"],
            last=normalized["last"],
            iv=_parse_float(raw.get("iv"), field_name="iv"),
            volume=_parse_int(raw.get("volume"), field_name="volume"),
            open_interest=_parse_int(raw.get("open_interest"), field_name="open_interest"),
            snapshot_kind=str(raw.get("snapshot_kind") or INTRADAY_SNAPSHOT_KIND),
        )


def load_import_batches(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    path = Path(db_path) if db_path else _db_path()
    init_schema(path)
    with closing(_sqlite_connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT *
            FROM import_batches
            ORDER BY imported_at_utc DESC, id DESC
            """
        ).fetchall()
    batches: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["warnings"] = json.loads(item.pop("warnings_json") or "[]")
        item["data_trust"] = _normalize_data_trust(item.get("data_trust"))
        batches.append(item)
    return batches


def available_quote_dates(
    underlying: str,
    *,
    snapshot_kind: str | None = None,
    trusted_only: bool = False,
    source_labels: Sequence[str] | None = None,
    db_path: str | Path | None = None,
) -> list[str]:
    store = HistoricalOptionsStore(db_path)
    return store.available_quote_dates(
        underlying,
        snapshot_kind=snapshot_kind,
        trusted_only=trusted_only,
        source_labels=source_labels,
    )
