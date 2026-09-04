import json
from types import SimpleNamespace

from fastapi import BackgroundTasks

from app.routers import chat as chat_router
from app.repositories.paper_artifacts import PaperArtifactRepository
from app.services import chat_service, vector_store
from app.services.paper_task_service import PaperTaskService
from app.services.vector_store import INDEX_VERSION, VectorStoreManager, _chunk_paper_pages


def _paper_result() -> dict:
    text = "This paper evaluates a security mechanism with a controlled experiment. " * 8
    return {
        "paper_task": True,
        "paper_document": {
            "title": "Example Paper",
            "doi": "10.1000/example",
            "source_url": "https://publisher.example/paper",
            "pages": [{"page": 3, "text": text}],
        },
        "insights": {},
    }


def test_paper_page_vector_chunks_retain_academic_provenance():
    chunks = _chunk_paper_pages(_paper_result())

    assert chunks
    assert all(chunk["metadata"]["source_type"] == "paper_page" for chunk in chunks)
    assert all(chunk["metadata"]["page_start"] == 3 for chunk in chunks)
    assert all(chunk["metadata"]["doi"] == "10.1000/example" for chunk in chunks)
    assert all(chunk["metadata"]["source_url"] == "https://publisher.example/paper" for chunk in chunks)


def test_disabled_vector_index_returns_terminal_status(monkeypatch):
    monkeypatch.setattr(chat_router, "vector_index_capability", lambda: (False, "测试环境未启用"))
    response = chat_router.index_task(
        chat_router.IndexRequest(task_id="11111111-1111-4111-8111-111111111111"),
        BackgroundTasks(),
    )
    payload = json.loads(response.body)

    assert payload["data"]["status"] == "disabled"
    assert payload["data"]["indexed"] is False
    assert payload["data"]["detail"] == "测试环境未启用"


def test_vector_index_auto_mode_follows_dependency_availability(monkeypatch):
    monkeypatch.delenv("CHAT_VECTOR_INDEX_ENABLED", raising=False)
    monkeypatch.setattr(vector_store.importlib.util, "find_spec", lambda _name: object())
    assert vector_store.vector_index_capability() == (True, "")

    monkeypatch.setattr(
        vector_store.importlib.util,
        "find_spec",
        lambda name: object() if name == "chromadb" else None,
    )
    enabled, detail = vector_store.vector_index_capability()
    assert enabled is False
    assert "FastEmbed" in detail


def test_vector_index_requires_chromadb_before_embedding_backend(monkeypatch):
    monkeypatch.delenv("CHAT_VECTOR_INDEX_ENABLED", raising=False)
    monkeypatch.setattr(vector_store.importlib.util, "find_spec", lambda _name: None)

    enabled, detail = vector_store.vector_index_capability()

    assert enabled is False
    assert "ChromaDB" in detail


def test_vector_index_reuses_unchanged_paper(monkeypatch):
    payload = _paper_result()
    payload["paper_document"]["content_hash"] = "paper-content-v1"
    chunks = _chunk_paper_pages(payload)
    collection = SimpleNamespace(
        metadata={
            "content_hash": "paper-content-v1",
            "index_version": INDEX_VERSION,
            "embedding_identity": vector_store.embedding_index_identity(),
        },
        count=lambda: len(chunks),
    )
    manager = object.__new__(VectorStoreManager)
    manager._client = SimpleNamespace(get_collection=lambda _name: collection)
    monkeypatch.setattr(vector_store.ARTIFACTS, "read_result", lambda _task_id: payload)

    result = manager.index_task("paper-task")

    assert result == {"status": "reused", "reason": "unchanged", "chunk_count": len(chunks)}


