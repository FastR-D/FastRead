"""Layered academic paper discovery with explicit evidence boundaries.

The core corpus is the configured security, systems, and AI conference
allowlist.  arXiv broadens discovery and an optional Google Scholar adapter
adds citation-chain / publisher-version metadata.  Search results are metadata
leads until FastRead imports and parses the full text; this module never marks a
search snippet as verified evidence.

Elasticsearch is used when configured and healthy.  Every fetched record is
also written to a persistent local inverted index so desktop installations keep
working when Elasticsearch is absent or temporarily unavailable.
"""

from __future__ import annotations

import hashlib
from html import unescape
import json
import math
import os
import re
import threading
import xml.etree.ElementTree as ET
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import httpx

from app.core.settings import get_settings
from app.services.academic_evidence import allowed_venue_catalog, match_allowed_venue, normalize_doi
from app.services.metadata_normalization import canonical_identity_keys
from app.services.search_connection_config import get_search_connection_config
from app.utils.logger import get_logger

logger = get_logger(__name__)

ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
OPENALEX_API = "https://api.openalex.org/works"
CROSSREF_API = "https://api.crossref.org/works"
OPENALEX_ARXIV_SOURCE_ID = "S4306400194"
SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper/search"

TRACK_CATEGORIES = {
    "security": ("cs.CR",),
    "systems": ("cs.OS", "cs.DC", "cs.NI", "cs.AR", "cs.PF"),
    "ai": ("cs.AI", "cs.LG", "cs.CL", "cs.CV", "stat.ML"),
}

SEARCH_TIMEOUT = float(os.getenv("PAPER_SEARCH_TIMEOUT", "8"))
SEARCH_DEADLINE = float(os.getenv("PAPER_SEARCH_DEADLINE", "8"))
FETCH_LIMIT = int(os.getenv("PAPER_SEARCH_FETCH_LIMIT", "100"))
INDEX_STALE_HOURS = int(os.getenv("PAPER_SEARCH_INDEX_STALE_HOURS", "168"))

STOPWORDS = frozenset(
    """
    a an and are as at be been but by for from has have how in into is it its of on or
    that the their there these this to was were what when where which who will with
    we our us you your they them he she his her i me my than then so such can could
    should would may might must do does did not no nor only own same too very just
    also however thus therefore paper papers work works study studies approach
    approaches method methods result results show shows shown propose proposes
    proposed present presents presented use uses used using based new novel
    """.split()
)
TOKEN_RE = re.compile(r"[a-z][a-z0-9+.#-]{1,}")


class AcademicProxyRequiredError(RuntimeError):
    """Raised when public academic traffic is forbidden from going direct."""


