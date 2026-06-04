# Repository Indexes

This file, `docs/repository-indexes.md`, is the semantic owner for Trading Desk repository index ownership. The code owner is `python-backend/repository_indexes.py`. Local SQLite hardening and read-only local DB audits are separate and live in `docs/local-db-hardening.md` and `python-backend/local_db_hardening.py`.

Indexes are read-path and performance support. They are not proof semantics, not scanner safety, and not uniqueness constraints unless a separate constraint decision explicitly says so.

## Current Indexes

| Store id | Index | Table | Read path |
| --- | --- | --- | --- |
| `postgres_tracked_positions` | `idx_tracked_positions_status` | `tracked_positions` | `/api/positions` status filters, compact closed reads, and tracked-position status counts. |
| `postgres_tracked_positions` | `idx_tracked_positions_filled_at` | `tracked_positions` | Position list ordering by `filled_at DESC`. |
| `postgres_tracked_positions` | `idx_position_reviews_position_id` | `position_reviews` | Latest-review lookup by `position_id` and `reviewed_at DESC`. |
| `sqlite_tracked_positions_test_legacy` | `idx_tracked_positions_status` | `tracked_positions` | Explicit test/legacy status-filtered reads. |
| `sqlite_tracked_positions_test_legacy` | `idx_tracked_positions_filled_at` | `tracked_positions` | Explicit test/legacy list ordering by `filled_at DESC`. |
| `sqlite_tracked_positions_test_legacy` | `idx_position_reviews_position_id` | `position_reviews` | Explicit test/legacy latest-review lookup. |
| `sqlite_suggested_trades` | `idx_suggested_trades_status` | `suggested_trades` | `/api/suggested-trades` status filters. |
| `sqlite_suggested_trades` | `idx_suggested_trades_filled_at` | `suggested_trades` | Suggested-trade list ordering by `filled_at DESC`. |
| `sqlite_suggested_trades` | `idx_suggested_trade_reviews_position_id` | `suggested_trade_reviews` | Latest-review lookup by `position_id`, `reviewed_at DESC`, and `id DESC`. |

## Deferred Candidates

These are plausible but not yet created:

- `tracked_positions(status, filled_at DESC, id DESC)` for paged status-filtered tracked-position lists.
- `suggested_trades(status, filled_at DESC, id DESC)` for paged status-filtered suggested-trade lists.
- `position_reviews(position_id, reviewed_at DESC, id DESC)` for tracked-position latest-review tiebreaking.
- `tracked_positions(status, closed_at DESC)` for realized-P&L-since and closed-row status reads.

Do not add these in startup schema code without measured row counts, query-plan evidence, and a migration/maintenance plan. Postgres index creation can lock tables, and `CREATE INDEX CONCURRENTLY` does not fit the current transaction-style `init_schema()` path.

## Hard Rules

- Do not treat indexes as constraints. Unique indexes require both an index decision and a constraint decision.
- Do not add proof/truth indexes that imply correctness for `proof_eligible`, `proof_class`, OPRA source, quote freshness, scanner lineage, or research/backfill markers.
- Do not index AI commodity artifacts, `historical_options_store.py`, or `data/options-validation/options_history.db` through this Trading Desk repository index contract.
- Do not drop existing indexes without query-plan evidence and a separate migration plan.
- Do not add new Postgres index DDL in Point 13.

## Read-Only Audit

Use `scripts/audit_repository_indexes.py --json` to inspect current index metadata without mutating rows. Missing Postgres configuration is reported as skipped rather than falling back to SQLite.

Use `scripts/audit_local_databases.py --json` only for local DB file health, sidecar/backup inventory, and read-only integrity checks. Do not use the local DB audit to add, drop, repair, or infer index behavior.

## Implementation Anchors

- Index manifest: `python-backend/repository_indexes.py`
- Local DB hardening: `docs/local-db-hardening.md` and `python-backend/local_db_hardening.py`
- Read-only index audit: `scripts/audit_repository_indexes.py`
- Migration manifest and ledger: `python-backend/repository_migrations.py`
- Constraint boundary: `docs/repository-constraints.md`
- Contract tests: `tests/test_repository_indexes.py`