def test_vector_index_writes_explicit_multilingual_embeddings(monkeypatch):
    payload = _paper_result()
    payload["paper_document"]["content_hash"] = "paper-content-v2"
    chunks = _chunk_paper_pages(payload)
    captured = {}

    class Collection:
        def add(self, **kwargs):
            captured.update(kwargs)

    class Client:
        def get_collection(self, _name):
            raise RuntimeError("missing")

        def delete_collection(self, _name):
            return None

        def create_collection(self, **kwargs):
            captured["collection"] = kwargs
            return Collection()

    manager = object.__new__(VectorStoreManager)
    manager._client = Client()
    monkeypatch.setattr(vector_store.ARTIFACTS, "read_result", lambda _task_id: payload)
    monkeypatch.setattr(
        vector_store,
        "_embed_documents",
        lambda documents, _config: [[1.0] + [0.0] * 383 for _ in documents],
    )

    result = manager.index_task("paper-task")

    assert result["status"] == "indexed"
    assert len(captured["embeddings"]) == len(chunks)
    assert captured["collection"]["metadata"]["embedding_model"] == vector_store.DEFAULT_EMBEDDING_MODEL
    assert captured["collection"]["metadata"]["embedding_revision"] == vector_store.DEFAULT_EMBEDDING_REVISION
    assert captured["collection"]["metadata"]["embedding_dimension"] == 384


def test_vector_query_uses_explicit_multilingual_query_embedding(monkeypatch):
    captured = {}

    class Collection:
        def query(self, **kwargs):
            captured.update(kwargs)
            return {
                "documents": [["English source paragraph"]],
                "metadatas": [[{"page_start": 2}]],
                "distances": [[0.2]],
            }

    manager = object.__new__(VectorStoreManager)
    manager._client = SimpleNamespace(get_collection=lambda _name: Collection())
    monkeypatch.setattr(manager, "is_indexed", lambda _task_id: True)
    monkeypatch.setattr(vector_store, "_embed_query", lambda _query: [1.0] + [0.0] * 383)

    result = manager.query("paper-task", "这个阶段在哪里？")

    assert result[0]["metadata"]["page_start"] == 2
    assert "query_texts" not in captured
    assert len(captured["query_embeddings"][0]) == 384


def test_default_multilingual_embedding_model_is_revision_pinned(monkeypatch):
    monkeypatch.delenv("CHAT_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("CHAT_EMBEDDING_MODEL_REVISION", raising=False)

    config = vector_store.embedding_model_config()

    assert config["model_name"] == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    assert config["revision"] == "faf4aa4225822f3bc6376869cb1164e8e3feedd0"
    assert "fastembed-0.8.0" in vector_store.embedding_index_identity(config)


def test_paper_chat_chunks_are_page_grounded():
    chunks = chat_service._paper_chunks("paper-task", _paper_result())
    source_types = [chunk["metadata"]["source_type"] for chunk in chunks]

    assert source_types
    assert set(source_types) == {"paper_page"}


def test_deleting_paper_artifacts_removes_only_owned_uuid_upload(monkeypatch, tmp_path):
    output_dir = tmp_path / "output"
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()
    filename = "a" * 32 + ".pdf"
    uploaded = uploads_dir / filename
    uploaded.write_bytes(b"pdf")
    unrelated = uploads_dir / "manual.pdf"
    unrelated.write_bytes(b"keep")

    artifacts = PaperArtifactRepository(output_dir)
    artifacts.write_result("paper-task", {
        "paper_task": True,
        "paper_document": {"pdf_url": f"/uploads/{filename}"},
    })
    monkeypatch.setattr(
        "app.services.paper_task_service.get_settings",
        lambda: SimpleNamespace(uploads_path="/uploads", uploads_dir=uploads_dir),
    )
    service = PaperTaskService(artifacts, vector_store_factory=lambda: SimpleNamespace(delete_index=lambda _id: None))

    assert service._delete_owned_upload("paper-task") == 1
    assert not uploaded.exists()
    assert unrelated.exists()


def test_paper_chat_never_exposes_unpaged_video_tools(monkeypatch):
    calls = []

    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="原文证据不足"))])

    fake_gpt = SimpleNamespace(
        model="test-model",
        client=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
    )
    monkeypatch.setattr(chat_service.ARTIFACTS, "read_result", lambda _task_id: _paper_result())
    monkeypatch.setattr(chat_service, "_get_gpt", lambda _provider, _model: fake_gpt)

    result = chat_service.chat("paper-task", "作者证明了什么？", [], "provider", "model")

    assert result["answer"].startswith("原文证据不足：")
    assert result["grounding_status"] == "response_format_invalid"
    assert len(calls) == 1
    assert "tools" not in calls[0]


