
CREATE TABLE IF NOT EXISTS schema_versions(version INTEGER PRIMARY KEY, applied REAL NOT NULL);
CREATE TABLE IF NOT EXISTS fastcas_signups(binding_hash TEXT PRIMARY KEY,issuer TEXT NOT NULL,subject TEXT NOT NULL,email TEXT NOT NULL,display_name TEXT NOT NULL,expires REAL NOT NULL,prepared TEXT);
CREATE TABLE IF NOT EXISTS admin_account_audit(id TEXT PRIMARY KEY,actor TEXT,target TEXT,action TEXT NOT NULL,reason TEXT NOT NULL,created REAL NOT NULL);
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


CREATE TABLE IF NOT EXISTS knowledge_migrations(name TEXT PRIMARY KEY, applied REAL NOT NULL);
CREATE TABLE IF NOT EXISTS knowledge_bases(id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id), name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', created REAL NOT NULL, UNIQUE(workspace_id,name));
CREATE TABLE IF NOT EXISTS knowledge_papers(knowledge_id TEXT NOT NULL REFERENCES knowledge_bases(id), paper_id TEXT NOT NULL REFERENCES papers(id), origin TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(knowledge_id,paper_id));
CREATE TABLE IF NOT EXISTS paper_insights(paper_id TEXT PRIMARY KEY REFERENCES papers(id), version_id TEXT NOT NULL, principle TEXT NOT NULL, evidence TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS paper_tags(paper_id TEXT NOT NULL REFERENCES papers(id), tag TEXT NOT NULL, origin TEXT NOT NULL DEFAULT 'manual', PRIMARY KEY(paper_id,tag));
CREATE INDEX IF NOT EXISTS paper_tags_tag ON paper_tags(tag);
CREATE TABLE IF NOT EXISTS knowledge_messages(id TEXT PRIMARY KEY, knowledge_id TEXT NOT NULL REFERENCES knowledge_bases(id), role TEXT NOT NULL, content TEXT NOT NULL, evidence TEXT NOT NULL DEFAULT '{}', job_id TEXT, created REAL NOT NULL, UNIQUE(job_id,role));


CREATE TABLE IF NOT EXISTS reading_annotations(
 id TEXT PRIMARY KEY, paper_id TEXT NOT NULL REFERENCES papers(id),
 version_id TEXT NOT NULL REFERENCES document_versions(id), page INTEGER NOT NULL,
 quote TEXT NOT NULL, note TEXT NOT NULL, rects TEXT NOT NULL,
 created REAL NOT NULL, updated REAL NOT NULL);
CREATE INDEX IF NOT EXISTS reading_annotations_page ON reading_annotations(version_id,page);


CREATE TABLE IF NOT EXISTS notebook_notes(
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
 scope TEXT NOT NULL, scope_id TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL,
 evidence TEXT NOT NULL, source_message_id TEXT, created REAL NOT NULL, updated REAL NOT NULL,
 UNIQUE(workspace_id,scope,scope_id,source_message_id));


CREATE TABLE IF NOT EXISTS fastcas_transactions(state TEXT PRIMARY KEY,payload TEXT NOT NULL,expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS fastcas_links(
 issuer TEXT NOT NULL,id TEXT NOT NULL,client_id TEXT NOT NULL,
 user_id TEXT NOT NULL REFERENCES users(id),subject TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('prepared','active','revoked')),
 version INTEGER NOT NULL CHECK(version>0),payload TEXT NOT NULL,
 PRIMARY KEY(issuer,id));
CREATE UNIQUE INDEX IF NOT EXISTS fastcas_local_live ON fastcas_links(issuer,client_id,user_id) WHERE state!='revoked';
CREATE UNIQUE INDEX IF NOT EXISTS fastcas_subject_live ON fastcas_links(issuer,client_id,subject) WHERE state!='revoked';
CREATE TABLE IF NOT EXISTS fastcas_events(issuer TEXT NOT NULL,id TEXT NOT NULL,created REAL NOT NULL,PRIMARY KEY(issuer,id));

CREATE TABLE IF NOT EXISTS shared_providers(id TEXT PRIMARY KEY,name TEXT NOT NULL,base_url TEXT NOT NULL,secret TEXT NOT NULL,models TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS shared_provider_workspaces(provider_id TEXT NOT NULL REFERENCES shared_providers(id) ON DELETE CASCADE,workspace_id TEXT NOT NULL REFERENCES workspaces(id),PRIMARY KEY(provider_id,workspace_id));
