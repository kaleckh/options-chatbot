# Autoresearch Constraints

## Critical Rule: Read Code First

- Never answer questions about the codebase, architecture, or design without reading the actual code first.
- Do not speculate from naming, memory, or what "makes sense."
- If asked whether `X` does `Y`, read `X` before answering.
- If asked why `Z` happens, read the relevant path before answering.
- If asked about a design decision, read the implementation before claiming what it does.
- Getting it wrong confidently is worse than saying "let me check."

This repo's autoresearch loop is research-only. It is meant to test one narrow deterministic hypothesis at a time and produce evidence for a human review decision.

Autoresearch 2.0 has two modes:

- `search`: test one narrow challenger against a compatible control frame
- `validation`: evaluate a frozen cohort under the truth bundle and forward holdout hierarchy

## Non-Negotiables

- Do not weaken pessimistic fills.
- Do not loosen calibrated expectancy behavior.
- Do not relax watch, block, or stability gating.
- Do not auto-apply strategy profiles or write live profile changes as part of a research cycle.
- Do not bundle multiple strategy concepts into one cycle.
- Do not treat one good replay as promotion-ready proof.

## Required Defaults

- One hypothesis per cycle.
- Fixed replay matrix:
  - `lookback_years`: `1`, `2`
  - `n_picks`: `1`
  - `iv_adj`: `1.2`
  - `pricing_lane`: `mid`, `pessimistic`
- Mandatory regression gate:
  - `python -m unittest tests.test_strategy_audit -v`
  - `python -m unittest tests.test_options_api_e2e -v`
- Required decision labels:
  - `promote`
  - `hold`
  - `reject`

## Out Of Scope For v1

- No automatic code mutation.
- No automatic profile promotion.
- No autonomous strategy optimization.
- No backend API orchestration.
- No direct broker or live-trading actions.
- No automatic live-profile promotion.

## Truth Guards

- A frozen phase manifest is the authority for allowed cohorts, truth lanes, and watchlists.
- Synthetic replay may screen ideas, but it does not justify promotion by itself.
- Imported daily truth may upgrade an idea to imported-truth review, but not to live-ready confidence by itself.
- Forward holdout is the highest-authority evidence lane once available.
- Human approval is required for final `promote` / `hold` / `reject` closure.
