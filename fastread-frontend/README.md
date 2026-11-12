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
pnpm install --frozen-lockfile
$env:VITE_API_BASE_URL="/api"
pnpm dev --host 127.0.0.1 --port 3015
```

## Build

```powershell
pnpm typecheck
pnpm lint
pnpm test
pnpm build
pnpm test:fastui:browser
pnpm test:reader:browser
```

The browser suite uses Microsoft Edge and the production build. It covers
settings and CAS dialogs, light/dark themes, administrator actions, connection
codes, research directions, and FastWrite handoff. HTTP fixtures isolate UI
behavior; API integration tests live in the Go backend.

For an end-to-end run against a disposable Go instance, set
`FASTREAD_TEST_BASE_URL`, `FASTREAD_TEST_EMAIL`, and `FASTREAD_TEST_PASSWORD`, then
run `pnpm test:go:browser`. This suite creates test users and providers,
imports a text PDF through the worker, and verifies the desktop and mobile reader.

## FastUI

`uno.config.ts` uses `fastUIContent` and `presetFastUI()`. The Vite plugin generates
the styles used by imported components; `src/main.tsx` imports `virtual:uno.css`.
Color mode follows the system or the user's saved `fastread.theme` preference.

Settings contains workspace models and FastWrite/FastNews connection codes. CAS
authentication opens separately. System administrators can manage users and
manage users and shared models in searchable tables from the top navigation.
Creation and permission changes open in dialogs. Shared models support workspace
grants and individual user grants; either match grants access. Changes to both
scopes are saved together, and cancellation preserves existing permissions. The reading desk uses the same FastUI components for PDF navigation, annotations,
conversations, knowledge bases, notes, reports and neighbor filtering.

All application appearance comes from FastUI components and `fastui-*` native
classes. `presetWind3()` supplies standard layout utilities for responsive panels;
there are no application CSS files, custom palettes, product CSS overrides, CSS
modules, Tailwind pipeline or shadcn configuration. Existing semantic class names
on the reading desk are browser-test hooks, not stylesheet selectors.
Sidebars compose `ActivityRail` with grouped explorer lists, following FastWrite.
Icon tabs use native FastUI tab classes and its keyboard navigation helper;
spacing and tab height are configured with layout utilities and FastUI tokens.

PDF.js 4.10.38 supplies its official text-layer stylesheet, matching the vendored
renderer. KaTeX supplies math typesetting. Inline PDF sizes and highlight rectangles
are calculated document coordinates, not application theme styles.

The reader browser suite renders a real text PDF with HTTP fixtures. It checks
keyboard tabs, modal focus return, source selection, annotations, notes, quoted
questions, citation highlights, report display and neighbor filters, then verifies
scrolling and overflow at 1440/1024/390px in light and dark mode. Screenshots and
results are written to `test-results/reader/`.
