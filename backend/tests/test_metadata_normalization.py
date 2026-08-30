from app.services.metadata_normalization import (
    canonical_identity_keys,
    first_page_candidates,
    normalize_paper_metadata,
)


def test_multiline_authors_affiliations_addresses_and_email_do_not_pollute_identity():
    first_page = """Published as a conference paper at ExampleConf 2025
How Reliable Are Small Measurements?
Alice Example
Bob Researcher
Department of Computer Science, Example University
123 Research Road, Example City, USA
alice@example.edu
Abstract
We study measurement reliability.
"""
    contract = normalize_paper_metadata(
        {"document_claimed_metadata": {"year": 2025, "venue": "ExampleConf 2025"}},
        first_page_text=first_page,
    )

    normalized = contract["normalized_metadata"]
    assert normalized["title"] == "How Reliable Are Small Measurements?"
    assert normalized["authors"] == ["Alice Example", "Bob Researcher"]
    assert all("University" not in author and "Road" not in author and "@" not in author for author in normalized["authors"])


def test_wrapped_title_stops_at_comma_separated_author_block():
    candidates = first_page_candidates(
        "A General Framework for Robust\nEvaluation Across Domains\nAlice Example, Bob Researcher\nInstitute of Computing\nAbstract\nBody"
    )

    assert candidates["title_candidates"][-1] == "A General Framework for Robust Evaluation Across Domains"
    assert candidates["author_candidates"] == ["Alice Example", "Bob Researcher"]


def test_identity_keys_close_doi_arxiv_official_url_and_title_aliases():
    source = canonical_identity_keys(
        {
            "title": "A Paper: With Punctuation",
            "doi": "https://doi.org/10.1000/XYZ.1",
            "source_url": "https://arxiv.org/abs/2601.01234",
            "official_record_url": "https://openreview.net/forum?id=record-1",
        }
    )
    alias = canonical_identity_keys(
        {
            "title": "A Paper With Punctuation",
            "doi": "10.1000/xyz.1",
            "pdf_url": "https://arxiv.org/pdf/2601.01234.pdf",
        }
    )

    assert "doi:10.1000/xyz.1" in source & alias
    assert "title:apaperwithpunctuation" in source & alias
