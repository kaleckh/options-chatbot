# Automation Handoff

This file family is the shared handoff between the read-only automations and the code-changing validation automation.

## Purpose

- `Hourly Operational Health` should update `automation-handoff.json` with the latest health snapshot and any new unresolved operational or evidence blockers.
- `Weekday Truth Holdout` should update `automation-handoff.json` with the latest forward-evidence snapshot and any new holdout sufficiency blockers.
- `Daily Profit Validation` should read `automation-handoff.json` first, prioritize the highest-profit-impact unresolved items, mark resolved issues, and write back the latest validation outcome.

## Contract

The shared JSON should keep:

- `latest_operational_health`
- `latest_truth_holdout`
- `latest_profit_validation`
- `open_issues`
- `resolved_issues`

Each issue should be specific enough for the daily validation cycle to act on without re-deriving the full problem statement:

- stable `issue_id`
- `source_automation`
- `first_seen_at`
- `last_seen_at`
- `severity`
- `blocker_class`
- `summary`
- `evidence`
- `suggested_fix_targets`
- `status`

## Rule

Read-only automations are still useful because they collect evidence and triage blockers, but that only matters if the code-changing automation consumes the same shared queue and closes the loop.
