"""Production regression cases: repost identity and page-boundary reasoning."""
import itertools
import json
from types import SimpleNamespace

from app.services.paper_search_service import OpenAlexAdapter, PaperSearchService
from app.services import chat_service


def test_reposts_never_overwrite_original_in_any_provider_order():
    original = dict(id='arxiv-1706.03762', title='Attention Is All You Need', year=2017,
                    source='arxiv', source_url='https://arxiv.org/abs/1706.03762',
                    pdf_url='https://arxiv.org/pdf/1706.03762', doi='')
    repost = dict(id='crossref-repost', title=original['title'], year=2025,
                  source='crossref', doi='10.65215/2q58a426', source_url='https://doi.org/10.65215/2q58a426')
    other = dict(repost, id='other', doi='10.65215/r5bs2d54')
    for records in itertools.permutations([original, repost, other]):
        result = PaperSearchService._dedupe(list(records))
        assert len(result) == 3
        retained = next(r for r in result if r['source'] == 'arxiv')
        assert retained['year'] == 2017 and retained['doi'] == ''
        assert retained['pdf_url'] == original['pdf_url']
        assert all(not r.get('pdf_url') for r in result if r['source'] != 'arxiv')


def test_same_doi_merges_but_shared_metadata_url_cannot_bridge_conflicting_dois():
    a = dict(title='Example', doi='10.1234/a', source='crossref', metadata_url='https://openalex.org/W1')
    b = dict(a, source='openalex', pdf_url='https://example.org/original.pdf')
    c = dict(a, doi='10.1234/b', year=2025)
    for records in itertools.permutations([a, b, c]):
        result = PaperSearchService._dedupe(list(records))
        assert len(result) == 2
        assert not next(r for r in result if r['doi'] == c['doi']).get('pdf_url')


def test_openalex_repost_download_is_not_attached_to_different_primary_doi():
    row = OpenAlexAdapter._normalize({
        'id': 'https://openalex.org/W2626778328', 'display_name': 'Attention Is All You Need',
        'doi': 'https://doi.org/10.65215/2q58a426', 'publication_year': 2025,
        'primary_location': {'landing_page_url': 'https://doi.org/10.65215/2q58a426'},
        'best_oa_location': {'landing_page_url': 'https://doi.org/10.65215/r5bs2d54',
                             'pdf_url': 'https://langtaosha.org.cn/index.php/lts/preprint/download/10/108'},
    })
    assert row['pdf_url'] == ''
    assert row['identity_warning']


def boundary_payload():
    return {'paper_task': True, 'paper_document': {'title': 'Boundary example', 'pages': [
        {'page': 4, 'text': 'Dot-product attention uses scaling.\nAttention(Q,K,V) = softmax(\nQKT\n√dk\n)V\n' +
         'Other context. ' * 80 + 'We suspect that for large values of dk, the dot products'},
        {'page': 5, 'text': 'grow large in magnitude, pushing the softmax function into regions where it has extremely small gradients. ' +
         'To counteract this effect, we scale the dot products by 1/√dk. ' * 10},
    ]}, 'insights': {}}


def test_retrieval_completes_cross_page_mechanism_and_preserves_formula_lines():
    payload = boundary_payload()
    _, chunks, diagnostics = chat_service._task_retrieval('paper', 'Dot-product attention scaling',
                                                         payload=payload, use_vectors=False, limit=1)
    context = chat_service._context(chunks)
    assert 'extremely small gradients' in context
    assert 'QKT\n√dk' in context
    assert diagnostics['retrieved_pages'] == [4, 5]
    assert context.index('第 4 页') < context.index('第 5 页')


def test_mixed_valid_and_invalid_citations_rejects_whole_answer():
    payload = boundary_payload()
    chunks = chat_service._paper_chunks('paper', payload)
    response = {'answer': 'A correct citation does not validate an invented mechanism.', 'citations': [
        {'page': 5, 'exact_quote': 'extremely small gradients'},
        {'page': 4, 'exact_quote': 'an invented source statement'},
    ]}
    result = chat_service._ground_task_answer(json.dumps(response), payload, chunks)
    assert result['grounding_status'] == 'citation_rejected'


def test_context_budget_and_requested_page_boundary():
    payload = boundary_payload()
    _, chunks, diag = chat_service._task_retrieval('paper', '第4页', payload=payload, use_vectors=False)
    assert diag['retrieved_pages'] == [4]
    all_chunks = chat_service._paper_chunks('paper', payload)
    expanded = chat_service._expand_context(all_chunks[:1], all_chunks, budget=1800)
    assert sum(len(c['text']) for c in expanded) <= 1800


def test_public_search_keeps_original_when_aggregators_return_repost(tmp_path):
    from app.web.search import PublicSearch
    from app.web.store import Store
    store = Store(tmp_path)
    store.initialize()
    search = PublicSearch(store)
    original = dict(id='original', title='Attention Is All You Need', source='arxiv', year=2017,
                    source_url='https://arxiv.org/abs/1706.03762', pdf_url='https://arxiv.org/pdf/1706.03762')
    repost = dict(id='repost', title=original['title'], source='openalex', year=2025,
                  doi='10.65215/2q58a426', source_url='https://doi.org/10.65215/2q58a426')
    search.adapters = {
        'arxiv': SimpleNamespace(search=lambda *_: ([original], {'available': True})),
        'openalex': SimpleNamespace(search=lambda *_: ([repost], {'available': True})),
        'crossref': SimpleNamespace(search=lambda *_: ([], {'available': False, 'reason': 'rate_limited'})),
    }
    result = search.search(original['title'])
    assert [p['year'] for p in result['papers']] == [2017, 2025]
    assert all(p['identity_warning'] for p in result['papers'])
    assert result['sources']['crossref']['available'] is False
    assert search.search(original['title'])['papers'] == result['papers']
