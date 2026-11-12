package fastread

import (
	"database/sql"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

func readable(s *Store, p Principal, id string) (Row, error) {
	r, err := s.Paper(p.WorkspaceID, id)
	if err != nil {
		return nil, err
	}
	if Str(r["active_version"]) == "" {
		return nil, Error(409, "请先上传 PDF")
	}
	return r, nil
}

func readBody(r *http.Request) (Row, error) { v := Row{}; err := Decode(r, &v); return v, err }
func rowsJSON(rows []Row, names ...string) []Row {
	for _, row := range rows {
		for _, name := range names {
			if name == "rects" {
				row[name] = Array(row[name])
			} else {
				row[name] = Object(row[name])
			}
		}
	}
	return rows
}
func requiredText(v any, min, max int) (string, error) {
	s := strings.TrimSpace(Str(v))
	n := len([]rune(s))
	if n < min || n > max {
		return "", Error(422, fmt.Sprintf("文本长度应为 %d–%d 字", min, max))
	}
	return s, nil
}
func bodyModel(a *App, p Principal, body Row) (Row, error) {
	return a.ChooseModel(p, Str(body["provider_id"]), Str(body["model"]))
}
func jobResponse(w http.ResponseWriter, job Row, err error) error {
	if err != nil {
		return err
	}
	JSON(w, 202, JobView(job))
	return nil
}
func fileInside(root, relative string) (string, error) {
	base := filepath.Join(root, "files")
	full := filepath.Join(root, filepath.FromSlash(relative))
	rel, e := filepath.Rel(base, full)
	if e != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) || filepath.IsAbs(rel) {
		return "", Error(400, "无效文件路径")
	}
	return full, nil
}

