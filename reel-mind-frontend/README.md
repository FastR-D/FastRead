# Reel Mind Web Frontend

React 19 + Vite frontend for Reel Mind.

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

Use this only when you are intentionally working on frontend code and the backend is already running through the root entry.

```powershell
cd reel-mind-frontend
corepack enable
pnpm install
$env:VITE_API_BASE_URL="/api"
pnpm run dev -- --host 0.0.0.0 --port 3015
```

## Build

```powershell
pnpm run build
```
