from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any


MIGRATION_LEDGER_TABLE = "repository_schema_migrations"

POSTGRES_TRACKED_POSITIONS_STORE_ID = "postgres_tracked_positions"
SQLITE_TRACKED_POSITIONS_STORE_ID = "sqlite_tracked_positions_test_legacy"
SQLITE_SUGGESTED_TRADES_STORE_ID = "sqlite_suggested_trades"


@dataclass(frozen=True)
class RepositoryMigration:
    store_id: str
    migration_id: str
    dialect: str
    description: str
    tables: tuple[str, ...]
    checksum: str


def _checksum(*parts: str) -> str:
    payload = "\n".join(parts).encode("utf-8")
    return sha256(payload).hexdigest()


def _baseline_migration(
    *,
    store_id: str,
    migration_id: str,
    dialect: str,
    description: str,
    tables: tuple[str, ...],
    schema_anchor: str,
) -> RepositoryMigration:
    return RepositoryMigration(
        store_id=store_id,
        migration_id=migration_id,
        dialect=dialect,
        description=description,
        tables=tables,
        checksum=_checksum(store_id, migration_id, dialect, ",".join(tables), schema_anchor),
    )


REPOSITORY_MIGRATIONS: tuple[RepositoryMigration, ...] = (
    _baseline_migration(
        store_id=POSTGRES_TRACKED_POSITIONS_STORE_ID,
        migration_id="tracked_positions_postgres_0001_current_schema_baseline",
        dialect="postgres",
        description=(
            "Current tracked-position Postgres schema baseline recorded after "
            "the repository's idempotent init_schema DDL succeeds."
        ),
        tables=("tracked_positions", "position_reviews"),
        schema_anchor="positions_repository.PostgresTrackedPositionsRepository.init_schema:2026-06-04",
    ),
    _baseline_migration(
        store_id=SQLITE_TRACKED_POSITIONS_STORE_ID,
        migration_id="tracked_positions_sqlite_0001_current_schema_baseline",
        dialect="sqlite",
        description=(
            "Current tracked-position SQLite test/legacy schema baseline recorded "
            "after the repository's idempotent init_schema DDL succeeds."
        ),
        tables=("tracked_positions", "position_reviews"),
        schema_anchor="positions_repository.SqliteTrackedPositionsRepository.init_schema:2026-06-04",
    ),
    _baseline_migration(
        store_id=SQLITE_SUGGESTED_TRADES_STORE_ID,
        migration_id="suggested_trades_sqlite_0001_current_schema_baseline",
        dialect="sqlite",
        description=(
            "Current suggested-trade SQLite schema baseline recorded after the "
            "repository's idempotent init_schema DDL succeeds."
        ),
        tables=("suggested_trades", "suggested_trade_reviews"),
        schema_anchor="suggested_trades_repository.SQLiteSuggestedTradesRepository.init_schema:2026-06-04",
    ),
)

_MIGRATIONS_BY_STORE: dict[str, tuple[RepositoryMigration, ...]] = {}
for _migration in REPOSITORY_MIGRATIONS:
    _MIGRATIONS_BY_STORE.setdefault(_migration.store_id, tuple())
    _MIGRATIONS_BY_STORE[_migration.store_id] = (
        *_MIGRATIONS_BY_STORE[_migration.store_id],
        _migration,
    )


def repository_migrations_for_store(store_id: str) -> tuple[RepositoryMigration, ...]:
    try:
        return _MIGRATIONS_BY_STORE[store_id]
    except KeyError as exc:
        raise ValueError(f"No repository migrations registered for store {store_id!r}.") from exc


def migration_manifest() -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "store_id": migration.store_id,
            "migration_id": migration.migration_id,
            "dialect": migration.dialect,
            "description": migration.description,
            "tables": migration.tables,
            "checksum": migration.checksum,
        }
        for migration in REPOSITORY_MIGRATIONS
    )


def _row_checksum(row: Any) -> str | None:
    if row is None:
        return None
    try:
        return str(row["checksum"])
    except (KeyError, TypeError, IndexError):
        return str(row[0])


def _validate_checksum(existing_checksum: str | None, migration: RepositoryMigration) -> bool:
    if existing_checksum is None:
        return False
    if existing_checksum != migration.checksum:
        raise RuntimeError(
            "Repository migration checksum mismatch for "
            f"{migration.store_id}/{migration.migration_id}: "
            f"stored {existing_checksum}, expected {migration.checksum}."
        )
    return True


def apply_sqlite_repository_migrations(conn: Any, store_id: str) -> None:
    migrations = repository_migrations_for_store(store_id)
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {MIGRATION_LEDGER_TABLE} (
            store_id TEXT NOT NULL,
            migration_id TEXT NOT NULL,
            checksum TEXT NOT NULL,
            description TEXT NOT NULL,
            dialect TEXT NOT NULL,
            tables TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (store_id, migration_id)
        )
        """
    )
    for migration in migrations:
        row = conn.execute(
            f"""
            SELECT checksum
            FROM {MIGRATION_LEDGER_TABLE}
            WHERE store_id = ? AND migration_id = ?
            """,
            (migration.store_id, migration.migration_id),
        ).fetchone()
        if _validate_checksum(_row_checksum(row), migration):
            continue
        conn.execute(
            f"""
            INSERT INTO {MIGRATION_LEDGER_TABLE}
                (store_id, migration_id, checksum, description, dialect, tables)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                migration.store_id,
                migration.migration_id,
                migration.checksum,
                migration.description,
                migration.dialect,
                ",".join(migration.tables),
            ),
        )


def apply_postgres_repository_migrations(cur: Any, store_id: str) -> None:
    migrations = repository_migrations_for_store(store_id)
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {MIGRATION_LEDGER_TABLE} (
            store_id TEXT NOT NULL,
            migration_id TEXT NOT NULL,
            checksum TEXT NOT NULL,
            description TEXT NOT NULL,
            dialect TEXT NOT NULL,
            tables TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (store_id, migration_id)
        )
        """
    )
    for migration in migrations:
        cur.execute(
            f"""
            SELECT checksum
            FROM {MIGRATION_LEDGER_TABLE}
            WHERE store_id = %s AND migration_id = %s
            """,
            (migration.store_id, migration.migration_id),
        )
        row = cur.fetchone()
        if _validate_checksum(_row_checksum(row), migration):
            continue
        cur.execute(
            f"""
            INSERT INTO {MIGRATION_LEDGER_TABLE}
                (store_id, migration_id, checksum, description, dialect, tables)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (store_id, migration_id) DO NOTHING
            """,
            (
                migration.store_id,
                migration.migration_id,
                migration.checksum,
                migration.description,
                migration.dialect,
                ",".join(migration.tables),
            ),
        )
