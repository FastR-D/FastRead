import json
import time
from tests.test_web_platform import setup, document
from tests.test_web_knowledge import seed

def prepare(setup):
    store,a,b,ca,cb=setup;p=seed(setup)
    other=store.ingest(a['workspace_id'],document('A second paper on attention translation.')|{'doi':'10.1234/second','title':'Second paper'})
    bid=ca.post('/api/knowledge-bases',json={'name':'研究工作区','description':'用户研究问题'}).json()['id']
    ca.post(f'/api/knowledge-bases/{bid}/papers',json={'paper_ids':[p['paper_id'],other['paper_id']]})
    return p,other,bid

def test_selected_sources_restrict_job_snapshot_and_reject_invalid(setup):
    store,a,b,ca,cb=setup;p,q,bid=prepare(setup)
    path=f'/api/knowledge-bases/{bid}/messages'
    data={'content':'比较方法','provider_id':'model','model':'test','paper_ids':[p['paper_id']]}
    assert ca.post(path,json=data|{'paper_ids':[]},headers={'Idempotency-Key':'empty'}).status_code==400
    assert ca.post(path,json=data|{'paper_ids':['foreign']},headers={'Idempotency-Key':'foreign'}).status_code==400
    response=ca.post(path,json=data,headers={'Idempotency-Key':'selected'})
    assert response.status_code==202,response.text
    payload=json.loads(store.one('SELECT payload FROM jobs WHERE id=?',(response.json()['id'],))['payload'])
    assert [s['id'] for s in payload['papers']]==[p['paper_id']]
    assert ca.post(path,json=data|{'paper_ids':[q['paper_id']]},headers={'Idempotency-Key':'selected'}).status_code==409
    assert ca.get(path).json()['items'][0]['evidence']['selected_paper_ids']==[p['paper_id']]

def test_saved_answer_is_server_sourced_scoped_and_keeps_citations(setup):
    store,a,b,ca,cb=setup;p,q,bid=prepare(setup)
    evidence={'sources':[{'paper_id':p['paper_id'],'version_id':p['version_id'],'page':1,'quote':'A verified quote','id':'S1'}]}
    with store.connect(write=True) as db:
        db.execute('INSERT INTO knowledge_messages VALUES(?,?,?,?,?,?,?)',('answer',bid,'assistant','Original answer',json.dumps(evidence),None,time.time()))
    data={'scope':'book','scope_id':bid,'source_message_id':'answer','content':'forged content'}
    result=ca.post('/api/workspace-notes',json=data)
    assert result.status_code==201,result.text
    nid=result.json()['id']
    assert ca.post('/api/workspace-notes',json=data).json()['id']==nid
    assert cb.post('/api/workspace-notes',json=data).status_code==404
    rows=ca.get('/api/workspace-notes',params={'scope':'book','scope_id':bid}).json()['items']
    assert len(rows)==1 and rows[0]['content']=='Original answer' and rows[0]['evidence']==evidence
    assert cb.put('/api/workspace-notes/'+nid,json={'title':'Bad','content':'Bad'}).status_code==404
    assert ca.put('/api/workspace-notes/'+nid,json={'title':'My understanding','content':'Revised note'}).status_code==200
    assert ca.get('/api/workspace-notes',params={'scope':'book','scope_id':bid}).json()['items'][0]['evidence']==evidence
    assert cb.delete('/api/workspace-notes/'+nid).status_code==404
    assert ca.delete('/api/workspace-notes/'+nid).status_code==200
    assert ca.get('/api/workspace-notes',params={'scope':'book','scope_id':bid}).json()['items']==[]

def test_narrowed_sources_exclude_history_from_other_sources(setup,monkeypatch):
    from app.web.knowledge import execute_knowledge
    from tests.test_web_knowledge import fake_model
    store,a,b,ca,cb=setup;p,q,bid=prepare(setup)
    with store.connect(write=True) as db:
        db.execute('INSERT INTO knowledge_messages VALUES(?,?,?,?,?,?,?)',('old-other',bid,'assistant','Information only from excluded paper',json.dumps({'selected_paper_ids':[q['paper_id']]}),None,time.time()))
    response=ca.post(f'/api/knowledge-bases/{bid}/messages',json={'content':'解释方法','provider_id':'model','model':'test','paper_ids':[p['paper_id']]},headers={'Idempotency-Key':'narrowed'})
    assert response.status_code==202
    def reply(client,instruction,data):
        assert not data['history']
        assert {s['paper_id'] for s in data['sources']}=={p['paper_id']}
        return {'answer':'方法依据当前选中的论文。[S1]','source_ids':[data['sources'][0]['id']]}
    monkeypatch.setattr('app.web.knowledge.json_completion',reply)
    job=store.claim('narrowed');execute_knowledge(store,job,'narrowed',fake_model)
    saved=ca.get(f'/api/knowledge-bases/{bid}/messages').json()['items'][-1]
    assert saved['evidence']['selected_paper_ids']==[p['paper_id']]
