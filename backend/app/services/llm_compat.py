"""Compatibility helpers for OpenAI-style chat completion endpoints.

The provider records accepted by FastRead are intentionally broader than the
official OpenAI API.  A few compatible endpoints return JSON inside Markdown
or explanatory prose, and some reasoning models expose an empty ``content``
field after spending the response budget on hidden reasoning.  Keep those wire
quirks here so product services can continue to validate one strict JSON object
instead of each growing its own permissive parser.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re

from app.utils.logger import get_logger


logger = get_logger(__name__)

_TEMPERATURE_REJECTION_TOKENS = (
    "only",
    "invalid",
    "unsupported",
    "not support",
)

_PARAMETER_REJECTION_TOKENS = (
    "invalid",
    "unsupported",
    "not support",
    "unknown",
    "unrecognized",
)


class StructuredOutputError(ValueError):
    """A model response could not be recovered as one JSON object."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class StructuredChatResult:
    payload: dict
    response: object
    repaired: bool
    response_format_used: bool


def is_temperature_rejection(exc: Exception) -> bool:
    """Return whether a provider rejected the requested temperature value."""
    raw = str(exc).lower()
    return "temperature" in raw and any(
        token in raw for token in _TEMPERATURE_REJECTION_TOKENS
    )


def _is_parameter_rejection(exc: Exception, parameter: str) -> bool:
    raw = str(exc or "").lower()
    return parameter.lower() in raw and any(
        token in raw for token in _PARAMETER_REJECTION_TOKENS
    )


def response_format_is_unsupported(exc: Exception) -> bool:
    """Return true only for JSON-mode compatibility errors.

    Transport, authentication, quota and rate-limit errors must never be
    relabelled as a provider compatibility problem.
    """

    status_code = getattr(exc, "status_code", None)
    text = str(exc or "").lower()
    mentions_format = (
        "response_format" in text
        or "json_object" in text
        or "json mode" in text
    )
    mentions_support = any(token in text for token in _PARAMETER_REJECTION_TOKENS)
    return bool(
        mentions_format
        and mentions_support
        and status_code in {None, 400, 404, 422}
    )


def _dashscope_structured_options(client, model: object) -> dict:
    """Disable long-form reasoning for DashScope structured-output calls.

    DashScope-compatible reasoning models can legally return a populated
    ``reasoning_content`` and an empty final ``content`` when the completion
    budget is exhausted.  Reports need a schema-conforming final answer, not a
    reasoning transcript.  The option is deliberately scoped to DashScope and
    is removed once if an endpoint explicitly rejects it.
    """

    base_url = str(getattr(client, "base_url", "") or "").lower()
    model_name = str(model or "").lower()
    if "dashscope.aliyuncs.com" not in base_url:
        return {}
    if not any(token in model_name for token in ("glm", "qwen", "qwq")):
        return {}
    return {"extra_body": {"enable_thinking": False}}


def create_chat_completion(client, **kwargs):
    """Create a completion with bounded compatible-parameter fallback.

    Some reasoning models only accept their server-side default temperature.
    Unrelated errors are deliberately re-raised unchanged.
    """

    request = dict(kwargs)
    removed: set[str] = set()
    while True:
        try:
            return client.chat.completions.create(**request)
        except Exception as exc:
            if (
                "temperature" in request
                and "temperature" not in removed
                and is_temperature_rejection(exc)
            ):
                removed.add("temperature")
                request.pop("temperature", None)
                logger.warning(
                    f"模型拒绝自定义 temperature，改用服务端默认值重试: {exc}"
                )
                continue
            extra_body = request.get("extra_body")
            if (
                isinstance(extra_body, dict)
                and "enable_thinking" in extra_body
                and "enable_thinking" not in removed
                and _is_parameter_rejection(exc, "enable_thinking")
            ):
                removed.add("enable_thinking")
                remaining = {
                    key: value
                    for key, value in extra_body.items()
                    if key != "enable_thinking"
                }
                if remaining:
                    request["extra_body"] = remaining
                else:
                    request.pop("extra_body", None)
                logger.warning(
                    f"模型拒绝 enable_thinking 兼容参数，移除后重试: {exc}"
                )
                continue
            raise


def _content_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for block in value:
        if isinstance(block, str):
            parts.append(block)
            continue
        if isinstance(block, dict):
            text = block.get("text") or block.get("content")
        else:
            text = getattr(block, "text", None) or getattr(block, "content", None)
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


