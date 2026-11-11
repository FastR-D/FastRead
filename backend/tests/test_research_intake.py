from fastapi import HTTPException
from fastapi.testclient import TestClient
from tests.test_web_platform import setup, document
import json
from pathlib import Path

CONTRACT = json.loads((Path(__file__).resolve().parents[2] / 'contracts/fastnews-intake/v1/cases.json').read_text(encoding='utf-8'))


def test_sso_rotates_session_and_preserves_workspace(setup):
    store, a, _, ca, _ = setup
    other = TestClient(ca.app)
    result = other.post('/api/auth/research', json={'ticket': 'test-a'})
    assert result.status_code == 200
    assert other.get('/api/auth/me').json()['workspace_id'] == a['workspace_id']
    assert ca.get('/api/auth/me').status_code == 401
    assert other.post('/api/knowledge-bases', json={'name': 'Test'}).status_code == 403


def test_sso_rejects_expired_ticket_without_forcing_external_login(setup, monkeypatch):
    _, _, _, ca, _ = setup
    def reject(*args, **kwargs):
        raise HTTPException(401, 'Expired ticket')
    monkeypatch.setattr('app.web.auth.research_json', reject)
    anonymous = TestClient(ca.app)
    assert anonymous.post('/api/auth/research', json={'ticket': 'expired'}).status_code == 401
    assert anonymous.get('/api/auth/me').status_code == 401
    info = anonymous.get('/api/auth/login-info').json()
    response = anonymous.get('/', headers={'Accept': 'text/html'}, follow_redirects=False)
    assert info['local'] is True
    # An unbuilt frontend returns 404; a built frontend serves its login shell.
    assert response.status_code in (200, 404)
    assert 'location' not in response.headers


def test_fastnews_intake_pdf_attachment_and_workspace_isolation(setup):
    store, a, b, ca, cb = setup
    data = CONTRACT['intake']
    first = ca.post('/api/integrations/fastnews/intake', json=data)
    assert first.status_code in (200, 201)
    assert all(first.json()[key] == value for key, value in CONTRACT['first_receipt'].items())
    pid = first.json()['id']
    assert pid and first.json()['title'] == data['title']
    repeated = ca.post('/api/integrations/fastnews/intake', json=data).json()
    assert repeated['id'] == pid
    assert all(repeated[key] == value for key, value in CONTRACT['repeat_receipt'].items())
    updated = ca.post('/api/integrations/fastnews/intake', json={**data, 'title': 'Updated title'})
    assert updated.json()['id'] == pid and updated.json()['created'] is False
    assert ca.get(f'/api/papers/{pid}').json()['title'] == 'Updated title'
    assert ca.post('/api/integrations/fastnews/intake', json=data).json()['title'] == data['title']
    assert cb.post('/api/integrations/fastnews/intake', json=data).json()['id'] != pid
    assert ca.get(f'/api/papers/{pid}/pages/1').status_code == 409
    assert cb.get(f'/api/papers/{pid}').status_code == 404
    uploaded = {'file': ('paper.pdf', b'%PDF-fixture', 'application/pdf')}
    assert cb.post('/api/imports/pdf', data={'paper_id': pid}, files=uploaded,
                   headers={'Idempotency-Key': 'cross-workspace'}).status_code == 404
    response = ca.post('/api/imports/pdf', data={'paper_id': pid}, files=uploaded,
                       headers={'Idempotency-Key': 'attach'})
    assert response.status_code == 202
    result = store.ingest(a['workspace_id'], document(), paper_id=pid)
    assert result['paper_id'] == pid
    paper = ca.get(f'/api/papers/{pid}').json()
    assert paper['active_version'] and paper['title'] == data['title']
    again = ca.post('/api/integrations/fastnews/intake', json=data)
    assert again.status_code == 200 and again.json()['awaiting_file'] is False
    assert ca.get(f'/api/papers/{pid}').json()['active_version'] == paper['active_version']


def test_intake_wire_errors_and_normalization(setup):
    _, _, _, ca, _ = setup
    endpoint = '/api/integrations/fastnews/intake'
    anonymous = TestClient(ca.app)
    assert anonymous.post(endpoint, json=CONTRACT['intake']).status_code == 401
    assert ca.post(endpoint, json=CONTRACT['intake'], headers={'X-CSRF-Token': 'wrong'}).status_code == 403
    for case in CONTRACT['invalid']:
        assert ca.post(endpoint, json=case['body']).status_code == case['status']
    for field, limit in [('title', 300), ('authors', 400), ('abstract', 800), ('venue', 80), ('year', 8), ('external_id', 200)]:
        assert ca.post(endpoint, json={**CONTRACT['intake'], field: 'x' * (limit + 1)}).status_code == 422
    for url in CONTRACT['url_normalization']:
        response = ca.post(endpoint, json={**CONTRACT['intake'], 'url': url})
        assert response.status_code == 200
        paper = ca.get('/api/papers/' + response.json()['id']).json()
        assert paper['metadata']['url'] == ''


def test_intake_without_external_id_uses_url_then_title_deduplication(setup):
    _, _, _, ca, _ = setup
    endpoint = '/api/integrations/fastnews/intake'
    for payload in [{'title': 'URL identity', 'url': 'https://example.org/keyless'}, {'title': 'Title identity'}]:
        first = ca.post(endpoint, json=payload)
        assert first.status_code == 200 and first.json()['created'] is True
        repeated = ca.post(endpoint, json={**payload, 'authors': 'Updated author'})
        assert repeated.status_code == 200
        assert repeated.json()['id'] == first.json()['id'] and repeated.json()['created'] is False
        paper = ca.get('/api/papers/' + first.json()['id']).json()
        assert paper['metadata']['authors'] == ['Updated author']
