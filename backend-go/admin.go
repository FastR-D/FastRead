package fastread

import (
	"database/sql"
	"net/http"
)

func (a *App) Admin(pattern string, h func(http.ResponseWriter, *http.Request, Principal) error) {
	a.Handle(pattern, func(w http.ResponseWriter, r *http.Request, p Principal) error {
		if e := RequireAdmin(p); e != nil {
			return e
		}
		return h(w, r, p)
	})
}
func (a *App) RegisterAdmin() {
	a.registerAccountAdmin()
	a.Admin("GET /api/admin/workspaces", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		rows, e := a.Store.All("SELECT id,name,daily_limit FROM workspaces ORDER BY name")
		if e == nil {
			JSON(w, 200, Row{"items": rows})
		}
		return e
	})
	a.Admin("GET /api/admin/status", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		row, e := a.Store.One("SELECT (SELECT count(*) FROM users) users,(SELECT count(*) FROM papers WHERE archived=0) papers,(SELECT count(*) FROM jobs WHERE state='queued') queued,(SELECT count(*) FROM jobs WHERE state='running') running")
		if e != nil {
			return e
		}
		row["version"] = Version
		row["backend"] = "go"
		JSON(w, 200, row)
		return nil
	})
	a.Admin("GET /api/admin/providers", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		rows, e := a.Store.All("SELECT id,name,base_url,models,enabled,created FROM shared_providers ORDER BY created")
		if e != nil {
			return e
		}
		for _, row := range rows {
			row["models"] = Array(row["models"])
			row["enabled"] = Num(row["enabled"]) == 1
			items, e := a.Store.All("SELECT workspace_id FROM shared_provider_workspaces WHERE provider_id=? ORDER BY workspace_id", row["id"])
			if e != nil {
				return e
			}
			ids := []string{}
			for _, item := range items {
				ids = append(ids, Str(item["workspace_id"]))
			}
			row["workspace_ids"] = ids
		}
		JSON(w, 200, Row{"items": rows})
		return nil
	})
	a.Admin("POST /api/admin/providers", func(w http.ResponseWriter, r *http.Request, p Principal) error {
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
		e = a.Store.Transaction(func(tx *sql.Tx) error {
			if _, e := tx.Exec("INSERT INTO shared_providers VALUES(?,?,?,?,?,1,?)", id, d.Name, d.BaseURL, secret, Encode(d.Models), Now()); e != nil {
				return e
			}
			return assignWorkspaces(tx, id, d.WorkspaceIDs)
		})
		if e == nil {
			JSON(w, 201, Row{"id": id, "name": d.Name})
		}
		return e
	})
	a.Admin("PATCH /api/admin/providers/{provider_id}", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		var d struct {
			Enabled      *bool
			WorkspaceIDs *[]string `json:"workspace_ids"`
		}
		if e := Decode(r, &d); e != nil {
			return e
		}
		id := r.PathValue("provider_id")
		e := a.Store.Transaction(func(tx *sql.Tx) error {
			if _, e := One(tx, "SELECT id FROM shared_providers WHERE id=?", id); e != nil {
				return e
			}
			if d.Enabled != nil {
				if _, e := tx.Exec("UPDATE shared_providers SET enabled=? WHERE id=?", *d.Enabled, id); e != nil {
					return e
				}
			}
			if d.WorkspaceIDs != nil {
				return assignWorkspaces(tx, id, *d.WorkspaceIDs)
			}
			return nil
		})
		if e == nil {
			JSON(w, 200, Row{"ok": true})
		}
		return e
	})
}
func assignWorkspaces(tx *sql.Tx, id string, ids []string) error {
	if _, e := tx.Exec("DELETE FROM shared_provider_workspaces WHERE provider_id=?", id); e != nil {
		return e
	}
	for _, ws := range ids {
		if _, e := One(tx, "SELECT id FROM workspaces WHERE id=?", ws); e != nil {
			return Error(422, "工作区不存在")
		}
		if _, e := tx.Exec("INSERT OR IGNORE INTO shared_provider_workspaces VALUES(?,?)", id, ws); e != nil {
			return e
		}
	}
	return nil
}
