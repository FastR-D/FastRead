from app.services.model import ModelService


def _models():
    return [
        {"id": 1, "provider_id": "qwen", "model_name": "glm-5.2"},
        {"id": 2, "provider_id": "qwen", "model_name": "qwen3.8-27b"},
        {"id": 3, "provider_id": "other", "model_name": "qwen3.8-27b"},
    ]


def test_format_models_puts_configured_default_first(monkeypatch):
    monkeypatch.setenv("FASTREAD_DEFAULT_PROVIDER", "qwen")
    monkeypatch.setenv("FASTREAD_DEFAULT_MODEL", "qwen3.8-27b")

    formatted = ModelService._format_models(_models())

    assert [(item["provider_id"], item["model_name"]) for item in formatted] == [
        ("qwen", "qwen3.8-27b"),
        ("qwen", "glm-5.2"),
        ("other", "qwen3.8-27b"),
    ]


def test_format_models_preserves_order_when_default_is_not_configured(monkeypatch):
    monkeypatch.delenv("FASTREAD_DEFAULT_PROVIDER", raising=False)
    monkeypatch.delenv("FASTREAD_DEFAULT_MODEL", raising=False)

    formatted = ModelService._format_models(_models())

    assert [item["id"] for item in formatted] == [1, 2, 3]


def test_format_models_preserves_order_when_default_is_not_enabled(monkeypatch):
    monkeypatch.setenv("FASTREAD_DEFAULT_PROVIDER", "qwen")
    monkeypatch.setenv("FASTREAD_DEFAULT_MODEL", "missing-model")

    formatted = ModelService._format_models(_models())

    assert [item["id"] for item in formatted] == [1, 2, 3]
