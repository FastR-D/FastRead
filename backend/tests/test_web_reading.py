import json
import pytest
from tests.test_web_platform import setup, document
from app.web.reading import discover
from app.web.evidence import EvidenceRepository


def test_annotation_persistence_page_version_and_workspace(setup):
    store, a, b, ca, cb = setup
    p = store.ingest(a['workspace_id'], document('Attention improves language translation.'))
    pid, vid = p['paper_id'], p['version_id']
    path = f'/api/papers/{pid}/annotations'
    data = {'version_id': vid, 'page': 1, 'quote': 'Attention', 'note': '注意力机制', 'rects': [{'x': .1, 'y': .2, 'width': .3, 'height': .02}]}
    response = ca.post(path, json=data)
    assert response.status_code == 201, response.text
    aid = response.json()['id']
    assert ca.get(path, params={'version': vid}).json()['items'][0]['rects'] == data['rects']
    assert cb.get(path, params={'version': vid}).status_code == 404
    assert cb.patch(path+'/'+aid, json={'note':'bad'}).status_code == 404
    assert cb.delete(path+'/'+aid).status_code == 404
    assert ca.post(path, json=data | {'page': 999}).status_code == 404
    assert ca.post(path, json=data | {'version_id': 'wrong'}).status_code == 404
    assert ca.post(path, json=data | {'rects': [{'x': .9, 'y': 0, 'width': .5, 'height': .1}]}).status_code == 422
    assert ca.patch(path+'/'+aid, json={'note':'修订理解'}).status_code == 200
    assert ca.get(path, params={'version': vid}).json()['items'][0]['note'] == '修订理解'
    # A new document version must not inherit coordinates from the old PDF.
    new = store.ingest(a['workspace_id'], document('A revised attention mechanism for language translation.'))
    assert new['version_id'] != vid
    assert ca.get(path, params={'version': new['version_id']}).json()['items'] == []
    assert ca.delete(path+'/'+aid).status_code == 200
    assert ca.get(path, params={'version': vid}).json()['items'] == []


def test_neighbors_include_only_same_workspace_active_tag_matches(setup):
    store, a, b, ca, cb = setup
    p = store.ingest(a['workspace_id'], document('Attention language translation'))
    other = document('Security attention language')
    other['doi'] = '10.1234/other'
    other['title'] = 'Other paper'
    q = store.ingest(a['workspace_id'], other)
    for pid in [p['paper_id'], q['paper_id']]:
        assert ca.put(f'/api/papers/{pid}/tags', json={'tags':['attention']}).status_code == 200
    result = ca.get(f"/api/papers/{p['paper_id']}/neighbors")
    assert result.status_code == 200, result.text
    assert [r['local_id'] for r in result.json()['papers']] == [q['paper_id']]
    assert result.json()['papers'][0]['shared_tags'] == ['attention']
    assert cb.get(f"/api/papers/{p['paper_id']}/neighbors").status_code == 404
    ca.delete(f"/api/papers/{q['paper_id']}")
    assert ca.get(f"/api/papers/{p['paper_id']}/neighbors").json()['papers'] == []


def test_discovery_reuses_grounded_anchors_and_drops_self_unrelated(setup, monkeypatch):
    store, a, b, ca, cb = setup
    p = store.ingest(a['workspace_id'], document('Abstract Attention translation mechanism language models.'))
    repo = EvidenceRepository(store, a['workspace_id'], p['paper_id'], p['version_id'])
    from app.web.search import PublicSearch
    monkeypatch.setattr(PublicSearch, 'search', lambda *args: {'papers':[
        {'id':'related','title':'Attention translation mechanism','abstract':'language models', 'year':2025},
        {'id':'irrelevant','title':'Marine geology coral reef'},
        {'id':'self','title':repo.read_result(p['paper_id'])['paper_document']['title']}
    ], 'sources':{}})
    result = discover(store, repo)
    assert result['anchors'] and result['queries']
    assert [r['id'] for r in result['papers']] == ['related']
    assert result['papers'][0]['matched_anchor_ids']
