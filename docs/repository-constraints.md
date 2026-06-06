# Repository Constraints

This file, `docs/repository-constraints.md`, is the semantic owner for Trading Desk repository invariants. The code owner is `python-backend/repository_constraints.py`. Local SQLite hardening is separate and lives in `docs/local-db-hardening.md` and `python-backend/local_db_hardening.py`. Index ownership is separate and lives in `docs/repository-indexes.md` and `python-backend/repository_indexes.py`.

## Enforcement Layers

| Layer | Owns | Current examples |
| --- | --- | --- |
| DB-enforced | Primitive relational safety that is already true for future writes without historical cleanup. | Primary keys, required columns, review foreign keys, migration-ledger primary key and checksum guard. |
| API/service-enforced | Request and payload shape before rows are persisted. | Positive `fill_price`, positive `contracts`, valid option fields, nonnegative manual close price, open-only review and close operations, close payloads that can persist canonical exit/P&L fields. |
| Proof-contract-owned | Trading proof truth that depends on source evidence, lineage, OPRA/freshness, research/backfill markers, and trusted exits. | `proof_eligible`, `proof_class`, live exact proof, manual exact evidence, truth-grade closed-row eligibility. |
| Deferred | Useful DB constraints that need an existing-row audit or a SQLite table rebuild before enforcement. | Status/direction `CHECK`s, positive numeric `CHECK`s, unique open-contract constraints, JSON-shape constraints, closed-row coherence constraints. |

## Current DB-Enforced Invariants

- `postgres_tracked_positions.tracked_positions.id` is a Postgres primary key.
- `postgres_tracked_positions.position_reviews.position_id` references `tracked_positions(id)` with cascade delete.
- `sqlite_suggested_trades.suggested_trades.id` is a SQLite primary key.
- `sqlite_suggested_trades.suggested_trade_reviews.position_id` references `suggested_trades(id)` with cascade delete, and `SQLiteSuggestedTradesRepository._connect()` enables `PRAGMA foreign_keys=ON`.
- `sqlite_tracked_positions_test_legacy.position_reviews.position_id` references `tracked_positions(id)` with cascade delete, and `SqliteTrackedPositionsRepository._connect()` enables `PRAGMA foreign_keys=ON`.
- `repository_schema_migrations` uses `(store_id, migration_id)` as its primary key and checksum guard.

## API/Service-Enforced Invariants

`positions_service.build_position_payload()` and the FastAPI create/close endpoints currently enforce the new-row shape that future DB `CHECK` constraints may mirror:

- `status` is created as `open`; close paths set `closed`.
- `direction` must be `call` or `put`.
- `ticker`, `strike`, `expiry`, and exact contract identity requirements are validated before persistence.
- `contracts`, `entry_option_price`, `strike`, `stop_loss_pct`, `profit_target_pct`, and `time_exit_day` are positive.
- manual close `exit_price` is finite and nonnegative; zero remains valid for worthless executable exits.
- review and close operations require the row to be open.
- closed suggested-trade and tracked-position write paths must persist canonical exit execution price and gross/net realized P&L whenever an executable close exists.

## Proof Boundary

Do not encode production proof as a DB constraint. Proof remains owned by `docs/proof-evidence-contract.md`, `data/contracts/proof-evidence-contract.json`, and `python-backend/proof_contract.py`.

Examples that must stay out of SQL constraints:

- `proof_eligible` implies `proof_class=live_scan_exact_contract`
- OPRA/NBBO source trust
- quote freshness
- source-scan lineage verification
- research/backfill and migration identity blockers
- trusted executable exit evidence for truth-grade closed rows

## Deferred DB Constraint Candidates

Add these only after a read-only audit proves existing rows are clean or intentionally exempt:

- `status IN ('open', 'closed')`
- `direction IN ('call', 'put')`
- non-empty `ticker`
- positive `strike`, `contracts`, `entry_option_price`, `stop_loss_pct`, `profit_target_pct`, and `time_exit_day`
- nullable nonnegative `entry_fee_total_usd`, `exit_option_price`, `exit_execution_price`, and `fee_total_usd`
- optional unique open exact-contract constraints per store
- JSON shape checks for source snapshots, warnings, and metrics snapshots
- closed-row coherence checks

