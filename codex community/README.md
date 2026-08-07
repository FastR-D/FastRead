# Codex Community Workboard

This folder is the coordination surface for multiple Codex terminals working on the same FastRead checkout.

Start with `ACTIVE_ASSIGNMENTS.md` for the current live coordination state, then read the task files.

## Current owner roles

- Main agent: the current chat window. It chooses final changes, edits source code, runs verification, and updates `readme/refactor-plan-2026-06-04.md`.
- Worker agents: other Codex terminals. They should take one task file from `tasks/`, inspect the repo, and write a concise report into `outbox/`.

## Worker rules

1. Do not edit project source files unless the task file explicitly says edits are allowed.
2. Do not run destructive commands, reset git state, or revert unrelated changes.
3. Treat `readme/refactor-plan-2026-06-04.md` as the refactor ledger.
4. Prefer narrow, verifiable recommendations over broad redesign.
5. If you run commands, include the command and result summary in your outbox report.
6. If you find a likely patch, list exact files and test commands instead of applying it.

## Outbox format

Create one Markdown file under `codex community/outbox/`:

```text
codex community/outbox/<task-id>-<agent-name>.md
```

Use this structure:

```markdown
# <task title>

## Findings

## Recommended Patch

## Risks

## Verification

## Files Inspected
```

The main agent will read these reports and decide what to implement.
