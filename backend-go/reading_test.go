package fastread

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

const evidenceText = "The proposed method reduces memory use while preserving exact page citations. Experiments compare the method against two controlled baselines."

func readingApp(s *Store) *App {
	a := NewApp(s)
	a.RegisterReading()
	a.RegisterKnowledge()
	a.RegisterIntegrations()
	return a
}
func seedDocument(t *testing.T, s *Store, p Principal, title string) Row {
	t.Helper()
	var result Row
	e := s.Transaction(func(tx *sql.Tx) error {
		var e error
		result, e = ingestDocument(tx, p.WorkspaceID, Row{"title": title, "authors": []string{"A. Author"}, "year": 2026, "page_count": 2}, []Row{{"page": 1, "text": evidenceText}, {"page": 2, "text": "The experiment evaluates multiple datasets and reports measured memory consumption and accuracy."}}, "files/sample.pdf", "")
		return e
	})
	if e != nil {
		t.Fatal(e)
	}
	return result
}
func modelFixture(t *testing.T, s *Store, p Principal, response string) (string, *httptest.Server) {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/chat/completions" || r.Header.Get("Authorization") != "Bearer test-model-secret" {
			t.Errorf("unexpected model request %s", r.URL.Path)
			w.WriteHeader(400)
			return
		}
		JSON(w, 200, Row{"choices": []Row{{"message": Row{"content": response}}}})
	}))
	t.Cleanup(server.Close)
	secret, e := s.ProtectSecret("test-model-secret")
	if e != nil {
		t.Fatal(e)
	}
	id := UID()
	_, e = s.DB.Exec("INSERT INTO providers VALUES(?,?,?,?,?,?,?)", id, p.WorkspaceID, "Test model", server.URL+"/v1", secret, Encode([]string{"test-model"}), Now())
	if e != nil {
		t.Fatal(e)
	}
	return id, server
}
func queuedJob(t *testing.T, s *Store, p Principal, kind string, payload Row, resource, version string, billable bool) Row {
	t.Helper()
	job, e := s.Enqueue(p, kind, payload, UID(), resource, version, billable)
	if e != nil {
		t.Fatal(e)
	}
	claimed, e := claimJob(s, "test-worker", 2)
	if e != nil || claimed == nil || claimed["id"] != job["id"] {
		t.Fatalf("claim failed %#v %v", claimed, e)
	}
	return claimed
}

