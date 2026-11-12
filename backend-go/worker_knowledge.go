package fastread

import (
	"context"
	"database/sql"
	"errors"
	"strings"
)

func snapshotRows(v any) []Row {
	if rows, ok := v.([]Row); ok {
		return rows
	}
	items, _ := v.([]any)
	rows := []Row{}
	for _, item := range items {
		if row, ok := item.(map[string]any); ok {
			rows = append(rows, row)
		}
	}
	return rows
}
func executeKnowledge(ctx context.Context, s *Store, job Row, owner string, payload Row) error {
	kind, workspace := Str(job["kind"]), Str(job["workspace_id"])
	if kind == "book_questions" {
		return executeBookQuestions(ctx, s, job, owner, payload)
	}
	snapshots := []Row{{"id": job["resource_id"], "active_version": job["version_id"]}}
	if kind == "knowledge_chat" {
		snapshots = snapshotRows(payload["papers"])
	}
	query := Str(payload["content"])
	if query == "" {
		query = "method mechanism principle contribution 方法 原理"
	}
	chunks, e := sourceExcerpts(s, workspace, snapshots, query)
	if e != nil {
		return e
	}
	if len(chunks) == 0 {
		return errors.New("insufficient source text")
	}
	var result Row
	if kind == "organize" {
		books, e := s.All("SELECT id,name,description FROM knowledge_bases WHERE workspace_id=? ORDER BY name LIMIT 200", workspace)
		if e != nil {
			return e
		}
		result, e = completeModel(ctx, s, job, owner, payload, `用中文总结论文的核心原理（80–200字），生成3–6个具体研究标签。选择最相关的已有知识库，没有合适的则建议简短主题名。返回 {"principle":"核心原理","tags":["标签"],"knowledge_id":"已有知识库 ID 或空字符串","new_knowledge_name":"建议名称","evidence":[{"source_id":"S1","quote":"逐字原文"}]}。至少提供一条支持原理的逐字引文。`, Row{"sources": chunks, "knowledge_bases": books})
		if e != nil {
			return e
		}
	} else {
		history, e := s.All("SELECT role,content,evidence FROM knowledge_messages WHERE knowledge_id=? AND job_id!=? ORDER BY created DESC LIMIT 20", job["resource_id"], job["id"])
		if e != nil {
			return e
		}
		selected := map[string]bool{}
		for _, p := range snapshots {
			selected[Str(p["id"])] = true
		}
		filtered := []Row{}
		for _, m := range history {
			ids := stringList(Object(m["evidence"])["selected_paper_ids"])
			same := len(ids) == len(selected)
			for _, id := range ids {
				same = same && selected[id]
			}
			if same {
				filtered = append([]Row{{"role": m["role"], "content": m["content"]}}, filtered...)
			}
		}
		result, e = completeModel(ctx, s, job, owner, payload, `用中文回答知识库的问题，比较论文的原理、联系与差异，尽量控制在600字以内。只能依据给定原文，引用处使用 [S1] 编号。返回 {"answer":"回答","source_ids":["S1","S2"]}。比较多篇论文时，每篇至少选择一个来源。`, Row{"question": payload["content"], "history": filtered, "sources": chunks})
		if e != nil {
			return e
		}
	}
	var evidence []Row
	if kind == "organize" {
		evidence, e = bindSources(result["evidence"], chunks)
	} else {
		evidence, e = selectedSources(result, chunks)
	}
	if e != nil {
		return e
	}
	bid := ""
	e = s.Transaction(func(tx *sql.Tx) error {
		if e := assertLease(tx, job, owner); e != nil {
			return e
		}
		output := Row{}
		if kind == "organize" {
			principle := Str(result["principle"])
			if len([]rune(principle)) < 20 || len([]rune(principle)) > 2000 {
				return errors.New("invalid principle")
			}
			tags, e := normalizeTags(result["tags"])
			if e != nil {
				return e
			}
			if len(tags) < 2 {
				return errors.New("insufficient tags")
			}
			active, e := One(tx, "SELECT active_version FROM papers WHERE id=? AND workspace_id=? AND archived=0", job["resource_id"], workspace)
			if e != nil {
				return e
			}
			if Str(active["active_version"]) != Str(job["version_id"]) {
				return errors.New("document version changed")
			}
			bid = Str(payload["knowledge_id"])
			if bid == "" {
				bid = Str(result["knowledge_id"])
			}
			if bid != "" {
				if _, e = One(tx, "SELECT id FROM knowledge_bases WHERE id=? AND workspace_id=?", bid, workspace); e != nil {
					return e
				}
			} else {
				name, e := requiredText(result["new_knowledge_name"], 1, 80)
				if e != nil {
					return e
				}
				previous, e := One(tx, "SELECT id FROM knowledge_bases WHERE workspace_id=? AND name=?", workspace, name)
				if e == nil {
					bid = Str(previous["id"])
				} else if e == sql.ErrNoRows {
					bid = UID()
					if _, e = tx.Exec("INSERT INTO knowledge_bases VALUES(?,?,?,?,?)", bid, workspace, name, "", Now()); e != nil {
						return e
					}
				} else {
					return e
				}
			}
			origin := "ai"
			if Str(payload["knowledge_id"]) != "" {
				origin = "manual"
			}
			if _, e = tx.Exec("INSERT OR IGNORE INTO knowledge_papers VALUES(?,?,?,?)", bid, job["resource_id"], origin, Now()); e != nil {
				return e
			}
			if _, e = tx.Exec("INSERT OR REPLACE INTO paper_insights VALUES(?,?,?,?,?)", job["resource_id"], job["version_id"], principle, Encode(evidence), Now()); e != nil {
				return e
			}
			if _, e = tx.Exec("DELETE FROM paper_tags WHERE paper_id=? AND origin='ai'", job["resource_id"]); e != nil {
				return e
			}
			for _, tag := range tags {
				if _, e = tx.Exec("INSERT OR IGNORE INTO paper_tags VALUES(?,?,'ai')", job["resource_id"], tag); e != nil {
					return e
				}
			}
			output = Row{"paper_id": job["resource_id"], "knowledge_id": bid, "tags": tags}
		} else {
			answer := Str(result["answer"])
			if e := validateAnswer(answer, evidence); e != nil {
				return e
			}
			ids := []string{}
			for _, p := range snapshots {
				ids = append(ids, Str(p["id"]))
			}
			contextPapers := map[string]bool{}
			for _, chunk := range chunks {
				contextPapers[Str(chunk["paper_id"])] = true
			}
			id := UID()
			if _, e := tx.Exec("INSERT INTO knowledge_messages VALUES(?,?,?,?,?,?,?)", id, job["resource_id"], "assistant", answer, Encode(Row{"sources": evidence, "selected_paper_ids": ids, "papers_considered": len(snapshots), "papers_in_context": len(contextPapers)}), job["id"], Now()); e != nil {
				return e
			}
			output = Row{"knowledge_id": job["resource_id"], "message_id": id}
		}
		return completeJob(tx, job, output)
	})
	if e == nil && bid != "" {
		app := &App{Store: s}
		app.scheduleQuestions(Principal{UserID: Str(job["user_id"]), WorkspaceID: workspace}, bid)
	}
	return e
}
func executeBookQuestions(ctx context.Context, s *Store, job Row, owner string, payload Row) error {
	book, e := s.One("SELECT * FROM knowledge_bases WHERE id=? AND workspace_id=?", job["resource_id"], job["workspace_id"])
	if e != nil {
		return e
	}
	if strings.TrimSpace(Str(book["description"])) != "" {
		return s.Transaction(func(tx *sql.Tx) error {
			if e := assertLease(tx, job, owner); e != nil {
				return e
			}
			return completeJob(tx, job, Row{"knowledge_id": book["id"], "preserved": true})
		})
	}
	papers, e := s.All("SELECT p.id,p.active_version,p.title FROM papers p JOIN knowledge_papers k ON k.paper_id=p.id WHERE k.knowledge_id=? AND p.workspace_id=? AND p.archived=0 AND p.active_version IS NOT NULL ORDER BY p.id LIMIT 30", book["id"], job["workspace_id"])
	if e != nil {
		return e
	}
	chunks, e := sourceExcerpts(s, Str(job["workspace_id"]), papers, "")
	if e != nil {
		return e
	}
	result, e := completeModel(ctx, s, job, owner, payload, `为知识库写一到两个具体研究问题，作为“关注的问题”。用20–100字自然简洁中文。有论文时根据论文原文提炼共同问题；没有论文时仅根据名称提出待研究问题。返回 {"description":"问题文本？"}。`, Row{"name": book["name"], "sources": chunks})
	if e != nil {
		return e
	}
	description := strings.TrimSpace(Str(result["description"]))
	if len([]rune(description)) < 10 || len([]rune(description)) > 200 || !strings.ContainsAny(description, "?？") {
		return errors.New("invalid research question")
	}
	return s.Transaction(func(tx *sql.Tx) error {
		if e := assertLease(tx, job, owner); e != nil {
			return e
		}
		changed, e := tx.Exec("UPDATE knowledge_bases SET description=? WHERE id=? AND workspace_id=? AND trim(description)=''", description, book["id"], job["workspace_id"])
		if e != nil {
			return e
		}
		n, _ := changed.RowsAffected()
		return completeJob(tx, job, Row{"knowledge_id": book["id"], "generated": n > 0})
	})
}