def test_paper_chat_returns_only_exact_page_citations(monkeypatch):
    class Completions:
        def create(self, **_kwargs):
            content = (
                '{"answer":"论文通过受控实验评估安全机制 [第 3 页]",'
                '"citations":[{"page":3,"exact_quote":'
                '"This paper evaluates a security mechanism with a controlled experiment."}]}'
            )
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    fake_gpt = SimpleNamespace(
        model="test-model",
        client=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
    )
    monkeypatch.setattr(chat_service.ARTIFACTS, "read_result", lambda _task_id: _paper_result())
    monkeypatch.setattr(chat_service, "_get_gpt", lambda _provider, _model: fake_gpt)

    result = chat_service.chat("paper-task", "controlled experiment", [], "provider", "model")

    assert result["grounding_status"] == "source_grounded"
    assert result["sources"][0]["page_start"] == 3
    assert result["sources"][0]["source_type"] == "paper_page"


def test_paper_chat_uses_grounded_report_evidence_for_cross_language_query(monkeypatch):
    target_quote = "The framework evaluates detection, clarification, and interaction use."
    payload = {
        "paper_task": True,
        "paper_document": {
            "id": "paper-task",
            "title": "English Paper",
            "source_url": "https://publisher.example/paper",
            "pages": [
                {"page": 1, "text": "A general introduction without the requested method." * 20},
                {"page": 2, "text": f"Context before. {target_quote} Context after." * 12},
            ],
        },
        "insights": {
            "reading_report": {
                "key_questions": [
                    {
                        "question": "论文把欠规格处理拆成哪三个核心能力？",
                        "answer": "检测、澄清和利用交互信息。",
                        "why_it_matters": "这决定智能体能否处理信息不足。",
                        "evidence": [{"page_start": 2, "page_end": 2, "exact_quote": target_quote}],
                    }
                ]
            }
        },
    }
    calls = []

    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            content = (
                '{"answer":"论文评估检测、澄清和利用交互信息三项能力 [第 2 页]",'
                f'"citations":[{{"page":2,"exact_quote":"{target_quote}"}}]}}'
            )
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    fake_gpt = SimpleNamespace(
        model="test-model",
        client=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
    )
    monkeypatch.setattr(chat_service.ARTIFACTS, "read_result", lambda _task_id: payload)
    monkeypatch.setattr(chat_service, "_get_gpt", lambda _provider, _model: fake_gpt)

    result = chat_service.chat(
        "paper-task",
        "论文把欠规格处理拆成哪三个核心能力？",
        [],
        "provider",
        "model",
    )

    assert result["grounding_status"] == "source_grounded"
    assert result["sources"][0]["page_start"] == 2
    assert target_quote in calls[0]["messages"][0]["content"]


def test_hybrid_retrieval_keeps_grounded_report_page_ahead_of_vector_noise(monkeypatch):
    target_quote = "The disclosure phase sends private data to the attacker endpoint."
    payload = {
        "paper_task": True,
        "paper_document": {
            "id": "paper-task",
            "title": "English Paper",
            "content_hash": "paper-v1",
            "pages": [
                {"page": 1, "text": "General background material. " * 30},
                {"page": 4, "text": f"Context. {target_quote} More details. " * 12},
            ],
        },
        "insights": {
            "reading_report": {
                "key_questions": [{
                    "question": "隐私披露阶段做了什么？",
                    "answer": "将隐私数据发送到攻击者端点。",
                    "why_it_matters": "这是攻击链的最终外泄步骤。",
                    "evidence": [{"page_start": 4, "page_end": 4, "exact_quote": target_quote}],
                }],
            },
        },
    }
    vector_noise = {
        "text": "General background material.",
        "metadata": {"task_id": "paper-task", "source_type": "paper_page", "page_start": 1, "chunk_index": 0},
        "distance": 0.2,
    }
    monkeypatch.setattr(chat_service.ARTIFACTS, "read_result", lambda _task_id: payload)
    monkeypatch.setattr(chat_service, "vector_index_capability", lambda: (True, ""))
    monkeypatch.setattr(chat_service, "VectorStoreManager", lambda: SimpleNamespace(query=lambda *_args, **_kwargs: [vector_noise]))

    _, chunks, diagnostics = chat_service._task_retrieval("paper-task", "隐私披露阶段做了什么？")

    assert diagnostics["strategy"] == "report_hint+vector"
    assert [chunk["metadata"]["page_start"] for chunk in chunks[:2]] == [4, 1]


