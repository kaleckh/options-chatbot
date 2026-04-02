from __future__ import annotations

import copy
import json
import math
from datetime import date, datetime
from typing import Any, Optional


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
        "recommendation": row.get("recommendation"),
        "reason": row.get("reason"),
        "warnings": copy.deepcopy(row.get("warnings") or []),
        "metrics_snapshot": copy.deepcopy(row.get("metrics_snapshot") or {}),
    }


def _normalize_position_row(row: dict[str, Any]) -> dict[str, Any]:
    latest_review = _normalize_latest_review(row)
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
        "exit_reason": row.get("exit_reason"),
        "created_at": _to_iso(row.get("created_at")),
        "updated_at": _to_iso(row.get("updated_at")),
        "latest_review": latest_review,
    }
    return normalized


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

    def close_position(
        self,
        position_id: int,
        exit_price: float,
        closed_at: datetime,
        exit_reason: str,
        notes: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        raise RuntimeError(self.error_message)


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
            exit_reason TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        ALTER TABLE tracked_positions
        ADD COLUMN IF NOT EXISTS contract_symbol TEXT;

        CREATE INDEX IF NOT EXISTS idx_tracked_positions_status ON tracked_positions (status);
        CREATE INDEX IF NOT EXISTS idx_tracked_positions_filled_at ON tracked_positions (filled_at DESC);

        CREATE TABLE IF NOT EXISTS position_reviews (
            id BIGSERIAL PRIMARY KEY,
            position_id BIGINT NOT NULL REFERENCES tracked_positions(id) ON DELETE CASCADE,
            reviewed_at TIMESTAMPTZ NOT NULL,
            pricing_source TEXT,
            current_option_price DOUBLE PRECISION,
            current_pnl_pct DOUBLE PRECISION,
            recommendation TEXT NOT NULL,
            reason TEXT NOT NULL,
            warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
            metrics_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

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
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s
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
                        payload.get("exit_reason"),
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
                        recommendation,
                        reason,
                        warnings,
                        metrics_snapshot
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb
                    )
                    """,
                    (
                        position_id,
                        review["reviewed_at"],
                        review.get("pricing_source"),
                        review.get("current_option_price"),
                        review.get("current_pnl_pct"),
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
    ) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                if not math.isfinite(float(exit_price)) or float(exit_price) <= 0:
                    raise ValueError("exit_price must be a finite number greater than 0.")

                cur.execute("SELECT status FROM tracked_positions WHERE id = %s", (position_id,))
                status_row = cur.fetchone()
                if not status_row:
                    return None
                if str(status_row["status"]) != "open":
                    raise ValueError(f"Tracked position {position_id} is already closed.")

                cur.execute(
                    """
                    UPDATE tracked_positions
                    SET
                        status = 'closed',
                        closed_at = %s,
                        exit_option_price = %s,
                        exit_reason = %s,
                        notes = CASE
                            WHEN %s IS NULL OR %s = '' THEN notes
                            WHEN notes IS NULL OR notes = '' THEN %s
                            ELSE notes || E'\n' || %s
                        END,
                        updated_at = NOW()
                    WHERE id = %s AND status = 'open'
                    RETURNING id
                    """,
                    (
                        closed_at,
                        exit_price,
                        exit_reason,
                        notes,
                        notes,
                        notes,
                        notes,
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
        normalized["latest_review"] = self._latest_review(position_id)
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
        position["last_reviewed_at"] = review.get("reviewed_at")
        position["updated_at"] = review.get("reviewed_at")
        return self.get_position(position_id)  # type: ignore[arg-type]

    def close_position(
        self,
        position_id: int,
        exit_price: float,
        closed_at: datetime,
        exit_reason: str,
        notes: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        position = self._find_position(position_id)
        if position is None:
            return None
        if not math.isfinite(float(exit_price)) or float(exit_price) <= 0:
            raise ValueError("exit_price must be a finite number greater than 0.")
        if position.get("status") != "open":
            raise ValueError(f"Tracked position {position_id} is already closed.")
        position["status"] = "closed"
        position["closed_at"] = closed_at
        position["exit_option_price"] = exit_price
        position["exit_reason"] = exit_reason
        if notes:
            existing = position.get("notes") or ""
            position["notes"] = f"{existing}\n{notes}".strip() if existing else notes
        position["updated_at"] = closed_at
        return self.get_position(position_id)  # type: ignore[arg-type]


def create_positions_repository(database_url: Optional[str]):
    if not database_url:
        return UnavailableTrackedPositionsRepository(
            "Tracked positions are unavailable because DATABASE_URL is not configured. "
            "Start local Postgres and set DATABASE_URL to enable the supervised options tracker."
        )
    repo = PostgresTrackedPositionsRepository(database_url)
    repo.init_schema()
    return repo
