from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Callable, Protocol

from fastapi import HTTPException, Request


@dataclass(frozen=True)
class AccountPrincipal:
    account_id: str
    auth_source: str


class AuthProvider(Protocol):
    def authenticate(self, request: Request) -> AccountPrincipal: ...


class LocalDesktopAuthProvider:
    """The local single-user desktop account is logged in by definition."""

    def authenticate(self, request: Request) -> AccountPrincipal:
        return AccountPrincipal(account_id="local", auth_source="local_desktop")


class SharedAuthProvider:
    """Deployment-neutral adapter; the host application supplies token verification."""

    def __init__(self, verifier: Callable[[str], str] | None = None):
        self._verifier = verifier

    def authenticate(self, request: Request) -> AccountPrincipal:
        if self._verifier is None:
            raise HTTPException(status_code=503, detail="shared authentication verifier is not configured")
        scheme, _, credential = request.headers.get("authorization", "").partition(" ")
        if scheme.casefold() != "bearer" or not credential:
            raise HTTPException(status_code=401, detail="bearer authentication required")
        account_id = str(self._verifier(credential) or "").strip()
        if not account_id:
            raise HTTPException(status_code=401, detail="invalid authentication credential")
        return AccountPrincipal(account_id=account_id, auth_source="shared_auth")


_shared_verifier: Callable[[str], str] | None = None


def configure_shared_auth_verifier(verifier: Callable[[str], str] | None) -> None:
    global _shared_verifier
    _shared_verifier = verifier


def current_account(request: Request) -> AccountPrincipal:
    mode = os.getenv("FASTREAD_AUTH_MODE", "local").strip().casefold()
    provider: AuthProvider = (
        LocalDesktopAuthProvider() if mode == "local" else SharedAuthProvider(_shared_verifier)
    )
    return provider.authenticate(request)
