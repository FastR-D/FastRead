package fastread

import (
	"bytes"
	"database/sql"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"
)

func testStore(t *testing.T) *Store {
	t.Helper()
	t.Setenv("FASTREAD_DATA_ROOT", "")
	t.Setenv("FASTREAD_ADMIN_EMAILS", "")
	s, e := OpenStore(t.TempDir())
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(func() { s.DB.Close() })
	return s
}
func testUser(t *testing.T, s *Store, email string, admin bool) (Principal, string) {
	t.Helper()
	u, e := s.CreateUser(email, "test-password-12345", "研究工作区", "研究员", admin)
	if e != nil {
		t.Fatal(e)
	}
	token, csrf, e := s.IssueSession(Str(u["user_id"]), Str(u["workspace_id"]), "local")
	if e != nil {
		t.Fatal(e)
	}
	return Principal{UserID: Str(u["user_id"]), WorkspaceID: Str(u["workspace_id"]), Email: email, Role: "owner", CSRF: csrf, IsAdmin: admin}, token
}
func call(a *App, method, path, token, csrf string, body any) *httptest.ResponseRecorder {
	var b bytes.Buffer
	if body != nil {
		_ = json.NewEncoder(&b).Encode(body)
	}
	r := httptest.NewRequest(method, path, &b)
	if token != "" {
		r.AddCookie(&http.Cookie{Name: "fastread_session", Value: token})
	}
	r.Header.Set("X-CSRF-Token", csrf)
	w := httptest.NewRecorder()
	a.ServeHTTP(w, r)
	return w
}
func decodeResponse(t *testing.T, w *httptest.ResponseRecorder) Row {
	t.Helper()
	var r Row
	if e := json.Unmarshal(w.Body.Bytes(), &r); e != nil {
		t.Fatal(e, w.Body.String())
	}
	return r
}

