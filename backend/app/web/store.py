from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


def uid() -> str:
    return str(uuid.uuid4())


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_versions(version INTEGER PRIMARY KEY, applied REAL NOT NULL);
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL,
 password TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS workspaces(id TEXT PRIMARY KEY, name TEXT NOT NULL, daily_limit INTEGER NOT NULL DEFAULT 50);
CREATE TABLE IF NOT EXISTS memberships(user_id TEXT REFERENCES users(id), workspace_id TEXT REFERENCES workspaces(id),
 role TEXT NOT NULL CHECK(role IN ('owner','member')), PRIMARY KEY(user_id,workspace_id));
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id),
 workspace_id TEXT REFERENCES workspaces(id), csrf TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS login_attempts(key TEXT PRIMARY KEY, failures INTEGER NOT NULL, until REAL NOT NULL);
CREATE TABLE IF NOT EXISTS providers(id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
 name TEXT NOT NULL, base_url TEXT NOT NULL, secret TEXT NOT NULL, models TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS papers(id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
 identity TEXT NOT NULL, title TEXT NOT NULL, metadata TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
 active_version TEXT, created REAL NOT NULL, archived INTEGER NOT NULL DEFAULT 0, UNIQUE(workspace_id,identity));
CREATE TABLE IF NOT EXISTS paper_identities(workspace_id TEXT NOT NULL REFERENCES workspaces(id),
 identity TEXT NOT NULL, paper_id TEXT NOT NULL REFERENCES papers(id), PRIMARY KEY(workspace_id,identity));
CREATE TABLE IF NOT EXISTS document_versions(id TEXT PRIMARY KEY, paper_id TEXT NOT NULL REFERENCES papers(id),
 fingerprint TEXT NOT NULL, metadata TEXT NOT NULL, file_path TEXT, created REAL NOT NULL,
 UNIQUE(paper_id,fingerprint));
CREATE TABLE IF NOT EXISTS pages(version_id TEXT NOT NULL REFERENCES document_versions(id),
 number INTEGER NOT NULL, text TEXT NOT NULL, PRIMARY KEY(version_id,number));
CREATE TABLE IF NOT EXISTS evidence_chunks(id TEXT PRIMARY KEY, version_id TEXT NOT NULL REFERENCES document_versions(id),
 page INTEGER NOT NULL, ordinal INTEGER NOT NULL, text TEXT NOT NULL, UNIQUE(version_id,page,ordinal));
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
 user_id TEXT NOT NULL REFERENCES users(id), kind TEXT NOT NULL,
 resource_id TEXT, version_id TEXT, dedupe_key TEXT NOT NULL, payload TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('queued','running','succeeded','failed','needs_attention','cancelled')),
 attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 3,
 available REAL NOT NULL, lease_owner TEXT, lease_until REAL, deadline REAL,
 billable INTEGER NOT NULL DEFAULT 0, dispatch_started INTEGER NOT NULL DEFAULT 0,
 error_code TEXT, error TEXT, result TEXT, created REAL NOT NULL, updated REAL NOT NULL,
 UNIQUE(workspace_id,dedupe_key));
CREATE INDEX IF NOT EXISTS jobs_claim ON jobs(state,available,created);
CREATE INDEX IF NOT EXISTS jobs_workspace ON jobs(workspace_id,created);
CREATE INDEX IF NOT EXISTS papers_page ON papers(workspace_id,created,id);
CREATE TABLE IF NOT EXISTS report_versions(id TEXT PRIMARY KEY, paper_id TEXT NOT NULL REFERENCES papers(id),
 version_id TEXT NOT NULL REFERENCES document_versions(id), job_id TEXT UNIQUE REFERENCES jobs(id),
 content TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
 paper_id TEXT NOT NULL REFERENCES papers(id), version_id TEXT NOT NULL REFERENCES document_versions(id), created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
 role TEXT NOT NULL CHECK(role IN ('user','assistant')), content TEXT NOT NULL, evidence TEXT NOT NULL DEFAULT '{}',
 job_id TEXT REFERENCES jobs(id), created REAL NOT NULL, UNIQUE(job_id,role));
