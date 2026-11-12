package fastread

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

func exchangeURL(service string) string {
	value := os.Getenv("FASTREAD_" + strings.ToUpper(service) + "_URL")
	if value == "" {
		if service == "fastnews" {
			value = "https://news.fastrd.io"
		} else {
			value = "https://write.fastrd.io"
		}
	}
	return strings.TrimRight(value, "/")
}
func validService(service string) bool { return service == "fastnews" || service == "fastwrite" }

func exchangePublicURL(service string) string {
	if value := os.Getenv("FASTREAD_" + strings.ToUpper(service) + "_PUBLIC_URL"); value != "" {
		return strings.TrimRight(value, "/")
	}
	if service == "fastnews" {
		return "https://news.fastrd.io"
	}
	return "https://write.fastrd.io"
}

func (a *App) RegisterExchange() error {
	_, err := a.Store.DB.Exec(`CREATE TABLE IF NOT EXISTS integration_connections(workspace_id TEXT NOT NULL REFERENCES workspaces(id),service TEXT NOT NULL,secret TEXT NOT NULL,created REAL NOT NULL,PRIMARY KEY(workspace_id,service)); CREATE TABLE IF NOT EXISTS integration_receipts(workspace_id TEXT NOT NULL REFERENCES workspaces(id),service TEXT NOT NULL,resource TEXT NOT NULL,content TEXT NOT NULL,updated REAL NOT NULL,PRIMARY KEY(workspace_id,service,resource));`)
	if err != nil {
		return err
	}
	a.Handle("GET /api/integrations/status", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		result := Row{}
		for _, service := range []string{"fastnews", "fastwrite"} {
			_, e := a.Store.One("SELECT workspace_id FROM integration_connections WHERE workspace_id=? AND service=?", p.WorkspaceID, service)
			result[service] = Row{"connected": e == nil, "url": exchangePublicURL(service)}
		}
		JSON(w, 200, result)
		return nil
	})
	a.Handle("POST /api/integrations/connections/{service}", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		if e := RequireOwner(p); e != nil {
			return e
		}
		service := r.PathValue("service")
		if !validService(service) {
			return Error(404, "联动服务不存在")
		}
		var body struct{ Token string }
		if e := Decode(r, &body); e != nil {
			return e
		}
		body.Token = strings.TrimSpace(body.Token)
		if len(body.Token) < 24 || len(body.Token) > 256 {
			return Error(422, "请输入目标服务生成的连接码")
		}
		if _, e := exchangeRequest(r, service, body.Token, "GET", "/api/integrations/fastread/token", nil); e != nil {
			return e
		}
		secret, e := a.Store.ProtectSecret(body.Token)
		if e != nil {
			return e
		}
		_, e = a.Store.DB.Exec("INSERT INTO integration_connections VALUES(?,?,?,?) ON CONFLICT(workspace_id,service) DO UPDATE SET secret=excluded.secret,created=excluded.created", p.WorkspaceID, service, secret, Now())
		if e != nil {
			return e
		}
		JSON(w, 200, Row{"ok": true})
		return nil
	})
	a.Handle("DELETE /api/integrations/connections/{service}", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		if e := RequireOwner(p); e != nil {
			return e
		}
		if !validService(r.PathValue("service")) {
			return Error(404, "联动服务不存在")
		}
		_, e := a.Store.DB.Exec("DELETE FROM integration_connections WHERE workspace_id=? AND service=?", p.WorkspaceID, r.PathValue("service"))
		if e == nil {
			JSON(w, 200, Row{"ok": true})
		}
		return e
	})
	a.Handle("GET /api/integrations/fastwrite/projects", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		return a.forwardExchange(w, r, p, "fastwrite", "GET", "/api/integrations/fastread/projects", nil)
	})
	a.Handle("GET /api/integrations/fastnews/directions", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		return a.forwardExchange(w, r, p, "fastnews", "GET", "/api/integrations/fastread/directions", nil)
	})
	a.Handle("POST /api/integrations/fastnews/directions", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		var body struct {
			Text string `json:"text"`
			Mode string `json:"mode"`
		}
		if e := Decode(r, &body); e != nil {
			return e
		}
		body.Text = strings.TrimSpace(body.Text)
		if body.Text == "" || len([]rune(body.Text)) > 4000 {
			return Error(422, "研究方向需要 1–4000 个字符")
		}
		if body.Mode != "append" && body.Mode != "replace" {
			return Error(422, "请选择追加或替换")
		}
		return a.forwardExchange(w, r, p, "fastnews", "PUT", "/api/integrations/fastread/directions", body)
	})
	a.Handle("POST /api/integrations/fastwrite/sync", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		var body struct {
			ProjectID string   `json:"project_id"`
			PaperIDs  []string `json:"paper_ids"`
		}
		if e := Decode(r, &body); e != nil {
			return e
		}
		if body.ProjectID == "" || len(body.PaperIDs) < 1 || len(body.PaperIDs) > 100 {
			return Error(422, "请选择写作项目和论文")
		}
		bundle, e := BuildFastWriteBundle(a.Store, p.WorkspaceID, body.PaperIDs)
		if e != nil {
			return e
		}
		token, e := a.exchangeToken(p, "fastwrite")
		if e != nil {
			return e
		}
		response, e := exchangeRequest(r, "fastwrite", token, "POST", "/api/integrations/fastread/projects/"+url.PathEscape(body.ProjectID)+"/bundles", bundle)
		if e != nil {
			return e
		}
		_, e = a.Store.DB.Exec("INSERT INTO integration_receipts VALUES(?,?,?,?,?) ON CONFLICT(workspace_id,service,resource) DO UPDATE SET content=excluded.content,updated=excluded.updated", p.WorkspaceID, "fastwrite", body.ProjectID, Encode(response), Now())
		if e != nil {
			return e
		}
		JSON(w, 200, response)
		return nil
	})
	a.Handle("GET /api/integrations/fastwrite/projects/{project}/feedback", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		return a.forwardExchange(w, r, p, "fastwrite", "GET", "/api/integrations/fastread/projects/"+url.PathEscape(r.PathValue("project"))+"/feedback", nil)
	})
	a.Handle("POST /api/integrations/fastwrite/projects/{project}/feedback", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		token, e := a.exchangeToken(p, "fastwrite")
		if e != nil {
			return e
		}
		response, e := exchangeRequest(r, "fastwrite", token, "GET", "/api/integrations/fastread/projects/"+url.PathEscape(r.PathValue("project"))+"/feedback", nil)
		if e != nil {
			return e
		}
		notes := snapshotRows(response["items"])
		saved := 0
		for _, note := range notes {
			paper := Str(note["paper_id"])
			if _, e = a.Store.Paper(p.WorkspaceID, paper); e != nil {
				continue
			}
			source := "fastwrite:" + r.PathValue("project") + ":" + Str(note["id"])
			id := UID()
			_, e = a.Store.DB.Exec("INSERT INTO notebook_notes(id,workspace_id,scope,scope_id,title,content,evidence,source_message_id,created,updated) VALUES(?,?,'paper',?,?,?,'[]',?,?,?) ON CONFLICT(workspace_id,scope,scope_id,source_message_id) DO UPDATE SET title=excluded.title,content=excluded.content,updated=excluded.updated", id, p.WorkspaceID, paper, "FastWrite · "+Str(note["title"]), Str(note["content"]), source, Now(), Now())
			if e != nil {
				return e
			}
			saved++
		}
		JSON(w, 200, Row{"ok": true, "saved": saved})
		return nil
	})
	return nil
}
func (a *App) exchangeToken(p Principal, service string) (string, error) {
	row, e := a.Store.One("SELECT secret FROM integration_connections WHERE workspace_id=? AND service=?", p.WorkspaceID, service)
	if e != nil {
		return "", Error(409, "请先在设置中连接 "+service)
	}
	return a.Store.UnprotectSecret(Str(row["secret"]))
}
func (a *App) forwardExchange(w http.ResponseWriter, r *http.Request, p Principal, service, method, path string, body any) error {
	token, e := a.exchangeToken(p, service)
	if e != nil {
		return e
	}
	result, e := exchangeRequest(r, service, token, method, path, body)
	if e != nil {
		return e
	}
	JSON(w, 200, result)
	return nil
}
func exchangeRequest(r *http.Request, service, token, method, path string, body any) (Row, error) {
	base, e := url.Parse(exchangeURL(service))
	if e != nil || base.Host == "" || (base.Scheme != "https" && !(base.Scheme == "http" && (base.Hostname() == "localhost" || base.Hostname() == "127.0.0.1" || base.Hostname() == "::1"))) {
		return nil, Error(503, "联动服务地址配置无效")
	}
	var data io.Reader
	if body != nil {
		raw, e := json.Marshal(body)
		if e != nil {
			return nil, e
		}
		data = bytes.NewReader(raw)
	}
	request, e := http.NewRequestWithContext(r.Context(), method, strings.TrimRight(base.String(), "/")+path, data)
	if e != nil {
		return nil, e
	}
	request.Header.Set("Authorization", "Bearer "+token)
	request.Header.Set("Content-Type", "application/json")
	client := &http.Client{Timeout: 45 * time.Second, CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse }}
	response, e := client.Do(request)
	if e != nil {
		return nil, Error(502, "暂时无法连接 "+service)
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		if response.StatusCode == 401 || response.StatusCode == 403 {
			return nil, Error(response.StatusCode, "连接码已失效或没有项目权限，请在设置中重新连接")
		}
		return nil, Error(502, fmt.Sprintf("%s 未完成操作（%d）", service, response.StatusCode))
	}
	var result Row
	if e = json.NewDecoder(io.LimitReader(response.Body, 8<<20)).Decode(&result); e != nil {
		return nil, Error(502, "联动服务返回内容无效")
	}
	return result, nil
}
