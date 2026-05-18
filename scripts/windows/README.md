# Windows Scripts

Run these from the repository root or double-click them in this folder.

| Script | Purpose |
| --- | --- |
| `check.bat` | Check Docker, Docker Compose, port, disk space, and required files. |
| `start.bat` | Build and start the Docker deployment. |
| `status.bat` | Show Compose status and backend health. |
| `stop.bat` | Stop Docker services. |
| `dev.bat` | Start backend and frontend from source after dependencies are installed. |

Common commands:

```powershell
.\scripts\windows\check.bat
.\scripts\windows\start.bat
.\scripts\windows\start.bat --quick
.\scripts\windows\stop.bat
```
