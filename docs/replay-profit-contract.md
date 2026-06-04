# Replay And Profit Contract

This is the semantic owner for replay/profit ownership boundaries. It explains where agents should look before changing replay diagnostics, scanner policy readbacks, proof/profit gates, or options-profit status.

## Canonical Ownership Map

| Responsibility | Owner | Notes |
| --- | --- | --- |
| Explicit replay run | `wfo_optimizer.run_historical_backtest` | Writes latest replay artifacts when the Strategy Lab run route is called. |
| Archived-forward replay | `wfo_optimizer.run_archived_forward_daily_backtest` | Replays archived `/api/scan` picks against exact-contract imported-daily evidence. |
| Replay readback assembly | `python-backend/replay_profit_service.py` | Decorator-free application service for cached report, metric-truth, forensics, stability, live-policy, exit-audit, comparison, and summary readbacks. |
| HTTP parsing and errors | `python-backend/main.py` | FastAPI composition root. Routes parse request knobs, run work in a thread, and translate exceptions to HTTP responses. |
| Metric truth report | `metric_truth_audit.py` | Builds calibration/profitability truth buckets from latest replay result. |
| Profitability forensics | `options_profitability_forensics.py` | Builds slice-based profitability diagnostics from latest replay result. |
| Scanner policy from replay | `wfo_optimizer.build_live_options_trade_policy` and `wfo_optimizer.build_playbook_exit_audit` | Produces replay-backed policy and exit audit readbacks consumed by scanner routes and `supervised_scan.py`. |
| Scanner application | `supervised_scan.py` | Applies policy and guardrails to live scan candidates; it does not own proof or row creation. |
| Proof/evidence semantics | `docs/proof-evidence-contract.md`, `data/contracts/proof-evidence-contract.json`, `python-backend/proof_contract.py` | Defines production proof, raw exact, manual exact, research/backfill, and lifecycle-only evidence. |
| Scanner creation safety | `docs/scanner-creation-safety-contract.md`, `data/contracts/scanner-creation-safety-contract.json` | Defines scanner-origin creation, scheduled auto-track, pending validation, and scanner pipeline stages. |
| Profit measurement gates | `options_profit_gate.py` | Consumes proof predicates and tracked-position evidence to evaluate loop health and claim readiness. It does not own proof definitions. |
| Profit-cycle state | `options_profit_state.py` and `options_profit_flywheel.py` | Own state artifact shape, active incumbents, canary state, and bounded profit-cycle decisions. |
| Options-profit status route | `GET /api/options-profit/status` in `python-backend/main.py` | Read-only status surface that combines state artifacts with runtime tracked-position health. It is not a proof owner and must not create or mutate rows. |

## Route Readback Contract

`python-backend/replay_profit_service.py` owns readback assembly for these FastAPI support surfaces:

- `GET /api/backtest/report`
- `GET /api/backtest/metric-truth`
- `POST /api/backtest/experiments`
- `GET /api/backtest/profitability-forensics`
- `GET /api/backtest/stability`
- `GET /api/backtest/live-policy`
- `GET /api/backtest/exit-audit`
- `GET /api/backtest/comparison`
- `GET /api/backtest/summary`

The service is late-bound through `BackendRouteContext`. It must not import canonical `main.py`, define FastAPI decorators, own route auth, own persistence, or change replay/profit thresholds. Cache keys, no-result payloads, and public response shapes belong to the existing route contracts and tests.

`data/contracts/proof-replay-golden-readbacks.json` pins deterministic readback expectations for proof counts, options-profit metrics, and replay-service summary assembly over test-only fixtures. The replay portion checks no-result shape, summary keys, cache-key prefixes, and request knobs through `python-backend/replay_profit_service.py`; it does not run WFO replay, validate profitability math, read live market data, or redefine proof/profit gates.

## Hard Rules

1. Do not move replay math, scanner policy generation, proof gates, or profit-cycle decisions into FastAPI route handlers.
2. Do not split `wfo_optimizer.py` behavior casually; create tests and a separate plan before moving replay engine internals.
3. Do not let replay profitability, manual exact rows, or research/backfill evidence relax `docs/proof-evidence-contract.md`.
4. Do not let options-profit status become a proof owner or row creation path.
5. Do not let scanner policy readbacks bypass `docs/scanner-creation-safety-contract.md`.
6. Keep application services decorator-free and late-bound so tests can patch backend globals after app creation.

## Implementation Anchors

- Route adapter and cache primitives: `python-backend/main.py`
- Replay/profit readback service: `python-backend/replay_profit_service.py`
- Service tests: `tests/test_replay_profit_service.py`
- Contract tests: `tests/test_replay_profit_contract.py` and `tests/test_golden_proof_replay_readbacks.py`
- Strategy Lab route lifecycle: `src/lib/strategy-lab/replayIntent.ts`
