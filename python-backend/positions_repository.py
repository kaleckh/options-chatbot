from __future__ import annotations

import copy
import contextlib
import json
import math
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from options_execution import commission_total_usd, option_pnl_snapshot


def _to_iso(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


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
        "warnings": copy.deepcopy(row.get("warnings") or []),
        "metrics_snapshot": copy.deepcopy(row.get("metrics_snapshot") or {}),
    }


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _closed_position_review(row: dict[str, Any], existing: Optional[dict[str, Any]]) -> dict[str, Any]:
    existing = existing or {}
    metrics_snapshot = copy.deepcopy(existing.get("metrics_snapshot") or {})
    metrics_snapshot.update(
        {
            "pricing_state": "closed",
            "exit_reason": row.get("exit_reason"),
            "closed_at": _to_iso(row.get("closed_at")),
        }
    )
    return {
        "id": existing.get("id"),
        "reviewed_at": _to_iso(
            _first_present(row.get("closed_at"), row.get("last_reviewed_at"), existing.get("reviewed_at"))
        ),
        "pricing_source": _first_present(row.get("exit_execution_basis"), row.get("exit_reason"), existing.get("pricing_source")),
        "current_option_price": _first_present(row.get("exit_option_price"), row.get("last_option_price"), existing.get("current_option_price")),
        "current_pnl_pct": _first_present(row.get("gross_pnl_pct"), row.get("last_pnl_pct"), existing.get("current_pnl_pct")),
        "gross_pnl_pct": _first_present(row.get("gross_pnl_pct"), existing.get("gross_pnl_pct")),
        "net_pnl_pct": _first_present(row.get("net_pnl_pct"), existing.get("net_pnl_pct")),
        "gross_pnl_usd": _first_present(row.get("gross_pnl_usd"), existing.get("gross_pnl_usd")),
        "net_pnl_usd": _first_present(row.get("net_pnl_usd"), existing.get("net_pnl_usd")),
        "entry_execution_price": _first_present(row.get("entry_execution_price"), existing.get("entry_execution_price")),
        "exit_execution_price": _first_present(row.get("exit_execution_price"), existing.get("exit_execution_price")),
        "entry_execution_basis": _first_present(row.get("entry_execution_basis"), existing.get("entry_execution_basis")),
        "exit_execution_basis": _first_present(row.get("exit_execution_basis"), existing.get("exit_execution_basis")),
        "fee_total_usd": _first_present(row.get("fee_total_usd"), existing.get("fee_total_usd")),
        "recommendation": "SELL",
        "reason": _first_present(row.get("exit_reason"), row.get("last_recommendation_reason"), existing.get("reason"), "Position closed."),
        "warnings": [],
        "metrics_snapshot": metrics_snapshot,
    }


def _normalize_position_row(row: dict[str, Any]) -> dict[str, Any]:
    latest_review = _normalize_latest_review(row)
    if str(row.get("status") or "").strip().lower() == "closed" and row.get("closed_at") is not None:
        latest_review = _closed_position_review(row, latest_review)
    gross_pnl_pct = row.get("gross_pnl_pct")
    net_pnl_pct = row.get("net_pnl_pct")
    gross_pnl_usd = row.get("gross_pnl_usd")
    net_pnl_usd = row.get("net_pnl_usd")
    fee_total_usd = row.get("fee_total_usd")
    exit_execution_price = row.get("exit_execution_price")
    exit_execution_basis = row.get("exit_execution_basis")
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
    normalized = {
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
        "source_pick_snapshot": copy.deepcopy(row.get("source_pick_snapshot") or {}),
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
        "source_scan_session_id": row.get("source_scan_session_id"),
        "source_scan_event_key": row.get("source_scan_event_key"),
        "source_scan_run_id": row.get("source_scan_run_id"),
        "source_scan_recorded_at_utc": _to_iso(row.get("source_scan_recorded_at_utc")),
        "proof_eligible": bool(row.get("proof_eligible", False)),
        "proof_ineligibility_reason": row.get("proof_ineligibility_reason"),
        "proof_class": row.get("proof_class"),
        "proof_class_reason": row.get("proof_class_reason"),
        "created_at": _to_iso(row.get("created_at")),
        "updated_at": _to_iso(row.get("updated_at")),
        "latest_review": latest_review,
    }
    return normalized


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


def _position_fee_sides(position: dict[str, Any]) -> int:
    return _source_snapshot_fee_sides(position.get("source_pick_snapshot"))


_POSITION_UPDATE_FIELDS = (
    "contract_symbol",
    "strike",
    "expiry",
    "filled_at",
    "entry_option_price",
    "entry_execution_price",
    "entry_execution_basis",
    "entry_fee_total_usd",
    "entry_underlying_price",
    "source_pick_snapshot",
    "notes",
    "source_scan_session_id",
    "source_scan_event_key",
    "source_scan_run_id",
    "source_scan_recorded_at_utc",
    "proof_eligible",
    "proof_ineligibility_reason",
    "proof_class",
    "proof_class_reason",
)


