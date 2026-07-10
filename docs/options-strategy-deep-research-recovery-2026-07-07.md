# Options Strategy Deep Research Recovery - 2026-07-07

This report preserves the recovered Claude deep-research run as research-only context. It does not authorize scanner changes, quote import, evidence mutation, proof-bar changes, live validation, auto-track, broker action, protected-holdout use, or promotion.

## Provenance

- Claude session title: `Audit options bot progress and local changes`
- Session ID: `1d85d233-7324-4b97-b706-f8c75116ce3e`
- Workflow run: `wf_d686b8fe-26c`
- Workflow task: `wjwzqslef`
- Workflow status: `completed`
- Failure mode: verifier and synthesis agents hit the Claude session limit; no completed final synthesis payload was recovered.

Source files:
- `workflow`: `C:\Users\kalec\.claude\projects\C--Users-kalec\1d85d233-7324-4b97-b706-f8c75116ce3e\workflows\wf_d686b8fe-26c.json` (`sha256=934fc473a1aa3a341c195be929bf7bc03aab75362aa1fe64717592f2630385ae`)
- `journal`: `C:\Users\kalec\.claude\projects\C--Users-kalec\1d85d233-7324-4b97-b706-f8c75116ce3e\subagents\workflows\wf_d686b8fe-26c\journal.jsonl` (`sha256=e32e8f5ac643f01d1c944d18b85d2f13c627e40e019e621a455c845657a67d0b`)
- `transcript`: `C:\Users\kalec\.claude\projects\C--Users-kalec\1d85d233-7324-4b97-b706-f8c75116ce3e.jsonl` (`sha256=bc3dc242e30ff08c089f4d268d2e157e57af36e354a2f6567468edb5aeb26b39`)
- `task_output`: `C:\Users\kalec\AppData\Local\Temp\claude\C--Users-kalec\1d85d233-7324-4b97-b706-f8c75116ce3e\tasks\wjwzqslef.output` (`sha256=655fefb98af7b48bc8e63152b0923b4013d4fbad9b24beb59bc0c53a89e4b204`)

## Run Stats

- Agent count: `104`
- Duration ms: `600185`
- Total tokens: `1721617`
- Total tool calls: `475`
- Search angles: `5`
- Workflow sources: `22`
- Workflow claims: `98`
- Claims sent to workflow verification: `25`
- Workflow confirmed claims: `9`
- Workflow killed/refuted panels: `0`
- Workflow unverified claims: `16`
- Journal events: `294`
- Journal result records: `91`
- Journal started-without-result records: `112`
- Extracted claims in journal: `199`
- Verifier verdict records in journal: `40` (`37` not refuted, `3` refuted)

## Confirmed Claims From Workflow

1. `3-0` - Over 08/1987–12/2000, one-month S&P 500 futures put options earned average excess returns of -39% per month for at-the-money puts and -95% per month for deep out-of-the-money puts, meaning systematic put selling captured an extraordinarily large premium.
   Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=375784
2. `3-0` - The put premium was persistent, not an artifact of one lucky regime: average returns were significantly negative in all four subperiods tested (1987–2000), and even in the worst subperiod — the one containing the October 1987 crash — put average returns ranged from -27% to -12% per month.
   Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=375784
3. `3-0` - Transaction costs and bid-ask spreads cannot explain the put-selling edge for liquid ATM/near-OTM options, because the buy-and-hold strategies involve minimal trading and the mispricing dwarfs realistic frictions — with the possible exception of extremely deep OTM puts.
   Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=375784
4. `3-0` - The S&P 500 volatility risk premium averaged 4.2 percentage points from 1990-2018 (mean VIX 19.3% vs mean realized volatility 15.1%), and was positive in 27 of 29 calendar years (negative only in 2008 and, per the annual table, marginally in no other year; 2008 shows -2.5), supporting persistent richness of index options.
   Source: https://cdn.cboe.com/resources/education/research_publications/PutWriteCBOE19_v14_by_Prof_Oleg_Bondarenko_as_of_June_14.pdf
5. `3-0` - Over June 1986 to December 2018, systematic monthly ATM S&P 500 put writing (PUT index) earned roughly the S&P 500's return with two-thirds of its volatility: 9.54% vs 9.80% annual compound return, 9.95% vs 14.93% standard deviation, Sharpe 0.65 vs 0.49, and monthly alpha of 0.89% in a down/up-beta regression — before any transaction costs.
   Source: https://cdn.cboe.com/resources/education/research_publications/PutWriteCBOE19_v14_by_Prof_Oleg_Bondarenko_as_of_June_14.pdf
