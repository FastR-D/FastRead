package fastread

import (
	"context"
	"database/sql"
	"errors"
	"net/http/httptest"
	"strings"
	"testing"
)

func sharedProvider(t *testing.T, a *App, admin Principal, token string, workspaces, users []string) string {
	t.Helper()
	w := call(a, "POST", "/api/admin/providers", token, admin.CSRF, Row{"name": "Shared model", "base_url": "https://93.184.216.34/v1", "api_key": "private-model-key", "models": []string{"model-a"}, "workspace_ids": workspaces, "user_ids": users})
	if w.Code != 201 {
		t.Fatalf("create provider: %d %s", w.Code, w.Body.String())
	}
	return Str(decodeResponse(t, w)["id"])
}

func TestSharedModelUserAndWorkspaceGrants(t *testing.T) {
	s := testStore(t)
	admin, adminToken := testUser(t, s, "admin@example.org", true)
	recipient, recipientToken := testUser(t, s, "recipient@example.org", false)
	peer, _ := testUser(t, s, "peer@example.org", false)
	outsider, outsideToken := testUser(t, s, "outsider@example.org", false)
	if _, e := s.DB.Exec("INSERT INTO memberships VALUES(?,?,'member')", peer.UserID, recipient.WorkspaceID); e != nil {
		t.Fatal(e)
	}
	peer.WorkspaceID = recipient.WorkspaceID
	peerToken, _, e := s.IssueSession(peer.UserID, peer.WorkspaceID, "local")
	if e != nil {
		t.Fatal(e)
	}
	a := NewApp(s)
	id := sharedProvider(t, a, admin, adminToken, nil, []string{recipient.UserID})
	check := func(p Principal, token string, allowed bool) {
		t.Helper()
		w := call(a, "GET", "/api/providers", token, "", nil)
		if w.Code != 200 {
			t.Fatal(w.Body.String())
		}
		items := decodeResponse(t, w)["items"].([]any)
		expected := 0
		if allowed {
			expected = 1
		}
		if len(items) != expected {
			t.Fatalf("%s got %d providers; want %d: %s", p.Email, len(items), expected, w.Body.String())
		}
		if strings.Contains(w.Body.String(), "private-model-key") || strings.Contains(w.Body.String(), "filekey:") {
			t.Fatal("secret leaked")
		}
		for _, provider := range []string{id, ""} {
			_, e := a.ChooseModel(p, provider, "model-a")
			if (e == nil) != allowed {
				t.Fatalf("%s select %q allowed=%v: %v", p.Email, provider, allowed, e)
			}
		}
	}
	patch := func(body Row) *httptest.ResponseRecorder {
		t.Helper()
		return call(a, "PATCH", "/api/admin/providers/"+id, adminToken, admin.CSRF, body)
	}
	check(recipient, recipientToken, true)
	check(peer, peerToken, false)
	check(outsider, outsideToken, false)
	// User grants may also follow that user into another workspace they belong to.
	if _, e = s.DB.Exec("INSERT INTO memberships VALUES(?,?,'member')", recipient.UserID, outsider.WorkspaceID); e != nil {
		t.Fatal(e)
	}
	otherContext := recipient
	otherContext.WorkspaceID = outsider.WorkspaceID
	if _, e = a.ChooseModel(otherContext, id, "model-a"); e != nil {
		t.Fatal("individual grant did not follow the user", e)
	}
	if w := patch(Row{"workspace_ids": []string{recipient.WorkspaceID}, "user_ids": []string{recipient.UserID, outsider.UserID}}); w.Code != 200 {
		t.Fatal(w.Body.String())
	}
	check(recipient, recipientToken, true) // Both grants must produce one listing.
	check(peer, peerToken, true)
	check(outsider, outsideToken, true)
	// Invalid targets roll back both dimensions and the enabled flag together.
	if w := patch(Row{"workspace_ids": []string{}, "user_ids": []string{"missing"}, "enabled": false}); w.Code != 422 {
		t.Fatal("invalid user accepted", w.Code, w.Body.String())
	}
	check(peer, peerToken, true)
	check(outsider, outsideToken, true)
	if w := patch(Row{"workspace_ids": []string{"missing"}, "user_ids": []string{}}); w.Code != 422 {
		t.Fatal("invalid workspace accepted", w.Code, w.Body.String())
	}
	check(outsider, outsideToken, true)
	if w := patch(Row{"user_ids": []string{}}); w.Code != 200 {
		t.Fatal(w.Body.String())
	}
	check(peer, peerToken, true)
	check(outsider, outsideToken, false)
	if w := patch(Row{"workspace_ids": []string{}, "user_ids": []string{recipient.UserID}}); w.Code != 200 {
		t.Fatal(w.Body.String())
	}
	check(recipient, recipientToken, true)
	check(peer, peerToken, false)
	if w := patch(Row{"enabled": false}); w.Code != 200 {
		t.Fatal(w.Body.String())
	}
	check(recipient, recipientToken, false)
	if w := patch(Row{"enabled": true}); w.Code != 200 {
		t.Fatal(w.Body.String())
	}
	check(recipient, recipientToken, true)
	w := call(a, "GET", "/api/admin/providers", adminToken, "", nil)
	if !strings.Contains(w.Body.String(), recipient.UserID) || strings.Contains(w.Body.String(), "private-model-key") {
		t.Fatal("admin grant response invalid", w.Body.String())
	}
	if w = call(a, "PATCH", "/api/admin/providers/"+id, recipientToken, recipient.CSRF, Row{"user_ids": []string{peer.UserID}}); w.Code != 403 {
		t.Fatal("non-admin edited grants", w.Code)
	}
}

