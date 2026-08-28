"""Compatibility helpers for OpenAI-style chat completion endpoints."""

from __future__ import annotations

from app.utils.logger import get_logger


logger = get_logger(__name__)

_TEMPERATURE_REJECTION_TOKENS = (
    "only",
    "invalid",
    "unsupported",
    "not support",
)


def is_temperature_rejection(exc: Exception) -> bool:
    """Return whether a provider rejected the requested temperature value."""
    raw = str(exc).lower()
    return "temperature" in raw and any(
        token in raw for token in _TEMPERATURE_REJECTION_TOKENS
    )


def create_chat_completion(client, **kwargs):
    """Create a completion, retrying once without a rejected temperature.

    Some reasoning models only accept their server-side default temperature.
    Unrelated errors are deliberately re-raised unchanged.
    """
    try:
        return client.chat.completions.create(**kwargs)
    except Exception as exc:
        if "temperature" not in kwargs or not is_temperature_rejection(exc):
            raise
        logger.warning(f"模型拒绝自定义 temperature，改用服务端默认值重试: {exc}")
        fallback = {key: value for key, value in kwargs.items() if key != "temperature"}
        return client.chat.completions.create(**fallback)
