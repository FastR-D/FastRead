from __future__ import annotations

import hashlib
import json
import os
import re
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
 password TEXT NOT NULL, created REAL NOT NULL, research_key_id TEXT, display_name TEXT);
CREATE TABLE IF NOT EXISTS workspaces(id TEXT PRIMARY KEY, name TEXT NOT NULL, daily_limit INTEGER NOT NULL DEFAULT 50);
CREATE TABLE IF NOT EXISTS memberships(user_id TEXT REFERENCES users(id), workspace_id TEXT REFERENCES workspaces(id),
 role TEXT NOT NULL CHECK(role IN ('owner','member')), PRIMARY KEY(user_id,workspace_id));
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id),
 workspace_id TEXT REFERENCES workspaces(id), csrf TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS login_attempts(key TEXT PRIMARY KEY, failures INTEGER NOT NULL, until REAL NOT NULL);
CREATE TABLE IF NOT EXISTS account_credentials(token_hash TEXT PRIMARY KEY,kind TEXT NOT NULL CHECK(kind IN ('invite','recovery')),email TEXT NOT NULL,user_id TEXT REFERENCES users(id),expires REAL NOT NULL,consumed REAL);
CREATE TABLE IF NOT EXISTS account_audit(id TEXT PRIMARY KEY,user_id TEXT,action TEXT NOT NULL,created REAL NOT NULL);
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
        from .fastcas_store import SCHEMA as FASTCAS_SCHEMA
        from .knowledge import SCHEMA as KNOWLEDGE_SCHEMA
        from .reading import SCHEMA as READING_SCHEMA
        from .notebook_notes import SCHEMA as NOTES_SCHEMA
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        (self.root / "files").mkdir(exist_ok=True)
        # Account/session hashes and short-lived PKCE verifiers share this DB.
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        for private_path in (self.path, Path(str(self.path)+"-wal"), Path(str(self.path)+"-shm")):
            if private_path.exists():
                private_path.chmod(0o600)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA + KNOWLEDGE_SCHEMA + READING_SCHEMA + NOTES_SCHEMA + FASTCAS_SCHEMA)
            columns = {row[1] for row in db.execute("PRAGMA table_info(papers)")}
            if "archived" not in columns:
                db.execute("ALTER TABLE papers ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
            session_columns = {row[1] for row in db.execute("PRAGMA table_info(sessions)")}
            for name, definition in {
                "auth_source": "TEXT NOT NULL DEFAULT 'legacy'",
                "authenticated_at": "REAL",
                "cas_issuer": "TEXT", "cas_sid": "TEXT",
                "cas_link_id": "TEXT", "cas_link_version": "INTEGER", "cas_checked": "REAL",
            }.items():
                if name not in session_columns:
                    db.execute(f"ALTER TABLE sessions ADD COLUMN {name} {definition}")
            user_columns = {row[1] for row in db.execute("PRAGMA table_info(users)")}
            if "research_key_id" not in user_columns:
                db.execute("ALTER TABLE users ADD COLUMN research_key_id TEXT")
            if "research_account_id" not in user_columns:
                db.execute("ALTER TABLE users ADD COLUMN research_account_id TEXT")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_research_account_id ON users(research_account_id) WHERE research_account_id IS NOT NULL")
            if "display_name" not in user_columns:
                db.execute("ALTER TABLE users ADD COLUMN display_name TEXT")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_research_key_id ON users(research_key_id) WHERE research_key_id IS NOT NULL AND research_key_id != ''")
            db.execute("INSERT OR IGNORE INTO schema_versions VALUES(1,?)", (time.time(),))
            if not db.execute("SELECT name FROM knowledge_migrations WHERE name='legacy-topics-v1'").fetchone():
                db.execute('INSERT OR IGNORE INTO knowledge_bases SELECT id,workspace_id,question,scope,created FROM topics')
                db.execute("INSERT OR IGNORE INTO knowledge_papers SELECT DISTINCT e.topic_id,e.paper_id,'manual',? FROM topic_evidence e JOIN topics t ON t.id=e.topic_id JOIN papers p ON p.id=e.paper_id AND p.workspace_id=t.workspace_id",(time.time(),))
                db.execute("INSERT INTO knowledge_migrations VALUES('legacy-topics-v1',?)",(time.time(),))

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

    def intake_fastnews(self, workspace: str, paper: dict) -> dict:
        """Create or update a metadata-only FastNews paper. PDF is attached later."""
        title = " ".join(str(paper.get("title") or "").split())[:300]
        if not title:
            raise ValueError("title required")
        authors_raw = " ".join(str(paper.get("authors") or "").split())[:400]
        authors = [part.strip() for part in re.split(r"[;；、]", authors_raw) if part.strip()] if authors_raw else []
        abstract = " ".join(str(paper.get("abstract") or "").split())[:800]
        url = " ".join(str(paper.get("url") or "").split())[:2048]
        venue = " ".join(str(paper.get("venue") or "").split())[:80]
        year = " ".join(str(paper.get("year") or "").split())[:8]
        external_id = " ".join(str(paper.get("external_id") or paper.get("id") or "").split())[:200]
        if external_id:
            identity = "fastnews:" + external_id
        elif url:
            identity = "fastnews-url:" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
        else:
            identity = "fastnews-title:" + hashlib.sha256(title.encode("utf-8")).hexdigest()[:32]
        now = time.time()
        with self.connect(write=True) as db:
            existing = db.execute(
                "SELECT * FROM papers WHERE workspace_id=? AND identity=?",
                (workspace, identity),
            ).fetchone()
            paper_id = existing["id"] if existing else uid()
            old_meta = json.loads(existing["metadata"]) if existing else {}
            awaiting_file = not (existing and existing["active_version"])
            metadata = dict(old_meta) if existing and existing["active_version"] else {}
            metadata.update({
                "source": "fastnews",
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "url": url,
                "venue": venue,
                "year": year,
                "external_id": external_id,
                "page_count": old_meta.get("page_count") or 0 if existing and existing["active_version"] else 0,
                "awaiting_file": awaiting_file,
            })
            if existing:
                db.execute(
                    "UPDATE papers SET archived=0, title=?, metadata=? WHERE id=?",
                    (title, encode(metadata), paper_id),
                )
            else:
                db.execute(
                    "INSERT INTO papers(id,workspace_id,identity,title,metadata,created) VALUES(?,?,?,?,?,?)",
                    (paper_id, workspace, identity, title, encode(metadata), now),
                )
            db.execute("INSERT OR IGNORE INTO paper_identities VALUES(?,?,?)", (workspace, identity, paper_id))
        return {"id": paper_id, "title": title, "awaiting_file": awaiting_file, "created": not existing}

    def ingest(self, workspace: str, document: dict, *, file_path=None, source_key=None, paper_id=None, db=None):
        """Atomically publish immutable document/pages/chunks and the active-version pointer."""
        if db is None:
            with self.connect(write=True) as connection:
                return self.ingest(workspace, document, file_path=file_path, source_key=source_key, paper_id=paper_id, db=connection)
        from app.services.metadata_normalization import canonical_identity_keys
        from app.services.chat_service import _chunk_page
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
        identities = sorted({re.sub(r"v\d+$", "", key) if key.startswith("arxiv:") else key
                             for key in canonical_identity_keys(document) if key.startswith(("doi:","arxiv:","openreview:"))})
        identity = next((x for x in identities if x.startswith("doi:")), None)
        identity = identity or next((x for x in identities if x.startswith("arxiv:")), None) or "content:" + content_fingerprint
        identities.append("content:" + content_fingerprint)
        existing = None
        if paper_id:
            existing = db.execute(
                "SELECT * FROM papers WHERE id=? AND workspace_id=? AND archived=0",
                (paper_id, workspace),
            ).fetchone()
            if not existing:
                raise LookupError("paper_not_found")
        else:
            matches = {row[0] for key in identities for row in db.execute("SELECT paper_id FROM paper_identities WHERE workspace_id=? AND identity=?", (workspace,key))}
            if len(matches)>1:
                raise ValueError("paper_identity_conflict_requires_review")
            existing = db.execute("SELECT * FROM papers WHERE id=?", (next(iter(matches)),)).fetchone() if matches else db.execute("SELECT * FROM papers WHERE workspace_id=? AND identity=?", (workspace, identity)).fetchone()
        paper_id = existing["id"] if existing else uid()
        metadata = {k: v for k, v in document.items() if k not in {"pages", "id"}}
        title = document.get("title") or "未命名论文"
        if existing:
            old_meta = json.loads(existing["metadata"] or "{}")
            if old_meta.get("source") == "fastnews":
                for key in ("title", "authors", "year", "venue", "abstract", "url", "external_id"):
                    if old_meta.get(key) not in (None, "", []):
                        metadata[key] = old_meta[key]
                metadata["source"] = "fastnews"
                metadata["awaiting_file"] = False
                if old_meta.get("title"):
                    title = old_meta["title"]
        if existing and metadata_revision["resolution"] != "registry_verified":
            active = db.execute("SELECT id,metadata FROM document_versions WHERE id=?", (existing["active_version"],)).fetchone()
            if active and (json.loads(active["metadata"]).get("metadata_resolution") or {}).get("status") == "registry_verified":
                active_pages = [dict(p) for p in db.execute("SELECT number AS page,text FROM pages WHERE version_id=? ORDER BY number", (active["id"],))]
                if active_pages == [{"page": p["page"], "text": p["text"]} for p in pages]:
                    return {"paper_id": paper_id, "version_id": active["id"], "deduplicated": True}
        now = time.time()
        if not existing:
            db.execute("INSERT INTO papers(id,workspace_id,identity,title,metadata,created) VALUES(?,?,?,?,?,?)",
                       (paper_id, workspace, identity, title, encode(metadata), now))
        for key in identities:
            owner = db.execute("SELECT paper_id FROM paper_identities WHERE workspace_id=? AND identity=?", (workspace, key)).fetchone()
            if owner and owner["paper_id"] != paper_id:
                continue
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
                       (version_id, title, encode(metadata), paper_id))
        if source_key:
            db.execute("INSERT INTO migration_records VALUES(?,?,?,?)", (source_key, paper_id, version_id, now))
        return {"paper_id": paper_id, "version_id": version_id, "deduplicated": bool(version)}

    def enqueue(self, workspace, user, kind, payload, key, *, resource_id=None, version_id=None, billable=False, db=None):
        if not key or len(key) > 160:
            raise ValueError('需要有效 Idempotency-Key')
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