6. `3-0` - In the more recent 2006-2018 period the edge shrank and higher-frequency (weekly) premium selling did WORSE, not better: annual compound returns were 5.97% (PUT), 4.51% (WPUT), 7.59% (S&P 500) with Sharpe ratios 0.50/0.40/0.51 — i.e., weekly put writing underperformed both monthly put writing and the index on a risk-adjusted basis despite collecting 37.1% vs 22.1% average annual gross premium, which cuts against the assumption that shorter-DTE selling harvests more premium net of outcomes.
   Source: https://cdn.cboe.com/resources/education/research_publications/PutWriteCBOE19_v14_by_Prof_Oleg_Bondarenko_as_of_June_14.pdf
7. `3-0` - The drawdown/crash profile of short-put harvesting is severe but smaller than equity: PUT max drawdown was -32.7% (Jan-09) vs -50.9% for the S&P 500, with strongly negative monthly skewness (-2.09) and kurtosis 12.58; weekly rolling (WPUT) reduced max drawdown to -24.2% and shortened the longest drawdown to 22 months — the main documented benefit of shorter tenors is tail/drawdown reduction, not higher return.
   Source: https://cdn.cboe.com/resources/education/research_publications/PutWriteCBOE19_v14_by_Prof_Oleg_Bondarenko_as_of_June_14.pdf
8. `3-0` - All reported performance is gross hypothetical index performance: the study explicitly states the indexes exclude transaction costs and taxes and that real implementations could face significantly higher costs — and it warns that more frequent (weekly) rolling raises transaction costs — so retail net edge after ~$0.65/leg commissions and spread crossing must be established separately, not inferred from these numbers.
   Source: https://cdn.cboe.com/resources/education/research_publications/PutWriteCBOE19_v14_by_Prof_Oleg_Bondarenko_as_of_June_14.pdf
9. `3-0` - A delta-hedged strategy selling one-month 5% OTM S&P 500 puts monthly (held to expiry), 1996-2016, earned 1.5% annualized excess return at 2.2% volatility (Sharpe 0.68), net of AQR's estimated transaction costs — more than double the S&P 500's 0.32 Sharpe over the same period, with near-zero equity beta (0.04).
   Source: https://www.aqr.com/-/media/AQR/Documents/Whitepapers/Understanding-the-Volatility-Risk-Premium.pdf

## Unverified Claims Requiring Follow-Up

These claims were not refuted by the final workflow result; they are unverified because verifier agents errored under session limits.

1. valid votes `1`, errored votes `2` - The mirror-image cost of the premium: continuously buying one-month 5% OTM protective puts on the S&P 500 (1996-2016) cut annualized returns from 5.1% to 1.8% and Sharpe from 0.32 to 0.14, while only reducing max drawdown from -62% to -57% — quantifying the ongoing bleed paid by option buyers that the seller harvests.
   Source: https://www.aqr.com/-/media/AQR/Documents/Whitepapers/Understanding-the-Volatility-Risk-Premium.pdf
2. valid votes `0`, errored votes `3` - The volatility risk premium persists across volatility regimes: even when volatility (and option prices) are low, implied volatility has still tended to exceed subsequent realized volatility, so systematic option selling has remained profitable on average — i.e., the edge is not confined to high-IV environments.
   Source: https://www.aqr.com/-/media/AQR/Documents/Whitepapers/Understanding-the-Volatility-Risk-Premium.pdf
3. valid votes `0`, errored votes `3` - Priced left-tail (crash) risk in S&P 500 index options is driven by a separate factor that cannot be spanned by market volatility or its components — i.e., the expensiveness of OTM puts/skew is a distinct premium, not just a volatility effect.
   Source: https://www.kellogg.northwestern.edu/faculty/todorov/htm/papers/opa.pdf
4. valid votes `0`, errored votes `3` - The compensation for market risk (risk premia) is far more persistent after crises than the risks themselves: the negative-jump-intensity tail factor mean-reverts much slower than volatility following crises, so OTM index puts remain expensive long after realized risk normalizes.
   Source: https://www.kellogg.northwestern.edu/faculty/todorov/htm/papers/opa.pdf
