# Deployment

Recommended path: Windows local startup with `run.bat`.

Docker is optional. Use it only when you explicitly want the container deployment path.

## Local Startup

First make sure these dependencies exist:

- `backend\.venv`
- `fastread-frontend\node_modules`

Start:

```powershell
.\run.bat
```

Open:

```text
http://127.0.0.1:3015/
```

Backend health:

```text
http://127.0.0.1:8483/api/sys_check
http://127.0.0.1:8483/api/sys_health
```

Stop:

```powershell
.\run.bat --stop
```

Status:

```powershell
.\run.bat --status
```

## Manual Development

Backend:

```powershell
cd backend
.\.venv\Scripts\python.exe main.py
```

Frontend:

```powershell
cd fastread-frontend
$env:VITE_API_BASE_URL="/api"
pnpm run dev -- --host 0.0.0.0 --port 3015
```

## Optional Docker Compose

```powershell
docker compose up -d --build
```

Open:

```text
http://127.0.0.1:3015/
```

Check:

```powershell
docker compose ps
docker compose logs --tail=80 backend
```

GPU backend builds are kept in `docker-compose.gpu.yml`:

```powershell
docker compose -f docker-compose.gpu.yml up -d --build
```

## Troubleshooting

If port `3015` is already in use, change the frontend port in `.env`.

If backend port `8483` is already in use, change `BACKEND_PORT` and keep frontend API settings aligned.

If related-work discovery fails:

- confirm the backend health checks pass;
- confirm search provider settings are configured;
- check backend logs for metadata search failures;
- inspect the provider status shown in the related-work panel;
- remember that provider degradation is reported explicitly and never replaced by model guesses.
