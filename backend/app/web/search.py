"""Public source adapters; search never writes papers or a private search index."""
from __future__ import annotations

import hashlib
import json
import time
import re
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor, wait
from urllib.parse import urlencode

import httpx

from .store import encode


class ArxivSearch:
    """Query the original registry independently of aggregator metadata."""

    def search(self, queries, limit):
        from app.services.arxiv_gateway import route_arxiv_request
        from app.services.paper_search_service import ARXIV_API, _parse_arxiv_feed, public_academic_client_kwargs
        query = re.sub(r'[^\w\s.-]', ' ', queries[0]).strip()
        terms = query.split()[:12]
        if not terms:
            return [], {"available": True, "result_count": 0}
        expression = f'ti:"{query}" OR (' + ' AND '.join(f'all:{term}' for term in terms) + ')'
        url = ARXIV_API + '?' + urlencode({"search_query": expression, "max_results": limit,
                                            "sortBy": "relevance", "sortOrder": "descending"})
        try:
            route = route_arxiv_request(url)
            kwargs = public_academic_client_kwargs(**({"require_proxy": False} if route.via_gateway else {}))
            with httpx.Client(**kwargs) as client:
                response = client.get(route.request_url, headers=route.headers)
                response.raise_for_status()
                import xml.etree.ElementTree as ET
                root = ET.fromstring(response.text)
                if root.tag != '{http://www.w3.org/2005/Atom}feed':
                    raise ValueError('invalid_feed')
                papers = _parse_arxiv_feed(response.text)
            return papers, {"available": True, "result_count": len(papers), "provider": "arxiv"}
        except httpx.HTTPStatusError as exc:
            return [], {"available": False, "reason": "rate_limited" if exc.response.status_code == 429 else "http_error"}
        except Exception:
            return [], {"available": False, "reason": "upstream_error"}


class PublicSearch:
    def __init__(self, store):
        from app.services.paper_search_service import CrossrefAdapter, OpenAlexAdapter
        self.store = store
        self.adapters = {"arxiv": ArxivSearch(), "crossref": CrossrefAdapter(), "openalex": OpenAlexAdapter()}

    def source(self, name, query, limit):
        key = "identity-v2:" + name + ":" + hashlib.sha256(encode([query, limit]).encode()).hexdigest()
        cached = self.store.one("SELECT content FROM provider_cache WHERE key=? AND expires>?", (key, time.time()))
        if cached:
            return json.loads(cached["content"])
        cooldown = self.store.one("SELECT until FROM provider_cooldown WHERE provider=? AND until>?", (name, time.time()))
        if cooldown:
            return [], {"available": False, "reason": "rate_limited", "retry_after": round(cooldown["until"] - time.time())}
        papers, status = self.adapters[name].search([query], limit)
        with self.store.connect(write=True) as db:
            if "rate_limit" in encode(status) or "429" in encode(status):
                db.execute("INSERT OR REPLACE INTO provider_cooldown VALUES(?,?)", (name, time.time() + 120))
            if status.get("available"):
                db.execute("DELETE FROM provider_cache WHERE expires<?", (time.time(),))
                db.execute("INSERT OR REPLACE INTO provider_cache VALUES(?,?,?)", (key, encode([papers, status]), time.time() + 600))
        return papers, status

    def search(self, query, limit=20):
        from app.services.paper_search_service import PaperSearchService
        pool = ThreadPoolExecutor(max_workers=len(self.adapters))
        futures = {name: pool.submit(self.source, name, query, limit) for name in self.adapters}
        done, _ = wait(futures.values(), timeout=22)
        papers, statuses = [], {}
        try:
            for name, future in futures.items():
                if future not in done:
                    future.cancel()
                    statuses[name] = {"available": False, "reason": "deadline_exceeded"}
                    continue
                try:
                    rows, status = future.result()
                    for row in rows:
                        row["discovery_sources"] = list(dict.fromkeys([*(row.get("discovery_sources") or []), name]))
                    papers.extend(rows)
                    statuses[name] = status
                except Exception:
                    statuses[name] = {"available": False, "reason": "upstream_error"}
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        query_words = set(re.findall(r"[a-z0-9]+", query.lower()))
        def score(paper):
            title = str(paper.get("title") or "").lower()
            words = set(re.findall(r"[a-z0-9]+", title))
            overlap = len(words & query_words) / max(1, len(query_words))
            return overlap + SequenceMatcher(None, query.lower(), title).ratio()
        ranked = sorted(PaperSearchService._dedupe(papers), key=score, reverse=True)
        # Preserve separate identities and make same-title ambiguity visible.
        titles = {}
        for paper in ranked:
            title_key = re.sub(r'\W+', '', str(paper.get('title') or '').casefold())
            titles.setdefault(title_key, []).append(paper)
        for group in titles.values():
            if len(group) > 1:
                for paper in group:
                    paper['identity_warning'] = (paper.get('identity_warning') or '') + '检索到同名的不同来源记录，请核对年份、标识符与原文。'
        if len(query_words) > 2:
            ranked = [paper for paper in ranked if score(paper) >= .5]
        return {"papers": ranked[:limit], "sources": statuses}
