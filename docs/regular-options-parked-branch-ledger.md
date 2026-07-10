# Regular Options Parked-Branch Ledger

This generated ledger consolidates parked, falsified, exhausted, and superseded regular-options branch docs that should not be rerun unless their revival condition changes.

## Summary

- Status: `parked_branch_ledger_ready`.
- Generated at UTC: `2026-07-10T04:05:13Z`.
- Branches: `7`.
- Live index references to parked source docs: `0`.
- Live index references to archived docs: `0`.
- Daily-ops parked step references: `0`.
- Accepted profitability: `false`.
- Historical rows are forward proof: `false`.
- Data artifacts deleted: `false`.

## Branch Ledger

| Branch | Title | Status | Blocker | Revival Condition | Archived Doc | Script | Data Artifact |
|---|---|---|---|---|---|---|---|
| `quote_surface_opening_range_reversal` | Quote-surface opening-range reversal replay | `parked_blocked_replay` | Latest-four strict executable rows remain below the 30-row evidence bar and PF/lower-bound/concentration blockers remain unresolved. | Revive only if a new trusted quote/underlying opening-bucket surface changes the strict executable row blocker. | `docs/archive/regular-options-quote-surface-opening-range-reversal-replay.md` | `scripts/build_regular_options_quote_surface_opening_range_reversal_replay.py` | `data/profitability-lab/regular-options-quote-surface-opening-range-reversal-replay/latest.json` |
| `quote_derived_synthetic_forward_surface` | Quote-derived synthetic-forward surface | `parked_missing_surface_coverage` | Same-minute call/put pair coverage has zero ready buckets and zero train/latest-month coverage. | Revive only if imported or otherwise trusted same-minute call/put quote coverage can satisfy the synthetic-forward coverage gate without synthetic marks as fills. | `docs/archive/regular-options-quote-derived-synthetic-forward-surface.md` | `scripts/build_regular_options_quote_derived_synthetic_forward_surface.py` | `data/profitability-lab/regular-options-quote-derived-synthetic-forward-surface/latest.json` |
| `local_quote_structure_capability_matrix` | Local quote-structure capability matrix | `exhausted_under_current_data` | No 13-symbol structure is replay-feasible because current local OPRA/NBBO coverage fails full-window, train-month, or latest-four feasibility gates. | Revive only after trusted local quote coverage expands enough to satisfy the fixed feasibility gates for at least one structure. | `docs/archive/regular-options-local-quote-structure-capability-matrix.md` | `scripts/build_regular_options_local_quote_structure_capability_matrix.py` | `data/profitability-lab/regular-options-local-quote-structure-capability-matrix/latest.json` |
| `all_local_quote_minute_structure_capability_atlas` | All-local quote-minute structure capability atlas | `exhausted_under_current_data` | All selected local quote-minute surfaces fail the 20-train-month feasibility gate despite dense latest-four quote depth. | Revive only after new trusted quote history or a separately approved feasibility contract changes the train-month coverage blocker. | `docs/archive/regular-options-all-local-quote-minute-structure-capability-atlas.md` | `scripts/build_regular_options_all_local_quote_minute_structure_capability_atlas.py` | `data/profitability-lab/regular-options-all-local-quote-minute-structure-capability-atlas/latest.json` |
| `direct_vix_source_repair_packet` | Direct VIX source-repair packet | `superseded_by_materialized_vix_source` | Point-in-time VIX bucket is already ready from the materialized source, so no direct-VIX import approval question is current. | Revive only if the materialized VIX source or VIX bucket becomes missing, stale, malformed, or policy-incompatible. | `docs/archive/regular-options-direct-vix-source-repair-packet.md` | `scripts/build_regular_options_direct_vix_source_repair_packet.py` | `data/profitability-lab/regular-options-direct-vix-source-repair-packet/latest.json` |
| `chain_native_relaxation_archive` | Chain-native relaxation archive | `archived_disproved_branch` | Exact-exit readback disproved all current and relaxed chain-native scenarios with negative net P&L and PF below one. | Revive only if a new exact-priced scenario or source surface changes the disproved chain-native relaxation evidence. | `docs/archive/regular-options-chain-native-relaxation-archive.md` | `scripts/build_regular_options_chain_native_relaxation_archive.py` | `data/forward-tracking/regular_options_chain_native_relaxation_archive_latest.json` |
| `exhausted_contract_archive` | Exhausted contract archive | `archived_exhausted_source_targets` | Repeated exact contract/date repair attempts returned no exact OPRA/NBBO rows from the current source. | Revive individual targets only if a new trusted source family or provider backfill changes the exact-date no-match result. | `docs/archive/regular-options-exhausted-contract-archive.md` | `scripts/build_regular_options_exhausted_contract_archive.py` | `data/profitability-lab/regular-options-exhausted-contract-archive/latest.json` |

## Reconstruction Contract

- Archived docs preserve generated report content under `docs/archive/`.
- Scripts and data artifacts remain in place for reconstruction or revival-condition review.
- These branches are not accepted profitability, not forward proof, and not production scanner evidence.
- Do not rerun a parked branch unless its ledger revival condition is met by new trusted data or a separate approved research contract.

## Boundary

This ledger is archival documentation only. It does not import quotes, mutate `options_history.db`, mutate evidence stores, consume protected holdout, change scanner policy, change stops or sizing, lower proof bars, enable live validation, enable auto-track, prepare broker orders, or promote any lane.
