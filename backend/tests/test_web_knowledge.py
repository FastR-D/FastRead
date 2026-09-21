import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from tests.test_web_platform import setup, document
from app.web.knowledge import execute_knowledge


def test_pdf_wrapping_matches_without_accepting_changed_words():
    from app.web.knowledge import validated_sources
    chunk={'id':'S1','paper_id':'p','title':'Paper','version_id':'v','page':1,'text':'The mechanism uses\nsemantic indexing and evidence.'}
    result=validated_sources([{'source_id':'S1','quote':'The mechanism uses semantic indexing and evidence.'}],[chunk])
    assert result[0]['quote']==chunk['text']
    assert not validated_sources([{'source_id':'S1','quote':'The mechanism uses neural indexing and evidence.'}],[chunk])


def seed(setup):
    store,a,b,ca,cb=setup
    paper=store.ingest(a['workspace_id'],document('The proposed retrieval mechanism combines semantic indexing with document evidence to answer scientific questions.'))
    with store.connect(write=True) as db:
        db.execute('INSERT INTO providers VALUES(?,?,?,?,?,?,?)',('model',a['workspace_id'],'Test','https://example.org','unused',json.dumps(['test']),time.time()))
    return paper


def test_legacy_public_setting_does_not_bypass_sso(setup,monkeypatch):
    store,a,b,ca,cb=setup
    seed(setup)
    monkeypatch.setenv('FASTREAD_PUBLIC_WORKSPACE',a['workspace_id'])
    client=TestClient(ca.app)
    me=client.get('/api/auth/me')
    assert me.status_code==401
    assert client.get('/api/papers').status_code==401
    assert client.post('/api/knowledge-bases',json={'name':'Retrieval'}).status_code==401
    assert ca.post('/api/knowledge-bases',json={'name':'Retrieval'},headers={'X-CSRF-Token':'wrong'}).status_code==403
    assert ca.post('/api/knowledge-bases',json={'name':'Retrieval'}).status_code==201
    assert cb.get('/api/knowledge-bases').json()['items']==[]


def test_manual_membership_tags_and_cross_workspace_boundary(setup):
    store,a,b,ca,cb=setup; paper=seed(setup); pid=paper['paper_id']
    book=ca.post('/api/knowledge-bases',json={'name':'检索知识库'}).json()['id']
    assert ca.post(f'/api/knowledge-bases/{book}/papers',json={'paper_ids':[pid]}).status_code==200
    assert cb.post(f'/api/knowledge-bases/{book}/papers',json={'paper_ids':[pid]}).status_code==404
    assert cb.get(f'/api/knowledge-bases/{book}').status_code==404
    assert ca.put(f'/api/papers/{pid}/tags',json={'tags':['RAG','检索','rag']}).json()['tags']==['rag','检索']
    assert ca.get('/api/papers?tag=RAG').json()['total']==1
    assert cb.get('/api/papers?tag=rag').json()['total']==0
    assert ca.get('/api/papers?tag=不存在').json()['total']==0
    assert ca.delete(f'/api/knowledge-bases/{book}/papers/{pid}').status_code==200
    assert ca.get(f'/api/papers/{pid}').status_code==200


def fake_model(*args):
    return SimpleNamespace(client=SimpleNamespace(close=lambda:None))


def organize(setup,monkeypatch,invalid=False):
    store,a,b,ca,cb=setup; paper=seed(setup); pid=paper['paper_id']
    ca.put(f'/api/papers/{pid}/tags',json={'tags':['手工标签']})
    r=ca.post(f'/api/papers/{pid}/organize',json={},headers={'Idempotency-Key':'organize'})
    assert r.status_code==202
    def reply(client,prompt,data):
        source=data['sources'][0]
        return {'principle':'本文通过语义索引和文档证据结合的检索机制，回答科学研究中的相关问题。','tags':['语义索引','文档检索'], 'knowledge_id':'','new_knowledge_name':'检索增强方法','evidence':[{'source_id':source['id'],'quote':'fabricated quote is not evidence' if invalid else source['text']}]}
    monkeypatch.setattr('app.web.knowledge.json_completion',reply)
    job=store.claim('test')
    return store,pid,job