def _academic_proxy_required(value: bool | None = None) -> bool:
    if value is not None:
        return value
    return os.getenv("PAPER_SEARCH_REQUIRE_PROXY", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def public_academic_client_kwargs(
    proxy_url: str | None = None,
    *,
    require_proxy: bool | None = None,
) -> dict:
    """Build an isolated HTTP client config for public academic providers.

    FastRead may need a local proxy to reach public metadata services while its
    own API, Elasticsearch, and model endpoints remain direct.  httpx 0.28 uses
    the singular ``proxy`` keyword.  Disabling ``trust_env`` here prevents a
    process-wide HTTP_PROXY setting from silently widening the proxy boundary.
    """

    configured_proxy = (
        str(proxy_url).strip()
        if proxy_url is not None
        else os.getenv("PAPER_SEARCH_PROXY_URL", "").strip()
    )
    if _academic_proxy_required(require_proxy) and not configured_proxy:
        raise AcademicProxyRequiredError(
            "PAPER_SEARCH_PROXY_URL is required for public academic providers"
        )
    kwargs = {
        "timeout": SEARCH_TIMEOUT,
        "follow_redirects": True,
        "trust_env": False,
    }
    if configured_proxy:
        kwargs["proxy"] = configured_proxy
    return kwargs


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for token in TOKEN_RE.findall(str(text or "").lower()):
        values = [token]
        if "-" in token:
            values.extend(token.split("-"))
        tokens.extend(value for value in values if value not in STOPWORDS and len(value) > 2)
    return tokens


def extract_keywords(title: str, abstract: str, limit: int = 12) -> list[str]:
    """Deterministic keyword fallback used when no AI enricher is configured."""
    scores: dict[str, float] = defaultdict(float)
    first_seen: dict[str, int] = {}
    position = 0
    for token in _tokenize(title):
        first_seen.setdefault(token, position)
        position += 1
        scores[token] += 3.0
    for token in _tokenize(abstract):
        first_seen.setdefault(token, position)
        position += 1
        scores[token] += 1.0
    for phrase in re.findall(r"[a-z][a-z0-9-]+(?:\s+[a-z][a-z0-9-]+){1,2}", str(title or "").lower()):
        words = [word for word in phrase.split() if word not in STOPWORDS and len(word) > 2]
        if len(words) >= 2:
            normalized_phrase = " ".join(words)
            first_seen.setdefault(normalized_phrase, position)
            position += 1
            scores[normalized_phrase] += 2.5
    return [
        term
        for term, _score in sorted(
            scores.items(),
            key=lambda item: (-item[1], first_seen[item[0]]),
        )[:limit]
    ]


def _stable_paper_id(*values: str) -> str:
    joined = "|".join(re.sub(r"\s+", " ", str(value or "")).strip().lower() for value in values)
    return hashlib.sha1(joined.encode("utf-8", errors="ignore")).hexdigest()[:20]


def _canonical_arxiv_pdf(arxiv_id: str) -> str:
    identifier = str(arxiv_id or "").strip().rsplit("/", 1)[-1]
    if not identifier:
        return ""
    return f"https://arxiv.org/pdf/{identifier}.pdf"


class HttpKeywordEnricher:
    """Optional AI keyword service; expected response: {"keywords": [...]}."""

    def __init__(self, endpoint: str | None = None, client_factory=None):
        self.endpoint = (endpoint or os.getenv("PAPER_SEARCH_KEYWORD_ENDPOINT", "")).strip()
        self._client_factory = client_factory or httpx.Client

    @property
    def configured(self) -> bool:
        return bool(self.endpoint)

    def enrich(self, title: str, abstract: str) -> list[str]:
        if not self.endpoint:
            return []
        with self._client_factory(timeout=SEARCH_TIMEOUT, follow_redirects=True) as client:
            response = client.post(self.endpoint, json={"title": title, "abstract": abstract})
            response.raise_for_status()
            payload = response.json()
        values = payload.get("keywords") if isinstance(payload, dict) else []
        return [str(item).strip().lower() for item in values or [] if str(item).strip()][:20]


class InvertedIndex:
    """Persistent local term-to-document index and safe Elasticsearch fallback."""

    def __init__(self, cache_path: Path | None = None):
        settings = get_settings()
        self.cache_path = Path(cache_path) if cache_path else settings.data_dir / "paper_search_index.json"
        self._lock = threading.RLock()
        self.postings: dict[str, dict[str, int]] = {}
        self.documents: dict[str, dict] = {}
        self.last_indexed_at = ""
        self.metadata: dict = {}
        self._load()

    def _load(self) -> None:
        try:
            if not self.cache_path.exists():
                return
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            self.postings = payload.get("postings") or {}
            self.documents = payload.get("documents") or {}
            self.last_indexed_at = payload.get("last_indexed_at") or ""
            self.metadata = payload.get("metadata") or {}
        except Exception as exc:
            logger.warning(f"论文检索索引缓存读取失败，将重建: {exc}")
            self.postings, self.documents, self.last_indexed_at, self.metadata = {}, {}, "", {}

    def _rebuild_postings(self) -> None:
        postings: dict[str, dict[str, int]] = {}
        for paper_id, paper in self.documents.items():
            terms = _tokenize(f"{paper.get('title', '')} {paper.get('abstract', '')}")
            terms.extend(token for keyword in paper.get("keywords") or [] for token in _tokenize(keyword))
            counts: dict[str, int] = defaultdict(int)
            for term in terms:
                counts[term] += 1
            for term, count in counts.items():
                postings.setdefault(term, {})[paper_id] = count
        self.postings = postings

    def save(self) -> None:
        with self._lock:
            try:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
                temporary.write_text(
                    json.dumps(
                        {
                            "version": 2,
                            "last_indexed_at": self.last_indexed_at,
                            "metadata": self.metadata,
                            "postings": self.postings,
                            "documents": self.documents,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                temporary.replace(self.cache_path)
            except Exception as exc:
                logger.warning(f"论文检索索引缓存写入失败: {exc}")

    def index_many(self, papers: list[dict]) -> int:
        if not papers:
            return len(self.documents)
        with self._lock:
            for paper in papers:
                paper_id = str(paper.get("id") or "").strip()
                if paper_id:
                    self.documents[paper_id] = paper
            self._rebuild_postings()
            self.last_indexed_at = utc_now_iso()
            self.save()
        return len(self.documents)

    def replace_all(self, papers: list[dict], *, metadata: dict | None = None) -> int:
        """Atomically replace the complete local fallback corpus."""
        with self._lock:
            self.documents = {
                str(paper.get("id")): dict(paper)
                for paper in papers
                if str(paper.get("id") or "").strip()
            }
            self.metadata = dict(metadata or {})
            self._rebuild_postings()
            self.last_indexed_at = utc_now_iso()
            self.save()
        return len(self.documents)

    def search(self, query: str, *, limit: int = 20) -> list[tuple[str, float]]:
        terms = _tokenize(query)
        if not terms:
            return []
        total_docs = max(1, len(self.documents))
        scores: dict[str, float] = defaultdict(float)
        for term in terms:
            postings = self.postings.get(term) or {}
            idf = math.log(1 + total_docs / (1 + len(postings)))
            for paper_id, term_frequency in postings.items():
                scores[paper_id] += (1 + math.log(term_frequency)) * idf
        return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]

    def stats(self) -> dict:
        return {
            "documents": len(self.documents),
            "terms": len(self.postings),
            "last_indexed_at": self.last_indexed_at,
            "metadata": self.metadata,
        }


class ElasticsearchIndex:
    """Small HTTP Elasticsearch adapter.  No Elasticsearch package is bundled."""

    def __init__(
        self,
        url: str | None = None,
        index_name: str | None = None,
        api_key: str | None = None,
        client_factory=None,
    ):
        configured_url = os.getenv("ELASTICSEARCH_URL", "") if url is None else url
        self.url = str(configured_url or "").strip().rstrip("/")
        self.index_name = (index_name or os.getenv("PAPER_SEARCH_ES_INDEX", "fastread-papers")).strip()
        self.api_key = (api_key or os.getenv("ELASTICSEARCH_API_KEY", "")).strip()
        self.username = os.getenv("ELASTICSEARCH_USERNAME", "").strip()
        self.password = os.getenv("ELASTICSEARCH_PASSWORD", "")
        self._client_factory = client_factory or httpx.Client
        self.last_error = ""

    @property
    def configured(self) -> bool:
        return bool(self.url)

    def _client_kwargs(self) -> dict:
        headers = {"Authorization": f"ApiKey {self.api_key}"} if self.api_key else {}
        auth = (self.username, self.password) if self.username else None
        return {
            "timeout": SEARCH_TIMEOUT,
            "follow_redirects": True,
            "trust_env": False,
            "headers": headers,
            "auth": auth,
        }

    def health(self) -> dict:
        if not self.configured:
            return {"configured": False, "available": False, "error": "not_configured"}
        try:
            with self._client_factory(**self._client_kwargs()) as client:
                response = client.get(f"{self.url}/_cluster/health")
                response.raise_for_status()
                payload = response.json() if response.content else {}
            self.last_error = ""
            return {"configured": True, "available": True, "status": payload.get("status", "unknown")}
        except Exception as exc:
            self.last_error = str(exc)
            return {"configured": True, "available": False, "error": self.last_error}

    def _ensure_index(self, client) -> None:
        response = client.head(f"{self.url}/{self.index_name}")
        if response.status_code == 404:
            created = client.put(
                f"{self.url}/{self.index_name}",
                json=self._mapping(),
            )
            created.raise_for_status()

    def _mapping(self) -> dict:
        replicas = max(0, int(os.getenv("PAPER_SEARCH_ES_REPLICAS", "0")))
        return {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": replicas,
            },
            "mappings": {
                "properties": {
                    "title": {"type": "text"},
                    "abstract": {"type": "text"},
                    "keywords": {"type": "keyword"},
                    "keyword_strategy": {"type": "keyword"},
                    "keyword_status": {"type": "keyword"},
                    "keyword_model": {"type": "keyword"},
                    "keyword_prompt_version": {"type": "keyword"},
                    "keyword_fallback_reason": {"type": "keyword"},
                    "scope_tier": {"type": "keyword"},
                    "track": {"type": "keyword"},
                    "venue_id": {"type": "keyword"},
                    "indexed_at": {"type": "date"},
                }
            }
        }

    def rebuild(self, papers: list[dict]) -> int:
        """Delete and recreate the index, then Bulk-write the complete corpus."""
        if not self.configured:
            raise RuntimeError("Elasticsearch is not configured")
        with self._client_factory(**self._client_kwargs()) as client:
            existing = client.head(f"{self.url}/{self.index_name}")
            if existing.status_code not in {200, 404}:
                existing.raise_for_status()
            if existing.status_code == 200:
                deleted = client.delete(f"{self.url}/{self.index_name}")
                deleted.raise_for_status()
            created = client.put(f"{self.url}/{self.index_name}", json=self._mapping())
            created.raise_for_status()
        return self.index_many(papers)

    def index_many(self, papers: list[dict]) -> int:
        if not papers or not self.configured:
            return 0
        lines: list[str] = []
        for paper in papers:
            paper_id = str(paper.get("id") or "")
            lines.append(json.dumps({"index": {"_index": self.index_name, "_id": paper_id}}))
            lines.append(json.dumps({**paper, "indexed_at": utc_now_iso()}, ensure_ascii=False))
        with self._client_factory(**self._client_kwargs()) as client:
            self._ensure_index(client)
            response = client.post(
                f"{self.url}/_bulk?refresh=true",
                content=("\n".join(lines) + "\n").encode("utf-8"),
                headers={"Content-Type": "application/x-ndjson"},
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("errors"):
                raise RuntimeError("Elasticsearch bulk indexing reported item errors")
        return len(papers)

    def search(self, query: str, *, limit: int = 20) -> list[tuple[dict, float]]:
        with self._client_factory(**self._client_kwargs()) as client:
            response = client.post(
                f"{self.url}/{self.index_name}/_search",
                json={
                    "size": limit,
                    "query": {
                        "multi_match": {
                            "query": query,
                            "fields": ["title^4", "abstract", "keywords^2"],
                        }
                    },
                },
            )
            response.raise_for_status()
            hits = (response.json().get("hits") or {}).get("hits") or []
        return [(dict(hit.get("_source") or {}), float(hit.get("_score") or 0)) for hit in hits]


class GoogleScholarAdapter:
    """Configured Google Scholar API adapter; deliberately avoids HTML scraping."""

    def __init__(
        self,
        endpoint: str | None = None,
        api_key: str | None = None,
        client_factory=None,
        proxy_url: str | None = None,
        require_proxy: bool | None = None,
    ):
        self.endpoint = (endpoint or os.getenv("GOOGLE_SCHOLAR_API_URL", "")).strip()
        self.api_key = (api_key or os.getenv("SERPAPI_API_KEY", "")).strip()
        self._client_factory = client_factory or httpx.Client
        self.proxy_url = (
            str(proxy_url).strip()
            if proxy_url is not None
            else os.getenv("PAPER_SEARCH_PROXY_URL", "").strip()
        )
        self.require_proxy = _academic_proxy_required(require_proxy)

    @property
    def configured(self) -> bool:
        return bool(self.endpoint or self.api_key)

    def _request(self, client, query: str, limit: int):
        if self.endpoint:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            return client.get(self.endpoint, params={"q": query, "num": limit}, headers=headers)
        return client.get(
            "https://serpapi.com/search.json",
            params={"engine": "google_scholar", "q": query, "num": limit, "api_key": self.api_key},
        )

    @staticmethod
    def _normalize(item: dict) -> dict | None:
        title = str(item.get("title") or "").strip()
        link = str(item.get("link") or item.get("url") or "").strip()
        if not title or not link:
            return None
        publication = item.get("publication_info") or {}
        summary = str(publication.get("summary") or item.get("publication") or "")
        author_text = str(item.get("authors") or summary.split(" - ", 1)[0] or "")
        authors = [value.strip() for value in re.split(r",|;|\band\b", author_text) if value.strip()][:20]
        year_match = re.search(r"\b(19|20)\d{2}\b", summary)
        resources = item.get("resources") or []
        pdf_url = ""
        for resource in resources:
            if str(resource.get("file_format") or "").upper() == "PDF" or str(resource.get("link") or "").lower().endswith(".pdf"):
                pdf_url = str(resource.get("link") or "")
                break
        doi = normalize_doi(item.get("doi"), link, summary)
        return {
            "id": f"scholar-{_stable_paper_id(doi, title)}",
            "title": title,
            "abstract": str(item.get("snippet") or item.get("abstract") or "").strip(),
            "authors": authors,
            "categories": [],
            "comment": summary,
            "journal_ref": summary,
            "doi": doi,
            "year": int(year_match.group(0)) if year_match else None,
            "published_at": "",
            "source_url": link,
            "pdf_url": pdf_url,
            "source": "google_scholar",
            "cited_by": ((item.get("inline_links") or {}).get("cited_by") or {}).get("total"),
        }

    def search(self, query: str, limit: int) -> tuple[list[dict], dict]:
        if not self.configured:
            return [], {"configured": False, "available": False, "reason": "not_configured"}
        try:
            with self._client_factory(
                **public_academic_client_kwargs(
                    self.proxy_url,
                    require_proxy=self.require_proxy,
                )
            ) as client:
                response = self._request(client, query, limit)
                response.raise_for_status()
                payload = response.json()
            raw_results = payload.get("organic_results") or payload.get("results") or payload.get("data") or []
            papers = [paper for item in raw_results if (paper := self._normalize(item))]
            return papers, {
                "configured": True,
                "available": True,
                "provider": "configured_endpoint" if self.endpoint else "serpapi_google_scholar",
                "result_count": len(papers),
            }
        except AcademicProxyRequiredError:
            return [], {
                "configured": True,
                "available": False,
                "reason": "proxy_required",
            }
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            logger.warning(f"Google Scholar 检索返回 HTTP {status_code}")
            return [], {
                "configured": True,
                "available": False,
                "reason": "rate_limited" if status_code == 429 else "http_error",
                "http_status": status_code,
            }
        except Exception as exc:
            logger.warning(f"Google Scholar 检索失败: {exc}")
            return [], {"configured": True, "available": False, "error": str(exc)}


def _abstract_from_inverted_index(value: object) -> str:
    """Reconstruct OpenAlex's lossless abstract representation."""
    if not isinstance(value, dict):
        return ""
    positioned: list[tuple[int, str]] = []
    for word, positions in value.items():
        if not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int):
                positioned.append((position, str(word)))
    return " ".join(word for _, word in sorted(positioned))


class CrossrefAdapter:
    """No-key Crossref REST adapter used as the primary metadata source."""

    def __init__(
        self,
        client_factory=None,
        proxy_url: str | None = None,
        require_proxy: bool | None = None,
        endpoint: str | None = None,
    ):
        self._client_factory = client_factory or httpx.Client
        self.proxy_url = (
            str(proxy_url).strip()
            if proxy_url is not None
            else os.getenv("PAPER_SEARCH_PROXY_URL", "").strip()
        )
        self.require_proxy = _academic_proxy_required(require_proxy)
        self.endpoint = (
            endpoint or os.getenv("CROSSREF_API_URL", CROSSREF_API)
        ).strip().rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self.endpoint)

    @staticmethod
    def _date_parts(item: dict) -> tuple[int | None, str]:
        for field in ("published-print", "published-online", "published", "issued", "created"):
            value = item.get(field) or {}
            parts = value.get("date-parts") or []
            if not parts or not parts[0]:
                continue
            values = [int(value) for value in parts[0][:3]]
            year = values[0]
            published = "-".join(
                [str(year), *[f"{value:02d}" for value in values[1:]]]
            )
            return year, published
        return None, ""

    @staticmethod
    def _normalize(item: dict) -> dict | None:
        raw_title = item.get("title") or []
        title = str(raw_title[0] if isinstance(raw_title, list) and raw_title else raw_title).strip()
        doi = normalize_doi(item.get("DOI"), item.get("URL"))
        if not title or not doi:
            return None
        authors = []
        for author in item.get("author") or []:
            name = " ".join(
                value for value in (
                    str(author.get("given") or "").strip(),
                    str(author.get("family") or "").strip(),
                ) if value
            )
            if name:
                authors.append(name)
        containers = item.get("container-title") or []
        journal_ref = str(
            containers[0] if isinstance(containers, list) and containers else containers
        ).strip()
        abstract = unescape(
            re.sub(r"<[^>]+>", " ", str(item.get("abstract") or ""))
        )
        abstract = re.sub(r"\s+", " ", abstract).strip()
        year, published_at = CrossrefAdapter._date_parts(item)
        pdf_url = ""
        for link in item.get("link") or []:
            if str(link.get("content-type") or "").lower() == "application/pdf":
                pdf_url = str(link.get("URL") or "").strip()
                break
        return {
            "id": f"crossref-{_stable_paper_id(doi)}",
            "title": title,
            "abstract": abstract,
            "authors": authors[:50],
            "categories": [str(value).strip() for value in item.get("subject") or [] if str(value).strip()][:10],
            "comment": str(item.get("type") or "").strip(),
            "journal_ref": journal_ref,
            "doi": doi,
            "year": year,
            "published_at": published_at,
            "source_url": f"https://doi.org/{doi}",
            "pdf_url": pdf_url,
            "metadata_url": str(item.get("URL") or f"https://api.crossref.org/works/{doi}").strip(),
            "source": "crossref",
            "cited_by": item.get("is-referenced-by-count"),
        }

    def search(self, queries: list[str], limit: int) -> tuple[list[dict], dict]:
        normalized_queries = list(
            dict.fromkeys(str(query or "").strip() for query in queries if str(query or "").strip())
        )[:3]
        if not normalized_queries:
            return [], {"configured": True, "available": True, "result_count": 0, "query_count": 0}
        papers_by_id: dict[str, dict] = {}
        try:
            per_query = max(1, min(20, math.ceil(limit / len(normalized_queries))))
            with self._client_factory(
                **public_academic_client_kwargs(
                    self.proxy_url,
                    require_proxy=self.require_proxy,
                )
            ) as client:
                for query_index, query in enumerate(normalized_queries):
                    params = {
                        "query.bibliographic": query,
                        "rows": per_query,
                        "select": (
                            "DOI,title,author,abstract,published-print,published-online,published,"
                            "issued,created,container-title,URL,type,is-referenced-by-count,resource,link,subject"
                        ),
                    }
                    mailto = os.getenv("CROSSREF_MAILTO", "").strip()
                    if mailto:
                        params["mailto"] = mailto
                    response = client.get(
                        self.endpoint,
                        params=params,
                        headers={"User-Agent": "FastRead/1.0 (mailto: metadata-discovery)"},
                    )
                    response.raise_for_status()
                    payload = response.json()
                    raw_items = ((payload.get("message") or {}).get("items") or [])
                    for rank, item in enumerate(raw_items, start=1):
                        paper = self._normalize(item)
                        if not paper:
                            continue
                        existing = papers_by_id.get(paper["id"])
                        rank_score = 1.0 / (60.0 + rank)
                        if existing:
                            existing["provider_relevance"] = round(
                                float(existing.get("provider_relevance") or 0) + rank_score,
                                8,
                            )
                            existing["provider_query_indexes"] = list(
                                dict.fromkeys([*(existing.get("provider_query_indexes") or []), query_index])
                            )
                            existing["provider_query_hits"] = len(existing["provider_query_indexes"])
                            existing.setdefault("provider_query_ranks", {})[str(query_index)] = rank
                        else:
                            paper["provider_relevance"] = round(rank_score, 8)
                            paper["provider_query_indexes"] = [query_index]
                            paper["provider_query_hits"] = 1
                            paper["provider_query_ranks"] = {str(query_index): rank}
                            papers_by_id[paper["id"]] = paper
            papers = list(papers_by_id.values())
            return papers, {
                "configured": True,
                "available": True,
                "provider": "crossref_rest_api",
                "result_count": len(papers),
                "query_count": len(normalized_queries),
            }
        except AcademicProxyRequiredError:
            return [], {
                "configured": True,
                "available": False,
                "reason": "proxy_required",
                "query_count": len(normalized_queries),
            }
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            return [], {
                "configured": True,
                "available": False,
                "reason": "rate_limited" if status_code == 429 else "http_error",
                "http_status": status_code,
                "query_count": len(normalized_queries),
            }
        except Exception as exc:
            logger.warning(f"Crossref 检索失败: {exc}")
            return [], {
                "configured": True,
                "available": False,
                "error": str(exc),
                "query_count": len(normalized_queries),
            }


class OpenAlexAdapter:
    """No-key public scholarly metadata adapter.

    OpenAlex results are discovery metadata, not imported or verified full text.
    Up to three source-grounded semantic queries may be supplied; the adapter
    merges them by stable OpenAlex work id before returning.
    """

    def __init__(
        self,
        client_factory=None,
        proxy_url: str | None = None,
        require_proxy: bool | None = None,
        endpoint: str | None = None,
        arxiv_only: bool = False,
    ):
        self._client_factory = client_factory or httpx.Client
        self.proxy_url = (
            str(proxy_url).strip()
            if proxy_url is not None
            else os.getenv("PAPER_SEARCH_PROXY_URL", "").strip()
        )
        self.require_proxy = _academic_proxy_required(require_proxy)
        self.endpoint = (
            endpoint or os.getenv("OPENALEX_API_URL", OPENALEX_API)
        ).strip().rstrip("/")
        self.arxiv_only = arxiv_only

    @property
    def configured(self) -> bool:
        return True

    @staticmethod
    def _normalize(item: dict) -> dict | None:
        title = str(item.get("display_name") or item.get("title") or "").strip()
        openalex_url = str(item.get("id") or "").strip()
        if not title or not openalex_url:
            return None
        openalex_id = openalex_url.rstrip("/").rsplit("/", 1)[-1]
        doi = normalize_doi(item.get("doi"))
        primary_location = item.get("primary_location") or {}
        best_oa_location = item.get("best_oa_location") or {}
        location = primary_location or best_oa_location
        source = location.get("source") or {}
        landing_page_url = str(location.get("landing_page_url") or "").strip().replace(
            "http://", "https://"
        )
        pdf_url = str(
            best_oa_location.get("pdf_url")
            or primary_location.get("pdf_url")
            or ""
        ).strip().replace("http://", "https://")
        arxiv_match = re.search(
            r"(?:arxiv(?:\.org/(?:abs|pdf)/|[.:]))([\w./-]+)",
            " ".join([doi, landing_page_url, pdf_url]),
            re.IGNORECASE,
        )
        arxiv_id = arxiv_match.group(1).removesuffix(".pdf") if arxiv_match else ""
        source_url = (
            f"https://doi.org/{doi}"
            if doi
            else landing_page_url
            or openalex_url
        )
        venue_name = str(source.get("display_name") or source.get("host_organization_name") or "").strip()
        authors = [
            str((authorship.get("author") or {}).get("display_name") or "").strip()
            for authorship in item.get("authorships") or []
            if str((authorship.get("author") or {}).get("display_name") or "").strip()
        ][:50]
        topics = item.get("topics") or []
        categories = [
            str(topic.get("display_name") or "").strip()
            for topic in topics[:10]
            if str(topic.get("display_name") or "").strip()
        ]
        return {
            "id": f"openalex-{openalex_id}",
            "title": title,
            "abstract": _abstract_from_inverted_index(item.get("abstract_inverted_index")),
            "authors": authors,
            "categories": categories,
            "comment": str(item.get("type_crossref") or item.get("type") or "").strip(),
            "journal_ref": venue_name,
            "doi": doi,
            "year": item.get("publication_year"),
            "published_at": str(item.get("publication_date") or ""),
            "source_url": source_url,
            "pdf_url": pdf_url,
            "metadata_url": openalex_url,
            "arxiv_id": arxiv_id,
            "source": "openalex",
            "cited_by": item.get("cited_by_count"),
        }

    def search(self, queries: list[str], limit: int) -> tuple[list[dict], dict]:
        normalized_queries = list(dict.fromkeys(str(query or "").strip() for query in queries if str(query or "").strip()))[:3]
        if not normalized_queries:
            return [], {"configured": True, "available": True, "result_count": 0, "query_count": 0}
        papers_by_id: dict[str, dict] = {}
        try:
            per_query = max(1, min(20, math.ceil(limit / len(normalized_queries))))
            with self._client_factory(
                **public_academic_client_kwargs(
                    self.proxy_url,
                    require_proxy=self.require_proxy,
                )
            ) as client:
                for query_index, query in enumerate(normalized_queries):
                    params = {
                            "search": query,
                            "per-page": per_query,
                            "select": (
                                "id,doi,title,display_name,publication_year,publication_date,"
                                "authorships,primary_location,best_oa_location,abstract_inverted_index,"
                                "cited_by_count,type,type_crossref,topics"
                            ),
                        }
                    if self.arxiv_only:
                        params["filter"] = f"locations.source.id:{OPENALEX_ARXIV_SOURCE_ID}"
                    response = client.get(
                        self.endpoint,
                        params=params,
                        headers={"User-Agent": "FastRead/1.0 (metadata discovery)"},
                    )
                    response.raise_for_status()
                    payload = response.json()
                    for rank, item in enumerate(payload.get("results") or [], start=1):
                        paper = self._normalize(item)
                        if paper:
                            existing = papers_by_id.get(paper["id"])
                            rank_score = 1.0 / (60.0 + rank)
                            if existing:
                                existing["provider_relevance"] = round(
                                    float(existing.get("provider_relevance") or 0) + rank_score,
                                    8,
                                )
                                existing["provider_query_indexes"] = list(
                                    dict.fromkeys(
                                        [*(existing.get("provider_query_indexes") or []), query_index]
                                    )
                                )
                                existing["provider_query_hits"] = len(existing["provider_query_indexes"])
                                existing.setdefault("provider_query_ranks", {})[str(query_index)] = rank
                            else:
                                paper["provider_relevance"] = round(rank_score, 8)
                                paper["provider_query_indexes"] = [query_index]
                                paper["provider_query_hits"] = 1
                                paper["provider_query_ranks"] = {str(query_index): rank}
                                papers_by_id[paper["id"]] = paper
            papers = list(papers_by_id.values())
            return papers, {
                "configured": True,
                "available": True,
                "provider": "openalex_public_api",
                "result_count": len(papers),
                "query_count": len(normalized_queries),
            }
        except AcademicProxyRequiredError:
            return [], {
                "configured": True,
                "available": False,
                "reason": "proxy_required",
                "query_count": len(normalized_queries),
            }
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            return [], {
                "configured": True,
                "available": False,
                "reason": "rate_limited" if status_code == 429 else "http_error",
                "http_status": status_code,
                "query_count": len(normalized_queries),
            }
        except Exception as exc:
            logger.warning(f"OpenAlex 检索失败: {exc}")
            return [], {
                "configured": True,
                "available": False,
                "error": str(exc),
                "query_count": len(normalized_queries),
            }


class SemanticScholarAdapter:
    """No-key Semantic Scholar Graph API metadata adapter."""

    def __init__(
        self,
        client_factory=None,
        proxy_url: str | None = None,
        require_proxy: bool | None = None,
    ):
        self._client_factory = client_factory or httpx.Client
        self.proxy_url = (
            str(proxy_url).strip()
            if proxy_url is not None
            else os.getenv("PAPER_SEARCH_PROXY_URL", "").strip()
        )
        self.require_proxy = _academic_proxy_required(require_proxy)

    @property
    def configured(self) -> bool:
        return True

    @staticmethod
    def _normalize(item: dict) -> dict | None:
        title = str(item.get("title") or "").strip()
        paper_id = str(item.get("paperId") or "").strip()
        if not title or not paper_id:
            return None
        external_ids = item.get("externalIds") or {}
        doi = normalize_doi(external_ids.get("DOI"))
        arxiv_id = str(external_ids.get("ArXiv") or "").strip()
        open_pdf = item.get("openAccessPdf") or {}
        metadata_url = str(item.get("url") or f"https://www.semanticscholar.org/paper/{paper_id}").strip()
        source_url = f"https://doi.org/{doi}" if doi else metadata_url
        publication_venue = item.get("publicationVenue") or {}
        venue = str(publication_venue.get("name") or item.get("venue") or "").strip()
        return {
            "id": f"semantic-scholar-{paper_id}",
            "title": title,
            "abstract": str(item.get("abstract") or "").strip(),
            "authors": [
                str(author.get("name") or "").strip()
                for author in item.get("authors") or []
                if str(author.get("name") or "").strip()
            ][:50],
            "categories": [],
            "comment": str(publication_venue.get("type") or "").strip(),
            "journal_ref": venue,
            "doi": doi,
            "year": item.get("year"),
            "published_at": str(item.get("publicationDate") or ""),
            "source_url": source_url,
            "pdf_url": str(open_pdf.get("url") or "").strip(),
            "metadata_url": metadata_url,
            "arxiv_id": arxiv_id,
            "source": "semantic_scholar",
            "cited_by": item.get("citationCount"),
        }

    def search(self, queries: list[str], limit: int) -> tuple[list[dict], dict]:
        normalized_queries = list(dict.fromkeys(str(query or "").strip() for query in queries if str(query or "").strip()))[:3]
        if not normalized_queries:
            return [], {"configured": True, "available": True, "result_count": 0, "query_count": 0}
        papers_by_id: dict[str, dict] = {}
        try:
            per_query = max(1, min(20, math.ceil(limit / len(normalized_queries))))
            with self._client_factory(
                **public_academic_client_kwargs(
                    self.proxy_url,
                    require_proxy=self.require_proxy,
                )
            ) as client:
                for query_index, query in enumerate(normalized_queries):
                    response = client.get(
                        SEMANTIC_SCHOLAR_API,
                        params={
                            "query": query,
                            "limit": per_query,
                            "fields": (
                                "paperId,title,abstract,year,authors,venue,publicationVenue,"
                                "externalIds,url,openAccessPdf,citationCount,publicationDate"
                            ),
                        },
                        headers={"User-Agent": "FastRead/1.0 (metadata discovery)"},
                    )
                    response.raise_for_status()
                    payload = response.json()
                    for rank, item in enumerate(payload.get("data") or [], start=1):
                        paper = self._normalize(item)
                        if paper:
                            existing = papers_by_id.get(paper["id"])
                            rank_score = 1.0 / (60.0 + rank)
                            if existing:
                                existing["provider_relevance"] = round(
                                    float(existing.get("provider_relevance") or 0) + rank_score,
                                    8,
                                )
                                existing["provider_query_indexes"] = list(
                                    dict.fromkeys(
                                        [*(existing.get("provider_query_indexes") or []), query_index]
                                    )
                                )
                                existing["provider_query_hits"] = len(existing["provider_query_indexes"])
                                existing.setdefault("provider_query_ranks", {})[str(query_index)] = rank
                            else:
                                paper["provider_relevance"] = round(rank_score, 8)
                                paper["provider_query_indexes"] = [query_index]
                                paper["provider_query_hits"] = 1
                                paper["provider_query_ranks"] = {str(query_index): rank}
                                papers_by_id[paper["id"]] = paper
            papers = list(papers_by_id.values())
            return papers, {
                "configured": True,
                "available": True,
                "provider": "semantic_scholar_graph_api",
                "result_count": len(papers),
                "query_count": len(normalized_queries),
            }
        except AcademicProxyRequiredError:
            return [], {
                "configured": True,
                "available": False,
                "reason": "proxy_required",
                "query_count": len(normalized_queries),
            }
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            return [], {
                "configured": True,
                "available": False,
                "reason": "rate_limited" if status_code == 429 else "http_error",
                "http_status": status_code,
                "query_count": len(normalized_queries),
            }
        except Exception as exc:
            logger.warning(f"Semantic Scholar 检索失败: {exc}")
            return [], {
                "configured": True,
                "available": False,
                "error": str(exc),
                "query_count": len(normalized_queries),
            }


def _arxiv_query(query: str, tracks: tuple[str, ...], limit: int) -> str:
    categories = tuple(dict.fromkeys(category for track in tracks for category in TRACK_CATEGORIES.get(track, ())))
    if not categories:
        categories = tuple(category for values in TRACK_CATEGORIES.values() for category in values)
    cleaned = re.sub(r"[^\w\s+.#-]", " ", str(query or "")).strip()
    # Require the first two code-ranked terms and treat the remainder as recall
    # expansion. Pure OR retrieval lets one generic token fill all 100 slots.
    values = cleaned.split()[:8]
    required = " AND ".join(f"all:{term}" for term in values[:1])
    optional = " OR ".join(f"all:{term}" for term in values[1:])
    terms = required + (f" AND ({optional})" if optional else "") if required else ""
    category_clause = " OR ".join(f"cat:{category}" for category in categories)
    search_query = f"({category_clause})" + (f" AND ({terms})" if terms else "")
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

        source_url = text("a:id")
        title = text("a:title")
        if not title:
            continue
        arxiv_id = source_url.rsplit("/", 1)[-1]
        comment = text("arxiv:comment")
        journal_ref = text("arxiv:journal_ref")
        published = text("a:published")
        year_match = re.search(r"\b(19|20)\d{2}\b", f"{published} {journal_ref} {comment}")
        pdf_url = ""
        for link in entry.findall("a:link", ARXIV_NS):
            if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
                pdf_url = link.attrib.get("href", "")
                break
        papers.append(
            {
                "id": f"arxiv-{arxiv_id}",
                "title": title,
                "abstract": text("a:summary"),
                "authors": [
                    re.sub(r"\s+", " ", (node.text or "").strip())
                    for node in entry.findall("a:author/a:name", ARXIV_NS)
                    if (node.text or "").strip()
                ],
                "categories": [
                    node.attrib.get("term", "")
                    for node in entry.findall("a:category", ARXIV_NS)
                    if node.attrib.get("term")
                ],
                "comment": comment,
                "journal_ref": journal_ref,
                "doi": normalize_doi(text("arxiv:doi"), journal_ref, comment),
                "year": int(year_match.group(0)) if year_match else None,
                "published_at": published,
                "source_url": source_url.replace("http://", "https://"),
                "pdf_url": (pdf_url.replace("http://", "https://") if pdf_url else _canonical_arxiv_pdf(arxiv_id)),
                "source": "arxiv",
            }
        )
    return papers


class PaperSearchService:
    def __init__(
        self,
        index: InvertedIndex | None = None,
        client_factory=None,
        scholar: GoogleScholarAdapter | None = None,
        crossref: CrossrefAdapter | None = None,
        openalex: OpenAlexAdapter | None = None,
        semantic_scholar: SemanticScholarAdapter | None = None,
        elasticsearch: ElasticsearchIndex | None = None,
        keyword_enricher: HttpKeywordEnricher | None = None,
        proxy_url: str | None = None,
        require_proxy: bool | None = None,
        connection_config_factory=None,
    ):
        self.index = index or InvertedIndex()
        self._client_factory = client_factory or httpx.Client
        self.proxy_url = (
            str(proxy_url).strip()
            if proxy_url is not None
            else os.getenv("PAPER_SEARCH_PROXY_URL", "").strip()
        )
        self.require_proxy = _academic_proxy_required(require_proxy)
        self.scholar = scholar or GoogleScholarAdapter(
            client_factory=self._client_factory,
            proxy_url=self.proxy_url,
            require_proxy=self.require_proxy,
        )
        self.crossref = crossref or CrossrefAdapter(
            client_factory=self._client_factory,
            proxy_url=self.proxy_url,
            require_proxy=self.require_proxy,
        )
        self.openalex = openalex or OpenAlexAdapter(
            client_factory=self._client_factory,
            proxy_url=self.proxy_url,
            require_proxy=self.require_proxy,
            arxiv_only=True,
        )
        self.semantic_scholar = semantic_scholar or SemanticScholarAdapter(
            client_factory=self._client_factory,
            proxy_url=self.proxy_url,
            require_proxy=self.require_proxy,
        )
        self.elasticsearch = elasticsearch or ElasticsearchIndex(
            url="" if index is not None else None,
            client_factory=self._client_factory,
        )
        self.keyword_enricher = keyword_enricher or HttpKeywordEnricher(client_factory=self._client_factory)
        self._connection_config_factory = connection_config_factory or get_search_connection_config
        # An explicit constructor proxy is a programmatic/test override. Normal
        # application services are constructed without it and refresh the saved
        # Settings value before every search, so no backend restart is needed.
        self._dynamic_connection_config = connection_config_factory is not None or (
            proxy_url is None and index is None and elasticsearch is None
        )

    def _refresh_connection_config(self) -> None:
        if not self._dynamic_connection_config:
            return
        config = self._connection_config_factory()
        self.proxy_url = str(config.paper_search_proxy_url or "").strip()
        for adapter in (self.scholar, self.crossref, self.openalex, self.semantic_scholar):
            adapter.proxy_url = self.proxy_url
            adapter.require_proxy = self.require_proxy
        self.scholar.endpoint = str(config.google_scholar_api_url or "").strip()
        self.scholar.api_key = str(config.serpapi_api_key or "").strip()
        self.elasticsearch.url = str(config.elasticsearch_url or "").strip().rstrip("/")

    def _fetch_arxiv(self, query: str, tracks: tuple[str, ...], limit: int) -> tuple[list[dict], dict]:
        url = _arxiv_query(query, tracks, limit)
        try:
            with self._client_factory(
                **public_academic_client_kwargs(
                    self.proxy_url,
                    require_proxy=self.require_proxy,
                )
            ) as client:
                response = client.get(
                    url,
                    headers={"User-Agent": "FastRead/1.0 (academic metadata discovery)"},
                )
                response.raise_for_status()
                papers = _parse_arxiv_feed(response.text)
            return papers, {"configured": True, "available": True, "result_count": len(papers)}
        except AcademicProxyRequiredError:
            return [], {
                "configured": True,
                "available": False,
                "reason": "proxy_required",
            }
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            logger.warning(f"arXiv 检索返回 HTTP {status_code}")
            return [], {
                "configured": True,
                "available": False,
                "reason": "rate_limited" if status_code == 429 else "http_error",
                "http_status": status_code,
            }
        except Exception as exc:
            logger.warning(f"arXiv 检索失败: {exc}")
            return [], {"configured": True, "available": False, "error": str(exc)}

    def _enrich(self, paper: dict, retrieved_at: str) -> dict:
        enriched = dict(paper)
        venue = match_allowed_venue(paper.get("journal_ref"), paper.get("comment"), paper.get("venue"))
        categories = set(paper.get("categories") or [])
        inferred_track = next(
            (
                track
                for track, track_categories in TRACK_CATEGORIES.items()
                if categories.intersection(track_categories)
            ),
            "",
        )
        deterministic = extract_keywords(paper.get("title", ""), paper.get("abstract", ""))
        # Online search must remain deterministic and model-free. Optional AI
        # enrichment belongs to offline indexing, not the click-to-search path.
        keywords = deterministic[:16]
        scope_tier = (
            "core"
            if venue.get("id")
            else "arxiv"
            if paper.get("source") == "arxiv" or paper.get("arxiv_id")
            else "local"
            if paper.get("source") == "paper_bibliography"
            else "scholar"
        )
        source = str(paper.get("source") or "")
        enriched.update(
            {
                "venue": venue,
                "venue_confirmed": bool(venue.get("id")),
                "track": venue.get("track") or inferred_track,
                "scope_tier": scope_tier,
                "scope_label": ({
                    "core": "核心顶会",
                    "arxiv": "arXiv 扩展",
                    "local": "当前论文引文",
                }.get(scope_tier) or {
                    "openalex": "OpenAlex 开放元数据",
                    "crossref": "Crossref DOI 元数据",
                    "semantic_scholar": "Semantic Scholar 开放元数据",
                    "google_scholar": "Google Scholar 补充",
                }.get(source, "开放学术元数据")),
                "keywords": keywords,
                "keyword_strategy": "deterministic",
                "keyword_error": "",
                "evidence_status": "discovery_metadata",
                "full_text_verified": False,
                "provenance": paper.get("provenance") or {
                    "provider": paper.get("source") or "unknown",
                    "retrieved_at": retrieved_at,
                    "metadata_only": True,
                    "note": "检索元数据仅用于发现；导入并解析全文后才能作为可引用证据。",
                },
            }
        )
        return enriched

    @staticmethod
    def _dedupe(papers: list[dict]) -> list[dict]:
        merged: dict[str, dict] = {}
        aliases: dict[str, str] = {}
        for paper in papers:
            identity_keys = canonical_identity_keys(paper)
            if paper.get("source") == "arxiv" and paper.get("id"):
                identity_keys.add(f"arxiv-provider:{str(paper['id']).casefold()}")
            if not identity_keys:
                continue
            key = next((aliases[item] for item in sorted(identity_keys) if item in aliases), sorted(identity_keys)[0])
            paper = dict(paper)
            provider = str((paper.get("provenance") or {}).get("provider") or paper.get("source") or "unknown")
            links = [
                {"kind": kind, "url": url, "provider": provider}
                for kind, url in (
                    ("landing", str(paper.get("source_url") or "")),
                    ("metadata", str(paper.get("metadata_url") or "")),
                    ("pdf", str(paper.get("pdf_url") or "")),
                )
                if url
            ]
            paper["discovery_sources"] = list(dict.fromkeys([provider, *(paper.get("discovery_sources") or [])]))
            paper["source_links"] = links
            current = merged.get(key)
            if not current:
                merged[key] = paper
                for identity in identity_keys:
                    aliases[identity] = key
                continue
            prefer_new = bool(paper.get("venue_confirmed")) and not bool(current.get("venue_confirmed"))
            primary, secondary = (paper, current) if prefer_new else (current, paper)
            all_links: list[dict] = []
            seen_links: set[str] = set()
            for link in [*(primary.get("source_links") or []), *(secondary.get("source_links") or [])]:
                url = str(link.get("url") or "")
                if url and url not in seen_links:
                    all_links.append(link)
                    seen_links.add(url)
            merged_doi = primary.get("doi") or secondary.get("doi") or ""
            merged[key] = {
                **secondary,
                **primary,
                "pdf_url": primary.get("pdf_url") or secondary.get("pdf_url") or "",
                "source_url": (
                    f"https://doi.org/{merged_doi}"
                    if merged_doi
                    else primary.get("source_url") or secondary.get("source_url") or ""
                ),
                "doi": merged_doi,
                "discovery_sources": list(
                    dict.fromkeys(
                        [
                            *(primary.get("discovery_sources") or []),
                            *(secondary.get("discovery_sources") or []),
                        ]
                    )
                ),
                "source_links": all_links,
            }
            for identity in identity_keys | canonical_identity_keys(merged[key]):
                aliases[identity] = key
        return list(merged.values())

    @staticmethod
    def _is_stale(last_indexed_at: str) -> bool:
        if not last_indexed_at:
            return True
        try:
            indexed = datetime.fromisoformat(last_indexed_at.replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - indexed.astimezone(timezone.utc)).total_seconds() / 3600
            return age_hours > INDEX_STALE_HOURS
        except ValueError:
            return True

    def search(
        self,
        *,
        query: str,
        semantic_queries: tuple[str, ...] = (),
        tracks: tuple[str, ...] = ("security", "systems", "ai"),
        venue_ids: tuple[str, ...] = (),
        limit: int = 20,
        include_unconfirmed: bool = True,
        refresh: bool = True,
        include_arxiv: bool = False,
        include_scholar: bool = False,
        include_crossref: bool = True,
        include_openalex: bool = True,
        include_semantic_scholar: bool = False,
        prioritize_arxiv: bool = False,
        local_candidates: list[dict] | None = None,
    ) -> dict:
        self._refresh_connection_config()
        retrieved_at = utc_now_iso()
        public_queries = list(
            dict.fromkeys(
                value
                for value in (str(item or "").strip() for item in semantic_queries)
                if value
            )
        )[:3]
        if not public_queries and str(query or "").strip():
            public_queries = [str(query).strip()]
        provider_status: dict[str, dict] = {
            "arxiv": {"configured": True, "available": False, "reason": "refresh_disabled"},
            "crossref": {
                "configured": self.crossref.configured,
                "available": False,
                "reason": "disabled" if not include_crossref else "refresh_disabled",
            },
            "openalex": {
                "configured": True,
                "available": False,
                "reason": "disabled" if not include_openalex else "refresh_disabled",
            },
            "semantic_scholar": {
                "configured": True,
                "available": False,
                "reason": "disabled" if not include_semantic_scholar else "refresh_disabled",
            },
            "google_scholar": {
                "configured": self.scholar.configured,
                "available": False,
                "reason": "disabled" if not include_scholar else "refresh_disabled",
            },
        }
        provider_status["google_scholar"]["manual_search_url"] = (
            "https://scholar.google.com/scholar?" + urlencode({"q": query})
        )
        local_candidates = local_candidates or []
        local_enriched = [self._enrich(paper, retrieved_at) for paper in local_candidates]
        if local_enriched:
            self.index.index_many(local_enriched)
        provider_status["paper_bibliography"] = {
            "configured": True,
            "available": bool(local_enriched),
            "result_count": len(local_enriched),
            "reason": "source_related_work" if local_enriched else "no_related_work_citations",
            "status": "extracted" if local_enriched else "no_matches",
        }
        fetched: list[dict] = []
        if not include_arxiv:
            provider_status["arxiv"] = {"configured": True, "available": False, "reason": "disabled"}
        if refresh:
            jobs: dict[str, object] = {}
            executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="paper-search")
            try:
                if include_arxiv:
                    jobs["arxiv"] = executor.submit(self._fetch_arxiv, query, tracks, FETCH_LIMIT)
                if include_crossref:
                    jobs["crossref"] = executor.submit(
                        self.crossref.search,
                        public_queries,
                        FETCH_LIMIT,
                    )
                if include_openalex:
                    jobs["openalex"] = executor.submit(
                        self.openalex.search,
                        public_queries,
                        FETCH_LIMIT,
                    )
                if include_semantic_scholar:
                    jobs["semantic_scholar"] = executor.submit(
                        self.semantic_scholar.search,
                        public_queries,
                        min(FETCH_LIMIT, 100),
                    )
                if include_scholar:
                    jobs["google_scholar"] = executor.submit(
                        self.scholar.search, query, min(FETCH_LIMIT, 50)
                    )
                done, pending = wait(set(jobs.values()), timeout=SEARCH_DEADLINE)
                for provider, future in jobs.items():
                    if future in done:
                        try:
                            papers, status = future.result()
                            fetched.extend(papers)
                            provider_status[provider] = status
                        except Exception as exc:
                            provider_status[provider] = {
                                "configured": True,
                                "available": False,
                                "error": str(exc),
                            }
                    else:
                        future.cancel()
                        provider_status[provider] = {
                            "configured": True,
                            "available": False,
                            "reason": "deadline_exceeded",
                        }
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
            provider_status["google_scholar"]["manual_search_url"] = (
                "https://scholar.google.com/scholar?" + urlencode({"q": query})
            )

        enriched = self._dedupe([self._enrich(paper, retrieved_at) for paper in fetched])
        local_by_title = {
            re.sub(r"\W+", "", str(paper.get("title") or "").lower()): paper
            for paper in local_enriched
            if str(paper.get("title") or "").strip()
        }
        resolved_local_titles: set[str] = set()
        for paper in enriched:
            for query_index in paper.get("provider_query_indexes") or []:
                if not isinstance(query_index, int) or query_index >= len(public_queries):
                    continue
                if int((paper.get("provider_query_ranks") or {}).get(str(query_index)) or 0) != 1:
                    continue
                query_key = re.sub(r"\W+", "", public_queries[query_index].lower())
                local_match = local_by_title.get(query_key)
                if not local_match:
                    continue
                local_year = local_match.get("year")
                provider_year = paper.get("year")
                if local_year and provider_year and int(local_year) != int(provider_year):
                    continue
                local_author_terms = {
                    token
                    for author in local_match.get("authors") or []
                    for token in _tokenize(str(author))
                }
                provider_author_terms = {
                    token
                    for author in paper.get("authors") or []
                    for token in _tokenize(str(author))
                }
                if local_author_terms and not local_author_terms.intersection(provider_author_terms):
                    continue
                resolved_local_titles.add(query_key)
                local_provenance = local_match.get("provenance") or {}
                paper["discovery_sources"] = list(
                    dict.fromkeys([*(paper.get("discovery_sources") or []), "paper_bibliography"])
                )
                paper["provenance"] = {
                    **(paper.get("provenance") or {}),
                    "source_page": local_provenance.get("source_page"),
                    "exact_quote": local_provenance.get("exact_quote") or "",
                    "citation_anchor": local_provenance,
                    "resolution": "public_metadata_matched_page_citation_title",
                }
        if enriched:
            self.index.index_many(enriched)

        es_health = self.elasticsearch.health()
        active_backend = "local_inverted_index"
        backend_error = ""
        ranked: list[tuple[dict, float]] = []
        elasticsearch_query_succeeded = False
        if es_health.get("available"):
            try:
                if enriched:
                    self.elasticsearch.index_many(enriched)
                ranked = self.elasticsearch.search(query, limit=max(limit * 8, 80))
                active_backend = "elasticsearch"
                elasticsearch_query_succeeded = True
            except Exception as exc:
                backend_error = str(exc)
                logger.warning(f"Elasticsearch 检索失败，回退本地倒排索引: {exc}")
        if not ranked and not elasticsearch_query_succeeded:
            ranked = [
                (self.index.documents[paper_id], score)
                for paper_id, score in self.index.search(query, limit=max(limit * 8, 80))
                if paper_id in self.index.documents
            ]
            active_backend = "local_inverted_index"

        # Page-grounded bibliography leads belong to this request and may not be
        # present in the persistent Elasticsearch corpus.  Merge them into the
        # common ranking explicitly so the active backend cannot make local
        # provenance disappear.  The caller's normal relevance filters still
        # decide whether a lead is useful.
        ranked_identity_keys = set().union(
            *(canonical_identity_keys(paper) for paper, _score in ranked)
        ) if ranked else set()
        query_terms = set(_tokenize(query))
        for paper in local_enriched:
            identity_keys = canonical_identity_keys(paper)
            if identity_keys and ranked_identity_keys.intersection(identity_keys):
                continue
            metadata_terms = set(
                _tokenize(
                    f"{paper.get('title', '')} {paper.get('abstract', '')} "
                    f"{' '.join(str(value) for value in paper.get('keywords') or [])}"
                )
            )
            ranked.append((paper, float(len(query_terms.intersection(metadata_terms)))))
            ranked_identity_keys.update(identity_keys)

        allowed_tracks = set(tracks)
        allowed_venues = set(venue_ids)
        general_query_terms = set(_tokenize(query)) if not semantic_queries else set()
        required_general_matches = (
            1
            if len(general_query_terms) == 1
            else min(4, max(2, math.ceil(len(general_query_terms) * 0.5)))
            if general_query_terms
            else 0
        )
        # Page-anchored bibliography leads are the strongest discovery provenance
        # available before full-text import, so keep them ahead of broad public
        # metadata expansion while still placing confirmed core records first.
        tier_rank = (
            {"core": 0, "arxiv": 0, "local": 1, "scholar": 2}
            if prioritize_arxiv
            else {"core": 0, "local": 1, "arxiv": 2, "scholar": 3}
        )
        source_rank = {
            "crossref": 0,
            "openalex": 1,
            "paper_bibliography": 2,
            "arxiv": 3,
            "semantic_scholar": 4,
            "google_scholar": 5,
        }
        results: list[dict] = []
        excluded: list[dict] = []
        for paper, score in ranked:
            if paper.get("source") == "paper_bibliography":
                local_title_key = re.sub(r"\W+", "", str(paper.get("title") or "").lower())
                if local_title_key in resolved_local_titles:
                    continue
            venue = paper.get("venue") or {}
            if allowed_venues:
                venue_id = venue.get("id")
                if paper.get("scope_tier") == "core" and venue_id not in allowed_venues:
                    continue
                if paper.get("scope_tier") != "core" and venue_id and venue_id not in allowed_venues:
                    continue
            if paper.get("scope_tier") == "core" and allowed_tracks and venue.get("track") not in allowed_tracks:
                continue
            if paper.get("scope_tier") != "core" and allowed_tracks and paper.get("track") and paper.get("track") not in allowed_tracks:
                continue
            if paper.get("scope_tier") == "arxiv" and not include_arxiv:
                continue
            if paper.get("scope_tier") == "scholar":
                source = paper.get("source")
                if source == "google_scholar" and not include_scholar:
                    continue
                if source == "crossref" and not include_crossref:
                    continue
                if source == "openalex" and not include_openalex:
                    continue
                if source == "semantic_scholar" and not include_semantic_scholar:
                    continue
            if general_query_terms and paper.get("source") != "paper_bibliography":
                title_keyword_terms = set(
                    _tokenize(
                        f"{paper.get('title', '')} {' '.join(str(value) for value in paper.get('keywords') or [])}"
                    )
                )
                all_metadata_terms = title_keyword_terms | set(_tokenize(str(paper.get("abstract") or "")))
                # Public search endpoints often treat a natural-language query as
                # a loose OR.  Require substantial query coverage and at least one
                # title/keyword hit before the record enters the local ranking;
                # this prevents a single word such as "alignment" from pulling in
                # genomics, agriculture, or legal-conversation papers.
                if (
                    not (general_query_terms & title_keyword_terms)
                    or len(general_query_terms & all_metadata_terms) < required_general_matches
                ):
                    continue
            item = {**paper, "relevance": round(float(score), 4)}
            if paper.get("scope_tier") == "core" or include_unconfirmed:
                results.append(item)
            else:
                excluded.append(item)

        results.sort(
            key=lambda paper: (
                tier_rank.get(paper.get("scope_tier"), 9),
                source_rank.get(str(paper.get("source") or ""), 9),
                -paper["relevance"],
                -int(paper.get("cited_by") or 0),
                paper.get("title", ""),
            )
        )
        results = results[:limit]
        scope_counts = {
            tier: sum(1 for paper in results if paper.get("scope_tier") == tier)
            for tier in ("core", "arxiv", "scholar")
        }
        index_stats = self.index.stats()
        for provider_name in ("arxiv", "crossref", "openalex", "semantic_scholar", "google_scholar"):
            provider_status.setdefault(provider_name, {})["via_proxy"] = bool(self.proxy_url)
        venue_catalog = allowed_venue_catalog()
        venue_allowlist = [
            {"id": venue_id, "name": meta["name"], "short_name": meta["short_name"], "track": meta["track"]}
            for venue_id, meta in venue_catalog.items()
            if meta["track"] in allowed_tracks and (not allowed_venues or venue_id in allowed_venues)
        ]
        return {
            "query": query,
            "semantic_queries": public_queries,
            "tracks": list(tracks),
            "results": results,
            "result_count": len(results),
            "scope_counts": scope_counts,
            "core_result_count": scope_counts["core"],
            "venue_unconfirmed_count": sum(
                1 for paper in results if paper.get("scope_tier") != "core"
            ) + len(excluded),
            "venue_unconfirmed": [paper for paper in results if paper.get("scope_tier") != "core"] if include_unconfirmed else [],
            "fetched_this_run": len(fetched),
            "search_backend": active_backend,
            "search_backend_error": backend_error,
            "elasticsearch_available": bool(es_health.get("available")),
            "provider_status": {**provider_status, "elasticsearch": es_health},
            "network_policy": {
                "academic_proxy_required": self.require_proxy,
                "academic_proxy_configured": bool(self.proxy_url),
                "public_direct_allowed": not self.require_proxy,
                "elasticsearch_uses_academic_proxy": False,
            },
            "index_stats": index_stats,
            "index_updated_at": index_stats.get("last_indexed_at") or "",
            "retrieved_at": retrieved_at,
            "index_stale": self._is_stale(index_stats.get("last_indexed_at") or ""),
            "stale_after_hours": INDEX_STALE_HOURS,
            "keyword_extraction": {
                "mode": (self.index.metadata.get("keyword_extraction") or {}).get("mode", "deterministic"),
                "ai_configured": bool((self.index.metadata.get("keyword_extraction") or {}).get("ai_configured")),
                "job_id": (self.index.metadata.get("keyword_extraction") or {}).get("job_id", ""),
                "prompt_version": (self.index.metadata.get("keyword_extraction") or {}).get("prompt_version", ""),
                "strategy_version": (self.index.metadata.get("keyword_extraction") or {}).get("strategy_version", ""),
                "status": (self.index.metadata.get("keyword_extraction") or {}).get("status", "not_run"),
            },
            "venue_allowlist": venue_allowlist,
            "corpus_scope": {
                "tracks": list(tracks),
                "core_venues": venue_allowlist,
                "sources": [
                    "core_venue_records",
                    "arxiv",
                    "crossref",
                    "openalex",
                    "semantic_scholar",
                    "google_scholar",
                    "paper_bibliography",
                ],
                "evidence_boundary": "discovery_metadata_until_full_text_import",
            },
            "coverage_note": (
                "核心层覆盖安全四大、系统顶会及 ICLR、ICML、AAAI、NeurIPS/NIPS、ACL；"
                "Crossref 是 DOI 与期刊论文的主检索源，OpenAlex 专门补充 arXiv 预印本；"
                "直连 arXiv、Semantic Scholar 与 Google Scholar 默认关闭，可按需显式启用。"
                "所有检索卡片均为发现元数据，只有导入并成功解析的全文才能进入证据引用。"
            ),
        }
