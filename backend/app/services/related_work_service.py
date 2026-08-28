from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone

from app.db.related_work_dao import (
    get_latest_related_work,
    get_related_work_by_cache_key,
    save_related_work,
)
from app.repositories.paper_artifacts import PaperArtifactRepository
from app.services.paper_search_service import PaperSearchService, extract_keywords


RELATED_WORK_CONFIG_VERSION = "related-work-v4-keyword-paged"
DEFAULT_RELATED_WORK_LIMIT = 120
MAX_RELATED_WORK_LIMIT = 200
TOKEN_RE = re.compile(r"[a-z][a-z0-9+.#-]{2,}", re.IGNORECASE)
GENERIC_TITLE_TERMS = {
    "comparative",
    "behavioral",
    "measure",
    "measurement",
    "framework",
    "approach",
    "method",
    "analysis",
    "study",
}
CITATION_RE = re.compile(
    r"(?P<title>[A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*"
    r"(?:\s+[A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*){0,3})"
    r"\s*\((?P<authors>[^()]{2,100}?),\s*(?P<year>(?:19|20)\d{2})\)"
)


def _pages(evidence) -> list[int]:
    pages: set[int] = set()
    for item in evidence if isinstance(evidence, list) else []:
        if not isinstance(item, dict):
            continue
        start = item.get("page_start") or item.get("page")
        end = item.get("page_end") or start
        if isinstance(start, int) and isinstance(end, int):
            pages.update(range(max(1, start), max(start, end) + 1))
    return sorted(pages)


def _anchor(kind: str, text: str, pages: list[int], report_version: str) -> dict:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    anchor_id = hashlib.sha1(
        f"{kind}|{normalized}|{','.join(map(str, pages))}|{report_version}".encode("utf-8")
    ).hexdigest()[:16]
    return {
        "anchor_id": anchor_id,
        "kind": kind,
        "text": normalized,
        "report_version": report_version,
        "pages": pages,
    }


def _terms(text: str) -> set[str]:
    terms: set[str] = set()
    camel_split = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(text or ""))
    for token in TOKEN_RE.findall(camel_split.lower()):
        token = token.strip(".")
        if token in {"al", "et", "etc"}:
            continue
        terms.add(token)
        if token.endswith("s") and len(token) > 4 and not token.endswith("ss"):
            terms.add(token[:-1])
        if "-" in token:
            terms.update(part for part in token.split("-") if len(part) > 2)
    return terms


def _bibliography_candidates(document: dict) -> list[dict]:
    """Extract source-grounded leads from the paper's Related Work section.

    These records are deliberately modest metadata leads.  They keep local-first
    discovery useful when external providers are unavailable without pretending
    that an inline citation is a verified publisher record.
    """
    candidates: dict[str, dict] = {}
    in_related_work = False
    for page in document.get("pages") or []:
        page_number = page.get("page")
        text = re.sub(r"\s+", " ", str(page.get("text") or "")).strip()
        if not text:
            continue
        if not in_related_work:
            heading = re.search(
                r"\b(?:\d+(?:\.\d+)*\.?\s+)?RELATED WORKS?\b", text, re.IGNORECASE
            )
            if not heading:
                continue
            in_related_work = True
            text = text[heading.end() :].strip()
        next_section = re.search(
            r"\b(?:\d+(?:\.\d+)*\.?\s+)?"
            r"(?:METHODOLOGY|METHODS?|EXPERIMENTS?|BACKGROUND)\b",
            text,
            re.IGNORECASE,
        )
        section_text = text[: next_section.start()] if next_section else text
        for match in CITATION_RE.finditer(section_text):
            title = re.sub(r"\s+", " ", match.group("title")).strip(" ,.;:")
            if title.lower() in {"eigenbench", "ours"}:
                continue
            citation = match.group(0)
            context_start = max(0, match.start() - 100)
            context_end = min(len(section_text), match.end() + 220)
            context = section_text[context_start:context_end].strip(" ,.;:")
            author_text = match.group("authors").replace(" et al.", "")
            authors = [
                author.strip()
                for author in re.split(r",|;|\band\b", author_text)
                if author.strip()
            ][:20]
            canonical_title = re.sub(r"\W+", "", title.lower())
            candidate_id = hashlib.sha1(
                f"{document.get('content_hash', '')}|{canonical_title}|{match.group('year')}".encode("utf-8")
            ).hexdigest()[:20]
            candidates.setdefault(
                f"{canonical_title}|{match.group('year')}",
                {
                    "id": f"bibliography-{candidate_id}",
                    "title": title,
                    "abstract": context,
                    "authors": authors,
                    "categories": [],
                    "comment": citation,
                    "journal_ref": "",
                    "doi": "",
                    "year": int(match.group("year")),
                    "published_at": "",
                    "source_url": "",
                    "pdf_url": "",
                    "source": "paper_bibliography",
                    "provenance": {
                        "provider": "paper_bibliography",
                        "retrieved_at": "",
                        "metadata_only": True,
                        "source_page": page_number,
                        "exact_quote": citation,
                        "note": "由当前论文 Related Work 章节中的引文确定性提取，题录与链接仍需外部来源闭合。",
                    },
                },
            )
        if next_section:
            break
    return list(candidates.values())