func TestWorkspaceIsolationAndCSRF(t *testing.T) {
	s := testStore(t)
	owner, token := testUser(t, s, "owner@example.org", false)
	_, other := testUser(t, s, "other@example.org", false)
	a := NewApp(s)
	_, e := s.DB.Exec("INSERT INTO papers(id,workspace_id,identity,title,metadata,created) VALUES('paper',?,'sample','论文','{}',?)", owner.WorkspaceID, Now())
	if e != nil {
		t.Fatal(e)
	}
	if w := call(a, "GET", "/api/papers/paper", other, "", nil); w.Code != 404 {
		t.Fatalf("cross workspace got %d: %s", w.Code, w.Body.String())
	}
	if w := call(a, "PUT", "/api/papers/paper/summary", token, "", Row{"content": "note"}); w.Code != 403 {
		t.Fatalf("missing csrf got %d", w.Code)
	}
	if w := call(a, "PUT", "/api/papers/paper/summary", token, owner.CSRF, Row{"content": "方法比较"}); w.Code != 200 {
		t.Fatalf("update got %d: %s", w.Code, w.Body.String())
	}
	if w := call(a, "GET", "/api/admin/users", token, "", nil); w.Code != 403 {
		t.Fatalf("workspace owner gained admin: %d", w.Code)
	}
}
func TestSharedModelAssignmentAndRevocation(t *testing.T) {
	s := testStore(t)
	admin, adminToken := testUser(t, s, "admin@example.org", true)
	user, token := testUser(t, s, "member@example.org", false)
	outsider, otherToken := testUser(t, s, "outside@example.org", false)
	a := NewApp(s)
	w := call(a, "POST", "/api/admin/providers", adminToken, admin.CSRF, Row{"name": "公共模型", "base_url": "https://93.184.216.34/v1", "api_key": "secret-not-in-responses", "models": []string{"model-a"}, "workspace_ids": []string{user.WorkspaceID}})
	if w.Code != 201 {
		t.Fatalf("create shared provider: %d %s", w.Code, w.Body.String())
	}
	id := Str(decodeResponse(t, w)["id"])
	w = call(a, "GET", "/api/providers", token, "", nil)
	if w.Code != 200 || !strings.Contains(w.Body.String(), "model-a") || strings.Contains(w.Body.String(), "secret-not-in-responses") {
		t.Fatalf("provider response %d %s", w.Code, w.Body.String())
	}
	if _, e := a.ChooseModel(user, id, "model-a"); e != nil {
		t.Fatal(e)
	}
	if _, e := a.ChooseModel(outsider, id, "model-a"); e == nil {
		t.Fatal("unassigned workspace gained model")
	}
	w = call(a, "GET", "/api/providers", otherToken, "", nil)
	if strings.Contains(w.Body.String(), "model-a") {
		t.Fatal("shared model leaked")
	}
	w = call(a, "PATCH", "/api/admin/providers/"+id, adminToken, admin.CSRF, Row{"enabled": false})
	if w.Code != 200 {
		t.Fatal(w.Body.String())
	}
	if _, e := a.ChooseModel(user, id, "model-a"); e == nil {
		t.Fatal("disabled model still selectable")
	}
}
func TestSingleUseRecoveryRevokesSessions(t *testing.T) {
	s := testStore(t)
	u, token := testUser(t, s, "user@example.org", false)
	raw, e := s.IssueCredential("recovery", u.Email)
	if e != nil {
		t.Fatal(e)
	}
	if e = s.RedeemCredential("recovery", raw, "replacement-password-123"); e != nil {
		t.Fatal(e)
	}
	if e = s.RedeemCredential("recovery", raw, "third-password-123"); e == nil {
		t.Fatal("credential replay accepted")
	}
	if w := call(NewApp(s), "GET", "/api/auth/me", token, "", nil); w.Code != 401 {
		t.Fatal("recovery retained session")
	}
	row, e := s.One("SELECT password FROM users WHERE id=?", u.UserID)
	if e != nil || !PasswordMatches("replacement-password-123", Str(row["password"])) {
		t.Fatal("replacement password missing")
	}
}
func TestJobIdempotencyQuotaAndArchive(t *testing.T) {
	s := testStore(t)
	u, token := testUser(t, s, "queue@example.org", false)
	a := NewApp(s)
	_, _ = s.DB.Exec("INSERT INTO papers(id,workspace_id,identity,title,metadata,created) VALUES('p',?,'sample','论文','{}',?)", u.WorkspaceID, Now())
	payload := Row{"model": "m", "provider_id": "p"}
	first, e := s.Enqueue(u, "report", payload, "request-1", "p", "v", true)
	if e != nil {
		t.Fatal(e)
	}
	retry, e := s.Enqueue(u, "report", Row{"provider_id": "p", "model": "m"}, "request-1", "p", "v", true)
	if e != nil || first["id"] != retry["id"] {
		t.Fatal("retry created another job", e)
	}
	if _, e = s.Enqueue(u, "report", Row{"model": "other"}, "request-1", "p", "v", true); e == nil {
		t.Fatal("conflicting retry accepted")
	}
	_, _ = s.DB.Exec("UPDATE workspaces SET daily_limit=1 WHERE id=?", u.WorkspaceID)
	if _, e = s.Enqueue(u, "report", payload, "request-2", "p", "v", true); e == nil {
		t.Fatal("quota ignored")
	}
	if w := call(a, "DELETE", "/api/papers/p", token, u.CSRF, nil); w.Code != 409 {
		t.Fatal("archived active job paper")
	}
	if w := call(a, "POST", "/api/jobs/"+Str(first["id"])+"/cancel", token, u.CSRF, nil); w.Code != 200 {
		t.Fatal(w.Body.String())
	}
	if w := call(a, "DELETE", "/api/papers/p", token, u.CSRF, nil); w.Code != 200 {
		t.Fatal(w.Body.String())
	}
}
func TestExistingSchemaAndEncryptedProviderRoundTrip(t *testing.T) {
	s := testStore(t)
	value, e := s.ProtectSecret("api-test-value")
	if e != nil {
		t.Fatal(e)
	}
	if !strings.HasPrefix(value, "filekey:v1:") {
		t.Fatal("plaintext stored")
	}
	plain, e := s.UnprotectSecret(value)
	if e != nil || plain != "api-test-value" {
		t.Fatal("secret round trip", e)
	}
	root := s.Root
	s.DB.Close()
	s, e = OpenStore(root)
	if e != nil {
		t.Fatal(e)
	}
	defer s.DB.Close()
	plain, e = s.UnprotectSecret(value)
	if e != nil || plain != "api-test-value" {
		t.Fatal("secret after restart", e)
	}
}
func TestTransactionRollback(t *testing.T) {
	s := testStore(t)
	err := s.Transaction(func(tx *sql.Tx) error {
		if _, e := tx.Exec("INSERT INTO workspaces(id,name) VALUES('rollback','test')"); e != nil {
			return e
		}
		return Error(409, "cancel")
	})
	if err == nil {
		t.Fatal("expected transaction error")
	}
	if _, e := s.One("SELECT id FROM workspaces WHERE id='rollback'"); e != sql.ErrNoRows {
		t.Fatalf("transaction not rolled back: %v", e)
	}
}
func TestPythonAccountAndSessionMigration(t *testing.T) {
	root := t.TempDir()
	db, e := sql.Open("sqlite", filepath.Join(root, "fastread-web.sqlite3"))
	if e != nil {
		t.Fatal(e)
	}
	_, e = db.Exec(`CREATE TABLE users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,created REAL NOT NULL);
CREATE TABLE workspaces(id TEXT PRIMARY KEY,name TEXT NOT NULL,daily_limit INTEGER NOT NULL DEFAULT 50);
CREATE TABLE memberships(user_id TEXT,workspace_id TEXT,role TEXT,PRIMARY KEY(user_id,workspace_id));
CREATE TABLE sessions(token TEXT PRIMARY KEY,user_id TEXT,workspace_id TEXT,csrf TEXT NOT NULL,expires REAL NOT NULL);
INSERT INTO users VALUES('legacy','legacy@example.org','scrypt$00112233445566778899aabbccddeeff$2b7781a15634d46152cf16aa999f6ada11e6083fe17091e2a0a0a529e1e14b26a7103e948c484c87e324e02edf3878065c4443dba012dee3fe9dcaeea8585a39',1);
INSERT INTO workspaces(id,name) VALUES('existing','现有资料库');INSERT INTO memberships VALUES('legacy','existing','owner');`)
	if e != nil {
		t.Fatal(e)
	}
	_, e = db.Exec("INSERT INTO sessions VALUES(?,?,?,?,?)", TokenHash("old-cookie"), "legacy", "existing", "old-csrf", Now()+3600)
	if e != nil {
		t.Fatal(e)
	}
	db.Close()
	s, e := OpenStore(root)
	if e != nil {
		t.Fatal(e)
	}
	defer s.DB.Close()
	u, e := s.One("SELECT * FROM users WHERE id='legacy'")
	if e != nil || !PasswordMatches("legacy-password-123", Str(u["password"])) {
		t.Fatal("existing Python password is unusable", e)
	}
	w := call(NewApp(s), "GET", "/api/auth/me", "old-cookie", "", nil)
	if w.Code != 200 {
		t.Fatal("existing session not preserved", w.Code, w.Body.String())
	}
	me := decodeResponse(t, w)
	if me["workspace_id"] != "existing" || me["is_admin"] != false {
		t.Fatal("existing account permissions changed", me)
	}
}
