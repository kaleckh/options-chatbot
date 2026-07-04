# Regular Options Phase 2 Drop Decomposition

- Status: `phase2_drop_decomposition_ready`.
- Target selection date: `2026-07-02`.
- Blockers: `[]`.
- Scheduled sessions: `77`.
- Raw candidates / returned picks: `0` / `0`.
- Aggregate drops: `2398`; throughput latest match `True`.
- Symbol drop-reason rows: `2398`; throughput latest match `True`.
- Liquidity/history rows: `688` (0.286906).
- Returned-pick rate over recorded drops: `0.0`.

## Top Drop Keys

- `momentum`: `1710` (0.713094).
- `option_liquidity`: `384` (0.160133).
- `history_or_liquidity`: `304` (0.126772).

## Top Symbols

- `DIA`: `77` (0.03211).
- `IWM`: `77` (0.03211).
- `QQQ`: `77` (0.03211).
- `SPY`: `77` (0.03211).
- `AA`: `38` (0.015847).
- `AAPL`: `38` (0.015847).
- `ABBV`: `38` (0.015847).
- `AMD`: `38` (0.015847).
- `AMT`: `38` (0.015847).
- `AMZN`: `38` (0.015847).

## Monthly Breakdown

| Month | Symbol Drop Reasons | Top Drop Keys |
|---|---:|---|
| `2026-07` | 2398 | history_or_liquidity=304, momentum=1710, option_liquidity=384 |

## Production-Gate Survival By Playbook

| Playbook | Sessions | Drops | Returned Picks | Returned Rate |
|---|---:|---:|---:|---:|
| `bullish_pullback_observation` | 38 | 2242 | 0 | 0.0 |
| `volatility_expansion_observation` | 39 | 156 | 0 | 0.0 |

## Boundary

This decomposition is read-only diagnostic evidence about scheduled Phase 2 drop reasons. It does not change scanner policy, filters, thresholds, proof bars, stops, sizing, live validation, auto-track, broker behavior, cohort rows, quote stores, evidence stores, holdout state, accepted profitability, or promotion.
