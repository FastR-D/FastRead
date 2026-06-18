# Task 01: Backend Refactor Slice

You are a worker Codex terminal. Work read-only.

## Goal

Find one backend refactor slice from `readme/refactor-plan-2026-06-04.md` that is still unfinished, high value, and small enough for the main agent to patch and verify now.

## Scope

Focus on unfinished P2/P3 items:

- DAO/repository plus session injection boundaries.
- `Provider.id` versus `Model.provider_id` type/constraint consistency.
- `task_serial_executor` naming or lifecycle mismatch.
- `TranscriptService` transcriber cache key, especially model/device changes.

## Required checks

Inspect only the files needed under:

- `backend/app/db/`
- `backend/app/services/`
- `backend/app/routers/`
- `backend/app/models/`
- `backend/tests/`
- `readme/refactor-plan-2026-06-04.md`

## Deliverable

Write `codex community/outbox/01-backend-refactor-slice-<agent>.md`.

Include:

- Best single slice to implement now.
- Why it is not already completed.
- Exact files likely to change.
- Tests to add or update.
- Verification command, preferably `backend\.venv\Scripts\python.exe -m pytest --basetemp .tmp\pytest backend\tests`.

Do not edit source files.
