package fastread

import (
	"database/sql"
	"net/http"
	"sort"
	"strings"
)

func normalizeTags(v any) ([]string, error) {
	items, ok := v.([]any)
	if !ok || len(items) > 20 {
		return nil, Error(422, "标签最多 20 个")
	}
	seen := map[string]bool{}
	tags := []string{}
	for _, raw := range items {
		value, ok := raw.(string)
		if !ok {
			return nil, Error(422, "标签须为文本")
		}
		value = strings.ToLower(strings.TrimSpace(value))
		if len([]rune(value)) < 1 || len([]rune(value)) > 40 {
			return nil, Error(422, "标签需为 1–40 字的文本")
		}
		if !seen[value] {
			tags = append(tags, value)
			seen[value] = true
		}
	}
	return tags, nil
}
func stringList(v any) []string {
	items, _ := v.([]any)
	result := []string{}
	seen := map[string]bool{}
	for _, raw := range items {
		value := Str(raw)
		if value != "" && !seen[value] {
			result = append(result, value)
			seen[value] = true
		}
	}
	return result
}
func (a *App) ownedBook(p Principal, id string) (Row, error) {
	return a.Store.One("SELECT * FROM knowledge_bases WHERE id=? AND workspace_id=?", id, p.WorkspaceID)
}
func DecoratePapers(s *Store, rows []Row) ([]Row, error) {
	for _, row := range rows {
		tags, e := s.All("SELECT tag FROM paper_tags WHERE paper_id=? ORDER BY tag", row["id"])
		if e != nil {
			return nil, e
		}
		values := []string{}
		for _, tag := range tags {
			values = append(values, Str(tag["tag"]))
		}
		row["tags"] = values
		books, e := s.All("SELECT k.id,k.name FROM knowledge_bases k JOIN knowledge_papers p ON p.knowledge_id=k.id WHERE p.paper_id=?", row["id"])
		if e != nil {
			return nil, e
		}
		row["knowledge_bases"] = books
		row["principle"] = ""
		row["principle_evidence"] = []any{}
		if insight, e := s.One("SELECT principle,evidence FROM paper_insights WHERE paper_id=? AND version_id=?", row["id"], row["active_version"]); e == nil {
			row["principle"] = insight["principle"]
			row["principle_evidence"] = Array(insight["evidence"])
		}
	}
	return rows, nil
}

