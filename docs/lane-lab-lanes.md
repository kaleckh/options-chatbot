# Lane Lab Lanes

Last updated: 2026-05-21

## Purpose

This registry defines the next paper-trading lanes to test without overstating the current evidence. Current listed trades can be profitable and still not be promotion-grade proof until the system records exact fills, exits, and lane-specific outcomes.

## Three Tiers

| Tier | Role | What It Answers | Promotion Rule |
| --- | --- | --- | --- |
| 1 | First Five | Which immediate lane ideas are worth testing first? | Must either produce a scored result from current artifacts or a concrete blocker that can be fixed. |
| 2 | Expansion | Which new strategy families diversify the current bullish call-spread bias? | Must collect enough tagged paper results or exact option history before sizing up. |
| 3 | Controls / Portfolio | Which controls, exits, and portfolio wrappers decide whether the edge is real? | Must compare against the accepted lanes and reduce false confidence, slippage, drawdown, or concentration. |

## First Five

| Priority | Lane | Current Result | Required Test |
| ---: | --- | --- | --- |
| 1 | `fill_discipline` | Current paper book is profitable, but only partial evidence. | Log timestamped two-leg quotes, spread mid, attempted limit, fill/no-fill, entry, review, and close. |
| 2 | `liquidity_first_spread` | Blocked by missing alternative-contract logging. | Persist top 3 spread alternatives per candidate and compare liquidity-first selection against current selection. |
| 3 | `high_debit_control` | Historical exact sample is thin. Cheap exact rows currently look better, but high-debit exact control has zero rows. | Shadow-reject debit verticals above 55% width and compare to cheap debit buckets. |
| 4 | `gld_macro_breakout` | Blocked by missing trusted GLD option history. | Import GLD option history, then paper 30-45 DTE debit spreads after daily breakout/breakdown signals. |
| 5 | `relative_strength_pullback` | Pending tagged paper log. | Track RS vs SPY, SMA50, RSI14, 3-day pullback, option fill, and outcome. |

## Tier 1 Lane Specs

| Priority | Lane | Hypothesis | Pass Bar |
| ---: | --- | --- | --- |
| 1 | `fill_discipline` | Current signals become more trustworthy when only fillable spreads are counted. | 30 filled paper trades, fill degradation under 10% of debit, positive expectancy, missed-fill rate under 40%. |
| 2 | `liquidity_first_spread` | The most closable spread may beat the best-looking theoretical spread. | 40 opportunities with lower slippage or failed exits and equal-or-better expectancy. |
| 3 | `high_debit_control` | Debit verticals above 55% of width underperform cheaper debit verticals. | Cheap buckets beat high-debit buckets on avg P&L, PF, and drawdown over 25+ trades. |
| 4 | `gld_macro_breakout` | GLD can create a non-equity beta lane distinct from tech/index calls. | PF >= 1.20, positive avg net P&L, median loser below 45% debit. |
| 5 | `relative_strength_pullback` | Strong names after controlled pullbacks beat momentum chasing. | 40 trades, underlying win rate >= 55%, avg underlying return >= 0.8%, option expectancy > 8%. |

## Tier 2 Lane Specs

| Priority | Lane | Hypothesis | Pass Bar |
| ---: | --- | --- | --- |
| 6 | `tlt_duration_shock` | TLT can diversify when equity call lanes are blocked. | Event-excluded cohort positive with PF >= 1.10. |
| 7 | `iwm_small_cap_risk` | IWM relative strength/weakness can create cleaner small-cap expansion or reversal trades. | 25 closed trades, PF >= 1.15, avg net P&L > 0, max drawdown < 4R. |
| 8 | `volatility_compression_breakout` | Low IV/HV compression can underprice directional expansion. | +1 ATR before -1 ATR at least 56% and option expectancy > 10%. |
| 9 | `bull_put_credit_spread` | Defined-risk put credit spreads may monetize bullish/neutral setups better than buying upside. | 40 trades, PF > 1.20, smoother drawdown than debit lanes. |
| 10 | `bearish_put_debit_spread` | Confirmed weak regimes need a bearish defined-risk lane. | Win rate > 45% and average winner >= 1.25x average loser. |
| 11 | `post_event_vol_crush` | After event risk passes inside expected move, IV collapse favors defined-risk premium selling. | Win rate > 58%, positive average R, and controlled tail losses. |
| 32 | `ai_commodity_infra_observation` | AI data-centre growth may create tradable stress in power, grid, copper, silver, lithium, and uranium proxies, but the shortage narrative needs liquidity-first proof. | 40 tagged trades, PF >= 1.15, positive avg net P&L, and no single sub-theme providing more than 50% of net profit. |

