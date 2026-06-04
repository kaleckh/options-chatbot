from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from repository_migrations import (
    POSTGRES_TRACKED_POSITIONS_STORE_ID,
    SQLITE_SUGGESTED_TRADES_STORE_ID,
    SQLITE_TRACKED_POSITIONS_STORE_ID,
)


ConstraintEnforcement = Literal[
    "db_enforced",
    "api_service_enforced",
    "proof_contract_owned",
    "deferred",
]


@dataclass(frozen=True)
class RepositoryConstraint:
    constraint_id: str
    store_id: str
    table: str
    invariant: str
    enforcement: ConstraintEnforcement
    owner: str
    notes: str


REPOSITORY_CONSTRAINTS: tuple[RepositoryConstraint, ...] = (
    RepositoryConstraint(
        constraint_id="tracked_positions_primary_key",
        store_id=POSTGRES_TRACKED_POSITIONS_STORE_ID,
        table="tracked_positions",
        invariant="id is the durable row identity.",
        enforcement="db_enforced",
        owner="positions_repository.PostgresTrackedPositionsRepository.init_schema",
        notes="BIGSERIAL PRIMARY KEY is enforced by Postgres.",
    ),
    RepositoryConstraint(
        constraint_id="tracked_position_reviews_parent_fk",
        store_id=POSTGRES_TRACKED_POSITIONS_STORE_ID,
        table="position_reviews",
        invariant="review rows must reference an existing tracked position.",
        enforcement="db_enforced",
        owner="positions_repository.PostgresTrackedPositionsRepository.init_schema",
        notes="Postgres enforces REFERENCES tracked_positions(id) ON DELETE CASCADE.",
    ),
    RepositoryConstraint(
        constraint_id="suggested_trades_primary_key",
        store_id=SQLITE_SUGGESTED_TRADES_STORE_ID,
        table="suggested_trades",
        invariant="id is the durable suggested-trade row identity.",
        enforcement="db_enforced",
        owner="suggested_trades_repository.SQLiteSuggestedTradesRepository.init_schema",
        notes="INTEGER PRIMARY KEY AUTOINCREMENT is enforced by SQLite.",
    ),
    RepositoryConstraint(
        constraint_id="suggested_trade_reviews_parent_fk",
        store_id=SQLITE_SUGGESTED_TRADES_STORE_ID,
        table="suggested_trade_reviews",
        invariant="review rows must reference an existing suggested trade.",
        enforcement="db_enforced",
        owner="suggested_trades_repository.SQLiteSuggestedTradesRepository._connect",
        notes="SQLite FK exists in DDL and requires PRAGMA foreign_keys=ON per connection.",
    ),
    RepositoryConstraint(
        constraint_id="sqlite_tracked_positions_test_legacy_parent_fk",
        store_id=SQLITE_TRACKED_POSITIONS_STORE_ID,
        table="position_reviews",
        invariant="legacy/test review rows must reference an existing tracked position.",
        enforcement="db_enforced",
        owner="positions_repository.SqliteTrackedPositionsRepository._connect",
        notes="SQLite FK exists in DDL and PRAGMA foreign_keys=ON is enabled per connection.",
    ),
    RepositoryConstraint(
        constraint_id="repository_schema_migrations_unique_version",
        store_id=POSTGRES_TRACKED_POSITIONS_STORE_ID,
        table="repository_schema_migrations",
        invariant="one checksum-guarded migration row exists per store and migration id.",
        enforcement="db_enforced",
        owner="repository_migrations.py",
        notes="The migration ledger primary key is enforced by each covered database.",
    ),
    RepositoryConstraint(
        constraint_id="sqlite_tracked_repository_schema_migrations_unique_version",
        store_id=SQLITE_TRACKED_POSITIONS_STORE_ID,
        table="repository_schema_migrations",
        invariant="one checksum-guarded migration row exists per store and migration id.",
        enforcement="db_enforced",
        owner="repository_migrations.py",
        notes="The SQLite tracked test/legacy migration ledger primary key is enforced by SQLite.",
    ),
    RepositoryConstraint(
        constraint_id="sqlite_suggested_repository_schema_migrations_unique_version",
        store_id=SQLITE_SUGGESTED_TRADES_STORE_ID,
        table="repository_schema_migrations",
        invariant="one checksum-guarded migration row exists per store and migration id.",
        enforcement="db_enforced",
        owner="repository_migrations.py",
        notes="The SQLite suggested-trade migration ledger primary key is enforced by SQLite.",
    ),
    RepositoryConstraint(
        constraint_id="position_create_core_shape",
        store_id=POSTGRES_TRACKED_POSITIONS_STORE_ID,
        table="tracked_positions",
        invariant="new position payloads use open/closed status, call/put direction, positive contracts, positive entry price, and positive option terms.",
        enforcement="api_service_enforced",
        owner="positions_service.build_position_payload",
        notes="Kept out of DB CHECK constraints until existing rows are audited clean.",
    ),
    RepositoryConstraint(
        constraint_id="suggested_trade_create_core_shape",
        store_id=SQLITE_SUGGESTED_TRADES_STORE_ID,
        table="suggested_trades",
        invariant="new suggested-trade payloads use open/closed status, call/put direction, positive contracts, positive entry price, and positive option terms.",
        enforcement="api_service_enforced",
        owner="positions_service.build_position_payload",
        notes="SQLite table rebuild constraints are deferred.",
    ),
    RepositoryConstraint(
        constraint_id="close_exit_price_nonnegative",
        store_id=POSTGRES_TRACKED_POSITIONS_STORE_ID,
        table="tracked_positions",
        invariant="manual close exit prices must be finite and nonnegative.",
        enforcement="api_service_enforced",
        owner="python-backend/main.py close endpoints and repository close_position methods",
        notes="Zero exit prices remain allowed for executable worthless exits.",
    ),
    RepositoryConstraint(
        constraint_id="proof_truth_not_sql",
        store_id=POSTGRES_TRACKED_POSITIONS_STORE_ID,
        table="tracked_positions",
        invariant="proof eligibility depends on exact contract identity, OPRA/freshness, lineage, research/backfill markers, and trusted exit evidence.",
        enforcement="proof_contract_owned",
        owner="docs/proof-evidence-contract.md and python-backend/proof_contract.py",
        notes="Do not encode proof-grade truth as a DB CHECK on proof_eligible or proof_class.",
    ),
    RepositoryConstraint(
        constraint_id="candidate_check_constraints",
        store_id=POSTGRES_TRACKED_POSITIONS_STORE_ID,
        table="tracked_positions",
        invariant="candidate future checks include status/direction enums, positive numeric fields, and nonnegative nullable exit/fee fields.",
        enforcement="deferred",
        owner="docs/repository-constraints.md",
        notes="Add only after the read-only constraint audit proves existing rows are clean or intentionally exempt.",
    ),
    RepositoryConstraint(
        constraint_id="candidate_unique_open_contract",
        store_id=POSTGRES_TRACKED_POSITIONS_STORE_ID,
        table="tracked_positions",
        invariant="future uniqueness may prevent duplicate open exact contracts per store.",
        enforcement="deferred",
        owner="docs/repository-constraints.md",
        notes="Currently enforced by repository/API lookup; DB unique index needs a separate data audit.",
    ),
)


def constraint_manifest() -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "constraint_id": constraint.constraint_id,
            "store_id": constraint.store_id,
            "table": constraint.table,
            "invariant": constraint.invariant,
            "enforcement": constraint.enforcement,
            "owner": constraint.owner,
            "notes": constraint.notes,
        }
        for constraint in REPOSITORY_CONSTRAINTS
    )


def constraints_by_enforcement(enforcement: ConstraintEnforcement) -> tuple[RepositoryConstraint, ...]:
    return tuple(
        constraint
        for constraint in REPOSITORY_CONSTRAINTS
        if constraint.enforcement == enforcement
    )


def constraints_for_store(store_id: str) -> tuple[RepositoryConstraint, ...]:
    return tuple(
        constraint
        for constraint in REPOSITORY_CONSTRAINTS
        if constraint.store_id == store_id
    )
