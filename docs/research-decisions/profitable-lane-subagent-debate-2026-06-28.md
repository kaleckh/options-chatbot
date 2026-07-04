# Profitable Lane Subagent Debate - 2026-06-28

This report records a three-round, six-angle subagent debate on regular-options profitable-lane blockers and improvements. It was run on branch `codex/profitable-lane-debate-20260628` in an isolated worktree, while separate memory-graph work continued elsewhere.

This is a research/control artifact only. It does not authorize source-row writes, quote import, evidence-store mutation, cohort append, protected-holdout use, scanner/strategy/stop/sizing/proof-bar changes, live validation, auto-track, broker action, promotion, or treating historical rows as forward proof.

## Inputs

Repo evidence reviewed included:

- `docs/PROJECT_CONTEXT.md`
- `docs/NEXT_STEPS.md`
- `docs/regular-options-profitability-blocker-inventory.md`
- `docs/research-decisions/options_oracle_profit_loop_packet_latest.md`
- `docs/regular-options-preregistered-playbook-readiness-selector.md`
- `docs/regular-options-forward-candidate-throughput-audit.md`
- `docs/regular-options-bullish-pullback-layer-executable-economics.md`
- `docs/regular-options-strict-forward-30-completion-monitor.md`
- `package.json`

Current web/source context used:

- FRED VIX showed VIX `18.89` on 2026-06-25, updated 2026-06-26: https://fred.stlouisfed.org/series/VIXCLS
- Cboe VIX page showed VIX `18.41` as of 2026-06-26 and describes VIX as SPX option-implied near-term volatility: https://www.cboe.com/tradable-products/vix/
- Cboe VIX term-structure page: https://www.cboe.com/tradable-products/vix/term-structure/
- OPRA is the listed-options quote/last-sale authority: https://www.opraplan.com/
- ThetaData pricing/source pages indicate OPRA/NBBO option access is tier/entitlement dependent: https://www.thetadata.net/pricing
- Alpaca option data docs distinguish historical option data and subscribed OPRA BBO from indicative data: https://docs.alpaca.markets/us/docs/historical-option-data
- NYSE/Cboe/Nasdaq calendars confirm normal next-session planning and options regular hours: https://www.nyse.com/trade/hours-calendars, https://www.cboe.com/about/hours/us-options/, https://www.nasdaqtrader.com/trader.aspx?id=calendar
- Official macro-event source candidates: Fed FOMC calendar, BLS release calendar, BEA release schedule: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm, https://www.bls.gov/schedule/2026/home.htm, https://www.bea.gov/news/schedule

## Round 1 Findings

All six agents agreed that stale VIX is no longer a current blocker. Direct VIX, Alpaca SIP underlying daily/minute inputs, base market-regime inputs, and Alpaca-backed dispersion/concentration proxy inputs are cleared in current repo artifacts.

The live forward-profitability blocker remains strict forward proof at `0/30`. Current candidate throughput is blocked by natural same-day Phase 2 candidate starvation: latest throughput readback has `0` target-date Phase 2 rows, `0` staged candidates, no candidate JSONL, and aggregate scan-filter drops led by `momentum`, `history_or_liquidity`, and `tech_score`.

Bullish-pullback `layer_4_clean_exact` remains the strongest practical forward-capture lead because historical executable economics are promising, but it is not proof. It still needs natural forward denominator rows, exact entry/exit evidence, and guarded review.

Dispersion proxy hybrid is the cleanest new research lane because its preregistered readiness currently has `blockers=[]`, but it has not been replayed and has no profitability evidence.

ThetaData repair has high source-unlock value, but the current blocker is entitlement/import execution, not stale connection refusal. Macro calendar and flow/OI source packets are ready, but trusted source files/rows are still missing.

## Round 2 Split

The debate split evenly:

- Data/source, forward-throughput, and statistics prioritized `candidate-starvation observability / near-miss audit`.
- Lane design, execution/proof, and loop control prioritized `bounded no-write dispersion replay`.

