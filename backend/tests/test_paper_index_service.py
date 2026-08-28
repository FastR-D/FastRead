from types import SimpleNamespace

from app.repositories.paper_artifacts import PaperArtifactRepository
from app.services.paper_index_service import (
    PROMPT_VERSION,
    STRATEGY_VERSION,
    PaperIndexService,
)
from app.services.paper_search_service import InvertedIndex, PaperSearchService


class FakeElasticsearch:
    url = "http://127.0.0.1:9200"

    def __init__(self):
        self.rebuilt = []

    def health(self):
        return {"configured": True, "available": True, "status": "green"}

    def rebuild(self, papers):
        self.rebuilt = list(papers)
        return len(self.rebuilt)


class FakeCompletion:
    def __call__(self, _client, **kwargs):
        assert kwargs["response_format"] == {"type": "json_object"}
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"keywords":["language model reliability","hallucination","evaluation"]}'
                    )
                )
            ]
        )


def test_offline_pipeline_persists_ai_provenance_and_bulk_rebuilds(monkeypatch, tmp_path):
    artifacts = PaperArtifactRepository(tmp_path / "papers")
    artifacts.write_result(
        "paper-a",
        {
            "paper_document": {
                "title": "How Reliable is Language Model Evaluation?",
                "authors": ["A. Researcher"],
                "pages": [
                    {
                        "page": 1,
                        "text": "Abstract We evaluate language model reliability and hallucination across tasks.\n1 Introduction More text.",
                    }
                ],
                "pdf_url": "/uploads/original.pdf",
            }
        },
    )
    index = InvertedIndex(cache_path=tmp_path / "paper-index.json")
    elasticsearch = FakeElasticsearch()
    search = PaperSearchService(index=index, elasticsearch=elasticsearch, require_proxy=False)
    search._dynamic_connection_config = False
    captured = {"records": []}
    monkeypatch.setattr("app.services.paper_index_service.create_index_job", lambda **kwargs: kwargs)
    monkeypatch.setattr(
        "app.services.paper_index_service.save_keyword_records",
        lambda job_id, records: captured["records"].extend(records),
    )
    monkeypatch.setattr(
        "app.services.paper_index_service.finish_index_job",
        lambda job_id, **values: {"job_id": job_id, **values},
    )
    service = PaperIndexService(
        search_service=search,
        artifacts=artifacts,
        model_factory=lambda **_kwargs: SimpleNamespace(client=object(), model="configured-model"),
        completion_factory=FakeCompletion(),
        task_list_factory=lambda: [{"task_id": "paper-a", "title": "Paper A"}],
    )

    result = service.rebuild(provider_id="provider-1", model_name="configured-model")

    assert result["status"] == "completed"
    assert result["search_backend"] == "elasticsearch"
    assert result["ai_keyword_count"] == 1
    assert result["fallback_count"] == 0
    assert index.metadata["keyword_extraction"]["prompt_version"] == PROMPT_VERSION
    assert index.metadata["keyword_extraction"]["strategy_version"] == STRATEGY_VERSION
    assert elasticsearch.rebuilt[0]["keyword_strategy"] == "ai_abstract_keywords"
    assert captured["records"][0]["execution_status"] == "ai_succeeded"
    assert captured["records"][0]["fallback_reason"] == ""


def test_offline_pipeline_records_explicit_fallback_reason(monkeypatch, tmp_path):
    index = InvertedIndex(cache_path=tmp_path / "paper-index.json")
    index.index_many([{"id": "metadata-only", "title": "Title Without Abstract", "abstract": ""}])
    search = PaperSearchService(index=index, elasticsearch=FakeElasticsearch(), require_proxy=False)
    search._dynamic_connection_config = False
    captured = {"records": []}
    monkeypatch.setattr("app.services.paper_index_service.create_index_job", lambda **kwargs: kwargs)
    monkeypatch.setattr(
        "app.services.paper_index_service.save_keyword_records",
        lambda job_id, records: captured["records"].extend(records),
    )
    monkeypatch.setattr(
        "app.services.paper_index_service.finish_index_job",
        lambda job_id, **values: {"job_id": job_id, **values},
    )

    result = PaperIndexService(
        search_service=search,
        artifacts=PaperArtifactRepository(tmp_path / "papers"),
        task_list_factory=lambda: [],
    ).rebuild(provider_id="provider-1", model_name="configured-model")

    assert result["status"] == "completed_with_fallback"
    assert result["fallback_count"] == 1
    assert result["fallback_reasons"] == {"abstract_missing": 1}
    assert captured["records"][0]["execution_status"] == "deterministic_fallback"
    assert captured["records"][0]["fallback_reason"] == "abstract_missing"