5. valid votes `0`, errored votes `3` - The factor driving short-maturity OTM put option prices has no impact on the actual (P-measure) volatility and jump dynamics of the underlying, but critically affects the pricing of risk — so a substantial part of short-dated OTM put value is pure risk premium rather than compensation for measurable statistical risk, directly supporting a persistent seller's edge in short-dated index puts/skew.
   Source: https://www.kellogg.northwestern.edu/faculty/todorov/htm/papers/opa.pdf
6. valid votes `0`, errored votes `3` - Buying at-the-money straddles on individual stocks from 3 days before an earnings announcement through the announcement date earned a highly significant average return of 3.34% (1996-2010 sample), meaning pre-earnings long-volatility positions were profitable and, conversely, selling premium into earnings during that window was negative-expectancy on average.
   Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2204549
7. valid votes `0`, errored votes `3` - Unconditionally (outside the earnings window), long straddles on individual stocks lose money at all horizons — roughly -0.19% daily, -2.09% weekly, and -17.1% monthly — which is direct evidence of a persistent volatility risk premium earned by option sellers on single names.
   Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2204549
8. valid votes `0`, errored votes `3` - The pre-earnings straddle edge concentrates in small, noisy, illiquid names: returns are more pronounced for smaller firms and firms with higher volatility, higher kurtosis, more volatile past earnings surprises, and lower trading volume / higher transaction costs — implying limited edge in an ultra-liquid mega-cap/ETF universe like the trader's 13 symbols.
   Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2204549
9. valid votes `0`, errored votes `3` - Retail option buyers lose 5-9% of their option investment on average around earnings announcements, and 10-14% for high expected-announcement-volatility (EAV) announcements, after accounting for bid-ask spreads and conservative price-improvement assumptions — the losses come from three mechanisms: overpaying for IV relative to realized volatility, enormous spreads, and holding positions weeks after the announcement.
   Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4050165
10. valid votes `0`, errored votes `3` - ATM straddles bought before high-EAV earnings announcements underperform those before low-EAV announcements by ~11% on the announcement day (t=19.44) plus an additional ~9% (t=8.31) over the following 10 days, with little skewness or kurtosis — i.e., the short side of pre-earnings ATM volatility is systematically overpriced (gross of costs) and the mispricing continues to decay for two weeks post-announcement rather than reversing.
   Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4050165
11. valid votes `0`, errored votes `3` - Transaction costs on the single-name options retail trades around earnings are enormous: typical percentage half-spreads incurred are on the order of 8% of the option midpoint, and among high-EAV announcements retail loses an average additional 9% of investment to the half-spread alone — so any retail strategy attempting to harvest the earnings IV-crush edge in single names must clear roughly 8-9% half-spread costs per round of exposure.
   Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4050165
12. valid votes `0`, errored votes `3` - Long straddles purchased prior to earnings announcements earn positive returns, in contrast to the generally negative returns on straddles at other times — implying pre-earnings implied volatility is systematically UNDERpriced, which is evidence AGAINST naive short-vol 'sell before earnings, harvest the IV crush' retail strategies.
   Source: https://www.sciencedirect.com/science/article/abs/pii/S0927539816300743
13. valid votes `0`, errored votes `3` - The average option trader overestimates future volatility immediately after recent earnings announcements, implying a positive-expectancy window for SELLING volatility (premium selling) in the post-announcement period rather than the pre-announcement period.
   Source: https://www.sciencedirect.com/science/article/abs/pii/S0927539816300743
14. valid votes `0`, errored votes `3` - In a 2014Q1-2017Q1 sample of 2,690 earnings announcements with weekly options, the average one-day ATM straddle return around earnings is statistically zero (mean +0.48%, median -17.69%), implying no unconditional pre-cost edge to either systematically buying or systematically selling earnings straddles/IV crush in liquid large-cap names.
   Source: https://www.mdpi.com/1911-8074/16/5/270
15. valid votes `0`, errored votes `3` - A conditional signal — historical average earnings-announcement move minus the option-implied earnings move (AvgEA-Implied) — predicts weekly straddle returns: a long-top-quintile/short-bottom-quintile hedge portfolio earned a mean quarterly return of 14.20% (t=2.72, significant at 5%) before any transaction costs, with the short leg (selling straddles when implied move exceeds historical move) being the individually significant leg at -5.42% per quarter.
   Source: https://www.mdpi.com/1911-8074/16/5/270
16. valid votes `0`, errored votes `3` - Transaction costs are the binding constraint on exploiting this earnings-straddle mispricing at retail: the mean quoted half-spread on the earnings-week ATM straddles is 7.4% of the midpoint, returns were computed at bid-ask midpoints, and the author states the strategy can become unprofitable at conventional effective half-spreads unless the trader times executions to reduce costs (per Muravyev and Pearson 2020).
   Source: https://www.mdpi.com/1911-8074/16/5/270

