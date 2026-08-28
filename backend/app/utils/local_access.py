import ipaddress
import os
from typing import Any

from fastapi import HTTPException, Request
from starlette.responses import PlainTextResponse


def _non_local_admin_enabled() -> bool:
    return os.getenv("ALLOW_NON_LOCAL_ADMIN", "").lower() in {"1", "true", "yes"}


def is_local_client_host(host: str) -> bool:
    if host == "testclient":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def require_local_request(request: Request) -> None:
    if _non_local_admin_enabled():
        return

    host = request.client.host if request.client else ""
    if not is_local_client_host(host):
        raise HTTPException(status_code=403, detail="仅允许本机访问该接口")


class LocalOnlyASGI:
    """Apply the same peer-address Gate to mounted ASGI applications."""

    def __init__(self, app: Any):
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") == "http" and not _non_local_admin_enabled():
            client = scope.get("client")
            host = str(client[0]) if client else ""
            if not is_local_client_host(host):
                response = PlainTextResponse("仅允许本机访问该资源", status_code=403)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
