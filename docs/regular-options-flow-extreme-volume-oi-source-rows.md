# Regular Options Flow-Extreme Volume/OI Source Rows

This generated artifact builds read-only point-in-time volume/open-interest source rows for the flow-extreme ratio/backspread branch. It does not import quotes, mutate the options history database, run replay, create trades, count profitability, enable live validation, enable auto-track, submit broker orders, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, or promote any lane.

## Summary

- Status: `blocked_flow_extreme_volume_oi_source_rows`.
- Source rows: `0`.
- Covered months: `0` / `24`.
- Date coverage: `0.0`.
- Write source rows allowed: `false`.

## Blockers

- `missing_trusted_volume_open_interest_source_rows`
- `trusted_rows_have_null_volume_open_interest`
- `insufficient_month_coverage`
- `insufficient_date_coverage`

## Threshold Policy

```json
{
  "flow_input_basis": "volume_open_interest",
  "future_outcomes_used": false,
  "known_at_rule": "prior trusted source date strictly before input_date_et",
  "outcome_tuned": false,
  "plain_bid_ask_used_as_flow": false,
  "quote_depth_fabricated": false,
  "realized_pnl_used": false,
  "selected_winners_used": false,
  "threshold_policy_id": "volume_open_interest_prior_day_trailing_distribution_v1"
}
```
