package fastread

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"log"
	"net"
	"sync"
	"time"
)

// RunWorker executes durable jobs; API and workers share the same data root.
func RunWorker(ctx context.Context, s *Store, concurrency int) error {
	if concurrency < 1 {
		concurrency = 2
	}
	owner := UID()
	var active sync.WaitGroup
	slots := make(chan struct{}, concurrency)
	ticker := time.NewTicker(500 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			active.Wait()
			return nil
		case <-ticker.C:
			select {
			case slots <- struct{}{}:
			default:
				continue
			}
			job, e := claimJob(s, owner, concurrency)
			if e != nil {
				<-slots
				return e
			}
			if job == nil {
				<-slots
				continue
			}
			active.Add(1)
			go func(job Row) { defer active.Done(); defer func() { <-slots }(); runJob(ctx, s, job, owner) }(job)
		}
	}
}
func claimJob(s *Store, owner string, concurrency int) (Row, error) {
	var job Row
	e := s.Transaction(func(tx *sql.Tx) error {
		now := Now()
		expired, e := Rows(tx, "SELECT * FROM jobs WHERE state='running' AND (lease_until<? OR deadline<?)", now, now)
		if e != nil {
			return e
		}
		for _, old := range expired {
			state, code, message := "queued", "lease_expired", "执行租约过期"
			if Num(old["billable"]) != 0 && Num(old["dispatch_started"]) != 0 {
				state, code, message = "needs_attention", "dispatch_outcome_unknown", "执行中断；请检查计费请求结果"
			} else if Num(old["attempts"]) >= Num(old["max_attempts"]) {
				state = "failed"
			}
			if _, e = tx.Exec("UPDATE jobs SET state=?,lease_owner=NULL,lease_until=NULL,error_code=?,error=?,updated=? WHERE id=?", state, code, message, now, old["id"]); e != nil {
				return e
			}
		}
		count, e := One(tx, "SELECT count(*) n FROM jobs WHERE state='running'")
		if e != nil {
			return e
		}
		if Num(count["n"]) >= float64(concurrency) {
			return nil
		}
		job, e = One(tx, "SELECT j.* FROM jobs j WHERE state='queued' AND available<=? AND (SELECT count(*) FROM jobs r WHERE r.workspace_id=j.workspace_id AND r.state='running')<1 ORDER BY created LIMIT 1", now)
		if e == sql.ErrNoRows {
			job = nil
			return nil
		}
		if e != nil {
			return e
		}
		_, e = tx.Exec("UPDATE jobs SET state='running',attempts=attempts+1,lease_owner=?,lease_until=?,deadline=?,updated=? WHERE id=?", owner, now+45, now+900, now, job["id"])
		if e != nil {
			return e
		}
		job, e = One(tx, "SELECT * FROM jobs WHERE id=?", job["id"])
		return e
	})
	return job, e
}
func runJob(parent context.Context, s *Store, job Row, owner string) {
	ctx, cancel := context.WithTimeout(parent, 15*time.Minute)
	defer cancel()
	done := make(chan struct{})
	go func() {
		ticker := time.NewTicker(10 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-done:
				return
			case <-ctx.Done():
				return
			case <-ticker.C:
				result, e := s.DB.Exec("UPDATE jobs SET lease_until=?,updated=? WHERE id=? AND lease_owner=? AND state='running' AND deadline>?", Now()+45, Now(), job["id"], owner, Now())
				if e != nil {
					cancel()
					return
				}
				n, _ := result.RowsAffected()
				if n != 1 {
					cancel()
					return
				}
			}
		}
	}()
	err := ExecuteJob(ctx, s, job, owner)
	close(done)
	if err != nil {
		failJob(s, job, owner, err)
		log.Printf("job=%s kind=%s failed=%T", Str(job["id"]), Str(job["kind"]), err)
	}
}
func assertLease(tx *sql.Tx, job Row, owner string) error {
	_, e := One(tx, "SELECT id FROM jobs WHERE id=? AND lease_owner=? AND state='running' AND lease_until>? AND deadline>?", job["id"], owner, Now(), Now())
	if e != nil {
		return errors.New("job lease lost")
	}
	return nil
}
func completeJob(tx *sql.Tx, job Row, result Row) error {
	_, e := tx.Exec("UPDATE jobs SET state='succeeded',result=?,lease_owner=NULL,lease_until=NULL,error=NULL,error_code=NULL,updated=? WHERE id=?", Encode(result), Now(), job["id"])
	return e
}
func failJob(s *Store, job Row, owner string, cause error) {
	code, message, retry := "invalid_input", "输入或生成结果未通过校验", false
	var netErr net.Error
	if errors.Is(cause, context.DeadlineExceeded) || errors.Is(cause, context.Canceled) {
		code, message, retry = "timeout", "任务执行超时或已停止", true
	} else if errors.As(cause, &netErr) {
		code, message, retry = "transport", "上游连接中断", true
	}
	_ = s.Transaction(func(tx *sql.Tx) error {
		row, e := One(tx, "SELECT * FROM jobs WHERE id=? AND lease_owner=? AND state='running'", job["id"], owner)
		if e != nil {
			return nil
		}
		state := "failed"
		if retry && Num(row["billable"]) != 0 && Num(row["dispatch_started"]) != 0 {
			state = "needs_attention"
		} else if retry && Num(row["billable"]) == 0 && Num(row["attempts"]) < Num(row["max_attempts"]) {
			state = "queued"
		}
		_, e = tx.Exec("UPDATE jobs SET state=?,error_code=?,error=?,available=?,lease_owner=NULL,lease_until=NULL,updated=? WHERE id=?", state, code, message, Now()+5, Now(), job["id"])
		return e
	})
}