def test_ai_organizes_with_verified_principle_and_preserves_manual_tags(setup,monkeypatch):
    store,pid,job=organize(setup,monkeypatch)
    execute_knowledge(store,job,'test',fake_model)
    assert store.one('SELECT state FROM jobs WHERE id=?',(job['id'],))['state']=='succeeded'
    assert len(store.all('SELECT * FROM paper_tags WHERE paper_id=?',(pid,)))==3
    assert store.one('SELECT principle FROM paper_insights WHERE paper_id=?',(pid,))
    assert store.one('SELECT origin FROM knowledge_papers WHERE paper_id=?',(pid,))['origin']=='ai'


def test_fabricated_evidence_cannot_publish_insight_or_membership(setup,monkeypatch):
    store,pid,job=organize(setup,monkeypatch,invalid=True)
    with pytest.raises(ValueError): execute_knowledge(store,job,'test',fake_model)
    assert not store.one('SELECT * FROM paper_insights WHERE paper_id=?',(pid,))
    assert not store.one('SELECT * FROM knowledge_papers WHERE paper_id=?',(pid,))


def test_knowledge_chat_uses_snapshot_and_deduplicates_questions(setup,monkeypatch):
    store,a,b,ca,cb=setup; paper=seed(setup); pid=paper['paper_id']
    book=ca.post('/api/knowledge-bases',json={'name':'检索','description':'用户填写的检索研究问题'}).json()['id']
    ca.post(f'/api/knowledge-bases/{book}/papers',json={'paper_ids':[pid]})
    headers={'Idempotency-Key':'question'}; payload={'content':'原理是什么？'}
    url=f'/api/knowledge-bases/{book}/messages'
    first=ca.post(url,json=payload,headers=headers)
    assert first.status_code==202
    assert ca.post(url,json=payload,headers=headers).json()['id']==first.json()['id']
    assert ca.post(url,json={'content':'另一个问题'},headers=headers).status_code==409
    assert cb.get(url).status_code==404
    def reply(client,prompt,data):
        source=data['sources'][0]
        return {'answer':'采用语义索引和文档证据 ['+source['id'][1:]+']','source_ids':[source['id']]}
    monkeypatch.setattr('app.web.knowledge.json_completion',reply)
    job=store.claim('chat-test'); execute_knowledge(store,job,'chat-test',fake_model)
    messages=ca.get(url).json()['items']
    assert len(messages)==2 and messages[-1]['role']=='assistant'
    assert messages[-1]['evidence']['sources'][0]['version_id']==paper['version_id']


def test_fastnews_handoff_requires_explicit_post_and_is_idempotent(setup):
    store,a,b,ca,cb=setup
    data={'url':'https://arxiv.org/pdf/1706.03762','external_id':'news-123'}
    headers={'Idempotency-Key':'fastnews-123'}
    first=ca.post('/api/integrations/fastnews',json=data,headers=headers)
    assert first.status_code==202
    assert ca.post('/api/integrations/fastnews',json=data,headers=headers).json()['job']['id']==first.json()['job']['id']
    row=store.one('SELECT payload FROM jobs WHERE id=?',(first.json()['job']['id'],))
    assert json.loads(row['payload'])['source']=='fastnews'


@pytest.mark.parametrize('manual',[False,True])
def test_import_schedules_organization_without_losing_paper(setup,monkeypatch,manual):
    from app.web.worker import execute
    store,a,b,ca,cb=setup;seed(setup)
    bid=ca.post('/api/knowledge-bases',json={'name':'手选归属','description':'用户填写的研究问题'}).json()['id'] if manual else ''
    doc=document('A newly imported paper combines evidence retrieval with a language model to support research.')
    doc['doi']='10.1234/new-import'
    monkeypatch.setattr('app.services.paper_ingest_service.PaperIngestService.ingest_url',lambda self,**kwargs:{'result':{'paper_document':doc}})
    response=ca.post('/api/imports/url',json={'url':'https://example.org/paper.pdf','knowledge_id':bid},headers={'Idempotency-Key':'import-auto'})
    assert response.status_code==202
    job=store.claim('import');execute(store,job,'import')
    result=json.loads(store.one('SELECT result FROM jobs WHERE id=?',(job['id'],))['result'])
    assert store.paper(a['workspace_id'],result['paper_id'])
    child=store.one('SELECT * FROM jobs WHERE id=?',(result['organize_job_id'],))
    assert child['kind']=='organize' and child['state']=='queued'
    assert json.loads(child['payload'])['knowledge_id']==bid
    if manual:
        assert store.one('SELECT origin FROM knowledge_papers WHERE knowledge_id=? AND paper_id=?',(bid,result['paper_id']))['origin']=='manual'
