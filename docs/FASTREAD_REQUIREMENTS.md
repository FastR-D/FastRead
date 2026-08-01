# FastRead requirement baseline

Updated: 2026-08-01

This file records the current product priority. It supersedes the older video-note-first and verification-first prioritization when they conflict, while preserving the existing verification evidence rules as a report evidence layer.

## P0: NotebookLM-style single-paper reading journey

```text
Import PDF or paper URL
-> retain paginated source text and paper identity
-> generate a guided key-question report
-> explain the research problem, method, contribution, evaluation, and limitations
-> show source URL, exact quote, and page for every accepted citation
-> save a separate personal summary of at most 300 Chinese characters
-> continue multi-turn questions against the same paper with page-aware sources
```

Acceptance rules:

1. A scan-only, encrypted, empty, or unparseable PDF fails closed. A report must not be generated without source text.
2. Report citations are structured as `source_url`, `page_start`, `page_end`, and `exact_quote`. Model-authored citation strings that cannot be matched to source text are discarded.
3. At least four key questions must cover the research problem, process/method, contribution, and evaluation/limitations.
4. A single paper may establish only what that study reports. It is not automatically field consensus.
5. The personal summary is user-authored, stored separately from the AI report, and hard-limited to 300 characters.

## Academic identity and evidence levels

- `A1`: formally published paper with complete identity in IEEE S&P, USENIX Security, ACM CCS, or NDSS.
- `A2`: formally published paper with complete identity outside the four-conference allowlist.
- `B1`: identifiable preprint; it must not be described as a formally accepted four-conference paper.
- `U`: some academic metadata exists, but title, authors, year, DOI, or official publication record is incomplete.
- `N/A`: no recognizable paper identity metadata.

The four-conference Gate requires aligned title, authors, publication year, canonical venue, and a DOI or official proceedings/publisher record. Retractions and withdrawals fail the Gate.

### Academic-grade evidence contract

`A1/A2/B1/U/N/A` is an identity profile only. It must never be used as a document-wide
"verified" score. FastRead keeps the following evidence axes independent and derives UI
labels from them:

1. `identity_status`: `unrecognized | incomplete | officially_aligned`.
   `officially_aligned` requires publisher/proceedings metadata to agree on title,
   authors, year, canonical venue, and DOI or official record URL. User-supplied fields
   remain unverified hints and never pass the Gate by themselves.
2. `source_status`: `blocked | parsed_partial | locked`. A locked source records the
   source hash, page count, parser/version, retrieval time, and any extraction limit.
3. `citation_status`: `unmatched | exact`. Only a normalized model quote fully contained
   in the specified locked page is exact. A real source fragment with model-added text is
   rejected.
4. `external_verification_status`: `not_run | source_only | supported | refuted | mixed |
   insufficient | data_void | source_risk`. The verification engine derives this state
   from stored claim/evidence identifiers; the report model cannot self-declare it.
5. `integrity_status`: `unknown | clear | preprint | retracted | withdrawn | stale`.
   A retraction or withdrawal invalidates any green academic-grade summary.
6. `reproducibility_status`: `not_assessed | artifacts_declared | artifacts_available |
   environment_locked | execution_attempted | reproduced | partially_reproduced |
   reproduction_failed`. A paper's own reproducibility claim is not experimental
   reproduction evidence.

User-visible labels follow these rules:

- **原文已定位**: the answer has at least one exact citation with locked source and page.
- **学术身份已确认**: identity is officially aligned, formally published, and the
  integrity check is current and clear.
- **学术级阅读 · 原文依据 · 未外部核验**: formal identity is confirmed, the source is
  locked, all substantive report sections are grounded by exact citations, and generation
  provenance is complete.
- **学术级阅读 · 外部已核实**: all conditions above plus rule-derived external support for
  every core claim and no equal-strength conflict.
- **实验已复现**: only when an actual execution has locked inputs, environment, commands,
  logs, outputs, and tolerance evidence.

Preprints may display `预印本 · 原文已定位` but not formal-publication or top-four-confirmed
labels. A report with any ungrounded core section must display `报告未完全落源` rather than
an academic-grade label.

## P1: scoped paper search

The search corpus is restricted to the four security conferences above plus a configurable systems-conference allowlist whose papers pass a security-topic Gate. Search metadata must retain title, abstract, authors, venue, year, DOI, official URL, and PDF URL. AI-extracted keywords are additive fields and never replace source metadata.

Elasticsearch remains the target inverted-index backend for the group deployment. Its absence must be reported explicitly; the generic web-verification search is not equivalent to the paper search engine.

## P2: presentation generation and group collaboration

- Generate a `.pptx` from the reading report, covering problem, method, contributions, evaluation, limitations, and references with page/source citations.
- Add shared group libraries, access control, comments, and review workflows only after the single-paper journey and scoped search are stable.
