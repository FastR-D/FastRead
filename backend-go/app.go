package fastread

import (
	"database/sql"
	"encoding/json"
	"errors"
	"io"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
)

const Version = "4.0.0"

type HTTPError struct {
	Status  int
	Message string
}

func (e *HTTPError) Error() string           { return e.Message }
func Error(status int, message string) error { return &HTTPError{status, message} }
func JSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}
func Fail(w http.ResponseWriter, err error) {
	var h *HTTPError
	if errors.As(err, &h) {
		JSON(w, h.Status, Row{"detail": h.Message})
		return
	}
	if errors.Is(err, sql.ErrNoRows) {
		JSON(w, 404, Row{"detail": "记录不存在"})
		return
	}
	log.Printf("request failed: %T", err)
	JSON(w, 500, Row{"detail": "服务器暂时无法完成请求"})
}
func Decode(r *http.Request, target any) error {
	d := json.NewDecoder(io.LimitReader(r.Body, 2<<20))
	if e := d.Decode(target); e != nil {
		return Error(422, "请求内容无效")
	}
	return nil
}
func QueryInt(r *http.Request, key string, def, min, max int) int {
	n, e := strconv.Atoi(r.URL.Query().Get(key))
	if e != nil {
		return def
	}
	if n < min {
		return min
	}
	if n > max {
		return max
	}
	return n
}

type Principal struct {
	UserID, WorkspaceID, Email, Role, CSRF, DisplayName, ResearchKeyID, ResearchAccountID string
	IsAdmin                                                                               bool
}
type App struct {
	Store              *Store
	Mux                *http.ServeMux
	ValidateCASSession func(Row) error
}

func NewApp(s *Store) *App {
	a := &App{Store: s, Mux: http.NewServeMux()}
	a.RegisterAuth()
	a.RegisterResearch()
	a.RegisterCore()
	a.RegisterAdmin()
	return a
}
func (a *App) Handle(pattern string, h func(http.ResponseWriter, *http.Request, Principal) error) {
	a.Mux.HandleFunc(pattern, func(w http.ResponseWriter, r *http.Request) {
		p, e := a.RequireUser(r)
		if e == nil {
			e = h(w, r, p)
		}
		if e != nil {
			Fail(w, e)
		}
	})
}
func (a *App) Public(pattern string, h func(http.ResponseWriter, *http.Request) error) {
	a.Mux.HandleFunc(pattern, func(w http.ResponseWriter, r *http.Request) {
		if e := h(w, r); e != nil {
			Fail(w, e)
		}
	})
}
func (a *App) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.Header().Set("Referrer-Policy", "same-origin")
	w.Header().Set("X-Frame-Options", "SAMEORIGIN")
	if strings.HasPrefix(r.URL.Path, "/api/") {
		w.Header().Set("Cache-Control", "no-store")
	}
	if r.Method != "GET" && r.Method != "HEAD" && r.Method != "OPTIONS" && r.Header.Get("Origin") != "" {
		expected := strings.TrimRight(os.Getenv("FASTREAD_PUBLIC_ORIGIN"), "/")
		if expected == "" {
			scheme := "http"
			if r.TLS != nil {
				scheme = "https"
			}
			expected = scheme + "://" + r.Host
		}
		if strings.TrimRight(r.Header.Get("Origin"), "/") != expected {
			Fail(w, Error(403, "不允许跨站请求"))
			return
		}
	}
	if a.ResearchDocument(w, r) {
		return
	}
	a.Mux.ServeHTTP(w, r)
}
func RequireOwner(p Principal) error {
	if p.Role != "owner" {
		return Error(403, "需要工作区管理员权限")
	}
	return nil
}
func RequireAdmin(p Principal) error {
	if !p.IsAdmin {
		return Error(403, "需要系统管理员权限")
	}
	return nil
}
