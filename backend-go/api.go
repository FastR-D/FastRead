package fastread

import (
	"database/sql"
	"net/http"
	"net/url"
	"strings"
)

func (s *Store) modelUser(workspace, user string) error {
	_, e := s.One("SELECT u.id FROM users u JOIN memberships m ON m.user_id=u.id WHERE u.id=? AND m.workspace_id=? AND u.disabled=0", user, workspace)
	return e
}

// Workspace and individual grants are additive. EXISTS avoids duplicate models
// when both grants apply to the same user.
const sharedProviderAccess = `(EXISTS(SELECT 1 FROM shared_provider_workspaces a WHERE a.provider_id=p.id AND a.workspace_id=?) OR EXISTS(SELECT 1 FROM shared_provider_users a WHERE a.provider_id=p.id AND a.user_id=?))`

func (s *Store) Providers(workspace, user string) ([]Row, error) {
	if e := s.modelUser(workspace, user); e != nil {
		return nil, e
	}
	return s.All("SELECT id,name,base_url,models,0 shared FROM providers WHERE workspace_id=? UNION ALL SELECT p.id,p.name,p.base_url,p.models,1 shared FROM shared_providers p WHERE p.enabled=1 AND "+sharedProviderAccess, workspace, workspace, user)
}

func (s *Store) Provider(workspace, user, id string) (Row, error) {
	if e := s.modelUser(workspace, user); e != nil {
		return nil, e
	}
	r, e := s.One("SELECT *,0 shared FROM providers WHERE id=? AND workspace_id=?", id, workspace)
	if e == nil {
		return r, nil
	}
	if e != sql.ErrNoRows {
		return nil, e
	}
	return s.One("SELECT p.*,1 shared FROM shared_providers p WHERE p.id=? AND p.enabled=1 AND "+sharedProviderAccess, id, workspace, user)
}
func (a *App) ChooseModel(p Principal, provider, model string) (Row, error) {
	var r Row
	var e error
	if provider != "" {
		r, e = a.Store.Provider(p.WorkspaceID, p.UserID, provider)
	} else {
		rows, x := a.Store.Providers(p.WorkspaceID, p.UserID)
		e = x
		if len(rows) > 0 {
			r = rows[0]
		} else {
			e = sql.ErrNoRows
		}
	}
	if e != nil {
		return nil, Error(400, "请先在模型设置中配置模型")
	}
	models := Array(r["models"])
	if model == "" && len(models) > 0 {
		model = Str(models[0])
		for _, m := range models {
			if Str(m) == "qwen3.8-27b" {
				model = Str(m)
			}
		}
	}
	for _, m := range models {
		if Str(m) == model {
			return Row{"provider_id": r["id"], "model": model}, nil
		}
	}
	return nil, Error(400, "当前账号无权使用所选模型")
}
func (a *App) Decorate(rows []Row) error {
	for _, r := range rows {
		tags, e := a.Store.All("SELECT tag FROM paper_tags WHERE paper_id=? ORDER BY tag", r["id"])
		if e != nil {
			return e
		}
		values := []string{}
		for _, t := range tags {
			values = append(values, Str(t["tag"]))
		}
		r["tags"] = values
		r["knowledge_bases"], e = a.Store.All("SELECT k.id,k.name FROM knowledge_bases k JOIN knowledge_papers p ON p.knowledge_id=k.id WHERE p.paper_id=?", r["id"])
		if e != nil {
			return e
		}
		insight, _ := a.Store.One("SELECT principle,evidence FROM paper_insights WHERE paper_id=? AND version_id=?", r["id"], r["active_version"])
		r["principle"] = Str(insight["principle"])
		r["principle_evidence"] = Array(insight["evidence"])
	}
	return nil
}
func (a *App) RegisterCore() {
	a.Public("GET /api/health", func(w http.ResponseWriter, r *http.Request) error {
		if e := a.Store.DB.Ping(); e != nil {
			return e
		}
		JSON(w, 200, Row{"status": "healthy", "schema": 1, "version": Version, "backend": "go"})
		return nil
	})
	a.Handle("GET /api/papers", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		limit, offset := QueryInt(r, "limit", 20, 1, 100), QueryInt(r, "offset", 0, 0, 1000000)
		archived := r.URL.Query().Get("archived") == "true"
		tag := strings.ToLower(strings.TrimSpace(r.URL.Query().Get("tag")))
		args := []any{p.WorkspaceID, "%" + r.URL.Query().Get("q") + "%", archived, tag, tag}
		where := "workspace_id=? AND title LIKE ? AND archived=? AND (?='' OR id IN (SELECT paper_id FROM paper_tags WHERE tag=?))"
		rows, e := a.Store.All("SELECT id,title,active_version,created,metadata FROM papers WHERE "+where+" ORDER BY created DESC,id LIMIT ? OFFSET ?", append(args, limit, offset)...)
		if e != nil {
			return e
		}
		for _, row := range rows {
			m := Object(row["metadata"])
			delete(row, "metadata")
			row["authors"] = m["authors"]
			if row["authors"] == nil {
				row["authors"] = []string{}
			}
			row["year"] = m["year"]
			row["page_count"] = Num(m["page_count"])
		}
		if e = a.Decorate(rows); e != nil {
			return e
		}
		count, e := a.Store.One("SELECT count(*) n FROM papers WHERE "+where, args...)
		if e != nil {
			return e
		}
		JSON(w, 200, Row{"items": rows, "total": count["n"], "limit": limit, "offset": offset})
		return nil
	})
	a.Handle("GET /api/papers/{paper_id}", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		row, e := a.Store.Paper(p.WorkspaceID, r.PathValue("paper_id"))
		if e != nil {
			return e
		}
		row["metadata"] = Object(row["metadata"])
		row["versions"], e = a.Store.All("SELECT v.id,v.created,(SELECT count(*) FROM pages p WHERE p.version_id=v.id) page_count FROM document_versions v WHERE paper_id=? ORDER BY created DESC", row["id"])
		if e != nil {
			return e
		}
		if e = a.Decorate([]Row{row}); e != nil {
			return e
		}
		JSON(w, 200, row)
		return nil
	})
	a.Handle("DELETE /api/papers/{paper_id}", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		pid := r.PathValue("paper_id")
		e := a.Store.Transaction(func(tx *sql.Tx) error {
			if _, e := One(tx, "SELECT id FROM papers WHERE id=? AND workspace_id=? AND archived=0", pid, p.WorkspaceID); e != nil {
				return e
			}
			pending, _ := One(tx, "SELECT id FROM jobs WHERE (resource_id=? OR resource_id IN (SELECT id FROM conversations WHERE paper_id=?)) AND state IN ('queued','running')", pid, pid)
			if pending != nil {
				return Error(409, "请等待论文任务完成后归档")
			}
			_, e := tx.Exec("UPDATE papers SET archived=1 WHERE id=?", pid)
			return e
		})
		if e == nil {
			JSON(w, 200, Row{"archived": true})
		}
		return e
	})
	a.Handle("POST /api/papers/{paper_id}/restore", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		res, e := a.Store.DB.Exec("UPDATE papers SET archived=0 WHERE id=? AND workspace_id=?", r.PathValue("paper_id"), p.WorkspaceID)
		if e != nil {
			return e
		}
		n, _ := res.RowsAffected()
		if n == 0 {
			return sql.ErrNoRows
		}
		JSON(w, 200, Row{"archived": false})
		return nil
	})
	a.Handle("PUT /api/papers/{paper_id}/summary", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		var d struct{ Content string }
		if e := Decode(r, &d); e != nil {
			return e
		}
		if len([]rune(d.Content)) > 10000 {
			return Error(422, "总结最多 10000 字")
		}
		if _, e := a.Store.Paper(p.WorkspaceID, r.PathValue("paper_id")); e != nil {
			return e
		}
		_, e := a.Store.DB.Exec("UPDATE papers SET summary=? WHERE id=?", d.Content, r.PathValue("paper_id"))
		if e == nil {
			JSON(w, 200, Row{"content": d.Content})
		}
		return e
	})
	a.Handle("GET /api/jobs", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		rows, e := a.Store.All("SELECT * FROM jobs WHERE workspace_id=? ORDER BY created DESC LIMIT ? OFFSET ?", p.WorkspaceID, QueryInt(r, "limit", 30, 1, 100), QueryInt(r, "offset", 0, 0, 1000000))
		if e != nil {
			return e
		}
		items := []Row{}
		for _, j := range rows {
			items = append(items, JobView(j))
		}
		JSON(w, 200, Row{"items": items})
		return nil
	})
	a.Handle("GET /api/jobs/{job_id}", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		row, e := a.Store.One("SELECT * FROM jobs WHERE id=? AND workspace_id=?", r.PathValue("job_id"), p.WorkspaceID)
		if e != nil {
			return e
		}
		JSON(w, 200, JobView(row))
		return nil
	})
	a.Handle("POST /api/jobs/{job_id}/cancel", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		res, e := a.Store.DB.Exec("UPDATE jobs SET state='cancelled',updated=? WHERE id=? AND workspace_id=? AND state='queued'", Now(), r.PathValue("job_id"), p.WorkspaceID)
		if e != nil {
			return e
		}
		n, _ := res.RowsAffected()
		if n == 0 {
			return Error(409, "只有排队中的任务可以取消")
		}
		JSON(w, 200, Row{"ok": true})
		return nil
	})
	a.Handle("GET /api/providers", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		rows, e := a.Store.Providers(p.WorkspaceID, p.UserID)
		if e != nil {
			return e
		}
		for _, row := range rows {
			row["models"] = Array(row["models"])
			row["shared"] = Num(row["shared"]) == 1
		}
		JSON(w, 200, Row{"items": rows})
		return nil
	})
	a.Handle("POST /api/providers", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		if e := RequireOwner(p); e != nil {
			return e
		}
		var d ProviderInput
		if e := Decode(r, &d); e != nil {
			return e
		}
		if e := d.Validate(); e != nil {
			return e
		}
		secret, e := a.Store.ProtectSecret(d.APIKey)
		if e != nil {
			return e
		}
		id := UID()
		_, e = a.Store.DB.Exec("INSERT INTO providers VALUES(?,?,?,?,?,?,?)", id, p.WorkspaceID, d.Name, d.BaseURL, secret, Encode(d.Models), Now())
		if e == nil {
			JSON(w, 201, Row{"id": id, "name": d.Name})
		}
		return e
	})
	a.Handle("DELETE /api/providers/{provider_id}", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		if e := RequireOwner(p); e != nil {
			return e
		}
		res, e := a.Store.DB.Exec("DELETE FROM providers WHERE id=? AND workspace_id=?", r.PathValue("provider_id"), p.WorkspaceID)
		if e != nil {
			return e
		}
		n, _ := res.RowsAffected()
		if n == 0 {
			return sql.ErrNoRows
		}
		JSON(w, 200, Row{"ok": true})
		return nil
	})
	a.Handle("GET /api/topics", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		rows, e := a.Store.All("SELECT id,question,scope FROM topics WHERE workspace_id=? ORDER BY created DESC", p.WorkspaceID)
		if e == nil {
			JSON(w, 200, Row{"items": rows})
		}
		return e
	})
	a.Handle("GET /api/topics/{topic_id}", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		row, e := a.Store.One("SELECT * FROM topics WHERE id=? AND workspace_id=?", r.PathValue("topic_id"), p.WorkspaceID)
		if e != nil {
			return e
		}
		row["hypotheses"] = Array(row["hypotheses"])
		row["evidence"], e = a.Store.All("SELECT * FROM topic_evidence WHERE topic_id=? ORDER BY page,id", row["id"])
		if e == nil {
			JSON(w, 200, row)
		}
		return e
	})
}

type ProviderInput struct {
	Name         string   `json:"name"`
	BaseURL      string   `json:"base_url"`
	APIKey       string   `json:"api_key"`
	Models       []string `json:"models"`
	WorkspaceIDs []string `json:"workspace_ids"`
	UserIDs      []string `json:"user_ids"`
}

func (d *ProviderInput) Validate() error {
	d.Name = strings.TrimSpace(d.Name)
	d.BaseURL = strings.TrimRight(d.BaseURL, "/")
	u, e := url.Parse(d.BaseURL)
	if e != nil || u.Scheme != "https" || u.Hostname() == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
		return Error(422, "供应商地址必须是 HTTPS API 地址")
	}
	if d.Name == "" || len(d.Name) > 300 || d.APIKey == "" || len(d.APIKey) > 4096 || len(d.Models) == 0 || len(d.Models) > 30 {
		return Error(422, "请输入供应商名称、密钥和模型")
	}
	for _, m := range d.Models {
		if strings.TrimSpace(m) == "" || len(m) > 100 {
			return Error(422, "模型 ID 无效")
		}
	}
	return ValidatePublicURL(d.BaseURL)
}
