# Regular Options Post-Event IV-Crush Replay Readiness

- Generated: `2026-06-27T18:32:22Z`.
- Status: `blocked_post_event_iv_crush_replay_readiness`.
- Concept: `post_event_iv_crush_index_iron_condor_v1`.
- Structure: `defined_risk_short_iron_condors_or_iron_butterflies_only`.
- Accepted profitability: `False`.
- Historical replay performed: `False`.
- Quotes imported: `False`.
- Protected holdout consumed: `False`.

This report is a read-only prerequisite audit. It does not implement scanner or playbook logic, run replay, import quotes, mutate evidence stores, consume protected holdout, enable live validation or auto-track, submit broker orders, change stops/sizing/proof bars, or promote any lane.

## Blockers

- `insufficient_full_window_rows`
- `insufficient_latest_four_months`
- `insufficient_latest_four_rows`
- `insufficient_train_months`
- `iv_event_premium_proxy_missing`
- `macro_event_calendar_category_coverage_missing`
- `macro_event_calendar_source_missing`
- `missing_required_macro_event_categories`

## Critical Prerequisites

| Prerequisite | Status | Blockers |
|---|---:|---|
| Valid preregistered post-event IV-crush playbook | `ready` | None |
| Point-in-time scheduled macro-event calendar | `blocked` | `macro_event_calendar_category_coverage_missing`, `macro_event_calendar_source_missing`, `missing_required_macro_event_categories` |
| Point-in-time IV/event-premium proxy | `blocked` | `iv_event_premium_proxy_missing` |
| Point-in-time VIX low/mid bucket | `ready` | None |
| Trusted four-leg index iron condor/butterfly quote surface | `blocked` | `insufficient_full_window_rows`, `insufficient_latest_four_months`, `insufficient_latest_four_rows`, `insufficient_train_months` |
| Four-leg side-aware short-premium entry/exit formula contract | `ready` | None |
| Defined-risk max-loss and margin convention | `ready` | None |
| Assignment/expiration handling contract | `ready` | None |
| Full denominator and outcome-status mapping | `ready` | None |
| Strict-new dedupe against base clean stack | `ready` | None |
| Protected holdout guard | `ready` | None |

## Source Artifacts

| Artifact | Status | Path |
|---|---:|---|
| `preregistered_playbook` | `loaded` | `data/profitability-lab/regular-options-preregistered-post-event-iv-crush-iron-condor-playbook/latest.json` |
| `macro_event_calendar` | `loaded` | `data/profitability-lab/regular-options-macro-event-calendar/latest.json` |
| `feature_store` | `loaded` | `data/profitability-lab/regular-options-feature-store/latest.json` |
| `point_in_time_vix_bucket` | `loaded` | `data/profitability-lab/regular-options-point-in-time-vix-bucket/latest.json` |
| `quote_capability` | `loaded` | `data/profitability-lab/regular-options-local-quote-structure-capability-matrix/latest.json` |
| `base_clean_stack_identity_ledger` | `loaded` | `data/profitability-lab/regular-options-base-clean-stack-identity-ledger/latest.json` |
| `holdout_contract` | `loaded` | `data/contracts/forward-holdout-contract.json` |
