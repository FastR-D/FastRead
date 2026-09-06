from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, FastAPI, File, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.gzip import GZipMiddleware
from starlette.staticfiles import StaticFiles

from .auth import Principal, login, require_owner, require_user, secure_cookie, token_hash
from .evidence import EvidenceRepository
from .store import Store, encode, uid

User = Annotated[Principal, Depends(require_user)]


class LoginInput(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class ImportInput(BaseModel):
    url: str = Field(min_length=8, max_length=2048)

    @field_validator("url")
    @classmethod
    def valid_url(cls, value):
        parsed = urlparse(value)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("需要公开论文的 HTTP/HTTPS 地址")
        return value


class SearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    limit: int = Field(default=20, ge=1, le=50)


class ModelInput(BaseModel):
    provider_id: str = Field(max_length=100)
    model: str = Field(default="qwen3.8-27b", min_length=1, max_length=100)


class MessageInput(ModelInput):
    content: str = Field(min_length=1, max_length=10000)


class SummaryInput(BaseModel):
    content: str = Field(max_length=10000)


class ProviderInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    base_url: str = Field(max_length=2048)
    api_key: str = Field(min_length=1, max_length=4096)
    models: list[str] = Field(min_length=1, max_length=30)

    @field_validator("base_url")
    @classmethod
    def valid_base_url(cls, value):
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("供应商地址必须是 HTTPS API 地址")
        return value.rstrip("/")

    @field_validator("models")
    @classmethod
    def valid_models(cls, values):
        if any(not value.strip() or len(value) > 100 for value in values):
            raise ValueError("模型 ID 无效")
        return list(dict.fromkeys(values))


def job_view(job):
    return {k: job[k] for k in ("id", "kind", "resource_id", "version_id", "state", "attempts", "error_code", "error", "created", "updated")} | {
        "result": json.loads(job["result"]) if job.get("result") else None}


def create_web_app(root=None, frontend=None):
    store = Store(root)
    store.initialize()
    app = FastAPI(title="FastRead Web", version="3.0.0")
    app.state.store = store
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    @app.middleware("http")
    async def browser_boundary(request, call_next):
        origin = request.headers.get("origin")
        allowed = os.environ.get("FASTREAD_PUBLIC_ORIGIN", "").rstrip("/")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
            expected = allowed or str(request.base_url).rstrip("/")
            if origin.rstrip("/") != expected:
                return JSONResponse({"detail": "不允许跨站请求"}, status_code=403)
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        return response

    @app.exception_handler(LookupError)
    async def missing(_request, _exc):
        return JSONResponse({"detail": "记录不存在"}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(_request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=429 if str(exc) in {"daily_model_limit", "workspace_queue_full"} else 409)

    @app.get("/api/health")
    def health():
        store.one("SELECT version FROM schema_versions LIMIT 1")
        return {"status": "healthy", "schema": 1}

    @app.post("/api/auth/login")
    def sign_in(data: LoginInput, request: Request, response: Response):
        token, csrf = login(store, data.email, data.password, request.client.host if request.client else "unknown")
        response.set_cookie("fastread_session", token, httponly=True, secure=secure_cookie(), samesite="lax", max_age=7 * 86400, path="/")
        return {"csrf": csrf}

    @app.get("/api/auth/me")
    def me(user: User):
        workspace = store.one("SELECT name,daily_limit FROM workspaces WHERE id=?", (user.workspace_id,))
        return {"email": user.email, "workspace_id": user.workspace_id, "role": user.role, "csrf": user.csrf, "workspace": workspace}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response, user: User):
        with store.connect(write=True) as db:
            db.execute("DELETE FROM sessions WHERE token=?", (token_hash(request.cookies.get("fastread_session", "")),))
        response.delete_cookie("fastread_session", path="/")
        return {"ok": True}

    api = APIRouter(prefix="/api", dependencies=[Depends(require_user)])

    def paper(user, paper_id):
        row = store.paper(user.workspace_id, paper_id)
        if not row:
            raise LookupError("paper_not_found")
        return row

    def model(user, data):
        row = store.one("SELECT id,models FROM providers WHERE id=? AND workspace_id=?", (data.provider_id, user.workspace_id))
        if not row or data.model not in json.loads(row["models"]):
            raise HTTPException(400, "请先配置工作区供应商与模型")

    def enqueue(user, kind, payload, key, **kwargs):
        if not key or len(key) > 160:
            raise HTTPException(400, "需要有效 Idempotency-Key")
        return job_view(store.enqueue(user.workspace_id, user.user_id, kind, payload, key, **kwargs))

    @api.get("/papers")
    def papers(user: User, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), q: str = Query("", max_length=300), archived: bool = False):
        args = (user.workspace_id, f"%{q}%", int(archived))
        rows = store.all("SELECT id,title,active_version,created,metadata FROM papers WHERE workspace_id=? AND title LIKE ? AND archived=? ORDER BY created DESC,id LIMIT ? OFFSET ?", (*args, limit, offset))
        for row in rows:
            metadata = json.loads(row.pop("metadata"))
            row.update(authors=metadata.get("authors") or [], year=metadata.get("year"), page_count=metadata.get("page_count") or 0)
        return {"items": rows, "total": store.one("SELECT count(*) AS n FROM papers WHERE workspace_id=? AND title LIKE ? AND archived=?", args)["n"], "limit": limit, "offset": offset}

    @api.delete("/papers/{paper_id}")
    def archive(paper_id: str, user: User):
        paper(user,paper_id)
        with store.connect(write=True) as db:
            if db.execute("SELECT id FROM jobs WHERE (resource_id=? OR resource_id IN (SELECT id FROM conversations WHERE paper_id=?)) AND state IN ('queued','running')", (paper_id,paper_id)).fetchone():
                raise HTTPException(409,"请等待论文任务完成后归档")
            db.execute("UPDATE papers SET archived=1 WHERE id=? AND workspace_id=?", (paper_id,user.workspace_id))
        return {"archived": True}

    @api.post("/papers/{paper_id}/restore")
    def restore(paper_id: str, user: User):
        with store.connect(write=True) as db:
            if not db.execute("UPDATE papers SET archived=0 WHERE id=? AND workspace_id=?", (paper_id,user.workspace_id)).rowcount:
                raise LookupError("paper_not_found")
        return {"archived": False}

    @api.get("/papers/{paper_id}")
    def detail(paper_id: str, user: User):
        row = paper(user, paper_id)
        metadata = json.loads(row.pop("metadata"))
        return row | {"metadata": metadata, "versions": store.all("SELECT v.id,v.created,(SELECT count(*) FROM pages p WHERE p.version_id=v.id) page_count FROM document_versions v WHERE v.paper_id=? ORDER BY v.created DESC", (paper_id,))}

    @api.get("/papers/{paper_id}/pages/{number}")
    def page(paper_id: str, number: int, user: User, version: str | None = None):
        row = paper(user, paper_id)
        version_id = version or row["active_version"]
        result = store.one("SELECT p.number,p.text FROM pages p JOIN document_versions v ON v.id=p.version_id WHERE v.paper_id=? AND v.id=? AND p.number=?", (paper_id, version_id, number))
        if not result:
            raise LookupError("page_not_found")
        return result | {"version_id": version_id}

    @api.get("/papers/{paper_id}/file")
    def pdf(paper_id: str, user: User, version: str | None = None):
        row = paper(user, paper_id)
        data = store.one("SELECT file_path FROM document_versions WHERE id=? AND paper_id=?", (version or row["active_version"], paper_id))
        if not data or not data["file_path"]:
            raise LookupError("file_not_found")
        target = (store.root / data["file_path"]).resolve()
        target.relative_to((store.root / "files").resolve())
        if not target.is_file():
            raise LookupError("file_not_found")
        return FileResponse(target, media_type="application/pdf", content_disposition_type="inline")

    @api.post("/imports/url", status_code=202)
    def import_url(data: ImportInput, user: User, idempotency_key: str = Header()):
        return enqueue(user, "import_url", data.model_dump(), idempotency_key)

    @api.post("/imports/pdf", status_code=202)
    async def import_pdf(user: User, file: UploadFile = File(), idempotency_key: str = Header()):
        if not idempotency_key or len(idempotency_key) > 160:
            raise HTTPException(400, "需要有效 Idempotency-Key")
        previous = store.one("SELECT * FROM jobs WHERE workspace_id=? AND dedupe_key=?", (user.workspace_id, idempotency_key))
        if previous:
            if previous["kind"] != "import_pdf":
                raise HTTPException(409, "idempotency_key_conflict")
            return job_view(previous)
        relative = "files/" + uid() + ".pdf"
        path = store.root / relative
        count = 0
        try:
            with path.open("xb") as handle:
                while chunk := await file.read(1024 * 1024):
                    if count == 0 and not chunk.startswith(b"%PDF-"):
                        raise HTTPException(415, "文件不是 PDF")
                    count += len(chunk)
                    if count > 64 * 1024 * 1024:
                        raise HTTPException(413, "PDF 不能超过 64 MB")
                    handle.write(chunk)
            if not count:
                raise HTTPException(400, "PDF 为空")
            return enqueue(user, "import_pdf", {"path": relative, "filename": Path(file.filename or "paper.pdf").name}, idempotency_key)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        finally:
            await file.close()

    @api.post("/search")
    def search(data: SearchInput, user: User):
        from .search import PublicSearch
        return PublicSearch(store).search(data.query, data.limit)

    @api.get("/jobs")
    def jobs(user: User, limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)):
        return {"items": [job_view(row) for row in store.all("SELECT * FROM jobs WHERE workspace_id=? ORDER BY created DESC LIMIT ? OFFSET ?", (user.workspace_id, limit, offset))]}

    @api.get("/jobs/{job_id}")
    def job(job_id: str, user: User):
        row = store.one("SELECT * FROM jobs WHERE id=? AND workspace_id=?", (job_id, user.workspace_id))
        if not row:
            raise LookupError("job_not_found")
        return job_view(row)

    @api.post("/papers/{paper_id}/reports", status_code=202)
    def report(paper_id: str, data: ModelInput, user: User, idempotency_key: str = Header()):
        row = paper(user, paper_id)
        model(user, data)
        return enqueue(user, "report", data.model_dump(), idempotency_key, resource_id=paper_id, version_id=row["active_version"], billable=True)

    @api.get("/papers/{paper_id}/reports")
    def reports(paper_id: str, user: User):
        row = paper(user, paper_id)
        return {"items": store.all("SELECT id,version_id,created FROM report_versions WHERE paper_id=? ORDER BY created DESC", (paper_id,)), "active_version": row["active_version"]}

    @api.get("/papers/{paper_id}/reports/{report_id}")
    def get_report(paper_id: str, report_id: str, user: User):
        row = paper(user, paper_id)
        report = store.one("SELECT * FROM report_versions WHERE id=? AND paper_id=?", (report_id, paper_id))
        if not report:
            raise LookupError("report_not_found")
        report["content"] = json.loads(report["content"])
        return report | {"stale": report["version_id"] != row["active_version"]}

    @api.put("/papers/{paper_id}/summary")
    def summary(paper_id: str, data: SummaryInput, user: User):
        paper(user, paper_id)
        with store.connect(write=True) as db:
            db.execute("UPDATE papers SET summary=? WHERE id=? AND workspace_id=?", (data.content, paper_id, user.workspace_id))
        return {"content": data.content}

    @api.get("/papers/{paper_id}/export")
    def export(paper_id: str, user: User):
        from app.services.reading_report_service import render_reading_report_markdown
        row = paper(user, paper_id)
        payload = EvidenceRepository(store, user.workspace_id, paper_id, row["active_version"]).read_result(paper_id)
        text = render_reading_report_markdown(payload)
        return Response(text, media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="reading-report.md"'})

    @api.get("/papers/{paper_id}/conversations")
    def conversations(paper_id: str, user: User):
        paper(user, paper_id)
        return {"items": store.all("SELECT id,version_id,created FROM conversations WHERE paper_id=? AND workspace_id=? ORDER BY created DESC", (paper_id,user.workspace_id))}

    @api.post("/papers/{paper_id}/conversations", status_code=201)
    def conversation(paper_id: str, user: User):
        row = paper(user, paper_id)
        with store.connect(write=True) as db:
            old = db.execute("SELECT * FROM conversations WHERE paper_id=? AND workspace_id=? AND version_id=? ORDER BY created LIMIT 1", (paper_id, user.workspace_id, row["active_version"])).fetchone()
            if old:
                return dict(old)
            cid = uid()
            db.execute("INSERT INTO conversations VALUES(?,?,?,?,?)", (cid, user.workspace_id, paper_id, row["active_version"], time.time()))
        return {"id": cid, "version_id": row["active_version"]}

    def owned_conversation(cid, user):
        row = store.one("SELECT * FROM conversations WHERE id=? AND workspace_id=?", (cid, user.workspace_id))
        if not row:
            raise LookupError("conversation_not_found")
        return row

    @api.get("/conversations/{cid}/messages")
    def messages(cid: str, user: User, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
        owned_conversation(cid, user)
        rows = store.all("SELECT * FROM messages WHERE conversation_id=? ORDER BY created,id LIMIT ? OFFSET ?", (cid, limit, offset))
        for row in rows:
            row["evidence"] = json.loads(row["evidence"])
        return {"items": rows}

    @api.post("/conversations/{cid}/messages", status_code=202)
    def ask(cid: str, data: MessageInput, user: User, idempotency_key: str = Header()):
        conversation = owned_conversation(cid, user)
        model(user, data)
        if not idempotency_key or len(idempotency_key) > 160:
            raise HTTPException(400, "需要有效 Idempotency-Key")
        with store.connect(write=True) as db:
            existing = db.execute("SELECT id FROM jobs WHERE workspace_id=? AND dedupe_key=?", (user.workspace_id, idempotency_key)).fetchone()
            pending = db.execute("SELECT id FROM jobs WHERE resource_id=? AND kind='chat' AND state IN ('queued','running')", (cid,)).fetchone()
            if pending and not existing:
                raise HTTPException(409, "请等待上一条回答完成")
            job = store.enqueue(user.workspace_id, user.user_id, "chat", data.model_dump(), idempotency_key,
                                resource_id=cid, version_id=conversation["version_id"], billable=True, db=db)
            db.execute("INSERT OR IGNORE INTO messages VALUES(?,?,?,?,?,?,?)", (uid(), cid, "user", data.content, "{}", job["id"], time.time()))
        return job_view(job)

    @api.post("/papers/{paper_id}/index", status_code=202)
    def index(paper_id: str, user: User, idempotency_key: str = Header()):
        row = paper(user, paper_id)
        return enqueue(user, "index", {}, idempotency_key, resource_id=paper_id, version_id=row["active_version"])

    @api.post("/papers/{paper_id}/neighbors", status_code=202)
    def neighbors(paper_id: str, user: User, idempotency_key: str = Header()):
        row = paper(user, paper_id)
        return enqueue(user, "neighbors", {}, idempotency_key, resource_id=paper_id, version_id=row["active_version"])

    @api.get("/providers")
    def providers(user: User):
        rows = store.all("SELECT id,name,base_url,models FROM providers WHERE workspace_id=? ORDER BY created", (user.workspace_id,))
        for row in rows:
            row["models"] = sorted(json.loads(row["models"]), key=lambda m: (m != "qwen3.8-27b", m != "glm-5.2", m))
        return {"items": rows}

    @api.get("/topics")
    def topics(user: User):
        return {"items": store.all("SELECT id,question,scope FROM topics WHERE workspace_id=? ORDER BY created DESC", (user.workspace_id,))}

    @api.get("/topics/{topic_id}")
    def topic(topic_id: str, user: User):
        row = store.one("SELECT * FROM topics WHERE id=? AND workspace_id=?", (topic_id,user.workspace_id))
        if not row:
            raise LookupError("topic_not_found")
        row["evidence"] = store.all("SELECT * FROM topic_evidence WHERE topic_id=? ORDER BY page,id", (topic_id,))
        row["hypotheses"] = json.loads(row["hypotheses"])
        return row

    @api.post("/providers", status_code=201)
    def add_provider(data: ProviderInput, user: User):
        require_owner(user)
        from app.services.paper_fetching import _validate_public_url
        from app.services.secret_store import protect_secret
        _validate_public_url(data.base_url)
        provider_id = uid()
        with store.connect(write=True) as db:
            db.execute("INSERT INTO providers VALUES(?,?,?,?,?,?,?)", (provider_id, user.workspace_id, data.name, data.base_url, protect_secret(data.api_key), encode(data.models), time.time()))
        return {"id": provider_id, "name": data.name}

    app.include_router(api)
    static = Path(frontend or os.environ.get("FASTREAD_WEB_DIST", Path(__file__).resolve().parents[3] / "../fastread-frontend/dist" )).resolve()
    if static.is_dir():
        app.mount("/", StaticFiles(directory=static, html=True), name="web")
    return app
