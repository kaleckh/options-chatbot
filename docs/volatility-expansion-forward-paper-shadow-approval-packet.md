# Volatility Expansion Forward Paper-Shadow Approval Packet

This packet is for deciding whether to start the append-only forward cohort for `volatility_expansion_observation`. It is not evidence by itself, and it does not approve live trading.

## Current State

- Lane: `volatility_expansion_observation`.
- Freeze date: `2026-06-14`.
- Current goal-loop state: `underpowered_forward_evidence`.
- Strict exact completed rows: `0` / `30`.
- Promotion-ready: `false`.
- Live entry, auto-track, broker order, and broker preparation: `false`.
- Cohort log path: `data/forward-tracking/volatility_expansion_forward_paper_shadow_cohort.jsonl`.
- Cohort log status: `cohort_log_missing_blocker` unless a later readback proves otherwise.
- Required contracts: `data/contracts/forward-cohort-preregistration.json` and `data/contracts/volatility-expansion-forward-paper-shadow-cohort-schema.json` must load before validation or append is allowed.

## Approval Question

Do you approve creating and appending to `data/forward-tracking/volatility_expansion_forward_paper_shadow_cohort.jsonl` during the next valid market-data window, limited to append-only paper-shadow evidence rows for natural `volatility_expansion_observation` scanner selections under the frozen policy and schema?

## What Approval Allows

- Create the cohort JSONL file if it does not exist.
- Stage candidate JSONL rows outside the cohort ledger and validate them before append.
- Append one JSON object per natural frozen-lane scanner selection.
- Append failed, missed, stale, zero-bid, display-only, fill-attempt-incomplete, open-waiting-exit, exact-entry, exact-exit, and missing-exit rows so the denominator is complete.
- Capture exact executable entry evidence from the current market window when a natural selection occurs.
- Capture exact executable exit evidence only after a policy-defined exit condition occurs.
- Run read-only report and verification commands after appends.

## What Approval Still Forbids

- Live trading, live validation, auto-track, broker order preparation, or broker orders.
- Scanner policy, strategy, stop, sizing, or proof-bar changes.
- Quote imports, historical evidence repair, protected-holdout consumption, or mutation of existing evidence databases.
- Counting historical, pre-freeze, stale, display-only, midpoint, EOD, manual, lookahead-only, non-executable, or synthetic marks as proof.
- Dropping failed or missing evidence rows from the denominator.
- Promoting any lane before strict acceptance gates and operator approval clear.

## Required Collection Order

1. Refresh read-only state:

```powershell
npm run options:gateboard
npm run options:triage:trade-qualification
npm run options:plan:paper-shadow-evidence
npm run options:checklist:market-window-evidence
npm run options:goal-loop:paper-shadow -- --json
```

2. Confirm the market-data window is valid and the scanner selection is natural, current, post-freeze, and still under the frozen `volatility_expansion_observation` policy.
3. Stage candidate row JSONL outside the append-only cohort ledger, then validate it:

```powershell
npm run options:validate:volatility-forward-paper-shadow-candidate -- path\to\candidate_rows.jsonl
```

4. Append a denominator row for every natural selection only if candidate validation returns `append_allowed=true`, including failures and missed evidence windows.
5. For an exact completed row, require executable entry evidence, policy-defined executable exit evidence, known denominator status, trusted entry/exit quote source and timestamps, entry/exit bid/ask provenance, policy exit condition, and `net_pnl_usd`.
6. If operator approval has been explicitly granted and the market-data window is valid, append with the guarded writer:

```powershell
npm run options:append:volatility-forward-paper-shadow -- path\to\candidate_rows.jsonl --approval-token APPROVE_VOLATILITY_FORWARD_COHORT_APPEND --market-window-confirmed
```

The approval token is a confirmation phrase, not a secret. The guarded writer also records the candidate batch hash, uses an append lock, re-reads the cohort ledger after append, and verifies row-count increment, malformed-row count, duplicate row IDs, and false live/promotion flags.

7. Rerun:

```powershell
npm run options:report:volatility-forward-paper-shadow
npm run options:goal-loop:paper-shadow -- --json
uv run --locked python -m unittest tests.test_options_goal_loop tests.test_volatility_expansion_forward_paper_shadow_report -v
uv run --locked python -m unittest tests.test_append_volatility_expansion_forward_paper_shadow_rows -v
npm run verify:docs
```

## Acceptance Metrics

- At least `30` post-freeze strict exact completed rows; `50` preferred.
- Positive total net USD P&L.
- Strict USD profit factor point estimate above `1.0`.
- 5% bootstrap strict USD PF lower bound above `1.0`; `1.20` is the healthier bar.
- Largest winner below `25%` of total net profit.
- Top three winners below `50%` of total net profit.
- Leave-one-trade-out PF lower bound above `1.0`.
- No single ticker, date, or month dependency explains the result.
- Gateboard, open-risk, promotion, and operator blockers clear without lowering proof bars.

## Stop Conditions

Stop and ask before continuing if any row would require policy interpretation outside this packet, a scanner or strategy edit, evidence-store mutation outside the cohort JSONL, quote import, historical repair, broker interaction, live validation, auto-track, proof-bar change, or protected-holdout use.
