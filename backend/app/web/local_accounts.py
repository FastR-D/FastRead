"""Local account provisioning and one-time recovery, independent of any IdP."""
from __future__ import annotations

import hmac
import re
import secrets
import sqlite3
import time

from fastapi import HTTPException, Request

from .auth import SSO_EMAIL_DOMAIN, password_hash, token_hash
from .store import Store, uid


def normalize_email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        raise ValueError("请输入有效邮箱")
    if value.endswith("@" + SSO_EMAIL_DOMAIN) or value.endswith("@identity.invalid"):
        raise ValueError("此地址仅用于外部身份，请先通过原登录方式证明账号")
    return value


def require_pre_auth(request: Request) -> None:
    cookie = request.cookies.get("fastread_preauth", "")
    header = request.headers.get("x-csrf-token", "")
    if len(cookie) < 32 or not hmac.compare_digest(cookie, header):
        raise HTTPException(403, "请刷新登录页面后重试")


def rate_limit(store: Store, action: str, peer: str) -> None:
    key = token_hash("account-action:" + action + ":" + peer)
    now = time.time()
    with store.connect(write=True) as db:
        row = db.execute("SELECT * FROM login_attempts WHERE key=?", (key,)).fetchone()
        failures = row["failures"] + 1 if row and row["until"] > now else 1
        until = row["until"] if row and row["until"] > now else now + 900
        db.execute("INSERT OR REPLACE INTO login_attempts VALUES(?,?,?)", (key, failures, until))
    if failures > 12:
        raise HTTPException(429, "操作过于频繁，请稍后重试")


def issue_credential(store: Store, kind: str, email: str) -> str:
    """Offline operator command only. Never exposed to ordinary workspace owners."""
    email = normalize_email(email)
    if kind not in {"invite", "recovery"}:
        raise ValueError("凭证类型无效")
    raw = secrets.token_urlsafe(32)
    now = time.time()
    with store.connect(write=True) as db:
        user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if kind == "invite" and user:
            raise ValueError("账号已存在")
        if kind == "recovery" and (not user or not user["password"].startswith("scrypt$")):
            raise ValueError("需要已设置本地密码的账号；外部账号请先通过原登录方式证明身份")
        user_id = user["id"] if user else None
        db.execute("UPDATE account_credentials SET consumed=? WHERE kind=? AND email=? AND consumed IS NULL", (now, kind, email))
        db.execute("INSERT INTO account_credentials VALUES(?,?,?,?,?,NULL)", (token_hash(raw), kind, email, user_id, now + 3600))
        db.execute("INSERT INTO account_audit VALUES(?,?,?,?)", (uid(), user_id, "operator.issue." + kind, now))
    return raw


def redeem_credential(store: Store, kind: str, raw: str, password: str) -> dict:
    if not 12 <= len(password) <= 256:
        raise ValueError("密码需要 12–256 个字符")
    if not 32 <= len(raw) <= 256:
        raise HTTPException(400, "凭证无效或已过期")
    # Hash outside the SQLite write lock. Single-use consumption and all identity
    # changes still commit together below, including concurrent redemption.
    encoded = password_hash(password)
    now = time.time()
    try:
        with store.connect(write=True) as db:
            token = db.execute("SELECT * FROM account_credentials WHERE token_hash=? AND kind=? AND consumed IS NULL AND expires>?", (token_hash(raw), kind, now)).fetchone()
            if not token:
                raise HTTPException(400, "凭证无效或已过期")
            if kind == "invite":
                user_id, workspace_id = uid(), uid()
                db.execute("INSERT INTO users(id,email,password,created) VALUES(?,?,?,?)", (user_id, token["email"], encoded, now))
                db.execute("INSERT INTO workspaces(id,name) VALUES(?,?)", (workspace_id, "我的资料库"))
                db.execute("INSERT INTO memberships VALUES(?,?,'owner')", (user_id, workspace_id))
            elif kind == "recovery":
                user_id = token["user_id"]
                changed = db.execute("UPDATE users SET password=? WHERE id=? AND email=? AND password LIKE 'scrypt$%'", (encoded, user_id, token["email"]))
                if changed.rowcount != 1:
                    raise HTTPException(400, "凭证无效或已过期")
                db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            else:
                raise ValueError("凭证类型无效")
            db.execute("UPDATE account_credentials SET consumed=? WHERE token_hash=?", (now, token_hash(raw)))
            db.execute("INSERT INTO account_audit VALUES(?,?,?,?)", (uid(), user_id, "account." + kind, now))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "账号已存在，请使用登录或恢复入口") from None
    return {"ok": True}


def set_local_credential(store: Store, raw_session: str, email: str, password: str, current_password: str):
    """Prove an existing password or a freshly consumed Research ticket session."""
    from .auth import password_matches
    email = normalize_email(email)
    if not 12 <= len(password) <= 256:
        raise HTTPException(400, '密码需要 12–256 个字符')
    encoded, now = password_hash(password), time.time()
    try:
        with store.connect(write=True) as db:
            row = db.execute('''SELECT s.*,u.password,u.research_key_id FROM sessions s JOIN users u ON u.id=s.user_id
                WHERE s.token=? AND s.expires>?''', (token_hash(raw_session), now)).fetchone()
            if not row:
                raise HTTPException(401, '请先登录')
            if row['password'].startswith('scrypt$'):
                proved = password_matches(current_password, row['password'])
            else:
                proved = bool(row['research_key_id'] and row['auth_source'] == 'research' and row['authenticated_at'] and now-300 <= row['authenticated_at'] <= now)
            if not proved:
                raise HTTPException(403, '请验证原密码；Research 账号请从原入口重新登录后在五分钟内设置')
            db.execute('UPDATE users SET email=?,password=? WHERE id=?', (email, encoded, row['user_id']))
            # Credential change invalidates other sessions, but preserves this
            # browser and its original login source rather than minting a new one.
            db.execute('DELETE FROM sessions WHERE user_id=? AND token!=?', (row['user_id'], row['token']))
            db.execute('INSERT INTO account_audit VALUES(?,?,?,?)', (uid(), row['user_id'], 'account.set_local_credential', now))
    except sqlite3.IntegrityError:
        raise HTTPException(409, '邮箱不可用，请使用其他邮箱或登录原账号') from None
    return {'ok': True}
