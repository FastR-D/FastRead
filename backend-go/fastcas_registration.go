package fastread

import (
	"database/sql"
	"encoding/json"
	"net/http"

	fastcas "github.com/FastR-D/FastCAS/sdk/go"
)

const registrationRequired = "registration_required"

func (c *casService) pending(binding string, prepared bool) (Row, error) {
	row, e := c.app.Store.One("SELECT * FROM fastcas_signups WHERE binding_hash=? AND issuer=? AND expires>?", TokenHash(binding), c.config.Issuer, Now())
	if e != nil || binding == "" || (Str(row["prepared"]) != "") != prepared {
		return nil, Error(401, "FastCAS 验证已过期，请重新登录")
	}
	return row, nil
}
func (c *casService) registrationRoutes() {
	c.app.Public("GET /api/auth/fastcas/registration", func(w http.ResponseWriter, r *http.Request) error {
		if e := c.enabled(); e != nil {
			return e
		}
		row, e := c.pending(Cookie(r, "fastread_fastcas_binding"), false)
		if e == nil {
			JSON(w, 200, Row{"email": row["email"], "display_name": row["display_name"]})
		}
		return e
	})
	c.app.Public("POST /api/auth/fastcas/registration", func(w http.ResponseWriter, r *http.Request) error {
		if e := c.origin(r); e != nil {
			return e
		}
		if !c.login || !c.link {
			return Error(403, "新的账号认证已关闭")
		}
		if e := c.app.preAuth(r); e != nil {
			return e
		}
		if e := c.app.Store.RateLimit("cas-registration", Peer(r)); e != nil {
			return e
		}
		pending, e := c.pending(Cookie(r, "fastread_fastcas_binding"), false)
		if e != nil {
			return e
		}
		var d accountInput
		if e = Decode(r, &d); e != nil {
			return e
		}
		u, e := prepareAccount(d)
		if e != nil {
			return e
		}
		if _, e = c.app.Store.One("SELECT id FROM users WHERE email=?", u.Email); e == nil {
			return Error(409, "此邮箱已有账号，请登录后绑定 FastCAS")
		} else if e != sql.ErrNoRows {
			return e
		}
		binding := Token()
		target, e := c.sdk.BeginRegistration(r.Context(), u.ID, fastcas.BeginOptions{BrowserBinding: binding})
		if e != nil {
			return casError(e)
		}
		res, e := c.app.Store.DB.Exec("UPDATE fastcas_signups SET binding_hash=?,prepared=? WHERE binding_hash=? AND prepared IS NULL AND expires>?", TokenHash(binding), Encode(u), pending["binding_hash"], Now())
		if e != nil {
			return e
		}
		n, _ := res.RowsAffected()
		if n != 1 {
			return Error(401, "请重新使用 FastCAS 登录")
		}
		c.cookie(w, binding, 300)
		JSON(w, 200, Row{"url": target})
		return nil
	})
}
func (c *casService) finishRegistration(r *http.Request, result *fastcas.LoginResult) (string, error) {
	if !c.login || !c.link {
		return "", Error(403, "新的账号认证已关闭")
	}
	pending, e := c.pending(Cookie(r, "fastread_fastcas_binding"), true)
	if e != nil {
		return "", e
	}
	var u preparedAccount
	if e = json.Unmarshal([]byte(Str(pending["prepared"])), &u); e != nil {
		return "", e
	}
	if result.Identity.Issuer != c.config.Issuer || result.Identity.Subject != Str(pending["subject"]) || result.Transaction.LocalAccountRef != u.ID {
		return "", Error(401, "FastCAS 身份已改变，请重新登录")
	}
	l, e := c.sdk.PrepareLink(r.Context(), result)
	if e != nil {
		return "", e
	}
	if l.LocalRef != u.ID || l.Subject != result.Identity.Subject {
		return "", Error(403, "认证关系不匹配")
	}
	e = c.app.Store.Transaction(func(tx *sql.Tx) error {
		if e := insertAccount(tx, u, false, false); e != nil {
			return e
		}
		if e := c.save(tx, l); e != nil {
			return e
		}
		_, e := tx.Exec("DELETE FROM fastcas_signups WHERE binding_hash=?", pending["binding_hash"])
		return e
	})
	if e != nil {
		return "", e
	}
	l, e = c.sdk.ActivateLink(r.Context(), l.ID)
	if e != nil {
		return "", e
	}
	if e = c.accept(l); e != nil {
		return "", e
	}
	return c.issueCAS(l, result)
}
func promoteCASAdmin(tx *sql.Tx, id string, identity fastcas.Identity) error {
	if identity.Role != "admin" {
		return nil
	}
	_, e := tx.Exec("UPDATE users SET is_admin=1 WHERE id=? AND disabled=0 AND deleted=0", id)
	return e
}