## Journal Refutations To Preserve

The workflow-level `killed` count was zero, but the raw journal contains individual refutation verdicts. All three refute over-strong interpretations that retail cost, margin, and current implementability are solved by historical put-overpricing evidence.

1. confidence `medium`, family `directional_buying_retail_losses`
   Evidence: The quote is genuine and the claim paraphrases Bondarenko (SSRN 375784; published QJF 2014) accurately, but the claim fails on contradiction and currency. (1) Bondarenko's friction statement is an unquantified aside in a paper about S&P 500 FUTURES options (CME futures-style margin, sample 08/1987-12/2000) — it does not measure retail NBBO spreads, Reg-T margin, or commissions, yet the claim generalizes it to 'liquid options' for retail. (2) Santa-Clara & Saretto (Journal of Financial Markets 2009), a peer-reviewed study built specifically to quantify frictions, finds trading frictions have an 'economically important impact on the execution and the profitability of option strategies that inv...
   Counter-source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=681643 (Santa-Clara & Saretto, "Option Strategies: Good Deals and Margin Calls", Journal of Financial Markets 2009)
2. confidence `high`, family `directional_buying_retail_losses`
   Evidence: The quote is genuine (verified in Bondarenko's PDF, Section 2.4), but it is a one-paragraph qualitative aside, not a result: Bondarenko's dataset uses CME settlement prices, never observes bid-ask spreads, and never models margin costs — the friction dismissal is asserted, not measured. The claim's operative statement ('margin costs are too small... to explain it away') is directly contradicted quantitatively by Santa-Clara & Saretto, 'Option Strategies: Good Deals and Margin Calls' (Journal of Financial Markets 2009; S&P 500 options, Jan 1985–Dec 2002 — same market, overlapping sample): verified quotes from their paper: 'We find that the Sharpe ratios decrease substantially, and sometimes e...
   Counter-source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=681643 (Santa-Clara & Saretto, 'Option Strategies: Good Deals and Margin Calls', Journal of Financial Markets 2009; full text verified at https://www.anderson.ucla.edu/documents/areas/fac/finance/santa_clara_option.pdf)
3. confidence `medium`, family `directional_buying_retail_losses`
   Evidence: The quoted statistics are verbatim accurate (verified by extracting the paper PDF: Bondarenko, 'Why Are Put Options So Expensive?', SSRN 375784, published QJF 2014): -39%/month ATM, -95%/month deep OTM put excess returns, 08/1987-12/2000, described as statistically significant and not explained by transaction costs. However, the claim's payload clause — 'establishing a large volatility/put risk premium harvestable by sellers' — is refuted on three grounds. (1) Mislabels the source: the paper's central conclusion is that NO model in a broad class of risk-based/rational models can explain the returns; it frames them as a mispricing puzzle, not an established risk premium, and calls seller gain...
   Counter-source: Broadie, Chernov & Johannes (2009), 'Understanding Index Option Returns,' Review of Financial Studies 22(11): 4493-4529, https://academic.oup.com/rfs/article-abstract/22/11/4493/1568222

## Source Leads

- `primary` (5 claims): https://papers.ssrn.com/sol3/papers.cfm?abstract_id=375784
- `primary` (5 claims): https://cdn.cboe.com/resources/education/research_publications/PutWriteCBOE19_v14_by_Prof_Oleg_Bondarenko_as_of_June_14.pdf
- `primary` (5 claims): https://www.aqr.com/-/media/AQR/Documents/Whitepapers/Understanding-the-Volatility-Risk-Premium.pdf
- `primary` (5 claims): https://www.kellogg.northwestern.edu/faculty/todorov/htm/papers/opa.pdf
- `blog` (5 claims): https://thehedgefundjournal.com/harvesting-the-s-p500-volatility-risk-premium/
- `secondary` (4 claims): https://quantpedia.com/strategies/volatility-risk-premium-effect
- `primary` (5 claims): https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2204549
- `primary` (5 claims): https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4050165
- `primary` (5 claims): https://www.sciencedirect.com/science/article/abs/pii/S0927539816300743
- `primary` (5 claims): https://www.mdpi.com/1911-8074/16/5/270
- `primary` (4 claims): https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4832160
- `secondary` (5 claims): https://alphaarchitect.com/straddle-earnings-announcements-and-win/
- `unreliable` (0 claims): https://spintwig.com/short-spx-put-0-dte-s1-signal-options-backtest/
- `unreliable` (0 claims): https://spintwig.com/short-spx-vertical-put-45-dte-s1-signal-options-backtest/
- `secondary` (5 claims): https://www.cboe.com/insights/posts/henry-schwartzs-zero-day-spx-iron-condor-strategy-a-deep-dive/
- `primary` (5 claims): https://onlinelibrary.wiley.com/doi/full/10.1111/jofi.13285
- `primary` (5 claims): https://www.timdesilva.me/files/papers/losing_optional.pdf
- `primary` (5 claims): https://www.lsu.edu/business/files/event-files/2025-finance-mardi-gras/retail_option_trading_v2.pdf
- `primary` (5 claims): https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
- `secondary` (5 claims): https://orats.com/university/backtesting-methodology
- `secondary` (5 claims): https://quantpedia.com/strategies/exploiting-term-structure-of-vix-futures
- `primary` (5 claims): https://www.researchgate.net/publication/315240072_Risk_Premia_and_the_VIX_Term_Structure

## Focused Reviewer Synthesis

Five focused read-only reviewer agents checked the recovered run by strategy family. Their integrated verdict is below.

### defined_risk_index_vrp_credit_spreads

- Verdict: `top_research_candidate_unproven_for_bot`
- Summary: Historical S&P 500 VRP and put-writing evidence is real and better supported than the other families, but it does not prove a retail put-credit-spread bot earns positive expectancy after NBBO fills, spread crossing, commissions, margin, and tail events.
- Recommended action: Run the first preregistered falsification test on SPY index-VRP put credit spreads, with QQQ/IWM/DIA as secondary holdouts and optional predeclared IV/skew filters.
- Source anchors:
  - https://papers.ssrn.com/sol3/papers.cfm?abstract_id=375784
  - https://cdn.cboe.com/resources/education/research_publications/PutWriteCBOE19_v14_by_Prof_Oleg_Bondarenko_as_of_June_14.pdf
  - https://www.aqr.com/-/media/AQR/Documents/Whitepapers/Understanding-the-Volatility-Risk-Premium.pdf
  - https://cdn.cboe.com/api/global/us_indices/governance/Cboe_SP_500_PutWrite_Indices_Methodology.pdf

### earnings_event_volatility

- Verdict: `conditional_research_candidate_only`
- Summary: The recovered workflow did not verify earnings/event claims, but primary sources support two cautions: naive retail event-vol buying loses badly around earnings, and naive pre-earnings short-vol 'IV crush' is not cleanly supported. Conditional post-event or implied-vs-historical move tests are plausible but cost-sensitive.
- Recommended action: Test only as a narrow conditional branch with a fixed event calendar, fixed entry/exit windows, liquidity filters, matched non-event controls, and no midpoint fills.
- Source anchors:
  - https://academic.oup.com/rof/article-abstract/30/2/489/8301159
  - https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2204549
  - https://www.mdpi.com/1911-8074/16/5/270
  - https://www.sciencedirect.com/science/article/abs/pii/S0927539816300743
  - https://academic.oup.com/rof/article/29/4/963/8079062

### short_dte_0dte_premium_selling

- Verdict: `defer_as_primary_strategy`
- Summary: Cboe evidence supports 0DTE liquidity and market-structure relevance, not a durable retail expectancy edge. The recovered workflow did not verify 0DTE profitability claims, and practitioner evidence remains vulnerable to selection, tail loss, and execution assumptions.
- Recommended action: Defer behind VRP. If tested, make it paper/research-only with explicit gamma, max-loss, event-day, no-price-improvement, and late-day slippage stress.
- Source anchors:
  - https://www.cboe.com/insights/posts/the-state-of-the-options-industry-2025/
  - https://www.cboe.com/insights/posts/henry-schwartzs-zero-day-spx-iron-condor-strategy-a-deep-dive/
  - https://cdn.cboe.com/resources/education/research_publications/PutWriteCBOE19_v14_by_Prof_Oleg_Bondarenko_as_of_June_14.pdf

### directional_option_buying_momentum_debit_spreads

- Verdict: `reject_for_live_capital`
- Summary: No credible live positive-expectancy case remains for the bot's directional momentum debit-spread branch after realistic costs. Retail long short-dated option buying loses after spreads, fees, and decay; academic option-momentum evidence is not the same as this branch.
- Recommended action: Disable for live capital and keep only shadow telemetry unless a new preregistered test beats stock/ETF momentum after NBBO fills, commissions, slippage, and untouched OOS data.
- Source anchors:
  - https://academic.oup.com/rof/article-abstract/30/2/489/8301159
  - https://onlinelibrary.wiley.com/doi/10.1111/jofi.13285
  - https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4065019

### methodology_backtest_contract

- Verdict: `strict_falsification_required`
- Summary: The recovered Claude run is useful as methodology evidence, not a final strategy conclusion. Any candidate must be preregistered, replayed from point-in-time OPRA/NBBO, filled side-aware, fee-adjusted, stress-tested, and controlled for multiple testing.
- Recommended action: Use a fail-closed contract with fixed parameters, quote-evidence rows for every trade, realistic multi-leg execution, PBO/CSCV or equivalent multiple-testing controls, and explicit kill criteria.
- Source anchors:
  - https://orats.com/university/backtesting-methodology
  - https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
  - https://www.finra.org/rules-guidance/rulebooks/finra-rules/5310
  - https://www.theocc.com/company-information/documents-and-archives/options-disclosure-document


## Recovered Research Interpretation

1. The strongest supported family is defined-risk index volatility-risk-premium harvesting, especially SPY/QQQ/IWM/DIA put-credit-spread style tests conditioned on volatility and skew. The evidence supports a persistent index option insurance premium, but not automatic retail profitability.
2. Retail execution costs, bid/ask crossing, margin/collateral, and tail clustering are gating uncertainties. The recovered verifier refutations specifically warn against treating historical put buyer losses or index benchmark returns as direct proof of current retail spread profitability.
3. Earnings/event volatility has source support but remains less settled for the bot's ultra-liquid 13-symbol universe. The recovered claims point to high retail losses around expected announcement volatility and to high spread costs; the bot should only test this with a strict event calendar, liquidity filters, and cost stress.
4. 0DTE/short-DTE evidence is mostly flow/practitioner evidence, not enough to outrank the VRP family. Treat it as a deferred branch unless a separate SPX/SPY 0DTE dataset and tail-loss controls are available.
5. Directional option buying and momentum debit spreads should remain low-priority after the bot's falsified out-of-sample result unless a new independent signal is pre-registered and tested under full costs.

## Plan To Finish The Research Work

1. Use this recovery artifact as the frozen evidence bundle, not the chat transcript.
2. Verify the decision-critical unverified claims by family: VRP/skew, earnings/event vol, 0DTE/short-DTE, directional buying/retail losses, and methodology/costs.
3. Draft a final cited synthesis that ranks strategy families and separates supported findings from unverified or refuted overreach.
4. Convert the top recommendation into a preregistered options-bot falsification contract for defined-risk index VRP spreads: fixed universe, quote source, entry/exit formulas, cost model, stress model, train/test split, and kill criteria.
5. Do not implement scanner changes, quote import, live validation, broker actions, or promotion from this literature review alone.

## Recommended Falsification Contract

- Candidate family: `defined_risk_index_vrp_credit_spread_v1`.
- Universe: SPY, QQQ, IWM, DIA first; single-name equities only after index results are known.
- Structures: put credit spreads or iron condors with explicit max loss; no naked options.
- Data: point-in-time OPRA/NBBO one-minute bid/ask quotes; no midpoint-only fills.
- Fill model: side-aware executable bid/ask plus stress cases. At minimum test optimistic natural/improved fills, realistic bid/ask-width travel, and adverse fill stress.
- Costs: include commission per contract-leg and all spread crossing; report net USD and percent P&L.
- Risk gates: max drawdown, left-tail clustering, gap-through-short-strike behavior, assignment/expiration handling, and collateral utilization.
- Validation: pre-register all parameters before scoring; use strict out-of-sample/fresh windows; account for every tried configuration to control backtest overfitting.
- Kill criteria: fail if net PF lower bound is not above 1.0 after costs, if stress PF is not above 1.0, if tail drawdown exceeds preset risk budget, if exact quote coverage is incomplete, or if performance depends on post-hoc symbol/date filtering.

## Immediate Next Build Step

Create or refresh a preregistered design-only contract for `defined_risk_index_vrp_credit_spread_v1` that consumes this recovery artifact as literature context. That contract should be read-only and should name the exact data, fill, cost, validation, and kill criteria before any replay or scanner implementation work.
