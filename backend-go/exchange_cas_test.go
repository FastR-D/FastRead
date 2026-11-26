package fastread

import (
	"context"
	"encoding/json"
	"errors"
	fastcas "github.com/FastR-D/FastCAS/sdk/go"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

type connectionFixture struct {
	workspaceFixture
	denied bool
}

func (f *connectionFixture) ClientCredentials(_ context.Context, scopes []string) (*fastcas.TokenResponse, error) {
	if f.denied || len(scopes) != 1 || scopes[0] != connectionScope {
		return nil, errors.New("scope denied")
	}
	return &fastcas.TokenResponse{AccessToken: "service-grant"}, nil
}

func TestCASConnectionUsesCurrentIdentityAndRevokesWithBinding(t *testing.T) {
	s := testStore(t)
	p, session := testUser(t, s, "cas-reader@example.test", false)
	a := NewApp(s)
	a.workspaceIssuer = "https://cas.test"
	a.workspaceClient = "fastread"
	provider := &connectionFixture{workspaceFixture: workspaceFixture{link: &fastcas.Link{ID: "link", ClientID: "fastread", Subject: "own-subject", LocalRef: p.UserID, State: "active", Version: 2}}}
	a.workspaceCAS = provider
	a.exchangeCAS = provider
	if _, err := s.DB.Exec("INSERT INTO fastcas_links VALUES(?,?,?,?,?,?,?,?)", a.workspaceIssuer, "link", "fastread", p.UserID, "own-subject", "active", 2, "{}"); err != nil {
		t.Fatal(err)
	}
	secret := "fw_read_" + strings.Repeat("x", 40)
	calls := 0
	wrongSubject := false
	target := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		if r.Header.Get("Cookie") != "" {
			t.Error("browser cookies forwarded")
		}
		if r.URL.Path == "/api/integrations/fastread/cas-connect" {
			if r.Header.Get("Authorization") != "Bearer service-grant" {
				t.Error("missing service grant")
			}
			var body Row
			_ = json.NewDecoder(r.Body).Decode(&body)
			if body["subject"] != "own-subject" {
				t.Error("browser controlled subject", body)
			}
			subject := "own-subject"
			if wrongSubject {
				subject = "other"
			}
			JSON(w, 201, Row{"subject": subject, "token": secret})
			return
		}
		if r.Header.Get("Authorization") != "Bearer "+secret {
			t.Error("missing connection credential")
		}
		JSON(w, 200, Row{"items": []Row{}})
	}))
	defer target.Close()
	t.Setenv("FASTREAD_FASTWRITE_URL", target.URL)
	if err := a.RegisterExchange(); err != nil {
		t.Fatal(err)
	}
	call := func(method, path, csrf string) *httptest.ResponseRecorder {
		r := httptest.NewRequest(method, path, strings.NewReader(`{"subject":"attacker-chosen"}`))
		r.AddCookie(&http.Cookie{Name: "fastread_session", Value: session})
		r.Header.Set("X-CSRF-Token", csrf)
		w := httptest.NewRecorder()
		a.ServeHTTP(w, r)
		return w
	}
	connect := "/api/integrations/connections/fastwrite/cas"
	if w := call("POST", connect, ""); w.Code != 403 || calls != 0 {
		t.Fatal("missing CSRF accepted", w.Code)
	}
	wrongSubject = true
	if w := call("POST", connect, p.CSRF); w.Code != 502 {
		t.Fatal("wrong identity accepted", w.Code, w.Body.String())
	}
	wrongSubject = false
	provider.denied = true
	if w := call("POST", connect, p.CSRF); w.Code != 503 {
		t.Fatal("missing grant accepted", w.Code)
	}
	provider.denied = false
	w := call("POST", connect, p.CSRF)
	if w.Code != 200 || strings.Contains(w.Body.String(), secret) {
		t.Fatal(w.Code, w.Body.String())
	}
	stored, _ := s.One("SELECT secret FROM integration_connections")
	if Str(stored["secret"]) == secret {
		t.Fatal("plaintext credential stored")
	}
	if w = call("GET", "/api/integrations/fastwrite/projects", ""); w.Code != 200 {
		t.Fatal(w.Code, w.Body.String())
	}
	before := calls
	_, _ = s.DB.Exec("UPDATE fastcas_links SET state='revoked',version=3")
	if w = call("GET", "/api/integrations/fastwrite/projects", ""); w.Code != 403 || calls != before {
		t.Fatal("revoked binding forwarded", w.Code)
	}
	_, _ = s.DB.Exec("UPDATE fastcas_links SET state='active',version=4")
	provider.link.Version = 4
	if w = call("GET", "/api/integrations/fastwrite/projects", ""); w.Code != 403 || calls != before {
		t.Fatal("relinked identity revived an old connection", w.Code)
	}
}
