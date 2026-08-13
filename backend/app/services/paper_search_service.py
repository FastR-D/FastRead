"""Venue-filtered academic paper search.

Scope (per product requirement): only surface security-relevant papers from the
security "big four" (IEEE S&P, USENIX Security, ACM CCS, NDSS) and a
configurable systems top-conference allowlist (OSDI, SOSP, ASPLOS, EuroSys,
USENIX ATC, SIGCOMM, NSDI, FAST).

Design notes
------------
* **Corpus source**: the arXiv API (``cs.CR`` and related categories). arXiv is
  used because it is keyless and its ``comments``/``journal_ref`` fields usually
  name the venue a preprint was accepted to — which is what lets us filter to
  the allowlist. A paper with no venue evidence is *not* silently promoted; it is
  reported separately as ``venue_unconfirmed`` so the caller can see what was
  excluded rather than mistaking the filter for exhaustive coverage.
* **Inverted index**: abstracts are tokenized into keywords and stored in a
  local inverted index (term -> paper ids) with an on-disk JSON cache. The index
  is deliberately shaped like an Elasticsearch mapping so the group deployment
  can swap :class:`InvertedIndex` for a real ES client without touching callers.
  Elasticsearch itself is *not* bundled — see ``search_backend`` in the response.
* **Ranking**: TF-IDF over the inverted index, plus a venue-track boost. No LLM
  is required for search itself; abstract keyword extraction is heuristic so the
  endpoint stays fast and free. An optional LLM pass can enrich keywords later.
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import httpx

from app.core.settings import get_settings
from app.services.academic_evidence import (
    allowed_venue_catalog,
    match_allowed_venue,
    normalize_doi,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

ARXIV_API = "http://export.arxiv.org/api/query"
ARXIV_NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

# Security-relevant arXiv categories. cs.CR is the primary security category.
SECURITY_CATEGORIES = ("cs.CR",)
SYSTEMS_CATEGORIES = ("cs.OS", "cs.DC", "cs.NI", "cs.AR")

SEARCH_TIMEOUT = float(os.getenv("PAPER_SEARCH_TIMEOUT", "12"))
FETCH_LIMIT = int(os.getenv("PAPER_SEARCH_FETCH_LIMIT", "80"))

# Tokens too generic to be useful index terms.
STOPWORDS = frozenset("""
a an and are as at be been but by for from has have how in into is it its of on or
that the their there these this to was were what when where which who will with
we our us you your they them he she his her i me my than then so such can could
should would may might must do does did not no nor only own same too very just
also however thus therefore paper papers work works study studies approach
approaches method methods result results show shows shown propose proposes
proposed present presents presented use uses used using based new novel
""".split())

TOKEN_RE = re.compile(r"[a-z][a-z0-9+.#-]{1,}")


def _tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(str(text or "").lower()) if t not in STOPWORDS and len(t) > 2]


def extract_keywords(title: str, abstract: str, limit: int = 12) -> list[str]:
    """Heuristic keyword extraction from a paper's title + abstract.

    Title terms are weighted higher because they are the author's own summary.
    This is the layer the requirement calls "利用 AI 工具分析论文摘要，提取关键词" —
    kept deterministic here so search works without an LLM round-trip; an LLM
    enrichment pass can override ``keywords`` later without changing the index.
    """
    scores: dict[str, float] = defaultdict(float)
    for token in _tokenize(title):
        scores[token] += 3.0
    for token in _tokenize(abstract):
        scores[token] += 1.0
    # Reward multi-word technical phrases appearing in the title.
    for phrase in re.findall(r"[a-z][a-z0-9-]+(?:\s+[a-z][a-z0-9-]+){1,2}", str(title or "").lower()):
        words = [w for w in phrase.split() if w not in STOPWORDS and len(w) > 2]
        if len(words) >= 2:
            scores[" ".join(words)] += 2.5
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return [term for term, _ in ranked[:limit]]


class InvertedIndex:
    """Minimal term -> doc-id inverted index with TF-IDF scoring.

    Shaped to mirror an Elasticsearch index so it can be replaced by a real ES
    client for the group deployment. Persisted as JSON under the data dir.
    """

    def __init__(self, cache_path: Path | None = None):
        settings = get_settings()
        self.cache_path = Path(cache_path) if cache_path else settings.data_dir / "paper_search_index.json"
        self._lock = threading.RLock()
        self.postings: dict[str, dict[str, int]] = {}
        self.documents: dict[str, dict] = {}
        self._load()

    # -- persistence --
    def _load(self) -> None:
        try:
            if self.cache_path.exists():
                payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
                self.postings = payload.get("postings") or {}
                self.documents = payload.get("documents") or {}
        except Exception as exc:  # a corrupt cache must not break search
            logger.warning(f"论文检索索引缓存读取失败，将重建: {exc}")
            self.postings, self.documents = {}, {}

    def save(self) -> None:
        with self._lock:
            try:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                self.cache_path.write_text(
                    json.dumps(
                        {"postings": self.postings, "documents": self.documents},
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            except Exception as exc:
                logger.warning(f"论文检索索引缓存写入失败: {exc}")

    # -- indexing --
    def index_paper(self, paper: dict) -> None:
        paper_id = str(paper.get("id") or "").strip()
        if not paper_id:
            return
        with self._lock:
            self.documents[paper_id] = paper
            terms = _tokenize(f"{paper.get('title', '')} {paper.get('abstract', '')}")
            terms.extend(t for kw in paper.get("keywords") or [] for t in _tokenize(kw))
            counts: dict[str, int] = defaultdict(int)
            for term in terms:
                counts[term] += 1
            for term, count in counts.items():
                self.postings.setdefault(term, {})[paper_id] = count

    def index_many(self, papers: list[dict]) -> int:
        for paper in papers:
            self.index_paper(paper)
        self.save()
        return len(self.documents)

    # -- querying --
    def search(self, query: str, *, limit: int = 20) -> list[tuple[str, float]]:
        query_terms = _tokenize(query)
        if not query_terms:
            return []
        total_docs = max(1, len(self.documents))
        scores: dict[str, float] = defaultdict(float)
        for term in query_terms:
            postings = self.postings.get(term)
            if not postings:
                continue
            idf = math.log(1 + total_docs / (1 + len(postings)))
            for paper_id, tf in postings.items():
                scores[paper_id] += (1 + math.log(tf)) * idf
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        return ranked[:limit]

    def stats(self) -> dict:
        return {"documents": len(self.documents), "terms": len(self.postings)}


def _arxiv_query(query: str, categories: tuple[str, ...], limit: int) -> str:
    """Build an arXiv API query restricted to the given categories."""
    cleaned = re.sub(r"[^\w\s+.#-]", " ", str(query or "")).strip()
    terms = " AND ".join(f"all:{t}" for t in cleaned.split()[:8]) if cleaned else ""
    cat_clause = " OR ".join(f"cat:{c}" for c in categories)
    search_query = f"({cat_clause})" + (f" AND ({terms})" if terms else "")
    return f"{ARXIV_API}?" + urlencode(
        {
            "search_query": search_query,
            "start": 0,
            "max_results": max(1, min(limit, 200)),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
    )


def _parse_arxiv_feed(xml_text: str) -> list[dict]:
    """Parse an arXiv Atom feed into normalized paper dicts."""
    papers: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning(f"arXiv 响应解析失败: {exc}")
        return papers
    for entry in root.findall("a:entry", ARXIV_NS):
        def text(path: str) -> str:
            node = entry.find(path, ARXIV_NS)
            return re.sub(r"\s+", " ", (node.text or "").strip()) if node is not None else ""

        arxiv_id = text("a:id")
        title = text("a:title")
        if not title:
            continue
        abstract = text("a:summary")
        comment = text("arxiv:comment")
        journal_ref = text("arxiv:journal_ref")
        doi = text("arxiv:doi")
        authors = [
            re.sub(r"\s+", " ", (n.text or "").strip())
            for n in entry.findall("a:author/a:name", ARXIV_NS)
            if (n.text or "").strip()
        ]
        categories = [
            c.attrib.get("term", "")
            for c in entry.findall("a:category", ARXIV_NS)
            if c.attrib.get("term")
        ]
        published = text("a:published")
        year = None
        match_year = re.search(r"(19|20)\d{2}", f"{published} {journal_ref} {comment}")
        if match_year:
            year = int(match_year.group(0))
        pdf_url = ""
        for link in entry.findall("a:link", ARXIV_NS):
            if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
                pdf_url = link.attrib.get("href", "")
                break
        papers.append(
            {
                "id": arxiv_id.rsplit("/", 1)[-1] or arxiv_id,
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "categories": categories,
                "comment": comment,
                "journal_ref": journal_ref,
                "doi": normalize_doi(doi, journal_ref, comment),
                "year": year,
                "published_at": published,
                "source_url": arxiv_id,
                "pdf_url": pdf_url,
                "source": "arxiv",
            }
        )
    return papers


class PaperSearchService:
    """Search security/systems top-conference papers, venue-filtered."""

    def __init__(self, index: InvertedIndex | None = None, client_factory=None):
        self.index = index or InvertedIndex()
        self._client_factory = client_factory or httpx.Client

    def _fetch_arxiv(self, query: str, tracks: tuple[str, ...], limit: int) -> list[dict]:
        categories: tuple[str, ...] = ()
        if "security" in tracks:
            categories += SECURITY_CATEGORIES
        if "systems" in tracks:
            categories += SYSTEMS_CATEGORIES
        if not categories:
            categories = SECURITY_CATEGORIES
        url = _arxiv_query(query, categories, limit)
        try:
            with self._client_factory(timeout=SEARCH_TIMEOUT, follow_redirects=True) as client:
                response = client.get(url)
                if response.status_code != 200:
                    logger.warning(f"arXiv 检索返回 {response.status_code}")
                    return []
                return _parse_arxiv_feed(response.text)
        except Exception as exc:
            logger.warning(f"arXiv 检索失败: {exc}")
            return []

    @staticmethod
    def _classify(paper: dict) -> dict:
        """Attach the allowlist venue match (if any) to a paper."""
        venue = match_allowed_venue(paper.get("journal_ref"), paper.get("comment"))
        enriched = dict(paper)
        enriched["venue"] = venue
        enriched["venue_confirmed"] = bool(venue.get("id"))
        enriched["keywords"] = extract_keywords(paper.get("title", ""), paper.get("abstract", ""))
        return enriched

    def search(
        self,
        *,
        query: str,
        tracks: tuple[str, ...] = ("security", "systems"),
        venue_ids: tuple[str, ...] = (),
        limit: int = 20,
        include_unconfirmed: bool = False,
        refresh: bool = True,
    ) -> dict:
        """Run a venue-filtered search.

        Returns matched papers plus an explicit account of what was excluded,
        so a thin result set is never mistaken for an exhaustive corpus.
        """
        fetched: list[dict] = []
        if refresh:
            fetched = self._fetch_arxiv(query, tracks, FETCH_LIMIT)
            classified = [self._classify(p) for p in fetched]
            if classified:
                self.index.index_many(classified)

        # Rank from the index so previously-fetched papers stay searchable.
        ranked_ids = self.index.search(query, limit=max(limit * 4, 40))
        results: list[dict] = []
        unconfirmed: list[dict] = []
        allowed = set(venue_ids) if venue_ids else set(allowed_venue_catalog().keys())

        for paper_id, score in ranked_ids:
            paper = self.index.documents.get(paper_id)
            if not paper:
                continue
            venue = paper.get("venue") or {}
            track = venue.get("track") or ""
            if not paper.get("venue_confirmed"):
                if len(unconfirmed) < limit:
                    unconfirmed.append({**paper, "relevance": round(score, 4)})
                continue
            if venue.get("id") not in allowed:
                continue
            if tracks and track and track not in tracks:
                continue
            boost = 1.15 if track == "security" else 1.0
            results.append({**paper, "relevance": round(score * boost, 4)})

        results.sort(key=lambda p: -p["relevance"])
        results = results[:limit]

        return {
            "query": query,
            "tracks": list(tracks),
            "search_backend": "local_inverted_index",
            "elasticsearch_available": False,
            "venue_allowlist": [
                {"id": vid, "short_name": meta["short_name"], "track": meta["track"]}
                for vid, meta in allowed_venue_catalog().items()
                if vid in allowed
            ],
            "results": results,
            "result_count": len(results),
            "venue_unconfirmed_count": len(unconfirmed),
            "venue_unconfirmed": unconfirmed[:limit] if include_unconfirmed else [],
            "fetched_this_run": len(fetched),
            "index_stats": self.index.stats(),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "coverage_note": (
                "结果仅来自 arXiv 中能通过 comments/journal_ref 确认属于允许会议的论文；"
                "Elasticsearch 尚未接入，venue 无法确认的论文单独计入 venue_unconfirmed，未混入结果。"
            ),
        }
