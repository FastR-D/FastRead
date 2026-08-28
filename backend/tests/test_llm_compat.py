from unittest.mock import MagicMock

import pytest

from app.services.llm_compat import create_chat_completion, is_temperature_rejection


def _client_with_side_effect(*effects):
    client = MagicMock()
    client.chat.completions.create.side_effect = list(effects)
    return client


@pytest.mark.parametrize(
    "message",
    [
        "invalid temperature: only 1 is allowed for this model",
        "Unsupported value: 'temperature' is not supported with this model.",
        "temperature is not supported for this model",
    ],
)
def test_temperature_rejection_matches_provider_messages(message):
    assert is_temperature_rejection(Exception(message))


@pytest.mark.parametrize(
    "message",
    ["rate limit exceeded", "invalid api key", "model not found"],
)
def test_temperature_rejection_ignores_unrelated_errors(message):
    assert not is_temperature_rejection(Exception(message))


def test_chat_completion_passes_through_when_accepted():
    client = MagicMock()
    client.chat.completions.create.return_value = "ok"
    result = create_chat_completion(client, model="m", messages=[], temperature=0.2)
    assert result == "ok"
    client.chat.completions.create.assert_called_once_with(
        model="m", messages=[], temperature=0.2
    )


def test_chat_completion_retries_without_rejected_temperature():
    client = _client_with_side_effect(
        Exception("invalid temperature: only 1 is allowed for this model"),
        "ok",
    )
    result = create_chat_completion(client, model="m", messages=[], temperature=0.2)
    assert result == "ok"
    assert client.chat.completions.create.call_count == 2
    assert "temperature" not in client.chat.completions.create.call_args.kwargs


def test_chat_completion_reraises_non_temperature_errors():
    client = _client_with_side_effect(Exception("rate limit exceeded"))
    with pytest.raises(Exception, match="rate limit exceeded"):
        create_chat_completion(client, model="m", messages=[], temperature=0.2)
    assert client.chat.completions.create.call_count == 1


def test_chat_completion_does_not_retry_when_temperature_was_not_set():
    client = _client_with_side_effect(
        Exception("invalid temperature: only 1 is allowed for this model")
    )
    with pytest.raises(Exception, match="invalid temperature"):
        create_chat_completion(client, model="m", messages=[])
    assert client.chat.completions.create.call_count == 1
