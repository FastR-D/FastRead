from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from io import BytesIO
import ipaddress
import json
from pathlib import Path, PurePosixPath
import re
import socket
from urllib.parse import quote, urlparse
import zipfile

import httpx

from app.core.settings import get_settings
from app.db.evidence_dao import EvidenceHubDAO
from app.repositories.paper_artifacts import PaperArtifactRepository
from app.services.evidence_hub_service import EvidenceHubService


FILE_ORDER = ["evidence.md", "citations.json", "references.bib", "user-notes.md", "manifest.json"]
SAFE_PROJECT_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _origin(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("FastWrite 地址必须是无凭据的 http/https origin")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("FastWrite 地址只能配置精确 origin，不能包含路径、查询或片段")
    port = parsed.port
    default_port = 80 if parsed.scheme == "http" else 443
    host = parsed.hostname.lower()
    display_host = f"[{host}]" if ":" in host else host
    return f"{parsed.scheme}://{display_host}" + (f":{port}" if port and port != default_port else "")


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        try:
            addresses = socket.getaddrinfo(host, None)
        except socket.gaierror:
            return False
        return bool(addresses) and all(ipaddress.ip_address(item[4][0]).is_loopback for item in addresses)


class FastWriteClient:
    def __init__(self, base_url: str | None = None, client_factory=httpx.Client):
        settings = get_settings()
        self.base_url = _origin(base_url or settings.fastwrite_base_url)
        parsed = urlparse(self.base_url)
        allowed = {_origin(item) for item in settings.fastwrite_allowed_origins}
        if not _is_loopback_host(parsed.hostname or "") and self.base_url not in allowed:
            raise ValueError("远程 FastWrite origin 未加入 FASTWRITE_ALLOWED_ORIGINS 精确白名单")
        self.timeout = settings.integration_timeout_seconds
        self.client_factory = client_factory

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if not path.startswith("/api/"):
            raise ValueError("FastWrite 请求路径不在允许 API 范围")
        with self.client_factory(timeout=self.timeout, follow_redirects=False) as client:
            response = client.request(method, self.base_url + path, **kwargs)
        if 300 <= response.status_code < 400:
            raise ValueError("FastWrite 返回重定向；为阻断 SSRF 未跟随该跳转")
        return response

    def health(self) -> dict:
        response = self._request("GET", "/api/health")
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {"status": "ok"}

    def projects(self) -> list[dict]:
        response = self._request("GET", "/api/projects")
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            payload = payload.get("projects") or payload.get("data") or []
        if not isinstance(payload, list):
            raise ValueError("FastWrite 项目响应格式异常")
        return [item for item in payload if isinstance(item, dict)]

    def create_file(self, project_id: str, path: str, content: bytes) -> None:
        if not SAFE_PROJECT_ID.fullmatch(project_id):
            raise ValueError("FastWrite project_id 格式无效")
        pure = PurePosixPath(path)
        if pure.is_absolute() or ".." in pure.parts or not str(pure).startswith("references/fastread/"):
            raise ValueError("FastWrite 交接路径越界")
        response = self._request(
            "POST",
            f"/api/projects/{quote(project_id, safe='')}/files",
            json={"path": str(pure), "content": content.decode("utf-8")},
        )
        if response.status_code == 409:
            raise FileExistsError(path)
        response.raise_for_status()


class EvidenceBundleService:
    def __init__(
        self,
        dao: EvidenceHubDAO | None = None,
        artifacts: PaperArtifactRepository | None = None,
        hub: EvidenceHubService | None = None,
        data_dir: Path | None = None,
    ):
        settings = get_settings()
        self.dao = dao or EvidenceHubDAO()
        self.artifacts = artifacts or PaperArtifactRepository()
        self.hub = hub or EvidenceHubService(self.dao, self.artifacts)
        self.root = Path(data_dir or settings.integration_data_dir) / "bundles"

    def _paper_citations(self, task_id: str) -> tuple[dict, list[dict], list[str]]:
        result, paper = self.hub.paper_document(task_id)
        citations = []
        seen = set()
        for annotation in self.dao.list_annotations(task_id):
            key = (annotation["page"], annotation["exact_quote"])
            if key in seen:
                continue
            seen.add(key)
            citations.append({
                "task_id": task_id,
                "page": annotation["page"],
                "exact_quote": annotation["exact_quote"],
                "role": "user_annotation",
                "note": annotation["note"],
                "source_hash": annotation["source_hash"],
            })
        report = ((result.get("insights") or {}).get("reading_report") or {})
        for question in report.get("key_questions") or []:
            for evidence in question.get("evidence") or []:
                page = int(evidence.get("page_start") or 0)
                exact_quote = str(evidence.get("exact_quote") or "")
                key = (page, exact_quote)
                if key in seen or not exact_quote:
                    continue
                try:
                    self.hub.validate_quote(task_id, page, exact_quote)
                except ValueError:
                    continue
                seen.add(key)
                citations.append({
                    "task_id": task_id,
                    "page": page,
                    "exact_quote": exact_quote,
                    "role": "report",
                    "note": "",
                    "source_hash": paper.get("content_hash") or "",
                })
        notes = []
        personal = ((result.get("insights") or {}).get("personal_summary") or {}).get("content")
        if personal:
            notes.append(str(personal))
        notes.extend(item["note"] for item in citations if item.get("note"))
        return paper, citations, notes

    @staticmethod
    def _bib_entry(paper: dict, index: int) -> str:
        authors = paper.get("authors") or []
        surname = re.sub(r"[^A-Za-z0-9]", "", str(authors[0]).split()[-1] if authors else "FastRead") or "FastRead"
        year = paper.get("year") or "nd"
        key = f"{surname}{year}_{index + 1}"
        title = str(paper.get("title") or "Untitled").replace("{", "").replace("}", "")
        author_text = " and ".join(str(item).replace("{", "").replace("}", "") for item in authors) or "Unknown"
        fields = [f"  title = {{{title}}}", f"  author = {{{author_text}}}", f"  year = {{{year}}}"]
        if paper.get("doi"):
            fields.append(f"  doi = {{{paper['doi']}}}")
        url = paper.get("resolved_source_url") or paper.get("source_url") or paper.get("pdf_url")
        if url:
            fields.append(f"  url = {{{url}}}")
        return f"@article{{{key},\n" + ",\n".join(fields) + "\n}"

    def build(self, *, task_id: str | None = None, topic_id: str | None = None, include_user_notes: bool = False) -> dict:
        if bool(task_id) == bool(topic_id):
            raise ValueError("必须且只能选择一篇论文或一个专题")
        papers = []
        citations = []
        notes = []
        title = "FastRead Evidence Bundle"
        synthesis = None
        selector = {"task_id": task_id or "", "topic_id": topic_id or ""}
        if task_id:
            paper, paper_citations, paper_notes = self._paper_citations(task_id)
            papers.append(paper)
            citations.extend(paper_citations)
            notes.extend(paper_notes)
            title = paper.get("title") or title
        else:
            topic = self.hub.get_topic(topic_id or "")
            self.hub.refresh_topic_evidence(topic_id or "")
            topic = self.hub.get_topic(topic_id or "")
            title = topic["question"]
            for link in topic["papers"]:
                try:
                    paper, _, paper_notes = self._paper_citations(link["task_id"])
                except ValueError:
                    continue
                papers.append(paper)
                notes.extend(paper_notes)
            for item in topic["evidence_items"]:
                citations.append({
                    "task_id": item["task_id"],
                    "page": item["page"],
                    "exact_quote": item["exact_quote"],
                    "role": item["role"],
                    "note": item["user_note"],
                    "source_hash": next((p.get("content_hash") for p in papers if p.get("id") == item["task_id"]), ""),
                })
            syntheses = self.hub.list_syntheses(topic_id or "")
            synthesis = syntheses[0] if syntheses else self.hub.create_synthesis(topic_id or "", {})
            if include_user_notes:
                notes.extend(topic.get("user_hypotheses") or [])
        canonical = {
            "selector": selector,
            "papers": [{key: paper.get(key) for key in ("id", "title", "authors", "year", "doi", "content_hash")} for paper in papers],
            "citations": citations,
            "include_user_notes": include_user_notes,
            "notes": notes if include_user_notes else [],
            "synthesis": synthesis,
        }
        bundle_id = hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]
        bundle_dir = self.root / bundle_id
        manifest_path = bundle_dir / "manifest.json"
        if manifest_path.is_file():
            return self._load_bundle(bundle_id)
        if bundle_dir.exists() and any(bundle_dir.iterdir()):
            raise ValueError("本地证据包目录不完整且非空；为避免覆盖已停止生成")
        bundle_dir.mkdir(parents=True, exist_ok=True)
        evidence_lines = [f"# {title}", "", "FastRead 证据包。上游元数据仅是发现线索；引用均来自 FastRead 已锁定原文。", ""]
        if synthesis:
            evidence_lines.extend(["## 专题综合", "", str(synthesis.get("question") or title), ""])
            for section, label in (("common_reports", "多篇论文共同报告"), ("differences", "差异"), ("conflicts", "冲突")):
                evidence_lines.extend([f"### {label}", ""])
                entries = synthesis.get(section) or []
                evidence_lines.extend([f"- {entry.get('statement') or ''}" for entry in entries] or ["- 暂无充分证据。"])
                evidence_lines.append("")
        evidence_lines.extend(["## 逐字证据", ""])
        for citation in citations:
            evidence_lines.append(f"- `{citation['task_id']}` p.{citation['page']}: “{citation['exact_quote']}”")
        if not citations:
            evidence_lines.append("- 暂无逐字页码证据；保留空缺，不自动补写。")
        evidence_md = "\n".join(evidence_lines).rstrip() + "\n"
        citations_payload = {
            "version": 1,
            "bundle_id": bundle_id,
            "selector": selector,
            "citations": citations,
            "papers": canonical["papers"],
        }
        references = "\n\n".join(self._bib_entry(paper, index) for index, paper in enumerate(papers)) + ("\n" if papers else "")
        contents: dict[str, bytes] = {
            "evidence.md": evidence_md.encode("utf-8"),
            "citations.json": _json_bytes(citations_payload),
            "references.bib": references.encode("utf-8"),
        }
        if include_user_notes:
            contents["user-notes.md"] = ("# User notes\n\n" + "\n\n".join(f"- {note}" for note in notes) + "\n").encode("utf-8")
        manifest = {
            "version": 1,
            "bundle_id": bundle_id,
            "created_at": _now(),
            "selector": selector,
            "immutable": True,
            "files": [
                {"name": name, "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
                for name, content in contents.items()
            ],
        }
        contents["manifest.json"] = _json_bytes(manifest)
        try:
            for name in FILE_ORDER:
                if name not in contents:
                    continue
                path = bundle_dir / name
                with path.open("xb") as handle:
                    handle.write(contents[name])
        except Exception:
            # Never overwrite partially written paths. The caller receives an explicit
            # incomplete-directory error on the next attempt.
            raise
        return self._load_bundle(bundle_id)

    def _load_bundle(self, bundle_id: str) -> dict:
        if not re.fullmatch(r"[0-9a-f]{24}", bundle_id):
            raise ValueError("bundle_id 格式无效")
        directory = self.root / bundle_id
        manifest_path = directory / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError("证据包尚未完成")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        names = [item["name"] for item in manifest.get("files") or []] + ["manifest.json"]
        contents = {name: (directory / name).read_bytes() for name in names if (directory / name).is_file()}
        return {"bundle_id": bundle_id, "directory": str(directory), "manifest": manifest, "contents": contents}

    def zip_bytes(self, bundle_id: str) -> bytes:
        bundle = self._load_bundle(bundle_id)
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in FILE_ORDER:
                if name in bundle["contents"]:
                    archive.writestr(f"references/fastread/{bundle_id}/{name}", bundle["contents"][name])
        return buffer.getvalue()


class FastWriteHandoffService:
    def __init__(
        self,
        dao: EvidenceHubDAO | None = None,
        bundles: EvidenceBundleService | None = None,
        client: FastWriteClient | None = None,
    ):
        self.dao = dao or EvidenceHubDAO()
        self.bundles = bundles or EvidenceBundleService(self.dao)
        self._client = client

    def client(self) -> FastWriteClient:
        if self._client is None:
            self._client = FastWriteClient()
        return self._client

    def status(self) -> dict:
        settings = get_settings()
        if not settings.fastwrite_enabled:
            return {"enabled": False, "available": False, "origin": settings.fastwrite_base_url, "message": "FastWrite 集成已关闭"}
        try:
            health = self.client().health()
            return {"enabled": True, "available": True, "origin": self.client().base_url, "health": health}
        except Exception as exc:
            return {"enabled": True, "available": False, "origin": settings.fastwrite_base_url, "message": str(exc)}

    def projects(self) -> list[dict]:
        if not get_settings().fastwrite_enabled:
            raise ValueError("FastWrite 集成已关闭")
        return self.client().projects()

    def create(self, payload: dict) -> dict:
        project_id = str(payload.get("project_id") or "")
        if not SAFE_PROJECT_ID.fullmatch(project_id):
            raise ValueError("请选择有效 FastWrite 项目")
        bundle = self.bundles.build(
            task_id=payload.get("task_id") or None,
            topic_id=payload.get("topic_id") or None,
            include_user_notes=bool(payload.get("include_user_notes")),
        )
        existing = self.dao.get_handoff_by_bundle_project(bundle["bundle_id"], project_id)
        if existing:
            return existing
        target_path = f"references/fastread/{bundle['bundle_id']}"
        receipt = self.dao.create_handoff({
            "bundle_id": bundle["bundle_id"],
            "project_id": project_id,
            "status": "pending",
            "target_path": target_path,
            "files_json": json.dumps(list(bundle["contents"]), ensure_ascii=False),
            "successful_files_json": "[]",
            "error": "",
            "manifest_hash": hashlib.sha256(bundle["contents"]["manifest.json"]).hexdigest(),
        })
        return self._send(receipt)

    def retry(self, handoff_id: str) -> dict:
        receipt = self.dao.get_handoff(handoff_id)
        if not receipt:
            raise LookupError("交接记录不存在")
        if receipt["status"] == "completed":
            return receipt
        return self._send(receipt)

    def _send(self, receipt: dict) -> dict:
        bundle = self.bundles._load_bundle(receipt["bundle_id"])
        successful = list(receipt.get("successful_files") or [])
        try:
            projects = self.projects()
            project_ids = {str(item.get("id") or item.get("projectId") or "") for item in projects}
            if receipt["project_id"] not in project_ids:
                raise ValueError("FastWrite 项目不存在")
            for name in FILE_ORDER:
                if name not in bundle["contents"] or name in successful:
                    continue
                path = f"{receipt['target_path']}/{name}"
                self.client().create_file(receipt["project_id"], path, bundle["contents"][name])
                successful.append(name)
                self.dao.update_handoff(
                    receipt["id"], status="writing", successful_files=successful, error=""
                )
            return self.dao.update_handoff(
                receipt["id"], status="completed", successful_files=successful, error=""
            )
        except FileExistsError as exc:
            return self.dao.update_handoff(
                receipt["id"], status="conflict", successful_files=successful,
                error=f"目标文件已存在，FastRead 未覆盖：{exc}",
            )
        except Exception as exc:
            return self.dao.update_handoff(
                receipt["id"], status="failed", successful_files=successful, error=str(exc)
            )

    def download(self, handoff_id: str) -> tuple[str, bytes]:
        receipt = self.dao.get_handoff(handoff_id)
        if not receipt:
            raise LookupError("交接记录不存在")
        return receipt["bundle_id"], self.bundles.zip_bytes(receipt["bundle_id"])
