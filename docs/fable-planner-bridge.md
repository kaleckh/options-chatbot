# Fable Planner Bridge

This bridge lets Claude Fable 5 act as an external technical planner while Codex remains the local implementer and verifier.

## Boundary

Fable plans are advisory orchestration context only. They do not authorize trading, evidence mutation, scanner or strategy changes, proof-bar changes, broker action, promotion, live validation, stop/sizing changes, protected-holdout use, cohort append, quote import, or treating historical rows as forward proof.

Codex must still read the relevant code and living docs before implementation. If a Fable plan asks for a high-risk action, convert that action into an explicit operator approval question plus a safe read-only fallback.

## Manual Handoff

Generate the packet:

```powershell
uv run --locked python scripts/build_fable_planner_packet.py --objective "Plan the next technical task for options-chatbot" --json
```

The script writes:

- `data/agent-control/fable/planner_packet_latest.json`
- `data/agent-control/fable/planner_packet_latest.md`

Send the Markdown prompt to Fable and ask it to return exactly the requested JSON object.

Validate Fable's returned plan:

```powershell
uv run --locked python scripts/build_fable_planner_packet.py --validate-plan path\to\fable-plan.json --json
```

If the plan validates and should become the current reviewed handoff, normalize it:

```powershell
uv run --locked python scripts/build_fable_planner_packet.py --validate-plan path\to\fable-plan.json --write-normalized-plan --json
```

The normalized plan is written under `data/agent-control/fable/`. It is still not accepted proof or approval; it is a reviewed implementation input for Codex.

## API Path

The first implementation is API-neutral. Official Anthropic docs identify the Fable API model ID as `claude-fable-5`, but no local API call is wired here yet. A future API wrapper should:

- keep the API key server-side or in the local shell environment, never in repo files;
- send the generated packet prompt as the model input;
- require JSON output matching the packet schema;
- handle `stop_reason: "refusal"` as a successful refusal response, not a crash;
- preserve the same validation step before Codex acts on the plan.

## Validation Limits

`scripts/build_fable_planner_packet.py --validate-plan` checks the required shape and rejects authority-shaped wording such as approving live validation, broker orders, proof-bar changes, promotion, or protected-holdout consumption.

It is a guardrail, not a substitute for engineering review. Codex still owns final scoping, code reads, implementation, tests, and the final proof-boundary statement.
