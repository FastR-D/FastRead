from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import signal
import time
from pathlib import Path

from .evidence import EvidenceRepository
from .store import Store, encode, uid


class MemoryArtifacts:
    def __init__(self):
        self.payload = None

    def write_result(self, _task_id, payload):
        self.payload = payload

    def write_status(self, *_args):
        pass


def model_client(store, job, payload, owner):
    from openai import OpenAI
    from app.services.gpt_provider import ChatModelClient
    from app.services.secret_store import unprotect_secret
    provider = store.one("SELECT * FROM providers WHERE id=? AND workspace_id=?", (payload["provider_id"], job["workspace_id"]))
    if not provider or payload["model"] not in json.loads(provider["models"]):
        raise ValueError("provider_not_available")
    with store.connect(write=True) as db:
        store.assert_lease(db, job, owner)
        db.execute("UPDATE jobs SET dispatch_started=1 WHERE id=?", (job["id"],))
    return ChatModelClient(OpenAI(api_key=unprotect_secret(provider["secret"]), base_url=provider["base_url"],
                                  timeout=240, max_retries=0), payload["model"])


def execute(store, job, owner):
    payload = json.loads(job["payload"])
    kind = job["kind"]
    file_path = None
    result = {}
    if kind in {"import_url", "import_pdf"}:
        from app.services.paper_ingest_service import PaperIngestService
        artifacts = MemoryArtifacts()
        def save_pdf(content):
            nonlocal file_path
            file_path = "files/" + job["id"] + ".pdf"
            temporary = store.root / (file_path + ".tmp")
            temporary.write_bytes(content)
            os.replace(temporary, store.root / file_path)
        service = PaperIngestService(artifacts, persist_legacy_registry=False, pdf_sink=save_pdf,
            metadata_client_factory=(lambda: model_client(store, job, payload, owner)) if payload.get("provider_id") else None)
        if kind == "import_pdf":
            path = (store.root / payload["path"]).resolve()
            path.relative_to((store.root / "files").resolve())
            imported = service.ingest_pdf(content=path.read_bytes(), filename=payload["filename"])
            file_path = payload["path"]
        else:
            imported = service.ingest_url(url=payload["url"])
        document = imported["result"]["paper_document"]
        with store.connect(write=True) as db:
            store.assert_lease(db, job, owner)
            result = store.ingest(job["workspace_id"], document, file_path=file_path, db=db)
            store.enqueue(job["workspace_id"], job["user_id"], "index", {}, "index:"+result["version_id"],
                          resource_id=result["paper_id"], version_id=result["version_id"], db=db)
            complete(db, job, result)
        return
    if kind == "chat":
        conversation = store.one("SELECT * FROM conversations WHERE id=? AND workspace_id=?", (job["resource_id"], job["workspace_id"]))
        if not conversation:
            raise LookupError("conversation_not_found")
        paper_id = conversation["paper_id"]
    else:
        paper_id = job["resource_id"]
    evidence = EvidenceRepository(store, job["workspace_id"], paper_id, job["version_id"])
    source = evidence.read_result(paper_id)
    if kind == "report":
        from app.services.reading_report_service import ReadingReportService
        client = model_client(store, job, payload, owner)
        try:
            result = ReadingReportService(evidence).generate(task_id=paper_id, provider_id=payload["provider_id"],
                         model_name=payload["model"], force=True, model_client=client)
        finally:
            client.client.close()
        for section in ("key_questions", "process", "contributions"):
            for item in result.get(section) or []:
                evidence.bind(item.get("evidence") or [])
        result["document_version_id"] = job["version_id"]
        result["citation_validation"] = "quote_and_page_location"
        result["claim_support_validation"] = "not_independently_verified"
    elif kind == "chat":
        from app.services.chat_service import chat
        history = store.all("SELECT role,content FROM messages WHERE conversation_id=? AND job_id!=? ORDER BY created DESC LIMIT 20", (job["resource_id"], job["id"]))
        client = model_client(store, job, payload, owner)
        try:
            result = chat(paper_id, payload["content"], list(reversed(history)), payload["provider_id"], payload["model"],
                          artifacts=evidence, model_client=client)
        finally:
            client.client.close()
        evidence.bind(result.get("sources") or [])
        result["document_version_id"] = job["version_id"]
    elif kind == "index":
        # The versioned lexical index is reconstructible from authoritative page text.
        from app.services.chat_service import _chunk_page
        chunks = [(page["page"], n, text) for page in source["paper_document"]["pages"] for n, text in enumerate(_chunk_page(page["text"]))]
        result = {"version_id": job["version_id"], "chunks": len(chunks), "engine": "versioned_lexical"}
        from app.services.vector_store import VectorStoreManager, vector_index_capability
        enabled, reason = vector_index_capability()
        if enabled:
            vector_chunks = [{"text": text, "metadata": {"task_id":paper_id,"title":source["paper_document"]["title"],
                "source_type":"paper_page","page_start":page,"page_end":page,"chunk_index":n,
                "document_version_id":job["version_id"],"chunk_id":f"{job['version_id']}:p{page}:c{n}"}} for page,n,text in chunks]
            try:
                result["vector"] = VectorStoreManager().index_task(job["version_id"],paper_result=source,chunks=vector_chunks)
            except Exception as exc:
                result["vector"] = {"status":"failed","reason":type(exc).__name__}
        else:
            result["vector"] = {"status":"disabled","reason":reason}
    elif kind == "neighbors":
        from .search import PublicSearch
        result = PublicSearch(store).search(source["paper_document"]["title"], 20)
        result.update(document_version_id=job["version_id"], evidence_status="discovery_candidates_not_verified_support")
    else:
        raise ValueError("unknown_job_kind")
    with store.connect(write=True) as db:
        store.assert_lease(db, job, owner)
        if kind == "report":
            report_id = uid()
            db.execute("INSERT INTO report_versions VALUES(?,?,?,?,?,?)", (report_id, paper_id, job["version_id"], job["id"], encode(result), time.time()))
            result = {"report_id": report_id, "paper_id": paper_id, "version_id": job["version_id"]}
        elif kind == "chat":
            message_id = uid()
            db.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,?)", (message_id, job["resource_id"], "assistant", result["answer"], encode(result), job["id"], time.time()))
            result = {"message_id": message_id, "conversation_id": job["resource_id"]}
        elif kind == "index":
            db.execute("DELETE FROM evidence_chunks WHERE version_id=?", (job["version_id"],))
            for page, n, text in chunks:
                db.execute("INSERT INTO evidence_chunks VALUES(?,?,?,?,?)", (f"{job['version_id']}:p{page}:c{n}", job["version_id"], page, n, text))
        complete(db, job, result)


