# Agent Worktree Hygiene

This is the operating contract for Codex agents and automations working in this repository.

## Start Cleanly

Before editing files:

1. Run `git status --short`.
2. Identify unrelated user changes and leave them alone.
3. Prefer an automation worktree for recurring, large, or exploratory work.
4. If the current worktree is already dirty, keep new edits scoped and report how they relate to the existing diff.

## Push Big Changes

Small local fixes can be left unstaged when the user only asked for investigation or a local patch. Big changes should not sit in a dirty worktree.

Agents should create a branch, commit, push, and report the branch or PR when a run produces any of the following:

- a broad audit fix set
- multiple code files changed across subsystems
- generated docs or scripts required for verification
- new tests that must ship with the fix
- any change that another weekly automation needs as a base
- any release-blocking fix that would be lost in a clean checkout

Use a `codex/` branch prefix unless the user asks for a different branch name. Do not push secrets, local databases, credentials, or generated runtime artifacts.

## Keep The Worktree Explainable

End each run with:

```powershell
git diff --check
git status --short
```

The final report must identify:

- files changed by category
- untracked files that are required for the fix
- generated files that changed during verification
- commands that passed or failed
- whether changes were pushed, and if not, why not

## Untracked Files

Untracked files are release risks until they are intentionally included or intentionally ignored. If an untracked file is required for tests, docs, runtime, or automation, agents must call it out explicitly and include it in the pushed branch when publishing is allowed.

## What Not To Do

- Do not revert unrelated user work.
- Do not hide dirty state by deleting files.
- Do not hand-edit generated files when their generator can be run.
- Do not leave a large verified fix only in local unstaged state when pushing is allowed.
- Do not claim a run is release-ready if required untracked files remain outside the branch or PR.
