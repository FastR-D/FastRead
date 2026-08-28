# FastRead requirement baseline

Updated: 2026-08-28

FastRead is a paper-only reading, discovery, and group-research workbench.

## P0: page-aware single-paper journey

```text
Import PDF or paper URL
-> retain paginated source text and academic identity
-> generate a guided key-question report
-> explain the research problem, method, contribution, evaluation, and limitations
-> discover neighboring papers / related work
-> save a separate personal summary of at most 300 Chinese characters
-> continue multi-turn questions with page-aware sources
```

Acceptance rules:

1. A scan-only, encrypted, empty, or unparseable PDF fails closed. A report cannot be generated without source text.
2. Report citations carry `source_url`, `page_start`, `page_end`, and `exact_quote`. Quotes that cannot be matched to the selected page are discarded.
3. At least four key questions cover the research problem, process/method, contribution, and evaluation/limitations.
4. Method steps and contributions retain exact page evidence; model-authored text without a source page cannot become a search anchor.
5. A single paper establishes only what that study reports. It is not automatically field consensus.
6. The personal summary is user-authored, stored separately from the AI report, and hard-limited to 300 characters.

## Academic identity Gate

Security, systems, and AI core conferences use the same formal identity rule:

```text
formal_identity_passed && venue.is_core
```

- `confirmed_core`: official title, authors, year, and venue close; level A1.
- `claimed_core_unverified`: a document claims a core venue but no official record closes it.
- `confirmed_formal_other`: a formal publication outside the core catalog; level A2.
- `preprint`: an identifiable preprint; level B1.
- `incomplete`: partial academic metadata without closure.
- `retracted_or_withdrawn`: a withdrawn or retracted record; the Gate fails.

The venue catalog is the single source for IEEE S&P, USENIX Security, ACM CCS, NDSS, OSDI, SOSP, ASPLOS, EuroSys, USENIX ATC, SIGCOMM, NSDI, USENIX FAST, ICLR, ICML, AAAI, NeurIPS/NIPS, and ACL. Academic identity says where a paper was formally published; it does not prove that its claims are correct.

## P0: neighboring papers / related work

Related-work discovery is a metadata retrieval and ranking path. It derives at most three queries from page-grounded report anchors, searches core-venue metadata plus arXiv and an optional Scholar provider in parallel, deduplicates candidates, and ranks explainable title/keyword/abstract overlap.

Each result retains title, authors, year, venue/source, available official/DOI/arXiv/PDF links, matched anchor IDs, overlapping terms, relevance score, provenance, and retrieval time. It does not fetch every candidate full text and does not use an AI judge. A provider failure is shown explicitly while other providers may still return results.

The preferred index is Elasticsearch BM25. When Elasticsearch is absent, the product reports and uses the local inverted index.

## P1: group research workflow

- Maintain visible topic membership and add/remove-paper controls.
- Build topic synthesis and continuing questions only from member papers' paginated source text.
- Reject invalid model JSON or unmatched citations instead of silently substituting global context.
- Generate presentation and FastWrite handoff artifacts only from source-grounded reading products.
