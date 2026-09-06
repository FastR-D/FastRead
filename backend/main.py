"""Supported server entrypoint. Legacy desktop routers are not mounted."""
import os
import uvicorn
from app.web.api import create_web_app

app = create_web_app()

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("BACKEND_PORT", "8483")))
