package fastread

import (
	"archive/zip"
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"sort"
	"strconv"
	"strings"
)

func (a *App) RegisterIntegrations() {
	a.Handle("POST /api/integrations/fastnews/intake", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		body, e := readBody(r)
		if e != nil {
			return e
		}
		result, e := a.Store.IntakeFastNews(p.WorkspaceID, body)
		if e != nil {
			return e
		}
		JSON(w, 200, result)
		return nil
	})
	a.Handle("POST /api/integrations/fastnews", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		body, e := readBody(r)
		if e != nil {
			return e
		}
		address, e := url.Parse(Str(body["url"]))
		if e != nil || address.Hostname() == "" || (address.Scheme != "https" && address.Scheme != "http") {
			return Error(422, "需要论文 HTTP/HTTPS 地址")
		}
		body["source"] = "fastnews"
		if e = a.validateImport(p, body); e != nil {
			return e
		}
		job, e := a.Store.Enqueue(p, "import_url", body, r.Header.Get("Idempotency-Key"), "", "", Str(body["provider_id"]) != "")
		if e != nil {
			return e
		}
		JSON(w, 202, Row{"job": JobView(job), "status_url": "/api/jobs/" + Str(job["id"]), "open_url": "/?job=" + Str(job["id"])})
		return nil
	})
	a.Handle("POST /api/integrations/fastwrite/export", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		body, e := readBody(r)
		if e != nil {
			return e
		}
		ids := stringList(body["paper_ids"])
		if len(ids) < 1 || len(ids) > 100 {
			return Error(422, "请选择 1–100 篇论文")
		}
		bundle, e := BuildFastWriteBundle(a.Store, p.WorkspaceID, ids)
		if e != nil {
			return e
		}
		format := Str(body["format"])
		if format == "zip" {
			w.Header().Set("Content-Type", "application/zip")
			w.Header().Set("Content-Disposition", `attachment; filename="fastread-evidence.zip"`)
			writer := zip.NewWriter(w)
			for _, file := range snapshotRows(bundle["files"]) {
				entry, e := writer.Create(Str(file["path"]))
				if e != nil {
					return e
				}
				if _, e = io.WriteString(entry, Str(file["content"])); e != nil {
					return e
				}
			}
			return writer.Close()
		}
		JSON(w, 200, bundle)
		return nil
	})
	a.Handle("POST /api/research/directions", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		body, e := readBody(r)
		if e != nil {
			return e
		}
		ids := stringList(body["paper_ids"])
		if len(ids) < 1 || len(ids) > 30 {
			return Error(422, "请选择 1–30 篇论文")
		}
		sort.Strings(ids)
		payload, e := bodyModel(a, p, body)
		if e != nil {
			return e
		}
		question, e := requiredText(body["question"], 0, 2000)
		if e != nil {
			return e
		}
		papers := []Row{}
		for _, id := range ids {
			paper, e := readable(a.Store, p, id)
			if e != nil {
				return e
			}
			papers = append(papers, Row{"id": id, "active_version": paper["active_version"]})
		}
		payload["papers"] = papers
		payload["paper_ids"] = ids
		payload["question"] = question
		job, e := a.Store.Enqueue(p, "research_directions", payload, r.Header.Get("Idempotency-Key"), "", "", true)
		return jobResponse(w, job, e)
	})
}

