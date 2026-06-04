from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from repository_migrations import (
    POSTGRES_TRACKED_POSITIONS_STORE_ID,
    SQLITE_SUGGESTED_TRADES_STORE_ID,
    SQLITE_TRACKED_POSITIONS_STORE_ID,
)


IndexStatus = Literal["db_existing", "candidate_deferred"]


@dataclass(frozen=True)
class RepositoryIndex:
    index_id: str
    store_id: str
    table: str
    index_name: str
    columns: tuple[str, ...]
    status: IndexStatus
    unique: bool
    supports: tuple[str, ...]
    notes: str


REPOSITORY_INDEXES: tuple[RepositoryIndex, ...] = (
    RepositoryIndex(
        index_id="postgres_tracked_positions_status",
        store_id=POSTGRES_TRACKED_POSITIONS_STORE_ID,
        table="tracked_positions",
        index_name="idx_tracked_positions_status",
        columns=("status",),
        status="db_existing",
        unique=False,
        supports=("list_positions(status)", "list_compact_positions(status)", "profit_status_snapshot counts"),
        notes="Basic status filtering for tracked-position reads.",
    ),
    RepositoryIndex(
        index_id="postgres_tracked_positions_filled_at",
        store_id=POSTGRES_TRACKED_POSITIONS_STORE_ID,
        table="tracked_positions",
        index_name="idx_tracked_positions_filled_at",
        columns=("filled_at DESC",),
        status="db_existing",
        unique=False,
        supports=("list_positions ORDER BY filled_at DESC", "list_compact_positions ORDER BY filled_at DESC"),
        notes="Basic chronological page ordering for tracked-position reads.",
    ),
    RepositoryIndex(
        index_id="postgres_position_reviews_position_id",
        store_id=POSTGRES_TRACKED_POSITIONS_STORE_ID,
        table="position_reviews",
        index_name="idx_position_reviews_position_id",
        columns=("position_id", "reviewed_at DESC"),
        status="db_existing",
        unique=False,
        supports=("latest review lateral lookup",),
        notes="Supports latest-review lookup by parent position; id DESC tiebreaker remains a deferred candidate.",
    ),
    RepositoryIndex(
        index_id="sqlite_tracked_positions_status",
        store_id=SQLITE_TRACKED_POSITIONS_STORE_ID,
        table="tracked_positions",
        index_name="idx_tracked_positions_status",
        columns=("status",),
        status="db_existing",
        unique=False,
        supports=("list_positions(status)", "list_compact_positions(status)", "profit_status_snapshot counts"),
        notes="Explicit test/legacy tracked-position SQLite index.",
    ),
    RepositoryIndex(
        index_id="sqlite_tracked_positions_filled_at",
        store_id=SQLITE_TRACKED_POSITIONS_STORE_ID,
        table="tracked_positions",
        index_name="idx_tracked_positions_filled_at",
        columns=("filled_at DESC",),
        status="db_existing",
        unique=False,
        supports=("list_positions ORDER BY filled_at DESC", "list_compact_positions ORDER BY filled_at DESC"),
        notes="Explicit test/legacy tracked-position SQLite index.",
    ),
    RepositoryIndex(
        index_id="sqlite_position_reviews_position_id",
        store_id=SQLITE_TRACKED_POSITIONS_STORE_ID,
        table="position_reviews",
        index_name="idx_position_reviews_position_id",
        columns=("position_id", "reviewed_at DESC"),
        status="db_existing",
        unique=False,
        supports=("latest review lookup",),
        notes="Explicit test/legacy tracked-position SQLite index; id DESC tiebreaker remains deferred.",
    ),
    RepositoryIndex(
        index_id="sqlite_suggested_trades_status",
        store_id=SQLITE_SUGGESTED_TRADES_STORE_ID,
        table="suggested_trades",
        index_name="idx_suggested_trades_status",
        columns=("status",),
        status="db_existing",
        unique=False,
        supports=("list_positions(status)",),
        notes="Basic status filtering for suggested-trade reads.",
    ),
    RepositoryIndex(
        index_id="sqlite_suggested_trades_filled_at",
        store_id=SQLITE_SUGGESTED_TRADES_STORE_ID,
        table="suggested_trades",
        index_name="idx_suggested_trades_filled_at",
        columns=("filled_at DESC",),
        status="db_existing",
        unique=False,
        supports=("list_positions ORDER BY filled_at DESC",),
        notes="Basic chronological page ordering for suggested-trade reads.",
    ),
    RepositoryIndex(
        index_id="sqlite_suggested_trade_reviews_position_id",
        store_id=SQLITE_SUGGESTED_TRADES_STORE_ID,
        table="suggested_trade_reviews",
        index_name="idx_suggested_trade_reviews_position_id",
        columns=("position_id", "reviewed_at DESC", "id DESC"),
        status="db_existing",
        unique=False,
        supports=("latest review lookup",),
        notes="Matches the suggested-trade latest-review subquery including id DESC tiebreaker.",
    ),
    RepositoryIndex(
        index_id="candidate_tracked_positions_status_filled_id",
        store_id=POSTGRES_TRACKED_POSITIONS_STORE_ID,
        table="tracked_positions",
        index_name="idx_tracked_positions_status_filled_id",
        columns=("status", "filled_at DESC", "id DESC"),
        status="candidate_deferred",
        unique=False,
        supports=("paged status-filtered tracked-position lists",),
        notes="Composite page index candidate; defer until row counts or query plans justify DDL.",
    ),
    RepositoryIndex(
        index_id="candidate_suggested_trades_status_filled_id",
        store_id=SQLITE_SUGGESTED_TRADES_STORE_ID,
        table="suggested_trades",
        index_name="idx_suggested_trades_status_filled_id",
        columns=("status", "filled_at DESC", "id DESC"),
        status="candidate_deferred",
        unique=False,
        supports=("paged status-filtered suggested-trade lists",),
        notes="Composite page index candidate; defer until row counts or query plans justify DDL.",
    ),
    RepositoryIndex(
        index_id="candidate_tracked_reviews_position_reviewed_id",
        store_id=POSTGRES_TRACKED_POSITIONS_STORE_ID,
        table="position_reviews",
        index_name="idx_position_reviews_position_reviewed_id",
        columns=("position_id", "reviewed_at DESC", "id DESC"),
        status="candidate_deferred",
        unique=False,
        supports=("latest review lateral lookup with id tiebreaker",),
        notes="Defer until measured need because existing prefix index already supports parent lookup.",
    ),
    RepositoryIndex(
        index_id="candidate_tracked_positions_status_closed_at",
        store_id=POSTGRES_TRACKED_POSITIONS_STORE_ID,
        table="tracked_positions",
        index_name="idx_tracked_positions_status_closed_at",
        columns=("status", "closed_at DESC"),
        status="candidate_deferred",
        unique=False,
        supports=("get_realized_pnl_since", "closed-row profit status reads"),
        notes="Deferred because it is not the current paged hot path.",
    ),
)


def index_manifest() -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "index_id": index.index_id,
            "store_id": index.store_id,
            "table": index.table,
            "index_name": index.index_name,
            "columns": index.columns,
            "status": index.status,
            "unique": index.unique,
            "supports": index.supports,
            "notes": index.notes,
        }
        for index in REPOSITORY_INDEXES
    )


def indexes_by_status(status: IndexStatus) -> tuple[RepositoryIndex, ...]:
    return tuple(index for index in REPOSITORY_INDEXES if index.status == status)


def indexes_for_store(store_id: str) -> tuple[RepositoryIndex, ...]:
    return tuple(index for index in REPOSITORY_INDEXES if index.store_id == store_id)
