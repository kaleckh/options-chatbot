from __future__ import annotations

import copy
import contextlib
import json
import math
import sqlite3
from datetime import date, datetime
from typing import Any, Optional

from options_execution import commission_total_usd, option_pnl_snapshot
from repository_contracts import SuggestedTradesRepository
from repository_migrations import (
    SQLITE_SUGGESTED_TRADES_STORE_ID,
    apply_sqlite_repository_migrations,
)


def _to_iso(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _load_json(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return copy.deepcopy(fallback)
    if isinstance(value, (dict, list)):
        return copy.deepcopy(value)
    try:
        return json.loads(value)
    except Exception:
        return copy.deepcopy(fallback)


def _normalize_latest_review(row: dict[str, Any]) -> Optional[dict[str, Any]]:
    review_id = row.get("review_id")
    if review_id is None:
        return None
    return {
        "id": review_id,
        "reviewed_at": _to_iso(row.get("reviewed_at")),
        "pricing_source": row.get("pricing_source"),
        "current_option_price": row.get("current_option_price"),
        "current_pnl_pct": row.get("current_pnl_pct"),
        "gross_pnl_pct": row.get("review_gross_pnl_pct"),
        "net_pnl_pct": row.get("review_net_pnl_pct"),
        "gross_pnl_usd": row.get("review_gross_pnl_usd"),
        "net_pnl_usd": row.get("review_net_pnl_usd"),
        "entry_execution_price": row.get("review_entry_execution_price"),
        "exit_execution_price": row.get("review_exit_execution_price"),
        "entry_execution_basis": row.get("review_entry_execution_basis"),
        "exit_execution_basis": row.get("review_exit_execution_basis"),
        "fee_total_usd": row.get("review_fee_total_usd"),
        "recommendation": row.get("recommendation"),
        "reason": row.get("reason"),
        "warnings": _load_json(row.get("warnings"), []),
        "metrics_snapshot": _load_json(row.get("metrics_snapshot"), {}),
    }


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _safe_number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _closed_position_pnl_snapshot(row: dict[str, Any]) -> Optional[dict[str, Any]]:
    is_closed = str(row.get("status") or "").strip().lower() == "closed" or row.get("closed_at") is not None
    if not is_closed:
        return None
    entry_execution_price = _safe_number(
        _first_present(row.get("entry_execution_price"), row.get("entry_option_price"))
    )
    exit_execution_price = _safe_number(
        _first_present(row.get("exit_execution_price"), row.get("exit_option_price"))
    )
    if entry_execution_price is None or entry_execution_price <= 0 or exit_execution_price is None:
        return None

    contracts = row.get("contracts") or 1
    fee_total_usd = _safe_number(row.get("fee_total_usd"))
    if fee_total_usd is None:
        fee_sides = _source_snapshot_fee_sides(row.get("source_pick_snapshot"))
        entry_fee_total_usd = _safe_number(row.get("entry_fee_total_usd"))
        if entry_fee_total_usd is None:
            entry_fee_total_usd = commission_total_usd(contracts=contracts, sides=fee_sides)
        exit_fee_total_usd = commission_total_usd(contracts=contracts, sides=fee_sides)
    else:
        entry_fee_total_usd = fee_total_usd
        exit_fee_total_usd = 0.0

    pnl = option_pnl_snapshot(
        entry_execution_price=entry_execution_price,
        exit_execution_price=exit_execution_price,
        contracts=contracts,
        entry_fee_total_usd=entry_fee_total_usd,
        exit_fee_total_usd=exit_fee_total_usd,
    )
    if pnl.get("gross_pnl_pct") is None and pnl.get("net_pnl_pct") is None:
        return None
    return {
        **pnl,
        "entry_execution_price": entry_execution_price,
        "exit_execution_price": exit_execution_price,
    }


def _closed_position_review(row: dict[str, Any], existing: Optional[dict[str, Any]]) -> dict[str, Any]:
    existing = existing or {}
    metrics_snapshot = _load_json(existing.get("metrics_snapshot"), {})
    computed_pnl = _closed_position_pnl_snapshot(row) or {}
    gross_pnl_pct = _first_present(computed_pnl.get("gross_pnl_pct"), row.get("gross_pnl_pct"), existing.get("gross_pnl_pct"))
    net_pnl_pct = _first_present(computed_pnl.get("net_pnl_pct"), row.get("net_pnl_pct"), existing.get("net_pnl_pct"))
    gross_pnl_usd = _first_present(computed_pnl.get("gross_pnl_usd"), row.get("gross_pnl_usd"), existing.get("gross_pnl_usd"))
    net_pnl_usd = _first_present(computed_pnl.get("net_pnl_usd"), row.get("net_pnl_usd"), existing.get("net_pnl_usd"))
    fee_total_usd = _first_present(computed_pnl.get("fee_total_usd"), row.get("fee_total_usd"), existing.get("fee_total_usd"))
    entry_execution_price = _first_present(
        row.get("entry_execution_price"),
        computed_pnl.get("entry_execution_price"),
        existing.get("entry_execution_price"),
    )
    exit_execution_price = _first_present(
        row.get("exit_execution_price"),
        computed_pnl.get("exit_execution_price"),
        existing.get("exit_execution_price"),
    )
    metrics_snapshot.update(
        {
            "pricing_state": "closed",
            "exit_reason": row.get("exit_reason"),
            "closed_at": _to_iso(row.get("closed_at")),
            "entry_execution_price": entry_execution_price,
            "exit_execution_price": exit_execution_price,
            "gross_pnl_pct": gross_pnl_pct,
            "net_pnl_pct": net_pnl_pct,
            "gross_pnl_usd": gross_pnl_usd,
            "net_pnl_usd": net_pnl_usd,
            "fee_total_usd": fee_total_usd,
        }
    )
    return {
        "id": existing.get("id"),
        "reviewed_at": _to_iso(
            _first_present(row.get("closed_at"), row.get("last_reviewed_at"), existing.get("reviewed_at"))
        ),
        "pricing_source": _first_present(row.get("exit_execution_basis"), row.get("exit_reason"), existing.get("pricing_source")),
        "current_option_price": _first_present(row.get("exit_option_price"), row.get("last_option_price"), existing.get("current_option_price")),
        "current_pnl_pct": _first_present(gross_pnl_pct, row.get("last_pnl_pct"), existing.get("current_pnl_pct")),
        "gross_pnl_pct": gross_pnl_pct,
        "net_pnl_pct": net_pnl_pct,
        "gross_pnl_usd": gross_pnl_usd,
        "net_pnl_usd": net_pnl_usd,
        "entry_execution_price": entry_execution_price,
        "exit_execution_price": exit_execution_price,
        "entry_execution_basis": _first_present(row.get("entry_execution_basis"), existing.get("entry_execution_basis")),
        "exit_execution_basis": _first_present(row.get("exit_execution_basis"), existing.get("exit_execution_basis")),
        "fee_total_usd": fee_total_usd,
        "recommendation": "SELL",
        "reason": _first_present(row.get("exit_reason"), row.get("last_recommendation_reason"), existing.get("reason"), "Position closed."),
        "warnings": [],
        "metrics_snapshot": metrics_snapshot,
    }


def _normalize_position_row(row: dict[str, Any]) -> dict[str, Any]:
    latest_review = _normalize_latest_review(row)
    if str(row.get("status") or "").strip().lower() == "closed" and row.get("closed_at") is not None:
        latest_review = _closed_position_review(row, latest_review)
    computed_pnl = _closed_position_pnl_snapshot(row)
    gross_pnl_pct = row.get("gross_pnl_pct")
    net_pnl_pct = row.get("net_pnl_pct")
    gross_pnl_usd = row.get("gross_pnl_usd")
    net_pnl_usd = row.get("net_pnl_usd")
    fee_total_usd = row.get("fee_total_usd")
    exit_execution_price = row.get("exit_execution_price")
    exit_execution_basis = row.get("exit_execution_basis")
    if computed_pnl is not None:
        gross_pnl_pct = computed_pnl.get("gross_pnl_pct")
        net_pnl_pct = computed_pnl.get("net_pnl_pct")
        gross_pnl_usd = computed_pnl.get("gross_pnl_usd")
        net_pnl_usd = computed_pnl.get("net_pnl_usd")
        fee_total_usd = computed_pnl.get("fee_total_usd")
        if exit_execution_price is None:
            exit_execution_price = computed_pnl.get("exit_execution_price")
    if latest_review is not None:
        if gross_pnl_pct is None:
            gross_pnl_pct = latest_review.get("gross_pnl_pct")
        if net_pnl_pct is None:
            net_pnl_pct = latest_review.get("net_pnl_pct")
        if gross_pnl_usd is None:
            gross_pnl_usd = latest_review.get("gross_pnl_usd")
        if net_pnl_usd is None:
            net_pnl_usd = latest_review.get("net_pnl_usd")
        if fee_total_usd is None:
            fee_total_usd = latest_review.get("fee_total_usd")
        if exit_execution_price is None:
            exit_execution_price = latest_review.get("exit_execution_price")
        if exit_execution_basis is None:
            exit_execution_basis = latest_review.get("exit_execution_basis")
    return {
        "id": row["id"],
        "status": row["status"],
        "ticker": row["ticker"],
        "direction": row["direction"],
        "contract_symbol": row.get("contract_symbol"),
        "strike": row["strike"],
        "expiry": _to_iso(row["expiry"]),
        "asset_class": row.get("asset_class"),
        "contracts": row["contracts"],
        "entry_option_price": row["entry_option_price"],
        "entry_execution_price": row.get("entry_execution_price"),
        "entry_execution_basis": row.get("entry_execution_basis"),
        "entry_fee_total_usd": row.get("entry_fee_total_usd"),
        "entry_underlying_price": row.get("entry_underlying_price"),
        "filled_at": _to_iso(row["filled_at"]),
        "stop_loss_pct": row["stop_loss_pct"],
        "profit_target_pct": row["profit_target_pct"],
        "time_exit_day": row["time_exit_day"],
        "peak_pnl_pct": row.get("peak_pnl_pct"),
        "last_option_price": row.get("last_option_price"),
        "last_pnl_pct": row.get("last_pnl_pct"),
        "last_recommendation": row.get("last_recommendation"),
        "last_recommendation_reason": row.get("last_recommendation_reason"),
        "last_reviewed_at": _to_iso(row.get("last_reviewed_at")),
        "source_pick_snapshot": _load_json(row.get("source_pick_snapshot"), {}),
        "notes": row.get("notes"),
        "closed_at": _to_iso(row.get("closed_at")),
        "exit_option_price": row.get("exit_option_price"),
        "exit_execution_price": exit_execution_price,
        "exit_execution_basis": exit_execution_basis,
        "exit_reason": row.get("exit_reason"),
        "gross_pnl_pct": gross_pnl_pct,
        "net_pnl_pct": net_pnl_pct,
        "gross_pnl_usd": gross_pnl_usd,
        "net_pnl_usd": net_pnl_usd,
        "fee_total_usd": fee_total_usd,
        "created_at": _to_iso(row.get("created_at")),
        "updated_at": _to_iso(row.get("updated_at")),
        "latest_review": latest_review,
    }


def _source_snapshot_fee_sides(source_pick_snapshot: Any) -> int:
    snapshot = source_pick_snapshot
    if isinstance(snapshot, str):
        try:
            snapshot = json.loads(snapshot)
        except (json.JSONDecodeError, TypeError):
            snapshot = {}
    if not isinstance(snapshot, dict):
        snapshot = {}
    strategy_type = str(snapshot.get("strategy_type") or "").strip().lower()
    if (
        strategy_type == "vertical_spread"
        or snapshot.get("short_strike") is not None
        or bool(snapshot.get("short_contract_symbol"))
    ):
        return 2
    return 1


class SQLiteSuggestedTradesRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.is_available = True
        self.error_message: Optional[str] = None

    @contextlib.contextmanager
    def _connect(self):
        if not self.is_available:
            raise RuntimeError(self.error_message or "Suggested trades storage is unavailable.")
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> bool:
        schema_sql = """
        CREATE TABLE IF NOT EXISTS suggested_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT NOT NULL DEFAULT 'open',
            ticker TEXT NOT NULL,
            direction TEXT NOT NULL,
            contract_symbol TEXT,
            strike REAL NOT NULL,
            expiry TEXT NOT NULL,
            asset_class TEXT,
            contracts INTEGER NOT NULL,
            entry_option_price REAL NOT NULL,
            entry_execution_price REAL,
            entry_execution_basis TEXT,
            entry_fee_total_usd REAL,
            entry_underlying_price REAL,
            filled_at TEXT NOT NULL,
            stop_loss_pct REAL NOT NULL,
            profit_target_pct REAL NOT NULL,
            time_exit_day INTEGER NOT NULL,
            peak_pnl_pct REAL,
            last_option_price REAL,
            last_pnl_pct REAL,
            last_recommendation TEXT,
            last_recommendation_reason TEXT,
            last_reviewed_at TEXT,
            source_pick_snapshot TEXT NOT NULL,
            notes TEXT,
            closed_at TEXT,
            exit_option_price REAL,
            exit_execution_price REAL,
            exit_execution_basis TEXT,
            exit_reason TEXT,
            gross_pnl_pct REAL,
            net_pnl_pct REAL,
            gross_pnl_usd REAL,
            net_pnl_usd REAL,
            fee_total_usd REAL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_suggested_trades_status
            ON suggested_trades (status);
        CREATE INDEX IF NOT EXISTS idx_suggested_trades_filled_at
            ON suggested_trades (filled_at DESC);

        CREATE TABLE IF NOT EXISTS suggested_trade_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id INTEGER NOT NULL,
            reviewed_at TEXT NOT NULL,
            pricing_source TEXT,
            current_option_price REAL,
            current_pnl_pct REAL,
            gross_pnl_pct REAL,
            net_pnl_pct REAL,
            gross_pnl_usd REAL,
            net_pnl_usd REAL,
            entry_execution_price REAL,
            exit_execution_price REAL,
            entry_execution_basis TEXT,
            exit_execution_basis TEXT,
            fee_total_usd REAL,
            recommendation TEXT NOT NULL,
            reason TEXT NOT NULL,
            warnings TEXT NOT NULL DEFAULT '[]',
            metrics_snapshot TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (position_id) REFERENCES suggested_trades(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_suggested_trade_reviews_position_id
            ON suggested_trade_reviews (position_id, reviewed_at DESC, id DESC);
        """
        try:
            with self._connect() as conn:
                conn.executescript(schema_sql)
                suggested_trade_columns = {
                    "contract_symbol": "TEXT",
                    "entry_execution_price": "REAL",
                    "entry_execution_basis": "TEXT",
                    "entry_fee_total_usd": "REAL",
                    "entry_underlying_price": "REAL",
                    "exit_execution_price": "REAL",
                    "exit_execution_basis": "TEXT",
                    "gross_pnl_pct": "REAL",
                    "net_pnl_pct": "REAL",
                    "gross_pnl_usd": "REAL",
                    "net_pnl_usd": "REAL",
                    "fee_total_usd": "REAL",
                }
                review_columns = {
                    "gross_pnl_pct": "REAL",
                    "net_pnl_pct": "REAL",
                    "gross_pnl_usd": "REAL",
                    "net_pnl_usd": "REAL",
                    "entry_execution_price": "REAL",
                    "exit_execution_price": "REAL",
                    "entry_execution_basis": "TEXT",
                    "exit_execution_basis": "TEXT",
                    "fee_total_usd": "REAL",
                }
                for table_name, columns in (
                    ("suggested_trades", suggested_trade_columns),
                    ("suggested_trade_reviews", review_columns),
                ):
                    for column_name, column_type in columns.items():
                        try:
                            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
                        except sqlite3.OperationalError as exc:
                            if "duplicate column name" not in str(exc).lower():
                                raise
                apply_sqlite_repository_migrations(conn, SQLITE_SUGGESTED_TRADES_STORE_ID)
            return True
        except Exception as exc:
            self.is_available = False
            self.error_message = (
                "Suggested trades storage is unavailable. "
                f"Details: {exc}"
            )
            return False

    def _fetch_one_position(self, where_sql: str, params: tuple[Any, ...]) -> Optional[dict[str, Any]]:
        query = f"""
        SELECT
            p.*,
            r.id AS review_id,
            r.reviewed_at,
            r.pricing_source,
            r.current_option_price,
            r.current_pnl_pct,
            r.gross_pnl_pct AS review_gross_pnl_pct,
            r.net_pnl_pct AS review_net_pnl_pct,
            r.gross_pnl_usd AS review_gross_pnl_usd,
            r.net_pnl_usd AS review_net_pnl_usd,
            r.entry_execution_price AS review_entry_execution_price,
            r.exit_execution_price AS review_exit_execution_price,
            r.entry_execution_basis AS review_entry_execution_basis,
            r.exit_execution_basis AS review_exit_execution_basis,
            r.fee_total_usd AS review_fee_total_usd,
            r.recommendation,
            r.reason,
            r.warnings,
            r.metrics_snapshot
        FROM suggested_trades p
        LEFT JOIN suggested_trade_reviews r
            ON r.id = (
                SELECT pr.id
                FROM suggested_trade_reviews pr
                WHERE pr.position_id = p.id
                ORDER BY pr.reviewed_at DESC, pr.id DESC
                LIMIT 1
            )
        {where_sql}
        """
        with self._connect() as conn:
            row = conn.execute(query, params).fetchone()
        if not row:
            return None
        return _normalize_position_row(dict(row))

    def _fetch_position_by_id_in_conn(self, conn, position_id: int) -> Optional[dict[str, Any]]:
        query = """
        SELECT
            p.*,
            r.id AS review_id,
            r.reviewed_at,
            r.pricing_source,
            r.current_option_price,
            r.current_pnl_pct,
            r.gross_pnl_pct AS review_gross_pnl_pct,
            r.net_pnl_pct AS review_net_pnl_pct,
            r.gross_pnl_usd AS review_gross_pnl_usd,
            r.net_pnl_usd AS review_net_pnl_usd,
            r.entry_execution_price AS review_entry_execution_price,
            r.exit_execution_price AS review_exit_execution_price,
            r.entry_execution_basis AS review_entry_execution_basis,
            r.exit_execution_basis AS review_exit_execution_basis,
            r.fee_total_usd AS review_fee_total_usd,
            r.recommendation,
            r.reason,
            r.warnings,
            r.metrics_snapshot
        FROM suggested_trades p
        LEFT JOIN suggested_trade_reviews r
            ON r.id = (
                SELECT pr.id
                FROM suggested_trade_reviews pr
                WHERE pr.position_id = p.id
                ORDER BY pr.reviewed_at DESC, pr.id DESC
                LIMIT 1
            )
        WHERE p.id = ?
        """
        row = conn.execute(query, (position_id,)).fetchone()
        if not row:
            return None
        return _normalize_position_row(dict(row))

    def _serialize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        serialized = copy.deepcopy(payload)
        for key in ("expiry", "filled_at", "last_reviewed_at", "closed_at"):
            serialized[key] = _to_iso(serialized.get(key))
        serialized["source_pick_snapshot"] = json.dumps(serialized.get("source_pick_snapshot") or {})
        return serialized

    def create_position(self, payload: dict[str, Any]) -> dict[str, Any]:
        serialized = self._serialize_payload(payload)
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO suggested_trades (
                    status,
                    ticker,
                    direction,
                    contract_symbol,
                    strike,
                    expiry,
                    asset_class,
                    contracts,
                    entry_option_price,
                    entry_execution_price,
                    entry_execution_basis,
                    entry_fee_total_usd,
                    entry_underlying_price,
                    filled_at,
                    stop_loss_pct,
                    profit_target_pct,
                    time_exit_day,
                    peak_pnl_pct,
                    last_option_price,
                    last_pnl_pct,
                    last_recommendation,
                    last_recommendation_reason,
                    last_reviewed_at,
                    source_pick_snapshot,
                    notes,
                    closed_at,
                    exit_option_price,
                    exit_execution_price,
                    exit_execution_basis,
                    exit_reason,
                    gross_pnl_pct,
                    net_pnl_pct,
                    gross_pnl_usd,
                    net_pnl_usd,
                    fee_total_usd
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    serialized["status"],
                    serialized["ticker"],
                    serialized["direction"],
                    serialized.get("contract_symbol"),
                    serialized["strike"],
                    serialized["expiry"],
                    serialized.get("asset_class"),
                    serialized["contracts"],
                    serialized["entry_option_price"],
                    serialized.get("entry_execution_price"),
                    serialized.get("entry_execution_basis"),
                    serialized.get("entry_fee_total_usd"),
                    serialized.get("entry_underlying_price"),
                    serialized["filled_at"],
                    serialized["stop_loss_pct"],
                    serialized["profit_target_pct"],
                    serialized["time_exit_day"],
                    serialized.get("peak_pnl_pct"),
                    serialized.get("last_option_price"),
                    serialized.get("last_pnl_pct"),
                    serialized.get("last_recommendation"),
                    serialized.get("last_recommendation_reason"),
                    serialized.get("last_reviewed_at"),
                    serialized["source_pick_snapshot"],
                    serialized.get("notes"),
                    serialized.get("closed_at"),
                    serialized.get("exit_option_price"),
                    serialized.get("exit_execution_price"),
                    serialized.get("exit_execution_basis"),
                    serialized.get("exit_reason"),
                    serialized.get("gross_pnl_pct"),
                    serialized.get("net_pnl_pct"),
                    serialized.get("gross_pnl_usd"),
                    serialized.get("net_pnl_usd"),
                    serialized.get("fee_total_usd"),
                ),
            )
            position_id = int(cur.lastrowid)
            position = self._fetch_position_by_id_in_conn(conn, position_id)
            if position is None:
                raise RuntimeError(f"Suggested trade {position_id} was not found after creation.")
            return position

    def list_positions(
        self,
        status: Optional[str] = "open",
        *,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        where_sql = ""
        params: list[Any] = []
        if status in {"open", "closed"}:
            where_sql = "WHERE p.status = ?"
            params.append(status)
        window_sql = ""
        if limit is not None:
            window_sql = "LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        query = f"""
        SELECT
            p.*,
            r.id AS review_id,
            r.reviewed_at,
            r.pricing_source,
            r.current_option_price,
            r.current_pnl_pct,
            r.gross_pnl_pct AS review_gross_pnl_pct,
            r.net_pnl_pct AS review_net_pnl_pct,
            r.gross_pnl_usd AS review_gross_pnl_usd,
            r.net_pnl_usd AS review_net_pnl_usd,
            r.entry_execution_price AS review_entry_execution_price,
            r.exit_execution_price AS review_exit_execution_price,
            r.entry_execution_basis AS review_entry_execution_basis,
            r.exit_execution_basis AS review_exit_execution_basis,
            r.fee_total_usd AS review_fee_total_usd,
            r.recommendation,
            r.reason,
            r.warnings,
            r.metrics_snapshot
        FROM suggested_trades p
        LEFT JOIN suggested_trade_reviews r
            ON r.id = (
                SELECT pr.id
                FROM suggested_trade_reviews pr
                WHERE pr.position_id = p.id
                ORDER BY pr.reviewed_at DESC, pr.id DESC
                LIMIT 1
            )
        {where_sql}
        ORDER BY p.filled_at DESC, p.id DESC
        {window_sql}
        """
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_normalize_position_row(dict(row)) for row in rows]

    def get_position(self, position_id: int) -> Optional[dict[str, Any]]:
        return self._fetch_one_position("WHERE p.id = ?", (position_id,))

    def save_review(self, position_id: int, review: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as conn:
            status_row = conn.execute(
                "SELECT status FROM suggested_trades WHERE id = ?",
                (position_id,),
            ).fetchone()
            if not status_row:
                raise RuntimeError(f"Suggested trade {position_id} not found.")
            if str(status_row["status"]) != "open":
                raise ValueError(f"Suggested trade {position_id} is not open for review.")

            conn.execute(
                """
                INSERT INTO suggested_trade_reviews (
                    position_id,
                    reviewed_at,
                    pricing_source,
                    current_option_price,
                    current_pnl_pct,
                    gross_pnl_pct,
                    net_pnl_pct,
                    gross_pnl_usd,
                    net_pnl_usd,
                    entry_execution_price,
                    exit_execution_price,
                    entry_execution_basis,
                    exit_execution_basis,
                    fee_total_usd,
                    recommendation,
                    reason,
                    warnings,
                    metrics_snapshot
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    position_id,
                    _to_iso(review["reviewed_at"]),
                    review.get("pricing_source"),
                    review.get("current_option_price"),
                    review.get("current_pnl_pct"),
                    review.get("gross_pnl_pct"),
                    review.get("net_pnl_pct"),
                    review.get("gross_pnl_usd"),
                    review.get("net_pnl_usd"),
                    review.get("entry_execution_price"),
                    review.get("exit_execution_price"),
                    review.get("entry_execution_basis"),
                    review.get("exit_execution_basis"),
                    review.get("fee_total_usd"),
                    review["recommendation"],
                    review["reason"],
                    json.dumps(review.get("warnings") or []),
                    json.dumps(review.get("metrics_snapshot") or {}),
                ),
            )
            conn.execute(
                """
                UPDATE suggested_trades
                SET
                    peak_pnl_pct = ?,
                    last_option_price = ?,
                    last_pnl_pct = ?,
                    last_recommendation = ?,
                    last_recommendation_reason = ?,
                    exit_execution_price = ?,
                    exit_execution_basis = ?,
                    gross_pnl_pct = ?,
                    net_pnl_pct = ?,
                    gross_pnl_usd = ?,
                    net_pnl_usd = ?,
                    fee_total_usd = ?,
                    last_reviewed_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    review.get("peak_pnl_pct"),
                    review.get("current_option_price"),
                    review.get("current_pnl_pct"),
                    review["recommendation"],
                    review["reason"],
                    review.get("exit_execution_price"),
                    review.get("exit_execution_basis"),
                    review.get("gross_pnl_pct"),
                    review.get("net_pnl_pct"),
                    review.get("gross_pnl_usd"),
                    review.get("net_pnl_usd"),
                    review.get("fee_total_usd"),
                    _to_iso(review["reviewed_at"]),
                    _to_iso(review["reviewed_at"]),
                    position_id,
                ),
            )
            position = self._fetch_position_by_id_in_conn(conn, position_id)
            if position is None:
                raise RuntimeError(f"Suggested trade {position_id} was not found after review save.")
            return position

    def close_position(
        self,
        position_id: int,
        exit_price: float,
        closed_at: datetime,
        exit_reason: str,
        notes: Optional[str] = None,
        *,
        exit_execution_basis: str = "manual_close",
        allow_zero_exit_price: bool = False,
    ) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            exit_price_value = float(exit_price)
            if (
                not math.isfinite(exit_price_value)
                or exit_price_value < 0
                or (not allow_zero_exit_price and exit_price_value <= 0)
            ):
                comparator = "greater than or equal to 0" if allow_zero_exit_price else "greater than 0"
                raise ValueError(f"exit_price must be a finite number {comparator}.")
            existing = self._fetch_position_by_id_in_conn(conn, position_id)
            if existing is None:
                return None
            if str(existing.get("status") or "").strip().lower() != "open":
                raise ValueError(f"Suggested trade {position_id} is already closed.")
            merged_notes = existing.get("notes")
            if notes:
                merged_notes = f"{merged_notes}\n{notes}".strip() if merged_notes else notes
            closed_at_iso = _to_iso(closed_at)
            contracts = int(existing.get("contracts") or 1)
            entry_execution_price = existing.get("entry_execution_price") or existing.get("entry_option_price")
            fee_sides = _source_snapshot_fee_sides(existing.get("source_pick_snapshot"))
            entry_fee_total_usd = existing.get("entry_fee_total_usd")
            if entry_fee_total_usd is None:
                entry_fee_total_usd = commission_total_usd(contracts=contracts, sides=fee_sides)
            exit_fee_total_usd = commission_total_usd(contracts=contracts, sides=fee_sides)
            pnl_snapshot = option_pnl_snapshot(
                entry_execution_price=entry_execution_price,
                exit_execution_price=exit_price_value,
                contracts=contracts,
                entry_fee_total_usd=entry_fee_total_usd,
                exit_fee_total_usd=exit_fee_total_usd,
            )
            cursor = conn.execute(
                """
                UPDATE suggested_trades
                SET
                    status = ?,
                    closed_at = ?,
                    exit_option_price = ?,
                    exit_execution_price = ?,
                    exit_execution_basis = ?,
                    exit_reason = ?,
                    last_option_price = ?,
                    last_pnl_pct = ?,
                    gross_pnl_pct = ?,
                    net_pnl_pct = ?,
                    gross_pnl_usd = ?,
                    net_pnl_usd = ?,
                    fee_total_usd = ?,
                    last_reviewed_at = ?,
                    last_recommendation = ?,
                    last_recommendation_reason = ?,
                    notes = ?,
                    updated_at = ?
                WHERE id = ? AND status = 'open'
                """,
                (
                    "closed",
                    closed_at_iso,
                    exit_price_value,
                    exit_price_value,
                    exit_execution_basis,
                    exit_reason,
                    exit_price_value,
                    pnl_snapshot.get("gross_pnl_pct"),
                    pnl_snapshot.get("gross_pnl_pct"),
                    pnl_snapshot.get("net_pnl_pct"),
                    pnl_snapshot.get("gross_pnl_usd"),
                    pnl_snapshot.get("net_pnl_usd"),
                    pnl_snapshot.get("fee_total_usd"),
                    closed_at_iso,
                    "SELL",
                    exit_reason,
                    merged_notes,
                    closed_at_iso,
                    position_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"Suggested trade {position_id} is already closed.")
            position = self._fetch_position_by_id_in_conn(conn, position_id)
            if position is None:
                raise RuntimeError(f"Suggested trade {position_id} was not found after close.")
            return position


def create_suggested_trades_repository(db_path: str) -> SuggestedTradesRepository:
    repo = SQLiteSuggestedTradesRepository(db_path)
    repo.init_schema()
    return repo