func TestReadingRoutesKeepVersionAndWorkspaceBoundaries(t *testing.T) {
	s := testStore(t)
	p, token := testUser(t, s, "reader@example.org", false)
	_, other := testUser(t, s, "reader2@example.org", false)
	doc := seedDocument(t, s, p, "Memory-aware reading")
	pid, version := Str(doc["paper_id"]), Str(doc["version_id"])
	a := readingApp(s)
	for _, path := range []string{"/api/papers/" + pid + "/pages/1", "/api/papers/" + pid + "/annotations?version=" + version, "/api/papers/" + pid + "/reports", "/api/papers/" + pid + "/neighbors"} {
		if w := call(a, "GET", path, other, "", nil); w.Code != 404 {
			t.Fatalf("foreign access %s returned %d", path, w.Code)
		}
	}
	w := call(a, "POST", "/api/papers/"+pid+"/annotations", token, p.CSRF, Row{"version_id": version, "page": 1, "quote": "The proposed method reduces memory use", "note": "Compare memory cost", "rects": []Row{{"x": .1, "y": .2, "width": .4, "height": .05}}})
	if w.Code != 201 {
		t.Fatal(w.Code, w.Body.String())
	}
	if w = call(a, "POST", "/api/papers/"+pid+"/annotations", token, p.CSRF, Row{"version_id": version, "page": 3, "note": "wrong page"}); w.Code != 404 {
		t.Fatal("accepted missing page", w.Code)
	}
	w = call(a, "POST", "/api/papers/"+pid+"/conversations", token, p.CSRF, nil)
	if w.Code != 201 {
		t.Fatal(w.Body.String())
	}
	cid := Str(decodeResponse(t, w)["id"])
	w = call(a, "POST", "/api/papers/"+pid+"/conversations", token, p.CSRF, nil)
	if Str(decodeResponse(t, w)["id"]) != cid {
		t.Fatal("duplicate conversation for version")
	}
	if w = call(a, "GET", "/api/papers/"+pid+"/pages/1?version="+version, token, "", nil); w.Code != 200 || !strings.Contains(w.Body.String(), "memory use") {
		t.Fatal(w.Code, w.Body.String())
	}
}
func TestDocumentReimportAndImmutableVersions(t *testing.T) {
	s := testStore(t)
	p, _ := testUser(t, s, "versions@example.org", false)
	doc := seedDocument(t, s, p, "Original")
	same := seedDocument(t, s, p, "Original")
	if doc["paper_id"] != same["paper_id"] || doc["version_id"] != same["version_id"] || same["deduplicated"] != true {
		t.Fatal("reimport duplicated paper", same)
	}
	var revised Row
	e := s.Transaction(func(tx *sql.Tx) error {
		var err error
		revised, err = ingestDocument(tx, p.WorkspaceID, Row{"title": "Revised", "page_count": 1}, []Row{{"page": 1, "text": evidenceText + " Revised content."}}, "files/revised.pdf", Str(doc["paper_id"]))
		return err
	})
	if e != nil {
		t.Fatal(e)
	}
	if revised["version_id"] == doc["version_id"] {
		t.Fatal("document mutation overwrote version")
	}
	old, e := s.One("SELECT text FROM pages WHERE version_id=? AND number=1", doc["version_id"])
	if e != nil || old["text"] != evidenceText {
		t.Fatal("old source changed", e)
	}
}
func TestQuoteValidationRejectsInventedEvidence(t *testing.T) {
	if quote, ok := locatedQuote("An efﬁcient memory-aware method preserves exact page citations.", "An efficient memory aware method preserves exact page citations"); !ok || quote != "An efﬁcient memory-aware method preserves exact page citations" {
		t.Fatal("PDF typography normalization did not preserve the original quote", quote)
	}
	if quote, ok := locatedQuote("The proposed\n  method reduces memory use.", "the proposed method reduces memory use"); !ok || quote != "The proposed\n  method reduces memory use" {
		t.Fatal("quote did not retain original source spelling", quote)
	}
	chunks := []Row{{"id": "S1", "paper_id": "p", "version_id": "v", "page": 2, "text": evidenceText, "canonical_quote": evidenceText}}
	if _, e := bindSources([]any{Row{"source_id": "S1", "quote": "The method achieves a 100 percent improvement."}}, chunks); e == nil {
		t.Fatal("fabricated quote accepted")
	}
	sources, e := bindSources([]any{Row{"source_id": "S1", "quote": "The proposed method reduces memory use"}}, chunks)
	if e != nil || sources[0]["page_start"] != 2 || sources[0]["document_version_id"] != "v" {
		t.Fatal("source binding lost", e, sources)
	}
	if e = validateAnswer("Answer [S9]", sources); e == nil {
		t.Fatal("unknown inline citation accepted")
	}
}
func TestNativeChatWorkerPersistsLocatedAnswer(t *testing.T) {
	s := testStore(t)
	p, _ := testUser(t, s, "chat@example.org", false)
	doc := seedDocument(t, s, p, "Memory-aware reading")
	provider, _ := modelFixture(t, s, p, `{"answer":"The method reduces memory use [S1].","source_ids":["S1"]}`)
	cid := UID()
	_, e := s.DB.Exec("INSERT INTO conversations VALUES(?,?,?,?,?)", cid, p.WorkspaceID, doc["paper_id"], doc["version_id"], Now())
	if e != nil {
		t.Fatal(e)
	}
	job := queuedJob(t, s, p, "chat", Row{"provider_id": provider, "model": "test-model", "content": "How does it use memory?"}, cid, Str(doc["version_id"]), true)
	if e = ExecuteJob(context.Background(), s, job, "test-worker"); e != nil {
		t.Fatal(e)
	}
	saved, e := s.One("SELECT * FROM messages WHERE job_id=? AND role='assistant'", job["id"])
	if e != nil {
		t.Fatal(e)
	}
	sources := snapshotRows(Object(saved["evidence"])["sources"])
	if len(sources) != 1 || Str(sources[0]["document_version_id"]) != Str(doc["version_id"]) {
		t.Fatal("missing versioned evidence", saved)
	}
	finished, _ := s.One("SELECT state FROM jobs WHERE id=?", job["id"])
	if finished["state"] != "succeeded" {
		t.Fatal("job not completed")
	}
}

