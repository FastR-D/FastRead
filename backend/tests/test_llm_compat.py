from unittest.mock import MagicMock

import pytest

from app.services.llm_compat import create_chat_completion, is_temperature_rejection


def _client_with_side_effect(*effects):
    client = MagicMock()
    client.chat.completions.create.side_effect = list(effects)
    return client


class TestIsTemperatureRejection:
    @pytest.mark.parametrize(
        "message",
        [
            "Error code: 400 - {'error': {'message': 'invalid temperature: only 1 is allowed for this model'}}",
            "Unsupported value: 'temperature' is not supported with this model.",
            "temperature is not supported for this model",
        ],
    )
    def test_matches_common_provider_messages(self, message):
        assert is_temperature_rejection(Exception(message))

    @pytest.mark.parametrize(
        "message",
        [
            "rate limit exceeded",
            "invalid api key",
            "model not found",
        ],
    )
    def test_ignores_unrelated_errors(self, message):
        assert not is_temperature_rejection(Exception(message))


class TestCreateChatCompletion:
    def test_passes_through_when_accepted(self):
        client = MagicMock()
        client.chat.completions.create.return_value = "ok"

        result = create_chat_completion(client, model="m", messages=[], temperature=0.2)

        assert result == "ok"
        client.chat.completions.create.assert_called_once_with(
            model="m", messages=[], temperature=0.2
        )

    def test_retries_without_temperature_when_rejected(self):
        client = _client_with_side_effect(
            Exception("invalid temperature: only 1 is allowed for this model"),
            "ok",
        )

        result = create_chat_completion(client, model="m", messages=[], temperature=0.2)

        assert result == "ok"
        assert client.chat.completions.create.call_count == 2
        second_call_kwargs = client.chat.completions.create.call_args.kwargs
        assert "temperature" not in second_call_kwargs
        assert second_call_kwargs["model"] == "m"

    def test_reraises_non_temperature_errors(self):
        client = _client_with_side_effect(Exception("rate limit exceeded"))

        with pytest.raises(Exception, match="rate limit exceeded"):
            create_chat_completion(client, model="m", messages=[], temperature=0.2)
        assert client.chat.completions.create.call_count == 1

    def test_reraises_temperature_error_when_not_set(self):
        client = _client_with_side_effect(
            Exception("invalid temperature: only 1 is allowed for this model")
        )

        with pytest.raises(Exception, match="invalid temperature"):
            create_chat_completion(client, model="m", messages=[])
        assert client.chat.completions.create.call_count == 1