class RelatedWorkService:
    def __init__(
        self,
        artifacts: PaperArtifactRepository | None = None,
        search: PaperSearchService | None = None,
    ):
        self.artifacts = artifacts or PaperArtifactRepository()
        self.search = search or PaperSearchService()

    @staticmethod
    def _anchors(result: dict) -> tuple[list[dict], str]:
        document = result.get("paper_document") or {}
        report = (result.get("insights") or {}).get("reading_report") or {}
        report_version = str(
            report.get("report_version")
            or report.get("version")
            or report.get("generated_at")
            or "no-report"
        )
        anchors: list[dict] = []

        for item in report.get("key_questions") or []:
            if not isinstance(item, dict):
                continue
            pages = _pages(item.get("evidence"))
            # The visible question can be a generic report template (for example,
            # “论文要解决的研究问题是什么？”).  Its evidence-backed answer carries
            # the actual retrieval vocabulary, so prefer it as the anchor text.
            text = item.get("answer") or item.get("question") or ""
            if pages and text:
                anchors.append(_anchor("research_question", text, pages, report_version))
                break
        for item in (report.get("process") or [])[:3]:
            if not isinstance(item, dict):
                continue
            pages = _pages(item.get("evidence"))
            text = " ".join(str(item.get(key) or "") for key in ("step", "description")).strip()
            if pages and text:
                anchors.append(_anchor("method", text, pages, report_version))
        for item in report.get("contributions") or []:
            if not isinstance(item, dict):
                continue
            pages = _pages(item.get("evidence"))
            text = " ".join(str(item.get(key) or "") for key in ("title", "description")).strip()
            if pages and text:
                anchors.append(_anchor("contribution", text, pages, report_version))

        if not anchors:
            title = str(document.get("title") or "").strip()
            first_page = next(
                (str(page.get("text") or "") for page in document.get("pages") or [] if page.get("page") == 1),
                "",
            )
            abstract_match = re.search(r"\babstract\b(.{0,1800})", first_page, re.IGNORECASE | re.DOTALL)
            abstract = re.sub(r"\s+", " ", abstract_match.group(1)).strip() if abstract_match else ""
            fallback = " ".join([title, *extract_keywords(title, abstract, limit=10)]).strip()
            if not fallback:
                raise ValueError("论文缺少可落源的报告锚点、标题和摘要")
            anchors.append(_anchor("fallback", fallback, [1], report_version))
        return anchors, report_version

    @staticmethod
    def _queries(
        anchors: list[dict],
        document: dict | None = None,
        bibliography_candidates: list[dict] | None = None,
    ) -> list[str]:
        queries: list[str] = []
        document = document or {}
        title = str(document.get("title") or "")
        first_page = next(
            (str(page.get("text") or "") for page in document.get("pages") or [] if page.get("page") == 1),
            "",
        )
        abstract_match = re.search(
            r"\babstract\b(.{0,1800}?)(?:\b\d+\s+introduction\b|$)",
            first_page,
            re.IGNORECASE | re.DOTALL,
        )
        abstract = abstract_match.group(1) if abstract_match else ""
        document_terms = dict.fromkeys(
            term for keyword in extract_keywords(title, abstract, limit=8) for term in keyword.split()
        )
        document_query = " ".join(list(document_terms)[:6])
        if document_query:
            queries.append(document_query)
        anchor_queries: list[str] = []
        for anchor in anchors:
            keywords = dict.fromkeys(
                term
                for keyword in extract_keywords(anchor["text"], "", limit=8)
                for term in keyword.split()
            )
            query = " ".join(list(keywords)[:6])
            if query and query not in queries and query not in anchor_queries:
                anchor_queries.append(query)

        candidates = bibliography_candidates or []
        anchor_vocabulary = set().union(*(_terms(anchor["text"]) for anchor in anchors)) if anchors else set()
        ranked_citations = sorted(
            candidates,
            key=lambda candidate: (
                -len(
                    anchor_vocabulary
                    & _terms(f"{candidate.get('title', '')} {candidate.get('abstract', '')}")
                ),
                -int(candidate.get("year") or 0),
                str(candidate.get("title") or ""),
            ),
        )
        citation_query = next(
            (
                re.sub(r"\s+", " ", str(candidate.get("title") or "")).strip()
                for candidate in ranked_citations
                if str(candidate.get("title") or "").strip()
            ),
            "",
        )
        if anchor_queries:
            queries.append(anchor_queries.pop(0))
        if citation_query and citation_query not in queries:
            queries.append(citation_query)
        for anchor_query in anchor_queries:
            if len(queries) == 3:
                break
            queries.append(anchor_query)
        return queries

    @staticmethod
    def _score_neighbor(
        candidate: dict,
        anchors: list[dict],
        topic_terms: set[str] | None = None,
    ) -> tuple[float, list[str], list[str]]:
        title_terms = _terms(str(candidate.get("title") or ""))
        keyword_terms = {
            term
            for keyword in candidate.get("keywords") or []
            for term in _terms(str(keyword))
        }
        abstract_terms = _terms(str(candidate.get("abstract") or ""))
        matched_ids: list[str] = []
        anchor_term_sets = [_terms(anchor["text"]) for anchor in anchors]
        all_anchor_terms = set().union(*anchor_term_sets) if anchor_term_sets else set()
        title_overlap = all_anchor_terms & title_terms
        keyword_overlap = (all_anchor_terms & keyword_terms) - title_overlap
        abstract_overlap = (all_anchor_terms & abstract_terms) - title_overlap - keyword_overlap
        overlap = title_overlap | keyword_overlap | abstract_overlap
        discovery_sources = set(candidate.get("discovery_sources") or [])
        is_source_grounded_citation = (
            candidate.get("source") == "paper_bibliography"
            or "paper_bibliography" in discovery_sources
        )
        if (
            topic_terms
            and not is_source_grounded_citation
            and len(topic_terms & (title_terms | keyword_terms)) < 2
        ):
            return 0.0, [], []
        for anchor in anchors:
            terms = _terms(anchor["text"])
            if terms & overlap:
                matched_ids.append(anchor["anchor_id"])
        # A term can occur in several report anchors, but it still represents one
        # lexical match.  Count it once so broad words such as "truth" are not
        # multiplied into a false top result merely because several anchors reuse it.
        score = 4 * len(title_overlap) + 3 * len(keyword_overlap) + len(abstract_overlap)
        score += min(float(candidate.get("relevance") or 0), 10.0)
        if (candidate.get("venue") or {}).get("id"):
            score += 2.0
        year = candidate.get("year")
        if isinstance(year, int):
            score += max(0.0, min(1.0, (year - 2000) / 30))
        return round(score, 4), matched_ids, sorted(overlap)

    @staticmethod
    def _discovery_channel(candidate: dict) -> tuple[str, str]:
        provider = str(
            (candidate.get("provenance") or {}).get("provider")
            or candidate.get("source")
            or "unknown"
        )
        sources = {provider, *(str(item) for item in candidate.get("discovery_sources") or [])}
        if "arxiv" in sources:
            return "primary", "arxiv"
        if sources.intersection({"openalex", "semantic_scholar", "google_scholar", "paper_bibliography"}):
            return "supplemental", "supplemental"
        return "primary", "elasticsearch"

    @staticmethod
    def _decorate_snapshot(snapshot: dict, queries: list[str], result_limit: int) -> dict:
        decorated = dict(snapshot)
        keywords = list(
            dict.fromkeys(
                term
                for query in queries
                for term in query.split()
                if term
            )
        )
        neighbors = decorated.get("neighbors") or []
        source_counts = {
            channel: sum(1 for item in neighbors if item.get("discovery_channel") == channel)
            for channel in ("arxiv", "elasticsearch", "supplemental")
        }
        decorated.update({
            "queries": queries,
            "search_keywords": keywords,
            "result_limit": result_limit,
            "source_counts": source_counts,
            "search_policy": {
                "mode": "keyword_first",
                "primary_channels": ["arxiv", "elasticsearch"],
                "supplemental_channels": [
                    "openalex",
                    "semantic_scholar",
                    "google_scholar",
                    "paper_bibliography",
                ],
            },
        })
        return decorated

    def generate(
        self,
        task_id: str,
        *,
        force: bool = False,
        limit: int = DEFAULT_RELATED_WORK_LIMIT,
    ) -> dict:
        limit = max(1, min(int(limit or DEFAULT_RELATED_WORK_LIMIT), MAX_RELATED_WORK_LIMIT))
        result = self.artifacts.read_result(task_id)
        if not result or result.get("paper_task") is not True:
            raise ValueError("论文任务不存在")
        document = result.get("paper_document") or {}
        anchors, report_version = self._anchors(result)
        local_candidates = _bibliography_candidates(document)
        queries = self._queries(anchors, document, local_candidates)
        cache_material = {
            "paper_content_hash": document.get("content_hash") or "",
            "report_version": report_version,
            "anchors": anchors,
            "queries": queries,
            "result_limit": limit,
            "config_version": RELATED_WORK_CONFIG_VERSION,
        }
        cache_key = hashlib.sha256(
            json.dumps(cache_material, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        if not force and (cached := get_related_work_by_cache_key(cache_key)):
            cached["cache_hit"] = True
            return self._decorate_snapshot(cached, queries, limit)

        combined_query = " ".join(dict.fromkeys(term for query in queries for term in query.split()))[:300]
        search_result = self.search.search(
            query=combined_query,
            semantic_queries=tuple(queries[:3]),
            tracks=("security", "systems", "ai"),
            limit=max(limit * 3, 180),
            include_unconfirmed=True,
            refresh=True,
            include_arxiv=True,
            include_scholar=True,
            prioritize_arxiv=True,
            local_candidates=local_candidates,
        )
        own_title = re.sub(r"\W+", "", str(document.get("title") or "").lower())
        topic_terms = _terms(combined_query) - GENERIC_TITLE_TERMS
        citation_query_indexes = {
            index
            for index, query in enumerate(queries)
            if any(
                re.sub(r"\W+", "", query.lower())
                == re.sub(r"\W+", "", str(candidate.get("title") or "").lower())
                for candidate in local_candidates
            )
        }
        source_grounded_query_indexes = {0, *citation_query_indexes}
        neighbors = []
        for candidate in search_result.get("results") or []:
            normalized_title = re.sub(r"\W+", "", str(candidate.get("title") or "").lower())
            if own_title and normalized_title == own_title:
                continue
            score, matched_ids, overlap = self._score_neighbor(candidate, anchors, topic_terms)
            if not matched_ids:
                continue
            if candidate.get("source") in {"openalex", "semantic_scholar"}:
                query_indexes = candidate.get("provider_query_indexes") or []
                # The first query is always derived from the paper title and
                # abstract.  Broad anchor-only matches must also occur in that
                # core query (or in multiple independent query formulations) to
                # avoid results that happen to share generic words such as
                # "ground truth" while discussing an unrelated field.
                if (
                    not source_grounded_query_indexes.intersection(query_indexes)
                    and int(candidate.get("provider_query_hits") or 0) < 2
                ):
                    continue
            venue = candidate.get("venue") or {}
            source_url = str(candidate.get("source_url") or "")
            source_role, discovery_channel = self._discovery_channel(candidate)
            neighbors.append(
                {
                    "canonical_paper_id": str(candidate.get("id") or uuid.uuid4()),
                    "title": str(candidate.get("title") or ""),
                    "authors": candidate.get("authors") or [],
                    "year": candidate.get("year"),
                    "venue": venue.get("short_name") or venue.get("name") or candidate.get("journal_ref") or "",
                    "doi": str(candidate.get("doi") or ""),
                    "official_url": source_url,
                    "metadata_url": str(candidate.get("metadata_url") or ""),
                    "source_links": candidate.get("source_links") or [],
                    "discovery_sources": candidate.get("discovery_sources") or [],
                    "arxiv_url": source_url if candidate.get("source") == "arxiv" else "",
                    "pdf_url": str(candidate.get("pdf_url") or ""),
                    "matched_anchor_ids": matched_ids,
                    "overlapping_terms": overlap,
                    "relevance_score": score,
                    "source_role": source_role,
                    "discovery_channel": discovery_channel,
                    "provenance": candidate.get("provenance") or {
                        "provider": candidate.get("source") or "unknown",
                        "retrieved_at": search_result.get("retrieved_at") or "",
                        "metadata_only": True,
                    },
                }
            )
        neighbors.sort(
            key=lambda item: (
                0 if item["source_role"] == "primary" else 1,
                -item["relevance_score"],
                -(item["year"] or 0),
                item["title"],
            )
        )
        snapshot = {
            "id": str(uuid.uuid4()),
            "paper_id": task_id,
            "paper_content_hash": str(document.get("content_hash") or ""),
            "report_version": report_version,
            "cache_key": cache_key,
            "anchors": anchors,
            "queries": queries,
            "neighbors": neighbors[:limit],
            "provider_status": search_result.get("provider_status") or {},
            "search_backend": search_result.get("search_backend") or "local_inverted_index",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "cache_hit": False,
        }
        saved = save_related_work(snapshot)
        saved["cache_hit"] = False
        return self._decorate_snapshot(saved, queries, limit)

    def get(self, task_id: str) -> dict | None:
        snapshot = get_latest_related_work(task_id)
        if not snapshot:
            return None
        result = self.artifacts.read_result(task_id) or {}
        document = result.get("paper_document") or {}
        anchors = snapshot.get("anchors") or []
        queries = self._queries(anchors, document, _bibliography_candidates(document))
        return self._decorate_snapshot(snapshot, queries, len(snapshot.get("neighbors") or []))
