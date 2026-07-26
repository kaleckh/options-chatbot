# Regular Options Post-Earnings Fallback Terminal Verdict

Date: 2026-07-26  
Verdict: `DEAD_ON_CONSTRUCTIBILITY`

## Decision

The frozen post-earnings premium-selling fallback is terminal. On its 2020-2021 OOS partition, only 13
events pass the complete entry geometry: 7 in 2020 and 6 in 2021. They occupy 10 independent event-week
clusters and 7 distinct months.

| Power measure | Measured ceiling | Required | Result |
| --- | ---: | ---: | --- |
| Closed observations | 13 | 60 | Fail |
| Independent event-week clusters | 10 | 20 | Fail |
| Distinct months | 7 | 12 | Fail |

Four OOS surfaces were provider-unavailable. Even granting the impossible best case that all four would
pass every construction filter raises the event ceiling only to 17, still below the 20-cluster minimum
even if every added event were independent. Outcome acquisition cannot rescue a contract that cannot
produce the minimum test population.

This supersedes
`data/profitability-lab/regular-options-post-earnings-fallback-feasibility/latest.json` and its status
`portfolio_capacity_conditional_on_train_early_exit_frequency_do_not_acquire_quotes_yet`. Its optimistic
70 and pessimistic 44 observations were concurrency bounds over the 72 semantic OOS events. They did not
apply the four-leg quote/liquidity filter or minimum-credit rule. They were valid for their narrower
calendar-capacity question but wrong as estimates of testable contract capacity; measured capacity is 13.

## Entry geometry

Rejection causes are nonexclusive. Pass-rate denominators are measured four-leg surfaces.

| Year | Measured | Symmetry fail | Any leg spread >25% | Minimum-credit fail | Pass | Pass rate |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2018 | 36 | 6 | 31 | 20 | 5 | 13.9% |
| 2019 | 34 | 4 | 30 | 12 | 3 | 8.8% |
| 2020 | 32 | 11 | 24 | 19 | 7 | 21.9% |
| 2021 | 36 | 13 | 26 | 25 | 6 | 16.7% |

Across all four years, 111/138 measured events fail the leg-spread rule, versus 34/138 failing symmetry
and 76/138 failing minimum credit. At leg level, 285/552 selected legs (51.6%) exceed the contract's
25%-of-midpoint limit. Leg-spread rejection dominates; symmetry is not the principal constraint.

The measured distributions below are Q1 / median / Q3. Spread values are full bid-ask width as a fraction
of midpoint; executable credit is short-leg bids minus long-leg asks.

| Year | Selected-leg spread | Legs >25% | Event-weighted spread | Executable credit/share | Credit / maximum wing |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2018 | 13.2% / 26.3% / 56.0% | 77/144 (53.5%) | 16.4% / 24.5% / 46.9% | $0.100 / $0.265 / $0.535 | 3.6% / 9.3% / 13.0% |
| 2019 | 10.0% / 20.7% / 47.1% | 60/136 (44.1%) | 13.8% / 18.6% / 30.7% | $0.193 / $0.330 / $0.745 | 9.4% / 11.2% / 13.5% |
| 2020 | 11.4% / 29.4% / 86.5% | 69/128 (53.9%) | 15.6% / 29.2% / 64.7% | $0.085 / $0.260 / $0.745 | 1.8% / 8.2% / 12.3% |
| 2021 | 12.2% / 33.6% / 106.3% | 79/144 (54.9%) | 14.2% / 39.5% / 107.3% | -$1.187 / $0.115 / $0.458 | -13.7% / 3.7% / 12.6% |

The negative 2021 lower quartile means at least one quarter of measured structures had crossed-NBBO entry
credit no better than -13.7% of maximum wing width.

## Economic burden, without outcomes

The 13 passing OOS events have median event-weighted full spread 10.1% and median executable credit 14.0%
of maximum wing. Mapping those measurements to the pre-existing 10%-spread / 15%-credit cost cell and the
measurement's explicit $5.60 one-lot round-trip fee assumption gives:

| Spread stress | Gross PF required for net PF 1.6 | Gross PF required for net PF 2.0 |
| ---: | ---: | ---: |
| 1.0x | 3.395 | 4.244 |
| 1.5x | 4.624 | 5.780 |
| 2.0x | 6.729 | 8.411 |

This is an entry-cost hurdle, not measured profitability. It independently shows demanding economics, but
constructibility is already decisive before any outcome test.

## Contract specification defects

The frozen contract is not independently executable as written:

1. Neither it nor its cited supporting contracts freezes a numeric per-contract/exchange fee schedule.
   The later geometry measurement had to introduce a separate $5.60 round-trip modeling assumption.
2. “Maximum wing width” is not frozen to a numeric width or cap; it is only derived after model-selected
   strikes exist.
3. `minimum_credit` requires credit to “strictly exceed round-trip fees” while the referenced fee amount is
   undefined in the contract. Contract-only eligibility is therefore non-deterministic.

These defects reinforce the terminal decision but do not cause it: 13 constructible events remain
insufficient under any reasonable resolution of them.

## Evidence, provenance, and acquisition cost

The review path was: Claude repository audit; Fable adversarial review (`agree with reservations`);
GPT-5.6-sol dissent; cost arithmetic (`INDETERMINATE_WITHOUT_QUOTES`); then the entry-geometry measurement
(`DEAD_ON_CONSTRUCTIBILITY`).

The decisive measurement artifacts are under
`data/profitability-lab/regular-options-fallback-entry-geometry/`. Acquisition attempted all 73 authorized
symbol-entry-date targets in 80 provider requests, including 7 bounded retries. It produced 68 usable
chains and 5 unavailable/empty chains; 4 of those 5 are OOS. The supplement contains 13,829 entry-only
rows across 68 symbol-entry dates and occupies 7,804,585 bytes (7.44 MiB). Total new geometry-directory
bytes were 8,145,392 (7.77 MiB).

The existing `data/options-validation/options_history.db` remained at 44,857,851,904 bytes with mtime
2026-07-14T08:06:04.5393832Z (`1784016364539383200` ns). The measurement opened it read-only/query-only
and wrote fetched rows only to the standalone supplement.

## Limits

This verdict does **not** economically falsify post-earnings short volatility as a phenomenon. No outcome,
exit quote, holding-period result, P&L, position, tracked trade, or broker fill was accessed. It establishes
the narrower and sufficient result that this frozen contract, on these nine symbols, cannot be constructed
densely enough to test.

The provider supplied bid/ask rows but no Greeks, IV, or underlying price. Leg selection therefore used a
same-timestamp parity-inferred expiration forward and a robust near-forward Black-76 volatility estimate at
4.5% to select the 0.15/0.05-delta legs. Small strike-selection differences versus provider Greeks remain
possible. They cannot bridge a 13-event ceiling to the required 60 observations or 20 independent clusters.

