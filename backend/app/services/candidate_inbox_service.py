from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from app.core.settings import get_settings
from app.db.evidence_dao import EvidenceHubDAO
from app.repositories.paper_artifacts import PaperArtifactRepository
from app.services.evidence_hub_service import atomic_write_json
from app.services.paper_ingest_service import PaperIngestService
from app.services.paper_task_service import PaperTaskService


TRACKING_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "source"}
ARXIV_RE = re.compile(r"(?:arxiv:|arxiv\.org/(?:abs|pdf)/)?([a-z-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_doi(value: object) -> str:
    raw = str(value or "").strip().lower()
    raw = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", raw)
    raw = re.sub(r"^doi:\s*", "", raw)
    return raw.strip().rstrip(".,;)")


def normalize_arxiv(value: object) -> str:
    match = ARXIV_RE.search(str(value or ""))
    return match.group(1).lower() if match else ""


def normalize_url(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return ""
    query = urlencode([(key, val) for key, val in parse_qsl(parsed.query, keep_blank_values=True) if key.lower() not in TRACKING_KEYS])
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    netloc = parsed.hostname.lower()
    if parsed.port and not ((parsed.scheme == "http" and parsed.port == 80) or (parsed.scheme == "https" and parsed.port == 443)):
        netloc = f"{netloc}:{parsed.port}"
    return urlunparse((parsed.scheme.lower(), netloc, path, "", query, ""))


def _authors(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raw = str(value or "").strip()
    if not raw:
        return []
    return [item.strip() for item in re.split(r"\s+(?:and|&amp;)\s+|\s*;\s*", raw) if item.strip()]


def _year(item: dict) -> int | None:
    raw = item.get("year") or item.get("published") or item.get("published_at") or ""
    match = re.search(r"(?:19|20)\d{2}", str(raw))
    return int(match.group(0)) if match else None


def normalize_candidate(item: dict, *, producer: str, source_commit: str = "", fetched_at: str = "", warnings=None, score=None) -> dict:
    if not isinstance(item, dict):
        raise ValueError("论文候选必须是 JSON 对象")
    title = str(item.get("title") or item.get("name") or "").strip()
    if not title:
        raise ValueError("论文候选缺少标题")
    detail_url = str(item.get("detail_url") or item.get("link") or item.get("url") or item.get("entry_url") or "").strip()
    pdf_url = str(item.get("pdf_url") or item.get("pdf") or item.get("paper_url") or "").strip()
    canonical_url = normalize_url(item.get("canonical_url") or detail_url or pdf_url)
    doi = normalize_doi(item.get("doi") or item.get("DOI"))
    arxiv_id = normalize_arxiv(item.get("arxiv_id") or item.get("arxiv") or detail_url or pdf_url)
    upstream_warnings = warnings if warnings is not None else item.get("warnings") or []
    if isinstance(upstream_warnings, str):
        upstream_warnings = [upstream_warnings]
    match_score = score if score is not None else item.get("match_score", item.get("score"))
    try:
        match_score = float(match_score) if match_score not in (None, "") else None
    except (TypeError, ValueError):
        match_score = None
    normalized = {
        "title": title[:1000],
        "authors": _authors(item.get("authors") or item.get("author")),
        "year": _year(item),
        "venue": str(item.get("venue") or item.get("source") or item.get("conference") or "")[:1000],
        "abstract": str(item.get("abstract") or item.get("description") or item.get("summary") or "")[:100000],
        "doi": doi,
        "doi_norm": doi,
        "arxiv_id": arxiv_id,
        "arxiv_norm": arxiv_id,
        "detail_url": detail_url,
        "canonical_url": canonical_url,
        "canonical_url_norm": canonical_url,
        "pdf_url": pdf_url,
        "pdf_sha256": str(item.get("pdf_sha256") or item.get("content_hash") or "").lower(),
        "producer": producer,
        "upstream_id": str(item.get("upstream_id") or item.get("_id") or item.get("id") or canonical_url or title),
        "source_commit": source_commit or str(item.get("source_commit") or ""),
        "fetched_at": fetched_at or str(item.get("fetched_at") or item.get("retrieved_at") or ""),
        "warnings": [str(value) for value in upstream_warnings if str(value)],
        "categories": [str(value) for value in (
            item.get("categories") if isinstance(item.get("categories"), list)
            else [item.get("category")] if item.get("category")
            else []
        ) if str(value)],
        "match_score": match_score,
        "raw": item,
    }
    return normalized


class FastNewsCatalogService:
    COMMIT_URL = "https://api.github.com/repos/FastR-D/FastNews/commits/main"
    TREE_URL = "https://api.github.com/repos/FastR-D/FastNews/git/trees/{sha}?recursive=1"
    RAW_URL = "https://raw.githubusercontent.com/FastR-D/FastNews/{sha}/{path}"

    def __init__(self, cache_path: Path | None = None, client_factory=httpx.Client):
        settings = get_settings()
        self.cache_path = Path(cache_path or settings.fastnews_cache_path)
        self.client_factory = client_factory
        self.timeout = settings.integration_timeout_seconds

    def _read_cache(self) -> dict | None:
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    def catalog(self, *, force: bool = False) -> dict:
        settings = get_settings()
        if not settings.fastnews_enabled:
            raise ValueError("FastNews 集成已关闭")
        cache = self._read_cache()
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "FastRead-evidence-hub"}
        if cache and cache.get("etag") and not force:
            headers["If-None-Match"] = cache["etag"]
        try:
            with self.client_factory(timeout=self.timeout, follow_redirects=False, headers=headers) as client:
                response = client.get(self.COMMIT_URL)
                if response.status_code == 304 and cache:
                    return {**cache, "stale": False, "cache_hit": True}
                response.raise_for_status()
                commit = response.json().get("sha") or ""
                if not re.fullmatch(r"[0-9a-f]{40}", commit):
                    raise ValueError("FastNews 返回了无效 commit SHA")
                tree_response = client.get(self.TREE_URL.format(sha=commit), headers={"Accept": "application/vnd.github+json"})
                tree_response.raise_for_status()
                paths = sorted(
                    node["path"]
                    for node in tree_response.json().get("tree") or []
                    if re.fullmatch(r"top-conf/data/conferences/[A-Za-z0-9_.-]+\.jsonl", str(node.get("path") or ""))
                )
                entries = []
                for path in paths:
                    raw_response = client.get(self.RAW_URL.format(sha=commit, path=path))
                    raw_response.raise_for_status()
                    if len(raw_response.content) > 8 * 1024 * 1024:
                        continue
                    for line_number, line in enumerate(raw_response.text.splitlines(), 1):
                        if not line.strip():
                            continue
                        try:
                            item = json.loads(line)
                            normalized = normalize_candidate(
                                item, producer="fastnews", source_commit=commit, fetched_at=str(item.get("fetched_at") or "")
                            )
                        except (ValueError, json.JSONDecodeError):
                            continue
                        catalog_id = hashlib.sha256(
                            f"{commit}\0{path}\0{normalized['upstream_id']}".encode("utf-8")
                        ).hexdigest()[:32]
                        entries.append({
                            **normalized,
                            "catalog_id": catalog_id,
                            "source_path": path,
                            "source_line": line_number,
                            "discovery_status": "发现线索",
                        })
                        if len(entries) >= 5000:
                            break
                    if len(entries) >= 5000:
                        break
                payload = {
                    "repository": settings.fastnews_repo,
                    "commit": commit,
                    "etag": response.headers.get("etag") or "",
                    "updated_at": _now(),
                    "entries": entries,
                    "stale": False,
                    "cache_hit": False,
                }
                atomic_write_json(self.cache_path, payload)
                return payload
        except Exception as exc:
            if cache:
                return {**cache, "stale": True, "cache_hit": True, "warning": f"FastNews 网络更新失败：{exc}"}
            raise ValueError(f"FastNews 目录读取失败：{exc}") from exc


class CandidateInboxService:
    def __init__(
        self,
        dao: EvidenceHubDAO | None = None,
        catalog_service: FastNewsCatalogService | None = None,
        papers: PaperIngestService | None = None,
        artifacts: PaperArtifactRepository | None = None,
    ):
        self.dao = dao or EvidenceHubDAO()
        self.catalog_service = catalog_service or FastNewsCatalogService()
        self.artifacts = artifacts or PaperArtifactRepository()
        self.papers = papers or PaperIngestService(self.artifacts)

    @staticmethod
    def _db_payload(normalized: dict) -> dict:
        return {
            "title": normalized["title"],
            "authors_json": json.dumps(normalized["authors"], ensure_ascii=False),
            "year": normalized["year"],
            "venue": normalized["venue"],
            "abstract": normalized["abstract"],
            "doi": normalized["doi"],
            "doi_norm": normalized["doi_norm"],
            "arxiv_id": normalized["arxiv_id"],
            "arxiv_norm": normalized["arxiv_norm"],
            "detail_url": normalized["detail_url"],
            "canonical_url": normalized["canonical_url"],
            "canonical_url_norm": normalized["canonical_url_norm"],
            "pdf_url": normalized["pdf_url"],
            "pdf_sha256": normalized["pdf_sha256"],
            "producer": normalized["producer"],
            "upstream_id": normalized["upstream_id"],
            "source_commit": normalized["source_commit"],
            "fetched_at": normalized["fetched_at"],
            "warnings_json": json.dumps(normalized["warnings"], ensure_ascii=False),
            "match_score": normalized["match_score"],
            "raw_json": json.dumps(normalized["raw"], ensure_ascii=False),
            "import_status": "pending",
        }

    def _store(self, normalized: dict) -> dict:
        duplicate = self.dao.find_candidate_duplicate(normalized)
        if duplicate:
            return {**duplicate, "deduplicated": True}
        return {**self.dao.create_candidate(self._db_payload(normalized)), "deduplicated": False}

    def import_fastnews(self, catalog_ids: list[str]) -> list[dict]:
        catalog = self.catalog_service.catalog()
        by_id = {item["catalog_id"]: item for item in catalog.get("entries") or []}
        if not catalog_ids:
            raise ValueError("请选择至少一个 FastNews 候选")
        results = []
        for catalog_id in catalog_ids[:200]:
            item = by_id.get(catalog_id)
            if not item:
                raise ValueError("FastNews 候选不在已锁定目录中")
            normalized = normalize_candidate(
                item,
                producer="fastnews",
                source_commit=catalog.get("commit") or "",
                fetched_at=item.get("fetched_at") or catalog.get("updated_at") or "",
            )
            results.append(self._store(normalized))
        return results

    def import_fastinsight(self, payload: object) -> list[dict]:
        root = payload
        warnings = []
        if isinstance(root, dict) and isinstance(root.get("result"), dict):
            root = root["result"]
        if isinstance(root, dict) and "best" in root:
            warnings = root.get("warnings") or []
            root = root.get("best")
        items = root if isinstance(root, list) else [root]
        if not items or any(not isinstance(item, dict) for item in items):
            raise ValueError("FastInsight JSON 不包含可识别论文对象")
        return [
            self._store(normalize_candidate(item, producer="fastinsight", warnings=warnings))
            for item in items[:200]
        ]

    def confirm(self, candidate_id: str) -> dict:
        candidate = self.dao.get_candidate(candidate_id)
        if not candidate:
            raise LookupError("候选不存在")
        if candidate.get("task_id"):
            return candidate
        source_url = candidate.get("pdf_url") or candidate.get("detail_url") or candidate.get("canonical_url")
        if not source_url:
            raise ValueError("候选没有可导入的论文 URL")
        created = self.papers.ingest_url(
            url=source_url,
            overrides={
                "title": candidate["title"],
                "authors": candidate["authors"],
                "venue": candidate["venue"],
                "year": candidate["year"],
                "doi": candidate["doi"],
                "producer": candidate["producer"],
                "upstream_id": candidate["upstream_id"],
                "source_commit": candidate["source_commit"],
                "discovery_status": "发现线索",
            },
        )
        task_id = created["task_id"]
        paper = (created.get("result") or {}).get("paper_document") or {}
        content_hash = paper.get("content_hash") or ""
        existing_task = self._find_existing_task_by_hash(content_hash, excluding=task_id)
        if existing_task:
            PaperTaskService(self.artifacts).delete_task(task_id)
            task_id = existing_task
        return self.dao.mark_candidate_imported(candidate_id, task_id, content_hash)

    def _find_existing_task_by_hash(self, content_hash: str, excluding: str) -> str | None:
        if not content_hash:
            return None
        for item in self.artifacts.iter_result_files() or []:
            if item.task_id == excluding:
                continue
            result = self.artifacts.read_result(item.task_id) or {}
            paper = result.get("paper_document") or {}
            if result.get("paper_task") and paper.get("content_hash") == content_hash:
                return item.task_id
        return None
