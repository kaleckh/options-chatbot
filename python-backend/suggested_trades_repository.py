from __future__ import annotations

import copy
import json
import sqlite3
from datetime import date, datetime
from typing import Any, Optional


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
        "recommendation": row.get("recommendation"),
        "reason": row.get("reason"),
        "warnings": _load_json(row.get("warnings"), []),
        "metrics_snapshot": _load_json(row.get("metrics_snapshot"), {}),
    }


def _normalize_position_row(row: dict[str, Any]) -> dict[str, Any]:
    latest_review = _normalize_latest_review(row)
    return {
        "id": row["id"],
        "status": row["status"],
        "ticker": row["ticker"],
        "direction": row["direction"],
        "strike": row["strike"],
        "expiry": _to_iso(row["expiry"]),
        "asset_class": row.get("asset_class"),
        "contracts": row["contracts"],
        "entry_option_price": row["entry_option_price"],
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
        "exit_reason": row.get("exit_reason"),
        "created_at": _to_iso(row.get("created_at")),
        "updated_at": _to_iso(row.get("updated_at")),
        "latest_review": latest_review,
    }


class SQLiteSuggestedTradesRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.is_available = True
        self.error_message: Optional[str] = None

    def _connect(self):
        if not self.is_available:
            raise RuntimeError(self.error_message or "Suggested trades storage is unavailable.")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> bool:
        schema_sql = """
        CREATE TABLE IF NOT EXISTS suggested_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT NOT NULL DEFAULT 'open',
            ticker TEXT NOT NULL,
            direction TEXT NOT NULL,
            strike REAL NOT NULL,
            expiry TEXT NOT NULL,
            asset_class TEXT,
            contracts INTEGER NOT NULL,
            entry_option_price REAL NOT NULL,
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
            exit_reason TEXT,
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
                    strike,
                    expiry,
                    asset_class,
                    contracts,
                    entry_option_price,
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
                    exit_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    serialized["status"],
                    serialized["ticker"],
                    serialized["direction"],
                    serialized["strike"],
                    serialized["expiry"],
                    serialized.get("asset_class"),
                    serialized["contracts"],
                    serialized["entry_option_price"],
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
                    serialized.get("exit_reason"),
                ),
            )
            position_id = int(cur.lastrowid)
        position = self.get_position(position_id)
        if position is None:
            raise RuntimeError(f"Suggested trade {position_id} was not found after creation.")
        return position

    def list_positions(self, status: Optional[str] = "open") -> list[dict[str, Any]]:
        where_sql = ""
        params: tuple[Any, ...] = ()
        if status in {"open", "closed"}:
            where_sql = "WHERE p.status = ?"
            params = (status,)
        query = f"""
        SELECT
            p.*,
            r.id AS review_id,
            r.reviewed_at,
            r.pricing_source,
            r.current_option_price,
            r.current_pnl_pct,
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
        """
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_normalize_position_row(dict(row)) for row in rows]

    def get_position(self, position_id: int) -> Optional[dict[str, Any]]:
        return self._fetch_one_position("WHERE p.id = ?", (position_id,))

    def save_review(self, position_id: int, review: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO suggested_trade_reviews (
                    position_id,
                    reviewed_at,
                    pricing_source,
                    current_option_price,
                    current_pnl_pct,
                    recommendation,
                    reason,
                    warnings,
                    metrics_snapshot
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    position_id,
                    _to_iso(review["reviewed_at"]),
                    review.get("pricing_source"),
                    review.get("current_option_price"),
                    review.get("current_pnl_pct"),
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
                    _to_iso(review["reviewed_at"]),
                    _to_iso(review["reviewed_at"]),
                    position_id,
                ),
            )
        position = self.get_position(position_id)
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
    ) -> Optional[dict[str, Any]]:
        existing = self.get_position(position_id)
        if existing is None:
            return None
        merged_notes = existing.get("notes")
        if notes:
            merged_notes = f"{merged_notes}\n{notes}".strip() if merged_notes else notes
        closed_at_iso = _to_iso(closed_at)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE suggested_trades
                SET
                    status = ?,
                    closed_at = ?,
                    exit_option_price = ?,
                    exit_reason = ?,
                    notes = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    "closed",
                    closed_at_iso,
                    exit_price,
                    exit_reason,
                    merged_notes,
                    closed_at_iso,
                    position_id,
                ),
            )
        return self.get_position(position_id)


def create_suggested_trades_repository(db_path: str):
    repo = SQLiteSuggestedTradesRepository(db_path)
    repo.init_schema()
    return repo
