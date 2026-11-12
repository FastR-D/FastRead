package fastread

import (
	"crypto/rand"
	"database/sql"
	_ "embed"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	_ "modernc.org/sqlite"
	"os"
	"path/filepath"
	"strings"
	"time"
)

//go:embed schema.sql
var schema string

type Row = map[string]any
type Store struct {
	DB   *sql.DB
	Root string
}
type Queryer interface {
	Query(string, ...any) (*sql.Rows, error)
	Exec(string, ...any) (sql.Result, error)
}

func UID() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		panic(err)
	}
	b[6] = (b[6] & 15) | 64
	b[8] = (b[8] & 63) | 128
	h := hex.EncodeToString(b[:])
	return h[:8] + "-" + h[8:12] + "-" + h[12:16] + "-" + h[16:20] + "-" + h[20:]
}
func Now() float64 { return float64(time.Now().UnixMilli()) / 1000 }
func Encode(v any) string {
	b, e := json.Marshal(v)
	if e != nil {
		panic(e)
	}
	return string(b)
}
func Object(v any) Row {
	var result Row
	_ = json.Unmarshal([]byte(Str(v)), &result)
	if result == nil {
		result = Row{}
	}
	return result
}
func Array(v any) []any {
	var result []any
	_ = json.Unmarshal([]byte(Str(v)), &result)
	if result == nil {
		result = []any{}
	}
	return result
}
func Str(v any) string {
	if v == nil {
		return ""
	}
	if s, ok := v.(string); ok {
		return s
	}
	if b, ok := v.([]byte); ok {
		return string(b)
	}
	return fmt.Sprint(v)
}
func Num(v any) float64 {
	switch n := v.(type) {
	case int:
		return float64(n)
	case int64:
		return float64(n)
	case float64:
		return n
	case json.Number:
		f, _ := n.Float64()
		return f
	}
	return 0
}
func OpenStore(root string) (*Store, error) {
	if root == "" {
		root = os.Getenv("FASTREAD_WEB_ROOT")
	}
	if root == "" {
		root = "web-data"
	}
	root, err := filepath.Abs(root)
	if err != nil {
		return nil, err
	}
	if err = os.MkdirAll(filepath.Join(root, "files"), 0700); err != nil {
		return nil, err
	}
	db, err := sql.Open("sqlite", filepath.Join(root, "fastread-web.sqlite3")+"?_pragma=foreign_keys(1)&_pragma=busy_timeout(30000)")
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(1)
	s := &Store{DB: db, Root: root}
	if _, err = db.Exec("PRAGMA journal_mode=WAL;" + schema); err != nil {
		db.Close()
		return nil, err
	}
	for table, columns := range map[string]map[string]string{"users": {"research_key_id": "TEXT", "research_account_id": "TEXT", "display_name": "TEXT", "is_admin": "INTEGER NOT NULL DEFAULT 0", "disabled": "INTEGER NOT NULL DEFAULT 0", "deleted": "INTEGER NOT NULL DEFAULT 0"}, "sessions": {"auth_source": "TEXT NOT NULL DEFAULT 'legacy'", "authenticated_at": "REAL", "cas_issuer": "TEXT", "cas_sid": "TEXT", "cas_link_id": "TEXT", "cas_link_version": "INTEGER", "cas_checked": "REAL"}, "papers": {"archived": "INTEGER NOT NULL DEFAULT 0"}} {
		info, e := s.All("PRAGMA table_info(" + table + ")")
		if e != nil {
			return nil, e
		}
		present := map[string]bool{}
		for _, r := range info {
			present[Str(r["name"])] = true
		}
		for name, def := range columns {
			if !present[name] {
				if _, e = db.Exec("ALTER TABLE " + table + " ADD COLUMN " + name + " " + def); e != nil {
					return nil, e
				}
			}
		}
	}
	_, err = db.Exec("CREATE UNIQUE INDEX IF NOT EXISTS users_research_account_id ON users(research_account_id) WHERE research_account_id IS NOT NULL; CREATE UNIQUE INDEX IF NOT EXISTS users_research_key_id ON users(research_key_id) WHERE research_key_id IS NOT NULL AND research_key_id!=''; INSERT OR IGNORE INTO schema_versions VALUES(1,?);", Now())
	if err != nil {
		return nil, err
	}
	if _, e := s.One("SELECT name FROM knowledge_migrations WHERE name='legacy-topics-v1'"); errors.Is(e, sql.ErrNoRows) {
		err = s.Transaction(func(tx *sql.Tx) error {
			if _, e := tx.Exec("INSERT OR IGNORE INTO knowledge_bases SELECT id,workspace_id,question,scope,created FROM topics"); e != nil {
				return e
			}
			if _, e := tx.Exec("INSERT OR IGNORE INTO knowledge_papers SELECT DISTINCT e.topic_id,e.paper_id,'manual',? FROM topic_evidence e JOIN topics t ON t.id=e.topic_id JOIN papers p ON p.id=e.paper_id AND p.workspace_id=t.workspace_id", Now()); e != nil {
				return e
			}
			_, e := tx.Exec("INSERT INTO knowledge_migrations VALUES('legacy-topics-v1',?)", Now())
			return e
		})
		if err != nil {
			return nil, err
		}
	}
	_ = os.Chmod(filepath.Join(root, "fastread-web.sqlite3"), 0600)
	return s, nil
}
func Rows(q Queryer, query string, args ...any) ([]Row, error) {
	rows, err := q.Query(query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	columns, err := rows.Columns()
	if err != nil {
		return nil, err
	}
	result := []Row{}
	for rows.Next() {
		values := make([]any, len(columns))
		dest := make([]any, len(columns))
		for i := range values {
			dest[i] = &values[i]
		}
		if err = rows.Scan(dest...); err != nil {
			return nil, err
		}
		r := Row{}
		for i, c := range columns {
			if b, ok := values[i].([]byte); ok {
				values[i] = string(b)
			}
			r[c] = values[i]
		}
		result = append(result, r)
	}
	return result, rows.Err()
}
func One(q Queryer, query string, args ...any) (Row, error) {
	rows, e := Rows(q, query, args...)
	if e != nil {
		return nil, e
	}
	if len(rows) == 0 {
		return nil, sql.ErrNoRows
	}
	return rows[0], nil
}
func (s *Store) All(query string, args ...any) ([]Row, error) { return Rows(s.DB, query, args...) }
func (s *Store) One(query string, args ...any) (Row, error)   { return One(s.DB, query, args...) }
func (s *Store) Paper(workspace, id string) (Row, error) {
	return s.One("SELECT * FROM papers WHERE workspace_id=? AND id=? AND archived=0", workspace, id)
}
func (s *Store) Document(workspace, id, version string) (Row, Row, Row, error) {
	p, e := s.Paper(workspace, id)
	if e != nil {
		return nil, nil, nil, e
	}
	if version == "" {
		version = Str(p["active_version"])
	}
	v, e := s.One("SELECT * FROM document_versions WHERE id=? AND paper_id=?", version, id)
	if e != nil {
		return nil, nil, nil, e
	}
	d := Object(v["metadata"])
	d["id"] = id
	d["document_version_id"] = version
	d["pages"], e = s.All("SELECT number AS page,text FROM pages WHERE version_id=? ORDER BY number", version)
	return p, v, d, e
}
func (s *Store) Transaction(fn func(*sql.Tx) error) error {
	tx, e := s.DB.Begin()
	if e != nil {
		return e
	}
	defer tx.Rollback()
	if e = fn(tx); e != nil {
		return e
	}
	return tx.Commit()
}
func (s *Store) Enqueue(user Principal, kind string, payload Row, key, resource, version string, billable bool) (Row, error) {
	var row Row
	err := s.Transaction(func(tx *sql.Tx) error {
		var e error
		row, e = EnqueueTx(tx, user, kind, payload, key, resource, version, billable)
		return e
	})
	return row, err
}
func EnqueueTx(tx *sql.Tx, user Principal, kind string, payload Row, key, resource, version string, billable bool) (Row, error) {
	if key == "" || len(key) > 160 {
		return nil, Error(400, "需要有效 Idempotency-Key")
	}
	old, e := One(tx, "SELECT * FROM jobs WHERE workspace_id=? AND dedupe_key=?", user.WorkspaceID, key)
	if e == nil {
		if Str(old["kind"]) != kind || Str(old["resource_id"]) != resource || Encode(Object(old["payload"])) != Encode(payload) {
			return nil, Error(409, "idempotency_key_conflict")
		}
		return old, nil
	}
	if !errors.Is(e, sql.ErrNoRows) {
		return nil, e
	}
	if billable {
		r, e := One(tx, "SELECT daily_limit,(SELECT count(*) FROM jobs WHERE workspace_id=? AND billable=1 AND created>=?) n FROM workspaces WHERE id=?", user.WorkspaceID, Now()-86400, user.WorkspaceID)
		if e != nil {
			return nil, e
		}
		if Num(r["n"]) >= Num(r["daily_limit"]) {
			return nil, Error(429, "daily_model_limit")
		}
	}
	r, e := One(tx, "SELECT count(*) n FROM jobs WHERE workspace_id=? AND state IN ('queued','running')", user.WorkspaceID)
	if e != nil {
		return nil, e
	}
	if Num(r["n"]) >= 30 {
		return nil, Error(429, "workspace_queue_full")
	}
	id := UID()
	_, e = tx.Exec("INSERT INTO jobs(id,workspace_id,user_id,kind,resource_id,version_id,dedupe_key,payload,state,available,billable,created,updated) VALUES(?,?,?,?,?,?,?,?,'queued',?,?,?,?)", id, user.WorkspaceID, user.UserID, kind, Null(resource), Null(version), key, Encode(payload), Now(), billable, Now(), Now())
	if e != nil {
		return nil, e
	}
	return One(tx, "SELECT * FROM jobs WHERE id=?", id)
}
func Null(s string) any {
	if s == "" {
		return nil
	}
	return s
}
func JobView(row Row) Row {
	r := Row{}
	for _, k := range strings.Fields("id kind resource_id version_id state attempts error_code error created updated") {
		r[k] = row[k]
	}
	r["result"] = nil
	if row["result"] != nil {
		var v any
		_ = json.Unmarshal([]byte(Str(row["result"])), &v)
		r["result"] = v
	}
	return r
}
