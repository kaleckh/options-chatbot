# Regular Options Repair Attempts

This report is generated from `scripts/build_regular_options_repair_attempt_readback.py`. It is a repair-memory/readback layer for regular options proof work, not a scanner or broker-action surface.

## Summary

- Latest attempts: `0`.
- Input summaries scanned: `156`.
- Latest outcomes: `{}`.
- Latest proof repair statuses: `{}`.
- Current-source exhausted exact dates: `0`.
- Exact-date rows found: `0`.
- Lookahead-only rows found: `0`.

## Outcome Matrix

| Outcome | Meaning | Proof posture |
|---|---|---|
| `imported_pending_replay` | Exact missing-date rows were imported. | Rerun the source replay before graduation. |
| `exact_date_rows_found` | Exact missing-date rows were found in dry-run. | Candidate only until imported and replayed. |
| `lookahead_only_rows_found` | Later dates had rows, missing date did not. | Diagnostic only; not proof repair. |
| `exact_date_no_match` | Current source returned no exact rows. | Exhausted for this source/date until new evidence exists. |
| `planned_not_requested` | Plan-only target; no provider request. | No proof change. |

## Latest Attempts

| Outcome | Proof status | Ticker | Contract | Missing date | Exact rows | Lookahead rows | First later date | Source |
|---|---|---|---|---|---:|---:|---|---|

## Inputs

| Status | Generated | Attempts | Path |
|---|---|---:|---|
| ok | 2026-05-29T04:27:12.582006Z | 0 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260529T042707Z.json |
| ok | 2026-05-29T05:08:11.560245Z | 0 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260529T050747Z.json |
| ok | 2026-05-29T05:15:37.716334Z | 0 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260529T051508Z.json |
| ok | 2026-05-30T00:00:32.297057Z | 0 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260530T000025Z.json |
| ok | 2026-05-30T22:41:46.775156Z | 0 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260530T224027Z.json |
| ok | 2026-05-30T22:43:53.011062Z | 0 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260530T224330Z.json |
| ok | 2026-05-30T22:47:07.748956Z | 0 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260530T224659Z.json |
| ok | 2026-05-31T01:06:57.063980Z | 0 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260531T010645Z.json |
| ok | 2026-05-31T01:12:19.564388Z | 0 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260531T011208Z.json |
| ok | 2026-05-31T01:14:06.008590Z | 0 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260531T011246Z.json |
| ok | 2026-05-31T01:17:55.968897Z | 0 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260531T011611Z.json |
| ok | 2026-06-02T13:54:22.031343Z | 0 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260602T135406Z.json |
| ok | 2026-06-02T17:05:32.477606Z | 0 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260602T170524Z.json |
| ok | 2026-06-04T18:27:33.794877Z | 0 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260604T182733Z.json |
| ok | 2026-06-04T18:27:48.393392Z | 0 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260604T182747Z.json |
| ok | 2026-06-04T18:31:47.917836Z | 0 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260604T183147Z.json |
| ok | 2026-06-04T18:32:32.595256Z | 0 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260604T183231Z.json |
| ok | 2026-06-04T18:33:40.635021Z | 0 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260604T183339Z.json |
| ok | 2026-06-04T18:46:25.356933Z | 0 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260604T184624Z.json |
| ok | 2026-06-04T18:47:26.228489Z | 0 | data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260604T184725Z.json |

Older input summaries omitted from this Markdown table: `136`.
