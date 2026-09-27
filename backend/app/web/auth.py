from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import time
from dataclasses import dataclass

import httpx
from fastapi import HTTPException, Request

from .store import Store, uid

RESEARCH_AUDIENCE = "fast-read"
SSO_EXPIRED = "Panel 登录已过期，请从 FastResearch 重新进入"
_KEY_ID_RE = re.compile(r"^[0-9a-f]{8,64}$")
_ACCOUNT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f"scrypt${salt}${value}"


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def research_placeholder_email(key_id: str) -> str:
    return f"key-{key_id}@sso.fastresearch.local"


@dataclass(frozen=True)
class Principal:
    user_id: str
    workspace_id: str
    email: str
    role: str
    csrf: str
    display_name: str = ""
    research_key_id: str | None = None
    research_account_id: str | None = None


def create_user(store: Store, email, password, workspace_name="我的资料库"):
    if len(password) < 12 or len(password) > 256:
        raise ValueError("密码需要 12–256 个字符")
    email = email.strip().lower()
    if "@" not in email or len(email) > 254:
        raise ValueError("请输入有效邮箱")
    user, workspace = uid(), uid()
    with store.connect(write=True) as db:
        db.execute(
            "INSERT INTO users(id,email,password,created,display_name) VALUES(?,?,?,?,?)",
            (user, email, password_hash(password), time.time(), workspace_name),
        )
        db.execute("INSERT INTO workspaces(id,name) VALUES(?,?)", (workspace, workspace_name))
        db.execute("INSERT INTO memberships VALUES(?,?,'owner')", (user, workspace))
    return {"user_id": user, "workspace_id": workspace, "email": email, "display_name": workspace_name}


def issue_session(store: Store, user_id: str, workspace_id: str):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    with store.connect(write=True) as db:
        db.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
        db.execute(
            "INSERT INTO sessions VALUES(?,?,?,?,?)",
            (token_hash(token), user_id, workspace_id, csrf, time.time() + 7 * 86400),
        )
    return token, csrf


def research_api_url() -> str:
    return os.environ.get("FASTRESEARCH_API_URL", "http://127.0.0.1:8787").strip().rstrip("/")


def consume_research_ticket(ticket: str) -> dict:
    base = research_api_url()
    if not base:
        raise HTTPException(503, "未配置 FastResearch 地址")
    try:
        response = httpx.post(
            f"{base}/api/sso/consume",
            json={"ticket": ticket, "audience": RESEARCH_AUDIENCE},
            timeout=5,
            trust_env=False,
        )
    except httpx.HTTPError:
        raise HTTPException(503, "无法连接 FastResearch，请稍后重试") from None
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.status_code != 200:
        raise HTTPException(401, SSO_EXPIRED)
    key_id = str(payload.get("keyId") or "").strip().lower()
    account_id = str(payload.get("accountId") or "").strip()
    person = str(payload.get("person") or "").strip()[:80]
    if not _KEY_ID_RE.fullmatch(key_id):
        raise HTTPException(401, SSO_EXPIRED)
    if account_id and not _ACCOUNT_ID_RE.fullmatch(account_id):
        raise HTTPException(401, SSO_EXPIRED)
    identity = {"key_id": key_id, "person": person or "未命名成员"}
    if account_id:
        identity["account_id"] = account_id
    return identity


def upsert_research_user(store: Store, key_id: str, person: str, account_id: str | None = None):
    email = research_placeholder_email(key_id)
    with store.connect(write=True) as db:
        user = None
        if account_id:
            user = db.execute("SELECT * FROM users WHERE research_account_id=?", (account_id,)).fetchone()
        if user is None:
            user = db.execute("SELECT * FROM users WHERE research_key_id=?", (key_id,)).fetchone()
        if user:
            member = db.execute(
                "SELECT * FROM memberships WHERE user_id=? ORDER BY workspace_id LIMIT 1",
                (user["id"],),
            ).fetchone()
            if not member:
                raise RuntimeError("research user has no workspace")
            # New tickets identify the stable account. Upgrade an old key-only
            # row when it is the first login observed for that account.
            if account_id and not user["research_account_id"]:
                db.execute("UPDATE users SET research_account_id=? WHERE id=?", (account_id, user["id"]))
            db.execute("UPDATE users SET display_name=? WHERE id=?", (person, user["id"]))
            db.execute("UPDATE workspaces SET name=? WHERE id=?", (person, member["workspace_id"]))
            return {
                "user_id": user["id"],
                "workspace_id": member["workspace_id"],
                "email": user["email"],
                "display_name": person,
                "research_key_id": key_id,
                "research_account_id": account_id or user["research_account_id"],
            }
        user_id, workspace_id = uid(), uid()
        db.execute(
            "INSERT INTO users(id,email,password,created,research_key_id,research_account_id,display_name) VALUES(?,?,?,?,?,?,?)",
            (user_id, email, password_hash(secrets.token_urlsafe(32)), time.time(), key_id, account_id, person),
        )
        db.execute("INSERT INTO workspaces(id,name) VALUES(?,?)", (workspace_id, person))
        db.execute("INSERT INTO memberships VALUES(?,?,'owner')", (user_id, workspace_id))
        return {
            "user_id": user_id,
            "workspace_id": workspace_id,
            "email": email,
            "display_name": person,
            "research_key_id": key_id,
            "research_account_id": account_id,
        }


def login_from_research(store: Store, ticket: str, peer: str):
    # FastResearch tickets are 192-bit one-time values. Counting consume 401s
    # toward an IP lockout blocks loopback SSO (Vite, TestClient, and the
    # browser all look like 127.0.0.1). FastNews does not rate-limit this path.
    del peer
    ticket = (ticket or "").strip()
    if not ticket or len(ticket) > 256:
        raise HTTPException(401, SSO_EXPIRED)
    identity = consume_research_ticket(ticket)
    user = upsert_research_user(store, identity["key_id"], identity["person"], identity.get("account_id"))
    return issue_session(store, user["user_id"], user["workspace_id"])


def require_user(request: Request) -> Principal:
    token = request.cookies.get("fastread_session", "")
    store = request.app.state.store
    row = store.one(
        """SELECT s.*,u.email,COALESCE(u.display_name,'') AS display_name,
        u.research_key_id,u.research_account_id,m.role
        FROM sessions s JOIN users u ON u.id=s.user_id
        JOIN memberships m ON m.user_id=s.user_id AND m.workspace_id=s.workspace_id
        WHERE s.token=? AND s.expires>?""",
        (token_hash(token), time.time()),
    )
    if not row:
        raise HTTPException(401, "请先登录")
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
        row["display_name"] or "",
        row["research_key_id"],
        row["research_account_id"],
    )


def require_owner(principal):
    if principal.role != "owner":
        raise HTTPException(403, "需要工作区管理员权限")


def secure_cookie():
    return os.environ.get("FASTREAD_COOKIE_SECURE", "true").lower() == "true"


def set_session_cookie(response, token):
    response.set_cookie(
        "fastread_session",
        token,
        httponly=True,
        secure=secure_cookie(),
        samesite="lax",
        max_age=7 * 86400,
        path="/",
    )