func TestSharedModelWorkerRechecksSubmittingUser(t *testing.T) {
	s := testStore(t)
	admin, adminToken := testUser(t, s, "admin@example.org", true)
	user, _ := testUser(t, s, "user@example.org", false)
	a := NewApp(s)
	id := sharedProvider(t, a, admin, adminToken, nil, []string{user.UserID})
	payload, e := a.ChooseModel(user, id, "model-a")
	if e != nil {
		t.Fatal(e)
	}
	job, e := s.Enqueue(user, "report", payload, "queued-before-revocation", "", "", true)
	if e != nil {
		t.Fatal(e)
	}
	w := call(a, "PATCH", "/api/admin/providers/"+id, adminToken, admin.CSRF, Row{"user_ids": []string{}})
	if w.Code != 200 {
		t.Fatal(w.Body.String())
	}
	_, e = completeModel(context.Background(), s, job, "worker", payload, "instruction", Row{})
	if !errors.Is(e, sql.ErrNoRows) {
		t.Fatal("worker did not reject a revoked user grant before dispatch", e)
	}
	// A workspace grant still requires an active account and current membership.
	w = call(a, "PATCH", "/api/admin/providers/"+id, adminToken, admin.CSRF, Row{"workspace_ids": []string{user.WorkspaceID}})
	if w.Code != 200 {
		t.Fatal(w.Body.String())
	}
	if _, e = s.DB.Exec("UPDATE users SET disabled=1 WHERE id=?", user.UserID); e != nil {
		t.Fatal(e)
	}
	if _, e = s.Provider(user.WorkspaceID, user.UserID, id); !errors.Is(e, sql.ErrNoRows) {
		t.Fatal("disabled user retained model access", e)
	}
	if _, e = completeModel(context.Background(), s, job, "worker", payload, "instruction", Row{}); !errors.Is(e, sql.ErrNoRows) {
		t.Fatal("worker accepted disabled submitter", e)
	}
	if _, e = s.DB.Exec("UPDATE users SET disabled=0 WHERE id=?", user.UserID); e != nil {
		t.Fatal(e)
	}
	if _, e = s.DB.Exec("DELETE FROM memberships WHERE user_id=? AND workspace_id=?", user.UserID, user.WorkspaceID); e != nil {
		t.Fatal(e)
	}
	if _, e = s.Providers(user.WorkspaceID, user.UserID); !errors.Is(e, sql.ErrNoRows) {
		t.Fatal("former workspace member retained access", e)
	}
}

func TestExistingSharedWorkspaceGrantsSurviveUserGrantMigration(t *testing.T) {
	s := testStore(t)
	admin, adminToken := testUser(t, s, "admin@example.org", true)
	user, _ := testUser(t, s, "user@example.org", false)
	id := sharedProvider(t, NewApp(s), admin, adminToken, []string{user.WorkspaceID}, nil)
	if _, e := s.DB.Exec("DROP TABLE shared_provider_users"); e != nil {
		t.Fatal(e)
	}
	root := s.Root
	s.DB.Close()
	migrated, e := OpenStore(root)
	if e != nil {
		t.Fatal(e)
	}
	defer migrated.DB.Close()
	if _, e = migrated.Provider(user.WorkspaceID, user.UserID, id); e != nil {
		t.Fatal("existing workspace grant lost", e)
	}
	if _, e = migrated.All("SELECT * FROM shared_provider_users"); e != nil {
		t.Fatal("user grants table not migrated", e)
	}
}
