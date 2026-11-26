package fastread

import (
	"context"
	"database/sql"
	"net/http"

	fastcas "github.com/FastR-D/FastCAS/sdk/go"
)

const connectionScope = "fastread:connect"

type connectionIssuer interface {
	ClientCredentials(context.Context, []string) (*fastcas.TokenResponse, error)
}

// Resolve the current local account, never an email or a subject supplied by a browser.
func (a *App) exchangeIdentity(r *http.Request, p Principal) (string, error) {
	if a.workspaceCAS == nil {
		return "", Error(409, "请先配置 FastCAS 并认证当前账号")
	}
	local, err := a.Store.One("SELECT * FROM fastcas_links WHERE issuer=? AND client_id=? AND user_id=? ORDER BY version DESC LIMIT 1", a.workspaceIssuer, a.workspaceClient, p.UserID)
	if err != nil || Str(local["state"]) != "active" {
		return "", Error(409, "请先认证当前账号的 FastCAS 身份")
	}
	remote, err := a.workspaceCAS.ResolveLink(r.Context(), Str(local["subject"]))
	if err != nil {
		return "", Error(503, "暂时无法确认 FastCAS 身份，请稍后重试")
	}
	if remote == nil || remote.ID != Str(local["id"]) || remote.ClientID != a.workspaceClient || remote.LocalRef != p.UserID || remote.Subject != Str(local["subject"]) || remote.State != "active" || remote.Version != int64(Num(local["version"])) {
		return "", Error(403, "FastCAS 身份绑定已更改，请重新认证")
	}
	// A revocation delivered while resolving the link must take effect immediately.
	current, err := a.Store.One("SELECT state,version FROM fastcas_links WHERE issuer=? AND id=?", a.workspaceIssuer, remote.ID)
	if err != nil || Str(current["state"]) != "active" || int64(Num(current["version"])) != remote.Version {
		return "", Error(403, "FastCAS 身份绑定已更改")
	}
	return remote.Subject, nil
}

func (a *App) registerCASExchange() error {
	_, err := a.Store.DB.Exec(`CREATE TABLE IF NOT EXISTS integration_cas_links(workspace_id TEXT NOT NULL,service TEXT NOT NULL,user_id TEXT NOT NULL,issuer TEXT NOT NULL,subject TEXT NOT NULL,link_id TEXT NOT NULL,version INTEGER NOT NULL,PRIMARY KEY(workspace_id,service));`)
	if err != nil {
		return err
	}
	a.Handle("POST /api/integrations/connections/{service}/cas", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		if err := RequireOwner(p); err != nil {
			return err
		}
		service := r.PathValue("service")
		if !validService(service) {
			return Error(404, "联动服务不存在")
		}
		subject, err := a.exchangeIdentity(r, p)
		if err != nil {
			return err
		}
		issuer := a.exchangeCAS
		if issuer == nil {
			return Error(503, "请配置 FastRead 同步服务身份 fastread-sync")
		}
		grant, err := issuer.ClientCredentials(r.Context(), []string{connectionScope})
		if err != nil || grant == nil || grant.AccessToken == "" {
			return Error(503, "FastCAS 尚未授予 FastRead 联动权限（fastread:connect）")
		}
		response, err := exchangeRequest(r, service, grant.AccessToken, "POST", "/api/integrations/fastread/cas-connect", Row{"subject": subject})
		if err != nil {
			return err
		}
		token := Str(response["token"])
		if Str(response["subject"]) != subject || len(token) < 24 || len(token) > 256 {
			return Error(502, "目标应用未确认同一 FastCAS 身份")
		}
		// Check again before retaining a durable connection.
		current, err := a.exchangeIdentity(r, p)
		if err != nil {
			return err
		}
		if current != subject {
			return Error(409, "身份已更改，请重新连接")
		}
		local, err := a.Store.One("SELECT id,version FROM fastcas_links WHERE issuer=? AND client_id=? AND user_id=? AND subject=? AND state='active'", a.workspaceIssuer, a.workspaceClient, p.UserID, subject)
		if err != nil {
			return Error(403, "CAS 绑定已更改")
		}
		secret, err := a.Store.ProtectSecret(token)
		if err != nil {
			return err
		}
		err = a.Store.Transaction(func(tx *sql.Tx) error {
			_, err := tx.Exec("INSERT INTO integration_connections VALUES(?,?,?,?) ON CONFLICT(workspace_id,service) DO UPDATE SET secret=excluded.secret,created=excluded.created", p.WorkspaceID, service, secret, Now())
			if err != nil {
				return err
			}
			_, err = tx.Exec("INSERT INTO integration_cas_links VALUES(?,?,?,?,?,?,?) ON CONFLICT(workspace_id,service) DO UPDATE SET user_id=excluded.user_id,issuer=excluded.issuer,subject=excluded.subject,link_id=excluded.link_id,version=excluded.version", p.WorkspaceID, service, p.UserID, a.workspaceIssuer, subject, local["id"], local["version"])
			return err
		})
		if err != nil {
			return err
		}
		JSON(w, 200, Row{"ok": true, "mode": "cas"})
		return nil
	})
	return nil
}
