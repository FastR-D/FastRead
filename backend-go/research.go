package fastread

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"io"
	"net/http"
	"os"
	"path"
	"strings"
	"time"
)

func (s *Store) LoginFromResearch(ctx context.Context, ticket string) (string, string, error) {
	ticket = strings.TrimSpace(ticket)
	if ticket == "" || len(ticket) > 256 {
		return "", "", Error(401, "登录票据无效或已过期")
	}
	base := strings.TrimRight(os.Getenv("FASTRESEARCH_API_URL"), "/")
	if base == "" {
		base = "http://127.0.0.1:8787"
	}
	req, e := http.NewRequestWithContext(ctx, "POST", base+"/api/sso/consume", bytes.NewBufferString(Encode(Row{"ticket": ticket, "audience": "fast-read"})))
	if e != nil {
		return "", "", e
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	client := &http.Client{Timeout: 5 * time.Second}
	res, e := client.Do(req)
	if e != nil {
		return "", "", Error(503, "无法连接 FastResearch")
	}
	defer res.Body.Close()
	if res.StatusCode < 200 || res.StatusCode >= 300 {
		return "", "", Error(401, "登录票据无效或已过期")
	}
	var identity Row
	if e = json.NewDecoder(io.LimitReader(res.Body, 1<<20)).Decode(&identity); e != nil {
		return "", "", Error(503, "FastResearch 响应无效")
	}
	key, account := strings.TrimSpace(Str(identity["keyId"])), strings.TrimSpace(Str(identity["accountId"]))
	person := []rune(strings.TrimSpace(Str(identity["person"])))
	if len(person) > 80 {
		person = person[:80]
	}
	name := string(person)
	if key == "" {
		return "", "", Error(401, "登录票据无效或已过期")
	}
	if name == "" {
		name = key
	}
	email := "key-" + key + "@sso.fastresearch.local"
	token, csrf := Token(), Token()
	e = s.Transaction(func(tx *sql.Tx) error {
		var user Row
		if account != "" {
			user, _ = One(tx, "SELECT * FROM users WHERE research_account_id=?", account)
		}
		if user == nil {
			user, _ = One(tx, "SELECT * FROM users WHERE research_key_id=?", key)
		}
		if user != nil && account != "" && Str(user["research_account_id"]) != "" && Str(user["research_account_id"]) != account {
			return Error(409, "Research 账号绑定不一致")
		}
		if user == nil {
			user, _ = One(tx, "SELECT * FROM users WHERE email=?", email)
		}
		id := UID()
		if user != nil {
			if Num(user["disabled"]) != 0 {
				return Error(403, "账号已停用")
			}
			id = Str(user["id"])
			if strings.HasPrefix(Str(user["password"]), "scrypt$") {
				email = Str(user["email"])
			}
			if _, e := tx.Exec("UPDATE users SET display_name=?,email=?,research_key_id=? WHERE id=?", name, email, key, id); e != nil {
				return e
			}
		} else {
			if _, e := tx.Exec("INSERT INTO users(id,email,password,created,research_key_id,display_name) VALUES(?,?,'disabled',?,?,?)", id, email, Now(), key, name); e != nil {
				return e
			}
		}
		if account != "" {
			if _, e := tx.Exec("UPDATE users SET research_account_id=? WHERE id=?", account, id); e != nil {
				return e
			}
		}
		owner, _ := One(tx, "SELECT workspace_id FROM memberships WHERE user_id=? AND role='owner' ORDER BY workspace_id LIMIT 1", id)
		ws := UID()
		if owner != nil {
			ws = Str(owner["workspace_id"])
			if _, e := tx.Exec("UPDATE workspaces SET name=? WHERE id=?", name, ws); e != nil {
				return e
			}
		} else {
			if _, e := tx.Exec("INSERT INTO workspaces(id,name) VALUES(?,?)", ws, name); e != nil {
				return e
			}
			if _, e := tx.Exec("INSERT INTO memberships VALUES(?,?,'owner')", id, ws); e != nil {
				return e
			}
		}
		if _, e := tx.Exec("DELETE FROM sessions WHERE user_id=? AND auth_source IN ('research','legacy')", id); e != nil {
			return e
		}
		_, e := tx.Exec("INSERT INTO sessions(token,user_id,workspace_id,csrf,expires,auth_source,authenticated_at) VALUES(?,?,?,?,?,'research',?)", TokenHash(token), id, ws, csrf, Now()+7*86400, Now())
		return e
	})
	return token, csrf, e
}
func (a *App) RegisterResearch() {
	a.Public("POST /api/auth/research", func(w http.ResponseWriter, r *http.Request) error {
		var d struct{ Ticket string }
		if e := Decode(r, &d); e != nil {
			return e
		}
		token, csrf, e := a.Store.LoginFromResearch(r.Context(), d.Ticket)
		if e != nil {
			return e
		}
		a.SetSessionCookie(w, token)
		JSON(w, 200, Row{"csrf": csrf})
		return nil
	})
}
func (a *App) ResearchDocument(w http.ResponseWriter, r *http.Request) bool {
	if r.Method != "GET" || r.URL.Query().Get("sso") == "" || strings.HasPrefix(r.URL.Path, "/api/") {
		return false
	}
	extension := strings.ToLower(path.Ext(r.URL.Path))
	if extension != "" && extension != ".html" && extension != ".htm" {
		return false
	}
	token, _, e := a.Store.LoginFromResearch(r.Context(), r.URL.Query().Get("sso"))
	if e != nil {
		return false
	}
	a.SetSessionCookie(w, token)
	q := r.URL.Query()
	q.Del("sso")
	target := r.URL.Path
	if q.Encode() != "" {
		target += "?" + q.Encode()
	}
	w.Header().Set("Cache-Control", "no-store")
	http.Redirect(w, r, target, http.StatusFound)
	return true
}
