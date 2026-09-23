"""Independent local authentication routes, also used by the full web app."""
import secrets

from fastapi import Request, Response
from pydantic import BaseModel, Field

from .auth import login, secure_cookie, require_user
from .local_accounts import rate_limit, redeem_credential, require_pre_auth, set_local_credential

class LoginInput(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class AccountCredentialInput(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    password: str = Field(min_length=12, max_length=256)


class LocalCredentialInput(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=12, max_length=256)
    current_password: str = Field(default='', max_length=256)


def register_local_routes(app, store, _set_session_cookie):
    @app.post('/api/auth/local-credential')
    def local_credential(data: LocalCredentialInput, request: Request):
        require_user(request)
        rate_limit(store, 'set-local-credential', request.client.host if request.client else 'unknown')
        return set_local_credential(store, request.cookies.get('fastread_session',''), data.email, data.password, data.current_password)


    @app.get("/api/auth/session-init")
    def session_init(response: Response):
        csrf = secrets.token_urlsafe(32)
        response.set_cookie("fastread_preauth", csrf, httponly=True,
                            secure=secure_cookie(), samesite="strict", max_age=1800, path="/")
        return {"csrf": csrf}

    @app.post("/api/auth/login")
    def sign_in(data: LoginInput, request: Request, response: Response):
        require_pre_auth(request)
        token, csrf = login(store, data.email, data.password, request.client.host if request.client else "unknown")
        _set_session_cookie(response, token)
        return {"csrf": csrf}

    @app.post("/api/auth/register")
    def register(data: AccountCredentialInput, request: Request):
        require_pre_auth(request)
        rate_limit(store, "invite", request.client.host if request.client else "unknown")
        return redeem_credential(store, "invite", data.token, data.password)

    @app.post("/api/auth/recover")
    def recover(data: AccountCredentialInput, request: Request):
        require_pre_auth(request)
        rate_limit(store, "recovery", request.client.host if request.client else "unknown")
        return redeem_credential(store, "recovery", data.token, data.password)
