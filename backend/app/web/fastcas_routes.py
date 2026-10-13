"""FastCAS browser endpoints; the signed event endpoint never accepts JSON."""
import secrets
import os
from urllib.parse import urlparse

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from .auth import require_user, secure_cookie
from .fastcas_service import FastCASService


class LocalProof(BaseModel):
    password: str = Field(min_length=1, max_length=256)


def register_fastcas_routes(app, store, set_session_cookie, service=None):
    service = service or FastCASService(store)
    app.state.fastcas = service
    configured_path = urlparse(service.config.get('redirect_uri', '')).path
    default_base = configured_path.removesuffix('/api/auth/fastcas/callback') if configured_path else ''
    base_path = "/" + os.environ.get("FASTREAD_BASE_PATH", default_base).strip("/")
    base_path = base_path.rstrip("/")
    cookie_path = base_path + "/api/auth/fastcas"

    def enabled():
        if not service.enabled:
            raise HTTPException(404, '未启用 FastCAS')

    def origin(request):
        enabled()
        target = urlparse(service.config['redirect_uri'])
        if request.headers.get('origin') != f'{target.scheme}://{target.netloc}':
            raise HTTPException(403, '不允许跨站请求')

    def execute(operation):
        try:
            return operation()
        except HTTPException:
            raise
        except Exception as error:
            # Never echo provider bodies, authorization codes or credential errors.
            status = getattr(error, 'status', 502)
            raise HTTPException(status if status in (400,401,403,409,429) else 502, 'FastCAS 请求未完成，请重试或使用本地登录') from None

    def cookie(response, binding):
        response.set_cookie('fastread_fastcas_binding', binding, httponly=True, secure=secure_cookie(), samesite='lax', max_age=300, path=cookie_path)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/api/auth/fastcas/available')
    def available():
        return {'enabled': service.enabled}

    @app.get('/api/auth/fastcas/login')
    def login():
        enabled()
        binding = secrets.token_urlsafe(32)
        url = execute(lambda: service.sdk.begin_login(binding))
        return cookie(RedirectResponse(url, status_code=302), binding)

    @app.post('/api/auth/fastcas/link')
    def link(data: LocalProof, request: Request):
        origin(request)
        require_user(request)
        binding = secrets.token_urlsafe(32)
        url = execute(lambda: service.begin_link(binding, request.cookies.get('fastread_session',''), data.password, request.client.host if request.client else 'unknown'))
        return cookie(JSONResponse({'url': url}), binding)

    @app.get('/api/auth/fastcas/callback')
    def callback(request: Request):
        enabled()
        # Use the configured external URL, never untrusted forwarded Host headers.
        callback_url = service.config['redirect_uri'].split('?',1)[0] + '?' + request.url.query
        try:
            token = execute(lambda: service.finish(callback_url, request.cookies.get('fastread_fastcas_binding',''), request.cookies.get('fastread_session','')))
        except HTTPException:
            response = RedirectResponse(base_path + '/?fastcas=failed', status_code=302)
        else:
            response = RedirectResponse(base_path + '/?fastcas=complete', status_code=302)
            if token:
                set_session_cookie(response, token)
        response.delete_cookie('fastread_fastcas_binding', path=cookie_path)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.get('/api/auth/fastcas/status')
    def status(request: Request):
        user = require_user(request)
        row = service.current(user.user_id) if service.enabled else None
        return {'enabled': service.enabled, 'link': {k: row[k] for k in ('id','subject','state','version')} if row else None}

    @app.post('/api/auth/fastcas/reconcile')
    def reconcile(request: Request):
        origin(request)
        user = require_user(request)
        row = service.current(user.user_id)
        if not row:
            raise HTTPException(404, '没有待完成的认证')
        execute(lambda: service.reconcile(row))
        return {'ok': True}

    @app.post('/api/auth/fastcas/revoke')
    def revoke(data: LocalProof, request: Request):
        origin(request)
        require_user(request)
        execute(lambda: service.revoke(request.cookies.get('fastread_session',''), data.password, request.client.host if request.client else 'unknown'))
        return {'ok': True}

    @app.post('/api/auth/fastcas/events')
    async def events(request: Request):
        enabled()
        if request.headers.get('content-type', '').split(';', 1)[0].strip() != 'application/jwt':
            raise HTTPException(415, '需要签名事件')
        from fastcas.fastapi import receive_event
        def apply(event):
            if event['type'] == 'account_link.revoked':
                service.links.apply_verified_event(event)
            elif event['status'] == 'disabled':
                service.links.apply_verified_logout({'id': event['id'], 'subject': event['subject']})
        await receive_event(request, service.sdk, apply)
        return {'ok': True}

    @app.post('/api/auth/fastcas/backchannel-logout')
    async def backchannel_logout(request: Request):
        enabled()
        from fastcas.fastapi import receive_logout
        await receive_logout(request, service.sdk, service.links.apply_verified_logout)
        return {'ok': True}
