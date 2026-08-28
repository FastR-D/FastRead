import json

from app.services.academic_identity_resolver import resolve_document_claim_record


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _Client:
    def __init__(self, payload, **_kwargs):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, _url, params):
        filters = json.loads(params["filters"])
        assert filters == [{"colIndex": 1, "terms": ["eigenbench"]}]
        return _Response(self.payload)


def test_iclr_registry_exact_match_returns_openreview_record():
    html = """
    <tr>
      <td>1</td>
      <td><a href="https://openreview.net/forum?id=fm79KXJIUQ">EigenBench: A Comparative Behavioral Measure of Value Alignment</a></td>
      <td class="pc-session-cell">alignment</td>
      <td class="pc-status-cell" title="Oral">Oral</td>
    </tr>
    """
    factory = lambda **kwargs: _Client({"html": html}, **kwargs)

    resolved = resolve_document_claim_record(
        {
            "title": "EIGENBENCH: A COMPARATIVE BEHAVIORAL MEASURE OF VALUE ALIGNMENT",
            "authors": ["Jonathn Chang", "Lionel Levine"],
            "year": 2026,
            "venue_metadata": {"id": "iclr", "track": "ai"},
        },
        client_factory=factory,
    )

    assert resolved["registry_record_verified"] is True
    assert resolved["registry_record_url"] == "https://openreview.net/forum?id=fm79KXJIUQ"
    assert resolved["verified_academic_metadata"]["publication_status"] == "Oral"


def test_iclr_registry_rejects_nonaccepted_status():
    html = """
    <tr>
      <td>1</td>
      <td><a href="https://openreview.net/forum?id=fixture">EigenBench: A Comparative Behavioral Measure of Value Alignment</a></td>
      <td class="pc-session-cell">alignment</td>
      <td class="pc-status-cell" title="Withdrawn">Withdrawn</td>
    </tr>
    """
    factory = lambda **kwargs: _Client({"html": html}, **kwargs)

    resolved = resolve_document_claim_record(
        {
            "title": "EigenBench: A Comparative Behavioral Measure of Value Alignment",
            "authors": ["Jonathn Chang"],
            "year": 2026,
            "venue_metadata": {"id": "iclr", "track": "ai"},
        },
        client_factory=factory,
    )

    assert resolved == {}
