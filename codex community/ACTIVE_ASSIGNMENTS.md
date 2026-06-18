# Active Assignments

Updated: 2026-06-19 01:12 Asia/Shanghai

## Coordination Contract

- Main agent: the other Codex terminal. Owns final source edits, verification, and updates to `readme/refactor-plan-2026-06-04.md`.
- Worker agent: this chat. Works read-only on project source files and writes investigation reports only unless the user explicitly expands scope.
- Shared channel: `codex community/tasks/` for task briefs and `codex community/outbox/` for reports.

## Current State

- This worker completed reports for all three task files:
  - `outbox/01-backend-refactor-slice-codex-worker.md`
  - `outbox/02-frontend-workspace-slice-codex-worker.md`
  - `outbox/03-engineering-gate-slice-codex-worker.md`
- The repository already has many modified and deleted files outside this coordination folder. Treat them as existing work and do not revert them.
- The next useful worker contribution is a read-only investigation report, not source edits.

## Worker Task Selection

Normal worker terminals should pick exactly one of these:

- `tasks/01-backend-refactor-slice.md`
- `tasks/02-frontend-workspace-slice.md`
- `tasks/03-engineering-gate-slice.md`

If multiple worker terminals are active, prefer different task numbers. If unsure, choose the lowest-numbered task that does not already have a matching report in `outbox/`.

## Claiming

Before starting, create a short claim report in your eventual outbox file path:

```text
codex community/outbox/<task-id>-<agent-name>.md
```

Initial content can be:

```markdown
# <task title>

Status: claimed
Agent: <agent-name>
Started: <local time>
```

When finished, replace or extend it with the full report format from `README.md`.

## Main Agent Intake

The main Codex terminal should treat files in `outbox/` as advisory reports. It should read them, choose patches, edit source files, run verification, and update the refactor ledger.
