from app.services import paper_fetching


class FakeResponse:
    def __init__(self, *, url, content, content_type):
        self.url = url
        self.content = content
        self.headers = {"content-type": content_type}
        self.encoding = "utf-8"
        self.history = []
        self.status_code = 200

    def raise_for_status(self):
        return None


class FakeArxivClient:
    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, url):
        if "/abs/" in url:
            html = b"""
                <html><head>
                <meta name="citation_title" content="A Paper" />
                <meta name="citation_author" content="Alice" />
                <meta name="citation_pdf_url" content="https://arxiv.org/pdf/2601.00001.pdf" />
                </head><body>Abstract page</body></html>
            """
            return FakeResponse(url=url, content=html, content_type="text/html")
        return FakeResponse(url=url, content=b"fake-pdf", content_type="application/pdf")


def test_arxiv_abstract_fetch_follows_citation_pdf(monkeypatch):
    monkeypatch.setattr(paper_fetching, "_validate_public_url", lambda url: url)
    monkeypatch.setattr(
        paper_fetching,
        "_pdf_snapshot",
        lambda url, content: {
            "url": url,
            "canonical_url": url,
            "title": "",
            "authors": [],
            "author": "",
            "published_at": "",
            "doi": "",
            "venue": "",
            "pdf_url": url,
            "text": "Parsed PDF body",
            "fetch_status": "pdf_ok",
            "source_type": "pdf",
            "content_hash": "pdf-hash",
        },
    )

    snapshot = paper_fetching.fetch_source_snapshot(
        "https://arxiv.org/abs/2601.00001",
        client_factory=FakeArxivClient,
    )

    assert snapshot["fetch_status"] == "pdf_ok"
    assert snapshot["source_type"] == "pdf"
    assert snapshot["source_page_url"] == "https://arxiv.org/abs/2601.00001"
    assert snapshot["url"] == "https://arxiv.org/pdf/2601.00001.pdf"


def test_paper_fetching_has_no_verdict_or_evidence_contract():
    snapshot = paper_fetching._html_snapshot(
        "https://example.org/paper",
        "<html><head><title>Paper</title></head><body>metadata only</body></html>",
    )

    assert "verdict" not in snapshot
    assert "stance" not in snapshot
