import ipaddress
import os

from fastapi import HTTPException, Request


def require_local_request(request: Request) -> None:
    if os.getenv("ALLOW_NON_LOCAL_ADMIN", "").lower() in {"1", "true", "yes"}:
        return

    host = request.client.host if request.client else ""
    if host == "testclient":
        return
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        raise HTTPException(status_code=403, detail="仅允许本机访问该接口")

    if not ip.is_loopback:
        raise HTTPException(status_code=403, detail="仅允许本机访问该接口")
