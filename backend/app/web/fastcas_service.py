"""Optional identity provider. Local authentication never calls this service."""
import json
import os
import secrets
import time
from threading import Lock

from fastapi import HTTPException

from .auth import password_matches, token_hash
from .fastcas_store import FastCASLinks, FastCASTransactions
from .local_accounts import rate_limit


class FastCASService:
    def __init__(self, store, sdk=None):
        self.store, self._sdk, self._lock = store, sdk, Lock()
        fields = ['ISSUER', 'CLIENT_ID', 'CLIENT_SECRET', 'REDIRECT_URI']
        self.config = {key.lower(): os.environ.get('FASTREAD_FASTCAS_' + key, '').strip() for key in fields}
        if sdk is not None:
            self.config.update(issuer=sdk.config.issuer, client_id=sdk.config.client_id, redirect_uri=sdk.config.redirect_uri)
        elif any(self.config.values()) and not all(self.config.values()):
            raise ValueError('FastCAS requires issuer, client ID, client secret and redirect URI together')
        self.enabled = sdk is not None or all(self.config.values())
        self.links = FastCASLinks(store, self.config['issuer'], self.config['client_id'])

    @property
    def sdk(self):
        if not self.enabled:
            raise HTTPException(404, '未启用 FastCAS')
        with self._lock:
            if self._sdk is None:
                from fastcas import Configuration, FastCAS
                self._sdk = FastCAS(Configuration(**self.config, allow_loopback_http=os.environ.get('FASTREAD_FASTCAS_ALLOW_LOOPBACK_HTTP') == 'true'), FastCASTransactions(self.store))
        return self._sdk

    def session(self, raw):
        return self.store.one('SELECT * FROM sessions WHERE token=? AND expires>?', (token_hash(raw), time.time()))

    def prove(self, raw, password, peer):
        rate_limit(self.store, 'fastcas-proof', peer)
        session = self.session(raw)
        user = self.store.one('SELECT * FROM users WHERE id=?', (session['user_id'],)) if session else None
        if not user or not password_matches(password, user['password']):
            raise HTTPException(403, '请确认当前账号的本地密码')
        return session

    def begin_link(self, binding, raw, password, peer):
        session = self.prove(raw, password, peer)
        return self.sdk.begin_link(binding, local_account_ref=session['user_id'], local_session_id=session['token'])

    def current(self, user_id):
        return self.store.one("SELECT * FROM fastcas_links WHERE issuer=? AND client_id=? AND user_id=? AND state!='revoked'", (self.config['issuer'], self.config['client_id'], user_id))

    def reconcile(self, row):
        remote = self.sdk.get_link(row['id'])
        if any(remote[k] != json.loads(row['payload'])[k] for k in ('id','subject','local_account_ref','client_id')):
            raise HTTPException(403, 'FastCAS 认证关系不匹配')
        if remote['state'] == 'prepared':
            remote = self.sdk.activate_link(row['id'])
        self._accept_remote(remote)
        return remote

    def _accept_remote(self, remote):
        if remote['state'] == 'revoked':
            self.links.apply_verified_event(dict(id='reconcile:'+remote['id']+':'+str(remote['version']), type='account_link.revoked', link=remote))
        else:
            self.links.save(remote)
        persisted = self.store.one('SELECT state,version FROM fastcas_links WHERE issuer=? AND id=?', (self.config['issuer'], remote['id']))
        if not persisted or persisted['state'] != remote['state'] or persisted['version'] != remote['version']:
            raise HTTPException(409, '认证状态已改变，请刷新后重试')

    def finish(self, callback, binding, raw):
        session = self.session(raw)
        result = self.sdk.finish_login(callback, binding, local_account_ref=session['user_id'] if session else '', local_session_id=session['token'] if session else '')
        if result['transaction']['purpose'] == 'link':
            link = self.sdk.prepare_link(result)
            # Recheck the original session after network calls and before committing.
            with self.store.connect(write=True) as db:
                live = db.execute('SELECT user_id FROM sessions WHERE token=? AND expires>?', (session['token'], time.time())).fetchone() if session else None
                if not live or live['user_id'] != link['local_account_ref']:
                    raise HTTPException(403, '原登录会话已失效，请重新认证')
                self.links._save(db, link)
            self._accept_remote(self.sdk.activate_link(link['id']))
            return None
        if result['transaction']['purpose'] != 'login':
            raise HTTPException(403, '请先通过项目邀请注册本地账号')
        identity = result['identity']
        row = self.store.one("SELECT * FROM fastcas_links WHERE issuer=? AND client_id=? AND subject=? AND state!='revoked'", (self.config['issuer'], self.config['client_id'], identity['subject']))
        if not row:
            raise HTTPException(409, '此身份尚未关联账号，请先使用项目原方式登录并认证')
        if row['state'] == 'prepared':
            self.reconcile(row)
        link = self.sdk.resolve_link(identity['subject'])
        return self._login(link, identity)

    def _login(self, link, identity):
        self.links._validate(link)
        if identity['issuer'] != self.config['issuer'] or identity['subject'] != link['subject'] or link['state'] != 'active':
            raise HTTPException(403, 'FastCAS 认证关系无效')
        with self.store.connect(write=True) as db:
            row = db.execute('SELECT * FROM fastcas_links WHERE issuer=? AND id=?', (self.config['issuer'], link['id'])).fetchone()
            if not row or row['state'] != 'active' or row['version'] != link['version'] or row['user_id'] != link['local_account_ref'] or row['subject'] != identity['subject']:
                raise HTTPException(403, 'FastCAS 认证关系已更改')
            member = db.execute('SELECT m.* FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.user_id=? ORDER BY workspace_id LIMIT 1', (row['user_id'],)).fetchone()
            if not member:
                raise HTTPException(403, '项目账号不可用')
            token, csrf, now = secrets.token_urlsafe(32), secrets.token_urlsafe(24), time.time()
            db.execute('''INSERT INTO sessions(token,user_id,workspace_id,csrf,expires,auth_source,authenticated_at,cas_issuer,cas_sid,cas_link_id,cas_link_version,cas_checked)
                VALUES(?,?,?,?,?,'fastcas',?,?,?,?,?,?)''', (token_hash(token), row['user_id'], member['workspace_id'], csrf, now+7*86400, now, self.config['issuer'], identity.get('sid'), link['id'], link['version'], now))
            return token

    def revoke(self, raw, password, peer):
        session = self.prove(raw, password, peer)
        row = self.current(session['user_id'])
        if not row:
            return
        # A previous response can be lost after remote commit. Read current
        # state before retrying instead of permanently retrying a stale version.
        remote = self.sdk.get_link(row['id'])
        if any(remote[k] != json.loads(row['payload'])[k] for k in ('id','subject','local_account_ref','client_id')):
            raise HTTPException(403, 'FastCAS 认证关系不匹配')
        link = remote if remote['state'] == 'revoked' else self.sdk.revoke_link(remote)
        self.links.apply_verified_event(dict(id='local-revoke:'+link['id']+':'+str(link['version']), type='account_link.revoked', link=link))

    def validate_session(self, session):
        if not self.enabled or session['cas_issuer'] != self.config['issuer']:
            raise HTTPException(401, 'FastCAS 登录不可用，请使用本地登录')
        row = self.current(session['user_id'])
        if not row or row['state'] != 'active' or row['id'] != session['cas_link_id'] or row['version'] != session['cas_link_version']:
            raise HTTPException(401, 'FastCAS 认证已撤销，请重新登录')
        if (session.get('cas_checked') or 0) + 300 > time.time():
            return
        try:
            remote = self.sdk.resolve_link(row['subject'])
        except Exception:
            raise HTTPException(401, '无法确认 FastCAS 认证，请使用本地登录') from None
        if any(remote[key] != json.loads(row['payload'])[key] for key in ('id','state','version','subject','local_account_ref','client_id')):
            raise HTTPException(401, 'FastCAS 认证关系已更改')
        with self.store.connect(write=True) as db:
            # No session recreation; a concurrent event deletion remains effective.
            updated = db.execute("""UPDATE sessions SET cas_checked=? WHERE token=? AND expires>?
                AND EXISTS(SELECT 1 FROM fastcas_links l WHERE l.issuer=sessions.cas_issuer
                AND l.id=sessions.cas_link_id AND l.client_id=? AND l.state='active'
                AND l.version=sessions.cas_link_version AND l.user_id=sessions.user_id)""",
                (time.time(), session['token'], time.time(), self.config['client_id']))
            if not updated.rowcount:
                raise HTTPException(401, '会话已失效')
