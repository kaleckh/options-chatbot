# Repository Contract

This is the semantic owner for Trading Desk repository boundaries. It explains which stores own tracked positions and suggested trades, which methods the route and review layers expect, and which repository capabilities are optional read optimizations. Tracked/suggested route and row-shape parity is owned separately by `docs/trading-desk-record-parity.md` and `python-backend/repository_parity.py`. Local SQLite hardening is owned separately by `docs/local-db-hardening.md` and `python-backend/local_db_hardening.py`. Schema evolution is owned separately by `docs/repository-migrations.md` and `python-backend/repository_migrations.py`; constraint ownership is mapped in `docs/repository-constraints.md` and `python-backend/repository_constraints.py`; index ownership is mapped in `docs/repository-indexes.md` and `python-backend/repository_indexes.py`.

## Canonical Store Ownership

| Surface | Repository | Store | Production role |
| --- | --- | --- | --- |
| Tracked positions | `PostgresTrackedPositionsRepository` | Postgres through `DATABASE_URL` | Production tracked-position rows, reviews, closes, proof/readback counts, and runtime tracked-position health. |
| Tracked positions unavailable sentinel | `UnavailableTrackedPositionsRepository` | None | Fail-closed route readback when Postgres is absent or unavailable. It exposes the required method surface but raises on mutation/read methods. |
| Tracked positions memory double | `MemoryTrackedPositionsRepository` | In-memory list | Test and fixture repository only. It is not production storage. |
| Tracked positions SQLite double | `SqliteTrackedPositionsRepository` | SQLite | Explicit tests and legacy tools only. It is not the browser tracked-position fallback. |
| Suggested trades | `SQLiteSuggestedTradesRepository` | `chat_history.db` SQLite | Suggested-trade rows, reviews, and closes for local paper/hypothetical workflow state. |

Tracked positions are owned by Postgres. Missing `DATABASE_URL` must return `UnavailableTrackedPositionsRepository`; it must not silently fall back to SQLite. Suggested trades are owned by SQLite and remain separate from production tracked-position proof rows.

## Tracked/Suggested Parity Boundary

`docs/trading-desk-record-parity.md` and `python-backend/repository_parity.py` own the readable map of what tracked positions and suggested trades share and what must stay different.

Shared parity:

- read/create/review/close lifecycle vocabulary
- common position-shaped repository methods
- common normalized display row and `latest_review` keys
- shared manual/scanner-origin creation and review orchestration

Intentional differences:

- tracked positions use `postgres_tracked_positions` and `tracked_position`; suggested trades use `sqlite_suggested_trades` and `suggested_trade`
- tracked response envelopes stay `position` / `positions`; suggested envelopes stay `trade` / `trades`
- tracked rows may persist top-level `source_scan_*` and `proof_*` fields; suggested rows must not
- tracked create/review/close responses include `position_event_persistence`; suggested create/review/close responses must not
- suggested trades remain local paper/hypothetical workflow state and do not feed production proof or options-profit truth

## Interface Owner

`python-backend/repository_contracts.py` defines structural Protocols for the existing duck-typed repository surface:

- `TradingDeskPositionRepository`
- `TrackedPositionsRepository`
- `SuggestedTradesRepository`
- `SupportsCompactPositionList`
- `SupportsProfitStatusSnapshot`
- `SupportsPositionUpdate`
- `SupportsRealizedPnl`

These Protocols are readability and drift guards. Concrete repositories do not need to inherit from base classes, and route code should keep the current late-bound, duck-typed behavior.

## Required Methods

The shared Trading Desk position-shaped repository surface requires:

- `init_schema()`
- `create_position(payload)`
- `list_positions(status="open", *, limit=None, offset=0)`
- `get_position(position_id)`
- `save_review(position_id, review)`
- `close_position(position_id, exit_price, closed_at, exit_reason, notes=None, *, exit_execution_basis="manual_close", allow_zero_exit_price=False)`

