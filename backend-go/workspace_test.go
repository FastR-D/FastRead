package fastread

import (
	"context"
	"encoding/json"
	"errors"
	"net/http/httptest"
	"strings"
	"testing"

	fastcas "github.com/FastR-D/FastCAS/sdk/go"
)

type workspaceFixture struct {
	link   *fastcas.Link
	active bool
	fail   bool
}

func (f *workspaceFixture) VerifyAccessToken(_ context.Context, raw, aud string, scopes ...string) (*fastcas.AccessClaims, error) {
	if raw != "valid" || aud != "fastread" || len(scopes) != 1 || scopes[0] != "workspace:read" {
		return nil, errors.New("bad token")
	}
	return &fastcas.AccessClaims{Subject: "fastresearch", ClientID: "fastresearch", Service: true}, nil
}
func (f *workspaceFixture) IntrospectToken(context.Context, string) (*fastcas.Introspection, error) {
	return &fastcas.Introspection{Active: f.active, Subject: "fastresearch", ClientID: "fastresearch", Audience: []string{"fastread"}, Scope: "workspace:read"}, nil
}
func (f *workspaceFixture) ResolveLink(context.Context, string) (*fastcas.Link, error) {
	if f.fail {
		return nil, errors.New("unavailable")
	}
	return f.link, nil
}
func TestWorkspaceSummaryKeepsWorkspaceAndUserBoundaries(t *testing.T) {
	s := testStore(t)
	a := NewApp(s)
	user, _ := testUser(t, s, "reader@example.test", false)
	other, _ := testUser(t, s, "other@example.test", false)
	paper := seedDocument(t, s, user, "Own paper")
	seedDocument(t, s, other, "Other private paper")
	a.workspaceIssuer = "https://cas.test"
	a.workspaceClient = "fastread"
	provider := &workspaceFixture{active: true, link: &fastcas.Link{ID: "link", ClientID: "fastread", Subject: "subject", LocalRef: user.UserID, State: "active", Version: 2}}
	a.workspaceCAS = provider
	_, e := s.DB.Exec(`INSERT INTO fastcas_links VALUES(?,?,?,?,?,?,?,?)`, a.workspaceIssuer, "link", "fastread", user.UserID, "subject", "active", 2, "{}")
	if e != nil {
		t.Fatal(e)
	}
	_, e = s.DB.Exec(`INSERT INTO notebook_notes VALUES(?,?, 'paper',?,?,?,'{}',NULL,?,?)`, "note", user.WorkspaceID, paper["paper_id"], "My note", "private body must not be returned", Now(), Now())
	if e != nil {
		t.Fatal(e)
	}
	call := func(subject, token string) (int, Row) {
		r := httptest.NewRequest("POST", "/api/integrations/fastresearch/workspace", strings.NewReader(`{"subject":"`+subject+`"}`))
		r.Header.Set("Authorization", "Bearer "+token)
		w := httptest.NewRecorder()
		a.ServeHTTP(w, r)
		if strings.Contains(w.Body.String(), "Other private paper") || strings.Contains(w.Body.String(), "private body must not be returned") {
			t.Fatal("summary leaked private content")
		}
		var result Row
		_ = json.Unmarshal(w.Body.Bytes(), &result)
		return w.Code, result
	}
	status, result := call("subject", "valid")
	if status != 200 || result["accountState"] != "active" {
		t.Fatal(status, result)
	}
	metrics := result["metrics"].([]any)
	if Num(metrics[0].(map[string]any)["value"]) != 1 || Num(metrics[2].(map[string]any)["value"]) != 1 {
		t.Fatal("wrong personal metrics", metrics)
	}
	if status, result = call("missing", "valid"); status != 200 || result["accountState"] != "missing" {
		t.Fatal(status, result)
	}
	_, e = s.DB.Exec(`UPDATE users SET disabled=1 WHERE id=?`, user.UserID)
	if e != nil {
		t.Fatal(e)
	}
	if status, result = call("subject", "valid"); status != 200 || result["accountState"] != "inactive" {
		t.Fatal("disabled user summary accepted", status, result)
	}
	_, e = s.DB.Exec(`UPDATE users SET disabled=0 WHERE id=?`, user.UserID)
	if e != nil {
		t.Fatal(e)
	}
	provider.fail = true
	if status, _ = call("subject", "valid"); status != 503 {
		t.Fatal("upstream failure became missing account", status)
	}
	provider.fail = false
	provider.active = false
	if status, _ = call("subject", "valid"); status != 401 {
		t.Fatal("revoked service accepted", status)
	}
	if status, _ = call("subject", "forged"); status != 401 {
		t.Fatal("forged credential accepted", status)
	}
}
