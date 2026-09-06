import json
from app.web.auth import create_user
from app.web.store import Store
from app.web.migrate import migrate
from app.services.metadata_normalization import first_page_candidates


def test_single_author_followed_by_affiliation_is_not_title():
    text="FlashAttention-2: Faster Attention with\nBetter Parallelism and Work Partitioning\nTri Dao1,2\n1Department of Computer Science, Stanford University\nAbstract\nWe improve attention."
    candidates=first_page_candidates(text)
    assert all("Tri Dao" not in title for title in candidates["title_candidates"])
    assert "Tri Dao" in candidates["author_candidates"]


def test_migration_is_copy_only_idempotent_and_preserves_summary(tmp_path):
    source=tmp_path/'legacy'; (source/'paper_results').mkdir(parents=True)
    payload={'paper_task':True,'paper_document':{'title':'Migration evidence','pages':[{'page':1,'text':'Original source page with enough evidence to construct a lexical chunk.'}],'page_count':1},'insights':{'personal_summary':{'content':'My original note'},'reading_report':{'summary':'Original report'}}}
    original=json.dumps(payload)
    (source/'paper_results'/'legacy.json').write_text(original)
    store=Store(tmp_path/'web');store.initialize();user=create_user(store,'m@example.org','migration-test-password')
    first=migrate(source,store,user['workspace_id']);second=migrate(source,store,user['workspace_id'])
    assert len(first['migrated'])==1 and second['already_migrated']==['legacy']
    assert (source/'paper_results'/'legacy.json').read_text()==original
    paper=store.paper(user['workspace_id'],first['migrated'][0]['paper_id'])
    assert paper['summary']=='My original note'
    assert store.one('SELECT count(*) n FROM report_versions')['n']==1


def test_empty_legacy_registry_does_not_resurrect_deleted_papers(tmp_path):
    import sqlite3
    source=tmp_path/'legacy';(source/'paper_results').mkdir(parents=True)
    with sqlite3.connect(source/'fastread.db') as db:
        db.execute('CREATE TABLE paper_tasks(task_id TEXT PRIMARY KEY)')
    (source/'paper_results'/'deleted.json').write_text(json.dumps({'paper_document':{'title':'Deleted paper','pages':[{'page':1,'text':'A retained result for a paper deleted from the legacy registry.'}]}}))
    store=Store(tmp_path/'web');store.initialize();user=create_user(store,'archive@example.org','archive-test-password')
    result=migrate(source,store,user['workspace_id'])
    assert result['orphan_result_ids']==['deleted']
    assert store.one('SELECT count(*) n FROM papers WHERE archived=0')['n']==0
    assert store.one('SELECT count(*) n FROM papers WHERE archived=1')['n']==1
