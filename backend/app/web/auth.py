from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from fastapi import HTTPException, Request

from .store import Store, uid

AUDIENCE = "fast-read"
SSO_EMAIL_DOMAIN = "sso.fastresearch.local"


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f"scrypt${salt}${value}"


def password_matches(password, stored):
    try:
        return hmac.compare_digest(password_hash(password, stored.split("$")[1]), stored)
    except (ValueError, IndexError):
        return False


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def research_api_url() -> str:
    return os.environ.get("FASTRESEARCH_API_URL", "http://127.0.0.1:8787").strip().rstrip("/")


def panel_url() -> str:
    return os.environ.get("FASTRESEARCH_PANEL_URL", "http://127.0.0.1:5173").strip().rstrip("/") or "http://127.0.0.1:5173"


def public_workspace_id() -> str:
    return os.environ.get("FASTREAD_PUBLIC_WORKSPACE", "").strip()


@dataclass(frozen=True)
class Principal:
    user_id: str
    workspace_id: str
    email: str
    role: str
    csrf: str
    research_key_id: str = ""
    display_name: str = ""
    research_account_id: str = ""


def create_user(store: Store, email, password, workspace_name="我的资料库"):
    if len(password) < 12 or len(password) > 256:
        raise ValueError("密码需要 12–256 个字符")
    email = email.strip().lower()
    if "@" not in email or len(email) > 254:
        raise ValueError("请输入有效邮箱")
    user, workspace = uid(), uid()
    with store.connect(write=True) as db:
        db.execute(
            "INSERT INTO users(id,email,password,created) VALUES(?,?,?,?)",
            (user, email, password_hash(password), time.time()),
        )
        db.execute("INSERT INTO workspaces(id,name) VALUES(?,?)", (workspace, workspace_name))
        db.execute("INSERT INTO memberships VALUES(?,?,'owner')", (user, workspace))
    return {"user_id": user, "workspace_id": workspace, "email": email}


def login(store: Store, email, password, peer):
    email = email.strip().lower()
    # Fixed window by account and connection peer; never trust an arbitrary forwarded IP.
    key = token_hash(email + "|" + peer)
    with store.connect(write=True) as db:
        row = db.execute("SELECT * FROM login_attempts WHERE key=?", (key,)).fetchone()
        if row and row["until"] > time.time() and row["failures"] >= 8:
            raise HTTPException(429, "登录尝试过多，请稍后重试")
        user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        good = password_matches(password, user["password"] if user else password_hash("nonexistent-account"))
        if not user or not good:
            failures = row["failures"] + 1 if row and row["until"] > time.time() else 1
            db.execute("INSERT OR REPLACE INTO login_attempts VALUES(?,?,?)", (key, failures, time.time() + 900))
        else:
            db.execute("DELETE FROM login_attempts WHERE key=?", (key,))
            member = db.execute(
                "SELECT * FROM memberships WHERE user_id=? ORDER BY workspace_id LIMIT 1",
                (user["id"],),
            ).fetchone()
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
            db.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
            db.execute(
                "INSERT INTO sessions(token,user_id,workspace_id,csrf,expires,auth_source,authenticated_at) VALUES(?,?,?,?,?,?,?)",
                (token_hash(token), user["id"], member["workspace_id"], csrf, time.time() + 7 * 86400, "local", time.time()),
            )
            return token, csrf
    raise HTTPException(401, "邮箱或密码错误")


def research_json(method: str, path: str, payload: dict | None = None, timeout: float = 5):
    url = f"{research_api_url()}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8") or "{}"
            return json.loads(raw), response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace") or "{}"
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {}
        detail = str(body.get("error") or body.get("detail") or "登录票据无效或已过期")
        raise HTTPException(exc.code if exc.code in {400, 401, 403, 404} else 401, detail) from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HTTPException(503, "无法连接 FastResearch") from exc


def consume_research_ticket(ticket: str) -> dict:
    ticket = (ticket or "").strip()
    if not ticket or len(ticket) > 256:
        raise HTTPException(401, "登录票据无效或已过期")
    payload, _status = research_json(
        "POST",
        "/api/sso/consume",
        {"ticket": ticket, "audience": AUDIENCE},
    )
    key_id = str(payload.get("keyId") or "").strip()
    person = str(payload.get("person") or "").strip()
    if not key_id:
        raise HTTPException(401, "登录票据无效或已过期")
    return {"keyId": key_id, "person": person[:80], "accountId": str(payload.get("accountId") or "").strip()}


