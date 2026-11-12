package fastread

import (
	"database/sql"
	fastcas "github.com/FastR-D/FastCAS/sdk/go"
	"strings"
	"testing"
)

func TestAccountAdministrationLifecycle(t *testing.T) {
	s := testStore(t)
	admin, token := testUser(t, s, "admin@example.org", true)
	a := NewApp(s)
	d := Row{"email": "member@example.org", "display_name": "Member", "password": "initial-password-long", "role": "user", "reason": "Onboarding"}
	w := call(a, "POST", "/api/admin/users", token, admin.CSRF, d)
	if w.Code != 201 {
		t.Fatal(w.Code, w.Body.String())
	}
	id := Str(decodeResponse(t, w)["id"])
	m, _ := s.One("SELECT workspace_id FROM memberships WHERE user_id=?", id)
	local, csrf, e := s.IssueSession(id, Str(m["workspace_id"]), "local")
	if e != nil {
		t.Fatal(e)
	}
	if w = call(a, "GET", "/api/admin/users", local, csrf, nil); w.Code != 403 {
		t.Fatal(w.Code)
	}
	d["email"] = "renamed@example.org"
	d["password"] = "replacement-password-long"
	d["role"] = "admin"
	d["status"] = "disabled"
	d["disabled"] = false
	if w = call(a, "PATCH", "/api/admin/users/"+id, token, admin.CSRF, d); w.Code != 200 {
		t.Fatal(w.Code, w.Body.String())
	}
	if w = call(a, "GET", "/api/auth/me", local, "", nil); w.Code != 401 {
		t.Fatal("session survived account update", w.Code)
	}
	u, _ := s.One("SELECT * FROM users WHERE id=?", id)
	if !PasswordMatches(Str(d["password"]), Str(u["password"])) || Num(u["is_admin"]) != 1 || Num(u["disabled"]) != 1 {
		t.Fatal("account update not applied")
	}
	if w = call(a, "DELETE", "/api/admin/users/"+admin.UserID, token, admin.CSRF, Row{"reason": "Delete"}); w.Code != 409 {
		t.Fatal("self delete accepted", w.Code)
	}
	if w = call(a, "DELETE", "/api/admin/users/"+id, token, admin.CSRF, Row{"reason": "Departure"}); w.Code != 200 {
		t.Fatal(w.Code, w.Body.String())
	}
	if w = call(a, "GET", "/api/admin/users", token, "", nil); w.Code != 200 || strings.Contains(w.Body.String(), "renamed@example.org") || strings.Contains(w.Body.String(), "password") {
		t.Fatal(w.Body.String())
	}
	if _, e = s.One("SELECT workspace_id FROM memberships WHERE user_id=?", id); e != nil {
		t.Fatal("deleted account lost workspace", e)
	}
	if w = call(a, "POST", "/api/auth/register", "", "", Row{}); w.Code != 403 {
		t.Fatal("public registration enabled", w.Code)
	}
}

func TestCASAccountPromotionAndDisabledAccount(t *testing.T) {
	s := testStore(t)
	user, _ := testUser(t, s, "member@example.org", false)
	c := &casService{app: NewApp(s), config: fastcas.Config{Issuer: "https://cas.test", ClientID: "read"}}
	link := &fastcas.Link{ID: "link", ClientID: "read", LocalRef: user.UserID, Subject: "subject", State: "active", Version: 1}
	if e := c.accept(link); e != nil {
		t.Fatal(e)
	}
	result := &fastcas.LoginResult{Identity: fastcas.Identity{Issuer: "https://cas.test", Subject: "subject", Role: "admin"}}
	if _, e := c.issueCAS(link, result); e != nil {
		t.Fatal(e)
	}
	current, _ := s.One("SELECT is_admin FROM users WHERE id=?", user.UserID)
	if Num(current["is_admin"]) != 1 {
		t.Fatal("CAS admin not promoted")
	}
	result.Identity.Role = "member"
	if _, e := c.issueCAS(link, result); e != nil {
		t.Fatal(e)
	}
	current, _ = s.One("SELECT is_admin FROM users WHERE id=?", user.UserID)
	if Num(current["is_admin"]) != 1 {
		t.Fatal("local admin demoted")
	}
	s.Transaction(func(tx *sql.Tx) error {
		_, e := tx.Exec("UPDATE users SET disabled=1 WHERE id=?", user.UserID)
		return e
	})
	if _, e := c.issueCAS(link, result); e == nil {
		t.Fatal("disabled user accepted")
	}
}
