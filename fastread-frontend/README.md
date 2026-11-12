# FastRead Web Frontend

React 19 + TypeScript + Vite frontend for the FastRead Go API. UI controls and the
application shell use FastUI 0.3.0 (`@fastrd/ui-react` and
`@fastrd/ui-foundation`).

## Project Entry

Do not start the whole project from this directory. The repository has one Windows entry at the root:

```powershell
.\run.bat
```

Useful root commands:

```powershell
.\run.bat --check
.\run.bat --status
.\run.bat --stop
.\run.bat --no-open
```

The default app URL is:

```text
http://127.0.0.1:3015/
```

## Frontend-Only Development

Run the Go API before starting frontend development. `BACKEND_PORT` selects the
local API port (8483 by default).

```powershell
cd fastread-frontend
corepack pnpm install --frozen-lockfile
$env:VITE_API_BASE_URL="/api"
corepack pnpm dev --host 127.0.0.1 --port 3015
```

## Build

```powershell
corepack pnpm typecheck
corepack pnpm lint
corepack pnpm test
corepack pnpm build
corepack pnpm test:fastui:browser
```

The browser suite uses Microsoft Edge and the production build. It covers
settings and CAS dialogs, light/dark themes, administrator actions, connection
codes, research directions, and FastWrite handoff. HTTP fixtures isolate UI
behavior; API integration tests live in the Go backend.

For an end-to-end run against a disposable Go instance, set
`FASTREAD_TEST_BASE_URL`, `FASTREAD_TEST_EMAIL`, and `FASTREAD_TEST_PASSWORD`, then
run `corepack pnpm test:go:browser`. This suite creates test users and providers,
imports a text PDF through the worker, and verifies the desktop and mobile reader.

## FastUI

`uno.config.ts` uses `fastUIContent` and `presetFastUI()`. The Vite plugin generates
the styles used by imported components; `src/main.tsx` imports `virtual:uno.css`.
Color mode follows the system or the user's saved `fastread.theme` preference.

Settings contains workspace models and FastWrite/FastNews connection codes. CAS
authentication opens separately. System administrators can manage users and
assign shared models from the top navigation. The reading desk retains PDF
navigation, annotations, conversations, knowledge bases, notes, and reports.