func (s *Store) IntakeFastNews(workspace string, body Row) (Row, error) {
	title, e := requiredText(body["title"], 1, 300)
	if e != nil {
		return nil, e
	}
	address := Str(body["url"])
	if address != "" {
		u, err := url.Parse(address)
		if err != nil || u.Hostname() == "" || (u.Scheme != "http" && u.Scheme != "https") || u.User != nil {
			address = ""
		}
	}
	external := trimRunes(strings.TrimSpace(Str(body["external_id"])), 200)
	identity := "fastnews:" + external
	if external == "" {
		source := address
		if source == "" {
			source = title
			identity = "fastnews-title:"
		} else {
			identity = "fastnews-url:"
		}
		digest := sha256.Sum256([]byte(source))
		identity += hex.EncodeToString(digest[:])[:32]
	}
	authors := stringList(body["authors"])
	if len(authors) == 0 {
		for _, name := range strings.FieldsFunc(Str(body["authors"]), func(r rune) bool { return r == ';' || r == '；' || r == '、' }) {
			if name = strings.TrimSpace(name); name != "" {
				authors = append(authors, name)
			}
		}
	}
	var result Row
	e = s.Transaction(func(tx *sql.Tx) error {
		existing, err := One(tx, "SELECT * FROM papers WHERE workspace_id=? AND identity=?", workspace, identity)
		if err != nil && err != sql.ErrNoRows {
			return err
		}
		id := UID()
		meta := Row{}
		awaiting := true
		if existing != nil {
			id = Str(existing["id"])
			meta = Object(existing["metadata"])
			awaiting = Str(existing["active_version"]) == ""
		}
		meta["source"] = "fastnews"
		meta["title"] = title
		meta["authors"] = authors
		meta["abstract"] = trimRunes(Str(body["abstract"]), 800)
		meta["url"] = address
		meta["venue"] = trimRunes(Str(body["venue"]), 80)
		meta["year"] = body["year"]
		meta["external_id"] = external
		meta["awaiting_file"] = awaiting
		if meta["page_count"] == nil {
			meta["page_count"] = 0
		}
		if existing == nil {
			_, err = tx.Exec("INSERT INTO papers(id,workspace_id,identity,title,metadata,created) VALUES(?,?,?,?,?,?)", id, workspace, identity, title, Encode(meta), Now())
		} else {
			_, err = tx.Exec("UPDATE papers SET archived=0,title=?,metadata=? WHERE id=?", title, Encode(meta), id)
		}
		if err != nil {
			return err
		}
		if _, err = tx.Exec("INSERT OR IGNORE INTO paper_identities VALUES(?,?,?)", workspace, identity, id); err != nil {
			return err
		}
		result = Row{"id": id, "title": title, "awaiting_file": awaiting, "created": existing == nil}
		return nil
	})
	return result, e
}

func BuildFastWriteBundle(s *Store, workspace string, ids []string) (Row, error) {
	papers := []Row{}
	citations := []Row{}
	var evidence, notes, bib strings.Builder
	for i, id := range ids {
		paper, e := s.Paper(workspace, id)
		if e != nil {
			return nil, e
		}
		meta := Object(paper["metadata"])
		record := Row{"id": id, "title": paper["title"], "authors": stringList(meta["authors"]), "document_version_id": paper["active_version"]}
		if doi := Str(meta["doi"]); doi != "" {
			record["doi"] = doi
		}
		year, _ := strconv.Atoi(Str(meta["year"]))
		if year > 0 {
			record["year"] = year
		}
		if version, e := s.One("SELECT fingerprint FROM document_versions WHERE id=? AND paper_id=?", paper["active_version"], id); e == nil {
			record["content_hash"] = version["fingerprint"]
		}
		papers = append(papers, record)
		evidence.WriteString(RenderPaperMarkdown(s, workspace, paper))
		evidence.WriteString("\n---\n\n")
		key := fmt.Sprintf("fastread%d", i+1)
		authors := stringList(meta["authors"])
		fmt.Fprintf(&bib, "@article{%s,\n  title = {%s},\n  author = {%s}", key, bibEscape(Str(paper["title"])), bibEscape(strings.Join(authors, " and ")))
		if year > 0 {
			fmt.Fprintf(&bib, ",\n  year = {%d}", year)
		}
		if doi := Str(meta["doi"]); doi != "" {
			fmt.Fprintf(&bib, ",\n  doi = {%s}", bibEscape(doi))
		}
		if link := Str(meta["url"]); link != "" {
			fmt.Fprintf(&bib, ",\n  url = {%s}", bibEscape(link))
		}
		bib.WriteString("\n}\n\n")
		seen := map[string]bool{}
		addCitation := func(page int, quote, role, note string) {
			if page < 1 || quote == "" {
				return
			}
			row, e := s.One("SELECT text FROM pages WHERE version_id=? AND number=?", paper["active_version"], page)
			if e != nil {
				return
			}
			actual, located := locatedQuote(Str(row["text"]), quote)
			if !located {
				return
			}
			quote = actual
			key := fmt.Sprint(page) + ":" + quote
			if seen[key] {
				return
			}
			seen[key] = true
			citations = append(citations, Row{"task_id": id, "page": page, "exact_quote": quote, "role": role, "note": note, "source_hash": record["content_hash"], "document_version_id": paper["active_version"]})
		}
		if report, e := s.One("SELECT content FROM report_versions WHERE paper_id=? AND version_id=? ORDER BY created DESC LIMIT 1", id, paper["active_version"]); e == nil {
			content := Object(report["content"])
			for _, section := range []string{"key_questions", "process", "contributions"} {
				for _, item := range snapshotRows(content[section]) {
					for _, ev := range snapshotRows(item["evidence"]) {
						page := int(Num(ev["page_start"]))
						if page == 0 {
							page = int(Num(ev["page"]))
						}
						addCitation(page, Str(ev["exact_quote"]), section, "")
					}
				}
			}
		}
		annotations, e := s.All("SELECT page,quote,note FROM reading_annotations WHERE paper_id=? AND version_id=? ORDER BY page,created", id, paper["active_version"])
		if e != nil {
			return nil, e
		}
		for _, annotation := range annotations {
			addCitation(int(Num(annotation["page"])), Str(annotation["quote"]), "user_annotation", Str(annotation["note"]))
		}
		userNotes, e := s.All("SELECT title,content FROM notebook_notes WHERE workspace_id=? AND scope='paper' AND scope_id=? ORDER BY created", workspace, id)
		if e != nil {
			return nil, e
		}
		if len(userNotes) > 0 {
			fmt.Fprintf(&notes, "# %s\n\n", Str(paper["title"]))
			for _, note := range userNotes {
				fmt.Fprintf(&notes, "## %s\n\n%s\n\n", Str(note["title"]), Str(note["content"]))
			}
		}
	}
	identity := sha256.Sum256([]byte(Encode(Row{"papers": papers, "citations": citations, "evidence": evidence.String(), "notes": notes.String()})))
	bundleID := hex.EncodeToString(identity[:])[:24]
	citationText := Encode(Row{"version": 1, "bundle_id": bundleID, "papers": papers, "citations": citations}) + "\n"
	contents := []Row{{"name": "evidence.md", "content": evidence.String()}, {"name": "citations.json", "content": citationText}, {"name": "references.bib", "content": bib.String()}, {"name": "user-notes.md", "content": notes.String()}}
	entries := []Row{}
	files := []Row{}
	directory := "references/fastread/" + bundleID + "/"
	for _, file := range contents {
		text := Str(file["content"])
		digest := sha256.Sum256([]byte(text))
		entries = append(entries, Row{"name": file["name"], "sha256": hex.EncodeToString(digest[:]), "bytes": len([]byte(text))})
		files = append(files, Row{"path": directory + Str(file["name"]), "content": text})
	}
	manifest := Row{"version": 1, "bundle_id": bundleID, "immutable": true, "files": entries}
	manifestPath := directory + "manifest.json"
	files = append(files, Row{"path": manifestPath, "content": Encode(manifest) + "\n"})
	return Row{"bundle_id": bundleID, "manifest_path": manifestPath, "manifest": manifest, "files": files, "papers": papers, "citations": citations}, nil
}
func bibEscape(s string) string {
	return strings.NewReplacer("\\", `\textbackslash{}`, "{", `\{`, "}", `\}`, "%", `\%`, "&", `\&`, "#", `\#`, "_", `\_`).Replace(s)
}

