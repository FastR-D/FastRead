from types import SimpleNamespace

from app.repositories.paper_artifacts import PaperArtifactRepository
from app.services import chat_service
from app.services.paper_task_service import PaperTaskService
from app.services.vector_store import _chunk_paper_pages


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

    assert result["answer"] == "原文证据不足"
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

    assert result == {
        "answer": "原文证据不足",
        "sources": [],
        "grounding_status": "citation_rejected",
    }


def test_paper_chat_rejects_non_paper_artifact(monkeypatch):
    monkeypatch.setattr(chat_service.ARTIFACTS, "read_result", lambda _task_id: {"kind": "legacy"})

    try:
        chat_service._load_task("legacy-task")
    except ValueError as exc:
        assert "论文任务不存在" in str(exc)
    else:  # pragma: no cover - explicit contract assertion
        raise AssertionError("legacy artifacts must not enter paper chat")