Tracked-position repositories additionally require:

- `update_position(position_id, updates)`
- `get_realized_pnl_since(since)`

Tracked-position repositories may also expose optional read optimizations:

- `list_compact_positions(status="open", *, limit=None, offset=0)`
- `profit_status_snapshot()`

The optional methods are not required on suggested trades or unavailable sentinels. Call sites should keep using `callable(getattr(...))` for optional capabilities.

## Review And Proof Boundaries

`python-backend/positions_service.py` computes review guidance with `review_open_positions(repository, position_ids=None)` and persists the resulting review or close through the repository contract. Repositories persist normalized rows and latest-review snapshots; they do not own proof definitions.

Proof semantics stay in `docs/proof-evidence-contract.md`, `data/contracts/proof-evidence-contract.json`, and `python-backend/proof_contract.py`. `/api/proof-summary` and `/api/options-profit/status` consume repository rows and `profit_status_snapshot()` readbacks; they are not repository proof owners.

## Migration Boundary

Trading Desk repository schema changes must go through `python-backend/repository_migrations.py` and the rules in `docs/repository-migrations.md`. The repository interface contract can name migration ownership, but it does not approve new schema behavior by itself.

## Local DB Hardening Boundary

Local SQLite safety rules live in `docs/local-db-hardening.md` and `python-backend/local_db_hardening.py`. That contract classifies `chat_history.db` as the active mutable suggested-trade SQLite store, `data/tracked_positions.db` as explicit test/legacy storage only, and options-history, forward-evidence, market-cache, and AI commodity stores as outside Trading Desk repository hardening. Its audit command is read-only and must not initialize schema, repair rows, vacuum, delete files, or add a tracked-position SQLite fallback.

## Constraint Boundary

Trading Desk repository constraints are mapped in `python-backend/repository_constraints.py` and explained in `docs/repository-constraints.md`. Repository interfaces do not own DB constraints; proof semantics still stay in the proof contract, and API/service validators still own request-shape enforcement before persistence.

## Index Boundary

Trading Desk repository indexes are mapped in `python-backend/repository_indexes.py` and explained in `docs/repository-indexes.md`. Indexes support read paths and performance; they are not constraints, proof semantics, or route behavior.

## Hard Rules

1. Do not add a silent tracked-position SQLite fallback.
2. Do not make `MemoryTrackedPositionsRepository` or `SqliteTrackedPositionsRepository` production storage.
3. Do not force optional tracked-position methods onto suggested trades.
4. Do not change DB schemas, migrations, constraints, indexes, or pooling in this repository-interface contract; use `docs/repository-migrations.md`, `python-backend/repository_migrations.py`, `docs/repository-constraints.md`, and `python-backend/repository_constraints.py` for schema evolution and constraint ownership.
5. Do not replace test fakes with inheritance-heavy repositories; structural typing is enough.
6. Do not let repository readbacks redefine proof, auth, scanner creation safety, or lifecycle evidence semantics.

## Implementation Anchors

- Repository Protocols: `python-backend/repository_contracts.py`
- Tracked/suggested parity manifest: `python-backend/repository_parity.py` and `docs/trading-desk-record-parity.md`
- Local DB hardening manifest: `python-backend/local_db_hardening.py` and `docs/local-db-hardening.md`
- Repository migrations: `python-backend/repository_migrations.py` and `docs/repository-migrations.md`
- Repository constraints: `python-backend/repository_constraints.py` and `docs/repository-constraints.md`
- Repository indexes: `python-backend/repository_indexes.py` and `docs/repository-indexes.md`
- Tracked-position repositories: `python-backend/positions_repository.py`
- Suggested-trade repository: `python-backend/suggested_trades_repository.py`
- Review workflow: `python-backend/positions_service.py`
- FastAPI store globals: `python-backend/main.py`
- Route/store lifecycle headers: `src/lib/trading-desk/storeOwnership.ts`
- Contract tests: `tests/test_repository_contract.py`