func (a *App) RegisterReading() {
	s := a.Store
	a.Handle("GET /api/papers/{pid}/pages/{number}", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		paper, e := readable(s, p, r.PathValue("pid"))
		if e != nil {
			return e
		}
		version := r.URL.Query().Get("version")
		if version == "" {
			version = Str(paper["active_version"])
		}
		row, e := s.One("SELECT p.number,p.text FROM pages p JOIN document_versions v ON v.id=p.version_id WHERE v.paper_id=? AND v.id=? AND p.number=?", r.PathValue("pid"), version, r.PathValue("number"))
		if e != nil {
			return e
		}
		row["version_id"] = version
		JSON(w, 200, row)
		return nil
	})
	a.Handle("GET /api/papers/{pid}/file", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		paper, e := readable(s, p, r.PathValue("pid"))
		if e != nil {
			return e
		}
		version := r.URL.Query().Get("version")
		if version == "" {
			version = Str(paper["active_version"])
		}
		row, e := s.One("SELECT file_path FROM document_versions WHERE id=? AND paper_id=?", version, r.PathValue("pid"))
		if e != nil {
			return e
		}
		target, e := fileInside(s.Root, Str(row["file_path"]))
		if e != nil {
			return e
		}
		f, e := os.Open(target)
		if e != nil {
			return Error(404, "PDF 文件不存在")
		}
		defer f.Close()
		info, e := f.Stat()
		if e != nil {
			return e
		}
		w.Header().Set("Content-Type", "application/pdf")
		w.Header().Set("Content-Disposition", `inline; filename="paper.pdf"`)
		w.Header().Set("Cache-Control", "private, no-cache")
		w.Header().Set("ETag", fmt.Sprintf(`"%x-%x"`, info.ModTime().UnixNano(), info.Size()))
		http.ServeContent(w, r, "paper.pdf", info.ModTime(), f)
		return nil
	})
	a.Handle("POST /api/imports/url", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		body, e := readBody(r)
		if e != nil {
			return e
		}
		address, e := url.Parse(Str(body["url"]))
		if e != nil || address.Hostname() == "" || (address.Scheme != "http" && address.Scheme != "https") || address.User != nil {
			return Error(422, "需要论文的 HTTP/HTTPS 地址")
		}
		if e = a.validateImport(p, body); e != nil {
			return e
		}
		job, e := s.Enqueue(p, "import_url", body, r.Header.Get("Idempotency-Key"), "", "", Str(body["provider_id"]) != "")
		return jobResponse(w, job, e)
	})
	a.Handle("POST /api/imports/pdf", a.uploadPDF)
	a.Handle("POST /api/search", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		body, e := readBody(r)
		if e != nil {
			return e
		}
		q, e := requiredText(body["query"], 1, 300)
		if e != nil {
			return e
		}
		limit := int(Num(body["limit"]))
		if limit < 1 || limit > 50 {
			limit = 20
		}
		result := SearchPublic(r.Context(), s, q, limit)
		JSON(w, 200, result)
		return nil
	})
	a.Handle("POST /api/papers/{pid}/reports", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		return a.enqueuePaper(w, r, p, "report", true)
	})
	a.Handle("POST /api/papers/{pid}/index", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		return a.enqueuePaper(w, r, p, "index", false)
	})
	a.Handle("POST /api/papers/{pid}/neighbors", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		return a.enqueuePaper(w, r, p, "neighbors", false)
	})
	a.Handle("GET /api/papers/{pid}/reports", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		paper, e := s.Paper(p.WorkspaceID, r.PathValue("pid"))
		if e != nil {
			return e
		}
		rows, e := s.All("SELECT id,version_id,created FROM report_versions WHERE paper_id=? ORDER BY created DESC", paper["id"])
		if e != nil {
			return e
		}
		JSON(w, 200, Row{"items": rows, "active_version": paper["active_version"]})
		return nil
	})
	a.Handle("GET /api/papers/{pid}/reports/{rid}", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		paper, e := s.Paper(p.WorkspaceID, r.PathValue("pid"))
		if e != nil {
			return e
		}
		row, e := s.One("SELECT * FROM report_versions WHERE id=? AND paper_id=?", r.PathValue("rid"), paper["id"])
		if e != nil {
			return e
		}
		row["content"] = Object(row["content"])
		row["stale"] = row["version_id"] != paper["active_version"]
		JSON(w, 200, row)
		return nil
	})
	a.Handle("GET /api/papers/{pid}/export", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		paper, e := readable(s, p, r.PathValue("pid"))
		if e != nil {
			return e
		}
		text := RenderPaperMarkdown(s, p.WorkspaceID, paper)
		w.Header().Set("Content-Type", "text/markdown; charset=utf-8")
		w.Header().Set("Content-Disposition", `attachment; filename="reading-report.md"`)
		_, e = io.WriteString(w, text)
		return e
	})
	a.Handle("GET /api/papers/{pid}/conversations", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		if _, e := s.Paper(p.WorkspaceID, r.PathValue("pid")); e != nil {
			return e
		}
		rows, e := s.All("SELECT id,version_id,created FROM conversations WHERE paper_id=? AND workspace_id=? ORDER BY created DESC", r.PathValue("pid"), p.WorkspaceID)
		if e != nil {
			return e
		}
		JSON(w, 200, Row{"items": rows})
		return nil
	})
	a.Handle("POST /api/papers/{pid}/conversations", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		paper, e := readable(s, p, r.PathValue("pid"))
		if e != nil {
			return e
		}
		var row Row
		e = s.Transaction(func(tx *sql.Tx) error {
			var err error
			row, err = One(tx, "SELECT * FROM conversations WHERE paper_id=? AND workspace_id=? AND version_id=? ORDER BY created LIMIT 1", paper["id"], p.WorkspaceID, paper["active_version"])
			if err == nil {
				return nil
			}
			if err != sql.ErrNoRows {
				return err
			}
			id := UID()
			_, err = tx.Exec("INSERT INTO conversations VALUES(?,?,?,?,?)", id, p.WorkspaceID, paper["id"], paper["active_version"], Now())
			row = Row{"id": id, "version_id": paper["active_version"]}
			return err
		})
		if e != nil {
			return e
		}
		JSON(w, 201, row)
		return nil
	})
	a.Handle("GET /api/conversations/{cid}/messages", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		if _, e := s.One("SELECT id FROM conversations WHERE id=? AND workspace_id=?", r.PathValue("cid"), p.WorkspaceID); e != nil {
			return e
		}
		limit := queryInt(r, "limit", 50, 1, 100)
		offset := queryInt(r, "offset", 0, 0, 1000000)
		rows, e := s.All("SELECT * FROM messages WHERE conversation_id=? ORDER BY created,id LIMIT ? OFFSET ?", r.PathValue("cid"), limit, offset)
		if e != nil {
			return e
		}
		JSON(w, 200, Row{"items": rowsJSON(rows, "evidence")})
		return nil
	})
	a.Handle("POST /api/conversations/{cid}/messages", a.askPaper)
	a.Handle("GET /api/papers/{pid}/annotations", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		if _, e := s.Paper(p.WorkspaceID, r.PathValue("pid")); e != nil {
			return e
		}
		rows, e := s.All("SELECT * FROM reading_annotations WHERE paper_id=? AND version_id=? ORDER BY page,created", r.PathValue("pid"), r.URL.Query().Get("version"))
		if e != nil {
			return e
		}
		JSON(w, 200, Row{"items": rowsJSON(rows, "rects")})
		return nil
	})
	a.Handle("POST /api/papers/{pid}/annotations", a.createAnnotation)
	a.Handle("PATCH /api/papers/{pid}/annotations/{aid}", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		if _, e := s.Paper(p.WorkspaceID, r.PathValue("pid")); e != nil {
			return e
		}
		body, e := readBody(r)
		if e != nil {
			return e
		}
		note, e := requiredText(body["note"], 0, 10000)
		if e != nil {
			return e
		}
		result, e := s.DB.Exec("UPDATE reading_annotations SET note=?,updated=? WHERE id=? AND paper_id=?", note, Now(), r.PathValue("aid"), r.PathValue("pid"))
		if e != nil {
			return e
		}
		return changedJSON(w, result)
	})
	a.Handle("DELETE /api/papers/{pid}/annotations/{aid}", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		if _, e := s.Paper(p.WorkspaceID, r.PathValue("pid")); e != nil {
			return e
		}
		result, e := s.DB.Exec("DELETE FROM reading_annotations WHERE id=? AND paper_id=?", r.PathValue("aid"), r.PathValue("pid"))
		if e != nil {
			return e
		}
		return changedJSON(w, result)
	})
	a.Handle("GET /api/papers/{pid}/neighbors", a.listNeighbors)
}

