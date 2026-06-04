# Repository Migrations

This file, `docs/repository-migrations.md`, is the semantic owner for Trading Desk repository schema evolution. The code owner is `python-backend/repository_migrations.py`. Local SQLite safety and read-only local DB audit ownership are mapped separately in `docs/local-db-hardening.md` and `python-backend/local_db_hardening.py`. Constraint ownership is mapped separately in `docs/repository-constraints.md` and `python-backend/repository_constraints.py`; index ownership is mapped in `docs/repository-indexes.md` and `python-backend/repository_indexes.py`.

## Covered Stores

| Store id | Repository | Tables | Role |
| --- | --- | --- | --- |
| `postgres_tracked_positions` | `PostgresTrackedPositionsRepository` | `tracked_positions`, `position_reviews` | Production tracked-position and review storage through `DATABASE_URL`. |
| `sqlite_suggested_trades` | `SQLiteSuggestedTradesRepository` | `suggested_trades`, `suggested_trade_reviews` | Local suggested-trade and paper-idea workflow storage. |
| `sqlite_tracked_positions_test_legacy` | `SqliteTrackedPositionsRepository` | `tracked_positions`, `position_reviews` | Explicit tests and legacy tools only. It is not a browser fallback. |

Each covered database records applied repository migrations in `repository_schema_migrations`. Point 11 records the current inline repository `init_schema()` DDL as a checksum-guarded baseline after that DDL succeeds. This keeps current startup behavior intact while giving future schema changes a versioned place to land.

## Migration Ledger Behavior Matrix

| Case | Expected behavior | Test anchor |
| --- | --- | --- |
| First repository init | Inline schema DDL succeeds, then the current baseline migration row is recorded. | `tests/test_repository_migrations.py` |
| Repeat repository init | The same `(store_id, migration_id)` row is reused after checksum validation. | `tests/test_repository_migrations.py` |
| Duplicate ledger insert | The database primary key rejects another row for the same store and migration id. | `tests/test_repository_migrations.py` |
| Checksum mismatch | Repository startup fails closed instead of accepting an edited baseline. | `tests/test_repository_migrations.py` |
| Unknown store id | Migration helper raises before creating a migration ledger table. | `tests/test_repository_migrations.py` |
| Future migration | Add a new ordered manifest entry; do not edit recorded baseline checksums. | `tests/test_repository_migrations.py` |

## How To Add A Schema Change

1. Add a new forward-only manifest entry in `python-backend/repository_migrations.py`.
2. Keep the change additive and idempotent unless a later decision explicitly approves a destructive migration.
3. Apply the change through the repository migration path, not through route handlers, frontend code, proof predicates, or scanner logic.
4. Add focused tests in `tests/test_repository_migrations.py` and any repository behavior tests that depend on the new column, constraint, or index.
5. Update this document, `docs/api-and-storage.md`, `docs/repository-contract.md`, and `docs/DECISIONS.md` when ownership or migration rules change.

## Hard Rules

- No Alembic or ORM migration framework is introduced by Point 11.
- Keep migrations forward-only unless a later decision adds a rollback policy.
- Keep baseline migrations checksum-stable; future schema work adds a new migration instead of editing a recorded baseline.
- New DB constraints must match `docs/repository-constraints.md` and `python-backend/repository_constraints.py`; deferred checks require a read-only audit before enforcement.
- New DB indexes must match `docs/repository-indexes.md` and `python-backend/repository_indexes.py`; deferred candidates require query-plan or row-count evidence before DDL.
- Local DB audits must match `docs/local-db-hardening.md` and `python-backend/local_db_hardening.py`; they are read-only and must not initialize schema, run repair, or change journal mode.
- Preserve no silent tracked-position SQLite fallback. Missing or failing Postgres still fails closed through `UnavailableTrackedPositionsRepository`.
- Do not use migrations to redefine proof, scanner creation safety, route payloads, auth, lifecycle evidence, replay math, or Trading Desk repository method contracts.
- Do not migrate `historical_options_store.py`, `data/options-validation/options_history.db`, or `data/ai-commodity-infra/` through this Trading Desk repository migration contract.

## Implementation Anchors

- Migration manifest and ledger helpers: `python-backend/repository_migrations.py`
- Tracked-position repository call sites: `python-backend/positions_repository.py`
- Suggested-trade repository call site: `python-backend/suggested_trades_repository.py`
- Repository ownership contract: `docs/repository-contract.md`
- Local DB hardening: `docs/local-db-hardening.md` and `python-backend/local_db_hardening.py`
- Route and storage map: `docs/api-and-storage.md`
- Contract tests: `tests/test_repository_migrations.py`
