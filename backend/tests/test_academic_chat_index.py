from types import SimpleNamespace

from app.repositories.note_artifacts import NoteArtifactRepository
from app.services import chat_service, note_task_service
from app.services.note_task_service import NoteTaskService
from app.services.vector_store import _chunk_paper_pages


def _paper_result() -> dict:
    text = "This paper evaluates a security mechanism with a controlled experiment. " * 8
    return {
        "paper_task": True,
        "audio_meta": {"title": "Example Paper", "platform": "paper", "raw_info": {}},
        "transcript": {"full_text": text, "segments": []},
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


def test_paper_chat_does_not_duplicate_full_text_as_unpaged_transcript(monkeypatch):
    monkeypatch.setattr(chat_service.ARTIFACTS, "read_result", lambda _task_id: _paper_result())

    chunks = chat_service._load_task_chunks("paper-task")
    source_types = [chunk["metadata"]["source_type"] for chunk in chunks]

    assert "paper_page" in source_types
    assert "transcript" not in source_types


def test_deleting_paper_artifacts_removes_only_owned_uuid_upload(monkeypatch, tmp_path):
    output_dir = tmp_path / "output"
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()
    filename = "a" * 32 + ".pdf"
    uploaded = uploads_dir / filename
    uploaded.write_bytes(b"pdf")
    unrelated = uploads_dir / "manual.pdf"
    unrelated.write_bytes(b"keep")

    artifacts = NoteArtifactRepository(output_dir)
    artifacts.write_result("paper-task", {
        "paper_task": True,
        "paper_document": {"pdf_url": f"/uploads/{filename}"},
    })
    monkeypatch.setattr(
        note_task_service,
        "get_settings",
        lambda: SimpleNamespace(uploads_path="/uploads", uploads_dir=uploads_dir),
    )
    service = NoteTaskService(artifacts, vector_store_factory=lambda: SimpleNamespace(delete_index=lambda _id: None))

    assert service.delete_task_artifacts("paper-task") == 2
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


def test_online_verification_merge_preserves_concurrent_reading_report(monkeypatch, tmp_path):
    artifacts = NoteArtifactRepository(tmp_path)
    artifacts.write_result("task-a", {
        "markdown": "# Note",
        "transcript": {"full_text": "claim context"},
        "audio_meta": {"title": "title", "raw_info": {}},
        "insights": {"verification": {"claims": [{"claim": "claim"}]}},
    })
    service = NoteTaskService(artifacts, vector_store_factory=lambda: SimpleNamespace(delete_index=lambda _id: None))

    def fake_verify(verification, **_kwargs):
        artifacts.update_result("task-a", lambda latest: {
            **latest,
            "insights": {
                **(latest.get("insights") or {}),
                "reading_report": {"title": "concurrent report"},
                "personal_summary": {"content": "keep me"},
            },
        })
        return {"claims": verification["claims"], "online": True}

    monkeypatch.setattr(note_task_service, "verify_claims_online", fake_verify)

    assert service.verify_task_online(task_id="task-a")["ok"] is True
    saved = artifacts.read_result("task-a")
    assert saved["insights"]["verification"]["online"] is True
    assert saved["insights"]["reading_report"]["title"] == "concurrent report"
    assert saved["insights"]["personal_summary"]["content"] == "keep me"
