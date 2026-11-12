package fastread

import (
	"database/sql"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	fastcas "github.com/FastR-D/FastCAS/sdk/go"
)

func TestCASRevocationKeepsLocalSessions(t *testing.T) {
	s, e := OpenStore(t.TempDir())
	if e != nil {
		t.Fatal(e)
	}
	defer s.DB.Close()
	u, e := s.CreateUser("cas@example.org", "long-local-password", "papers", "CAS", false)
	if e != nil {
		t.Fatal(e)
	}
	local, _, e := s.IssueSession(Str(u["user_id"]), Str(u["workspace_id"]), "local")
	if e != nil {
		t.Fatal(e)
	}
	remote, _, e := s.IssueSession(Str(u["user_id"]), Str(u["workspace_id"]), "fastcas")
	if e != nil {
		t.Fatal(e)
	}
	c := &casService{app: NewApp(s), config: fastcas.Config{Issuer: "https://cas.example.org", ClientID: "fastread"}}
	l := &fastcas.Link{ID: "link1", ClientID: "fastread", LocalRef: Str(u["user_id"]), Subject: "subject1", State: "active", Version: 1}
	if e = c.accept(l); e != nil {
		t.Fatal(e)
	}
	_, e = s.DB.Exec("UPDATE sessions SET cas_issuer=?,cas_link_id=?,cas_link_version=1 WHERE token=?", c.config.Issuer, l.ID, TokenHash(remote))
	if e != nil {
		t.Fatal(e)
	}
	l.State = "revoked"
	l.Version = 2
	for range 2 {
		if e = c.notification(fastcas.Notification{ID: "event1", Type: "account_link.revoked", Link: l}); e != nil {
			t.Fatal(e)
		}
	}
	if _, e = s.One("SELECT token FROM sessions WHERE token=?", TokenHash(remote)); e != sql.ErrNoRows {
		t.Fatalf("CAS session survived: %v", e)
	}
	if _, e = s.One("SELECT token FROM sessions WHERE token=?", TokenHash(local)); e != nil {
		t.Fatal("local login was revoked", e)
	}
	l.State = "active"
	l.Version = 1
	if e = c.accept(l); e == nil {
		t.Fatal("stale activation accepted")
	}
	row, _ := s.One("SELECT state FROM fastcas_links WHERE id='link1'")
	if row["state"] != "revoked" {
		t.Fatal(row)
	}
}

func TestExchangeUsesScopedConnectionAndPersistsFeedback(t *testing.T) {
	s, e := OpenStore(t.TempDir())
	if e != nil {
		t.Fatal(e)
	}
	defer s.DB.Close()
	t.Setenv("FASTREAD_DATA_ROOT", s.Root)
	t.Setenv("FASTREAD_COOKIE_SECURE", "false")
	u, e := s.CreateUser("reader@example.org", "long-local-password", "papers", "Reader", false)
	if e != nil {
		t.Fatal(e)
	}
	token, csrf, e := s.IssueSession(Str(u["user_id"]), Str(u["workspace_id"]), "local")
	if e != nil {
		t.Fatal(e)
	}
	_, e = s.DB.Exec("INSERT INTO papers(id,workspace_id,identity,title,metadata,created) VALUES('paper1',?,'paper1','Paper','{}',?)", u["workspace_id"], Now())
	if e != nil {
		t.Fatal(e)
	}
	pairing := strings.Repeat("a", 32)
	calls := 0
	target := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer "+pairing {
			w.WriteHeader(401)
			return
		}
		if r.Header.Get("Cookie") != "" {
			t.Error("browser cookies forwarded")
		}
		calls++
		switch r.URL.Path {
		case "/api/integrations/fastread/token":
			JSON(w, 200, Row{"connected": true})
		case "/api/integrations/fastread/projects/p1/feedback":
			JSON(w, 200, Row{"items": []Row{{"id": "note1", "paper_id": "paper1", "title": "Method", "content": "Compare the sample sizes."}, {"id": "foreign", "paper_id": "unknown", "title": "Skip", "content": "Private"}}})
		default:
			w.WriteHeader(404)
		}
	}))
	defer target.Close()
	t.Setenv("FASTREAD_FASTWRITE_URL", target.URL)
	a := NewApp(s)
	if e = a.RegisterExchange(); e != nil {
		t.Fatal(e)
	}
	call := func(method, path, body string) *httptest.ResponseRecorder {
		r := httptest.NewRequest(method, path, strings.NewReader(body))
		r.AddCookie(&http.Cookie{Name: "fastread_session", Value: token})
		r.Header.Set("X-CSRF-Token", csrf)
		w := httptest.NewRecorder()
		a.ServeHTTP(w, r)
		return w
	}
	w := call("POST", "/api/integrations/connections/fastwrite", `{"token":"`+pairing+`"}`)
	if w.Code != 200 {
		t.Fatal(w.Code, w.Body.String())
	}
	stored, _ := s.One("SELECT secret FROM integration_connections")
	if strings.Contains(Str(stored["secret"]), pairing) {
		t.Fatal("connection not encrypted")
	}
	for range 2 {
		w = call("POST", "/api/integrations/fastwrite/projects/p1/feedback", "{}")
		if w.Code != 200 {
			t.Fatal(w.Code, w.Body.String())
		}
	}
	notes, e := s.All("SELECT * FROM notebook_notes")
	if e != nil || len(notes) != 1 || notes[0]["content"] != "Compare the sample sizes." {
		t.Fatal(notes, e)
	}
	w = call("GET", "/api/integrations/status", "")
	var status Row
	_ = json.Unmarshal(w.Body.Bytes(), &status)
	if status["fastwrite"].(map[string]any)["url"] != "https://write.fastrd.io" {
		t.Fatal("browser received an internal service address", status)
	}
	if strings.Contains(w.Body.String(), pairing) {
		t.Fatal("secret leaked")
	}
	w = call("DELETE", "/api/integrations/connections/fastwrite", "")
	if w.Code != 200 {
		t.Fatal(w.Code, w.Body.String())
	}
	before := calls
	w = call("POST", "/api/integrations/fastwrite/projects/p1/feedback", "{}")
	if w.Code != 409 || calls != before {
		t.Fatal("disconnected service was called", w.Code)
	}
}