func executeDirections(ctx context.Context, s *Store, job Row, owner string, payload Row) error {
	snapshots := snapshotRows(payload["papers"])
	chunks, e := sourceExcerpts(s, Str(job["workspace_id"]), snapshots, Str(payload["question"]))
	if e != nil {
		return e
	}
	if len(chunks) == 0 {
		return errors.New("no source text")
	}
	result, e := completeModel(ctx, s, job, owner, payload, `依据所选论文提炼 2–4 个值得持续跟踪的科研方向。每个方向给出具体研究问题、检索关键词和来自论文的理由。返回 {"directions":[{"title":"方向标题","question":"具体问题","keywords":["英文关键词"],"rationale":"依据与联系","source_ids":["S1"]}]}。仅使用提供的原文，来源编号必须存在。`, Row{"question": payload["question"], "sources": chunks})
	if e != nil {
		return e
	}
	directions := snapshotRows(result["directions"])
	if len(directions) == 0 || len(directions) > 8 {
		return errors.New("invalid directions")
	}
	var text strings.Builder
	allSources := []Row{}
	seen := map[string]bool{}
	for _, direction := range directions {
		title, e := requiredText(direction["title"], 1, 160)
		if e != nil {
			return e
		}
		question, e := requiredText(direction["question"], 1, 1000)
		if e != nil {
			return e
		}
		sources, e := selectedSources(direction, chunks)
		if e != nil {
			return e
		}
		fmt.Fprintf(&text, "## %s\n\n%s\n\n关键词：%s\n\n%s\n\n", title, question, strings.Join(stringList(direction["keywords"]), ", "), Str(direction["rationale"]))
		direction["sources"] = sources
		for _, source := range sources {
			if !seen[Str(source["id"])] {
				allSources = append(allSources, source)
				seen[Str(source["id"])] = true
			}
		}
	}
	result["text"] = text.String()
	result["sources"] = allSources
	result["paper_ids"] = payload["paper_ids"]
	return s.Transaction(func(tx *sql.Tx) error {
		if e := assertLease(tx, job, owner); e != nil {
			return e
		}
		return completeJob(tx, job, result)
	})
}