CREATE TABLE IF NOT EXISTS provider_cache(key TEXT PRIMARY KEY, content TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS provider_cooldown(provider TEXT PRIMARY KEY, until REAL NOT NULL);
CREATE TABLE IF NOT EXISTS migration_records(source TEXT PRIMARY KEY, paper_id TEXT NOT NULL, version_id TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS legacy_archive(workspace_id TEXT NOT NULL REFERENCES workspaces(id), source TEXT NOT NULL,
 table_name TEXT NOT NULL, record_id TEXT NOT NULL, content TEXT NOT NULL, PRIMARY KEY(workspace_id,source,table_name,record_id));
CREATE TABLE IF NOT EXISTS topics(id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
 question TEXT NOT NULL, scope TEXT NOT NULL, hypotheses TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS topic_evidence(id TEXT PRIMARY KEY, topic_id TEXT NOT NULL REFERENCES topics(id),
 paper_id TEXT REFERENCES papers(id), version_id TEXT REFERENCES document_versions(id), page INTEGER,
 quote TEXT NOT NULL, note TEXT NOT NULL, role TEXT NOT NULL, location_status TEXT NOT NULL);
"""


class Store:
    def __init__(self, root: Path | str | None = None):
        self.root = Path(root or os.environ.get("FASTREAD_WEB_ROOT", "web-data")).resolve()
        self.path = self.root / "fastread-web.sqlite3"

    def initialize(self):
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "files").mkdir(exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
            if "archived" not in {row[1] for row in db.execute("PRAGMA table_info(papers)")}:
                db.execute("ALTER TABLE papers ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
            db.execute("INSERT OR IGNORE INTO schema_versions VALUES(1,?)", (time.time(),))

    @contextmanager
    def connect(self, *, write=False):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=30000")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def one(self, sql, args=()):
        with self.connect() as db:
            row = db.execute(sql, args).fetchone()
            return dict(row) if row else None

    def all(self, sql, args=()):
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, args)]

    def paper(self, workspace: str, paper_id: str):
        return self.one("SELECT * FROM papers WHERE id=? AND workspace_id=? AND archived=0", (paper_id, workspace))

    def document(self, workspace: str, paper_id: str, version_id=None):
        paper = self.paper(workspace, paper_id)
        if not paper:
            raise LookupError("paper_not_found")
        version = self.one("SELECT * FROM document_versions WHERE id=? AND paper_id=?",
                           (version_id or paper["active_version"], paper_id))
        if not version:
            raise LookupError("document_not_found")
        document = json.loads(version["metadata"])
        document.update(id=paper_id, document_version_id=version["id"])
        document["pages"] = self.all("SELECT number AS page,text FROM pages WHERE version_id=? ORDER BY number", (version["id"],))
        return paper, version, document

    def ingest(self, workspace: str, document: dict, *, file_path=None, source_key=None, db=None):
        """Atomically publish immutable document/pages/chunks and the active-version pointer."""
        if db is None:
            with self.connect(write=True) as connection:
                return self.ingest(workspace, document, file_path=file_path, source_key=source_key, db=connection)
        from app.services.metadata_normalization import canonical_identity_keys
        from app.services.chat_service import _chunk_page
        import hashlib
        pages = document.get("pages") or []
        if not pages:
            raise ValueError("document_has_no_pages")
        # Content digest is required for import deduplication, not a delivery checksum.
        content_fingerprint = hashlib.sha256(encode(pages).encode()).hexdigest()
        contract = document.get("metadata_contract") or {}
        # A successful extraction/registry retry can improve the same PDF. Keep
        # that as an immutable metadata revision without keying on timestamps.
        metadata_revision = {key: document.get(key) for key in ("title", "authors", "year", "doi")}
        metadata_revision["resolution"] = (document.get("metadata_resolution") or {}).get("status")
        fingerprint = hashlib.sha256(encode([pages, contract.get("parser_version", ""),
            contract.get("strategy_version", ""), metadata_revision]).encode()).hexdigest()
        import re
        identities = sorted({re.sub(r"v\d+$", "", key) if key.startswith("arxiv:") else key
                             for key in canonical_identity_keys(document) if key.startswith(("doi:","arxiv:","openreview:"))})
        identity = next((x for x in identities if x.startswith("doi:")), None)
        identity = identity or next((x for x in identities if x.startswith("arxiv:")), None) or "content:" + content_fingerprint
        identities.append("content:" + content_fingerprint)
        matches = {row[0] for key in identities for row in db.execute("SELECT paper_id FROM paper_identities WHERE workspace_id=? AND identity=?", (workspace,key))}
        if len(matches)>1:
            raise ValueError("paper_identity_conflict_requires_review")
        existing = db.execute("SELECT * FROM papers WHERE id=?", (next(iter(matches)),)).fetchone() if matches else db.execute("SELECT * FROM papers WHERE workspace_id=? AND identity=?", (workspace, identity)).fetchone()
        paper_id = existing["id"] if existing else uid()
        metadata = {k: v for k, v in document.items() if k not in {"pages", "id"}}
        if existing and metadata_revision["resolution"] != "registry_verified":
            active = db.execute("SELECT id,metadata FROM document_versions WHERE id=?", (existing["active_version"],)).fetchone()
            if active and (json.loads(active["metadata"]).get("metadata_resolution") or {}).get("status") == "registry_verified":
                active_pages = [dict(p) for p in db.execute("SELECT number AS page,text FROM pages WHERE version_id=? ORDER BY number", (active["id"],))]
                if active_pages == [{"page": p["page"], "text": p["text"]} for p in pages]:
                    return {"paper_id": paper_id, "version_id": active["id"], "deduplicated": True}
        now = time.time()
        if not existing:
            db.execute("INSERT INTO papers(id,workspace_id,identity,title,metadata,created) VALUES(?,?,?,?,?,?)",
                       (paper_id, workspace, identity, document.get("title") or "未命名论文", encode(metadata), now))
        for key in identities:
            db.execute("INSERT OR IGNORE INTO paper_identities VALUES(?,?,?)", (workspace,key,paper_id))
        version = db.execute("SELECT id FROM document_versions WHERE paper_id=? AND fingerprint=?", (paper_id, fingerprint)).fetchone()
        version_id = version["id"] if version else uid()
        if not version:
            db.execute("INSERT INTO document_versions(id,paper_id,fingerprint,metadata,file_path,created) VALUES(?,?,?,?,?,?)",
                       (version_id, paper_id, fingerprint, encode(metadata), file_path, now))
            for page in pages:
                number = int(page["page"])
                db.execute("INSERT INTO pages VALUES(?,?,?)", (version_id, number, page["text"]))
                for ordinal, text in enumerate(_chunk_page(page["text"])):
                    db.execute("INSERT INTO evidence_chunks VALUES(?,?,?,?,?)",
                               (f"{version_id}:p{number}:c{ordinal}", version_id, number, ordinal, text))
            db.execute("UPDATE papers SET active_version=?,title=?,metadata=? WHERE id=?",
                       (version_id, document.get("title") or "未命名论文", encode(metadata), paper_id))
        if source_key:
            db.execute("INSERT INTO migration_records VALUES(?,?,?,?)", (source_key, paper_id, version_id, now))
        return {"paper_id": paper_id, "version_id": version_id, "deduplicated": bool(version)}

    def enqueue(self, workspace, user, kind, payload, key, *, resource_id=None, version_id=None, billable=False, db=None):
        if db is None:
            with self.connect(write=True) as connection:
                return self.enqueue(workspace, user, kind, payload, key, resource_id=resource_id,
                                    version_id=version_id, billable=billable, db=connection)
        existing = db.execute("SELECT * FROM jobs WHERE workspace_id=? AND dedupe_key=?", (workspace, key)).fetchone()
        if existing:
            if existing["payload"] != encode(payload) or existing["kind"] != kind or existing["resource_id"] != resource_id:
                raise ValueError("idempotency_key_conflict")
            return dict(existing)
        now = time.time()
        if billable:
            count = db.execute("SELECT count(*) FROM jobs WHERE workspace_id=? AND billable=1 AND created>=?", (workspace, now - 86400)).fetchone()[0]
            limit = db.execute("SELECT daily_limit FROM workspaces WHERE id=?", (workspace,)).fetchone()[0]
            if count >= limit:
                raise ValueError("daily_model_limit")
        pending = db.execute("SELECT count(*) FROM jobs WHERE workspace_id=? AND state IN ('queued','running')", (workspace,)).fetchone()[0]
        if pending >= 30:
            raise ValueError("workspace_queue_full")
        job_id = uid()
        db.execute("""INSERT INTO jobs(id,workspace_id,user_id,kind,resource_id,version_id,dedupe_key,payload,state,
                   available,billable,created,updated) VALUES(?,?,?,?,?,?,?,?, 'queued',?,?,?,?)""",
                   (job_id, workspace, user, kind, resource_id, version_id, key, encode(payload), now, int(billable), now, now))
        return dict(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def claim(self, owner, *, concurrency=2, per_workspace=1, lease_seconds=45, timeout=900):
        now = time.time()
        with self.connect(write=True) as db:
            expired = db.execute("SELECT * FROM jobs WHERE state='running' AND (lease_until<? OR deadline<?)", (now, now)).fetchall()
            for job in expired:
                uncertain = bool(job["billable"] and job["dispatch_started"])
                state = "needs_attention" if uncertain else "failed" if job["attempts"] >= job["max_attempts"] else "queued"
                db.execute("UPDATE jobs SET state=?,lease_owner=NULL,lease_until=NULL,error_code=?,error=?,updated=? WHERE id=?",
                           (state, "dispatch_outcome_unknown" if uncertain else "lease_expired", "执行中断；计费请求不会自动重放" if uncertain else "执行租约过期", now, job["id"]))
            if db.execute("SELECT count(*) FROM jobs WHERE state='running'").fetchone()[0] >= concurrency:
                return None
            job = db.execute("""SELECT j.* FROM jobs j WHERE state='queued' AND available<=? AND
                (SELECT count(*) FROM jobs r WHERE r.workspace_id=j.workspace_id AND r.state='running')<?
                ORDER BY created LIMIT 1""", (now, per_workspace)).fetchone()
            if not job:
                return None
            db.execute("UPDATE jobs SET state='running',attempts=attempts+1,lease_owner=?,lease_until=?,deadline=?,updated=? WHERE id=?",
                       (owner, now + lease_seconds, now + timeout, now, job["id"]))
            return dict(db.execute("SELECT * FROM jobs WHERE id=?", (job["id"],)).fetchone())

    def heartbeat(self, job_id, owner, seconds=45):
        with self.connect(write=True) as db:
            return db.execute("UPDATE jobs SET lease_until=?,updated=? WHERE id=? AND lease_owner=? AND state='running' AND deadline>?",
                              (time.time() + seconds, time.time(), job_id, owner, time.time())).rowcount == 1

    @staticmethod
    def assert_lease(db, job, owner):
        current = db.execute("SELECT * FROM jobs WHERE id=? AND lease_owner=? AND state='running' AND lease_until>? AND deadline>?",
                             (job["id"], owner, time.time(), time.time())).fetchone()
        if not current:
            raise RuntimeError("lease_lost")

    def fail(self, job, owner, code, message, *, retryable=False):
        with self.connect(write=True) as db:
            row = db.execute("SELECT * FROM jobs WHERE id=? AND lease_owner=? AND state='running'", (job["id"], owner)).fetchone()
            if not row:
                return
            uncertain = row["billable"] and row["dispatch_started"] and code in {"timeout", "transport", "worker_crash"}
            state = "needs_attention" if uncertain else "queued" if retryable and not row["billable"] and row["attempts"] < row["max_attempts"] else "failed"
            db.execute("UPDATE jobs SET state=?,error_code=?,error=?,available=?,lease_owner=NULL,lease_until=NULL,updated=? WHERE id=?",
                       (state, code, message, time.time() + min(60, 2 ** row["attempts"]), time.time(), job["id"]))
