# Regular Options Exact Target Import Approval Packet

This packet is a read-only decision aid for Prime CEO. It does not approve or run provider queries, quote imports, evidence-store writes, DB writes, policy edits, scanner/broker/live commands, `--apply`, `--run-all-planned`, or protected-holdout consumption.

## Current Status

- Decision posture: `blocked_non_promotable_observe_only`.
- Walk-forward posture: `historical_walkforward_ran_candidates_blocked`; `promotion_ready=false`.
- Exact target plan posture: `exact_target_plan_ready_read_only`.
- Protected holdout starts `2026-06-05`; target-plan overlap is `0`.
- Even a clean quote import would only reprice or reclassify historical blockers. It would not make any lane promotion-ready, live-validation-ready, or production-proof-ready.

## Scope Readback

Sources read:

- `docs/regular-options-exact-target-plan.md`
- `data/profitability-lab/regular-options-exact-target-plan/latest.json`
- `scripts/import_missing_replay_quotes_from_thetadata.py` source and `--help`
- `docs/NEXT_STEPS.md`
- `docs/PROJECT_CONTEXT.md`
- `docs/regular-options-historical-walk-forward.md`

The importable exact-target scope is limited to pre-holdout missing-exit quote targets from the two current source replay artifacts:

| Bucket | Source rows | Unique exact targets | Date range | Importable | Notes |
|---|---:|---:|---|---|---|
| `bullish_pullback_missing_exit_quotes` | 3 | 3 | `2026-03-23` to `2026-03-26` | Yes | WMT=2, JNJ=1 |
| `lane_a_missing_exit_quotes` | 127 | 111 | `2025-08-26` to `2026-04-30` | Yes | 16 duplicate extra source rows |
| `lane_a_no_chain_native_spread` | 10 | 0 | entries `2025-09-22` to `2026-03-04` | No | Selection-gap rows, excluded/non-importable |

Global importable scope: `130` source rows, `114` unique exact targets, `16` duplicate extra rows, `0` cross-group duplicate targets, and `0` protected-holdout overlap.

The Lane A `10` no-chain-native rows are not quote-import targets. They remain selection/contract-construction gaps and must not be folded into provider query counts.

## Approval Recommendation

Do not ask for direct import approval yet. The safe approval path is staged:

1. Stage 1: plan-only helper readback. This is no-provider and no-write, and should be the first approval request.
2. Stage 2: dry-run provider query. This contacts ThetaData but still writes no CSV, summary, or DB rows. Ask separately after Stage 1 matches exactly.
3. Stage 3: quote import. This would write artifacts and import rows into the historical option store. It is not approved by this packet and should require a separate approval after dry-run readback.

Direct import is technically bounded by the helper when run without `--plan-only` or `--dry-run`, but it is not the right first action because the target set is large enough to deserve one no-provider target readback and one no-write provider readback first.

## Commands Not Approved Until User Says Yes

Run from `C:\Users\kalec\options-chatbot`.

Stage 1, plan-only target readback. This must be marked `NOT APPROVED UNTIL USER SAYS YES`:

```powershell
uv run --locked python scripts/import_missing_replay_quotes_from_thetadata.py data/options-validation/runs/20260528_224313_sleeve_pf59_coverage_a_refill_v1_intraday.json data/options-validation/runs/20260530_191945_lane_a_chain_native_ret20_4_stop200_time75_rerun4_v1_intraday.json --plan-only --json --lookahead-calendar-days 0 --theta-url http://127.0.0.1:25503 --source thetadata_opra_nbbo_1m --snapshot-kind intraday --interval 1m --start-time 15:55:00 --end-time 15:55:00
```

Stage 2, no-write provider dry-run. This must be a separate approval after Stage 1 is clean, and must be marked `NOT APPROVED UNTIL USER SAYS YES`:

```powershell
uv run --locked python scripts/import_missing_replay_quotes_from_thetadata.py data/options-validation/runs/20260528_224313_sleeve_pf59_coverage_a_refill_v1_intraday.json data/options-validation/runs/20260530_191945_lane_a_chain_native_ret20_4_stop200_time75_rerun4_v1_intraday.json --dry-run --json --lookahead-calendar-days 0 --theta-url http://127.0.0.1:25503 --source thetadata_opra_nbbo_1m --snapshot-kind intraday --interval 1m --start-time 15:55:00 --end-time 15:55:00
```

