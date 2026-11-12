package fastread

import (
	"database/sql"
	"net/http"
	"strings"
)

func (s *Store) IssueCredential(kind, email string) (string, error) {
	email, e := NormalizeEmail(email)
	if e != nil {
		return "", e
	}
	if kind != "invite" && kind != "recovery" {
		return "", Error(422, "凭证类型无效")
	}
	token := Token()
	e = s.Transaction(func(tx *sql.Tx) error {
		u, _ := One(tx, "SELECT id,password FROM users WHERE email=?", email)
		if kind == "invite" && u != nil {
			return Error(409, "账号已存在")
		}
		if kind == "recovery" && (u == nil || !strings.HasPrefix(Str(u["password"]), "scrypt$")) {
			return Error(409, "账号尚未设置本地密码")
		}
		_, e := tx.Exec("UPDATE account_credentials SET consumed=? WHERE kind=? AND email=? AND consumed IS NULL", Now(), kind, email)
		if e != nil {
			return e
		}
		_, e = tx.Exec("INSERT INTO account_credentials VALUES(?,?,?,?,?,NULL)", TokenHash(token), kind, email, u["id"], Now()+3600)
		return e
	})
	return token, e
}
func (s *Store) RedeemCredential(kind, token, password string) error {
	if e := ValidatePassword(password); e != nil {
		return e
	}
	if len(token) < 32 || len(token) > 256 {
		return Error(400, "凭证无效或已过期")
	}
	hash, e := PasswordHash(password)
	if e != nil {
		return e
	}
	return s.Transaction(func(tx *sql.Tx) error {
		row, e := One(tx, "SELECT * FROM account_credentials WHERE token_hash=? AND kind=? AND consumed IS NULL AND expires>?", TokenHash(token), kind, Now())
		if e != nil {
			return Error(400, "凭证无效或已过期")
		}
		user := Str(row["user_id"])
		if kind == "invite" {
			user = UID()
			ws := UID()
			if _, e = tx.Exec("INSERT INTO users(id,email,password,created) VALUES(?,?,?,?)", user, row["email"], hash, Now()); e != nil {
				return Error(409, "账号已存在，请使用登录或恢复入口")
			}
			if _, e = tx.Exec("INSERT INTO workspaces(id,name) VALUES(?,?)", ws, "我的资料库"); e != nil {
				return e
			}
			_, e = tx.Exec("INSERT INTO memberships VALUES(?,?,'owner')", user, ws)
		} else {
			res, x := tx.Exec("UPDATE users SET password=? WHERE id=? AND email=? AND password LIKE 'scrypt$%'", hash, user, row["email"])
			if x != nil {
				return x
			}
			n, _ := res.RowsAffected()
			if n != 1 {
				return Error(400, "凭证无效或已过期")
			}
			_, e = tx.Exec("DELETE FROM sessions WHERE user_id=?", user)
		}
		if e != nil {
			return e
		}
		if _, e = tx.Exec("UPDATE account_credentials SET consumed=? WHERE token_hash=?", Now(), TokenHash(token)); e != nil {
			return e
		}
		_, e = tx.Exec("INSERT INTO account_audit VALUES(?,?,?,?)", UID(), user, "account."+kind, Now())
		return e
	})
}
func (a *App) localCredential(w http.ResponseWriter, r *http.Request, p Principal) error {
	if e := a.Store.RateLimit("set-local-credential", Peer(r)); e != nil {
		return e
	}
	var d struct {
		Email, Password string
		CurrentPassword string `json:"current_password"`
	}
	if e := Decode(r, &d); e != nil {
		return e
	}
	email, e := NormalizeEmail(d.Email)
	if e != nil {
		return e
	}
	if e = ValidatePassword(d.Password); e != nil {
		return e
	}
	hash, e := PasswordHash(d.Password)
	if e != nil {
		return e
	}
	e = a.Store.Transaction(func(tx *sql.Tx) error {
		row, e := One(tx, "SELECT s.*,u.password,u.research_key_id FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>?", TokenHash(Cookie(r, "fastread_session")), Now())
		if e != nil {
			return e
		}
		proved := PasswordMatches(d.CurrentPassword, Str(row["password"]))
		if !strings.HasPrefix(Str(row["password"]), "scrypt$") {
			proved = Str(row["research_key_id"]) != "" && Str(row["auth_source"]) == "research" && Num(row["authenticated_at"]) >= Now()-300
		}
		if !proved {
			return Error(403, "请验证原密码；Research 账号请从原入口重新登录后在五分钟内设置")
		}
		if _, e = tx.Exec("UPDATE users SET email=?,password=? WHERE id=?", email, hash, p.UserID); e != nil {
			return Error(409, "邮箱不可用，请使用其他邮箱")
		}
		_, e = tx.Exec("DELETE FROM sessions WHERE user_id=? AND token!=?", p.UserID, row["token"])
		return e
	})
	if e == nil {
		JSON(w, 200, Row{"ok": true})
	}
	return e
}
