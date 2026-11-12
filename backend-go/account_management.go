package fastread

import (
	"database/sql"
	"net/http"
	"strings"
)

type accountInput struct {
	Email         string `json:"email"`
	Password      string `json:"password"`
	DisplayName   string `json:"display_name"`
	Role          string `json:"role"`
	Status        string `json:"status"`
	Reason        string `json:"reason"`
	WorkspaceName string `json:"workspace_name"`
	Disabled      *bool  `json:"disabled"`
}
type preparedAccount struct{ ID, Workspace, Email, Password, Name, WorkspaceName string }

func prepareAccount(d accountInput) (preparedAccount, error) {
	email, e := NormalizeEmail(d.Email)
	if e != nil {
		return preparedAccount{}, e
	}
	if e = ValidatePassword(d.Password); e != nil {
		return preparedAccount{}, e
	}
	name := strings.TrimSpace(d.DisplayName)
	if len([]rune(name)) > 120 {
		return preparedAccount{}, Error(422, "姓名最多 120 个字符")
	}
	hash, e := PasswordHash(d.Password)
	workspace := strings.TrimSpace(d.WorkspaceName)
	if workspace == "" {
		workspace = "我的资料库"
	}
	return preparedAccount{UID(), UID(), email, hash, name, workspace}, e
}
func insertAccount(tx *sql.Tx, u preparedAccount, admin, disabled bool) error {
	if _, e := One(tx, "SELECT id FROM users WHERE email=?", u.Email); e == nil {
		return Error(409, "此邮箱已有账号，请登录后绑定 FastCAS")
	} else if e != sql.ErrNoRows {
		return e
	}
	if _, e := tx.Exec("INSERT INTO users(id,email,password,display_name,created,is_admin,disabled) VALUES(?,?,?,?,?,?,?)", u.ID, u.Email, u.Password, u.Name, Now(), admin, disabled); e != nil {
		return e
	}
	if _, e := tx.Exec("INSERT INTO workspaces(id,name) VALUES(?,?)", u.Workspace, u.WorkspaceName); e != nil {
		return e
	}
	_, e := tx.Exec("INSERT INTO memberships VALUES(?,?,'owner')", u.ID, u.Workspace)
	return e
}
func accountAudit(tx *sql.Tx, actor, target, action, reason string) error {
	_, e := tx.Exec("INSERT INTO admin_account_audit VALUES(?,?,?,?,?,?)", UID(), actor, target, action, reason, Now())
	return e
}
func (a *App) registerAccountAdmin() {
	a.Admin("GET /api/admin/users", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		rows, e := a.Store.All("SELECT u.id,u.email,u.display_name,u.is_admin,u.disabled,u.created,m.workspace_id,w.name workspace_name FROM users u LEFT JOIN memberships m ON m.user_id=u.id LEFT JOIN workspaces w ON w.id=m.workspace_id WHERE u.deleted=0 ORDER BY u.created DESC,w.name")
		if e != nil {
			return e
		}
		for _, u := range rows {
			u["role"] = "user"
			if Num(u["is_admin"]) == 1 || AdminEmail(Str(u["email"])) {
				u["role"] = "admin"
			}
			u["status"] = "active"
			if Num(u["disabled"]) == 1 {
				u["status"] = "disabled"
			}
			u["disabled"] = Num(u["disabled"]) == 1
			delete(u, "is_admin")
		}
		JSON(w, 200, Row{"items": rows})
		return nil
	})
	a.Admin("POST /api/admin/users", func(w http.ResponseWriter, r *http.Request, p Principal) error {
		var d accountInput
		if e := Decode(r, &d); e != nil {
			return e
		}
		if d.Role == "" {
			d.Role = "user"
		}
		if d.Status == "" {
			d.Status = "active"
		}
		if d.Role != "admin" && d.Role != "user" || d.Status != "active" && d.Status != "disabled" {
			return Error(422, "角色或状态无效")
		}
		if strings.TrimSpace(d.Reason) == "" {
			return Error(422, "请填写操作原因")
		}
		u, e := prepareAccount(d)
		if e != nil {
			return e
		}
		e = a.Store.Transaction(func(tx *sql.Tx) error {
			if e := insertAccount(tx, u, d.Role == "admin", d.Status == "disabled"); e != nil {
				return e
			}
			return accountAudit(tx, p.UserID, u.ID, "user.create", d.Reason)
		})
		if e == nil {
			JSON(w, 201, Row{"id": u.ID, "user_id": u.ID, "workspace_id": u.Workspace})
		}
		return e
	})
	for _, method := range []string{"PATCH", "DELETE"} {
		a.Admin(method+" /api/admin/users/{user_id}", func(w http.ResponseWriter, r *http.Request, p Principal) error {
			var d accountInput
			if e := Decode(r, &d); e != nil {
				return e
			}
			if strings.TrimSpace(d.Reason) == "" {
				return Error(422, "请填写操作原因")
			}
			id := r.PathValue("user_id")
			remove := r.Method == "DELETE"
			password := ""
			if d.Password != "" && !remove {
				if e := ValidatePassword(d.Password); e != nil {
					return e
				}
				var e error
				password, e = PasswordHash(d.Password)
				if e != nil {
					return e
				}
			}
			e := a.Store.Transaction(func(tx *sql.Tx) error {
				old, e := One(tx, "SELECT * FROM users WHERE id=? AND deleted=0", id)
				if e != nil {
					return e
				}
				role := "user"
				if Num(old["is_admin"]) == 1 || AdminEmail(Str(old["email"])) {
					role = "admin"
				}
				status := "active"
				if Num(old["disabled"]) == 1 {
					status = "disabled"
				}
				email, name := Str(old["email"]), Str(old["display_name"])
				if d.Role != "" {
					role = d.Role
				}
				if d.Status != "" {
					status = d.Status
				}
				if d.Disabled != nil && d.Status == "" {
					status = "active"
					if *d.Disabled {
						status = "disabled"
					}
				}
				if d.Email != "" {
					email, e = NormalizeEmail(d.Email)
					if e != nil {
						return e
					}
					name = strings.TrimSpace(d.DisplayName)
				}
				if role != "admin" && role != "user" || status != "active" && status != "disabled" || len([]rune(name)) > 120 {
					return Error(422, "账号资料无效")
				}
				removing := remove || role != "admin" || status != "active"
				if removing && id == p.UserID {
					return Error(409, "不能删除、停用或降级当前管理员")
				}
				if removing && (Num(old["is_admin"]) == 1 || AdminEmail(Str(old["email"]))) && Num(old["disabled"]) == 0 {
					rows, e := Rows(tx, "SELECT email,is_admin FROM users WHERE id!=? AND disabled=0 AND deleted=0", id)
					if e != nil {
						return e
					}
					found := false
					for _, u := range rows {
						if Num(u["is_admin"]) == 1 || AdminEmail(Str(u["email"])) {
							found = true
						}
					}
					if !found {
						return Error(409, "必须保留至少一名启用的管理员")
					}
				}
				if !remove && role != "admin" && AdminEmail(email) {
					return Error(409, "此邮箱由服务器配置指定为管理员")
				}
				if remove {
					_, e = tx.Exec("UPDATE users SET deleted=1,disabled=1,is_admin=0,password='',email=?,display_name='已删除用户',research_key_id=NULL,research_account_id=NULL WHERE id=?", id+"@deleted.invalid", id)
				} else {
					duplicate, x := One(tx, "SELECT id FROM users WHERE email=? AND id!=?", email, id)
					if x != nil && x != sql.ErrNoRows {
						return x
					}
					if duplicate != nil {
						return Error(409, "邮箱已使用")
					}
					nextPassword := Str(old["password"])
					if password != "" {
						nextPassword = password
					}
					_, e = tx.Exec("UPDATE users SET email=?,display_name=?,password=?,is_admin=?,disabled=? WHERE id=?", email, name, nextPassword, role == "admin", status == "disabled", id)
				}
				if e != nil {
					return e
				}
				if remove || password != "" || email != Str(old["email"]) || (role == "admin") != (Num(old["is_admin"]) == 1) || (status == "disabled") != (Num(old["disabled"]) == 1) {
					if _, e = tx.Exec("DELETE FROM sessions WHERE user_id=?", id); e != nil {
						return e
					}
				}
				return accountAudit(tx, p.UserID, id, "user."+strings.ToLower(r.Method), d.Reason)
			})
			if e == nil {
				JSON(w, 200, Row{"ok": true})
			}
			return e
		})
	}
}
