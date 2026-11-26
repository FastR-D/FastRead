package fastread

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func studioJSON(t *testing.T, raw string) Row {
	t.Helper()
	var value Row
	if err := json.Unmarshal([]byte(raw), &value); err != nil {
		t.Fatal(err)
	}
	return value
}
func TestReadingInteractionGroundingAndSimulation(t *testing.T) {
	chunks := []Row{{"id": "S1", "paper_id": "paper", "version_id": "v1", "page": 2, "text": "Our score is x divided by scale. Baseline obtains 90.0 accuracy; Method obtains 95.5 accuracy on Dataset A."}}
	report := studioJSON(t, `{"formulas":[{"title":"Score","latex":"x/s","explanation":"Scale the input.","variables":[{"name":"x","min":0,"max":10,"value":2},{"name":"scale","min":1,"max":5,"value":2}],"expression":{"op":"div","args":["x","scale"]},"evidence":[{"source_id":"S1","quote":"Our score is x divided by scale."}]}],"experiments":[{"title":"Main result","conditions":"Dataset A","metric":"accuracy","unit":"%","rows":[{"label":"Baseline","value":"90.0","evidence":[{"source_id":"S1","quote":"Baseline obtains 90.0 accuracy"}]},{"label":"Method","value":"95.5","evidence":[{"source_id":"S1","quote":"Method obtains 95.5 accuracy on Dataset A."}]},{"label":"Invented","value":"99.0","evidence":[{"source_id":"S1","quote":"Method obtains 95.5 accuracy on Dataset A."}]}]}]}`)
	bindReadingInteractions(report, chunks)
	formulas := report["formulas"].([]Row)
	if len(formulas) != 1 || formulas[0]["expression"] == nil {
		t.Fatal("valid simulation was removed", report)
	}
	experiments := report["experiments"].([]Row)
	if len(experiments) != 1 || len(experiments[0]["rows"].([]Row)) != 2 {
		t.Fatal("ungrounded experiment survived", report)
	}
	if len(report["interaction_warnings"].([]string)) == 0 {
		t.Fatal("missing component warning")
	}
	ev := formulas[0]["evidence"].([]Row)[0]
	if ev["version_id"] != "v1" || ev["page"] != 2 {
		t.Fatal("lost provenance", ev)
	}
	// Export sees the JSON representation loaded from storage.
	stored := studioJSON(t, Encode(report))
	var out strings.Builder
	renderReadingInteractions(&out, stored)
	for _, part := range []string{"公式与教学试算", "教学试算（非论文实验复现）", "95.5", "第 2 页"} {
		if !strings.Contains(out.String(), part) {
			t.Fatalf("export missing %q: %s", part, out.String())
		}
	}
}
func TestReadingInteractionsRejectUnsafeOrInventedMaterial(t *testing.T) {
	chunks := []Row{{"id": "S1", "page": 1, "text": "Baseline reports 190.0 points in the experiment."}}
	report := studioJSON(t, `{"formulas":[{"title":"Explain only","latex":"x","variables":[{"name":"x","min":0,"max":1,"value":0}],"expression":{"op":"javascript","args":[]},"evidence":[{"source_id":"S1","quote":"Baseline reports 190.0 points"}]},{"title":"Invented","latex":"y","evidence":[{"source_id":"S1","quote":"This quotation does not exist."}]}],"experiments":[{"title":"Invalid substring","conditions":"test","metric":"points","rows":[{"label":"Baseline","value":"90.0","evidence":[{"source_id":"S1","quote":"Baseline reports 190.0 points"}]}]}]}`)
	bindReadingInteractions(report, chunks)
	formulas := report["formulas"].([]Row)
	if len(formulas) != 1 || formulas[0]["expression"] != nil {
		t.Fatal("unsafe formula was not downgraded", formulas)
	}
	if len(report["experiments"].([]Row)) != 0 {
		t.Fatal("number substring accepted")
	}
}
func TestReadingModeValidationAndHistoricalExport(t *testing.T) {
	s := testStore(t)
	p, token := testUser(t, s, "reading-studio@example.org", false)
	doc := seedDocument(t, s, p, "Reading studio")
	pid, vid := Str(doc["paper_id"]), Str(doc["version_id"])
	provider, _ := modelFixture(t, s, p, `{}`)
	a := readingApp(s)
	bad := call(a, "POST", "/api/papers/"+pid+"/reports", token, p.CSRF, Row{"provider_id": provider, "model": "test-model", "reading_mode": "unknown"})
	if bad.Code != 422 {
		t.Fatal(bad.Code, bad.Body.String())
	}
	req := httptest.NewRequest("POST", "/api/papers/"+pid+"/reports", strings.NewReader(Encode(Row{"provider_id": provider, "model": "test-model", "reading_mode": "skim"})))
	req.AddCookie(&http.Cookie{Name: "fastread_session", Value: token})
	req.Header.Set("X-CSRF-Token", p.CSRF)
	req.Header.Set("Idempotency-Key", UID())
	good := httptest.NewRecorder()
	a.ServeHTTP(good, req)
	if good.Code != 202 {
		t.Fatal(good.Code, good.Body.String())
	}
	job, err := s.One("SELECT payload FROM jobs WHERE resource_id=? AND kind='report'", pid)
	if err != nil || Object(job["payload"])["reading_mode"] != "skim" {
		t.Fatal("mode lost", job, err)
	}
	// A history export must not silently export the newest report.
	for i, id := range []string{"report-old", "report-new"} {
		_, err = s.DB.Exec("INSERT INTO report_versions VALUES(?,?,?,?,?,?)", id, pid, vid, nil, Encode(Row{"executive_summary": id}), i+1)
		if err != nil {
			t.Fatal(err)
		}
	}
	selected := call(a, "GET", "/api/papers/"+pid+"/export?report=report-old", token, "", nil)
	if selected.Code != 200 || !strings.Contains(selected.Body.String(), "report-old") || strings.Contains(selected.Body.String(), "report-new") {
		t.Fatal(selected.Code, selected.Body.String())
	}
	missing := call(a, "GET", "/api/papers/"+pid+"/export?report=foreign", token, "", nil)
	if missing.Code != 404 {
		t.Fatal("missing report should not fall back", missing.Code)
	}
}

