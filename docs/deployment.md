# Deployment

Recommended path: Windows + Docker Desktop.

## Windows Scripts

All helper scripts live in `scripts/windows/`.

| Script | Purpose |
| --- | --- |
| `check.bat` | Check Docker, Docker Compose, port, disk space, and required project files. |
| `start.bat` | Build and start the Docker demo. |
| `status.bat` | Show Docker Compose status and backend health. |
| `stop.bat` | Stop Docker services. |
| `dev.bat` | Start backend and frontend from source after dependencies are installed. |

First run:

```powershell
.\scripts\windows\check.bat
.\scripts\windows\start.bat
```

Open:

```text
http://127.0.0.1:3015/
```

Fast restart without rebuilding images:

```powershell
.\scripts\windows\start.bat --quick
```

Stop services:

```powershell
.\scripts\windows\stop.bat
```

## Docker Compose

The main deployment uses:

```powershell
docker compose up -d --build
```

GPU backend builds are kept in `docker-compose.gpu.yml`:

```powershell
docker compose -f docker-compose.gpu.yml up -d --build
```

## Troubleshooting

If Docker is unavailable, open Docker Desktop and wait until the engine is running.

If port `3015` is already in use, edit `.env` and change `APP_PORT`.

If the page opens but note generation fails, check model provider settings, cookie sync, and `scripts/windows/status.bat`.
