# Trading Desk Record Parity

This file, `docs/trading-desk-record-parity.md`, is the semantic owner for how tracked positions and suggested trades intentionally line up without becoming the same thing. The code owner is `python-backend/repository_parity.py`.

Tracked positions and suggested trades share enough shape that the Trading Desk UI and review service can treat them as position-shaped rows. That parity is for readability and workflow reuse only. Suggested trades are local paper/hypothetical ideas, not production proof rows, broker fills, or a fallback store for tracked positions.

## Shared Surfaces

| Surface | Shared rule |
| --- | --- |
| Lifecycle vocabulary | Both route families expose `read`, `create`, `review`, and `close` lifecycle contracts. |
| Repository method surface | Both support `init_schema`, `create_position`, `list_positions`, `get_position`, `save_review`, and `close_position`. |
| Creation workflow | Manual and scanner-origin creates share `positions_service.build_position_payload()` and the scanner creation-safety contract. |
| Review workflow | Both route families can use `positions_service.review_open_positions()` and return a normalized `latest_review`. |
| Close workflow | Both store exit price, close time, realized P&L snapshot fields, and a synthetic SELL latest review for closed rows. |
| Display row shape | Common Trading Desk fields such as ticker, contract, fill, stop/target, P&L, notes, and latest review stay under the same names. |

`src/lib/types.ts` currently defines `SuggestedTrade = TrackedPosition`. Treat that as a shared display-row alias only. It does not imply shared proof status, shared storage, shared route envelopes, or shared production role.

## Intentional Differences

| Boundary | Tracked positions | Suggested trades |
| --- | --- | --- |
| Store id | `postgres_tracked_positions` | `sqlite_suggested_trades` |
| Record class | `tracked_position` | `suggested_trade` |
| Response envelope | `position` / `positions` | `trade` / `trades` |
| Repository owner | `PostgresTrackedPositionsRepository` through `DATABASE_URL` | `SQLiteSuggestedTradesRepository` through `chat_history.db` |
| Production role | Production tracked-position rows, reviews, closes, proof/readback counts, and runtime health | Local paper/hypothetical workflow state |
| Proof/source-scan top-level fields | May persist `source_scan_*` and `proof_*` fields | Must not persist those top-level fields |
| Lifecycle event persistence | Create/review/close responses include `position_event_persistence` | Create/review/close responses must not include `position_event_persistence` |
| Profit/proof readbacks | May feed `/api/proof-summary` and `/api/options-profit/status` through tracked-only readbacks | Must not feed production proof/profit truth |
| Optional capabilities | May expose `list_compact_positions`, `profit_status_snapshot`, and `get_realized_pnl_since` | Must not be required to expose tracked-only capabilities |
| Close meaning | A tracked manual close can be a production row mutation, subject to proof/evidence rules | `manual_hypothetical_close` is paper workflow state |

## Hard Rules

- Do not merge suggested trades into tracked positions.
- Do not add a silent SQLite fallback for tracked positions.
- Do not add top-level `proof_*` or `source_scan_*` columns to `suggested_trades` as part of parity work.
- Do not add `position_event_persistence` to suggested-trade mutation responses.
- Do not require suggested trades to implement `profit_status_snapshot`, `list_compact_positions`, `update_position`, or `get_realized_pnl_since`.
- Do not count suggested trades in production proof, truth-grade, or options-profit status claims.
- Do not normalize public response envelopes from `trade(s)` to `position(s)` just because the row shapes overlap.

## Executable Row-Shape Test Map

`tests/test_trading_desk_record_parity.py` owns the executable parity smoke tests. They create the same canonical display-row payload through `MemoryTrackedPositionsRepository` and `SQLiteSuggestedTradesRepository`, then prove the shared row and review fields stay aligned without implying shared production meaning.

| Guard | Runtime proof |
| --- | --- |
| Open row parity | `test_executable_open_rows_share_common_display_fields_but_keep_tracked_only_fields_split` asserts both rows expose every `COMMON_POSITION_ROW_FIELDS` key and match representative shared display values. |
| Suggested proof/source boundary | The open-row test proves tracked rows expose top-level `source_scan_*` and `proof_*` fields, while suggested rows omit those top-level fields and may preserve the scanner context only inside `source_pick_snapshot`. |
| Review shape parity | `test_executable_review_and_close_rows_share_common_shapes_without_merging_meaning` saves the same review into both stores and asserts both `latest_review` payloads exactly match `COMMON_LATEST_REVIEW_FIELDS`. |
| Close shape parity | The review/close test closes both rows and asserts common exit, realized P&L, fee, and synthetic `SELL` review fields stay aligned while suggested rows still omit tracked-only top-level proof/source fields. |

## Implementation Anchors

- Parity manifest: `python-backend/repository_parity.py`
- API body models: `docs/trading-desk-api-models.md` and `python-backend/trading_desk_api_models.py`
- Repository contract: `docs/repository-contract.md` and `python-backend/repository_contracts.py`
- Store headers: `src/lib/trading-desk/storeOwnership.ts`
- Mutation intent headers: `src/lib/trading-desk/mutationIntent.ts`
- Tracked repository: `python-backend/positions_repository.py`
- Suggested repository: `python-backend/suggested_trades_repository.py`
- FastAPI route adapters: `python-backend/main.py`
- Scanner creation safety: `docs/scanner-creation-safety-contract.md`
- Proof/evidence contract: `docs/proof-evidence-contract.md`
- Contract tests: `tests/test_trading_desk_record_parity.py`