SQLite table-level `CHECK` constraints require a table rebuild for existing stores, so they are deferred. Postgres `NOT VALID` checks also affect future updates to legacy-invalid rows, so they are deferred until the audit is clean.

## Read-Only Audit

Use `npm run options:audit:data-integrity` for the strict project gate, or `scripts/audit_repository_constraints.py --json` for a direct read-only inspection. The CLI loads local env before resolving `DATABASE_URL`, so a normal local run audits Postgres instead of silently skipping it. Missing Postgres configuration is still reported as skipped rather than falling back to SQLite. AI commodity artifacts, `historical_options_store.py`, and `data/options-validation/options_history.db` are outside this Trading Desk repository constraint contract.

Strict mode exits nonzero only for hard violations. Research/backfill tracked rows that are closed but still missing realized P&L because the exact executable exit leg quote is absent are diagnostics: they must remain visible, unpriced, and excluded from live proof/exposure math, but they do not fail strict mode. The June 5 zero-bid repair cleared the prior diagnostics by retaining exact `bid=0, ask>0` OPRA/NBBO rows and pricing historical close/mark paths side-aware at long bid and short ask. Current June 5 readback is `pass_or_skipped`: SQLite suggested trades `pass`, Postgres tracked positions `pass`, hard violations `0`, and diagnostics `0`.

## Constraint Audit Behavior Matrix

| Case | Expected behavior | Test anchor |
| --- | --- | --- |
| Clean initialized SQLite suggested store | Audit returns `pass` with no violations. | `tests/test_repository_constraints.py` |
| Missing SQLite suggested store | Audit returns `skipped` and does not create the file. | `tests/test_repository_constraints.py` |
| Dirty SQLite suggested rows | Audit returns `violations_found` for status, direction, ticker, positive-number, nonnegative-number, review recommendation, and review numeric checks. | `tests/test_repository_constraints.py` |
| Closed SQLite suggested trade missing stored exit/P&L | Audit returns `violations_found` under `suggested_trades_closed_missing_realized_pnl`. | `tests/test_repository_constraints.py` |
| Orphan suggested review | Audit reports the orphan without repairing it. | `tests/test_repository_constraints.py` |
| Missing Postgres configuration | Audit returns `skipped`; tracked positions do not fall back to SQLite. | `tests/test_repository_constraints.py` |
| Closed production tracked row missing realized P&L | Audit returns `violations_found` under `tracked_positions_closed_production_missing_realized_pnl`. | `scripts/audit_repository_constraints.py` |
| Closed unclassified tracked row missing realized P&L | Audit returns `violations_found` under `tracked_positions_closed_unclassified_missing_realized_pnl`. | `scripts/audit_repository_constraints.py` |
| Closed research/backfill tracked row missing exact exit quote | Audit returns `pass_with_diagnostics`; strict mode does not fail, and the row stays unpriced/quarantined. | `scripts/audit_repository_constraints.py` |
| Strict mode with diagnostics only | `--strict` exits `0`; diagnostics must still be read and repaired only with trusted exact evidence. | `scripts/audit_repository_constraints.py` |
| Deferred candidates | They remain audit/readiness targets, not active DB `CHECK` constraints. | `tests/test_repository_constraints.py` |
| Proof truth | Production proof and truth-grade semantics stay in the proof contract, not SQL. | `tests/test_repository_constraints.py` |

For local SQLite file ownership, backup rules, sidecar inventory, and read-only `quick_check` / `foreign_key_check`, use `scripts/audit_local_databases.py --json` under the contract in `docs/local-db-hardening.md`.

## Implementation Anchors

- Constraint manifest: `python-backend/repository_constraints.py`
- Local DB hardening: `docs/local-db-hardening.md` and `python-backend/local_db_hardening.py`
- Migration manifest and ledger: `python-backend/repository_migrations.py`
- Tracked-position repository: `python-backend/positions_repository.py`
- Suggested-trade repository: `python-backend/suggested_trades_repository.py`
- Constraint audit: `scripts/audit_repository_constraints.py`
- Contract tests: `tests/test_repository_constraints.py`
