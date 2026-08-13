"""OpenAI 兼容接口的调用兼容层。

部分模型（如各家推理模型及其网关）只接受服务端默认的 temperature，
请求里带自定义值会直接 400。这里统一处理这类参数兼容回退。
"""

from __future__ import annotations

from app.utils.logger import get_logger


logger = get_logger(__name__)

_TEMPERATURE_REJECTION_TOKENS = (
    "only",          # "invalid temperature: only 1 is allowed for this model"
    "invalid",       # "invalid temperature"
    "unsupported",   # "Unsupported value: 'temperature'"
    "not support",   # "does not support temperature" / "temperature is not supported"
)


def is_temperature_rejection(exc: Exception) -> bool:
    """判断异常是否因为 temperature 取值被模型拒绝。"""
    raw = str(exc).lower()
    return "temperature" in raw and any(
        token in raw for token in _TEMPERATURE_REJECTION_TOKENS
    )


def create_chat_completion(client, **kwargs):
    """调用 ``client.chat.completions.create``，并在 temperature 被拒时去掉该参数重试一次。

    其他异常原样抛出，不掩盖真实错误。
    """
    try:
        return client.chat.completions.create(**kwargs)
    except Exception as exc:
        if "temperature" not in kwargs or not is_temperature_rejection(exc):
            raise
        logger.warning(f"模型拒绝自定义 temperature，改用服务端默认值重试: {exc}")
        fallback = {key: value for key, value in kwargs.items() if key != "temperature"}
        return client.chat.completions.create(**fallback)
