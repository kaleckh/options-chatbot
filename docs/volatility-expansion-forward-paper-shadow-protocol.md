# Volatility Expansion Forward Paper-Shadow Protocol

This protocol moves `volatility_expansion_observation` from research-search review into frozen forward paper-shadow evidence collection. It is append-only and read-only from the reporting side.

## Files

- Schema contract: `data/contracts/volatility-expansion-forward-paper-shadow-cohort-schema.json`
- Append-only cohort ledger path: `data/forward-tracking/volatility_expansion_forward_paper_shadow_cohort.jsonl`
- Read-only report builder: `scripts/build_volatility_expansion_forward_paper_shadow_report.py`
- Proposed report artifact path, if a separately approved writer is added later: `data/forward-tracking/volatility_expansion_forward_paper_shadow_report_latest.json`
- NPM command: `npm run options:report:volatility-forward-paper-shadow`
- Candidate row validation command: `npm run options:validate:volatility-forward-paper-shadow-candidate -- path\to\candidate_rows.jsonl`
- Guarded append command, only after explicit approval and valid market-data window: `npm run options:append:volatility-forward-paper-shadow -- path\to\candidate_rows.jsonl --approval-token APPROVE_VOLATILITY_FORWARD_COHORT_APPEND --market-window-confirmed`

## Denominator Rule

Every natural scanner selection under the frozen `volatility_expansion_observation` rules must be logged. Do not log only successful evidence captures.

Rows include:

- successful exact entries
- missed entry evidence windows
- zero-bid / untradable rows
- stale quote failures
- display-only quote failures
- open positions waiting for policy-defined exit
- exact exits
- missing exits
- failed or incomplete fill-attempt evidence

Zero-bid and untradable rows are execution failures. Lookahead-only rows are diagnostic only.

## Gates

The minimum review packet requires at least 30 fresh exact completed forward paper-shadow rows. The preferred packet is 50 rows. Point PF is not enough: the stressed PF lower bound must be greater than 1.0 for minimum continuation, and at least 1.20 is the healthier bar. This still does not authorize live trading.

Strict acceptance rows must be post-freeze rows from after `2026-06-14` for `volatility_expansion_observation` only. A completed row counts only when executable entry evidence, policy-defined executable exit evidence, exact realized net P&L in USD, and a known denominator status are all present. Pre-freeze rows, duplicate row IDs or selection IDs, missing required schema fields, missing USD P&L, unknown denominator status, scanner-policy hash drift, non-executable marks, stale/display-only quotes, and lookahead-only diagnostics are rejected before any paper-validation review state.

The forward-cohort preregistration and cohort schema are required contracts. If either contract is missing or malformed, the report and guarded append fail closed with `blocked_missing_required_contract`, `append_allowed=false`, `0` strict rows, strict USD PF lower bound `null`, and all live/promotion flags false. The forward report distinguishes `cohort_log_missing_blocker`, `cohort_log_malformed_blocker`, `initialized_empty_zero_of_gate`, `rows_present_none_strict_excluded`, and `strict_rows_under_minimum`.

All review packet counts, point PF, stressed PF, bootstrap PF lower bound, leave-one-trade-out PF, and continuation gates are USD-strict. Percent-only completed rows may remain diagnostic but cannot satisfy any review or continuation gate.

Winner concentration gates:

- largest single winner must be less than 25% of total net profit
- top three winners must be less than 50% of total net profit
- leave-one-trade-out PF lower bound must remain greater than 1.0
- no single ticker, date, or month dependency may explain the result

## Approval Boundary

The cohort log at `data/forward-tracking/volatility_expansion_forward_paper_shadow_cohort.jsonl` must not be created or appended while markets are closed without separate human approval. Approval to start the cohort authorizes only append-only paper-shadow evidence rows for natural scanner selections under the frozen lane policy during a valid market-data window. It does not authorize quote imports, historical repair, scanner edits, strategy edits, stop or sizing changes, auto-track, live validation, broker order preparation, broker orders, protected-holdout consumption, or promotion.

Candidate rows should be validated before append with `--candidate-rows`; validation is read-only and reports `cohort_append_performed=false`. It allows legitimate full-denominator failure rows, but rejects pre-freeze rows, wrong-lane rows, non-preregistered symbols, duplicate row IDs, unknown denominator statuses, scanner-hash drift, lookahead sources, and exact-completed rows missing executable entry/exit quote source, timestamps, bid/ask provenance, policy exit condition, or net USD P&L.

The guarded append command refuses to write unless candidate validation passes, the exact approval token is supplied, and `--market-window-confirmed` is present. It also rejects candidate rows whose row IDs already exist in the cohort log, takes a single-writer append lock, re-reads the cohort ledger after append, verifies the row-count increment, checks malformed rows and duplicate row IDs, and preserves live/promotion flags false. Tests exercise this path against temporary logs only.

Use `docs/volatility-expansion-forward-paper-shadow-approval-packet.md` as the operator packet before asking for or acting on approval.

## Non-Goals

This protocol does not change scanner policy, stops, sizing, live validation, auto-track behavior, broker behavior, or strategy logic. It does not import quotes, repair historical rows, mutate existing evidence databases, place orders, prepare orders, or change the preserved decision state.
