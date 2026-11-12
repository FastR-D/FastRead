package fastread

import (
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"database/sql"
	"encoding/base64"
	"encoding/hex"
	"golang.org/x/crypto/scrypt"
	"net"
	"net/http"
	"os"
	"regexp"
	"strings"
)

func Token() string {
	b := make([]byte, 32)
	if _, e := rand.Read(b); e != nil {
		panic(e)
	}
	return base64.RawURLEncoding.EncodeToString(b)
}
func TokenHash(token string) string {
	h := sha256.Sum256([]byte(token))
	return hex.EncodeToString(h[:])
}
func PasswordHash(password string) (string, error) {
	salt := make([]byte, 16)
	if _, e := rand.Read(salt); e != nil {
		return "", e
	}
	key, e := scrypt.Key([]byte(password), salt, 16384, 8, 1, 64)
	if e != nil {
		return "", e
	}
	return "scrypt$" + hex.EncodeToString(salt) + "$" + hex.EncodeToString(key), nil
}
func PasswordMatches(password, stored string) bool {
	parts := strings.Split(stored, "$")
	if len(parts) != 3 || parts[0] != "scrypt" {
		return false
	}
	salt, e := hex.DecodeString(parts[1])
	if e != nil {
		return false
	}
	want, e := hex.DecodeString(parts[2])
	if e != nil || len(want) != 64 {
		return false
	}
	key, e := scrypt.Key([]byte(password), salt, 16384, 8, 1, 64)
	return e == nil && subtle.ConstantTimeCompare(key, want) == 1
}
func SecureCookie() bool { return strings.ToLower(os.Getenv("FASTREAD_COOKIE_SECURE")) != "false" }
func AdminEmail(email string) bool {
	for _, value := range strings.Split(os.Getenv("FASTREAD_ADMIN_EMAILS"), ",") {
		if value != "" && strings.EqualFold(strings.TrimSpace(value), email) {
			return true
		}
	}
	return false
}
func (a *App) SetSessionCookie(w http.ResponseWriter, token string) {
	http.SetCookie(w, &http.Cookie{Name: "fastread_session", Value: token, Path: "/", HttpOnly: true, Secure: SecureCookie(), SameSite: http.SameSiteLaxMode, MaxAge: 7 * 86400})
}
func Cookie(r *http.Request, name string) string {
	c, e := r.Cookie(name)
	if e != nil {
		return ""
	}
	return c.Value
}
func Peer(r *http.Request) string {
	p, _, e := net.SplitHostPort(r.RemoteAddr)
	if e != nil {
		return r.RemoteAddr
	}
	return p
}
func (s *Store) IssueSession(user, workspace, source string) (string, string, error) {
	token, csrf := Token(), Token()
	_, e := s.DB.Exec("INSERT INTO sessions(token,user_id,workspace_id,csrf,expires,auth_source,authenticated_at) VALUES(?,?,?,?,?,?,?)", TokenHash(token), user, workspace, csrf, Now()+7*86400, source, Now())
	return token, csrf, e
}
func (a *App) RequireUser(r *http.Request) (Principal, error) {
	row, e := a.Store.One("SELECT s.*,u.email,u.display_name,u.research_key_id,u.research_account_id,u.is_admin,u.disabled,m.role FROM sessions s JOIN users u ON u.id=s.user_id JOIN memberships m ON m.user_id=s.user_id AND m.workspace_id=s.workspace_id WHERE s.token=? AND s.expires>?", TokenHash(Cookie(r, "fastread_session")), Now())
	if e != nil || Num(row["disabled"]) != 0 {
		return Principal{}, Error(401, "请先登录")
	}
	if Str(row["auth_source"]) == "fastcas" {
		if a.ValidateCASSession == nil {
			return Principal{}, Error(401, "请重新进行 CAS 认证")
		}
		if e = a.ValidateCASSession(row); e != nil {
			return Principal{}, e
		}
	}
	if r.Method != "GET" && r.Method != "HEAD" && r.Method != "OPTIONS" && subtle.ConstantTimeCompare([]byte(r.Header.Get("X-CSRF-Token")), []byte(Str(row["csrf"]))) != 1 {
		return Principal{}, Error(403, "请求校验失败，请刷新后重试")
	}
	admin := Num(row["is_admin"]) == 1 || AdminEmail(Str(row["email"]))
	return Principal{UserID: Str(row["user_id"]), WorkspaceID: Str(row["workspace_id"]), Email: Str(row["email"]), Role: Str(row["role"]), CSRF: Str(row["csrf"]), DisplayName: Str(row["display_name"]), ResearchKeyID: Str(row["research_key_id"]), ResearchAccountID: Str(row["research_account_id"]), IsAdmin: admin}, nil
}
func NormalizeEmail(s string) (string, error) {
	s = strings.ToLower(strings.TrimSpace(s))
	if len(s) > 254 || !regexp.MustCompile(`^[^\s@]+@[^\s@]+\.[^\s@]+$`).MatchString(s) || strings.HasSuffix(s, "@sso.fastresearch.local") || strings.HasSuffix(s, "@identity.invalid") {
		return "", Error(422, "请输入有效邮箱")
	}
	return s, nil
}
func ValidatePassword(p string) error {
	if len([]rune(p)) < 12 || len([]rune(p)) > 256 {
		return Error(422, "密码需要 12–256 个字符")
	}
	return nil
}
func (s *Store) CreateUser(email, password, workspace, display string, admin bool) (Row, error) {
	email, e := NormalizeEmail(email)
	if e != nil {
		return nil, e
	}
	if e = ValidatePassword(password); e != nil {
		return nil, e
	}
	hash, e := PasswordHash(password)
	if e != nil {
		return nil, e
	}
	id, wid := UID(), UID()
	if workspace == "" {
		workspace = "我的资料库"
	}
	e = s.Transaction(func(tx *sql.Tx) error {
		if _, e := tx.Exec("INSERT INTO users(id,email,password,created,display_name,is_admin) VALUES(?,?,?,?,?,?)", id, email, hash, Now(), display, admin); e != nil {
			return Error(409, "账号已存在")
		}
		if _, e := tx.Exec("INSERT INTO workspaces(id,name) VALUES(?,?)", wid, workspace); e != nil {
			return e
		}
		_, e := tx.Exec("INSERT INTO memberships VALUES(?,?,'owner')", id, wid)
		return e
	})
	return Row{"user_id": id, "workspace_id": wid, "email": email}, e
}
func (a *App) preAuth(r *http.Request) error {
	cookie := Cookie(r, "fastread_preauth")
	if len(cookie) < 32 || subtle.ConstantTimeCompare([]byte(cookie), []byte(r.Header.Get("X-CSRF-Token"))) != 1 {
		return Error(403, "请刷新登录页面后重试")
	}
	return nil
}
func (s *Store) RateLimit(action, peer string) error {
	key := TokenHash("account-action:" + action + ":" + peer)
	limited := false
	e := s.Transaction(func(tx *sql.Tx) error {
		row, _ := One(tx, "SELECT * FROM login_attempts WHERE key=?", key)
		failures, until := 1, Now()+900
		if Num(row["until"]) > Now() {
			failures = int(Num(row["failures"])) + 1
			until = Num(row["until"])
		}
		_, e := tx.Exec("INSERT OR REPLACE INTO login_attempts VALUES(?,?,?)", key, failures, until)
		limited = failures > 12
		return e
	})
	if e != nil {
		return e
	}
	if limited {
		return Error(429, "操作过于频繁，请稍后重试")
	}
	return nil
}
func (a *App) RegisterAuth() {
	a.Public("GET /api/auth/session-init", func(w http.ResponseWriter, r *http.Request) error {
		token := Token()
		http.SetCookie(w, &http.Cookie{Name: "fastread_preauth", Value: token, Path: "/", HttpOnly: true, Secure: SecureCookie(), SameSite: http.SameSiteStrictMode, MaxAge: 1800})
		JSON(w, 200, Row{"csrf": token})
		return nil
	})
	a.Public("GET /api/auth/login-info", func(w http.ResponseWriter, r *http.Request) error {
		panel := os.Getenv("FASTRESEARCH_PANEL_URL")
		if panel == "" {
			panel = "http://127.0.0.1:5173"
		}
		JSON(w, 200, Row{"mode": "local", "local": true, "registration": "invite", "panel_url": panel})
		return nil
	})
	a.Public("POST /api/auth/login", func(w http.ResponseWriter, r *http.Request) error {
		if e := a.preAuth(r); e != nil {
			return e
		}
		var d struct{ Email, Password string }
		if e := Decode(r, &d); e != nil {
			return e
		}
		email := strings.ToLower(strings.TrimSpace(d.Email))
		key := TokenHash(email + "|" + Peer(r))
		attempt, _ := a.Store.One("SELECT * FROM login_attempts WHERE key=?", key)
		if Num(attempt["until"]) > Now() && Num(attempt["failures"]) >= 8 {
			return Error(429, "登录尝试过多，请稍后重试")
		}
		u, e := a.Store.One("SELECT * FROM users WHERE email=?", email)
		if e != nil || Num(u["disabled"]) != 0 || !PasswordMatches(d.Password, Str(u["password"])) {
			fail := 1
			if Num(attempt["until"]) > Now() {
				fail += int(Num(attempt["failures"]))
			}
			_, _ = a.Store.DB.Exec("INSERT OR REPLACE INTO login_attempts VALUES(?,?,?)", key, fail, Now()+900)
			return Error(401, "邮箱或密码错误")
		}
		m, e := a.Store.One("SELECT workspace_id FROM memberships WHERE user_id=? ORDER BY workspace_id LIMIT 1", u["id"])
		if e != nil {
			return e
		}
		token, csrf, e := a.Store.IssueSession(Str(u["id"]), Str(m["workspace_id"]), "local")
		if e != nil {
			return e
		}
		_, _ = a.Store.DB.Exec("DELETE FROM login_attempts WHERE key=?", key)
		a.SetSessionCookie(w, token)
		JSON(w, 200, Row{"csrf": csrf})
		return nil
	})
	a.Handle("GET /api/auth/me", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		ws, e := a.Store.One("SELECT name,daily_limit FROM workspaces WHERE id=?", p.WorkspaceID)
		if e != nil {
			return e
		}
		JSON(w, 200, Row{"id": p.UserID, "email": p.Email, "workspace_id": p.WorkspaceID, "role": p.Role, "csrf": p.CSRF, "workspace": ws, "public": os.Getenv("FASTREAD_PUBLIC_WORKSPACE") != "", "research_key_id": p.ResearchKeyID, "research_account_id": p.ResearchAccountID, "display_name": p.DisplayName, "is_admin": p.IsAdmin})
		return nil
	})
	a.Handle("POST /api/auth/logout", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		_, e := a.Store.DB.Exec("DELETE FROM sessions WHERE token=?", TokenHash(Cookie(r, "fastread_session")))
		http.SetCookie(w, &http.Cookie{Name: "fastread_session", Path: "/", MaxAge: -1, HttpOnly: true, Secure: SecureCookie()})
		if e == nil {
			JSON(w, 200, Row{"ok": true})
		}
		return e
	})
	for _, kind := range []string{"invite", "recovery"} {
		kind := kind
		path := "register"
		if kind == "recovery" {
			path = "recover"
		}
		a.Public("POST /api/auth/"+path, func(w http.ResponseWriter, r *http.Request) error {
			if e := a.preAuth(r); e != nil {
				return e
			}
			if e := a.Store.RateLimit(kind, Peer(r)); e != nil {
				return e
			}
			var d struct{ Token, Password string }
			if e := Decode(r, &d); e != nil {
				return e
			}
			if e := a.Store.RedeemCredential(kind, d.Token, d.Password); e != nil {
				return e
			}
			JSON(w, 200, Row{"ok": true})
			return nil
		})
	}
	a.Handle("POST /api/auth/local-credential", a.localCredential)
}
