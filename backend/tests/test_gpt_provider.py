from app.enmus.exception import ProviderErrorEnum
from app.exceptions.provider import ProviderError
from app.services.gpt_provider import GPTProvider


class FakeFactory:
    captured_config = None

    def from_config(self, config):
        FakeFactory.captured_config = config
        return {"model": config.model_name}


def test_create_builds_gpt_from_provider(monkeypatch):
    monkeypatch.setattr(
        "app.services.gpt_provider.ProviderService.get_provider_by_id",
        lambda provider_id: {
            "api_key": "key",
            "base_url": "http://example.test",
            "type": "openai",
            "name": f"provider-{provider_id}",
        },
    )
    monkeypatch.setattr("app.services.gpt_provider.GPTFactory", FakeFactory)

    gpt = GPTProvider.create(provider_id="p1", model_name="model-a")

    assert gpt == {"model": "model-a"}
    assert FakeFactory.captured_config.api_key == "key"
    assert FakeFactory.captured_config.base_url == "http://example.test"
    assert FakeFactory.captured_config.provider == "openai"
    assert FakeFactory.captured_config.name == "provider-p1"


def test_create_returns_none_when_optional_provider_missing(monkeypatch):
    monkeypatch.setattr("app.services.gpt_provider.ProviderService.get_provider_by_id", lambda _provider_id: None)

    assert GPTProvider.create(provider_id="missing", model_name="model-a", required=False) is None


def test_create_raises_provider_error_when_required_provider_missing(monkeypatch):
    monkeypatch.setattr("app.services.gpt_provider.ProviderService.get_provider_by_id", lambda _provider_id: None)

    try:
        GPTProvider.create(provider_id="missing", model_name="model-a")
    except ProviderError as exc:
        assert exc.code == ProviderErrorEnum.NOT_FOUND
    else:
        raise AssertionError("expected ProviderError")