def response_text_candidates(response) -> list[str]:
    """Return final content first and reasoning only as an empty-final fallback."""

    try:
        message = response.choices[0].message
    except (AttributeError, IndexError, TypeError) as exc:
        raise StructuredOutputError(
            "missing_message", "模型响应缺少 choices[0].message"
        ) from exc
    content = _content_text(getattr(message, "content", None)).strip()
    if content:
        return [content]
    reasoning = _content_text(
        getattr(message, "reasoning_content", None)
        or getattr(message, "reasoning", None)
    ).strip()
    return [reasoning] if reasoning else []


def parse_json_object(value: object) -> dict:
    """Parse one JSON object, accepting fences or bounded surrounding prose."""

    if isinstance(value, dict):
        return value
    text = str(value or "").lstrip("\ufeff").strip()
    if not text:
        raise StructuredOutputError("empty_response", "模型返回了空内容")
    fenced = re.fullmatch(
        r"```(?:json)?\s*(.*?)\s*```",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if fenced:
        text = fenced.group(1).strip()
    try:
        decoded = json.loads(text)
        if isinstance(decoded, dict):
            return decoded
        raise StructuredOutputError("not_object", "模型响应必须是 JSON 对象")
    except json.JSONDecodeError as direct_error:
        decoder = json.JSONDecoder()
        for match in re.finditer(r"\{", text):
            try:
                decoded, _end = decoder.raw_decode(text, match.start())
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, dict):
                return decoded
        preview = re.sub(r"\s+", " ", text)[:200]
        raise StructuredOutputError(
            "invalid_json",
            f"模型返回内容不是有效 JSON 对象: {direct_error}; 内容预览={preview!r}",
        ) from direct_error


def parse_json_chat_response(response) -> dict:
    candidates = response_text_candidates(response)
    if not candidates:
        finish_reason = ""
        try:
            finish_reason = str(response.choices[0].finish_reason or "")
        except (AttributeError, IndexError, TypeError):
            pass
        suffix = f"（finish_reason={finish_reason}）" if finish_reason else ""
        raise StructuredOutputError(
            "empty_response",
            "模型返回了空的最终内容" + suffix,
        )
    return parse_json_object(candidates[0])


def create_structured_chat_completion(
    client,
    *,
    repair: bool = True,
    repair_output_limit: int = 16_000,
    completion_factory=None,
    **kwargs,
) -> StructuredChatResult:
    """Request and validate a JSON object with one bounded repair attempt."""

    complete = completion_factory or create_chat_completion
    request = dict(kwargs)
    if "extra_body" not in request:
        request.update(_dashscope_structured_options(client, request.get("model")))
    response_format_used = True
    try:
        response = complete(
            client,
            **request,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        if not response_format_is_unsupported(exc):
            raise
        response_format_used = False
        logger.warning(
            f"模型明确不支持 JSON response_format，回退普通 JSON 提示: {exc}"
        )
        response = complete(client, **request)

    try:
        payload = parse_json_chat_response(response)
        return StructuredChatResult(payload, response, False, response_format_used)
    except StructuredOutputError:
        if not repair:
            raise

    try:
        candidates = response_text_candidates(response)
    except StructuredOutputError:
        candidates = []
    previous = candidates[0][:repair_output_limit] if candidates else ""
    messages = list(request.get("messages") or [])
    if previous:
        messages.append({"role": "assistant", "content": previous})
    messages.append(
        {
            "role": "user",
            "content": (
                "上一次响应为空或不是单个有效 JSON 对象。请重新完成原任务，只输出一个"
                "符合既定结构的 JSON 对象；不要 Markdown 代码围栏、解释或前后缀。"
            ),
        }
    )
    repair_request = {**request, "messages": messages}
    try:
        if response_format_used:
            repaired_response = complete(
                client,
                **repair_request,
                response_format={"type": "json_object"},
            )
        else:
            repaired_response = complete(client, **repair_request)
        payload = parse_json_chat_response(repaired_response)
    except StructuredOutputError as repair_error:
        raise StructuredOutputError(
            repair_error.reason,
            f"模型结构化输出修复失败: {repair_error}",
        ) from repair_error
    return StructuredChatResult(payload, repaired_response, True, response_format_used)
