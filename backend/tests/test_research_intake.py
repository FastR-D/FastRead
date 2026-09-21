from fastapi import HTTPException
from fastapi.testclient import TestClient
from tests.test_web_platform import setup, document


def test_sso_rotates_session_and_preserves_workspace(setup):
    store, a, _, ca, _ = setup
    other = TestClient(ca.app)
    result = other.post('/api/auth/research', json={'ticket': 'test-a'})
    assert result.status_code == 200
    assert other.get('/api/auth/me').json()['workspace_id'] == a['workspace_id']
    assert ca.get('/api/auth/me').status_code == 401
    assert other.post('/api/knowledge-bases', json={'name': 'Test'}).status_code == 403


def test_sso_rejects_expired_ticket_and_html_redirects(setup, monkeypatch):
    _, _, _, ca, _ = setup
    def reject(*args, **kwargs):
        raise HTTPException(401, 'Expired ticket')
    monkeypatch.setattr('app.web.auth.research_json', reject)
    anonymous = TestClient(ca.app)
    assert anonymous.post('/api/auth/research', json={'ticket': 'expired'}).status_code == 401
    assert anonymous.get('/api/auth/me').status_code == 401
    info = anonymous.get('/api/auth/login-info').json()
    response = anonymous.get('/', headers={'Accept': 'text/html'}, follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers['location'].startswith(info['panel_url'])


def test_fastnews_intake_pdf_attachment_and_workspace_isolation(setup):
    store, a, b, ca, cb = setup
    data = {'title': 'A metadata-only paper', 'authors': 'Alice', 'abstract': 'A recorded abstract',
            'url': 'https://example.org/paper', 'external_id': 'fixture-1', 'year': '2026'}
    first = ca.post('/api/integrations/fastnews/intake', json=data)
    assert first.status_code in (200, 201)
    pid = first.json()['id']
    assert ca.post('/api/integrations/fastnews/intake', json=data).json()['id'] == pid
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
