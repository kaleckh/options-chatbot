# Regular Options Source Replay Pass

Source replay did not make any high-value blocker exact proof-eligible.

## At A Glance

- Overall status: `source_replay_no_change`.
- Targets attempted: `2`.
- Targets resolved: `0`.
- Targets still blocked: `5`.
- Targets unsafe/no scoped replay command: `3`.
- Final holdout before / after: `28` / `28`.
- PF lower bound before / after: `0.61` / `0.61`.
- Forward-freeze candidates after: `0`.
- Robust candidates after: `0`.
- Promotion ready after: `False`.

## Target Results

| target_id | lane_id | ticker | contract_symbol | quote_date | result | reason_codes | next_action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| source-replay-aapl-2026-01-12 | bullish_pullback_observation | AAPL | AAPL260116C00295000 | 2026-01-12 | unsafe_to_run | ['source_replay_variant_not_executed', 'no_safe_scoped_source_replay_command_found'] | No existing safe scoped source replay command was found for this target. |
| source-replay-aapl-2026-03-12 | bullish_pullback_observation | AAPL | AAPL260320C00300000 | 2026-03-12 | unsafe_to_run | ['source_replay_variant_not_executed', 'no_safe_scoped_source_replay_command_found'] | No existing safe scoped source replay command was found for this target. |
| source-replay-unh-2025-11-06 | bullish_pullback_observation | UNH | UNH251128C00410000 | 2025-11-06 | unsafe_to_run | ['source_replay_variant_not_executed', 'no_safe_scoped_source_replay_command_found'] | No existing safe scoped source replay command was found for this target. |
| source-replay-dia-2025-11-05 | tracked_winner_cheap_debit_continuity_v1 | DIA | DIA251128C00495000 | 2025-11-05 | still_missing | ['target_contract_remains_in_unpriced_replay_rows'] | Do not repeat provider loops; this source replay did not clear the exact blocker. |
| source-replay-dia-2025-11-17 | tracked_winner_cheap_debit_continuity_v1 | DIA | DIA251219C00500000 | 2025-11-17 | still_missing | ['target_contract_remains_in_unpriced_replay_rows'] | Do not repeat provider loops; this source replay did not clear the exact blocker. |

## Interpretation

- The DIA tracked-winner replay was derived-artifact-only and did not import quotes or write evidence databases.
- The two DIA contracts remained in unpriced replay rows, so they are not exact proof-eligible.
- The AAPL and UNH ticker-sleeve rows did not have a confirmed safe scoped replay command in the inspected local runners, so they remain unsafe-to-run/no-action under this pass.
- Final-holdout count and PF lower bound did not improve in the refreshed robust stack.
- No candidate moved from paper-shadow to forward-freeze eligible.

## Post-Replay Rerun Commands

- `npm run options:features:regular-options`
- `npm run options:robust-search:regular-options`
- `npm run options:replay:regular-options-walk-forward`
- `npm run options:research:robust-edge`
- `npm run options:research:hypothesis-tournament`
- `npm run options:research:evidence-blocker-burndown`
- `npm run options:audit:monthly-profitability`

## Non-Goals

- This readback does not create trades.
- This readback does not submit broker orders.
- This readback does not enable auto-track.
- This readback does not enable live validation.
- This readback does not change scanner policy.
- This readback does not change stops.
- This readback does not change sizing.
- This readback does not lower proof bars.
- This readback does not mutate evidence databases.
- This readback does not import quotes.
