# External Evidence Review: Retail-Accessible Options Edges (2026-07-07)

Synthesized from a two-round adversarially-verified web research pass (each claim voted by 3 independent skeptic agents against primary sources). Status labels: **[3-0]** = unanimously verified against source; **[extracted]** = pulled from a credible primary source but verification votes were cut off by session limits. This document is research context only — not profitability proof, not a policy change.

## Primary sources

1. Bondarenko, "Why Are Put Options So Expensive?" (SSRN 375784)
2. Bondarenko/CBOE, "Historical Performance of Put-Writing Strategies" (PUT/WPUT index study, 1986–2018)
3. AQR, "Understanding the Volatility Risk Premium" (1996–2016)
4. Todorov (Kellogg), option tail-risk pricing papers
5. SSRN 2204549 (earnings-announcement straddle returns literature)

## Verified core (survived 3-0 skeptic votes)

- **The index volatility/put risk premium is large**: 1987–2000 one-month SPX futures puts earned buyers −39%/month (ATM) to −95%/month (deep OTM) — sellers captured the mirror image. **[3-0]**
- **It is persistent, not one regime**: significantly negative put returns in all four tested subperiods, including the one containing the 1987 crash (−27% to −12%/month even there). **[3-0]**
- **VRP averaged 4.2 vol points 1990–2018** (VIX 19.3 vs realized 15.1), positive in ~28 of 29 calendar years (2008 the exception). **[3-0]**
- **Academic frictions cannot explain the anomaly for liquid ATM/near-OTM buy-and-hold positions** (possible exception: extremely deep OTM). **[3-0]**
- **Monthly SPX put-writing (PUT index) 1986–2018**: matched S&P return (9.54% vs 9.80%) at two-thirds the volatility, Sharpe 0.65 vs 0.49, monthly alpha 0.89% — **gross, before any transaction costs**. **[3-0]**
- **The edge shrank after 2006**: 2006–2018 Sharpe 0.50 (PUT) vs 0.51 (S&P). Weekly rolling (WPUT) did WORSE (Sharpe 0.40) despite collecting 37.1%/yr gross premium vs 22.1% — more frequent selling collected more premium and returned less. **[3-0]**
- **Drawdown profile**: PUT max drawdown −32.7%, skew −2.09, kurtosis 12.6; weekly tenor's real benefit is drawdown reduction (−24.2%), not return. **[3-0]**
- **The index numbers are gross hypothetical performance**: the study itself warns real implementations face materially higher costs, especially at weekly frequency. Retail net edge must be established separately. **[3-0]**

## Extracted, votes incomplete (credible sources, treat as leads)

- AQR: delta-hedged 5% OTM put selling 1996–2016 ≈ 1.5%/yr at 2.2% vol (Sharpe 0.68, −10% max DD) net of estimated costs; systematic option BUYING persistently negative. **[extracted]**
- VRP positive across volatility regimes, including low-VIX (Israelov & Nielsen 2015). **[extracted]**
- Tail-risk premium is a distinct priced factor; OTM put richness persists long after crises normalize. **[extracted]**
- Pre-earnings LONG straddles earned ~+3.3% into announcements (IV underprices events) — but the effect concentrates in small/illiquid names and is likely absent in ultra-liquid large caps; transaction costs on earnings-week straddles are the binding constraint. **[extracted]**
- Unconditional long straddles on single names: significantly negative at all horizons (~−0.19%/day, −17%/month). Retail option buyers lose 5–9% of premium around earnings (10–14% on high-expected-move names), largely to the spread. **[extracted]**
- **Post-announcement premium-selling window**: option traders overestimate volatility immediately AFTER earnings announcements — a positive-expectancy window for selling premium post-print (supports the repo's pre-registered post-event IV-crush playbook). **[extracted]**
- **High-EAV short-vol effect**: straddles bought before high expected-announcement-volatility prints underperformed by ~11% on announcement day (t≈19) plus ~9% over the next 10 days — the short side is strongly positive gross. **[extracted]**
- **Computable conditional signal**: (historical average earnings move − option-implied move) predicted weekly earnings-straddle returns; long/short quintile hedge ≈ 14.2%/quarter (t=2.72) before costs. Implementable from the SEC earnings calendar + OPRA history. **[extracted]**
- **Cost reality check**: earnings-week single-name straddle half-spreads ≈ 7–8% of midpoint; the authors note the edges can become unprofitable under conservative cost assumptions. All published cost figures are from the broad single-name universe — this repo's 13 penny-quoted mega-liquid names are the minimum-cost corner of the market, so net-edge measurement there is genuinely novel. **[extracted]**

## Implications for this repo

1. **Best-evidenced family for the next pre-registered falsification test: defined-risk index put-credit-spread VRP harvesting** (SPY/QQQ/IWM/DIA), monthly-tenor bias (weekly frequency is evidence-negative), conditioned on the existing point-in-time VIX bucket. The repo's pre-registered `low_mid_vix_index_put_credit_spread_vrp_v1` playbook is independently supported.
2. **The decisive open question is net-of-costs capture** — gross index results do not transfer; NBBO-exact entry/exit pricing over the never-consumed 2018–2021 window is precisely the right instrument.
3. **Directional long-premium strategies carry a documented negative base rate** — consistent with this repo's own OOS falsification of the momentum debit-spread filter. The F1 family test proceeds as a cheap closure of that question, with a low prior.
4. **Bar a credible backtest must clear** (from the failure modes in the literature): point-in-time inputs, NBBO side-aware fills, all fees, cluster-robust inference (not i.i.d.), pre-registered rules with no window reuse, and a drawdown/tail assessment — the repo's existing contract machinery already encodes these.

## What this review does NOT establish

No live edge is proven. The 2006+ attenuation is verified — the premium's harvestable remainder at retail scale is an open empirical question this repo's instruments can answer. Nothing here changes scanner policy, proof bars, or promotion state.
