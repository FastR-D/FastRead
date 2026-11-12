package fastread

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	fastcas "github.com/FastR-D/FastCAS/sdk/go"
)

type casTransactions struct{ s *Store }

func (t casTransactions) Put(ctx context.Context, value fastcas.Transaction) error {
	_, err := t.s.DB.ExecContext(ctx, "INSERT INTO fastcas_transactions(state,payload,expires) VALUES(?,?,?)", value.State, Encode(value), float64(value.ExpiresAt.Unix()))
	return err
}
func (t casTransactions) Take(ctx context.Context, state string) (*fastcas.Transaction, error) {
	var result *fastcas.Transaction
	err := t.s.Transaction(func(tx *sql.Tx) error {
		row, err := One(tx, "SELECT payload FROM fastcas_transactions WHERE state=?", state)
		if errors.Is(err, sql.ErrNoRows) {
			return nil
		}
		if err != nil {
			return err
		}
		if _, err = tx.ExecContext(ctx, "DELETE FROM fastcas_transactions WHERE state=?", state); err != nil {
			return err
		}
		var value fastcas.Transaction
		if err = json.Unmarshal([]byte(Str(row["payload"])), &value); err != nil {
			return err
		}
		result = &value
		return nil
	})
	return result, err
}

type casService struct {
	app              *App
	sdk              *fastcas.Client
	config           fastcas.Config
	login, link      bool
	base, cookiePath string
}