def complete(db, job, result):
    db.execute("UPDATE jobs SET state='succeeded',result=?,lease_owner=NULL,lease_until=NULL,error=NULL,error_code=NULL,updated=? WHERE id=?",
               (encode(result), time.time(), job["id"]))


def run_one(root, job, owner):
    store = Store(root)
    try:
        execute(store, job, owner)
    except Exception as exc:
        # Do not persist provider response bodies, URLs with tokens or exception secrets.
        name = type(exc).__name__.lower()
        code = "timeout" if "timeout" in name else "transport" if any(s in name for s in ("connection", "transport")) else "invalid_input" if isinstance(exc, ValueError) else "execution_failed"
        store.fail(job, owner, code, {"timeout": "上游响应超时", "transport": "上游连接中断", "invalid_input": "输入或生成结果未通过校验", "execution_failed": "任务执行失败，请查看服务器诊断"}[code], retryable=code in {"timeout", "transport"})
        print(encode({"job_id": job["id"], "kind": job["kind"], "error_type": type(exc).__name__}), flush=True)


def serve(root=None, concurrency=2):
    store = Store(root)
    store.initialize()
    owner = uid()
    active = {}
    stopping = False

    def stop(*_args):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    context = mp.get_context("spawn")
    while not stopping or active:
        for job_id, (process, job, renewed) in list(active.items()):
            if not process.is_alive():
                process.join()
                if process.exitcode:
                    store.fail(job, owner, "worker_crash", "执行进程中断", retryable=True)
                del active[job_id]
            elif time.time() >= job["deadline"] or stopping:
                process.terminate()
                process.join(timeout=5)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=5)
                store.fail(job, owner, "timeout" if not stopping else "worker_crash", "执行进程已停止", retryable=True)
                del active[job_id]
            elif time.time() - renewed >= 10:
                if not store.heartbeat(job_id, owner):
                    process.terminate()
                active[job_id] = (process, job, time.time())
        if not stopping and len(active) < concurrency:
            job = store.claim(owner, concurrency=concurrency)
            if job:
                process = context.Process(target=run_one, args=(str(store.root), job, owner))
                process.start()
                active[job["id"]] = (process, job, time.time())
                continue
        time.sleep(0.5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    parser.add_argument("--concurrency", type=int, default=2, choices=range(1, 9))
    args = parser.parse_args()
    serve(args.root, args.concurrency)
