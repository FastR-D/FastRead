"""Version-bound PDF annotations and evidence-anchored related papers."""
import json
import time
from typing import Annotated

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .auth import Principal, require_user
from .store import encode, uid
User = Annotated[Principal, Depends(require_user)]

SCHEMA = """
CREATE TABLE IF NOT EXISTS reading_annotations(
 id TEXT PRIMARY KEY, paper_id TEXT NOT NULL REFERENCES papers(id),
 version_id TEXT NOT NULL REFERENCES document_versions(id), page INTEGER NOT NULL,
 quote TEXT NOT NULL, note TEXT NOT NULL, rects TEXT NOT NULL,
 created REAL NOT NULL, updated REAL NOT NULL);
CREATE INDEX IF NOT EXISTS reading_annotations_page ON reading_annotations(version_id,page);
"""

class Rect(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

class AnnotationInput(BaseModel):
    version_id: str = Field(max_length=100)
    page: int = Field(ge=1)
    quote: str = Field(default='', max_length=10000)
    note: str = Field(default='', max_length=10000)
    rects: list[Rect] = Field(default_factory=list, max_length=200)

class NoteInput(BaseModel):
    note: str = Field(max_length=10000)

def register(api, store):
    def owned(user, pid):
        row = store.paper(user.workspace_id, pid)
        if not row:
            raise LookupError('paper_not_found')
        return row

    @api.get('/papers/{pid}/annotations')
    def annotations(pid: str, user: User, version: str = Query(max_length=100)):
        owned(user, pid)
        rows = store.all('SELECT * FROM reading_annotations WHERE paper_id=? AND version_id=? ORDER BY page,created', (pid, version))
        return {'items': [r | {'rects': json.loads(r['rects'])} for r in rows]}

    @api.post('/papers/{pid}/annotations', status_code=201)
    def annotate(pid: str, data: AnnotationInput, user: User):
        owned(user, pid)
        if not store.one('SELECT p.number FROM pages p JOIN document_versions v ON v.id=p.version_id WHERE v.paper_id=? AND v.id=? AND p.number=?', (pid, data.version_id, data.page)):
            raise LookupError('page_not_found')
        if not data.quote.strip() and not data.note.strip():
            raise HTTPException(422, '请选择原文或填写批注')
        if any(r.x + r.width > 1.001 or r.y + r.height > 1.001 for r in data.rects):
            raise HTTPException(422, '批注位置超出页面')
        aid, now = uid(), time.time()
        with store.connect(write=True) as db:
            db.execute('INSERT INTO reading_annotations VALUES(?,?,?,?,?,?,?,?,?)', (aid, pid, data.version_id, data.page, data.quote, data.note, encode([r.model_dump() for r in data.rects]), now, now))
        return {'id': aid}

    @api.patch('/papers/{pid}/annotations/{aid}')
    def update(pid: str, aid: str, data: NoteInput, user: User):
        owned(user, pid)
        with store.connect(write=True) as db:
            if not db.execute('UPDATE reading_annotations SET note=?,updated=? WHERE id=? AND paper_id=?', (data.note, time.time(), aid, pid)).rowcount:
                raise LookupError('annotation_not_found')
        return {'ok': True}

    @api.delete('/papers/{pid}/annotations/{aid}')
    def delete(pid: str, aid: str, user: User):
        owned(user, pid)
        with store.connect(write=True) as db:
            if not db.execute('DELETE FROM reading_annotations WHERE id=? AND paper_id=?', (aid, pid)).rowcount:
                raise LookupError('annotation_not_found')
        return {'ok': True}

    @api.get('/papers/{pid}/neighbors')
    def neighbors(pid: str, user: User):
        row = owned(user, pid)
        job = store.one("SELECT result FROM jobs WHERE workspace_id=? AND resource_id=? AND version_id=? AND kind='neighbors' AND state='succeeded' ORDER BY updated DESC LIMIT 1", (user.workspace_id, pid, row['active_version']))
        snapshot = json.loads(job['result']) if job else {'papers': [], 'anchors': [], 'sources': {}}
        from .knowledge import decorate
        local = decorate(store, store.all('SELECT id,title,metadata,active_version FROM papers WHERE workspace_id=? AND archived=0 AND id<>?', (user.workspace_id, pid)))
        tags = {r['tag'] for r in store.all('SELECT tag FROM paper_tags WHERE paper_id=?', (pid,))}
        local_matches = []
        for p in local:
            p['shared_tags'] = sorted(tags & set(p.get('tags', [])))
            if p['shared_tags']:
                meta = json.loads(p.pop('metadata'))
                p.update(year=meta.get('year'), authors=meta.get('authors', []), local_id=p['id'], discovery_sources=['资料库'], relevance_score=len(p['shared_tags']), matched_anchor_ids=[])
                local_matches.append(p)
        return snapshot | {'papers': local_matches + snapshot.get('papers', []), 'has_snapshot': bool(job), 'paper_tags': sorted(tags)}

def discover(store, repository):
    from app.services.related_work_service import RelatedWorkService, _terms, GENERIC_TITLE_TERMS
    from .search import PublicSearch
    source = repository.read_result(repository.paper_id)
    anchors, _ = RelatedWorkService._anchors(source)
    queries = RelatedWorkService._queries(anchors, source['paper_document'])[:3]
    own_title = source['paper_document']['title'].casefold().strip()
    terms = _terms(' '.join(queries)) - GENERIC_TITLE_TERMS
    candidates, sources = {}, {}
    for query in queries:
        result = PublicSearch(store).search(query[:300], 30)
        sources.update(result.get('sources', {}))
        for p in result.get('papers', []):
            if p.get('title', '').casefold().strip() == own_title:
                continue
            key = p.get('doi') or p.get('id') or p.get('title', '').casefold()
            scoring = p if isinstance(p.get('venue'), dict) else p | {'venue': {}}
            score, matched, overlap = RelatedWorkService._score_neighbor(scoring, anchors, terms)
            if matched:
                candidates[key] = p | {'relevance_score': score, 'matched_anchor_ids': matched, 'matched_terms': overlap, 'tags': [], 'shared_tags': []}
    return {'papers': sorted(candidates.values(), key=lambda p: -p['relevance_score']), 'anchors': anchors, 'queries': queries, 'sources': sources, 'document_version_id': repository.version_id}