Both positions were valid under different objectives. Candidate-starvation diagnostics attack the current `0/30` forward proof bottleneck. Dispersion replay is the best closed-market way to create a new falsifiable lane result without provider/source approvals.

## Round 3 Resolution

The final consensus is a sequenced plan rather than a single universal winner.

### 1. Closed-Market Work

Use closed-market time for the two local, non-live, non-import actions:

1. Build or refresh a read-only candidate-starvation near-miss audit so the next market-window scan cannot return only aggregate drop counts.
2. Implement or run the bounded no-write dispersion proxy hybrid replay if the near-miss audit surface is already concrete enough or can be done in parallel.

Candidate-starvation audit acceptance metrics:

- Per frozen lane and symbol, record attempted symbol, first failed gate, drop reason, and margin-to-pass.
- Replace `opaque_zero_candidate_diagnosis_missing_symbol_drop_reasons` with symbol-level near-miss evidence.
- Separate data/source blockers from true threshold, liquidity, timing, policy/provenance, and no-signal blockers.
- No scanner policy change, no proof-bar change, no append, no live/broker/autotrack path.

Dispersion replay acceptance metrics:

- Emit denominator rows, selected rows, priced exact rows, strict-new exact completed rows, latest-four/post-freeze-style counts, quote coverage, side-aware all-leg entry/exit pricing, fees/slippage, max-loss/collateral, assignment/expiration handling, net USD P&L, PF, PF lower bound, stress PF, and concentration checks.
- If rows are insufficient, name the single smallest blocker.
- No source-row write, quote import, protected-holdout consumption, cohort append, live/broker/autotrack path, proof-bar change, or promotion claim.

### 2. Next Valid Market Window

Run the strict-forward no-append collector/sweep during the next valid regular session and immediately inspect candidate review/throughput.

Required result:

- Either a real same-day Phase 2 candidate JSONL exists and validates, or zero candidates are explained with symbol-level near-miss evidence.
- If zero candidates repeat with only aggregate drops, the observability work failed.
- If two or three valid windows show structural starvation and no near misses, stop forcing the frozen forward cohort and pivot lane-development effort to the best research branch.

### 3. External Provider And Source Checks

Ask or verify ThetaData entitlement separately from local loop work:

- Confirm the local account has paid OPRA/NBBO options entitlement, not `Options: FREE`.
- Run a tiny dry-run/current quote probe for known contracts before selecting bulk quote-surface repair.
- If `403 Forbidden` or entitlement ambiguity persists, park ThetaData quote-surface repair as external/provider blocked.

Macro and flow/OI source work should remain source-supply work until trusted files exist:

- Macro calendar needs trusted official event rows with category, event timestamp, known-at timestamp, and source hash.
- Flow/OI needs trusted SPY/QQQ daily option volume/open-interest source rows.
- Do not rerun packet-only source planning; those packets are already ready.

### 4. Stop Conditions

Stop doing:

- Stale VIX, underlying daily/minute, base-regime, or dispersion-input relitigation.
- Generic readiness/doc refreshes that do not change candidate counts, symbol-level diagnostics, priced rows, strict-new rows, quote coverage, source rows, provider entitlement status, PF, or PF lower bound.
- Historical sleeve/count tuning before the forward denominator is observable.
- Momentum replay until point-in-time breadth/momentum inputs materially change.
- Macro/flow replay attempts before real source rows exist.
- ThetaData retry loops that ignore the current entitlement/import-execution blocker.

## Final Action List

1. Implement or refresh a read-only frozen-cohort candidate-starvation near-miss audit.
2. Implement or run the bounded no-write dispersion proxy hybrid replay.
3. At the next valid market window, run the no-append strict-forward collector/sweep and require candidate JSONL or symbol-level near-miss evidence.
4. Verify ThetaData OPRA/NBBO entitlement with a tiny probe before any quote-surface import work.
5. Ask for trusted macro calendar and SPY/QQQ flow/OI source files only if those branches become the selected lane path.
