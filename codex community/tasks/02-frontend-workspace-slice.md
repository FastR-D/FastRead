# Task 02: Frontend Workspace Slice

You are a worker Codex terminal. Work read-only.

## Goal

Find the next small frontend refactor slice from the plan that continues the workspace cleanup without destabilizing the UI.

## Scope

Focus on unfinished P3/P5 frontend items:

- Remaining `MarkdownViewer.tsx` responsibilities.
- Whether `VersionSelector`, `WorkspaceToolbar`, or `WorkspacePanels` can be extracted cleanly.
- Whether Markmap, Chat, or KnowledgeCards dynamic import is a safe next step.
- Any remaining typed API boundary issues that block workspace cleanup.

## Required checks

Inspect only the files needed under:

- `fastread-frontend/src/pages/HomePage/components/`
- `fastread-frontend/src/hooks/`
- `fastread-frontend/src/services/`
- `fastread-frontend/src/store/`
- `fastread-frontend/package.json`
- `readme/refactor-plan-2026-06-04.md`

## Deliverable

Write `codex community/outbox/02-frontend-workspace-slice-<agent>.md`.

Include:

- Best single slice to implement now.
- Exact component boundaries and props if extraction is recommended.
- Risks around state, event handling, or bundle splitting.
- Verification command, preferably `npm run build` from `fastread-frontend`.

Do not edit source files.
