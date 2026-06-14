# Local DB Hardening

This file, `docs/local-db-hardening.md`, is the semantic owner for local SQLite database safety. The code owner is `python-backend/local_db_hardening.py`, and the read-only audit is `scripts/audit_local_databases.py`.

Point 15 is a guardrail and readability point. It classifies local DB files, documents safe handling, and adds a read-only health audit. It does not migrate, repair, vacuum, delete, checkpoint, or rewrite any local database.

## Covered Local DB Roles

| DB role | Path | Scope | Rule |
| --- | --- | --- | --- |
| Active suggested-trade SQLite | `chat_history.db` | Trading Desk suggested trades and local paper workflow state | Mutable through `SQLiteSuggestedTradesRepository`; repository write connections enable `PRAGMA foreign_keys=ON`. |
| Explicit tracked SQLite legacy/test DB | `data/tracked_positions.db` | Tests and legacy tools only | Never a browser tracked-position fallback; Postgres through `DATABASE_URL` owns production tracked positions. |
| SQLite sidecars/backups | `*.db-wal`, `*.db-shm`, `chat_history.backup-*.db`, `data/tracked_positions.backup-*` | Local runtime or recovery files | Ignored locally; audit may enumerate but must not delete or rewrite them. |
| Evidence backup directory | `data/backups/**` | Nightly evidence-store backups | Ignored locally; owned by `scripts/backup_evidence_stores.py` and rotated by that script only. |

## Classified Outside This Contract

These files are local databases or DB-like artifacts, but they are not Trading Desk repository hardening targets:

- `data/options-validation/options_history.db`
  - imported options truth store owned by historical options import/replay tooling
- `data/options-validation/forward_tracking_authoritative.db`
  - canonical forward-evidence ledger
- `data/options-validation/forward_tracking.db`
  - archive forward-evidence ledger
- `market_data.db`
  - market data cache
- `data/ai-commodity-infra/*`
  - separate AI commodity proof-first lane artifacts

Do not run Trading Desk repository migrations, constraints, indexes, or local DB cleanup against those stores from this contract.

## Read-Only Audit

Run:

```bash
uv run --locked python scripts/audit_local_databases.py --json
```

The audit:

- opens existing SQLite files with `mode=ro`
- skips missing DB files without creating them
- runs `PRAGMA quick_check`
- runs `PRAGMA foreign_key_check`
- checks required tables for the covered Trading Desk SQLite roles
- reports optional migration-ledger absence as a warning, not a repair task
- reports DB size, page metadata, journal mode, sidecar presence, and backup presence
- classifies out-of-scope stores without opening large truth/cache DBs by default

The audit must not call repository `init_schema()`, set PRAGMAs, run `VACUUM`, run `REINDEX`, checkpoint WAL files, delete backups, rebuild tables, or mutate row data.

Use `--include-legacy-tracked` only when intentionally inspecting the explicit legacy/test tracked SQLite DB:

```bash
uv run --locked python scripts/audit_local_databases.py --include-legacy-tracked --json
```

## Backup Discipline

For manual mutation or one-off repair scripts:

- take an application-aware SQLite backup before writes
- prefer SQLite's backup API or stop writers before copying a live DB file
- record the backup path in the repair output
- keep backups ignored unless a specific recovery workflow requires publishing one
- do not prune backup or sidecar files from audit scripts

For operational survivability:

- run `npm run evidence:backup` nightly on the authoritative evidence host
- run `npm run evidence:backup:weekly` from a scheduled weekly task after setting `OPTIONS_BACKUP_WEEKLY_COPY_DIR` to an off-machine target
- the backup script uses SQLite's backup API for `chat_history.db`, `data/options-validation/forward_tracking_authoritative.db`, and `data/options-validation/options_history.db`
- the same script uses `pg_dump --format=custom` for Postgres tracked positions when `DATABASE_URL` or `OPTIONS_BACKUP_DATABASE_URL` is configured
- generated runs live under ignored `data/backups/<timestamp>/` and are rotated after `14` days by the backup script, not by the read-only audit

## Hard Rules

- Do not add a silent tracked-position SQLite fallback.
- Do not move suggested trades to Postgres in this point.
- Do not change proof, scanner, replay, auth, route payload, or lifecycle evidence semantics.
- Do not add schema DDL, migrations, constraints, indexes, or table rebuilds through local DB hardening.
- Do not change `chat_history.db` journal mode in Point 15.
- Do not include AI commodity, options-history, forward-evidence, or market-cache stores in Trading Desk repository hardening.
- Do not treat `data/backups/**` as an active database source.

## Implementation Anchors

- Local DB manifest: `python-backend/local_db_hardening.py`
- Read-only local DB audit: `scripts/audit_local_databases.py`
- Evidence backup script: `scripts/backup_evidence_stores.py`
- Suggested-trade repository: `python-backend/suggested_trades_repository.py`
- Explicit legacy/test tracked SQLite repository: `python-backend/positions_repository.py`
- Repository ownership: `docs/repository-contract.md`
- Schema migrations: `docs/repository-migrations.md`
- Constraints: `docs/repository-constraints.md`
- Indexes: `docs/repository-indexes.md`
- Tracked/suggested parity: `docs/trading-desk-record-parity.md`
- Contract tests: `tests/test_local_db_hardening.py`