func queryInt(r *http.Request, name string, fallback, min, max int) int {
	v, e := strconv.Atoi(r.URL.Query().Get(name))
	if e != nil {
		return fallback
	}
	if v < min {
		return min
	}
	if v > max {
		return max
	}
	return v
}
func changedJSON(w http.ResponseWriter, result sql.Result) error {
	n, e := result.RowsAffected()
	if e != nil {
		return e
	}
	if n == 0 {
		return sql.ErrNoRows
	}
	JSON(w, 200, Row{"ok": true})
	return nil
}
func (a *App) validateImport(p Principal, b Row) error {
	if id := Str(b["knowledge_id"]); id != "" {
		if _, e := a.Store.One("SELECT id FROM knowledge_bases WHERE id=? AND workspace_id=?", id, p.WorkspaceID); e != nil {
			return e
		}
	}
	if Str(b["provider_id"]) != "" || Str(b["model"]) != "" {
		v, e := bodyModel(a, p, b)
		if e != nil {
			return e
		}
		b["provider_id"] = v["provider_id"]
		b["model"] = v["model"]
	}
	return nil
}
func (a *App) uploadPDF(w http.ResponseWriter, r *http.Request, p Principal) error {
	r.Body = http.MaxBytesReader(w, r.Body, 65<<20)
	if e := r.ParseMultipartForm(2 << 20); e != nil {
		return Error(413, "PDF 不能超过 64 MB")
	}
	defer r.MultipartForm.RemoveAll()
	body := Row{"provider_id": r.FormValue("provider_id"), "model": r.FormValue("model"), "knowledge_id": r.FormValue("knowledge_id"), "organize": r.FormValue("organize") != "false"}
	if id := r.FormValue("paper_id"); id != "" {
		if _, e := a.Store.Paper(p.WorkspaceID, id); e != nil {
			return e
		}
		body["paper_id"] = id
	}
	if e := a.validateImport(p, body); e != nil {
		return e
	}
	key := r.Header.Get("Idempotency-Key")
	if key == "" || len(key) > 160 {
		return Error(400, "需要有效 Idempotency-Key")
	}
	old, e := a.Store.One("SELECT * FROM jobs WHERE workspace_id=? AND dedupe_key=?", p.WorkspaceID, key)
	if e == nil {
		oldBody := Object(old["payload"])
		if Str(old["kind"]) != "import_pdf" {
			return Error(409, "idempotency_key_conflict")
		}
		for k, v := range body {
			if Encode(v) != Encode(oldBody[k]) {
				return Error(409, "idempotency_key_conflict")
			}
		}
		return jobResponse(w, old, nil)
	}
	file, header, e := r.FormFile("file")
	if e != nil {
		return Error(422, "请选择 PDF 文件")
	}
	defer file.Close()
	prefix := make([]byte, 5)
	if _, e = io.ReadFull(file, prefix); e != nil || string(prefix) != "%PDF-" {
		return Error(415, "文件不是 PDF")
	}
	relative := "files/" + UID() + ".pdf"
	target := filepath.Join(a.Store.Root, filepath.FromSlash(relative))
	out, e := os.OpenFile(target, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if e != nil {
		return e
	}
	ok := false
	defer func() {
		out.Close()
		if !ok {
			os.Remove(target)
		}
	}()
	if _, e = out.Write(prefix); e != nil {
		return e
	}
	n, e := io.Copy(out, io.LimitReader(file, 64<<20))
	if e != nil {
		return e
	}
	if n+5 > 64<<20 {
		return Error(413, "PDF 不能超过 64 MB")
	}
	if e = out.Close(); e != nil {
		return e
	}
	body["path"] = relative
	body["filename"] = filepath.Base(header.Filename)
	job, e := a.Store.Enqueue(p, "import_pdf", body, key, "", "", Str(body["provider_id"]) != "")
	if e != nil {
		return e
	}
	ok = true
	return jobResponse(w, job, nil)
}
func (a *App) enqueuePaper(w http.ResponseWriter, r *http.Request, p Principal, kind string, billable bool) error {
	paper, e := readable(a.Store, p, r.PathValue("pid"))
	if e != nil {
		return e
	}
	body := Row{}
	if billable {
		body, e = readBody(r)
		if e != nil {
			return e
		}
		body, e = bodyModel(a, p, body)
		if e != nil {
			return e
		}
	}
	job, e := a.Store.Enqueue(p, kind, body, r.Header.Get("Idempotency-Key"), Str(paper["id"]), Str(paper["active_version"]), billable)
	return jobResponse(w, job, e)
}
func (a *App) askPaper(w http.ResponseWriter, r *http.Request, p Principal) error {
	conversation, e := a.Store.One("SELECT * FROM conversations WHERE id=? AND workspace_id=?", r.PathValue("cid"), p.WorkspaceID)
	if e != nil {
		return e
	}
	body, e := readBody(r)
	if e != nil {
		return e
	}
	content, e := requiredText(body["content"], 1, 10000)
	if e != nil {
		return e
	}
	payload, e := bodyModel(a, p, body)
	if e != nil {
		return e
	}
	payload["content"] = content
	var job Row
	e = a.Store.Transaction(func(tx *sql.Tx) error {
		old, err := One(tx, "SELECT id FROM jobs WHERE workspace_id=? AND dedupe_key=?", p.WorkspaceID, r.Header.Get("Idempotency-Key"))
		if err != nil && err != sql.ErrNoRows {
			return err
		}
		if old == nil {
			pending, err := One(tx, "SELECT id FROM jobs WHERE resource_id=? AND kind='chat' AND state IN ('queued','running')", conversation["id"])
			if err == nil && pending != nil {
				return Error(409, "请等待上一条回答完成")
			}
		}
		job, err = EnqueueTx(tx, p, "chat", payload, r.Header.Get("Idempotency-Key"), Str(conversation["id"]), Str(conversation["version_id"]), true)
		if err != nil {
			return err
		}
		_, err = tx.Exec("INSERT OR IGNORE INTO messages VALUES(?,?,?,?,?,?,?)", UID(), conversation["id"], "user", content, "{}", job["id"], Now())
		return err
	})
	return jobResponse(w, job, e)
}
func (a *App) createAnnotation(w http.ResponseWriter, r *http.Request, p Principal) error {
	if _, e := a.Store.Paper(p.WorkspaceID, r.PathValue("pid")); e != nil {
		return e
	}
	b, e := readBody(r)
	if e != nil {
		return e
	}
	quote, e := requiredText(b["quote"], 0, 10000)
	if e != nil {
		return e
	}
	note, e := requiredText(b["note"], 0, 10000)
	if e != nil {
		return e
	}
	if quote == "" && note == "" {
		return Error(422, "请选择原文或填写批注")
	}
	if _, e = a.Store.One("SELECT p.number FROM pages p JOIN document_versions v ON v.id=p.version_id WHERE v.paper_id=? AND v.id=? AND p.number=?", r.PathValue("pid"), b["version_id"], b["page"]); e != nil {
		return e
	}
	rects, ok := b["rects"].([]any)
	if !ok {
		rects = []any{}
	}
	if len(rects) > 200 {
		return Error(422, "批注区域过多")
	}
	for _, v := range rects {
		rect, ok := v.(map[string]any)
		if !ok {
			return Error(422, "无效批注区域")
		}
		x, y, width, height := Num(rect["x"]), Num(rect["y"]), Num(rect["width"]), Num(rect["height"])
		if x < 0 || y < 0 || width <= 0 || height <= 0 || x+width > 1.001 || y+height > 1.001 {
			return Error(422, "批注位置超出页面")
		}
	}
	id := UID()
	_, e = a.Store.DB.Exec("INSERT INTO reading_annotations VALUES(?,?,?,?,?,?,?,?,?)", id, r.PathValue("pid"), b["version_id"], b["page"], quote, note, Encode(rects), Now(), Now())
	if e != nil {
		return e
	}
	JSON(w, 201, Row{"id": id})
	return nil
}
func (a *App) listNeighbors(w http.ResponseWriter, r *http.Request, p Principal) error {
	paper, e := a.Store.Paper(p.WorkspaceID, r.PathValue("pid"))
	if e != nil {
		return e
	}
	snapshot := Row{"papers": []Row{}, "anchors": []Row{}, "sources": Row{}, "has_snapshot": false}
	job, e := a.Store.One("SELECT result FROM jobs WHERE workspace_id=? AND resource_id=? AND version_id=? AND kind='neighbors' AND state='succeeded' ORDER BY updated DESC LIMIT 1", p.WorkspaceID, paper["id"], paper["active_version"])
	if e == nil {
		snapshot = Object(job["result"])
		snapshot["has_snapshot"] = true
	}
	local, e := a.Store.All("SELECT DISTINCT p.id,p.title,p.metadata,p.active_version FROM papers p JOIN paper_tags t ON t.paper_id=p.id WHERE p.workspace_id=? AND p.archived=0 AND p.id<>? AND t.tag IN (SELECT tag FROM paper_tags WHERE paper_id=?)", p.WorkspaceID, paper["id"], paper["id"])
	if e != nil {
		return e
	}
	tags, e := a.Store.All("SELECT tag FROM paper_tags WHERE paper_id=? ORDER BY tag", paper["id"])
	if e != nil {
		return e
	}
	tagList := []string{}
	for _, t := range tags {
		tagList = append(tagList, Str(t["tag"]))
	}
	snapshot["paper_tags"] = tagList
	items := []any{}
	for _, row := range local {
		meta := Object(row["metadata"])
		row["authors"] = meta["authors"]
		row["year"] = meta["year"]
		row["local_id"] = row["id"]
		row["discovery_sources"] = []string{"资料库"}
		shared, _ := a.Store.All("SELECT tag FROM paper_tags WHERE paper_id=? AND tag IN (SELECT tag FROM paper_tags WHERE paper_id=?) ORDER BY tag", row["id"], paper["id"])
		values := []string{}
		for _, t := range shared {
			values = append(values, Str(t["tag"]))
		}
		row["shared_tags"] = values
		row["tags"] = values
		row["relevance_score"] = len(values)
		row["matched_anchor_ids"] = []string{}
		items = append(items, row)
	}
	if remote, ok := snapshot["papers"].([]any); ok {
		items = append(items, remote...)
	}
	snapshot["papers"] = items
	JSON(w, 200, snapshot)
	return nil
}

func RenderPaperMarkdown(s *Store, workspace string, paper Row) string {
	var out strings.Builder
	fmt.Fprintf(&out, "# %s\n\n", Str(paper["title"]))
	metadata := Object(paper["metadata"])
	if link := Str(metadata["url"]); link != "" {
		fmt.Fprintf(&out, "来源：%s\n\n", link)
	}
	if Str(paper["summary"]) != "" {
		fmt.Fprintf(&out, "## 个人总结\n\n%s\n\n", Str(paper["summary"]))
	}
	report, e := s.One("SELECT content FROM report_versions WHERE paper_id=? AND version_id=? ORDER BY created DESC LIMIT 1", paper["id"], paper["active_version"])
	if e == nil {
		value := Object(report["content"])
		if generated := Str(value["generated_at"]); generated != "" {
			fmt.Fprintf(&out, "报告生成时间：%s\n\n", generated)
		}
		if summary := Str(value["executive_summary"]); summary != "" {
			fmt.Fprintf(&out, "## 报告总览\n\n%s\n\n", summary)
		}
		for _, section := range []struct{ key, title string }{{"key_questions", "关键问题"}, {"process", "方法过程"}, {"contributions", "主要贡献"}} {
			fmt.Fprintf(&out, "## %s\n\n", section.title)
			items, _ := value[section.key].([]any)
			for _, v := range items {
				item, ok := v.(map[string]any)
				if !ok {
					continue
				}
				title := Str(item["question"])
				if title == "" {
					title = Str(item["step"])
				}
				if title == "" {
					title = Str(item["title"])
				}
				answer := Str(item["answer"])
				if answer == "" {
					answer = Str(item["description"])
				}
				fmt.Fprintf(&out, "### %s\n\n%s\n\n", title, answer)
				if why := Str(item["why_it_matters"]); why != "" {
					fmt.Fprintf(&out, "**为什么重要：** %s\n\n", why)
				}
				evidence, _ := item["evidence"].([]any)
				for _, raw := range evidence {
					ev, ok := raw.(map[string]any)
					if ok {
						page := ev["page_start"]
						if page == nil {
							page = ev["page"]
						}
						fmt.Fprintf(&out, "> 第 %v 页：%s\n\n", page, Str(ev["exact_quote"]))
					}
				}
			}
		}
		if limits := stringList(value["limitations"]); len(limits) > 0 {
			out.WriteString("## 局限与证据边界\n\n")
			for _, limit := range limits {
				fmt.Fprintf(&out, "- %s\n", limit)
			}
			out.WriteString("\n")
		}
		if terms := snapshotRows(value["terms"]); len(terms) > 0 {
			out.WriteString("## 关键术语\n\n")
			for _, term := range terms {
				fmt.Fprintf(&out, "- **%s：** %s\n", Str(term["term"]), Str(term["explanation"]))
			}
			out.WriteString("\n")
		}
		if questions := stringList(value["suggested_questions"]); len(questions) > 0 {
			out.WriteString("## 建议继续追问\n\n")
			for _, question := range questions {
				fmt.Fprintf(&out, "- %s\n", question)
			}
			out.WriteString("\n")
		}
	}
	annotations, _ := s.All("SELECT page,quote,note FROM reading_annotations WHERE paper_id=? AND version_id=? ORDER BY page,created", paper["id"], paper["active_version"])
	if len(annotations) > 0 {
		out.WriteString("## 原文批注\n\n")
		for _, ev := range annotations {
			fmt.Fprintf(&out, "> 第 %v 页：%s\n\n%s\n\n", ev["page"], Str(ev["quote"]), Str(ev["note"]))
		}
	}
	return out.String()
}