func ExecuteJob(ctx context.Context, s *Store, job Row, owner string) error {
	payload := Object(job["payload"])
	kind := Str(job["kind"])
	switch kind {
	case "import_pdf", "import_url":
		return executeImport(ctx, s, job, owner, payload)
	case "organize", "knowledge_chat", "book_questions":
		return executeKnowledge(ctx, s, job, owner, payload)
	case "research_directions":
		return executeDirections(ctx, s, job, owner, payload)
	}
	pid := Str(job["resource_id"])
	if kind == "chat" {
		conversation, e := s.One("SELECT * FROM conversations WHERE id=? AND workspace_id=?", pid, job["workspace_id"])
		if e != nil {
			return e
		}
		pid = Str(conversation["paper_id"])
	}
	paper, _, document, e := s.Document(Str(job["workspace_id"]), pid, Str(job["version_id"]))
	if e != nil {
		return e
	}
	var result Row
	switch kind {
	case "index":
		return s.Transaction(func(tx *sql.Tx) error {
			if e := assertLease(tx, job, owner); e != nil {
				return e
			}
			if _, e := tx.Exec("DELETE FROM evidence_chunks WHERE version_id=?", job["version_id"]); e != nil {
				return e
			}
			pages, _ := document["pages"].([]Row)
			count := 0
			for _, page := range pages {
				for i, text := range chunkText(Str(page["text"]), 1600) {
					if _, e := tx.Exec("INSERT INTO evidence_chunks VALUES(?,?,?,?,?)", fmt.Sprintf("%s:p%v:c%d", Str(job["version_id"]), page["page"], i), job["version_id"], page["page"], i, text); e != nil {
						return e
					}
					count++
				}
			}
			return completeJob(tx, job, Row{"version_id": job["version_id"], "chunks": count, "engine": "versioned_lexical"})
		})
	case "neighbors":
		result = discoverNeighbors(ctx, s, paper, document)
	case "report":
		result, e = generateReport(ctx, s, job, owner, payload, paper)
	case "chat":
		result, e = generateChat(ctx, s, job, owner, payload, paper)
	default:
		return fmt.Errorf("unsupported job kind: %s", kind)
	}
	if e != nil {
		return e
	}
	return s.Transaction(func(tx *sql.Tx) error {
		if e := assertLease(tx, job, owner); e != nil {
			return e
		}
		switch kind {
		case "report":
			id := UID()
			if _, e := tx.Exec("INSERT INTO report_versions VALUES(?,?,?,?,?,?)", id, pid, job["version_id"], job["id"], Encode(result), Now()); e != nil {
				return e
			}
			result = Row{"report_id": id, "paper_id": pid, "version_id": job["version_id"]}
		case "chat":
			id := UID()
			if _, e := tx.Exec("INSERT INTO messages VALUES(?,?,?,?,?,?,?)", id, job["resource_id"], "assistant", result["answer"], Encode(result), job["id"], Now()); e != nil {
				return e
			}
			result = Row{"message_id": id, "conversation_id": job["resource_id"]}
		}
		return completeJob(tx, job, result)
	})
}