func TestNativeOrganizeWorkerStoresPrincipleAndMembership(t *testing.T) {
	s := testStore(t)
	p, _ := testUser(t, s, "organize@example.org", false)
	doc := seedDocument(t, s, p, "Memory-aware reading")
	provider, _ := modelFixture(t, s, p, `{"principle":"The method reduces memory consumption while preserving citations to the source pages.","tags":["memory efficiency","source grounding"],"knowledge_id":"","new_knowledge_name":"Evidence-aware reading","evidence":[{"source_id":"S1","quote":"The proposed method reduces memory use"}]}`)
	job := queuedJob(t, s, p, "organize", Row{"provider_id": provider, "model": "test-model", "knowledge_id": ""}, Str(doc["paper_id"]), Str(doc["version_id"]), true)
	if e := ExecuteJob(context.Background(), s, job, "test-worker"); e != nil {
		t.Fatal(e)
	}
	insight, e := s.One("SELECT principle,evidence FROM paper_insights WHERE paper_id=? AND version_id=?", doc["paper_id"], doc["version_id"])
	if e != nil || !strings.Contains(Str(insight["principle"]), "memory consumption") {
		t.Fatal("principle not stored", e)
	}
	membership, e := s.One("SELECT k.name FROM knowledge_bases k JOIN knowledge_papers p ON p.knowledge_id=k.id WHERE p.paper_id=?", doc["paper_id"])
	if e != nil || membership["name"] != "Evidence-aware reading" {
		t.Fatal("knowledge membership missing", e)
	}
	tags, e := s.All("SELECT tag FROM paper_tags WHERE paper_id=?", doc["paper_id"])
	if e != nil || len(tags) != 2 {
		t.Fatal("tags missing", e)
	}
}

func TestReportKeepsBalancedPagesAndCompleteMarkdown(t *testing.T) {
	s := testStore(t)
	p, _ := testUser(t, s, "report-export@example.org", false)
	pages := []Row{}
	for page := 1; page <= 30; page++ {
		pages = append(pages, Row{"page": page, "text": evidenceText + strings.Repeat(" Detailed source material.", 400)})
	}
	var document Row
	if e := s.Transaction(func(tx *sql.Tx) error {
		var err error
		document, err = ingestDocument(tx, p.WorkspaceID, Row{"title": "Balanced report", "page_count": 30}, pages, "files/report.pdf", "")
		return err
	}); e != nil {
		t.Fatal(e)
	}
	sources, metadata, e := reportSources(s, p.WorkspaceID, Str(document["paper_id"]), Str(document["version_id"]))
	if e != nil || len(sources) != 30 || Num(metadata["context_characters"]) != 120000 {
		t.Fatal("report did not cover all pages within budget", e, metadata)
	}
	questions := []Row{}
	for i := 0; i < 4; i++ {
		questions = append(questions, Row{"question": fmt.Sprintf("Question %d", i+1), "answer": "A supported answer.", "why_it_matters": "A useful motivation.", "evidence": []Row{{"source_id": "S1", "quote": "The proposed method reduces memory use"}}})
	}
	result := Row{"title": "Balanced report", "executive_summary": "Overview retained in export.", "key_questions": questions, "process": []Row{{"step": "Method", "description": "Method description.", "evidence": []Row{{"source_id": "S1", "quote": "The proposed method reduces memory use"}}}}, "contributions": []Row{{"title": "Contribution", "description": "Contribution description.", "evidence": []Row{{"source_id": "S1", "quote": "The proposed method reduces memory use"}}}}, "limitations": []string{"Limited evaluation coverage."}, "terms": []Row{{"term": "Grounding", "explanation": "A link to source text."}}, "suggested_questions": []string{"How does the method scale?"}}
	provider, _ := modelFixture(t, s, p, Encode(result))
	job := queuedJob(t, s, p, "report", Row{"provider_id": provider, "model": "test-model"}, Str(document["paper_id"]), Str(document["version_id"]), true)
	if e = ExecuteJob(context.Background(), s, job, "test-worker"); e != nil {
		t.Fatal(e)
	}
	paper, e := s.Paper(p.WorkspaceID, Str(document["paper_id"]))
	if e != nil {
		t.Fatal(e)
	}
	markdown := RenderPaperMarkdown(s, p.WorkspaceID, paper)
	for _, expected := range []string{"Overview retained in export.", "Limited evaluation coverage.", "Grounding", "How does the method scale?", "A useful motivation.", "第 1 页"} {
		if !strings.Contains(markdown, expected) {
			t.Fatalf("export omitted %q", expected)
		}
	}
}

