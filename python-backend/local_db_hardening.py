from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from repository_migrations import (
    MIGRATION_LEDGER_TABLE,
    SQLITE_SUGGESTED_TRADES_STORE_ID,
    SQLITE_TRACKED_POSITIONS_STORE_ID,
)


LocalDatabaseMutability = Literal[
    "active_mutable",
    "test_legacy_mutable",
    "outside_repository_scope",
    "ignored_sidecar_or_backup",
]


@dataclass(frozen=True)
class LocalDatabaseRole:
    database_id: str
    store_id: str
    path_pattern: str
    owner: str
    mutability: LocalDatabaseMutability
    active_scope: str
    expected_tables: tuple[str, ...]
    optional_tables: tuple[str, ...]
    expected_connection_policy: tuple[str, ...]
    audit_checks: tuple[str, ...]
    backup_rule: str
    notes: str


LOCAL_DATABASE_ROLES: tuple[LocalDatabaseRole, ...] = (
    LocalDatabaseRole(
        database_id="chat_history_sqlite_suggested_trades",
        store_id=SQLITE_SUGGESTED_TRADES_STORE_ID,
        path_pattern="chat_history.db",
        owner="python-backend/suggested_trades_repository.py",
        mutability="active_mutable",
        active_scope="Trading Desk suggested trades and local paper workflow state.",
        expected_tables=("suggested_trades", "suggested_trade_reviews"),
        optional_tables=(MIGRATION_LEDGER_TABLE, "sessions", "messages", "session_context"),
        expected_connection_policy=(
            "repository write connections enable PRAGMA foreign_keys=ON",
            "audits open existing files with SQLite mode=ro and do not initialize schema",
        ),
        audit_checks=(
            "exists_or_skipped",
            "read_only_uri_open",
            "quick_check",
            "foreign_key_check",
            "required_tables",
            "sidecar_and_backup_inventory",
        ),
        backup_rule=(
            "Create an application-aware SQLite backup before manual mutation; "
            "do not prune backups from audit scripts."
        ),
        notes="This is the only active mutable Trading Desk SQLite browser store.",
    ),
    LocalDatabaseRole(
        database_id="tracked_positions_sqlite_test_legacy",
        store_id=SQLITE_TRACKED_POSITIONS_STORE_ID,
        path_pattern="data/tracked_positions.db",
        owner="python-backend/positions_repository.py::SqliteTrackedPositionsRepository",
        mutability="test_legacy_mutable",
        active_scope="Explicit tests and legacy tools only; never the browser tracked-position fallback.",
        expected_tables=("tracked_positions", "position_reviews"),
        optional_tables=(MIGRATION_LEDGER_TABLE,),
        expected_connection_policy=(
            "repository connections enable PRAGMA foreign_keys=ON",
            "legacy repository connections currently request PRAGMA journal_mode=WAL",
            "audits open existing files with SQLite mode=ro and do not initialize schema",
        ),
        audit_checks=(
            "exists_or_skipped",
            "read_only_uri_open",
            "quick_check",
            "foreign_key_check",
            "required_tables",
            "sidecar_and_backup_inventory",
        ),
        backup_rule=(
            "Prefer JSON snapshots or SQLite backup API for legacy repair scripts; "
            "do not copy live SQLite files without quiescing writers."
        ),
        notes="This DB is local legacy/test state and must not replace Postgres tracked positions.",
    ),
    LocalDatabaseRole(
        database_id="options_history_truth_store",
        store_id="options_history_truth_store",
        path_pattern="data/options-validation/options_history.db",
        owner="historical_options_store.py and import/replay scripts",
        mutability="outside_repository_scope",
        active_scope="Imported options truth store and replay input.",
        expected_tables=(),
        optional_tables=(),
        expected_connection_policy=("Owned by options-history/import tooling, not Trading Desk repositories.",),
        audit_checks=("classified_out_of_scope",),
        backup_rule="Use options-history import/replay runbooks; do not repair from this Trading Desk audit.",
        notes="Large proof/research store; Point 15 does not open or mutate it by default.",
    ),
    LocalDatabaseRole(
        database_id="forward_tracking_ledgers",
        store_id="forward_tracking_ledgers",
        path_pattern="data/options-validation/forward_tracking*.db",
        owner="forward-evidence and options-profit tooling",
        mutability="outside_repository_scope",
        active_scope="Canonical and archive forward-evidence ledgers.",
        expected_tables=(),
        optional_tables=(),
        expected_connection_policy=("Owned by forward-evidence tooling, not Trading Desk repositories.",),
        audit_checks=("classified_out_of_scope",),
        backup_rule="Use forward-evidence runbooks; do not repair from this Trading Desk audit.",
        notes="Forward evidence is proof-adjacent but not a local repository hardening target.",
    ),
    LocalDatabaseRole(
        database_id="market_data_cache",
        store_id="market_data_cache",
        path_pattern="market_data.db",
        owner="market data service and research support workflows",
        mutability="outside_repository_scope",
        active_scope="Market data cache and support data.",
        expected_tables=(),
        optional_tables=(),
        expected_connection_policy=("Owned by market data cache code, not Trading Desk repositories.",),
        audit_checks=("classified_out_of_scope",),
        backup_rule="Use market-data cache runbooks; cache rebuilds are outside Point 15.",
        notes="Mutable cache, but outside Trading Desk repository migrations/constraints/indexes.",
    ),
    LocalDatabaseRole(
        database_id="ai_commodity_artifacts",
        store_id="ai_commodity_artifacts",
        path_pattern="data/ai-commodity-infra/*",
        owner="scripts/run_ai_commodity_opra_progress.py",
        mutability="outside_repository_scope",
        active_scope="Separate AI commodity proof-first lane artifacts.",
        expected_tables=(),
        optional_tables=(),
        expected_connection_policy=("Owned by AI commodity lane tooling.",),
        audit_checks=("classified_out_of_scope",),
        backup_rule="Use AI commodity progress/acquisition runbooks.",
        notes="Separate non-browser proof lane; excluded from Trading Desk local DB hardening.",
    ),
    LocalDatabaseRole(
        database_id="sqlite_sidecars_and_backups",
        store_id="sqlite_sidecars_and_backups",
        path_pattern="*.db-wal, *.db-shm, chat_history.backup-*.db, data/tracked_positions.backup-*",
        owner=".gitignore and manual backup hygiene",
        mutability="ignored_sidecar_or_backup",
        active_scope="SQLite sidecars and backups generated by local runtime or repair scripts.",
        expected_tables=(),
        optional_tables=(),
        expected_connection_policy=("Do not treat sidecars or backups as active stores.",),
        audit_checks=("classified_ignored",),
        backup_rule="Keep ignored locally unless a specific recovery workflow needs them.",
        notes="Audit scripts may enumerate these files but must not delete or rewrite them.",
    ),
    LocalDatabaseRole(
        database_id="evidence_store_backup_directory",
        store_id="evidence_store_backup_directory",
        path_pattern="data/backups/**",
        owner="scripts/backup_evidence_stores.py",
        mutability="ignored_sidecar_or_backup",
        active_scope="Nightly local evidence-store backups and optional weekly off-machine copies.",
        expected_tables=(),
        optional_tables=(),
        expected_connection_policy=("Do not treat backup files as active stores.",),
        audit_checks=("classified_ignored",),
        backup_rule="Keep generated backup runs ignored; rotate inside the backup script only.",
        notes=(
            "Contains SQLite backup API outputs and pg_dump artifacts for irreplaceable evidence stores; "
            "the local DB audit classifies it but must not open or prune it."
        ),
    ),
)


def local_database_manifest() -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "database_id": role.database_id,
            "store_id": role.store_id,
            "path_pattern": role.path_pattern,
            "owner": role.owner,
            "mutability": role.mutability,
            "active_scope": role.active_scope,
            "expected_tables": role.expected_tables,
            "optional_tables": role.optional_tables,
            "expected_connection_policy": role.expected_connection_policy,
            "audit_checks": role.audit_checks,
            "backup_rule": role.backup_rule,
            "notes": role.notes,
        }
        for role in LOCAL_DATABASE_ROLES
    )


def local_database_roles_by_mutability(
    mutability: LocalDatabaseMutability,
) -> tuple[LocalDatabaseRole, ...]:
    return tuple(role for role in LOCAL_DATABASE_ROLES if role.mutability == mutability)


def local_database_role(database_id: str) -> LocalDatabaseRole:
    for role in LOCAL_DATABASE_ROLES:
        if role.database_id == database_id:
            return role
    raise ValueError(f"No local database role registered for {database_id!r}.")