def _issue_session(db, user_id: str, workspace_id: str):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    db.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
    db.execute(
        "INSERT INTO sessions(token,user_id,workspace_id,csrf,expires,auth_source,authenticated_at) VALUES(?,?,?,?,?,?,?)",
        (token_hash(token), user_id, workspace_id, csrf, time.time() + 7 * 86400, "research", time.time()),
    )
    return token, csrf


def login_from_research(store: Store, ticket: str):
    identity = consume_research_ticket(ticket)
    key_id = identity["keyId"]
    person = identity["person"] or key_id
    account_id = identity.get("accountId") or None
    email = f"key-{key_id}@{SSO_EMAIL_DOMAIN}"
    with store.connect(write=True) as db:
        user = db.execute("SELECT * FROM users WHERE research_account_id=?", (account_id,)).fetchone() if account_id else None
        if user is None:
            user = db.execute("SELECT * FROM users WHERE research_key_id=?", (key_id,)).fetchone()
        if user and account_id and user["research_account_id"] not in (None, "", account_id):
            raise HTTPException(409, "Research 账号绑定不一致")
        if not user:
            user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user:
            user_id = user["id"]
            db.execute(
                "UPDATE users SET display_name=?, email=?, research_key_id=? WHERE id=?",
                (person, user["email"] if user["password"].startswith("scrypt$") else email, key_id, user_id),
            )
        else:
            user_id = uid()
            db.execute(
                "INSERT INTO users(id,email,password,created,research_key_id,display_name) VALUES(?,?,?,?,?,?)",
                (user_id, email, "disabled", time.time(), key_id, person),
            )
        if account_id:
            db.execute("UPDATE users SET research_account_id=? WHERE id=?", (account_id, user_id))
        owner = db.execute(
            "SELECT * FROM memberships WHERE user_id=? AND role='owner' ORDER BY workspace_id LIMIT 1",
            (user_id,),
        ).fetchone()
        if owner:
            workspace_id = owner["workspace_id"]
            db.execute("UPDATE workspaces SET name=? WHERE id=?", (person, workspace_id))
        else:
            workspace_id = uid()
            db.execute("INSERT INTO workspaces(id,name) VALUES(?,?)", (workspace_id, person))
            db.execute("INSERT INTO memberships VALUES(?,?,'owner')", (user_id, workspace_id))
        db.execute("DELETE FROM sessions WHERE user_id=? AND auth_source IN ('research','legacy')", (user_id,))
        return _issue_session(db, user_id, workspace_id)


def session_exists(store: Store, token: str) -> bool:
    token = (token or "").strip()
    if not token:
        return False
    return bool(
        store.one(
            "SELECT token FROM sessions WHERE token=? AND expires>?",
            (token_hash(token), time.time()),
        )
    )


def require_user(request: Request) -> Principal:
    if getattr(request.state, "public_principal", None):
        return request.state.public_principal
    token = request.cookies.get("fastread_session", "")
    store = request.app.state.store
    row = store.one(
        """SELECT s.*,u.email,u.research_key_id,u.display_name,u.research_account_id,m.role FROM sessions s JOIN users u ON u.id=s.user_id
        JOIN memberships m ON m.user_id=s.user_id AND m.workspace_id=s.workspace_id WHERE s.token=? AND s.expires>?""",
        (token_hash(token), time.time()),
    )
    if not row:
        raise HTTPException(401, "请先登录")
    if row["auth_source"] == "fastcas":
        request.app.state.fastcas.validate_session(row)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(csrf, row["csrf"]):
            raise HTTPException(403, "请求校验失败，请刷新后重试")
    return Principal(
        row["user_id"],
        row["workspace_id"],
        row["email"],
        row["role"],
        row["csrf"],
        row.get("research_key_id") or "",
        row.get("display_name") or "",
        row.get("research_account_id") or "",
    )


def require_owner(principal):
    if principal.role != "owner":
        raise HTTPException(403, "需要工作区管理员权限")


def secure_cookie():
    return os.environ.get("FASTREAD_COOKIE_SECURE", "true").lower() == "true"


def public_session(request, response, store):
    """Kept for compatibility; SSO login is the only public entry."""
    workspace = public_workspace_id()
    if not workspace or not store.one("SELECT id FROM workspaces WHERE id=?", (workspace,)):
        raise HTTPException(503, "共享资料库尚未配置")
    try:
        current = require_user(request)
        if current.workspace_id == workspace:
            return
    except HTTPException:
        pass
    raise HTTPException(401, "请先登录")