def test_paper_chat_uses_balanced_pages_when_cross_language_report_hints_are_absent(monkeypatch):
    payload = _paper_result()
    monkeypatch.setattr(chat_service.ARTIFACTS, "read_result", lambda _task_id: payload)

    _, chunks = chat_service._task_chunks("paper-task", "请解释完全不同语言中的问题")

    assert chunks
    assert all(chunk["metadata"]["source_type"] == "paper_page" for chunk in chunks)


def test_paper_chat_rewrites_anaphoric_follow_up_for_retrieval(monkeypatch):
    payload = {
        "paper_task": True,
        "paper_document": {
            "id": "paper-task",
            "title": "Privacy Paper",
            "pages": [
                {"page": 1, "text": "A general introduction to the system. " * 20},
                {"page": 4, "text": "Privacy Disclosure sends collected private data to an attacker endpoint. " * 12},
            ],
        },
        "insights": {},
    }
    monkeypatch.setattr(chat_service.ARTIFACTS, "read_result", lambda _task_id: payload)

    _, chunks, diagnostics = chat_service._task_retrieval(
        "paper-task",
        "这个阶段在哪些页面？",
        [{"role": "user", "content": "Privacy Disclosure 是什么？"}],
    )

    assert diagnostics["query_rewritten"] is True
    assert diagnostics["strategy"] == "lexical"
    assert diagnostics["retrieved_pages"] == [4]
    assert chunks[0]["metadata"]["page_start"] == 4


def test_paper_chat_lexical_ranking_keeps_matching_page_coverage():
    chunks = []
    for page, repeats in [(1, 1), (2, 1), (4, 3), (5, 2)]:
        for index in range(3):
            chunks.append({
                "text": (("Privacy Disclosure " * repeats) + f"details on page {page} chunk {index}"),
                "metadata": {"page_start": page, "chunk_index": index},
            })

    ranked = chat_service._rank(chunks, "Privacy Disclosure", limit=4)

    assert [chunk["metadata"]["page_start"] for chunk in ranked] == [4, 5, 1, 2]


def test_paper_chat_reports_requested_page_without_source(monkeypatch):
    monkeypatch.setattr(chat_service.ARTIFACTS, "read_result", lambda _task_id: _paper_result())

    _, chunks, diagnostics = chat_service._task_retrieval("paper-task", "请只看第 99 页")

    assert chunks == []
    assert diagnostics["strategy"] == "requested_page_missing"


def test_paper_chat_parses_compact_multi_page_request():
    assert chat_service._explicit_page_numbers("请重点核对第4/5页") == [4, 5]


def test_paper_chat_rejects_unmatched_or_uncited_answers(monkeypatch):
    class Completions:
        def create(self, **_kwargs):
            content = (
                '{"answer":"论文证明该机制永远安全 [第 9 页]",'
                '"citations":[{"page":9,"exact_quote":"invented quote"}]}'
            )
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    fake_gpt = SimpleNamespace(
        model="test-model",
        client=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
    )
    monkeypatch.setattr(chat_service.ARTIFACTS, "read_result", lambda _task_id: _paper_result())
    monkeypatch.setattr(chat_service, "_get_gpt", lambda _provider, _model: fake_gpt)

    result = chat_service.chat("paper-task", "是否永远安全？", [], "provider", "model")

    assert result["answer"].startswith("原文证据不足：")
    assert result["sources"] == []
    assert result["grounding_status"] == "citation_rejected"
    assert "未通过原文校验" in result["grounding_detail"]


def test_paper_chat_distinguishes_missing_citation_from_invalid_response():
    payload = _paper_result()
    chunks = chat_service._paper_chunks("paper-task", payload)

    missing = chat_service._ground_task_answer(
        '{"answer":"论文作出了一个结论","citations":[]}',
        payload,
        chunks,
    )
    invalid = chat_service._ground_task_answer("not-json", payload, chunks)

    assert missing["grounding_status"] == "citation_missing"
    assert invalid["grounding_status"] == "response_format_invalid"


def test_paper_chat_rejects_non_paper_artifact(monkeypatch):
    monkeypatch.setattr(chat_service.ARTIFACTS, "read_result", lambda _task_id: {"kind": "legacy"})

    try:
        chat_service._load_task("legacy-task")
    except ValueError as exc:
        assert "论文任务不存在" in str(exc)
    else:  # pragma: no cover - explicit contract assertion
        raise AssertionError("legacy artifacts must not enter paper chat")