func (a *App) RegisterKnowledge() {
	s := a.Store
	a.Handle("GET /api/knowledge-bases", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		rows, e := s.All("SELECT k.*,(SELECT count(*) FROM knowledge_papers kp JOIN papers p ON p.id=kp.paper_id WHERE kp.knowledge_id=k.id AND p.archived=0) paper_count FROM knowledge_bases k WHERE workspace_id=? ORDER BY name", p.WorkspaceID)
		if e != nil {
			return e
		}
		for _, b := range rows {
			b["questions_status"] = "not_started"
			if strings.TrimSpace(Str(b["description"])) != "" {
				b["questions_status"] = "ready"
			} else if job, e := s.One("SELECT state FROM jobs WHERE workspace_id=? AND resource_id=? AND kind='book_questions' ORDER BY created DESC LIMIT 1", p.WorkspaceID, b["id"]); e == nil {
				b["questions_status"] = job["state"]
			}
		}
		JSON(w, 200, Row{"items": rows})
		return nil
	})
	a.Handle("POST /api/knowledge-bases", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		body, e := readBody(r)
		if e != nil {
			return e
		}
		name, e := requiredText(body["name"], 1, 80)
		if e != nil {
			return e
		}
		description, e := requiredText(body["description"], 0, 1000)
		if e != nil {
			return e
		}
		_, e = s.DB.Exec("INSERT OR IGNORE INTO knowledge_bases VALUES(?,?,?,?,?)", UID(), p.WorkspaceID, name, description, Now())
		if e != nil {
			return e
		}
		book, e := s.One("SELECT * FROM knowledge_bases WHERE workspace_id=? AND name=?", p.WorkspaceID, name)
		if e != nil {
			return e
		}
		a.scheduleQuestions(p, Str(book["id"]))
		JSON(w, 201, book)
		return nil
	})
	a.Handle("GET /api/knowledge-bases/{bid}", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		book, e := a.ownedBook(p, r.PathValue("bid"))
		if e != nil {
			return e
		}
		rows, e := s.All("SELECT p.id,p.title,p.metadata,p.active_version,k.origin FROM papers p JOIN knowledge_papers k ON k.paper_id=p.id WHERE k.knowledge_id=? AND p.workspace_id=? AND p.archived=0 ORDER BY p.created DESC", book["id"], p.WorkspaceID)
		if e != nil {
			return e
		}
		for _, row := range rows {
			row["metadata"] = Object(row["metadata"])
		}
		rows, e = DecoratePapers(s, rows)
		if e != nil {
			return e
		}
		book["papers"] = rows
		JSON(w, 200, book)
		return nil
	})
	a.Handle("PATCH /api/knowledge-bases/{bid}", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		if _, e := a.ownedBook(p, r.PathValue("bid")); e != nil {
			return e
		}
		body, e := readBody(r)
		if e != nil {
			return e
		}
		name, e := requiredText(body["name"], 1, 80)
		if e != nil {
			return e
		}
		description, e := requiredText(body["description"], 0, 1000)
		if e != nil {
			return e
		}
		result, e := s.DB.Exec("UPDATE knowledge_bases SET name=?,description=? WHERE id=? AND workspace_id=?", name, description, r.PathValue("bid"), p.WorkspaceID)
		if e != nil {
			return e
		}
		return changedJSON(w, result)
	})
	a.Handle("POST /api/knowledge-bases/{bid}/questions", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		if _, e := a.ownedBook(p, r.PathValue("bid")); e != nil {
			return e
		}
		job, e := a.scheduleQuestions(p, r.PathValue("bid"))
		if e != nil {
			return e
		}
		var result any
		if job != nil {
			result = JobView(job)
		}
		JSON(w, 202, Row{"job": result})
		return nil
	})
	a.Handle("POST /api/knowledge-bases/{bid}/papers", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		if _, e := a.ownedBook(p, r.PathValue("bid")); e != nil {
			return e
		}
		body, e := readBody(r)
		if e != nil {
			return e
		}
		ids := stringList(body["paper_ids"])
		if len(ids) < 1 || len(ids) > 100 {
			return Error(422, "请选择 1–100 篇论文")
		}
		for _, id := range ids {
			if _, e = s.Paper(p.WorkspaceID, id); e != nil {
				return e
			}
		}
		e = s.Transaction(func(tx *sql.Tx) error {
			for _, id := range ids {
				if _, err := tx.Exec("INSERT INTO knowledge_papers VALUES(?,?,'manual',?) ON CONFLICT(knowledge_id,paper_id) DO UPDATE SET origin='manual'", r.PathValue("bid"), id, Now()); err != nil {
					return err
				}
			}
			return nil
		})
		if e != nil {
			return e
		}
		a.scheduleQuestions(p, r.PathValue("bid"))
		JSON(w, 200, Row{"added": len(ids)})
		return nil
	})
	a.Handle("DELETE /api/knowledge-bases/{bid}/papers/{pid}", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		if _, e := a.ownedBook(p, r.PathValue("bid")); e != nil {
			return e
		}
		_, e := s.DB.Exec("DELETE FROM knowledge_papers WHERE knowledge_id=? AND paper_id=?", r.PathValue("bid"), r.PathValue("pid"))
		if e != nil {
			return e
		}
		JSON(w, 200, Row{"removed": true})
		return nil
	})
	a.Handle("GET /api/tags", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		rows, e := s.All("SELECT t.tag,count(*) paper_count FROM paper_tags t JOIN papers p ON p.id=t.paper_id WHERE p.workspace_id=? AND p.archived=0 GROUP BY t.tag ORDER BY paper_count DESC,t.tag", p.WorkspaceID)
		if e != nil {
			return e
		}
		JSON(w, 200, Row{"items": rows})
		return nil
	})
	a.Handle("PUT /api/papers/{pid}/tags", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		if _, e := s.Paper(p.WorkspaceID, r.PathValue("pid")); e != nil {
			return e
		}
		body, e := readBody(r)
		if e != nil {
			return e
		}
		tags, e := normalizeTags(body["tags"])
		if e != nil {
			return e
		}
		e = s.Transaction(func(tx *sql.Tx) error {
			if _, err := tx.Exec("DELETE FROM paper_tags WHERE paper_id=?", r.PathValue("pid")); err != nil {
				return err
			}
			for _, tag := range tags {
				if _, err := tx.Exec("INSERT INTO paper_tags VALUES(?,?,'manual')", r.PathValue("pid"), tag); err != nil {
					return err
				}
			}
			return nil
		})
		if e != nil {
			return e
		}
		JSON(w, 200, Row{"tags": tags})
		return nil
	})
	a.Handle("POST /api/papers/{pid}/organize", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		paper, e := readable(s, p, r.PathValue("pid"))
		if e != nil {
			return e
		}
		body, e := readBody(r)
		if e != nil {
			return e
		}
		model, e := bodyModel(a, p, body)
		if e != nil {
			return e
		}
		bid := Str(body["knowledge_id"])
		if bid != "" {
			if _, e = a.ownedBook(p, bid); e != nil {
				return e
			}
		}
		model["knowledge_id"] = bid
		job, e := s.Enqueue(p, "organize", model, r.Header.Get("Idempotency-Key"), Str(paper["id"]), Str(paper["active_version"]), true)
		return jobResponse(w, job, e)
	})
	a.Handle("GET /api/knowledge-bases/{bid}/messages", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		if _, e := a.ownedBook(p, r.PathValue("bid")); e != nil {
			return e
		}
		rows, e := s.All("SELECT * FROM (SELECT * FROM knowledge_messages WHERE knowledge_id=? ORDER BY created DESC LIMIT 100) ORDER BY created", r.PathValue("bid"))
		if e != nil {
			return e
		}
		JSON(w, 200, Row{"items": rowsJSON(rows, "evidence")})
		return nil
	})
	a.Handle("POST /api/knowledge-bases/{bid}/messages", a.askKnowledge)
	a.Handle("GET /api/workspace-notes", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		scope, id := r.URL.Query().Get("scope"), r.URL.Query().Get("scope_id")
		if e := a.ownScope(p, scope, id); e != nil {
			return e
		}
		rows, e := s.All("SELECT * FROM notebook_notes WHERE workspace_id=? AND scope=? AND scope_id=? ORDER BY updated DESC", p.WorkspaceID, scope, id)
		if e != nil {
			return e
		}
		JSON(w, 200, Row{"items": rowsJSON(rows, "evidence")})
		return nil
	})
	a.Handle("POST /api/workspace-notes", a.createNotebookNote)
	a.Handle("PUT /api/workspace-notes/{nid}", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		body, e := readBody(r)
		if e != nil {
			return e
		}
		title, e := requiredText(body["title"], 1, 120)
		if e != nil {
			return e
		}
		content, e := requiredText(body["content"], 1, 30000)
		if e != nil {
			return e
		}
		result, e := s.DB.Exec("UPDATE notebook_notes SET title=?,content=?,updated=? WHERE id=? AND workspace_id=?", title, content, Now(), r.PathValue("nid"), p.WorkspaceID)
		if e != nil {
			return e
		}
		return changedJSON(w, result)
	})
	a.Handle("DELETE /api/workspace-notes/{nid}", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		result, e := s.DB.Exec("DELETE FROM notebook_notes WHERE id=? AND workspace_id=?", r.PathValue("nid"), p.WorkspaceID)
		if e != nil {
			return e
		}
		return changedJSON(w, result)
	})
}