No write/import command is included here. If Stage 2 is clean and import is still desired, Prime CEO should request a separate, explicit import approval packet using the exact dry-run readback.

## Stop Conditions

Stop before provider query or import if any of these appear:

- Any importable target `quote_date >= 2026-06-05`.
- Any no-chain-native selection-gap `candidate_entry_date >= 2026-06-05`.
- Any count mismatch from the expected `130` source rows, `114` unique importable targets, bullish-pullback `3` unique targets, Lane A `111` unique targets, or Lane A `10` excluded selection-gap rows.
- Stage 1 output is not `plan_only=true`, `write_artifacts=false`, `request_count=0`, `base_unique_items=114`, `unique_items=114`, `expanded_unique_items=114`, and `lookahead_calendar_days=0`.
- Stage 2 output is not `dry_run=true`, `write_artifacts=false`, `base_unique_items=114`, `unique_items=114`, `expanded_unique_items=114`, and `lookahead_calendar_days=0`.
- Any `lookahead_calendar_days > 0`, any `lookahead_row_count > 0`, or any `lookahead_only_rows_found`.
- Any non-empty `errors`, `theta_feed_down`, `request_failed`, timeout, or connection error.
- Any provider `exact_date_no_match` / `current_source_exhausted` classification if the proposed next step is import; classify no-match rows as blockers instead of importing around them.
- Any command uses the wrong run paths, adds extra run paths, omits the required source replay artifacts, or includes `--run-all-planned`, `--apply`, broker, scanner, live, promotion, lane-state, source-quality policy, stop, sizing, or contract-selection changes.
- Any output shows unexpected write paths during plan-only or dry-run, including non-null `csv_path`, non-null `summary_path`, or non-null `import_result`.
- Any gateboard, operator, or reviewer asks to treat this as live release, production proof, lane promotion, proof-bar relaxation, or protected-holdout consumption.

## Later Verification If Approved

After an approved Stage 1 plan-only run, verify stdout before asking for Stage 2:

- `plan_only=true`, `dry_run=false`, `write_artifacts=false`.
- `base_unique_items=114`, `unique_items=114`, `expanded_unique_items=114`.
- `request_count=0`, `normalized_rows=0`, `csv_path=null`, `summary_path=null`, `import_result=null`.
- `repair_attempt_summary.attempt_count=114` and all attempts are `planned_not_requested`.

After an approved Stage 2 dry-run, verify stdout before asking for import:

- `dry_run=true`, `plan_only=false`, `write_artifacts=false`.
- `request_count=114`, `lookahead_calendar_days=0`, `repair_attempt_summary.lookahead_row_count=0`.
- `errors=[]`, `csv_path=null`, `summary_path=null`, `import_result=null`.
- No `lookahead_only_rows_found`, `request_failed`, `theta_feed_down`, or provider no-match rows are treated as import-ready proof.

If a later, separate import is approved and executed, expected post-import checks are:

```powershell
uv run --locked python scripts/build_regular_options_exact_target_plan.py --no-write --json
uv run --locked python scripts/audit_paid_data_readiness.py --force --json --snapshot-kind intraday --source-labels thetadata_opra_nbbo_1m --required-underlyings SPY,QQQ,IWM,AAPL,GOOGL,UNH,LLY,JNJ,XOM,CVX,COP,NEM,DIA --min-quote-dates 504 --min-shared-quote-dates 504 --min-executable-quote-pct 90
npm run options:features:regular-options
npm run options:robust-search:regular-options
npm run options:replay:regular-options-walk-forward
npm run verify:docs
git diff --check
```

The import summary must be reviewed for `errors=[]`, `lookahead_row_count=0`, no protected-holdout targets, and no rejects. Duplicate rows are not promotion evidence. Successful import should be followed by replay/readback classification, not by live release.

## Decision Boundary

This approval decision is only about whether to validate and maybe query the `114` pre-holdout exact missing quote targets. It is not approval for:

- quote import or DB mutation;
- scanner, broker, paper, live-trading, promotion, or lane-state changes;
- proof-bar, source-quality policy, stop, sizing, or contract-selection changes;
- protected-holdout consumption;
- treating historical rows as fresh forward proof.

Approval question: Do you approve running only the Stage 1 plan-only, no-provider, no-write target readback for the `114` pre-holdout exact targets, with any ThetaData dry-run or quote import requiring a separate yes?