func TestRepositorySourceValidationAndEvidence(t *testing.T) {
	sha := strings.Repeat("a", 40)
	valid := Row{"url": "https://github.com/owner/repository", "commit": sha, "paths": []string{"src/model.py", "README.md"}}
	repo, err := validateReadingRepository(valid)
	if err != nil {
		t.Fatal(err)
	}
	for _, bad := range []Row{
		{"url": "https://github.com.evil.test/o/r", "commit": sha, "paths": []string{"README.md"}},
		{"url": "https://github.com/o/r", "commit": "main", "paths": []string{"README.md"}},
		{"url": "https://github.com/o/r", "commit": sha, "paths": []string{"../private"}},
		{"url": "https://github.com/o/r", "commit": sha, "paths": []string{"src/../../private"}},
		{"url": "https://github.com/o/r", "commit": sha, "paths": []string{"src.py?token=secret"}},
	} {
		if _, err := validateReadingRepository(bad); err == nil {
			t.Fatal("unsafe repository accepted", bad)
		}
	}
	repo["files"] = []Row{{"path": "src/model.py", "content": "def encode(x):\n    return x / 2", "line_start": 1, "line_end": 2}}
	result := studioJSON(t, `{"implementation_raw":[{"title":"Encode","description":"Scale input.","evidence":[{"source_id":"S1","quote":"The method scales its input by a factor of two."}],"code_evidence":[{"path":"src/model.py","line_start":1,"line_end":2,"quote":"return x / 2"}]},{"title":"Invented","evidence":[{"source_id":"S1","quote":"The method scales its input by a factor of two."}],"code_evidence":[{"path":"src/model.py","line_start":99,"line_end":101,"quote":"return x / 2"}]}]}`)
	bindRepositoryImplementation(result, repo, []Row{{"id": "S1", "text": "The method scales its input by a factor of two.", "page": 3}})
	if len(result["implementation"].([]Row)) != 1 {
		t.Fatal("unread code was accepted", result)
	}
	var out strings.Builder
	renderReadingInteractions(&out, studioJSON(t, Encode(result)))
	for _, part := range []string{sha, "src/model.py", "return x / 2", "第 3 页"} {
		if !strings.Contains(out.String(), part) {
			t.Fatal("export lost repository provenance", part)
		}
	}
	// The model cannot inject a repository when no source was fetched.
	bindRepositoryImplementation(result, nil, nil)
	if result["repository"] != nil {
		t.Fatal("unverified repository survived")
	}
}

type repositoryTransport func(*http.Request) (*http.Response, error)

func (f repositoryTransport) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }
func TestRepositorySnapshotFetchBoundaries(t *testing.T) {
	repo := Row{"url": "https://github.com/owner/repo", "commit": strings.Repeat("b", 40), "paths": []string{"src/model.py"}}
	content := strings.Repeat("source line\n", 350)
	status := 200
	client := &http.Client{Transport: repositoryTransport(func(req *http.Request) (*http.Response, error) {
		if req.URL.Host != "raw.githubusercontent.com" || !strings.Contains(req.URL.Path, strings.Repeat("b", 40)+"/src/model.py") {
			t.Fatal("fetch lost immutable source", req.URL)
		}
		return &http.Response{StatusCode: status, Body: io.NopCloser(strings.NewReader(content)), Header: http.Header{}}, nil
	})}
	result, err := fetchReadingRepository(context.Background(), repo, client)
	if err != nil {
		t.Fatal(err)
	}
	file := result["files"].([]Row)[0]
	if file["line_end"] != 300 || file["truncated"] != true {
		t.Fatal("missing excerpt boundary", file)
	}
	for _, data := range []string{"binary\x00data", strings.Repeat("x", 128*1024+1)} {
		content = data
		if _, err := fetchReadingRepository(context.Background(), repo, client); err == nil {
			t.Fatal("non-source input accepted")
		}
	}
	content = "valid source"
	status = 404
	if _, err := fetchReadingRepository(context.Background(), repo, client); err == nil {
		t.Fatal("404 source accepted")
	}
}
