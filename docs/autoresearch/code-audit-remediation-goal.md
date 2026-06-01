# Code Audit Remediation Goal

Use this prompt when running a multi-agent `/goal` loop to harden the active options product codebase section by section. The loop is complete only when every audit section has a long-term solution implemented and at least `4` of `6` independent subagents agree that the section is addressed.

## Objective

Iterate through the active regular supervised options product and AI commodity proof-lane code audit sections until each section has a durable implementation, verification evidence, and reviewer consensus.

Do not spend implementation effort on crypto options, Polymarket, or day-trading lanes unless a shared-infrastructure change directly touches the active regular options product or AI commodity proof lane.

## Audit Sections

Work through these sections one at a time:

1. Runtime architecture and request flow
2. Trading Desk UX monolith
3. Read versus mutate semantics
4. Data lifecycle and store ownership
5. Proof and evidence integrity
6. Live scan to position flow
7. Replay, Strategy Lab, and research pipelines
8. Monolithic Python files
9. Shared UI components and mobile UX
10. Verification gaps

## Definition Of Addressed

A section is addressed only when all of these are true:

- the implementation removes or materially reduces the root cause, not just the visible symptom
- the fix follows existing repo architecture and active lane boundaries
- user-facing behavior is clearer, safer, or more reliable
- proof and evidence classifications remain stricter than the UI claims
- relevant tests, scripts, or generated checks cover the changed behavior
- living docs are updated when architecture, workflow, route maps, proof posture, or next actions change
- no new stale, duplicate, or hidden state-changing path is introduced

For monolith sections, a long-term solution may be a safe extraction, a tested internal boundary, or a written and partially implemented migration seam. A TODO-only note is not enough.

## Consensus Gate

For each section, after implementation and local verification, run six independent subagent reviews:

1. Architecture reviewer
2. UX and workflow reviewer
3. Data lifecycle reviewer
4. Proof and evidence reviewer
5. Test and regression reviewer
6. Maintainability reviewer

Each reviewer must return one of:

- `agree_addressed`
- `agree_with_minor_followups`
- `blocked`

Count `agree_addressed` and `agree_with_minor_followups` as agreement. The section passes consensus when at least `4` of `6` reviewers agree.

Do not treat the vote as a substitute for correctness. If any reviewer reports a credible P0/P1 issue involving data loss, proof-source contamination, unintended state mutation, incorrect P&L, or a broken primary user flow, fix that issue before accepting the section, even if `4` reviewers agree.

## Loop Rules

1. Read the current living docs and route/storage maps before changing code.
2. Pick the highest-risk unaddressed audit section.
3. State the concrete root cause and expected long-term solution.
4. Make the smallest durable implementation that addresses the root cause.
5. Run focused verification first, then broader checks only when the blast radius warrants it.
6. Ask six subagents to review the completed section using the consensus rubric.
7. If fewer than `4` reviewers agree, use the blocking feedback to implement another iteration.
8. If `4` or more reviewers agree and no severe blocker remains, mark the section addressed in the run report.
9. Continue until all sections are addressed.

Do not edit this goal prompt to make an in-progress run pass. If the acceptance criteria need to change, stop the run and get explicit operator approval.

## Required Section Report

For every section, record:

- section name
- root cause
- files changed
- behavior changed
- verification commands and results
- subagent vote tally
- unresolved minor follow-ups
- why the solution is long-term rather than cosmetic

## Suggested Verification Ladder

Use the smallest relevant checks for each change:

```powershell
npm run verify:docs
npm run lint
npm run verify:typecheck
python -m pytest <tests> -q
npm run verify
```

For route changes, run:

```powershell
npm run docs:route-parity
npm run verify:docs
```

For active browser UX changes, run the app and do desktop plus mobile browser QA.

For proof, replay, tracked-position, or data-lifecycle changes, include targeted Python tests and a no-write/read-only artifact check whenever possible.

## Reviewer Prompt Template

Use this prompt for each of the six subagent reviews:

```text
You are reviewer <role> for the options-chatbot code audit remediation loop.

Review only section: <section name>.

Active scope: regular supervised options browser product and AI commodity proof lane. Do not spend review effort on crypto options, Polymarket, or day-trading except shared infrastructure touched by this patch.

Read the changed files, relevant tests, and the section report. Decide whether the section has a long-term solution implemented.

Return:
- verdict: agree_addressed, agree_with_minor_followups, or blocked
- confidence: high, medium, or low
- evidence: specific files/functions/tests reviewed
- blockers: concrete issues that must be fixed before acceptance
- minor_followups: non-blocking improvements

Block if the patch introduces or preserves a credible severe issue involving data loss, proof-source contamination, unintended state mutation, incorrect P&L, or a broken primary user flow.
```

## Initial Priority

Start with:

1. Trading Desk UX monolith
2. Read versus mutate semantics
3. Data lifecycle and store ownership
4. Proof and evidence integrity

Those four are the most likely to make or break user trust in the current product.
