from fastapi.testclient import TestClient
from tests.test_web_platform import setup, document


def pdf_fixture(setup):
    store, a, b, ca, cb = setup
    payload = b'%PDF-1.7\n' + bytes(range(256)) * 1024
    (store.root / 'files' / 'reader.pdf').write_bytes(payload)
    result = store.ingest(a['workspace_id'], document(), file_path='files/reader.pdf')
    url = f"/api/papers/{result['paper_id']}/file?version={result['version_id']}"
    return ca, cb, url, payload


def test_pdf_identity_ranges_and_private_revalidation(setup):
    ca, cb, url, payload = pdf_fixture(setup)
    headers = {'Accept-Encoding': 'gzip'}
    full = ca.get(url, headers=headers)
    assert full.status_code == 200
    assert full.content == payload
    assert 'content-encoding' not in full.headers
    assert int(full.headers['content-length']) == len(payload)
    assert full.headers['accept-ranges'] == 'bytes'
    assert full.headers['cache-control'] == 'private, no-cache'
    partial = ca.get(url, headers=headers | {'Range': 'bytes=65536-131071'})
    assert partial.status_code == 206
    assert partial.content == payload[65536:131072]
    assert partial.headers['content-range'] == f'bytes 65536-131071/{len(payload)}'
    assert 'content-encoding' not in partial.headers
    assert ca.get(url, headers={'Range':'bytes=9999999-'}).status_code == 416
    assert ca.head(url).headers['content-length'] == str(len(payload))
    assert ca.head(url).content == b''
    cached = ca.get(url, headers={'If-None-Match':'W/'+full.headers['etag']})
    assert cached.status_code == 304 and cached.content == b''
    assert cached.headers['cache-control'] == 'private, no-cache'
    # Possession of an ETag does not bypass authentication or workspace checks.
    forbidden = cb.get(url, headers={'If-None-Match':full.headers['etag']})
    assert forbidden.status_code == 404
    assert forbidden.headers['cache-control'] == 'no-store'
    assert TestClient(ca.app).get(url).status_code == 401


def test_non_pdf_api_remains_uncacheable(setup):
    ca, _, _, _ = pdf_fixture(setup)
    response = ca.get('/api/papers', headers={'Accept-Encoding':'gzip'})
    assert response.headers['cache-control'] == 'no-store'