func (a *App) RegisterFastCAS() error {
	c := &casService{app: a, config: fastcas.Config{Issuer: os.Getenv("FASTREAD_FASTCAS_ISSUER"), ClientID: os.Getenv("FASTREAD_FASTCAS_CLIENT_ID"), ClientSecret: os.Getenv("FASTREAD_FASTCAS_CLIENT_SECRET"), RedirectURI: os.Getenv("FASTREAD_FASTCAS_REDIRECT_URI"), AllowLoopbackHTTP: os.Getenv("FASTREAD_FASTCAS_ALLOW_LOOPBACK_HTTP") == "true"}, login: os.Getenv("FASTREAD_FASTCAS_LOGIN_ENABLED") != "false", link: os.Getenv("FASTREAD_FASTCAS_LINK_ENABLED") != "false"}
	count := 0
	for _, v := range []string{c.config.Issuer, c.config.ClientID, c.config.ClientSecret, c.config.RedirectURI} {
		if v != "" {
			count++
		}
	}
	if count != 0 && count != 4 {
		return errors.New("FastCAS requires issuer, client ID, client secret and redirect URI together")
	}
	if count == 4 {
		var err error
		c.sdk, err = fastcas.New(c.config, casTransactions{a.Store})
		if err != nil {
			return err
		}
	}
	c.base = strings.TrimRight(os.Getenv("FASTREAD_BASE_PATH"), "/")
	if c.base == "" {
		u, _ := url.Parse(c.config.RedirectURI)
		if u != nil {
			c.base = strings.TrimSuffix(u.Path, "/api/auth/fastcas/callback")
		}
	}
	c.cookiePath = c.base + "/api/auth/fastcas"
	a.ValidateCASSession = c.validateSession
	a.Public("GET /api/auth/fastcas/available", func(w http.ResponseWriter, r *http.Request) error {
		JSON(w, 200, Row{"enabled": c.sdk != nil, "login_enabled": c.sdk != nil && c.login, "link_enabled": c.sdk != nil && c.link})
		return nil
	})
	a.Public("GET /api/auth/fastcas/login", func(w http.ResponseWriter, r *http.Request) error {
		if e := c.enabled(); e != nil {
			return e
		}
		if !c.login {
			return Error(403, "此实例已关闭 FastCAS 登录")
		}
		binding := Token()
		target, e := c.sdk.BeginLogin(r.Context(), fastcas.BeginOptions{BrowserBinding: binding})
		if e != nil {
			return casError(e)
		}
		c.cookie(w, binding, 300)
		http.Redirect(w, r, target, 302)
		return nil
	})
	a.Handle("POST /api/auth/fastcas/link", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		if e := c.origin(r); e != nil {
			return e
		}
		if !c.link {
			return Error(403, "此实例已关闭新的 FastCAS 认证")
		}
		if e := c.prove(r, p); e != nil {
			return e
		}
		binding := Token()
		target, e := c.sdk.BeginLink(r.Context(), fastcas.BeginOptions{BrowserBinding: binding, LocalAccountRef: p.UserID, LocalSessionID: TokenHash(Cookie(r, "fastread_session"))})
		if e != nil {
			return casError(e)
		}
		c.cookie(w, binding, 300)
		JSON(w, 200, Row{"url": target})
		return nil
	})
	a.Public("GET /api/auth/fastcas/callback", func(w http.ResponseWriter, r *http.Request) error {
		if e := c.enabled(); e != nil {
			return e
		}
		token, e := c.finish(r)
		c.cookie(w, "", -1)
		w.Header().Set("Referrer-Policy", "no-referrer")
		target := c.base + "/?fastcas=failed"
		if e == nil {
			target = c.base + "/?fastcas=complete"
			if token != "" {
				a.SetSessionCookie(w, token)
			}
		}
		http.Redirect(w, r, target, 302)
		return nil
	})
	a.Handle("GET /api/auth/fastcas/status", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		var link any
		row, e := c.current(p.UserID)
		if e == nil {
			link = Row{"id": row["id"], "subject": row["subject"], "state": row["state"], "version": row["version"]}
		}
		JSON(w, 200, Row{"enabled": c.sdk != nil, "login_enabled": c.sdk != nil && c.login, "link_enabled": c.sdk != nil && c.link, "link": link})
		return nil
	})
	a.Handle("POST /api/auth/fastcas/reconcile", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		if e := c.origin(r); e != nil {
			return e
		}
		row, e := c.current(p.UserID)
		if e != nil {
			return Error(404, "没有待完成的认证")
		}
		if e = c.reconcile(r.Context(), row); e != nil {
			return casError(e)
		}
		JSON(w, 200, Row{"ok": true})
		return nil
	})
	a.Handle("POST /api/auth/fastcas/revoke", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		if e := c.origin(r); e != nil {
			return e
		}
		if e := c.prove(r, p); e != nil {
			return e
		}
		row, e := c.current(p.UserID)
		if e == nil {
			remote, err := c.sdk.GetLink(r.Context(), Str(row["id"]))
			if err != nil {
				return casError(err)
			}
			if !sameLink(row, remote) {
				return Error(403, "FastCAS 认证关系不匹配")
			}
			if remote.State != "revoked" {
				remote, err = c.sdk.RevokeLink(r.Context(), remote)
				if err != nil {
					return casError(err)
				}
			}
			if err = c.accept(remote); err != nil {
				return err
			}
		} else if !errors.Is(e, sql.ErrNoRows) {
			return e
		}
		JSON(w, 200, Row{"ok": true})
		return nil
	})
	a.Public("POST /api/auth/fastcas/events", c.events)
	a.Public("POST /api/auth/fastcas/backchannel-logout", c.logout)
	return nil
}
func casError(err error) error {
	var api *fastcas.APIError
	if errors.As(err, &api) {
		switch api.Status {
		case 400, 401, 403, 409, 429:
			return Error(api.Status, "FastCAS 请求未完成，请重试或使用本地登录")
		}
	}
	return Error(502, "FastCAS 请求未完成，请重试或使用本地登录")
}
func (c *casService) enabled() error {
	if c.sdk == nil {
		return Error(404, "未启用 FastCAS")
	}
	return nil
}
func (c *casService) origin(r *http.Request) error {
	if e := c.enabled(); e != nil {
		return e
	}
	u, _ := url.Parse(c.config.RedirectURI)
	if r.Header.Get("Origin") != u.Scheme+"://"+u.Host {
		return Error(403, "不允许跨站请求")
	}
	return nil
}
func (c *casService) cookie(w http.ResponseWriter, value string, age int) {
	http.SetCookie(w, &http.Cookie{Name: "fastread_fastcas_binding", Value: value, Path: c.cookiePath, HttpOnly: true, Secure: SecureCookie(), SameSite: http.SameSiteLaxMode, MaxAge: age})
}
func (c *casService) current(user string) (Row, error) {
	return c.app.Store.One("SELECT * FROM fastcas_links WHERE issuer=? AND client_id=? AND user_id=? AND state!='revoked'", c.config.Issuer, c.config.ClientID, user)
}
func (c *casService) prove(r *http.Request, p Principal) error {
	if e := c.app.Store.RateLimit("fastcas-proof", Peer(r)); e != nil {
		return e
	}
	var body struct{ Password string }
	if e := Decode(r, &body); e != nil {
		return e
	}
	u, e := c.app.Store.One("SELECT password FROM users WHERE id=?", p.UserID)
	if e != nil || !PasswordMatches(body.Password, Str(u["password"])) {
		return Error(403, "请确认当前账号的本地密码")
	}
	return nil
}
func sameLink(row Row, l *fastcas.Link) bool {
	return Str(row["id"]) == l.ID && Str(row["subject"]) == l.Subject && Str(row["user_id"]) == l.LocalRef && Str(row["client_id"]) == l.ClientID
}
func (c *casService) save(tx *sql.Tx, l *fastcas.Link) error {
	if l.ClientID != c.config.ClientID || l.ID == "" || l.Subject == "" || l.LocalRef == "" || l.Version < 1 || (l.State != "active" && l.State != "prepared" && l.State != "revoked") {
		return Error(403, "FastCAS 认证关系无效")
	}
	old, e := One(tx, "SELECT * FROM fastcas_links WHERE issuer=? AND id=?", c.config.Issuer, l.ID)
	if e == nil {
		if !sameLink(old, l) {
			return Error(403, "FastCAS 认证关系不匹配")
		}
		if Num(old["version"]) >= float64(l.Version) || Str(old["state"]) == "revoked" {
			return nil
		}
	} else if !errors.Is(e, sql.ErrNoRows) {
		return e
	}
	_, e = tx.Exec("INSERT INTO fastcas_links(issuer,id,client_id,user_id,subject,state,version,payload) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(issuer,id) DO UPDATE SET state=excluded.state,version=excluded.version,payload=excluded.payload", c.config.Issuer, l.ID, l.ClientID, l.LocalRef, l.Subject, l.State, l.Version, Encode(l))
	return e
}
func (c *casService) accept(l *fastcas.Link) error {
	return c.app.Store.Transaction(func(tx *sql.Tx) error {
		if e := c.save(tx, l); e != nil {
			return e
		}
		if l.State == "revoked" {
			_, e := tx.Exec("DELETE FROM sessions WHERE auth_source='fastcas' AND cas_issuer=? AND cas_link_id=? AND cas_link_version<=?", c.config.Issuer, l.ID, l.Version)
			return e
		}
		row, e := One(tx, "SELECT state,version FROM fastcas_links WHERE issuer=? AND id=?", c.config.Issuer, l.ID)
		if e != nil {
			return e
		}
		if Str(row["state"]) != l.State || Num(row["version"]) != float64(l.Version) {
			return Error(409, "认证状态已改变，请刷新后重试")
		}
		return nil
	})
}
func (c *casService) reconcile(ctx context.Context, row Row) error {
	l, e := c.sdk.GetLink(ctx, Str(row["id"]))
	if e != nil {
		return e
	}
	if !sameLink(row, l) {
		return Error(403, "FastCAS 认证关系不匹配")
	}
	if l.State == "prepared" {
		l, e = c.sdk.ActivateLink(ctx, l.ID)
		if e != nil {
			return e
		}
	}
	return c.accept(l)
}
func (c *casService) finish(r *http.Request) (string, error) {
	s := c.app.Store
	session, _ := s.One("SELECT * FROM sessions WHERE token=? AND expires>?", TokenHash(Cookie(r, "fastread_session")), Now())
	result, e := c.sdk.FinishLogin(r.Context(), strings.Split(c.config.RedirectURI, "?")[0]+"?"+r.URL.RawQuery, fastcas.FinishOptions{BrowserBinding: Cookie(r, "fastread_fastcas_binding"), LocalAccountRef: Str(session["user_id"]), LocalSessionID: Str(session["token"])})
	if e != nil {
		return "", e
	}
	if result.Transaction.Purpose == "link" {
		if !c.link {
			return "", Error(403, "新的认证已关闭")
		}
		l, e := c.sdk.PrepareLink(r.Context(), result)
		if e != nil {
			return "", e
		}
		e = s.Transaction(func(tx *sql.Tx) error {
			live, e := One(tx, "SELECT user_id FROM sessions WHERE token=? AND expires>?", session["token"], Now())
			if e != nil || Str(live["user_id"]) != l.LocalRef {
				return Error(403, "原登录会话已失效")
			}
			return c.save(tx, l)
		})
		if e != nil {
			return "", e
		}
		l, e = c.sdk.ActivateLink(r.Context(), l.ID)
		if e != nil {
			return "", e
		}
		return "", c.accept(l)
	}
	if !c.login || result.Transaction.Purpose != "login" {
		return "", Error(403, "请使用本地登录")
	}
	row, e := s.One("SELECT * FROM fastcas_links WHERE issuer=? AND client_id=? AND subject=? AND state!='revoked'", c.config.Issuer, c.config.ClientID, result.Identity.Subject)
	if e != nil {
		return "", Error(409, "请先登录项目并关联 CAS 账号")
	}
	if Str(row["state"]) == "prepared" {
		if e = c.reconcile(r.Context(), row); e != nil {
			return "", e
		}
	}
	l, e := c.sdk.ResolveLink(r.Context(), result.Identity.Subject)
	if e != nil {
		return "", e
	}
	if l.State != "active" || result.Identity.Issuer != c.config.Issuer || result.Identity.Subject != l.Subject {
		return "", Error(403, "FastCAS 认证关系无效")
	}
	token := Token()
	e = s.Transaction(func(tx *sql.Tx) error {
		row, e := One(tx, "SELECT * FROM fastcas_links WHERE issuer=? AND id=?", c.config.Issuer, l.ID)
		if e != nil || !sameLink(row, l) || Str(row["state"]) != "active" || Num(row["version"]) != float64(l.Version) {
			return Error(403, "认证关系已更改")
		}
		member, e := One(tx, "SELECT m.workspace_id FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.user_id=? AND u.disabled=0 ORDER BY workspace_id LIMIT 1", l.LocalRef)
		if e != nil {
			return Error(403, "项目账号不可用")
		}
		_, e = tx.Exec("INSERT INTO sessions(token,user_id,workspace_id,csrf,expires,auth_source,authenticated_at,cas_issuer,cas_sid,cas_link_id,cas_link_version,cas_checked) VALUES(?,?,?,?,?,'fastcas',?,?,?,?,?,?)", TokenHash(token), l.LocalRef, member["workspace_id"], Token(), Now()+7*86400, Now(), c.config.Issuer, result.Identity.SessionID, l.ID, l.Version, Now())
		return e
	})
	return token, e
}
func (c *casService) validateSession(session Row) error {
	if c.sdk == nil || Str(session["cas_issuer"]) != c.config.Issuer {
		return Error(401, "请使用本地登录")
	}
	row, e := c.current(Str(session["user_id"]))
	if e != nil || Str(row["state"]) != "active" || row["id"] != session["cas_link_id"] || Num(row["version"]) != Num(session["cas_link_version"]) {
		return Error(401, "CAS 认证已撤销，请重新登录")
	}
	if Num(session["cas_checked"])+300 > Now() {
		return nil
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	l, e := c.sdk.ResolveLink(ctx, Str(row["subject"]))
	if e != nil || !sameLink(row, l) || l.State != "active" || float64(l.Version) != Num(row["version"]) {
		return Error(401, "请重新登录确认 CAS 认证")
	}
	res, e := c.app.Store.DB.Exec("UPDATE sessions SET cas_checked=? WHERE token=? AND expires>? AND EXISTS(SELECT 1 FROM fastcas_links l WHERE l.issuer=sessions.cas_issuer AND l.id=sessions.cas_link_id AND l.client_id=? AND l.state='active' AND l.version=sessions.cas_link_version AND l.user_id=sessions.user_id)", Now(), session["token"], Now(), c.config.ClientID)
	if e != nil {
		return e
	}
	n, _ := res.RowsAffected()
	if n != 1 {
		return Error(401, "会话已失效")
	}
	return nil
}
func (c *casService) notification(event fastcas.Notification) error {
	return c.app.Store.Transaction(func(tx *sql.Tx) error {
		if _, e := One(tx, "SELECT id FROM fastcas_events WHERE issuer=? AND id=?", c.config.Issuer, event.ID); e == nil {
			return nil
		}
		if event.Type == "account_link.revoked" {
			l := event.Link
			if _, e := One(tx, "SELECT id FROM users WHERE id=?", l.LocalRef); e == nil {
				if e = c.save(tx, l); e != nil {
					return e
				}
				if _, e = tx.Exec("DELETE FROM sessions WHERE auth_source='fastcas' AND cas_issuer=? AND cas_link_id=? AND cas_link_version<=?", c.config.Issuer, l.ID, l.Version); e != nil {
					return e
				}
			}
		} else if event.Status == "disabled" {
			if _, e := tx.Exec("DELETE FROM sessions WHERE auth_source='fastcas' AND cas_issuer=? AND cas_link_id IN (SELECT id FROM fastcas_links WHERE issuer=? AND client_id=? AND subject=?)", c.config.Issuer, c.config.Issuer, c.config.ClientID, event.Subject); e != nil {
				return e
			}
		}
		_, e := tx.Exec("INSERT INTO fastcas_events VALUES(?,?,?)", c.config.Issuer, event.ID, Now())
		return e
	})
}
func (c *casService) events(w http.ResponseWriter, r *http.Request) error {
	if e := c.enabled(); e != nil {
		return e
	}
	if strings.Split(r.Header.Get("Content-Type"), ";")[0] != "application/jwt" {
		return Error(415, "需要签名事件")
	}
	raw, e := io.ReadAll(http.MaxBytesReader(w, r.Body, 65536))
	if e != nil {
		return Error(413, "事件过大")
	}
	var commit error
	e = c.sdk.HandleNotification(r.Context(), string(raw), func(_ context.Context, event fastcas.Notification) error {
		commit = c.notification(event)
		return commit
	})
	if commit != nil {
		return Error(503, "事件暂未保存")
	}
	if e != nil {
		return Error(401, "签名事件无效")
	}
	JSON(w, 200, Row{"ok": true})
	return nil
}
func (c *casService) logout(w http.ResponseWriter, r *http.Request) error {
	if e := c.enabled(); e != nil {
		return e
	}
	if strings.Split(r.Header.Get("Content-Type"), ";")[0] != "application/x-www-form-urlencoded" {
		return Error(415, "需要退出令牌")
	}
	r.Body = http.MaxBytesReader(w, r.Body, 65536)
	if e := r.ParseForm(); e != nil {
		return Error(400, "退出请求无效")
	}
	notice, e := c.sdk.VerifyLogout(r.Context(), r.Form.Get("logout_token"))
	if e != nil {
		return Error(401, "退出令牌无效")
	}
	e = c.app.Store.Transaction(func(tx *sql.Tx) error {
		if _, e := One(tx, "SELECT id FROM fastcas_events WHERE issuer=? AND id=?", c.config.Issuer, notice.ID); e == nil {
			return nil
		}
		if _, e := tx.Exec("DELETE FROM sessions WHERE auth_source='fastcas' AND cas_issuer=? AND cas_link_id IN (SELECT id FROM fastcas_links WHERE issuer=? AND client_id=? AND subject=?) AND (?='' OR cas_sid=?)", c.config.Issuer, c.config.Issuer, c.config.ClientID, notice.Subject, notice.SessionID, notice.SessionID); e != nil {
			return e
		}
		_, e := tx.Exec("INSERT INTO fastcas_events VALUES(?,?,?)", c.config.Issuer, notice.ID, Now())
		return e
	})
	if e != nil {
		return Error(503, "退出通知暂未保存")
	}
	JSON(w, 200, Row{"ok": true})
	return nil
}
