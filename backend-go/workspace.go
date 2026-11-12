package fastread

import (
	"context"
	"database/sql"
	"encoding/json"
	"io"
	"net/http"
	"net/url"
	"slices"
	"sort"
	"strings"
	"time"

	fastcas "github.com/FastR-D/FastCAS/sdk/go"
)

type workspaceProvider interface {
	VerifyAccessToken(context.Context, string, string, ...string) (*fastcas.AccessClaims, error)
	IntrospectToken(context.Context, string) (*fastcas.Introspection, error)
	ResolveLink(context.Context, string) (*fastcas.Link, error)
}

func (a *App) RegisterWorkspaceSummary() {
	a.Public("POST /api/integrations/fastresearch/workspace", a.workspaceSummary)
}
func (a *App) workspaceSummary(w http.ResponseWriter, r *http.Request) error {
	if a.workspaceCAS == nil {
		return Error(503, "FastCAS 未配置")
	}
	authorization := r.Header.Get("Authorization")
	if !strings.HasPrefix(authorization, "Bearer ") {
		return Error(401, "需要 FastCAS 服务令牌")
	}
	raw := strings.TrimPrefix(authorization, "Bearer ")
	claims, e := a.workspaceCAS.VerifyAccessToken(r.Context(), raw, a.workspaceClient, "workspace:read")
	if e != nil || claims == nil || !claims.Service || claims.Subject != "fastresearch" || claims.ClientID != "fastresearch" {
		return Error(401, "个人摘要服务凭证无效")
	}
	live, e := a.workspaceCAS.IntrospectToken(r.Context(), raw)
	if e != nil || live == nil || !live.Active || live.Subject != claims.Subject || live.ClientID != claims.ClientID || !slices.Contains(live.Audience, a.workspaceClient) || !slices.Contains(strings.Fields(live.Scope), "workspace:read") {
		return Error(401, "个人摘要服务凭证已失效")
	}
	var body struct {
		Subject string `json:"subject"`
	}
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096))
	decoder.DisallowUnknownFields()
	if e = decoder.Decode(&body); e != nil || decoder.Decode(&struct{}{}) != io.EOF || body.Subject == "" || len(body.Subject) > 256 {
		return Error(400, "需要有效的 CAS 身份")
	}
	result := Row{"schemaVersion": "fastresearch.workspace.v1", "appId": "fast-read", "accountState": "missing", "updatedAt": time.Now().UTC().Format(time.RFC3339), "metrics": []Row{}, "items": []Row{}}
	local, e := a.Store.One(`SELECT * FROM fastcas_links WHERE issuer=? AND client_id=? AND subject=? ORDER BY version DESC LIMIT 1`, a.workspaceIssuer, a.workspaceClient, body.Subject)
	if e == sql.ErrNoRows {
		JSON(w, 200, result)
		return nil
	}
	if e != nil {
		return e
	}
	if local["state"] != "active" {
		result["accountState"] = "inactive"
		JSON(w, 200, result)
		return nil
	}
	remote, e := a.workspaceCAS.ResolveLink(r.Context(), body.Subject)
	if e != nil {
		return Error(503, "暂时无法确认 FastCAS 账号绑定")
	}
	if remote == nil || remote.ID != Str(local["id"]) || remote.LocalRef != Str(local["user_id"]) || remote.Subject != body.Subject || remote.ClientID != a.workspaceClient || remote.State != "active" || float64(remote.Version) != Num(local["version"]) {
		result["accountState"] = "inactive"
		JSON(w, 200, result)
		return nil
	}
	user := Str(local["user_id"])
	account, e := a.Store.One(`SELECT disabled FROM users WHERE id=?`, user)
	if e == sql.ErrNoRows || (e == nil && Num(account["disabled"]) != 0) {
		result["accountState"] = "inactive"
		JSON(w, 200, result)
		return nil
	}
	if e != nil {
		return e
	}
	members, e := a.Store.All(`SELECT workspace_id FROM memberships WHERE user_id=?`, user)
	if e != nil {
		return e
	}
	if len(members) == 0 {
		result["accountState"] = "inactive"
		JSON(w, 200, result)
		return nil
	}
	metric := func(id, label, query string) (Row, error) {
		row, e := a.Store.One(query, user)
		return Row{"id": id, "label": label, "value": int(Num(row["n"]))}, e
	}
	metrics := []Row{}
	queries := [][3]string{
		{"papers", "资料论文", `SELECT count(*) n FROM papers p WHERE p.archived=0 AND p.workspace_id IN (SELECT workspace_id FROM memberships WHERE user_id=?)`},
		{"reports", "生成报告", `SELECT count(*) n FROM report_versions r JOIN papers p ON p.id=r.paper_id WHERE p.archived=0 AND p.workspace_id IN (SELECT workspace_id FROM memberships WHERE user_id=?)`},
		{"notes", "研究笔记", `SELECT count(*) n FROM notebook_notes n WHERE n.workspace_id IN (SELECT workspace_id FROM memberships WHERE user_id=?)`},
		{"pending", "待处理任务", `SELECT count(*) n FROM jobs WHERE user_id=? AND state IN ('queued','running','needs_attention')`},
	}
	for _, q := range queries {
		m, e := metric(q[0], q[1], q[2])
		if e != nil {
			return e
		}
		metrics = append(metrics, m)
	}
	items := []Row{}
	papers, e := a.Store.All(`SELECT id,title,created FROM papers WHERE archived=0 AND workspace_id IN (SELECT workspace_id FROM memberships WHERE user_id=?) ORDER BY created DESC LIMIT 2`, user)
	if e != nil {
		return e
	}
	for _, p := range papers {
		items = append(items, Row{"id": "paper:" + Str(p["id"]), "kind": "paper", "title": p["title"], "description": "最近加入资料库", "path": "/?paper=" + url.QueryEscape(Str(p["id"])), "occurredAt": workspaceTime(p["created"])})
	}
	reports, e := a.Store.All(`SELECT r.id,r.paper_id,r.created,p.title FROM report_versions r JOIN papers p ON p.id=r.paper_id WHERE p.archived=0 AND p.workspace_id IN (SELECT workspace_id FROM memberships WHERE user_id=?) ORDER BY r.created DESC LIMIT 2`, user)
	if e != nil {
		return e
	}
	for _, report := range reports {
		items = append(items, Row{"id": "report:" + Str(report["id"]), "kind": "report", "title": report["title"], "description": "阅读报告已生成", "path": "/?paper=" + url.QueryEscape(Str(report["paper_id"])), "occurredAt": workspaceTime(report["created"])})
	}
	notes, e := a.Store.All(`SELECT id,scope,scope_id,title,updated FROM notebook_notes WHERE workspace_id IN (SELECT workspace_id FROM memberships WHERE user_id=?) ORDER BY updated DESC LIMIT 2`, user)
	if e != nil {
		return e
	}
	for _, note := range notes {
		query := "paper"
		if note["scope"] == "book" {
			query = "book"
		}
		items = append(items, Row{"id": "note:" + Str(note["id"]), "kind": "note", "title": note["title"], "description": "研究笔记已更新", "path": "/?" + query + "=" + url.QueryEscape(Str(note["scope_id"])), "occurredAt": workspaceTime(note["updated"])})
	}
	jobs, e := a.Store.All(`SELECT id,kind,state,updated FROM jobs WHERE user_id=? AND state IN ('queued','running','failed','needs_attention') ORDER BY updated DESC LIMIT 2`, user)
	if e != nil {
		return e
	}
	labels := map[string]string{"queued": "任务正在排队", "running": "任务正在处理", "failed": "任务处理失败，请查看", "needs_attention": "任务需要处理"}
	for _, job := range jobs {
		items = append(items, Row{"id": "job:" + Str(job["id"]), "kind": "task", "title": labels[Str(job["state"])], "description": "阅读处理任务", "path": "/?job=" + url.QueryEscape(Str(job["id"])), "occurredAt": workspaceTime(job["updated"])})
	}
	sort.SliceStable(items, func(i, j int) bool { return Str(items[i]["occurredAt"]) > Str(items[j]["occurredAt"]) })
	check, e := a.Store.One(`SELECT version FROM fastcas_links WHERE issuer=? AND id=? AND state='active'`, a.workspaceIssuer, local["id"])
	if e != nil || Num(check["version"]) != Num(local["version"]) {
		return Error(409, "账号绑定已更改，请重试")
	}
	result["accountState"] = "active"
	result["metrics"] = metrics
	result["items"] = items
	JSON(w, 200, result)
	return nil
}
func workspaceTime(v any) string {
	return time.UnixMilli(int64(Num(v) * 1000)).UTC().Format(time.RFC3339Nano)
}