`ai_commodity_infra_observation` now gets its scan universe from `data/ai-commodity-infra/universe.json`. The exact proof loop requires the full scan-eligible universe to have Alpaca SIP/OPRA daily snapshots; core/conditional buckets remain thematic metadata and do not narrow the profitability gate.

## Tier 3 Lane Specs

| Priority | Lane | Hypothesis | Pass Bar |
| ---: | --- | --- | --- |
| 12 | `iron_condor_range` | Range-bound regimes can outperform directional lanes with defined-risk premium selling. | Positive expectancy with tolerable drawdown versus credit collected. |
| 13 | `market_neutral_premium_control` | Some bullish-lane performance may be generic premium/regime behavior. | Clarifies whether direction matters; concerning if it beats directional lanes with lower drawdown. |
| 14 | `no_trade_opportunity_cost` | Rejected near-misses should underperform accepted trades if filters help. | Near-misses underperform accepted trades or add volatility without expectancy. |
| 15 | `random_approved_control` | Real filters should beat constrained random selection from the same eligible universe. | Actual lanes beat random on expectancy, drawdown, and consistency. |
| 16 | `inverse_signal_bearish_control` | Opposite-side trades should underperform if bullish signals have directional value. | Inverse expectancy is materially worse than the bullish lane. |
| 17 | `risk_budget_sizing` | Vol/debit/correlation sizing should beat uniform sizing. | Similar expectancy with at least 25% lower max drawdown. |
| 18 | `mechanical_profit_harvest` | Earlier harvesting can reduce giveback and improve realized expectancy. | Giveback falls and avg realized P&L rises without major PF deterioration. |
| 19 | `quote_deterioration_stop` | Quote/structure stops can reduce worst-decile losses. | Near-total losses fall without excessive false exits. |
| 20 | `portfolio_throttle` | Duplicate beta theses should be throttled. | Drawdown and clustered losses fall while preserving most net profit. |
| 21 | `sector_rotation_confirmation` | Sector inflow confirmation improves single-name entries. | Beats index controls by >= 0.4% avg underlying return. |
| 22 | `earnings_premium_avoidance` | Post-earnings reset beats entering near expensive pre-earnings IV. | Reset expectancy exceeds pre-earnings shadow by >= 15 points. |
| 23 | `rsi_trend_reclaim` | RSI reclaim separates healthy pullbacks from weak bounces. | Beats simple trend entries by >= 0.5% avg underlying return. |
| 24 | `breadth_gated_index` | Index trades improve when breadth confirms the move. | Expectancy improves 20% and loser frequency drops 10%. |
| 25 | `monday_gap_fade` | Monday failed gaps can partially retrace. | Intraday gains survive spreads and slippage. |
| 26 | `opex_pin_risk` | OpEx/month-end behavior differs from normal trend lanes. | OI filter improves win rate/drawdown versus baseline condors. |
| 27 | `calendar_volatility` | Calendars can profit from contained near-term movement and favorable term structure. | Positive expectancy with lower directional dependence than verticals. |
| 28 | `pmcc_diagonal` | Long call diagonals can smooth bullish exposure. | 10-15 campaigns are smoother and avoid large drawdowns. |
| 29 | `xle_energy_inflation` | Energy options diversify away from tech/index beta. | One cohort has PF >= 1.15 and combined avg net P&L > 0. |
| 30 | `xlf_financials` | Financials add rate/credit-sensitive exposure distinct from tech momentum. | XLF alone works before KRE is considered. |
| 31 | `smh_semiconductor` | SMH can capture chip momentum without single-name concentration. | SMH beats single-name observation on risk-adjusted expectancy and PF >= 1.20. |

## Operating Rules

- Do not grade from closed historical trades when the user asks for current listed trades.
- Treat open marked paper P&L as useful evidence, not proof for live cash.
- Keep research, exact-contract proof, and forward paper evidence separate.
- Every new lane must have a lane id, tier, required fields, pass bar, and blocker reason.
- Any lane blocked by data stays blocked until trusted option history or tagged paper logs exist.
