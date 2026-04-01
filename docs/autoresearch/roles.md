# Autoresearch Roles

The v1 loop assumes three distinct roles. A single person can fill all three, but the responsibilities stay separate.

## Hypothesis

Purpose: propose one narrow deterministic change.

Must do:

- Name the idea with a short slug.
- State the exact behavior change.
- Limit the edit scope to the smallest relevant files.
- List the metrics that define success or failure.
- Mark whether the idea is replay-only or could affect live behavior later.

Stop when:

- The proposal is written.
- The allowed file list is explicit.
- The rollback condition is explicit.

## Executor

Purpose: run the fixed research bundle and write artifacts only.

Must do:

- Copy the approved proposal into the run directory.
- Run the mandatory regression tests.
- Run the fixed replay matrix.
- Build the primary-scenario reports.
- Build the evidence bundle and decision packet.
- Write artifacts under `research_runs/<timestamp>_<slug>/`.

Stop when:

- The run artifacts exist.
- The comparison is written when `--compare-to` is supplied.
- The run status is recorded as success or failure.
- The machine recommendation is written, but not treated as final approval.

## Auditor

Purpose: compare baseline vs candidate and make a human-readable recommendation.

Must do:

- Review `matrix.json`, `stability.json`, `policy.json`, `metric_truth.json`, and `comparison.json` when present.
- Review `evidence_bundle.json` and `decision_packet.json`.
- Decide `promote`, `hold`, or `reject`.
- Explain the decision in one short memo.
- Record the final closure artifact rather than editing the log by hand.

Stop when:

- The decision is written.
- Any reason for caution is explicit.
- No silent promotion is implied.
