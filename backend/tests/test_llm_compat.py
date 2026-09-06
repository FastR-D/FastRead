from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.llm_compat import (
    StructuredOutputError,
    create_chat_completion,
    create_structured_chat_completion,
    is_temperature_rejection,
    parse_json_object,
)


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


def _response(content, *, reasoning_content="", finish_reason="stop"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(
                    content=content,
                    reasoning_content=reasoning_content,
                ),
            )
        ]
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"ok": true}', {"ok": True}),
        ('```json\n{"ok": true}\n```', {"ok": True}),
        ('结果如下：\n{"ok": true}\n以上。', {"ok": True}),
    ],
)
def test_parse_json_object_accepts_compatible_wrappers(raw, expected):
    assert parse_json_object(raw) == expected


def test_parse_json_object_rejects_non_object_and_malformed_output():
    with pytest.raises(StructuredOutputError, match="JSON 对象"):
        parse_json_object('[1, 2]')
    with pytest.raises(StructuredOutputError) as error:
        parse_json_object("not json")
    assert error.value.reason == "invalid_json"


def test_structured_completion_uses_reasoning_json_when_final_content_is_empty():
    client = MagicMock()
    client.chat.completions.create.return_value = _response(
        "", reasoning_content='analysis then {"ok": true}'
    )

    result = create_structured_chat_completion(
        client, model="m", messages=[], temperature=0.2
    )

    assert result.payload == {"ok": True}
    assert result.repaired is False


def test_structured_completion_repairs_empty_response_once():
    client = _client_with_side_effect(
        _response("", finish_reason="length"),
        _response('{"ok": true}'),
    )

    result = create_structured_chat_completion(
        client, model="m", messages=[{"role": "user", "content": "return json"}]
    )

    assert result.payload == {"ok": True}
    assert result.repaired is True
    assert client.chat.completions.create.call_count == 2
    repair_messages = client.chat.completions.create.call_args.kwargs["messages"]
    assert "上一次响应为空" in repair_messages[-1]["content"]


def test_dashscope_glm_structured_completion_disables_thinking():
    client = MagicMock()
    client.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1/"
    client.chat.completions.create.return_value = _response('{"ok": true}')

    create_structured_chat_completion(client, model="glm-5.2", messages=[])

    assert client.chat.completions.create.call_args.kwargs["extra_body"] == {
        "enable_thinking": False
    }
