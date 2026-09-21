import json
from tests.test_web_platform import setup
from tests.test_web_knowledge import seed, fake_model
from app.web.book_questions import execute

def test_blank_generates_with_sources_and_deduplicates(setup, monkeypatch):
    store,a,b,ca,cb=setup; p=seed(setup)
    bid=ca.post('/api/knowledge-bases',json={'name':'检索机制','description':'   '}).json()['id']
    ca.post(f'/api/knowledge-bases/{bid}/papers',json={'paper_ids':[p['paper_id']]})
    assert len(store.all("SELECT id FROM jobs WHERE kind='book_questions'"))==1
    assert cb.post(f'/api/knowledge-bases/{bid}/questions').status_code==404
    def reply(client,prompt,data):
        assert data['sources'] and data['paper_titles']
        return {'description':'如何结合语义索引与文档证据，提高科学问题回答的可靠性？'}
    monkeypatch.setattr('app.web.knowledge.json_completion',reply)
    job=store.claim('test');execute(store,job,'test',fake_model)
    assert '可靠性' in ca.get(f'/api/knowledge-bases/{bid}').json()['description']
    assert ca.get('/api/knowledge-bases').json()['items'][0]['questions_status']=='ready'

def test_empty_library_uses_name_and_preserves_concurrent_user_text(setup,monkeypatch):
    store,a,b,ca,cb=setup;seed(setup)
    bid=ca.post('/api/knowledge-bases',json={'name':'工具链安全'}).json()['id']
    def reply(client,prompt,data):
        assert data['name']=='工具链安全' and data['sources']==[]
        with store.connect(write=True) as db:
            db.execute('UPDATE knowledge_bases SET description=? WHERE id=?',('用户后来补写的内容',bid))
        return {'description':'工具调用过程中有哪些攻击方式，可以怎样验证防护效果？'}
    monkeypatch.setattr('app.web.knowledge.json_completion',reply)
    job=store.claim('test');execute(store,job,'test',fake_model)
    assert ca.get(f'/api/knowledge-bases/{bid}').json()['description']=='用户后来补写的内容'

def test_explicit_description_and_missing_model_do_not_break_creation(setup):
    store,a,b,ca,cb=setup
    response=ca.post('/api/knowledge-bases',json={'name':'手写','description':'研究哪些具体问题？'})
    assert response.status_code==201 and response.json()['description']=='研究哪些具体问题？'
    response=ca.post('/api/knowledge-bases',json={'name':'留空'})
    assert response.status_code==201
    assert not store.all("SELECT id FROM jobs WHERE kind='book_questions'")
    assert ca.post(f"/api/knowledge-bases/{response.json()['id']}/questions").status_code==400
