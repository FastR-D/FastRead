from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request

from .store import Store, uid


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


@dataclass(frozen=True)
class Principal:
    user_id: str
    workspace_id: str
    email: str
    role: str
    csrf: str


def create_user(store: Store, email, password, workspace_name="我的资料库"):
    if len(password) < 12 or len(password) > 256:
        raise ValueError("密码需要 12–256 个字符")
    email = email.strip().lower()
    if "@" not in email or len(email) > 254:
        raise ValueError("请输入有效邮箱")
    user, workspace = uid(), uid()
    with store.connect(write=True) as db:
        db.execute("INSERT INTO users VALUES(?,?,?,?)", (user, email, password_hash(password), time.time()))
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
            member = db.execute("SELECT * FROM memberships WHERE user_id=? ORDER BY workspace_id LIMIT 1", (user["id"],)).fetchone()
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
            db.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
            db.execute("INSERT INTO sessions VALUES(?,?,?,?,?)", (token_hash(token), user["id"], member["workspace_id"], csrf, time.time() + 7 * 86400))
            return token, csrf
    raise HTTPException(401, "邮箱或密码错误")


def require_user(request: Request) -> Principal:
    token = request.cookies.get("fastread_session", "")
    store = request.app.state.store
    row = store.one("""SELECT s.*,u.email,m.role FROM sessions s JOIN users u ON u.id=s.user_id
        JOIN memberships m ON m.user_id=s.user_id AND m.workspace_id=s.workspace_id WHERE s.token=? AND s.expires>?""",
                    (token_hash(token), time.time()))
    if not row:
        raise HTTPException(401, "请先登录")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(csrf, row["csrf"]):
            raise HTTPException(403, "请求校验失败，请刷新后重试")
    return Principal(row["user_id"], row["workspace_id"], row["email"], row["role"], row["csrf"])


def require_owner(principal):
    if principal.role != "owner":
        raise HTTPException(403, "需要工作区管理员权限")


def secure_cookie():
    return os.environ.get("FASTREAD_COOKIE_SECURE", "true").lower() == "true"
