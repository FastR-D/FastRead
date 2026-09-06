"""Public source adapters; search never writes papers or a private search index."""
from __future__ import annotations

import hashlib
import json
import time
import re
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor, wait

from .store import encode


class PublicSearch:
    def __init__(self, store):
        from app.services.paper_search_service import CrossrefAdapter, OpenAlexAdapter
        self.store = store
        self.adapters = {"crossref": CrossrefAdapter(), "openalex": OpenAlexAdapter()}

    def source(self, name, query, limit):
        key = name + ":" + hashlib.sha256(encode([query, limit]).encode()).hexdigest()
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
        pool = ThreadPoolExecutor(max_workers=2)
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
        if len(query_words) > 2:
            ranked = [paper for paper in ranked if score(paper) >= .5]
        return {"papers": ranked[:limit], "sources": statuses}