class UnavailableTrackedPositionsRepository:
    def __init__(self, error_message: str):
        self.error_message = error_message
        self.is_available = False

    def init_schema(self) -> bool:
        return False

    def create_position(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError(self.error_message)

    def list_positions(self, status: Optional[str] = "open") -> list[dict[str, Any]]:
        raise RuntimeError(self.error_message)

    def get_position(self, position_id: int) -> Optional[dict[str, Any]]:
        raise RuntimeError(self.error_message)

    def save_review(self, position_id: int, review: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError(self.error_message)

    def update_position(self, position_id: int, updates: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError(self.error_message)

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
        raise RuntimeError(self.error_message)

    def get_realized_pnl_since(self, since: datetime) -> float:
        return 0.0


class PostgresTrackedPositionsRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.is_available = True
        self.error_message: Optional[str] = None
        self._psycopg = None
        self._dict_row = None
        try:
            import psycopg  # type: ignore
            from psycopg.rows import dict_row  # type: ignore

            self._psycopg = psycopg
            self._dict_row = dict_row
        except Exception as exc:
            self.is_available = False
            self.error_message = (
                "Tracked positions require psycopg and a valid DATABASE_URL. "
                f"Import failed: {exc}"
            )

    def _connect(self):
        if not self.is_available or self._psycopg is None or self._dict_row is None:
            raise RuntimeError(self.error_message or "Tracked positions storage is unavailable.")
        return self._psycopg.connect(self.database_url, row_factory=self._dict_row)

    def init_schema(self) -> bool:
        if not self.is_available:
            return False
        schema_sql = """
        CREATE TABLE IF NOT EXISTS tracked_positions (
            id BIGSERIAL PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'open',
            ticker TEXT NOT NULL,
            direction TEXT NOT NULL,
            contract_symbol TEXT,
            strike DOUBLE PRECISION NOT NULL,
            expiry DATE NOT NULL,
            asset_class TEXT,
            contracts INTEGER NOT NULL,
            entry_option_price DOUBLE PRECISION NOT NULL,
            entry_execution_price DOUBLE PRECISION,
            entry_execution_basis TEXT,
            entry_fee_total_usd DOUBLE PRECISION,
            entry_underlying_price DOUBLE PRECISION,
            filled_at TIMESTAMPTZ NOT NULL,
            stop_loss_pct DOUBLE PRECISION NOT NULL,
            profit_target_pct DOUBLE PRECISION NOT NULL,
            time_exit_day INTEGER NOT NULL,
            peak_pnl_pct DOUBLE PRECISION,
            last_option_price DOUBLE PRECISION,
            last_pnl_pct DOUBLE PRECISION,
            last_recommendation TEXT,
            last_recommendation_reason TEXT,
            last_reviewed_at TIMESTAMPTZ,
            source_pick_snapshot JSONB NOT NULL,
            notes TEXT,
            closed_at TIMESTAMPTZ,
            exit_option_price DOUBLE PRECISION,
            exit_execution_price DOUBLE PRECISION,
            exit_execution_basis TEXT,
            exit_reason TEXT,
            gross_pnl_pct DOUBLE PRECISION,
            net_pnl_pct DOUBLE PRECISION,
            gross_pnl_usd DOUBLE PRECISION,
            net_pnl_usd DOUBLE PRECISION,
            fee_total_usd DOUBLE PRECISION,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        ALTER TABLE tracked_positions
        ADD COLUMN IF NOT EXISTS contract_symbol TEXT;
        ALTER TABLE tracked_positions
        ADD COLUMN IF NOT EXISTS entry_execution_price DOUBLE PRECISION;
        ALTER TABLE tracked_positions
        ADD COLUMN IF NOT EXISTS entry_execution_basis TEXT;
        ALTER TABLE tracked_positions
        ADD COLUMN IF NOT EXISTS entry_fee_total_usd DOUBLE PRECISION;
        ALTER TABLE tracked_positions
        ADD COLUMN IF NOT EXISTS entry_underlying_price DOUBLE PRECISION;
        ALTER TABLE tracked_positions
        ADD COLUMN IF NOT EXISTS exit_execution_price DOUBLE PRECISION;
        ALTER TABLE tracked_positions
        ADD COLUMN IF NOT EXISTS exit_execution_basis TEXT;
        ALTER TABLE tracked_positions
        ADD COLUMN IF NOT EXISTS gross_pnl_pct DOUBLE PRECISION;
        ALTER TABLE tracked_positions
        ADD COLUMN IF NOT EXISTS net_pnl_pct DOUBLE PRECISION;
        ALTER TABLE tracked_positions
        ADD COLUMN IF NOT EXISTS gross_pnl_usd DOUBLE PRECISION;
        ALTER TABLE tracked_positions
        ADD COLUMN IF NOT EXISTS net_pnl_usd DOUBLE PRECISION;
        ALTER TABLE tracked_positions
        ADD COLUMN IF NOT EXISTS fee_total_usd DOUBLE PRECISION;

        ALTER TABLE tracked_positions
        ADD COLUMN IF NOT EXISTS source_scan_session_id BIGINT;
        ALTER TABLE tracked_positions
        ADD COLUMN IF NOT EXISTS source_scan_event_key TEXT;
        ALTER TABLE tracked_positions
        ADD COLUMN IF NOT EXISTS source_scan_run_id TEXT;
        ALTER TABLE tracked_positions
        ADD COLUMN IF NOT EXISTS source_scan_recorded_at_utc TIMESTAMPTZ;
        ALTER TABLE tracked_positions
        ADD COLUMN IF NOT EXISTS proof_eligible BOOLEAN NOT NULL DEFAULT FALSE;
        ALTER TABLE tracked_positions
        ADD COLUMN IF NOT EXISTS proof_ineligibility_reason TEXT;
        ALTER TABLE tracked_positions
        ADD COLUMN IF NOT EXISTS proof_class TEXT;
        ALTER TABLE tracked_positions
        ADD COLUMN IF NOT EXISTS proof_class_reason TEXT;

        CREATE INDEX IF NOT EXISTS idx_tracked_positions_status ON tracked_positions (status);
        CREATE INDEX IF NOT EXISTS idx_tracked_positions_filled_at ON tracked_positions (filled_at DESC);

        CREATE TABLE IF NOT EXISTS position_reviews (
            id BIGSERIAL PRIMARY KEY,
            position_id BIGINT NOT NULL REFERENCES tracked_positions(id) ON DELETE CASCADE,
            reviewed_at TIMESTAMPTZ NOT NULL,
            pricing_source TEXT,
            current_option_price DOUBLE PRECISION,
            current_pnl_pct DOUBLE PRECISION,
            gross_pnl_pct DOUBLE PRECISION,
            net_pnl_pct DOUBLE PRECISION,
            gross_pnl_usd DOUBLE PRECISION,
            net_pnl_usd DOUBLE PRECISION,
            entry_execution_price DOUBLE PRECISION,
            exit_execution_price DOUBLE PRECISION,
            entry_execution_basis TEXT,
            exit_execution_basis TEXT,
            fee_total_usd DOUBLE PRECISION,
            recommendation TEXT NOT NULL,
            reason TEXT NOT NULL,
            warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
            metrics_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        ALTER TABLE position_reviews
        ADD COLUMN IF NOT EXISTS gross_pnl_pct DOUBLE PRECISION;

        ALTER TABLE position_reviews
        ADD COLUMN IF NOT EXISTS net_pnl_pct DOUBLE PRECISION;

        ALTER TABLE position_reviews
        ADD COLUMN IF NOT EXISTS gross_pnl_usd DOUBLE PRECISION;

        ALTER TABLE position_reviews
        ADD COLUMN IF NOT EXISTS net_pnl_usd DOUBLE PRECISION;

        ALTER TABLE position_reviews
        ADD COLUMN IF NOT EXISTS entry_execution_price DOUBLE PRECISION;

        ALTER TABLE position_reviews
        ADD COLUMN IF NOT EXISTS exit_execution_price DOUBLE PRECISION;

        ALTER TABLE position_reviews
        ADD COLUMN IF NOT EXISTS entry_execution_basis TEXT;

        ALTER TABLE position_reviews
        ADD COLUMN IF NOT EXISTS exit_execution_basis TEXT;

        ALTER TABLE position_reviews
        ADD COLUMN IF NOT EXISTS fee_total_usd DOUBLE PRECISION;

        ALTER TABLE position_reviews
        ADD COLUMN IF NOT EXISTS warnings JSONB NOT NULL DEFAULT '[]'::jsonb;

        ALTER TABLE position_reviews
        ADD COLUMN IF NOT EXISTS metrics_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb;

        CREATE INDEX IF NOT EXISTS idx_position_reviews_position_id ON position_reviews (position_id, reviewed_at DESC);
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(schema_sql)
            return True
        except Exception as exc:
            self.is_available = False
            self.error_message = (
                "Tracked positions database is unavailable. "
                f"Check DATABASE_URL and local Postgres. Details: {exc}"
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
        FROM tracked_positions p
        LEFT JOIN LATERAL (
            SELECT *
            FROM position_reviews pr
            WHERE pr.position_id = p.id
            ORDER BY pr.reviewed_at DESC, pr.id DESC
            LIMIT 1
        ) r ON TRUE
        {where_sql}
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                row = cur.fetchone()
        if not row:
            return None
        return _normalize_position_row(row)

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
        FROM tracked_positions p
        LEFT JOIN LATERAL (
            SELECT *
            FROM position_reviews pr
            WHERE pr.position_id = p.id
            ORDER BY pr.reviewed_at DESC, pr.id DESC
            LIMIT 1
        ) r ON TRUE
        WHERE p.id = %s
        """
        with conn.cursor() as cur:
            cur.execute(query, (position_id,))
            row = cur.fetchone()
        if not row:
            return None
        return _normalize_position_row(row)

    def create_position(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tracked_positions (
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
                        fee_total_usd,
                        source_scan_session_id,
                        source_scan_event_key,
                        source_scan_run_id,
                        source_scan_recorded_at_utc,
                        proof_eligible,
                        proof_ineligibility_reason,
                        proof_class,
                        proof_class_reason
                    ) VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s::jsonb,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    RETURNING id
                    """,
                    (
                        payload["status"],
                        payload["ticker"],
                        payload["direction"],
                        payload.get("contract_symbol"),
                        payload["strike"],
                        payload["expiry"],
                        payload.get("asset_class"),
                        payload["contracts"],
                        payload["entry_option_price"],
                        payload.get("entry_execution_price"),
                        payload.get("entry_execution_basis"),
                        payload.get("entry_fee_total_usd"),
                        payload.get("entry_underlying_price"),
                        payload["filled_at"],
                        payload["stop_loss_pct"],
                        payload["profit_target_pct"],
                        payload["time_exit_day"],
                        payload.get("peak_pnl_pct"),
                        payload.get("last_option_price"),
                        payload.get("last_pnl_pct"),
                        payload.get("last_recommendation"),
                        payload.get("last_recommendation_reason"),
                        payload.get("last_reviewed_at"),
                        json.dumps(payload.get("source_pick_snapshot") or {}),
                        payload.get("notes"),
                        payload.get("closed_at"),
                        payload.get("exit_option_price"),
                        payload.get("exit_execution_price"),
                        payload.get("exit_execution_basis"),
                        payload.get("exit_reason"),
                        payload.get("fee_total_usd"),
                        payload.get("source_scan_session_id"),
                        payload.get("source_scan_event_key"),
                        payload.get("source_scan_run_id"),
                        payload.get("source_scan_recorded_at_utc"),
                        bool(payload.get("proof_eligible", False)),
                        payload.get("proof_ineligibility_reason"),
                        payload.get("proof_class"),
                        payload.get("proof_class_reason"),
                    ),
                )
                row = cur.fetchone()
                if not row:
                    raise RuntimeError("Inserted tracked position was not returned.")
                position = self._fetch_position_by_id_in_conn(conn, int(row["id"]))
        if position is None:
            raise RuntimeError(f"Tracked position {int(row['id'])} was not found after creation.")
        return position

    def list_positions(self, status: Optional[str] = "open") -> list[dict[str, Any]]:
        where_sql = ""
        params: tuple[Any, ...] = ()
        if status in {"open", "closed"}:
            where_sql = "WHERE p.status = %s"
            params = (status,)
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
        FROM tracked_positions p
        LEFT JOIN LATERAL (
            SELECT *
            FROM position_reviews pr
            WHERE pr.position_id = p.id
            ORDER BY pr.reviewed_at DESC, pr.id DESC
            LIMIT 1
        ) r ON TRUE
        {where_sql}
        ORDER BY p.filled_at DESC, p.id DESC
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
        return [_normalize_position_row(row) for row in rows]

    def get_position(self, position_id: int) -> Optional[dict[str, Any]]:
        return self._fetch_one_position("WHERE p.id = %s", (position_id,))

    def update_position(self, position_id: int, updates: dict[str, Any]) -> dict[str, Any]:
        assignments: list[str] = []
        params: list[Any] = []
        for field in _POSITION_UPDATE_FIELDS:
            if field not in updates:
                continue
            if field == "source_pick_snapshot":
                assignments.append("source_pick_snapshot = %s::jsonb")
                params.append(json.dumps(updates.get(field) or {}))
                continue
            if field in {"expiry", "filled_at"}:
                assignments.append("expiry = %s")
                if field == "filled_at":
                    assignments[-1] = "filled_at = %s"
                params.append(_to_iso(updates.get(field)))
                continue
            if field == "proof_eligible":
                assignments.append("proof_eligible = %s")
                params.append(bool(updates.get(field)))
                continue
            assignments.append(f"{field} = %s")
            params.append(updates.get(field))

        if not assignments:
            position = self.get_position(position_id)
            if position is None:
                raise RuntimeError(f"Tracked position {position_id} not found.")
            return position

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM tracked_positions WHERE id = %s", (position_id,))
                if not cur.fetchone():
                    raise RuntimeError(f"Tracked position {position_id} not found.")
                cur.execute(
                    f"""
                    UPDATE tracked_positions
                    SET {", ".join(assignments)},
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (*params, position_id),
                )
                position = self._fetch_position_by_id_in_conn(conn, position_id)
        if position is None:
            raise RuntimeError(f"Tracked position {position_id} was not found after update.")
        return position

    def save_review(self, position_id: int, review: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM tracked_positions WHERE id = %s", (position_id,))
                status_row = cur.fetchone()
                if not status_row:
                    raise RuntimeError(f"Tracked position {position_id} not found.")
                if str(status_row["status"]) != "open":
                    raise ValueError(f"Tracked position {position_id} is not open for review.")

                cur.execute(
                    """
                    INSERT INTO position_reviews (
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
                    ) VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s::jsonb,
                        %s::jsonb
                    )
                    """,
                    (
                        position_id,
                        review["reviewed_at"],
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
                cur.execute(
                    """
                    UPDATE tracked_positions
                    SET
                        peak_pnl_pct = %s,
                        last_option_price = %s,
                        last_pnl_pct = %s,
                        last_recommendation = %s,
                        last_recommendation_reason = %s,
                        exit_execution_price = %s,
                        exit_execution_basis = %s,
                        gross_pnl_pct = %s,
                        net_pnl_pct = %s,
                        gross_pnl_usd = %s,
                        net_pnl_usd = %s,
                        fee_total_usd = %s,
                        last_reviewed_at = %s,
                        updated_at = NOW()
                    WHERE id = %s
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
                        review["reviewed_at"],
                        position_id,
                    ),
                )
                position = self._fetch_position_by_id_in_conn(conn, position_id)
                if position is None:
                    raise RuntimeError(f"Tracked position {position_id} was not found after review save.")
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
            with conn.cursor() as cur:
                exit_price_value = float(exit_price)
                if (
                    not math.isfinite(exit_price_value)
                    or exit_price_value < 0
                    or (not allow_zero_exit_price and exit_price_value <= 0)
                ):
                    comparator = "greater than or equal to 0" if allow_zero_exit_price else "greater than 0"
                    raise ValueError(f"exit_price must be a finite number {comparator}.")

                cur.execute(
                    """
                    SELECT status, contracts, entry_execution_price, entry_option_price, entry_fee_total_usd, source_pick_snapshot
                    FROM tracked_positions
                    WHERE id = %s
                    """,
                    (position_id,),
                )
                status_row = cur.fetchone()
                if not status_row:
                    return None
                if str(status_row["status"]) != "open":
                    raise ValueError(f"Tracked position {position_id} is already closed.")
                contracts = int(status_row.get("contracts") or 1)
                entry_execution_price = status_row.get("entry_execution_price") or status_row.get("entry_option_price")
                entry_fee_total_usd = status_row.get("entry_fee_total_usd")
                fee_sides = _source_snapshot_fee_sides(status_row.get("source_pick_snapshot"))
                if entry_fee_total_usd is None:
                    entry_fee_total_usd = commission_total_usd(contracts=contracts, sides=fee_sides)
                exit_fee_total_usd = commission_total_usd(contracts=contracts, sides=fee_sides)
                pnl_snapshot = option_pnl_snapshot(
                    entry_execution_price=entry_execution_price,
                    exit_execution_price=exit_price,
                    contracts=contracts,
                    entry_fee_total_usd=entry_fee_total_usd,
                    exit_fee_total_usd=exit_fee_total_usd,
                )
                merged_notes = None
                if notes:
                    cur.execute("SELECT notes FROM tracked_positions WHERE id = %s", (position_id,))
                    existing_row = cur.fetchone()
                    existing_notes = existing_row.get("notes") if existing_row else None
                    merged_notes = f"{existing_notes}\n{notes}".strip() if existing_notes else notes

                cur.execute(
                    """
                    UPDATE tracked_positions
                    SET
                        status = 'closed',
                        closed_at = %s,
                        exit_option_price = %s,
                        exit_execution_price = %s,
                        exit_execution_basis = %s,
                        exit_reason = %s,
                        last_option_price = %s,
                        last_pnl_pct = %s,
                        gross_pnl_pct = %s,
                        net_pnl_pct = %s,
                        gross_pnl_usd = %s,
                        net_pnl_usd = %s,
                        fee_total_usd = %s,
                        last_reviewed_at = %s,
                        last_recommendation = %s,
                        last_recommendation_reason = %s,
                        notes = COALESCE(%s, notes),
                        updated_at = NOW()
                    WHERE id = %s AND status = 'open'
                    RETURNING id
                    """,
                    (
                        closed_at,
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
                        closed_at,
                        "SELL",
                        exit_reason,
                        merged_notes,
                        position_id,
                    ),
                )
                row = cur.fetchone()
                if not row:
                    return None
                position = self._fetch_position_by_id_in_conn(conn, position_id)
                if position is None:
                    raise RuntimeError(f"Tracked position {position_id} was not found after close.")
                return position

    def get_realized_pnl_since(self, since: datetime) -> float:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COALESCE(SUM(net_pnl_usd), 0) AS total_pnl_usd
                    FROM tracked_positions
                    WHERE status = 'closed' AND closed_at >= %s
                    """,
                    (since,),
                )
                row = cur.fetchone()
                return float(row["total_pnl_usd"]) if row else 0.0


class SqliteTrackedPositionsRepository:
    """SQLite-backed tracked positions repository (fallback when Postgres is unavailable)."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            project_root = Path(__file__).resolve().parent.parent
            db_dir = project_root / "data"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(db_dir / "tracked_positions.db")
        self.db_path = db_path
        self.is_available = True
        self.error_message: Optional[str] = None

    @contextlib.contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
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
        CREATE TABLE IF NOT EXISTS tracked_positions (
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
            source_pick_snapshot TEXT NOT NULL DEFAULT '{}',
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
            source_scan_session_id INTEGER,
            source_scan_event_key TEXT,
            source_scan_run_id TEXT,
            source_scan_recorded_at_utc TEXT,
            proof_eligible INTEGER NOT NULL DEFAULT 0,
            proof_ineligibility_reason TEXT,
            proof_class TEXT,
            proof_class_reason TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_tracked_positions_status ON tracked_positions (status);
        CREATE INDEX IF NOT EXISTS idx_tracked_positions_filled_at ON tracked_positions (filled_at DESC);

        CREATE TABLE IF NOT EXISTS position_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id INTEGER NOT NULL REFERENCES tracked_positions(id) ON DELETE CASCADE,
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
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_position_reviews_position_id ON position_reviews (position_id, reviewed_at DESC);
        """
        try:
            with self._connect() as conn:
                conn.executescript(schema_sql)
                tracked_position_columns = {
                    "contract_symbol": "TEXT",
                    "asset_class": "TEXT",
                    "entry_execution_price": "REAL",
                    "entry_execution_basis": "TEXT",
                    "entry_fee_total_usd": "REAL",
                    "entry_underlying_price": "REAL",
                    "peak_pnl_pct": "REAL",
                    "last_option_price": "REAL",
                    "last_pnl_pct": "REAL",
                    "last_recommendation": "TEXT",
                    "last_recommendation_reason": "TEXT",
                    "last_reviewed_at": "TEXT",
                    "notes": "TEXT",
                    "closed_at": "TEXT",
                    "exit_option_price": "REAL",
                    "exit_execution_price": "REAL",
                    "exit_execution_basis": "TEXT",
                    "exit_reason": "TEXT",
                    "gross_pnl_pct": "REAL",
                    "net_pnl_pct": "REAL",
                    "gross_pnl_usd": "REAL",
                    "net_pnl_usd": "REAL",
                    "fee_total_usd": "REAL",
                    "source_scan_session_id": "INTEGER",
                    "source_scan_event_key": "TEXT",
                    "source_scan_run_id": "TEXT",
                    "source_scan_recorded_at_utc": "TEXT",
                    "proof_eligible": "INTEGER NOT NULL DEFAULT 0",
                    "proof_ineligibility_reason": "TEXT",
                    "proof_class": "TEXT",
                    "proof_class_reason": "TEXT",
                }
                position_review_columns = {
                    "gross_pnl_pct": "REAL",
                    "net_pnl_pct": "REAL",
                    "gross_pnl_usd": "REAL",
                    "net_pnl_usd": "REAL",
                    "entry_execution_price": "REAL",
                    "exit_execution_price": "REAL",
                    "entry_execution_basis": "TEXT",
                    "exit_execution_basis": "TEXT",
                    "fee_total_usd": "REAL",
                    "warnings": "TEXT NOT NULL DEFAULT '[]'",
                    "metrics_snapshot": "TEXT NOT NULL DEFAULT '{}'",
                }
                for table_name, columns in (
                    ("tracked_positions", tracked_position_columns),
                    ("position_reviews", position_review_columns),
                ):
                    for column_name, column_type in columns.items():
                        try:
                            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
                        except sqlite3.OperationalError as exc:
                            if "duplicate column name" not in str(exc).lower():
                                raise
            return True
        except Exception as exc:
            self.is_available = False
            self.error_message = (
                "SQLite tracked positions database is unavailable. "
                f"Details: {exc}"
            )
            return False

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """Convert a sqlite3.Row to a dict, parsing JSON text columns."""
        d = dict(row)
        for key in ("source_pick_snapshot", "warnings", "metrics_snapshot"):
            if key in d and isinstance(d[key], str):
                try:
                    d[key] = json.loads(d[key])
                except (json.JSONDecodeError, TypeError):
                    pass
        if "proof_eligible" in d:
            d["proof_eligible"] = bool(d["proof_eligible"])
        return d

    _POSITION_WITH_LATEST_REVIEW_SQL = """
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
        FROM tracked_positions p
        LEFT JOIN position_reviews r ON r.id = (
            SELECT pr.id
            FROM position_reviews pr
            WHERE pr.position_id = p.id
            ORDER BY pr.reviewed_at DESC, pr.id DESC
            LIMIT 1
        )
    """

    def _fetch_one_position(self, where_sql: str, params: tuple[Any, ...]) -> Optional[dict[str, Any]]:
        query = f"{self._POSITION_WITH_LATEST_REVIEW_SQL} {where_sql}"
        with self._connect() as conn:
            cur = conn.execute(query, params)
            row = cur.fetchone()
        if not row:
            return None
        return _normalize_position_row(self._row_to_dict(row))

    def _fetch_position_by_id_in_conn(self, conn: sqlite3.Connection, position_id: int) -> Optional[dict[str, Any]]:
        query = f"{self._POSITION_WITH_LATEST_REVIEW_SQL} WHERE p.id = ?"
        cur = conn.execute(query, (position_id,))
        row = cur.fetchone()
        if not row:
            return None
        return _normalize_position_row(self._row_to_dict(row))

    def create_position(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO tracked_positions (
                    status, ticker, direction, contract_symbol, strike, expiry,
                    asset_class, contracts, entry_option_price, entry_execution_price,
                    entry_execution_basis, entry_fee_total_usd, entry_underlying_price,
                    filled_at, stop_loss_pct, profit_target_pct, time_exit_day,
                    peak_pnl_pct, last_option_price, last_pnl_pct,
                    last_recommendation, last_recommendation_reason, last_reviewed_at,
                    source_pick_snapshot, notes, closed_at, exit_option_price,
                    exit_execution_price, exit_execution_basis, exit_reason,
                    fee_total_usd, source_scan_session_id, source_scan_event_key,
                    source_scan_run_id, source_scan_recorded_at_utc,
                    proof_eligible, proof_ineligibility_reason, proof_class, proof_class_reason
                ) VALUES (
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?,
                    ?, ?,
                    ?, ?
                )
                """,
                (
                    payload["status"],
                    payload["ticker"],
                    payload["direction"],
                    payload.get("contract_symbol"),
                    payload["strike"],
                    _to_iso(payload["expiry"]),
                    payload.get("asset_class"),
                    payload["contracts"],
                    payload["entry_option_price"],
                    payload.get("entry_execution_price"),
                    payload.get("entry_execution_basis"),
                    payload.get("entry_fee_total_usd"),
                    payload.get("entry_underlying_price"),
                    _to_iso(payload["filled_at"]),
                    payload["stop_loss_pct"],
                    payload["profit_target_pct"],
                    payload["time_exit_day"],
                    payload.get("peak_pnl_pct"),
                    payload.get("last_option_price"),
                    payload.get("last_pnl_pct"),
                    payload.get("last_recommendation"),
                    payload.get("last_recommendation_reason"),
                    _to_iso(payload.get("last_reviewed_at")),
                    json.dumps(payload.get("source_pick_snapshot") or {}),
                    payload.get("notes"),
                    _to_iso(payload.get("closed_at")),
                    payload.get("exit_option_price"),
                    payload.get("exit_execution_price"),
                    payload.get("exit_execution_basis"),
                    payload.get("exit_reason"),
                    payload.get("fee_total_usd"),
                    payload.get("source_scan_session_id"),
                    payload.get("source_scan_event_key"),
                    payload.get("source_scan_run_id"),
                    _to_iso(payload.get("source_scan_recorded_at_utc")),
                    1 if payload.get("proof_eligible") else 0,
                    payload.get("proof_ineligibility_reason"),
                    payload.get("proof_class"),
                    payload.get("proof_class_reason"),
                ),
            )
            position_id = cur.lastrowid
            position = self._fetch_position_by_id_in_conn(conn, position_id)
        if position is None:
            raise RuntimeError(f"Tracked position {position_id} was not found after creation.")
        return position

    def list_positions(self, status: Optional[str] = "open") -> list[dict[str, Any]]:
        where_sql = ""
        params: tuple[Any, ...] = ()
        if status in {"open", "closed"}:
            where_sql = "WHERE p.status = ?"
            params = (status,)
        query = f"""
        {self._POSITION_WITH_LATEST_REVIEW_SQL}
        {where_sql}
        ORDER BY p.filled_at DESC, p.id DESC
        """
        with self._connect() as conn:
            cur = conn.execute(query, params)
            rows = cur.fetchall()
        return [_normalize_position_row(self._row_to_dict(row)) for row in rows]

    def get_position(self, position_id: int) -> Optional[dict[str, Any]]:
        return self._fetch_one_position("WHERE p.id = ?", (position_id,))

    def update_position(self, position_id: int, updates: dict[str, Any]) -> dict[str, Any]:
        assignments: list[str] = []
        params: list[Any] = []
        for field in _POSITION_UPDATE_FIELDS:
            if field not in updates:
                continue
            assignments.append(f"{field} = ?")
            if field == "source_pick_snapshot":
                params.append(json.dumps(updates.get(field) or {}))
            elif field == "expiry":
                params.append(_to_iso(updates.get(field)))
            elif field == "proof_eligible":
                params.append(1 if updates.get(field) else 0)
            else:
                params.append(updates.get(field))

        if not assignments:
            position = self.get_position(position_id)
            if position is None:
                raise RuntimeError(f"Tracked position {position_id} not found.")
            return position

        with self._connect() as conn:
            cur = conn.execute("SELECT 1 FROM tracked_positions WHERE id = ?", (position_id,))
            if not cur.fetchone():
                raise RuntimeError(f"Tracked position {position_id} not found.")
            conn.execute(
                f"""
                UPDATE tracked_positions
                SET {", ".join(assignments)},
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (*params, position_id),
            )
            position = self._fetch_position_by_id_in_conn(conn, position_id)
        if position is None:
            raise RuntimeError(f"Tracked position {position_id} was not found after update.")
        return position

    def save_review(self, position_id: int, review: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as conn:
            cur = conn.execute("SELECT status FROM tracked_positions WHERE id = ?", (position_id,))
            status_row = cur.fetchone()
            if not status_row:
                raise RuntimeError(f"Tracked position {position_id} not found.")
            if str(status_row["status"]) != "open":
                raise ValueError(f"Tracked position {position_id} is not open for review.")

            conn.execute(
                """
                INSERT INTO position_reviews (
                    position_id, reviewed_at, pricing_source,
                    current_option_price, current_pnl_pct,
                    gross_pnl_pct, net_pnl_pct, gross_pnl_usd, net_pnl_usd,
                    entry_execution_price, exit_execution_price,
                    entry_execution_basis, exit_execution_basis,
                    fee_total_usd,
                    recommendation, reason, warnings, metrics_snapshot
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
                UPDATE tracked_positions
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
                    updated_at = datetime('now')
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
                    position_id,
                ),
            )
            position = self._fetch_position_by_id_in_conn(conn, position_id)
            if position is None:
                raise RuntimeError(f"Tracked position {position_id} was not found after review save.")
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

            cur = conn.execute(
                """
                SELECT status, contracts, entry_execution_price, entry_option_price, entry_fee_total_usd, source_pick_snapshot
                FROM tracked_positions
                WHERE id = ?
                """,
                (position_id,),
            )
            status_row = cur.fetchone()
            if not status_row:
                return None
            if str(status_row["status"]) != "open":
                raise ValueError(f"Tracked position {position_id} is already closed.")
            contracts = int(status_row["contracts"] or 1)
            entry_execution_price = status_row["entry_execution_price"] or status_row["entry_option_price"]
            entry_fee_total_usd = status_row["entry_fee_total_usd"]
            fee_sides = _source_snapshot_fee_sides(status_row["source_pick_snapshot"])
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

            # Build notes update
            if notes:
                cur2 = conn.execute("SELECT notes FROM tracked_positions WHERE id = ?", (position_id,))
                existing_row = cur2.fetchone()
                existing_notes = existing_row["notes"] if existing_row and existing_row["notes"] else ""
                new_notes = f"{existing_notes}\n{notes}".strip() if existing_notes else notes
            else:
                new_notes = None

            closed_at_iso = _to_iso(closed_at)
            conn.execute(
                """
                UPDATE tracked_positions
                SET
                    status = 'closed',
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
                    notes = COALESCE(?, notes),
                    updated_at = datetime('now')
                WHERE id = ? AND status = 'open'
                """,
                (
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
                    new_notes,
                    position_id,
                ),
            )
            position = self._fetch_position_by_id_in_conn(conn, position_id)
            if position is None:
                raise RuntimeError(f"Tracked position {position_id} was not found after close.")
            return position

    def get_realized_pnl_since(self, since: datetime) -> float:
        since_iso = _to_iso(since)
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT COALESCE(SUM(net_pnl_usd), 0) AS total_pnl_usd
                FROM tracked_positions
                WHERE status = 'closed' AND closed_at >= ?
                """,
                (since_iso,),
            )
            row = cur.fetchone()
            return float(row["total_pnl_usd"]) if row else 0.0


class MemoryTrackedPositionsRepository:
    def __init__(self):
        self.is_available = True
        self.error_message: Optional[str] = None
        self._next_position_id = 1
        self._next_review_id = 1
        self._positions: list[dict[str, Any]] = []
        self._reviews: list[dict[str, Any]] = []

    def init_schema(self) -> bool:
        return True

    def _find_position(self, position_id: int) -> Optional[dict[str, Any]]:
        for position in self._positions:
            if position["id"] == position_id:
                return position
        return None

    def _latest_review(self, position_id: int) -> Optional[dict[str, Any]]:
        reviews = [review for review in self._reviews if review["position_id"] == position_id]
        if not reviews:
            return None
        reviews.sort(key=lambda review: (review["reviewed_at"], review["id"]), reverse=True)
        review = reviews[0]
        return {
            "id": review["id"],
            "reviewed_at": _to_iso(review["reviewed_at"]),
            "pricing_source": review.get("pricing_source"),
            "current_option_price": review.get("current_option_price"),
            "current_pnl_pct": review.get("current_pnl_pct"),
            "gross_pnl_pct": review.get("gross_pnl_pct"),
            "net_pnl_pct": review.get("net_pnl_pct"),
            "gross_pnl_usd": review.get("gross_pnl_usd"),
            "net_pnl_usd": review.get("net_pnl_usd"),
            "entry_execution_price": review.get("entry_execution_price"),
            "exit_execution_price": review.get("exit_execution_price"),
            "entry_execution_basis": review.get("entry_execution_basis"),
            "exit_execution_basis": review.get("exit_execution_basis"),
            "fee_total_usd": review.get("fee_total_usd"),
            "recommendation": review.get("recommendation"),
            "reason": review.get("reason"),
            "warnings": copy.deepcopy(review.get("warnings") or []),
            "metrics_snapshot": copy.deepcopy(review.get("metrics_snapshot") or {}),
        }

    def create_position(self, payload: dict[str, Any]) -> dict[str, Any]:
        position = copy.deepcopy(payload)
        position["id"] = self._next_position_id
        self._next_position_id += 1
        position.setdefault("created_at", position["filled_at"])
        position.setdefault("updated_at", position["filled_at"])
        self._positions.append(position)
        return self.get_position(position["id"])  # type: ignore[arg-type]

    def list_positions(self, status: Optional[str] = "open") -> list[dict[str, Any]]:
        items = self._positions
        if status in {"open", "closed"}:
            items = [position for position in items if position["status"] == status]
        normalized = [self.get_position(position["id"]) for position in items]
        normalized = [position for position in normalized if position is not None]
        normalized.sort(key=lambda position: (position["filled_at"], position["id"]), reverse=True)
        return normalized

    def get_position(self, position_id: int) -> Optional[dict[str, Any]]:
        position = self._find_position(position_id)
        if position is None:
            return None
        normalized = copy.deepcopy(position)
        for key in ("filled_at", "last_reviewed_at", "closed_at", "created_at", "updated_at"):
            normalized[key] = _to_iso(normalized.get(key))
        normalized["expiry"] = _to_iso(normalized.get("expiry"))
        normalized["source_pick_snapshot"] = copy.deepcopy(normalized.get("source_pick_snapshot") or {})
        latest_review = self._latest_review(position_id)
        if str(normalized.get("status") or "").strip().lower() == "closed" and normalized.get("closed_at") is not None:
            latest_review = _closed_position_review(normalized, latest_review)
        normalized["latest_review"] = latest_review
        return normalized

    def save_review(self, position_id: int, review: dict[str, Any]) -> dict[str, Any]:
        position = self._find_position(position_id)
        if position is None:
            raise RuntimeError(f"Tracked position {position_id} not found.")
        if position.get("status") != "open":
            raise ValueError(f"Tracked position {position_id} is not open for review.")
        stored_review = copy.deepcopy(review)
        stored_review["id"] = self._next_review_id
        stored_review["position_id"] = position_id
        self._next_review_id += 1
        self._reviews.append(stored_review)
        position["peak_pnl_pct"] = review.get("peak_pnl_pct")
        position["last_option_price"] = review.get("current_option_price")
        position["last_pnl_pct"] = review.get("current_pnl_pct")
        position["last_recommendation"] = review.get("recommendation")
        position["last_recommendation_reason"] = review.get("reason")
        position["exit_execution_price"] = review.get("exit_execution_price")
        position["exit_execution_basis"] = review.get("exit_execution_basis")
        position["gross_pnl_pct"] = review.get("gross_pnl_pct")
        position["net_pnl_pct"] = review.get("net_pnl_pct")
        position["gross_pnl_usd"] = review.get("gross_pnl_usd")
        position["net_pnl_usd"] = review.get("net_pnl_usd")
        position["fee_total_usd"] = review.get("fee_total_usd")
        position["last_reviewed_at"] = review.get("reviewed_at")
        position["updated_at"] = review.get("reviewed_at")
        return self.get_position(position_id)  # type: ignore[arg-type]

    def update_position(self, position_id: int, updates: dict[str, Any]) -> dict[str, Any]:
        position = self._find_position(position_id)
        if position is None:
            raise RuntimeError(f"Tracked position {position_id} not found.")
        for field in _POSITION_UPDATE_FIELDS:
            if field not in updates:
                continue
            position[field] = copy.deepcopy(updates[field])
        position["updated_at"] = datetime.now()
        return self.get_position(position_id)  # type: ignore[arg-type]

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
        position = self._find_position(position_id)
        if position is None:
            return None
        exit_price_value = float(exit_price)
        if (
            not math.isfinite(exit_price_value)
            or exit_price_value < 0
            or (not allow_zero_exit_price and exit_price_value <= 0)
        ):
            comparator = "greater than or equal to 0" if allow_zero_exit_price else "greater than 0"
            raise ValueError(f"exit_price must be a finite number {comparator}.")
        if position.get("status") != "open":
            raise ValueError(f"Tracked position {position_id} is already closed.")
        fee_sides = _position_fee_sides(position)
        exit_fee_total_usd = commission_total_usd(contracts=position.get("contracts"), sides=fee_sides)
        entry_fee_total_usd = (
            position.get("entry_fee_total_usd")
            if position.get("entry_fee_total_usd") is not None
            else commission_total_usd(contracts=position.get("contracts"), sides=fee_sides)
        )
        pnl_snapshot = option_pnl_snapshot(
            entry_execution_price=position.get("entry_execution_price") or position.get("entry_option_price"),
            exit_execution_price=exit_price_value,
            contracts=position.get("contracts"),
            entry_fee_total_usd=entry_fee_total_usd,
            exit_fee_total_usd=exit_fee_total_usd,
        )
        position["status"] = "closed"
        position["closed_at"] = closed_at
        position["exit_option_price"] = exit_price_value
        position["exit_execution_price"] = exit_price_value
        position["exit_execution_basis"] = exit_execution_basis
        position["exit_reason"] = exit_reason
        position["last_option_price"] = exit_price_value
        position["last_pnl_pct"] = pnl_snapshot.get("gross_pnl_pct")
        position["last_recommendation"] = "SELL"
        position["last_recommendation_reason"] = exit_reason
        position["gross_pnl_pct"] = pnl_snapshot.get("gross_pnl_pct")
        position["net_pnl_pct"] = pnl_snapshot.get("net_pnl_pct")
        position["gross_pnl_usd"] = pnl_snapshot.get("gross_pnl_usd")
        position["net_pnl_usd"] = pnl_snapshot.get("net_pnl_usd")
        position["fee_total_usd"] = pnl_snapshot.get("fee_total_usd")
        position["last_reviewed_at"] = closed_at
        if notes:
            existing = position.get("notes") or ""
            position["notes"] = f"{existing}\n{notes}".strip() if existing else notes
        position["updated_at"] = closed_at
        return self.get_position(position_id)  # type: ignore[arg-type]

    def get_realized_pnl_since(self, since: datetime) -> float:
        total = 0.0
        for position in self._positions:
            if position.get("status") == "closed":
                closed_at = position.get("closed_at")
                if closed_at is not None and closed_at >= since:
                    pnl = position.get("net_pnl_usd")
                    if pnl is not None:
                        total += float(pnl)
        return total


def create_positions_repository(database_url: Optional[str]):
    if database_url:
        repo = PostgresTrackedPositionsRepository(database_url)
        repo.init_schema()
        if repo.is_available:
            # Verify we can actually connect (init_schema tests the connection)
            try:
                repo.list_positions("open")
                return repo
            except Exception as exc:
                repo.is_available = False
                repo.error_message = (
                    "Tracked positions database is unavailable. "
                    f"Check DATABASE_URL and local Postgres. Details: {exc}"
                )
        return UnavailableTrackedPositionsRepository(
            repo.error_message
            or "Tracked positions database is unavailable. Check DATABASE_URL and local Postgres."
        )
    # Fall back to SQLite
    repo = SqliteTrackedPositionsRepository()
    repo.init_schema()
    return repo