func (a *App) scheduleQuestions(p Principal, bid string) (Row, error) {
	book, e := a.ownedBook(p, bid)
	if e != nil {
		return nil, e
	}
	if strings.TrimSpace(Str(book["description"])) != "" {
		return nil, nil
	}
	if old, e := a.Store.One("SELECT * FROM jobs WHERE workspace_id=? AND resource_id=? AND kind='book_questions' AND state IN ('queued','running')", p.WorkspaceID, bid); e == nil {
		return old, nil
	}
	config, e := a.ChooseModel(p, "", "")
	if e != nil {
		return nil, e
	}
	return a.Store.Enqueue(p, "book_questions", config, "book-questions:"+UID(), bid, "", true)
}
func (a *App) askKnowledge(w http.ResponseWriter, r *http.Request, p Principal) error {
	if _, e := a.ownedBook(p, r.PathValue("bid")); e != nil {
		return e
	}
	body, e := readBody(r)
	if e != nil {
		return e
	}
	content, e := requiredText(body["content"], 1, 5000)
	if e != nil {
		return e
	}
	payload, e := bodyModel(a, p, body)
	if e != nil {
		return e
	}
	payload["content"] = content
	ids := stringList(body["paper_ids"])
	sort.Strings(ids)
	if _, ok := body["paper_ids"]; ok {
		if len(ids) == 0 || len(ids) > 100 {
			return Error(422, "请选择 1–100 篇论文")
		}
		payload["paper_ids"] = ids
	} else {
		payload["paper_ids"] = nil
	}
	var job Row
	e = a.Store.Transaction(func(tx *sql.Tx) error {
		old, err := One(tx, "SELECT * FROM jobs WHERE workspace_id=? AND dedupe_key=?", p.WorkspaceID, r.Header.Get("Idempotency-Key"))
		if err == nil {
			previous := Object(old["payload"])
			for k, v := range payload {
				if Encode(previous[k]) != Encode(v) {
					return Error(409, "idempotency_key_conflict")
				}
			}
			if Str(old["kind"]) != "knowledge_chat" || Str(old["resource_id"]) != r.PathValue("bid") {
				return Error(409, "idempotency_key_conflict")
			}
			job = old
			return nil
		}
		if err != sql.ErrNoRows {
			return err
		}
		if _, err = One(tx, "SELECT id FROM jobs WHERE resource_id=? AND kind='knowledge_chat' AND state IN ('queued','running')", r.PathValue("bid")); err == nil {
			return Error(409, "请等待上一条回答完成")
		}
		papers, err := Rows(tx, "SELECT p.id,p.active_version FROM papers p JOIN knowledge_papers k ON k.paper_id=p.id WHERE k.knowledge_id=? AND p.workspace_id=? AND p.archived=0 ORDER BY p.id", r.PathValue("bid"), p.WorkspaceID)
		if err != nil {
			return err
		}
		if payload["paper_ids"] != nil {
			selected := []Row{}
			for _, id := range ids {
				found := false
				for _, paper := range papers {
					if Str(paper["id"]) == id {
						selected = append(selected, paper)
						found = true
						break
					}
				}
				if !found {
					return Error(400, "请选择当前知识库中的有效论文")
				}
			}
			papers = selected
		}
		if len(papers) == 0 || len(papers) > 100 {
			return Error(400, "知识库需要 1–100 篇论文")
		}
		for _, paper := range papers {
			if Str(paper["active_version"]) == "" {
				return Error(409, "请先为所选论文上传 PDF")
			}
		}
		payload["papers"] = papers
		job, err = EnqueueTx(tx, p, "knowledge_chat", payload, r.Header.Get("Idempotency-Key"), r.PathValue("bid"), "", true)
		if err != nil {
			return err
		}
		selected := []string{}
		for _, paper := range papers {
			selected = append(selected, Str(paper["id"]))
		}
		_, err = tx.Exec("INSERT INTO knowledge_messages VALUES(?,?,?,?,?,?,?)", UID(), r.PathValue("bid"), "user", content, Encode(Row{"selected_paper_ids": selected}), job["id"], Now())
		return err
	})
	return jobResponse(w, job, e)
}
func (a *App) ownScope(p Principal, scope, id string) error {
	if scope == "paper" {
		_, e := a.Store.Paper(p.WorkspaceID, id)
		return e
	}
	if scope == "book" {
		_, e := a.ownedBook(p, id)
		return e
	}
	return Error(422, "无效笔记范围")
}
func (a *App) createNotebookNote(w http.ResponseWriter, r *http.Request, p Principal) error {
	body, e := readBody(r)
	if e != nil {
		return e
	}
	scope, id := Str(body["scope"]), Str(body["scope_id"])
	if e = a.ownScope(p, scope, id); e != nil {
		return e
	}
	title := Str(body["title"])
	if title == "" {
		title = "研究笔记"
	}
	title, e = requiredText(title, 1, 120)
	if e != nil {
		return e
	}
	content, e := requiredText(body["content"], 0, 30000)
	if e != nil {
		return e
	}
	source := Str(body["source_message_id"])
	evidence := "{}"
	if source != "" {
		var message Row
		if scope == "book" {
			message, e = a.Store.One("SELECT content,evidence FROM knowledge_messages WHERE id=? AND knowledge_id=? AND role='assistant'", source, id)
		} else {
			message, e = a.Store.One("SELECT m.content,m.evidence FROM messages m JOIN conversations c ON c.id=m.conversation_id WHERE m.id=? AND c.paper_id=? AND c.workspace_id=? AND m.role='assistant'", source, id, p.WorkspaceID)
		}
		if e != nil {
			return e
		}
		content = Str(message["content"])
		evidence = Str(message["evidence"])
	}
	if strings.TrimSpace(content) == "" {
		return Error(422, "笔记内容不能为空")
	}
	nid := UID()
	_, e = a.Store.DB.Exec("INSERT OR IGNORE INTO notebook_notes VALUES(?,?,?,?,?,?,?,?,?,?)", nid, p.WorkspaceID, scope, id, title, content, evidence, Null(source), Now(), Now())
	if e != nil {
		return e
	}
	if source != "" {
		row, err := a.Store.One("SELECT id FROM notebook_notes WHERE workspace_id=? AND scope=? AND scope_id=? AND source_message_id=?", p.WorkspaceID, scope, id, source)
		if err != nil {
			return err
		}
		nid = Str(row["id"])
	}
	JSON(w, 201, Row{"id": nid})
	return nil
}
