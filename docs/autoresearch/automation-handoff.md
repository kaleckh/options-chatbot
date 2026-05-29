# Automation Handoff

`docs/autoresearch/automation-handoff.json` is no longer the live shared state for unattended profit-loop automations.

## What Changed

- Live automation state now lives outside repo worktrees under `%CODEX_HOME%/automations/shared/options-chatbot/`.
- The repo copy is documentation only so worktree runs do not fight over a tracked file.
- The authoritative contract for the patch-capable automation loop is now [Profit Loop Contract](../profit-loop/contract.md).

## What Stays Here

- The repo JSON remains as a schema/example for humans.
- `scripts/autoresearch_cycle.py` and the truth-first research docs remain research-only.
- The automation loop now uses deterministic driver scripts and a shared external state store instead of prompt-managed JSON edits.