func TestResearchDirectionsWorkerReturnsEditableGroundedText(t *testing.T) {
	s := testStore(t)
	p, _ := testUser(t, s, "directions@example.org", false)
	doc := seedDocument(t, s, p, "Memory-aware reading")
	provider, _ := modelFixture(t, s, p, `{"directions":[{"title":"Memory-efficient evidence retrieval","question":"How can exact citations be preserved under a lower memory budget?","keywords":["evidence retrieval","memory efficiency"],"rationale":"The paper describes a memory reduction with page citations.","source_ids":["S1"]}]}`)
	payload := Row{"provider_id": provider, "model": "test-model", "papers": []Row{{"id": doc["paper_id"], "active_version": doc["version_id"]}}, "paper_ids": []string{Str(doc["paper_id"])}, "question": "memory"}
	job := queuedJob(t, s, p, "research_directions", payload, "", "", true)
	if e := ExecuteJob(context.Background(), s, job, "test-worker"); e != nil {
		t.Fatal(e)
	}
	saved, e := s.One("SELECT state,result FROM jobs WHERE id=?", job["id"])
	if e != nil || saved["state"] != "succeeded" {
		t.Fatal(saved, e)
	}
	result := Object(saved["result"])
	if !strings.Contains(Str(result["text"]), "Memory-efficient evidence retrieval") || len(snapshotRows(result["sources"])) != 1 {
		t.Fatal("directions lost editable text or evidence", result)
	}
}
func TestInterruptedBillableJobRequiresAttention(t *testing.T) {
	s := testStore(t)
	p, _ := testUser(t, s, "lease@example.org", false)
	job := queuedJob(t, s, p, "report", Row{}, "p", "v", true)
	_, e := s.DB.Exec("UPDATE jobs SET lease_until=?,dispatch_started=1 WHERE id=?", Now()-1, job["id"])
	if e != nil {
		t.Fatal(e)
	}
	next, e := claimJob(s, "next", 2)
	if e != nil || next != nil {
		t.Fatal("replayed billed request", next, e)
	}
	saved, _ := s.One("SELECT state,error_code FROM jobs WHERE id=?", job["id"])
	if saved["state"] != "needs_attention" || saved["error_code"] != "dispatch_outcome_unknown" {
		t.Fatal(saved)
	}
}
func TestFastWriteBundleMatchesManifestContract(t *testing.T) {
	s := testStore(t)
	p, _ := testUser(t, s, "writer@example.org", false)
	doc := seedDocument(t, s, p, "中文论文")
	_, e := s.DB.Exec("INSERT INTO reading_annotations VALUES(?,?,?,?,?,?,?,?,?)", UID(), doc["paper_id"], doc["version_id"], 1, "The proposed method reduces memory use", "研究批注", "[]", Now(), Now())
	if e != nil {
		t.Fatal(e)
	}
	bundle, e := BuildFastWriteBundle(s, p.WorkspaceID, []string{Str(doc["paper_id"])})
	if e != nil {
		t.Fatal(e)
	}
	if len(Str(bundle["bundle_id"])) != 24 {
		t.Fatal("invalid bundle id")
	}
	manifest := bundle["manifest"].(Row)
	files := snapshotRows(bundle["files"])
	for _, entry := range snapshotRows(manifest["files"]) {
		found := false
		for _, file := range files {
			if strings.HasSuffix(Str(file["path"]), "/"+Str(entry["name"])) {
				found = true
				content := []byte(Str(file["content"]))
				sum := sha256.Sum256(content)
				if Str(entry["sha256"]) != hex.EncodeToString(sum[:]) || Num(entry["bytes"]) != float64(len(content)) {
					t.Fatal("manifest mismatch")
				}
			}
		}
		if !found {
			t.Fatal("missing bundle file")
		}
	}
	citations := snapshotRows(bundle["citations"])
	if len(citations) != 1 || citations[0]["task_id"] != doc["paper_id"] {
		t.Fatal("missing citation", citations)
	}
	again, e := BuildFastWriteBundle(s, p.WorkspaceID, []string{Str(doc["paper_id"])})
	if e != nil || again["bundle_id"] != bundle["bundle_id"] {
		t.Fatal("unchanged export not stable", e)
	}
}
func TestKnowledgeNotesEnforceScopeAndCopyEvidence(t *testing.T) {
	s := testStore(t)
	p, token := testUser(t, s, "notes@example.org", false)
	_, other := testUser(t, s, "notes-other@example.org", false)
	doc := seedDocument(t, s, p, "Notebook")
	a := readingApp(s)
	w := call(a, "POST", "/api/workspace-notes", token, p.CSRF, Row{"scope": "paper", "scope_id": doc["paper_id"], "title": "Comparison", "content": "Compare the memory footprint."})
	if w.Code != 201 {
		t.Fatal(w.Code, w.Body.String())
	}
	id := Str(decodeResponse(t, w)["id"])
	w = call(a, "GET", "/api/workspace-notes?scope=paper&scope_id="+Str(doc["paper_id"]), other, "", nil)
	if w.Code != 404 {
		t.Fatal("foreign notes visible")
	}
	w = call(a, "PUT", "/api/workspace-notes/"+id, token, p.CSRF, Row{"title": "Updated comparison", "content": "Include the accuracy metric."})
	if w.Code != 200 {
		t.Fatal(w.Code, w.Body.String())
	}
	w = call(a, "GET", "/api/workspace-notes?scope=paper&scope_id="+Str(doc["paper_id"]), token, "", nil)
	if !strings.Contains(w.Body.String(), "accuracy metric") {
		t.Fatal("note edit not durable")
	}
}
func TestFastNewsIntakeAttachesExistingMetadata(t *testing.T) {
	s := testStore(t)
	p, _ := testUser(t, s, "news@example.org", false)
	first, e := s.IntakeFastNews(p.WorkspaceID, Row{"title": "Original source title", "external_id": "news-42", "authors": "Author A;Author B", "year": 2026})
	if e != nil {
		t.Fatal(e)
	}
	second, e := s.IntakeFastNews(p.WorkspaceID, Row{"title": "Original source title", "external_id": "news-42"})
	if e != nil || first["id"] != second["id"] {
		t.Fatal("duplicate intake", e)
	}
	var imported Row
	e = s.Transaction(func(tx *sql.Tx) error {
		var err error
		imported, err = ingestDocument(tx, p.WorkspaceID, Row{"title": "PDF metadata title", "page_count": 1}, []Row{{"page": 1, "text": evidenceText}}, "files/source.pdf", Str(first["id"]))
		return err
	})
	if e != nil || imported["paper_id"] != first["id"] {
		t.Fatal(e)
	}
	paper, _ := s.Paper(p.WorkspaceID, Str(first["id"]))
	if paper["title"] != "Original source title" || Object(paper["metadata"])["awaiting_file"] != false {
		t.Fatal("intake metadata not retained", paper)
	}
}
func TestPDFNativeExtraction(t *testing.T) {
	program := os.Getenv("FASTREAD_PDFTOTEXT")
	if program == "" {
		program = "pdftotext"
	}
	if _, e := exec.LookPath(program); e != nil {
		t.Skip("poppler pdftotext not installed")
	}
	path := filepath.Join(t.TempDir(), "paper.pdf")
	if e := os.WriteFile(path, minimalPDF(evidenceText), 0600); e != nil {
		t.Fatal(e)
	}
	meta, pages, e := parsePDF(context.Background(), path)
	if e != nil {
		t.Fatal(e)
	}
	if len(pages) != 1 || !strings.Contains(Str(pages[0]["text"]), "reduces memory use") || Num(meta["page_count"]) != 1 {
		t.Fatal("PDF text/page boundary lost", pages)
	}
}
func minimalPDF(text string) []byte {
	objects := []string{"<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>", "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 1600 800] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"}
	stream := "BT /F1 12 Tf 40 750 Td (" + text + ") Tj ET"
	objects = append(objects, fmt.Sprintf("<< /Length %d >>\nstream\n%s\nendstream", len(stream), stream))
	var out strings.Builder
	out.WriteString("%PDF-1.4\n")
	offsets := []int{0}
	for i, obj := range objects {
		offsets = append(offsets, out.Len())
		fmt.Fprintf(&out, "%d 0 obj\n%s\nendobj\n", i+1, obj)
	}
	xref := out.Len()
	fmt.Fprintf(&out, "xref\n0 %d\n0000000000 65535 f \n", len(objects)+1)
	for _, offset := range offsets[1:] {
		fmt.Fprintf(&out, "%010d 00000 n \n", offset)
	}
	fmt.Fprintf(&out, "trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n", len(objects)+1, xref)
	return []byte(out.String())
}
func TestSearchAdapterParsingArxivMetadata(t *testing.T) {
	page := `<html><meta content="https://example.org/article.pdf" name="citation_pdf_url"></html>`
	if findPDFLink(page) != "https://example.org/article.pdf" {
		t.Fatal("citation PDF link not parsed")
	}
	jsonData := Encode(Row{"papers": []Row{{"title": "sample"}}, "status": Row{"available": true}})
	var decoded Row
	if e := json.Unmarshal([]byte(jsonData), &decoded); e != nil || len(snapshotRows(decoded["papers"])) != 1 {
		t.Fatal("cached search serialization broken")
	}
}
