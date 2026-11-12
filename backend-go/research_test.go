package fastread

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestResearchStableAccountAndLocalCredential(t *testing.T) {
	s := testStore(t)
	key := "key-one"
	provider := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var payload Row
		if e := Decode(r, &payload); e != nil {
			t.Error(e)
		}
		if r.URL.Path != "/api/sso/consume" || payload["audience"] != "fast-read" || payload["ticket"] != "one-use-ticket" {
			t.Errorf("unexpected SSO request: %s %v", r.URL.Path, payload)
		}
		JSON(w, 200, Row{"keyId": key, "accountId": "stable-account", "person": "测试用户"})
	}))
	defer provider.Close()
	t.Setenv("FASTRESEARCH_API_URL", provider.URL)
	token, csrf, e := s.LoginFromResearch(context.Background(), "one-use-ticket")
	if e != nil {
		t.Fatal(e)
	}
	a := NewApp(s)
	w := call(a, "GET", "/api/auth/me", token, "", nil)
	first := decodeResponse(t, w)
	if w.Code != 200 {
		t.Fatal(w.Body.String())
	}
	w = call(a, "POST", "/api/auth/local-credential", token, csrf, Row{"email": "local@example.org", "password": "local-password-123"})
	if w.Code != 200 {
		t.Fatal("set local credential", w.Code, w.Body.String())
	}
	key = "key-two"
	next, _, e := s.LoginFromResearch(context.Background(), "one-use-ticket")
	if e != nil {
		t.Fatal(e)
	}
	w = call(a, "GET", "/api/auth/me", next, "", nil)
	second := decodeResponse(t, w)
	if w.Code != 200 || first["id"] != second["id"] || first["workspace_id"] != second["workspace_id"] || second["email"] != "local@example.org" {
		t.Fatalf("account changed after key rotation: %v / %v", first, second)
	}
	if w = call(a, "GET", "/api/auth/me", token, "", nil); w.Code != 401 {
		t.Fatal("old Research session remains usable")
	}
}
func TestResearchDocumentConsumesAndRemovesTicket(t *testing.T) {
	s := testStore(t)
	provider := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		JSON(w, 200, Row{"keyId": "document-key", "person": "Reader"})
	}))
	defer provider.Close()
	t.Setenv("FASTRESEARCH_API_URL", provider.URL)
	w := call(NewApp(s), "GET", "/?sso=secret-ticket&paper=abc", "", "", nil)
	if w.Code != 302 || w.Header().Get("Location") != "/?paper=abc" {
		t.Fatal(w.Code, w.Header())
	}
	if len(w.Result().Cookies()) == 0 {
		t.Fatal("SSO did not issue session")
	}
}
